"""Node 4 — deterministic routing + HITL decision (no model output participates)."""
from __future__ import annotations
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    ex = event.get("extraction", {})
    routing = core.routing_decision(
        document_type=ex.get("document_type", "unknown"),
        composite_confidence=float(ex.get("confidence", 0.0)),
        business_rule_violations=event.get("business_rule_violations", []),
        pii_handling=event.get("pii_handling_required", "STANDARD"),
        validation_errors=event.get("validation_errors", []),
    )
    return {**event, "routing": routing}
