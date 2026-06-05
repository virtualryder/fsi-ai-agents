# tools/sar_generator.py
# ============================================================
# SAR (Suspicious Activity Report) Generator
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   Writing a SAR narrative is the most time-consuming part of the AML investigation
#   workflow. A quality SAR narrative (500-2,000 words) requires synthesizing all
#   investigation findings into a coherent, legally defensible document that follows
#   FinCEN guidelines. An experienced analyst takes 4-8 hours per SAR. This tool
#   generates a high-quality first draft in seconds — the human BSA Officer then
#   reviews, edits, and approves before filing.
#
# REGULATORY REQUIREMENTS SERVED:
#   - 31 CFR § 1020.320: SAR filing obligation for banks
#   - 31 CFR § 1022.320: SAR filing for MSBs (slightly different threshold: $2,000)
#   - FinCEN Form 111 (SAR): Electronic filing format
#   - FIN-2014-G001: "Guidance on Preparing a Complete & Sufficient SAR Narrative"
#     This FinCEN guidance is the definitive standard for SAR quality.
#   - 31 U.S.C. § 5318(g)(2): NO TIPPING OFF — criminal penalty for disclosure
#   - 31 U.S.C. § 5318(g)(3): Safe harbor from civil liability for good-faith filers
#   - BSA: 30-day filing deadline from date of determination
#   - BSA: 60-day deadline if no identified subject
#   - BSA: 5-year retention from date of filing
#
# SAR FILING THRESHOLDS:
#   - Banks (31 CFR § 1020.320): $5,000+ AND suspicious activity indicators
#   - MSBs (31 CFR § 1022.320): $2,000+ AND suspicious activity indicators
#   - Securities firms (31 CFR § 1023.320): $5,000+
#   - OFAC: No threshold — all OFAC violations must be reported regardless of amount
#
# TIPPING OFF PROHIBITION:
#   31 U.S.C. § 5318(g)(2): "A financial institution... may not notify any
#   person involved in the transaction that the transaction has been reported."
#   NEVER disclose to the customer, their attorney, or associated parties that
#   a SAR is being filed or has been filed. Criminal penalties apply.
#
# SAFE HARBOR:
#   31 U.S.C. § 5318(g)(3): Financial institutions and their employees filing
#   SARs in good faith are protected from civil liability. This safe harbor
#   applies to both the filing AND any disclosure to authorized government agencies.
# ============================================================

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from agent.prompts import SAR_NARRATIVE_PROMPT

logger = logging.getLogger(__name__)


