"""Node 1 — PII mask + feature surface (rule pre-score, historical base rates)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("alert", {}))
    return {**event, "alert": masked, "pii_types": pii}
