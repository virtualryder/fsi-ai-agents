"""
Agent 12 — Collections & Recovery Agent
State definition, constants, and regulatory data structures.

Security architecture:
- Consumer PII (account numbers, SSNs) masked at intake — never stored in LangGraph state
  in raw form. Account numbers stored as ACCT-****{last4}; SSNs as SSN-***-**-{last4}.
- All HITL conditions and FDCPA hard rules are Python frozensets — immutable at runtime.
  Any attempt to .add() to these sets raises TypeError. This is tested in test_nodes.py.
- Settlement computations are Python arithmetic — the LLM does not determine discount rates,
  payment plan terms, or credit reporting outcomes.

FDCPA compliance is deterministic Python throughout this agent. The LLM drafts written
communications (collection letters, payment agreements, settlement offers) but does not
determine: call time legality, cease-and-desist status, validation notice requirements,
SCRA applicability, bankruptcy stay status, or collectability scores.
"""

from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# FDCPA Hard Rules — Python frozensets, immutable at module load time
# ---------------------------------------------------------------------------

# FDCPA § 805(a)(1) — 15 U.S.C. § 1692c(a)(1)
# Collectors may not contact consumers before 8am or after 9pm LOCAL TIME.
# These hours are the prohibited contact hours in 24h format (0-23).
# Enforcement is Python comparison: contact_hour_local < 8 or contact_hour_local >= 21
FDCPA_PROHIBITED_HOURS_BEFORE = 8   # Before 8:00am local
FDCPA_PROHIBITED_HOURS_AFTER  = 21  # At or after 9:00pm local (21:00 = 9:00pm)

# FDCPA § 805(b) — 15 U.S.C. § 1692c(b)
# Collectors may not communicate with third parties except in specified circumstances.
# These are the ONLY permitted third-party contact purposes.
PERMITTED_THIRD_PARTY_PURPOSES = frozenset({
    "LOCATE_CONSUMER",      # Permitted once to find consumer's address/phone
    "ATTORNEY_OF_RECORD",   # Consumer's attorney — all communications go through attorney
    "CREDIT_REPORTING",     # Credit bureaus — separate reporting rules apply
    "LEGAL_PROCESS",        # Courts, enforcement process servers
})

# FDCPA § 807 — 15 U.S.C. § 1692e
# These representations are absolutely prohibited — no exception, no context.
# Any communication containing these elements is an FDCPA violation.
FDCPA_PROHIBITED_REPRESENTATIONS = frozenset({
    "FALSE_AFFILIATION_GOVERNMENT",     # Implying government affiliation
    "FALSE_AFFILIATION_ATTORNEY",       # Misrepresenting attorney status (if not an attorney)
    "THREAT_ARREST",                    # Threatening arrest for debt
    "THREAT_CRIMINAL_ACTION",           # Threatening criminal prosecution for civil debt
    "THREAT_LEGAL_ACTION_NOT_INTENDED", # Threatening lawsuit with no intention to sue
    "FALSE_DEBT_AMOUNT",                # Misrepresenting the amount owed
    "FALSE_CHARACTER_OF_DEBT",          # Misrepresenting legal status of the debt
    "OBSCENE_LANGUAGE",                 # Using profane or obscene language
    "PUBLISH_DEBTOR_LIST",              # Publishing "shame" list of debtors
    "DECEPTIVE_COMMUNICATION_FORM",     # Using documents that look like court orders
})

# CFPB Regulation F (12 CFR Part 1006) — 7-in-7 rule
# No more than 7 telephone calls within 7 consecutive days to a consumer.
# No telephone call within 7 days after a telephone conversation with the consumer.
REGULATION_F_CALL_LIMIT_7_DAYS = 7
REGULATION_F_POST_CONVERSATION_WAIT_DAYS = 7

# SCRA — Servicemembers Civil Relief Act (50 U.S.C. § 3937)
# Maximum interest rate for active military is 6% per year on pre-service debt.
# All collection activity involving active military requires HITL.
SCRA_MAX_INTEREST_RATE_PCT = 6.0

