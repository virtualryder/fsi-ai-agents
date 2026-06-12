"""Node 1 — mask + carry the regulatory change."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, _ = core.mask_record(event.get("change", {}))
    return {**event, "change": masked}
