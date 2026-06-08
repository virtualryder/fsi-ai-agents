# agent/state.py
# ============================================================
# ChangeManagementState — Complete state for a regulatory change workflow
#
# Regulatory context:
#   Every field maps to requirements in:
#   - OCC Bulletin 2020-10 — Sound Practices for Model Risk Management
#   - Federal Reserve SR 11-7 — Guidance on Model Risk Management
#   - FFIEC BSA/AML Examination Manual — Regulatory Change Management
#   - 12 CFR Part 30, Appendix D — OCC Safety and Soundness Standards
#   - FDIC FIL-44-2008 — Regulatory Compliance Management
#
# Regulatory change management design:
#   This state supports both:
#   1. Automated ingestion from regulatory feeds (FinCEN, OCC, CFPB, SEC, FINRA)
#   2. Manual entry by compliance team for off-cycle regulatory developments
#   The change type and regulatory domain determine impact scoring weights
#   and routing to the appropriate compliance function.
#
# Human-in-the-loop:
#   CRITICAL and HIGH impact changes require Compliance Officer approval
#   of the gap analysis and remediation plan before stakeholder notification.
#   MEDIUM and LOW changes may route directly to remediation planning.
# ============================================================

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class ChangeType(str, Enum):
    """
    Classification of the regulatory document type.

    FINAL_RULE:           Published rule with binding legal effect; has effective date
    PROPOSED_RULE:        NPRM — comment period open; future obligation
    INTERIM_FINAL_RULE:   Effective immediately with comment period
    GUIDANCE:             Interpretive guidance — not binding law, but examiners expect compliance
    FAQ:                  Regulatory agency FAQ clarifying existing rule
    EXAMINATION_PROCEDURE: Updated examiner procedures — signals near-term examination focus
    ENFORCEMENT_ACTION:   Consent order or MRA — signals industry-wide examiner expectations
    BULLETIN:             Agency bulletin or letter (OCC Interpretive Letter, FDIC FIL)
    CIRCULAR:             FINRA Regulatory Notice or similar circular
    ADVISORY:             FinCEN Advisory or Geographic Targeting Order (GTO)
    """
    FINAL_RULE = "FINAL_RULE"
    PROPOSED_RULE = "PROPOSED_RULE"
    INTERIM_FINAL_RULE = "INTERIM_FINAL_RULE"
    GUIDANCE = "GUIDANCE"
    FAQ = "FAQ"
    EXAMINATION_PROCEDURE = "EXAMINATION_PROCEDURE"
    ENFORCEMENT_ACTION = "ENFORCEMENT_ACTION"
    BULLETIN = "BULLETIN"
    CIRCULAR = "CIRCULAR"
    ADVISORY = "ADVISORY"


class RegulatoryDomain(str, Enum):
    """
    Primary regulatory compliance domain the change falls under.

    Determines routing to the correct compliance owner and
    which business lines / products are potentially in scope.
    """
    BSA_AML = "BSA_AML"
    CONSUMER_COMPLIANCE = "CONSUMER_COMPLIANCE"
    CAPITAL_SAFETY_SOUNDNESS = "CAPITAL_SAFETY_SOUNDNESS"
    INVESTMENT_PRODUCTS = "INVESTMENT_PRODUCTS"
    TECHNOLOGY_OPERATIONS = "TECHNOLOGY_OPERATIONS"
    PRIVACY_DATA = "PRIVACY_DATA"
    FRAUD_PAYMENTS = "FRAUD_PAYMENTS"
    FAIR_LENDING = "FAIR_LENDING"
    COMMUNITY_REINVESTMENT = "COMMUNITY_REINVESTMENT"
    CROSS_BORDER = "CROSS_BORDER"
    OTHER = "OTHER"


