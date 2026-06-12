"""Node 3 — deterministic routing + HITL decision (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    sc = event.get("screening", {})
    routing = core.routing_decision(
        composite_score=float(event.get("composite_score", 0.0)),
        ofac_hit=bool(sc.get("ofac_hit")),
        pep_hit=bool(sc.get("pep_hit")),
    )
    return {**event, "routing": routing}