def generate_sar_narrative(state: Dict[str, Any]) -> str:
    """
    Generate a BSA-compliant SAR Part II narrative.

    This function produces a draft SAR narrative following FinCEN's quality
    guidance (FIN-2014-G001). The narrative answers the 5 W's + How:
    - WHO: Subject(s) and their relationship to the bank
    - WHAT: Specific suspicious transactions and patterns
    - WHEN: Date range of the suspicious activity
    - WHERE: Branches, accounts, jurisdictions involved
    - WHY: Why this activity is suspicious (departures from expected behavior)
    - HOW: The mechanism used to conduct the suspicious activity

    Quality standards (what FinCEN examiners look for):
    - Specific dollar amounts (not "large amounts")
    - Specific dates (not "recently")
    - Specific account numbers (masked: ***1234)
    - Named counterparties (with masked account numbers)
    - Reference to known typologies (structuring, layering, etc.)
    - Description of normal expected activity vs. observed activity
    - Prior SARs on this customer/account
    - Investigative steps taken (what was verified, what remains unknown)

    Args:
        state: The full investigation state dictionary containing all findings

    Returns:
        Formatted SAR narrative text (500-2,000 words)

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # In production, after the SAR narrative is generated and approved by
    # the BSA Officer, submit via FinCEN's BSA E-Filing System:
    # - URL: https://bsaefiling.fincen.treas.gov/
    # - API: FinCEN provides a web services API for batch filing
    # - Format: FinCEN SAR XML format (schema available at fincen.gov)
    # Most TMS vendors (Actimize, Oracle Mantas) include SAR filing integration
    # with the BSA E-Filing system directly in their case management module.
    # ──────────────────────────────────────────────────────────────────────────
    """
    customer_profile = state.get("customer_profile", {})
    patterns = state.get("transaction_patterns", {})
    watchlist_hits = state.get("watchlist_hits", [])
    network_graph = state.get("network_graph", {})
    adverse_media = state.get("adverse_media_hits", [])
    risk_factors = state.get("risk_factors", [])

    # ── PREPARE CUSTOMER IDENTITY INFORMATION ───────────────────────────────────
    # SAR Part I requires specific subject identification fields
    customer_name = (
        customer_profile.get("full_name") or
        customer_profile.get("entity_name") or
        f"Customer {state.get('customer_id', 'UNKNOWN')}"
    )
    account_ids = state.get("account_ids", [])
    # Mask account numbers per privacy/security requirements
    masked_accounts = [f"***{acc[-4:]}" if len(acc) >= 4 else acc for acc in account_ids]

    # ── EXTRACT KEY TRANSACTION PATTERN INFORMATION ─────────────────────────────
    pattern_summary = patterns.get("summary", {})
    suspicious_volume = pattern_summary.get("total_suspicious_volume", 0)
    activity_start = pattern_summary.get("activity_start_date", "Unknown")
    activity_end = pattern_summary.get("activity_end_date", "Unknown")
    primary_typology = pattern_summary.get("primary_typology", "Unknown suspicious activity")

    # ── FORMAT WATCHLIST FINDINGS ──────────────────────────────────────────────
    watchlist_text = "No watchlist hits identified."
    if watchlist_hits:
        watchlist_lines = []
        for hit in watchlist_hits:
            watchlist_lines.append(
                f"{hit.get('list_name', 'Unknown List')}: {hit.get('screened_name', 'Unknown')} "
                f"(match score: {hit.get('match_score', 0)}%)"
            )
        watchlist_text = "; ".join(watchlist_lines)

    # ── FORMAT NETWORK FINDINGS ────────────────────────────────────────────────
    network_findings_text = "Network analysis completed."
    llm_analysis = network_graph.get("llm_analysis", {})
    if llm_analysis:
        key_findings = llm_analysis.get("key_findings", [])
        if key_findings:
            network_findings_text = ". ".join(key_findings[:3])

    shell_count = len(network_graph.get("shell_company_findings", {}))
    circular_count = len(network_graph.get("circular_flows", []))
    if shell_count > 0 or circular_count > 0:
        network_findings_text += (
            f" {shell_count} suspected shell companies identified in counterparty network. "
            f"{circular_count} circular money flows detected."
        )

    # ── FORMAT ADVERSE MEDIA FINDINGS ──────────────────────────────────────────
    adverse_media_text = "No significant adverse media identified."
    if adverse_media:
        critical_hits = [h for h in adverse_media if h.get("severity") in ["CRITICAL", "HIGH"]]
        if critical_hits:
            adverse_media_text = (
                f"{len(adverse_media)} adverse media hits identified, including "
                f"{len(critical_hits)} HIGH/CRITICAL severity items: "
                + "; ".join([h.get("headline", "")[:100] for h in critical_hits[:2]])
            )

    # ── INVOKE LLM FOR SAR NARRATIVE ──────────────────────────────────────────
    try:
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.1,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        prompt = SAR_NARRATIVE_PROMPT.format(
            customer_name=customer_name,
            customer_id=state.get("customer_id", "UNKNOWN"),
            account_ids=", ".join(masked_accounts) if masked_accounts else "N/A",
            alert_type=state.get("alert_type", "Unknown"),
            investigation_period=f"{activity_start} to {activity_end}",
            transaction_patterns=json.dumps({
                "primary_typology": primary_typology,
                "suspicious_volume": suspicious_volume,
                "structuring": patterns.get("structuring", {}),
                "layering": patterns.get("layering", {}),
                "velocity_anomalies": patterns.get("velocity_anomalies", {}),
                "geographic_concentration": patterns.get("geographic_concentration", {}),
                "summary_note": pattern_summary.get("analyst_note", ""),
            }, indent=2),
            watchlist_findings=watchlist_text,
            network_findings=network_findings_text,
            adverse_media_findings=adverse_media_text,
            risk_score=state.get("risk_score", 0),
            risk_factors=json.dumps(risk_factors[:10], indent=2),  # Top 10 factors
            prior_sars=customer_profile.get("prior_sars", 0),
        )

        response = llm.invoke([HumanMessage(content=prompt)])

        # Try to parse as JSON (the prompt asks for JSON with "narrative" key)
        try:
            sar_data = json.loads(response.content)
            narrative = sar_data.get("narrative", response.content)
        except json.JSONDecodeError:
            # If not JSON, use the raw text as the narrative
            narrative = response.content

        logger.info(f"[sar_generator] SAR narrative generated — {len(narrative)} characters")
        return narrative

    except Exception as e:
        logger.error(f"[sar_generator] LLM error: {e}", exc_info=True)
        # Return a template narrative if LLM fails
        return _generate_template_narrative(state, customer_name, masked_accounts,
                                            suspicious_volume, activity_start, activity_end,
                                            primary_typology, watchlist_text, risk_factors)


