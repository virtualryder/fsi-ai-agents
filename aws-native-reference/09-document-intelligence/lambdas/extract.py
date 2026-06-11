"""Node 2 — classification + field extraction (LLM drafting via Strands/Bedrock)."""
from __future__ import annotations
from . import _shared  # noqa: F401
import strands_agent


def handler(event, context=None):
    extraction = strands_agent.classify_and_extract(event.get("masked_text", ""))
    return {**event, "extraction": extraction}
