"""Node 4 — deterministic routing + HITL decision."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    routing = core.routing_decision(event.get("evaluation", {}), event.get("fair_lending_flags", []))
    return {**event, "routing": routing}
