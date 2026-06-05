# tools/case_manager.py
# ============================================================
# Case Management & Audit Log
#
# Creates and updates fraud cases, maintains the examination-ready
# append-only JSONL audit log.
#
# Retention:
#   BSA 31 U.S.C. § 5318: 5-year minimum record retention.
#   Audit log is append-only — records are never modified or deleted.
#
# Case workflow:
#   OPEN → UNDER_REVIEW → CLOSED (CONFIRMED_FRAUD | FALSE_POSITIVE)
#                       → ESCALATED → CLOSED
# ============================================================

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default audit log path (override with AUDIT_LOG_PATH env var)
_DEFAULT_AUDIT_LOG = Path(__file__).parent.parent / "data" / "audit_log.jsonl"


def create_case_record(
    transaction_id: str,
    account_id: str,
    customer_id: str,
    fraud_decision: str,
    composite_score: float,
    fraud_type: Optional[str] = None,
    analyst_queue: Optional[str] = None,
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new fraud case record in the case management system.

    Case ID format: FRAUD-YYYYMMDD-XXXXXXXX (8-char UUID segment)
    In production: insert into case management DB (Salesforce, ServiceNow, etc.)

    Returns the created case record dict.
    """
    if not case_id:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        case_id = f"FRAUD-{date_str}-{str(uuid.uuid4())[:8].upper()}"

    case = {
        "case_id": case_id,
        "transaction_id": transaction_id,
        "account_id": account_id,
        "customer_id": customer_id,
        "fraud_decision": fraud_decision,
        "composite_score": composite_score,
        "suspected_fraud_type": fraud_type or "UNKNOWN",
        "analyst_queue": analyst_queue or "CARD_FRAUD",
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "retention_date": _retention_date(),
        "regulatory_basis": "BSA 31 U.S.C. § 5318 — 5-year fraud case retention",
    }

    # Write to audit log
    _append_audit_log(case_id, "CASE_CREATED", case)

    logger.info(f"[case_manager] Case {case_id} created for transaction {transaction_id}")
    return case


def update_case_with_analyst_decision(
    case_id: str,
    analyst_id: str,
    analyst_decision: str,
    analyst_notes: str,
    transaction_id: str,
) -> Dict[str, Any]:
    """
    Record analyst determination on an open case.

    analyst_decision options:
      CONFIRMED_FRAUD   — Transaction is confirmed fraudulent
      FALSE_POSITIVE    — Transaction is legitimate; close case
      NEEDS_MORE_INFO   — Additional investigation required
      ESCALATE          — Escalate to senior analyst or BSA team

    For CONFIRMED_FRAUD: BSA Officer must evaluate SAR filing
    within 30 days (BSA § 5318(g)).
    """
    update = {
        "case_id": case_id,
        "transaction_id": transaction_id,
        "analyst_id": analyst_id,
        "analyst_decision": analyst_decision,
        "analyst_notes": analyst_notes,
        "decision_timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "CLOSED" if analyst_decision in ("CONFIRMED_FRAUD", "FALSE_POSITIVE") else "UNDER_REVIEW",
        "sar_evaluation_required": analyst_decision == "CONFIRMED_FRAUD",
    }

    _append_audit_log(case_id, "ANALYST_DECISION", update)
    logger.info(f"[case_manager] Case {case_id} updated — analyst decision: {analyst_decision}")
    return update


def append_audit_entry(
    case_id: str,
    transaction_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """
    Append a structured event to the audit log.
    Called by individual nodes to create the examination-ready trail.
    """
    entry = {
        "case_id": case_id,
        "transaction_id": transaction_id,
        "event_type": event_type,
        **data,
    }
    _append_audit_log(case_id or transaction_id, event_type, entry)


def get_audit_log(limit: int = 100) -> list:
    """
    Read the most recent entries from the audit log.
    Used by the Streamlit audit trail tab.
    """
    log_path = Path(os.getenv("AUDIT_LOG_PATH", str(_DEFAULT_AUDIT_LOG)))

    if not log_path.exists():
        return []

    try:
        entries = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:]
    except Exception as e:
        logger.error(f"[case_manager] Failed to read audit log: {e}")
        return []


# ── Private Helpers ───────────────────────────────────────────────────────────

def _append_audit_log(reference_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """
    Append a single JSON line to the audit log file.
    Creates the file and parent directories if they don't exist.
    Thread-safe via file append mode (a+).
    """
    log_path = Path(os.getenv("AUDIT_LOG_PATH", str(_DEFAULT_AUDIT_LOG)))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "log_timestamp": datetime.now(timezone.utc).isoformat(),
        "reference_id": reference_id,
        "event_type": event_type,
        **data,
    }

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        logger.error(f"[case_manager] Failed to write audit log: {e}")


def _retention_date() -> str:
    """
    Calculate BSA 5-year retention date from today.
    BSA 31 U.S.C. § 5318: fraud records must be retained 5 years.
    """
    retention_dt = datetime.now(timezone.utc) + timedelta(days=5 * 365)
    return retention_dt.isoformat()
