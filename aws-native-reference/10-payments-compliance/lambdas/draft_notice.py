"""Normal-dispute path — draft the customer notice (Strands). No determinations."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    det = {"reg_e_eligible": event.get("routing", {}).get("reg_e_eligible"),
           "return_code": event.get("screening", {}).get("return_code")}
    return {**event, "notice": strands_agent.draft_notice(det)}
