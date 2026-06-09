# agent/state.py
# ============================================================
# Trading Surveillance Agent — State Definitions
#
# TradingSurveillanceState: TypedDict (total=False) so all
# fields are optional at initialization. Each node populates
# its section of state as the workflow progresses.
# ============================================================
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


# ── Enumerations ──────────────────────────────────────────────────────────────

class AlertType(str, Enum):
    LAYERING_SPOOFING = "LAYERING_SPOOFING"
    FRONT_RUNNING = "FRONT_RUNNING"
    WASH_TRADING = "WASH_TRADING"
    INSIDER_TRADING = "INSIDER_TRADING"
    MARKING_THE_CLOSE = "MARKING_THE_CLOSE"
    EXCESSIVE_TRADING = "EXCESSIVE_TRADING"
    BEST_EXECUTION_FAILURE = "BEST_EXECUTION_FAILURE"
    SHORT_SELLING_VIOLATION = "SHORT_SELLING_VIOLATION"
    CROSS_MARKET_MANIPULATION = "CROSS_MARKET_MANIPULATION"
    INFORMATION_BARRIER_BREACH = "INFORMATION_BARRIER_BREACH"
    UNUSUAL_ACTIVITY = "UNUSUAL_ACTIVITY"


class SeverityTier(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    FIXED_INCOME = "FIXED_INCOME"
    DERIVATIVES = "DERIVATIVES"
    FX = "FX"
    COMMODITIES = "COMMODITIES"
    CRYPTO = "CRYPTO"


class DispositionOutcome(str, Enum):
    ESCALATED_TO_LEGAL = "ESCALATED_TO_LEGAL"
    SAR_FILED = "SAR_FILED"
    REFERRED_TO_REGULATOR = "REFERRED_TO_REGULATOR"
    INTERNAL_DISCIPLINE = "INTERNAL_DISCIPLINE"
    CLOSED_NO_ACTION = "CLOSED_NO_ACTION"
    CLOSED_EXPLAINED = "CLOSED_EXPLAINED"
    PENDING_INVESTIGATION = "PENDING_INVESTIGATION"


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    AWAITING_COMPLIANCE = "AWAITING_COMPLIANCE"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    CLOSED = "CLOSED"


# ── State TypedDict ────────────────────────────────────────────────────────────

class TradingSurveillanceState(TypedDict, total=False):
    """
    Complete state for the trading surveillance workflow.
    total=False: every field is Optional at initialization.
    Nodes populate only the fields they own.
    """

    # ── Alert Identification ───────────────────────────────────────────────
    alert_id: str
    alert_type: str                         # AlertType enum value
    alert_source: str                       # SURVEILLANCE_SYSTEM | MANUAL | REGULATORY_INQUIRY
    alert_timestamp: str                    # ISO-8601 UTC

    # ── Trade / Activity Data ──────────────────────────────────────────────
    trader_id: str
    trader_name: str
    desk: str                               # e.g., EQUITIES_PROP, FIXED_INCOME_MM, DERIVATIVES_STRUCTURING
    account_id: str
    instrument_id: str                      # ticker or ISIN
    instrument_name: str
    asset_class: str                        # AssetClass enum value
    trade_date: str
    notional_value: float
    trade_direction: str                    # BUY | SELL | BOTH
    quantity: float
    price: float
    counterparty: Optional[str]
    venue: str                              # NYSE | NASDAQ | OTC | DARK_POOL | CME
    raw_alert_data: Dict[str, Any]          # full alert payload from surveillance system

    # ── Data Enrichment ────────────────────────────────────────────────────
    trader_history_summary: str             # narrative of trader's prior alert record
    prior_alert_count: int                  # total prior alerts for this trader
    prior_alerts: List[Dict[str, Any]]      # prior alert records (last 12 months)
    account_risk_tier: str                  # HIGH_RISK | MEDIUM_RISK | STANDARD
    restricted_list_hit: bool               # instrument on firm restricted list
    watch_list_hit: bool                    # instrument on watch list (heightened scrutiny)
    pep_flag: bool                          # trader or counterparty PEP-related
    corroborating_signals: List[str]        # additional supporting signals detected
    market_context_summary: str             # relevant news / events for instrument + date

    # ── Pattern Detection ──────────────────────────────────────────────────
    detected_patterns: List[str]            # patterns identified by Python rule engine
    pattern_confidence_scores: Dict[str, float]  # pattern → confidence 0.0–1.0
    pattern_rationale: str                  # explanation of why patterns triggered
    regulatory_flags: List[str]             # specific regulations potentially implicated

    # ── Risk Scoring ──────────────────────────────────────────────────────
    # ALL scoring is Python-only (SR 11-7 / FINRA Rule 3110 documented)
    risk_score: float                       # composite 0.0–1.0
    severity_tier: str                      # SeverityTier enum value
    risk_score_components: Dict[str, float] # factor-by-factor breakdown
    score_rationale: str                    # plain-language score explanation

    # ── Routing ────────────────────────────────────────────────────────────
    primary_reviewer: str                   # role assigned as case owner
    secondary_reviewers: List[str]          # additional notification recipients
    human_review_required: bool             # CRITICAL/HIGH → True
    escalation_reason: str

    # ── Human Review Gate ──────────────────────────────────────────────────
    reviewer_id: str
    reviewer_decision: str                  # INVESTIGATE | ESCALATE | CLOSE_EXPLAINED | CLOSE_NO_ACTION
    reviewer_notes: str
    review_timestamp: str

    # ── Investigation ──────────────────────────────────────────────────────
    investigation_narrative: str            # LLM-synthesized investigation summary
    evidence_summary: List[str]             # key evidence items (chronological)
    is_suspicious: Optional[bool]           # investigator determination

    # ── Disposition ────────────────────────────────────────────────────────
    disposition_outcome: str                # DispositionOutcome enum value
    disposition_memo: str                   # LLM-drafted formal disposition memorandum
    sar_consideration: bool                 # whether SAR should be considered (BSA)
    sar_rationale: str                      # rationale for SAR determination
    regulatory_reporting_required: bool     # FINRA/SEC/CFTC reporting required?
    regulatory_reporting_bodies: List[str]  # bodies to be notified

    # ── Case Register ──────────────────────────────────────────────────────
    case_register_entry: Dict[str, Any]
    case_status: str                        # CaseStatus enum value

    # ── Audit Trail ───────────────────────────────────────────────────────
    audit_trail: List[Dict[str, Any]]
    completed_steps: List[str]
    errors: List[str]
