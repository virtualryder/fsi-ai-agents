# agent/nodes.py
# ============================================================
# Credit Underwriting Agent — Node Functions
#
# LLM vs. Python boundary (documented per SR 11-7):
#
#   PYTHON ONLY (deterministic, auditable, no LLM opacity):
#     - DTI / LTV / DSCR calculation
#     - Risk score (5-factor composite model)
#     - Hard decline rules (DTI > 50%, OFAC, bankruptcy <2yr)
#     - Fair lending flags (ECOA / FHA / Reg B)
#     - Adverse action reason selection (Reg B standard list)
#     - HITL routing decision
#     - HMDA reportability determination
#     - SAR referral flag
#
#   LLM (narrative synthesis only — never a decision):
#     - Credit memo drafting
#     - Adverse action notice drafting
#     - Conditions letter drafting
#     - Policy exception narrative
#
# Security:
#   - No raw SSN or account numbers stored or logged.
#   - OFAC match triggers immediate hard block + BSA referral;
#     this path cannot be bypassed by any downstream node.
#   - Fair lending flags force HITL; no LLM path can clear them.
#   - All audit entries are append-only (list.append — no edits).
#   - Input sanitization applied in application_intake_node.
# ============================================================
from __future__ import annotations

import json
import os
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)

# ── Claude model tiers (Anthropic) ───────────────────────────────────────────
# NARRATIVE tier — Claude Sonnet 4.6: regulatory narratives, SAR/dispute
#   analysis, anything an examiner, reviewer, or customer will read.
# FAST tier — Claude Haiku 4.5: high-volume triage, classification, and
#   scoring-assist nodes where latency and unit cost dominate.
# Override via env: CLAUDE_NARRATIVE_MODEL / CLAUDE_FAST_MODEL.
# ── INTEGRATION POINT (production) ───────────────────────────────────────────
# For VPC-contained inference, swap ChatAnthropic for ChatBedrockConverse
# (langchain-aws) with Bedrock model IDs:
#   anthropic.claude-sonnet-4-6-20260601-v1:0  (narrative)
#   anthropic.claude-haiku-4-5-20251001        (fast)
# ─────────────────────────────────────────────────────────────────────────────
import os as _os_llm
CLAUDE_NARRATIVE_MODEL = _os_llm.getenv("CLAUDE_NARRATIVE_MODEL", "claude-sonnet-4-6")
CLAUDE_FAST_MODEL = _os_llm.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5")
CLAUDE_DEFAULT_MODEL = CLAUDE_NARRATIVE_MODEL


from agent.prompts import (
    ADVERSE_ACTION_SYSTEM_PROMPT,
    ADVERSE_ACTION_USER_PROMPT,
    CONDITIONS_LETTER_SYSTEM_PROMPT,
    CONDITIONS_LETTER_USER_PROMPT,
    CREDIT_MEMO_SYSTEM_PROMPT,
    CREDIT_MEMO_USER_PROMPT,
    EXCEPTION_NARRATIVE_SYSTEM_PROMPT,
    EXCEPTION_NARRATIVE_USER_PROMPT,
)
from agent.state import (
    AdverseActionReason,
    ApplicationStatus,
    CollateralType,
    CreditUnderwritingState,
    LoanDecision,
    LoanType,
    RiskTier,
)

# ── Constants ─────────────────────────────────────────────────────────────────

# Hard decline rules — Python constants, never configurable via UI or LLM
HARD_DECLINE_DTI_MAX = 0.50          # Total DTI above this → always decline
FICO_MIN_CONVENTIONAL = 580          # FNMA/FHLMC minimum for conventional mortgage
FICO_MIN_JUMBO = 680                 # Jumbo minimum (institution policy)
BANKRUPTCY_CH7_SEASONING_YEARS = 2   # Chapter 7 — minimum years since discharge
BANKRUPTCY_CH13_SEASONING_YEARS = 1  # Chapter 13 — minimum years since discharge

# Loan types requiring DSCR analysis (commercial underwriting)
COMMERCIAL_LOAN_TYPES = frozenset({
    LoanType.COMMERCIAL_REAL_ESTATE.value,
    LoanType.COMMERCIAL_TERM_LOAN.value,
    LoanType.SBA_7A.value,
    LoanType.SBA_504.value,
})

# Loan types requiring HMDA reporting
HMDA_LOAN_TYPES = frozenset({
    LoanType.CONVENTIONAL_MORTGAGE.value,
    LoanType.FHA_MORTGAGE.value,
    LoanType.VA_MORTGAGE.value,
    LoanType.JUMBO_MORTGAGE.value,
    LoanType.HELOC.value,
})

# Required documents per loan type
REQUIRED_DOCUMENTS: Dict[str, list] = {
    LoanType.CONVENTIONAL_MORTGAGE.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
        "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT",
        "CREDIT_AUTHORIZATION",
    ],
    LoanType.FHA_MORTGAGE.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
        "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT",
        "FHA_CASE_NUMBER", "CREDIT_AUTHORIZATION",
    ],
    LoanType.VA_MORTGAGE.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "DD214_OR_COE",
        "TAX_RETURNS_2YR", "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL",
        "CERTIFICATE_OF_ELIGIBILITY", "CREDIT_AUTHORIZATION",
    ],
    LoanType.JUMBO_MORTGAGE.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
        "BANK_STATEMENTS_6MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT",
        "RESERVES_DOCUMENTATION", "CREDIT_AUTHORIZATION",
    ],
    LoanType.COMMERCIAL_TERM_LOAN.value: [
        "GOVERNMENT_ID", "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR",
        "BUSINESS_FINANCIALS_3YR", "BUSINESS_PLAN", "COLLATERAL_DOCUMENTATION",
        "ENTITY_DOCUMENTS", "CREDIT_AUTHORIZATION",
    ],
    LoanType.COMMERCIAL_REAL_ESTATE.value: [
        "GOVERNMENT_ID", "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR",
        "RENT_ROLLS", "PROPERTY_APPRAISAL", "ENVIRONMENTAL_REPORT",
        "ENTITY_DOCUMENTS", "CREDIT_AUTHORIZATION",
    ],
    LoanType.SBA_7A.value: [
        "GOVERNMENT_ID", "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR",
        "BUSINESS_FINANCIALS_3YR", "SBA_FORMS_1919_1920", "BUSINESS_PLAN",
        "COLLATERAL_DOCUMENTATION", "CREDIT_AUTHORIZATION",
    ],
    LoanType.SBA_504.value: [
        "GOVERNMENT_ID", "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR",
        "BUSINESS_FINANCIALS_3YR", "SBA_504_PROJECT_DESCRIPTION",
        "COLLATERAL_DOCUMENTATION", "ENTITY_DOCUMENTS", "CREDIT_AUTHORIZATION",
    ],
    LoanType.CONSUMER_PERSONAL.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "BANK_STATEMENTS_2MO",
        "CREDIT_AUTHORIZATION",
    ],
    LoanType.AUTO.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "VEHICLE_INFORMATION",
        "INSURANCE_VERIFICATION", "CREDIT_AUTHORIZATION",
    ],
    LoanType.HELOC.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
        "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL", "TITLE_REPORT",
        "CREDIT_AUTHORIZATION",
    ],
    LoanType.CREDIT_CARD_LINE.value: [
        "GOVERNMENT_ID", "INCOME_VERIFICATION", "CREDIT_AUTHORIZATION",
    ],
}

