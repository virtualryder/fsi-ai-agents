"""Node 1 — mask the surveillance alert."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("alert", {}))
    return {**event, "alert": masked, "pii_types": pii}
