# agent/state.py
# ============================================================
# InvestigationState — The complete state object for an AML investigation
#
# Regulatory context:
#   Every field in this state corresponds to data elements required by:
#   - FinCEN SAR Form (FinCEN 111) — subject info, account info, suspicious activity
#   - BSA examination expectations — documented analysis, risk basis, disposition rationale
#   - FATF Recommendation 20 — comprehensive suspicious transaction reporting
#   - OCC Examination Handbook (BSA/AML) — evidence of risk-based investigation
#
# Audit requirement:
#   The audit_trail field ensures every agent action is logged with timestamp,
#   actor, and action taken — this is a first-class regulatory requirement.
#   Examiners (OCC, FDIC, FinCEN, state regulators) will review this trail.
#
# Human-in-the-loop:
#   The investigation state is designed to support interruption at the
#   human_review_gate node, where a licensed BSA officer reviews AI findings
#   before any SAR is filed. The AI NEVER autonomously files a SAR.
# ============================================================

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class RecommendedAction(str, Enum):
    """
    The three possible dispositions for an AML investigation.

    CLOSE:    Investigation found no credible suspicious activity.
              The alert was a false positive. Document the rationale.
              BSA requires retaining even closed case records for 5 years.

    ESCALATE: Evidence is present but insufficient or ambiguous.
              Route to senior analyst, EDD team, or compliance officer.
              May also trigger a 314(b) information sharing request.

    FILE_SAR: Clear indicators of suspicious activity meeting the BSA
              threshold ($5,000+ for banks, $2,000+ for MSBs).
              SAR must be filed within 30 days of determination.
              No tipping off the subject (18 U.S.C. § 1960).
    """
    CLOSE = "CLOSE"
    ESCALATE = "ESCALATE"
    FILE_SAR = "FILE_SAR"


