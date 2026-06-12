"""Node 1 — PII mask the request/client context."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("request", {}))
    return {**event, "request": masked, "pii_types": pii}
