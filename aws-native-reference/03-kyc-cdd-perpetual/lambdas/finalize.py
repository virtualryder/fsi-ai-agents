"""Finalize — masked review record + audit."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    r = event.get("rescore", {})
    out = {"customer_id": event.get("customer", {}).get("customer_id"),
           "outcome": r.get("outcome"), "edd_required": r.get("edd_required"),
           "human_review_required": r.get("human_review_required"),
           "reviewer_decision": event.get("review", {}).get("reviewer_decision"),
           "edd_present": "edd" in event}
    audit, _ = core.mask_record({"event": "FINALIZE", **out})
    return {**event, "structured_output": out, "audit": audit, "status": "COMPLETE"}
