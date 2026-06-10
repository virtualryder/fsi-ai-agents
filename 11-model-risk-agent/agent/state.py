"""
Agent 11 — Model Risk Management Agent
State definition: TypedDict with full model validation lifecycle fields.

SR 11-7 requires that model risk be documented, bounded, and subject to
independent validation. Every field in this state is designed to support
examination-ready reporting: each decision (risk tier, validation outcome,
performance metrics) is traceable to its source (Python constant, model
output, or human reviewer decision).

Design principles:
- All model risk determinations (tier, performance flags, HITL triggers)
  are Python — not LLM output
- LLM is used only for narrative: conceptual soundness review, findings
  summary, recommendations, validation report draft
- Validation outcomes are append-only in the audit trail
- Model inventory updates require human reviewer approval via HITL gate
"""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


# ── Validation request types ──────────────────────────────────────────────────
# Each type triggers a different validation scope and HITL threshold.
# INITIAL_VALIDATION and CHANGE_VALIDATION always require HITL for HIGH-tier
# models because model deployment / change approval requires documented sign-off.
VALIDATION_TYPES = {
    "INITIAL_VALIDATION": "New model deployment — full validation scope required",
    "ANNUAL_REVALIDATION": "Scheduled annual review — all SR 11-7 components",
    "TRIGGERED_REVIEW": "Performance degradation detected — urgent review",
    "CHANGE_VALIDATION": "Model change event (weight/threshold/feature update)",
    "ONGOING_MONITORING": "Routine monthly/quarterly performance monitoring",
}

# ── Model risk tiers (SR 11-7 §§ 5-6) ────────────────────────────────────────
# Tier drives validation frequency, HITL requirements, and documentation depth.
# HIGH: systemic risk or loss potential > $10M — mandatory HITL for all
#       validation types, annual revalidation, challenger model required
# MEDIUM: material impact $1M-$10M — HITL for triggered reviews and changes,
#         annual revalidation, benchmark comparison recommended
# LOW: limited impact < $1M — HITL for triggered reviews, 18-month revalidation
MODEL_RISK_TIERS = {
    "HIGH": {
        "loss_threshold_usd": 10_000_000,
        "revalidation_months": 12,
        "hitl_required": True,
        "challenger_required": True,
        "description": "Systemic or high-loss-potential model — mandatory annual independent validation",
    },
    "MEDIUM": {
        "loss_threshold_usd": 1_000_000,
        "revalidation_months": 12,
        "hitl_required": False,  # except triggered/change reviews
        "challenger_required": False,
        "description": "Material impact — annual revalidation, benchmark comparison recommended",
    },
    "LOW": {
        "loss_threshold_usd": 0,
        "revalidation_months": 18,
        "hitl_required": False,
        "challenger_required": False,
        "description": "Limited impact — 18-month revalidation cycle, ongoing monitoring",
    },
}