def _generate_template_narrative(
    state: Dict[str, Any],
    customer_name: str,
    masked_accounts: List[str],
    suspicious_volume: float,
    activity_start: str,
    activity_end: str,
    primary_typology: str,
    watchlist_text: str,
    risk_factors: List[str],
) -> str:
    """
    Generate a template SAR narrative when the LLM is unavailable.
    This is a fallback that produces a structured but incomplete narrative
    requiring significant human editing before submission.
    """
    bank_name = os.getenv("BANK_NAME", "First National Bank")
    filing_date = datetime.utcnow().strftime("%B %d, %Y")

    narrative = f"""DRAFT SAR NARRATIVE — REQUIRES BSA OFFICER REVIEW AND EDITING BEFORE FILING
Generated: {filing_date} | Alert ID: {state.get('alert_id', 'UNKNOWN')} | Case ID: {state.get('case_id', 'PENDING')}

On {filing_date}, {bank_name} (the "Bank") identified suspicious financial activity associated with
customer {customer_name} (Customer ID: {state.get('customer_id', 'UNKNOWN')})
through account(s) {', '.join(masked_accounts) if masked_accounts else 'N/A'}.

SUSPICIOUS ACTIVITY DESCRIPTION:
The Bank's transaction monitoring system generated an alert indicating suspicious activity
consistent with {primary_typology}. The total volume of suspicious transactions identified
during the investigation period ({activity_start} to {activity_end}) is approximately
${suspicious_volume:,.2f}.

INVESTIGATION FINDINGS:
{chr(10).join(['- ' + factor for factor in risk_factors[:8]])}

WATCHLIST SCREENING:
{watchlist_text}

PRIOR ACTIVITY:
Prior SARs on this customer: {state.get('customer_profile', {}).get('prior_sars', 0)}

RECOMMENDED ACTION:
Based on the totality of the investigation findings, the Bank believes the above-described
activity is suspicious and potentially related to {primary_typology}. The Bank is filing
this SAR pursuant to 31 CFR § 1020.320.

[BSA OFFICER NOTE: This narrative requires completion before filing. Please add:
1. Specific transaction dates and amounts
2. Detailed description of why activity deviates from customer's normal profile
3. What investigative steps were taken to verify or explain the activity
4. Law enforcement contact information if applicable
5. Your professional assessment of the activity]

CONTACT INFORMATION:
Compliance Contact: [BSA Officer Name]
Phone: [BSA Officer Phone]
Institution: {bank_name}
Filing Deadline: {state.get('sar_filing_deadline', 'See BSA requirements')}

CONFIDENTIALITY: This SAR is protected from disclosure per 31 U.S.C. § 5318(g)(2).
Do not disclose to the subject or any unauthorized party."""

    return narrative


