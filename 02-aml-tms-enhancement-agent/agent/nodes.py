"""
AML/TMS Enhancement Agent — Graph Nodes
Pre-queue false positive scoring workflow.

Node execution order:
  ingest_raw_alert
    → customer_context_lookup
    → historical_pattern_check
    → extract_features_node
    → rule_based_prescoring
    → llm_false_positive_analysis
    → compute_composite_score_node
    → determine_routing
    → [execute_suppression | execute_downgrade | enqueue_alert | execute_escalation]
    → finalize_scoring
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from langchain_anthropic import ChatAnthropic
from agent.persistence import audit_sink

from agent.state import AlertScoringState, AuditEntry
from agent.prompts import (
    SYSTEM_PERSONA,
    FALSE_POSITIVE_ANALYSIS_PROMPT,
    SUPPRESSION_JUSTIFICATION_PROMPT,
    DOWNGRADE_JUSTIFICATION_PROMPT,
)
from scoring.false_positive_classifier import (
    check_regulatory_override,
    compute_rule_based_score,
    compute_composite_score,
)
from scoring.feature_extractor import extract_features
from scoring.threshold_manager import ThresholdManager
from tools.customer_context import get_customer_summary
from tools.historical_patterns import get_historical_patterns
from tools.tms_connector import update_alert_disposition

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
CLAUDE_DEFAULT_MODEL = CLAUDE_FAST_MODEL

from tools.suppression_engine import (
    record_suppression,
    record_downgrade,
    record_pass_through,
    record_escalation,
)

logger = logging.getLogger(__name__)

def _make_llm():
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
            model=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001"),
            temperature=0.0,
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        )
        if os.getenv("BEDROCK_GUARDRAIL_ID"):
            _bedrock_kwargs["guardrail_config"] = {
                "guardrailIdentifier": os.environ["BEDROCK_GUARDRAIL_ID"],
                "guardrailVersion": os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT"),
            }
        return ChatBedrockConverse(**_bedrock_kwargs)
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL, temperature=0.0)


_llm = _make_llm()
_threshold_manager = ThresholdManager()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _append_audit(state: AlertScoringState, action: str, details: dict, sources: list[str]) -> list[AuditEntry]:
    trail = list(state.get("audit_trail", []))
    trail.append(AuditEntry(
        timestamp=_now(),
        actor="AI_SCORING_AGENT",
        action=action,
        details=details,
        data_sources=sources,
        ai_model_used=None,
    ))
    # WRITE-AHEAD: durable audit record at creation (agent/persistence.py)
    audit_sink().record(trail[-1])
    return trail


def _append_audit_llm(state: AlertScoringState, action: str, details: dict, sources: list[str]) -> list[AuditEntry]:
    trail = list(state.get("audit_trail", []))
    trail.append(AuditEntry(
        timestamp=_now(),
        actor="AI_SCORING_AGENT",
        action=action,
        details=details,
        data_sources=sources,
        ai_model_used="claude-sonnet-4-6",
    ))
    # WRITE-AHEAD: durable audit record at creation (agent/persistence.py)
    audit_sink().record(trail[-1])
    return trail


def _parse_llm_json(content: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting the first JSON object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


# ── Node 1: Ingest ────────────────────────────────────────────────────────────

def ingest_raw_alert(state: AlertScoringState) -> AlertScoringState:
    """Parse and validate the incoming TMS alert."""
    raw_alert = state["raw_alert"]
    alert_id = raw_alert["alert_id"]
    customer_id = raw_alert["customer_id"]
    ingested_at = _now()

    notes = list(state.get("scoring_notes", []))
    notes.append(f"Alert {alert_id} ingested from {raw_alert.get('tms_vendor', 'unknown')} TMS")

    audit = _append_audit(
        state,
        "ALERT_INGESTED",
        {"alert_id": alert_id, "alert_type": raw_alert["alert_type"],
         "severity": raw_alert["severity"], "amount": raw_alert["amount"]},
        [raw_alert.get("tms_vendor", "tms")],
    )

    logger.info("Ingested alert %s | type=%s amount=$%.2f",
                alert_id, raw_alert["alert_type"], raw_alert["amount"])

    return {
        **state,
        "alert_id": alert_id,
        "customer_id": customer_id,
        "ingested_at": ingested_at,
        "errors": [],
        "fallback_to_manual": False,
        "audit_trail": audit,
        "scoring_notes": notes,
    }


# ── Node 2: Customer Context ───────────────────────────────────────────────────

def customer_context_lookup(state: AlertScoringState) -> AlertScoringState:
    """Fetch lightweight customer profile for scoring."""
    customer_id = state["customer_id"]
    errors = list(state.get("errors", []))
    notes = list(state.get("scoring_notes", []))

    customer = get_customer_summary(customer_id)

    if customer is None:
        errors.append(f"Customer {customer_id} not found — will fall back to manual review")
        notes.append("Customer lookup failed — triggering manual fallback")
        audit = _append_audit(
            state, "CUSTOMER_LOOKUP_FAILED",
            {"customer_id": customer_id, "fallback": True},
            ["core_banking_api"],
        )
        return {
            **state,
            "fallback_to_manual": True,
            "errors": errors,
            "scoring_notes": notes,
            "audit_trail": audit,
        }

    notes.append(
        f"Customer: {customer['full_name']} | Tier: {customer['risk_tier']} | "
        f"FP history: {customer['historical_fp_rate']:.0%}"
    )

    audit = _append_audit(
        state, "CUSTOMER_CONTEXT_LOADED",
        {"customer_id": customer_id, "risk_tier": customer["risk_tier"],
         "historical_fp_rate": customer["historical_fp_rate"],
         "pep_flag": customer["pep_flag"], "open_investigations": customer["open_investigation_count"]},
        ["core_banking_api"],
    )

    return {
        **state,
        "customer_summary": customer,
        "errors": errors,
        "scoring_notes": notes,
        "audit_trail": audit,
    }


# ── Node 3: Historical Patterns ───────────────────────────────────────────────

def historical_pattern_check(state: AlertScoringState) -> AlertScoringState:
    """Retrieve rule-level and customer-level historical FP rate data."""
    if state.get("fallback_to_manual"):
        return state  # Skip — already falling back

    raw_alert = state["raw_alert"]
    customer = state["customer_summary"]

    history = get_historical_patterns(
        customer_id=state["customer_id"],
        alert_type=raw_alert["alert_type"],
        triggered_rule=raw_alert["triggered_rule"],
        business_type=customer["business_type"],
        risk_tier=customer["risk_tier"],
    )

    notes = list(state.get("scoring_notes", []))
    notes.append(
        f"Rule FP rate: {history['rule_fp_rate']:.0%} | "
        f"Typology FP rate: {history['typology_fp_rate']:.0%} | "
        f"Customer FP rate: {history['customer_fp_rate']:.0%}"
    )

    audit = _append_audit(
        state, "HISTORICAL_PATTERNS_LOADED",
        {"rule_fp_rate": history["rule_fp_rate"],
         "typology_fp_rate": history["typology_fp_rate"],
         "customer_fp_rate": history["customer_fp_rate"],
         "prior_alert_count": len(history["customer_alert_history"])},
        ["data_warehouse", "case_management_system"],
    )

    return {
        **state,
        "historical_patterns": history,
        "scoring_notes": notes,
        "audit_trail": audit,
    }


# ── Node 4: Feature Extraction ────────────────────────────────────────────────

def extract_features_node(state: AlertScoringState) -> AlertScoringState:
    """Build structured ScoringFeatures from raw alert + customer + history."""
    if state.get("fallback_to_manual"):
        return state

    features = extract_features(
        raw_alert=state["raw_alert"],
        customer=state["customer_summary"],
        history=state["historical_patterns"],
    )

    audit = _append_audit(
        state, "FEATURES_EXTRACTED",
        {"amount_vs_expected_ratio": features["amount_vs_expected_ratio"],
         "high_risk_geography": features["high_risk_geography"],
         "is_month_end": features["is_month_end"]},
        ["feature_extractor"],
    )

    return {**state, "scoring_features": features, "audit_trail": audit}


# ── Node 5: Rule-Based Pre-Scoring ────────────────────────────────────────────

def rule_based_prescoring(state: AlertScoringState) -> AlertScoringState:
    """Fast deterministic scoring — catches obvious FPs and mandatory overrides."""
    if state.get("fallback_to_manual"):
        return state

    features = state["scoring_features"]

    # Check regulatory overrides first — these cannot be overridden by score
    override, override_reason = check_regulatory_override(features)

    rule_score, rule_factors = compute_rule_based_score(features)

    notes = list(state.get("scoring_notes", []))
    notes.append(f"Rule-based pre-score: {rule_score:.0f}/100 | Override: {override}")

    audit = _append_audit(
        state, "RULE_BASED_PRESCORE_COMPLETE",
        {"rule_based_fp_score": rule_score,
         "regulatory_override": override,
         "regulatory_override_reason": override_reason,
         "factors_count": len(rule_factors)},
        ["rule_engine"],
    )

    return {
        **state,
        "rule_based_fp_score": rule_score,
        "rule_based_factors": rule_factors,
        "scoring_notes": notes,
        "audit_trail": audit,
    }


# ── Node 6: LLM False Positive Analysis ───────────────────────────────────────

def llm_false_positive_analysis(state: AlertScoringState) -> AlertScoringState:
    """
    LLM reasoning step — the largest scoring weight (50%).

    The LLM receives all extracted features, historical rates, and the
    rule-based pre-score, then produces an FP probability estimate and
    structured recommendation with full supporting reasoning.
    """
    if state.get("fallback_to_manual"):
        return state

    raw_alert = state["raw_alert"]
    customer = state["customer_summary"]
    features = state["scoring_features"]
    history = state["historical_patterns"]

    # Build customer alert history summary for prompt
    history_summary = _format_history_summary(history.get("customer_alert_history", []))

    prompt = FALSE_POSITIVE_ANALYSIS_PROMPT.format(
        system_persona=SYSTEM_PERSONA,
        alert_id=raw_alert["alert_id"],
        alert_type=raw_alert["alert_type"],
        triggered_rule=raw_alert["triggered_rule"],
        rule_fp_rate=features["rule_fp_rate"],
        severity=raw_alert["severity"],
        amount=raw_alert["amount"],
        currency=raw_alert.get("currency", "USD"),
        alert_date=raw_alert["alert_date"],
        transaction_count=features["transaction_count"],
        time_window_days=features["time_window_days"],
        tms_vendor=raw_alert.get("tms_vendor", "unknown"),
        customer_name=customer["full_name"],
        business_type=customer["business_type"],
        risk_tier=customer["risk_tier"],
        account_age_days=customer["account_age_days"],
        account_age_years=customer["account_age_days"] / 365,
        expected_monthly_cash_volume=customer["expected_monthly_cash_volume"],
        expected_monthly_wire_volume=customer["expected_monthly_wire_volume"],
        amount_vs_expected_ratio=features["amount_vs_expected_ratio"],
        customer_historical_fp_rate=features["customer_historical_fp_rate"],
        open_investigation_count=customer["open_investigation_count"],
        prior_sars_filed=customer["prior_sars_filed"],
        prior_ctrs_filed=customer["prior_ctrs_filed"],
        pep_flag=customer["pep_flag"],
        edd_active=customer["edd_active"],
        typology_fp_rate=features["typology_fp_rate"],
        peer_group_fp_rate=features["peer_group_fp_rate"],
        days_since_last_similar_alert=features["days_since_last_similar_alert"],
        customer_alert_history_summary=history_summary,
        rule_based_fp_score=state.get("rule_based_fp_score", 0),
        prefilter_factors="; ".join(state.get("rule_based_factors", [])) or "None",
        high_risk_geography=features["high_risk_geography"],
        is_weekend=features["is_weekend"],
        is_month_end=features["is_month_end"],
    )

    try:
        response = _llm.invoke(prompt)
        parsed = _parse_llm_json(response.content)

        llm_fp_prob = float(parsed.get("fp_probability", 50))
        llm_confidence = float(parsed.get("confidence", 0.5))
        llm_recommendation = parsed.get("recommendation", "PASS_THROUGH")
        llm_primary_reason = parsed.get("primary_reason", "Unable to determine")
        llm_suppression_factors = parsed.get("suppression_factors", [])
        llm_pass_through_factors = parsed.get("pass_through_factors", [])
        llm_narrative = parsed.get("analysis_narrative", "")
        llm_reg_override = bool(parsed.get("regulatory_override", False))
        llm_reg_override_reason = parsed.get("regulatory_override_reason", "")

    except Exception as exc:
        logger.error("LLM analysis failed for alert %s: %s", state["alert_id"], exc)
        errors = list(state.get("errors", []))
        errors.append(f"LLM analysis failed: {exc}")
        # Conservative fallback: treat as uncertain, pass through
        return {
            **state,
            "llm_fp_probability": 50.0,
            "llm_confidence": 0.0,
            "llm_recommendation": "PASS_THROUGH",
            "llm_primary_reason": "LLM analysis failed — conservative pass-through",
            "llm_suppression_factors": [],
            "llm_pass_through_factors": ["LLM failure — fallback to manual review"],
            "llm_analysis_narrative": "LLM analysis unavailable.",
            "llm_regulatory_override": False,
            "llm_regulatory_override_reason": "",
            "errors": errors,
        }

    notes = list(state.get("scoring_notes", []))
    notes.append(
        f"LLM assessment: FP={llm_fp_prob:.0f}% | confidence={llm_confidence:.0%} | "
        f"recommendation={llm_recommendation}"
    )

    audit = _append_audit_llm(
        state, "LLM_ANALYSIS_COMPLETE",
        {"fp_probability": llm_fp_prob, "confidence": llm_confidence,
         "recommendation": llm_recommendation, "regulatory_override": llm_reg_override},
        ["claude-sonnet-4-6", "scoring_features", "historical_patterns"],
    )

    return {
        **state,
        "llm_fp_probability": llm_fp_prob,
        "llm_confidence": llm_confidence,
        "llm_recommendation": llm_recommendation,
        "llm_primary_reason": llm_primary_reason,
        "llm_suppression_factors": llm_suppression_factors,
        "llm_pass_through_factors": llm_pass_through_factors,
        "llm_analysis_narrative": llm_narrative,
        "llm_regulatory_override": llm_reg_override,
        "llm_regulatory_override_reason": llm_reg_override_reason,
        "scoring_notes": notes,
        "audit_trail": audit,
    }


# ── Node 7: Composite Score ────────────────────────────────────────────────────

def compute_composite_score_node(state: AlertScoringState) -> AlertScoringState:
    """Combine rule-based, LLM, and historical scores into final composite."""
    if state.get("fallback_to_manual"):
        return state

    composite, breakdown = compute_composite_score(
        rule_based_score=state.get("rule_based_fp_score", 50.0),
        llm_fp_probability=state.get("llm_fp_probability", 50.0),
        features=state["scoring_features"],
    )

    notes = list(state.get("scoring_notes", []))
    notes.append(f"Composite FP score: {composite:.0f}/100")

    audit = _append_audit(
        state, "COMPOSITE_SCORE_COMPUTED",
        {"composite_fp_score": composite, "score_breakdown": breakdown},
        ["scoring_engine"],
    )

    return {
        **state,
        "composite_fp_score": composite,
        "score_breakdown": breakdown,
        "scoring_notes": notes,
        "audit_trail": audit,
    }


# ── Node 8: Routing Decision ───────────────────────────────────────────────────

def determine_routing(state: AlertScoringState) -> AlertScoringState:
    """
    Map composite FP score to a routing decision using ThresholdManager.

    Regulatory override from LLM or rule-based layer forces ESCALATE.
    Manual fallback forces PASS_THROUGH with analyst note.
    """
    # Fallback: route to analysts at HIGH priority
    if state.get("fallback_to_manual"):
        from agent.state import RoutingDecision
        routing = RoutingDecision(
            decision="PASS_THROUGH",
            fp_probability=50.0,
            confidence=0.0,
            primary_reason="Scoring pipeline failure — routed to analyst for manual review",
            suppression_factors=[],
            pass_through_factors=["Scoring failure — conservative manual routing"],
            recommended_priority="HIGH",
            regulatory_override=False,
            regulatory_override_reason="",
        )
        return {**state, "routing": routing}

    features = state["scoring_features"]
    composite = state.get("composite_fp_score", 50.0)

    # Check regulatory override from either source
    reg_override = state.get("llm_regulatory_override", False)
    reg_override_reason = state.get("llm_regulatory_override_reason", "")

    # Also re-run rule-based override check (belt-and-suspenders)
    rule_override, rule_override_reason = check_regulatory_override(features)
    if rule_override and not reg_override:
        reg_override = True
        reg_override_reason = rule_override_reason

    decision, thresholds = _threshold_manager.route(
        fp_probability=composite,
        alert_type=features["alert_type"],
        risk_tier=features["risk_tier"],
        regulatory_override=reg_override,
        regulatory_override_reason=reg_override_reason,
    )

    # ── LLM-agreement guard (conservative, one-direction) ─────────────────
    # An alert may be auto-suppressed or auto-downgraded ONLY when the LLM
    # contextual layer itself supports the false-positive determination.
    # If the deterministic components (rule prescore + historical FP rates)
    # drive the composite over a disposition threshold while the LLM reads
    # the alert as uncertain (fp below the downgrade line), the components
    # disagree — the alert routes to a human analyst instead. This guard can
    # only ADD analyst review; it can never suppress more.
    llm_fp = float(state.get("llm_fp_probability", 50.0))
    if decision in ("SUPPRESS", "DOWNGRADE") and llm_fp < thresholds.downgrade:
        disagreement_note = (
            f"Component disagreement: deterministic composite {composite:.0f} supports "
            f"{decision}, but LLM contextual assessment is {llm_fp:.0f} (< downgrade "
            f"threshold {thresholds.downgrade:.0f}) — conservative PASS_THROUGH to analyst"
        )
        decision = "PASS_THROUGH"
        pass_through_factors = list(state.get("llm_pass_through_factors", [])) + [disagreement_note]
    else:
        pass_through_factors = state.get("llm_pass_through_factors", [])

    # Determine recommended priority for queued alerts
    recommended_priority = _recommend_priority(composite, decision, features)

    from agent.state import RoutingDecision
    routing = RoutingDecision(
        decision=decision,
        fp_probability=composite,
        confidence=state.get("llm_confidence", 0.5),
        primary_reason=state.get("llm_primary_reason", ""),
        suppression_factors=state.get("llm_suppression_factors", []),
        pass_through_factors=pass_through_factors,
        recommended_priority=recommended_priority,
        regulatory_override=reg_override,
        regulatory_override_reason=reg_override_reason,
    )

    notes = list(state.get("scoring_notes", []))
    notes.append(
        f"ROUTING DECISION: {decision} | FP={composite:.0f}% | priority={recommended_priority}"
    )

    audit = _append_audit(
        state, "ROUTING_DECISION_MADE",
        {"decision": decision, "composite_fp_score": composite,
         "regulatory_override": reg_override,
         "effective_suppress_threshold": thresholds.suppress,
         "effective_downgrade_threshold": thresholds.downgrade},
        ["threshold_manager"],
    )

    return {**state, "routing": routing, "scoring_notes": notes, "audit_trail": audit}


# ── Action Nodes ───────────────────────────────────────────────────────────────

def execute_suppression(state: AlertScoringState) -> AlertScoringState:
    """
    Suppress the alert — keep it out of the analyst queue.

    Generates a full regulatory-grade justification narrative via LLM,
    records the suppression in the audit log, and notifies the TMS.
    """
    raw_alert = state["raw_alert"]
    customer = state["customer_summary"]
    routing = state["routing"]

    # Generate regulatory-grade justification
    justification_prompt = SUPPRESSION_JUSTIFICATION_PROMPT.format(
        system_persona=SYSTEM_PERSONA,
        alert_id=raw_alert["alert_id"],
        alert_type=raw_alert["alert_type"],
        customer_name=customer["full_name"],
        risk_tier=customer["risk_tier"],
        business_type=customer["business_type"],
        amount=raw_alert["amount"],
        fp_probability=routing["fp_probability"],
        confidence=routing["confidence"],
        primary_reason=routing["primary_reason"],
        suppression_factors="; ".join(routing["suppression_factors"]),
    )

    try:
        justification_response = _llm.invoke(justification_prompt)
        justification_narrative = justification_response.content.strip()
    except Exception as exc:
        logger.error("Justification generation failed: %s", exc)
        justification_narrative = routing["primary_reason"]

    # Record suppression with 90-day review date
    suppression_record = record_suppression(
        alert_id=raw_alert["alert_id"],
        customer_id=state["customer_id"],
        alert_type=raw_alert["alert_type"],
        fp_probability=routing["fp_probability"],
        confidence=routing["confidence"],
        primary_reason=routing["primary_reason"],
        suppression_factors=routing["suppression_factors"],
        pass_through_factors=routing["pass_through_factors"],
        justification_narrative=justification_narrative,
        score_breakdown=state.get("score_breakdown", {}),
        thresholds_used=_threshold_manager.explain_thresholds(
            state["scoring_features"]["alert_type"],
            state["scoring_features"]["risk_tier"],
        ),
    )

    # Notify TMS
    update_alert_disposition(
        alert_id=raw_alert["alert_id"],
        disposition="SUPPRESSED",
        new_priority=None,
        reason=routing["primary_reason"],
        fp_probability=routing["fp_probability"],
    )

    audit = _append_audit_llm(
        state, "ALERT_SUPPRESSED",
        {"suppression_id": suppression_record["suppression_id"],
         "fp_probability": routing["fp_probability"],
         "review_date": suppression_record["mandatory_review_date"]},
        ["suppression_engine", "tms_connector", "claude-sonnet-4-6"],
    )

    logger.info(
        "SUPPRESSED alert %s | FP=%.0f%% | review_due=%s",
        raw_alert["alert_id"], routing["fp_probability"],
        suppression_record["mandatory_review_date"],
    )

    return {
        **state,
        "queue_action": "suppressed",
        "tms_updated": True,
        "downstream_queue_notified": False,
        "suppression_id": suppression_record["suppression_id"],
        "suppression_timestamp": suppression_record["suppressed_at"],
        "suppression_justification": justification_narrative,
        "suppression_review_date": suppression_record["mandatory_review_date"],
        "audit_trail": audit,
    }


def execute_downgrade(state: AlertScoringState) -> AlertScoringState:
    """Downgrade alert priority before releasing to analyst queue."""
    raw_alert = state["raw_alert"]
    customer = state["customer_summary"]
    routing = state["routing"]

    original_priority = raw_alert["severity"]
    new_priority = routing["recommended_priority"]

    # Brief downgrade justification
    try:
        dg_prompt = DOWNGRADE_JUSTIFICATION_PROMPT.format(
            system_persona=SYSTEM_PERSONA,
            alert_id=raw_alert["alert_id"],
            alert_type=raw_alert["alert_type"],
            customer_name=customer["full_name"],
            risk_tier=customer["risk_tier"],
            original_priority=original_priority,
            new_priority=new_priority,
            fp_probability=routing["fp_probability"],
            suppression_factors="; ".join(routing["suppression_factors"]),
        )
        dg_response = _llm.invoke(dg_prompt)
        justification = dg_response.content.strip()
    except Exception:
        justification = routing["primary_reason"]

    record_downgrade(
        alert_id=raw_alert["alert_id"],
        customer_id=state["customer_id"],
        original_priority=original_priority,
        new_priority=new_priority,
        fp_probability=routing["fp_probability"],
        reason=routing["primary_reason"],
        justification=justification,
    )

    update_alert_disposition(
        alert_id=raw_alert["alert_id"],
        disposition="DOWNGRADED",
        new_priority=new_priority,
        reason=routing["primary_reason"],
        fp_probability=routing["fp_probability"],
    )

    audit = _append_audit(
        state, "ALERT_DOWNGRADED",
        {"original_priority": original_priority, "new_priority": new_priority,
         "fp_probability": routing["fp_probability"]},
        ["suppression_engine", "tms_connector"],
    )

    logger.info("DOWNGRADED alert %s | %s→%s | FP=%.0f%%",
                raw_alert["alert_id"], original_priority, new_priority, routing["fp_probability"])

    return {
        **state,
        "queue_action": "downgraded",
        "tms_updated": True,
        "downstream_queue_notified": True,
        "audit_trail": audit,
    }


def enqueue_alert(state: AlertScoringState) -> AlertScoringState:
    """Pass alert to analyst queue at AI-recommended priority."""
    raw_alert = state["raw_alert"]
    routing = state["routing"]

    record_pass_through(
        alert_id=raw_alert["alert_id"],
        customer_id=state["customer_id"],
        priority=routing["recommended_priority"],
        fp_probability=routing["fp_probability"],
        reason=routing["primary_reason"],
    )

    update_alert_disposition(
        alert_id=raw_alert["alert_id"],
        disposition="QUEUED",
        new_priority=routing["recommended_priority"],
        reason=routing["primary_reason"],
        fp_probability=routing["fp_probability"],
    )

    audit = _append_audit(
        state, "ALERT_QUEUED",
        {"priority": routing["recommended_priority"],
         "fp_probability": routing["fp_probability"]},
        ["tms_connector", "investigation_queue"],
    )

    logger.info("QUEUED alert %s | priority=%s | FP=%.0f%%",
                raw_alert["alert_id"], routing["recommended_priority"],
                routing["fp_probability"])

    return {
        **state,
        "queue_action": "queued",
        "tms_updated": True,
        "downstream_queue_notified": True,
        "audit_trail": audit,
    }


def execute_escalation(state: AlertScoringState) -> AlertScoringState:
    """Fast-track alert to senior analyst / FCU at HIGH priority."""
    raw_alert = state["raw_alert"]
    routing = state["routing"]

    record_escalation(
        alert_id=raw_alert["alert_id"],
        customer_id=state["customer_id"],
        fp_probability=routing["fp_probability"],
        reason=routing["primary_reason"],
    )

    update_alert_disposition(
        alert_id=raw_alert["alert_id"],
        disposition="ESCALATED",
        new_priority="HIGH",
        reason=routing["primary_reason"],
        fp_probability=routing["fp_probability"],
    )

    audit = _append_audit(
        state, "ALERT_ESCALATED",
        {"fp_probability": routing["fp_probability"],
         "regulatory_override": routing.get("regulatory_override", False),
         "reason": routing["primary_reason"]},
        ["tms_connector", "investigation_queue"],
    )

    logger.info("ESCALATED alert %s | FP=%.0f%% | reason=%s",
                raw_alert["alert_id"], routing["fp_probability"],
                routing["primary_reason"][:80])

    return {
        **state,
        "queue_action": "escalated",
        "tms_updated": True,
        "downstream_queue_notified": True,
        "audit_trail": audit,
    }


# ── Final Node ─────────────────────────────────────────────────────────────────

def finalize_scoring(state: AlertScoringState) -> AlertScoringState:
    """Close the scoring record with timing and final audit entry."""
    scored_at = _now()
    ingested_at = state.get("ingested_at", scored_at)

    try:
        from datetime import datetime as dt
        t_in = dt.fromisoformat(ingested_at.rstrip("Z"))
        t_out = dt.fromisoformat(scored_at.rstrip("Z"))
        processing_ms = int((t_out - t_in).total_seconds() * 1000)
    except Exception:
        processing_ms = 0

    action = state.get("queue_action", "unknown")
    notes = list(state.get("scoring_notes", []))
    notes.append(
        f"Scoring complete | action={action} | processing_time={processing_ms}ms"
    )

    audit = _append_audit(
        state, "SCORING_FINALIZED",
        {"queue_action": action,
         "composite_fp_score": state.get("composite_fp_score", 0),
         "processing_time_ms": processing_ms,
         "error_count": len(state.get("errors", []))},
        ["scoring_engine"],
    )

    return {
        **state,
        "scored_at": scored_at,
        "processing_time_ms": processing_ms,
        "scoring_notes": notes,
        "audit_trail": audit,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _recommend_priority(fp_score: float, decision: str, features: dict) -> str:
    """Map FP score and decision to an analyst queue priority."""
    if decision == "ESCALATE":
        return "HIGH"
    if decision == "SUPPRESS":
        return "NONE"
    if decision == "DOWNGRADE":
        return "LOW" if fp_score >= 75 else "MEDIUM"
    # PASS_THROUGH
    if fp_score <= 30:
        return "HIGH"
    elif fp_score <= 50:
        return "MEDIUM"
    else:
        return "LOW"


def _format_history_summary(history: list[dict]) -> str:
    if not history:
        return "No prior alert history for this customer"
    lines = [
        f"{h.get('date', 'unknown')}: {h.get('alert_type', '?')} → {h.get('outcome', '?')}"
        for h in history[-5:]  # Last 5 alerts
    ]
    return "; ".join(lines)
