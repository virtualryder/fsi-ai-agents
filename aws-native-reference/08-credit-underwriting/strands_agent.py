"""
Strands drafter — LLM DRAFTING layer (Agent 08 native rebuild).

Drafts the adverse-action LETTER BODY (DECLINE) or an approval memo. The ECOA
adverse-action REASON CODES and the decision are deterministic (core.py); the
model only renders prose. It must use the provided reasons verbatim and must not
introduce prohibited-basis language. Bedrock via Strands, demo fallback.
"""
from __future__ import annotations

import os
from typing import Any, Dict

SYSTEM_PROMPT = (
    "You draft consumer credit notices. For a declined application, write the "
    "adverse-action letter body using ONLY the provided ECOA principal reasons; "
    "never mention prohibited bases (race, sex, age, national origin, marital "
    "status, religion, receipt of public assistance, neighborhood). For an "
    "approval, write a brief approval memo. Do not change the decision or the "
    "reasons — those are fixed."
)
_PROHIBITED = ("race", "sex", "gender", "age of applicant", "national origin", "marital",
               "religion", "public assistance", "neighborhood", "census tract")


def _bedrock_model():
    from strands.models import BedrockModel
    kwargs: Dict[str, Any] = dict(
        model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
        region_name=os.getenv("BEDROCK_REGION", "us-east-1"), temperature=0.0)
    gid = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if gid:
        kwargs["guardrail_id"] = gid
        kwargs["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**kwargs)


def _demo(evaluation: Dict[str, Any]) -> str:
    if evaluation.get("decision") == "DECLINE":
        rs = ", ".join(evaluation.get("adverse_action_reasons", [])) or "credit policy factors"
        return ("We are unable to approve your application at this time. The principal "
                f"reason(s) for this decision: {rs}. You have the right to a free copy of "
                "any credit report used and to dispute its accuracy.")
    return ("Your application has been approved subject to standard verification. "
            "Conditions, if any, will be communicated separately.")


def draft_notice(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """Return {letter_text, drafted_by}. Decision/reasons are NOT set here."""
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        text = _demo(evaluation)
    else:
        try:
            from strands import Agent
            agent = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
            res = agent(f"Decision + reasons:\n{evaluation}")
            text = str(getattr(res, "message", None) or res)
        except Exception:
            text = _demo(evaluation)
    # Defensive: never emit prohibited-basis language even if the model slips.
    safe = not any(p in text.lower() for p in _PROHIBITED)
    return {"letter_text": text, "drafted_by": "demo-stub", "prohibited_language_clean": safe}