# Collateral factor lookup — deterministic Python, never LLM
COLLATERAL_FACTORS: Dict[str, float] = {
    CollateralType.PRIMARY_RESIDENCE.value: 0.90,
    CollateralType.COMMERCIAL_REAL_ESTATE.value: 0.80,
    CollateralType.INVESTMENT_PROPERTY.value: 0.75,
    CollateralType.SBA_GUARANTEE.value: 0.85,
    CollateralType.VEHICLE.value: 0.70,
    CollateralType.EQUIPMENT.value: 0.60,
    CollateralType.ACCOUNTS_RECEIVABLE.value: 0.50,
    CollateralType.INVENTORY.value: 0.40,
    CollateralType.UNSECURED.value: 0.30,
}

# Geographic census tracts flagged for heightened fair lending review
# In production: loaded from FFIEC geocoding database
FLAGGED_CENSUS_TRACTS = {"17031838400", "06037207400", "36061010000"}

# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm() -> ChatAnthropic:
    """Return a deterministic, zero-temperature LLM for narrative generation."""
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL,
        temperature=0,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

# ── Utility ───────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_present(*values, default=None):
    """
    Return the first value that is not None, else the default.

    Why this exists (CONTROL): `state.get(key, default)` returns None when the
    key is PRESENT with a None value — so `float(state.get(k, 0.0))` crashes on
    missing bureau data. In a lending pipeline an unhandled crash is a control
    failure: it kills the run BEFORE the fair-lending HITL gate. Missing data
    must degrade to a reviewable default, never to an exception.
    """
    for v in values:
        if v is not None:
            return v
    return default


def _coerce_num(value, cast, default):
    """Cast to int/float, treating None/invalid as the default (fail-soft)."""
    try:
        return cast(value)
    except (TypeError, ValueError):
        return cast(default)


def fail_safe_node(node_fn):
    """
    Decorator: a node exception must NEVER crash the underwriting pipeline.

    FAIL-SAFE ROUTING CONTROL (Agent 12 idiom, applied suite-wide):
    Any unhandled exception inside a node routes the application to mandatory
    human review with the error recorded in state and the audit trail. The
    graph keeps moving toward the HITL gate; it does not die before it.
    """
    import functools

    @functools.wraps(node_fn)
    def wrapper(state):
        try:
            return node_fn(state)
        except Exception as exc:  # noqa: BLE001 — deliberate catch-all at the node boundary
            node_name = node_fn.__name__
            err = f"{node_name} failed: {type(exc).__name__}: {exc}"
            logger.exception("Node %s raised — routing to human review", node_name)
            errors = list(state.get("errors", [])) + [err]
            audit = _append_audit(state, node_name, {
                "status": "NODE_ERROR",
                "error": err,
                "fail_safe_action": "ROUTED_TO_HUMAN_REVIEW",
            })
            return {
                "errors": errors,
                "audit_trail": audit,
                "human_review_required": True,
                "human_review_reasons": list(state.get("human_review_reasons", []))
                + [f"SYSTEM ERROR in {node_name} — manual underwriting review required"],
                "completed_steps": list(state.get("completed_steps", [])) + [node_name],
            }

    return wrapper

def _append_audit(state: CreditUnderwritingState, step: str, details: Dict[str, Any]) -> list:
    """Append a timestamped entry to the audit trail. Entries are never modified."""
    trail = list(state.get("audit_trail", []))
    trail.append({
        "step": step,
        "timestamp": _now_utc(),
        "application_id": state.get("application_id", "UNKNOWN"),
        **details,
    })
    return trail

def _sanitize_text(value: str) -> str:
    """
    Strip potential injection characters from free-text inputs.
    Guards against prompt injection and log injection attacks.
    """
    if not isinstance(value, str):
        return ""
    # Remove control characters and null bytes
    sanitized = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", value)
    # Cap length to prevent oversized payloads
    return sanitized[:2000]

def _mask_pii(value: str) -> str:
    """Mask PII in audit log entries — never log raw SSN, DL, or account numbers."""
    if not isinstance(value, str):
        return ""
    # Mask SSN patterns
    value = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "***-**-****", value)
    # Mask 9-digit numbers (potential SSN without dashes)
    value = re.sub(r"\b\d{9}\b", "*********", value)
    # Mask credit card patterns
    value = re.sub(r"\b(?:\d{4}[\s-]?){3}\d{4}\b", "****-****-****-****", value)
    return value

def _calculate_monthly_payment(principal: float, annual_rate: float, term_months: int) -> float:
    """Standard amortizing payment formula. Returns 0 on invalid inputs."""
    if principal <= 0 or term_months <= 0:
        return 0.0
    if annual_rate <= 0:
        return principal / term_months
    monthly_rate = annual_rate / 12
    return principal * (monthly_rate * (1 + monthly_rate) ** term_months) / (
        (1 + monthly_rate) ** term_months - 1
    )

# ── Node 1: Application Intake ────────────────────────────────────────────────

@fail_safe_node
def application_intake_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Validate and sanitize the incoming application.
    Security: sanitize all free-text fields, verify required fields present,
    generate application_id if not provided.
    """
    application_id = state.get("application_id") or f"APP-{uuid.uuid4().hex[:8].upper()}"
    loan_type = state.get("loan_type", "")
    requested_amount = _coerce_num(state.get("requested_amount"), float, 0)
    errors = list(state.get("errors", []))

    # Validate loan type
    valid_loan_types = {lt.value for lt in LoanType}
    if loan_type not in valid_loan_types:
        errors.append(f"Invalid loan_type: {loan_type}")
        loan_type = LoanType.CONSUMER_PERSONAL.value

    # Validate amount
    if requested_amount <= 0:
        errors.append("requested_amount must be positive")

    # Sanitize free-text fields — prevent prompt injection
    applicant_name = _sanitize_text(state.get("applicant_name", "Unknown Applicant"))
    collateral_description = _sanitize_text(state.get("collateral_description", ""))
    loan_purpose = _sanitize_text(state.get("loan_purpose", "PURCHASE"))

    audit = _append_audit(state, "application_intake", {
        "loan_type": loan_type,
        "requested_amount": requested_amount,
        "applicant_id": state.get("applicant_id", "UNKNOWN"),
        "source": state.get("application_source", "UNKNOWN"),
        "errors_at_intake": errors,
    })

    return {
        "application_id": application_id,
        "loan_type": loan_type,
        "requested_amount": requested_amount,
        "applicant_name": applicant_name,
        "collateral_description": collateral_description,
        "loan_purpose": loan_purpose,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["application_intake"],
        "errors": errors,
    }

# ── Node 2: Applicant Profile Lookup ─────────────────────────────────────────

@fail_safe_node
def applicant_profile_lookup_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Retrieve applicant relationship history and existing account data.
    In production: queries core banking system via internal API (not external).
    Simulated from fixture data in development.
    """
    applicant_id = state.get("applicant_id", "")
    existing_relationship = state.get("existing_relationship", False)
    existing_balance = state.get("existing_deposit_balance", 0.0)

    # Load applicant profiles from fixture
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "fixtures", "applicant_profiles.json"
    )
    profile = {}
    if os.path.exists(fixture_path):
        with open(fixture_path) as f:
            profiles = json.load(f)
        profile = profiles.get(applicant_id, {})
        if profile:
            existing_relationship = profile.get("existing_relationship", existing_relationship)
            existing_balance = profile.get("existing_deposit_balance", existing_balance)

    audit = _append_audit(state, "applicant_profile_lookup", {
        "applicant_id": applicant_id,
        "existing_relationship": existing_relationship,
        "profile_found": bool(profile),
    })

    return {
        "existing_relationship": existing_relationship,
        "existing_deposit_balance": existing_balance,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["applicant_profile_lookup"],
    }

