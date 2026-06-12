"""
Strands SAR-narrative drafter — the LLM DRAFTING layer (Agent 01 native rebuild).

Drafts a FinCEN-style SAR narrative from already-masked, deterministically-scored
evidence. It does NOT decide the risk score, the routing, or whether to file —
those are core.py (deterministic) and a BSA Officer (HITL). The model only writes
the narrative a human reviews. Bedrock via Strands, with a demo fallback so the
pipeline runs without an AWS account.
"""
from __future__ import annotations

import os
from typing import Any, Dict

SYSTEM_PROMPT = (
    "You are a BSA/AML analyst drafting a Suspicious Activity Report narrative for "
    "human review. Use only the facts provided. Cover who, what, when, where, and "
    "why the activity is suspicious. Never state that the SAR has been filed or that "
    "a decision is final — a BSA Officer reviews and approves. Do not invent figures "
    "or names not present in the evidence. Never reproduce raw SSNs or account numbers."
)


def _bedrock_model():
    from strands.models import BedrockModel
    kwargs: Dict[str, Any] = dict(
        model_id=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
        region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        temperature=0.0,
    )
    gid = os.getenv("BEDROCK_GUARDRAIL_ID", "")
    if gid:
        kwargs["guardrail_id"] = gid
        kwargs["guardrail_version"] = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    return BedrockModel(**kwargs)


def _demo_narrative(evidence: Dict[str, Any]) -> str:
    subj = evidence.get("customer_name", "the subject")
    acct = evidence.get("account_last4", "----")
    score = evidence.get("composite_score", "")
    typ = evidence.get("alert_type", "suspicious activity")
    return (
        f"This Suspicious Activity Report concerns customer {subj}, account ending {acct}. "
        f"The institution's automated review identified {typ} with a composite AML risk "
        f"assessment of {score}/100 across sanctions screening, counterparty network, "
        f"transaction patterns, and adverse media. The activity is inconsistent with the "
        f"customer's expected profile and lacks apparent economic purpose. This narrative is "
        f"prepared for BSA Officer review; no filing has occurred."
    )


def draft_sar_narrative(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Return {narrative, drafted_by}. Routing/score/decision are NOT set here."""
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return {"narrative": _demo_narrative(evidence), "drafted_by": "demo-stub"}
    try:
        from strands import Agent
        agent = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        result = agent(f"Draft a SAR narrative from this evidence:\n{evidence}")
        text = getattr(result, "message", None) or str(result)
        return {"narrative": str(text), "drafted_by": "bedrock"}
    except Exception:
        return {"narrative": _demo_narrative(evidence), "drafted_by": "demo-stub-fallback"}
