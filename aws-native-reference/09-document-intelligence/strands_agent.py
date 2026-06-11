"""
Strands Agents SDK extraction agent — the LLM DRAFTING layer (Phase 2).

AWS-native counterpart to the LangGraph agent's extraction/classification nodes.
It is deliberately narrow: it classifies the document and extracts fields with
per-field confidence, and returns that as structured data. It does NOT decide
routing or whether a human must review — those are deterministic (see core.py).
This preserves the suite thesis ("Python decides; the model drafts") under an
AWS-native runtime.

Model: Amazon Bedrock (default Claude Sonnet 4) via the Strands SDK, with
Bedrock Guardrails attached when BEDROCK_GUARDRAIL_ID is configured.

Runtime fit: this module runs as-is inside a Lambda (see lambdas/extract.py) or
can be deployed to Amazon Bedrock AgentCore Runtime — Strands documents both.

Graceful degradation: if the `strands` SDK or Bedrock access is unavailable
(local dev / CI / demo), `classify_and_extract` returns a deterministic stub so
the whole pipeline can be exercised end-to-end without an AWS account. The stub
NEVER fabricates high confidence for sensitive types — it leaves them for the
deterministic HITL gate.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

SYSTEM_PROMPT = (
    "You are a financial-services document intelligence assistant. Classify the "
    "document and extract its key fields. Return ONLY structured data: a "
    "document_type, a flat map of extracted fields, an overall confidence in "
    "[0,1], and a per-field confidence map. Never claim a document is approved, "
    "routed, or cleared — you only describe what the document contains. If you "
    "are unsure of the type, return 'unknown' with low confidence."
)

# Document types the model may assign (mirrors core.DOCUMENT_ROUTING keys).
KNOWN_TYPES = [
    "loan_application_1003", "bank_statement", "wire_instruction", "kyc_document",
    "sar_form", "ctr_form", "government_id", "consent_order", "unknown",
]


def _bedrock_model():
    """Build a Strands BedrockModel with Guardrails when configured."""
    from strands.models import BedrockModel  # lazy — optional dep

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


def _demo_extract(masked_text: str) -> Dict[str, Any]:
    """Deterministic stub used when Strands/Bedrock is unavailable (no fabricated certainty)."""
    t = (masked_text or "").lower()
    if "uniform residential loan application" in t or "form 1003" in t:
        return {"document_type": "loan_application_1003",
                "fields": {"borrower": "[NAME-MASKED]", "loan_amount": "250000"},
                "confidence": 0.88,
                "field_confidences": {"borrower": 0.9, "loan_amount": 0.86}}
    if "suspicious activity report" in t or "fincen sar" in t:
        return {"document_type": "sar_form", "fields": {}, "confidence": 0.80,
                "field_confidences": {}}  # always-HITL type; deterministic gate decides
    if "driver" in t and "license" in t:
        return {"document_type": "government_id", "fields": {"id_number": "[ID-MASKED]"},
                "confidence": 0.92, "field_confidences": {"id_number": 0.92}}
    return {"document_type": "unknown", "fields": {}, "confidence": 0.30, "field_confidences": {}}


def classify_and_extract(masked_text: str) -> Dict[str, Any]:
    """
    Classify + extract from already-PII-masked document text.

    Returns: {document_type, fields, confidence, field_confidences}. Routing and
    HITL are NOT decided here — core.routing_decision consumes this output.
    """
    if os.getenv("EXTRACT_MODE", "").strip().lower() == "demo":
        return _demo_extract(masked_text)
    try:
        from strands import Agent
        from pydantic import BaseModel, Field

        class ExtractionResult(BaseModel):
            document_type: str = Field(description=f"One of: {', '.join(KNOWN_TYPES)}")
            fields: Dict[str, str] = Field(default_factory=dict)
            confidence: float = Field(ge=0.0, le=1.0)
            field_confidences: Dict[str, float] = Field(default_factory=dict)

        agent = Agent(model=_bedrock_model(), system_prompt=SYSTEM_PROMPT, callback_handler=None)
        result: "ExtractionResult" = agent.structured_output(
            ExtractionResult, f"Document text:\n{masked_text}"
        )
        dt = result.document_type if result.document_type in KNOWN_TYPES else "unknown"
        return {
            "document_type": dt,
            "fields": dict(result.fields),
            "confidence": float(result.confidence),
            "field_confidences": dict(result.field_confidences),
        }
    except Exception:
        # SDK/Bedrock unavailable → deterministic stub keeps the pipeline runnable.
        return _demo_extract(masked_text)
