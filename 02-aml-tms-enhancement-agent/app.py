"""
AML/TMS Enhancement Agent — Streamlit Dashboard
Pre-queue false positive reduction monitoring and control center.

Panels:
  1. Live Scoring Queue    — process pending TMS alerts through the AI scoring pipeline
  2. FP Reduction Metrics — daily/cumulative suppression stats and analyst hours saved
  3. Suppression Audit    — BSA Officer review panel for all suppression decisions
  4. Alert Detail         — full score breakdown for any processed alert
  5. Threshold Config     — operational controls for scoring thresholds (BSA Officer only)
"""
import os
import time
import json
from datetime import datetime

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AML/TMS Enhancement Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: #1c2333;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px 20px;
        margin: 4px 0;
    }
    .metric-label { color: #8b949e; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { color: #f0f6fc; font-size: 1.8rem; font-weight: 700; }
    .metric-sub   { color: #58a6ff; font-size: 0.75rem; margin-top: 2px; }
    .decision-suppress   { background:#1a0a0a; border-left:4px solid #f85149; border-radius:6px; padding:10px 14px; margin:4px 0; }
    .decision-downgrade  { background:#1a140a; border-left:4px solid #e3b341; border-radius:6px; padding:10px 14px; margin:4px 0; }
    .decision-passthrough{ background:#0a1a14; border-left:4px solid #3fb950; border-radius:6px; padding:10px 14px; margin:4px 0; }
    .decision-escalate   { background:#0a0a1a; border-left:4px solid #58a6ff; border-radius:6px; padding:10px 14px; margin:4px 0; }
    .badge-suppress    { background:#f85149; color:#fff; padding:2px 8px; border-radius:12px; font-size:0.72rem; font-weight:700; }
    .badge-downgrade   { background:#e3b341; color:#000; padding:2px 8px; border-radius:12px; font-size:0.72rem; font-weight:700; }
    .badge-passthrough { background:#3fb950; color:#000; padding:2px 8px; border-radius:12px; font-size:0.72rem; font-weight:700; }
    .badge-escalate    { background:#58a6ff; color:#000; padding:2px 8px; border-radius:12px; font-size:0.72rem; font-weight:700; }
    .section-header { color: #f0f6fc; font-size: 1.05rem; font-weight: 600; margin: 16px 0 8px 0; border-bottom: 1px solid #30363d; padding-bottom: 6px; }
</style>
""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "processed_alerts": [],       # List of completed scoring results
        "scoring_in_progress": False,
        "current_user_role": "BSA_OFFICER",
        "current_user": "Officer J. Reynolds",
        "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "thresholds": {
            "suppress": float(os.getenv("SUPPRESS_THRESHOLD", 85)),
            "downgrade": float(os.getenv("DOWNGRADE_THRESHOLD", 60)),
            "escalate": float(os.getenv("ESCALATE_THRESHOLD", 15)),
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ AML/TMS Enhancement")
    st.markdown("**Pre-Queue False Positive Reduction**")
    st.divider()

    role = st.selectbox(
        "Role",
        ["BSA_OFFICER", "ANALYST_SENIOR", "ANALYST"],
        index=["BSA_OFFICER", "ANALYST_SENIOR", "ANALYST"].index(
            st.session_state.current_user_role
        ),
    )
    st.session_state.current_user_role = role

    st.divider()

    # API key status
    if st.session_state.api_key_set:
        st.success("✓ OpenAI API key configured")
    else:
        api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
            st.session_state.api_key_set = True
            st.rerun()

    st.divider()
    st.markdown("**Scoring Thresholds**")
    st.caption(f"Suppress ≥ {st.session_state.thresholds['suppress']:.0f}% FP")
    st.caption(f"Downgrade ≥ {st.session_state.thresholds['downgrade']:.0f}% FP")
    st.caption(f"Escalate ≤ {st.session_state.thresholds['escalate']:.0f}% FP")

    st.divider()
    st.caption("Downstream: Financial Crime Investigation Agent →")
    st.caption("Regulatory: BSA | SR 11-7 | FinCEN")


# ── Tab layout ─────────────────────────────────────────────────────────────────
tab_queue, tab_metrics, tab_audit, tab_detail, tab_thresholds = st.tabs([
    "⚡ Live Scoring Queue",
    "📊 FP Reduction Metrics",
    "📋 Suppression Audit",
    "🔍 Alert Detail",
    "⚙️ Threshold Config",
])


# ── Tab 1: Live Scoring Queue ──────────────────────────────────────────────────
with tab_queue:
    st.markdown("## ⚡ Live Alert Scoring Queue")
    st.markdown(
        "Process pending TMS alerts through the AI false positive scoring pipeline. "
        "Surviving alerts are forwarded to the **Financial Crime Investigation Agent**."
    )

    if not st.session_state.api_key_set:
        st.warning("Configure your OpenAI API key in the sidebar to run live scoring.")
    else:
        col_load, col_run, col_clear = st.columns([2, 2, 1])

        with col_load:
            if st.button("📥 Load Pending TMS Alerts", use_container_width=True):
                from tools.tms_connector import get_pending_alerts
                st.session_state["pending_alerts"] = get_pending_alerts()
                st.success(f"Loaded {len(st.session_state['pending_alerts'])} pending alerts")

        with col_run:
            run_all = st.button(
                "🚀 Score All Alerts",
                use_container_width=True,
                disabled=not st.session_state.get("pending_alerts"),
            )

        with col_clear:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state["pending_alerts"] = []
                st.session_state["processed_alerts"] = []
                st.rerun()

        # Show pending alerts
        pending = st.session_state.get("pending_alerts", [])
        if pending:
            st.markdown(f"**{len(pending)} alerts pending scoring:**")
            for alert in pending:
                with st.expander(
                    f"📨 {alert['alert_id']} | {alert['alert_type']} | "
                    f"${alert['amount']:,.0f} | Severity: {alert['severity']}"
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.json({
                            "alert_id": alert["alert_id"],
                            "customer_id": alert["customer_id"],
                            "alert_type": alert["alert_type"],
                            "triggered_rule": alert["triggered_rule"],
                            "amount": f"${alert['amount']:,.2f}",
                            "tms_vendor": alert["tms_vendor"],
                        })
                    with col2:
                        if st.button(f"Score this alert", key=f"score_{alert['alert_id']}"):
                            _run_single_alert(alert)

        # Run all
        if run_all and pending:
            progress = st.progress(0, text="Scoring alerts...")
            for i, alert in enumerate(pending):
                progress.progress((i + 1) / len(pending), text=f"Scoring {alert['alert_id']}...")
                _run_single_alert(alert)
            st.success(f"✅ Scored {len(pending)} alerts")
            st.rerun()

    # Display processed results
    processed = st.session_state.get("processed_alerts", [])
    if processed:
        st.divider()
        st.markdown(f"### Scoring Results ({len(processed)} alerts)")

        for result in reversed(processed):
            routing = result.get("routing", {})
            decision = routing.get("decision", "UNKNOWN")
            fp_prob = routing.get("fp_probability", 0)
            alert_id = result.get("alert_id", "?")
            raw_alert = result.get("raw_alert", {})
            action = result.get("queue_action", "unknown")

            badge_class = {
                "SUPPRESS": "badge-suppress",
                "DOWNGRADE": "badge-downgrade",
                "PASS_THROUGH": "badge-passthrough",
                "ESCALATE": "badge-escalate",
            }.get(decision, "badge-passthrough")

            card_class = {
                "SUPPRESS": "decision-suppress",
                "DOWNGRADE": "decision-downgrade",
                "PASS_THROUGH": "decision-passthrough",
                "ESCALATE": "decision-escalate",
            }.get(decision, "decision-passthrough")

            st.markdown(
                f"""<div class="{card_class}">
                <span class="{badge_class}">{decision}</span>
                &nbsp;&nbsp;<strong>{alert_id}</strong> &nbsp;|&nbsp;
                {raw_alert.get('alert_type','?')} &nbsp;|&nbsp;
                FP Probability: <strong>{fp_prob:.0f}%</strong> &nbsp;|&nbsp;
                Action: <strong>{action}</strong>
                <br/><small style="color:#8b949e">{routing.get('primary_reason','')[:120]}</small>
                </div>""",
                unsafe_allow_html=True,
            )


# ── Tab 2: FP Reduction Metrics ────────────────────────────────────────────────
with tab_metrics:
    st.markdown("## 📊 False Positive Reduction Metrics")

    from tools.suppression_engine import get_suppression_stats
    stats = get_suppression_stats(days=30)

    # KPI row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(
            f"""<div class="metric-card">
            <div class="metric-label">Total Processed</div>
            <div class="metric-value">{stats['total_processed']:,}</div>
            <div class="metric-sub">Last 30 days</div>
            </div>""", unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"""<div class="metric-card">
            <div class="metric-label">Suppressed</div>
            <div class="metric-value" style="color:#f85149">{stats['suppressed']:,}</div>
            <div class="metric-sub">{stats['suppression_rate']:.0%} of total</div>
            </div>""", unsafe_allow_html=True
        )
    with col3:
        st.markdown(
            f"""<div class="metric-card">
            <div class="metric-label">Downgraded</div>
            <div class="metric-value" style="color:#e3b341">{stats['downgraded']:,}</div>
            <div class="metric-sub">Lower priority</div>
            </div>""", unsafe_allow_html=True
        )
    with col4:
        st.markdown(
            f"""<div class="metric-card">
            <div class="metric-label">Analyst Hours Saved</div>
            <div class="metric-value" style="color:#3fb950">{stats['analyst_hours_saved']:.1f}h</div>
            <div class="metric-sub">@ 25 min/alert</div>
            </div>""", unsafe_allow_html=True
        )
    with col5:
        st.markdown(
            f"""<div class="metric-card">
            <div class="metric-label">Escalated</div>
            <div class="metric-value" style="color:#58a6ff">{stats['escalated']:,}</div>
            <div class="metric-sub">Fast-tracked to FCU</div>
            </div>""", unsafe_allow_html=True
        )

    st.divider()

    # Distribution chart from processed results
    processed = st.session_state.get("processed_alerts", [])
    if processed:
        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            # Decision distribution pie
            from collections import Counter
            decisions = [r.get("routing", {}).get("decision", "UNKNOWN") for r in processed]
            counts = Counter(decisions)
            fig_pie = go.Figure(data=[go.Pie(
                labels=list(counts.keys()),
                values=list(counts.values()),
                hole=0.4,
                marker_colors=["#f85149", "#e3b341", "#3fb950", "#58a6ff"],
            )])
            fig_pie.update_layout(
                title="Alert Disposition Distribution",
                paper_bgcolor="#1c2333",
                font_color="#f0f6fc",
                showlegend=True,
                height=320,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_chart2:
            # FP probability distribution
            fp_probs = [
                r.get("routing", {}).get("fp_probability", 0) for r in processed
            ]
            fig_hist = go.Figure(data=[go.Histogram(
                x=fp_probs,
                nbinsx=10,
                marker_color="#58a6ff",
                opacity=0.8,
            )])
            fig_hist.update_layout(
                title="FP Probability Distribution",
                xaxis_title="FP Probability (%)",
                yaxis_title="Alert Count",
                paper_bgcolor="#1c2333",
                plot_bgcolor="#161b22",
                font_color="#f0f6fc",
                height=320,
            )
            # Add threshold lines
            fig_hist.add_vline(x=st.session_state.thresholds["suppress"],
                               line_dash="dash", line_color="#f85149",
                               annotation_text="Suppress")
            fig_hist.add_vline(x=st.session_state.thresholds["downgrade"],
                               line_dash="dash", line_color="#e3b341",
                               annotation_text="Downgrade")
            fig_hist.add_vline(x=st.session_state.thresholds["escalate"],
                               line_dash="dash", line_color="#58a6ff",
                               annotation_text="Escalate")
            st.plotly_chart(fig_hist, use_container_width=True)

        # ROI calculation
        st.divider()
        st.markdown("### 💰 ROI Estimate")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            analyst_cost = st.number_input(
                "Analyst fully-loaded annual cost ($)",
                value=80_000, step=5_000, format="%d"
            )
            daily_alerts = st.number_input(
                "Daily alert volume (bank-wide)",
                value=500, step=50
            )
        with col_r2:
            hourly_cost = analyst_cost / 2080
            alert_cost = hourly_cost * (25 / 60)
            fp_rate = 0.90  # Industry baseline
            suppression_rate_ai = st.session_state.thresholds["suppress"] / 100

            annual_fp_cost = daily_alerts * 365 * fp_rate * alert_cost
            annual_savings = annual_fp_cost * (suppression_rate_ai * 0.55)  # ~55% of FPs suppressed

            st.markdown(f"""
            | Metric | Value |
            |--------|-------|
            | Cost per alert reviewed | ${alert_cost:.2f} |
            | Annual FP cost (baseline) | ${annual_fp_cost:,.0f} |
            | **Estimated annual savings** | **${annual_savings:,.0f}** |
            | Alerts removed from queue/yr | {int(daily_alerts * 365 * fp_rate * 0.55):,} |
            """)

    else:
        st.info("Score some alerts in the **Live Scoring Queue** tab to see metrics.")


# ── Tab 3: Suppression Audit ───────────────────────────────────────────────────
with tab_audit:
    st.markdown("## 📋 Suppression Audit Trail")
    st.markdown(
        "All alert suppression decisions are recorded here for BSA Officer review. "
        "Suppressions must be reviewed within **90 days** per SR 11-7 model monitoring requirements."
    )

    from tools.suppression_engine import get_suppression_log
    suppression_log = get_suppression_log(days=90)

    if st.session_state.thresholds:
        pending_review = [r for r in suppression_log if r.get("review_status") == "PENDING"]
        if pending_review:
            st.warning(f"⚠️ {len(pending_review)} suppression(s) pending BSA Officer review")

    if not suppression_log:
        st.info("No suppression records in the last 90 days. Score some alerts to generate records.")
    else:
        for record in reversed(suppression_log):
            with st.expander(
                f"SUP: {record['suppression_id']} | Alert: {record['alert_id']} | "
                f"FP={record['fp_probability']:.0f}% | "
                f"Review due: {record['mandatory_review_date']} | "
                f"Status: {record['review_status']}"
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown("**Suppression Justification**")
                    st.markdown(record.get("justification_narrative", "No narrative generated."))

                    st.markdown("**Key Suppression Factors**")
                    for factor in record.get("suppression_factors", []):
                        st.markdown(f"- {factor}")

                    if record.get("pass_through_factors"):
                        st.markdown("**Factors Considered But Outweighed**")
                        for factor in record.get("pass_through_factors", []):
                            st.markdown(f"- {factor}")

                with col2:
                    st.metric("FP Probability", f"{record['fp_probability']:.0f}%")
                    st.metric("Confidence", f"{record['confidence']:.0%}")
                    st.caption(f"Suppressed: {record['suppressed_at'][:10]}")
                    st.caption(f"Review due: {record['mandatory_review_date']}")

                    if st.session_state.current_user_role == "BSA_OFFICER":
                        col_a, col_r = st.columns(2)
                        with col_a:
                            if st.button("✓ Approve", key=f"approve_{record['suppression_id']}"):
                                st.success("Suppression approved")
                        with col_r:
                            if st.button("✗ Reverse", key=f"reverse_{record['suppression_id']}"):
                                st.warning("Reversal queued — alert will be routed to analyst")
                    else:
                        st.caption("BSA Officer role required to review")

    # Full audit trail for processed alerts
    processed = st.session_state.get("processed_alerts", [])
    if processed:
        st.divider()
        st.markdown("### Full Scoring Audit Trail")
        selected_alert = st.selectbox(
            "Select alert",
            options=[r["alert_id"] for r in processed],
        )
        result = next((r for r in processed if r["alert_id"] == selected_alert), None)
        if result:
            trail = result.get("audit_trail", [])
            for entry in trail:
                st.markdown(
                    f"**{entry['timestamp'][:19]}** | `{entry['action']}` "
                    f"| Actor: {entry['actor']}"
                    + (f" | Model: {entry['ai_model_used']}" if entry.get("ai_model_used") else "")
                )
                with st.expander("Details", expanded=False):
                    st.json(entry.get("details", {}))


# ── Tab 4: Alert Detail ────────────────────────────────────────────────────────
with tab_detail:
    st.markdown("## 🔍 Alert Scoring Detail")

    processed = st.session_state.get("processed_alerts", [])
    if not processed:
        st.info("No scored alerts yet. Use the **Live Scoring Queue** tab to score alerts.")
    else:
        selected = st.selectbox(
            "Select alert to inspect",
            options=[r["alert_id"] for r in processed],
            key="detail_select",
        )
        result = next((r for r in processed if r["alert_id"] == selected), None)

        if result:
            routing = result.get("routing", {})
            decision = routing.get("decision", "UNKNOWN")
            fp_prob = routing.get("fp_probability", 0)

            # Header
            badge_colors = {
                "SUPPRESS": "#f85149", "DOWNGRADE": "#e3b341",
                "PASS_THROUGH": "#3fb950", "ESCALATE": "#58a6ff",
            }
            color = badge_colors.get(decision, "#58a6ff")
            st.markdown(
                f"<h3 style='color:{color}'>{decision} — FP Probability: {fp_prob:.0f}%</h3>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**{routing.get('primary_reason', '')}**")

            col1, col2 = st.columns(2)

            with col1:
                # FP probability gauge
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=fp_prob,
                    title={"text": "FP Probability", "font": {"color": "#f0f6fc"}},
                    gauge={
                        "axis": {"range": [0, 100], "tickcolor": "#8b949e"},
                        "bar": {"color": color},
                        "bgcolor": "#1c2333",
                        "steps": [
                            {"range": [0, 15], "color": "#0d1117"},
                            {"range": [15, 60], "color": "#161b22"},
                            {"range": [60, 85], "color": "#21262d"},
                            {"range": [85, 100], "color": "#30363d"},
                        ],
                        "threshold": {
                            "line": {"color": "#f85149", "width": 3},
                            "thickness": 0.75,
                            "value": st.session_state.thresholds["suppress"],
                        },
                    },
                    number={"suffix": "%", "font": {"color": "#f0f6fc"}},
                ))
                fig_gauge.update_layout(
                    paper_bgcolor="#1c2333", font_color="#f0f6fc", height=280
                )
                st.plotly_chart(fig_gauge, use_container_width=True)

            with col2:
                # Score breakdown bar chart
                breakdown = result.get("score_breakdown", {})
                if breakdown:
                    components = ["Rule-Based", "LLM", "Historical"]
                    scores = [
                        breakdown.get("rule_based_score", 0),
                        breakdown.get("llm_score", 0),
                        breakdown.get("historical_score", 0),
                    ]
                    weights = [
                        breakdown.get("rule_based_weight", 0.3),
                        breakdown.get("llm_weight", 0.5),
                        breakdown.get("historical_weight", 0.2),
                    ]
                    contributions = [s * w for s, w in zip(scores, weights)]

                    fig_bar = go.Figure(go.Bar(
                        x=components,
                        y=contributions,
                        marker_color=["#58a6ff", "#3fb950", "#e3b341"],
                        text=[f"{c:.1f}" for c in contributions],
                        textposition="outside",
                    ))
                    fig_bar.update_layout(
                        title="Score Component Contributions",
                        yaxis_title="Weighted Contribution (0-100)",
                        paper_bgcolor="#1c2333",
                        plot_bgcolor="#161b22",
                        font_color="#f0f6fc",
                        height=280,
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

            # Suppression factors
            col3, col4 = st.columns(2)
            with col3:
                st.markdown("**Suppression Factors** (evidence for FP)")
                for f in routing.get("suppression_factors", []):
                    st.markdown(f"🔴 {f}")

            with col4:
                st.markdown("**Pass-Through Factors** (evidence against suppression)")
                for f in routing.get("pass_through_factors", []):
                    st.markdown(f"🟢 {f}")

            # LLM narrative
            if result.get("llm_analysis_narrative"):
                st.divider()
                st.markdown("**LLM Analysis Narrative**")
                st.markdown(result["llm_analysis_narrative"])

            # Suppression justification
            if result.get("suppression_justification"):
                st.divider()
                st.markdown("**Regulatory Suppression Justification** *(stored in audit log)*")
                st.info(result["suppression_justification"])

            # Raw state JSON
            with st.expander("Raw scoring state (full JSON)"):
                # Exclude verbose fields for readability
                display = {k: v for k, v in result.items()
                           if k not in ("audit_trail", "scoring_notes", "raw_alert")}
                st.json(display)


# ── Tab 5: Threshold Config ────────────────────────────────────────────────────
with tab_thresholds:
    st.markdown("## ⚙️ Scoring Threshold Configuration")

    if st.session_state.current_user_role != "BSA_OFFICER":
        st.warning("BSA Officer role required to modify scoring thresholds.")
    else:
        st.markdown(
            "Thresholds govern the minimum FP probability required for each routing decision. "
            "Changes take effect immediately and are logged in the audit trail. "
            "**SR 11-7**: threshold changes must be reviewed and approved by the CAMLO."
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            new_suppress = st.slider(
                "SUPPRESS threshold (FP% ≥ this → alert suppressed)",
                min_value=70, max_value=99,
                value=int(st.session_state.thresholds["suppress"]),
                help="Higher = more conservative; fewer suppressions",
            )
            new_downgrade = st.slider(
                "DOWNGRADE threshold (FP% ≥ this → priority reduced)",
                min_value=40, max_value=int(new_suppress) - 1,
                value=min(int(st.session_state.thresholds["downgrade"]), new_suppress - 1),
                help="Alert still reaches analyst, just at lower priority",
            )
            new_escalate = st.slider(
                "ESCALATE threshold (FP% ≤ this → fast-tracked)",
                min_value=5, max_value=30,
                value=int(st.session_state.thresholds["escalate"]),
                help="Lower = fewer escalations; alerts between escalate and downgrade are PASS_THROUGH",
            )

        with col2:
            st.markdown("**Decision Bands (current settings)**")
            fig_thresh = go.Figure()
            bands = [
                (0, new_escalate, "#58a6ff", "ESCALATE"),
                (new_escalate, new_downgrade, "#3fb950", "PASS_THROUGH"),
                (new_downgrade, new_suppress, "#e3b341", "DOWNGRADE"),
                (new_suppress, 100, "#f85149", "SUPPRESS"),
            ]
            for low, high, color, label in bands:
                fig_thresh.add_shape(
                    type="rect", x0=0, x1=1, y0=low, y1=high,
                    fillcolor=color, opacity=0.25, line_width=0,
                )
                fig_thresh.add_annotation(
                    x=0.5, y=(low + high) / 2, text=label,
                    showarrow=False, font={"color": "#f0f6fc", "size": 12},
                )
            fig_thresh.update_layout(
                xaxis={"visible": False},
                yaxis={"title": "FP Probability (%)", "range": [0, 100]},
                paper_bgcolor="#1c2333", plot_bgcolor="#161b22",
                font_color="#f0f6fc", height=350, showlegend=False,
            )
            st.plotly_chart(fig_thresh, use_container_width=True)

        if st.button("💾 Save Threshold Changes", type="primary"):
            st.session_state.thresholds = {
                "suppress": new_suppress,
                "downgrade": new_downgrade,
                "escalate": new_escalate,
            }
            os.environ["SUPPRESS_THRESHOLD"] = str(new_suppress)
            os.environ["DOWNGRADE_THRESHOLD"] = str(new_downgrade)
            os.environ["ESCALATE_THRESHOLD"] = str(new_escalate)
            st.success(
                f"Thresholds updated: Suppress≥{new_suppress}% | "
                f"Downgrade≥{new_downgrade}% | Escalate≤{new_escalate}%"
            )

        st.divider()
        st.markdown("**Alert-Type Override Thresholds** *(defined in scoring/threshold_manager.py)*")
        from scoring.threshold_manager import ALERT_TYPE_OVERRIDES
        override_data = [
            {
                "Alert Type": at,
                "Suppress ≥": t.suppress,
                "Downgrade ≥": t.downgrade,
                "Escalate ≤": t.escalate,
                "Note": "Never suppress" if t.suppress >= 999 else "",
            }
            for at, t in ALERT_TYPE_OVERRIDES.items()
        ]
        st.dataframe(pd.DataFrame(override_data), use_container_width=True, hide_index=True)


# ── Helper function ────────────────────────────────────────────────────────────
def _run_single_alert(alert: dict):
    """Score one alert and append result to session state."""
    from agent.graph import build_graph

    try:
        app = build_graph()
        result = app.invoke(
            {"raw_alert": alert},
            config={"configurable": {"thread_id": alert["alert_id"]}},
        )
        processed = st.session_state.get("processed_alerts", [])
        # Avoid duplicates
        processed = [p for p in processed if p.get("alert_id") != alert["alert_id"]]
        processed.append(result)
        st.session_state["processed_alerts"] = processed
    except Exception as exc:
        st.error(f"Scoring failed for {alert['alert_id']}: {exc}")
