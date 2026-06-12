"""Review path — draft gap analysis (Strands). Sets no tier."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    return {**event, "gap_analysis": strands_agent.draft_gap_analysis(event.get("impact", {}))}
