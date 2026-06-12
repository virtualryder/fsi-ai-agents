"""Finalize — masked output + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    s = event.get("suitability", {})
    out = {"request_id": event.get("request", {}).get("request_id"),
           "suitability_status": s.get("status"),
           "human_review_required": s.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "blocked": event.get("output_type") == "UNSUITABLE_BLOCK",
           "recommendation_present": "recommendation" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
