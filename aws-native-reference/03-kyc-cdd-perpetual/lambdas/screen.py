"""Node 1 — PII mask + deterministic OFAC/PEP screening."""
from . import _shared  # noqa: F401
import core
_SANCTIONS = {"ivan petrov": {"program": "RUSSIA-EO14024"}}
_PEPS = {"maria gonzalez": {"role": "Deputy Finance Minister"}}


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("customer", {}))
    parties = masked.get("parties", [{"name": masked.get("full_name", "")}])
    return {**event, "customer": masked, "pii_types": pii,
            "screening": core.screen(parties, _SANCTIONS, _PEPS)}
