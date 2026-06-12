"""Node 2 — deterministic composite risk score (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    factors = event.get("case", {}).get("factors", {})
    # Sanctions sub-score is pinned high when there is an OFAC hit.
    if event.get("screening", {}).get("ofac_hit"):
        factors = {**factors, "sanctions": 1.0}
    score, breakdown = core.compute_risk_score(factors)
    return {**event, "composite_score": score, "score_breakdown": breakdown}
