# agent/state.py
# ============================================================
# Payments Compliance Agent — State Definitions
#
# PURPOSE
# -------
# Defines the complete state schema for the payments compliance
# workflow. This agent handles the full lifecycle of payment
# compliance events: ACH transactions, wire transfers, card
# disputes, RTP/FedNow payments, and prepaid card transactions.
#
# REGULATORY SCOPE
# ----------------
# - Regulation E (12 CFR Part 1005): Electronic fund transfer
#   consumer protections — error resolution, unauthorized
#   transaction claims, provisional credit timelines.
# - Nacha Operating Rules: ACH network rules — return code
#   processing, SEC code validation, ODFI/RDFI obligations,
#   late return rules (R07 after 60 days).
# - CFPB Oversight: UDAAP enforcement, Prepaid Rule (12 CFR
#   Part 1005 Subpart E), EFTA implementation.
# - OFAC/Sanctions: All payments screened against SDN list and
#   high-risk jurisdiction BIC/ABA codes.
# - UCC Article 4A: Wire transfer liability and error correction.
# - Reg J / Regulation CC: Federal Reserve wire transfer rules
#   and funds availability requirements.
# - SWIFT gpi: Cross-border payment tracking requirements.
#
# SECURITY DESIGN
# ---------------
# - Account numbers are stored as last-4 only in state.
#   Full account numbers are never written to the LangGraph
#   checkpoint database.
# - Payment amounts are stored as floats — no rounding or
#   truncation that could alter compliance thresholds.
# - OFAC and sanctions screening results are Python-determined.
#   The LLM never makes a sanctions determination.
# - All SLA deadlines are computed in UTC and stored as ISO-8601
#   strings — no timezone ambiguity.
# ============================================================
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


# ── Payment Type ──────────────────────────────────────────────────────────────

class PaymentType(str, Enum):
    """
    Supported payment rail types.
    Each type has different regulatory requirements, return windows,
    and dispute handling procedures.
    """
    # ACH — Automated Clearing House (Nacha rules)
    ACH_CREDIT     = "ACH_CREDIT"     # Payroll, vendor payments, tax refunds
    ACH_DEBIT      = "ACH_DEBIT"      # Bill pay, mortgage, consumer debits
    ACH_IAT        = "ACH_IAT"        # International ACH Transaction — enhanced OFAC screening

    # Wire Transfers (UCC Article 4A, Reg J)
    WIRE_DOMESTIC  = "WIRE_DOMESTIC"  # Fedwire Funds Service
    WIRE_INTERNATIONAL = "WIRE_INTERNATIONAL"  # SWIFT — cross-border

    # Card (Reg E for debit/prepaid; Reg Z for credit)
    CARD_DEBIT     = "CARD_DEBIT"     # PIN-based or signature debit card
    CARD_PREPAID   = "CARD_PREPAID"   # Prepaid card (CFPB Prepaid Rule)

    # Faster Payments
    RTP            = "RTP"            # The Clearing House RTP network
    FEDWIRE        = "FEDWIRE"        # Fedwire Funds (same-day settlement)
    FEDNOW         = "FEDNOW"         # FedNow instant payment service

    # Checks (Reg CC, Check 21)
    CHECK_PRESENTED = "CHECK_PRESENTED"   # Physical or image check presented
    CHECK_RETURNED  = "CHECK_RETURNED"    # Check return item

    UNKNOWN        = "UNKNOWN"


class SECCode(str, Enum):
    """
    Nacha Standard Entry Class (SEC) codes that define the authorization
    type and permissible use case for each ACH transaction.
    """
    PPD  = "PPD"   # Prearranged Payment and Deposit — consumer accounts
    CCD  = "CCD"   # Corporate Credit or Debit — business accounts
    CTX  = "CTX"   # Corporate Trade Exchange — includes EDI addenda
    WEB  = "WEB"   # Internet-initiated debit — requires annual audit
    TEL  = "TEL"   # Telephone-initiated debit — inbound call only
    POP  = "POP"   # Point-of-Purchase — check converted at POS
    ARC  = "ARC"   # Accounts Receivable Check — lockbox conversion
    BOC  = "BOC"   # Back Office Conversion — check converted in back office
    RCK  = "RCK"   # Re-presented Check — NSF re-presentment
    IAT  = "IAT"   # International ACH Transaction — cross-border
    CIE  = "CIE"   # Customer Initiated Entry — online bill pay
    MTE  = "MTE"   # Machine Transfer Entry — ATM transactions
    PBR  = "PBR"   # Consumer Cross-Border Payment
    CBR  = "CBR"   # Corporate Cross-Border Payment
    DNE  = "DNE"   # Death Notification Entry
    ENR  = "ENR"   # Automated Enrollment Entry
    TRX  = "TRX"   # Healthcare — electronic payment
    UNKNOWN = "UNKNOWN"


