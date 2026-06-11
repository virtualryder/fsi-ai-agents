"""
False Positive Classifier — rule-based pre-scoring layer.

Runs BEFORE the LLM call to:
1. Catch obvious false positives cheaply (high rule FP rate + known benign pattern)
2. Catch mandatory pass-throughs (PEP, watchlist hit, open investigation)
3. Produce a 0-100 rule-based FP score for LLM context

The composite final score weights:
  - Rule-based pre-filter:  30%
  - LLM analysis:           50%
  - Historical patterns:    20%

Each weight is justified by back-testing and documented per SR 11-7.
"""
from __future__ import annotations

import logging
from agent.state import ScoringFeatures

logger = logging.getLogger(__name__)

# ── Composite scoring weights ─────────────────────────────────────────────────
WEIGHT_RULE_BASED = 0.30
WEIGHT_LLM = 0.50
WEIGHT_HISTORICAL = 0.20

# ── Mandatory regulatory overrides ───────────────────────────────────────────
# Any of these conditions force the alert to ESCALATE regardless of FP score.
def check_regulatory_override(features: ScoringFeatures) -> tuple[bool, str]:
    """
    Return (should_override, reason) if a mandatory regulatory rule applies.

    Override conditions — documented per BSA policy:
    1. PEP flag: FATF R.12 requires enhanced scrutiny; AI cannot suppress
    2. Open investigation: alert must reach the active case
    3. OFAC-adjacent (high-risk geography + large wire + new account):
       combination that matches FinCEN typology patterns
    """
    if features.get("pep_flag"):
        return True, "Customer is a Politically Exposed Person (PEP) — FATF R.12 requires human review; AI suppression prohibited"

    if features.get("has_open_investigation"):
        return True, "Customer has an active open investigation — all alerts must reach the investigating analyst"

    # OFAC-adjacent: high-risk geography + significant wire + new account
    if (
        features.get("high_risk_geography")
        and features.get("amount_usd", 0) >= 50_000
        and features.get("account_age_days", 9999) < 180
        and features.get("prior_sars_filed", 0) == 0
    ):
        return True, (
            "Alert exhibits OFAC-adjacent profile: high-risk geography + "
            "large wire + new account + no SAR history — mandatory human review"
        )

    return False, ""


# ── Rule-based FP scoring ─────────────────────────────────────────────────────

def compute_rule_based_score(features: ScoringFeatures) -> tuple[float, list[str]]:
    """
    Compute a rule-based false positive score (0–100) and list of factors.

    Higher score = more likely to be a false positive.
    This is an additive scoring model — each rule contributes a weighted signal.

    Returns (score, factors_list).
    """
    score = 0.0
    factors: list[str] = []

    # ── Signal 1: Rule-level historical FP rate (strongest single predictor) ──
    rule_fp = features.get("rule_fp_rate", 0.5)
    rule_contribution = rule_fp * 35  # Max 35 pts
    score += rule_contribution
    if rule_fp >= 0.80:
        factors.append(
            f"Rule historical FP rate is {rule_fp:.0%} — very high false positive base rate"
        )
    elif rule_fp >= 0.60:
        factors.append(f"Rule historical FP rate is {rule_fp:.0%} — elevated false positive rate")

    # ── Signal 2: Customer historical FP rate ─────────────────────────────────
    cust_fp = features.get("customer_historical_fp_rate", 0.5)
    prior_count = features.get("customer_prior_alert_count", 0)
    if prior_count >= 2:  # Only weight if we have meaningful history
        cust_contribution = cust_fp * 20  # Max 20 pts
        score += cust_contribution
        if cust_fp >= 0.80 and prior_count >= 2:
            factors.append(
                f"Customer's last {prior_count} alert(s) were all false positives ({cust_fp:.0%} FP rate)"
            )

    # ── Signal 3: Amount vs. expected volume ──────────────────────────────────
    ratio = features.get("amount_vs_expected_ratio", 1.0)
    if ratio <= 0.5:
        # Alert amount is less than 50% of expected volume — highly consistent with normal ops
        score += 15
        factors.append(
            f"Alert amount is only {ratio:.0%} of expected monthly volume — consistent with normal activity"
        )
    elif ratio <= 1.0:
        score += 8
        factors.append(f"Alert amount is within expected monthly volume range ({ratio:.0%})")
    elif ratio > 3.0:
        # Amount far exceeds what's expected — reduces FP likelihood
        score = max(0, score - 10)
        factors.append(f"Alert amount is {ratio:.1f}x expected volume — anomalous relative to customer profile")

    # ── Signal 4: Account age (established accounts have known behavior) ──────
    age_days = features.get("account_age_days", 0)
    if age_days >= 1825:  # 5+ years
        score += 8
        factors.append(f"Established customer relationship ({age_days // 365} years) with documented activity patterns")
    elif age_days < 90:
        score = max(0, score - 5)
        factors.append(f"New account ({age_days} days old) — limited behavioral baseline")

    # ── Signal 5: Business type and typology match ────────────────────────────
    business_type = features.get("business_type", "")
    alert_type = features.get("alert_type", "")
    if business_type == "restaurant" and alert_type == "STRUCTURING":
        score += 10
        factors.append(
            "Restaurant businesses routinely handle high cash volumes — "
            "structuring alerts for this segment have a 87%+ FP rate"
        )
    elif business_type == "individual_consumer" and alert_type == "VELOCITY":
        score += 10
        factors.append(
            "Card velocity alerts for individual consumers are 92% false positives — "
            "typically travel or legitimate merchant activity"
        )
    elif business_type in ("shell_company",) and alert_type == "RAPID_MOVEMENT":
        score = max(0, score - 15)
        factors.append(
            "Shell company + rapid movement typology matches known layering patterns — "
            "strong indicator of genuine suspicious activity"
        )

    # ── Signal 6: Peer group FP rate ─────────────────────────────────────────
    peer_fp = features.get("peer_group_fp_rate", 0.5)
    if peer_fp >= 0.85:
        score += 7
        factors.append(
            f"Peer group ({business_type} + {features.get('risk_tier', 'UNKNOWN')} tier) "
            f"has {peer_fp:.0%} FP rate for this alert typology"
        )

    # ── Signal 7: Prior CTR filings (legitimizes cash activity) ──────────────
    ctr_count = features.get("prior_ctrs_filed", 0)
    if ctr_count >= 5 and alert_type == "STRUCTURING":
        score += 6
        factors.append(
            f"Customer has {ctr_count} prior CTR filings — cash activity is documented "
            "and reported, structuring alert is likely noise"
        )

    # ── Signal 8: Temporal patterns ───────────────────────────────────────────
    if features.get("is_month_end") and business_type in ("restaurant", "retail"):
        score += 4
        factors.append("Month-end timing consistent with normal business cash collection patterns")

    # Clamp to [0, 100]
    score = max(0.0, min(100.0, score))

    return round(score, 1), factors


