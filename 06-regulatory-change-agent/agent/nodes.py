# agent/nodes.py
# ============================================================
# Regulatory Change Management — Node Functions
#
# Each function is one node in the LangGraph DAG.
# Nodes receive the full ChangeManagementState and return a dict
# of state updates — LangGraph merges these back into the state.
#
# Design principles:
#   - Deterministic gates: routing, scoring, and scope determination
#     are Python — not LLM output
#   - LLM for drafting/narrative only (gap analysis, remediation plans,
#     notifications, comment letters)
#   - Every significant action appended to audit_trail
#   - Hard-coded overrides: ENFORCEMENT_ACTION always requires HITL;
#     FINAL_RULE with immediate effective date → CRITICAL tier floor
#   - Simulated tool calls in dev mode (no live feed APIs required)
# ============================================================

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from langchain_anthropic import ChatAnthropic
from agent.persistence import audit_sink
from langchain_core.messages import SystemMessage, HumanMessage

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


from agent.state import (
    ChangeManagementState,
    ChangeType,
    RegulatoryDomain,
    ImpactTier,
    CaseStatus,
)
from agent.prompts import (
    GAP_ANALYSIS_SYSTEM_PROMPT,
    GAP_ANALYSIS_USER_PROMPT,
    REMEDIATION_PLANNING_SYSTEM_PROMPT,
    REMEDIATION_PLANNING_USER_PROMPT,
    STAKEHOLDER_NOTIFICATION_SYSTEM_PROMPT,
    STAKEHOLDER_NOTIFICATION_USER_PROMPT,
    COMMENT_LETTER_SYSTEM_PROMPT,
    COMMENT_LETTER_USER_PROMPT,
    EXECUTIVE_SUMMARY_PROMPT,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_llm():
    """Initialize LLM client. Centralized for easy model swapping."""
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL,
        temperature=0,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


def _add_audit_entry(
    state: ChangeManagementState,
    action: str,
    node: str,
    data_sources: list = None,
    used_llm: bool = False,
    regulatory_basis: str = None,
) -> list:
    """Append an audit trail entry. Returns updated audit_trail list."""
    trail = list(state.get("audit_trail", []))
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": "ai_agent",
        "action": action,
        "node": node,
        "data_sources_accessed": data_sources or [],
        "ai_model_used": "claude-sonnet-4-6" if used_llm else None,
        "regulatory_basis": regulatory_basis,
        "change_id": state.get("change_id"),
        "change_title": state.get("change_title"),
    }
    trail.append(entry)
    # WRITE-AHEAD: durable audit record at creation time (see agent/persistence.py)
    audit_sink().record(entry)
    return trail


def _days_until(date_str: Optional[str]) -> Optional[int]:
    """Calculate calendar days from today to a future date string."""
    if not date_str:
        return None
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        return (target - today).days
    except (ValueError, TypeError):
        return None


def _load_policy_registry() -> List[Dict]:
    """Load the institution's policy registry from fixtures."""
    registry_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "fixtures", "policy_registry.json"
    )
    try:
        with open(registry_path) as f:
            return json.load(f)
    except FileNotFoundError:
        return _default_policy_registry()


def _load_routing_matrix() -> Dict:
    """Load the compliance routing matrix from fixtures."""
    matrix_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "fixtures", "routing_matrix.json"
    )
    try:
        with open(matrix_path) as f:
            return json.load(f)
    except FileNotFoundError:
        return _default_routing_matrix()


def _default_policy_registry() -> List[Dict]:
    """Fallback policy registry if fixture file not found."""
    return [
        {"policy_id": "POL-001", "name": "BSA/AML Compliance Program", "domain": "BSA_AML", "owner": "BSA_OFFICER"},
        {"policy_id": "POL-002", "name": "Customer Identification Program", "domain": "BSA_AML", "owner": "BSA_OFFICER"},
        {"policy_id": "POL-003", "name": "Customer Due Diligence Policy", "domain": "BSA_AML", "owner": "BSA_OFFICER"},
        {"policy_id": "POL-004", "name": "SAR Filing Policy", "domain": "BSA_AML", "owner": "BSA_OFFICER"},
        {"policy_id": "POL-005", "name": "Consumer Compliance Program", "domain": "CONSUMER_COMPLIANCE", "owner": "CONSUMER_COMPLIANCE_OFFICER"},
        {"policy_id": "POL-006", "name": "Fair Lending Policy", "domain": "FAIR_LENDING", "owner": "CONSUMER_COMPLIANCE_OFFICER"},
        {"policy_id": "POL-007", "name": "Privacy Policy (GLBA)", "domain": "PRIVACY_DATA", "owner": "CHIEF_PRIVACY_OFFICER"},
        {"policy_id": "POL-008", "name": "Model Risk Management Policy", "domain": "CAPITAL_SAFETY_SOUNDNESS", "owner": "CHIEF_RISK_OFFICER"},
        {"policy_id": "POL-009", "name": "Investment Suitability Policy", "domain": "INVESTMENT_PRODUCTS", "owner": "INVESTMENT_COMPLIANCE_OFFICER"},
        {"policy_id": "POL-010", "name": "Fraud Risk Management Policy", "domain": "FRAUD_PAYMENTS", "owner": "CHIEF_RISK_OFFICER"},
    ]


def _default_routing_matrix() -> Dict:
    """Fallback routing matrix if fixture file not found."""
    return {
        "BSA_AML": {"primary": "BSA_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER"]},
        "CONSUMER_COMPLIANCE": {"primary": "CONSUMER_COMPLIANCE_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER"]},
        "CAPITAL_SAFETY_SOUNDNESS": {"primary": "CHIEF_RISK_OFFICER", "secondary": ["CFO", "CHIEF_COMPLIANCE_OFFICER"]},
        "INVESTMENT_PRODUCTS": {"primary": "INVESTMENT_COMPLIANCE_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER"]},
        "TECHNOLOGY_OPERATIONS": {"primary": "CHIEF_COMPLIANCE_OFFICER", "secondary": ["CTO", "CHIEF_RISK_OFFICER"]},
        "PRIVACY_DATA": {"primary": "CHIEF_PRIVACY_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER", "GENERAL_COUNSEL"]},
        "FRAUD_PAYMENTS": {"primary": "CHIEF_RISK_OFFICER", "secondary": ["BSA_OFFICER", "CHIEF_COMPLIANCE_OFFICER"]},
        "FAIR_LENDING": {"primary": "CONSUMER_COMPLIANCE_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER", "GENERAL_COUNSEL"]},
        "COMMUNITY_REINVESTMENT": {"primary": "CRA_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER"]},
        "CROSS_BORDER": {"primary": "BSA_OFFICER", "secondary": ["CHIEF_COMPLIANCE_OFFICER", "GENERAL_COUNSEL"]},
        "OTHER": {"primary": "CHIEF_COMPLIANCE_OFFICER", "secondary": []},
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1: Change Intake
# ══════════════════════════════════════════════════════════════════════════════

