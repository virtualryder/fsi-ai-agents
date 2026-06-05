# agent/nodes.py
# ============================================================
# LangGraph Node Functions — The Investigation Workflow Engine
#
# Each function in this file represents one step in the AML investigation
# workflow. The functions are designed to mirror the actual process used by
# Financial Crimes Units (FCUs) at major US banks.
#
# Design principles:
#   1. Every node logs to audit_trail (regulatory requirement)
#   2. Every node appends to investigation_notes (case file documentation)
#   3. Errors are captured gracefully — the investigation continues
#   4. Comments explain the INVESTIGATOR'S thought process, not just the code
#   5. Integration points are clearly marked for production system connections
#
# Regulatory basis:
#   OCC BSA/AML Examination Procedures — investigation documentation standards
#   FinCEN SAR guidance — investigation thoroughness requirements
# ============================================================

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent.state import InvestigationState, RecommendedAction
from agent.prompts import (
    ALERT_ANALYSIS_PROMPT,
    TRANSACTION_PATTERN_PROMPT,
    RISK_SCORING_PROMPT,
    SAR_NARRATIVE_PROMPT,
    NETWORK_ANALYSIS_PROMPT,
    ADVERSE_MEDIA_PROMPT,
)
from tools.transaction_monitor import (
    get_transaction_history,
    detect_structuring_patterns,
    detect_velocity_anomalies,
    get_alerts_for_customer,
)
from tools.customer_profile import (
    get_customer_profile,
    get_account_details,
    get_beneficial_owners,
)
from tools.watchlist_screening import (
    screen_against_ofac,
    screen_pep_lists,
    screen_eu_un_sanctions,
    screen_internal_watchlist,
)
from tools.network_analysis import (
    build_counterparty_network,
    detect_shell_company_indicators,
    calculate_network_risk_score,
    identify_circular_flows,
)
from tools.adverse_media import search_adverse_media, categorize_media_hits
from tools.sar_generator import generate_sar_narrative, format_sar_part_ii
from tools.case_management import create_case, update_case_status, close_case

# Configure module logger
logger = logging.getLogger(__name__)

# ── LLM Configuration ─────────────────────────────────────────────────────────
# We use gpt-4o for all analysis tasks. Temperature is set to 0.1 to ensure
# analytical precision and reproducibility — AML analysis is not creative writing.
# SR 11-7 (Model Risk Management) requires that AI outputs be consistent and
# explainable. A low temperature setting supports this requirement.

def _get_llm() -> ChatOpenAI:
    """
    Initialize the LLM. Called fresh in each node to respect environment
    variable changes without requiring a restart.

    In production, this would use AWS Bedrock, Azure OpenAI, or a
    private deployment — never a shared public API with customer data.

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with your organization's approved LLM endpoint:
    # - AWS Bedrock (Claude 3/GPT-4 via Bedrock): use boto3 + langchain-aws
    # - Azure OpenAI (data stays in Azure tenant): use AzureChatOpenAI
    # - On-premise: use Ollama or vLLM with an approved model
    # ──────────────────────────────────────────────────────────────────────────
    """
    import os
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def _log_audit_entry(
    state: InvestigationState,
    action: str,
    node: str,
    data_sources: list = None,
    ai_model: str = None,
) -> None:
    """
    Add a timestamped entry to the investigation audit trail.

    This function is called at the start and end of every node execution.
    The audit trail is a first-class regulatory artifact — examiners will
    review it to confirm that investigations were conducted thoroughly and
    that all AI decisions had human oversight.

    Args:
        state: The current investigation state
        action: Human-readable description of what was done
        node: The graph node name (for traceability)
        data_sources: List of external systems accessed
        ai_model: LLM model name if AI analysis was performed
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": "ai_agent",
        "investigator_id": state.get("investigator_id", "system"),
        "action": action,
        "node": node,
        "alert_id": state.get("alert_id", "UNKNOWN"),
        "customer_id": state.get("customer_id", "UNKNOWN"),
        "data_sources_accessed": data_sources or [],
        "ai_model_used": ai_model,
        "human_review_required": node in ["generate_sar", "finalize_case"],
    }

    audit_trail = state.get("audit_trail", [])
    audit_trail.append(entry)
    state["audit_trail"] = audit_trail


def _add_note(state: InvestigationState, note: str) -> None:
    """
    Append a note to the investigation's running case file.

    Investigation notes are the narrative thread of the case file.
    They are written in the voice of the investigator and will be
    read by any analyst who picks up this case, by the BSA officer
    who reviews the SAR, and by examiners during regulatory review.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    notes = state.get("investigation_notes", [])
    notes.append(f"[{timestamp}] {note}")
    state["investigation_notes"] = notes


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1: alert_intake
# ══════════════════════════════════════════════════════════════════════════════

