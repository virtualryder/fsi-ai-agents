"""No-HITL path — draft the letter (Strands body + Python-injected disclosures)."""
from . import _shared  # noqa: F401
import core
import strands_agent


def handler(event, context=None):
    a = event.get("account", {}); assessment = event.get("assessment", {})
    disclosures = core.required_disclosures(a, assessment)
    return {**event, "letter": strands_agent.draft_letter(assessment, disclosures)}
