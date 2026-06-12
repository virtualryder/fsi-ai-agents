"""Node 1 — mask the account."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("account", {}))
    return {**event, "account": masked, "pii_types": pii}
