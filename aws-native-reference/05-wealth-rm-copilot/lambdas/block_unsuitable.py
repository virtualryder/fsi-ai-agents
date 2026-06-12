"""UNSUITABLE path — surface to RM; never reaches the client (audited)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "BLOCKED_UNSUITABLE",
                                 "request_id": event.get("request", {}).get("request_id")})
    return {**event, "output_type": "UNSUITABLE_BLOCK", "audit": audit}
