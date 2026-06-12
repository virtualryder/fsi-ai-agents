"""Node 2 — deterministic 5-factor impact + tier + hard overrides (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    return {**event, "impact": core.assess(event.get("change", {}))}
