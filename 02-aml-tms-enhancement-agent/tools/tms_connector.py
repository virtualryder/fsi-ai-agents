"""
TMS Connector — integration with Transaction Monitoring Systems.

Supports: Actimize | Verafin | NICE | Oracle Mantas

In development/demo mode, all functions return fixture data from
data/fixtures/sample_pending_alerts.json.

Integration point: replace the _load_fixture_* functions with real
vendor API calls. Each vendor uses slightly different auth and endpoint
conventions — see docs/integration-guide.md for specifics.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from agent.state import RawAlert

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).parent.parent / "data" / "fixtures"
_ALERTS_FIXTURE = _FIXTURES_DIR / "sample_pending_alerts.json"
_HISTORY_FIXTURE = _FIXTURES_DIR / "historical_outcomes.json"

# In-memory store for disposition updates (mock only)
_DISPOSITIONS: dict[str, dict] = {}


# ── Public interface ──────────────────────────────────────────────────────────

def get_pending_alerts(limit: int = 50) -> list[RawAlert]:
    """
    Pull raw TMS alerts that have NOT yet entered the analyst queue.

    These are alerts in "PENDING_SCORING" status — they have been generated
    by the TMS rule engine but are held in a pre-queue staging area for
    AI scoring before release to analysts.

    Production integration:
      Actimize:     GET /api/v1/alerts?status=PENDING_AI_REVIEW&limit={limit}
      Verafin:      GET /alerts/queue/prestage?max={limit}
      NICE:         GET /actimize-alert-api/alerts?stage=PRESCORING&pageSize={limit}
      Oracle Mantas: GET /mantas/api/alerts?alertStatus=NEW&assignedTo=AI_LAYER&limit={limit}
    """
    vendor = os.getenv("TMS_VENDOR", "actimize")
    logger.info("Fetching pending alerts from %s (limit=%d)", vendor, limit)

    alerts = _load_fixture_alerts()
    return alerts[:limit]


def get_alert_details(alert_id: str) -> Optional[RawAlert]:
    """
    Fetch full alert payload for a specific alert ID.

    Production integration: GET /api/v1/alerts/{alert_id}
    """
    alerts = _load_fixture_alerts()
    for alert in alerts:
        if alert["alert_id"] == alert_id:
            return alert
    logger.warning("Alert %s not found in fixture data", alert_id)
    return None


def get_rule_metadata(rule_id: str) -> dict:
    """
    Return metadata about a TMS rule: description, typical FP rate, date created.

    Production integration: GET /api/v1/rules/{rule_id}
    """
    history = _load_fixture_history()
    fp_rate = history.get("rule_fp_rates", {}).get(rule_id, 0.5)
    return {
        "rule_id": rule_id,
        "historical_fp_rate": fp_rate,
        "description": f"TMS rule {rule_id}",
        "active": True,
    }


def update_alert_disposition(
    alert_id: str,
    disposition: str,         # "SUPPRESSED" | "DOWNGRADED" | "QUEUED" | "ESCALATED"
    new_priority: Optional[str],  # HIGH | MEDIUM | LOW | None (for suppressed)
    reason: str,
    fp_probability: float,
) -> bool:
    """
    Send the scoring decision back to the TMS so it can update the alert record.

    For SUPPRESSED alerts: TMS moves the alert to a suppression audit queue
    (visible to BSA Officers) rather than deleting it.

    For DOWNGRADED alerts: TMS updates the priority field before releasing to analysts.

    For QUEUED/ESCALATED: TMS releases the alert at the specified priority.

    Production integration:
      PATCH /api/v1/alerts/{alert_id}
      Body: {"disposition": disposition, "priority": new_priority,
             "aiReason": reason, "fpProbability": fp_probability}

    Returns True on success.
    """
    _DISPOSITIONS[alert_id] = {
        "alert_id": alert_id,
        "disposition": disposition,
        "new_priority": new_priority,
        "reason": reason,
        "fp_probability": fp_probability,
    }
    logger.info(
        "TMS updated | alert=%s disposition=%s priority=%s fp_prob=%.0f%%",
        alert_id, disposition, new_priority, fp_probability,
    )
    return True


def get_disposition_log() -> list[dict]:
    """Return all disposition updates sent to TMS this session (mock only)."""
    return list(_DISPOSITIONS.values())


# ── Fixtures (development / demo) ─────────────────────────────────────────────

def _load_fixture_alerts() -> list[RawAlert]:
    try:
        with open(_ALERTS_FIXTURE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Fixture file not found: %s", _ALERTS_FIXTURE)
        return []


def _load_fixture_history() -> dict:
    try:
        with open(_HISTORY_FIXTURE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Fixture file not found: %s", _HISTORY_FIXTURE)
        return {}
