"""Finalize — masked disposition record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    r = event.get("routing", {})
    out = {
        "payment_id": event.get("payment_event", {}).get("payment_id"),
        "human_review_required": r.get("human_review_required"),
        "reg_e_eligible": r.get("reg_e_eligible"),
        "triggers": r.get("triggers", []),
        "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
        "disposition": event.get("disposition"),
        "notice_present": "notice" in event,
    }
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