# Bankruptcy automatic stay — 11 U.S.C. § 362
# Filing bankruptcy triggers automatic stay — ALL collection activity must IMMEDIATELY stop.
# Only permitted exception: certain secured creditor rights under § 362(d).
BANKRUPTCY_STAY_EXCEPTIONS = frozenset({
    "CRIMINAL_PROSECUTION",         # Criminal proceeding against debtor
    "FAMILY_SUPPORT_ENFORCEMENT",   # Alimony, child support enforcement
    "REGULATORY_ENFORCEMENT",       # Government regulatory enforcement action
    "SECURED_CREDITOR_RELIEF",      # Post-§362(d) motion approved by court
})

# ---------------------------------------------------------------------------
# ALWAYS_HITL_CONDITIONS — Immutable frozenset
# All 9 conditions ALWAYS route to human review regardless of other state.
# Tested in test_nodes.py: TypeError on .add() is a security property test.
# ---------------------------------------------------------------------------

ALWAYS_HITL_CONDITIONS = frozenset({
    "SCRA_DETECTED",               # Active military — SCRA rate cap, special procedures
    "BANKRUPTCY_STAY_DETECTED",    # Automatic stay — ALL collection must stop immediately
    "DISPUTE_RECEIVED",            # Consumer disputed debt — validation notice + 30-day hold
    "CEASE_DESIST_RECEIVED",       # C&D letter received — only legal action notice permitted
    "DECEASED_ACCOUNT",            # Deceased debtor — estate/executor procedures required
    "SETTLEMENT_HIGH_VALUE",       # Settlement value > $10K or discount > 40%
    "LITIGATION_HIGH_RISK",        # Legal review required before any further action
    "REGULATORY_COMPLAINT",        # CFPB complaint / state AG complaint received
    "MINOR_ACCOUNT",               # Debtor < 18 — legal guardian required, state law varies
})

# ---------------------------------------------------------------------------
# Debt type classifications — affects SOL, FDCPA applicability, credit reporting
# ---------------------------------------------------------------------------

# FDCPA § 803(5) — 15 U.S.C. § 1692a(5)
# FDCPA applies to "consumer debts" — personal, family, or household purposes.
# Business debts are NOT covered by FDCPA.
CONSUMER_DEBT_TYPES = frozenset({
    "CREDIT_CARD",
    "PERSONAL_LOAN",
    "MEDICAL_DEBT",
    "AUTO_LOAN_DEFICIENCY",
    "MORTGAGE_DEFICIENCY",
    "PRIVATE_STUDENT_LOAN",
    "UTILITY_DEBT",
    "RENT_DEFICIENCY",
    "RETAIL_INSTALLMENT",
    "PAYDAY_LOAN",
})

BUSINESS_DEBT_TYPES = frozenset({
    "COMMERCIAL_LOAN",
    "BUSINESS_CREDIT_CARD",
    "TRADE_PAYABLE",
    "SBA_LOAN_DEFICIENCY",
    "EQUIPMENT_LEASE",
})

# Federal student loans are NOT subject to FDCPA (government debt exemption).
# However, private student loan servicers ARE covered.
FEDERAL_STUDENT_LOAN_PROGRAMS = frozenset({
    "DIRECT_LOAN",
    "PERKINS",
    "FFEL",
    "GRAD_PLUS",
    "PARENT_PLUS",
})

# ---------------------------------------------------------------------------
# State Statute of Limitations matrix
# Key: (state_code, debt_category) → years
# Debt categories: "written_contract", "open_account", "oral_contract", "judgment"
# Source: State consumer protection statutes as of 2024.
# NOTE: SOL does not eliminate the debt — it limits the right to sue.
# Collecting on time-barred debt (if consumer pays voluntarily) is permissible.
# Threatening to sue on time-barred debt is an FDCPA violation.
# ---------------------------------------------------------------------------

