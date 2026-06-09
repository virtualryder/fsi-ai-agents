# agent/nodes.py
# ============================================================
# Trading Surveillance Agent — Node Functions
#
# LLM/Python boundary:
#   Python ONLY: pattern_detection, risk_scoring, routing_decision
#   LLM:         market_context, investigation, disposition, SAR narrative
#
# This boundary is enforced for FINRA Rule 3110 supervisory
# procedures and SR 11-7 model risk management requirements.
# ============================================================
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from agent.prompts import (
    DISPOSITION_SYSTEM_PROMPT,
    DISPOSITION_USER_PROMPT,
    INVESTIGATION_SYSTEM_PROMPT,
    INVESTIGATION_USER_PROMPT,
    MARKET_CONTEXT_PROMPT,
    SAR_NARRATIVE_SYSTEM_PROMPT,
    SAR_NARRATIVE_USER_PROMPT,
)
from agent.state import (
    AlertType,
    AssetClass,
    CaseStatus,
    DispositionOutcome,
    SeverityTier,
    TradingSurveillanceState,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Alert types that ALWAYS require HITL regardless of score
ALWAYS_HITL_ALERT_TYPES = {
    AlertType.INSIDER_TRADING.value,
    AlertType.INFORMATION_BARRIER_BREACH.value,
    AlertType.CROSS_MARKET_MANIPULATION.value,
}

# Base severity scores by alert type (pattern severity component)
ALERT_TYPE_BASE_SEVERITY = {
    AlertType.INSIDER_TRADING.value: 0.95,
    AlertType.LAYERING_SPOOFING.value: 0.90,
    AlertType.CROSS_MARKET_MANIPULATION.value: 0.88,
    AlertType.FRONT_RUNNING.value: 0.85,
    AlertType.INFORMATION_BARRIER_BREACH.value: 0.85,
    AlertType.WASH_TRADING.value: 0.80,
    AlertType.MARKING_THE_CLOSE.value: 0.75,
    AlertType.SHORT_SELLING_VIOLATION.value: 0.70,
    AlertType.EXCESSIVE_TRADING.value: 0.55,
    AlertType.BEST_EXECUTION_FAILURE.value: 0.50,
    AlertType.UNUSUAL_ACTIVITY.value: 0.40,
}

# Regulatory flags by alert type
ALERT_REGULATORY_FLAGS = {
    AlertType.INSIDER_TRADING.value: [
        "SEA Section 10(b)", "SEC Rule 10b-5", "18 U.S.C. § 1348",
        "Dodd-Frank Section 929L", "SAR consideration — 31 CFR § 1023.320",
    ],
    AlertType.LAYERING_SPOOFING.value: [
        "SEA Section 9(a)(2)", "Dodd-Frank Section 747 (spoofing ban)",
        "CFTC Regulation 180.1", "FINRA Rule 5210", "FINRA Rule 2010",
    ],
    AlertType.FRONT_RUNNING.value: [
        "SEA Section 10(b)", "SEC Rule 10b-5", "FINRA Rule 5270",
        "FINRA Rule 2010", "Investment Advisers Act Section 206",
    ],
    AlertType.WASH_TRADING.value: [
        "SEA Section 9(a)(1)", "CFTC Commodity Exchange Act Section 4c(a)",
        "FINRA Rule 5210", "SAR consideration — 31 CFR § 1023.320",
    ],
    AlertType.MARKING_THE_CLOSE.value: [
        "SEA Section 9(a)(2)", "FINRA Rule 5210", "FINRA Rule 2010",
    ],
    AlertType.CROSS_MARKET_MANIPULATION.value: [
        "SEA Section 9(a)(2)", "CFTC Commodity Exchange Act Section 6(c)",
        "Dodd-Frank Section 747", "SEC Rule 10b-5",
        "SAR consideration — 31 CFR § 1023.320",
    ],
    AlertType.INFORMATION_BARRIER_BREACH.value: [
        "SEA Section 10(b)", "SEC Rule 10b-5", "Regulation FD",
        "FINRA Rule 3110", "18 U.S.C. § 1348",
    ],
    AlertType.SHORT_SELLING_VIOLATION.value: [
        "SEC Regulation SHO Rule 203", "SEC Regulation SHO Rule 204",
        "SEA Section 9(a)(1)",
    ],
    AlertType.EXCESSIVE_TRADING.value: [
        "FINRA Rule 2111 (suitability)", "FINRA Rule 2010",
        "SEC Rule 15c3-5 (market access)",
    ],
    AlertType.BEST_EXECUTION_FAILURE.value: [
        "FINRA Rule 5310", "SEC Rule 606", "Reg NMS Rule 611",
        "FINRA Rule 2010",
    ],
    AlertType.UNUSUAL_ACTIVITY.value: [
        "FINRA Rule 3110", "SAR consideration — 31 CFR § 1023.320",
    ],
}

# Routing matrix by asset class
ASSET_CLASS_ROUTING = {
    AssetClass.EQUITY.value: {
        "primary": "EQUITIES_SURVEILLANCE_OFFICER",
        "secondary": ["HEAD_OF_EQUITIES_COMPLIANCE", "CHIEF_COMPLIANCE_OFFICER"],
    },
    AssetClass.FIXED_INCOME.value: {
        "primary": "FIXED_INCOME_SURVEILLANCE_OFFICER",
        "secondary": ["HEAD_OF_FIXED_INCOME_COMPLIANCE", "CHIEF_COMPLIANCE_OFFICER"],
    },
    AssetClass.DERIVATIVES.value: {
        "primary": "DERIVATIVES_SURVEILLANCE_OFFICER",
        "secondary": ["HEAD_OF_DERIVATIVES_COMPLIANCE", "CHIEF_COMPLIANCE_OFFICER"],
    },
    AssetClass.FX.value: {
        "primary": "FX_SURVEILLANCE_OFFICER",
        "secondary": ["HEAD_OF_FX_COMPLIANCE", "CHIEF_COMPLIANCE_OFFICER"],
    },
    AssetClass.COMMODITIES.value: {
        "primary": "COMMODITIES_SURVEILLANCE_OFFICER",
        "secondary": ["HEAD_OF_COMMODITIES_COMPLIANCE", "CHIEF_COMPLIANCE_OFFICER"],
    },
    AssetClass.CRYPTO.value: {
        "primary": "DIGITAL_ASSETS_SURVEILLANCE_OFFICER",
        "secondary": ["CHIEF_COMPLIANCE_OFFICER", "LEGAL_COUNSEL"],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def _add_audit_entry(
    state: TradingSurveillanceState,
    node: str,
    action: str,
    data_sources: List[str] = None,
    ai_model: str = None,
    regulatory_basis: str = None,
) -> List[Dict[str, Any]]:
    trail = list(state.get("audit_trail", []))
    trail.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "node": node,
        "actor": "compliance_officer" if node == "human_review_gate" else "ai_agent",
        "action": action,
        "data_sources_accessed": data_sources or [],
        "ai_model_used": ai_model,
        "regulatory_basis": regulatory_basis,
        "human_review_required": state.get("human_review_required", False),
    })
    return trail


def _load_trader_registry() -> List[Dict[str, Any]]:
    try:
        path = os.path.join("data", "fixtures", "trader_registry.json")
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _load_routing_matrix() -> Dict[str, Any]:
    try:
        path = os.path.join("data", "fixtures", "routing_matrix.json")
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _compute_notional_score(notional: float) -> float:
    """Score based on trade notional value."""
    if notional < 10_000:
        return 0.10
    elif notional < 100_000:
        return 0.25
    elif notional < 1_000_000:
        return 0.50
    elif notional < 10_000_000:
        return 0.75
    else:
        return 0.95


def _compute_recidivism_score(prior_count: int) -> float:
    """Score based on prior alert history for this trader."""
    if prior_count == 0:
        return 0.10
    elif prior_count == 1:
        return 0.30
    elif prior_count <= 3:
        return 0.55
    elif prior_count <= 5:
        return 0.75
    else:
        return 0.90


def _compute_regulatory_exposure_score(
    alert_type: str,
    restricted_list_hit: bool,
    sar_threshold_met: bool,
) -> float:
    """Score based on regulatory reporting exposure."""
    base_scores = {
        AlertType.INSIDER_TRADING.value: 0.95,
        AlertType.CROSS_MARKET_MANIPULATION.value: 0.92,
        AlertType.INFORMATION_BARRIER_BREACH.value: 0.90,
        AlertType.WASH_TRADING.value: 0.85,
        AlertType.LAYERING_SPOOFING.value: 0.85,
        AlertType.FRONT_RUNNING.value: 0.80,
        AlertType.MARKING_THE_CLOSE.value: 0.70,
        AlertType.SHORT_SELLING_VIOLATION.value: 0.70,
        AlertType.EXCESSIVE_TRADING.value: 0.50,
        AlertType.BEST_EXECUTION_FAILURE.value: 0.45,
        AlertType.UNUSUAL_ACTIVITY.value: 0.35,
    }
    score = base_scores.get(alert_type, 0.30)
    if restricted_list_hit:
        score = min(1.0, score + 0.10)
    if sar_threshold_met:
        score = min(1.0, score + 0.05)
    return score


def _compute_evidence_quality_score(
    corroborating_signals: List[str],
    pattern_confidence_scores: Dict[str, float],
) -> float:
    """Score based on quantity and quality of supporting evidence."""
    signal_count = len(corroborating_signals)
    avg_confidence = (
        sum(pattern_confidence_scores.values()) / len(pattern_confidence_scores)
        if pattern_confidence_scores else 0.20
    )
    if signal_count == 0:
        base = 0.15
    elif signal_count <= 1:
        base = 0.30
    elif signal_count <= 3:
        base = 0.55
    elif signal_count <= 5:
        base = 0.75
    else:
        base = 0.90
    return min(1.0, (base + avg_confidence) / 2)


# ── Node Functions ────────────────────────────────────────────────────────────

def alert_intake_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Receive a surveillance alert, assign a case ID, normalize timestamps,
    and initialize the audit trail.
    """
    now = datetime.utcnow()
    trader_id = state.get("trader_id", "UNK")
    alert_type = state.get("alert_type", "UNUSUAL_ACTIVITY")

    alert_id = state.get("alert_id") or (
        f"SURV-{now.strftime('%Y%m%d')}-{alert_type[:3]}-{uuid.uuid4().hex[:6].upper()}"
    )

    audit_trail = _add_audit_entry(
        state,
        node="alert_intake",
        action=(
            f"Alert received: {alert_type} on trader {trader_id}. "
            f"Assigned case ID {alert_id}. Workflow initiated."
        ),
        data_sources=["surveillance_system_feed"],
        regulatory_basis="FINRA Rule 3110 — supervisory procedures",
    )

    return {
        **state,
        "alert_id": alert_id,
        "alert_timestamp": state.get("alert_timestamp", now.isoformat() + "Z"),
        "case_status": CaseStatus.OPEN.value,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["alert_intake"],
        "errors": list(state.get("errors", [])),
        "corroborating_signals": list(state.get("corroborating_signals", [])),
        "prior_alerts": list(state.get("prior_alerts", [])),
        "detected_patterns": list(state.get("detected_patterns", [])),
        "regulatory_flags": list(state.get("regulatory_flags", [])),
        "secondary_reviewers": list(state.get("secondary_reviewers", [])),
        "evidence_summary": list(state.get("evidence_summary", [])),
        "regulatory_reporting_bodies": list(state.get("regulatory_reporting_bodies", [])),
    }


def data_enrichment_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Enrich alert with trader history, account risk tier, and watch/restricted
    list status. All lookups are Python — no LLM.
    """
    trader_id = state.get("trader_id", "")
    instrument_id = state.get("instrument_id", "")
    notional = float(state.get("notional_value", 0))

    # Load trader registry
    registry = _load_trader_registry()
    trader_record = next(
        (t for t in registry if t.get("trader_id") == trader_id), None
    )

    if trader_record:
        prior_alerts = trader_record.get("prior_alerts", [])
        prior_alert_count = len(prior_alerts)
        account_risk_tier = trader_record.get("account_risk_tier", "STANDARD")
        pep_flag = trader_record.get("pep_flag", False)
        restricted_instruments = trader_record.get("restricted_instruments", [])
        watch_instruments = trader_record.get("watch_instruments", [])

        trader_history_summary = (
            f"Trader {trader_record.get('trader_name', trader_id)} "
            f"has {prior_alert_count} prior surveillance alert(s) in the past 12 months. "
            f"Account risk tier: {account_risk_tier}. "
            f"{'PEP-associated. ' if pep_flag else ''}"
            f"Prior alert types: {', '.join(set(a.get('alert_type', '') for a in prior_alerts)) or 'None'}."
        )
        restricted_list_hit = instrument_id in restricted_instruments
        watch_list_hit = instrument_id in watch_instruments
    else:
        prior_alerts = []
        prior_alert_count = 0
        account_risk_tier = "STANDARD"
        pep_flag = False
        restricted_list_hit = False
        watch_list_hit = False
        trader_history_summary = f"No prior surveillance record found for trader ID {trader_id}."

    # Identify corroborating signals from raw alert data
    raw = state.get("raw_alert_data", {})
    signals = list(state.get("corroborating_signals", []))

    if restricted_list_hit:
        signals.append("RESTRICTED_LIST_HIT — instrument on firm restricted list")
    if watch_list_hit:
        signals.append("WATCH_LIST_HIT — instrument on heightened scrutiny list")
    if pep_flag:
        signals.append("PEP_FLAG — trader or counterparty politically exposed person")
    if prior_alert_count >= 3:
        signals.append(f"RECIDIVIST — {prior_alert_count} prior alerts in 12 months")
    if notional >= 1_000_000:
        signals.append(f"LARGE_NOTIONAL — ${notional:,.0f} trade size")
    if raw.get("cancel_rate", 0) >= 0.80:
        signals.append(f"HIGH_CANCEL_RATE — {raw.get('cancel_rate', 0):.0%} orders cancelled")
    if raw.get("related_accounts"):
        signals.append(f"RELATED_ACCOUNTS — activity linked to {len(raw.get('related_accounts', []))} related accounts")
    if raw.get("pre_trade_news"):
        signals.append("PRE_TRADE_NEWS — material news preceded trade")
    if raw.get("short_exempt") is False and raw.get("locate_obtained") is False:
        signals.append("NO_LOCATE — short sale without documented locate")

    audit_trail = _add_audit_entry(
        state,
        node="data_enrichment",
        action=(
            f"Enrichment complete. Trader history: {prior_alert_count} prior alerts. "
            f"Restricted list: {restricted_list_hit}. Watch list: {watch_list_hit}. "
            f"Corroborating signals: {len(signals)}."
        ),
        data_sources=["trader_registry", "restricted_list", "watch_list", "account_database"],
        regulatory_basis="FINRA Rule 3110; SEC Rule 17a-4",
    )

    return {
        **state,
        "trader_history_summary": trader_history_summary,
        "prior_alert_count": prior_alert_count,
        "prior_alerts": prior_alerts,
        "account_risk_tier": account_risk_tier,
        "restricted_list_hit": restricted_list_hit,
        "watch_list_hit": watch_list_hit,
        "pep_flag": pep_flag,
        "corroborating_signals": signals,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["data_enrichment"],
    }


def pattern_detection_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Python rule engine for pattern detection.
    All pattern logic is deterministic Python — no LLM.
    Each pattern produces a confidence score 0.0–1.0.
    """
    alert_type = state.get("alert_type", AlertType.UNUSUAL_ACTIVITY.value)
    raw = state.get("raw_alert_data", {})
    notional = float(state.get("notional_value", 0))
    asset_class = state.get("asset_class", "")

    detected = list(state.get("detected_patterns", []))
    confidence_scores: Dict[str, float] = {}
    rationale_parts = []
    reg_flags = list(
        ALERT_REGULATORY_FLAGS.get(alert_type, ALERT_REGULATORY_FLAGS[AlertType.UNUSUAL_ACTIVITY.value])
    )

    # ── LAYERING / SPOOFING detection ──
    cancel_rate = float(raw.get("cancel_rate", 0))
    order_count = int(raw.get("order_count", 0))
    opposite_side_orders = bool(raw.get("opposite_side_orders", False))

    if alert_type == AlertType.LAYERING_SPOOFING.value or (
        cancel_rate >= 0.80 and order_count >= 5 and opposite_side_orders
    ):
        confidence = min(1.0, 0.40 + cancel_rate * 0.40 + (0.20 if opposite_side_orders else 0))
        if AlertType.LAYERING_SPOOFING.value not in detected:
            detected.append(AlertType.LAYERING_SPOOFING.value)
        confidence_scores[AlertType.LAYERING_SPOOFING.value] = confidence
        rationale_parts.append(
            f"Layering/spoofing: {cancel_rate:.0%} cancel rate on {order_count} orders "
            f"with {'confirmed' if opposite_side_orders else 'no'} opposite-side orders."
        )
        for flag in ALERT_REGULATORY_FLAGS[AlertType.LAYERING_SPOOFING.value]:
            if flag not in reg_flags:
                reg_flags.append(flag)

    # ── FRONT RUNNING detection ──
    pre_position = float(raw.get("pre_customer_order_position", 0))
    customer_order_size = float(raw.get("customer_order_size", 0))
    direction_match = bool(raw.get("direction_matches_customer_order", False))

    if alert_type == AlertType.FRONT_RUNNING.value or (
        pre_position > 0 and customer_order_size > 0 and direction_match
    ):
        time_gap_seconds = float(raw.get("time_gap_seconds", 999))
        confidence = min(1.0, 0.50 + (0.30 if time_gap_seconds < 30 else 0.10) + (0.20 if direction_match else 0))
        if AlertType.FRONT_RUNNING.value not in detected:
            detected.append(AlertType.FRONT_RUNNING.value)
        confidence_scores[AlertType.FRONT_RUNNING.value] = confidence
        rationale_parts.append(
            f"Front running: proprietary position established {time_gap_seconds:.0f}s before "
            f"${customer_order_size:,.0f} customer order in same direction."
        )
        for flag in ALERT_REGULATORY_FLAGS[AlertType.FRONT_RUNNING.value]:
            if flag not in reg_flags:
                reg_flags.append(flag)

    # ── WASH TRADING detection ──
    related_accounts = raw.get("related_accounts", [])
    same_instrument_both_sides = bool(raw.get("same_instrument_both_sides", False))

    if alert_type == AlertType.WASH_TRADING.value or (
        related_accounts and same_instrument_both_sides
    ):
        confidence = min(1.0, 0.60 + (0.20 if len(related_accounts) > 1 else 0.10))
        if AlertType.WASH_TRADING.value not in detected:
            detected.append(AlertType.WASH_TRADING.value)
        confidence_scores[AlertType.WASH_TRADING.value] = confidence
        rationale_parts.append(
            f"Wash trading: buy/sell of same instrument across {len(related_accounts)} "
            f"related account(s) with no change in beneficial ownership."
        )
        for flag in ALERT_REGULATORY_FLAGS[AlertType.WASH_TRADING.value]:
            if flag not in reg_flags:
                reg_flags.append(flag)

    # ── INSIDER TRADING / INFORMATION BARRIER BREACH detection ──
    restricted_list_hit = bool(state.get("restricted_list_hit", False))
    pre_trade_news = bool(raw.get("pre_trade_news", False))
    material_nonpublic = bool(raw.get("material_nonpublic_information_flag", False))

    if alert_type in (AlertType.INSIDER_TRADING.value, AlertType.INFORMATION_BARRIER_BREACH.value) or (
        restricted_list_hit and (pre_trade_news or material_nonpublic)
    ):
        if alert_type == AlertType.INFORMATION_BARRIER_BREACH.value:
            atype = AlertType.INFORMATION_BARRIER_BREACH.value
        else:
            atype = AlertType.INSIDER_TRADING.value
        confidence = min(1.0, 0.55 + (0.25 if restricted_list_hit else 0) + (0.20 if pre_trade_news else 0))
        if atype not in detected:
            detected.append(atype)
        confidence_scores[atype] = confidence
        rationale_parts.append(
            f"{'Information barrier breach' if atype == AlertType.INFORMATION_BARRIER_BREACH.value else 'Insider trading'}: "
            f"{'instrument on restricted list, ' if restricted_list_hit else ''}"
            f"{'material news preceded trade, ' if pre_trade_news else ''}"
            f"{'MNPI flag set' if material_nonpublic else ''}."
        )
        for flag in ALERT_REGULATORY_FLAGS[atype]:
            if flag not in reg_flags:
                reg_flags.append(flag)

    # ── MARKING THE CLOSE detection ──
    pct_volume_last_30_min = float(raw.get("pct_volume_last_30_min", 0))
    closing_price_impact = float(raw.get("closing_price_impact_bps", 0))

    if alert_type == AlertType.MARKING_THE_CLOSE.value or (
        pct_volume_last_30_min >= 0.25 and closing_price_impact >= 10
    ):
        confidence = min(1.0, 0.40 + pct_volume_last_30_min * 0.40 + min(closing_price_impact / 100, 0.20))
        if AlertType.MARKING_THE_CLOSE.value not in detected:
            detected.append(AlertType.MARKING_THE_CLOSE.value)
        confidence_scores[AlertType.MARKING_THE_CLOSE.value] = confidence
        rationale_parts.append(
            f"Marking the close: {pct_volume_last_30_min:.0%} of daily volume in final 30 minutes, "
            f"{closing_price_impact:.0f} bps closing price impact."
        )

    # ── SHORT SELLING VIOLATION detection ──
    short_sale = bool(raw.get("short_sale", False))
    locate_obtained = bool(raw.get("locate_obtained", True))
    ftd_flag = bool(raw.get("failure_to_deliver", False))

    if alert_type == AlertType.SHORT_SELLING_VIOLATION.value or (
        short_sale and not locate_obtained
    ) or ftd_flag:
        confidence = 0.85 if (short_sale and not locate_obtained) else 0.70
        if AlertType.SHORT_SELLING_VIOLATION.value not in detected:
            detected.append(AlertType.SHORT_SELLING_VIOLATION.value)
        confidence_scores[AlertType.SHORT_SELLING_VIOLATION.value] = confidence
        rationale_parts.append(
            f"Short selling violation: "
            f"{'no locate documented' if not locate_obtained else ''}"
            f"{', failure to deliver' if ftd_flag else ''}."
        )

    # ── Baseline: if alert type not yet detected, add with base confidence ──
    if not detected:
        detected.append(alert_type)
        confidence_scores[alert_type] = ALERT_TYPE_BASE_SEVERITY.get(alert_type, 0.40) * 0.75
        rationale_parts.append(
            f"Alert type {alert_type} triggered by surveillance system. "
            f"Pattern rules did not identify additional corroborating pattern signals."
        )

    if AlertType.UNUSUAL_ACTIVITY.value not in detected and not rationale_parts:
        detected.append(AlertType.UNUSUAL_ACTIVITY.value)
        confidence_scores[AlertType.UNUSUAL_ACTIVITY.value] = 0.35

    audit_trail = _add_audit_entry(
        state,
        node="pattern_detection",
        action=(
            f"Pattern detection complete. Detected: {', '.join(detected)}. "
            f"Regulatory flags: {len(reg_flags)}."
        ),
        data_sources=["surveillance_rule_engine", "order_management_system"],
        regulatory_basis="FINRA Rule 3110; SEA Section 10(b); Dodd-Frank Section 747",
    )

    return {
        **state,
        "detected_patterns": detected,
        "pattern_confidence_scores": confidence_scores,
        "pattern_rationale": " | ".join(rationale_parts) or "Pattern analysis complete.",
        "regulatory_flags": reg_flags,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["pattern_detection"],
    }


def market_context_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    LLM-powered market context summary. Identifies publicly known events
    that may provide legitimate explanation for unusual trading activity.
    """
    alert_type = state.get("alert_type", "")
    notional = float(state.get("notional_value", 0))
    direction = state.get("trade_direction", "")

    activity_description = (
        f"{direction} of ${notional:,.0f} notional — {alert_type.replace('_', ' ').lower()} alert"
    )

    prompt = MARKET_CONTEXT_PROMPT.format(
        instrument_name=state.get("instrument_name", "Unknown"),
        instrument_id=state.get("instrument_id", ""),
        asset_class=state.get("asset_class", ""),
        trade_date=state.get("trade_date", ""),
        alert_type=alert_type,
        activity_description=activity_description,
    )

    try:
        llm = _get_llm()
        response = llm.invoke(prompt)
        market_context = response.content
        ai_model = "gpt-4o"
    except Exception as e:
        logger.warning(f"Market context LLM failed: {e}")
        market_context = (
            f"Market context lookup unavailable. "
            f"Manual review of {state.get('instrument_name', '')} news and corporate events "
            f"for {state.get('trade_date', '')} is recommended."
        )
        ai_model = None

    audit_trail = _add_audit_entry(
        state,
        node="market_context",
        action="Market context summary generated for instrument and trade date.",
        data_sources=["market_data_api", "news_feed"],
        ai_model=ai_model,
        regulatory_basis="FINRA Rule 3110; SEC Rule 10b-5 (context assessment)",
    )

    return {
        **state,
        "market_context_summary": market_context,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["market_context"],
    }


def risk_scoring_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Python-only composite risk scoring (SR 11-7 / FINRA Rule 3110 compliant).

    5-factor model:
      Pattern Severity      25%  — inherent seriousness of detected alert type
      Trade Size/Impact     25%  — notional value relative to market
      Recidivism/History    20%  — prior alert count for this trader
      Regulatory Exposure   15%  — mandatory reporting obligations at stake
      Evidence Quality      15%  — number and quality of corroborating signals

    Hard overrides:
      INSIDER_TRADING/INFORMATION_BARRIER_BREACH → minimum CRITICAL
      restricted_list_hit → minimum HIGH
      prior_alert_count >= 6 and HIGH → escalate to CRITICAL
    """
    alert_type = state.get("alert_type", AlertType.UNUSUAL_ACTIVITY.value)
    notional = float(state.get("notional_value", 0))
    prior_count = int(state.get("prior_alert_count", 0))
    restricted_hit = bool(state.get("restricted_list_hit", False))
    signals = list(state.get("corroborating_signals", []))
    confidence_scores = dict(state.get("pattern_confidence_scores", {}))
    alert_data = state.get("raw_alert_data", {})

    # ── Factor 1: Pattern Severity (25%) ──
    pattern_severity = max(
        (ALERT_TYPE_BASE_SEVERITY.get(p, 0.40) for p in state.get("detected_patterns", [alert_type])),
        default=ALERT_TYPE_BASE_SEVERITY.get(alert_type, 0.40),
    )

    # ── Factor 2: Trade Size / Market Impact (25%) ──
    trade_size_score = _compute_notional_score(notional)

    # ── Factor 3: Recidivism / History (20%) ──
    recidivism_score = _compute_recidivism_score(prior_count)

    # ── Factor 4: Regulatory Exposure (15%) ──
    sar_threshold_met = notional >= 5_000 and alert_type in {
        AlertType.INSIDER_TRADING.value,
        AlertType.WASH_TRADING.value,
        AlertType.CROSS_MARKET_MANIPULATION.value,
        AlertType.UNUSUAL_ACTIVITY.value,
    }
    regulatory_exposure_score = _compute_regulatory_exposure_score(
        alert_type, restricted_hit, sar_threshold_met
    )

    # ── Factor 5: Evidence Quality (15%) ──
    evidence_quality_score = _compute_evidence_quality_score(signals, confidence_scores)

    # ── Composite Score ──
    composite = (
        pattern_severity * 0.25
        + trade_size_score * 0.25
        + recidivism_score * 0.20
        + regulatory_exposure_score * 0.15
        + evidence_quality_score * 0.15
    )
    composite = round(min(1.0, max(0.0, composite)), 4)

    # ── Tier Assignment ──
    if composite >= 0.85:
        tier = SeverityTier.CRITICAL.value
    elif composite >= 0.65:
        tier = SeverityTier.HIGH.value
    elif composite >= 0.40:
        tier = SeverityTier.MEDIUM.value
    else:
        tier = SeverityTier.LOW.value

    # ── Hard Overrides ──
    override_reason = []

    if alert_type in ALWAYS_HITL_ALERT_TYPES:
        if tier not in (SeverityTier.CRITICAL.value,):
            tier = SeverityTier.CRITICAL.value
            composite = max(composite, 0.85)
            override_reason.append(
                f"OVERRIDE: {alert_type} always escalated to CRITICAL per policy"
            )

    if restricted_hit and tier == SeverityTier.MEDIUM.value:
        tier = SeverityTier.HIGH.value
        composite = max(composite, 0.65)
        override_reason.append(
            "OVERRIDE: restricted list hit — tier escalated to HIGH"
        )

    if prior_count >= 6 and tier == SeverityTier.HIGH.value:
        tier = SeverityTier.CRITICAL.value
        composite = max(composite, 0.85)
        override_reason.append(
            f"OVERRIDE: {prior_count} prior alerts — recidivist trader escalated to CRITICAL"
        )

    sar_consideration = sar_threshold_met and tier in (
        SeverityTier.CRITICAL.value, SeverityTier.HIGH.value
    )

    components = {
        "pattern_severity_score": round(pattern_severity, 4),
        "trade_size_score": round(trade_size_score, 4),
        "recidivism_score": round(recidivism_score, 4),
        "regulatory_exposure_score": round(regulatory_exposure_score, 4),
        "evidence_quality_score": round(evidence_quality_score, 4),
    }

    rationale = (
        f"Composite risk score {composite:.3f} → {tier}. "
        f"Pattern severity: {pattern_severity:.2f} (alert type: {alert_type}). "
        f"Trade size: {trade_size_score:.2f} (${notional:,.0f} notional). "
        f"Recidivism: {recidivism_score:.2f} ({prior_count} prior alerts). "
        f"Regulatory exposure: {regulatory_exposure_score:.2f}. "
        f"Evidence quality: {evidence_quality_score:.2f} ({len(signals)} signals). "
        + (" | " + " | ".join(override_reason) if override_reason else "")
    )

    audit_trail = _add_audit_entry(
        state,
        node="risk_scoring",
        action=(
            f"Risk scoring complete. Score: {composite:.3f}. Tier: {tier}. "
            f"SAR consideration: {sar_consideration}."
        ),
        data_sources=["scoring_model_v1", "alert_payload"],
        regulatory_basis="SR 11-7 model risk management; FINRA Rule 3110",
    )

    return {
        **state,
        "risk_score": composite,
        "severity_tier": tier,
        "risk_score_components": components,
        "score_rationale": rationale,
        "sar_consideration": sar_consideration,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["risk_scoring"],
    }


def routing_decision_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Assign primary and secondary reviewers based on asset class + severity.
    Determine whether HITL (compliance officer review) is required.
    Python-only: deterministic routing logic.
    """
    severity_tier = state.get("severity_tier", SeverityTier.MEDIUM.value)
    asset_class = state.get("asset_class", AssetClass.EQUITY.value)
    alert_type = state.get("alert_type", "")

    # Route by asset class
    routing = ASSET_CLASS_ROUTING.get(asset_class, ASSET_CLASS_ROUTING[AssetClass.EQUITY.value])
    primary_reviewer = routing["primary"]
    secondary_reviewers = list(routing["secondary"])

    # CRITICAL/HIGH always require HITL
    human_review_required = severity_tier in (
        SeverityTier.CRITICAL.value, SeverityTier.HIGH.value
    )

    # Hard HITL overrides regardless of tier
    if alert_type in ALWAYS_HITL_ALERT_TYPES:
        human_review_required = True

    # Additional escalation for CRITICAL: add C-suite
    escalation_reason = ""
    if severity_tier == SeverityTier.CRITICAL.value:
        if "LEGAL_COUNSEL" not in secondary_reviewers:
            secondary_reviewers.append("LEGAL_COUNSEL")
        if "CHIEF_COMPLIANCE_OFFICER" not in secondary_reviewers:
            secondary_reviewers.append("CHIEF_COMPLIANCE_OFFICER")
        escalation_reason = (
            f"CRITICAL severity — legal and CCO escalation mandatory. "
            f"SAR consideration flagged: {state.get('sar_consideration', False)}."
        )
    elif severity_tier == SeverityTier.HIGH.value:
        if "CHIEF_COMPLIANCE_OFFICER" not in secondary_reviewers:
            secondary_reviewers.append("CHIEF_COMPLIANCE_OFFICER")
        escalation_reason = "HIGH severity — compliance officer review required."
    elif severity_tier == SeverityTier.MEDIUM.value:
        escalation_reason = "MEDIUM severity — supervisor review; no HITL required."
    else:
        escalation_reason = "LOW severity — auto-document and close."

    audit_trail = _add_audit_entry(
        state,
        node="routing_decision",
        action=(
            f"Routing: {severity_tier} → {primary_reviewer}. "
            f"HITL required: {human_review_required}. "
            f"{escalation_reason}"
        ),
        data_sources=["routing_matrix", "asset_class_registry"],
        regulatory_basis="FINRA Rule 3110 — written supervisory procedures",
    )

    return {
        **state,
        "primary_reviewer": primary_reviewer,
        "secondary_reviewers": secondary_reviewers,
        "human_review_required": human_review_required,
        "escalation_reason": escalation_reason,
        "case_status": CaseStatus.AWAITING_COMPLIANCE.value if human_review_required else CaseStatus.IN_REVIEW.value,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["routing_decision"],
    }


def human_review_gate(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Human-in-the-loop gate. Graph pauses here via interrupt_before.
    Compliance officer submits a decision via the dashboard.
    Resumes when graph.update_state() injects the reviewer decision.

    Decisions:
      INVESTIGATE      → proceed to full investigation + disposition
      ESCALATE         → escalate to legal / senior management
      CLOSE_EXPLAINED  → legitimate explanation found; close with documentation
      CLOSE_NO_ACTION  → insufficient evidence; close
    """
    decision = state.get("reviewer_decision", "INVESTIGATE")
    reviewer_id = state.get("reviewer_id", "UNKNOWN")
    notes = state.get("reviewer_notes", "")

    audit_trail = _add_audit_entry(
        state,
        node="human_review_gate",
        action=(
            f"Compliance Officer {reviewer_id} reviewed alert. "
            f"Decision: {decision}. Notes: {notes[:200] if notes else 'None'}."
        ),
        data_sources=["compliance_officer_review"],
        regulatory_basis="FINRA Rule 3110; SR 11-7 human oversight requirement",
    )

    return {
        **state,
        "reviewer_decision": decision,
        "review_timestamp": datetime.utcnow().isoformat() + "Z",
        "case_status": CaseStatus.UNDER_INVESTIGATION.value,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["human_review_gate"],
    }


def investigation_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    LLM-synthesized investigation narrative. Assembles all evidence and
    produces a structured investigation memo with regulatory considerations.
    """
    reviewer_decision = state.get("reviewer_decision", "INVESTIGATE")

    # For CLOSE decisions (non-HITL path or reviewer decision to close)
    if reviewer_decision in ("CLOSE_EXPLAINED", "CLOSE_NO_ACTION"):
        narrative = (
            f"Alert reviewed by compliance officer. Decision: {reviewer_decision}. "
            f"Reviewer notes: {state.get('reviewer_notes', 'N/A')}. "
            f"No further investigation required."
        )
        evidence = [f"Compliance officer review — {reviewer_decision}"]
        is_suspicious = False if reviewer_decision == "CLOSE_EXPLAINED" else None

        audit_trail = _add_audit_entry(
            state,
            node="investigation",
            action=f"Investigation bypassed — reviewer decision: {reviewer_decision}.",
            data_sources=["compliance_officer_review"],
            regulatory_basis="FINRA Rule 3110",
        )
        return {
            **state,
            "investigation_narrative": narrative,
            "evidence_summary": evidence,
            "is_suspicious": is_suspicious,
            "audit_trail": audit_trail,
            "completed_steps": list(state.get("completed_steps", [])) + ["investigation"],
        }

    # Full LLM investigation
    detected = state.get("detected_patterns", [])
    confidence = state.get("pattern_confidence_scores", {})
    signals = state.get("corroborating_signals", [])
    reg_flags = state.get("regulatory_flags", [])

    prompt_kwargs = {
        "alert_id": state.get("alert_id"),
        "alert_type": state.get("alert_type"),
        "trader_name": state.get("trader_name", "Unknown"),
        "trader_id": state.get("trader_id", "Unknown"),
        "desk": state.get("desk", "Unknown"),
        "instrument_name": state.get("instrument_name", "Unknown"),
        "instrument_id": state.get("instrument_id", ""),
        "asset_class": state.get("asset_class", ""),
        "trade_date": state.get("trade_date", ""),
        "notional_value": float(state.get("notional_value", 0)),
        "trade_direction": state.get("trade_direction", ""),
        "venue": state.get("venue", ""),
        "detected_patterns": "\n".join(f"• {p}" for p in detected),
        "pattern_confidence": "\n".join(f"• {k}: {v:.0%}" for k, v in confidence.items()),
        "corroborating_signals": "\n".join(f"• {s}" for s in signals) or "None identified",
        "trader_history_summary": state.get("trader_history_summary", "No history"),
        "prior_alert_count": state.get("prior_alert_count", 0),
        "restricted_list_hit": state.get("restricted_list_hit", False),
        "watch_list_hit": state.get("watch_list_hit", False),
        "market_context_summary": state.get("market_context_summary", "Not available"),
        "reviewer_decision": reviewer_decision,
        "reviewer_notes": state.get("reviewer_notes", "None"),
        "regulatory_flags": "\n".join(f"• {f}" for f in reg_flags) or "None",
    }

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=INVESTIGATION_SYSTEM_PROMPT),
            HumanMessage(content=INVESTIGATION_USER_PROMPT.format(**prompt_kwargs)),
        ])
        narrative = response.content
        ai_model = "gpt-4o"
    except Exception as e:
        logger.warning(f"Investigation LLM failed: {e}")
        narrative = (
            f"Investigation narrative generation failed ({e}). "
            f"Manual review required. Detected patterns: {', '.join(detected)}. "
            f"Risk score: {state.get('risk_score', 0):.3f}."
        )
        ai_model = None

    # Build evidence summary
    evidence = []
    if state.get("restricted_list_hit"):
        evidence.append(f"Instrument {state.get('instrument_id')} on firm restricted list")
    for signal in signals[:8]:
        evidence.append(signal)
    for p, c in confidence.items():
        evidence.append(f"Pattern detected: {p} (confidence: {c:.0%})")

    is_suspicious = (
        True if any(s == "INVESTIGATE" or s == "ESCALATE" for s in [reviewer_decision]) else None
    )

    audit_trail = _add_audit_entry(
        state,
        node="investigation",
        action=(
            f"Investigation narrative generated. "
            f"Evidence items: {len(evidence)}. AI model: {ai_model or 'N/A'}."
        ),
        data_sources=["pattern_analysis", "trader_history", "market_context"],
        ai_model=ai_model,
        regulatory_basis="FINRA Rule 3110; SEC Rule 17a-4",
    )

    return {
        **state,
        "investigation_narrative": narrative,
        "evidence_summary": evidence,
        "is_suspicious": is_suspicious,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["investigation"],
    }


