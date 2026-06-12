"""Node 2 — deterministic Reg BI / FINRA 2111 suitability (no model)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    r = event.get("request", {})
    s = core.suitability_check(
        client_profile=r.get("client_profile", {}),
        ips=r.get("ips_summary", {}),
        request_type=r.get("request_type", ""),
        investment_idea=r.get("investment_idea", ""),
        concentrated_positions=r.get("concentrated_positions", []),
    )
    return {**event, "suitability": s}
