"""Node 3 — deterministic routing + suppression gate (LLM fp is advisory only)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    a = event.get("alert", {})
    routing = core.routing_decision(
        rule_score=float(a.get("rule_score", 50.0)),
        llm_fp=float(event.get("justification", {}).get("advisory_fp_probability", 50.0)),
        historical_score=float(a.get("historical_score", 50.0)),
        features=a.get("features", {}),
    )
    return {**event, "routing": routing}