def format_sar_part_ii(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate structured FinCEN SAR Form 111 Part I & II fields.

    This function maps investigation findings to the specific fields
    required on the FinCEN SAR electronic form. These fields are
    submitted through the BSA E-Filing System at bsaefiling.fincen.treas.gov

    FinCEN SAR Form 111 key sections:
    - Part I: Reporting Financial Institution
    - Part II: Subject Information (who is doing the suspicious activity)
    - Part III: Suspicious Activity Information (what, when, how much)
    - Part IV: Law Enforcement Contact
    - Part V: Narrative (the text narrative generated above)

    Args:
        state: Full investigation state

    Returns:
        Dictionary mapping to FinCEN SAR form fields

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # To submit the SAR electronically:
    # 1. Format the fields below as FinCEN XML schema
    # 2. Submit via BSA E-Filing SOAP/REST API
    # 3. Retain the BSA E-Filing confirmation number (required for 5-year retention)
    #
    # Most enterprise TMS systems (Actimize, Oracle Mantas) have built-in
    # BSA E-Filing integration — work with your vendor to configure this.
    # ──────────────────────────────────────────────────────────────────────────
    """
    customer_profile = state.get("customer_profile", {})
    patterns = state.get("transaction_patterns", {})
    watchlist_hits = state.get("watchlist_hits", [])
    pattern_summary = patterns.get("summary", {})

    # Determine suspicious activity types (FinCEN checkbox categories)
    suspicious_activity_types = []
    if patterns.get("structuring", {}).get("detected"):
        suspicious_activity_types.append("BSA/Structuring/Money Laundering - Structuring")
    if patterns.get("layering", {}).get("detected"):
        suspicious_activity_types.append("BSA/Structuring/Money Laundering - Layering")
    if patterns.get("velocity_anomalies", {}).get("detected"):
        suspicious_activity_types.append("BSA/Structuring/Money Laundering - Unusual activity")
    if watchlist_hits:
        suspicious_activity_types.append("OFAC/Sanctions")
    if not suspicious_activity_types:
        suspicious_activity_types.append("BSA/Structuring/Money Laundering - Other")

    # Calculate BSA filing deadline
    detection_date = datetime.utcnow()
    has_subject = bool(
        customer_profile.get("full_name") or customer_profile.get("entity_name")
    )
    deadline_days = 30 if has_subject else 60
    filing_deadline = (detection_date + timedelta(days=deadline_days)).strftime("%Y-%m-%d")

    return {
        # Part I — Filing Institution
        "filing_institution": os.getenv("BANK_NAME", "First National Bank"),
        "filing_institution_ein": os.getenv("BANK_EIN", "**-*****"),
        "filing_institution_rssd_id": os.getenv("BANK_RSSD", "XXXXXXXXX"),
        "filing_contact_name": os.getenv("BSA_OFFICER_NAME", "[BSA Officer Name]"),
        "filing_contact_phone": os.getenv("BSA_OFFICER_PHONE", "[BSA Officer Phone]"),
        "filing_contact_email": os.getenv("BSA_OFFICER_EMAIL", "bsa@yourbank.com"),
        "filing_date": datetime.utcnow().strftime("%Y-%m-%d"),

        # Part II — Subject Information
        "subject_entity_name": customer_profile.get("entity_name"),
        "subject_last_name": customer_profile.get("full_name", "").split()[-1] if customer_profile.get("full_name") else None,
        "subject_first_name": customer_profile.get("full_name", "").split()[0] if customer_profile.get("full_name") else None,
        "subject_dob": customer_profile.get("date_of_birth"),
        "subject_ssn_ein": customer_profile.get("ssn_masked") or customer_profile.get("ein_masked"),
        "subject_address": customer_profile.get("address"),
        "subject_phone": customer_profile.get("phone"),
        "subject_occupation": customer_profile.get("occupation") or customer_profile.get("business_type"),
        "subject_id_type": customer_profile.get("id_document_type"),
        "subject_id_number": customer_profile.get("id_document_number"),

        # Account Information
        "account_numbers_involved": [
            f"***{acc[-4:]}" if len(acc) >= 4 else acc
            for acc in state.get("account_ids", [])
        ],
        "account_types": ["CHECKING", "SAVINGS"],  # Simplified for demo

        # Part III — Suspicious Activity Information
        "suspicious_activity_type": suspicious_activity_types,
        "amount_involved": pattern_summary.get("total_suspicious_volume", 0),
        "activity_start_date": pattern_summary.get("activity_start_date", "Unknown"),
        "activity_end_date": pattern_summary.get("activity_end_date", "Unknown"),
        "currencies_involved": ["USD"],

        # Law Enforcement
        "law_enforcement_contacted": False,  # Default — investigator updates if LE contacted
        "law_enforcement_agency": None,
        "law_enforcement_contact_name": None,
        "law_enforcement_phone": None,
        "law_enforcement_case_number": None,

        # Administrative
        "sar_filing_deadline": filing_deadline,
        "retention_expiry_date": (
            datetime.utcnow() + timedelta(days=1825)  # 5 years
        ).strftime("%Y-%m-%d"),
        "prior_sar_reference": f"SAR-{customer_profile.get('prior_sars', 0) > 0 and 'See file' or 'None'}",
        "continuing_activity": customer_profile.get("prior_sars", 0) > 0,

        # AI Model Documentation (for SR 11-7 compliance)
        "ai_model_used": "gpt-4o via OpenAI API",
        "ai_model_version": "gpt-4o-2024",
        "human_reviewer_required": True,
        "human_reviewer_approval_required_before_filing": True,
        "ai_confidence_score": state.get("risk_score", 0),
    }