def change_intake_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Receive and parse an incoming regulatory change.

    Accepts input from:
    - Automated regulatory feed polling (FinCEN, OCC, Federal Register RSS)
    - Manual entry by compliance team
    - Email parsing from regulatory update distribution lists

    Normalizes the input into a consistent state format.
    """
    change_id = (
        state.get("change_id")
        or f"REG-CHANGE-{datetime.utcnow().strftime('%Y%m%d')}-{state.get('regulatory_authority', 'UNK')[:3].upper()}-"
           f"{abs(hash(state.get('change_title', ''))) % 10000:04d}"
    )

    days_to_effective = _days_until(state.get("effective_date"))

    logger.info(f"Change intake: {change_id} | {state.get('change_title', 'UNKNOWN')}")

    return {
        "change_id": change_id,
        "days_to_effective": days_to_effective,
        "case_status": CaseStatus.IN_PROGRESS,
        "current_step": "change_intake_node",
        "completed_steps": ["change_intake_node"],
        "errors": [],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Regulatory change received. Source: {state.get('regulatory_authority')}. "
                   f"Type: {state.get('change_type')}. "
                   f"Effective: {state.get('effective_date', 'TBD')}. "
                   f"Days until effective: {days_to_effective}.",
            node="change_intake_node",
            data_sources=["regulatory_feed", "manual_entry"],
            regulatory_basis="FFIEC Regulatory Change Management — intake logging requirement",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2: Source Validation
# ══════════════════════════════════════════════════════════════════════════════

# Recognized regulatory authorities and their tier classification
RECOGNIZED_AUTHORITIES = {
    "FinCEN": "TIER_2_FEDERAL_SECONDARY",
    "OCC": "TIER_1_FEDERAL_PRIMARY",
    "Federal Reserve": "TIER_1_FEDERAL_PRIMARY",
    "FDIC": "TIER_1_FEDERAL_PRIMARY",
    "CFPB": "TIER_1_FEDERAL_PRIMARY",
    "SEC": "TIER_2_FEDERAL_SECONDARY",
    "FINRA": "TIER_2_FEDERAL_SECONDARY",
    "NCUA": "TIER_1_FEDERAL_PRIMARY",
    "CFTC": "TIER_2_FEDERAL_SECONDARY",
    "FHFA": "TIER_2_FEDERAL_SECONDARY",
    "HUD": "TIER_2_FEDERAL_SECONDARY",
    "DOJ": "TIER_2_FEDERAL_SECONDARY",
    "FATF": "TIER_4_INTERNATIONAL",
    "BIS": "TIER_4_INTERNATIONAL",
    "BCBS": "TIER_4_INTERNATIONAL",
    "State": "TIER_3_STATE",  # State regulators — partial match
}

# These change types always require HITL regardless of impact score
ALWAYS_HITL_CHANGE_TYPES = {
    ChangeType.ENFORCEMENT_ACTION,
    ChangeType.EXAMINATION_PROCEDURE,
}


def source_validation_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Validate the regulatory source and classify authority tier.

    Prevents processing of:
    - Unofficial summaries (law firm client alerts, trade publications)
    - Duplicate submissions of the same rule
    - Changes from authorities with no jurisdiction over this institution

    Authority tier drives the authority_tier_score component of impact scoring.
    Tier 1 federal primary regulators carry the most weight — their rules
    are directly enforceable against the institution.
    """
    authority = state.get("regulatory_authority", "")
    source_url = state.get("source_url", "")
    change_type = state.get("change_type")

    # Validate source authority
    tier = "UNRECOGNIZED"
    for auth_key, auth_tier in RECOGNIZED_AUTHORITIES.items():
        if auth_key.lower() in authority.lower():
            tier = auth_tier
            break

    source_validated = tier != "UNRECOGNIZED"

    # State-chartered banks may not be subject to OCC guidance
    # Simplified heuristic: assume institution is subject to all federal regulators
    # In production: compare against institution charter configuration
    authority_applies = tier in (
        "TIER_1_FEDERAL_PRIMARY",
        "TIER_2_FEDERAL_SECONDARY",
        "TIER_3_STATE",
        "TIER_4_INTERNATIONAL",
    )

    # Hard override: enforcement actions always require HITL
    force_hitl = change_type in ALWAYS_HITL_CHANGE_TYPES

    if not source_validated:
        logger.warning(f"Change {state.get('change_id')}: Unrecognized authority '{authority}'")

    audit_trail = _add_audit_entry(
        state,
        action=f"Source validation: authority='{authority}', tier={tier}, "
               f"validated={source_validated}, applies_to_institution={authority_applies}. "
               f"{'ENFORCEMENT ACTION — mandatory HITL flagged.' if force_hitl else ''}",
        node="source_validation_node",
        data_sources=["regulatory_source_registry"],
    )

    updates = {
        "source_validated": source_validated,
        "source_tier": tier,
        "authority_applies_to_institution": authority_applies,
        "current_step": "source_validation_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["source_validation_node"],
        "audit_trail": audit_trail,
    }

    # Flag enforcement actions for mandatory HITL by pre-setting impact tier
    if force_hitl:
        updates["human_review_required"] = True

    return updates


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3: Scope Determination
# ══════════════════════════════════════════════════════════════════════════════

