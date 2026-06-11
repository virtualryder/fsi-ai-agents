# agent/nodes.py
# ============================================================
# KYC/CDD Perpetual Review — Node Functions
#
# Each function is one node in the LangGraph DAG.
# Nodes receive the full KYCReviewState and return a dict of
# state updates — LangGraph merges these back into the state.
#
# Design principles:
#   - Deterministic gates: routing logic is Python, not LLM output
#   - LLM for drafting/narrative only — not for routing decisions
#   - Every significant action appended to audit_trail
#   - Hard-coded regulatory overrides: OFAC hits, PEP escalation
#   - Tool calls use simulated data in dev mode (no real API keys needed)
# ============================================================

import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any

from langchain_anthropic import ChatAnthropic
from agent.persistence import audit_sink
from langchain_core.messages import SystemMessage, HumanMessage

from agent.state import KYCReviewState, TriggerType, RiskTier, ReviewOutcome
from agent.prompts import (
    EDD_OUTREACH_PROMPT,
    RM_NOTIFICATION_PROMPT,
    RISK_NARRATIVE_PROMPT,
)
from tools.kyc_lookup import fetch_customer_record
from tools.document_checker import assess_document_gaps
from tools.watchlist_screener import screen_all_parties
from tools.adverse_media import search_adverse_media
from tools.risk_scorer import compute_risk_score
from tools.edd_engine import generate_edd_package
from tools.case_manager import create_case_record, update_kyc_record

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


logger = logging.getLogger(__name__)


def _get_llm():
    """Initialize the LLM client. Centralized for easy model swapping."""
    import os
    # ── Provider switch (Rec 4) ──────────────────────────────────────────────
    # LLM_PROVIDER=bedrock routes inference through ChatBedrockConverse via a
    # VPC interface endpoint — model calls stay inside the customer's AWS
    # account (the data-residency configuration). Optional Guardrails attach
    # when BEDROCK_GUARDRAIL_ID is set. Canonical implementation:
    # platform_core/fsi_agent_platform/llm_factory.py (this branch is vendored
    # so the agent stays independently deployable).
    if os.getenv("LLM_PROVIDER", "anthropic").strip().lower() == "bedrock":
        from langchain_aws import ChatBedrockConverse  # lazy optional dep
        _bedrock_kwargs = dict(
            model=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6-20260601-v1:0"),
            temperature=0.0,
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        )
        if os.getenv("BEDROCK_GUARDRAIL_ID"):
            _bedrock_kwargs["guardrail_config"] = {
                "guardrailIdentifier": os.environ["BEDROCK_GUARDRAIL_ID"],
                "guardrailVersion": os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT"),
            }
        return ChatBedrockConverse(**_bedrock_kwargs)
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL,
        temperature=0,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


def _add_audit_entry(
    state: KYCReviewState,
    action: str,
    node: str,
    data_sources: list = None,
    used_llm: bool = False,
    regulatory_basis: str = None,
    human_required: bool = False,
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
        "human_review_required": human_required,
        "review_id": state.get("review_id"),
        "customer_id": state.get("customer_id"),
    }
    trail.append(entry)
    # WRITE-AHEAD: durable audit record at creation time (see agent/persistence.py)
    audit_sink().record(entry)
    return trail


def _review_deadline(trigger_type: TriggerType) -> str:
    """
    Compute review completion deadline based on trigger urgency.

    Risk-based timelines per FFIEC BSA/AML Examination Manual guidance:
    - OFAC / Watchlist hit: 3 business days (immediate regulatory obligation)
    - SAR filed / Adverse media (critical): 7 days
    - Risk model flag / Transaction spike: 14 days
    - Event-driven (non-critical): 30 days
    - Scheduled periodic review: 60 days
    """
    today = datetime.utcnow()
    days_map = {
        TriggerType.WATCHLIST_HIT: 3,
        TriggerType.SAR_FILED: 7,
        TriggerType.ADVERSE_MEDIA: 7,
        TriggerType.RISK_MODEL_FLAG: 14,
        TriggerType.TRANSACTION_SPIKE: 14,
        TriggerType.BENEFICIAL_OWNER_CHANGE: 14,
        TriggerType.JURISDICTION_CHANGE: 30,
        TriggerType.NEW_PRODUCT: 30,
        TriggerType.MANUAL: 30,
        TriggerType.REGULATORY_EXAM: 7,
        TriggerType.SCHEDULED: 60,
    }
    days = days_map.get(trigger_type, 30)
    return (today + timedelta(days=days)).date().isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1: Trigger Evaluation
# ══════════════════════════════════════════════════════════════════════════════

