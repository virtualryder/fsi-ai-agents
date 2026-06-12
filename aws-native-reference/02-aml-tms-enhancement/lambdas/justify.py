"""Node 2 — LLM justification + ADVISORY fp probability (Strands/Bedrock). No routing."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    just = strands_agent.draft_justification(event.get("alert", {}))
    return {**event, "justification": just}
