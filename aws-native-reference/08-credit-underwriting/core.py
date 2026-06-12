"""
Deterministic core for the AWS-native Credit Underwriting agent.

Faithful to 08-credit-underwriting-agent: all credit decisioning is deterministic
Python — FICO-band credit factor, DTI/LTV/income/reserves composite, hard-decline
rules, ECOA adverse-action reason codes, and tier thresholds. The LLM (Strands)
only drafts the adverse-action letter body or the approval memo; the REASONS and
the decision are Python (the parts an examiner cares about under ECOA/Reg B).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ── Composite weights (sum 1.0) ───────────────────────────────────────────────
WEIGHTS = {"credit": 0.30, "dti": 0.25, "ltv": 0.20, "income": 0.15, "reserves": 0.10}

HARD_DECLINE_DTI_MAX = 0.50
FICO_MIN_CONVENTIONAL = 620
FICO_MIN_JUMBO = 700
BANKRUPTCY_CH7_SEASONING_YEARS = 4.0
BANKRUPTCY_CH13_SEASONING_YEARS = 2.0

# ── ECOA / Reg B adverse-action reason codes (Python, never LLM) ──────────────
class AAR:
    CREDIT_SCORE_TOO_LOW = "CREDIT_SCORE_TOO_LOW"
    DTI_TOO_HIGH = "DTI_TOO_HIGH"
    EXCESSIVE_OBLIGATIONS = "EXCESSIVE_OBLIGATIONS"
    INSUFFICIENT_INCOME = "INSUFFICIENT_INCOME"
    INADEQUATE_COLLATERAL = "INADEQUATE_COLLATERAL"
    BANKRUPTCY = "BANKRUPTCY"
    OFAC_MATCH = "OFAC_MATCH"
    POOR_CREDIT_PERFORMANCE = "POOR_CREDIT_PERFORMANCE"
    INSUFFICIENT_CREDIT_EXPERIENCE = "INSUFFICIENT_CREDIT_EXPERIENCE"


def credit_factor(fico: int) -> float:
    """FICO → [0,1] credit sub-score (banded, faithful to the agent)."""
    bands = [(800, 0.95), (760, 0.90), (740, 0.85), (720, 0.80), (700, 0.70),
             (680, 0.60), (660, 0.50), (640, 0.38), (620, 0.25), (580, 0.12)]
    for floor, val in bands:
        if fico >= floor:
            return val
    return 0.0


def _ratio_factor(value: float, good: float, bad: float) -> float:
    """Linear factor: <=good → 1.0, >=bad → 0.0."""
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return round(1.0 - (value - good) / (bad - good), 3)


def evaluate(application: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic credit evaluation. Returns decision, tier, composite, factors,
    adverse_action_reasons (ECOA codes), hard_decline + reason, and the routing.
    """
    fico = int(application.get("credit_score", 0))
    total_dti = float(application.get("total_dti_ratio", 0.0))
    ltv = float(application.get("ltv_ratio", 0.0))
    income_ok = bool(application.get("income_verified", True))
    reserves_months = float(application.get("reserves_months", 0.0))
    loan_type = application.get("loan_type", "CONVENTIONAL_MORTGAGE")
    ofac_hit = bool(application.get("ofac_hit", False))
    bankruptcy = application.get("bankruptcy", {})  # {chapter, discharge_years} or {}

    factors = {
        "credit": credit_factor(fico),
        "dti": _ratio_factor(total_dti, 0.36, 0.50),
        "ltv": _ratio_factor(ltv, 0.80, 0.97),
        "income": 1.0 if income_ok else 0.0,
        "reserves": min(1.0, reserves_months / 6.0),
    }
    composite = round(sum(factors[k] * w for k, w in WEIGHTS.items()), 3)

    reasons: List[str] = []
    hard_decline = False
    hard_reason = ""

    if ofac_hit:
        hard_decline, hard_reason = True, "OFAC SDN match — application cannot be processed"
        reasons.append(AAR.OFAC_MATCH)
    if not hard_decline and total_dti > HARD_DECLINE_DTI_MAX:
        hard_decline = True
        hard_reason = f"Total DTI {total_dti:.0%} exceeds maximum {HARD_DECLINE_DTI_MAX:.0%}"
        reasons += [AAR.DTI_TOO_HIGH, AAR.EXCESSIVE_OBLIGATIONS]
    fico_min = FICO_MIN_JUMBO if loan_type == "JUMBO_MORTGAGE" else FICO_MIN_CONVENTIONAL
    if not hard_decline and fico < fico_min:
        hard_decline = True
        hard_reason = f"FICO {fico} below minimum {fico_min} for {loan_type}"
        reasons.append(AAR.CREDIT_SCORE_TOO_LOW)
    if not hard_decline and bankruptcy:
        ch = bankruptcy.get("chapter")
        yrs = float(bankruptcy.get("discharge_years", 99))
        too_recent = ((ch == "CHAPTER_7" and yrs < BANKRUPTCY_CH7_SEASONING_YEARS) or
                      (ch == "CHAPTER_13" and yrs < BANKRUPTCY_CH13_SEASONING_YEARS))
        if too_recent:
            hard_decline = True
            hard_reason = f"{ch} discharged {yrs:.1f}y ago — insufficient seasoning"
            reasons.append(AAR.BANKRUPTCY)

    if hard_decline:
        composite = min(composite, 0.34)
        tier = "DECLINE"
    elif composite >= 0.75:
        tier = "APPROVE"
    elif composite >= 0.55:
        tier = "APPROVE_WITH_CONDITIONS"
    elif composite >= 0.35:
        tier = "REFER_TO_COMMITTEE"
    else:
        tier = "DECLINE"

    if tier == "DECLINE" and not reasons:
        if factors["credit"] < 0.30:
            reasons.append(AAR.POOR_CREDIT_PERFORMANCE)
        if factors["dti"] < 0.30:
            reasons.append(AAR.DTI_TOO_HIGH)
        if factors["ltv"] < 0.30:
            reasons.append(AAR.INADEQUATE_COLLATERAL)
        if factors["income"] < 0.5:
            reasons.append(AAR.INSUFFICIENT_INCOME)
        if not reasons:
            reasons.append(AAR.INSUFFICIENT_CREDIT_EXPERIENCE)

    # Reg B: a principal-reasons notice cites up to 4.
    reasons = list(dict.fromkeys(reasons))[:4]
    decision = "DECLINE" if tier == "DECLINE" else ("APPROVE" if tier == "APPROVE" else "REFER")
    return {
        "decision": decision,
        "tier": tier,
        "composite": composite,
        "factors": factors,
        "hard_decline": hard_decline,
        "hard_decline_reason": hard_reason,
        "adverse_action_reasons": reasons if decision == "DECLINE" else [],
    }


