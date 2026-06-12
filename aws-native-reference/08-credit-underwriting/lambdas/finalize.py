"""Finalize — masked decision record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    ev = event.get("evaluation", {})
    out = {
        "application_id": event.get("application", {}).get("application_id"),
        "decision": ev.get("decision"), "tier": ev.get("tier"),
        "composite": ev.get("composite"),
        "adverse_action_reasons": ev.get("adverse_action_reasons", []),
        "human_review_required": event.get("routing", {}).get("human_review_required"),
        "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
        "notice_present": "notice" in event,
    }
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
