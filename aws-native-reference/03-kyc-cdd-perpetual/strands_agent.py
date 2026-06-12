"""Strands EDD-package drafter — LLM DRAFTING (Agent 03). Sets no risk rating."""
from __future__ import annotations
import os
from typing import Any, Dict

SYSTEM_PROMPT = ("You draft Enhanced Due Diligence packages and RM communications for KYC review. "
                 "Use only provided facts. Do not set or change the customer's risk rating or outcome "
                 "— a Compliance Officer decides. Never reveal raw SSN/account numbers.")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.0)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    return (f"EDD package: review outcome {ctx.get('outcome')} for customer. Recommended document "
            "checklist and adverse-media summary attached for Compliance Officer review. No risk-rating "
            "change has been applied.")


def draft_edd(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"edd_text": _demo(ctx), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        return {"edd_text": str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""), "drafted_by": "bedrock"}
    except Exception:
        return {"edd_text": _demo(ctx), "drafted_by": "demo-stub-fallback"}
