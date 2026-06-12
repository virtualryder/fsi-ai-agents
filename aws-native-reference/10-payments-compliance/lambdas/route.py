"""Node 3 — deterministic routing + HITL triggers (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    routing = core.routing_decision(event.get("payment_event", {}), event.get("screening", {}))
    return {**event, "routing": routing}