STATE_SOL_YEARS: Dict[str, Dict[str, int]] = {
    "AL": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "AK": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 10},
    "AZ": {"written_contract": 6, "open_account": 6, "oral_contract": 3, "judgment": 5},
    "AR": {"written_contract": 5, "open_account": 3, "oral_contract": 3, "judgment": 10},
    "CA": {"written_contract": 4, "open_account": 4, "oral_contract": 2, "judgment": 10},
    "CO": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 6},
    "CT": {"written_contract": 6, "open_account": 6, "oral_contract": 3, "judgment": 25},
    "DE": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 5},
    "FL": {"written_contract": 5, "open_account": 5, "oral_contract": 4, "judgment": 20},
    "GA": {"written_contract": 6, "open_account": 6, "oral_contract": 4, "judgment": 7},
    "HI": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 10},
    "ID": {"written_contract": 5, "open_account": 5, "oral_contract": 4, "judgment": 6},
    "IL": {"written_contract": 10, "open_account": 5, "oral_contract": 5, "judgment": 20},
    "IN": {"written_contract": 10, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "IA": {"written_contract": 10, "open_account": 5, "oral_contract": 5, "judgment": 20},
    "KS": {"written_contract": 5, "open_account": 5, "oral_contract": 3, "judgment": 5},
    "KY": {"written_contract": 10, "open_account": 5, "oral_contract": 5, "judgment": 15},
    "LA": {"written_contract": 10, "open_account": 3, "oral_contract": 3, "judgment": 10},
    "ME": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "MD": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 12},
    "MA": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "MI": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 10},
    "MN": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 10},
    "MS": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 7},
    "MO": {"written_contract": 10, "open_account": 5, "oral_contract": 5, "judgment": 10},
    "MT": {"written_contract": 8, "open_account": 5, "oral_contract": 5, "judgment": 10},
    "NE": {"written_contract": 5, "open_account": 5, "oral_contract": 4, "judgment": 5},
    "NV": {"written_contract": 6, "open_account": 6, "oral_contract": 4, "judgment": 6},
    "NH": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 20},
    "NJ": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "NM": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 14},
    "NY": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "NC": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 10},
    "ND": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 10},
    "OH": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 21},
    "OK": {"written_contract": 5, "open_account": 3, "oral_contract": 3, "judgment": 5},
    "OR": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 10},
    "PA": {"written_contract": 4, "open_account": 4, "oral_contract": 4, "judgment": 20},
    "RI": {"written_contract": 10, "open_account": 10, "oral_contract": 10, "judgment": 20},
    "SC": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 10},
    "SD": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "TN": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 10},
    "TX": {"written_contract": 4, "open_account": 4, "oral_contract": 4, "judgment": 10},
    "UT": {"written_contract": 6, "open_account": 6, "oral_contract": 4, "judgment": 8},
    "VT": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 8},
    "VA": {"written_contract": 5, "open_account": 5, "oral_contract": 3, "judgment": 20},
    "WA": {"written_contract": 6, "open_account": 6, "oral_contract": 3, "judgment": 10},
    "WV": {"written_contract": 10, "open_account": 10, "oral_contract": 5, "judgment": 10},
    "WI": {"written_contract": 6, "open_account": 6, "oral_contract": 6, "judgment": 20},
    "WY": {"written_contract": 8, "open_account": 8, "oral_contract": 8, "judgment": 5},
    "DC": {"written_contract": 3, "open_account": 3, "oral_contract": 3, "judgment": 12},
}

# ---------------------------------------------------------------------------
# Payment plan configuration — Python constants, not LLM configurable
# ---------------------------------------------------------------------------

# Collectability scoring weights (SR 11-7 model documentation)
COLLECTABILITY_WEIGHTS = {
    "debt_age_factor":     0.25,  # Newer debt = higher collectability
    "balance_factor":      0.20,  # Smaller balances = higher payment probability
    "contact_success":     0.20,  # Ability to reach consumer
    "payment_history":     0.20,  # Historical payment pattern
    "hardship_score":      0.15,  # Income/employment stability indicators
}