class NachaReturnCode(str, Enum):
    """
    Nacha ACH return and NOC codes. These are the RDFI's mechanism for
    returning ACH entries that cannot be posted. Return codes determine
    the ODFI's obligations, re-originiation rights, and dispute procedures.

    Critical compliance distinction:
    - R01–R06: Administrative returns (NSF, closed, invalid) — ODFI may re-originate
    - R07–R10: Unauthorized returns — 60-day window from settlement; may trigger SAR
    - R11: Check truncation errors
    - R29: Corporate unauthorized — separate from R07
    - R51–R82: Return detail codes for specific scenarios
    """
    # Most common return codes
    R01 = "R01"  # Insufficient Funds
    R02 = "R02"  # Account Closed
    R03 = "R03"  # No Account / Unable to Locate Account
    R04 = "R04"  # Invalid Account Number
    R05 = "R05"  # Unauthorized Debit to Consumer Account Using Corporate SEC Code
    R06 = "R06"  # Returned per ODFI Request
    R07 = "R07"  # Authorization Revoked by Customer — consumer STOP PAYMENT
    R08 = "R08"  # Payment Stopped
    R09 = "R09"  # Uncollected Funds
    R10 = "R10"  # Customer Advises Originator is Not Known / Not Authorized
    R11 = "R11"  # Check Truncation Early Return
    R12 = "R12"  # Branch Sold to Another DFI
    R13 = "R13"  # RDFI Not Qualified to Participate
    R14 = "R14"  # Representative Payee Deceased or Unable to Continue
    R15 = "R15"  # Beneficiary or Account Holder Deceased
    R16 = "R16"  # Account Frozen / Ofac Blocked
    R17 = "R17"  # File Record Edit Criteria
    R20 = "R20"  # Non-Transaction Account
    R21 = "R21"  # Invalid Company Identification
    R22 = "R22"  # Invalid Individual ID Number
    R23 = "R23"  # Credit Entry Refused by Receiver
    R24 = "R24"  # Duplicate Entry
    R26 = "R26"  # Mandatory Field Error
    R28 = "R28"  # Routing Number Check Digit Error
    R29 = "R29"  # Corporate Customer Advises Not Authorized
    R30 = "R30"  # RDFI Not Participant in Check Truncation Program
    R31 = "R31"  # Permissible Return Entry
    R33 = "R33"  # Return of XCK Entry
    R37 = "R37"  # Source Document Presented for Payment
    R38 = "R38"  # Stop Payment on Source Document
    R39 = "R39"  # Improper Source Document
    R40 = "R40"  # Return of ENR Entry by Federal Government Agency
    R50 = "R50"  # State Law Affecting RCK Acceptance
    R51 = "R51"  # Item is Ineligible, Notice Not Provided
    R52 = "R52"  # Stop Payment on Item
    R53 = "R53"  # Item and ACH Entry Presented for Payment
    R61 = "R61"  # Misrouted Return
    R67 = "R67"  # Duplicate Return
    R68 = "R68"  # Untimely Return
    R69 = "R69"  # Field Error(s)
    R70 = "R70"  # Permissible Return Entry Not Accepted
    R71 = "R71"  # Misrouted Dishonored Return
    R72 = "R72"  # Untimely Dishonored Return
    R73 = "R73"  # Timely Original Return
    R74 = "R74"  # Corrected Return
    R75 = "R75"  # Return Not a Duplicate
    R76 = "R76"  # No Errors Found
    R77 = "R77"  # Non-Acceptance of R62 Dishonored Return
    C01 = "C01"  # Incorrect DFI Account Number (NOC)
    C02 = "C02"  # Incorrect Routing Number (NOC)
    C03 = "C03"  # Incorrect Routing and Account Number (NOC)
    C04 = "C04"  # Incorrect Individual Name (NOC)
    C05 = "C05"  # Incorrect Transaction Code (NOC)
    C06 = "C06"  # Incorrect Account Number and Transaction Code (NOC)
    C07 = "C07"  # Incorrect Routing Number, Account Number, and Transaction Code (NOC)
    C09 = "C09"  # Incorrect Individual ID Number (NOC)
    NONE = "NONE"  # No return code — original transaction


