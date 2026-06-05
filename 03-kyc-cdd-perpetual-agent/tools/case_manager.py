# tools/case_manager.py
# ============================================================
# KYC Case Record Management
#
# Creates and updates case records in the institution's case
# management system and writes to the append-only audit log.
#
# Production integrations:
#   - Actimize CRM (most common at Tier 1 banks)
#   - Fenergo CLM
#   - Pega KYC / CLM
#   - FIS/Metavante
#   - Custom PostgreSQL / DynamoDB case store
#
# Audit log design:
#   Append-only JSONL file (dev) or DynamoDB (prod)
#   BSA requires 5-year retention of KYC review records
#   Records must be examination-ready (OCC, FDIC, FinCEN)
# ============================================================

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path("data/audit_log.jsonl")


def create_case_record(
    review_id: str,
    customer_id: str,
    outcome: str,
    final_risk_tier: str,
    compliance_officer_id: str = None,
    audit_trail: List[Dict] = None,
) -> bool:
    """
    Create a permanent case record for the completed KYC review.

    In production: POST to case management API and write to DynamoDB
    with append-only (insert-only, no updates) access pattern.

    Returns:
        True if successful, False if failed (caller should flag for manual follow-up)
    """
    record = {
        "record_type": "KYC_REVIEW_CASE",
        "review_id": review_id,
        "customer_id": customer_id,
        "outcome": outcome,
        "final_risk_tier": final_risk_tier,
        "compliance_officer_id": compliance_officer_id or "system",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "audit_trail_entries": len(audit_trail or []),
        "regulatory_retention_required": True,
        "retention_until": _retention_date(),
    }

    return _write_to_audit_log(record)


def update_kyc_record(
    customer_id: str,
    review_id: str,
    new_risk_tier: str,
    next_review_date: str,
    reviewed_by: str,
    edd_required: bool = False,
) -> bool:
    """
    Update the customer's risk tier and next review date in the KYC system.

    In production: PUT to core banking KYC API endpoint.

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    #   import requests
    #   response = requests.put(
    #       f"{os.getenv('KYC_API_BASE_URL')}/customers/{customer_id}/risk-profile",
    #       json={
    #           "risk_tier": new_risk_tier,
    #           "next_review_date": next_review_date,
    #           "last_reviewed_by": reviewed_by,
    #           "last_review_id": review_id,
    #           "edd_active": edd_required,
    #       },
    #       headers={"Authorization": f"Bearer {os.getenv('KYC_API_TOKEN')}"},
    #       timeout=10,
    #   )
    #   response.raise_for_status()
    # ──────────────────────────────────────────────────────────────────────────
    """
    update_record = {
        "record_type": "KYC_RECORD_UPDATE",
        "customer_id": customer_id,
        "review_id": review_id,
        "new_risk_tier": new_risk_tier,
        "next_review_date": next_review_date,
        "updated_by": reviewed_by,
        "edd_active": edd_required,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }

    return _write_to_audit_log(update_record)


def _write_to_audit_log(record: dict) -> bool:
    """Write to append-only audit log (JSONL format)."""
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
        return True
    except Exception as e:
        logger.error(f"Audit log write failed: {e}")
        return False


def _retention_date() -> str:
    """BSA requires 5-year record retention from the date of review."""
    from datetime import timedelta
    return (datetime.utcnow() + timedelta(days=5 * 365)).date().isoformat()
