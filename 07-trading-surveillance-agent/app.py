# app.py
# ============================================================
# Trading Surveillance Agent — Streamlit Dashboard
#
# Dashboard tabs:
#   1. Alert Queue       — Incoming alerts, severity distribution, case register
#   2. Case Investigation — Pattern analysis, risk scoring, evidence assembly
#   3. Disposition       — Compliance review, disposition memo, SAR determination
#   4. Trader Registry   — Trader profiles, alert history, risk tiers
#   5. Audit Trail       — Full decision and action log (examination evidence)
#   6. Configuration     — Surveillance rules, routing, scoring thresholds
#
# HITL:
#   CRITICAL/HIGH alerts pause at human_review_gate.
#   The Compliance Officer reviews the case in Tab 2 and submits
#   a decision (INVESTIGATE / ESCALATE / CLOSE_EXPLAINED / CLOSE_NO_ACTION).
#   The workflow resumes automatically.
#
# Port: 8507
# ============================================================

import json
import logging
import os
import uuid
from datetime import datetime

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from agent.graph import build_trading_surveillance_graph
from agent.state import (
    AlertType,
    AssetClass,
    CaseStatus,
    SeverityTier,
    TradingSurveillanceState,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Surveillance",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.critical-badge { background:#dc3545; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.high-badge     { background:#fd7e14; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.medium-badge   { background:#ffc107; color:#212529; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.low-badge      { background:#28a745; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.metric-card    { background:#f8f9fa; border-left:4px solid #2196F3; padding:12px 16px; border-radius:4px; margin-bottom:8px; }
.sar-warning    { background:#fff3cd; border-left:4px solid #ffc107; padding:12px 16px; border-radius:4px; }
</style>
""", unsafe_allow_html=True)


# ── Session State ─────────────────────────────────────────────────────────────
if "graph" not in st.session_state:
    st.session_state.graph = build_trading_surveillance_graph(use_memory=True)
if "active_case" not in st.session_state:
    st.session_state.active_case = None
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "workflow_status" not in st.session_state:
    st.session_state.workflow_status = "idle"
if "case_register" not in st.session_state:
    st.session_state.case_register = _load_sample_register()


def _load_sample_register():
    try:
        with open(os.path.join("data", "fixtures", "sample_alerts.json")) as f:
            samples = json.load(f)
        register = {}
        severity_map = {
            "LAYERING_SPOOFING": "HIGH",
            "INSIDER_TRADING": "CRITICAL",
            "MARKING_THE_CLOSE": "HIGH",
        }
        for s in samples:
            alert_id = s["alert_id"]
            register[alert_id] = {
                **s,
                "severity_tier": severity_map.get(s["alert_type"], "MEDIUM"),
                "risk_score": 0.78 if s["alert_type"] == "LAYERING_SPOOFING" else 0.92 if s["alert_type"] == "INSIDER_TRADING" else 0.71,
                "primary_reviewer": "EQUITIES_SURVEILLANCE_OFFICER",
                "case_status": "AWAITING_COMPLIANCE",
                "disposition_outcome": None,
                "sar_consideration": s["alert_type"] == "INSIDER_TRADING",
                "regulatory_reporting_required": s["alert_type"] in ("INSIDER_TRADING", "LAYERING_SPOOFING"),
                "human_review_completed": False,
            }
        return register
    except Exception:
        return {}


def _load_trader_registry():
    try:
        with open(os.path.join("data", "fixtures", "trader_registry.json")) as f:
            return json.load(f)
    except Exception:
        return []


def _load_surveillance_rules():
    try:
        with open(os.path.join("data", "fixtures", "surveillance_rules.json")) as f:
            return json.load(f)
    except Exception:
        return {"rules": []}


def _severity_icon(tier):
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(tier, "⚪")


def _days_label(date_str):
    if not date_str:
        return "N/A"
    try:
        target = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        days = (today - target).days
        if days == 0:
            return "Today"
        elif days == 1:
            return "Yesterday"
        elif days < 30:
            return f"{days}d ago"
        else:
            return date_str
    except Exception:
        return date_str


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Trading Surveillance")
    st.markdown("*Market Abuse Detection Agent*")
    st.divider()

    register = st.session_state.case_register
    critical_count = sum(1 for c in register.values() if c.get("severity_tier") == "CRITICAL")
    high_count = sum(1 for c in register.values() if c.get("severity_tier") == "HIGH")
    sar_count = sum(1 for c in register.values() if c.get("sar_consideration"))
    open_count = sum(1 for c in register.values() if c.get("case_status") in ("AWAITING_COMPLIANCE", "IN_REVIEW", "UNDER_INVESTIGATION"))

    st.metric("Active Cases", len(register))
    col1, col2 = st.columns(2)
    col1.metric("Critical", critical_count)
    col2.metric("High", high_count)
    st.metric("SAR Consideration", sar_count)
    st.metric("Pending Review", open_count)
    st.divider()

    status = st.session_state.workflow_status
    status_icons = {"idle": "🔵", "running": "🟡", "awaiting_review": "🟠", "complete": "🟢", "error": "🔴"}
    st.markdown(f"**Workflow:** {status_icons.get(status, '⚪')} {status.replace('_', ' ').title()}")
    if st.session_state.active_case:
        st.markdown(f"**Active:** `{st.session_state.active_case.get('alert_id', 'N/A')}`")


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🚨 Alert Queue",
    "🔍 Case Investigation",
    "⚖️ Disposition",
    "👤 Trader Registry",
    "📋 Audit Trail",
    "⚙️ Configuration",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: ALERT QUEUE
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Alert Queue")
    st.caption("Submit and review trading surveillance alerts. AI-powered pattern detection and risk scoring.")

    col_form, col_queue = st.columns([3, 2])

    with col_form:
        st.subheader("Submit New Alert")
        with st.form("new_alert_form"):
            col1, col2 = st.columns(2)
            trader_id = col1.text_input("Trader ID *", placeholder="TRD-001")
            trader_name = col2.text_input("Trader Name *", placeholder="Alex Chen")
            col3, col4 = st.columns(2)
            desk = col3.text_input("Desk", placeholder="EQUITIES_PROP")
            account_id = col4.text_input("Account ID", placeholder="ACCT-88421")

            col5, col6 = st.columns(2)
            alert_type = col5.selectbox(
                "Alert Type *",
                [a.value for a in AlertType],
                format_func=lambda x: x.replace("_", " ").title(),
            )
            asset_class = col6.selectbox(
                "Asset Class *",
                [a.value for a in AssetClass],
            )
            col7, col8 = st.columns(2)
            instrument_id = col7.text_input("Instrument ID *", placeholder="ACME")
            instrument_name = col8.text_input("Instrument Name", placeholder="ACME Corporation")

            col9, col10 = st.columns(2)
            trade_date = col9.date_input("Trade Date *", value=datetime.today())
            notional = col10.number_input("Notional Value ($) *", min_value=0.0, value=500_000.0, step=10_000.0)

            col11, col12 = st.columns(2)
            direction = col11.selectbox("Trade Direction", ["BUY", "SELL", "BOTH"])
            venue = col12.selectbox("Venue", ["NYSE", "NASDAQ", "OTC", "DARK_POOL", "CME", "CBOE", "ICE", "OTHER"])

            st.markdown("**Alert-Specific Data**")
            col13, col14 = st.columns(2)
            cancel_rate = col13.slider("Order Cancel Rate", 0.0, 1.0, 0.0, 0.01,
                                        help="Proportion of orders cancelled before execution")
            order_count = col14.number_input("Order Count", min_value=0, value=0)

            col15, col16 = st.columns(2)
            opposite_orders = col15.checkbox("Opposite-Side Orders?", help="Orders placed in opposite direction on same instrument")
            restricted_flag = col16.checkbox("Restricted List Hit?", help="Instrument on firm restricted list")

            alert_source = st.selectbox("Alert Source", ["SURVEILLANCE_SYSTEM", "MANUAL", "REGULATORY_INQUIRY"])
            submitted = st.form_submit_button("🔍 Analyze Alert", type="primary")

        if submitted and trader_id and instrument_id and notional > 0:
            raw_data = {
                "cancel_rate": cancel_rate,
                "order_count": order_count,
                "opposite_side_orders": opposite_orders,
            }

            initial_state: TradingSurveillanceState = {
                "alert_type": alert_type,
                "alert_source": alert_source,
                "trader_id": trader_id,
                "trader_name": trader_name or trader_id,
                "desk": desk or "UNKNOWN",
                "account_id": account_id or f"ACCT-{trader_id}",
                "instrument_id": instrument_id,
                "instrument_name": instrument_name or instrument_id,
                "asset_class": asset_class,
                "trade_date": trade_date.isoformat(),
                "notional_value": float(notional),
                "trade_direction": direction,
                "quantity": 0,
                "price": 0.0,
                "venue": venue,
                "raw_alert_data": raw_data,
                "audit_trail": [],
                "completed_steps": [],
                "errors": [],
                "corroborating_signals": [],
                "prior_alerts": [],
                "detected_patterns": [],
                "regulatory_flags": [],
                "secondary_reviewers": [],
                "evidence_summary": [],
                "regulatory_reporting_bodies": [],
            }
            if restricted_flag:
                initial_state["restricted_list_hit"] = True

            thread_id = str(uuid.uuid4())
            st.session_state.thread_id = thread_id
            st.session_state.workflow_status = "running"
            config = {"configurable": {"thread_id": thread_id}}

            with st.spinner("Analyzing alert — pattern detection and risk scoring..."):
                try:
                    for event in st.session_state.graph.stream(initial_state, config):
                        pass

                    snapshot = st.session_state.graph.get_state(config)
                    paused = snapshot.next

                    if paused and "human_review_gate" in paused:
                        st.session_state.workflow_status = "awaiting_review"
                    else:
                        st.session_state.workflow_status = "complete"

                    active = dict(snapshot.values)
                    st.session_state.active_case = active

                    # Register case
                    cid = active.get("alert_id", f"SURV-{thread_id[:8]}")
                    st.session_state.case_register[cid] = {
                        "alert_id": cid,
                        "alert_type": alert_type,
                        "trader_id": trader_id,
                        "trader_name": trader_name or trader_id,
                        "desk": desk,
                        "instrument_id": instrument_id,
                        "instrument_name": instrument_name or instrument_id,
                        "asset_class": asset_class,
                        "trade_date": trade_date.isoformat(),
                        "notional_value": float(notional),
                        "severity_tier": active.get("severity_tier", "MEDIUM"),
                        "risk_score": active.get("risk_score", 0.5),
                        "primary_reviewer": active.get("primary_reviewer", ""),
                        "case_status": active.get("case_status", "IN_REVIEW"),
                        "disposition_outcome": active.get("disposition_outcome"),
                        "sar_consideration": active.get("sar_consideration", False),
                        "regulatory_reporting_required": active.get("regulatory_reporting_required", False),
                        "human_review_completed": active.get("reviewer_decision") is not None,
                    }

                    tier = active.get("severity_tier", "MEDIUM")
                    if st.session_state.workflow_status == "awaiting_review":
                        st.warning(
                            f"🟠 {tier} alert — Compliance Officer review required. "
                            "Go to **Case Investigation** tab to complete the review."
                        )
                    else:
                        st.success(f"✅ Alert analyzed. Severity: {tier}. Go to **Case Investigation** for details.")

                    st.rerun()
                except Exception as e:
                    st.error(f"Workflow error: {e}")
                    st.session_state.workflow_status = "error"
                    logger.exception(e)
        elif submitted:
            st.warning("Please fill in: Trader ID, Instrument ID, and Notional Value.")

    with col_queue:
        st.subheader("Case Register")

        # Summary chart
        tier_counts = {}
        for c in register.values():
            t = c.get("severity_tier", "MEDIUM")
            tier_counts[t] = tier_counts.get(t, 0) + 1

        if tier_counts:
            fig = go.Figure(go.Pie(
                labels=list(tier_counts.keys()),
                values=list(tier_counts.values()),
                marker_colors=["#dc3545", "#fd7e14", "#ffc107", "#28a745"],
                hole=0.4,
            ))
            fig.update_layout(height=200, margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        # Filter
        tier_filter = st.multiselect(
            "Severity",
            ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            default=["CRITICAL", "HIGH"],
        )

        for case in sorted(
            [c for c in register.values() if c.get("severity_tier", "MEDIUM") in tier_filter],
            key=lambda x: x.get("risk_score", 0),
            reverse=True,
        ):
            tier = case.get("severity_tier", "MEDIUM")
            icon = _severity_icon(tier)
            with st.expander(
                f"{icon} {case.get('alert_type', 'UNKNOWN').replace('_', ' ')} — "
                f"{case.get('trader_name', 'Unknown')}",
                expanded=False,
            ):
                st.markdown(f"**ID:** `{case.get('alert_id', 'N/A')}`")
                st.markdown(f"**Instrument:** {case.get('instrument_name', '')} ({case.get('instrument_id', '')})")
                st.markdown(f"**Desk:** {case.get('desk', 'N/A')}")
                st.markdown(f"**Notional:** ${case.get('notional_value', 0):,.0f}")
                st.markdown(f"**Score:** {case.get('risk_score', 0):.3f} → **{tier}**")
                st.markdown(f"**Status:** `{case.get('case_status', 'N/A')}`")
                if case.get("sar_consideration"):
                    st.markdown("⚠️ **SAR consideration flagged**")
                if st.button("Open Case", key=f"open_case_{case.get('alert_id')}"):
                    st.session_state.active_case = case


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: CASE INVESTIGATION
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Case Investigation")

    active = st.session_state.active_case
    if not active:
        st.info("No active case. Submit an alert in the Alert Queue tab or select from the Case Register.")
        st.stop()

    alert_id = active.get("alert_id", "N/A")
    severity_tier = active.get("severity_tier", "MEDIUM")
    risk_score = float(active.get("risk_score", 0))

    # Header metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Alert ID", alert_id.split("-")[-1] if "-" in alert_id else alert_id)
    col2.metric("Severity", f"{_severity_icon(severity_tier)} {severity_tier}")
    col3.metric("Risk Score", f"{risk_score:.3f}")
    col4.metric("SAR Consideration", "⚠️ YES" if active.get("sar_consideration") else "NO")

    st.markdown(
        f"**{active.get('alert_type', '').replace('_', ' ').title()}** — "
        f"{active.get('trader_name', 'Unknown')} ({active.get('trader_id', '')})"
        f" | {active.get('desk', '')} | {active.get('instrument_name', '')} | "
        f"${active.get('notional_value', 0):,.0f}"
    )

    # HITL Review Panel
    if st.session_state.workflow_status == "awaiting_review":
        st.divider()
        st.subheader("⏸️ Compliance Officer Review Required")
        st.warning(
            f"This **{severity_tier}** alert requires Compliance Officer review. "
            "Review the patterns and evidence below, then submit your decision."
        )

        with st.form("officer_review_form"):
            reviewer_id = st.text_input("Compliance Officer ID / Name *")
            decision = st.radio(
                "Decision *",
                ["INVESTIGATE", "ESCALATE", "CLOSE_EXPLAINED", "CLOSE_NO_ACTION"],
                horizontal=True,
                help=(
                    "INVESTIGATE: proceed to full investigation | "
                    "ESCALATE: refer to legal/senior management | "
                    "CLOSE_EXPLAINED: legitimate explanation documented | "
                    "CLOSE_NO_ACTION: insufficient evidence, close case"
                ),
            )
            notes = st.text_area(
                "Review Notes (required for ESCALATE and CLOSE decisions)",
                placeholder="Document your review findings and rationale...",
            )
            review_submitted = st.form_submit_button("Submit Decision", type="primary")

        if review_submitted and reviewer_id:
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            st.session_state.graph.update_state(
                config,
                {
                    "reviewer_id": reviewer_id,
                    "reviewer_decision": decision,
                    "reviewer_notes": notes,
                },
                as_node="human_review_gate",
            )
            with st.spinner("Completing investigation workflow..."):
                for event in st.session_state.graph.stream(None, config):
                    pass
            snapshot = st.session_state.graph.get_state(config)
            st.session_state.active_case = dict(snapshot.values)
            st.session_state.workflow_status = "complete"
            st.success(f"Decision submitted: {decision}. Workflow complete.")
            st.rerun()
        elif review_submitted:
            st.warning("Compliance Officer ID is required.")

    st.divider()

    col_score, col_patterns = st.columns([2, 3])

    with col_score:
        st.subheader("Risk Score Breakdown")
        components = active.get("risk_score_components", {})
        if components:
            labels = [k.replace("_score", "").replace("_", " ").title() for k in components]
            values = list(components.values())
            weights = ["25%", "25%", "20%", "15%", "15%"]
            colors = ["#dc3545" if v >= 0.85 else "#fd7e14" if v >= 0.65 else "#ffc107" if v >= 0.40 else "#28a745" for v in values]

            fig = go.Figure(go.Bar(
                x=values, y=labels, orientation="h",
                marker_color=colors,
                text=[f"{v:.2f}" for v in values],
                textposition="outside",
            ))
            fig.update_layout(
                height=250, margin=dict(l=0, r=50, t=20, b=20),
                xaxis=dict(range=[0, 1.15]), yaxis=dict(title=""),
            )
            st.plotly_chart(fig, use_container_width=True)

            import pandas as pd
            df = pd.DataFrame({"Factor": labels, "Score": [f"{v:.3f}" for v in values], "Weight": weights})
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Scoring breakdown will appear after analysis.")

        st.markdown(f"**Score Rationale:**")
        st.caption(active.get("score_rationale", "N/A"))

    with col_patterns:
        st.subheader("Detected Patterns")
        patterns = active.get("detected_patterns", [])
        confidence = active.get("pattern_confidence_scores", {})

        if patterns:
            for p in patterns:
                conf = confidence.get(p, 0)
                color = "🔴" if conf >= 0.80 else "🟠" if conf >= 0.60 else "🟡"
                st.markdown(
                    f"{color} **{p.replace('_', ' ').title()}** — "
                    f"Confidence: {conf:.0%}"
                )

            st.markdown("---")
            st.markdown("**Pattern Rationale:**")
            st.markdown(active.get("pattern_rationale", "N/A"))
        else:
            st.info("Pattern detection results will appear here.")

        st.subheader("Regulatory Flags")
        flags = active.get("regulatory_flags", [])
        if flags:
            for f in flags:
                st.markdown(f"• {f}")
        else:
            st.info("No regulatory flags identified.")

    # Evidence & Signals
    st.divider()
    st.subheader("Corroborating Evidence")
    col_ev, col_sig = st.columns(2)

    with col_ev:
        st.markdown("**Evidence Summary**")
        for ev in active.get("evidence_summary", []):
            st.markdown(f"• {ev}")

    with col_sig:
        st.markdown("**Corroborating Signals**")
        for sig in active.get("corroborating_signals", []):
            st.markdown(f"• {sig}")

    # Investigation Narrative
    narrative = active.get("investigation_narrative", "")
    if narrative:
        st.divider()
        st.subheader("Investigation Narrative")
        st.markdown(narrative)

    # Market Context
    market_ctx = active.get("market_context_summary", "")
    if market_ctx:
        with st.expander("Market Context", expanded=False):
            st.markdown(market_ctx)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: DISPOSITION
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Disposition")

    active = st.session_state.active_case
    if not active:
        st.info("No active case selected.")
        st.stop()

    # SAR Warning Banner
    if active.get("sar_consideration"):
        st.markdown(
            '<div class="sar-warning">⚠️ <strong>SAR Consideration Flagged</strong> — '
            "This case requires a BSA/AML Suspicious Activity Report evaluation. "
            "See SAR determination section below.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("")

    col1, col2, col3 = st.columns(3)
    col1.metric("Disposition", active.get("disposition_outcome", "PENDING") or "PENDING")
    col2.metric("Regulatory Reporting", "YES" if active.get("regulatory_reporting_required") else "NO")
    reporting_bodies = active.get("regulatory_reporting_bodies", [])
    col3.metric("Reporting Bodies", ", ".join(reporting_bodies) if reporting_bodies else "None")

    # Disposition Memo
    memo = active.get("disposition_memo", "")
    if memo:
        st.subheader("Disposition Memorandum")
        st.markdown(memo)
    else:
        st.info("Disposition memorandum will appear after the workflow completes.")

    # SAR Section
    st.divider()
    st.subheader("SAR Determination")
    sar = active.get("sar_consideration", False)
    sar_rationale = active.get("sar_rationale", "")

    col_sar1, col_sar2 = st.columns([1, 3])
    col_sar1.metric("SAR Required", "YES" if sar else "NO")
    if sar:
        col_sar1.markdown("**Filing Deadline:** 30 days from detection")
        col_sar1.markdown("**Authority:** FinCEN / 31 CFR § 1023.320")
    with col_sar2:
        if sar_rationale:
            st.markdown(f"**Rationale:** {sar_rationale}")
        else:
            st.info("SAR determination pending case completion.")

    # Regulatory Reporting
    if active.get("regulatory_reporting_required") and reporting_bodies:
        st.divider()
        st.subheader("Regulatory Reporting Requirements")
        for body in reporting_bodies:
            reporting_info = {
                "FinCEN": "SAR — 30-day filing deadline; continuing activity SAR at 90-day intervals",
                "FINRA": "Regulatory event report per FINRA Rule 4530; prompt notification required",
                "SEC": "Potential referral per SEC Rule 21F (whistleblower) or internal escalation",
                "CFTC": "Suspicious activity per CEA Section 4s(f); potential large trader report",
            }.get(body, "Consult legal counsel for reporting requirements.")
            with st.expander(f"📋 {body}", expanded=True):
                st.markdown(reporting_info)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: TRADER REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Trader Registry")
    st.caption("Trader profiles, alert history, and risk tier classifications.")

    traders = _load_trader_registry()
    if not traders:
        st.warning("Trader registry not loaded. Check data/fixtures/trader_registry.json.")
        st.stop()

    # Risk tier distribution
    risk_tiers = {}
    for t in traders:
        rt = t.get("account_risk_tier", "STANDARD")
        risk_tiers[rt] = risk_tiers.get(rt, 0) + 1

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Traders", len(traders))
    col2.metric("High Risk", risk_tiers.get("HIGH_RISK", 0))
    col3.metric("Medium Risk", risk_tiers.get("MEDIUM_RISK", 0))

    # Trader table
    search = st.text_input("Search traders", placeholder="Name, ID, or desk...")
    risk_filter = st.multiselect(
        "Risk Tier",
        ["HIGH_RISK", "MEDIUM_RISK", "STANDARD"],
        default=["HIGH_RISK", "MEDIUM_RISK", "STANDARD"],
    )

    filtered = [
        t for t in traders
        if t.get("account_risk_tier", "STANDARD") in risk_filter
        and (
            not search
            or search.lower() in t.get("trader_name", "").lower()
            or search.lower() in t.get("trader_id", "").lower()
            or search.lower() in t.get("desk", "").lower()
        )
    ]

    for trader in filtered:
        prior_count = len(trader.get("prior_alerts", []))
        risk_tier = trader.get("account_risk_tier", "STANDARD")
        risk_icon = "🔴" if risk_tier == "HIGH_RISK" else "🟡" if risk_tier == "MEDIUM_RISK" else "🟢"

        with st.expander(
            f"{risk_icon} [{trader.get('trader_id')}] {trader.get('trader_name')} — "
            f"{trader.get('desk')} ({prior_count} prior alerts)",
            expanded=False,
        ):
            col_a, col_b = st.columns(2)
            col_a.markdown(f"**Desk:** {trader.get('desk')}")
            col_a.markdown(f"**Account:** {trader.get('account_id')}")
            col_a.markdown(f"**Risk Tier:** {risk_tier}")
            col_a.markdown(f"**Supervisor:** {trader.get('supervisor', 'N/A')}")
            col_b.markdown(f"**Employed Since:** {trader.get('employment_start', 'N/A')}")
            col_b.markdown(f"**Last Training:** {trader.get('last_training_date', 'N/A')}")
            col_b.markdown(f"**PEP Flag:** {'⚠️ YES' if trader.get('pep_flag') else 'No'}")
            licenses = trader.get("licenses", [])
            col_b.markdown(f"**Licenses:** {', '.join(licenses)}")

            restricted = trader.get("restricted_instruments", [])
            watch = trader.get("watch_instruments", [])
            if restricted:
                st.markdown(f"**Restricted Instruments:** {', '.join(restricted)}")
            if watch:
                st.markdown(f"**Watch List:** {', '.join(watch)}")

            notes = trader.get("notes", "")
            if notes:
                st.info(notes)

            # Prior alerts
            if prior_count > 0:
                st.markdown(f"**Prior Alerts ({prior_count}):**")
                for alert in trader.get("prior_alerts", []):
                    tier_icon = _severity_icon(alert.get("severity_tier", "MEDIUM"))
                    st.markdown(
                        f"  {tier_icon} `{alert.get('alert_id', 'N/A')}` — "
                        f"{alert.get('alert_type', '').replace('_', ' ')} | "
                        f"{alert.get('alert_date', '')} | "
                        f"${alert.get('notional_value', 0):,.0f} | "
                        f"{alert.get('disposition', 'N/A')}"
                    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: AUDIT TRAIL
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("Audit Trail")
    st.caption(
        "Append-only log of all workflow decisions and actions. "
        "Required for FINRA Rule 4511 / SEC Rule 17a-4 record retention (minimum 3 years)."
    )

    active = st.session_state.active_case
    audit = active.get("audit_trail", []) if active else []

    if audit:
        col1, col2 = st.columns([3, 1])
        col1.metric("Total Audit Entries", len(audit))
        col2.metric("LLM Invocations", sum(1 for e in audit if e.get("ai_model_used")))

        st.subheader(f"Case: {active.get('alert_id', 'N/A')}")

        for i, entry in enumerate(reversed(audit)):
            with st.expander(
                f"[{entry.get('timestamp', '')[:19]}] {entry.get('node', '')} — {entry.get('action', '')[:80]}",
                expanded=(i == 0),
            ):
                col_a, col_b = st.columns(2)
                col_a.markdown(f"**Node:** `{entry.get('node')}`")
                col_a.markdown(f"**Actor:** {entry.get('actor', 'ai_agent')}")
                col_a.markdown(f"**Timestamp:** {entry.get('timestamp', '')}")
                col_b.markdown(f"**LLM Used:** {'Yes — ' + entry.get('ai_model_used', '') if entry.get('ai_model_used') else 'No'}")
                col_b.markdown(f"**HITL Required:** {entry.get('human_review_required', False)}")
                if entry.get("regulatory_basis"):
                    st.markdown(f"**Regulatory Basis:** {entry.get('regulatory_basis')}")
                sources = entry.get("data_sources_accessed", [])
                if sources:
                    st.markdown(f"**Data Sources:** {', '.join(sources)}")
                st.markdown(f"**Action:** {entry.get('action', '')}")

        if audit:
            st.download_button(
                "📥 Export Audit Trail (JSON)",
                data=json.dumps(audit, indent=2),
                file_name=f"audit_{active.get('alert_id', 'unknown')}_{datetime.utcnow().strftime('%Y%m%d')}.json",
                mime="application/json",
            )
    else:
        st.info("Audit trail entries will appear after a surveillance alert has been processed.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6: CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("Configuration")
    st.caption("Manage surveillance rules, routing, and scoring thresholds.")

    conf_tab1, conf_tab2, conf_tab3 = st.tabs(["Surveillance Rules", "Routing Matrix", "Scoring Thresholds"])

    with conf_tab1:
        st.subheader("Active Surveillance Rules")
        rules_data = _load_surveillance_rules()
        rules = rules_data.get("rules", [])

        active_rules = [r for r in rules if r.get("active")]
        st.metric("Active Rules", len(active_rules))

        for rule in rules:
            active_flag = rule.get("active", False)
            status_icon = "🟢" if active_flag else "⚪"
            with st.expander(f"{status_icon} [{rule.get('rule_id')}] {rule.get('name')}", expanded=False):
                st.markdown(f"**Pattern:** {rule.get('pattern', '').replace('_', ' ')}")
                st.markdown(f"**Description:** {rule.get('description')}")
                st.markdown(f"**Regulatory Basis:** {rule.get('regulatory_basis')}")
                st.markdown(f"**Status:** {'Active' if active_flag else 'Inactive'}")
                thresholds = rule.get("thresholds", {})
                if thresholds:
                    st.markdown("**Thresholds:**")
                    for k, v in thresholds.items():
                        st.markdown(f"  • {k.replace('_', ' ')}: {v}")

        sar = rules_data.get("sar_thresholds", {})
        if sar:
            st.subheader("SAR Thresholds")
            st.markdown(f"**Minimum suspicious amount:** ${sar.get('minimum_suspicious_amount_usd', 5000):,.0f}")
            st.markdown(f"**Filing deadline:** {sar.get('filing_deadline_days', 30)} days")
            st.markdown(f"**Mandatory filing alert types:** {', '.join(sar.get('mandatory_filing_alert_types', []))}")

    with conf_tab2:
        st.subheader("Routing Matrix by Asset Class")
        try:
            with open(os.path.join("data", "fixtures", "routing_matrix.json")) as f:
                routing_data = json.load(f)

            for asset_class, config in routing_data.items():
                if asset_class == "alert_type_overrides":
                    continue
                with st.expander(asset_class, expanded=False):
                    col_a, col_b = st.columns(2)
                    col_a.markdown(f"**Primary Reviewer:** {config.get('primary')}")
                    col_a.markdown(f"**Secondary:** {', '.join(config.get('secondary', []))}")
                    col_b.markdown(f"**Legal Escalation:** {config.get('legal_escalation_threshold', 'CRITICAL')} +")
                    col_b.markdown(f"**Board Notification:** {config.get('board_notification_threshold', 'CRITICAL')} +")
                    if config.get("notes"):
                        st.info(config["notes"])

            st.subheader("Alert Type Overrides")
            overrides = routing_data.get("alert_type_overrides", {})
            for atype, config in overrides.items():
                with st.expander(atype.replace("_", " ").title(), expanded=False):
                    st.markdown(f"**Additional Reviewers:** {', '.join(config.get('additional_reviewers', []))}")
                    st.markdown(f"**Mandatory HITL:** {config.get('mandatory_hitl', False)}")
                    if config.get("mandatory_sar_evaluation"):
                        st.markdown("**SAR Evaluation:** Mandatory")
        except Exception:
            st.warning("Routing matrix not loaded.")

    with conf_tab3:
        st.subheader("Risk Scoring Thresholds")
        st.info(
            "Tier thresholds are configurable here. All changes must be documented "
            "per SR 11-7 model risk management and FINRA Rule 3110 supervisory procedures."
        )
        col1, col2 = st.columns(2)
        critical_thresh = col1.slider("CRITICAL Threshold", 0.70, 0.95, 0.85, 0.01)
        high_thresh = col2.slider("HIGH Threshold", 0.50, 0.84, 0.65, 0.01)
        st.caption(
            f"CRITICAL ≥ {critical_thresh:.2f} | HIGH ≥ {high_thresh:.2f} | "
            f"MEDIUM ≥ 0.40 | LOW < 0.40"
        )

        st.subheader("Scoring Model — Factor Weights")
        st.info("Weights are fixed in code per SR 11-7. Changes require model validation and CCO approval.")

        import pandas as pd
        weights_df = pd.DataFrame({
            "Factor": ["Pattern Severity", "Trade Size / Market Impact", "Recidivism / History",
                        "Regulatory Exposure", "Evidence Quality"],
            "Weight": ["25%", "25%", "20%", "15%", "15%"],
            "Rationale": [
                "Alert type base severity reflects inherent manipulation seriousness",
                "Larger trades have greater market impact and enforcement significance",
                "Prior alerts indicate supervision failure; recidivists warrant escalation",
                "Mandatory reporting exposure drives institutional and reputational risk",
                "More corroborating signals reduce false-positive probability",
            ],
        })
        st.dataframe(weights_df, use_container_width=True, hide_index=True)

        st.subheader("API Configuration")
        st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""),
                      help="Managed via OPENAI_API_KEY environment variable")
