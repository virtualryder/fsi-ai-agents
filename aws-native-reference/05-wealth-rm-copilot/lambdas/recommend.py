"""Non-blocked path — draft the recommendation (Strands). Sets no suitability."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    return {**event, "recommendation": strands_agent.draft_recommendation(event.get("suitability", {}))}
