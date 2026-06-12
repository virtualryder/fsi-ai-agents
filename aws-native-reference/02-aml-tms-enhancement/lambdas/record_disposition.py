"""Downgrade / pass-through path — record disposition (alert stays human-visible)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    r = event.get("routing", {})
    audit, _ = core.mask_record({"event": "DISPOSITION", "alert_id": event.get("alert", {}).get("alert_id"),
                                 "decision": r.get("decision"), "deterministic_fp": r.get("deterministic_fp_score")})
    return {**event, "audit": audit}
