"""Strands drafter — LLM DRAFTING (Agent 04): Reg E disclosure / analyst context. Sets no decision."""
from __future__ import annotations
import os
from typing import Any, Dict

SYSTEM_PROMPT = ("You draft fraud-operations text: Reg E provisional-credit disclosures for blocked "
                 "transactions and concise analyst context for review. Use only provided facts. Do not "
                 "decide block/allow — those are fixed. Never reveal full card numbers.")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.0)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    return ("Your transaction was declined as a fraud-prevention measure. If this was authorized, you may "
            "dispute it; under Regulation E provisional credit applies while we investigate eligible items.")


def draft_reg_e(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"notice_text": _demo(ctx), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        return {"notice_text": str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""), "drafted_by": "bedrock"}
    except Exception:
        return {"notice_text": _demo(ctx), "drafted_by": "demo-stub-fallback"}