# Settlement discount tiers — approved by credit loss policy
# Python constants — LLM cannot override these boundaries
SETTLEMENT_TIERS = {
    "TIER_1": {"max_discount_pct": 20.0, "min_balance": 0,     "auth_level": "COLLECTOR"},
    "TIER_2": {"max_discount_pct": 35.0, "min_balance": 1000,  "auth_level": "SUPERVISOR"},
    "TIER_3": {"max_discount_pct": 50.0, "min_balance": 5000,  "auth_level": "MANAGER"},
    "TIER_4": {"max_discount_pct": 70.0, "min_balance": 10000, "auth_level": "VP_COLLECTIONS"},
}

# Minimum payment computation parameters
MIN_PAYMENT_PCT_OF_BALANCE = 0.015    # 1.5% of balance per month minimum
MAX_PAYMENT_TERM_MONTHS    = 60       # 5-year maximum plan
HARDSHIP_PLAN_MIN_PAYMENT  = 25.0     # $25/month minimum for hardship plans

# Credit reporting thresholds (FCRA — 15 U.S.C. § 1681)
CREDIT_REPORTING_THRESHOLDS = {
    "min_balance_report": 100.0,          # Minimum balance to report to bureaus
    "charge_off_days_delinquent": 180,    # Standard charge-off at 180 days (OCC guidance)
    "medical_debt_min_balance": 500.0,    # CFPB Reg F: medical debt <$500 not reportable (2025)
    "paid_in_full_remove_days": 7,        # Remove negative tradeline within 7 days of PIF
    "settled_report_years": 7,            # Settled accounts report for 7 years
}

# Validation notice requirements — FDCPA § 809 / CFPB Reg F 12 CFR 1006.34
VALIDATION_NOTICE_REQUIRED_DAYS = 5     # Must provide within 5 days of initial communication
DISPUTE_HOLD_DAYS = 30                  # All collection activity paused during dispute period
CONSUMER_RESPONSE_WINDOW_DAYS = 30     # Consumer has 30 days to dispute from receipt

# ---------------------------------------------------------------------------
# CollectionsState — LangGraph TypedDict
# total=False: all keys optional; node only writes what it computes.
# ---------------------------------------------------------------------------