class ImpactTier(str, Enum):
    """
    Impact classification based on composite score.

    CRITICAL (score >= 0.85):  Immediate action required. BSA/OFAC/exam timing.
                               CCO escalation + mandatory HITL.
    HIGH (0.65-0.84):         Significant policy changes or short compliance window.
                               Compliance owner + mandatory HITL.
    MEDIUM (0.40-0.64):       Policy amendments needed; implementation window >= 90 days.
                               Compliance owner notification; HITL optional.
    LOW (< 0.40):             Clarification or FAQ with minimal operational impact.
                               Auto-document; compliance owner awareness notification.
    """
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CaseStatus(str, Enum):
    """
    Lifecycle status of the regulatory change case.
    """
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    PENDING_REMEDIATION = "PENDING_REMEDIATION"
    REMEDIATION_IN_PROGRESS = "REMEDIATION_IN_PROGRESS"
    CLOSED_COMPLIANT = "CLOSED_COMPLIANT"
    CLOSED_NOT_APPLICABLE = "CLOSED_NOT_APPLICABLE"
    ESCALATED = "ESCALATED"


class ChangeManagementState(TypedDict, total=False):
    """
    Complete state for a single regulatory change management workflow.

    This TypedDict flows through every node in the LangGraph DAG.
    Fields are populated incrementally as the analysis progresses —
    mirroring how a compliance analyst works a regulatory change from
    intake through remediation planning.

    total=False: all fields optional at initialization, populated by nodes.
    """

    # ── Change Identification ───────────────────────────────────────────────
    change_id: str
    # Unique change identifier. Format: "REG-CHANGE-YYYY-XXXXXX"
    # Links to regulatory change management register (e.g., Wolters Kluwer,
    # MetricStream, or internal SharePoint tracker)

    change_title: str
    # Official title of the regulatory publication
    # Example: "Anti-Money Laundering/Countering the Financing of Terrorism Program
    # Effectiveness; Due Diligence; SAR Requirements"

    change_type: ChangeType
    # Classification of document type — affects urgency and response obligation

    regulatory_authority: str
    # Issuing agency: FinCEN | OCC | Federal Reserve | FDIC | CFPB |
    # SEC | FINRA | NCUA | State Banking Regulator | FATF | BIS/BCBS
    # May include multiple if joint rulemaking

    regulatory_domain: RegulatoryDomain
    # Primary compliance domain for routing and policy mapping

    publication_date: str
    # ISO 8601 date the change was officially published
    # For FRN rules: date published in Federal Register

    effective_date: Optional[str]
    # ISO 8601 date the change becomes enforceable
    # None for PROPOSED_RULE (not yet final)

    comment_deadline: Optional[str]
    # ISO 8601 comment period end date (PROPOSED_RULE and INTERIM_FINAL_RULE only)
    # Institution may want to submit comment letter for significant proposed rules

    citation: str
    # Official regulatory citation
    # Examples: "31 CFR Part 1010", "12 CFR Part 1026", "87 FR 58246"

    docket_number: Optional[str]
    # Federal Register docket or agency docket number for tracking

    source_url: str
    # Direct URL to the official regulatory publication

    full_text: str
    # Complete text of the regulatory change (may be truncated for LLM processing)
    # Stored in S3; this field holds the first 50,000 characters for analysis

    summary_text: str
    # Summary of the change (auto-generated or agency-provided)
    # Used as the primary input for gap analysis when full_text is too large

    # ── Source Validation ────────────────────────────────────────────────────
    source_validated: bool
    # Whether the source has been confirmed as a recognized regulatory authority
    # Prevents processing of unofficial summaries or third-party interpretations
    # as if they were binding regulatory changes

    source_tier: str
    # TIER_1_FEDERAL_PRIMARY:  Primary federal regulator (OCC, FDIC, Fed, NCUA, CFPB)
    # TIER_2_FEDERAL_SECONDARY: Secondary federal agencies (FinCEN, SEC, FINRA, DOJ)
    # TIER_3_STATE:             State banking regulator
    # TIER_4_INTERNATIONAL:     FATF, BIS, BCBS (advisory significance)
    # UNRECOGNIZED:             Source not validated — hold for manual review

    authority_applies_to_institution: bool
    # Whether this regulatory authority has jurisdiction over this institution
    # A state-chartered bank may not be subject to OCC-only guidance

    # ── Scope Determination ──────────────────────────────────────────────────
    affected_business_lines: List[str]
    # Business lines potentially in scope:
    # ["retail_banking", "commercial_banking", "wealth_management",
    #  "mortgage", "credit_cards", "payments", "trust_services",
    #  "international_banking", "insurance", "investment_banking"]

    affected_products: List[str]
    # Specific products potentially affected
    # Examples: ["wire_transfers", "ACH_origination", "mortgage_loans",
    #            "checking_accounts", "letters_of_credit"]

    affected_operations: List[str]
    # Operational processes potentially requiring change
    # Examples: ["KYC_onboarding", "SAR_filing", "CRA_reporting",
    #            "model_validation", "stress_testing", "consumer_disclosures"]

    scope_determination_rationale: str
    # Explanation of why specific business lines/products were identified
    # Examiner may ask why certain areas were included or excluded from scope

    # ── Policy Mapping ───────────────────────────────────────────────────────
    mapped_policies: List[Dict[str, Any]]
    # Policies from the institution's policy registry that may require updating
    # Each: {
    #   "policy_id": str,
    #   "policy_name": str,
    #   "policy_owner": str,
    #   "last_review_date": str,
    #   "current_version": str,
    #   "relevance_reason": str,  # why this policy is mapped
    #   "change_required": bool   # True if gap analysis confirms change needed
    # }

    mapped_procedures: List[Dict[str, Any]]
    # Standard operating procedures potentially requiring update
    # Same structure as mapped_policies

    mapped_controls: List[Dict[str, Any]]
    # Risk controls (in the control library) potentially affected
    # Each: {control_id, control_name, control_owner, current_effectiveness, relevance_reason}

    policy_mapping_rationale: str
    # Explanation of the policy/procedure mapping decisions

    # ── Gap Analysis (LLM) ───────────────────────────────────────────────────
    gap_analysis_narrative: str
    # Full LLM-generated gap analysis comparing the regulatory change
    # against the institution's current policies and procedures
    # Structured: requirement by requirement, current state, gap identified

    gap_analysis_summary: str
    # 3-5 sentence executive summary of the gap analysis
    # Used in the compliance officer review package

    identified_gaps: List[Dict[str, Any]]
    # Structured list of specific gaps identified
    # Each: {
    #   "gap_id": str,
    #   "requirement": str,      # specific regulatory requirement
    #   "current_state": str,    # what the institution does today
    #   "gap_description": str,  # what's missing or insufficient
    #   "affected_policy": str,  # which policy needs to change
    #   "severity": str,         # CRITICAL | HIGH | MEDIUM | LOW
    #   "remediation_effort": str  # MAJOR_REWRITE | AMENDMENT | CLARIFICATION
    # }

    is_applicable: bool
    # Whether this change applies to the institution at all
    # Some changes are institution-type specific or product-specific

    applicability_rationale: str
    # Explanation of why the change is or is not applicable

    # ── Impact Scoring (Python) ──────────────────────────────────────────────
    impact_score: float
    # Composite impact score 0.0 - 1.0
    # Weights: authority_tier 25%, deadline_urgency 25%, scope_breadth 20%,
    #          policy_depth 15%, remediation_complexity 15%

    impact_tier: ImpactTier
    # CRITICAL | HIGH | MEDIUM | LOW — derived from impact_score

    impact_score_components: Dict[str, float]
    # Factor-by-factor score breakdown for SR 11-7 explainability:
    # {
    #   "authority_tier_score": 0.0-1.0,    # regulator primacy
    #   "deadline_urgency_score": 0.0-1.0,  # days until effective
    #   "scope_breadth_score": 0.0-1.0,     # business lines affected
    #   "policy_depth_score": 0.0-1.0,      # extent of policy changes needed
    #   "remediation_complexity_score": 0.0-1.0  # effort to implement
    # }

    days_to_effective: Optional[int]
    # Calendar days from today to effective_date
    # None if effective_date is not yet set (PROPOSED_RULE)

    implementation_complexity: str
    # MAJOR: New policies, new systems, significant training required
    # MODERATE: Policy amendments, updated procedures, targeted training
    # MINOR: Clarifications, FAQ, minimal operational change

    compliance_window_adequate: bool
    # Whether the institution has adequate time to implement before effective date
    # False → automatically elevates urgency in impact scoring

    # ── Routing ──────────────────────────────────────────────────────────────
    primary_compliance_owner: str
    # Role responsible for leading the remediation effort
    # BSA_OFFICER | CHIEF_COMPLIANCE_OFFICER | CONSUMER_COMPLIANCE_OFFICER |
    # CHIEF_RISK_OFFICER | INVESTMENT_COMPLIANCE_OFFICER | CHIEF_PRIVACY_OFFICER

    secondary_compliance_owners: List[str]
    # Additional compliance roles who need awareness or contribution

    business_unit_owners: List[str]
    # Business line heads who need to implement operational changes
    # These receive stakeholder notifications, not the full gap analysis

    routing_rationale: str
    # Explanation of routing decisions

    # ── Human Review Gate ────────────────────────────────────────────────────
    human_review_required: bool
    # True for CRITICAL and HIGH impact changes (mandatory)
    # True for any ENFORCEMENT_ACTION regardless of score

    compliance_officer_id: Optional[str]
    # ID of the Compliance Officer who reviewed the gap analysis

    compliance_officer_decision: Optional[str]
    # APPROVED | MODIFIED | ESCALATED | NOT_APPLICABLE
    # If MODIFIED: compliance_officer_notes explains changes made

    compliance_officer_notes: Optional[str]
    # Notes from the reviewing officer

    human_review_completed_at: Optional[str]
    # ISO 8601 timestamp of review completion

    # ── Remediation Planning (LLM) ───────────────────────────────────────────
    remediation_plan_narrative: str
    # Full LLM-drafted remediation plan with specific action items,
    # owners, sequencing, dependencies, and timeline

    remediation_tasks: List[Dict[str, Any]]
    # Structured action items generated from the remediation plan
    # Each: {
    #   "task_id": str,
    #   "task_description": str,
    #   "task_owner": str,         # role responsible
    #   "due_date": str,           # ISO 8601
    #   "priority": str,           # HIGH | MEDIUM | LOW
    #   "dependencies": List[str], # other task_ids that must complete first
    #   "status": str,             # OPEN | IN_PROGRESS | COMPLETE | BLOCKED
    #   "linked_gap_id": str       # which identified_gap this resolves
    # }

    remediation_deadline: str
    # Overall deadline for completing all remediation tasks
    # Set to effective_date minus 14 days for buffer; or publication_date + 90 days
    # if effective_date is not specified

    estimated_effort_hours: Optional[int]
    # Estimated total implementation hours across all tasks
    # Used for resource planning and staffing requests

    # ── Stakeholder Notifications ────────────────────────────────────────────
    stakeholder_notifications: List[Dict[str, Any]]
    # Notification records for each stakeholder
    # Each: {
    #   "recipient_role": str,
    #   "notification_type": str,  # AWARENESS | ACTION_REQUIRED | FYI
    #   "draft_message": str,      # tailored message per recipient role
    #   "sent_at": Optional[str]   # ISO 8601 when sent
    # }

    comment_letter_recommended: bool
    # Whether the institution should consider submitting a comment letter
    # (for PROPOSED_RULE with significant operational impact)

    comment_letter_draft: Optional[str]
    # Draft comment letter if comment_letter_recommended is True

    # ── Tracking Register ────────────────────────────────────────────────────
    change_register_entry: Dict[str, Any]
    # Summary record for the regulatory change register
    # {change_id, title, authority, domain, impact_tier, effective_date,
    #  remediation_deadline, primary_owner, status, last_updated}

    case_status: CaseStatus
    # Lifecycle status

    # ── LangGraph Infrastructure ─────────────────────────────────────────────
    current_step: str
    completed_steps: List[str]
    errors: List[Dict[str, Any]]

    # ── Audit Trail ──────────────────────────────────────────────────────────
    # REGULATORY REQUIREMENT: Compliance program documentation must show that
    # the institution has a process for identifying, analyzing, and implementing
    # regulatory changes. FFIEC examiners review this process during BSA
    # and consumer compliance examinations.

    audit_trail: List[Dict[str, Any]]
    # Each entry: {
    #   "timestamp": ISO 8601,
    #   "actor": "system" | officer_id | "ai_agent",
    #   "action": description,
    #   "node": graph node name,
    #   "data_sources_accessed": list,
    #   "ai_model_used": model name if LLM invoked,
    #   "regulatory_basis": citation
    # }
