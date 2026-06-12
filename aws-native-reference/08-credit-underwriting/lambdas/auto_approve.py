"""Clean APPROVE path — record approval (audited)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "APPROVED",
                                 "application_id": event.get("application", {}).get("application_id"),
                                 "tier": event.get("evaluation", {}).get("tier")})
    return {**event, "audit": audit}