def trigger_evaluation(state: KYCReviewState) -> Dict[str, Any]:
    """
    Parse the incoming review trigger and establish review parameters.

    Determines:
    - Trigger urgency level (drives review deadline)
    - Whether this is event-driven (higher urgency) or scheduled
    - Initial case status and review ID

    Regulatory basis: FFIEC BSA/AML Examination Manual — Risk-Based CDD
    recommends different response timelines based on trigger type and severity.
    """
    trigger_type = TriggerType(state.get("trigger_type", TriggerType.SCHEDULED))
    review_id = state.get("review_id") or f"KYC-REVIEW-{datetime.utcnow().strftime('%Y%m%d')}-{state.get('customer_id', 'UNKNOWN')[:8].upper()}"
    deadline = _review_deadline(trigger_type)

    logger.info(f"KYC Review {review_id}: trigger={trigger_type.value}, deadline={deadline}")

    updates = {
        "review_id": review_id,
        "trigger_type": trigger_type,
        "review_initiated_date": datetime.utcnow().date().isoformat(),
        "review_deadline": deadline,
        "case_status": "IN_PROGRESS",
        "current_step": "trigger_evaluation",
        "completed_steps": ["trigger_evaluation"],
        "errors": [],
        "audit_trail": _add_audit_entry(
            state,
            action=f"KYC review initiated. Trigger: {trigger_type.value}. "
                   f"Description: {state.get('trigger_description', 'N/A')}. "
                   f"Review deadline: {deadline}.",
            node="trigger_evaluation",
            data_sources=["review_trigger_system"],
            regulatory_basis="FFIEC BSA/AML Examination Manual — Risk-Based CDD",
        ),
    }
    return updates


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2: Customer Risk Profile
# ══════════════════════════════════════════════════════════════════════════════

