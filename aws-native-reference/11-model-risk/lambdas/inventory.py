"""Node 1 — model inventory lookup (mask + carry)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, _ = core.mask_record(event.get("model", {}))
    return {**event, "model": masked}
