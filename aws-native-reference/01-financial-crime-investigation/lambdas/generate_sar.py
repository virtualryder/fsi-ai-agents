"""Node 4 (SAR path) — draft the SAR narrative (LLM drafting via Strands/Bedrock)."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    case = event.get("case", {})
    evidence = {
        "customer_name": case.get("customer_name"),
        "account_last4": case.get("account_last4"),
        "alert_type": case.get("alert_type"),
        "composite_score": event.get("composite_score"),
        "score_breakdown": event.get("score_breakdown"),
        "screening": event.get("screening"),
    }
    sar = strands_agent.draft_sar_narrative(evidence)
    return {**event, "sar": sar}
