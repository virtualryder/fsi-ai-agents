"""Node 6 — emit structured JSON output + audit record (deterministic)."""
from __future__ import annotations
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    routing = event.get("routing", {})
    reviewer = event.get("reviewer_decision")  # present only when resumed from HITL
    output = {
        "doc_id": event.get("document", {}).get("doc_id"),
        "document_type": routing.get("document_type"),
        "confidence_tier": routing.get("confidence_tier"),
        "target_agents": routing.get("target_agents", []),
        "human_review_required": routing.get("human_review_required"),
        "reviewer_decision": reviewer,
        "fields": event.get("extraction", {}).get("fields", {}),
    }
    audit, _ = core.mask_record({"event": "FINALIZE", **output})  # masked before persist
    return {**event, "structured_output": output, "audit": audit, "status": "COMPLETE"}