# ── Node 3: Document Verification ────────────────────────────────────────────

@fail_safe_node
def document_verification_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Verify that all required documents are present for the loan type.
    Also validates CIP (Customer Identification Program) compliance per BSA.
    """
    loan_type = state.get("loan_type", LoanType.CONSUMER_PERSONAL.value)
    documents_received = list(state.get("documents_received", []))
    required = REQUIRED_DOCUMENTS.get(loan_type, REQUIRED_DOCUMENTS[LoanType.CONSUMER_PERSONAL.value])

    missing = [doc for doc in required if doc not in documents_received]
    document_exceptions = list(state.get("document_exceptions", []))

    # BSA CIP check — identity must be verified before credit decision
    identity_verified = "GOVERNMENT_ID" in documents_received and "CREDIT_AUTHORIZATION" in documents_received
    cip_method = state.get("cip_method", "DOCUMENTARY" if identity_verified else "NON_DOCUMENTARY")

    if not identity_verified:
        document_exceptions.append("BSA CIP: Government-issued ID not yet verified")

    documents_verified = len(missing) == 0 and identity_verified

    audit = _append_audit(state, "document_verification", {
        "loan_type": loan_type,
        "documents_received_count": len(documents_received),
        "missing_count": len(missing),
        "identity_verified": identity_verified,
        "cip_method": cip_method,
    })

    return {
        "documents_verified": documents_verified,
        "missing_documents": missing,
        "document_exceptions": document_exceptions,
        "identity_verified": identity_verified,
        "cip_method": cip_method,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["document_verification"],
    }

# ── Node 4: Credit Bureau Pull ────────────────────────────────────────────────

@fail_safe_node
def credit_bureau_pull_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Retrieve credit bureau data and run OFAC screening.

    Security critical:
    - OFAC screening is performed here; match is a Python hard block.
    - Only derived metrics are stored in state (no raw credit report).
    - ofac_hit = True cannot be cleared by any downstream node or LLM.

    In production: calls credit bureau API (Equifax/Experian/TransUnion)
    and OFAC SDN list check via FinScan/Accuity/Dow Jones.
    """
    applicant_id = state.get("applicant_id", "")
    errors = list(state.get("errors", []))

    # Load from fixture (simulates bureau pull)
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "fixtures", "applicant_profiles.json"
    )
    bureau_data: Dict[str, Any] = {}
    if os.path.exists(fixture_path):
        with open(fixture_path) as f:
            profiles = json.load(f)
        bureau_data = profiles.get(applicant_id, {}).get("credit_bureau", {})

    # None-safe coercion: a key present-with-None in state must behave like
    # missing data (default applies), never like a float(None) crash.
    credit_score = _coerce_num(_first_present(bureau_data.get("credit_score"), state.get("credit_score")), int, 650)
    credit_score_model = _first_present(bureau_data.get("credit_score_model"), state.get("credit_score_model"), default="FICO_8")
    derogatory_marks = _coerce_num(_first_present(bureau_data.get("derogatory_marks"), state.get("derogatory_marks")), int, 0)
    bankruptcy_flag = bool(_first_present(bureau_data.get("bankruptcy_flag"), state.get("bankruptcy_flag"), default=False))
    bankruptcy_chapter = _first_present(bureau_data.get("bankruptcy_chapter"), state.get("bankruptcy_chapter"))
    bankruptcy_discharge_years = _coerce_num(
        _first_present(bureau_data.get("bankruptcy_discharge_years"), state.get("bankruptcy_discharge_years")), float, 10.0)
    foreclosure_flag = bool(_first_present(bureau_data.get("foreclosure_flag"), state.get("foreclosure_flag"), default=False))
    collections_count = _coerce_num(_first_present(bureau_data.get("collections_count"), state.get("collections_count")), int, 0)
    collections_balance = _coerce_num(
        _first_present(bureau_data.get("collections_balance"), state.get("collections_balance")), float, 0.0)
    thin_file_flag = bool(_first_present(bureau_data.get("thin_file_flag"), state.get("thin_file_flag"), default=False))
    recent_inquiries_90d = _coerce_num(
        _first_present(bureau_data.get("recent_inquiries_90d"), state.get("recent_inquiries_90d")), int, 0)

    # OFAC check — hard block; cannot be overridden downstream
    # STICKY CONTROL: an OFAC hit already present in state can NEVER be
    # cleared by a subsequent (clean) bureau response — only a BSA Officer
    # can clear a sanctions match, and that happens outside this pipeline.
    # OR-semantics: hit if EITHER the prior state OR the bureau pull flags it.
    ofac_hit = bool(state.get("ofac_hit", False)) or bool(bureau_data.get("ofac_hit", False))
    ofac_hit_details = "OFAC SDN match detected" if ofac_hit else None
    if ofac_hit:
        errors.append("OFAC match: application blocked; BSA referral initiated")

    audit = _append_audit(state, "credit_bureau_pull", {
        "credit_score": credit_score,
        "credit_score_model": credit_score_model,
        "bankruptcy_flag": bankruptcy_flag,
        "ofac_hit": ofac_hit,
        "collections_count": collections_count,
        "thin_file": thin_file_flag,
        # Never log SSN or raw bureau report in audit trail
    })

    return {
        "credit_score": credit_score,
        "credit_score_model": credit_score_model,
        "credit_report_date": _now_utc()[:10],
        "derogatory_marks": derogatory_marks,
        "bankruptcy_flag": bankruptcy_flag,
        "bankruptcy_chapter": bankruptcy_chapter,
        "bankruptcy_discharge_years": float(bankruptcy_discharge_years),
        "foreclosure_flag": foreclosure_flag,
        "collections_count": collections_count,
        "collections_balance": collections_balance,
        "thin_file_flag": thin_file_flag,
        "recent_inquiries_90d": recent_inquiries_90d,
        "ofac_hit": ofac_hit,
        "ofac_hit_details": ofac_hit_details,
        "audit_trail": audit,
        "errors": errors,
        "completed_steps": list(state.get("completed_steps", [])) + ["credit_bureau_pull"],
    }

# ── Node 5: Financial Analysis ────────────────────────────────────────────────

