"""
Strands FP-justification drafter — the LLM DRAFTING layer (Agent 02 native rebuild).

Produces a written suppression/disposition justification and an ADVISORY
false-positive probability for the reviewer's context. The advisory probability
is NOT used for routing — routing is the deterministic suppression gate in
core.py. The model can read an alert as a false positive and write why; it can
never be the reason the alert is removed from the analyst queue. Bedrock via
Strands, demo fallback included.
"""
from __future__ import annotations

import os
from typing import Any, Dict

SYSTEM_PROMPT = (
    "You are an AML analyst assistant. Given a transaction-monitoring alert and "
    "context, write a concise justification for the recommended disposition and "
    "estimate a false-positive probability (0-100) as ADVISORY context only. Use "
    "only the provided facts. Do not claim the alert is suppressed or closed — a "
    "deterministic policy and a BSA Officer decide that. Never reveal raw PII."
)


def _bedrock_model():
    from strands.models import BedrockModel
    kwargs: Dict[str, Any] = dict(
        model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001"),
        region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        temperature=0.0,
    )
    gid = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if gid:
        kwargs["guardrail_id"] = gid
        kwargs["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**kwargs)


def _demo(alert: Dict[str, Any]) -> Dict[str, Any]:
    typ = alert.get("alert_type", "alert")
    return {
        "advisory_fp_probability": 70.0,
        "narrative": (f"The {typ} alert is consistent with the customer's established "
                      "pattern and prior dispositions; no new suspicious indicators are "
                      "present. Recommended disposition is advisory only and subject to the "
                      "deterministic policy and BSA Officer review."),
        "drafted_by": "demo-stub",
    }


def draft_justification(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Return {advisory_fp_probability, narrative, drafted_by}. Sets no routing."""
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return _demo(alert)
    try:
        from strands import Agent
        agent = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        result = agent(f"Alert + context:\n{alert}")
        text = getattr(result, "message", None) or str(result)
        return {"advisory_fp_probability": float(alert.get("hint_fp", 60.0)),
                "narrative": str(text), "drafted_by": "bedrock"}
    except Exception:
        return {**_demo(alert), "drafted_by": "demo-stub-fallback"}
