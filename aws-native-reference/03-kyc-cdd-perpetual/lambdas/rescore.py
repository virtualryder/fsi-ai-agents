"""Node 2 — deterministic risk rescoring → review outcome (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    c = event.get("customer", {}); sc = event.get("screening", {})
    r = core.rescore(current_tier=c.get("risk_tier", "MEDIUM"),
                     risk_score=float(c.get("risk_score", 50.0)),
                     pep_hit=bool(sc.get("pep_hit") or c.get("pep_flag")),
                     ofac_hit=bool(sc.get("ofac_hit")),
                     edd_current=bool(c.get("edd_current", True)))
    return {**event, "rescore": r}
