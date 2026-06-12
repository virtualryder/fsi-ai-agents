"""
Deterministic core for the AWS-native Regulatory Change Management agent.

Faithful to 06-regulatory-change-agent: the 5-factor impact score, tier
assignment, and hard overrides are deterministic Python (SR 11-7 documented
weights). The LLM only drafts the gap analysis and remediation narrative.

Weights (sum 1.0): authority_tier 0.25 · deadline_urgency 0.25 · scope_breadth
0.20 · policy_count 0.15 · change_type_risk 0.15.
Tiers: CRITICAL ≥0.85 · HIGH 0.65-0.84 · MEDIUM 0.40-0.64 · LOW <0.40.
Hard rules: ENFORCEMENT_ACTION → mandatory HITL + HIGH tier floor; an
already-effective FINAL_RULE → CRITICAL; a too-short compliance window for a
MEDIUM-tier change escalates it to HIGH.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

WEIGHTS = {"authority_tier": 0.25, "deadline_urgency": 0.25, "scope_breadth": 0.20,
           "policy_count": 0.15, "change_type_risk": 0.15}

AUTHORITY_TIER_SCORES = {"TIER_1": 1.0, "TIER_2": 0.70, "TIER_3": 0.40, "UNRECOGNIZED": 0.10}
CHANGE_TYPE_RISK = {"ENFORCEMENT_ACTION": 1.0, "FINAL_RULE": 0.85, "PROPOSED_RULE": 0.55,
                    "GUIDANCE": 0.45, "BULLETIN": 0.35, "SPEECH": 0.15}

CRITICAL_T, HIGH_T, MEDIUM_T = 0.85, 0.65, 0.40
TIER_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _deadline_urgency(days_to_effective: int) -> float:
    if days_to_effective <= 0:
        return 1.0
    if days_to_effective <= 30:
        return 0.90
    if days_to_effective <= 90:
        return 0.65
    if days_to_effective <= 180:
        return 0.45
    return 0.25


def compute_impact(source_tier: str, days_to_effective: int, business_lines: int,
                   products: int, mapped_policies: int, change_type: str) -> Tuple[float, Dict[str, float]]:
    factors = {
        "authority_tier": AUTHORITY_TIER_SCORES.get(source_tier, 0.10),
        "deadline_urgency": _deadline_urgency(days_to_effective),
        "scope_breadth": min(business_lines / 6.0, 1.0) * 0.6 + min(products / 8.0, 1.0) * 0.4,
        "policy_count": min(mapped_policies / 4.0, 1.0),
        "change_type_risk": CHANGE_TYPE_RISK.get(change_type, 0.40),
    }
    score = round(sum(factors[k] * w for k, w in WEIGHTS.items()), 3)
    return score, factors


def _tier_for(score: float) -> str:
    if score >= CRITICAL_T:
        return "CRITICAL"
    if score >= HIGH_T:
        return "HIGH"
    if score >= MEDIUM_T:
        return "MEDIUM"
    return "LOW"


def assess(change: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic impact assessment + tier + hard overrides + routing."""
    score, factors = compute_impact(
        source_tier=change.get("source_tier", "UNRECOGNIZED"),
        days_to_effective=int(change.get("days_to_effective", 365)),
        business_lines=int(change.get("business_lines_count", 0)),
        products=int(change.get("products_count", 0)),
        mapped_policies=int(change.get("mapped_policies_count", 0)),
        change_type=change.get("change_type", "GUIDANCE"),
    )
    tier = _tier_for(score)
    overrides: List[str] = []
    change_type = change.get("change_type", "")
    force_hitl = False

    if change_type == "ENFORCEMENT_ACTION":
        force_hitl = True
        if TIER_ORDER[tier] < TIER_ORDER["HIGH"]:
            tier = "HIGH"
        overrides.append("enforcement action — mandatory HITL + HIGH tier floor")
    if change_type == "FINAL_RULE" and change.get("already_effective"):
        tier = "CRITICAL"
        overrides.append("already-effective final rule — CRITICAL")
    if tier == "MEDIUM" and change.get("compliance_window_too_short"):
        tier = "HIGH"
        overrides.append("compliance window too short for complexity — escalated to HIGH")

    # CRITICAL/HIGH (or enforcement) require CCO review; MEDIUM/LOW do not.
    human_review_required = force_hitl or TIER_ORDER[tier] >= TIER_ORDER["HIGH"]
    nxt = "GapAnalysis" if human_review_required else "Finalize"
    return {
        "impact_score": score, "factors": factors, "tier": tier,
        "overrides": overrides, "human_review_required": human_review_required, "next": nxt,
    }


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    try:
        from fsi_agent_platform.pii import mask_obj
        return mask_obj(record)
    except Exception:
        return record, []
