"""Finalize — masked record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    a = event.get("assessment", {})
    out = {"account_id": a.get("account_id"),
           "contact_permitted": a.get("contact_permitted"),
           "hitl_conditions": a.get("hitl_conditions", []),
           "scra_rate_cap": a.get("scra_rate_cap"),
           "all_collection_halted": a.get("all_collection_halted"),
           "human_review_required": a.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "letter_present": "letter" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
