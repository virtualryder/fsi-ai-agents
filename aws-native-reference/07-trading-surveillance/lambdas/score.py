"""Node 3 — deterministic severity + SAR determination + routing (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    return {**event, "scoring": core.score_and_route(event.get("alert", {}), event.get("detection", {}))}
