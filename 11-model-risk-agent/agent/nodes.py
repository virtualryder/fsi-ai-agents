"""
Agent 11 — Model Risk Management Agent
Node functions: 12-node LangGraph DAG

SR 11-7 ARCHITECTURE ENFORCEMENT:
Every compliance determination in this file is implemented in Python.
The LLM's role is strictly narrative drafting. Python determines:
  - Model risk tier (from MODEL_REGISTRY)
  - Performance degradation (metric comparisons against PERFORMANCE_DEGRADATION_THRESHOLDS)
  - PSI classification (STABLE / WARNING / CRITICAL based on numeric thresholds)
  - HITL trigger conditions (intersection of state flags with ALWAYS_HITL_CONDITIONS)
  - Routing destination (MODEL_RISK_OFFICER / CHIEF_RISK_OFFICER / BOARD)
  - Validation outcome recommendation (APPROVED / CONDITIONALLY_APPROVED / SUSPENDED)

The Model Risk Officer's decision at the HITL gate is the final authority.
No LLM output can change the routing decision, override a suspension, or
approve a model that Python has flagged for suspension.

SECURITY: No individual customer predictions, training data, or PII flows
through this agent. Performance metrics are aggregate statistics only.
"""

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from agent.persistence import audit_sink
from langchain_core.messages import HumanMessage, SystemMessage

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


from .prompts import (
    CONCEPTUAL_SOUNDNESS_REVIEW_PROMPT,
    OUTCOMES_ANALYSIS_PROMPT,
    VALIDATION_REPORT_PROMPT,
    ONGOING_MONITORING_PROMPT,
)
from .state import (
    ALWAYS_HITL_CONDITIONS,
    MODEL_REGISTRY,
    MODEL_RISK_TIERS,
    PERFORMANCE_DEGRADATION_THRESHOLDS,
    VALIDATION_OUTCOMES,
    REVIEWER_DECISIONS,
)

# ── Python constants — immutable, not subject to LLM influence ────────────────

# Models that always require HITL for any validation type.
# HIGH-tier models have mandatory review at every validation event.
HIGH_TIER_ALWAYS_HITL = frozenset({
    model_id for model_id, meta in MODEL_REGISTRY.items()
    if meta["risk_tier"] == "HIGH"
})

# Validation types where HIGH-tier models always require HITL.
HITL_VALIDATION_TYPES = frozenset({
    "INITIAL_VALIDATION",
    "ANNUAL_REVALIDATION",
    "TRIGGERED_REVIEW",
    "CHANGE_VALIDATION",
})

# Routing destinations by finding severity.
ROUTING_DESTINATIONS = {
    "HIGH_TIER_CRITICAL": "CHIEF_RISK_OFFICER",
    "HIGH_TIER_STANDARD": "MODEL_RISK_OFFICER",
    "MEDIUM_TIER_TRIGGERED": "MODEL_RISK_OFFICER",
    "MEDIUM_TIER_STANDARD": "MODEL_RISK_OFFICER",
    "LOW_TIER_STANDARD": "MODEL_VALIDATION_TEAM",
    "BOARD_ESCALATION": "BOARD_RISK_COMMITTEE",
}

# Performance outcome levels.
PERFORMANCE_OUTCOMES = {
    "PASS": "All metrics within acceptable bounds; no material degradation",
    "DEGRADED": "One or more metrics show degradation; enhanced monitoring required",
    "CRITICAL": "Material performance degradation; model use under review",
}


def _get_utc_timestamp() -> str:
    """Return ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _append_audit(current: List[Dict], node_name: str, data: Dict) -> List[Dict]:
    """
    Append-only audit trail update.
    Creates a new list — never modifies prior entries.
    Prior entries are read-only after they are written.
    """
    entry = {
        "node": node_name,
        "timestamp_utc": _get_utc_timestamp(),
        **data,
    }
    # WRITE-AHEAD: durable audit record at creation (agent/persistence.py)
    audit_sink().record(entry)
    return list(current) + [entry]


def _compute_psi(current_dist: Dict[str, float], baseline_dist: Dict[str, float]) -> float:
    """
    Compute Population Stability Index (PSI) to detect distribution shift.

    PSI = Σ (Actual% - Expected%) × ln(Actual% / Expected%)

    Interpretation:
      PSI < 0.10  → Stable — no significant population shift
      0.10-0.25   → Warning — moderate shift, investigate
      PSI > 0.25  → Critical — significant shift, validation required

    This is pure mathematics — no LLM involvement.
    """
    psi = 0.0
    for bucket in set(list(current_dist.keys()) + list(baseline_dist.keys())):
        actual = current_dist.get(bucket, 0.001)    # avoid log(0)
        expected = baseline_dist.get(bucket, 0.001)
        # Normalize to fractions if needed
        if actual > 1:
            actual = actual / 100.0
        if expected > 1:
            expected = expected / 100.0
        psi += (actual - expected) * math.log(actual / expected)
    return round(abs(psi), 4)


def _classify_psi(psi_score: float) -> str:
    """Classify PSI into STABLE / WARNING / CRITICAL based on numeric thresholds."""
    if psi_score < PERFORMANCE_DEGRADATION_THRESHOLDS["psi_warning"]:
        return "STABLE"
    elif psi_score < PERFORMANCE_DEGRADATION_THRESHOLDS["psi_critical"]:
        return "WARNING"
    else:
        return "CRITICAL"


def _get_llm(temperature: float = 0.1) -> Optional[Any]:
    """Return LLM client if API key is set, else None (demo mode)."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-your"):
        return None
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
            temperature=temperature,
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        )
        if os.getenv("BEDROCK_GUARDRAIL_ID"):
            _bedrock_kwargs["guardrail_config"] = {
                "guardrailIdentifier": os.environ["BEDROCK_GUARDRAIL_ID"],
                "guardrailVersion": os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT"),
            }
        return ChatBedrockConverse(**_bedrock_kwargs)
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL, temperature=temperature, api_key=api_key)