def disposition_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    LLM-drafted disposition memorandum. Determines final disposition outcome
    and regulatory reporting requirements. SAR consideration is evaluated here.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    severity_tier = state.get("severity_tier", SeverityTier.MEDIUM.value)
    reviewer_decision = state.get("reviewer_decision", "INVESTIGATE")
    sar_consideration = bool(state.get("sar_consideration", False))

    # Determine regulatory reporting requirements (Python — not LLM)
    reporting_required = False
    reporting_bodies = list(state.get("regulatory_reporting_bodies", []))
    alert_type = state.get("alert_type", "")
    notional = float(state.get("notional_value", 0))

    # SAR: BSA requirement for $5,000+ suspicious activity
    if sar_consideration and state.get("is_suspicious"):
        reporting_required = True
        if "FinCEN" not in reporting_bodies:
            reporting_bodies.append("FinCEN")

    # FINRA mandatory reporting for certain manipulation and short selling violations
    if alert_type in (
        AlertType.LAYERING_SPOOFING.value,
        AlertType.CROSS_MARKET_MANIPULATION.value,
        AlertType.SHORT_SELLING_VIOLATION.value,
    ) and severity_tier in (SeverityTier.CRITICAL.value, SeverityTier.HIGH.value):
        reporting_required = True
        if "FINRA" not in reporting_bodies:
            reporting_bodies.append("FINRA")

    # SEC reporting for insider trading
    if alert_type in (
        AlertType.INSIDER_TRADING.value,
        AlertType.INFORMATION_BARRIER_BREACH.value,
    ) and state.get("is_suspicious"):
        reporting_required = True
        if "SEC" not in reporting_bodies:
            reporting_bodies.append("SEC")

    # CFTC reporting for derivatives manipulation
    if state.get("asset_class") in (AssetClass.DERIVATIVES.value, AssetClass.COMMODITIES.value) and (
        alert_type in (AlertType.LAYERING_SPOOFING.value, AlertType.CROSS_MARKET_MANIPULATION.value)
    ):
        reporting_required = True
        if "CFTC" not in reporting_bodies:
            reporting_bodies.append("CFTC")

    # Map reviewer decision to disposition outcome
    outcome_map = {
        "CLOSE_NO_ACTION": DispositionOutcome.CLOSED_NO_ACTION.value,
        "CLOSE_EXPLAINED": DispositionOutcome.CLOSED_EXPLAINED.value,
        "ESCALATE": DispositionOutcome.ESCALATED_TO_LEGAL.value,
    }
    if reviewer_decision in outcome_map:
        disposition_outcome = outcome_map[reviewer_decision]
    elif sar_consideration and state.get("is_suspicious"):
        disposition_outcome = DispositionOutcome.SAR_FILED.value
    elif reporting_required and "SEC" in reporting_bodies:
        disposition_outcome = DispositionOutcome.REFERRED_TO_REGULATOR.value
    elif severity_tier == SeverityTier.CRITICAL.value:
        disposition_outcome = DispositionOutcome.ESCALATED_TO_LEGAL.value
    else:
        disposition_outcome = DispositionOutcome.PENDING_INVESTIGATION.value

    # LLM disposition memo
    narrative = state.get("investigation_narrative", "")
    excerpt = narrative[:1500] if narrative else "Not available."

    prompt_kwargs = {
        "alert_id": state.get("alert_id"),
        "alert_type": alert_type,
        "severity_tier": severity_tier,
        "risk_score": float(state.get("risk_score", 0)),
        "trader_name": state.get("trader_name", "Unknown"),
        "trader_id": state.get("trader_id", ""),
        "desk": state.get("desk", ""),
        "instrument_name": state.get("instrument_name", ""),
        "asset_class": state.get("asset_class", ""),
        "trade_date": state.get("trade_date", ""),
        "notional_value": notional,
        "investigation_narrative_excerpt": excerpt,
        "is_suspicious": state.get("is_suspicious"),
        "reviewer_decision": reviewer_decision,
        "reviewer_notes": state.get("reviewer_notes", "None"),
        "sar_consideration": sar_consideration,
        "sar_rationale": state.get("sar_rationale", ""),
        "regulatory_reporting_required": reporting_required,
        "regulatory_reporting_bodies": ", ".join(reporting_bodies) if reporting_bodies else "None",
        "evidence_summary": "\n".join(f"• {e}" for e in state.get("evidence_summary", [])) or "None",
        "today": today,
    }

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = _get_llm()
        response = llm.invoke([
            SystemMessage(content=DISPOSITION_SYSTEM_PROMPT.format(
                alert_id=state.get("alert_id"), today=today
            )),
            HumanMessage(content=DISPOSITION_USER_PROMPT.format(**prompt_kwargs)),
        ])
        memo = response.content
        ai_model = "gpt-4o"
    except Exception as e:
        logger.warning(f"Disposition LLM failed: {e}")
        memo = (
            f"Disposition Memorandum\n"
            f"Case: {state.get('alert_id')}\n"
            f"Decision: {disposition_outcome}\n"
            f"Alert Type: {alert_type} | Severity: {severity_tier}\n"
            f"[LLM generation failed — manual memo required]"
        )
        ai_model = None

    audit_trail = _add_audit_entry(
        state,
        node="disposition",
        action=(
            f"Disposition: {disposition_outcome}. "
            f"Regulatory reporting: {reporting_required} ({', '.join(reporting_bodies) or 'none'}). "
            f"SAR: {sar_consideration}."
        ),
        data_sources=["investigation_narrative", "regulatory_reporting_thresholds"],
        ai_model=ai_model,
        regulatory_basis=(
            "31 CFR § 1023.320 (SAR); FINRA Rule 4511; "
            "SEC Rule 17a-4; FINRA Rule 3110"
        ),
    )

    sar_rationale = state.get("sar_rationale", "")
    if not sar_rationale:
        if sar_consideration and state.get("is_suspicious"):
            sar_rationale = (
                f"SAR filing required: suspicious activity of ${notional:,.0f} "
                f"meets BSA threshold. Alert type: {alert_type}."
            )
        else:
            sar_rationale = "SAR not required: activity does not meet BSA suspicious activity threshold or was explained."

    return {
        **state,
        "disposition_outcome": disposition_outcome,
        "disposition_memo": memo,
        "regulatory_reporting_required": reporting_required,
        "regulatory_reporting_bodies": reporting_bodies,
        "sar_rationale": sar_rationale,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["disposition"],
    }