# Domain → business lines and products mapping
DOMAIN_SCOPE_MAP = {
    RegulatoryDomain.BSA_AML: {
        "business_lines": ["retail_banking", "commercial_banking", "wealth_management",
                           "mortgage", "international_banking", "payments"],
        "products": ["wire_transfers", "ACH_origination", "cash_management",
                     "correspondent_banking", "letters_of_credit", "trade_finance"],
        "operations": ["KYC_onboarding", "SAR_filing", "CTR_filing",
                       "OFAC_screening", "transaction_monitoring", "EDD_reviews"],
    },
    RegulatoryDomain.CONSUMER_COMPLIANCE: {
        "business_lines": ["retail_banking", "mortgage", "credit_cards", "auto_lending"],
        "products": ["mortgage_loans", "HELOC", "credit_cards", "personal_loans",
                     "checking_accounts", "savings_accounts"],
        "operations": ["consumer_disclosures", "loan_origination", "servicing",
                       "debt_collection", "fair_lending_analysis"],
    },
    RegulatoryDomain.CAPITAL_SAFETY_SOUNDNESS: {
        "business_lines": ["retail_banking", "commercial_banking", "investment_banking"],
        "products": ["commercial_loans", "CRE_loans", "securities_portfolio"],
        "operations": ["stress_testing", "CECL_modeling", "capital_planning",
                       "model_risk_management", "liquidity_management"],
    },
    RegulatoryDomain.INVESTMENT_PRODUCTS: {
        "business_lines": ["wealth_management", "retirement_services", "trust_services"],
        "products": ["mutual_funds", "annuities", "managed_accounts",
                     "retirement_plans", "trust_accounts", "securities"],
        "operations": ["suitability_review", "recommendations", "disclosures",
                       "trade_execution", "custody"],
    },
    RegulatoryDomain.TECHNOLOGY_OPERATIONS: {
        "business_lines": ["retail_banking", "commercial_banking", "wealth_management",
                           "mortgage", "payments"],
        "products": ["online_banking", "mobile_banking", "digital_payments"],
        "operations": ["IT_risk_management", "cybersecurity", "vendor_management",
                       "business_continuity", "change_management"],
    },
    RegulatoryDomain.PRIVACY_DATA: {
        "business_lines": ["retail_banking", "commercial_banking", "mortgage",
                           "credit_cards", "wealth_management"],
        "products": ["all_products_processing_NPI"],
        "operations": ["data_governance", "privacy_notices", "opt_out_processing",
                       "data_sharing", "vendor_data_management"],
    },
    RegulatoryDomain.FRAUD_PAYMENTS: {
        "business_lines": ["retail_banking", "commercial_banking", "payments"],
        "products": ["debit_cards", "credit_cards", "wire_transfers", "ACH",
                     "Zelle", "FedNow", "RTP"],
        "operations": ["fraud_detection", "dispute_resolution", "Reg_E_compliance",
                       "Nacha_compliance", "network_compliance"],
    },
    RegulatoryDomain.FAIR_LENDING: {
        "business_lines": ["retail_banking", "mortgage", "commercial_banking", "credit_cards"],
        "products": ["mortgage_loans", "HELOC", "personal_loans", "credit_cards",
                     "small_business_loans"],
        "operations": ["underwriting", "pricing", "marketing", "HMDA_reporting",
                       "CRA_compliance", "fair_lending_testing"],
    },
}