class InvestigationState(TypedDict, total=False):
    """
    Complete state for a single AML investigation case.

    This TypedDict is passed through every node in the LangGraph DAG.
    Each node reads what it needs and writes its findings back into state.
    The state accumulates evidence as the investigation progresses —
    exactly mirroring how a human investigator builds a case file.

    total=False means all fields are optional at initialization,
    which allows the graph to populate them incrementally.
    """

    # ── Alert / Trigger Information ────────────────────────────────────────────
    # These fields come from the Transaction Monitoring System (TMS) that
    # generated the alert. They are the starting point of every investigation.

    alert_id: str
    # Unique identifier for the TMS alert (e.g., "ALT-2024-001234")

    alert_type: str
    # Category: STRUCTURING, RAPID_MOVEMENT, HIGH_RISK_GEOGRAPHY,
    # VELOCITY_ANOMALY, SMURFING, LAYERING, PEP_TRANSACTION, etc.

    alert_severity: str
    # HIGH, MEDIUM, or LOW — drives investigation priority queue
    # HIGH alerts must be assigned within 24 hours per most bank policies

    alert_source: str
    # Which TMS rule or model triggered this: "Rule-Based", "ML-Model", "Manual"
    # ML-model alerts require model risk documentation (SR 11-7 compliance)

    alert_date: str
    # ISO 8601 date when the TMS generated the alert

    triggered_rule: str
    # The specific rule or model ID that fired (e.g., "CASH-STRUCT-001")

    # ── Customer / Subject Information ─────────────────────────────────────────
    # FinCEN SAR Part I requires: subject name, address, DOB/EIN, account numbers
    # These fields directly map to SAR filing requirements.

    customer_id: str
    # Internal customer identifier from core banking system

    account_ids: List[str]
    # All account numbers associated with this investigation
    # Multiple accounts are common for structuring across accounts

    customer_profile: Dict[str, Any]
    # Full KYC record including:
    #   - customer_type: INDIVIDUAL or ENTITY
    #   - risk_tier: LOW / MEDIUM / HIGH / VERY_HIGH
    #   - kyc_date: When KYC was last refreshed
    #   - edd_status: Whether Enhanced Due Diligence is active
    #   - pep_flag: Politically Exposed Person indicator
    #   - beneficial_owners: UBO structure (FATF R.10 requirement)
    #   - business_type: Industry/NAICS code (for cash-intensive businesses)

    # ── Transaction Data ────────────────────────────────────────────────────────
    # The transaction record is the core evidentiary basis for AML.
    # BSA requires investigation of all transactions related to suspected activity.

    transactions: List[Dict[str, Any]]
    # Full 12-month transaction history for all involved accounts
    # Each transaction dict includes: date, amount, type, counterparty,
    # channel, currency, reference, originating country

    transaction_patterns: Dict[str, Any]
    # Detected patterns from the transaction_analysis node:
    #   - structuring_indicators: sub-threshold deposits
    #   - layering_indicators: rapid in/out with intermediaries
    #   - smurfing_indicators: multiple individuals depositing for one account
    #   - velocity_anomalies: spending/deposit spikes vs. baseline
    #   - round_dollar_flows: suspiciously round amounts
    #   - geographic_concentration: concentration in high-risk jurisdictions
    #   - dormancy_then_activity: account woke up suddenly

    # ── Watchlist / Sanctions Results ──────────────────────────────────────────
    # OFAC screening is a LEGAL REQUIREMENT — not optional.
    # OFAC violations can result in civil/criminal penalties up to $20M per violation.
    # Banks must screen customers, beneficial owners, and all counterparties.

    watchlist_hits: List[Dict[str, Any]]
    # Each hit includes: list_name, matched_name, match_score, hit_type,
    # SDN_id (if OFAC), designation_reason, match_date

    # ── Adverse Media ──────────────────────────────────────────────────────────
    # Adverse media screening is a best-practice / FATF R.12 expectation.
    # Regulators look for evidence that banks check public negative news.

    adverse_media_hits: List[Dict[str, Any]]
    # Each hit includes: source, headline, date, category, url, relevance_score
    # Categories: fraud, corruption, drug_trafficking, terrorism, money_laundering

    # ── Network Analysis ───────────────────────────────────────────────────────
    # Counterparty analysis reveals the broader network of suspicious actors.
    # FATF R.20 expects banks to consider the "network" around a transaction.

    network_graph: Dict[str, Any]
    # Graph structure:
    #   - nodes: list of entities (customers, counterparties, intermediaries)
    #   - edges: list of transactions between nodes
    #   - shell_company_flags: entities with shell company indicators
    #   - circular_flows: money leaving and returning (classic layering)
    #   - hops_to_known_bad_actor: shortest path to sanctioned/flagged entity
    #   - high_risk_jurisdictions: countries involved in flows

    # ── Risk Assessment ────────────────────────────────────────────────────────
    # The composite risk score supports the routing decision.
    # This score is ADVISORY — the human investigator makes the final call.
    # Model risk (SR 11-7): this model must be validated before production use.

    risk_score: float
    # 0-100 composite score. Thresholds: <30=close, 30-70=escalate, >70=SAR

    risk_factors: List[str]
    # Human-readable list of the specific factors driving the score.
    # Example: "OFAC SDN match on counterparty Acme Holdings LLC (score: 87/100)"
    # These factors must be documented in the SAR narrative.

    # ── Investigation Narrative ─────────────────────────────────────────────────
    # The investigation_notes field is the running narrative — equivalent to
    # the investigator's case notes. These feed directly into the SAR narrative.

    investigation_notes: List[str]
    # Chronological notes from each investigation step.
    # BSA examiners will read these to assess investigation quality.

    # ── Disposition ────────────────────────────────────────────────────────────

    recommended_action: RecommendedAction
    # The AI's recommended disposition. MUST be reviewed by a human.
    # The routing_decision node sets this based on risk_score thresholds.

    # ── SAR Draft ──────────────────────────────────────────────────────────────
    # Only populated when recommended_action == FILE_SAR.
    # The SAR narrative must follow FinCEN guidelines (FIN-2014-G001):
    #   - Who is conducting the suspicious activity
    #   - What suspicious activity was conducted
    #   - When the activity occurred
    #   - Where the activity took place
    #   - Why the activity is suspicious
    #   - How the activity was conducted

    sar_narrative: str
    # Full BSA-compliant SAR Part II narrative text
    # Target length: 500-2000 words per FinCEN quality guidance

    sar_fields: Dict[str, Any]
    # Structured FinCEN SAR form fields for Part I and Part II

    sar_filing_deadline: str
    # ISO 8601 deadline date. BSA: 30 days from determination date.
    # If no identified subject: 60 days from detection date.

    # ── Case Management ────────────────────────────────────────────────────────

    case_id: str
    # Case management system ID (e.g., "CASE-2024-00892")
    # This links the investigation to the case management system audit trail.

    investigator_id: str
    # The licensed BSA officer / analyst assigned to this case
    # Only licensed BSA officers can approve SAR filings.

    case_status: str
    # OPEN, PENDING_REVIEW, ESCALATED, SAR_FILED, CLOSED

    # ── LangGraph Infrastructure ───────────────────────────────────────────────

    messages: List[Any]
    # LangChain message history for multi-turn LLM interactions.
    # Stores the conversation between the agent and the LLM.

    current_step: str
    # Name of the currently executing graph node.
    # Used by the Streamlit UI to show real-time progress.

    completed_steps: List[str]
    # List of all nodes that have completed successfully.
    # Used to determine which results to display in the UI.

    errors: List[Dict[str, Any]]
    # Error records from failed steps. Format:
    #   {"step": str, "error": str, "timestamp": str, "recoverable": bool}
    # The investigation continues on non-fatal errors.

    # ── Audit Trail ────────────────────────────────────────────────────────────
    # REGULATORY REQUIREMENT: Every action taken during an investigation
    # must be logged with who did it, what they did, and when.
    # This is equivalent to the chain of custody in a law enforcement case.
    # BSA examiners WILL review this during examinations.

    audit_trail: List[Dict[str, Any]]
    # Each entry: {
    #   "timestamp": ISO 8601 datetime,
    #   "actor": "system" | investigator_id | "ai_agent",
    #   "action": str description of what was done,
    #   "node": graph node name,
    #   "data_sources_accessed": list of systems queried,
    #   "ai_model_used": model name if LLM was invoked,
    #   "human_review_required": bool
    # }