# ── Models in the FSI AI Suite that this agent validates ─────────────────────
# Each entry describes the scoring model's weights, thresholds, and tier.
# This registry is the source of truth for what Agent 11 validates.
# Validators check these against actual model outputs during validation.
MODEL_REGISTRY = {
    "AGT02-FP-SCORE-v1": {
        "agent": "02",
        "agent_name": "AML/TMS Enhancement Agent",
        "model_name": "False Positive Probability Composite",
        "model_type": "COMPOSITE_SCORING",
        "risk_tier": "HIGH",
        "weights": {
            "rule_based_prescore": 0.30,
            "llm_contextual": 0.50,
            "historical_fp_rates": 0.20,
        },
        "decision_thresholds": {
            "SUPPRESS": 0.85,
            "DOWNGRADE": 0.60,
            "PASS_THROUGH": 0.15,
            "ESCALATE": 0.0,
        },
        "hard_rules": ["PEP_flag → always ESCALATE", "HIGH_RISK_GEO + LARGE_WIRE + NEW_ACCOUNT → always ESCALATE"],
        "revalidation_months": 12,
    },
    "AGT03-KYC-RISK-v1": {
        "agent": "03",
        "agent_name": "KYC/CDD Perpetual Monitoring Agent",
        "model_name": "8-Factor Customer Risk Score",
        "model_type": "WEIGHTED_RISK_SCORE",
        "risk_tier": "HIGH",
        "weights": {
            "transaction_behavior": 0.20,
            "pep_flag": 0.15,
            "adverse_media": 0.15,
            "jurisdiction": 0.15,
            "documents": 0.10,
            "beneficial_ownership": 0.10,
            "industry": 0.10,
            "tenure": 0.05,
        },
        "decision_thresholds": {
            "ESCALATE": 0.85,
            "EDD_REQUIRED": 0.65,
            "PASS": 0.40,
            "EXIT": None,  # Rule-based, not score-based
        },
        "hard_rules": ["OFAC_hit → ESCALATE always", "PEP_flag → minimum EDD_REQUIRED"],
        "revalidation_months": 12,
    },
    "AGT04-FRAUD-SCORE-v1": {
        "agent": "04",
        "agent_name": "Real-Time Fraud Detection Agent",
        "model_name": "Fraud Detection Composite Score",
        "model_type": "COMPOSITE_SCORING",
        "risk_tier": "HIGH",
        "weights": {
            "rule_engine": 0.30,
            "llm_analysis": 0.50,
            "historical_pattern": 0.20,
        },
        "decision_thresholds": {
            "BLOCK": 85,
            "STEP_UP_AUTH": 65,
            "ANALYST_REVIEW": 40,
            "ALLOW": 0,
        },
        "hard_rules": [
            "confirmed_fraud_ip (RULE-091) → BLOCK regardless of score",
            "tor_exit_node (RULE-092) → BLOCK regardless of score",
        ],
        "revalidation_months": 12,
    },
    "AGT07-SURV-RISK-v1": {
        "agent": "07",
        "agent_name": "Trading Surveillance Agent",
        "model_name": "5-Factor Trading Surveillance Risk Score",
        "model_type": "WEIGHTED_RISK_SCORE",
        "risk_tier": "HIGH",
        "weights": {
            "pattern_severity": 0.25,
            "trade_size": 0.25,
            "recidivism": 0.20,
            "regulatory_exposure": 0.15,
            "evidence_quality": 0.15,
        },
        "decision_thresholds": {
            "CRITICAL": 0.85,
            "HIGH": 0.65,
            "MEDIUM": 0.40,
            "LOW": 0.0,
        },
        "hard_rules": [
            "INSIDER_TRADING → always CRITICAL + mandatory HITL",
            "INFORMATION_BARRIER_BREACH → always CRITICAL + mandatory HITL",
            "CROSS_MARKET_MANIPULATION → always CRITICAL + mandatory HITL",
        ],
        "revalidation_months": 12,
    },
    "AGT08-CREDIT-SCORE-v1": {
        "agent": "08",
        "agent_name": "Credit Underwriting Agent",
        "model_name": "5-Factor Credit Underwriting Composite",
        "model_type": "COMPOSITE_SCORING",
        "risk_tier": "HIGH",
        "weights": {
            "credit_quality": 0.30,
            "dti_analysis": 0.25,
            "ltv_analysis": 0.20,
            "cash_flow": 0.15,
            "collateral": 0.10,
        },
        "decision_thresholds": {
            "APPROVE": 0.70,
            "APPROVE_WITH_CONDITIONS": 0.55,
            "REFER": 0.40,
            "DECLINE": 0.0,
        },
        "hard_rules": [
            "DTI > 50% → DECLINE (all loan types)",
            "FICO < 580 conventional → DECLINE_HARD_BLOCK",
            "Chapter_7 < 2 years → DECLINE_HARD_BLOCK",
            "OFAC_hit → DECLINE_HARD_BLOCK (unresetable)",
        ],
        "revalidation_months": 12,
    },
}