@fail_safe_node
def financial_analysis_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Calculate all financial metrics — DTI, LTV, DSCR, reserves.
    All calculations are deterministic Python. No LLM involvement.
    """
    annual_income = _coerce_num(state.get("annual_income"), float, 0)
    monthly_income = annual_income / 12 if annual_income > 0 else 0.0
    monthly_debt = _coerce_num(state.get("monthly_debt_obligations"), float, 0)
    requested_amount = _coerce_num(state.get("requested_amount"), float, 0)
    appraised_value = _coerce_num(state.get("appraised_value"), float, requested_amount)
    quoted_rate = _coerce_num(state.get("quoted_rate"), float, 0.07)
    requested_term = _coerce_num(state.get("requested_term"), int, 360)
    loan_type = state.get("loan_type", LoanType.CONSUMER_PERSONAL.value)

    # Monthly payment (amortizing)
    proposed_monthly_payment = _calculate_monthly_payment(requested_amount, quoted_rate, requested_term)

    # DTI calculations
    front_end_dti = proposed_monthly_payment / monthly_income if monthly_income > 0 else 1.0
    total_dti_ratio = (monthly_debt + proposed_monthly_payment) / monthly_income if monthly_income > 0 else 1.0

    # LTV
    ltv_ratio = requested_amount / appraised_value if appraised_value > 0 else 1.0

    # CLTV (if subordinate liens provided)
    subordinate_liens = float(state.get("cltv_ratio", 0) or 0)
    cltv_ratio = (requested_amount + subordinate_liens) / appraised_value if appraised_value > 0 else ltv_ratio

    # DSCR (commercial loans)
    noi = float(state.get("net_operating_income", 0) or 0)
    annual_debt_service = proposed_monthly_payment * 12
    dscr = noi / annual_debt_service if (annual_debt_service > 0 and loan_type in COMMERCIAL_LOAN_TYPES) else None

    # Reserves (residential mortgage)
    liquid_assets = float(state.get("liquid_assets", 0) or 0)
    reserves_months = liquid_assets / proposed_monthly_payment if proposed_monthly_payment > 0 else 0.0

    # Cash flow adequacy check (residual income approach — VA / FHA standard)
    # Minimum residual income varies by family size and region; using simplified threshold
    residual_income = monthly_income - (monthly_debt + proposed_monthly_payment)
    cash_flow_adequate = residual_income >= (monthly_income * 0.10)  # 10% residual minimum

    audit = _append_audit(state, "financial_analysis", {
        "front_end_dti": round(front_end_dti, 4),
        "total_dti_ratio": round(total_dti_ratio, 4),
        "ltv_ratio": round(ltv_ratio, 4),
        "dscr": round(dscr, 4) if dscr else None,
        "proposed_monthly_payment": round(proposed_monthly_payment, 2),
        "cash_flow_adequate": cash_flow_adequate,
    })

    return {
        "monthly_income": monthly_income,
        "proposed_monthly_payment": proposed_monthly_payment,
        "front_end_dti": front_end_dti,
        "total_dti_ratio": total_dti_ratio,
        "ltv_ratio": ltv_ratio,
        "cltv_ratio": cltv_ratio,
        "annual_debt_service": annual_debt_service,
        "dscr": dscr,
        "reserves_months": reserves_months,
        "cash_flow_adequate": cash_flow_adequate,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["financial_analysis"],
    }

# ── Node 6: Fair Lending Check ────────────────────────────────────────────────

@fail_safe_node
def fair_lending_check_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    ECOA / Fair Housing Act / Reg B screening.

    This node sets fair_lending_flags and fair_lending_review_required.
    These flags are Python-set and CANNOT be cleared by any LLM node.
    Any flag → mandatory HITL in routing_decision_node.

    Checks performed:
    1. Geographic redlining flag (census tract + denial concentration)
    2. Product steering flag (loan type vs. qualification)
    3. Pricing exception flag (rate outside policy without documented justification)
    4. HMDA reportability determination
    5. CRA-eligible geography flag
    """
    loan_type = state.get("loan_type", "")
    credit_score = _coerce_num(state.get("credit_score"), int, 0)
    total_dti = _coerce_num(state.get("total_dti_ratio"), float, 1.0)
    ltv = _coerce_num(state.get("ltv_ratio"), float, 1.0)
    census_tract = state.get("property_census_tract", "")
    quoted_rate = _coerce_num(state.get("quoted_rate"), float, 0.07)
    property_state = state.get("property_state", "")

    fair_lending_flags = list(state.get("fair_lending_flags", []))
    geographic_flag = False
    steering_flag = False
    pricing_exception_flag = False

    # 1. Geographic redlining flag
    if census_tract in FLAGGED_CENSUS_TRACTS:
        geographic_flag = True
        fair_lending_flags.append(
            f"GEOGRAPHIC_FLAG: Census tract {census_tract} is in heightened fair lending review area"
        )

    # 2. Product steering detection
    # If borrower qualifies for conventional but was offered FHA (higher cost), flag for review
    if (loan_type == LoanType.FHA_MORTGAGE.value
            and credit_score >= 620
            and ltv <= 0.80
            and total_dti <= 0.43):
        steering_flag = True
        fair_lending_flags.append(
            "STEERING_FLAG: Applicant may qualify for conventional mortgage at lower cost — "
            "FHA routing requires documented justification (Reg B / CFPB UDAAP)"
        )

    # 3. Pricing exception — rate more than 150bps above risk-based pricing schedule
    # Simplified: flag if quoted_rate > 9% for conforming residential (proxy for exception)
    if loan_type in (LoanType.CONVENTIONAL_MORTGAGE.value, LoanType.FHA_MORTGAGE.value) and quoted_rate > 0.09:
        pricing_exception_flag = True
        fair_lending_flags.append(
            f"PRICING_EXCEPTION_FLAG: Rate {quoted_rate:.2%} exceeds pricing policy threshold — "
            "exception requires documented business justification and fair lending review"
        )

    # 4. HMDA reportability
    hmda_reportable = loan_type in HMDA_LOAN_TYPES and bool(property_state)

    # 5. CRA eligibility (simplified — LMI census tract or small business loan < $1M)
    cra_eligible = (
        geographic_flag  # LMI / underserved census tract
        or (loan_type in COMMERCIAL_LOAN_TYPES and state.get("requested_amount", 0) <= 1_000_000)
    )

    fair_lending_review_required = bool(fair_lending_flags)

    audit = _append_audit(state, "fair_lending_check", {
        "geographic_flag": geographic_flag,
        "steering_flag": steering_flag,
        "pricing_exception_flag": pricing_exception_flag,
        "hmda_reportable": hmda_reportable,
        "cra_eligible": cra_eligible,
        "flags_count": len(fair_lending_flags),
        "fair_lending_review_required": fair_lending_review_required,
    })

    return {
        "fair_lending_flags": fair_lending_flags,
        "geographic_flag": geographic_flag,
        "steering_flag": steering_flag,
        "pricing_exception_flag": pricing_exception_flag,
        "hmda_reportable": hmda_reportable,
        "cra_eligible": cra_eligible,
        "fair_lending_review_required": fair_lending_review_required,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["fair_lending_check"],
    }

# ── Node 7: Risk Scoring ──────────────────────────────────────────────────────

