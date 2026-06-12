"""Strands proposal drafter — LLM DRAFTING (Agent 05). Sets no suitability."""
from __future__ import annotations
import os
from typing import Any, Dict

SYSTEM_PROMPT = ("You draft wealth-management client materials (meeting prep, proposals, reviews). Use only "
                 "provided facts and the deterministic suitability result. Do NOT determine or change "
                 "suitability — that is fixed. Include any required disclosures verbatim.")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.2)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    disc = " ".join(ctx.get("disclosures", []))
    return (f"Draft recommendation (suitability: {ctx.get('status')}). Prepared for RM review and approval "
            f"before any client delivery. {disc}").strip()


def draft_recommendation(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"draft_text": _demo(ctx), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        return {"draft_text": str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""), "drafted_by": "bedrock"}
    except Exception:
        return {"draft_text": _demo(ctx), "drafted_by": "demo-stub-fallback"}
