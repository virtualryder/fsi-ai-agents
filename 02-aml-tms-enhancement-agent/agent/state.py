"""
AML/TMS Enhancement Agent — State Schema
Pre-queue alert scoring state for false positive reduction.

Regulatory basis: SR 11-7 (Model Risk Management) requires explainable,
auditable AI scoring decisions. Every alert suppression must be logged with
a factor-by-factor justification that a BSA Officer can review and override.

Design: All fields use total=False so the TypedDict is valid at initialization
with just the raw alert. Each node populates its slice of the state as the
graph executes.
"""
from __future__ import annotations
from typing import TypedDict, Optional, List, Dict, Any, Literal


class AuditEntry(TypedDict):
    timestamp: str
    actor: str                    # "AI_SCORING_AGENT" or analyst user ID
    action: str
    details: Dict[str, Any]
    data_sources: List[str]
    ai_model_used: Optional[str]  # e.g. "claude-sonnet-4-6" — required by SR 11-7


class RawAlert(TypedDict):
    alert_id: str
    customer_id: str
    alert_type: str               # STRUCTURING | VELOCITY | HIGH_RISK_GEOGRAPHY | RAPID_MOVEMENT | ...
    triggered_rule: str           # Vendor-specific rule ID (e.g. "CASH_STRUCTURING_10K")
    severity: str                 # HIGH | MEDIUM | LOW (TMS-assigned)
    amount: float
    currency: str
    alert_date: str               # ISO 8601
    transaction_ids: List[str]
    tms_vendor: str               # actimize | verafin | nice | oracle_mantas
    raw_data: Dict[str, Any]      # Vendor-specific payload


class CustomerSummary(TypedDict):
    customer_id: str
    full_name: str
    risk_tier: str                # LOW | MEDIUM | HIGH | VERY_HIGH
    business_type: str            # restaurant | retail | individual_consumer | shell_company | ...
    account_age_days: int
    expected_monthly_cash_volume: float
    expected_monthly_wire_volume: float
    open_investigation_count: int
    prior_sars_filed: int
    prior_ctrs_filed: int
    pep_flag: bool
    edd_active: bool              # Enhanced Due Diligence currently active
    beneficial_owners: List[Dict[str, Any]]
    historical_fp_rate: float     # 0.0–1.0: fraction of this customer's past alerts that were FPs


class HistoricalPatterns(TypedDict):
    rule_fp_rate: float           # Bank-wide FP rate for the triggered rule (0.0–1.0)
    typology_fp_rate: float       # Bank-wide FP rate for this alert typology (0.0–1.0)
    peer_group_fp_rate: float     # FP rate for customers with same business_type + risk_tier
    customer_alert_history: List[Dict[str, Any]]  # Past alerts with outcomes
    customer_fp_rate: float       # Derived: fraction of customer's past alerts that were FPs
    days_since_last_similar_alert: int            # -1 if no prior similar alert


class ScoringFeatures(TypedDict):
    # Alert characteristics
    alert_type: str
    triggered_rule: str
    tms_severity: str
    amount_usd: float
    transaction_count: int
    time_window_days: int

    # Customer characteristics
    risk_tier: str
    account_age_days: int
    business_type: str
    amount_vs_expected_ratio: float   # alert amount / expected monthly volume; >1 = above expected
    pep_flag: bool
    edd_active: bool
    prior_sars_filed: int
    prior_ctrs_filed: int

    # Historical signals (strong FP predictors)
    rule_fp_rate: float               # Bank-wide historical FP rate for this rule
    typology_fp_rate: float
    peer_group_fp_rate: float
    customer_historical_fp_rate: float
    customer_prior_alert_count: int
    days_since_last_similar_alert: int

    # Contextual signals
    has_open_investigation: bool
    high_risk_geography: bool         # Destination country on FinCEN/FATF watch list
    is_weekend: bool
    is_month_end: bool                # Month-end activity is a known FP driver for businesses


class RoutingDecision(TypedDict):
    decision: Literal["SUPPRESS", "DOWNGRADE", "PASS_THROUGH", "ESCALATE"]
    fp_probability: float             # 0–100: final composite FP probability
    confidence: float                 # 0–1: model confidence in this estimate
    primary_reason: str               # One-sentence reason for the audit log
    suppression_factors: List[str]    # Evidence supporting suppression/downgrade
    pass_through_factors: List[str]   # Evidence arguing against suppression
    recommended_priority: str         # HIGH | MEDIUM | LOW (for pass-through or downgrade)
    regulatory_override: bool         # True if a mandatory rule forced the decision
    regulatory_override_reason: str


class AlertScoringState(TypedDict, total=False):
    """
    Accumulated state for one alert's journey through the pre-queue scoring graph.

    Initialized with raw_alert only. Each node adds its output to the state
    and appends an entry to audit_trail. The graph router reads `routing.decision`
    to branch to the correct action node.
    """

    # ── Input ──────────────────────────────────────────────────────────────
    raw_alert: RawAlert
    alert_id: str
    customer_id: str
    ingested_at: str              # ISO 8601 timestamp when alert entered scoring pipeline

    # ── Scoring inputs ──────────────────────────────────────────────────────
    customer_summary: CustomerSummary
    historical_patterns: HistoricalPatterns
    scoring_features: ScoringFeatures

    # ── Rule-based pre-filter ───────────────────────────────────────────────
    # Fast, deterministic scoring applied before the LLM call.
    # Catches obvious FPs (e.g. rule FP rate > 90%) without spending tokens.
    rule_based_fp_score: float    # 0–100
    rule_based_factors: List[str] # Which rules fired

    # ── LLM analysis ───────────────────────────────────────────────────────
    llm_fp_probability: float     # 0–100: LLM's estimated FP probability
    llm_confidence: float         # 0–1
    llm_recommendation: str       # SUPPRESS | DOWNGRADE | PASS_THROUGH | ESCALATE
    llm_primary_reason: str
    llm_suppression_factors: List[str]
    llm_pass_through_factors: List[str]
    llm_analysis_narrative: str   # 2–3 paragraph reasoning for audit log
    llm_regulatory_override: bool
    llm_regulatory_override_reason: str

    # ── Composite score ─────────────────────────────────────────────────────
    composite_fp_score: float     # Final weighted composite (0–100)
    score_breakdown: Dict[str, float]  # component → weighted contribution

    # ── Routing decision ────────────────────────────────────────────────────
    routing: RoutingDecision

    # ── Actions taken ───────────────────────────────────────────────────────
    queue_action: str             # "suppressed" | "downgraded" | "queued" | "escalated"
    tms_updated: bool             # Whether TMS was notified of decision
    downstream_queue_notified: bool  # Whether investigation agent queue was notified

    # ── Suppression record ─────────────────────────────────────────────────
    # Required fields for any alert suppression (BSA/SR 11-7)
    suppression_id: Optional[str]           # UUID; None if not suppressed
    suppression_timestamp: Optional[str]
    suppression_justification: Optional[str]  # Full regulatory-grade narrative
    suppression_review_date: Optional[str]    # 90-day mandatory review date

    # ── Timing ──────────────────────────────────────────────────────────────
    scored_at: Optional[str]
    processing_time_ms: Optional[int]

    # ── Error handling ──────────────────────────────────────────────────────
    errors: List[str]
    fallback_to_manual: bool      # True if scoring failed → route alert to analyst regardless

    # ── Audit trail (append-only, required by BSA / SR 11-7) ───────────────
    audit_trail: List[AuditEntry]
    scoring_notes: List[str]
