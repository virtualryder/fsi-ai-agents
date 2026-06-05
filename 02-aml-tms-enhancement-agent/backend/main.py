"""
FastAPI backend — exposes the LangGraph scoring pipeline as a REST API.

The Next.js frontend calls these endpoints. The Python scoring code
(agent/, scoring/, tools/) is unchanged — this is purely an API wrapper.

In-memory state is used for the demo. Production: replace with
Redis (scored_alerts cache) + PostgreSQL (suppression log).
"""
import sys
import os
import asyncio
import uuid
from datetime import datetime
from typing import Optional

# Add parent directory to path so we can import agent/, scoring/, tools/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

app = FastAPI(
    title="AML/TMS Enhancement Agent API",
    description="Pre-queue false positive reduction for financial crime compliance",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory state ────────────────────────────────────────────────────────────
_scored_alerts: dict[str, dict] = {}          # alert_id → scoring result
_scoring_jobs: dict[str, dict] = {}           # job_id → {status, alert_ids, progress}
_thresholds: dict[str, float] = {
    "suppress": float(os.getenv("SUPPRESS_THRESHOLD", "85")),
    "downgrade": float(os.getenv("DOWNGRADE_THRESHOLD", "60")),
    "escalate": float(os.getenv("ESCALATE_THRESHOLD", "15")),
}


# ── Request / response models ──────────────────────────────────────────────────

class ThresholdsUpdate(BaseModel):
    suppress: float
    downgrade: float
    escalate: float


class ScoreAllRequest(BaseModel):
    alert_ids: Optional[list[str]] = None  # None = score all pending


# ── Alert endpoints ────────────────────────────────────────────────────────────

@app.get("/api/alerts/pending")
async def get_pending_alerts(limit: int = 50):
    """Load pending TMS alerts from the connector (fixture data in dev)."""
    from tools.tms_connector import get_pending_alerts as _load
    alerts = await asyncio.to_thread(_load, limit)
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/api/alerts/{alert_id}/score")
async def score_alert(alert_id: str):
    """
    Score a single alert through the LangGraph pipeline.
    Runs synchronously in a thread pool (LLM call may take 5-15s).
    """
    # Load alert from TMS
    from tools.tms_connector import get_alert_details
    alert = await asyncio.to_thread(get_alert_details, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    # Apply current threshold env vars before scoring
    os.environ["SUPPRESS_THRESHOLD"] = str(_thresholds["suppress"])
    os.environ["DOWNGRADE_THRESHOLD"] = str(_thresholds["downgrade"])
    os.environ["ESCALATE_THRESHOLD"] = str(_thresholds["escalate"])

    result = await asyncio.to_thread(_run_graph, alert)
    _scored_alerts[alert_id] = _serialize_result(result)
    return _scored_alerts[alert_id]


@app.post("/api/alerts/score-all")
async def score_all_alerts(
    request: ScoreAllRequest,
    background_tasks: BackgroundTasks,
):
    """
    Kick off a background job to score all pending alerts.
    Returns a job_id; poll /api/jobs/{job_id} for progress.
    """
    from tools.tms_connector import get_pending_alerts as _load, get_alert_details
    pending = await asyncio.to_thread(_load, 50)

    if request.alert_ids:
        pending = [a for a in pending if a["alert_id"] in request.alert_ids]

    job_id = str(uuid.uuid4())[:8].upper()
    _scoring_jobs[job_id] = {
        "status": "RUNNING",
        "total": len(pending),
        "completed": 0,
        "alert_ids": [a["alert_id"] for a in pending],
        "started_at": datetime.utcnow().isoformat() + "Z",
    }

    background_tasks.add_task(_score_all_background, job_id, pending)
    return {"job_id": job_id, "total": len(pending), "status": "RUNNING"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Poll scoring job progress."""
    job = _scoring_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@app.get("/api/alerts/scored")
async def get_scored_alerts():
    """Return all alerts that have been scored this session."""
    return {"alerts": list(_scored_alerts.values()), "count": len(_scored_alerts)}


@app.get("/api/alerts/scored/{alert_id}")
async def get_scored_alert(alert_id: str):
    """Return the scoring result for a specific alert."""
    result = _scored_alerts.get(alert_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"No scoring result for alert {alert_id}")
    return result


# ── Metrics endpoint ───────────────────────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    """Compute FP reduction metrics from scored alerts + suppression engine."""
    from tools.suppression_engine import get_suppression_stats
    stats = await asyncio.to_thread(get_suppression_stats, 30)

    # Augment with session-level distribution
    decisions = [
        r.get("routing", {}).get("decision", "UNKNOWN")
        for r in _scored_alerts.values()
    ]
    fp_probs = [
        r.get("routing", {}).get("fp_probability", 0)
        for r in _scored_alerts.values()
    ]

    from collections import Counter
    dist = dict(Counter(decisions))

    return {
        **stats,
        "session_decision_distribution": dist,
        "session_fp_probabilities": fp_probs,
        "session_alert_count": len(_scored_alerts),
    }


# ── Suppression audit endpoints ────────────────────────────────────────────────

@app.get("/api/suppression")
async def get_suppression_log(days: int = 90):
    """Return all suppression records for the last N days."""
    from tools.suppression_engine import get_suppression_log as _log
    records = await asyncio.to_thread(_log, days)
    return {"records": records, "count": len(records)}


# ── Threshold endpoints ────────────────────────────────────────────────────────

@app.get("/api/thresholds")
async def get_thresholds():
    """Return current scoring thresholds."""
    from scoring.threshold_manager import ALERT_TYPE_OVERRIDES
    overrides = [
        {
            "alert_type": at,
            "suppress": t.suppress,
            "downgrade": t.downgrade,
            "escalate": t.escalate,
        }
        for at, t in ALERT_TYPE_OVERRIDES.items()
    ]
    return {"thresholds": _thresholds, "alert_type_overrides": overrides}


@app.put("/api/thresholds")
async def update_thresholds(body: ThresholdsUpdate):
    """Update scoring thresholds (BSA Officer action — logged in production)."""
    if body.suppress <= body.downgrade:
        raise HTTPException(
            status_code=422,
            detail="suppress threshold must be greater than downgrade threshold",
        )
    if body.downgrade <= body.escalate:
        raise HTTPException(
            status_code=422,
            detail="downgrade threshold must be greater than escalate threshold",
        )
    _thresholds["suppress"] = body.suppress
    _thresholds["downgrade"] = body.downgrade
    _thresholds["escalate"] = body.escalate
    os.environ["SUPPRESS_THRESHOLD"] = str(body.suppress)
    os.environ["DOWNGRADE_THRESHOLD"] = str(body.downgrade)
    os.environ["ESCALATE_THRESHOLD"] = str(body.escalate)
    return {"thresholds": _thresholds, "updated_at": datetime.utcnow().isoformat() + "Z"}


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


# ── Private helpers ────────────────────────────────────────────────────────────

def _run_graph(alert: dict) -> dict:
    """Run the LangGraph scoring pipeline synchronously (called in thread pool)."""
    from agent.graph import build_graph
    app_graph = build_graph()
    result = app_graph.invoke(
        {"raw_alert": alert},
        config={"configurable": {"thread_id": alert["alert_id"]}},
    )
    return result


def _serialize_result(result: dict) -> dict:
    """Make the result JSON-serializable (remove non-serializable objects)."""
    import json

    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    return _clean(result)


async def _score_all_background(job_id: str, alerts: list[dict]):
    """Background task: score all alerts sequentially, update job progress."""
    for i, alert in enumerate(alerts):
        try:
            result = await asyncio.to_thread(_run_graph, alert)
            _scored_alerts[alert["alert_id"]] = _serialize_result(result)
        except Exception as exc:
            _scored_alerts[alert["alert_id"]] = {
                "alert_id": alert["alert_id"],
                "error": str(exc),
                "queue_action": "error",
                "routing": {"decision": "PASS_THROUGH", "fp_probability": 50},
            }
        _scoring_jobs[job_id]["completed"] = i + 1

    _scoring_jobs[job_id]["status"] = "COMPLETE"
    _scoring_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat() + "Z"