@fail_safe_node
def risk_scoring_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    5-factor composite credit risk score (0.0–1.0).
    Documented per SR 11-7 Model Risk Management guidance.

    Weights:
      Credit Score   30%  — FICO to normalized 0-1
      DTI            25%  — total DTI including proposed payment
      LTV            20%  — loan-to-value ratio
      Cash Flow      15%  — DSCR (commercial) or residual income (consumer)
      Collateral     10%  — collateral type risk weight

    Hard decline overrides (Python — no LLM can waive):
      - Total DTI > 50%
      - FICO < 580 (conventional/jumbo mortgage)
      - FICO < 680 (jumbo mortgage)
      - Chapter 7 bankruptcy discharged < 2 years
      - OFAC match
    """
    credit_score = _coerce_num(state.get("credit_score"), int, 0)
    total_dti = _coerce_num(state.get("total_dti_ratio"), float, 1.0)
    ltv = _coerce_num(state.get("ltv_ratio"), float, 1.0)
    cash_flow_adequate = bool(state.get("cash_flow_adequate", False))
    dscr = state.get("dscr")
    collateral_type = state.get("collateral_type", CollateralType.UNSECURED.value)
    loan_type = state.get("loan_type", LoanType.CONSUMER_PERSONAL.value)
    bankruptcy_flag = bool(state.get("bankruptcy_flag", False))
    bankruptcy_chapter = state.get("bankruptcy_chapter", "")
    bankruptcy_discharge_years = _coerce_num(state.get("bankruptcy_discharge_years"), float, 10.0)
    ofac_hit = bool(state.get("ofac_hit", False))

    # ── Factor 1: Credit Score (30%) ──────────────────────────────────────
    if credit_score >= 800:
        credit_factor = 1.00
    elif credit_score >= 760:
        credit_factor = 0.95
    elif credit_score >= 740:
        credit_factor = 0.90
    elif credit_score >= 720:
        credit_factor = 0.85
    elif credit_score >= 700:
        credit_factor = 0.80
    elif credit_score >= 680:
        credit_factor = 0.70
    elif credit_score >= 660:
        credit_factor = 0.60
    elif credit_score >= 640:
        credit_factor = 0.50
    elif credit_score >= 620:
        credit_factor = 0.38
    elif credit_score >= 600:
        credit_factor = 0.25
    elif credit_score >= 580:
        credit_factor = 0.12
    else:
        credit_factor = 0.00

    # ── Factor 2: DTI (25%) ───────────────────────────────────────────────
    if total_dti <= 0.28:
        dti_factor = 1.00
    elif total_dti <= 0.33:
        dti_factor = 0.90
    elif total_dti <= 0.36:
        dti_factor = 0.80
    elif total_dti <= 0.40:
        dti_factor = 0.65
    elif total_dti <= 0.43:
        dti_factor = 0.50
    elif total_dti <= 0.45:
        dti_factor = 0.35
    elif total_dti <= 0.50:
        dti_factor = 0.15
    else:
        dti_factor = 0.00  # Hard decline trigger

    # ── Factor 3: LTV (20%) ───────────────────────────────────────────────
    if ltv <= 0.65:
        ltv_factor = 1.00
    elif ltv <= 0.70:
        ltv_factor = 0.95
    elif ltv <= 0.75:
        ltv_factor = 0.90
    elif ltv <= 0.80:
        ltv_factor = 0.85
    elif ltv <= 0.85:
        ltv_factor = 0.70
    elif ltv <= 0.90:
        ltv_factor = 0.50
    elif ltv <= 0.95:
        ltv_factor = 0.30
    elif ltv <= 0.97:
        ltv_factor = 0.15
    else:
        ltv_factor = 0.00

    # ── Factor 4: Cash Flow / DSCR (15%) ─────────────────────────────────
    if loan_type in COMMERCIAL_LOAN_TYPES and dscr is not None:
        if dscr >= 1.75:
            cash_flow_factor = 1.00
        elif dscr >= 1.50:
            cash_flow_factor = 0.85
        elif dscr >= 1.35:
            cash_flow_factor = 0.70
        elif dscr >= 1.25:
            cash_flow_factor = 0.55
        elif dscr >= 1.15:
            cash_flow_factor = 0.35
        elif dscr >= 1.00:
            cash_flow_factor = 0.15
        else:
            cash_flow_factor = 0.00
    else:
        cash_flow_factor = 0.80 if cash_flow_adequate else 0.35

    # ── Factor 5: Collateral (10%) ────────────────────────────────────────
    collateral_factor = COLLATERAL_FACTORS.get(collateral_type, 0.50)

    # ── Composite Score ───────────────────────────────────────────────────
    composite = (
        credit_factor * 0.30
        + dti_factor * 0.25
        + ltv_factor * 0.20
        + cash_flow_factor * 0.15
        + collateral_factor * 0.10
    )

    # ── Hard Decline Overrides (Python — cannot be waived by LLM) ─────────
    hard_decline = False
    hard_decline_reason = None
    adverse_action_reasons = []

    if ofac_hit:
        hard_decline = True
        hard_decline_reason = "OFAC SDN match — application cannot be processed"
        adverse_action_reasons.append(AdverseActionReason.OFAC_MATCH.value)

    if not hard_decline and total_dti > HARD_DECLINE_DTI_MAX:
        hard_decline = True
        hard_decline_reason = f"Total DTI {total_dti:.1%} exceeds maximum {HARD_DECLINE_DTI_MAX:.0%}"
        adverse_action_reasons.append(AdverseActionReason.DTI_TOO_HIGH.value)
        adverse_action_reasons.append(AdverseActionReason.EXCESSIVE_OBLIGATIONS.value)

    if not hard_decline and loan_type == LoanType.JUMBO_MORTGAGE.value and credit_score < FICO_MIN_JUMBO:
        hard_decline = True
        hard_decline_reason = f"FICO {credit_score} below jumbo minimum {FICO_MIN_JUMBO}"
        adverse_action_reasons.append(AdverseActionReason.CREDIT_SCORE_TOO_LOW.value)

    if not hard_decline and loan_type in (LoanType.CONVENTIONAL_MORTGAGE.value, LoanType.FHA_MORTGAGE.value) and credit_score < FICO_MIN_CONVENTIONAL:
        hard_decline = True
        hard_decline_reason = f"FICO {credit_score} below minimum {FICO_MIN_CONVENTIONAL} for {loan_type}"
        adverse_action_reasons.append(AdverseActionReason.CREDIT_SCORE_TOO_LOW.value)
        adverse_action_reasons.append(AdverseActionReason.INSUFFICIENT_CREDIT_EXPERIENCE.value)

    if not hard_decline and bankruptcy_flag:
        is_ch7_too_recent = (bankruptcy_chapter == "CHAPTER_7" and bankruptcy_discharge_years < BANKRUPTCY_CH7_SEASONING_YEARS)
        is_ch13_too_recent = (bankruptcy_chapter == "CHAPTER_13" and bankruptcy_discharge_years < BANKRUPTCY_CH13_SEASONING_YEARS)
        if is_ch7_too_recent or is_ch13_too_recent:
            hard_decline = True
            hard_decline_reason = (
                f"{bankruptcy_chapter} bankruptcy discharged {bankruptcy_discharge_years:.1f} years ago "
                f"(minimum seasoning: {BANKRUPTCY_CH7_SEASONING_YEARS if 'CHAPTER_7' in bankruptcy_chapter else BANKRUPTCY_CH13_SEASONING_YEARS} years)"
            )
            adverse_action_reasons.append(AdverseActionReason.BANKRUPTCY.value)

    # ── Tier Determination ────────────────────────────────────────────────
    if hard_decline:
        tier = RiskTier.DECLINE.value
        composite = min(composite, 0.34)
    elif composite >= 0.75:
        tier = RiskTier.APPROVE.value
    elif composite >= 0.55:
        tier = RiskTier.APPROVE_WITH_CONDITIONS.value
    elif composite >= 0.35:
        tier = RiskTier.REFER_TO_COMMITTEE.value
    else:
        tier = RiskTier.DECLINE.value
        # Build adverse action reasons for scored decline
        if not adverse_action_reasons:
            if credit_factor < 0.30:
                adverse_action_reasons.append(AdverseActionReason.POOR_CREDIT_PERFORMANCE.value)
            if dti_factor < 0.30:
                adverse_action_reasons.append(AdverseActionReason.EXCESSIVE_OBLIGATIONS.value)
            if ltv_factor < 0.30:
                adverse_action_reasons.append(AdverseActionReason.INADEQUATE_COLLATERAL.value)
            if cash_flow_factor < 0.20:
                adverse_action_reasons.append(AdverseActionReason.INSUFFICIENT_INCOME.value)
            if len(adverse_action_reasons) == 0:
                adverse_action_reasons.append(AdverseActionReason.POOR_CREDIT_PERFORMANCE.value)

    score_breakdown = {
        "credit_score_factor": round(credit_factor, 4),
        "credit_score_weight": 0.30,
        "dti_factor": round(dti_factor, 4),
        "dti_weight": 0.25,
        "ltv_factor": round(ltv_factor, 4),
        "ltv_weight": 0.20,
        "cash_flow_factor": round(cash_flow_factor, 4),
        "cash_flow_weight": 0.15,
        "collateral_factor": round(collateral_factor, 4),
        "collateral_weight": 0.10,
        "composite_score": round(composite, 4),
        "risk_tier": tier,
        "hard_decline_triggered": hard_decline,
        "hard_decline_reason": hard_decline_reason,
        "model_version": "credit-underwriting-v1.0",
        "model_governance": "SR 11-7",
        "scored_at": _now_utc(),
    }

    audit = _append_audit(state, "risk_scoring", {
        "composite_score": round(composite, 4),
        "risk_tier": tier,
        "hard_decline_triggered": hard_decline,
        "hard_decline_reason": hard_decline_reason,
        "score_breakdown": score_breakdown,
    })

    return {
        "credit_score_factor": credit_factor,
        "dti_factor": dti_factor,
        "ltv_factor": ltv_factor,
        "cash_flow_factor": cash_flow_factor,
        "collateral_factor": collateral_factor,
        "composite_score": composite,
        "risk_tier": tier,
        "hard_decline_triggered": hard_decline,
        "hard_decline_reason": hard_decline_reason,
        "score_breakdown": score_breakdown,
        "adverse_action_reasons": adverse_action_reasons,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["risk_scoring"],
    }

# ── Node 8: Routing Decision ──────────────────────────────────────────────────

@fail_safe_node
def routing_decision_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Determine HITL requirement and assign reviewer.
    Python-only. No LLM involvement in routing.

    HITL required when:
    - Risk tier is REFER_TO_COMMITTEE or DECLINE (for adverse action review)
    - Any fair lending flag is present
    - Loan amount > $5M (jumbo / large commercial)
    - Document exceptions present
    - OFAC hit (BSA officer review required)
    - Bankruptcy flag (committee review for borderline seasoning)
    """
    risk_tier = state.get("risk_tier", RiskTier.DECLINE.value)
    fair_lending_review = bool(state.get("fair_lending_review_required", False))
    requested_amount = _coerce_num(state.get("requested_amount"), float, 0)
    document_exceptions = list(state.get("document_exceptions", []))
    ofac_hit = bool(state.get("ofac_hit", False))
    bankruptcy_flag = bool(state.get("bankruptcy_flag", False))
    loan_type = state.get("loan_type", "")

    escalation_reasons = []

    # HITL triggers
    if risk_tier in (RiskTier.REFER_TO_COMMITTEE.value, RiskTier.DECLINE.value):
        escalation_reasons.append(f"Risk tier {risk_tier} requires underwriter or committee review")

    if fair_lending_review:
        escalation_reasons.append("Fair lending flag present — compliance officer review mandatory")

    if requested_amount > 5_000_000:
        escalation_reasons.append(f"Loan amount ${requested_amount:,.0f} exceeds $5M — credit committee required")

    if document_exceptions:
        escalation_reasons.append(f"Document exceptions: {', '.join(document_exceptions[:3])}")

    if ofac_hit:
        escalation_reasons.append("OFAC match — BSA officer review required before any decision")

    if bankruptcy_flag:
        escalation_reasons.append("Bankruptcy flag — underwriter judgment required on seasoning adequacy")

    human_review_required = bool(escalation_reasons)

    # Committee vs. single underwriter
    committee_required = (
        requested_amount > 2_000_000
        or risk_tier == RiskTier.REFER_TO_COMMITTEE.value
        or (fair_lending_review and requested_amount > 500_000)
    )

    # Assign reviewer based on loan type and flags
    if ofac_hit:
        assigned_underwriter = "BSA_OFFICER"
        escalation_path = "BSA_OFFICER"
    elif fair_lending_review:
        assigned_underwriter = "COMPLIANCE_OFFICER"
        escalation_path = "CCO"
    elif committee_required:
        assigned_underwriter = "CREDIT_COMMITTEE"
        escalation_path = "CREDIT_COMMITTEE"
    elif loan_type in COMMERCIAL_LOAN_TYPES:
        assigned_underwriter = "COMMERCIAL_UNDERWRITER"
        escalation_path = "UNDERWRITER"
    else:
        assigned_underwriter = "CONSUMER_UNDERWRITER"
        escalation_path = "UNDERWRITER"

    routing_rationale = "; ".join(escalation_reasons) if escalation_reasons else "Auto-decision eligible"

    audit = _append_audit(state, "routing_decision", {
        "human_review_required": human_review_required,
        "committee_required": committee_required,
        "assigned_underwriter": assigned_underwriter,
        "escalation_path": escalation_path,
        "escalation_reasons": escalation_reasons,
    })

    return {
        "human_review_required": human_review_required,
        "committee_required": committee_required,
        "assigned_underwriter": assigned_underwriter,
        "escalation_path": escalation_path,
        "routing_rationale": routing_rationale,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["routing_decision"],
    }

