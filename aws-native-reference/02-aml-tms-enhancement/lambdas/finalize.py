"""Finalize — masked disposition record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    r = event.get("routing", {})
    out = {
        "alert_id": event.get("alert", {}).get("alert_id"),
        "decision": r.get("decision"),
        "deterministic_fp_score": r.get("deterministic_fp_score"),
        "routing_basis": r.get("routing_basis"),
        "human_review_required": r.get("human_review_required"),
        "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
    }
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
