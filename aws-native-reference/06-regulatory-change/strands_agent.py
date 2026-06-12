"""Strands gap-analysis drafter — LLM DRAFTING (Agent 06). Sets no tier/impact."""
from __future__ import annotations
import os
from typing import Any, Dict

SYSTEM_PROMPT = ("You draft regulatory gap-analysis and remediation narratives for a compliance team. "
                 "Use only provided facts and the deterministic impact tier. Do NOT set or change the "
                 "impact tier or the routing — those are fixed. Output a concise gap analysis and a "
                 "remediation outline for CCO review.")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.2)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    return (f"Gap analysis (impact tier {ctx.get('tier')}): mapped policies require review against the "
            "change; recommended remediation tasks and owners outlined for CCO approval. No tier change applied.")


def draft_gap_analysis(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"gap_text": _demo(ctx), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        return {"gap_text": str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""), "drafted_by": "bedrock"}
    except Exception:
        return {"gap_text": _demo(ctx), "drafted_by": "demo-stub-fallback"}
