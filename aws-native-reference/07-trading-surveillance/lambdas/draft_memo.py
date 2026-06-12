"""Review path — draft disposition memo / SAR narrative (Strands). Sets no tier/SAR."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    return {**event, "memo": strands_agent.draft_memo(event.get("scoring", {}))}
