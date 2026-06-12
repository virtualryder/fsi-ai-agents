"""Strands disposition/SAR drafter — LLM DRAFTING (Agent 07). Sets no tier/SAR; no tipping off."""
from __future__ import annotations
import os
from typing import Any, Dict

SYSTEM_PROMPT = ("You draft trading-surveillance disposition memos and, when flagged, SAR narratives for "
                 "compliance review. Use only provided facts and the deterministic severity/SAR result. Do "
                 "NOT set severity, the SAR determination, or routing — those are fixed. A SAR and its "
                 "existence must NEVER be disclosed to the subject (no tipping off, 31 U.S.C. § 5318(g)(2)).")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.0)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    sar = " A SAR is under consideration (internal only)." if ctx.get("sar_required") else ""
    return (f"Disposition memo — alert {ctx.get('alert_type')}, severity tier {ctx.get('tier')}. "
            f"Market context and trade reconstruction summarized for compliance-officer review.{sar}")


def draft_memo(ctx: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"memo_text": _demo(ctx), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        return {"memo_text": str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""), "drafted_by": "bedrock"}
    except Exception:
        return {"memo_text": _demo(ctx), "drafted_by": "demo-stub-fallback"}