def alert_intake(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 1: Alert Intake and Initial Classification

    When a TMS alert fires, the first job of the FCU analyst is to:
    1. Validate the alert contains all required fields
    2. Understand the alert type and regulatory context
    3. Form an initial hypothesis about what suspicious activity may be occurring
    4. Assign appropriate priority and investigation complexity estimate

    This mirrors what happens in the first 15-30 minutes of a human
    investigator opening a new alert in their queue.

    Regulatory note:
    - BSA requires investigation of all alerts generated by the compliance program
    - OCC expects documented rationale even for alerts that are closed quickly
    - The alert_intake step creates the formal case record that begins the clock
      for any potential SAR filing (30-day deadline from determination date)
    """
    logger.info(f"[alert_intake] Starting investigation for alert: {state.get('alert_id')}")

    # Update progress tracking — the UI uses this to show which step is running
    state["current_step"] = "alert_intake"
    completed = state.get("completed_steps", [])

    # Log this action to the audit trail
    _log_audit_entry(
        state,
        action=f"Investigation initiated for alert {state.get('alert_id')} — alert intake and classification",
        node="alert_intake",
        data_sources=["TMS Alert Queue"],
    )

    try:
        # ── VALIDATION: Ensure the alert has all required fields ────────────────
        # An investigator would first verify the alert is complete before proceeding.
        # Missing fields could indicate a TMS configuration issue.
        required_fields = ["alert_id", "alert_type", "customer_id", "alert_severity"]
        missing_fields = [f for f in required_fields if not state.get(f)]

        if missing_fields:
            error_msg = f"Alert missing required fields: {missing_fields}"
            logger.error(f"[alert_intake] {error_msg}")
            errors = state.get("errors", [])
            errors.append({
                "step": "alert_intake",
                "error": error_msg,
                "timestamp": datetime.utcnow().isoformat(),
                "recoverable": False,  # Cannot proceed without core alert data
            })
            state["errors"] = errors
            state["current_step"] = "alert_intake_failed"
            return state

        # ── LLM ANALYSIS: Initial alert classification ──────────────────────────
        # We invoke the LLM to perform the initial triage analysis.
        # This replaces the 15-30 minutes an analyst spends reading the alert
        # and forming their initial hypothesis.

        llm = _get_llm()

        # Format the alert data for the prompt
        alert_data = {
            "alert_id": state.get("alert_id"),
            "alert_type": state.get("alert_type"),
            "alert_severity": state.get("alert_severity"),
            "alert_source": state.get("alert_source", "TMS"),
            "triggered_rule": state.get("triggered_rule", "UNKNOWN"),
            "alert_date": state.get("alert_date", datetime.utcnow().date().isoformat()),
            "transaction_ids": state.get("transactions", [])[:5],  # First 5 for context
        }

        customer_context = {
            "customer_id": state.get("customer_id"),
            "account_ids": state.get("account_ids", []),
            # Full profile comes in step 2 — here we only have basic identifiers
        }

        prompt = ALERT_ANALYSIS_PROMPT.format(
            alert_data=json.dumps(alert_data, indent=2),
            customer_context=json.dumps(customer_context, indent=2),
        )

        response = llm.invoke([HumanMessage(content=prompt)])

        # Parse the LLM's structured response
        try:
            analysis = json.loads(response.content)
        except json.JSONDecodeError:
            # If the LLM didn't return clean JSON, extract what we can
            logger.warning("[alert_intake] LLM returned non-JSON response, using defaults")
            analysis = {
                "alert_classification": state.get("alert_type", "UNKNOWN"),
                "typology_match": "UNKNOWN",
                "preliminary_risk": state.get("alert_severity", "MEDIUM"),
                "risk_rationale": "Auto-classification: LLM parsing error",
                "investigation_priorities": ["Review transaction history", "Screen watchlists", "Check customer profile"],
                "regulatory_flags": [],
                "working_hypothesis": "Investigation required to determine suspicious activity type",
                "estimated_investigation_complexity": "MODERATE",
            }

        # ── STORE ANALYSIS RESULTS IN STATE ────────────────────────────────────
        # We enrich the state with the LLM's initial analysis.
        # These findings will inform the priority and approach of subsequent steps.

        state["alert_type"] = analysis.get("alert_classification", state.get("alert_type"))
        state["risk_factors"] = analysis.get("regulatory_flags", [])

        # Add the working hypothesis to investigation notes
        _add_note(
            state,
            f"ALERT INTAKE: Alert {state['alert_id']} classified as '{analysis.get('alert_classification')}'. "
            f"Working hypothesis: {analysis.get('working_hypothesis')}. "
            f"Preliminary risk: {analysis.get('preliminary_risk')}. "
            f"Investigation complexity: {analysis.get('estimated_investigation_complexity')}. "
            f"Priority areas: {'; '.join(analysis.get('investigation_priorities', []))}."
        )

        _log_audit_entry(
            state,
            action=f"Alert classified as '{analysis.get('alert_classification')}' with preliminary risk '{analysis.get('preliminary_risk')}'",
            node="alert_intake",
            ai_model="gpt-4o",
        )

        # Mark step as complete
        completed.append("alert_intake")
        state["completed_steps"] = completed

        logger.info(f"[alert_intake] Completed — Alert: {state['alert_id']}, Type: {analysis.get('alert_classification')}, Preliminary Risk: {analysis.get('preliminary_risk')}")

    except Exception as e:
        # Capture unexpected errors — the graph will continue to next possible step
        logger.error(f"[alert_intake] Unexpected error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "alert_intake",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,  # We can continue with basic alert data
        })
        state["errors"] = errors
        _add_note(state, f"ALERT INTAKE ERROR: {str(e)} — investigation continuing with available data")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2: customer_profile_lookup
# ══════════════════════════════════════════════════════════════════════════════

def customer_profile_lookup(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 2: Customer Profile and KYC Review

    Before diving into transactions, an investigator always reviews the customer
    file — understanding WHO we're investigating and whether existing risk context
    explains or deepens concern about the alert.

    Key questions at this step:
    - What is the customer's stated business purpose? Does activity fit?
    - When was KYC last refreshed? Is it current (BSA requires periodic review)?
    - Is this customer on Enhanced Due Diligence (EDD) already?
    - Are there Politically Exposed Persons (PEPs) involved?
    - For legal entities: who are the Ultimate Beneficial Owners (UBOs)?
    - What is the current risk tier, and has behavior changed since assignment?

    Regulatory basis:
    - BSA: Customer Due Diligence (CDD) Rule (31 CFR § 1010.230)
    - FATF R.10: Customer due diligence measures
    - FATF R.12: Enhanced due diligence for PEPs
    - FATF R.17: Reliance on third parties for CDD
    """
    logger.info(f"[customer_profile_lookup] Retrieving customer profile for: {state.get('customer_id')}")
    state["current_step"] = "customer_profile_lookup"

    _log_audit_entry(
        state,
        action=f"Retrieving KYC/customer profile for customer {state.get('customer_id')}",
        node="customer_profile_lookup",
        data_sources=["Core Banking System", "KYC Platform", "CDD Database"],
    )

    try:
        customer_id = state.get("customer_id")
        account_ids = state.get("account_ids", [])

        # ── RETRIEVE CUSTOMER KYC PROFILE ───────────────────────────────────────
        # This calls the core banking / KYC system to get the full customer record.
        # In production, this would be a real API call to your core banking platform.
        customer_profile = get_customer_profile(customer_id)
        state["customer_profile"] = customer_profile

        # ── RETRIEVE ACCOUNT DETAILS FOR ALL ASSOCIATED ACCOUNTS ───────────────
        # Each account may have different risk profiles, signatories, and activity.
        account_details = {}
        for account_id in account_ids:
            account_details[account_id] = get_account_details(account_id)

        # ── FOR LEGAL ENTITIES: RETRIEVE BENEFICIAL OWNERSHIP ──────────────────
        # The FinCEN CDD Rule requires banks to identify and verify the identity
        # of all beneficial owners (25%+ ownership or control) of legal entities.
        # This is a critical AML control — shell companies often hide BOs.
        beneficial_owners = []
        if customer_profile.get("customer_type") == "ENTITY":
            beneficial_owners = get_beneficial_owners(customer_id)
            customer_profile["beneficial_owners"] = beneficial_owners

            # Flag if beneficial owner is in a high-risk jurisdiction
            high_risk_countries = [
                "Iran", "North Korea", "Syria", "Myanmar", "Cuba", "Russia",
                "Belarus", "Venezuela", "Yemen", "Libya", "Somalia"
            ]
            for bo in beneficial_owners:
                bo_country = bo.get("country_of_residence", "")
                if bo_country in high_risk_countries:
                    risk_factors = state.get("risk_factors", [])
                    risk_factors.append(
                        f"Beneficial owner {bo.get('name', 'UNKNOWN')} is a resident of {bo_country} — high-risk jurisdiction per FinCEN advisory"
                    )
                    state["risk_factors"] = risk_factors
                    _add_note(
                        state,
                        f"RISK FLAG: Beneficial owner '{bo.get('name')}' in high-risk jurisdiction ({bo_country}). EDD required per FATF R.12."
                    )

        # ── FLAG PEP STATUS ─────────────────────────────────────────────────────
        # PEPs (Politically Exposed Persons) require Enhanced Due Diligence under
        # FATF R.12 — they have elevated corruption risk by virtue of their position.
        if customer_profile.get("pep_flag") or any(bo.get("pep_flag") for bo in beneficial_owners):
            risk_factors = state.get("risk_factors", [])
            risk_factors.append("PEP status identified — Enhanced Due Diligence required per FATF R.12")
            state["risk_factors"] = risk_factors
            _add_note(state, "PEP FLAG: Customer or beneficial owner identified as Politically Exposed Person. EDD mandatory.")

        # ── CHECK EDD STATUS ────────────────────────────────────────────────────
        # If the customer is already on EDD, prior concerns exist.
        # If EDD is LAPSED, that itself is a compliance issue — it means the
        # bank failed to conduct required periodic reviews.
        edd_status = customer_profile.get("edd_status", "NOT_REQUIRED")
        if edd_status == "LAPSED":
            _add_note(
                state,
                f"COMPLIANCE CONCERN: Customer {customer_id} has lapsed EDD. "
                "Bank is required to refresh EDD for high-risk customers. "
                "This may represent a BSA program deficiency."
            )
        elif edd_status == "ACTIVE":
            _add_note(
                state,
                f"EDD CONTEXT: Customer {customer_id} is currently under Enhanced Due Diligence. "
                f"EDD opened: {customer_profile.get('edd_open_date', 'UNKNOWN')}. "
                "Prior concerns on file — review EDD case notes."
            )

        # ── KYC FRESHNESS CHECK ─────────────────────────────────────────────────
        # BSA requires periodic KYC refresh — typically annually for high-risk,
        # every 3 years for medium-risk, every 5 years for low-risk customers.
        kyc_date_str = customer_profile.get("kyc_date")
        if kyc_date_str:
            try:
                kyc_date = datetime.strptime(kyc_date_str, "%Y-%m-%d")
                kyc_age_days = (datetime.utcnow() - kyc_date).days
                risk_tier = customer_profile.get("risk_tier", "MEDIUM")

                # Thresholds by risk tier
                max_kyc_age = {"HIGH": 365, "VERY_HIGH": 180, "MEDIUM": 1095, "LOW": 1825}
                tier_threshold = max_kyc_age.get(risk_tier, 1095)

                if kyc_age_days > tier_threshold:
                    _add_note(
                        state,
                        f"KYC STALENESS: Customer's KYC was last refreshed {kyc_age_days} days ago "
                        f"({kyc_date_str}). For {risk_tier} risk tier, refresh required every "
                        f"{tier_threshold} days. BSA refresh overdue."
                    )
            except ValueError:
                pass  # If date parsing fails, skip this check

        # ── COMPREHENSIVE PROFILE NOTE ──────────────────────────────────────────
        _add_note(
            state,
            f"CUSTOMER PROFILE REVIEW COMPLETE: Customer {customer_id} — "
            f"Type: {customer_profile.get('customer_type')}, "
            f"Risk Tier: {customer_profile.get('risk_tier')}, "
            f"EDD Status: {customer_profile.get('edd_status')}, "
            f"PEP: {customer_profile.get('pep_flag')}, "
            f"KYC Date: {customer_profile.get('kyc_date')}, "
            f"Business Type: {customer_profile.get('business_type', 'N/A')}. "
            f"Accounts reviewed: {len(account_ids)}. "
            f"Beneficial owners identified: {len(beneficial_owners)}."
        )

        completed = state.get("completed_steps", [])
        completed.append("customer_profile_lookup")
        state["completed_steps"] = completed

        logger.info(f"[customer_profile_lookup] Complete — Risk Tier: {customer_profile.get('risk_tier')}, EDD: {edd_status}")

    except Exception as e:
        logger.error(f"[customer_profile_lookup] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "customer_profile_lookup",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        _add_note(state, f"CUSTOMER PROFILE ERROR: Unable to retrieve full profile — {str(e)}. Proceeding with available data.")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3: transaction_analysis
# ══════════════════════════════════════════════════════════════════════════════

def transaction_analysis(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 3: Transaction History Analysis

    The heart of most AML investigations — analyzing the transaction record
    for patterns consistent with known money laundering typologies.

    This step retrieves 12 months of transaction history (BSA requires
    investigation of the full period of suspicious activity, which the OCC
    typically expects to be at least 12 months for annual reviews).

    Key typologies analyzed:
    - STRUCTURING: Multiple sub-$10K cash deposits to evade CTR reporting
    - LAYERING: Rapid movement through intermediary accounts
    - SMURFING: Multiple individuals depositing into same account
    - VELOCITY ANOMALIES: Activity dramatically inconsistent with customer profile
    - DORMANCY-THEN-ACTIVITY: Sudden reactivation of dormant accounts
    - GEOGRAPHIC CONCENTRATION: Flows to/from high-risk jurisdictions

    Regulatory basis:
    - 31 U.S.C. § 5313: Currency Transaction Reporting ($10K threshold)
    - 31 CFR § 1010.100(xx): Definition of structuring
    - FinCEN SAR typologies guidance (FIN-2007-G003)
    """
    logger.info(f"[transaction_analysis] Analyzing transactions for customer: {state.get('customer_id')}")
    state["current_step"] = "transaction_analysis"

    _log_audit_entry(
        state,
        action="Retrieving and analyzing 12-month transaction history for all associated accounts",
        node="transaction_analysis",
        data_sources=["Transaction Monitoring System", "Core Banking", "Wire Transfer System"],
    )

    try:
        account_ids = state.get("account_ids", [])
        all_transactions = []

        # ── RETRIEVE TRANSACTION HISTORY FOR ALL ACCOUNTS ──────────────────────
        # We look at all accounts associated with this customer — structuring
        # often involves splitting transactions across multiple accounts at
        # multiple branches. Siloed account-by-account review misses this.
        for account_id in account_ids:
            # 365 days = 12 months as required by OCC examination procedures
            txn_history = get_transaction_history(account_id, days=365)
            all_transactions.extend(txn_history)

        # If the alert itself has specific transactions, include them
        # These are the "triggering" transactions — most important to analyze
        state_transactions = state.get("transactions", [])
        if state_transactions:
            # Merge alert transactions with historical data, deduplicating
            existing_ids = {t.get("transaction_id") for t in all_transactions}
            for txn in state_transactions:
                if txn.get("transaction_id") not in existing_ids:
                    all_transactions.append(txn)

        state["transactions"] = all_transactions

        _add_note(
            state,
            f"TRANSACTION RETRIEVAL: Retrieved {len(all_transactions)} transactions across "
            f"{len(account_ids)} account(s) for the 12-month investigation period."
        )

        # ── STRUCTURING DETECTION ───────────────────────────────────────────────
        # Structuring is specifically illegal under 31 U.S.C. § 5324.
        # "No person shall, for the purpose of evading the reporting requirements of
        # section 5313(a)... cause or attempt to cause a domestic financial institution
        # to fail to file a report..."
        # The key element: INTENT to evade. Multiple sub-$10K deposits alone are not
        # illegal — the pattern must suggest evasion intent.
        structuring_results = detect_structuring_patterns(all_transactions)

        # ── VELOCITY ANOMALY DETECTION ──────────────────────────────────────────
        # Compare current activity against the customer's historical baseline.
        # A restaurant suddenly processing $500K in wire transfers is anomalous
        # regardless of the individual transaction amounts.
        customer_profile = state.get("customer_profile", {})
        baseline = {
            "monthly_cash_avg": customer_profile.get("expected_monthly_cash", 0),
            "monthly_wire_avg": customer_profile.get("expected_monthly_wires", 0),
            "risk_tier": customer_profile.get("risk_tier", "MEDIUM"),
        }
        velocity_results = detect_velocity_anomalies(all_transactions, baseline)

        # ── LLM PATTERN ANALYSIS ────────────────────────────────────────────────
        # The LLM performs a holistic analysis of the full transaction set,
        # looking for patterns that algorithmic rules might miss — like a
        # series of transactions that look normal individually but form a
        # suspicious pattern in aggregate.
        llm = _get_llm()

        # Prepare transaction summary for LLM analysis
        # We summarize to avoid hitting token limits while preserving key data
        txn_summary = []
        for t in all_transactions[:100]:  # Cap at 100 for token management
            txn_summary.append({
                "date": t.get("date"),
                "amount": t.get("amount"),
                "type": t.get("transaction_type"),
                "channel": t.get("channel"),
                "counterparty": t.get("counterparty_name"),
                "counterparty_country": t.get("counterparty_country"),
                "currency": t.get("currency", "USD"),
            })

        prompt = TRANSACTION_PATTERN_PROMPT.format(
            transaction_data=json.dumps(txn_summary, indent=2),
            customer_baseline=json.dumps(baseline, indent=2),
            analysis_period="12 months",
        )

        response = llm.invoke([HumanMessage(content=prompt)])

        try:
            pattern_analysis = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("[transaction_analysis] LLM returned non-JSON, using algorithmic results only")
            pattern_analysis = {
                "structuring": structuring_results,
                "velocity_anomalies": velocity_results,
                "summary": {"analyst_note": "Pattern analysis completed by algorithmic tools"},
            }

        # ── COMBINE ALGORITHMIC AND LLM ANALYSIS ───────────────────────────────
        # The final pattern assessment combines:
        # 1. Rule-based detection (structuring detector, velocity analyzer)
        # 2. LLM holistic pattern recognition
        # Both are needed — rules catch known patterns; LLM catches novel ones.
        transaction_patterns = {
            **pattern_analysis,
            "algorithmic_structuring": structuring_results,
            "algorithmic_velocity": velocity_results,
            "total_transactions_analyzed": len(all_transactions),
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }
        state["transaction_patterns"] = transaction_patterns

        # ── DOCUMENT KEY FINDINGS ───────────────────────────────────────────────
        summary = pattern_analysis.get("summary", {})
        suspicious_volume = summary.get("total_suspicious_volume", 0)
        primary_typology = summary.get("primary_typology", "Unknown")

        if suspicious_volume > 0:
            risk_factors = state.get("risk_factors", [])
            risk_factors.append(
                f"Suspicious transaction volume: ${suspicious_volume:,.2f} — "
                f"primary typology: {primary_typology}"
            )
            state["risk_factors"] = risk_factors

        _add_note(
            state,
            f"TRANSACTION ANALYSIS COMPLETE: Analyzed {len(all_transactions)} transactions. "
            f"Primary typology detected: {primary_typology}. "
            f"Total suspicious volume: ${suspicious_volume:,.2f}. "
            f"Structuring indicators: {pattern_analysis.get('structuring', {}).get('detected', False)}. "
            f"Layering indicators: {pattern_analysis.get('layering', {}).get('detected', False)}. "
            f"Velocity anomalies: {pattern_analysis.get('velocity_anomalies', {}).get('detected', False)}. "
            f"Analyst note: {summary.get('analyst_note', 'N/A')}."
        )

        completed = state.get("completed_steps", [])
        completed.append("transaction_analysis")
        state["completed_steps"] = completed

        logger.info(f"[transaction_analysis] Complete — {len(all_transactions)} transactions analyzed, primary typology: {primary_typology}")

    except Exception as e:
        logger.error(f"[transaction_analysis] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "transaction_analysis",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        state["transaction_patterns"] = {}
        _add_note(state, f"TRANSACTION ANALYSIS ERROR: {str(e)} — proceeding with available data")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4: watchlist_screening
# ══════════════════════════════════════════════════════════════════════════════

def watchlist_screening(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 4: Watchlist and Sanctions Screening

    OFAC screening is a LEGAL REQUIREMENT, not an optional best practice.
    Banks that facilitate transactions with OFAC-designated entities face:
    - Civil penalties up to $20,000,000 per violation
    - Criminal penalties including imprisonment for willful violations
    - Reputational damage and potential loss of banking license

    This step screens:
    1. OFAC SDN (Specially Designated Nationals) — primary US sanctions list
    2. PEP lists — Politically Exposed Persons (FATF R.12)
    3. EU and UN sanctions lists — for international business
    4. Internal watchlists — customers the bank has flagged internally

    The 50% Rule:
    OFAC's 50% rule (2014 guidance) requires screening entities in which
    an SDN holds 50% or more ownership interest — even if the entity itself
    is not named on the list. This is why beneficial ownership data (Step 2)
    is critical for screening.

    Regulatory basis:
    - Executive Order 13224 (terrorism financing)
    - 50 U.S.C. §§ 1701-1707 (IEEPA — International Emergency Economic Powers Act)
    - OFAC regulations (31 CFR Parts 500-598)
    - FATF R.12: Enhanced due diligence for PEPs
    """
    logger.info(f"[watchlist_screening] Screening customer and counterparties: {state.get('customer_id')}")
    state["current_step"] = "watchlist_screening"

    _log_audit_entry(
        state,
        action="Conducting OFAC SDN, PEP, EU/UN sanctions, and internal watchlist screening",
        node="watchlist_screening",
        data_sources=["OFAC SDN Database", "World-Check/Refinitiv", "UN Consolidated List", "EU Sanctions List", "Internal Watchlist"],
    )

    try:
        customer_profile = state.get("customer_profile", {})
        all_hits = []

        # ── COMPILE NAMES TO SCREEN ─────────────────────────────────────────────
        # We must screen:
        # 1. The customer (primary name + any aliases/DBA names)
        # 2. All beneficial owners
        # 3. All counterparties identified in the transaction analysis
        # This comprehensive screening is what regulators expect.
        names_to_screen = []

        # Primary customer
        customer_name = customer_profile.get("full_name") or customer_profile.get("entity_name", "")
        if customer_name:
            names_to_screen.append({
                "name": customer_name,
                "role": "PRIMARY_CUSTOMER",
                "dob": customer_profile.get("date_of_birth"),
                "country": customer_profile.get("country_of_residence", "US"),
                "customer_id": state.get("customer_id"),
            })

        # Aliases / DBA names
        for alias in customer_profile.get("aliases", []):
            names_to_screen.append({
                "name": alias,
                "role": "CUSTOMER_ALIAS",
                "dob": customer_profile.get("date_of_birth"),
                "country": customer_profile.get("country_of_residence", "US"),
            })

        # Beneficial owners
        for bo in customer_profile.get("beneficial_owners", []):
            names_to_screen.append({
                "name": bo.get("name"),
                "role": "BENEFICIAL_OWNER",
                "dob": bo.get("date_of_birth"),
                "country": bo.get("country_of_residence"),
                "ownership_pct": bo.get("ownership_percentage"),
            })

        # Key counterparties from transaction analysis
        transactions = state.get("transactions", [])
        counterparties_screened = set()
        for txn in transactions:
            cp_name = txn.get("counterparty_name")
            if cp_name and cp_name not in counterparties_screened and cp_name != "CASH":
                names_to_screen.append({
                    "name": cp_name,
                    "role": "COUNTERPARTY",
                    "country": txn.get("counterparty_country"),
                })
                counterparties_screened.add(cp_name)
                # Limit counterparty screening to top 20 to manage API costs
                if len(counterparties_screened) >= 20:
                    break

        _add_note(
            state,
            f"WATCHLIST SCREENING SCOPE: Screening {len(names_to_screen)} names — "
            f"customer + aliases, {len(customer_profile.get('beneficial_owners', []))} beneficial owners, "
            f"{len(counterparties_screened)} counterparties."
        )

        # ── OFAC SDN SCREENING ──────────────────────────────────────────────────
        # OFAC SDN hits require IMMEDIATE action — potentially freezing the account
        # and contacting OFAC directly. This is the most critical check.
        for subject in names_to_screen:
            ofac_result = screen_against_ofac(
                name=subject["name"],
                dob=subject.get("dob"),
                country=subject.get("country"),
            )
            if ofac_result.get("hit"):
                ofac_result["subject_role"] = subject["role"]
                ofac_result["subject_name_screened"] = subject["name"]
                all_hits.append(ofac_result)

                # OFAC hit is immediately critical — document urgently
                _add_note(
                    state,
                    f"⚠️ OFAC SDN HIT: '{subject['name']}' ({subject['role']}) matched OFAC SDN list. "
                    f"Match score: {ofac_result.get('match_score')}%. "
                    f"SDN ID: {ofac_result.get('sdn_id')}. "
                    f"IMMEDIATE REVIEW REQUIRED — potential account freeze and OFAC reporting obligation."
                )
                risk_factors = state.get("risk_factors", [])
                risk_factors.append(
                    f"OFAC SDN MATCH: {subject['name']} — match score {ofac_result.get('match_score')}%"
                )
                state["risk_factors"] = risk_factors

        # ── PEP SCREENING ───────────────────────────────────────────────────────
        # PEPs include current and former: heads of state, senior politicians,
        # senior government/military/judiciary officials, and their immediate family
        # and close associates. FATF R.12 requires EDD for foreign PEPs.
        for subject in names_to_screen:
            pep_result = screen_pep_lists(
                name=subject["name"],
                country=subject.get("country", "US"),
            )
            if pep_result.get("hit"):
                pep_result["subject_role"] = subject["role"]
                pep_result["subject_name_screened"] = subject["name"]
                all_hits.append(pep_result)
                _add_note(
                    state,
                    f"PEP HIT: '{subject['name']}' ({subject['role']}) identified as Politically Exposed Person. "
                    f"Position: {pep_result.get('position', 'Unknown')}. "
                    f"Country: {pep_result.get('country', 'Unknown')}. "
                    f"Enhanced Due Diligence required per FATF R.12."
                )

        # ── EU AND UN SANCTIONS SCREENING ──────────────────────────────────────
        # For banks with international operations or foreign counterparties,
        # EU and UN sanctions are equally binding.
        for subject in names_to_screen[:5]:  # Screen top subjects only for efficiency
            eu_un_result = screen_eu_un_sanctions(name=subject["name"])
            if eu_un_result.get("hit"):
                eu_un_result["subject_role"] = subject["role"]
                all_hits.append(eu_un_result)
                _add_note(
                    state,
                    f"EU/UN SANCTIONS HIT: '{subject['name']}' found on {eu_un_result.get('list_name')}. "
                    f"Immediate escalation required."
                )

        # ── INTERNAL WATCHLIST SCREENING ────────────────────────────────────────
        # Banks maintain internal lists of customers who have been flagged
        # for prior suspicious activity but are not on public lists.
        # This includes: prior SAR subjects, refused business, exit-banked customers.
        internal_result = screen_internal_watchlist(state.get("customer_id"))
        if internal_result.get("hit"):
            all_hits.append(internal_result)
            _add_note(
                state,
                f"INTERNAL WATCHLIST HIT: Customer {state.get('customer_id')} is on bank's internal watchlist. "
                f"Reason: {internal_result.get('reason', 'Unknown')}. "
                f"Prior SAR filed: {internal_result.get('prior_sar', False)}."
            )

        # ── STORE ALL HITS IN STATE ─────────────────────────────────────────────
        state["watchlist_hits"] = all_hits

        # Summary note
        ofac_hits = [h for h in all_hits if h.get("list_type") == "OFAC_SDN"]
        pep_hits = [h for h in all_hits if h.get("list_type") == "PEP"]

        _add_note(
            state,
            f"WATCHLIST SCREENING COMPLETE: {len(all_hits)} total hits. "
            f"OFAC SDN: {len(ofac_hits)}, PEP: {len(pep_hits)}, Other: {len(all_hits) - len(ofac_hits) - len(pep_hits)}. "
            f"{'IMMEDIATE ESCALATION REQUIRED FOR OFAC HITS.' if ofac_hits else 'No OFAC hits found.'}"
        )

        completed = state.get("completed_steps", [])
        completed.append("watchlist_screening")
        state["completed_steps"] = completed

        logger.info(f"[watchlist_screening] Complete — {len(all_hits)} hits found ({len(ofac_hits)} OFAC, {len(pep_hits)} PEP)")

    except Exception as e:
        logger.error(f"[watchlist_screening] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "watchlist_screening",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        state["watchlist_hits"] = []
        _add_note(state, f"WATCHLIST SCREENING ERROR: {str(e)} — proceeding without watchlist data (HIGH RISK)")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5: adverse_media_search
# ══════════════════════════════════════════════════════════════════════════════

def adverse_media_search(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 5: Adverse Media Search

    Adverse media screening has become a regulatory expectation — regulators
    now expect banks to supplement database screening with open-source
    intelligence (OSINT) to identify reputational and financial crime risks
    that may not yet be captured in formal watchlists.

    An investigator would search for:
    - News articles linking the customer to crime or corruption
    - Prior regulatory actions or enforcement orders
    - Civil litigation involving financial misconduct
    - Negative coverage in trade/industry press
    - Associations with known criminal organizations

    Regulatory basis:
    - FATF R.12: EDD for PEPs includes adverse media screening
    - OCC BSA/AML Examination Handbook: Due diligence for high-risk customers
    - FinCEN CDD Rule: Risk-based approach to customer screening
    """
    logger.info(f"[adverse_media_search] Searching adverse media for customer: {state.get('customer_id')}")
    state["current_step"] = "adverse_media_search"

    _log_audit_entry(
        state,
        action="Conducting adverse media and OSINT screening",
        node="adverse_media_search",
        data_sources=["Adverse Media Database", "News Wire Services", "Regulatory Action Databases"],
    )

    try:
        customer_profile = state.get("customer_profile", {})

        # Build list of names to search
        primary_name = customer_profile.get("full_name") or customer_profile.get("entity_name", "")
        aliases = customer_profile.get("aliases", [])
        all_names = [primary_name] + aliases

        # Also search beneficial owners for entities
        for bo in customer_profile.get("beneficial_owners", []):
            bo_name = bo.get("name")
            if bo_name:
                all_names.append(bo_name)

        # ── SEARCH ADVERSE MEDIA ────────────────────────────────────────────────
        raw_hits = search_adverse_media(name=primary_name, aliases=aliases if aliases else None)

        # ── LLM CATEGORIZATION ──────────────────────────────────────────────────
        # The LLM evaluates each hit for: relevance (is it actually our customer?),
        # severity, and AML relevance. This reduces false positives from
        # common names while ensuring genuine hits are not missed.
        if raw_hits:
            llm = _get_llm()
            prompt = ADVERSE_MEDIA_PROMPT.format(
                subject_names=json.dumps(all_names),
                media_hits=json.dumps(raw_hits, indent=2),
            )
            response = llm.invoke([HumanMessage(content=prompt)])

            try:
                media_analysis = json.loads(response.content)
                categorized_hits = media_analysis.get("relevant_hits", [])
                overall_risk = media_analysis.get("overall_adverse_media_risk", "NONE")
            except json.JSONDecodeError:
                categorized_hits = raw_hits
                overall_risk = "UNKNOWN"
        else:
            categorized_hits = []
            overall_risk = "NONE"

        state["adverse_media_hits"] = categorized_hits

        # Document findings
        critical_hits = [h for h in categorized_hits if h.get("severity") in ["CRITICAL", "HIGH"]]

        if critical_hits:
            for hit in critical_hits:
                risk_factors = state.get("risk_factors", [])
                risk_factors.append(
                    f"Adverse media ({hit.get('category', 'Unknown')}): {hit.get('headline', 'See full report')}"
                )
                state["risk_factors"] = risk_factors

        _add_note(
            state,
            f"ADVERSE MEDIA COMPLETE: {len(categorized_hits)} relevant hits found. "
            f"Overall adverse media risk: {overall_risk}. "
            f"Critical/high severity hits: {len(critical_hits)}. "
            f"{'SIGNIFICANT ADVERSE MEDIA REQUIRES DOCUMENTATION IN SAR NARRATIVE.' if critical_hits else 'No critical adverse media found.'}"
        )

        completed = state.get("completed_steps", [])
        completed.append("adverse_media_search")
        state["completed_steps"] = completed

        logger.info(f"[adverse_media_search] Complete — {len(categorized_hits)} relevant hits, risk: {overall_risk}")

    except Exception as e:
        logger.error(f"[adverse_media_search] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "adverse_media_search",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        state["adverse_media_hits"] = []
        _add_note(state, f"ADVERSE MEDIA ERROR: {str(e)} — proceeding without adverse media data")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6: network_analysis
# ══════════════════════════════════════════════════════════════════════════════

def network_analysis(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 6: Counterparty Network Analysis

    Modern money laundering rarely involves a single customer acting alone.
    It involves networks of entities — shell companies, nominees, intermediaries —
    designed to create distance between the criminal proceeds and the ultimate
    beneficiary.

    Network analysis asks:
    - Who is this customer transacting with?
    - Are any of those counterparties themselves suspicious?
    - Are there shell company structures being used to obscure ownership?
    - Is money going out and coming back in a circular flow (layering)?
    - How many hops is this customer from a known bad actor?

    This is the investigator's "follow the money" step — the most analytically
    complex and often most revealing part of an AML investigation.

    Regulatory basis:
    - FATF R.20: Suspicious transaction reporting
    - FATF R.24/25: Transparency of legal persons and beneficial ownership
    - FinCEN CDD Rule: Beneficial ownership requirements for legal entities
    - BSA 314(b): Voluntary information sharing between financial institutions
    """
    logger.info(f"[network_analysis] Mapping counterparty network for customer: {state.get('customer_id')}")
    state["current_step"] = "network_analysis"

    _log_audit_entry(
        state,
        action="Building counterparty network graph and analyzing for shell company indicators, circular flows, and proximity to known bad actors",
        node="network_analysis",
        data_sources=["Transaction History", "Corporate Registry APIs", "Internal Network Intelligence", "Shared Watchlist"],
    )

    try:
        transactions = state.get("transactions", [])

        # ── BUILD COUNTERPARTY NETWORK GRAPH ────────────────────────────────────
        # Using NetworkX to build a directed graph:
        # - Nodes = entities (customer, counterparties, intermediaries)
        # - Edges = transactions (with amount, date, type as edge attributes)
        network_graph = build_counterparty_network(transactions)

        # ── DETECT SHELL COMPANY INDICATORS ─────────────────────────────────────
        # For each entity in the network, check for shell company red flags.
        # Shell companies are the #1 tool for hiding beneficial ownership.
        shell_company_findings = {}
        for entity_name in network_graph.get("nodes", []):
            if entity_name == state.get("customer_profile", {}).get("entity_name", ""):
                continue  # Skip the primary customer node

            entity_data = {
                "name": entity_name,
                "transaction_pattern": [t for t in transactions if t.get("counterparty_name") == entity_name],
            }
            shell_indicators = detect_shell_company_indicators(entity_data)
            if shell_indicators.get("shell_company_probability", 0) > 50:
                shell_company_findings[entity_name] = shell_indicators

        network_graph["shell_company_findings"] = shell_company_findings

        # ── IDENTIFY CIRCULAR FLOWS ──────────────────────────────────────────────
        # Circular flows are a hallmark of layering — money leaves an account
        # and returns via a different path, making it appear "clean."
        circular_flows = identify_circular_flows(network_graph)
        network_graph["circular_flows"] = circular_flows

        # ── CALCULATE NETWORK RISK SCORE ─────────────────────────────────────────
        # Consider: number of shell companies, circular flows, high-risk jurisdictions,
        # proximity to watchlist-flagged entities
        network_risk = calculate_network_risk_score(network_graph)
        network_graph["network_risk_score"] = network_risk

        # ── LLM ANALYSIS OF NETWORK ─────────────────────────────────────────────
        # The LLM synthesizes the graph data into a human-readable analysis
        # with specific findings and recommendations.
        llm = _get_llm()

        prompt = NETWORK_ANALYSIS_PROMPT.format(
            network_data=json.dumps({
                "nodes": network_graph.get("nodes", [])[:20],  # Limit for token management
                "edges_summary": f"{len(network_graph.get('edges', []))} transactions",
                "shell_company_findings": shell_company_findings,
                "circular_flows": circular_flows,
                "high_risk_jurisdictions": network_graph.get("high_risk_jurisdictions", []),
            }, indent=2),
            customer_profile=json.dumps(state.get("customer_profile", {}), indent=2),
        )

        response = llm.invoke([HumanMessage(content=prompt)])

        try:
            network_analysis_result = json.loads(response.content)
        except json.JSONDecodeError:
            network_analysis_result = {
                "network_summary": network_graph.get("network_risk_score", {}),
                "key_findings": ["Network analysis completed — see graph data"],
            }

        # Merge LLM findings into network graph
        network_graph["llm_analysis"] = network_analysis_result
        state["network_graph"] = network_graph

        # ── DOCUMENT KEY NETWORK FINDINGS ───────────────────────────────────────
        key_findings = network_analysis_result.get("key_findings", [])
        for finding in key_findings[:3]:  # Top 3 findings into risk factors
            risk_factors = state.get("risk_factors", [])
            risk_factors.append(f"NETWORK: {finding}")
            state["risk_factors"] = risk_factors

        shell_count = len(shell_company_findings)
        circular_count = len(circular_flows)

        _add_note(
            state,
            f"NETWORK ANALYSIS COMPLETE: Mapped {len(network_graph.get('nodes', []))} counterparties. "
            f"Suspected shell companies: {shell_count}. "
            f"Circular flows detected: {circular_count}. "
            f"High-risk jurisdiction counterparties: {len(network_graph.get('high_risk_jurisdictions', []))}. "
            f"Network risk score: {network_risk.get('score', 0)}/100. "
            f"Key finding: {key_findings[0] if key_findings else 'No significant network risk identified'}."
        )

        completed = state.get("completed_steps", [])
        completed.append("network_analysis")
        state["completed_steps"] = completed

        logger.info(f"[network_analysis] Complete — {len(network_graph.get('nodes', []))} nodes, {shell_count} shell companies, {circular_count} circular flows")

    except Exception as e:
        logger.error(f"[network_analysis] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "network_analysis",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        state["network_graph"] = {}
        _add_note(state, f"NETWORK ANALYSIS ERROR: {str(e)} — proceeding without network data")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 7: risk_scoring
# ══════════════════════════════════════════════════════════════════════════════

def risk_scoring(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 7: Composite Risk Scoring

    After gathering all evidence, the investigator synthesizes the findings
    into a single risk assessment. This is the equivalent of the analyst
    sitting down with their case notes and making a holistic judgment.

    The composite score uses a weighted methodology:
    - Watchlist/Sanctions Hits: 30 points (regulatory zero-tolerance)
    - Network Risk: 25 points (proximity to bad actors)
    - Transaction Patterns: 25 points (direct typology evidence)
    - Adverse Media: 15 points (reputational/forward-looking risk)
    - Customer Risk Profile: 5 points (contextual baseline)

    Total: 100 points
    Thresholds:
    - <30: CLOSE case (no credible suspicious activity)
    - 30-70: ESCALATE (ambiguous, needs senior review)
    - >70: FILE SAR (sufficient evidence of suspicious activity)

    Model Risk:
    This scoring model must be validated per SR 11-7 before production use.
    The weights and thresholds should be calibrated against the bank's
    historical SAR population and false positive rate.
    """
    logger.info(f"[risk_scoring] Calculating composite risk score for: {state.get('customer_id')}")
    state["current_step"] = "risk_scoring"

    _log_audit_entry(
        state,
        action="Calculating composite AML risk score across all investigation dimensions",
        node="risk_scoring",
        ai_model="gpt-4o",
    )

    try:
        # ── PREPARE INVESTIGATION SUMMARY FOR LLM SCORING ───────────────────────
        # Compile all investigation findings into a structured summary
        # that the LLM will use to calculate the weighted risk score.
        investigation_summary = {
            "customer_id": state.get("customer_id"),
            "alert_type": state.get("alert_type"),
            "customer_profile": {
                "risk_tier": state.get("customer_profile", {}).get("risk_tier"),
                "edd_status": state.get("customer_profile", {}).get("edd_status"),
                "pep_flag": state.get("customer_profile", {}).get("pep_flag"),
                "customer_type": state.get("customer_profile", {}).get("customer_type"),
            },
            "watchlist_hits": state.get("watchlist_hits", []),
            "transaction_patterns": {
                "structuring": state.get("transaction_patterns", {}).get("structuring", {}),
                "layering": state.get("transaction_patterns", {}).get("layering", {}),
                "velocity_anomalies": state.get("transaction_patterns", {}).get("velocity_anomalies", {}),
                "primary_typology": state.get("transaction_patterns", {}).get("summary", {}).get("primary_typology", "Unknown"),
                "suspicious_volume": state.get("transaction_patterns", {}).get("summary", {}).get("total_suspicious_volume", 0),
            },
            "network_risk": {
                "shell_companies": len(state.get("network_graph", {}).get("shell_company_findings", {})),
                "circular_flows": len(state.get("network_graph", {}).get("circular_flows", [])),
                "network_risk_score": state.get("network_graph", {}).get("network_risk_score", {}).get("score", 0),
                "high_risk_jurisdictions": state.get("network_graph", {}).get("high_risk_jurisdictions", []),
            },
            "adverse_media": {
                "hits_count": len(state.get("adverse_media_hits", [])),
                "critical_hits": [h for h in state.get("adverse_media_hits", []) if h.get("severity") in ["CRITICAL", "HIGH"]],
            },
            "prior_risk_factors": state.get("risk_factors", []),
        }

        # ── LLM RISK SCORING ─────────────────────────────────────────────────────
        # The LLM applies the weighted scoring methodology defined in the prompt.
        # Each factor is scored independently with documented rationale.
        # This ensures the score is explainable — a regulatory requirement (SR 11-7).
        llm = _get_llm()
        prompt = RISK_SCORING_PROMPT.format(
            investigation_summary=json.dumps(investigation_summary, indent=2),
        )

        response = llm.invoke([HumanMessage(content=prompt)])

        try:
            scoring_result = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback scoring if LLM JSON fails
            logger.warning("[risk_scoring] LLM scoring failed — using algorithmic fallback")
            scoring_result = _algorithmic_fallback_score(state)

        total_score = float(scoring_result.get("total_score", 0))
        state["risk_score"] = total_score

        # ── MAP SCORE TO RECOMMENDED ACTION ─────────────────────────────────────
        # These thresholds are configurable — different banks may use different cutoffs
        # based on their risk appetite and SAR population analysis.
        recommended = scoring_result.get("recommended_action", "ESCALATE")
        if total_score < 30:
            state["recommended_action"] = RecommendedAction.CLOSE
        elif total_score <= 70:
            state["recommended_action"] = RecommendedAction.ESCALATE
        else:
            state["recommended_action"] = RecommendedAction.FILE_SAR

        # ── STORE RISK FACTORS ───────────────────────────────────────────────────
        key_risk_factors = scoring_result.get("key_risk_factors", [])
        existing_risk_factors = state.get("risk_factors", [])
        # Merge without duplicates
        for factor in key_risk_factors:
            if factor not in existing_risk_factors:
                existing_risk_factors.append(factor)
        state["risk_factors"] = existing_risk_factors

        _add_note(
            state,
            f"RISK SCORING COMPLETE: Composite score = {total_score:.1f}/100. "
            f"Factor breakdown — "
            f"Watchlist/Sanctions: {scoring_result.get('factor_scores', {}).get('watchlist_sanctions', {}).get('score', 0)}/30, "
            f"Network Risk: {scoring_result.get('factor_scores', {}).get('network_risk', {}).get('score', 0)}/25, "
            f"Transaction Patterns: {scoring_result.get('factor_scores', {}).get('transaction_patterns', {}).get('score', 0)}/25, "
            f"Adverse Media: {scoring_result.get('factor_scores', {}).get('adverse_media', {}).get('score', 0)}/15, "
            f"Customer Risk Profile: {scoring_result.get('factor_scores', {}).get('customer_risk_profile', {}).get('score', 0)}/5. "
            f"Recommended action: {state['recommended_action'].value}. "
            f"Examiner note: {scoring_result.get('examiner_note', 'N/A')}."
        )

        completed = state.get("completed_steps", [])
        completed.append("risk_scoring")
        state["completed_steps"] = completed

        logger.info(f"[risk_scoring] Complete — Score: {total_score:.1f}/100, Action: {state['recommended_action'].value}")

    except Exception as e:
        logger.error(f"[risk_scoring] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "risk_scoring",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        # Default to ESCALATE if scoring fails — conservative approach
        state["risk_score"] = 50.0
        state["recommended_action"] = RecommendedAction.ESCALATE
        _add_note(state, f"RISK SCORING ERROR: {str(e)} — defaulting to ESCALATE (conservative)")

    return state


def _algorithmic_fallback_score(state: InvestigationState) -> dict:
    """
    Fallback risk scoring using pure algorithmic logic.
    Used when LLM scoring fails. Ensures the investigation can continue.
    """
    score = 0

    # Watchlist (30 pts max)
    watchlist_hits = state.get("watchlist_hits", [])
    ofac_hits = [h for h in watchlist_hits if h.get("list_type") == "OFAC_SDN"]
    if ofac_hits:
        score += 28
    elif watchlist_hits:
        score += 15

    # Network (25 pts max)
    network = state.get("network_graph", {})
    shell_count = len(network.get("shell_company_findings", {}))
    circular_count = len(network.get("circular_flows", []))
    network_score = min(25, shell_count * 10 + circular_count * 8)
    score += network_score

    # Patterns (25 pts max)
    patterns = state.get("transaction_patterns", {})
    pattern_score = 0
    if patterns.get("structuring", {}).get("detected"):
        pattern_score += 22
    if patterns.get("layering", {}).get("detected"):
        pattern_score += 20
    if patterns.get("velocity_anomalies", {}).get("detected"):
        pattern_score += 15
    score += min(25, pattern_score)

    # Adverse media (15 pts max)
    media_hits = state.get("adverse_media_hits", [])
    critical = [h for h in media_hits if h.get("severity") in ["CRITICAL", "HIGH"]]
    if critical:
        score += 12
    elif media_hits:
        score += 5

    # Customer profile (5 pts max)
    profile = state.get("customer_profile", {})
    if profile.get("risk_tier") in ["VERY_HIGH", "HIGH"]:
        score += 4
    elif profile.get("risk_tier") == "MEDIUM":
        score += 1

    return {
        "total_score": min(100, score),
        "recommended_action": "FILE_SAR" if score > 70 else ("ESCALATE" if score > 30 else "CLOSE"),
        "key_risk_factors": state.get("risk_factors", []),
        "factor_scores": {
            "watchlist_sanctions": {"score": min(30, 28 if ofac_hits else 15 if watchlist_hits else 0)},
            "network_risk": {"score": network_score},
            "transaction_patterns": {"score": min(25, pattern_score)},
            "adverse_media": {"score": 12 if critical else (5 if media_hits else 0)},
            "customer_risk_profile": {"score": 4 if profile.get("risk_tier") in ["VERY_HIGH", "HIGH"] else 1},
        },
        "examiner_note": "Score calculated using algorithmic fallback — LLM unavailable",
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 8: routing_decision
# ══════════════════════════════════════════════════════════════════════════════

def routing_decision(state: InvestigationState) -> str:
    """
    ROUTING DECISION: Determine the next graph node based on risk score.

    This is a conditional edge function — it returns the name of the next
    node to execute, not a modified state. LangGraph uses the return value
    to route execution.

    Score thresholds:
    - < 30: close_case (no credible suspicious activity)
    - 30-70: human_review_gate (escalate for human decision)
    - > 70: generate_sar (prepare SAR narrative for human review)

    These thresholds represent industry-standard risk-appetite settings.
    They should be calibrated per bank based on:
    - Historical SAR population analysis
    - Regulatory examination findings
    - False positive/negative tolerance
    """
    risk_score = state.get("risk_score", 50)
    recommended_action = state.get("recommended_action", RecommendedAction.ESCALATE)

    logger.info(f"[routing_decision] Risk score: {risk_score:.1f}, Recommended action: {recommended_action}")

    if recommended_action == RecommendedAction.FILE_SAR or risk_score > 70:
        return "generate_sar"
    elif recommended_action == RecommendedAction.ESCALATE or risk_score >= 30:
        return "human_review_gate"
    else:
        return "close_case"


# ══════════════════════════════════════════════════════════════════════════════
# NODE 9: generate_sar
# ══════════════════════════════════════════════════════════════════════════════

def generate_sar(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 9: SAR Narrative Generation

    If the investigation findings cross the threshold, the next step is to
    prepare a draft Suspicious Activity Report (SAR) for BSA Officer review.

    CRITICAL: The AI generates a DRAFT. A licensed BSA Officer MUST review
    and approve before filing. The AI cannot and does not file SARs autonomously.

    SAR Filing Requirements (31 CFR § 1020.320):
    - Must be filed within 30 days of initial detection of suspicious activity
    - Extended to 60 days if no identified subject
    - 5-year retention requirement from date of filing
    - No tipping off: Do NOT inform the customer a SAR is being filed
      (31 U.S.C. § 5318(g)(2) — criminal penalty for disclosure)

    FinCEN Quality Standards (FIN-2014-G001):
    - Complete 5 W's + How (who, what, when, where, why, how)
    - Specific transaction details (amounts, dates, account numbers)
    - Reference to typologies and red flags
    - Prior SAR references if continuing activity
    - Target: 500-2,000 words
    """
    logger.info(f"[generate_sar] Generating SAR narrative for: {state.get('customer_id')}")
    state["current_step"] = "generate_sar"

    _log_audit_entry(
        state,
        action="Generating BSA-compliant SAR narrative draft — HUMAN REVIEW REQUIRED before filing",
        node="generate_sar",
        ai_model="gpt-4o",
        data_sources=["Investigation Findings", "Transaction History", "Watchlist Results", "Network Analysis"],
    )

    try:
        customer_profile = state.get("customer_profile", {})
        patterns = state.get("transaction_patterns", {})

        # ── CALCULATE SAR FILING DEADLINE ───────────────────────────────────────
        # BSA: 30 days from the date the bank determines a transaction is suspicious.
        # If the subject cannot be identified: 60 days from detection.
        # OCC examination focus: Was the SAR filed within the statutory deadline?
        detection_date = datetime.utcnow()
        watchlist_hits = state.get("watchlist_hits", [])
        has_identified_subject = bool(
            customer_profile.get("full_name") or customer_profile.get("entity_name")
        )
        deadline_days = 30 if has_identified_subject else 60
        filing_deadline = detection_date + timedelta(days=deadline_days)
        state["sar_filing_deadline"] = filing_deadline.strftime("%Y-%m-%d")

        _add_note(
            state,
            f"SAR FILING DEADLINE: {filing_deadline.strftime('%Y-%m-%d')} "
            f"({deadline_days} days from detection — {'identified subject' if has_identified_subject else 'no identified subject'}). "
            f"This deadline is a legal requirement under 31 CFR § 1020.320."
        )

        # ── GENERATE SAR NARRATIVE VIA TOOL ─────────────────────────────────────
        # The SAR generator tool handles the detailed prompt and LLM invocation
        sar_narrative_text = generate_sar_narrative(state)
        state["sar_narrative"] = sar_narrative_text

        # ── GENERATE STRUCTURED SAR PART I FIELDS ───────────────────────────────
        sar_fields = format_sar_part_ii(state)
        state["sar_fields"] = sar_fields

        _add_note(
            state,
            f"SAR DRAFT GENERATED: BSA-compliant SAR narrative prepared. "
            f"Narrative length: {len(sar_narrative_text)} characters. "
            f"Suspicious activity amount: ${sar_fields.get('amount_involved', 0):,.2f}. "
            f"Activity period: {sar_fields.get('activity_start_date')} to {sar_fields.get('activity_end_date')}. "
            f"⚠️ IMPORTANT: This draft requires BSA Officer review and approval before filing. "
            f"Filing deadline: {state['sar_filing_deadline']}. "
            f"Do NOT disclose SAR to subject (31 U.S.C. § 5318(g)(2))."
        )

        completed = state.get("completed_steps", [])
        completed.append("generate_sar")
        state["completed_steps"] = completed

        logger.info(f"[generate_sar] Complete — SAR draft generated, deadline: {state['sar_filing_deadline']}")

    except Exception as e:
        logger.error(f"[generate_sar] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "generate_sar",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        state["sar_narrative"] = f"SAR narrative generation failed: {str(e)}. Manual preparation required."
        _add_note(state, f"SAR GENERATION ERROR: {str(e)} — manual SAR preparation required")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 10: human_review_gate
# ══════════════════════════════════════════════════════════════════════════════

def human_review_gate(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 10: Human-in-the-Loop Review Gate

    This node creates an interrupt point where a licensed BSA Officer or
    senior analyst must review all AI-generated findings before any
    compliance action is taken (filing a SAR, escalating a case, or closing).

    Why this matters:
    - AI systems can make errors — human oversight catches mistakes
    - Regulatory expectation: Examiners expect humans to be accountable for decisions
    - SR 11-7 Model Risk Management: Human oversight is required for compliance decisions
    - ECOA/Fair Lending: Human review helps identify potential disparate impact
    - The SAR is a legal document — only licensed professionals can sign off

    In the LangGraph implementation, this node uses `interrupt()` to pause
    execution and await human input through the Streamlit UI. The investigator
    reviews all findings in the dashboard and either approves or modifies the
    AI's recommended action.

    In this demo, the node prepares the review package and marks the case
    as pending human review. In production, this integrates with your
    case management system's workflow engine.
    """
    logger.info(f"[human_review_gate] Preparing case for human review: {state.get('case_id', 'UNASSIGNED')}")
    state["current_step"] = "human_review_gate"

    _log_audit_entry(
        state,
        action="Investigation findings prepared for human review — awaiting BSA Officer approval",
        node="human_review_gate",
        data_sources=[],
    )

    # ── PREPARE REVIEW SUMMARY ───────────────────────────────────────────────
    # Compile everything the human reviewer needs to make an informed decision.
    # This is what the investigator sees in the "Review" tab of the dashboard.
    review_summary = {
        "case_prepared_at": datetime.utcnow().isoformat() + "Z",
        "alert_id": state.get("alert_id"),
        "customer_id": state.get("customer_id"),
        "risk_score": state.get("risk_score"),
        "recommended_action": state.get("recommended_action", RecommendedAction.ESCALATE).value if state.get("recommended_action") else "ESCALATE",
        "key_risk_factors": state.get("risk_factors", [])[:5],  # Top 5
        "watchlist_hits_count": len(state.get("watchlist_hits", [])),
        "adverse_media_count": len(state.get("adverse_media_hits", [])),
        "total_suspicious_volume": state.get("transaction_patterns", {}).get("summary", {}).get("total_suspicious_volume", 0),
        "sar_deadline": state.get("sar_filing_deadline"),
        "investigation_steps_completed": state.get("completed_steps", []),
        "errors_encountered": len(state.get("errors", [])),
    }

    state["case_status"] = "PENDING_HUMAN_REVIEW"

    _add_note(
        state,
        f"PENDING HUMAN REVIEW: Investigation findings are complete and ready for BSA Officer review. "
        f"All AI findings are advisory — human decision required. "
        f"Risk score: {state.get('risk_score', 0):.1f}/100. "
        f"Recommended action: {state.get('recommended_action', RecommendedAction.ESCALATE).value if state.get('recommended_action') else 'ESCALATE'}. "
        f"{'SAR deadline: ' + state.get('sar_filing_deadline', 'N/A') + '. ' if state.get('sar_filing_deadline') else ''}"
        f"Awaiting investigator {state.get('investigator_id', 'UNASSIGNED')} review and decision."
    )

    completed = state.get("completed_steps", [])
    if "human_review_gate" not in completed:
        completed.append("human_review_gate")
    state["completed_steps"] = completed

    logger.info(f"[human_review_gate] Case ready for human review — Risk: {state.get('risk_score', 0):.1f}, Action: {state.get('recommended_action', 'ESCALATE')}")

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 11: close_case (routing target for low-risk alerts)
# ══════════════════════════════════════════════════════════════════════════════

def close_case(state: InvestigationState) -> InvestigationState:
    """
    CASE CLOSURE: No credible suspicious activity found.

    Even when closing a case, BSA requires documentation of WHY the case
    was closed. Examiners look for documented rationale — "no suspicious
    activity found" is not sufficient without explaining what was investigated
    and what information was considered.

    BSA record retention: 5 years from closure date.
    """
    logger.info(f"[close_case] Closing case — insufficient evidence of suspicious activity")
    state["current_step"] = "close_case"

    _log_audit_entry(
        state,
        action=f"Case closed — risk score {state.get('risk_score', 0):.1f}/100 below SAR threshold. No suspicious activity requiring reporting.",
        node="close_case",
    )

    state["case_status"] = "CLOSED"
    state["recommended_action"] = RecommendedAction.CLOSE

    _add_note(
        state,
        f"CASE CLOSED: Investigation complete — no suspicious activity requiring SAR filing. "
        f"Risk score {state.get('risk_score', 0):.1f}/100 is below the threshold (30 pts). "
        f"Key factors reviewed: {'; '.join(state.get('risk_factors', ['None identified'])[:3])}. "
        f"BSA requires this case record be retained for 5 years per 31 CFR § 1010.430. "
        f"Closure subject to BSA Officer concurrence."
    )

    completed = state.get("completed_steps", [])
    completed.append("close_case")
    state["completed_steps"] = completed

    return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 12: finalize_case
# ══════════════════════════════════════════════════════════════════════════════

def finalize_case(state: InvestigationState) -> InvestigationState:
    """
    INVESTIGATION STEP 12: Case Finalization and Record Creation

    The final step of every investigation — creating the formal case record,
    logging all actions to the audit trail, updating the case management system,
    and triggering any required notifications.

    This step ensures:
    1. Case record is created in the case management system
    2. All evidence is linked to the case record
    3. Appropriate notifications are sent (compliance team, law enforcement if applicable)
    4. BSA retention timer is started (5 years from case close or SAR filing)
    5. Any required follow-up actions are scheduled (EDD refresh, SAR filing workflow)

    Regulatory basis:
    - 31 CFR § 1010.430: BSA record retention (5 years)
    - OCC: Case management documentation standards
    - FinCEN: SAR filing workflow requirements
    """
    logger.info(f"[finalize_case] Finalizing case record for alert: {state.get('alert_id')}")
    state["current_step"] = "finalize_case"

    _log_audit_entry(
        state,
        action="Finalizing investigation case record and updating case management system",
        node="finalize_case",
        data_sources=["Case Management System"],
    )

    try:
        # ── CREATE CASE RECORD ───────────────────────────────────────────────────
        case_id = create_case(
            alert_id=state.get("alert_id"),
            customer_id=state.get("customer_id"),
            investigator_id=state.get("investigator_id", "SYSTEM"),
        )
        state["case_id"] = case_id

        # ── DETERMINE FINAL DISPOSITION ─────────────────────────────────────────
        action = state.get("recommended_action", RecommendedAction.ESCALATE)
        action_value = action.value if isinstance(action, RecommendedAction) else str(action)

        # ── UPDATE CASE WITH FINAL STATUS ────────────────────────────────────────
        update_case_status(
            case_id=case_id,
            status=state.get("case_status", "PENDING_REVIEW"),
            notes=f"Investigation complete. Risk score: {state.get('risk_score', 0):.1f}/100. "
                  f"Recommended action: {action_value}. "
                  f"Key findings: {'; '.join(state.get('risk_factors', [])[:3])}",
        )

        _add_note(
            state,
            f"CASE FINALIZED: Case ID {case_id} created in case management system. "
            f"Final status: {state.get('case_status', 'PENDING_REVIEW')}. "
            f"Recommended action: {action_value}. "
            f"Risk score: {state.get('risk_score', 0):.1f}/100. "
            f"Investigation steps completed: {', '.join(state.get('completed_steps', []))}. "
            f"{'SAR filing deadline: ' + state.get('sar_filing_deadline', 'N/A') if state.get('sar_filing_deadline') else ''}. "
            f"BSA 5-year retention clock started: {datetime.utcnow().strftime('%Y-%m-%d')}."
        )

        completed = state.get("completed_steps", [])
        completed.append("finalize_case")
        state["completed_steps"] = completed

        logger.info(f"[finalize_case] Complete — Case {case_id} finalized, status: {state.get('case_status')}")

    except Exception as e:
        logger.error(f"[finalize_case] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append({
            "step": "finalize_case",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "recoverable": True,
        })
        state["errors"] = errors
        _add_note(state, f"CASE FINALIZATION ERROR: {str(e)} — manual case creation required")

    return state
