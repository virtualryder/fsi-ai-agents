"""Node 2 — deterministic OFAC / Nacha / Reg E screening."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    return {**event, "screening": core.screen(event.get("payment_event", {}))}
