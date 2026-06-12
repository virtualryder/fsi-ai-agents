"""Escalate path — route to the Financial Crime Investigation agent (downstream)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "ESCALATED", "alert_id": event.get("alert", {}).get("alert_id"),
                                 "to": "01-financial-crime-investigation"})
    return {**event, "escalated_to": "01-financial-crime-investigation", "audit": audit}
