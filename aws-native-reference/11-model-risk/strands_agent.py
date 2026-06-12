"""Strands validation-narrative drafter — LLM DRAFTING (Agent 11). Sets no outcome/tier."""
from __future__ import annotations
import os
from typing import Any, Dict

SYSTEM_PROMPT = ("You draft SR 11-7 model-validation narratives (conceptual soundness, outcomes analysis, "
                 "ongoing monitoring). Use only the provided deterministic metrics (Gini/KS/PSI), degradation "
                 "flags, and HITL conditions. Do NOT set the validation outcome, risk tier, PSI class, or "
                 "routing — those are fixed. The Model Risk Officer signs the final outcome.")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.1)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    return (f"Validation narrative for {ctx.get('model_id')} (tier {ctx.get('risk_tier')}): PSI "
            f"{ctx.get('psi')} ({ctx.get('psi_class')}); degradation {ctx.get('degradation_flags')}. "
            f"Findings prepared for {ctx.get('reviewer')} sign-off. No outcome has been set by this draft.")


def draft_narrative(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"narrative_text": _demo(ctx), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        return {"narrative_text": str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""), "drafted_by": "bedrock"}
    except Exception:
        return {"narrative_text": _demo(ctx), "drafted_by": "demo-stub-fallback"}
