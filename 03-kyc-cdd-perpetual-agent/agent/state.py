# agent/state.py
# ============================================================
# KYCReviewState — Complete state for a KYC/CDD perpetual review
#
# Regulatory context:
#   Every field maps to requirements in:
#   - FinCEN CDD Rule (31 CFR 1020.210) — CDD for legal entity customers
#   - FATF Recommendation 10 — Customer due diligence measures
#   - FATF Recommendation 12 — Politically exposed persons (PEPs)
#   - FFIEC BSA/AML Examination Manual — KYC program expectations
#   - BSA 31 U.S.C. § 5318(l) — CIP (Customer Identification Program)
#   - OCC Bulletin 2018-17 / SR 11-7 — Model risk management
#
# Perpetual KYC design:
#   This state supports both:
#   1. Event-driven reviews (trigger_type != SCHEDULED)
#   2. Scheduled periodic reviews (trigger_type == SCHEDULED)
#   The trigger source determines urgency, EDD thresholds, and routing.
#
# Human-in-the-loop:
#   No risk rating change is recorded without Compliance Officer approval
#   at the human_review_gate node. The agent drafts; the human decides.
# ============================================================

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class TriggerType(str, Enum):
    """
    What caused this KYC review to be initiated.

    SCHEDULED:           Periodic risk-based review cycle
                         (HIGH=annual, MEDIUM=2yr, LOW=3yr)
    ADVERSE_MEDIA:       Negative news hit on customer or beneficial owner
    WATCHLIST_HIT:       OFAC/PEP/sanctions screening match
    TRANSACTION_SPIKE:   Unusual transaction volume vs. expected behavior profile
    BENEFICIAL_OWNER_CHANGE: UBO structure change detected or reported
    NEW_PRODUCT:         Customer onboarded for a new high-risk product
    JURISDICTION_CHANGE: Customer activity in newly high-risk jurisdiction
    SAR_FILED:           SAR was filed on this customer — triggers EDD review
    MANUAL:              Compliance officer or relationship manager initiated
    REGULATORY_EXAM:     Examiner requested review during BSA exam
    RISK_MODEL_FLAG:     ML risk score drift exceeded threshold
    """
    SCHEDULED = "SCHEDULED"
    ADVERSE_MEDIA = "ADVERSE_MEDIA"
    WATCHLIST_HIT = "WATCHLIST_HIT"
    TRANSACTION_SPIKE = "TRANSACTION_SPIKE"
    BENEFICIAL_OWNER_CHANGE = "BENEFICIAL_OWNER_CHANGE"
    NEW_PRODUCT = "NEW_PRODUCT"
    JURISDICTION_CHANGE = "JURISDICTION_CHANGE"
    SAR_FILED = "SAR_FILED"
    MANUAL = "MANUAL"
    REGULATORY_EXAM = "REGULATORY_EXAM"
    RISK_MODEL_FLAG = "RISK_MODEL_FLAG"


