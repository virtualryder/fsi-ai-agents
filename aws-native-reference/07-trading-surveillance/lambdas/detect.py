"""Node 2 — deterministic pattern detection + Reg SHO check."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    return {**event, "detection": core.detect(event.get("alert", {}))}
