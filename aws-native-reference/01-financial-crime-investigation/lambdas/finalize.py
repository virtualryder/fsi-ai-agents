"""Finalize — emit masked case record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    routing = event.get("routing", {})
    out = {
        "case_id": event.get("case", {}).get("case_id"),
        "decision": routing.get("decision"),
        "composite_score": event.get("composite_score"),
        "human_review_required": routing.get("human_review_required"),
        "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
        "sar_present": "sar" in event,
    }
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
