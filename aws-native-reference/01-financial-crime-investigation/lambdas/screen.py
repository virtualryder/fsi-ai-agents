"""Node 1 — PII mask + deterministic watchlist screening (OFAC/PEP)."""
from . import _shared  # noqa: F401
import core

# Demo sanctions/PEP maps (the watchlist connector returns these in production).
_SANCTIONS = {"ivan petrov": {"program": "RUSSIA-EO14024", "match_score": 0.97}}
_PEPS = {"maria gonzalez": {"role": "Deputy Finance Minister", "match_score": 0.88}}


def handler(event, context=None):
    masked, pii = core.mask_record(event.get("case", {}))
    parties = masked.get("parties", [{"name": masked.get("customer_name", "")}])
    screen = core.screen_parties(parties, _SANCTIONS, _PEPS)
    return {**event, "case": masked, "pii_types": pii, "screening": screen}
