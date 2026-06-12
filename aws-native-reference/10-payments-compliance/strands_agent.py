"""
Strands notice drafter — LLM DRAFTING layer (Agent 10 native rebuild).

Drafts the customer/compliance notice (Reg E provisional-credit language, ACH
dispute resolution, NOC acknowledgement). All compliance determinations are
deterministic (core.py); the model renders prose only. Bedrock via Strands,
demo fallback included.
"""
from __future__ import annotations

import os
from typing import Any, Dict

SYSTEM_PROMPT = (
    "You draft payments-operations notices (ACH disputes, Reg E provisional "
    "credit, NOC acknowledgements). Use only the provided determinations. Do not "
    "decide eligibility, holds, or OFAC outcomes — those are fixed. Never reveal "
    "raw account or SSN numbers."
)


def _bedrock_model():
    from strands.models import BedrockModel
    kwargs: Dict[str, Any] = dict(
        model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001"),
        region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.0)
    gid = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if gid:
        kwargs["guardrail_id"] = gid
        kwargs["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**kwargs)


def _demo(determinations: Dict[str, Any]) -> str:
    if determinations.get("reg_e_eligible"):
        return ("We have received your dispute. Under Regulation E, provisional credit will be "
                "applied while we investigate. We will notify you of the outcome and your rights.")
    return ("We have received and processed your payment item per the applicable network rules. "
            "No further action is required at this time.")


def draft_notice(determinations: Dict[str, Any]) -> Dict[str, Any]:
    """Return {notice_text, drafted_by}. Sets no compliance determination."""
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"notice_text": _demo(determinations), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        agent = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        res = agent(f"Determinations:\n{determinations}")
        return {"notice_text": str(getattr(res, "message", None) or res), "drafted_by": "bedrock"}
    except Exception:
        return {"notice_text": _demo(determinations), "drafted_by": "demo-stub-fallback"}
