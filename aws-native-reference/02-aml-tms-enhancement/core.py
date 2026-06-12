"""
Deterministic core for the AWS-native AML/TMS false-positive triage agent.

Faithful to 02-aml-tms-enhancement-agent and its Phase 1.3 control-integrity fix:
the consequential action — SUPPRESS, which removes an alert from the analyst
queue — is gated on a DETERMINISTIC-ONLY score (rule pre-score + historical base
rates, LLM EXCLUDED). The model may author a justification narrative and may
ESCALATE, but it can never be the reason an alert disappears from review.

Routing: ESCALATE (override or deterministic ≤ escalate line) · SUPPRESS
(deterministic ≥ suppress line) · DOWNGRADE (≥ downgrade line) · PASS_THROUGH.
SUPPRESS additionally routes to a sampled BSA-Officer review gate (the 90-day
suppression review made a framework-enforced, governed step).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

WEIGHT_RULE = 0.30
WEIGHT_LLM = 0.50
WEIGHT_HISTORICAL = 0.20
# Deterministic-only renormalization (LLM excluded): 0.60 / 0.40
_DET_RULE = WEIGHT_RULE / (WEIGHT_RULE + WEIGHT_HISTORICAL)
_DET_HIST = WEIGHT_HISTORICAL / (WEIGHT_RULE + WEIGHT_HISTORICAL)

SUPPRESS_THRESHOLD = 85.0
DOWNGRADE_THRESHOLD = 60.0
ESCALATE_THRESHOLD = 15.0


def deterministic_score(rule_score: float, historical_score: float) -> float:
    """Deterministic-only FP score (0-100): rule + historical, LLM excluded."""
    return round(rule_score * _DET_RULE + historical_score * _DET_HIST, 1)


def composite_score(rule_score: float, llm_fp: float, historical_score: float) -> float:
    """Blended FP score for display/explainability only — NOT the routing driver."""
    return round(rule_score * WEIGHT_RULE + llm_fp * WEIGHT_LLM + historical_score * WEIGHT_HISTORICAL, 1)


def regulatory_override(features: Dict[str, Any]) -> Tuple[bool, str]:
    """PEP / open investigation / OFAC-adjacent → mandatory ESCALATE (never suppress)."""
    if features.get("pep_flag"):
        return True, "PEP — FATF R.12 requires human review; suppression prohibited"
    if features.get("has_open_investigation"):
        return True, "open investigation — alert must reach the investigating analyst"
    if (features.get("high_risk_geography") and features.get("amount_usd", 0) >= 50_000
            and features.get("account_age_days", 9999) < 180 and features.get("prior_sars_filed", 0) == 0):
        return True, "OFAC-adjacent profile (high-risk geo + large wire + new account)"
    return False, ""


def routing_decision(rule_score: float, llm_fp: float, historical_score: float,
                     features: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic routing with the suppression gate. LLM fp is advisory only."""
    det = deterministic_score(rule_score, historical_score)
    comp = composite_score(rule_score, llm_fp, historical_score)
    override, override_reason = regulatory_override(features)
    notes: List[str] = []

    if override:
        decision = "ESCALATE"
        notes.append(f"regulatory override: {override_reason}")
    elif det <= ESCALATE_THRESHOLD:
        decision = "ESCALATE"
        notes.append(f"deterministic FP {det:.0f} <= escalate line {ESCALATE_THRESHOLD:.0f}")
    elif det >= SUPPRESS_THRESHOLD:
        decision = "SUPPRESS"
        notes.append(f"deterministic FP {det:.0f} >= suppress line {SUPPRESS_THRESHOLD:.0f} "
                     "(rule+historical; LLM excluded) — sampled BSA review required")
    elif det >= DOWNGRADE_THRESHOLD:
        decision = "DOWNGRADE"
        notes.append(f"deterministic FP {det:.0f} >= downgrade line {DOWNGRADE_THRESHOLD:.0f} — low-priority queue")
    else:
        decision = "PASS_THROUGH"
        notes.append(f"deterministic FP {det:.0f} in normal band — analyst queue")

    # SUPPRESS is the only disposition that removes an alert from review, so it
    # is the only one that routes to a (sampled) human gate.
    next_state = {
        "SUPPRESS": "SuppressionReviewGate",
        "DOWNGRADE": "RecordDisposition",
        "PASS_THROUGH": "RecordDisposition",
        "ESCALATE": "Escalate",
    }[decision]
    return {
        "decision": decision,
        "deterministic_fp_score": det,
        "composite_fp_score": comp,
        "routing_basis": "deterministic_suppression_gate",
        "regulatory_override": override,
        "human_review_required": decision == "SUPPRESS",
        "notes": notes,
        "next": next_state,
    }


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    try:
        from fsi_agent_platform.pii import mask_obj
        return mask_obj(record)
    except Exception:
        import re
        ssn = re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
        found: List[str] = []

        def _walk(o):
            if isinstance(o, str):
                if ssn.search(o):
                    found.append("SSN"); return ssn.sub("[SSN-MASKED]", o)
                return o
            if isinstance(o, dict):
                return {k: _walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_walk(v) for v in o]
            return o
        return _walk(record), sorted(set(found))
