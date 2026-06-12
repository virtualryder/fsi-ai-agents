"""Finalize — masked record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    sc = event.get("scoring", {})
    out = {"alert_id": event.get("alert", {}).get("alert_id"),
           "alert_type": sc.get("alert_type"), "tier": sc.get("tier"),
           "sar_required": sc.get("sar_required"), "reg_sho_violation": sc.get("reg_sho_violation"),
           "human_review_required": sc.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "memo_present": "memo" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
