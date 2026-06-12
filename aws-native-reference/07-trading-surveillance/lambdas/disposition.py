"""Non-HITL path — record disposition (audited)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "DISPOSITIONED", "alert_id": event.get("alert", {}).get("alert_id"),
                                 "tier": event.get("scoring", {}).get("tier")})
    return {**event, "audit": audit}