class RegEDisputeType(str, Enum):
    """
    Regulation E dispute categories. Each type has different investigation
    timelines, provisional credit requirements, and documentation standards.

    Reg E applies to: consumer EFT transactions including ACH debits,
    debit card transactions, ATM withdrawals, and transfers initiated
    through electronic means. Does NOT apply to wire transfers, checks,
    or credit card transactions (Reg Z governs credit cards).
    """
    UNAUTHORIZED_TRANSACTION    = "UNAUTHORIZED_TRANSACTION"    # 10/45 day rule; provisional credit
    INCORRECT_AMOUNT            = "INCORRECT_AMOUNT"            # Wrong dollar amount processed
    DUPLICATE_TRANSACTION       = "DUPLICATE_TRANSACTION"       # Same transaction posted twice
    TRANSACTION_NOT_RECEIVED    = "TRANSACTION_NOT_RECEIVED"    # Credit not posted to account
    ERROR_IN_PERIODIC_STATEMENT = "ERROR_IN_PERIODIC_STATEMENT" # Statement error
    FAILURE_TO_STOP_PAYMENT     = "FAILURE_TO_STOP_PAYMENT"     # Stop payment not honored
    INCORRECT_ACCOUNT           = "INCORRECT_ACCOUNT"           # Posted to wrong account
    NOT_DISPUTE                 = "NOT_DISPUTE"                  # Not a Reg E dispute
    UNKNOWN                     = "UNKNOWN"


class ComplianceRiskTier(str, Enum):
    """
    Compliance risk tier — Python-computed from violation severity,
    payment amount, and regulatory exposure.
    """
    CRITICAL  = "CRITICAL"   # Sanctions hit, potential fraud, immediate HITL
    HIGH      = "HIGH"       # Unauthorized return, Reg E violation, SLA breach risk
    MEDIUM    = "MEDIUM"     # Administrative return, documentation gap
    LOW       = "LOW"        # Routine administrative issue, auto-resolve


class PaymentStatus(str, Enum):
    RECEIVED         = "RECEIVED"
    SCREENING        = "SCREENING"
    VALIDATING       = "VALIDATING"
    ASSESSING        = "ASSESSING"
    PENDING_REVIEW   = "PENDING_REVIEW"
    RESOLVED         = "RESOLVED"
    ESCALATED        = "ESCALATED"
    REJECTED         = "REJECTED"


class ResolutionType(str, Enum):
    """Possible resolution outcomes for a compliance event."""
    RETURN_ITEM            = "RETURN_ITEM"            # Return the ACH entry to ODFI
    PROVISIONAL_CREDIT     = "PROVISIONAL_CREDIT"     # Issue provisional credit (Reg E)
    FINAL_CREDIT           = "FINAL_CREDIT"           # Finalize credit after investigation
    DENY_CLAIM             = "DENY_CLAIM"             # Deny dispute with explanation
    ESCALATE_TO_LEGAL      = "ESCALATE_TO_LEGAL"      # Refer to legal/litigation
    ESCALATE_TO_BSA        = "ESCALATE_TO_BSA"        # File SAR consideration
    BLOCK_AND_FREEZE       = "BLOCK_AND_FREEZE"       # Block payment and freeze account
    FORWARD_AND_NOTIFY     = "FORWARD_AND_NOTIFY"     # Forward to correct account + notice
    NOC_UPDATE_REQUIRED    = "NOC_UPDATE_REQUIRED"    # Update originator's records per NOC
    RESUBMIT               = "RESUBMIT"               # Correct and resubmit
    NO_ACTION_REQUIRED     = "NO_ACTION_REQUIRED"     # Compliant, no action needed


class SLAType(str, Enum):
    """
    Regulation E SLA types. Each has a specific calendar/business-day
    deadline. Python computes the deadline from receipt_timestamp.
    """
    REG_E_PROVISIONAL_CREDIT    = "REG_E_PROVISIONAL_CREDIT"   # 10 business days
    REG_E_INVESTIGATION         = "REG_E_INVESTIGATION"         # 45 calendar days
    REG_E_NOTIFICATION          = "REG_E_NOTIFICATION"          # 3 business days (inform customer)
    REG_E_EXTENDED_INVESTIGATION = "REG_E_EXTENDED_INVESTIGATION" # 90 days (new accounts/foreign)
    NACHA_RETURN_WINDOW          = "NACHA_RETURN_WINDOW"         # 2 banking days (most returns)
    NACHA_UNAUTHORIZED_RETURN    = "NACHA_UNAUTHORIZED_RETURN"   # 60 calendar days (R07/R10/R29)
    NACHA_LATE_RETURN            = "NACHA_LATE_RETURN"           # After 60 days — only R07 allowed
    CTR_FILING                   = "CTR_FILING"                  # 15 calendar days
    SAR_FILING                   = "SAR_FILING"                  # 30 calendar days
    WIRE_CUTOFF                  = "WIRE_CUTOFF"                 # Same-day (Fedwire 6:00 PM ET)


