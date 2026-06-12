"""DECLINE path — draft the adverse-action letter body (Strands). Reasons are Python."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    notice = strands_agent.draft_notice(event.get("evaluation", {}))
    return {**event, "notice": notice}
