"""Node 1 — PII/PAN mask the transaction."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("transaction", {}))
    return {**event, "transaction": masked, "pii_types": pii}