def scope_determination_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Determine which business lines, products, and operations are in scope.

    Uses rule-based matching on regulatory_domain + change_type.
    This is deterministic Python — not LLM judgment.

    A narrow scope (fewer business lines, low product coverage) reduces
    the scope_breadth_score component of the impact score.
    """
    domain = state.get("regulatory_domain", RegulatoryDomain.OTHER)
    try:
        domain_enum = RegulatoryDomain(domain)
    except ValueError:
        domain_enum = RegulatoryDomain.OTHER

    scope = DOMAIN_SCOPE_MAP.get(domain_enum, {
        "business_lines": ["retail_banking"],
        "products": [],
        "operations": []
    })

    rationale = (
        f"Scope determined based on regulatory domain '{domain_enum.value}'. "
        f"{len(scope.get('business_lines', []))} business lines, "
        f"{len(scope.get('products', []))} product categories, "
        f"{len(scope.get('operations', []))} operational areas identified as potentially in scope. "
        "Institution-specific exclusions (products not offered) applied in production via institution_profile config."
    )

    return {
        "affected_business_lines": scope.get("business_lines", []),
        "affected_products": scope.get("products", []),
        "affected_operations": scope.get("operations", []),
        "scope_determination_rationale": rationale,
        "current_step": "scope_determination_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["scope_determination_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Scope determined: {len(scope.get('business_lines', []))} business lines, "
                   f"{len(scope.get('products', []))} product categories in scope.",
            node="scope_determination_node",
            data_sources=["domain_scope_matrix", "institution_product_registry"],
            regulatory_basis="FFIEC Regulatory Change Management — scope analysis",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4: Policy Mapping
# ══════════════════════════════════════════════════════════════════════════════

def policy_mapping_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Map the regulatory change to the institution's policy registry.

    Identifies which written policies, standard operating procedures,
    and risk controls may need to be updated or created.

    In production: performs full-text search against the institution's
    policy management system (MetricStream, Archer, SharePoint).
    In dev mode: uses fixture-based registry with domain matching.
    """
    domain = state.get("regulatory_domain", RegulatoryDomain.OTHER)
    try:
        domain_enum = RegulatoryDomain(domain)
    except ValueError:
        domain_enum = RegulatoryDomain.OTHER

    policy_registry = _load_policy_registry()

    # Find policies matching this regulatory domain
    matched_policies = []
    for policy in policy_registry:
        policy_domain = policy.get("domain", "")
        if policy_domain == domain_enum.value:
            matched_policies.append({
                "policy_id": policy.get("policy_id"),
                "policy_name": policy.get("name"),
                "policy_owner": policy.get("owner"),
                "last_review_date": policy.get("last_review_date", "Unknown"),
                "current_version": policy.get("version", "1.0"),
                "relevance_reason": f"Policy domain '{policy_domain}' matches regulatory change domain.",
                "change_required": None,  # Populated by gap analysis
            })

    # Also map cross-domain policies (e.g., model risk policy applies to BSA)
    cross_domain_policies = {
        RegulatoryDomain.BSA_AML: ["POL-008"],  # Model risk → TMS models
        RegulatoryDomain.INVESTMENT_PRODUCTS: ["POL-008"],  # Model risk → suitability
        RegulatoryDomain.FRAUD_PAYMENTS: ["POL-008"],  # Model risk → fraud models
    }

    cross_policy_ids = cross_domain_policies.get(domain_enum, [])
    for policy in policy_registry:
        if policy.get("policy_id") in cross_policy_ids:
            matched_policies.append({
                "policy_id": policy.get("policy_id"),
                "policy_name": policy.get("name"),
                "policy_owner": policy.get("owner"),
                "last_review_date": policy.get("last_review_date", "Unknown"),
                "current_version": policy.get("version", "1.0"),
                "relevance_reason": "Cross-domain dependency: model risk/validation requirements may apply.",
                "change_required": None,
            })

    rationale = (
        f"Policy mapping: {len(matched_policies)} policies identified in domain '{domain_enum.value}'. "
        f"Gap analysis will confirm which policies require amendment."
    )

    return {
        "mapped_policies": matched_policies,
        "mapped_procedures": [],  # Populated from procedure registry in production
        "mapped_controls": [],    # Populated from control library in production
        "policy_mapping_rationale": rationale,
        "current_step": "policy_mapping_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["policy_mapping_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Policy mapping complete: {len(matched_policies)} policies mapped. "
                   f"Gap analysis will determine specific change requirements.",
            node="policy_mapping_node",
            data_sources=["policy_registry", "procedure_registry", "control_library"],
            regulatory_basis="FFIEC Regulatory Change Management — policy review requirement",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5: Gap Analysis (LLM)
# ══════════════════════════════════════════════════════════════════════════════

def gap_analysis_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    LLM-driven gap analysis comparing regulatory requirements to current policy.

    This is the core analytical node — where the agent earns its value.
    The LLM reviews the regulatory text and the institution's current policies
    to identify specific gaps, contradictions, and required changes.

    LLM ROLE: Analysis and narrative only.
    LLM does NOT route, score, or make compliance decisions.
    """
    llm = _get_llm()

    # Build policy summary for context
    policies = state.get("mapped_policies", [])
    policy_names = [p.get("policy_name", "") for p in policies]
    current_policies_summary = (
        f"Current policies in scope: {', '.join(policy_names)}. "
        f"These policies were last reviewed and are in the institution's current policy register."
        if policy_names
        else "No specific policies currently mapped to this regulatory domain."
    )

    # Truncate full text if too large for context window
    full_text = state.get("full_text", "")
    regulatory_text = full_text[:40000] if len(full_text) > 40000 else full_text
    if not regulatory_text:
        regulatory_text = state.get("summary_text", "No full text available — analysis based on summary.")

    user_message = GAP_ANALYSIS_USER_PROMPT.format(
        change_title=state.get("change_title", "Unknown"),
        regulatory_authority=state.get("regulatory_authority", "Unknown"),
        change_type=state.get("change_type", "Unknown"),
        citation=state.get("citation", "N/A"),
        publication_date=state.get("publication_date", "Unknown"),
        effective_date=state.get("effective_date", "TBD"),
        regulatory_domain=state.get("regulatory_domain", "Unknown"),
        regulatory_text=regulatory_text,
        current_policies_summary=current_policies_summary,
        institution_type=os.getenv("INSTITUTION_TYPE", "Commercial Bank"),
        institution_charter=os.getenv("INSTITUTION_CHARTER", "State-chartered, Federal Reserve member"),
        primary_regulator=os.getenv("PRIMARY_REGULATOR", "Federal Reserve / State Banking Department"),
        products_summary=", ".join(state.get("affected_products", [])[:10]),
        business_lines=", ".join(state.get("affected_business_lines", [])),
    )

    logger.info(f"Running gap analysis for {state.get('change_id')} using LLM...")

    response = llm.invoke([
        SystemMessage(content=GAP_ANALYSIS_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])

    gap_narrative = response.content

    # Extract structured summary (first section of the LLM response)
    lines = gap_narrative.split("\n")
    summary_lines = []
    in_summary = False
    for line in lines:
        if "EXECUTIVE SUMMARY" in line.upper():
            in_summary = True
            continue
        elif in_summary and (line.startswith("#") or line.startswith("2.") or "KEY REQUIREMENTS" in line.upper()):
            break
        elif in_summary and line.strip():
            summary_lines.append(line.strip())

    gap_summary = " ".join(summary_lines[:5]) if summary_lines else gap_narrative[:500]

    # Determine applicability from the narrative
    is_applicable = "not applicable" not in gap_narrative.lower()[:200]

    return {
        "gap_analysis_narrative": gap_narrative,
        "gap_analysis_summary": gap_summary,
        "identified_gaps": [],  # In production: parse structured gaps from LLM JSON output
        "is_applicable": is_applicable,
        "applicability_rationale": (
            "Gap analysis determined change is applicable based on regulatory domain and institution profile."
            if is_applicable
            else "Gap analysis determined change is NOT applicable to this institution. See narrative for details."
        ),
        "current_step": "gap_analysis_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["gap_analysis_node"],
        "audit_trail": _add_audit_entry(
            state,
            action="LLM gap analysis complete. Regulatory text analyzed against current policy register. "
                   f"Applicable: {is_applicable}.",
            node="gap_analysis_node",
            used_llm=True,
            data_sources=["regulatory_text", "policy_registry", "institution_profile"],
            regulatory_basis="SR 11-7 — LLM used for analysis only; routing decisions are Python-only",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6: Impact Scoring (Python — no LLM)
# ══════════════════════════════════════════════════════════════════════════════

# Authority tier → score mapping
AUTHORITY_TIER_SCORES = {
    "TIER_1_FEDERAL_PRIMARY": 1.0,    # OCC, FDIC, Fed, NCUA, CFPB
    "TIER_2_FEDERAL_SECONDARY": 0.75,  # FinCEN, SEC, FINRA, DOJ
    "TIER_3_STATE": 0.50,              # State banking regulators
    "TIER_4_INTERNATIONAL": 0.25,      # FATF, BIS (advisory)
    "UNRECOGNIZED": 0.10,
}

# Change type → urgency modifier
CHANGE_TYPE_URGENCY = {
    ChangeType.FINAL_RULE: 1.0,
    ChangeType.INTERIM_FINAL_RULE: 1.0,
    ChangeType.ENFORCEMENT_ACTION: 1.0,        # Highest — signals exam focus now
    ChangeType.EXAMINATION_PROCEDURE: 0.90,    # Examiners using this next cycle
    ChangeType.PROPOSED_RULE: 0.40,            # Not final; monitor only
    ChangeType.GUIDANCE: 0.70,                 # Examiners expect compliance
    ChangeType.ADVISORY: 0.65,
    ChangeType.BULLETIN: 0.60,
    ChangeType.CIRCULAR: 0.55,
    ChangeType.FAQ: 0.30,                      # Clarification only
}


def _compute_deadline_urgency_score(days_to_effective: Optional[int], change_type: str) -> float:
    """
    Score urgency based on days until effective date.

    Score is higher for shorter implementation windows.
    PROPOSED_RULE has no effective date — score based on type urgency only.
    """
    if days_to_effective is None:
        return 0.40  # No deadline known — moderate default

    if days_to_effective <= 0:
        return 1.0   # Already effective — immediate action
    elif days_to_effective <= 30:
        return 0.95  # < 30 days: critical urgency
    elif days_to_effective <= 60:
        return 0.85
    elif days_to_effective <= 90:
        return 0.70
    elif days_to_effective <= 180:
        return 0.55
    elif days_to_effective <= 365:
        return 0.40
    else:
        return 0.20  # > 1 year: low urgency


def impact_scoring_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Compute composite impact score (Python-only — no LLM).

    Composite weight allocation:
    - Authority tier:         25% — regulator primacy
    - Deadline urgency:       25% — implementation window
    - Scope breadth:          20% — business lines / products affected
    - Policy depth:           15% — extent of policy changes required
    - Remediation complexity: 15% — estimated implementation effort

    SR 11-7: scoring weights are documented and justified.
    BSA Officer can adjust tier thresholds (not weights) via configuration.
    """
    # ── Component 1: Authority Tier Score (25%) ────────────────────────────
    source_tier = state.get("source_tier", "UNRECOGNIZED")
    authority_tier_score = AUTHORITY_TIER_SCORES.get(source_tier, 0.10)

    # ── Component 2: Deadline Urgency Score (25%) ───────────────────────────
    days_to_effective = state.get("days_to_effective")
    change_type_str = state.get("change_type", ChangeType.GUIDANCE)
    try:
        change_type_enum = ChangeType(change_type_str)
    except ValueError:
        change_type_enum = ChangeType.GUIDANCE

    type_urgency = CHANGE_TYPE_URGENCY.get(change_type_enum, 0.50)
    deadline_urgency_score = _compute_deadline_urgency_score(days_to_effective, change_type_str)
    # Blend deadline + type urgency (70/30)
    blended_urgency = (deadline_urgency_score * 0.70) + (type_urgency * 0.30)

    # ── Component 3: Scope Breadth Score (20%) ─────────────────────────────
    business_lines = state.get("affected_business_lines", [])
    products = state.get("affected_products", [])
    # More business lines + products = higher scope score
    biz_score = min(len(business_lines) / 6.0, 1.0)    # 6+ lines = max
    prod_score = min(len(products) / 8.0, 1.0)          # 8+ products = max
    scope_breadth_score = (biz_score * 0.60) + (prod_score * 0.40)

    # ── Component 4: Policy Depth Score (15%) ──────────────────────────────
    mapped_policies = state.get("mapped_policies", [])
    gap_narrative = state.get("gap_analysis_narrative", "")
    # Heuristic: more policies + gap keywords → higher policy depth
    policy_count_score = min(len(mapped_policies) / 4.0, 1.0)
    gap_severity_keywords = ["must", "required", "prohibited", "shall", "immediately",
                              "new requirement", "contradiction", "CRITICAL", "HIGH"]
    keyword_hits = sum(1 for kw in gap_severity_keywords if kw.lower() in gap_narrative.lower())
    keyword_score = min(keyword_hits / 5.0, 1.0)
    policy_depth_score = (policy_count_score * 0.40) + (keyword_score * 0.60)

    # ── Component 5: Remediation Complexity Score (15%) ───────────────────
    ops_count = len(state.get("affected_operations", []))
    complexity_score = min(ops_count / 6.0, 1.0)   # 6+ ops = max complexity

    # ── Binding-nature moderation ───────────────────────────────────────────
    # Policy depth and remediation complexity above are derived from the
    # DOMAIN's footprint (policy count, operational areas) — they say nothing
    # about whether THIS change actually imposes obligations. A non-binding
    # clarification (FAQ: "clarification only", modifier 0.30) cannot impose
    # MAJOR remediation across the domain; a FINAL_RULE (1.0) can. Scale both
    # components by the change-type modifier so an FAQ in a broad domain like
    # BSA/AML does not score like a final rule.
    type_binding_modifier = CHANGE_TYPE_URGENCY.get(change_type_enum, 0.60)
    policy_depth_score = policy_depth_score * type_binding_modifier
    complexity_score = complexity_score * type_binding_modifier

    # ── Composite Score ─────────────────────────────────────────────────────
    composite_score = (
        authority_tier_score * 0.25
        + blended_urgency * 0.25
        + scope_breadth_score * 0.20
        + policy_depth_score * 0.15
        + complexity_score * 0.15
    )

    # Round to 4 decimal places
    composite_score = round(composite_score, 4)

    # ── Impact Tier Determination ───────────────────────────────────────────
    if composite_score >= 0.85:
        impact_tier = ImpactTier.CRITICAL
    elif composite_score >= 0.65:
        impact_tier = ImpactTier.HIGH
    elif composite_score >= 0.40:
        impact_tier = ImpactTier.MEDIUM
    else:
        impact_tier = ImpactTier.LOW

    # Hard override: ENFORCEMENT_ACTION is always at least HIGH.
    # The floor applies to ANY tier below HIGH — checking only LOW would let
    # a MEDIUM-scored enforcement action bypass the elevation (enforcement
    # actions signal active examiner focus and always warrant HIGH treatment).
    if change_type_enum == ChangeType.ENFORCEMENT_ACTION and impact_tier in (
        ImpactTier.LOW,
        ImpactTier.MEDIUM,
    ):
        impact_tier = ImpactTier.HIGH
        composite_score = max(composite_score, 0.65)

    # Hard override: already-effective rule → CRITICAL floor for TIER_1
    if (days_to_effective is not None and days_to_effective <= 0
            and source_tier == "TIER_1_FEDERAL_PRIMARY"):
        impact_tier = ImpactTier.CRITICAL
        composite_score = max(composite_score, 0.85)

    # ── Implementation Complexity Classification ────────────────────────────
    if complexity_score >= 0.70:
        impl_complexity = "MAJOR"
    elif complexity_score >= 0.40:
        impl_complexity = "MODERATE"
    else:
        impl_complexity = "MINOR"

    # ── Compliance Window Assessment ────────────────────────────────────────
    compliance_window_adequate = True
    if days_to_effective is not None:
        if impl_complexity == "MAJOR" and days_to_effective < 180:
            compliance_window_adequate = False
        elif impl_complexity == "MODERATE" and days_to_effective < 90:
            compliance_window_adequate = False
        elif impl_complexity == "MINOR" and days_to_effective < 30:
            compliance_window_adequate = False

    score_components = {
        "authority_tier_score": round(authority_tier_score, 4),
        "deadline_urgency_score": round(blended_urgency, 4),
        "scope_breadth_score": round(scope_breadth_score, 4),
        "policy_depth_score": round(policy_depth_score, 4),
        "remediation_complexity_score": round(complexity_score, 4),
    }

    logger.info(
        f"Impact scoring: {state.get('change_id')} → score={composite_score}, tier={impact_tier.value}"
    )

    return {
        "impact_score": composite_score,
        "impact_tier": impact_tier,
        "impact_score_components": score_components,
        "implementation_complexity": impl_complexity,
        "compliance_window_adequate": compliance_window_adequate,
        "current_step": "impact_scoring_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["impact_scoring_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Impact scoring complete. Composite score: {composite_score:.4f}. "
                   f"Tier: {impact_tier.value}. Complexity: {impl_complexity}. "
                   f"Compliance window adequate: {compliance_window_adequate}. "
                   f"Components: {json.dumps(score_components)}",
            node="impact_scoring_node",
            regulatory_basis="SR 11-7 — model scoring methodology documented and deterministic",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 7: Routing Decision (Python — no LLM)
# ══════════════════════════════════════════════════════════════════════════════

def routing_decision_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Assign compliance owners and determine whether HITL is required.

    Routing is deterministic Python — not LLM output.

    CRITICAL:  Primary + secondary owners. Mandatory HITL. CCO CC'd.
    HIGH:      Primary + secondary owners. Mandatory HITL.
    MEDIUM:    Primary owner only. HITL optional (defaulting to required for safety).
    LOW:       Primary owner awareness notification. No HITL required.

    Hard rules:
    - ENFORCEMENT_ACTION → always HITL required (already set in source_validation_node)
    - Compliance window inadequate → escalate to next tier
    """
    domain_str = state.get("regulatory_domain", RegulatoryDomain.OTHER)
    try:
        domain_enum = RegulatoryDomain(domain_str)
    except ValueError:
        domain_enum = RegulatoryDomain.OTHER

    routing_matrix = _load_routing_matrix()
    routing_config = routing_matrix.get(domain_enum.value, routing_matrix.get("OTHER", {}))

    primary_owner = routing_config.get("primary", "CHIEF_COMPLIANCE_OFFICER")
    secondary_owners = routing_config.get("secondary", [])

    impact_tier_str = state.get("impact_tier", ImpactTier.MEDIUM)
    try:
        impact_tier = ImpactTier(impact_tier_str)
    except ValueError:
        impact_tier = ImpactTier.MEDIUM

    # Compliance window escalation
    if not state.get("compliance_window_adequate", True):
        if impact_tier == ImpactTier.MEDIUM:
            impact_tier = ImpactTier.HIGH
        elif impact_tier == ImpactTier.LOW:
            impact_tier = ImpactTier.MEDIUM

    # Determine HITL requirement
    human_review_required = (
        impact_tier in (ImpactTier.CRITICAL, ImpactTier.HIGH)
        or state.get("human_review_required", False)  # Already set for enforcement actions
    )

    # Business unit owners for stakeholder notifications
    domain_bus_units = {
        RegulatoryDomain.BSA_AML: ["HEAD_OF_OPERATIONS", "HEAD_OF_RETAIL_BANKING",
                                    "HEAD_OF_COMMERCIAL_BANKING", "HEAD_OF_INTERNATIONAL"],
        RegulatoryDomain.CONSUMER_COMPLIANCE: ["HEAD_OF_RETAIL_BANKING", "HEAD_OF_MORTGAGE",
                                                "HEAD_OF_CREDIT_CARDS"],
        RegulatoryDomain.INVESTMENT_PRODUCTS: ["HEAD_OF_WEALTH_MANAGEMENT", "HEAD_OF_TRUST"],
        RegulatoryDomain.FRAUD_PAYMENTS: ["HEAD_OF_OPERATIONS", "HEAD_OF_RETAIL_BANKING"],
        RegulatoryDomain.TECHNOLOGY_OPERATIONS: ["CTO", "HEAD_OF_OPERATIONS"],
        RegulatoryDomain.PRIVACY_DATA: ["CTO", "HEAD_OF_OPERATIONS", "HEAD_OF_MARKETING"],
    }
    business_unit_owners = domain_bus_units.get(domain_enum, ["HEAD_OF_OPERATIONS"])

    rationale = (
        f"Domain '{domain_enum.value}' routes to primary owner: {primary_owner}. "
        f"Impact tier: {impact_tier.value}. "
        f"Human review: {'REQUIRED' if human_review_required else 'NOT REQUIRED'}. "
        f"{'Compliance window inadequate — tier escalated.' if not state.get('compliance_window_adequate', True) else ''}"
    )

    return {
        "primary_compliance_owner": primary_owner,
        "secondary_compliance_owners": secondary_owners,
        "business_unit_owners": business_unit_owners,
        "human_review_required": human_review_required,
        "impact_tier": impact_tier,  # May have been escalated
        "routing_rationale": rationale,
        "case_status": CaseStatus.PENDING_HUMAN_REVIEW if human_review_required else CaseStatus.PENDING_REMEDIATION,
        "current_step": "routing_decision_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["routing_decision_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Routing decision: primary_owner={primary_owner}, "
                   f"impact={impact_tier.value}, HITL={'required' if human_review_required else 'not required'}. "
                   f"{rationale}",
            node="routing_decision_node",
            regulatory_basis="Internal routing matrix — compliance program ownership structure",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 8: Human Review Gate (HITL interrupt)
# ══════════════════════════════════════════════════════════════════════════════

def human_review_gate(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Human-in-the-loop gate for Compliance Officer review.

    This node executes AFTER the LangGraph interrupt is satisfied.
    The Streamlit UI collects the officer's decision via graph.update_state(),
    then the graph resumes here with the decision injected into state.

    The Compliance Officer can:
    - APPROVED: Accept the gap analysis and proceed to remediation planning
    - MODIFIED: Accept with changes (noted in compliance_officer_notes)
    - NOT_APPLICABLE: Mark the change as not applicable to this institution
    - ESCALATED: Route to senior management or legal counsel

    The AI's analysis is advisory. The human decides.
    """
    decision = state.get("compliance_officer_decision", "APPROVED")
    officer_id = state.get("compliance_officer_id", "PENDING")
    notes = state.get("compliance_officer_notes", "")

    logger.info(
        f"Human review gate: change={state.get('change_id')}, "
        f"officer={officer_id}, decision={decision}"
    )

    new_status = CaseStatus.PENDING_REMEDIATION
    if decision == "NOT_APPLICABLE":
        new_status = CaseStatus.CLOSED_NOT_APPLICABLE
    elif decision == "ESCALATED":
        new_status = CaseStatus.ESCALATED

    return {
        "human_review_completed_at": datetime.utcnow().isoformat() + "Z",
        "case_status": new_status,
        "current_step": "human_review_gate",
        "completed_steps": list(state.get("completed_steps", [])) + ["human_review_gate"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Human review completed. Officer: {officer_id}. "
                   f"Decision: {decision}. "
                   f"Notes: {notes or 'None'}.",
            node="human_review_gate",
            regulatory_basis="SR 11-7 — human oversight required for compliance-consequential AI output",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 9: Remediation Planning (LLM)
# ══════════════════════════════════════════════════════════════════════════════

def remediation_planning_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    LLM-drafted remediation plan with specific action items and timeline.

    Produces:
    - Full narrative remediation plan
    - Structured task list (task_id, owner, due_date, priority, dependencies)
    - Critical path identification
    - Estimated effort hours

    The plan is reviewed by the Compliance Officer (who already approved
    the gap analysis in the human_review_gate). For LOW/MEDIUM changes,
    this node executes without a second HITL stop.
    """
    llm = _get_llm()

    # Set remediation deadline
    effective_date = state.get("effective_date")
    remediation_deadline = (
        (datetime.strptime(effective_date, "%Y-%m-%d") - timedelta(days=14)).date().isoformat()
        if effective_date
        else (datetime.utcnow() + timedelta(days=90)).date().isoformat()
    )

    user_message = REMEDIATION_PLANNING_USER_PROMPT.format(
        change_title=state.get("change_title", "Unknown"),
        regulatory_authority=state.get("regulatory_authority", "Unknown"),
        effective_date=state.get("effective_date", "TBD"),
        impact_tier=state.get("impact_tier", "MEDIUM"),
        remediation_deadline=remediation_deadline,
        gap_analysis_summary=state.get("gap_analysis_summary", "See full gap analysis narrative."),
        identified_gaps_json=json.dumps(state.get("identified_gaps", []), indent=2),
        primary_compliance_owner=state.get("primary_compliance_owner", "CHIEF_COMPLIANCE_OFFICER"),
        business_unit_owners=", ".join(state.get("business_unit_owners", [])),
        implementation_complexity=state.get("implementation_complexity", "MODERATE"),
        today_date=datetime.utcnow().date().isoformat(),
    )

    logger.info(f"Generating remediation plan for {state.get('change_id')} using LLM...")

    response = llm.invoke([
        SystemMessage(content=REMEDIATION_PLANNING_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])

    plan_narrative = response.content

    # Parse task list from narrative (simplified — in production use structured LLM output)
    # Generate a default set of tasks based on implementation complexity
    complexity = state.get("implementation_complexity", "MODERATE")
    base_tasks = _generate_default_tasks(state, remediation_deadline, complexity)

    # Effort estimate
    effort_by_complexity = {"MAJOR": 320, "MODERATE": 120, "MINOR": 40}
    estimated_effort = effort_by_complexity.get(complexity, 80)

    return {
        "remediation_plan_narrative": plan_narrative,
        "remediation_tasks": base_tasks,
        "remediation_deadline": remediation_deadline,
        "estimated_effort_hours": estimated_effort,
        "current_step": "remediation_planning_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["remediation_planning_node"],
        "case_status": CaseStatus.REMEDIATION_IN_PROGRESS,
        "audit_trail": _add_audit_entry(
            state,
            action=f"Remediation plan generated. Deadline: {remediation_deadline}. "
                   f"Tasks: {len(base_tasks)}. Estimated effort: {estimated_effort} hours.",
            node="remediation_planning_node",
            used_llm=True,
            data_sources=["gap_analysis", "policy_registry", "routing_matrix"],
            regulatory_basis="FFIEC Regulatory Change Management — remediation planning requirement",
        ),
    }


def _generate_default_tasks(
    state: ChangeManagementState,
    remediation_deadline: str,
    complexity: str,
) -> List[Dict]:
    """Generate default task structure based on complexity tier."""
    today = datetime.utcnow().date()
    deadline = datetime.strptime(remediation_deadline, "%Y-%m-%d").date()
    total_days = (deadline - today).days

    def offset_date(fraction: float) -> str:
        return (today + timedelta(days=int(total_days * fraction))).isoformat()

    owner = state.get("primary_compliance_owner", "CHIEF_COMPLIANCE_OFFICER")

    base_tasks = [
        {
            "task_id": "TASK-001",
            "task_description": "Complete detailed gap analysis review and distribute to affected business units",
            "task_owner": owner,
            "due_date": offset_date(0.10),
            "priority": "HIGH",
            "dependencies": [],
            "status": "OPEN",
            "linked_gap_id": "GAP-001",
        },
        {
            "task_id": "TASK-002",
            "task_description": "Update applicable policies to reflect new regulatory requirements",
            "task_owner": owner,
            "due_date": offset_date(0.40),
            "priority": "HIGH",
            "dependencies": ["TASK-001"],
            "status": "OPEN",
            "linked_gap_id": "GAP-001",
        },
        {
            "task_id": "TASK-003",
            "task_description": "Update standard operating procedures and job aids for affected processes",
            "task_owner": "HEAD_OF_OPERATIONS",
            "due_date": offset_date(0.55),
            "priority": "HIGH",
            "dependencies": ["TASK-002"],
            "status": "OPEN",
            "linked_gap_id": "GAP-002",
        },
        {
            "task_id": "TASK-004",
            "task_description": "Deliver compliance training to affected staff",
            "task_owner": "TRAINING_OFFICER",
            "due_date": offset_date(0.75),
            "priority": "MEDIUM",
            "dependencies": ["TASK-002", "TASK-003"],
            "status": "OPEN",
            "linked_gap_id": None,
        },
        {
            "task_id": "TASK-005",
            "task_description": "Conduct pre-effective date testing/validation of updated controls",
            "task_owner": owner,
            "due_date": offset_date(0.90),
            "priority": "HIGH",
            "dependencies": ["TASK-003", "TASK-004"],
            "status": "OPEN",
            "linked_gap_id": None,
        },
    ]

    if complexity == "MAJOR":
        base_tasks.extend([
            {
                "task_id": "TASK-006",
                "task_description": "Engage technology team for system configuration or new control implementation",
                "task_owner": "CTO",
                "due_date": offset_date(0.50),
                "priority": "HIGH",
                "dependencies": ["TASK-001"],
                "status": "OPEN",
                "linked_gap_id": "GAP-003",
            },
            {
                "task_id": "TASK-007",
                "task_description": "Board or Risk Committee notification and approval of updated policies",
                "task_owner": "CHIEF_COMPLIANCE_OFFICER",
                "due_date": offset_date(0.65),
                "priority": "HIGH",
                "dependencies": ["TASK-002"],
                "status": "OPEN",
                "linked_gap_id": None,
            },
        ])

    return base_tasks


# ══════════════════════════════════════════════════════════════════════════════
# NODE 10: Stakeholder Notification
# ══════════════════════════════════════════════════════════════════════════════

def stakeholder_notification_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Draft and (in production) send notifications to all stakeholders.

    Each stakeholder receives a tailored message:
    - Compliance owners: full context + gap summary + action required
    - Business unit owners: what this means for their operations, what they need to do
    - Senior management: executive summary if CRITICAL or HIGH
    - Board Risk Committee: summary if CRITICAL

    LLM drafts each notification with appropriate role-specific framing.
    """
    llm = _get_llm()
    impact_tier = state.get("impact_tier", ImpactTier.MEDIUM)

    # Determine who receives notifications based on impact tier
    recipients = []

    # Primary compliance owner — always
    recipients.append({
        "recipient_role": state.get("primary_compliance_owner", "CHIEF_COMPLIANCE_OFFICER"),
        "notification_type": "ACTION_REQUIRED",
        "recipient_context": "Lead compliance officer responsible for implementing this change",
    })

    # Business unit owners — always
    for bu_owner in state.get("business_unit_owners", []):
        recipients.append({
            "recipient_role": bu_owner,
            "notification_type": "ACTION_REQUIRED",
            "recipient_context": f"Business unit head with operational responsibility for affected products",
        })

    # Senior management for HIGH and CRITICAL
    try:
        tier = ImpactTier(impact_tier)
    except ValueError:
        tier = ImpactTier.MEDIUM

    if tier in (ImpactTier.CRITICAL, ImpactTier.HIGH):
        recipients.append({
            "recipient_role": "CHIEF_EXECUTIVE_OFFICER",
            "notification_type": "AWARENESS",
            "recipient_context": "CEO awareness notification for significant regulatory change",
        })

    # Board for CRITICAL only
    if tier == ImpactTier.CRITICAL:
        recipients.append({
            "recipient_role": "BOARD_RISK_COMMITTEE",
            "notification_type": "AWARENESS",
            "recipient_context": "Board-level notification for critical regulatory change",
        })

    # Draft notifications via LLM — ONE draft per notification_type, not one
    # LLM call per recipient. Recipient-specific addressing is Python string
    # work; the narrative body is identical within a type. This bounds LLM
    # cost/latency to the number of types (2-3) instead of the recipient
    # count (6+ for broad domains like BSA/AML).
    notifications = []
    drafts_by_type: Dict[str, str] = {}
    for recipient in recipients:
        ntype = recipient["notification_type"]
        if ntype not in drafts_by_type:
            user_message = STAKEHOLDER_NOTIFICATION_USER_PROMPT.format(
                change_title=state.get("change_title", "Unknown"),
                regulatory_authority=state.get("regulatory_authority", "Unknown"),
                impact_tier=state.get("impact_tier", "MEDIUM"),
                effective_date=state.get("effective_date", "TBD"),
                remediation_deadline=state.get("remediation_deadline", "TBD"),
                gap_analysis_summary=state.get("gap_analysis_summary", "See full analysis."),
                recipient_role=recipient["recipient_role"],
                recipient_context=recipient["recipient_context"],
                notification_type=ntype,
            )

            response = llm.invoke([
                SystemMessage(content=STAKEHOLDER_NOTIFICATION_SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ])
            drafts_by_type[ntype] = response.content

        notifications.append({
            "recipient_role": recipient["recipient_role"],
            "notification_type": ntype,
            "draft_message": drafts_by_type[ntype],
            "sent_at": None,  # Set when actually sent in production
        })

    # Comment letter recommendation for significant proposed rules
    comment_recommended = (
        state.get("change_type") == ChangeType.PROPOSED_RULE
        and tier in (ImpactTier.CRITICAL, ImpactTier.HIGH)
    )

    return {
        "stakeholder_notifications": notifications,
        "comment_letter_recommended": comment_recommended,
        "current_step": "stakeholder_notification_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["stakeholder_notification_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Stakeholder notifications drafted for {len(notifications)} recipients. "
                   f"Comment letter {'recommended' if comment_recommended else 'not recommended'}.",
            node="stakeholder_notification_node",
            used_llm=True,
            regulatory_basis="FFIEC — compliance program communication requirements",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 11: Tracking Update
# ══════════════════════════════════════════════════════════════════════════════

def tracking_update_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Write the final record to the regulatory change management register.

    The register is the institution's authoritative record of:
    - All regulatory changes identified
    - Impact assessments and gap analyses
    - Remediation plans and task status
    - Completion records for examination evidence

    In production: writes to DynamoDB (append-only) + updates
    the regulatory change tracker in the GRC system.
    """
    register_entry = {
        "change_id": state.get("change_id"),
        "change_title": state.get("change_title"),
        "regulatory_authority": state.get("regulatory_authority"),
        "change_type": state.get("change_type"),
        "domain": state.get("regulatory_domain"),
        "citation": state.get("citation"),
        "publication_date": state.get("publication_date"),
        "effective_date": state.get("effective_date"),
        "impact_tier": state.get("impact_tier"),
        "impact_score": state.get("impact_score"),
        "primary_compliance_owner": state.get("primary_compliance_owner"),
        "is_applicable": state.get("is_applicable"),
        "remediation_deadline": state.get("remediation_deadline"),
        "task_count": len(state.get("remediation_tasks", [])),
        "estimated_effort_hours": state.get("estimated_effort_hours"),
        "case_status": state.get("case_status", CaseStatus.REMEDIATION_IN_PROGRESS),
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "human_review_completed": state.get("compliance_officer_decision") is not None,
        "compliance_officer_id": state.get("compliance_officer_id"),
    }

    return {
        "change_register_entry": register_entry,
        "current_step": "tracking_update_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["tracking_update_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=f"Regulatory change register updated. "
                   f"Impact: {state.get('impact_tier')}. "
                   f"Tasks: {len(state.get('remediation_tasks', []))}. "
                   f"Deadline: {state.get('remediation_deadline')}.",
            node="tracking_update_node",
            data_sources=["change_register", "grc_system"],
            regulatory_basis="FFIEC — regulatory change management documentation requirement",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 12: Finalize
# ══════════════════════════════════════════════════════════════════════════════

def finalize_node(state: ChangeManagementState) -> Dict[str, Any]:
    """
    Complete the workflow: lock audit trail, set final status.

    For NOT_APPLICABLE decisions: status = CLOSED_NOT_APPLICABLE
    For completed analysis + remediation plan: status = REMEDIATION_IN_PROGRESS
    (The case remains open until all remediation tasks are marked COMPLETE.)
    """
    co_decision = state.get("compliance_officer_decision")
    final_status = state.get("case_status", CaseStatus.REMEDIATION_IN_PROGRESS)

    if co_decision == "NOT_APPLICABLE":
        final_status = CaseStatus.CLOSED_NOT_APPLICABLE

    summary = (
        f"Regulatory change workflow complete. "
        f"Change: '{state.get('change_title')}'. "
        f"Impact: {state.get('impact_tier')}. "
        f"Applicable: {state.get('is_applicable')}. "
        f"Tasks generated: {len(state.get('remediation_tasks', []))}. "
        f"Status: {final_status.value}."
    )

    logger.info(f"Finalize: {state.get('change_id')} → {final_status.value}")

    return {
        "case_status": final_status,
        "current_step": "finalize_node",
        "completed_steps": list(state.get("completed_steps", [])) + ["finalize_node"],
        "audit_trail": _add_audit_entry(
            state,
            action=summary,
            node="finalize_node",
            regulatory_basis="FFIEC — regulatory change management completion record",
        ),
    }
