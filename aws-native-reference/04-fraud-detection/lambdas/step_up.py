"""STEP_UP path — request additional authentication (audited)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "STEP_UP_AUTH", "txn": event.get("transaction", {}).get("transaction_id")})
    return {**event, "disposition": "STEP_UP_REQUESTED", "audit": audit}
