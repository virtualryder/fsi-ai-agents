"""Review path — draft EDD package / RM comm (Strands). Sets no rating."""
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    return {**event, "edd": strands_agent.draft_edd(event.get("rescore", {}))}
