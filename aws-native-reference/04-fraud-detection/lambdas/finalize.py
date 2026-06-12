"""Finalize — masked decision record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    d = event.get("decision", {})
    out = {"transaction_id": event.get("transaction", {}).get("transaction_id"),
           "decision": d.get("decision"), "composite_score": d.get("composite_score"),
           "reg_e_disclosure_required": d.get("reg_e_disclosure_required"),
           "human_review_required": d.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "notice_present": "notice" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
