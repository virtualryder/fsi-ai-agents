# tools/risk_scorer.py
# ============================================================
# Deterministic KYC Risk Scoring Model
#
# Computes a composite 0-100 risk score across 8 weighted dimensions.
# This is deterministic Python — NOT LLM output.
#
# SR 11-7 (Model Risk Management) compliance:
#   - Model must be documented with clear methodology
#   - Every component score must be explainable
#   - Weights must be justified and periodically validated
#   - Human override must be possible at every decision point
#   - Model performance must be monitored and back-tested
#
# Scoring methodology:
#   The weights below reflect FFIEC risk-based approach guidance,
#   placing highest weight on transaction behavior (reflects actual
#   money flow risk) and PEP status (FATF R.12 elevated risk).
# ============================================================

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Component weights — must sum to 1.0
# Validated against OCC/FFIEC risk weighting guidance
COMPONENT_WEIGHTS = {
    "transaction_behavior": 0.20,    # Actual money flow vs. expected profile
    "pep_status": 0.15,              # FATF R.12 — PEPs require elevated scoring
    "adverse_media": 0.15,           # News/regulatory findings
    "jurisdiction_risk": 0.15,       # Country/geography risk
    "document_completeness": 0.10,   # CDD file gaps create opacity risk
    "beneficial_ownership_clarity": 0.10,  # UBO transparency (FinCEN CDD Rule)
    "industry_risk": 0.10,           # NAICS code risk rating
    "account_tenure": 0.05,          # New relationships = higher inherent risk
}

# Industry risk ratings (FFIEC high-risk categories)
INDUSTRY_RISK_RATINGS = {
    "money_services": 90,
    "cannabis": 85,
    "casino_gaming": 80,
    "cryptocurrency": 80,
    "pawn_broker": 75,
    "used_car_dealer": 65,
    "jewelry_dealer": 65,
    "real_estate": 60,
    "import_export": 55,
    "foreign_exchange": 70,
    "check_cashing": 85,
    "shell_company": 95,
    "attorney_trust": 70,
    "restaurant": 30,
    "retail_trade": 25,
    "manufacturing": 30,
    "professional_services": 25,
    "healthcare": 35,
    "technology": 20,
}

# Jurisdiction risk scores (simplified — production: use FinCEN advisories + FATF grey/black lists)
JURISDICTION_RISK_SCORES = {
    "LOW": 20,
    "MEDIUM": 55,
    "HIGH": 85,
}

ADVERSE_MEDIA_SEVERITY_SCORES = {
    "NONE": 0,
    "LOW": 25,
    "MEDIUM": 50,
    "HIGH": 75,
    "CRITICAL": 95,
}


