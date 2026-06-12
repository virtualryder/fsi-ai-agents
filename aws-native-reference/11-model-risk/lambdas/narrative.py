"""Review path — draft the validation narrative (Strands). Sets no outcome."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    return {**event, "narrative": strands_agent.draft_narrative(event.get("validation", {}))}