def case_tracking_update_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Write the final case record to the surveillance register.
    """
    entry = {
        "alert_id": state.get("alert_id"),
        "alert_type": state.get("alert_type"),
        "trader_id": state.get("trader_id"),
        "trader_name": state.get("trader_name"),
        "desk": state.get("desk"),
        "instrument_id": state.get("instrument_id"),
        "instrument_name": state.get("instrument_name"),
        "asset_class": state.get("asset_class"),
        "trade_date": state.get("trade_date"),
        "notional_value": state.get("notional_value"),
        "risk_score": state.get("risk_score"),
        "severity_tier": state.get("severity_tier"),
        "primary_reviewer": state.get("primary_reviewer"),
        "reviewer_decision": state.get("reviewer_decision"),
        "disposition_outcome": state.get("disposition_outcome"),
        "sar_consideration": state.get("sar_consideration"),
        "regulatory_reporting_required": state.get("regulatory_reporting_required"),
        "regulatory_reporting_bodies": state.get("regulatory_reporting_bodies", []),
        "case_status": CaseStatus.CLOSED.value,
        "closed_at": datetime.utcnow().isoformat() + "Z",
        "audit_entry_count": len(state.get("audit_trail", [])),
    }

    audit_trail = _add_audit_entry(
        state,
        node="case_tracking_update",
        action=(
            f"Case record written to surveillance register. "
            f"Disposition: {state.get('disposition_outcome')}. "
            f"Regulatory reporting: {state.get('regulatory_reporting_required')}."
        ),
        data_sources=["surveillance_register"],
        regulatory_basis="FINRA Rule 4511; SEC Rule 17a-4 (3-year retention)",
    )

    return {
        **state,
        "case_register_entry": entry,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["case_tracking_update"],
    }


def finalize_node(state: TradingSurveillanceState) -> TradingSurveillanceState:
    """
    Lock the audit trail and set final case status.
    """
    audit_trail = _add_audit_entry(
        state,
        node="finalize",
        action=(
            f"Workflow complete. Case {state.get('alert_id')} closed. "
            f"Final status: CLOSED. "
            f"Total audit entries: {len(state.get('audit_trail', [])) + 1}."
        ),
        regulatory_basis="FINRA Rule 4511; SEC Rule 17a-4; 31 CFR § 1010.430",
    )

    return {
        **state,
        "case_status": CaseStatus.CLOSED.value,
        "audit_trail": audit_trail,
        "completed_steps": list(state.get("completed_steps", [])) + ["finalize"],
    }
