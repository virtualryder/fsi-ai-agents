"""Node 1 — PII mask + document/identity verification (deterministic)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("application", {}))
    return {**event, "application": masked, "pii_types": pii}
