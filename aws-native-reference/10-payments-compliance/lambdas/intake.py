"""Node 1 — PII mask the payment event."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("payment_event", {}))
    return {**event, "payment_event": masked, "pii_types": pii}
