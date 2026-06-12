"""Node 2 — deterministic FDCPA contact-time + SCRA/bankruptcy + HITL conditions (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    return {**event, "assessment": core.assess(event.get("account", {}))}
