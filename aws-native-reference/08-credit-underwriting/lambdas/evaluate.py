"""Node 2 — deterministic credit evaluation (FICO/DTI/LTV, hard declines, ECOA codes)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    ev = core.evaluate(event.get("application", {}))
    return {**event, "evaluation": ev}
