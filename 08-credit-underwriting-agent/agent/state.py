# agent/state.py
# ============================================================
# Credit Underwriting Agent — State Definitions
#
# CreditUnderwritingState: TypedDict (total=False) so all
# fields are optional at initialization. Each node populates
# its section of state as the workflow progresses.
#
# Security notes:
#   - SSN and full credit report are never stored in state;
#     only derived metrics (FICO score, DTI) pass through.
#   - All PII fields are masked in the Streamlit UI layer.
#   - OFAC match and fair lending flags are Python-only
#     hard overrides — no LLM path can bypass them.
# ============================================================
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


# ── Enumerations ──────────────────────────────────────────────────────────────

class LoanType(str, Enum):
    CONVENTIONAL_MORTGAGE = "CONVENTIONAL_MORTGAGE"
    FHA_MORTGAGE = "FHA_MORTGAGE"
    VA_MORTGAGE = "VA_MORTGAGE"
    JUMBO_MORTGAGE = "JUMBO_MORTGAGE"
    HELOC = "HELOC"
    COMMERCIAL_REAL_ESTATE = "COMMERCIAL_REAL_ESTATE"
    COMMERCIAL_TERM_LOAN = "COMMERCIAL_TERM_LOAN"
    SBA_7A = "SBA_7A"
    SBA_504 = "SBA_504"
    CONSUMER_PERSONAL = "CONSUMER_PERSONAL"
    AUTO = "AUTO"
    CREDIT_CARD_LINE = "CREDIT_CARD_LINE"


class RiskTier(str, Enum):
    """
    Credit decision tier — set by Python scoring logic only.
    No LLM may set or override this field.
    Documented per SR 11-7 Model Risk Management guidance.
    """
    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITIONS = "APPROVE_WITH_CONDITIONS"
    REFER_TO_COMMITTEE = "REFER_TO_COMMITTEE"
    DECLINE = "DECLINE"


class LoanDecision(str, Enum):
    APPROVED = "APPROVED"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    REFERRED = "REFERRED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"


class CollateralType(str, Enum):
    PRIMARY_RESIDENCE = "PRIMARY_RESIDENCE"
    INVESTMENT_PROPERTY = "INVESTMENT_PROPERTY"
    COMMERCIAL_REAL_ESTATE = "COMMERCIAL_REAL_ESTATE"
    EQUIPMENT = "EQUIPMENT"
    INVENTORY = "INVENTORY"
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    SBA_GUARANTEE = "SBA_GUARANTEE"
    VEHICLE = "VEHICLE"
    UNSECURED = "UNSECURED"


class ApplicationStatus(str, Enum):
    RECEIVED = "RECEIVED"
    IN_UNDERWRITING = "IN_UNDERWRITING"
    PENDING_DOCUMENTS = "PENDING_DOCUMENTS"
    PENDING_COMMITTEE = "PENDING_COMMITTEE"
    DECISION_RENDERED = "DECISION_RENDERED"
    ADVERSE_ACTION_SENT = "ADVERSE_ACTION_SENT"
    CLOSED = "CLOSED"


class AdverseActionReason(str, Enum):
    """
    Reg B (12 CFR Part 1002) standard adverse action reasons.
    Must cite specific reasons — vague denials violate ECOA.
    """
    INSUFFICIENT_INCOME = "Insufficient income"
    EXCESSIVE_OBLIGATIONS = "Excessive obligations in relation to income"
    UNABLE_TO_VERIFY_INCOME = "Unable to verify income"
    TEMPORARY_EMPLOYMENT = "Temporary or irregular employment"
    LENGTH_OF_EMPLOYMENT = "Length of employment"
    INSUFFICIENT_CREDIT_EXPERIENCE = "Insufficient credit experience"
    NO_CREDIT_FILE = "No credit file"
    POOR_CREDIT_PERFORMANCE = "Poor credit performance — delinquent obligations"
    COLLECTION_ACTION_JUDGMENT = "Collection action or judgment"
    BANKRUPTCY = "Bankruptcy"
    FORECLOSURE_REPOSSESSION = "Foreclosure or repossession"
    INADEQUATE_COLLATERAL = "Inadequate collateral"
    VALUE_TYPE_COLLATERAL = "Value or type of collateral not sufficient"
    DEROGATORY_PUBLIC_RECORD = "Derogatory public record or information"
    DTI_TOO_HIGH = "Total obligations in relation to income"
    CREDIT_SCORE_TOO_LOW = "Credit score below minimum threshold"
    OFAC_MATCH = "Unable to process — regulatory restriction"
    INCOMPLETE_APPLICATION = "Credit application incomplete"
    UNABLE_TO_VERIFY_RESIDENCE = "Unable to verify residence"
    RECENT_DELINQUENCY = "Number and severity of delinquencies"


