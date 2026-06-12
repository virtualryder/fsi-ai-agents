"""Strands letter drafter — LLM DRAFTING (Agent 12). Writes the body only; required disclosures are Python-injected."""
from __future__ import annotations
import os
from typing import Any, Dict, List

SYSTEM_PROMPT = ("You draft the body of a consumer collections letter in a respectful, FDCPA-compliant tone. "
                 "Use only provided facts. Do NOT decide eligibility, SCRA, bankruptcy, or contact timing — "
                 "those are fixed. Do NOT write the required disclosures (they are appended verbatim). Never "
                 "threaten action that cannot legally be taken; never reveal full SSN/account numbers.")


def _bedrock_model():
    from strands.models import BedrockModel
    k = dict(model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
             region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.2)
    g = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if g:
        k["guardrail_id"] = g; k["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**k)


def _demo(ctx: Dict[str, Any]) -> str:
    return ("Regarding your account, we would like to discuss repayment options that work for your situation. "
            "Please contact us to arrange a plan.")


def draft_letter(ctx: Dict[str, Any], disclosures: List[str]) -> Dict[str, Any]:
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        body = _demo(ctx); drafted_by = "demo-stub"
    else:
        try:
            from strands import Agent
            a = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
            body = str(getattr(a(f"Context:\n{ctx}"), "message", None) or ""); drafted_by = "bedrock"
        except Exception:
            body = _demo(ctx); drafted_by = "demo-stub-fallback"
    # Required disclosures are injected by Python, never written by the model.
    letter_text = body.strip() + "\n\n" + "\n".join(disclosures)
    return {"letter_text": letter_text, "body": body, "disclosures_injected": disclosures, "drafted_by": drafted_by}
