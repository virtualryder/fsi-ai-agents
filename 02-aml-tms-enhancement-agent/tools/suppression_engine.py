"""
Suppression Engine — records and manages alert disposition decisions.

Every suppression must produce an auditable record per BSA and SR 11-7.
Regulators can examine suppression logs during exam — this is the
equivalent of a "do not file" decision and must be defensible.

Production: persist to append-only DynamoDB table with IAM policy
that denies UpdateItem and DeleteItem (true WORM compliance).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory store (replace with DynamoDB / PostgreSQL in production)
_SUPPRESSION_LOG: list[dict] = []
_DISPOSITION_LOG: list[dict] = []


def record_suppression(
    alert_id: str,
    customer_id: str,
    alert_type: str,
    fp_probability: float,
    confidence: float,
    primary_reason: str,
    suppression_factors: list[str],
    pass_through_factors: list[str],
    justification_narrative: str,
    score_breakdown: dict,
    thresholds_used: dict,
) -> dict:
    """
    Create a formal suppression record for a suppressed alert.

    Returns the record dict including the suppression_id and review_date.

    The 90-day review requirement: suppressed alerts must be reviewed
    within 90 days to validate the suppression was appropriate.
    (Based on FinCEN SAR lookback and SR 11-7 model monitoring requirements.)
    """
    suppression_id = f"SUP-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat() + "Z"
    review_date = (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%d")

    record = {
        "suppression_id": suppression_id,
        "alert_id": alert_id,
        "customer_id": customer_id,
        "alert_type": alert_type,
        "fp_probability": fp_probability,
        "confidence": confidence,
        "primary_reason": primary_reason,
        "suppression_factors": suppression_factors,
        "pass_through_factors": pass_through_factors,
        "justification_narrative": justification_narrative,
        "score_breakdown": score_breakdown,
        "thresholds_used": thresholds_used,
        "suppressed_at": timestamp,
        "mandatory_review_date": review_date,
        "review_status": "PENDING",
        "reviewed_by": None,
        "review_outcome": None,
    }

    _SUPPRESSION_LOG.append(record)
    logger.info(
        "Suppression recorded | id=%s alert=%s fp_prob=%.0f%% review_due=%s",
        suppression_id, alert_id, fp_probability, review_date,
    )
    return record


def record_downgrade(
    alert_id: str,
    customer_id: str,
    original_priority: str,
    new_priority: str,
    fp_probability: float,
    reason: str,
    justification: str,
) -> dict:
    """Record a priority downgrade. Alert still reaches analysts."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    record = {
        "disposition_id": f"DG-{uuid.uuid4().hex[:8].upper()}",
        "action": "DOWNGRADE",
        "alert_id": alert_id,
        "customer_id": customer_id,
        "original_priority": original_priority,
        "new_priority": new_priority,
        "fp_probability": fp_probability,
        "reason": reason,
        "justification": justification,
        "recorded_at": timestamp,
    }
    _DISPOSITION_LOG.append(record)
    logger.info(
        "Downgrade recorded | alert=%s %s→%s fp_prob=%.0f%%",
        alert_id, original_priority, new_priority, fp_probability,
    )
    return record


def record_pass_through(
    alert_id: str,
    customer_id: str,
    priority: str,
    fp_probability: float,
    reason: str,
) -> dict:
    """Record a pass-through (alert queued for analyst at assigned priority)."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    record = {
        "disposition_id": f"PT-{uuid.uuid4().hex[:8].upper()}",
        "action": "PASS_THROUGH",
        "alert_id": alert_id,
        "customer_id": customer_id,
        "priority": priority,
        "fp_probability": fp_probability,
        "reason": reason,
        "recorded_at": timestamp,
    }
    _DISPOSITION_LOG.append(record)
    logger.info(
        "Pass-through recorded | alert=%s priority=%s fp_prob=%.0f%%",
        alert_id, priority, fp_probability,
    )
    return record


def record_escalation(
    alert_id: str,
    customer_id: str,
    fp_probability: float,
    reason: str,
) -> dict:
    """Record an escalation (fast-tracked to senior analyst / FCU)."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    record = {
        "disposition_id": f"ESC-{uuid.uuid4().hex[:8].upper()}",
        "action": "ESCALATE",
        "alert_id": alert_id,
        "customer_id": customer_id,
        "fp_probability": fp_probability,
        "reason": reason,
        "recorded_at": timestamp,
    }
    _DISPOSITION_LOG.append(record)
    logger.info(
        "Escalation recorded | alert=%s fp_prob=%.0f%%",
        alert_id, fp_probability,
    )
    return record


def get_suppression_log(days: int = 30) -> list[dict]:
    """Return all suppression records from the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return [
        r for r in _SUPPRESSION_LOG
        if datetime.fromisoformat(r["suppressed_at"].rstrip("Z")) >= cutoff
    ]


def get_suppression_stats(days: int = 30) -> dict:
    """
    Return summary statistics used on the Streamlit dashboard.

    Includes: total processed, suppressed, downgraded, passed-through, escalated.
    """
    log = get_suppression_log(days)
    all_dispositions = [r for r in _DISPOSITION_LOG]

    suppressed = len(log)
    downgraded = sum(1 for r in all_dispositions if r.get("action") == "DOWNGRADE")
    passed = sum(1 for r in all_dispositions if r.get("action") == "PASS_THROUGH")
    escalated = sum(1 for r in all_dispositions if r.get("action") == "ESCALATE")
    total = suppressed + downgraded + passed + escalated

    suppression_rate = suppressed / total if total > 0 else 0.0
    avg_fp_prob = (
        sum(r["fp_probability"] for r in log) / suppressed if suppressed > 0 else 0.0
    )

    # Analyst hours saved: assume 25 min per alert reviewed
    analyst_hours_saved = suppressed * 25 / 60

    return {
        "total_processed": total,
        "suppressed": suppressed,
        "downgraded": downgraded,
        "passed_through": passed,
        "escalated": escalated,
        "suppression_rate": suppression_rate,
        "avg_fp_probability": avg_fp_prob,
        "analyst_hours_saved": analyst_hours_saved,
        "pending_90day_review": sum(
            1 for r in log if r.get("review_status") == "PENDING"
        ),
    }
