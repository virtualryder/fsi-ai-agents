"""BLOCK path — draft the Reg E disclosure (Strands). Decision is Python."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    return {**event, "notice": strands_agent.draft_reg_e(event.get("decision", {}))}
