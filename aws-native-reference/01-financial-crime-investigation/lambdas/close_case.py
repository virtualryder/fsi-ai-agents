"""Close path — document closure (no SAR, no human gate). Audited."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    audit, _ = core.mask_record({"event": "CASE_CLOSED",
                                 "case_id": event.get("case", {}).get("case_id"),
                                 "composite_score": event.get("composite_score")})
    return {**event, "disposition": "CLOSED_NO_SAR", "audit": audit}