def _call_llm(llm: Any, system_prompt: str, user_prompt: str, demo_text: str) -> str:
    """Invoke LLM with fallback to demo text when in demo mode."""
    if llm is None:
        return demo_text
    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        return f"[LLM unavailable: {e}] {demo_text}"


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — model_inventory_lookup
# ══════════════════════════════════════════════════════════════════════════════

def model_inventory_lookup_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Look up the model in the registry and compute scheduling metadata.

    All outputs here are Python-determined:
    - model_record: directly from MODEL_REGISTRY constant
    - risk_tier: directly from model_record
    - revalidation_overdue: arithmetic on dates
    - days_since_last_validation: arithmetic on dates

    No LLM involvement. This data feeds subsequent Python validation nodes.
    """
    model_id = state.get("model_id", "")
    validation_id = str(uuid.uuid4())[:8].upper()
    now = _get_utc_timestamp()

    model_record = MODEL_REGISTRY.get(model_id)
    if not model_record:
        return {
            "validation_id": validation_id,
            "error_message": f"Model ID '{model_id}' not found in model registry",
            "audit_trail": _append_audit(
                state.get("audit_trail", []),
                "model_inventory_lookup",
                {"model_id": model_id, "status": "ERROR_NOT_FOUND"},
            ),
        }

    risk_tier = model_record["risk_tier"]
    last_validation_date = state.get("last_validation_date")

    # Compute days since last validation (integer arithmetic)
    days_since = None
    revalidation_overdue = False
    if last_validation_date:
        try:
            last_dt = datetime.fromisoformat(last_validation_date.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - last_dt).days
            revalidation_months = model_record.get("revalidation_months", 12)
            revalidation_overdue = days_since > (revalidation_months * 30)
        except (ValueError, TypeError):
            pass

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "model_inventory_lookup",
        {
            "model_id": model_id,
            "validation_id": validation_id,
            "risk_tier": risk_tier,
            "validation_type": state.get("validation_type"),
            "last_validation_date": last_validation_date,
            "days_since_last_validation": days_since,
            "revalidation_overdue": revalidation_overdue,
        },
    )

    return {
        "validation_id": validation_id,
        "model_record": model_record,
        "risk_tier": risk_tier,
        "days_since_last_validation": days_since,
        "revalidation_overdue": revalidation_overdue,
        "audit_trail": audit_trail,
        "demo_mode": _get_llm() is None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — data_sample_pull
# ══════════════════════════════════════════════════════════════════════════════

def data_sample_pull_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load performance metrics for the validation period.

    In production: queries the model monitoring store (DynamoDB / CloudWatch)
    for aggregate performance metrics computed over the validation window.
    No individual predictions or customer PII is retrieved — only aggregate
    statistics: accuracy, precision, recall, Gini, KS, FPR, FNR, PSI by decile.

    In this implementation: metrics are loaded from the request state (passed
    in by the Streamlit UI) or from demo fixtures when in demo mode.

    Security: aggregate metrics only — no individual prediction data or PII.
    """
    model_id = state.get("model_id", "")
    model_record = state.get("model_record", {})
    validation_type = state.get("validation_type", "")

    # Accept pre-populated metrics from the UI (live or demo mode)
    current_metrics = state.get("current_metrics")
    baseline_metrics = state.get("baseline_metrics")

    # Compute deltas (Python arithmetic — not LLM)
    metric_deltas = {}
    if current_metrics and baseline_metrics:
        for key in current_metrics:
            if key in baseline_metrics:
                delta = current_metrics[key] - baseline_metrics[key]
                metric_deltas[key] = round(delta, 4)

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "data_sample_pull",
        {
            "model_id": model_id,
            "validation_type": validation_type,
            "validation_period_start": state.get("validation_period_start"),
            "validation_period_end": state.get("validation_period_end"),
            "metrics_loaded": bool(current_metrics),
            "baseline_loaded": bool(baseline_metrics),
        },
    )

    return {
        "current_metrics": current_metrics,
        "baseline_metrics": baseline_metrics,
        "metric_deltas": metric_deltas,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — conceptual_soundness_review
# ══════════════════════════════════════════════════════════════════════════════

def conceptual_soundness_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM node: review conceptual soundness of the model design per SR 11-7 §§ 5-7.

    LLM scope: narrative evaluation of model design, assumptions, and limitations.
    LLM does NOT determine risk tier, performance flags, or validation outcome.

    The output is a narrative section of the SR 11-7 validation report.
    """
    model_record = state.get("model_record", {})
    llm = _get_llm(temperature=0.1)

    user_prompt = CONCEPTUAL_SOUNDNESS_REVIEW_PROMPT.format(
        model_id=state.get("model_id", ""),
        agent_name=model_record.get("agent_name", ""),
        model_name=model_record.get("model_name", ""),
        model_type=model_record.get("model_type", ""),
        risk_tier=state.get("risk_tier", ""),
        validation_type=state.get("validation_type", ""),
        weights=json.dumps(model_record.get("weights", {}), indent=2),
        decision_thresholds=json.dumps(model_record.get("decision_thresholds", {}), indent=2),
        hard_rules=model_record.get("hard_rules", []),
    )

    demo_text = (
        f"[DEMO] Conceptual Soundness Review — {model_record.get('model_name', 'Model')}\n\n"
        "The model's theoretical basis is grounded in established financial crime compliance "
        "and risk management literature. The composite scoring approach — combining "
        "rule-based signals, machine learning outputs, and historical performance data — "
        "reflects current industry practice for this use case.\n\n"
        "The factor weights are documented and their relative magnitudes are appropriate: "
        "higher-weight factors correspond to those with greater discriminatory power in the "
        "training data. Hard rules for regulatory bright-line cases (OFAC hits, PEP flags) "
        "correctly bypass the model scoring to ensure deterministic compliance outcomes.\n\n"
        "Key assumption: the training population is representative of the institution's current "
        "customer and transaction profile. Population stability monitoring (PSI) is in place "
        "to detect when this assumption breaks down.\n\n"
        "Known limitation: the LLM component (50% weight in composite) introduces "
        "non-determinism. This is mitigated by: (1) LLM output is bounded by Python-determined "
        "input features, (2) hard rules override LLM-influenced scores for regulatory "
        "bright-line cases, (3) HITL review is required for all HIGH-tier decisions. "
        "This design is consistent with SR 11-7 § 7 guidance on model use limitations."
    )

    narrative = _call_llm(llm, "You are a senior model risk analyst.", user_prompt, demo_text)

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "conceptual_soundness_review",
        {
            "model_id": state.get("model_id"),
            "llm_used": llm is not None,
            "narrative_length": len(narrative),
        },
    )

    return {
        "conceptual_soundness_narrative": narrative,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — outcomes_analysis
# ══════════════════════════════════════════════════════════════════════════════

def outcomes_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python node: compute performance outcome, degradation flags, and material findings.

    All thresholds come from PERFORMANCE_DEGRADATION_THRESHOLDS constants.
    No LLM in this node — performance outcome is deterministic.

    SR 11-7 § 8: "Back-testing should compare model predictions with actual outcomes
    over the relevant time period, using appropriate statistical tests."
    """
    current_metrics = state.get("current_metrics", {}) or {}
    baseline_metrics = state.get("baseline_metrics", {}) or {}
    metric_deltas = state.get("metric_deltas", {}) or {}
    model_record = state.get("model_record", {})
    hard_rules = model_record.get("hard_rules", [])

    degradation_flags: List[str] = []
    material_findings: List[str] = []
    hard_rule_violations: List[str] = []

    thresholds = PERFORMANCE_DEGRADATION_THRESHOLDS

    # Check accuracy degradation
    if "accuracy" in metric_deltas:
        drop = -metric_deltas["accuracy"]  # positive = degradation
        if drop > thresholds["accuracy_drop_pct"]:
            degradation_flags.append("ACCURACY_DEGRADATION")
            material_findings.append(
                f"Model accuracy declined {drop:.1f}pp (threshold: {thresholds['accuracy_drop_pct']}pp). "
                "This exceeds SR 11-7 acceptable drift — investigation required."
            )

    # Check Gini coefficient degradation
    if "gini_coefficient" in metric_deltas:
        drop = -metric_deltas["gini_coefficient"]
        if drop > thresholds["gini_drop_points"]:
            degradation_flags.append("GINI_DEGRADATION")
            material_findings.append(
                f"Gini coefficient declined {drop:.1f} points (threshold: {thresholds['gini_drop_points']}). "
                "The model has lost discriminatory power — likely population shift or concept drift."
            )

    # Check KS statistic degradation
    if "ks_statistic" in metric_deltas:
        drop = -metric_deltas["ks_statistic"]
        if drop > thresholds["ks_stat_drop_pct"]:
            degradation_flags.append("KS_DEGRADATION")
            material_findings.append(
                f"KS statistic declined {drop:.1f}pp (threshold: {thresholds['ks_stat_drop_pct']}pp). "
                "Separation between positive and negative classes is weakening."
            )

    # Check false positive rate increase
    if "false_positive_rate" in metric_deltas:
        increase = metric_deltas["false_positive_rate"]
        if increase > thresholds["false_positive_rate_increase"] * 100:
            degradation_flags.append("FPR_INCREASE")
            material_findings.append(
                f"False positive rate increased {increase:.1f}pp. "
                "Analyst efficiency impact and potential for compliance alert fatigue."
            )

    # Check false negative rate increase (more sensitive — higher severity)
    if "false_negative_rate" in metric_deltas:
        increase = metric_deltas["false_negative_rate"]
        if increase > thresholds["false_negative_rate_increase"] * 100:
            degradation_flags.append("FNR_INCREASE")
            material_findings.append(
                f"False negative rate increased {increase:.1f}pp (threshold: {thresholds['false_negative_rate_increase']*100:.0f}pp). "
                "The model is missing more true positives — regulatory and financial risk."
            )

    # Determine performance outcome
    if "ACCURACY_DEGRADATION" in degradation_flags or "FNR_INCREASE" in degradation_flags:
        performance_outcome = "CRITICAL"
    elif degradation_flags:
        performance_outcome = "DEGRADED"
    else:
        performance_outcome = "PASS"

    # Check for hard rule violations (scanned from state flags if any were logged)
    # In production: queries model monitoring log for cases where hard rules
    # should have fired but score routing was observed instead
    violations = state.get("hard_rule_violations", [])

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "outcomes_analysis",
        {
            "model_id": state.get("model_id"),
            "performance_outcome": performance_outcome,
            "degradation_flags": degradation_flags,
            "material_findings_count": len(material_findings),
        },
    )

    return {
        "degradation_flags": degradation_flags,
        "material_findings": material_findings,
        "hard_rule_violations": violations,
        "performance_outcome": performance_outcome,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — population_stability_analysis
# ══════════════════════════════════════════════════════════════════════════════

def population_stability_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python node: compute Population Stability Index (PSI) and classify.

    PSI measures whether the input population has shifted since the model was
    developed or last validated. A shift in population means the model was not
    trained on data representative of current inputs — a form of concept drift.

    PSI < 0.10: Stable
    PSI 0.10-0.25: Warning — moderate shift
    PSI > 0.25: Critical — significant shift, triggers PERFORMANCE_DEGRADATION condition

    This is pure Python mathematics — no LLM.
    """
    current_metrics = state.get("current_metrics", {}) or {}
    baseline_metrics = state.get("baseline_metrics", {}) or {}

    # PSI can be pre-computed and provided as a metric
    psi_score = current_metrics.get("psi", None)

    # If not provided, estimate from score distribution buckets if available
    if psi_score is None:
        score_dist_current = current_metrics.get("score_distribution_buckets", {})
        score_dist_baseline = baseline_metrics.get("score_distribution_buckets", {})
        if score_dist_current and score_dist_baseline:
            psi_score = _compute_psi(score_dist_current, score_dist_baseline)
        else:
            # Default: cannot compute PSI — flag as unknown
            psi_score = None

    psi_flag = _classify_psi(psi_score) if psi_score is not None else "UNKNOWN"

    # Add PSI-related degradation flags
    degradation_flags = list(state.get("degradation_flags", []))
    if psi_flag == "CRITICAL":
        if "PSI_CRITICAL" not in degradation_flags:
            degradation_flags.append("PSI_CRITICAL")
    elif psi_flag == "WARNING":
        if "PSI_WARNING" not in degradation_flags:
            degradation_flags.append("PSI_WARNING")

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "population_stability_analysis",
        {
            "psi_score": psi_score,
            "psi_flag": psi_flag,
            "additional_degradation_flags": [f for f in degradation_flags if f.startswith("PSI")],
        },
    )

    return {
        "psi_score": psi_score,
        "psi_flag": psi_flag,
        "degradation_flags": degradation_flags,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6 — benchmark_comparison
# ══════════════════════════════════════════════════════════════════════════════

def benchmark_comparison_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python node: compare production model against challenger or benchmark.

    SR 11-7 § 8 recommends comparison against alternative approaches.
    For HIGH-tier models, a challenger comparison is required.

    Challenger metrics are pre-computed and provided in state (from model
    monitoring system). Comparison logic is Python — not LLM.
    """
    risk_tier = state.get("risk_tier", "")
    challenger_available = bool(state.get("challenger_metrics"))
    challenger_metrics = state.get("challenger_metrics", {})
    current_metrics = state.get("current_metrics", {}) or {}

    challenger_comparison_result = None
    material_findings = list(state.get("material_findings", []))

    if challenger_available and challenger_metrics and current_metrics:
        # Compare primary discriminatory metric (Gini or AUC-ROC)
        prod_gini = current_metrics.get("gini_coefficient", 0)
        chal_gini = challenger_metrics.get("gini_coefficient", 0)

        if chal_gini > prod_gini + 5:   # Challenger materially better (5 Gini points)
            challenger_comparison_result = "CHALLENGER_BETTER"
            material_findings.append(
                f"Challenger model outperforms production: Gini {chal_gini:.1f} vs {prod_gini:.1f} "
                f"({chal_gini - prod_gini:.1f} point advantage). Model replacement should be evaluated."
            )
        elif prod_gini > chal_gini + 5:
            challenger_comparison_result = "PRODUCTION_BETTER"
        else:
            challenger_comparison_result = "PARITY"
    elif risk_tier == "HIGH" and not challenger_available:
        material_findings.append(
            "HIGH-tier model: no challenger model available for comparison. "
            "SR 11-7 recommends challenger comparison for high-risk models. "
            "Consider developing a challenger for next validation cycle."
        )

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "benchmark_comparison",
        {
            "challenger_available": challenger_available,
            "challenger_comparison_result": challenger_comparison_result,
        },
    )

    return {
        "challenger_available": challenger_available,
        "challenger_comparison_result": challenger_comparison_result,
        "material_findings": material_findings,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 7 — sensitivity_analysis
# ══════════════════════════════════════════════════════════════════════════════

def sensitivity_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python node: stress-test model behavior at threshold extremes.

    Validates that:
    1. Hard rule overrides work at extreme values (OFAC hit → BLOCK regardless)
    2. Scoring remains monotonic (higher risk inputs → higher scores)
    3. Boundary conditions near thresholds behave predictably
    4. Model is not excessively sensitive to any single factor

    In production: sends synthetic test vectors to the model API and
    validates response. Here we validate documented weight sensitivity.
    """
    model_record = state.get("model_record", {}) or {}
    weights = model_record.get("weights", {})

    sensitivity_results: Dict[str, Any] = {}

    # Weight concentration check: is any single factor weighted > 50%?
    max_weight_factor = max(weights.items(), key=lambda x: x[1]) if weights else ("", 0)
    if max_weight_factor[1] > 0.50:
        sensitivity_results["concentration_warning"] = (
            f"Factor '{max_weight_factor[0]}' carries {max_weight_factor[1]*100:.0f}% of the score weight. "
            "High concentration in a single factor increases model sensitivity and fragility."
        )
    else:
        sensitivity_results["concentration_check"] = "PASS — no single factor exceeds 50% weight"

    # Weight sum validation: must equal 1.0 within tolerance
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.001:
        sensitivity_results["weight_sum_error"] = (
            f"Factor weights sum to {weight_sum:.4f} (expected 1.0000). "
            "Weight normalization error — all decisions are potentially miscalibrated."
        )
    else:
        sensitivity_results["weight_sum_check"] = f"PASS — weights sum to {weight_sum:.4f}"

    # Hard rule coverage check: are all bright-line regulatory cases covered?
    hard_rules = model_record.get("hard_rules", [])
    ofac_covered = any("OFAC" in r.upper() for r in hard_rules)
    pep_covered = any("PEP" in r.upper() for r in hard_rules)
    sensitivity_results["hard_rule_coverage"] = {
        "ofac_override": "DOCUMENTED" if ofac_covered else "MISSING — CRITICAL GAP",
        "pep_override": "DOCUMENTED" if pep_covered else "MISSING",
        "total_hard_rules": len(hard_rules),
    }

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "sensitivity_analysis",
        {
            "weight_sum": round(weight_sum, 4),
            "max_weight_factor": max_weight_factor[0],
            "max_weight_value": max_weight_factor[1],
            "hard_rule_count": len(hard_rules),
        },
    )

    return {
        "sensitivity_analysis_results": sensitivity_results,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 8 — risk_tier_determination
# ══════════════════════════════════════════════════════════════════════════════

def risk_tier_determination_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python node: compute validation risk score and HITL conditions.

    This is the routing decision node — all logic is Python.
    The HITL conditions are checked against ALWAYS_HITL_CONDITIONS frozenset.
    No LLM output influences whether HITL is required.

    SR 11-7 § 5: "The level of validation and the rigor applied should be
    commensurate with the model's complexity and risk."
    """
    risk_tier = state.get("risk_tier", "LOW")
    validation_type = state.get("validation_type", "")
    performance_outcome = state.get("performance_outcome", "PASS")
    degradation_flags = state.get("degradation_flags", [])
    material_findings = state.get("material_findings", [])
    psi_flag = state.get("psi_flag", "STABLE")
    challenger_comparison_result = state.get("challenger_comparison_result")
    hard_rule_violations = state.get("hard_rule_violations", [])
    revalidation_overdue = state.get("revalidation_overdue", False)

    # Build set of HITL conditions triggered
    hitl_conditions: List[str] = []

    # HIGH tier + certain validation types always require HITL
    if risk_tier == "HIGH" and validation_type in HITL_VALIDATION_TYPES:
        hitl_conditions.append("HIGH_TIER_INITIAL_VALIDATION" if validation_type == "INITIAL_VALIDATION"
                               else "ANNUAL_REVALIDATION_HIGH_TIER" if validation_type == "ANNUAL_REVALIDATION"
                               else "HIGH_TIER_CHANGE_VALIDATION")

    # Performance degradation triggers
    if performance_outcome == "CRITICAL":
        hitl_conditions.append("PERFORMANCE_DEGRADATION_TRIGGERED")
    if psi_flag == "CRITICAL":
        hitl_conditions.append("PSI_CRITICAL")

    # Material findings
    if material_findings:
        hitl_conditions.append("MATERIAL_FINDING")

    # Challenger underperforms
    if challenger_comparison_result == "CHALLENGER_BETTER":
        hitl_conditions.append("CHALLENGER_UNDERPERFORMS")

    # Hard rule violations (very serious — escalate to CRO)
    if hard_rule_violations:
        hitl_conditions.append("HARD_RULE_VIOLATION_DETECTED")

    # Validate conditions against frozenset (defensive check)
    valid_conditions = [c for c in hitl_conditions if c in ALWAYS_HITL_CONDITIONS]

    # Compute validation risk score (Python arithmetic)
    # Higher = more validation risk = more likely to need HITL + conditions
    risk_components = {
        "tier_factor": 1.0 if risk_tier == "HIGH" else 0.5 if risk_tier == "MEDIUM" else 0.2,
        "performance_factor": 1.0 if performance_outcome == "CRITICAL" else 0.5 if performance_outcome == "DEGRADED" else 0.0,
        "psi_factor": 1.0 if psi_flag == "CRITICAL" else 0.4 if psi_flag == "WARNING" else 0.0,
        "findings_factor": min(len(material_findings) * 0.25, 1.0),
        "overdue_factor": 0.3 if revalidation_overdue else 0.0,
    }
    weights = {"tier_factor": 0.30, "performance_factor": 0.30, "psi_factor": 0.20,
               "findings_factor": 0.15, "overdue_factor": 0.05}
    validation_risk_score = round(sum(risk_components[k] * weights[k] for k in weights), 3)

    # Routing destination
    if "HARD_RULE_VIOLATION_DETECTED" in valid_conditions:
        target_reviewer = "CHIEF_RISK_OFFICER"
    elif risk_tier == "HIGH" and performance_outcome == "CRITICAL":
        target_reviewer = "CHIEF_RISK_OFFICER"
    elif valid_conditions:
        target_reviewer = "MODEL_RISK_OFFICER"
    else:
        target_reviewer = "MODEL_VALIDATION_TEAM"

    # Preliminary resolution recommendation (Python — not LLM)
    if "HARD_RULE_VIOLATION_DETECTED" in valid_conditions:
        resolution_type = "SUSPENDED"
    elif performance_outcome == "CRITICAL" and risk_tier == "HIGH":
        resolution_type = "CONDITIONALLY_APPROVED"
    elif material_findings or degradation_flags:
        resolution_type = "CONDITIONALLY_APPROVED"
    else:
        resolution_type = "APPROVED"

    human_review_required = bool(valid_conditions)

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "risk_tier_determination",
        {
            "validation_risk_score": validation_risk_score,
            "hitl_conditions": valid_conditions,
            "human_review_required": human_review_required,
            "target_reviewer": target_reviewer,
            "resolution_type": resolution_type,
        },
    )

    return {
        "hitl_conditions": valid_conditions,
        "validation_risk_score": validation_risk_score,
        "human_review_required": human_review_required,
        "target_reviewer": target_reviewer,
        "resolution_type": resolution_type,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 9 — validation_narrative
# ══════════════════════════════════════════════════════════════════════════════

def validation_narrative_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM node: draft outcomes analysis narrative and validation report.

    LLM scope: interpret Python-computed metrics in plain language,
    draft the SR 11-7 validation report sections.
    LLM does NOT determine outcome, tier, or HITL status — all set by Python.
    """
    model_record = state.get("model_record", {})
    llm = _get_llm(temperature=0.1)

    # Outcomes analysis narrative
    outcomes_prompt = OUTCOMES_ANALYSIS_PROMPT.format(
        model_id=state.get("model_id", ""),
        model_name=model_record.get("model_name", ""),
        risk_tier=state.get("risk_tier", ""),
        validation_period_start=state.get("validation_period_start", ""),
        validation_period_end=state.get("validation_period_end", ""),
        current_metrics=json.dumps(state.get("current_metrics", {}), indent=2),
        baseline_metrics=json.dumps(state.get("baseline_metrics", {}), indent=2),
        metric_deltas=json.dumps(state.get("metric_deltas", {}), indent=2),
        psi_score=state.get("psi_score", "Not computed"),
        psi_flag=state.get("psi_flag", "UNKNOWN"),
        performance_outcome=state.get("performance_outcome", ""),
        degradation_flags=state.get("degradation_flags", []),
        material_findings=state.get("material_findings", []),
        challenger_available=state.get("challenger_available", False),
        challenger_comparison_result=state.get("challenger_comparison_result", "N/A"),
    )

    outcomes_demo = (
        "[DEMO] Outcomes Analysis Summary\n\n"
        "The model demonstrates stable performance across the validation period with "
        "all primary metrics within acceptable tolerance bands. Accuracy remains at "
        "94.2% (baseline: 94.8%), a 0.6pp decline that is within the 5pp degradation "
        "threshold. Gini coefficient is 68.4 (baseline: 70.1), a 1.7 point decline — "
        "within the 10-point threshold.\n\n"
        "Population Stability Index (PSI) of 0.07 indicates the input population "
        "remains representative of the training distribution — no significant concept "
        "drift is detected. The score distribution is stable across all deciles.\n\n"
        "No material degradation flags were triggered. The model continues to demonstrate "
        "appropriate discriminatory power for its intended use case. Ongoing monthly "
        "monitoring is sufficient for the current performance profile."
    )

    outcomes_narrative = _call_llm(llm, "You are a senior model risk analyst.", outcomes_prompt, outcomes_demo)

    # Full validation report
    report_prompt = VALIDATION_REPORT_PROMPT.format(
        model_id=state.get("model_id", ""),
        model_name=model_record.get("model_name", ""),
        agent_name=model_record.get("agent_name", ""),
        risk_tier=state.get("risk_tier", ""),
        validation_type=state.get("validation_type", ""),
        validation_period_start=state.get("validation_period_start", ""),
        validation_period_end=state.get("validation_period_end", ""),
        requested_by=state.get("requested_by", ""),
        triggering_event=state.get("triggering_event", "N/A"),
        performance_outcome=state.get("performance_outcome", ""),
        validation_risk_score=state.get("validation_risk_score", 0),
        degradation_flags=state.get("degradation_flags", []),
        material_findings=state.get("material_findings", []),
        hitl_conditions=state.get("hitl_conditions", []),
        resolution_type=state.get("resolution_type", ""),
        target_reviewer=state.get("target_reviewer", ""),
        conceptual_soundness_narrative=state.get("conceptual_soundness_narrative", ""),
        outcomes_analysis_summary=outcomes_narrative,
    )

    report_demo = (
        "[DEMO] SR 11-7 Model Validation Report\n\n"
        "1. EXECUTIVE SUMMARY\n"
        "This validation covers the annual revalidation of the model for the period "
        "Q1-Q2 2026. The model demonstrates acceptable performance with no material "
        "degradation. Recommended outcome: APPROVED with continued monthly monitoring.\n\n"
        "2. SCOPE AND METHODOLOGY\n"
        "Full SR 11-7 validation scope: conceptual soundness review, outcomes analysis "
        "(back-testing against 6-month production data), PSI analysis, sensitivity "
        "testing, and challenger comparison where available.\n\n"
        "3. FINDINGS AND CONDITIONS\n"
        "No material findings. Minor observations: (1) PSI trending toward WARNING "
        "threshold in one score decile — increase monitoring frequency recommended. "
        "(2) Challenger model development recommended for next validation cycle.\n\n"
        "4. CONCLUSION\n"
        "Model is approved for continued production use. Enhanced monitoring for "
        "PSI trending. Next annual revalidation due Q2 2027.\n"
        "Regulatory basis: SR 11-7 §§ 8-10, OCC 2011-12."
    )

    report_draft = _call_llm(llm, "You are a senior model risk analyst.", report_prompt, report_demo)

    # Concise findings summary for HITL reviewer panel
    findings_summary = (
        f"Model: {model_record.get('model_name', '')} ({state.get('model_id', '')})\n"
        f"Risk Tier: {state.get('risk_tier', '')} | "
        f"Validation Type: {state.get('validation_type', '')}\n"
        f"Performance Outcome: {state.get('performance_outcome', '')} | "
        f"Validation Risk Score: {state.get('validation_risk_score', 0):.3f}\n"
        f"Degradation Flags: {', '.join(state.get('degradation_flags', [])) or 'None'}\n"
        f"Material Findings: {len(state.get('material_findings', []))} identified\n"
        f"HITL Conditions: {', '.join(state.get('hitl_conditions', [])) or 'None'}\n"
        f"Recommended Outcome: {state.get('resolution_type', '')}\n"
        f"Target Reviewer: {state.get('target_reviewer', '')}"
    )

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "validation_narrative",
        {
            "model_id": state.get("model_id"),
            "llm_used": llm is not None,
            "report_length": len(report_draft),
        },
    )

    return {
        "outcomes_analysis_summary": outcomes_narrative,
        "validation_report_draft": report_draft,
        "findings_summary": findings_summary,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 10 — routing_decision
# ══════════════════════════════════════════════════════════════════════════════

def routing_decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Python node: finalize routing for HITL or auto-completion.

    This is pure Python routing — no LLM. The routing decision is based
    on Python-computed flags set in risk_tier_determination_node.
    The human_review_required flag controls graph branching.
    """
    model_id = state.get("model_id", "")
    human_review_required = state.get("human_review_required", True)  # Default: HITL
    target_reviewer = state.get("target_reviewer", "MODEL_RISK_OFFICER")
    resolution_type = state.get("resolution_type", "UNDER_REVIEW")

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "routing_decision",
        {
            "model_id": model_id,
            "human_review_required": human_review_required,
            "target_reviewer": target_reviewer,
            "resolution_type": resolution_type,
        },
    )

    return {
        "human_review_required": human_review_required,
        "target_reviewer": target_reviewer,
        "resolution_type": resolution_type,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 11 — human_review_gate
# ══════════════════════════════════════════════════════════════════════════════

def human_review_gate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    HITL gate: paused by LangGraph interrupt_before mechanism.

    This node executes AFTER the Model Risk Officer submits their decision
    via the Streamlit UI → graph.update_state() → graph.stream(None, config).

    The reviewer's decision is Python-validated against REVIEWER_DECISIONS.
    Unknown decisions are rejected — they cannot be passed through.

    SR 11-7 § 4: "Model risk management should be embedded in the firm's
    overall risk management framework... with appropriate human oversight."
    """
    reviewer_decision = state.get("reviewer_decision", "")
    reviewer_conditions = state.get("reviewer_conditions", "")
    reviewer_notes = state.get("reviewer_notes", "")
    reviewer_id = state.get("reviewer_id", "unknown")

    # Validate reviewer decision against known decisions
    if reviewer_decision not in REVIEWER_DECISIONS:
        reviewer_decision = ""  # Reject unknown decision strings

    # Map reviewer decision to final validation outcome
    if reviewer_decision == "APPROVE_VALIDATION":
        validation_outcome = "APPROVED"
    elif reviewer_decision == "CONDITIONALLY_APPROVE":
        validation_outcome = "CONDITIONALLY_APPROVED"
    elif reviewer_decision == "REQUIRE_REMEDIATION":
        validation_outcome = "SUSPENDED"
    elif reviewer_decision == "ESCALATE_TO_BOARD":
        validation_outcome = "UNDER_REVIEW"
    else:
        validation_outcome = "UNDER_REVIEW"  # Fail-safe: unknown decision → leave under review

    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "human_review_gate",
        {
            "reviewer_id": reviewer_id,
            "reviewer_decision": reviewer_decision,
            "validation_outcome": validation_outcome,
            "has_conditions": bool(reviewer_conditions),
        },
    )

    return {
        "reviewer_decision": reviewer_decision,
        "reviewer_timestamp": _get_utc_timestamp(),
        "validation_outcome": validation_outcome,
        "audit_trail": audit_trail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 12 — audit_finalize
# ══════════════════════════════════════════════════════════════════════════════

def audit_finalize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final node: write validation outcome to model registry and finalize audit trail.

    SR 11-7 retention: model validation reports must be retained for the life
    of the model plus the BSA/examination record retention period (5 years minimum).
    In production: report written to S3 Object Lock (WORM) with GOVERNANCE mode,
    10-year retention for model validation records.

    The model_approval_status and next_revalidation_date are Python-computed —
    never set by LLM output.
    """
    model_id = state.get("model_id", "")
    model_record = state.get("model_record", {}) or {}
    validation_outcome = state.get("validation_outcome") or state.get("resolution_type", "UNDER_REVIEW")

    # Compute next revalidation date (Python arithmetic)
    revalidation_months = model_record.get("revalidation_months", 12)
    if validation_outcome == "SUSPENDED":
        # Suspended models: revalidation after remediation — no scheduled date
        next_revalidation_date = "PENDING_REMEDIATION"
    else:
        next_date = datetime.now(timezone.utc) + timedelta(days=revalidation_months * 30)
        next_revalidation_date = next_date.strftime("%Y-%m-%d")

    # Map outcome to approval status
    approval_status_map = {
        "APPROVED": "APPROVED",
        "CONDITIONALLY_APPROVED": "CONDITIONALLY_APPROVED",
        "SUSPENDED": "SUSPENDED",
        "UNDER_REVIEW": "UNDER_REVIEW",
        "RETIRED": "RETIRED",
    }
    model_approval_status = approval_status_map.get(validation_outcome, "UNDER_REVIEW")

    # Final audit entry
    audit_trail = _append_audit(
        state.get("audit_trail", []),
        "audit_finalize",
        {
            "validation_id": state.get("validation_id"),
            "model_id": model_id,
            "final_outcome": validation_outcome,
            "model_approval_status": model_approval_status,
            "next_revalidation_date": next_revalidation_date,
            "total_nodes_executed": len(state.get("audit_trail", [])) + 1,
            "audit_retention": "10_YEARS_S3_OBJECT_LOCK_GOVERNANCE",
        },
    )

    return {
        "validation_outcome": validation_outcome,
        "model_approval_status": model_approval_status,
        "next_revalidation_date": next_revalidation_date,
        "audit_trail": audit_trail,
    }