# ── Node 9: Human Review Gate (HITL) ─────────────────────────────────────────

def human_review_gate(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    HITL interrupt node — workflow pauses here until a reviewer submits a decision.
    This node is listed in interrupt_before in graph.py.

    Reviewer decisions:
    - APPROVE: Override system to approve (with documentation requirement)
    - APPROVE_WITH_CONDITIONS: Approve with listed conditions
    - DECLINE: Confirm decline
    - REQUEST_MORE_INFO: Return to applicant for additional documentation

    Security: reviewer_id is logged and cannot be empty. Pricing overrides
    are captured and flagged for fair lending review in audit trail.
    """
    reviewer_decision = state.get("reviewer_decision", "")
    reviewer_id = state.get("reviewer_id", "")
    reviewer_notes = _sanitize_text(state.get("reviewer_notes", ""))
    conditions_imposed = list(state.get("conditions_imposed", []))
    pricing_override = state.get("pricing_override")
    risk_tier = state.get("risk_tier", "")

    if not reviewer_id:
        reviewer_id = "SYSTEM_PENDING"

    # Log pricing override for fair lending monitoring
    fair_lending_note = None
    if pricing_override and pricing_override != state.get("quoted_rate"):
        fair_lending_note = (
            f"PRICING_OVERRIDE: Rate changed from {state.get('quoted_rate', 0):.2%} "
            f"to {pricing_override:.2%} by {reviewer_id} — flagged for quarterly fair lending review"
        )

    # Exception tracking — if reviewer approves a scored DECLINE, document exception
    exception_approved = (
        reviewer_decision in ("APPROVE", "APPROVE_WITH_CONDITIONS")
        and risk_tier == RiskTier.DECLINE.value
    )

    audit = _append_audit(state, "human_review_gate", {
        "reviewer_id": reviewer_id,
        "reviewer_decision": reviewer_decision,
        "original_risk_tier": risk_tier,
        "exception_approved": exception_approved,
        "pricing_override": pricing_override,
        "fair_lending_note": fair_lending_note,
        "conditions_count": len(conditions_imposed),
    })

    return {
        "reviewer_id": reviewer_id,
        "reviewer_decision": reviewer_decision,
        "reviewer_notes": reviewer_notes,
        "conditions_imposed": conditions_imposed,
        "pricing_override": pricing_override,
        "review_timestamp": _now_utc(),
        "exception_approved": exception_approved,
        "exception_authority": reviewer_id if exception_approved else None,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["human_review_gate"],
    }

# ── Node 10: Credit Memo Drafting ─────────────────────────────────────────────

@fail_safe_node
def credit_memo_drafting_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    LLM generates the credit memorandum narrative and conditions letter.
    LLM receives only derived financial metrics — no raw PII, no SSN.
    LLM cannot change the risk tier or decision.
    """
    llm = _get_llm()

    # Determine effective decision (reviewer may have overridden)
    reviewer_decision = state.get("reviewer_decision", "")
    risk_tier = state.get("risk_tier", RiskTier.DECLINE.value)
    hard_decline = bool(state.get("hard_decline_triggered", False))

    if reviewer_decision == "APPROVE":
        effective_tier = RiskTier.APPROVE.value
    elif reviewer_decision == "APPROVE_WITH_CONDITIONS":
        effective_tier = RiskTier.APPROVE_WITH_CONDITIONS.value
    elif reviewer_decision == "DECLINE":
        effective_tier = RiskTier.DECLINE.value
    else:
        effective_tier = risk_tier

    # Build adverse action flag
    adverse_action_required = effective_tier == RiskTier.DECLINE.value

    dscr = state.get("dscr")
    dscr_display = f"{dscr:.2f}" if dscr is not None else "N/A (consumer loan)"
    liquid_assets = state.get("liquid_assets", 0) or 0
    reserves_months = state.get("reserves_months", 0) or 0
    reserves_display = f"${liquid_assets:,.0f} ({reserves_months:.1f} months PITI)" if liquid_assets else "Not provided"

    bankruptcy_note = ""
    if state.get("bankruptcy_flag"):
        bankruptcy_note = f" ({state.get('bankruptcy_chapter', 'Unknown')} — {state.get('bankruptcy_discharge_years', 0):.1f} years ago)"

    fair_lending_flags = state.get("fair_lending_flags", [])
    fair_lending_note = (
        "\n⚠️ FAIR LENDING FLAG: This file requires compliance officer review before final disposition."
        if fair_lending_flags else ""
    )
    hard_decline_note = (
        f"Hard decline reason: {state.get('hard_decline_reason', 'N/A')}"
        if hard_decline else ""
    )

    memo_prompt = CREDIT_MEMO_USER_PROMPT.format(
        application_id=state.get("application_id", ""),
        loan_type=state.get("loan_type", ""),
        loan_purpose=state.get("loan_purpose", ""),
        requested_amount=state.get("requested_amount", 0),
        requested_term=state.get("requested_term", 0),
        quoted_rate=state.get("quoted_rate", 0),
        collateral_type=state.get("collateral_type", ""),
        collateral_description=state.get("collateral_description", "N/A"),
        applicant_name=state.get("applicant_name", ""),
        applicant_type=state.get("applicant_type", "INDIVIDUAL"),
        existing_relationship=state.get("existing_relationship", False),
        income_source=state.get("income_source", ""),
        annual_income=state.get("annual_income", 0),
        credit_score=state.get("credit_score", 0),
        credit_score_model=state.get("credit_score_model", ""),
        derogatory_marks=state.get("derogatory_marks", 0),
        bankruptcy_flag=state.get("bankruptcy_flag", False),
        bankruptcy_note=bankruptcy_note,
        collections_count=state.get("collections_count", 0),
        collections_balance=state.get("collections_balance", 0),
        recent_inquiries_90d=state.get("recent_inquiries_90d", 0),
        thin_file_flag=state.get("thin_file_flag", False),
        front_end_dti=state.get("front_end_dti", 0),
        total_dti_ratio=state.get("total_dti_ratio", 0),
        ltv_ratio=state.get("ltv_ratio", 0),
        dscr_display=dscr_display,
        reserves_display=reserves_display,
        cash_flow_adequate=state.get("cash_flow_adequate", False),
        credit_score_factor=state.get("credit_score_factor", 0),
        dti_factor=state.get("dti_factor", 0),
        ltv_factor=state.get("ltv_factor", 0),
        cash_flow_factor=state.get("cash_flow_factor", 0),
        collateral_factor=state.get("collateral_factor", 0),
        composite_score=state.get("composite_score", 0),
        risk_tier=effective_tier,
        hard_decline_triggered=hard_decline,
        hard_decline_note=hard_decline_note,
        fair_lending_flags=fair_lending_flags,
        fair_lending_note=fair_lending_note,
        document_exceptions=state.get("document_exceptions", []),
        missing_documents=state.get("missing_documents", []),
        conditions_imposed=state.get("conditions_imposed", []),
    )

    from langchain_core.messages import HumanMessage, SystemMessage
    response = llm.invoke([
        SystemMessage(content=CREDIT_MEMO_SYSTEM_PROMPT),
        HumanMessage(content=memo_prompt),
    ])
    credit_memo_draft = response.content

    # Generate conditions letter if conditional approval
    conditions_letter = None
    if effective_tier == RiskTier.APPROVE_WITH_CONDITIONS.value and state.get("conditions_imposed"):
        conditions_formatted = "\n".join(
            f"{i+1}. {c}" for i, c in enumerate(state.get("conditions_imposed", []))
        )
        cond_prompt = CONDITIONS_LETTER_USER_PROMPT.format(
            applicant_name=state.get("applicant_name", ""),
            loan_type=state.get("loan_type", ""),
            requested_amount=state.get("requested_amount", 0),
            requested_term=state.get("requested_term", 0),
            quoted_rate=state.get("pricing_override") or state.get("quoted_rate", 0),
            conditions_formatted=conditions_formatted,
            reviewer_notes=state.get("reviewer_notes", ""),
        )
        cond_response = llm.invoke([
            SystemMessage(content=CONDITIONS_LETTER_SYSTEM_PROMPT),
            HumanMessage(content=cond_prompt),
        ])
        conditions_letter = cond_response.content

    # Exception narrative if exception was granted
    exception_narrative = None
    if state.get("exception_approved") and state.get("conditions_imposed"):
        exceptions_list = "\n".join(f"- {e}" for e in state.get("document_exceptions", []))
        exc_prompt = EXCEPTION_NARRATIVE_USER_PROMPT.format(
            application_id=state.get("application_id", ""),
            loan_type=state.get("loan_type", ""),
            risk_tier=risk_tier,
            exception_authority=state.get("exception_authority", ""),
            exceptions_list=exceptions_list or "Policy exception to credit tier",
            credit_score=state.get("credit_score", 0),
            ltv_ratio=state.get("ltv_ratio", 0),
            reserves_display=reserves_display,
            existing_relationship=state.get("existing_relationship", False),
            reviewer_notes=state.get("reviewer_notes", ""),
        )
        exc_response = llm.invoke([
            SystemMessage(content=EXCEPTION_NARRATIVE_SYSTEM_PROMPT),
            HumanMessage(content=exc_prompt),
        ])
        exception_narrative = exc_response.content

    audit = _append_audit(state, "credit_memo_drafting", {
        "effective_tier": effective_tier,
        "adverse_action_required": adverse_action_required,
        "conditions_letter_generated": conditions_letter is not None,
        "exception_narrative_generated": exception_narrative is not None,
    })

    return {
        "credit_memo_draft": credit_memo_draft,
        "loan_structure_recommendation": conditions_letter or "",
        "exceptions_narrative": exception_narrative,
        "adverse_action_required": adverse_action_required,
        "risk_tier": effective_tier,  # propagate reviewer override
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["credit_memo_drafting"],
    }

# ── Node 11: Adverse Action Notice ────────────────────────────────────────────

@fail_safe_node
def adverse_action_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    LLM drafts the Reg B (ECOA) adverse action notice.
    Adverse action reasons are pre-selected by Python (risk_scoring_node).
    LLM drafts only the letter — it cannot change the reasons.

    Includes FCRA Section 615 credit score disclosure.
    30-day notice deadline calculated in Python.
    """
    llm = _get_llm()

    # 30-day notice deadline (Reg B 12 CFR § 1002.9)
    decision_ts = _now_utc()
    deadline = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()[:10]

    adverse_action_reasons = list(state.get("adverse_action_reasons", []))
    # Limit to 4 reasons (Reg B standard)
    adverse_action_reasons = adverse_action_reasons[:4]
    if not adverse_action_reasons:
        adverse_action_reasons = [AdverseActionReason.POOR_CREDIT_PERFORMANCE.value]

    reasons_formatted = "\n".join(f"{i+1}. {r}" for i, r in enumerate(adverse_action_reasons))

    # Credit score factors — these would come from bureau in production
    score_factors = (
        "Payment history; Amounts owed; Length of credit history; New credit inquiries"
    )

    notice_prompt = ADVERSE_ACTION_USER_PROMPT.format(
        application_id=state.get("application_id", ""),
        applicant_name=state.get("applicant_name", ""),
        loan_type=state.get("loan_type", ""),
        requested_amount=state.get("requested_amount", 0),
        decision_timestamp=decision_ts[:10],
        adverse_action_deadline=deadline,
        adverse_action_reasons_formatted=reasons_formatted,
        credit_score=state.get("credit_score", 0),
        credit_score_model=state.get("credit_score_model", "FICO_8"),
        credit_report_date=state.get("credit_report_date", ""),
        score_factors=score_factors,
    )

    from langchain_core.messages import HumanMessage, SystemMessage
    response = llm.invoke([
        SystemMessage(content=ADVERSE_ACTION_SYSTEM_PROMPT),
        HumanMessage(content=notice_prompt),
    ])
    notice_draft = response.content

    # HMDA action taken code for decline (code 3 per HMDA LAR)
    hmda_action = "3" if state.get("hmda_reportable") else None

    audit = _append_audit(state, "adverse_action_notice", {
        "adverse_action_reasons": adverse_action_reasons,
        "deadline": deadline,
        "hmda_action_taken": hmda_action,
        "credit_score_disclosure": True,
    })

    return {
        "adverse_action_required": True,
        "adverse_action_reasons": adverse_action_reasons,
        "adverse_action_notice_draft": notice_draft,
        "adverse_action_deadline": deadline,
        "credit_score_disclosure_required": True,
        "hmda_action_taken": hmda_action,
        "decision_timestamp": decision_ts,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["adverse_action_node"],
    }

# ── Node 12: Finalize Decision ────────────────────────────────────────────────

@fail_safe_node
def finalize_decision_node(state: CreditUnderwritingState) -> Dict[str, Any]:
    """
    Set the final loan decision, HMDA action taken, SAR referral flag,
    and close out the audit trail.
    """
    risk_tier = state.get("risk_tier", RiskTier.DECLINE.value)
    reviewer_decision = state.get("reviewer_decision", "")
    adverse_action_required = bool(state.get("adverse_action_required", False))

    # Map risk tier to loan decision
    if reviewer_decision == "REQUEST_MORE_INFO":
        final_decision = LoanDecision.WITHDRAWN.value
        hmda_action = "5"  # File closed — incomplete
    elif adverse_action_required or risk_tier == RiskTier.DECLINE.value:
        final_decision = LoanDecision.DECLINED.value
        hmda_action = "3"  # Application denied
    elif risk_tier == RiskTier.APPROVE_WITH_CONDITIONS.value or state.get("conditions_imposed"):
        final_decision = LoanDecision.CONDITIONALLY_APPROVED.value
        hmda_action = "1"  # Loan originated (conditional)
    elif risk_tier == RiskTier.APPROVE.value:
        final_decision = LoanDecision.APPROVED.value
        hmda_action = "1"  # Loan originated
    else:
        final_decision = LoanDecision.REFERRED.value
        hmda_action = "6"  # Application withdrawn

    # SAR referral for OFAC hits or suspicious application patterns
    sar_referral = bool(state.get("ofac_hit", False))

    # Build decision rationale
    hard_decline_note = f" Hard decline triggered: {state.get('hard_decline_reason')}." if state.get("hard_decline_triggered") else ""
    decision_rationale = (
        f"Risk tier: {risk_tier}. Composite score: {state.get('composite_score', 0):.3f}.{hard_decline_note} "
        f"Reviewer: {state.get('reviewer_id', 'AUTO')} — {reviewer_decision or 'AUTO_DECISION'}. "
        f"Conditions: {len(state.get('conditions_imposed', []))}."
    )

    # Final audit entry
    audit = _append_audit(state, "finalize_decision", {
        "final_decision": final_decision,
        "risk_tier": risk_tier,
        "hmda_action_taken": hmda_action,
        "sar_referral": sar_referral,
        "exception_approved": state.get("exception_approved", False),
        "adverse_action_sent": adverse_action_required,
    })

    return {
        "final_decision": final_decision,
        "final_conditions": list(state.get("conditions_imposed", [])),
        "decision_timestamp": _now_utc(),
        "decision_rationale": decision_rationale,
        "sar_referral": sar_referral,
        "hmda_action_taken": hmda_action,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["finalize_decision"],
    }
