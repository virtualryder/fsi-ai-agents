"""ALLOW path — authorize (audited)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "ALLOWED", "txn": event.get("transaction", {}).get("transaction_id")})
    return {**event, "disposition": "ALLOWED", "audit": audit}
