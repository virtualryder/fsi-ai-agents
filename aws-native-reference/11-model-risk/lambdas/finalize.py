"""Finalize — masked validation record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    v = event.get("validation", {})
    out = {"model_id": v.get("model_id"), "risk_tier": v.get("risk_tier"),
           "psi": v.get("psi"), "psi_class": v.get("psi_class"),
           "degradation_flags": v.get("degradation_flags", []),
           "hitl_conditions": v.get("hitl_conditions", []), "reviewer": v.get("reviewer"),
           "human_review_required": v.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "narrative_present": "narrative" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
