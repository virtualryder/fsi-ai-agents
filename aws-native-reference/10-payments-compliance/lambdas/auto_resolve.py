"""Auto-resolve path — NOC / administrative events (no human, no notice)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "AUTO_RESOLVED",
                                 "payment_id": event.get("payment_event", {}).get("payment_id")})
    return {**event, "disposition": "AUTO_RESOLVED", "audit": audit}