# ── State TypedDict ────────────────────────────────────────────────────────────

class PaymentsComplianceState(TypedDict, total=False):
    """
    Complete state for the payments compliance workflow.
    total=False: every field is Optional at initialization.
    Each node populates only the fields it owns.

    Security design:
    - account_number fields store last-4 digits only — never full account numbers
    - routing_numbers are stored in full (not PII — public bank routing data)
    - OFAC and sanctions decisions are Python-only (LLM never determines sanctions status)
    - SLA deadlines are ISO-8601 UTC — no timezone ambiguity in compliance calculations
    - All monetary amounts are float — no string truncation that could affect thresholds
    """

    # ── Payment Identification ─────────────────────────────────────────────
    payment_event_id: str               # Canonical UUID for this compliance event
    payment_id: str                     # Mirrors payment_event_id (legacy callers)
    payment_hash: str                   # SHA-256 of original payment data
    original_transaction_id: str        # Bank/network transaction ID
    trace_number: str                   # ACH trace number or wire reference
    source_system: str                  # CORE_BANKING | NACHA_FILE | SWIFT | CARD_NETWORK | MANUAL
    received_timestamp: str             # ISO-8601 UTC — when event was received
    submission_timestamp: str           # ISO-8601 UTC — when submitted to this agent
    submitted_by: str                   # Submitting system or user ID

    # ── Payment Classification ──────────────────────────────────────────────
    payment_type: str                   # PaymentType enum value
    sec_code: str                       # SECCode enum value (ACH only)
    is_return: bool                     # True if this is a return/NOC item
    return_code: str                    # NachaReturnCode enum value
    is_dispute: bool                    # True if this is a customer dispute
    dispute_type: str                   # RegEDisputeType enum value

    # ── Payment Details ────────────────────────────────────────────────────
    amount: float                       # Transaction amount (float, USD)
    currency: str                       # ISO 4217 currency code
    settlement_date: str                # ISO date YYYY-MM-DD
    effective_date: str                 # ISO date YYYY-MM-DD (ACH effective entry date)
    value_date: str                     # ISO date YYYY-MM-DD (wire value date)

    # ── Originator / Sender ────────────────────────────────────────────────
    odfi_routing_number: str            # Originating DFI ABA routing number
    odfi_name: str                      # Originating DFI name
    originator_name: str                # Company / individual name
    originator_account_raw: str         # Raw account at intake ONLY — scrubbed to "" by payment_intake_node
    originator_account_last4: str       # Last 4 of originator account — SECURITY
    originator_country: str             # ISO 3166-1 alpha-2 — SCREENED by sanctions node
    originator_routing: str             # ABA routing (public bank data)
    originator_id: str                  # Nacha Company ID or SWIFT BIC

    # ── Receiver / Beneficiary ──────────────────────────────────────────────
    rdfi_routing_number: str            # Receiving DFI ABA routing number
    rdfi_name: str                      # Receiving DFI name
    receiver_name: str                  # Individual or company name
    receiver_account_raw: str           # Raw account at intake ONLY — scrubbed to "" by payment_intake_node
    receiver_account_last4: str         # Last 4 of receiver account — SECURITY
    receiver_country: str               # ISO 3166-1 alpha-2 — SCREENED by sanctions node
    receiver_routing: str               # ABA routing (public bank data)
    receiver_account_type: str          # CHECKING | SAVINGS | GENERAL_LEDGER | LOAN

    # ── Wire-Specific ──────────────────────────────────────────────────────
    swift_bic: str                      # Correspondent bank BIC (SWIFT wires)
    iban: str                           # Beneficiary IBAN (masked) — international wires
    correspondent_bank: str             # Correspondent bank name
    remittance_information: str         # Payment purpose / invoice reference

    # ── Sanctions Screening ────────────────────────────────────────────────
    # All screening results are Python-determined — LLM has no role here
    ofac_screening_performed: bool
    ofac_hit: bool                      # True if SDN/OFAC match found
    ofac_hit_details: str               # Matching SDN entry (masked for audit)
    screening_data_missing: bool        # FAIL-CLOSED flag — no screenable identifiers; forces hold + CRITICAL
    high_risk_country_flag: bool        # True if country in FATF black/grey list
    high_risk_country_name: str         # Country name for reporting
    pep_flag: bool                      # Politically Exposed Person match
    sanctions_hold_required: bool       # True if payment must be blocked pending review

    # ── Nacha Validation ───────────────────────────────────────────────────
    nacha_validation_passed: bool
    nacha_violations: List[str]         # Specific Nacha rule violations found
    return_reason: str                  # Human-readable reason for return
    return_window_open: bool            # True if within allowable return window
    return_window_days_remaining: int   # Days remaining in return window
    unauthorized_return_eligible: bool  # True if R07/R10/R29 is applicable
    late_return_flag: bool              # True if past standard return window (60+ days)
    noc_correction_required: bool       # NOC (C-series) requires ODFI record update
    noc_required: bool                  # Alias of noc_correction_required (test/reporting contract)
    ctr_threshold_triggered: bool       # Amount > $10K CTR threshold (31 CFR 1010.311) — rail-agnostic
    customer_claim_text: str            # Customer dispute claim narrative (sanitized at intake)
    account_tenure_months: int          # Receiver account age — Reg E new-account window input
    prior_dispute_count: int            # Prior disputes on the account — pattern factor input
    account_good_standing: bool         # Account standing — dispute analysis context
    noc_corrected_data: Dict[str, str]  # Corrected field values from NOC

    # ── Reg E Assessment ───────────────────────────────────────────────────
    reg_e_applicable: bool              # True if consumer EFT — Reg E governs
    reg_e_violation_detected: bool
    reg_e_violations: List[str]         # Specific Reg E rule violations
    dispute_claim_summary: str          # LLM-generated summary of customer's claim
    dispute_evidence_present: List[str] # Evidence supporting the dispute
    dispute_evidence_missing: List[str] # Evidence still needed

    # ── SLA Management ─────────────────────────────────────────────────────
    # SLA deadlines are Python-computed from received_timestamp in UTC
    sla_type: str                       # SLAType enum value
    sla_deadline: str                   # ISO-8601 UTC deadline
    sla_business_days_remaining: int    # Business days until deadline
    sla_calendar_days_remaining: int    # Calendar days until deadline
    sla_breached: bool                  # True if deadline already passed
    provisional_credit_required: bool   # Reg E 10-business-day rule
    provisional_credit_deadline: str    # ISO-8601 UTC — when provisional credit due
    provisional_credit_amount: float    # Amount to provisionally credit

    # ── Compliance Scoring ──────────────────────────────────────────────────
    # All scoring is Python-computed — not LLM
    compliance_risk_score: float        # 0.0–1.0 Python-computed composite
    compliance_risk_tier: str           # ComplianceRiskTier enum value
    score_breakdown: Dict[str, Any]     # Factor-by-factor scoring detail
    violation_count: int
    violation_severity_max: str         # CRITICAL | HIGH | MEDIUM | LOW

    # ── Routing & Resolution ────────────────────────────────────────────────
    target_team: str                    # PAYMENTS_OPS | DISPUTES | BSA | LEGAL | AUTO_RESOLVE
    resolution_type: str                # ResolutionType enum value
    human_review_required: bool
    human_review_reason: str
    priority: str                       # CRITICAL | HIGH | NORMAL | LOW
    escalation_path: List[str]          # Ordered list of escalation steps

    # ── LLM Analysis ───────────────────────────────────────────────────────
    # LLM-generated content — used for human reviewers and customer notices
    compliance_analysis: str            # LLM narrative analysis of the event
    anomaly_flags: List[str]            # Specific unusual patterns identified
    regulatory_citations: List[str]     # Applicable Nacha rules, CFR sections
    risk_narrative: str                 # LLM risk summary for reviewer

    # ── Human Review Gate ──────────────────────────────────────────────────
    reviewer_id: str
    reviewer_decision: str              # APPROVE_RESOLUTION | ESCALATE | OVERRIDE_RESOLUTION | REJECT_CLAIM
    reviewer_override_resolution: str   # Alternative resolution chosen by reviewer
    reviewer_notes: str
    review_timestamp: str

    # ── Resolution Output ──────────────────────────────────────────────────
    resolution_summary: str             # LLM-drafted resolution summary
    customer_notice_text: str           # LLM-drafted customer notification
    customer_notice_required: bool      # True if Reg E requires written notice
    customer_notice_deadline: str       # ISO-8601 UTC — when notice must be sent
    internal_memo: str                  # Internal memo for operations team

    # ── Output Payload ──────────────────────────────────────────────────────
    output_payload: Dict[str, Any]      # Structured compliance event record
    downstream_actions: List[Dict[str, Any]]  # Actions for downstream systems

    # ── Audit Trail ────────────────────────────────────────────────────────
    payment_status: str                 # PaymentStatus enum value
    processing_time_seconds: float
    audit_trail: List[Dict[str, Any]]   # Append-only — never modified
    completed_steps: List[str]
    errors: List[str]