class CollectionsState(TypedDict, total=False):
    # Debt identification (masked — raw account numbers never in state)
    account_id: str           # ACCT-****{last4} masked format
    original_account_number: str  # Internal reference only — not logged
    debt_type: str            # From CONSUMER_DEBT_TYPES or BUSINESS_DEBT_TYPES
    original_creditor: str    # Name of original creditor
    current_balance: float    # Current balance including interest/fees
    original_balance: float   # Balance at charge-off / account opening
    interest_accrued: float   # Interest since itemization date
    fees_accrued: float       # Collection fees, late fees
    itemization_date: str     # CFPB Reg F: balance itemized as of this date

    # Consumer information (PII masked)
    consumer_id: str          # Internal consumer identifier (masked)
    consumer_name_masked: str # First name + last initial only
    consumer_state: str       # 2-letter state code (affects SOL, state laws)
    consumer_timezone: str    # IANA timezone string (FDCPA time enforcement)
    consumer_is_deceased: bool
    consumer_is_minor: bool   # Under 18

    # FDCPA / compliance flags (Python-computed, never LLM)
    fdcpa_applies: bool               # False for business debts
    contact_permitted_now: bool       # Time-of-day check result (Python)
    contact_hour_local: int           # Current hour in consumer's local timezone
    validation_notice_sent: bool      # Has FDCPA § 809 notice been provided?
    validation_notice_date: str       # Date sent
    dispute_received: bool            # Consumer disputed the debt
    dispute_date: str                 # Date dispute received
    cease_desist_received: bool       # Consumer sent C&D letter
    cease_desist_date: str            # Date C&D received
    prior_contacts_7_days: int        # Reg F 7-in-7: calls in last 7 days
    days_since_last_conversation: int # Reg F: days since last actual phone conversation

    # Protective flags (SCRA, bankruptcy)
    scra_check_performed: bool        # Whether SCRA lookup was run
    scra_active_military: bool        # Active duty confirmed
    scra_branch: str                  # Military branch (if SCRA applies)
    bankruptcy_check_performed: bool
    bankruptcy_stay_active: bool      # Automatic stay in effect
    bankruptcy_chapter: str           # Chapter 7, 13, 11, etc.
    bankruptcy_case_number: str

    # Statute of limitations
    debt_date_of_last_payment: str    # Restarts SOL clock
    debt_origination_date: str        # Original account open date
    sol_years: int                    # Applicable SOL from STATE_SOL_YEARS
    sol_expiration_date: str          # Computed expiration
    sol_expired: bool                 # True if SOL has run
    sol_warning: bool                 # Within 90 days of SOL expiration

    # Collectability scoring (Python — SR 11-7 documented)
    collectability_score: float       # 0.0-1.0
    collectability_tier: str          # HIGH (≥0.70), MEDIUM (0.40-0.69), LOW (<0.40)
    debt_age_factor: float            # Sub-score: age of debt
    contact_success_factor: float     # Sub-score: contact history
    payment_history_factor: float     # Sub-score: prior payment behavior
    hardship_score: float             # Sub-score: income/employment hardship indicators

    # Payment plan options (Python-computed)
    payment_plan_options: List[Dict[str, Any]]  # List of plan dicts with term/payment/total
    recommended_plan_index: int                  # Index into payment_plan_options
    min_monthly_payment: float                   # Python computed: balance × 0.015
    hardship_plan_eligible: bool                 # $25/month minimum hardship plan

    # Settlement analysis (Python-computed; LLM provides narrative only)
    settlement_eligible: bool         # Whether settlement is appropriate for this account
    settlement_tiers: List[Dict[str, Any]]  # List of tier dicts
    recommended_settlement_tier: str  # TIER_1 through TIER_4
    settlement_amount: float          # Dollar amount of settlement offer (Python math)
    settlement_discount_pct: float    # Discount percentage (Python math)
    settlement_auth_level: str        # Required authorization level
    settlement_high_value: bool       # Above threshold — triggers HITL

    # Credit reporting determination (Python — FCRA)
    credit_reporting_appropriate: bool   # Whether to report to bureaus
    credit_reporting_action: str         # REPORT_NEW / UPDATE_EXISTING / DELETE / NONE
    days_delinquent: int                 # Total days past due
    medical_debt_flag: bool             # Medical debt special rules under CFPB

    # HITL conditions
    hitl_required: bool
    hitl_conditions: List[str]       # Subset of ALWAYS_HITL_CONDITIONS
    escalation_level: str            # COLLECTOR / SUPERVISOR / MANAGER / LEGAL / COMPLIANCE

    # Regulatory compliance assessment (LLM narrative + Python flags)
    fdcpa_compliance_issues: List[str]   # Python-detected compliance issues
    regulation_f_violations: List[str]   # Python-detected Reg F issues
    regulatory_risk_score: float         # Python: 0.0-1.0
    regulatory_risk_tier: str            # LOW / MEDIUM / HIGH / CRITICAL

    # LLM-produced narratives (not compliance determinations)
    hardship_assessment_narrative: str   # LLM interpretation of hardship signals
    collections_strategy_narrative: str  # LLM: recommended approach narrative
    collection_letter_draft: str         # LLM: FDCPA-compliant letter draft
    settlement_offer_letter_draft: str   # LLM: settlement offer letter
    payment_agreement_draft: str         # LLM: payment plan agreement language

    # Human review gate (HITL)
    reviewer_id: str
    reviewer_decision: str        # APPROVE_PLAN / APPROVE_SETTLEMENT / ESCALATE / CEASE_COLLECTION / REFER_LEGAL
    reviewer_conditions: str      # Any conditions attached to the decision
    reviewer_notes: str
    reviewer_timestamp: str

    # Final outcome
    collections_outcome: str      # PAYMENT_PLAN / SETTLEMENT / CEASE_AND_DESIST / LEGAL_REFERRAL / HARDSHIP_PLAN / CLOSED_DISPUTE
    credit_reporting_filed: bool

    # Audit trail (append-only — list(current) + [new_entry] pattern)
    audit_trail: List[Dict[str, Any]]
    case_id: str
    case_timestamp: str
    audit_retention: str          # "7_YEARS_S3_OBJECT_LOCK_GOVERNANCE"
