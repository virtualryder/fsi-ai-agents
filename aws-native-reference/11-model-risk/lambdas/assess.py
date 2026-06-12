"""Node 2 — deterministic outcomes analysis (Gini/KS/PSI) + HITL conditions (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    return {**event, "validation": core.assess(event.get("model", {}))}