# ── State TypedDict ────────────────────────────────────────────────────────────

class CreditUnderwritingState(TypedDict, total=False):
    """
    Complete state for the credit underwriting workflow.
    total=False: every field is Optional at initialization.
    Nodes populate only the fields they own.

    Security design:
    - No raw SSN, full credit report, or account numbers in state.
    - Credit bureau data reduced to derived metrics only.
    - OFAC and fair lending flags enforced exclusively in Python.
    - Audit trail is append-only; entries are never modified.
    """

    # ── Application Identification ─────────────────────────────────────────
    application_id: str
    loan_type: str                           # LoanType enum value
    loan_purpose: str                        # PURCHASE | REFINANCE | CASH_OUT | WORKING_CAPITAL | EQUIPMENT
    request_date: str                        # ISO-8601 date
    application_source: str                  # BRANCH | ONLINE | BROKER | CALL_CENTER

    # ── Applicant Information ──────────────────────────────────────────────
    # Note: SSN is never stored in state — only masked reference ID
    applicant_id: str                        # Internal reference (not SSN)
    applicant_name: str                      # For display; masked in UI audit trail
    applicant_type: str                      # INDIVIDUAL | BUSINESS | TRUST
    co_applicant_id: Optional[str]
    co_applicant_name: Optional[str]
    business_name: Optional[str]             # For commercial applications
    years_in_business: Optional[float]       # Commercial underwriting
    industry_code: Optional[str]             # NAICS code for commercial
    existing_relationship: bool              # Existing customer at institution
    existing_deposit_balance: Optional[float]

    # ── Loan Parameters ────────────────────────────────────────────────────
    requested_amount: float
    requested_term: int                      # Months
    quoted_rate: float                       # Annual interest rate (decimal)
    collateral_type: str                     # CollateralType enum value
    appraised_value: Optional[float]         # For secured loans
    collateral_description: Optional[str]
    property_address: Optional[str]          # Residential/CRE only (masked in audit)
    property_state: Optional[str]            # State code — used for geographic fair lending
    property_county: Optional[str]           # MSA/county for HMDA reporting
    property_census_tract: Optional[str]     # For CRA and fair lending geographic analysis

    # ── Document Verification ──────────────────────────────────────────────
    documents_received: List[str]            # List of received document types
    documents_verified: bool
    missing_documents: List[str]
    document_exceptions: List[str]           # Documents present but with deficiencies
    identity_verified: bool                  # BSA/AML CIP requirement
    cip_method: str                          # DOCUMENTARY | NON_DOCUMENTARY

    # ── Credit Bureau (derived metrics only — no raw report in state) ──────
    credit_score: int                        # FICO score
    credit_score_model: str                  # FICO_8 | FICO_9 | VANTAGE_4
    credit_report_date: str
    derogatory_marks: int                    # Count of derogatory entries
    bankruptcy_flag: bool
    bankruptcy_chapter: Optional[str]        # CHAPTER_7 | CHAPTER_13 | CHAPTER_11
    bankruptcy_discharge_years: Optional[float]  # Years since discharge
    foreclosure_flag: bool
    collections_count: int
    collections_balance: float               # Total collections balance
    thin_file_flag: bool                     # < 3 tradelines
    recent_inquiries_90d: int                # Hard inquiries last 90 days
    ofac_hit: bool                           # OFAC match — Python hard block; never LLM-waivable
    ofac_hit_details: Optional[str]          # Sanitized (no PII in detail field)

    # ── Financial Analysis (all Python-calculated) ─────────────────────────
    annual_income: float                     # Gross annual income (verified)
    income_source: str                       # W2 | SELF_EMPLOYED | RENTAL | BUSINESS | MIXED
    monthly_income: float                    # Derived: annual_income / 12
    monthly_debt_obligations: float          # Existing monthly debt payments
    proposed_monthly_payment: float          # Calculated from amount/rate/term
    front_end_dti: float                     # Housing-only DTI (mortgage)
    total_dti_ratio: float                   # All debt including proposed payment
    ltv_ratio: float                         # Loan-to-value
    cltv_ratio: Optional[float]              # Combined LTV (if subordinate liens)
    net_operating_income: Optional[float]    # Annual NOI for commercial
    annual_debt_service: Optional[float]     # Annual P&I for commercial
    dscr: Optional[float]                    # NOI / annual debt service
    liquid_assets: Optional[float]           # Verified liquid reserves
    reserves_months: Optional[float]         # Months of PITI in reserves (mortgage)
    cash_flow_adequate: bool                 # Python determination — adequate residual income

    # ── Fair Lending Analysis (Python-only — ECOA / FHA / Reg B) ──────────
    # These flags CANNOT be cleared by LLM reasoning or manual override
    # Any fair_lending_flag → mandatory HITL (Python-enforced)
    fair_lending_flags: List[str]            # Specific flags triggered
    geographic_flag: bool                    # Redlining / geographic concentration flag
    steering_flag: bool                      # Product steering concern
    pricing_exception_flag: bool             # Rate/fee outside policy without justification
    cra_eligible: bool                       # CRA-qualified loan / geography
    hmda_reportable: bool                    # HMDA LAR filing required
    hmda_action_taken: Optional[str]         # HMDA action taken code (1-8)
    fair_lending_review_required: bool       # Triggers mandatory HITL gate

    # ── Risk Scoring (Python-only per SR 11-7) ────────────────────────────
    # Weights: Credit Score 30%, DTI 25%, LTV 20%, Cash Flow 15%, Collateral 10%
    credit_score_factor: float              # 0.0–1.0
    dti_factor: float                       # 0.0–1.0
    ltv_factor: float                       # 0.0–1.0
    cash_flow_factor: float                 # 0.0–1.0
    collateral_factor: float                # 0.0–1.0
    composite_score: float                  # Weighted 0.0–1.0
    risk_tier: str                          # RiskTier enum value — Python-set only
    hard_decline_triggered: bool            # Hard rule override active
    hard_decline_reason: Optional[str]      # Specific hard rule violated
    score_breakdown: Dict[str, Any]         # Factor-by-factor documentation for SR 11-7

    # ── Routing ────────────────────────────────────────────────────────────
    human_review_required: bool
    committee_required: bool                # Credit committee vs. single underwriter
    assigned_underwriter: str
    assigned_officer: Optional[str]         # Loan officer (if committee track)
    routing_rationale: str
    escalation_path: str                    # UNDERWRITER | CREDIT_COMMITTEE | CCO | BSA_OFFICER

    # ── Human Review Gate ──────────────────────────────────────────────────
    reviewer_id: str
    reviewer_decision: str                  # APPROVE | APPROVE_WITH_CONDITIONS | DECLINE | REQUEST_MORE_INFO
    reviewer_notes: str
    conditions_imposed: List[str]           # Conditions attached to conditional approval
    pricing_override: Optional[float]       # Rate override applied by reviewer (logged)
    review_timestamp: str

    # ── Credit Memo ────────────────────────────────────────────────────────
    credit_memo_draft: str                  # LLM-generated credit memo narrative
    loan_structure_recommendation: str      # LLM-drafted structure summary
    exceptions_narrative: Optional[str]     # LLM narrative on any policy exceptions

    # ── Adverse Action (Reg B / ECOA) ─────────────────────────────────────
    adverse_action_required: bool
    adverse_action_reasons: List[str]       # AdverseActionReason enum values (max 4 per Reg B)
    adverse_action_notice_draft: str        # LLM-drafted Reg B notice
    credit_score_disclosure_required: bool  # If score used in decision (FCRA § 615)
    adverse_action_deadline: str            # 30-day notice deadline (ISO-8601)

    # ── Final Decision ────────────────────────────────────────────────────
    final_decision: str                     # LoanDecision enum value
    final_conditions: List[str]
    decision_timestamp: str
    decision_rationale: str
    sar_referral: bool                      # Refer to BSA (OFAC / suspicious application)
    exception_approved: bool                # Policy exception granted (must be documented)
    exception_authority: Optional[str]      # Who approved the exception

    # ── Audit Trail ───────────────────────────────────────────────────────
    audit_trail: List[Dict[str, Any]]       # Append-only; entries never modified
    completed_steps: List[str]
    processing_time_seconds: float
    errors: List[str]