def routing_decision(evaluation: Dict[str, Any], fair_lending_flags: List[str] | None = None) -> Dict[str, Any]:
    """
    Deterministic routing + HITL. Fair-lending flags or non-clean tiers route to
    an underwriter/compliance gate; a clean APPROVE auto-routes.
    """
    fair_lending_flags = fair_lending_flags or []
    tier = evaluation["tier"]
    reasons: List[str] = []
    if fair_lending_flags:
        reasons.append("fair-lending flag — compliance officer review mandatory")
    if tier in ("REFER_TO_COMMITTEE", "DECLINE"):
        reasons.append(f"tier {tier} requires underwriter/committee review")
    if tier == "APPROVE_WITH_CONDITIONS":
        reasons.append("conditional approval requires underwriter sign-off")

    human_review_required = bool(reasons)
    if evaluation["decision"] == "DECLINE":
        nxt = "GenerateAdverseAction"
    elif human_review_required:
        nxt = "UnderwriterReviewGate"
    else:
        nxt = "AutoApprove"
    return {
        "decision": evaluation["decision"],
        "tier": tier,
        "human_review_required": human_review_required or evaluation["decision"] == "DECLINE",
        "fair_lending_flags": fair_lending_flags,
        "reasons": reasons,
        "next": nxt,
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
