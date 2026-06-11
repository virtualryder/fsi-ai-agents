"""Node 1 — PII masking before any model sees the text (deterministic)."""
from __future__ import annotations
from . import _shared  # noqa: F401  (sys.path shim)
import core


def handler(event, context=None):
    doc = event.get("document", {})
    text = doc.get("text", "")
    masked_record, pii_types = core.mask_record({"text": text, **{k: v for k, v in doc.items() if k != "text"}})
    return {
        **event,
        "masked_text": masked_record.get("text", ""),
        "pii_types": pii_types,
        "pii_handling_required": "HUMAN_REVIEW" if pii_types else "STANDARD",
    }
