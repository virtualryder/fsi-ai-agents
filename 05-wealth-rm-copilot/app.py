# app.py
# ============================================================
# Wealth & RM Copilot — Streamlit Dashboard
#
# Run: streamlit run app.py
# Port: 8505
#
# Tabs:
#   1. RM Request       — Load scenario or enter custom request
#   2. Client Profile   — CRM data, IPS, risk profile, goals
#   3. Portfolio Intel  — Holdings, performance, drift, news
#   4. AI Draft         — Generated briefing/proposal/review/letter
#   5. RM Approval      — HITL: RM reviews, edits, approves
#   6. Audit Trail      — Compliance archive (SEC 204-2 / FINRA 4511)
# ============================================================

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import plotly.graph_objects as go
import streamlit as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Wealth & RM Copilot",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State ─────────────────────────────────────────────────────────────
for key, default in [
    ("graph", None), ("thread_config", None), ("workflow_result", None),
    ("running", False), ("rm_submitted", False), ("selected_request", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


@st.cache_resource
def get_graph():
    from agent.graph import build_wealth_rm_graph
    return build_wealth_rm_graph(use_memory=True)


@st.cache_data
def load_sample_requests():
    p = Path("data/fixtures/sample_requests.json")
    return json.load(open(p)) if p.exists() else []


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💼 Wealth & RM Copilot")
    st.markdown("""
    **AI-Powered RM Productivity Suite**

    Workflows:
    - Meeting Preparation
    - Rebalancing Proposals
    - Investment Proposals
    - Portfolio Reviews
    - Client Communications
    - Alert Responses

    **Regulatory Coverage:**
    - Reg BI (17 CFR 240.15l-1)
    - FINRA 2111 Suitability
    - FINRA 2210 Communications
    - ERISA Fiduciary Standard
    - SEC Rule 204-2 / FINRA 4511
    """)

    st.divider()
    api_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    st.divider()
    st.markdown("**Suitability Routing:**")
    st.markdown("""
    | Status | Action |
    |--------|--------|
    | SUITABLE | Proceed |
    | SUITABLE_WITH_NOTE | Proceed + disclosures |
    | NEEDS_REVIEW | Proceed + flag |
    | UNSUITABLE | ❌ Block |
    """)


# ── Header ─────────────────────────────────────────────────────────────────────
st.title("💼 Wealth & RM Copilot")
st.markdown(
    "**LangGraph 10-Node Pipeline** · Client Profile · Portfolio Analysis · Reg BI Suitability · "
    "GPT-4o Drafting · FINRA 2210 Compliance · RM Approval Gate"
)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 RM Request",
    "👤 Client Profile",
    "📊 Portfolio Intel",
    "📝 AI Draft",
    "✅ RM Approval",
    "🗂️ Audit Trail",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: RM Request
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Create RM Workflow Request")

    mode = st.radio("Input Mode", ["Sample Scenarios", "Custom Request"], horizontal=True)

    if mode == "Sample Scenarios":
        samples = load_sample_requests()
        if samples:
            labels = {s["request_id"]: s["_scenario"] for s in samples}
            sel = st.selectbox("Select Scenario", list(labels.keys()), format_func=lambda x: labels[x])
            req = next(s for s in samples if s["request_id"] == sel)
            st.session_state.selected_request = {k: v for k, v in req.items() if not k.startswith("_")}
            st.json(st.session_state.selected_request)
    else:
        col1, col2 = st.columns(2)
        with col1:
            req_id = st.text_input("Request ID", value=f"RM-{datetime.now().strftime('%Y%m%d')}-CUSTOM001")
            rm_id = st.text_input("RM ID", value="RM-SMITH-001")
            client_id = st.text_input("Client ID", value="CUST-WM-001")
            req_type = st.selectbox("Request Type", [
                "MEETING_PREP", "REBALANCING_PROPOSAL", "INVESTMENT_PROPOSAL",
                "PORTFOLIO_REVIEW", "CLIENT_COMMUNICATION", "ALERT_RESPONSE",
            ])
        with col2:
            context = st.text_area("Request Context", height=100,
                                   placeholder="E.g., Q3 review, client concerned about rates...")
            investment_idea = st.text_input("Investment Idea (if applicable)",
                                            placeholder="E.g., Vanguard TIPS fund for inflation hedge")
            meeting_date = st.date_input("Meeting Date (if applicable)")

        if st.button("Load Request"):
            st.session_state.selected_request = {
                "request_id": req_id, "rm_id": rm_id, "client_id": client_id,
                "request_type": req_type, "request_context": context,
                "investment_idea": investment_idea or None,
                "meeting_date": str(meeting_date) if meeting_date else None,
            }
            st.success("Request loaded.")

    st.divider()
    if st.session_state.selected_request:
        if st.button("🚀 Run Workflow", type="primary", use_container_width=True):
            if not os.getenv("OPENAI_API_KEY"):
                st.warning("OpenAI API key required.")
            else:
                st.session_state.running = True
                st.session_state.workflow_result = None
                st.session_state.rm_submitted = False
                try:
                    graph = get_graph()
                    import uuid
                    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
                    st.session_state.thread_config = config
                    with st.spinner("Running RM Copilot workflow..."):
                        result = graph.invoke(st.session_state.selected_request, config=config)
                    st.session_state.workflow_result = result
                    st.session_state.running = False
                    output_type = result.get("output_type", "DOCUMENT")
                    st.success(f"Workflow complete — {output_type} ready for RM review.")
                    st.rerun()
                except Exception as e:
                    st.session_state.running = False
                    st.error(f"Workflow failed: {e}")
    else:
        st.info("Load a request above to run the workflow.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: Client Profile
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Client Profile & Investment Policy Statement")
    result = st.session_state.workflow_result

    if not result:
        st.info("Run a workflow to see client profile.")
    else:
        profile = result.get("client_profile") or {}
        ips = result.get("ips_summary") or {}

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total AUM", f"${profile.get('total_aum', 0):,.0f}")
        col2.metric("Risk Tolerance", profile.get("risk_tolerance", "—"))
        col3.metric("Time Horizon", f"{profile.get('time_horizon_years', '—')} yrs")
        col4.metric("Client Since", profile.get("client_since_date", "—")[:4] if profile.get("client_since_date") else "—")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Client Details")
            st.markdown(f"**Name:** {profile.get('full_name', '—')}")
            st.markdown(f"**Age:** {profile.get('age', '—')}")
            st.markdown(f"**Employment:** {profile.get('employment_status', '—')}")
            st.markdown(f"**Tax Bracket:** {profile.get('tax_bracket', '—')}")
            st.markdown(f"**Primary Goals:** {', '.join(profile.get('primary_goals', []))}")
            st.markdown(f"**Retirement Account:** {'Yes (ERISA)' if profile.get('is_retirement_account') else 'No'}")
            st.markdown(f"**ESG Preference:** {'Yes' if profile.get('esg_preference') else 'No'}")
            if profile.get("next_rmd_date"):
                st.warning(f"⚠️ RMD Due: {profile.get('next_rmd_date')}")

        with col2:
            st.markdown("### Investment Policy Statement")
            st.markdown(f"**Benchmark:** {ips.get('benchmark', '—')}")
            st.markdown(f"**Return Objective:** {ips.get('return_objective', '—')}")
            st.markdown(f"**IPS Version:** {ips.get('ips_version', '—')}")
            st.markdown(f"**Last Updated:** {ips.get('last_updated', '—')}")
            if ips.get("income_requirement"):
                st.markdown(f"**Annual Income Req:** ${ips.get('income_requirement', 0):,.0f}")

            targets = ips.get("target_allocations", {})
            if targets:
                fig = go.Figure(go.Pie(
                    labels=list(targets.keys()),
                    values=list(targets.values()),
                    hole=0.4,
                ))
                fig.update_layout(
                    title="IPS Target Allocation",
                    height=250, paper_bgcolor="rgba(0,0,0,0)", font_color="white",
                    showlegend=True, legend=dict(orientation="h"),
                )
                st.plotly_chart(fig, use_container_width=True)

        # Suitability summary
        suit = result.get("suitability_analysis") or {}
        status = result.get("suitability_status")
        status_val = status.value if hasattr(status, "value") else str(status or "—")
        status_colors = {
            "SUITABLE": "green", "SUITABLE_WITH_NOTE": "orange",
            "NEEDS_REVIEW": "orange", "UNSUITABLE": "red",
        }
        color = status_colors.get(status_val, "gray")
        st.markdown(f"### Suitability Status: :{color}[{status_val}]")

        checks = suit.get("checks_performed", [])
        if checks:
            for c in checks:
                icon = "✅" if c.get("passed") else "❌"
                st.markdown(f"{icon} **{c.get('check')}** — {c.get('note')}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: Portfolio Intel
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Portfolio Analysis & Market Intelligence")
    result = st.session_state.workflow_result

    if not result:
        st.info("Run a workflow to see portfolio data.")
    else:
        portfolio = result.get("portfolio_snapshot") or {}
        drift = result.get("allocation_drift") or {}
        ips = result.get("ips_summary") or {}

        # Performance metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Market Value", f"${portfolio.get('total_market_value', 0):,.0f}")
        ytd = portfolio.get("ytd_return", 0)
        bench = portfolio.get("benchmark_ytd", 0)
        col2.metric("YTD Return", f"{ytd:+.1f}%", delta=f"{ytd - bench:+.1f}% vs benchmark")
        col3.metric("1-Year Return", f"{portfolio.get('one_year_return', 0):+.1f}%")
        col4.metric("Sharpe Ratio", f"{portfolio.get('sharpe_ratio', 0):.2f}")

        col1, col2 = st.columns(2)

        with col1:
            # Current vs IPS target allocation
            curr_alloc = portfolio.get("current_allocations", {})
            targets = ips.get("target_allocations", {})
            asset_classes = list(targets.keys())
            if asset_classes:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name="Current",
                    x=asset_classes,
                    y=[curr_alloc.get(a, 0) for a in asset_classes],
                    marker_color="#3b82f6",
                ))
                fig.add_trace(go.Bar(
                    name="IPS Target",
                    x=asset_classes,
                    y=[targets.get(a, 0) for a in asset_classes],
                    marker_color="#10b981",
                ))
                fig.update_layout(
                    barmode="group", title="Current vs. IPS Target Allocation",
                    height=300, paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)", font_color="white",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Drift gauge
            max_drift = drift.get("max_drift", 0)
            fig_drift = go.Figure(go.Indicator(
                mode="gauge+number",
                value=max_drift,
                title={"text": "Max Allocation Drift (%)"},
                gauge={
                    "axis": {"range": [0, 15]},
                    "bar": {"color": "#ef4444" if max_drift > 5 else "#10b981"},
                    "steps": [
                        {"range": [0, 5], "color": "#1a3a1a"},
                        {"range": [5, 10], "color": "#3a2a00"},
                        {"range": [10, 15], "color": "#3a0000"},
                    ],
                },
            ))
            fig_drift.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_drift, use_container_width=True)

        # Drift detail
        if drift.get("requires_rebalancing"):
            st.warning(f"⚠️ Rebalancing Required — {drift.get('drift_summary')}")

        # Holdings table
        holdings = portfolio.get("holdings", [])
        if holdings:
            with st.expander("Portfolio Holdings", expanded=True):
                cols = ["symbol", "name", "asset_class", "value", "weight"]
                rows = [{k: h.get(k) for k in cols} for h in holdings]
                st.table(rows)

        # Concentrated positions
        concentrated = result.get("concentrated_positions") or []
        if concentrated:
            st.warning(f"⚠️ Concentrated Position(s): "
                       f"{', '.join(p.get('name', p.get('symbol')) for p in concentrated)}")

        # Market intelligence
        market = result.get("market_context") or {}
        news = market.get("relevant_news", [])
        if news:
            st.markdown("### Market Intelligence — Relevant to This Portfolio")
            for n in news:
                with st.expander(n.get("headline", ""), expanded=False):
                    st.markdown(f"**Source:** {n.get('source')} · {n.get('date')}")
                    st.markdown(n.get("impact_summary", ""))
                    if n.get("symbols_affected"):
                        st.markdown(f"**Holdings affected:** {', '.join(n.get('symbols_affected'))}")

        # Life events
        life_events = result.get("life_events") or []
        if life_events:
            st.markdown("### Life Events Detected")
            for e in life_events:
                st.info(f"**{e.get('type')}** — {e.get('action_required')}")

        # Open items
        open_items = result.get("open_items") or []
        if open_items:
            st.markdown("### Open Action Items")
            for item in open_items:
                st.markdown(f"• {item}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: AI Draft
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("AI-Generated Draft")
    result = st.session_state.workflow_result

    if not result:
        st.info("Run a workflow to see the AI draft.")
    elif result.get("output_type") == "UNSUITABLE_BLOCK":
        st.error("Workflow blocked — unsuitable determination.")
        st.code(result.get("draft_content", ""), language=None)
    else:
        output_type = result.get("output_type", "DOCUMENT")
        compliance_status = result.get("compliance_status")
        compliance_val = compliance_status.value if hasattr(compliance_status, "value") else str(compliance_status or "PENDING")

        col1, col2, col3 = st.columns(3)
        col1.metric("Output Type", output_type)
        col2.metric("Compliance Status", compliance_val)
        col3.metric("Recommendations", len(result.get("recommendations") or []))

        # Compliance notes
        compliance_notes = result.get("compliance_notes") or []
        if compliance_notes:
            st.warning("**Compliance Issues Flagged:**")
            for note in compliance_notes:
                st.markdown(f"• {note}")

        # Draft content
        draft = result.get("edited_content") or result.get("draft_content") or ""
        st.markdown("### Draft Content")
        st.markdown("*Subject to RM review and approval before any client use*")
        st.text_area("Draft", value=draft, height=450, disabled=False, key="draft_display")

        # Talking points
        talking_points = result.get("talking_points") or []
        if talking_points:
            with st.expander("Extracted Talking Points"):
                for i, tp in enumerate(talking_points, 1):
                    st.markdown(f"{i}. {tp}")

        # Recommendations
        recs = result.get("recommendations") or []
        if recs:
            st.markdown("### Recommendations")
            for rec in recs:
                action = rec.get("action", "REVIEW")
                color_map = {"BUY": "green", "SELL": "red", "REBALANCE": "orange",
                             "HOLD": "blue", "REVIEW": "gray"}
                color = color_map.get(action, "gray")
                with st.expander(f":{color}[{action}] — {rec.get('security')}"):
                    st.markdown(f"**Rationale:** {rec.get('rationale')}")
                    st.markdown(f"**IPS Alignment:** {rec.get('ips_alignment')}")
                    st.markdown(f"**Risk Level:** {rec.get('risk_level')}")
                    if rec.get("amount_usd"):
                        st.markdown(f"**Estimated Amount:** ${rec.get('amount_usd'):,.0f}")
                    if rec.get("estimated_cost"):
                        st.markdown(f"**Estimated Cost:** ${rec.get('estimated_cost'):,.2f}")
                    if rec.get("alternatives_considered"):
                        st.markdown(f"**Alternatives Considered:** {', '.join(rec.get('alternatives_considered'))}")

        # Rebalancing trades
        trades = result.get("rebalancing_trades") or []
        if trades:
            st.markdown("### Rebalancing Trades")
            st.table([{
                "Asset Class": t.get("asset_class"),
                "Symbol": t.get("symbol"),
                "Action": t.get("action"),
                "Est. Value": f"${t.get('estimated_value', 0):,.0f}",
                "Current %": f"{t.get('current_pct', 0):.1f}%",
                "Target %": f"{t.get('target_pct', 0):.0f}%",
            } for t in trades])

        # Required disclosures
        disclosures = result.get("required_disclosures") or []
        if disclosures:
            with st.expander(f"Required Regulatory Disclosures ({len(disclosures)})", expanded=False):
                for d in disclosures:
                    st.markdown(f"• {d}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: RM Approval
# ═══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("✅ RM Review & Approval")
    result = st.session_state.workflow_result

    if not result:
        st.info("Run a workflow to see the RM approval panel.")
    elif result.get("output_type") == "UNSUITABLE_BLOCK":
        st.error("No approval required — workflow blocked for unsuitability.")
    elif result.get("rm_approved"):
        st.success(f"✅ Content approved at {result.get('rm_approved_at', '')[:19]}")
        final = result.get("final_content", "")
        if final:
            st.text_area("Final Approved Content", value=final, height=400, disabled=True)
    else:
        st.markdown("### RM Review Required")
        st.markdown(
            "Review the AI-generated draft below. You are the accountable professional — "
            "your approval represents your professional judgment that this content is appropriate for the client."
        )

        draft_for_review = result.get("edited_content") or result.get("draft_content") or ""
        rm_id = (st.session_state.selected_request or {}).get("rm_id", "RM-001")

        compliance_status = result.get("compliance_status")
        compliance_val = compliance_status.value if hasattr(compliance_status, "value") else str(compliance_status or "")
        if compliance_val == "REJECTED":
            st.error("⚠️ Compliance review REJECTED this draft. Significant issues must be resolved before approval.")

        with st.form("rm_approval"):
            st.markdown("**Review the draft (edit as needed):**")
            edited = st.text_area("Content for Approval", value=draft_for_review, height=400)
            notes = st.text_area("RM Notes / Modifications", height=100,
                                 placeholder="Document any changes made, additional context, or approval rationale...")
            approve = st.form_submit_button("✅ Approve & Finalize", type="primary")
            reject = st.form_submit_button("❌ Reject — Revise Required")

            if approve:
                result["rm_approved"] = True
                result["rm_approved_at"] = datetime.now(timezone.utc).isoformat()
                result["rm_approval_notes"] = notes
                result["edited_content"] = edited

                # Resume LangGraph from rm_approval_gate
                try:
                    graph = get_graph()
                    config = st.session_state.thread_config
                    if config:
                        final_result = graph.invoke(
                            {"rm_approved": True, "rm_approval_notes": notes,
                             "rm_approved_at": result["rm_approved_at"], "edited_content": edited},
                            config=config,
                        )
                        st.session_state.workflow_result = final_result
                except Exception as e:
                    logger.warning(f"Graph resume: {e}")
                    from agent.nodes import finalize_output
                    finalized = finalize_output(result)
                    result.update(finalized)
                    st.session_state.workflow_result = result

                st.session_state.rm_submitted = True
                st.success("✅ Content approved and finalized.")
                st.rerun()

            if reject:
                st.error("Draft rejected. Please revise the request and re-run the workflow.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6: Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("Compliance Audit Trail")
    st.markdown("*Append-only record — SEC Rule 204-2 / FINRA 4511 (6-year retention)*")

    result = st.session_state.workflow_result
    if result:
        trail = result.get("audit_trail") or []
        st.markdown(f"**{len(trail)} entries** for this workflow run")

        for i, entry in enumerate(trail):
            with st.expander(
                f"{i+1}. [{entry.get('node', '?')}] {entry.get('action', '')[:80]}...",
                expanded=(i == len(trail) - 1),
            ):
                col1, col2 = st.columns(2)
                col1.markdown(f"**Timestamp:** {entry.get('timestamp', '')[:19]}")
                col1.markdown(f"**Actor:** {entry.get('actor', '—')}")
                col1.markdown(f"**Node:** `{entry.get('node', '—')}`")
                col2.markdown(f"**Data Sources:** {', '.join(entry.get('data_sources') or [])}")
                if entry.get("ai_model_used"):
                    col2.markdown(f"**AI Model:** {entry.get('ai_model_used')}")
                if entry.get("regulatory_basis"):
                    st.markdown(f"**Regulatory Basis:** *{entry.get('regulatory_basis')}*")

        if trail:
            st.divider()
            st.download_button(
                "📥 Download Audit Trail (JSON)",
                data=json.dumps(trail, indent=2, default=str),
                file_name=f"audit_{result.get('request_id', 'workflow')}.json",
                mime="application/json",
            )
    else:
        st.info("Run a workflow to see the audit trail.")