# ── Performance degradation thresholds (SR 11-7 ongoing monitoring) ───────────
# When these thresholds are exceeded, a TRIGGERED_REVIEW is initiated.
# These are Python constants — not configurable at runtime.
PERFORMANCE_DEGRADATION_THRESHOLDS = {
    "accuracy_drop_pct": 5.0,       # >5% accuracy decline triggers review
    "gini_drop_points": 10.0,       # >10 Gini point decline triggers review
    "ks_stat_drop_pct": 8.0,        # >8% KS statistic decline triggers review
    "psi_warning": 0.10,            # PSI 0.10-0.25 = population shift warning
    "psi_critical": 0.25,           # PSI >0.25 = significant population shift
    "false_positive_rate_increase": 0.05,  # >5pp FPR increase triggers review
    "false_negative_rate_increase": 0.03,  # >3pp FNR increase triggers review (higher sensitivity for risk)
}

# ── Validation outcomes ────────────────────────────────────────────────────────
VALIDATION_OUTCOMES = {
    "APPROVED": "Model approved for continued use without conditions",
    "CONDITIONALLY_APPROVED": "Model approved with specific conditions that must be remediated",
    "UNDER_REVIEW": "Validation in progress — model use may continue with enhanced monitoring",
    "SUSPENDED": "Model use suspended pending remediation — manual process required",
    "RETIRED": "Model decommissioned — successor model required before retirement",
}

# ── HITL always-required conditions ─────────────────────────────────────────
# Any of these conditions forces a human Model Risk Officer review.
# frozenset enforces immutability — cannot be modified by any code path.
ALWAYS_HITL_CONDITIONS = frozenset({
    "HIGH_TIER_INITIAL_VALIDATION",
    "HIGH_TIER_CHANGE_VALIDATION",
    "PERFORMANCE_DEGRADATION_TRIGGERED",
    "PSI_CRITICAL",                 # PSI > 0.25 — significant population shift
    "ANNUAL_REVALIDATION_HIGH_TIER",
    "MATERIAL_FINDING",             # Validator identifies a material model limitation
    "CHALLENGER_UNDERPERFORMS",     # Production model underperforms challenger
    "HARD_RULE_VIOLATION_DETECTED", # A hard rule was circumvented in production logs
    "FAIR_LENDING_FLAG",            # Fair lending / disparate impact concern raised
})

# ── Reviewer decisions ────────────────────────────────────────────────────────
REVIEWER_DECISIONS = {
    "APPROVE_VALIDATION": "Validation complete — model approved",
    "CONDITIONALLY_APPROVE": "Validation complete — model approved with conditions",
    "REQUIRE_REMEDIATION": "Model must be remediated before approval — use suspended",
    "ESCALATE_TO_BOARD": "Findings escalated to Board Risk Committee or senior management",
}

# ── Performance metric labels ──────────────────────────────────────────────
METRIC_LABELS = {
    "accuracy": "Prediction Accuracy (%)",
    "precision": "Precision (True Positive Rate)",
    "recall": "Recall (Sensitivity)",
    "f1_score": "F1 Score",
    "gini_coefficient": "Gini Coefficient (0-100)",
    "ks_statistic": "Kolmogorov-Smirnov Statistic",
    "psi": "Population Stability Index",
    "auc_roc": "Area Under ROC Curve",
    "false_positive_rate": "False Positive Rate (%)",
    "false_negative_rate": "False Negative Rate (%)",
}


# ── LangGraph State ───────────────────────────────────────────────────────────