class RiskTier(str, Enum):
    """
    Customer risk classification.

    Maps to FinCEN CDD Rule and FFIEC risk-based approach.
    Determines review frequency, EDD requirements, and monitoring intensity.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"     # EDD required — PEPs, high-risk industries
    PROHIBITED = "PROHIBITED"   # Relationship exit required


class ReviewOutcome(str, Enum):
    """
    Disposition of the KYC review after all evidence is assembled.

    PASS:              No material changes. Update review date. No RM action needed.
    RISK_UPGRADE:      Risk tier increases. RM notification + compliance approval required.
    RISK_DOWNGRADE:    Risk tier decreases. Compliance approval required.
    EDD_REQUIRED:      Enhanced Due Diligence triggered. Document collection package generated.
    ESCALATE:          Findings require senior compliance review or SAR consideration.
    RELATIONSHIP_EXIT: Risk exceeds institution's appetite. Exit process initiated.
    """
    PASS = "PASS"
    RISK_UPGRADE = "RISK_UPGRADE"
    RISK_DOWNGRADE = "RISK_DOWNGRADE"
    EDD_REQUIRED = "EDD_REQUIRED"
    ESCALATE = "ESCALATE"
    RELATIONSHIP_EXIT = "RELATIONSHIP_EXIT"


class KYCReviewState(TypedDict, total=False):
    """
    Complete state for a single KYC/CDD perpetual review.

    This TypedDict flows through every node in the LangGraph DAG.
    Fields are populated incrementally as the review progresses —
    mirroring how a KYC analyst builds a review file.

    total=False: all fields optional at initialization, populated by nodes.
    """

    # ── Review / Trigger Information ──────────────────────────────────────────
    # How and why this review was initiated.

    review_id: str
    # Unique review identifier. Format: "KYC-REVIEW-YYYY-XXXXXX"
    # Links to KYC case management system (e.g., Actimize CRM, Fiserv Compliance)

    trigger_type: TriggerType
    # What caused this review — drives urgency and EDD thresholds

    trigger_description: str
    # Human-readable description of the specific trigger event
    # Example: "Adverse media hit: Reuters article dated 2024-11-15 — customer
    # named in SEC enforcement action for undisclosed related-party transactions"

    trigger_event_date: str
    # ISO 8601 date of the triggering event (not the review start date)
    # Critical for regulatory timelines: EDD must begin within X days of trigger

    review_initiated_date: str
    # ISO 8601 date review was opened in the system

    review_deadline: str
    # ISO 8601 deadline date for completing the review
    # Risk-based: HIGH triggers = 7 days, MEDIUM = 30 days, LOW/SCHEDULED = 60 days

    # ── Customer / Entity Information ─────────────────────────────────────────
    # FinCEN CDD Rule requires: entity name, principal place of business,
    # EIN/TIN, nature of business, beneficial ownership (≥25% equity).
    # BSA CIP requires: name, address, DOB/EIN, identifying document.

    customer_id: str
    # Internal customer ID from core banking system

    customer_name: str
    # Legal entity name or individual full name

    customer_type: str
    # INDIVIDUAL | SOLE_PROPRIETOR | PARTNERSHIP | CORPORATION |
    # LLC | TRUST | NON_PROFIT | FOREIGN_ENTITY | FINANCIAL_INSTITUTION

    account_ids: List[str]
    # All active account numbers. Reviews cover all accounts simultaneously.

    relationship_manager_id: str
    # RM assigned to this customer — receives notification of review outcome

    # ── Current KYC Record ────────────────────────────────────────────────────
    # The existing CDD file at time of review trigger.
    # This is what we're reviewing, refreshing, and potentially upgrading.

    current_risk_tier: RiskTier
    # Risk classification before this review

    kyc_last_refreshed: str
    # ISO 8601 date of last CDD refresh

    cdd_completeness_score: float
    # 0-100 score of how complete the current CDD file is
    # Assessed by document_collection node against required document checklist

    edd_status: bool
    # Whether the customer is currently on Enhanced Due Diligence program

    pep_flag: bool
    # Politically Exposed Person indicator
    # PEP flag → mandatory EDD, regardless of other risk factors (FATF R.12)

    pep_category: Optional[str]
    # If PEP: DOMESTIC_PEP | FOREIGN_PEP | INTERNATIONAL_ORG_PEP | FAMILY_MEMBER | CLOSE_ASSOCIATE
    # Foreign PEPs (heads of state, senior officials) require strongest EDD

    beneficial_owners: List[Dict[str, Any]]
    # UBO list — all natural persons owning ≥25% equity (FinCEN CDD Rule)
    # Each entry: {name, ownership_pct, nationality, pep_flag, dob, address}
    # Legal entity customers must provide UBO list before account opening

    business_type: str
    # Industry/NAICS code — drives expected transaction behavior profile
    # High-risk businesses: money services, casinos, cannabis, shell companies

    expected_transaction_profile: Dict[str, Any]
    # Customer's documented expected activity profile:
    #   - monthly_volume_range: [min, max] in USD
    #   - primary_transaction_types: [wire, ACH, cash, check]
    #   - primary_counterparty_countries: [list of ISO country codes]
    #   - expected_cash_intensity: LOW | MEDIUM | HIGH

    jurisdiction_risk: str
    # LOW | MEDIUM | HIGH — based on countries of operation/incorporation
    # References: FATF grey/black list, OFAC comprehensively sanctioned countries,
    # FinCEN advisories, State Department INCSR

    # ── Document Collection Results ───────────────────────────────────────────
    # What documents are on file, what's missing, what's expired.

    required_documents: List[str]
    # List of documents required for this customer type and risk tier
    # Generated by document_collection node based on CDD Rule and risk tier

    documents_on_file: List[Dict[str, Any]]
    # Documents currently in the KYC file
    # Each: {doc_type, date_collected, expiry_date, status: CURRENT|EXPIRED|MISSING}

    missing_documents: List[str]
    # Documents required but not on file or expired

    document_gap_narrative: str
    # Human-readable description of document gaps for RM outreach letter

    # ── Watchlist / Sanctions Screening ───────────────────────────────────────
    # Re-screening required at every review cycle regardless of trigger type.
    # OFAC screening is a continuous legal obligation — not a one-time check.

    watchlist_screening_results: List[Dict[str, Any]]
    # Results for customer + all beneficial owners + all counterparties
    # Each: {screened_entity, list_name, match_score, match_type, hit_details}

    ofac_hit: bool
    # Hard flag: any OFAC SDN match triggers immediate escalation
    # OFAC matches are never suppressed — legal obligation to freeze and report

    pep_watchlist_hit: bool
    # PEP list hit on customer or beneficial owner

    # ── Adverse Media ──────────────────────────────────────────────────────────
    # Required for EDD and high-risk customers under FATF R.12 / OCC guidance.
    # News lag means a customer may be involved in misconduct before appearing on lists.

    adverse_media_results: List[Dict[str, Any]]
    # Each: {source, headline, date, category, url, relevance_score, entity_matched}
    # Categories: fraud | corruption | tax_evasion | money_laundering |
    #             drug_trafficking | sanctions_violation | regulatory_action |
    #             terrorism | human_trafficking

    adverse_media_severity: str
    # NONE | LOW | MEDIUM | HIGH | CRITICAL
    # CRITICAL (regulatory action, law enforcement) → triggers immediate EDD

    # ── Risk Rescoring ─────────────────────────────────────────────────────────
    # Composite risk score calculated across all review findings.
    # Score is ADVISORY — Compliance Officer makes final risk tier determination.
    # SR 11-7: model must be documented, validated, and explainable.

    previous_risk_score: float
    # Risk score from last review (0-100)

    new_risk_score: float
    # Updated composite risk score after this review (0-100)

    risk_score_delta: float
    # Change from previous score. Material change (±15+) triggers routing escalation.

    risk_score_components: Dict[str, float]
    # Factor-by-factor breakdown for SR 11-7 explainability:
    # {
    #   "jurisdiction_risk": score,
    #   "transaction_behavior": score,
    #   "pep_status": score,
    #   "adverse_media": score,
    #   "document_completeness": score,
    #   "beneficial_ownership_clarity": score,
    #   "industry_risk": score,
    #   "account_tenure": score
    # }

    risk_narrative: str
    # Plain-language explanation of risk score factors
    # Compliance Officer reads this to make risk tier decision

    # ── Review Outcome & Routing ───────────────────────────────────────────────

    recommended_outcome: ReviewOutcome
    # Agent's recommended disposition — MUST be approved by Compliance Officer

    proposed_risk_tier: RiskTier
    # If RISK_UPGRADE or RISK_DOWNGRADE: the proposed new tier
    # Compliance Officer can accept, modify, or override

    routing_rationale: str
    # Explanation of why this routing decision was made

    # ── EDD Package ───────────────────────────────────────────────────────────
    # Generated when EDD_REQUIRED outcome is triggered.
    # Sent to RM for customer outreach and document collection.

    edd_required: bool
    # Whether EDD has been triggered by this review

    edd_trigger_reasons: List[str]
    # Specific reasons EDD was triggered (PEP flag, adverse media, etc.)

    edd_document_checklist: List[Dict[str, Any]]
    # Documents required for EDD completion
    # Each: {document, reason_required, deadline, priority: HIGH|MEDIUM|LOW}

    edd_outreach_draft: str
    # Draft communication for RM to send to customer requesting EDD documents
    # Written in plain language, referencing specific document requests

    edd_deadline: str
    # ISO 8601 deadline for EDD document collection
    # If documents not received: escalate to relationship exit consideration

    # ── Relationship Manager Notification ─────────────────────────────────────
    # All outcomes trigger RM notification (even PASS) for portfolio awareness.

    rm_notification_draft: str
    # Draft message to Relationship Manager summarizing review outcome
    # Includes: risk change, action required (if any), customer-facing talking points

    rm_action_required: bool
    # Whether the RM needs to take action (customer outreach, document collection)

    # ── Human Review Gate ──────────────────────────────────────────────────────
    # Compliance Officer review and approval before any record change is written.

    human_review_required: bool
    # True for: RISK_UPGRADE, RISK_DOWNGRADE, EDD_REQUIRED, ESCALATE, RELATIONSHIP_EXIT

    compliance_officer_id: Optional[str]
    # ID of the Compliance Officer who reviewed and approved/overrode the outcome

    compliance_officer_decision: Optional[str]
    # APPROVED | OVERRIDDEN | ESCALATED_FURTHER
    # If OVERRIDDEN: compliance_officer_notes explains the change

    compliance_officer_notes: Optional[str]
    # Notes from Compliance Officer on their decision

    human_review_completed_at: Optional[str]
    # ISO 8601 timestamp of human review completion

    # ── KYC Record Update ──────────────────────────────────────────────────────
    # Fields written to the official KYC record after compliance approval.

    final_risk_tier: RiskTier
    # The approved risk tier written to the KYC record
    # (compliance_officer_decision determines whether this matches proposed_risk_tier)

    next_review_date: str
    # ISO 8601 date of next scheduled review
    # Risk-based: VERY_HIGH/HIGH = 1 year, MEDIUM = 2 years, LOW = 3 years

    kyc_record_updated_at: str
    # ISO 8601 timestamp of KYC record update

    # ── Case Management ────────────────────────────────────────────────────────

    case_status: str
    # OPEN | IN_PROGRESS | PENDING_HUMAN_REVIEW | PENDING_EDD_DOCS |
    # PENDING_RM_ACTION | APPROVED | ESCALATED | RELATIONSHIP_EXIT | CLOSED

    # ── LangGraph Infrastructure ───────────────────────────────────────────────

    current_step: str
    # Currently executing node name — used by Streamlit UI for progress display

    completed_steps: List[str]
    # All completed node names

    errors: List[Dict[str, Any]]
    # Non-fatal errors: {step, error, timestamp, recoverable}

    # ── Audit Trail ────────────────────────────────────────────────────────────
    # REGULATORY REQUIREMENT: Examiners expect full documentation of every
    # review action, decision, and data source accessed. OCC and FinCEN
    # will review these records during BSA examinations.

    audit_trail: List[Dict[str, Any]]
    # Each entry: {
    #   "timestamp": ISO 8601,
    #   "actor": "system" | compliance_officer_id | relationship_manager_id | "ai_agent",
    #   "action": description,
    #   "node": graph node name,
    #   "data_sources_accessed": list,
    #   "ai_model_used": model name if LLM invoked,
    #   "regulatory_basis": citation (e.g., "FinCEN CDD Rule 31 CFR 1020.210"),
    #   "human_review_required": bool
    # }
