"""
Deterministic core for the AWS-native Document Intelligence reference (Phase 2).

This is the "Python decides" layer — identical in spirit to
`09-document-intelligence-agent/agent/nodes.py`, but framework-free so it can run
unchanged inside a Lambda. The LLM (via Strands/Bedrock) only DRAFTS the
classification and field extraction; everything that determines whether a
document is auto-routed or sent to a human is deterministic code here.

Faithful to the LangGraph agent's constants:
  * CONFIDENCE_HITL_THRESHOLD = 0.65
  * ALWAYS_HITL_DOCUMENT_TYPES = {government_id, sar_form, ctr_form, consent_order}
  * the six HITL triggers (low/uncertain confidence, always-HITL type, unknown
    type, business-rule violations, sensitive PII handling, validation errors)
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ── Confidence thresholds (Python constants — never model-set) ────────────────
CONFIDENCE_HITL_THRESHOLD = 0.65
CONFIDENCE_HIGH_TIER = 0.85

# ── Document types that ALWAYS require human review, regardless of score ──────
ALWAYS_HITL_DOCUMENT_TYPES = frozenset({
    "government_id",
    "sar_form",
    "ctr_form",
    "consent_order",
})

# ── Routing table (Python constant — cannot be altered at runtime) ────────────
DOCUMENT_ROUTING: Dict[str, List[str]] = {
    "loan_application_1003": ["08-credit-underwriting"],
    "bank_statement": ["01-financial-crime-investigation", "08-credit-underwriting"],
    "wire_instruction": ["10-payments-compliance"],
    "kyc_document": ["03-kyc-cdd-perpetual"],
    "sar_form": [],            # HITL only — never auto-routed
    "ctr_form": [],
    "government_id": ["03-kyc-cdd-perpetual"],
    "consent_order": [],
    "unknown": [],             # HITL — no auto-routing
}
DOCUMENT_PRIORITY: Dict[str, str] = {
    "sar_form": "HIGH", "ctr_form": "HIGH", "consent_order": "HIGH",
    "government_id": "NORMAL", "wire_instruction": "HIGH",
}


def confidence_tier(score: float) -> str:
    """Map a composite confidence score to a tier (deterministic)."""
    if score >= CONFIDENCE_HIGH_TIER:
        return "HIGH"
    if score >= CONFIDENCE_HITL_THRESHOLD:
        return "MEDIUM"
    if score > 0.0:
        return "LOW"
    return "UNCERTAIN"


def routing_decision(
    document_type: str,
    composite_confidence: float,
    business_rule_violations: List[str] | None = None,
    pii_handling: str = "STANDARD",
    validation_errors: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Deterministic routing + HITL decision. No model output participates.

    Returns a dict with: document_type, confidence_tier, target_agents, priority,
    human_review_required, human_review_reason, hitl_reasons.
    """
    business_rule_violations = business_rule_violations or []
    validation_errors = validation_errors or []
    tier = confidence_tier(composite_confidence)
    target_agents = list(DOCUMENT_ROUTING.get(document_type, []))
    priority = DOCUMENT_PRIORITY.get(document_type, "NORMAL")

    hitl_reasons: List[str] = []
    if tier in ("LOW", "UNCERTAIN"):
        hitl_reasons.append(f"Confidence tier {tier} below threshold for auto-routing")
    if document_type in ALWAYS_HITL_DOCUMENT_TYPES:
        hitl_reasons.append(f"Document type {document_type} always requires human review")
    if document_type == "unknown":
        hitl_reasons.append("Document type could not be classified — manual review required")
    if business_rule_violations:
        hitl_reasons.append(f"Business rule violations: {'; '.join(business_rule_violations[:2])}")
    if pii_handling in ("HUMAN_REVIEW", "ENCRYPT"):
        hitl_reasons.append(f"PII handling level {pii_handling} requires reviewer confirmation")
    if validation_errors:
        hitl_reasons.append(f"Validation errors: {len(validation_errors)} field(s) failed validation")

    human_review_required = bool(hitl_reasons)
    return {
        "document_type": document_type,
        "confidence_tier": tier,
        "composite_confidence": composite_confidence,
        "target_agents": target_agents,
        "priority": priority,
        "human_review_required": human_review_required,
        "human_review_reason": "; ".join(hitl_reasons) if hitl_reasons else "Auto-route eligible",
        "hitl_reasons": hitl_reasons,
        # The Step Functions Choice state branches on this string.
        "next": "HumanReviewGate" if human_review_required else "AutoRoute",
    }


# ── PII masking at the state-write boundary (reuse platform middleware) ───────
def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Mask PII in a structured record before it is persisted or sent downstream.
    Prefers the shared platform middleware; falls back to a minimal local masker
    so this reference stays independently runnable.
    """
    try:
        from fsi_agent_platform.pii import mask_obj  # shared boundary middleware
        return mask_obj(record)
    except Exception:
        import re
        ssn = re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
        found: List[str] = []

        def _walk(o):
            if isinstance(o, str):
                if ssn.search(o):
                    found.append("SSN")
                    return ssn.sub("[SSN-MASKED]", o)
                return o
            if isinstance(o, dict):
                return {k: _walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_walk(v) for v in o]
            return o

        return _walk(record), sorted(set(found))