def customer_risk_profile(state: KYCReviewState) -> Dict[str, Any]:
    """
    Load the current CDD record for the customer under review.

    Retrieves:
    - Current risk tier, EDD status, PEP flag
    - Beneficial ownership structure (FinCEN CDD Rule: ≥25% equity threshold)
    - Expected transaction profile
    - Existing document inventory with expiry dates
    - Account IDs, relationship manager, business type

    Regulatory basis:
    - FinCEN CDD Rule (31 CFR 1020.210): requires maintaining current,
      accurate CDD records on all covered financial institution customers
    - FATF R.10: ongoing due diligence on the business relationship
    """
    customer_id = state.get("customer_id")
    logger.info(f"Review {state.get('review_id')}: Loading customer record for {customer_id}")

    try:
        record = fetch_customer_record(customer_id)
    except Exception as e:
        logger.error(f"Failed to load customer record: {e}")
        errors = list(state.get("errors", []))
        errors.append({"step": "customer_risk_profile", "error": str(e), "recoverable": True})
        return {"errors": errors, "current_step": "customer_risk_profile"}

    completed = list(state.get("completed_steps", []))
    completed.append("customer_risk_profile")

    return {
        "customer_name": record.get("customer_name"),
        "customer_type": record.get("customer_type"),
        "account_ids": record.get("account_ids", []),
        "relationship_manager_id": record.get("relationship_manager_id"),
        "current_risk_tier": RiskTier(record.get("risk_tier", "MEDIUM")),
        "kyc_last_refreshed": record.get("kyc_last_refreshed"),
        "edd_status": record.get("edd_status", False),
        "pep_flag": record.get("pep_flag", False),
        "pep_category": record.get("pep_category"),
        "beneficial_owners": record.get("beneficial_owners", []),
        "business_type": record.get("business_type"),
        "expected_transaction_profile": record.get("expected_transaction_profile", {}),
        "jurisdiction_risk": record.get("jurisdiction_risk", "LOW"),
        "previous_risk_score": record.get("risk_score", 0.0),
        "current_step": "customer_risk_profile",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"Customer record loaded. Current risk tier: {record.get('risk_tier')}. "
                   f"EDD status: {record.get('edd_status')}. PEP: {record.get('pep_flag')}. "
                   f"KYC last refreshed: {record.get('kyc_last_refreshed')}. "
                   f"Beneficial owners: {len(record.get('beneficial_owners', []))}.",
            node="customer_risk_profile",
            data_sources=["core_banking_kyc_system", "cdd_record_store"],
            regulatory_basis="FinCEN CDD Rule 31 CFR 1020.210 — CDD record retrieval",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3: Document Collection Assessment
# ══════════════════════════════════════════════════════════════════════════════

def document_collection(state: KYCReviewState) -> Dict[str, Any]:
    """
    Identify required documents and assess gaps in the current CDD file.

    Builds the required document checklist for this customer type and risk tier,
    then compares against documents currently on file to identify:
    - Missing documents (never collected)
    - Expired documents (past their validity period)
    - Documents expiring soon (within 90 days)

    Regulatory basis:
    - FinCEN CDD Rule: requires maintaining current information on legal entity
      customers including beneficial ownership, business purpose, and activity
    - FFIEC: expects risk-based documentation refreshes with appropriate frequency
    - BSA CIP (31 CFR 1020.220): valid government-issued photo ID for individuals
    """
    customer_type = state.get("customer_type", "INDIVIDUAL")
    risk_tier = state.get("current_risk_tier", RiskTier.MEDIUM)
    customer_id = state.get("customer_id")

    logger.info(f"Review {state.get('review_id')}: Assessing document gaps for {customer_type} / {risk_tier.value}")

    gap_result = assess_document_gaps(
        customer_id=customer_id,
        customer_type=customer_type,
        risk_tier=risk_tier.value,
        pep_flag=state.get("pep_flag", False),
        edd_status=state.get("edd_status", False),
    )

    completed = list(state.get("completed_steps", []))
    completed.append("document_collection")

    missing = gap_result.get("missing_documents", [])
    expired = [d for d in gap_result.get("documents_on_file", []) if d.get("status") == "EXPIRED"]
    gap_narrative = (
        f"Document review identified {len(missing)} missing document(s) and "
        f"{len(expired)} expired document(s). "
        f"Missing: {', '.join(missing) if missing else 'None'}. "
        f"Expired: {', '.join([d['doc_type'] for d in expired]) if expired else 'None'}."
    )

    return {
        "required_documents": gap_result.get("required_documents", []),
        "documents_on_file": gap_result.get("documents_on_file", []),
        "missing_documents": missing,
        "cdd_completeness_score": gap_result.get("completeness_score", 100.0),
        "document_gap_narrative": gap_narrative,
        "current_step": "document_collection",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"Document assessment complete. Completeness score: {gap_result.get('completeness_score')}%. "
                   f"{gap_narrative}",
            node="document_collection",
            data_sources=["document_management_system", "kyc_document_vault"],
            regulatory_basis="FinCEN CDD Rule 31 CFR 1020.210 — Documentation requirements",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4: Watchlist Screening
# ══════════════════════════════════════════════════════════════════════════════

def watchlist_screening(state: KYCReviewState) -> Dict[str, Any]:
    """
    Screen customer, beneficial owners, and key counterparties against watchlists.

    Screened lists:
    - OFAC SDN (Office of Foreign Assets Control — Specially Designated Nationals)
    - OFAC Consolidated Sanctions List (multiple programs)
    - PEP lists (Refinitiv World-Check, LexisNexis Bridger, Dow Jones)
    - EU Consolidated Financial Sanctions List
    - UN Security Council Consolidated List
    - HM Treasury Financial Sanctions List (UK)
    - Internal bank watchlist

    Hard regulatory controls:
    - OFAC hit → ofac_hit=True → force escalation (overrides all other routing)
    - PEP hit → pep_watchlist_hit=True → mandatory EDD (FATF R.12)
    - All screening results retained for 5 years (BSA record retention)

    Regulatory basis: OFAC IEEPA, USA PATRIOT Act § 326, FinCEN CDD Rule,
    FATF R.10, FATF R.12 (PEP EDD requirements)
    """
    customer_id = state.get("customer_id")
    customer_name = state.get("customer_name")
    beneficial_owners = state.get("beneficial_owners", [])
    logger.info(f"Review {state.get('review_id')}: Screening {customer_name} + {len(beneficial_owners)} UBOs")

    screening_results = screen_all_parties(
        customer_id=customer_id,
        customer_name=customer_name,
        beneficial_owners=beneficial_owners,
        account_ids=state.get("account_ids", []),
    )

    ofac_hit = any(r.get("list_name", "").upper().startswith("OFAC") for r in screening_results)
    pep_hit = any(r.get("match_type", "").upper() == "PEP" for r in screening_results)

    # Hard regulatory control: OFAC hit requires immediate escalation
    # No analyst discretion — institutional obligation under IEEPA
    if ofac_hit:
        logger.critical(
            f"Review {state.get('review_id')}: OFAC HIT detected for {customer_name}. "
            f"Immediate escalation required. Transaction freeze may be required."
        )

    completed = list(state.get("completed_steps", []))
    completed.append("watchlist_screening")

    screening_summary = (
        f"Screened customer + {len(beneficial_owners)} UBOs across 7 watchlists. "
        f"Hits: {len(screening_results)} total. "
        f"OFAC: {'HIT — ESCALATION REQUIRED' if ofac_hit else 'Clear'}. "
        f"PEP: {'HIT — EDD REQUIRED' if pep_hit else 'Clear'}."
    )

    return {
        "watchlist_screening_results": screening_results,
        "ofac_hit": ofac_hit,
        "pep_watchlist_hit": pep_hit,
        "pep_flag": state.get("pep_flag") or pep_hit,  # Preserve existing flag
        "current_step": "watchlist_screening",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=screening_summary,
            node="watchlist_screening",
            data_sources=["OFAC_SDN_list", "OFAC_consolidated_list", "refinitiv_world_check",
                          "lexisnexis_bridger", "dow_jones_rdc", "eu_sanctions_list",
                          "un_sc_consolidated_list", "internal_watchlist"],
            regulatory_basis="OFAC IEEPA; USA PATRIOT Act § 326; FinCEN CDD Rule; FATF R.12",
            human_required=ofac_hit,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5: Adverse Media Check
# ══════════════════════════════════════════════════════════════════════════════

def adverse_media_check(state: KYCReviewState) -> Dict[str, Any]:
    """
    Search for negative news and regulatory actions involving the customer.

    Searches: news databases, court records, regulatory enforcement actions,
    sanctions announcements, corporate filings for negative indicators.

    Severity classification:
    - CRITICAL: SEC/CFTC/OCC/FinCEN enforcement action, criminal indictment,
                law enforcement action, sanctions violation
    - HIGH:     Ongoing investigation, civil lawsuit, financial fraud allegations
    - MEDIUM:   Reputational risk (negative media, political controversy)
    - LOW:      Historical/resolved issues, minor regulatory findings
    - NONE:     No adverse findings

    Regulatory basis: FATF R.12 (PEP EDD), OCC Heightened Standards,
    FFIEC BSA/AML Examination Manual (adverse media as EDD requirement)
    """
    customer_id = state.get("customer_id")
    customer_name = state.get("customer_name")
    beneficial_owners = state.get("beneficial_owners", [])
    logger.info(f"Review {state.get('review_id')}: Adverse media check for {customer_name}")

    media_results = search_adverse_media(
        customer_id=customer_id,
        customer_name=customer_name,
        beneficial_owners=beneficial_owners,
        trigger_type=state.get("trigger_type"),
    )

    hits = media_results.get("hits", [])
    severity = media_results.get("severity", "NONE")
    critical_hits = [h for h in hits if h.get("relevance_score", 0) >= 0.85]

    completed = list(state.get("completed_steps", []))
    completed.append("adverse_media_check")

    media_summary = (
        f"Adverse media check complete. Hits: {len(hits)}. "
        f"Severity: {severity}. "
        f"Critical findings: {len(critical_hits)}."
    )

    return {
        "adverse_media_results": hits,
        "adverse_media_severity": severity,
        "current_step": "adverse_media_check",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=media_summary,
            node="adverse_media_check",
            data_sources=["lexisnexis_news", "dow_jones_rdc", "factiva",
                          "regulatory_enforcement_database", "court_records_db"],
            regulatory_basis="FATF R.12 — EDD adverse media screening; FFIEC BSA/AML Examination Manual",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6: Risk Rescoring
# ══════════════════════════════════════════════════════════════════════════════

def risk_rescoring(state: KYCReviewState) -> Dict[str, Any]:
    """
    Compute updated composite risk score from all review findings.

    8-component weighted risk model:
    1. Jurisdiction risk (15%) — based on countries of operation/incorporation
    2. Transaction behavior (20%) — vs. expected profile
    3. PEP status (15%) — current screening results
    4. Adverse media (15%) — severity of negative findings
    5. Document completeness (10%) — CDD file gaps
    6. Beneficial ownership clarity (10%) — UBO transparency
    7. Industry risk (10%) — NAICS code risk rating
    8. Account tenure / relationship stability (5%)

    LLM is used to generate the plain-language risk narrative explaining
    the score to the Compliance Officer. The numeric score is computed
    deterministically in risk_scorer.py (not by LLM).

    SR 11-7 compliance: every score component is documented, the model
    is explainable, and the Compliance Officer can override the output.
    """
    customer_id = state.get("customer_id")
    logger.info(f"Review {state.get('review_id')}: Computing risk score")

    # Deterministic scoring — Python, not LLM
    score_result = compute_risk_score(
        customer_id=customer_id,
        customer_type=state.get("customer_type"),
        jurisdiction_risk=state.get("jurisdiction_risk", "LOW"),
        pep_flag=state.get("pep_flag", False),
        pep_category=state.get("pep_category"),
        adverse_media_severity=state.get("adverse_media_severity", "NONE"),
        cdd_completeness_score=state.get("cdd_completeness_score", 100.0),
        beneficial_owners=state.get("beneficial_owners", []),
        business_type=state.get("business_type"),
        watchlist_hits=state.get("watchlist_screening_results", []),
        trigger_type=state.get("trigger_type"),
    )

    new_score = score_result.get("composite_score", 0.0)
    previous_score = state.get("previous_risk_score", 0.0)
    delta = new_score - previous_score

    # Determine recommended outcome based on score and hard overrides
    # This logic is deterministic Python — not LLM
    if state.get("ofac_hit"):
        recommended_outcome = ReviewOutcome.ESCALATE
    elif new_score >= 80 and state.get("current_risk_tier") != RiskTier.VERY_HIGH:
        recommended_outcome = ReviewOutcome.RISK_UPGRADE
    elif new_score >= 70 and (state.get("adverse_media_severity") in ["CRITICAL", "HIGH"] or state.get("pep_flag")):
        recommended_outcome = ReviewOutcome.EDD_REQUIRED
    elif new_score >= 85:
        recommended_outcome = ReviewOutcome.ESCALATE
    elif new_score < 30 and state.get("current_risk_tier") in [RiskTier.HIGH, RiskTier.VERY_HIGH]:
        recommended_outcome = ReviewOutcome.RISK_DOWNGRADE
    elif delta >= 20:
        recommended_outcome = ReviewOutcome.RISK_UPGRADE
    elif delta <= -20:
        recommended_outcome = ReviewOutcome.RISK_DOWNGRADE
    elif state.get("missing_documents") and len(state.get("missing_documents", [])) > 2:
        recommended_outcome = ReviewOutcome.EDD_REQUIRED
    else:
        recommended_outcome = ReviewOutcome.PASS

    # Compute proposed risk tier
    if new_score >= 80:
        proposed_tier = RiskTier.VERY_HIGH
    elif new_score >= 60:
        proposed_tier = RiskTier.HIGH
    elif new_score >= 35:
        proposed_tier = RiskTier.MEDIUM
    else:
        proposed_tier = RiskTier.LOW

    # LLM generates the plain-language narrative for the Compliance Officer
    llm = _get_llm()
    narrative_prompt = RISK_NARRATIVE_PROMPT.format(
        customer_name=state.get("customer_name"),
        customer_type=state.get("customer_type"),
        current_risk_tier=state.get("current_risk_tier", "MEDIUM"),
        new_score=new_score,
        previous_score=previous_score,
        delta=delta,
        components=json.dumps(score_result.get("components", {}), indent=2),
        trigger_type=state.get("trigger_type"),
        trigger_description=state.get("trigger_description", "N/A"),
        watchlist_summary=f"OFAC: {'HIT' if state.get('ofac_hit') else 'Clear'}, PEP: {'HIT' if state.get('pep_flag') else 'Clear'}",
        adverse_media_summary=f"Severity: {state.get('adverse_media_severity', 'NONE')}, Hits: {len(state.get('adverse_media_results', []))}",
        document_gaps=", ".join(state.get("missing_documents", [])) or "None",
        recommended_outcome=recommended_outcome.value,
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are a BSA/AML compliance expert writing risk narratives for Compliance Officer review."),
            HumanMessage(content=narrative_prompt),
        ])
        risk_narrative = response.content
    except Exception as e:
        logger.warning(f"LLM narrative generation failed: {e}. Using structured summary.")
        risk_narrative = (
            f"Risk score: {new_score:.1f} (previous: {previous_score:.1f}, delta: {delta:+.1f}). "
            f"Key factors: {', '.join(score_result.get('top_factors', []))}. "
            f"Recommended outcome: {recommended_outcome.value}."
        )

    completed = list(state.get("completed_steps", []))
    completed.append("risk_rescoring")

    return {
        "new_risk_score": new_score,
        "risk_score_delta": delta,
        "risk_score_components": score_result.get("components", {}),
        "risk_narrative": risk_narrative,
        "recommended_outcome": recommended_outcome,
        "proposed_risk_tier": proposed_tier,
        "routing_rationale": (
            f"Score {new_score:.1f} (delta {delta:+.1f}). "
            f"Outcome: {recommended_outcome.value}. "
            f"Proposed tier: {proposed_tier.value}."
        ),
        "current_step": "risk_rescoring",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"Risk rescoring complete. New score: {new_score:.1f}. "
                   f"Previous: {previous_score:.1f}. Delta: {delta:+.1f}. "
                   f"Recommended outcome: {recommended_outcome.value}. "
                   f"Proposed risk tier: {proposed_tier.value}.",
            node="risk_rescoring",
            data_sources=["risk_scoring_model_v2", "transaction_monitoring_system"],
            used_llm=True,
            regulatory_basis="SR 11-7 — Model risk management; FFIEC BSA/AML risk-based approach",
            human_required=recommended_outcome != ReviewOutcome.PASS,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 7: EDD Package Generation
# ══════════════════════════════════════════════════════════════════════════════

def edd_package_generation(state: KYCReviewState) -> Dict[str, Any]:
    """
    Generate Enhanced Due Diligence package when EDD is triggered.

    Produces:
    1. EDD document checklist — specific documents required, with deadlines
       and regulatory basis for each request
    2. Draft RM outreach communication — what to ask the customer for
       and why (in plain language, without disclosing SAR considerations)

    EDD triggers (any one sufficient):
    - PEP flag (FATF R.12 mandatory EDD)
    - OFAC proximity risk
    - Adverse media severity HIGH or CRITICAL
    - Risk score ≥ 70 with risk upgrade
    - New high-risk product (correspondent banking, crypto, MLRO referral)
    - Jurisdiction change to FATF grey/black list country

    Regulatory basis: FATF R.12 — Enhanced due diligence for higher-risk customers;
    FFIEC BSA/AML Examination Manual — EDD program requirements
    """
    customer_id = state.get("customer_id")
    customer_type = state.get("customer_type")
    risk_tier = state.get("proposed_risk_tier", state.get("current_risk_tier", RiskTier.HIGH))
    trigger_type = state.get("trigger_type")

    logger.info(f"Review {state.get('review_id')}: Generating EDD package")

    # Determine EDD trigger reasons for documentation
    edd_triggers = []
    if state.get("pep_flag"):
        edd_triggers.append("Politically Exposed Person (PEP) — mandatory EDD per FATF R.12")
    if state.get("ofac_hit"):
        edd_triggers.append("OFAC watchlist hit — immediate escalation required")
    if state.get("adverse_media_severity") in ["CRITICAL", "HIGH"]:
        edd_triggers.append(f"Adverse media severity: {state.get('adverse_media_severity')}")
    if state.get("risk_score_delta", 0) >= 20:
        edd_triggers.append(f"Significant risk score increase: {state.get('risk_score_delta', 0):+.1f} points")
    if state.get("missing_documents"):
        edd_triggers.append(f"Critical document gaps: {', '.join(state.get('missing_documents', []))}")
    if trigger_type in [TriggerType.BENEFICIAL_OWNER_CHANGE, TriggerType.JURISDICTION_CHANGE]:
        edd_triggers.append(f"Material change trigger: {trigger_type.value}")

    edd_package = generate_edd_package(
        customer_id=customer_id,
        customer_type=customer_type,
        risk_tier=risk_tier.value if hasattr(risk_tier, "value") else risk_tier,
        pep_flag=state.get("pep_flag", False),
        pep_category=state.get("pep_category"),
        trigger_reasons=edd_triggers,
        missing_documents=state.get("missing_documents", []),
    )

    # LLM drafts the RM-facing outreach communication
    llm = _get_llm()
    outreach_prompt = EDD_OUTREACH_PROMPT.format(
        customer_name=state.get("customer_name"),
        customer_type=customer_type,
        edd_trigger_reasons="\n".join(f"- {r}" for r in edd_triggers),
        document_checklist=json.dumps(edd_package.get("document_checklist", []), indent=2),
        edd_deadline=edd_package.get("edd_deadline"),
        rm_name="[Relationship Manager]",
    )

    try:
        response = llm.invoke([
            SystemMessage(content=(
                "You are a compliance expert writing professional, clear EDD outreach communications for relationship managers. "
                "Never disclose SAR activity or hint at suspicious activity investigations. "
                "Frame all document requests as standard compliance program requirements."
            )),
            HumanMessage(content=outreach_prompt),
        ])
        outreach_draft = response.content
    except Exception as e:
        logger.warning(f"EDD outreach draft generation failed: {e}")
        outreach_draft = (
            f"Dear [Relationship Manager],\n\n"
            f"As part of our ongoing compliance program, we are requesting the following updated documentation "
            f"from {state.get('customer_name')} by {edd_package.get('edd_deadline')}:\n\n"
            + "\n".join(f"- {d.get('document')}" for d in edd_package.get("document_checklist", []))
        )

    completed = list(state.get("completed_steps", []))
    completed.append("edd_package_generation")

    return {
        "edd_required": True,
        "edd_trigger_reasons": edd_triggers,
        "edd_document_checklist": edd_package.get("document_checklist", []),
        "edd_outreach_draft": outreach_draft,
        "edd_deadline": edd_package.get("edd_deadline"),
        "case_status": "PENDING_EDD_DOCS",
        "current_step": "edd_package_generation",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"EDD package generated. Triggers: {len(edd_triggers)}. "
                   f"Documents requested: {len(edd_package.get('document_checklist', []))}. "
                   f"EDD deadline: {edd_package.get('edd_deadline')}.",
            node="edd_package_generation",
            used_llm=True,
            regulatory_basis="FATF R.12 — EDD for higher-risk customers; FFIEC BSA/AML EDD requirements",
            human_required=True,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 8: RM Notification
# ══════════════════════════════════════════════════════════════════════════════

def rm_notification(state: KYCReviewState) -> Dict[str, Any]:
    """
    Draft notification to the Relationship Manager.

    All review outcomes — including PASS — generate an RM notification
    for portfolio awareness and documentation.

    Contents:
    - Review outcome summary
    - Risk tier change (if applicable), with explanation
    - Actions required from RM (document collection, customer outreach)
    - Customer-facing talking points (plain language, no regulatory jargon)
    - Timeline for any required actions

    Important: RM notifications NEVER disclose SAR consideration or
    investigation details (BSA tipping-off prohibition, 18 U.S.C. § 1960).
    """
    outcome = state.get("recommended_outcome", ReviewOutcome.PASS)
    llm = _get_llm()

    notification_prompt = RM_NOTIFICATION_PROMPT.format(
        customer_name=state.get("customer_name"),
        customer_type=state.get("customer_type"),
        review_outcome=outcome.value,
        current_risk_tier=state.get("current_risk_tier", "MEDIUM"),
        proposed_risk_tier=state.get("proposed_risk_tier", state.get("current_risk_tier", "MEDIUM")),
        risk_score_delta=state.get("risk_score_delta", 0.0),
        edd_required=state.get("edd_required", False),
        edd_trigger_reasons="\n".join(f"- {r}" for r in state.get("edd_trigger_reasons", [])),
        edd_deadline=state.get("edd_deadline", "N/A"),
        document_gaps=", ".join(state.get("missing_documents", [])) or "None",
        rm_action_required=outcome in [ReviewOutcome.EDD_REQUIRED, ReviewOutcome.RISK_UPGRADE, ReviewOutcome.RELATIONSHIP_EXIT],
        review_deadline=state.get("review_deadline"),
    )

    try:
        response = llm.invoke([
            SystemMessage(content=(
                "You are a compliance officer writing professional notifications to relationship managers. "
                "Be clear and actionable. Never mention SAR activity or investigations. "
                "Frame everything as standard compliance program requirements."
            )),
            HumanMessage(content=notification_prompt),
        ])
        rm_draft = response.content
    except Exception as e:
        logger.warning(f"RM notification draft failed: {e}")
        rm_draft = (
            f"KYC Review Update for {state.get('customer_name')}: "
            f"Outcome: {outcome.value}. "
            f"Action required: {'Yes' if outcome != ReviewOutcome.PASS else 'No'}."
        )

    rm_action = outcome not in [ReviewOutcome.PASS, ReviewOutcome.RISK_DOWNGRADE]

    completed = list(state.get("completed_steps", []))
    completed.append("rm_notification")

    return {
        "rm_notification_draft": rm_draft,
        "rm_action_required": rm_action,
        "case_status": "PENDING_HUMAN_REVIEW",
        "current_step": "rm_notification",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"RM notification drafted. Outcome: {outcome.value}. "
                   f"RM action required: {rm_action}.",
            node="rm_notification",
            used_llm=True,
            regulatory_basis="18 U.S.C. § 1960 — No tipping off; BSA confidentiality provisions",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 9: Human Review Gate
# ══════════════════════════════════════════════════════════════════════════════

def human_review_gate(state: KYCReviewState) -> Dict[str, Any]:
    """
    Mandatory pause point for Compliance Officer review and approval.

    This node implements the LangGraph interrupt pattern:
    - Graph pauses execution here (interrupt_before=["human_review_gate"])
    - Streamlit UI presents findings and recommended outcome to Compliance Officer
    - Officer reviews, optionally modifies outcome, and approves
    - UI calls graph.update_state() with compliance decision
    - Graph resumes with officer's decision incorporated

    The Compliance Officer can:
    - APPROVE: Accept the agent's recommended outcome
    - OVERRIDE: Change the risk tier or outcome with documented rationale
    - ESCALATE_FURTHER: Refer to senior management or BSA committee

    Regulatory basis: No AI system should autonomously change a customer's
    risk classification. FFIEC expects documented Compliance Officer oversight
    of risk-based CDD decisions.
    """
    compliance_decision = state.get("compliance_officer_decision")
    compliance_notes = state.get("compliance_officer_notes", "")
    recommended_outcome = state.get("recommended_outcome")

    if compliance_decision is None:
        # Graph is pausing here — the UI will collect the officer's decision
        logger.info(
            f"Review {state.get('review_id')}: Pausing for Compliance Officer review. "
            f"Recommended outcome: {recommended_outcome}."
        )
        return {
            "human_review_required": True,
            "case_status": "PENDING_HUMAN_REVIEW",
            "current_step": "human_review_gate",
        }

    # Officer has reviewed and made a decision
    logger.info(
        f"Review {state.get('review_id')}: Compliance Officer decision: {compliance_decision}. "
        f"Notes: {compliance_notes[:100] if compliance_notes else 'None'}."
    )

    # Determine final outcome
    if compliance_decision == "APPROVED":
        final_outcome = recommended_outcome
        final_tier = state.get("proposed_risk_tier", state.get("current_risk_tier"))
    elif compliance_decision == "OVERRIDDEN":
        # Officer's override is recorded in state via update_state()
        final_outcome = state.get("compliance_officer_override_outcome", recommended_outcome)
        final_tier = state.get("compliance_officer_override_tier", state.get("current_risk_tier"))
    else:  # ESCALATED_FURTHER
        final_outcome = ReviewOutcome.ESCALATE
        final_tier = state.get("current_risk_tier")

    completed = list(state.get("completed_steps", []))
    completed.append("human_review_gate")

    return {
        "human_review_required": False,
        "human_review_completed_at": datetime.utcnow().isoformat() + "Z",
        "final_risk_tier": final_tier,
        "case_status": "APPROVED" if compliance_decision == "APPROVED" else "ESCALATED",
        "current_step": "human_review_gate",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"Compliance Officer review complete. "
                   f"Decision: {compliance_decision}. "
                   f"Final outcome: {final_outcome.value if hasattr(final_outcome, 'value') else final_outcome}. "
                   f"Notes: {compliance_notes or 'None'}.",
            node="human_review_gate",
            data_sources=["compliance_officer_review"],
            regulatory_basis="FFIEC BSA/AML Examination Manual — Compliance Officer oversight of risk decisions",
            human_required=False,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 10: Initiate Relationship Exit
# ══════════════════════════════════════════════════════════════════════════════

def initiate_relationship_exit(state: KYCReviewState) -> Dict[str, Any]:
    """
    Prepare relationship exit documentation when risk exceeds institutional appetite.

    Generates:
    - Exit rationale memo (for internal records)
    - Account closure notification requirements
    - Timeline per contractual/regulatory obligations
    - SAR consideration note for BSA Officer

    Important: Exit process itself requires Compliance Officer and
    sometimes BSA Committee approval — routes to human_review_gate next.

    Regulatory note: Banks must consider SAR filing when exiting for
    AML/BSA reasons (activity may still be reportable). The "no tipping off"
    rule applies — customer cannot be told the real reason for exit
    if a SAR has been or will be filed.
    """
    logger.info(f"Review {state.get('review_id')}: Initiating relationship exit process")

    completed = list(state.get("completed_steps", []))
    completed.append("initiate_relationship_exit")

    return {
        "case_status": "RELATIONSHIP_EXIT",
        "current_step": "initiate_relationship_exit",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"Relationship exit process initiated. "
                   f"Risk score: {state.get('new_risk_score', 0):.1f}. "
                   f"Risk tier: {state.get('proposed_risk_tier', 'N/A')}. "
                   f"Trigger: {state.get('trigger_type', 'N/A')}. "
                   f"Routing to Compliance Officer for exit approval.",
            node="initiate_relationship_exit",
            regulatory_basis="BSA 31 U.S.C. § 5318 — SAR consideration on exit; 18 U.S.C. § 1960",
            human_required=True,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 11: KYC Record Update
# ══════════════════════════════════════════════════════════════════════════════

def kyc_record_update(state: KYCReviewState) -> Dict[str, Any]:
    """
    Write the approved review outcome to the official KYC record.

    After Compliance Officer approval (or for PASS outcomes):
    - Update risk tier in core banking / KYC system
    - Set next scheduled review date (risk-based)
    - Record review completion date
    - Flag any open EDD requests in the system

    Risk-based review frequency:
    - VERY_HIGH / HIGH: 1 year
    - MEDIUM: 2 years
    - LOW: 3 years

    Regulatory basis: FinCEN CDD Rule — requires maintaining updated,
    current CDD records. FFIEC expects documented review date tracking.
    """
    final_tier = state.get("final_risk_tier", state.get("current_risk_tier", RiskTier.MEDIUM))
    if isinstance(final_tier, str):
        final_tier = RiskTier(final_tier)

    # Compute next review date based on final risk tier
    review_frequency = {
        RiskTier.VERY_HIGH: 365,
        RiskTier.HIGH: 365,
        RiskTier.MEDIUM: 730,
        RiskTier.LOW: 1095,
        RiskTier.PROHIBITED: 0,  # Exit — no next review
    }
    days = review_frequency.get(final_tier, 730)
    next_review = (datetime.utcnow() + timedelta(days=days)).date().isoformat()
    now_iso = datetime.utcnow().isoformat() + "Z"

    try:
        update_kyc_record(
            customer_id=state.get("customer_id"),
            review_id=state.get("review_id"),
            new_risk_tier=final_tier.value,
            next_review_date=next_review,
            reviewed_by=state.get("compliance_officer_id", "ai_agent"),
            edd_required=state.get("edd_required", False),
        )
        update_success = True
    except Exception as e:
        logger.error(f"KYC record update failed: {e}")
        update_success = False

    completed = list(state.get("completed_steps", []))
    completed.append("kyc_record_update")

    tier_changed = final_tier != state.get("current_risk_tier")

    return {
        "next_review_date": next_review,
        "kyc_record_updated_at": now_iso,
        "case_status": "APPROVED" if update_success else "ERROR",
        "current_step": "kyc_record_update",
        "completed_steps": completed,
        "audit_trail": _add_audit_entry(
            state,
            action=f"KYC record updated. "
                   f"Final risk tier: {final_tier.value} "
                   f"({'changed from ' + str(state.get('current_risk_tier', '')) if tier_changed else 'unchanged'}). "
                   f"Next review date: {next_review}. "
                   f"EDD flag: {state.get('edd_required', False)}. "
                   f"Update {'successful' if update_success else 'FAILED — manual update required'}.",
            node="kyc_record_update",
            data_sources=["kyc_record_system", "core_banking"],
            regulatory_basis="FinCEN CDD Rule 31 CFR 1020.210 — Ongoing CDD; FFIEC review tracking",
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 12: Finalize Review
# ══════════════════════════════════════════════════════════════════════════════

def finalize_review(state: KYCReviewState) -> Dict[str, Any]:
    """
    Lock the audit trail and close the review case.

    Final actions:
    - Append final audit trail entry
    - Create/update case record in case management system
    - Send any pending notifications (EDD deadlines, RM alerts)
    - Set case_status to CLOSED
    - Record total review duration

    Audit trail is append-only (JSONL) — no modification after this step.
    BSA requires retaining case records for 5 years minimum.
    """
    review_id = state.get("review_id")
    initiated = state.get("review_initiated_date", datetime.utcnow().date().isoformat())
    now = datetime.utcnow()

    try:
        create_case_record(
            review_id=review_id,
            customer_id=state.get("customer_id"),
            outcome=state.get("recommended_outcome", ReviewOutcome.PASS).value
            if hasattr(state.get("recommended_outcome"), "value")
            else str(state.get("recommended_outcome", "PASS")),
            final_risk_tier=state.get("final_risk_tier", state.get("current_risk_tier", "MEDIUM")),
            compliance_officer_id=state.get("compliance_officer_id"),
            audit_trail=state.get("audit_trail", []),
        )
    except Exception as e:
        logger.error(f"Case record creation failed for {review_id}: {e}")

    completed = list(state.get("completed_steps", []))
    completed.append("finalize_review")

    final_audit = _add_audit_entry(
        state,
        action=f"KYC review finalized. Review ID: {review_id}. "
               f"Outcome: {state.get('recommended_outcome', 'PASS')}. "
               f"Final risk tier: {state.get('final_risk_tier', 'N/A')}. "
               f"Compliance Officer: {state.get('compliance_officer_id', 'N/A')}. "
               f"Next review: {state.get('next_review_date', 'N/A')}. "
               f"Steps completed: {len(completed)}. "
               "Audit trail locked.",
        node="finalize_review",
        regulatory_basis="BSA 31 U.S.C. § 5318 — 5-year record retention requirement",
    )

    logger.info(f"Review {review_id}: Finalized. Outcome: {state.get('recommended_outcome')}")

    return {
        "case_status": "CLOSED",
        "current_step": "finalize_review",
        "completed_steps": completed,
        "audit_trail": final_audit,
    }