class ModelRiskState(TypedDict, total=False):
    """
    State object for the Model Risk Management Agent's 12-node LangGraph DAG.

    total=False means all keys are optional — each node adds its outputs
    to the state without requiring prior nodes' outputs to be pre-populated.
    This allows LangGraph to checkpointer only the fields that exist.

    Security note: no model training data, raw predictions, or customer PII
    flows through this state. The agent validates model design, weights,
    thresholds, and aggregate performance metrics — not individual predictions.
    """

    # ── Validation request ────────────────────────────────────────────────
    model_id: str                           # Registry key (e.g., "AGT02-FP-SCORE-v1")
    validation_type: str                    # From VALIDATION_TYPES keys
    validation_id: str                      # Unique validation run ID
    requested_by: str                       # Role/team initiating validation
    validation_period_start: str            # ISO date: start of performance window
    validation_period_end: str              # ISO date: end of performance window
    triggering_event: Optional[str]         # For TRIGGERED_REVIEW: what triggered it

    # ── Model registry lookup ─────────────────────────────────────────────
    model_record: Optional[Dict[str, Any]]  # Full record from MODEL_REGISTRY
    risk_tier: Optional[str]                # HIGH / MEDIUM / LOW
    last_validation_date: Optional[str]     # ISO date of prior validation
    days_since_last_validation: Optional[int]
    revalidation_overdue: bool              # True if past scheduled revalidation date

    # ── Performance metrics (Python-computed) ──────────────────────────────
    current_metrics: Optional[Dict[str, float]]   # Current period metrics
    baseline_metrics: Optional[Dict[str, float]]  # Prior validation baseline
    metric_deltas: Optional[Dict[str, float]]     # Current - baseline
    psi_score: Optional[float]                    # Population Stability Index
    psi_flag: Optional[str]                       # STABLE / WARNING / CRITICAL
    degradation_flags: List[str]                  # List of triggered degradation conditions

    # ── Outcomes analysis (Python-computed) ────────────────────────────────
    performance_outcome: Optional[str]      # PASS / DEGRADED / CRITICAL
    material_findings: List[str]            # Specific material model limitations found
    hard_rule_violations: List[str]         # Any hard rules found violated in production

    # ── Challenger / benchmark comparison (Python-computed) ────────────────
    challenger_available: bool
    challenger_metrics: Optional[Dict[str, float]]
    challenger_comparison_result: Optional[str]  # PRODUCTION_BETTER / CHALLENGER_BETTER / PARITY

    # ── SR 11-7 validation components ──────────────────────────────────────
    conceptual_soundness_narrative: Optional[str]   # LLM: design and assumption review
    outcomes_analysis_summary: Optional[str]        # LLM: performance metric interpretation
    ongoing_monitoring_assessment: Optional[str]    # LLM: monitoring adequacy review
    sensitivity_analysis_results: Optional[Dict[str, Any]]  # Python: stress-test results

    # ── Risk determination (Python-computed) ───────────────────────────────
    validation_risk_score: Optional[float]  # 0.0-1.0 composite validation risk
    hitl_conditions: List[str]              # Conditions triggering HITL from ALWAYS_HITL_CONDITIONS
    human_review_required: bool             # True if any HITL condition met

    # ── LLM validation report (narrative only) ─────────────────────────────
    validation_report_draft: Optional[str]  # Full SR 11-7 validation report narrative
    findings_summary: Optional[str]         # Concise findings for HITL reviewer
    recommendations: Optional[str]          # Specific remediation recommendations

    # ── Routing ─────────────────────────────────────────────────────────────
    target_reviewer: Optional[str]          # MODEL_RISK_OFFICER / CHIEF_RISK_OFFICER / BOARD
    resolution_type: Optional[str]          # From VALIDATION_OUTCOMES keys

    # ── Human review ────────────────────────────────────────────────────────
    reviewer_id: Optional[str]
    reviewer_decision: Optional[str]        # From REVIEWER_DECISIONS keys
    reviewer_conditions: Optional[str]      # Specific conditions if CONDITIONALLY_APPROVE
    reviewer_notes: Optional[str]
    reviewer_timestamp: Optional[str]

    # ── Final disposition ───────────────────────────────────────────────────
    validation_outcome: Optional[str]       # From VALIDATION_OUTCOMES keys
    model_approval_status: Optional[str]    # Updated status to write back to registry
    next_revalidation_date: Optional[str]   # Computed ISO date

    # ── Audit trail ──────────────────────────────────────────────────────────
    # Append-only: nodes use list(current) + [new_entry] — never modify prior entries.
    # Every entry includes node name, timestamp, and key decision data.
    audit_trail: List[Dict[str, Any]]

    # ── Error handling ────────────────────────────────────────────────────
    error_message: Optional[str]
    demo_mode: bool                         # True when no OpenAI API key present
