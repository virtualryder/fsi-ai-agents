"""
Deterministic core for the AWS-native Model Risk Management agent (SR 11-7).

Faithful to 11-model-risk-agent: every risk determination — Gini/KS/PSI, the
degradation flags, the PSI classification, the HITL trigger conditions, and the
risk tier — is deterministic Python. The LLM only writes the validation
narrative. The Model Risk Officer (or CRO) signs every HIGH-tier outcome.

PSI = Σ (Actual% - Expected%) × ln(Actual% / Expected%); PSI<0.10 STABLE,
0.10-0.25 WARNING, >0.25 CRITICAL. The 9 ALWAYS_HITL conditions are immutable.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

PERFORMANCE_DEGRADATION_THRESHOLDS = {
    "psi_warning": 0.10, "psi_critical": 0.25,
    "gini_drop_points": 5.0, "ks_stat_drop_pct": 5.0, "auc_drop": 0.03, "fnr_increase": 0.05,
}

ALWAYS_HITL_CONDITIONS = frozenset({
    "HIGH_TIER_INITIAL_VALIDATION", "HIGH_TIER_CHANGE_VALIDATION",
    "PERFORMANCE_DEGRADATION_TRIGGERED", "PSI_CRITICAL", "ANNUAL_REVALIDATION_HIGH_TIER",
    "MATERIAL_FINDING", "CHALLENGER_UNDERPERFORMS", "HARD_RULE_VIOLATION_DETECTED",
    "FAIR_LENDING_FLAG",
})
# Conditions that escalate to the Chief Risk Officer (vs. the Model Risk Officer).
CRO_CONDITIONS = frozenset({"HARD_RULE_VIOLATION_DETECTED", "FAIR_LENDING_FLAG"})


def compute_psi(current_dist: Dict[str, float], baseline_dist: Dict[str, float]) -> float:
    """Population Stability Index — pure mathematics, no LLM."""
    psi = 0.0
    for bucket in set(list(current_dist) + list(baseline_dist)):
        actual = current_dist.get(bucket, 0.001)
        expected = baseline_dist.get(bucket, 0.001)
        if actual > 1:
            actual /= 100.0
        if expected > 1:
            expected /= 100.0
        psi += (actual - expected) * math.log(actual / expected)
    return round(abs(psi), 4)


def classify_psi(psi: float) -> str:
    if psi < PERFORMANCE_DEGRADATION_THRESHOLDS["psi_warning"]:
        return "STABLE"
    if psi < PERFORMANCE_DEGRADATION_THRESHOLDS["psi_critical"]:
        return "WARNING"
    return "CRITICAL"


def detect_degradation(metric_deltas: Dict[str, float]) -> List[str]:
    """Deterministic outcomes-analysis: Gini/KS/AUC drops, FNR increase."""
    t = PERFORMANCE_DEGRADATION_THRESHOLDS
    flags: List[str] = []
    if -metric_deltas.get("gini_coefficient", 0.0) > t["gini_drop_points"]:
        flags.append("GINI_DROP")
    if -metric_deltas.get("ks_statistic", 0.0) > t["ks_stat_drop_pct"]:
        flags.append("KS_DROP")
    if -metric_deltas.get("auc_roc", 0.0) > t["auc_drop"]:
        flags.append("AUC_DROP")
    if metric_deltas.get("fnr", 0.0) > t["fnr_increase"]:
        flags.append("FNR_INCREASE")
    return flags


def assess(model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic validation outcome: PSI, degradation, HITL conditions, reviewer.
    No LLM output participates.
    """
    risk_tier = (model.get("risk_tier") or "MEDIUM").upper()
    validation_type = (model.get("validation_type") or "ANNUAL").upper()
    psi = compute_psi(model.get("current_dist", {}), model.get("baseline_dist", {}))
    psi_class = classify_psi(psi)
    degradation = detect_degradation(model.get("metric_deltas", {}))

    conditions: List[str] = []
    if risk_tier == "HIGH":
        if validation_type == "INITIAL":
            conditions.append("HIGH_TIER_INITIAL_VALIDATION")
        elif validation_type == "CHANGE":
            conditions.append("HIGH_TIER_CHANGE_VALIDATION")
        elif validation_type == "ANNUAL":
            conditions.append("ANNUAL_REVALIDATION_HIGH_TIER")
    if psi_class == "CRITICAL":
        conditions.append("PSI_CRITICAL")
    if degradation:
        conditions.append("PERFORMANCE_DEGRADATION_TRIGGERED")
    if model.get("material_finding"):
        conditions.append("MATERIAL_FINDING")
    if model.get("challenger_underperforms"):
        conditions.append("CHALLENGER_UNDERPERFORMS")
    if model.get("hard_rule_violation"):
        conditions.append("HARD_RULE_VIOLATION_DETECTED")
    if model.get("fair_lending_flag"):
        conditions.append("FAIR_LENDING_FLAG")

    # Defensive: only recognized conditions count.
    triggered = [c for c in conditions if c in ALWAYS_HITL_CONDITIONS]
    human_review_required = bool(triggered)
    reviewer = "CHIEF_RISK_OFFICER" if any(c in CRO_CONDITIONS for c in triggered) else "MODEL_RISK_OFFICER"
    nxt = "ModelRiskReviewGate" if human_review_required else "Finalize"
    return {
        "model_id": model.get("model_id"), "risk_tier": risk_tier, "validation_type": validation_type,
        "psi": psi, "psi_class": psi_class, "degradation_flags": degradation,
        "hitl_conditions": triggered, "reviewer": reviewer,
        "human_review_required": human_review_required, "next": nxt,
    }


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    try:
        from fsi_agent_platform.pii import mask_obj
        return mask_obj(record)
    except Exception:
        return record, []
