"""Finalize — masked record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    im = event.get("impact", {})
    out = {"change_id": event.get("change", {}).get("change_id"),
           "tier": im.get("tier"), "impact_score": im.get("impact_score"),
           "overrides": im.get("overrides", []),
           "human_review_required": im.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "gap_analysis_present": "gap_analysis" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