def compute_risk_score(
    customer_id: str,
    customer_type: str,
    jurisdiction_risk: str,
    pep_flag: bool,
    pep_category: str = None,
    adverse_media_severity: str = "NONE",
    cdd_completeness_score: float = 100.0,
    beneficial_owners: List[Dict] = None,
    business_type: str = None,
    watchlist_hits: List[Dict] = None,
    trigger_type: str = None,
) -> Dict[str, Any]:
    """
    Compute composite KYC risk score (0-100) across 8 weighted dimensions.

    Args:
        customer_id: For logging
        customer_type: Customer entity type
        jurisdiction_risk: LOW | MEDIUM | HIGH
        pep_flag: PEP indicator
        pep_category: Type of PEP (FOREIGN_PEP scores highest)
        adverse_media_severity: NONE/LOW/MEDIUM/HIGH/CRITICAL
        cdd_completeness_score: 0-100 completeness score
        beneficial_owners: UBO list
        business_type: Industry/NAICS
        watchlist_hits: Results from watchlist screening
        trigger_type: Review trigger type (some inflate scores)

    Returns:
        Dict with composite_score, components dict, top_factors list.
    """
    components = {}

    # ── 1. Transaction Behavior (20%) ──────────────────────────────────────
    # In production: compare recent transactions to expected profile
    # For this model: use trigger type as proxy
    txn_risk = 30  # Baseline
    if trigger_type in ["TRANSACTION_SPIKE", "SAR_FILED"]:
        txn_risk = 80
    elif trigger_type in ["NEW_PRODUCT", "JURISDICTION_CHANGE"]:
        txn_risk = 60
    components["transaction_behavior"] = txn_risk

    # ── 2. PEP Status (15%) ────────────────────────────────────────────────
    # Foreign PEPs (heads of state, senior foreign officials) score highest
    # per FATF R.12 which requires mandatory EDD for all PEPs
    if not pep_flag:
        pep_score = 0
    elif pep_category == "FOREIGN_PEP":
        pep_score = 95
    elif pep_category in ["DOMESTIC_PEP", "INTERNATIONAL_ORG_PEP"]:
        pep_score = 80
    elif pep_category in ["FAMILY_MEMBER", "CLOSE_ASSOCIATE"]:
        pep_score = 65
    else:
        pep_score = 70  # Unknown PEP category — default elevated
    components["pep_status"] = pep_score

    # ── 3. Adverse Media (15%) ─────────────────────────────────────────────
    components["adverse_media"] = ADVERSE_MEDIA_SEVERITY_SCORES.get(adverse_media_severity, 0)

    # ── 4. Jurisdiction Risk (15%) ─────────────────────────────────────────
    components["jurisdiction_risk"] = JURISDICTION_RISK_SCORES.get(jurisdiction_risk, 20)

    # ── 5. Document Completeness (10%) ────────────────────────────────────
    # Invert: high completeness = low risk contribution
    completeness_risk = max(0, 100 - cdd_completeness_score)
    components["document_completeness"] = completeness_risk

    # ── 6. Beneficial Ownership Clarity (10%) ─────────────────────────────
    # FinCEN CDD Rule: unclear UBO structure = higher opacity risk
    ubo_count = len(beneficial_owners or [])
    ubo_pep_flag = any(ubo.get("pep_flag") for ubo in (beneficial_owners or []))
    if ubo_count == 0 and customer_type not in ["INDIVIDUAL", "SOLE_PROPRIETOR"]:
        ubo_risk = 80  # Missing UBO information for entity = high risk
    elif ubo_pep_flag:
        ubo_risk = 75  # UBO is a PEP
    elif ubo_count > 5:
        ubo_risk = 50  # Complex ownership structure
    else:
        ubo_risk = 15
    components["beneficial_ownership_clarity"] = ubo_risk

    # ── 7. Industry Risk (10%) ────────────────────────────────────────────
    industry_score = INDUSTRY_RISK_RATINGS.get(
        (business_type or "").lower().replace(" ", "_"), 35
    )
    components["industry_risk"] = industry_score

    # ── 8. Account Tenure (5%) ────────────────────────────────────────────
    # New relationships have higher inherent risk (no baseline behavior)
    if trigger_type == "NEW_PRODUCT":
        tenure_risk = 70
    else:
        tenure_risk = 20  # Established relationship — lower baseline risk
    components["account_tenure"] = tenure_risk

    # ── Watchlist adjustment ───────────────────────────────────────────────
    # OFAC hits are handled as hard overrides in routing, but also
    # inflate the PEP/adverse media components for accurate scoring
    if watchlist_hits:
        ofac_hits = [h for h in watchlist_hits if "OFAC" in h.get("list_name", "")]
        if ofac_hits:
            components["pep_status"] = max(components["pep_status"], 95)
            components["adverse_media"] = max(components["adverse_media"], 90)

    # ── Composite weighted score ───────────────────────────────────────────
    composite = sum(
        components[key] * COMPONENT_WEIGHTS[key]
        for key in COMPONENT_WEIGHTS
        if key in components
    )
    composite = round(min(100.0, max(0.0, composite)), 1)

    # ── Top factors for narrative ──────────────────────────────────────────
    sorted_factors = sorted(
        [(key, score * COMPONENT_WEIGHTS[key]) for key, score in components.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    top_factors = [
        f"{key.replace('_', ' ').title()}: {components[key]:.0f}/100 (weight {COMPONENT_WEIGHTS[key]*100:.0f}%)"
        for key, _ in sorted_factors[:4]
    ]

    logger.info(
        f"Risk score for {customer_id}: {composite} "
        f"(PEP={components['pep_status']}, Media={components['adverse_media']}, "
        f"Jurisdiction={components['jurisdiction_risk']}, Industry={components['industry_risk']})"
    )

    return {
        "composite_score": composite,
        "components": components,
        "weights": COMPONENT_WEIGHTS,
        "top_factors": top_factors,
    }