def compute_historical_score(features: ScoringFeatures) -> float:
    """
    Distill historical pattern signals into a single 0–100 FP probability score.
    Used as the third component in the composite scoring formula.
    """
    rule_fp = features.get("rule_fp_rate", 0.5)
    typology_fp = features.get("typology_fp_rate", 0.5)
    peer_fp = features.get("peer_group_fp_rate", 0.5)
    cust_fp = features.get("customer_historical_fp_rate", 0.5)

    # Weighted average of historical signals
    # Rule FP rate is the strongest signal; customer FP rate is most specific
    score = (rule_fp * 0.35 + typology_fp * 0.25 + peer_fp * 0.20 + cust_fp * 0.20) * 100
    return round(score, 1)


def compute_composite_score(
    rule_based_score: float,
    llm_fp_probability: float,
    features: ScoringFeatures,
) -> tuple[float, dict[str, float]]:
    """
    Compute the final weighted composite FP probability score.

    Weights (documented per SR 11-7 model governance):
      Rule-based:  30% — fast, deterministic, interpretable
      LLM:         50% — contextual reasoning across multiple signals
      Historical:  20% — statistical base rates

    Returns (composite_score, score_breakdown).
    """
    historical_score = compute_historical_score(features)

    breakdown = {
        "rule_based_score": rule_based_score,
        "rule_based_weight": WEIGHT_RULE_BASED,
        "rule_based_contribution": round(rule_based_score * WEIGHT_RULE_BASED, 2),
        "llm_score": llm_fp_probability,
        "llm_weight": WEIGHT_LLM,
        "llm_contribution": round(llm_fp_probability * WEIGHT_LLM, 2),
        "historical_score": historical_score,
        "historical_weight": WEIGHT_HISTORICAL,
        "historical_contribution": round(historical_score * WEIGHT_HISTORICAL, 2),
    }

    composite = (
        rule_based_score * WEIGHT_RULE_BASED
        + llm_fp_probability * WEIGHT_LLM
        + historical_score * WEIGHT_HISTORICAL
    )

    breakdown["composite_fp_score"] = round(composite, 1)
    return round(composite, 1), breakdown


# ── Deterministic-only score (control-integrity, Phase 1.3) ──────────────────
# Weights for the deterministic gate (rule-based + historical, LLM EXCLUDED),
# renormalized so they sum to 1.0 on their own.
_DET_WEIGHT_TOTAL = WEIGHT_RULE_BASED + WEIGHT_HISTORICAL          # 0.50
_DET_WEIGHT_RULE = WEIGHT_RULE_BASED / _DET_WEIGHT_TOTAL           # 0.60
_DET_WEIGHT_HISTORICAL = WEIGHT_HISTORICAL / _DET_WEIGHT_TOTAL     # 0.40


def compute_deterministic_score(
    rule_based_score: float,
    features: ScoringFeatures,
) -> tuple[float, dict[str, float]]:
    """
    Deterministic-only false-positive score: the rule-based pre-score plus
    historical base rates, renormalized to 0-100. The LLM contextual score is
    deliberately EXCLUDED.

    This is the score that GATES SUPPRESSION — the only disposition that removes
    an alert from human review (see agent/nodes.py::determine_routing). Routing
    an alert out of the analyst queue must never depend on a model-generated
    number; it must rest on deterministic rules and statistical base rates that
    an examiner can reproduce. The LLM still authors the suppression
    justification narrative and can still force ESCALATE, but it can never be
    the reason an alert disappears.

    Returns (deterministic_fp_score, breakdown).
    """
    historical_score = compute_historical_score(features)
    score = (
        rule_based_score * _DET_WEIGHT_RULE
        + historical_score * _DET_WEIGHT_HISTORICAL
    )
    breakdown = {
        "rule_based_score": rule_based_score,
        "rule_based_weight": round(_DET_WEIGHT_RULE, 4),
        "rule_based_contribution": round(rule_based_score * _DET_WEIGHT_RULE, 2),
        "historical_score": historical_score,
        "historical_weight": round(_DET_WEIGHT_HISTORICAL, 4),
        "historical_contribution": round(historical_score * _DET_WEIGHT_HISTORICAL, 2),
        "llm_excluded": True,
        "deterministic_fp_score": round(score, 1),
    }
    return round(score, 1), breakdown
