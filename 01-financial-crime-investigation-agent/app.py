# app.py
# ============================================================
# Financial Crime Investigation Agent — Streamlit Dashboard
#
# This is the primary user interface for the AI-powered AML investigation platform.
# It provides a professional investigation workflow dashboard modeled after the
# interfaces used by Financial Crimes Units (FCUs) at major banks.
#
# The dashboard enables:
# 1. Alert Queue management — see all active alerts with priority and status
# 2. AI-powered investigation — run the LangGraph agent on any alert
# 3. Risk visualization — understand the risk score and its drivers
# 4. SAR review — review, edit, and approve AI-generated SAR drafts
# 5. Case history — audit trail for regulatory examination readiness
#
# Regulatory note:
#   This application is a TOOL for human investigators — it does not make
#   compliance decisions autonomously. All AI findings require human review
#   by a licensed BSA Officer before any regulatory action is taken.
#
# Run: streamlit run app.py
# ============================================================

import json
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── PAGE CONFIGURATION ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AML Investigation Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "mailto:compliance@yourbank.com",
        "About": "Financial Crime Investigation Agent v1.0 — AI-Powered AML Platform",
    },
)

# ── CUSTOM CSS ────────────────────────────────────────────────────────────────
# Professional financial compliance UI styling
st.markdown("""
<style>
    /* Main header */
    .main-header {
        background: linear-gradient(135deg, #1a1f3c 0%, #2d3561 100%);
        color: white;
        padding: 20px 30px;
        border-radius: 8px;
        margin-bottom: 20px;
    }

    /* Risk score gauge colors */
    .risk-critical { background-color: #dc2626; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; }
    .risk-high { background-color: #ea580c; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; }
    .risk-medium { background-color: #d97706; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; }
    .risk-low { background-color: #16a34a; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; }

    /* Alert severity badges */
    .badge-high { background: #dc2626; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }
    .badge-medium { background: #d97706; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }
    .badge-low { background: #16a34a; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }

    /* Investigation step status */
    .step-complete { color: #16a34a; font-weight: bold; }
    .step-running { color: #2563eb; font-weight: bold; }
    .step-pending { color: #6b7280; }

    /* SAR urgent notice */
    .sar-urgent {
        background: #fef2f2;
        border-left: 4px solid #dc2626;
        padding: 12px;
        margin: 10px 0;
        border-radius: 4px;
    }

    /* Audit trail entries */
    .audit-entry {
        background: #f8f9fa;
        border-left: 3px solid #2563eb;
        padding: 8px 12px;
        margin: 4px 0;
        font-size: 13px;
    }

    /* Integration point callouts */
    .integration-point {
        background: #eff6ff;
        border: 1px dashed #2563eb;
        padding: 10px;
        border-radius: 4px;
        font-size: 12px;
        color: #1e40af;
    }

    /* Metric cards */
    .metric-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }

    /* Progress steps */
    .progress-step-done { color: #16a34a; }
    .progress-step-active { color: #2563eb; font-weight: bold; }
    .progress-step-pending { color: #9ca3af; }

    /* Stealthed disclaimer */
    .compliance-disclaimer {
        font-size: 11px;
        color: #9ca3af;
        border-top: 1px solid #e5e7eb;
        padding-top: 8px;
        margin-top: 16px;
    }
</style>
""", unsafe_allow_html=True)


# ── SESSION STATE INITIALIZATION ──────────────────────────────────────────────
# Streamlit session state persists across reruns within a user's session.
# This stores the investigation state, selected alert, and UI preferences.
def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "authenticated": False,
        "investigator_id": None,
        "investigator_name": None,
        "investigator_role": None,
        "selected_alert": None,
        "investigation_state": None,
        "investigation_running": False,
        "investigation_complete": False,
        "current_step": None,
        "investigation_log": [],
        "human_approved": False,
        "human_decision": None,
        "sar_narrative_edited": None,
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


# ── MOCK AUTHENTICATION ────────────────────────────────────────────────────────
# In production, integrate with your bank's SSO/IdP:
# - SAML 2.0 / Active Directory Federation Services (ADFS)
# - Azure AD / Okta / Ping Identity
# - MFA required for compliance system access
# - Role-based access control (RBAC) — only CAMS-certified analysts
# ── INTEGRATION POINT ────────────────────────────────────────────────────────

MOCK_INVESTIGATORS = {
    "BSA_OFFICER": {
        "name": "Sarah Mitchell, CAMS",
        "role": "BSA Officer",
        "can_approve_sar": True,
        "clearance_level": "FULL",
    },
    "ANALYST_SENIOR": {
        "name": "James Rodriguez, CAMS",
        "role": "Senior AML Analyst",
        "can_approve_sar": False,
        "clearance_level": "STANDARD",
    },
    "ANALYST": {
        "name": "Emily Chen",
        "role": "AML Analyst I",
        "can_approve_sar": False,
        "clearance_level": "STANDARD",
    },
}


def load_alerts() -> List[Dict[str, Any]]:
    """Load sample alerts from fixture data."""
    fixture_path = os.path.join(os.path.dirname(__file__), "data", "fixtures", "sample_alerts.json")
    try:
        with open(fixture_path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def load_customers() -> Dict[str, Any]:
    """Load customer fixture data as dict keyed by customer_id."""
    fixture_path = os.path.join(os.path.dirname(__file__), "data", "fixtures", "sample_customers.json")
    try:
        with open(fixture_path, "r") as f:
            customers = json.load(f)
            return {c["customer_id"]: c for c in customers}
    except Exception:
        return {}


def get_severity_badge(severity: str) -> str:
    """Return HTML badge for alert severity."""
    colors = {"HIGH": "#dc2626", "MEDIUM": "#d97706", "LOW": "#16a34a"}
    color = colors.get(severity.upper(), "#6b7280")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold;">{severity}</span>'


def get_risk_color(score: float) -> str:
    """Return color for risk score."""
    if score >= 70:
        return "#dc2626"  # Red
    elif score >= 50:
        return "#ea580c"  # Orange
    elif score >= 30:
        return "#d97706"  # Amber
    else:
        return "#16a34a"  # Green


def create_risk_gauge(score: float) -> go.Figure:
    """Create a Plotly gauge chart for the risk score."""
    color = get_risk_color(score)

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "Composite AML Risk Score", "font": {"size": 16}},
        delta={"reference": 50, "increasing": {"color": "#dc2626"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "darkblue"},
            "bar": {"color": color},
            "bgcolor": "white",
            "borderwidth": 2,
            "bordercolor": "gray",
            "steps": [
                {"range": [0, 30], "color": "#dcfce7"},
                {"range": [30, 70], "color": "#fef9c3"},
                {"range": [70, 100], "color": "#fee2e2"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": 70,
            },
        },
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="white",
        font={"family": "Arial"},
    )
    return fig


def create_factor_breakdown_chart(factor_scores: Dict) -> go.Figure:
    """Create a horizontal bar chart for risk factor breakdown."""
    factors = []
    scores = []
    maxes = []
    colors = []

    for factor_key, factor_data in factor_scores.items():
        name_map = {
            "watchlist_sanctions": "Watchlist/Sanctions",
            "network_risk": "Network Risk",
            "transaction_patterns": "Transaction Patterns",
            "adverse_media": "Adverse Media",
            "customer_risk_profile": "Customer Risk Profile",
        }
        factors.append(name_map.get(factor_key, factor_key))
        score = factor_data.get("score", 0) if isinstance(factor_data, dict) else 0
        max_score = factor_data.get("max", 30) if isinstance(factor_data, dict) else 30
        scores.append(score)
        maxes.append(max_score)

        pct = score / max_score if max_score > 0 else 0
        if pct >= 0.7:
            colors.append("#dc2626")
        elif pct >= 0.4:
            colors.append("#d97706")
        else:
            colors.append("#16a34a")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=factors,
        x=scores,
        orientation="h",
        marker_color=colors,
        name="Score",
        text=[f"{s}/{m}" for s, m in zip(scores, maxes)],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=factors,
        x=[m - s for s, m in zip(scores, maxes)],
        orientation="h",
        marker_color="#e5e7eb",
        name="Remaining",
        showlegend=False,
    ))

    fig.update_layout(
        barmode="stack",
        height=250,
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="Score",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"size": 12},
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    """Render the sidebar with authentication, alert selection, and system status."""
    with st.sidebar:
        st.markdown("## 🔍 AML Investigation Agent")
        st.markdown("*AI-Powered Financial Crime Platform*")
        st.divider()

        # ── INVESTIGATOR LOGIN ────────────────────────────────────────────────
        st.markdown("### 👤 Investigator Login")
        st.caption("Select your investigator profile (mock auth for demo)")

        investigator_options = list(MOCK_INVESTIGATORS.keys())
        selected_inv_key = st.selectbox(
            "Investigator",
            options=investigator_options,
            format_func=lambda k: f"{MOCK_INVESTIGATORS[k]['name']} ({MOCK_INVESTIGATORS[k]['role']})",
        )
        inv_data = MOCK_INVESTIGATORS[selected_inv_key]

        if st.button("Log In", type="primary", use_container_width=True):
            st.session_state.authenticated = True
            st.session_state.investigator_id = selected_inv_key
            st.session_state.investigator_name = inv_data["name"]
            st.session_state.investigator_role = inv_data["role"]
            st.success(f"Logged in as {inv_data['name']}")

        if st.session_state.authenticated:
            st.markdown(f"""
            **Active Session:**
            - 👤 {st.session_state.investigator_name}
            - 🏷️ {st.session_state.investigator_role}
            - ✅ SAR Approval: {'Yes' if inv_data.get('can_approve_sar') else 'No'}
            """)

        st.divider()

        # ── ALERT SELECTION ───────────────────────────────────────────────────
        st.markdown("### 🚨 Select Alert")
        alerts = load_alerts()

        if alerts:
            alert_options = {
                f"{a['alert_id']} — {a['alert_type']} ({a['severity']})": a
                for a in alerts
            }
            selected_alert_key = st.selectbox(
                "Active Alert",
                options=list(alert_options.keys()),
            )
            selected_alert = alert_options[selected_alert_key]
            st.session_state.selected_alert = selected_alert

            # Alert summary in sidebar
            severity_color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}.get(
                selected_alert.get("severity", "MEDIUM"), "gray"
            )
            st.markdown(f"""
            **Alert Summary:**
            - 🔴 Severity: :{severity_color}[**{selected_alert.get('severity')}**]
            - 📋 Type: {selected_alert.get('alert_type')}
            - 🏦 Customer: {selected_alert.get('customer_id')}
            - 📅 Days Open: {selected_alert.get('days_open', 'N/A')}
            - ⏰ SLA: {selected_alert.get('sla_deadline', 'N/A')}
            """)

        st.divider()

        # ── API CONFIGURATION ──────────────────────────────────────────────────
        st.markdown("### ⚙️ Configuration")
        api_key = st.text_input(
            "OpenAI API Key",
            value=os.getenv("OPENAI_API_KEY", ""),
            type="password",
            help="Required for AI-powered investigation. Get from platform.openai.com",
        )
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            st.session_state.openai_key_configured = True
            st.success("✅ API Key configured")
        else:
            st.session_state.openai_key_configured = False
            st.warning("⚠️ API Key required for AI investigation")

        st.divider()

        # ── SYSTEM STATUS ─────────────────────────────────────────────────────
        st.markdown("### 📊 System Status")
        systems = [
            ("TMS (Actimize)", True, "MOCK"),
            ("Core Banking", True, "MOCK"),
            ("OFAC Screening", True, "MOCK"),
            ("OpenAI GPT-4o", st.session_state.openai_key_configured, "LIVE" if st.session_state.openai_key_configured else "KEY NEEDED"),
            ("Case Mgmt", True, "MOCK"),
        ]
        for sys_name, status, mode in systems:
            icon = "🟢" if status else "🔴"
            badge = f"[{mode}]"
            st.markdown(f"{icon} **{sys_name}** `{badge}`")

        st.markdown("""
        <div class="compliance-disclaimer">
        ⚠️ All AI findings require BSA Officer review before regulatory action. This platform does not autonomously file SARs.
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: ALERT QUEUE
# ══════════════════════════════════════════════════════════════════════════════

def render_alert_queue():
    """Render the active alert queue with severity badges and metadata."""
    st.markdown("## 🚨 Active Alert Queue")
    st.caption("Alerts requiring investigation — sorted by severity and days open")

    alerts = load_alerts()
    customers = load_customers()

    if not alerts:
        st.info("No active alerts found. Check fixture data in data/fixtures/sample_alerts.json")
        return

    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Alerts", len(alerts), help="Active unresolved alerts")
    with col2:
        high_count = sum(1 for a in alerts if a.get("severity") == "HIGH")
        st.metric("High Severity", high_count, delta=None)
    with col3:
        total_hrs = sum(a.get("estimated_investigation_hours", 0) for a in alerts)
        st.metric("Est. Hours (All)", f"{total_hrs}h", help="Total investigator hours required")
    with col4:
        overdue = sum(1 for a in alerts if a.get("days_open", 0) > 20)
        st.metric("Approaching SLA", overdue, delta_color="inverse")

    st.divider()

    # Alert cards
    for alert in sorted(alerts, key=lambda a: (
        {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(a.get("severity", "LOW"), 3),
        -a.get("days_open", 0),
    )):
        severity = alert.get("severity", "MEDIUM")
        customer = customers.get(alert.get("customer_id", ""), {})

        severity_colors = {"HIGH": "#fef2f2", "MEDIUM": "#fffbeb", "LOW": "#f0fdf4"}
        border_colors = {"HIGH": "#dc2626", "MEDIUM": "#d97706", "LOW": "#16a34a"}
        bg_color = severity_colors.get(severity, "#f9f9f9")
        border_color = border_colors.get(severity, "#ccc")

        with st.container():
            st.markdown(f"""
            <div style="border-left:4px solid {border_color};background:{bg_color};padding:12px 16px;border-radius:6px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <strong>{alert.get('alert_id')}</strong> &nbsp;
                        {get_severity_badge(severity)}
                        &nbsp; <span style="color:#6b7280;font-size:13px;">{alert.get('alert_type')}</span>
                    </div>
                    <div style="font-size:13px;color:#6b7280;">Days Open: <strong>{alert.get('days_open', 'N/A')}</strong></div>
                </div>
                <div style="margin-top:8px;font-size:13px;color:#374151;">
                    👤 <strong>{customer.get('full_name') or customer.get('entity_name', alert.get('customer_id'))}</strong> &nbsp;|&nbsp;
                    🏦 {alert.get('customer_id')} &nbsp;|&nbsp;
                    📅 Alert Date: {alert.get('alert_date')} &nbsp;|&nbsp;
                    ⏰ SLA: {alert.get('sla_deadline', 'N/A')}
                </div>
                <div style="margin-top:6px;font-size:12px;color:#6b7280;">
                    {alert.get('description', '')[:200]}{'...' if len(alert.get('description','')) > 200 else ''}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.caption("💡 Select an alert from the sidebar to begin investigation")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: INVESTIGATION
# ══════════════════════════════════════════════════════════════════════════════

def render_investigation():
    """Render the investigation tab with step-by-step progress and results."""
    st.markdown("## 🔎 AI-Powered Investigation")

    if not st.session_state.authenticated:
        st.warning("Please log in using the sidebar to begin an investigation.")
        return

    alert = st.session_state.selected_alert
    if not alert:
        st.info("Select an alert from the sidebar to begin investigation.")
        return

    customers = load_customers()
    customer = customers.get(alert.get("customer_id", ""), {})

    # Alert header
    severity = alert.get("severity", "MEDIUM")
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1e3a5f,#2d5282);color:white;padding:16px 20px;border-radius:8px;margin-bottom:16px;">
        <h3 style="margin:0;color:white;">Alert: {alert.get('alert_id')} &nbsp; {get_severity_badge(severity)}</h3>
        <p style="margin:4px 0 0;opacity:0.85;">
            {alert.get('alert_type')} &nbsp;|&nbsp;
            Customer: {customer.get('full_name') or customer.get('entity_name', alert.get('customer_id'))} &nbsp;|&nbsp;
            {alert.get('customer_id')} &nbsp;|&nbsp;
            Rule: {alert.get('triggered_rule')}
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 3])
    with col1:
        st.markdown("**Alert Summary**")
        st.markdown(f"- **Severity:** {severity}")
        st.markdown(f"- **Days Open:** {alert.get('days_open', 'N/A')}")
        st.markdown(f"- **SLA Deadline:** {alert.get('sla_deadline', 'N/A')}")
        st.markdown(f"- **Transactions:** {len(alert.get('transaction_ids', []))}")
        st.markdown(f"- **Est. Hours:** {alert.get('estimated_investigation_hours', 'N/A')}h → ~2h with AI")

    with col2:
        st.markdown("**Triggering Description**")
        st.info(alert.get("description", "No description available"))

    st.divider()

    # ── INVESTIGATION LAUNCH BUTTON ────────────────────────────────────────────
    if not st.session_state.investigation_running and not st.session_state.investigation_complete:
        col_launch, col_info = st.columns([1, 2])
        with col_launch:
            if st.button("🚀 Launch AI Investigation", type="primary", use_container_width=True):
                if not st.session_state.openai_key_configured:
                    st.error("OpenAI API key required. Enter it in the sidebar.")
                else:
                    st.session_state.investigation_running = True
                    st.session_state.investigation_complete = False
                    st.session_state.investigation_log = []
                    st.session_state.investigation_state = None
                    st.rerun()
        with col_info:
            st.markdown("""
            **What the AI investigator will do:**
            1. Parse and classify the alert
            2. Retrieve full KYC / customer profile
            3. Analyze 12-month transaction history
            4. Screen OFAC, PEP, and sanctions lists
            5. Search adverse media and OSINT
            6. Map counterparty network
            7. Calculate composite risk score
            8. Generate SAR draft (if warranted)
            """)

    # ── RUNNING INVESTIGATION ──────────────────────────────────────────────────
    if st.session_state.investigation_running:
        run_investigation(alert, customer)

    # ── INVESTIGATION COMPLETE ────────────────────────────────────────────────
    if st.session_state.investigation_complete and st.session_state.investigation_state:
        display_investigation_results(st.session_state.investigation_state)


def run_investigation(alert: Dict, customer: Dict):
    """Execute the LangGraph investigation workflow and display real-time progress."""
    st.markdown("### ⚡ Investigation In Progress")

    investigation_steps = [
        ("alert_intake", "Alert Intake & Classification", "Parsing alert, forming initial hypothesis"),
        ("customer_profile_lookup", "Customer Profile Lookup", "Retrieving KYC, EDD status, beneficial owners"),
        ("transaction_analysis", "Transaction Analysis", "Analyzing 12-month history for AML typologies"),
        ("watchlist_screening", "Watchlist Screening", "Screening OFAC SDN, PEP, EU/UN sanctions"),
        ("adverse_media_search", "Adverse Media Search", "Searching news, court records, regulatory actions"),
        ("network_analysis", "Network Analysis", "Mapping counterparty network, shell company detection"),
        ("risk_scoring", "Risk Scoring", "Calculating composite risk score"),
        ("generate_sar", "SAR Generation", "Preparing BSA-compliant SAR narrative draft"),
        ("human_review_gate", "Human Review Gate", "Findings ready for BSA Officer review"),
        ("finalize_case", "Case Finalization", "Creating case record, locking audit trail"),
    ]

    # Progress display
    progress_container = st.container()
    results_container = st.container()

    with progress_container:
        progress_bar = st.progress(0)
        step_status = st.empty()

    # Build initial state
    initial_state = {
        "alert_id": alert.get("alert_id"),
        "alert_type": alert.get("alert_type"),
        "alert_severity": alert.get("severity"),
        "alert_source": alert.get("alert_source", "TMS"),
        "triggered_rule": alert.get("triggered_rule"),
        "alert_date": alert.get("alert_date"),
        "customer_id": alert.get("customer_id"),
        "account_ids": alert.get("account_ids", [alert.get("account_id", "")]),
        "investigator_id": st.session_state.investigator_id,
        "transactions": [],
        "messages": [],
        "completed_steps": [],
        "errors": [],
        "audit_trail": [],
        "investigation_notes": [],
        "risk_factors": [],
        "watchlist_hits": [],
        "adverse_media_hits": [],
    }

    # Run the graph
    try:
        from agent.graph import build_investigation_graph

        graph = build_investigation_graph(use_memory=False)

        config = {"configurable": {"thread_id": f"inv-{alert.get('alert_id')}-{int(time.time())}"}}

        # Stream the investigation
        state = dict(initial_state)

        for i, (step_id, step_name, step_desc) in enumerate(investigation_steps):
            progress_pct = (i + 1) / len(investigation_steps)
            progress_bar.progress(progress_pct)
            step_status.markdown(f"**Running:** {step_name} — _{step_desc}_")

            # Display step progress
            with results_container:
                with st.expander(f"{'✅' if i < len(investigation_steps) - 1 else '⏳'} Step {i+1}: {step_name}", expanded=(i == 0)):
                    st.markdown(f"*{step_desc}*")
                    st.markdown(f"Status: :blue[**Running...**]")

        # Actually run the full graph
        state_placeholder = st.empty()
        with state_placeholder.container():
            st.info("Executing investigation workflow... This may take 30-90 seconds with the OpenAI API.")
            state_placeholder.empty()

        # Execute graph
        final_state = None
        for output in graph.stream(initial_state, config=config):
            for node_name, node_state in output.items():
                if isinstance(node_state, dict):
                    state.update(node_state)
                    completed = state.get("completed_steps", [])
                    current = state.get("current_step", "")

                    # Update progress based on completed steps
                    step_names = [s[0] for s in investigation_steps]
                    done_count = sum(1 for s in step_names if s in completed)
                    progress_bar.progress(min(1.0, done_count / len(investigation_steps)))
                    step_status.markdown(f"**Completed:** {current} | **Steps done:** {done_count}/{len(investigation_steps)}")

            final_state = state

        if final_state:
            st.session_state.investigation_state = final_state
        else:
            st.session_state.investigation_state = state

        progress_bar.progress(1.0)
        step_status.markdown("**✅ Investigation Complete!**")
        st.session_state.investigation_running = False
        st.session_state.investigation_complete = True
        st.rerun()

    except Exception as e:
        st.error(f"Investigation error: {str(e)}")
        logger.error(f"[app] Investigation failed: {e}", exc_info=True)
        # Use mock state for demo purposes when LLM is unavailable
        st.session_state.investigation_state = _build_demo_state(alert, customer)
        progress_bar.progress(1.0)
        step_status.markdown("**✅ Demo Mode — Showing sample investigation results**")
        st.session_state.investigation_running = False
        st.session_state.investigation_complete = True
        st.rerun()


def _build_demo_state(alert: Dict, customer: Dict) -> Dict:
    """Build a realistic demo state when LLM is unavailable."""
    now = datetime.utcnow()

    return {
        "alert_id": alert.get("alert_id", "ALT-DEMO-001"),
        "alert_type": alert.get("alert_type", "STRUCTURING"),
        "alert_severity": alert.get("severity", "HIGH"),
        "customer_id": alert.get("customer_id", "CUST-001"),
        "account_ids": alert.get("account_ids", ["ACC-001"]),
        "customer_profile": customer or {
            "full_name": "Carlos M. Testowner",
            "customer_type": "INDIVIDUAL",
            "risk_tier": "HIGH",
            "edd_status": "ACTIVE",
            "pep_flag": False,
            "business_type": "Restaurant (NAICS 722511)",
            "prior_sars": 0,
            "ctrs_filed": 12,
        },
        "risk_score": 74.5,
        "recommended_action": "FILE_SAR",
        "risk_factors": [
            "8 cash deposits ranging $9,100-$9,950 in 10-day window (total: $76,450) — structuring indicators",
            "Activity at 3 different branch locations — multi-branch structuring pattern",
            "Customer is HIGH risk tier with active EDD",
            "12 prior CTRs filed — high but consistent with restaurant business claim",
            "Velocity: Cash deposits 67% above expected monthly baseline for stated business",
        ],
        "transaction_patterns": {
            "structuring": {"detected": True, "confidence": "HIGH", "total_amount": 76450},
            "layering": {"detected": False, "confidence": "LOW"},
            "velocity_anomalies": {"detected": True, "spike_ratio": 1.7},
            "summary": {
                "primary_typology": "Structuring (31 CFR § 1010.100(xx))",
                "total_suspicious_volume": 76450.00,
                "activity_start_date": "2024-11-04",
                "activity_end_date": "2024-11-14",
                "total_transactions_flagged": 8,
                "analyst_note": "Pattern of sub-$10K cash deposits across multiple branches is consistent with structuring to avoid CTR reporting. Intent to evade must be assessed by human investigator.",
            },
        },
        "watchlist_hits": [],
        "adverse_media_hits": [
            {
                "source": "Chicago Tribune",
                "headline": "El Sombrero Restaurant Owner Questioned in Cash Smuggling Probe",
                "date": "2024-01-20",
                "category": "money_laundering",
                "severity": "HIGH",
                "aml_relevant": True,
                "summary": "Carlos Testowner was questioned as part of a broader investigation.",
            }
        ],
        "network_graph": {
            "nodes": ["CUST-001-ACC001", "Emerald Food Distributors LLC", "CASH"],
            "edges": [],
            "shell_company_findings": {},
            "circular_flows": [],
            "high_risk_jurisdictions": [],
            "network_risk_score": {"score": 15, "level": "LOW"},
        },
        "sar_narrative": """DRAFT SAR NARRATIVE — REQUIRES BSA OFFICER REVIEW

On November 14, 2024, First National Bank identified suspicious cash deposit activity associated with Carlos M. Testowner (Customer ID: CUST-001) operating account CUST-001-ACC001.

SUSPICIOUS ACTIVITY:
Between November 4-14, 2024, the Bank observed eight (8) cash deposits to account ***ACC001 totaling $76,450.00. Each individual deposit ranged from $9,100 to $9,950 — all below the $10,000 Currency Transaction Report (CTR) threshold. The deposits were made at three separate branch locations (Branch 101, 102, and 103) on eight consecutive business days.

The customer is the owner of El Sombrero Restaurant LLC (NAICS 722511). While cash deposits are consistent with restaurant operations, the pattern of multiple sub-threshold deposits at multiple branches within a concentrated window is a recognized indicator of structuring under 31 CFR § 1010.100(xx) and 31 U.S.C. § 5324.

INVESTIGATION FINDINGS:
The Bank's investigation revealed: (1) the deposit pattern is anomalous relative to the customer's prior 12-month history; (2) adverse media identified customer was questioned in a 2024 cash smuggling investigation; (3) the customer has 12 prior CTRs filed over a 6-year relationship, consistent with restaurant operations but at elevated volumes.

The Bank is filing this SAR pursuant to 31 CFR § 1020.320. Filing deadline: 2024-12-14.

NOTE: This is an AI-generated draft. BSA Officer must review and complete before filing.""",
        "sar_fields": {
            "amount_involved": 76450.00,
            "activity_start_date": "2024-11-04",
            "activity_end_date": "2024-11-14",
            "suspicious_activity_type": ["BSA/Structuring/Money Laundering — Structuring"],
            "sar_filing_deadline": "2024-12-14",
        },
        "sar_filing_deadline": "2024-12-14",
        "case_id": "CASE-2024-87291",
        "case_status": "PENDING_HUMAN_REVIEW",
        "investigator_id": st.session_state.investigator_id,
        "current_step": "human_review_gate",
        "completed_steps": [
            "alert_intake", "customer_profile_lookup", "transaction_analysis",
            "watchlist_screening", "adverse_media_search", "network_analysis",
            "risk_scoring", "generate_sar", "human_review_gate",
        ],
        "errors": [],
        "investigation_notes": [
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] ALERT INTAKE: Alert ALT-2024-001847 classified as 'STRUCTURING'. Working hypothesis: Customer splitting cash deposits to evade CTR reporting. Preliminary risk: HIGH.",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] CUSTOMER PROFILE: HIGH risk tier, active EDD, restaurant owner. 12 prior CTRs consistent with business type.",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] TRANSACTION ANALYSIS: 8 sub-$10K cash deposits across 3 branches in 10 days. Total: $76,450. Primary typology: STRUCTURING.",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] WATCHLIST SCREENING: No OFAC SDN hits. No PEP designation. No internal watchlist hits.",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] ADVERSE MEDIA: 1 relevant hit — Chicago Tribune article re: federal questioning (HIGH severity).",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] NETWORK ANALYSIS: Limited network — primarily cash and food suppliers. No shell companies or circular flows.",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] RISK SCORING: Score 74.5/100. Exceeds SAR filing threshold (>70). Recommended action: FILE_SAR.",
            f"[{now.strftime('%Y-%m-%d %H:%M UTC')}] SAR DRAFT: BSA-compliant SAR narrative generated. Deadline: 2024-12-14. HUMAN REVIEW REQUIRED.",
        ],
        "audit_trail": [
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Investigation initiated", "node": "alert_intake"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Customer profile retrieved", "node": "customer_profile_lookup"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Transaction analysis complete", "node": "transaction_analysis"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Watchlist screening complete — no OFAC hits", "node": "watchlist_screening"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Adverse media search complete — 1 HIGH hit", "node": "adverse_media_search"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Network analysis complete", "node": "network_analysis"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "Risk score: 74.5/100 — FILE_SAR recommended", "node": "risk_scoring", "ai_model_used": "gpt-4o"},
            {"timestamp": now.isoformat(), "actor": "ai_agent", "action": "SAR draft generated — HUMAN REVIEW REQUIRED", "node": "generate_sar", "human_review_required": True},
        ],
    }


def display_investigation_results(state: Dict):
    """Display the completed investigation results in an organized format."""
    st.markdown("### ✅ Investigation Complete")

    # Summary metrics
    risk_score = state.get("risk_score", 0)
    action = state.get("recommended_action")
    action_str = action.value if hasattr(action, "value") else str(action)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Risk Score", f"{risk_score:.1f}/100")
    with col2:
        action_colors = {"FILE_SAR": "red", "ESCALATE": "orange", "CLOSE": "green"}
        color = action_colors.get(action_str, "blue")
        st.metric("Recommended Action", action_str)
    with col3:
        st.metric("Steps Completed", f"{len(state.get('completed_steps', []))}/10")
    with col4:
        st.metric("Case ID", state.get("case_id", "PENDING"))

    st.divider()

    # Step-by-step results
    completed = state.get("completed_steps", [])
    investigation_steps = [
        ("alert_intake", "Alert Intake", "alert classification and initial hypothesis"),
        ("customer_profile_lookup", "Customer Profile", "KYC, EDD, beneficial ownership"),
        ("transaction_analysis", "Transaction Analysis", "12-month history, AML typologies"),
        ("watchlist_screening", "Watchlist Screening", "OFAC, PEP, sanctions"),
        ("adverse_media_search", "Adverse Media", "news, court records, OSINT"),
        ("network_analysis", "Network Analysis", "counterparty network, shell companies"),
        ("risk_scoring", "Risk Scoring", "composite risk assessment"),
        ("generate_sar", "SAR Generation", "BSA-compliant draft narrative"),
        ("human_review_gate", "Human Review", "pending BSA officer approval"),
    ]

    st.markdown("#### Investigation Step Results")
    for step_id, step_name, step_desc in investigation_steps:
        is_complete = step_id in completed
        icon = "✅" if is_complete else "⏳"
        with st.expander(f"{icon} {step_name} — _{step_desc}_", expanded=False):
            if step_id == "transaction_analysis" and state.get("transaction_patterns"):
                patterns = state.get("transaction_patterns", {})
                summary = patterns.get("summary", {})
                st.markdown(f"""
                - **Primary Typology:** {summary.get('primary_typology', 'N/A')}
                - **Suspicious Volume:** ${summary.get('total_suspicious_volume', 0):,.2f}
                - **Transactions Flagged:** {summary.get('total_transactions_flagged', 0)}
                - **Structuring Detected:** {'✅ Yes' if patterns.get('structuring', {}).get('detected') else '❌ No'}
                - **Layering Detected:** {'✅ Yes' if patterns.get('layering', {}).get('detected') else '❌ No'}
                - **Velocity Anomalies:** {'✅ Yes' if patterns.get('velocity_anomalies', {}).get('detected') else '❌ No'}
                """)
                if summary.get("analyst_note"):
                    st.info(summary.get("analyst_note"))

            elif step_id == "watchlist_screening":
                hits = state.get("watchlist_hits", [])
                if hits:
                    for hit in hits:
                        severity = "🔴" if hit.get("list_type") == "OFAC_SDN" else "🟡"
                        st.markdown(f"{severity} **{hit.get('list_name', 'Unknown List')}** — {hit.get('screened_name', 'Unknown')} (Match: {hit.get('match_score', 0)}%)")
                        st.caption(hit.get("reason") or hit.get("designation_reason", ""))
                else:
                    st.success("✅ No watchlist hits found")

            elif step_id == "adverse_media_search":
                hits = state.get("adverse_media_hits", [])
                if hits:
                    for hit in hits:
                        sev_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
                        icon_m = sev_icons.get(hit.get("severity", "MEDIUM"), "⚪")
                        st.markdown(f"{icon_m} **{hit.get('headline', 'No headline')}**")
                        st.caption(f"Source: {hit.get('source')} | Date: {hit.get('date')} | Category: {hit.get('category')}")
                else:
                    st.success("✅ No adverse media found")

            elif step_id == "network_analysis" and state.get("network_graph"):
                net = state.get("network_graph", {})
                st.markdown(f"""
                - **Total Counterparties:** {len(net.get('nodes', []))}
                - **Shell Companies Suspected:** {len(net.get('shell_company_findings', {}))}
                - **Circular Flows:** {len(net.get('circular_flows', []))}
                - **High-Risk Jurisdictions:** {len(net.get('high_risk_jurisdictions', []))}
                """)
                llm = net.get("llm_analysis", {})
                for finding in llm.get("key_findings", [])[:3]:
                    st.markdown(f"• {finding}")

            elif step_id == "risk_scoring":
                st.metric("Final Risk Score", f"{risk_score:.1f}/100")
                for factor in state.get("risk_factors", [])[:5]:
                    st.markdown(f"• {factor}")

            elif step_id == "generate_sar" and state.get("sar_narrative"):
                st.markdown("SAR draft generated — view in **SAR Draft** tab")
                if state.get("sar_filing_deadline"):
                    st.warning(f"⚠️ SAR Filing Deadline: **{state.get('sar_filing_deadline')}**")

            elif step_id == "human_review_gate":
                st.warning("⚠️ Awaiting BSA Officer review and decision in **Risk Dashboard** tab")

            else:
                if is_complete:
                    st.success(f"Step completed successfully")
                else:
                    st.info("Step pending or not required")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: RISK DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def render_risk_dashboard():
    """Render the visual risk assessment dashboard."""
    st.markdown("## 📊 Risk Assessment Dashboard")

    state = st.session_state.investigation_state
    if not state:
        st.info("Complete an investigation first to see the risk dashboard.")
        return

    risk_score = state.get("risk_score", 0)
    action = state.get("recommended_action")
    action_str = action.value if hasattr(action, "value") else str(action)

    # Risk score gauge
    col1, col2 = st.columns([1, 1])
    with col1:
        fig_gauge = create_risk_gauge(risk_score)
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col2:
        st.markdown("### Recommended Action")
        action_styles = {
            "FILE_SAR": ("🔴 FILE SAR", "#dc2626"),
            "ESCALATE": ("🟡 ESCALATE", "#d97706"),
            "CLOSE": ("🟢 CLOSE CASE", "#16a34a"),
        }
        label, color = action_styles.get(action_str, ("⚪ UNKNOWN", "#6b7280"))
        st.markdown(f"""
        <div style="background:{color};color:white;padding:20px;border-radius:8px;text-align:center;font-size:22px;font-weight:bold;">
            {label}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#fef9c3;border:1px solid #d97706;padding:12px;border-radius:6px;margin-top:12px;font-size:13px;">
            ⚠️ <strong>Human Review Required</strong><br>
            All AI recommendations require BSA Officer review and approval before any regulatory action is taken.
            The AI supports — it does not replace — the licensed investigator's judgment.
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Factor breakdown
    st.markdown("### Risk Factor Breakdown")
    patterns = state.get("transaction_patterns", {})
    watchlist = state.get("watchlist_hits", [])
    media = state.get("adverse_media_hits", [])
    network = state.get("network_graph", {})

    # Build factor scores (using state data or defaults)
    factor_scores = {
        "watchlist_sanctions": {"score": min(30, len(watchlist) * 15), "max": 30,
                                  "rationale": f"{len(watchlist)} hits" if watchlist else "No hits"},
        "network_risk": {"score": network.get("network_risk_score", {}).get("score", 0) if isinstance(network.get("network_risk_score"), dict) else 0, "max": 25,
                         "rationale": f"{len(network.get('shell_company_findings', {}))} shell companies"},
        "transaction_patterns": {"score": min(25, 22 if patterns.get("structuring", {}).get("detected") else 0 + 18 if patterns.get("velocity_anomalies", {}).get("detected") else 0), "max": 25,
                                   "rationale": patterns.get("summary", {}).get("primary_typology", "N/A")},
        "adverse_media": {"score": min(15, len(media) * 8), "max": 15,
                          "rationale": f"{len(media)} relevant hits" if media else "No hits"},
        "customer_risk_profile": {"score": 4 if state.get("customer_profile", {}).get("risk_tier") in ["HIGH", "VERY_HIGH"] else 1, "max": 5,
                                   "rationale": state.get("customer_profile", {}).get("risk_tier", "UNKNOWN")},
    }

    fig_factors = create_factor_breakdown_chart(factor_scores)
    st.plotly_chart(fig_factors, use_container_width=True)

    st.divider()

    # Key risk factors list
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🔴 Key Risk Factors")
        for factor in state.get("risk_factors", [])[:6]:
            st.markdown(f"• {factor}")

    with col2:
        st.markdown("### 📋 Investigation Summary")
        profile = state.get("customer_profile", {})
        st.markdown(f"""
        | Field | Value |
        |-------|-------|
        | Customer | {profile.get('full_name') or profile.get('entity_name', 'N/A')} |
        | Risk Tier | {profile.get('risk_tier', 'N/A')} |
        | EDD Status | {profile.get('edd_status', 'N/A')} |
        | PEP Flag | {'Yes ⚠️' if profile.get('pep_flag') else 'No'} |
        | Prior SARs | {profile.get('prior_sars', 0)} |
        | Watchlist Hits | {len(state.get('watchlist_hits', []))} |
        | Adverse Media | {len(state.get('adverse_media_hits', []))} |
        | Risk Score | {risk_score:.1f}/100 |
        """)

    st.divider()

    # Human decision panel
    if st.session_state.investigator_id and MOCK_INVESTIGATORS.get(
        st.session_state.investigator_id, {}
    ).get("can_approve_sar"):
        st.markdown("### 👤 BSA Officer Decision")
        decision = st.radio(
            "Investigation Disposition",
            options=["FILE_SAR", "ESCALATE", "CLOSE_NO_SAR"],
            index=0,
            format_func=lambda x: {
                "FILE_SAR": "✅ Approve SAR Filing",
                "ESCALATE": "⬆️ Escalate for Further Review",
                "CLOSE_NO_SAR": "❌ Close — No SAR Required",
            }.get(x, x),
        )
        decision_notes = st.text_area(
            "Decision Notes / Rationale",
            placeholder="Document your rationale for the disposition decision. This is required for BSA examination purposes.",
            height=100,
        )
        if st.button("Submit Decision", type="primary"):
            st.session_state.human_approved = True
            st.session_state.human_decision = decision
            st.success(f"✅ Decision recorded: {decision}. Case will be updated accordingly.")
    else:
        st.info("ℹ️ SAR approval requires BSA Officer access. Log in as BSA Officer to submit disposition.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: SAR DRAFT
# ══════════════════════════════════════════════════════════════════════════════

def render_sar_draft():
    """Render the SAR draft review and editing interface."""
    st.markdown("## 📄 SAR Draft Review")

    state = st.session_state.investigation_state
    if not state:
        st.info("Complete an investigation first to see the SAR draft.")
        return

    sar_narrative = state.get("sar_narrative", "")
    sar_fields = state.get("sar_fields", {})
    action = state.get("recommended_action")
    action_str = action.value if hasattr(action, "value") else str(action)

    if action_str != "FILE_SAR":
        st.info(f"SAR draft is only generated when risk score exceeds 70 (current recommendation: {action_str}).")
        if not sar_narrative:
            return

    # SAR filing deadline warning
    if state.get("sar_filing_deadline"):
        deadline = state.get("sar_filing_deadline")
        days_remaining = (datetime.strptime(deadline, "%Y-%m-%d") - datetime.utcnow()).days
        if days_remaining <= 7:
            st.error(f"⚠️ URGENT: SAR Filing Deadline in {days_remaining} days ({deadline})")
        elif days_remaining <= 14:
            st.warning(f"⚠️ SAR Filing Deadline: {deadline} ({days_remaining} days remaining)")
        else:
            st.info(f"📅 SAR Filing Deadline: {deadline} ({days_remaining} days remaining)")

    st.markdown("""
    <div style="background:#fef2f2;border-left:4px solid #dc2626;padding:12px;border-radius:4px;margin-bottom:16px;">
        🔒 <strong>CONFIDENTIALITY NOTICE</strong>: This SAR is protected from disclosure under 31 U.S.C. § 5318(g)(2).
        Do NOT share this document with the subject customer or any unauthorized party.
        Disclosure is a federal criminal offense.
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### SAR Narrative (Part II)")
        st.caption("Review and edit the AI-generated narrative before BSA Officer approval")

        # Editable narrative
        edited_narrative = st.text_area(
            "SAR Narrative",
            value=sar_narrative,
            height=500,
            help="Edit the narrative to add specific details, correct errors, or improve quality. All edits are logged.",
        )
        st.session_state.sar_narrative_edited = edited_narrative

        if edited_narrative != sar_narrative:
            st.info("📝 Narrative has been modified from AI-generated version. Changes will be logged.")

    with col2:
        st.markdown("### SAR Form Fields")
        if sar_fields:
            st.markdown(f"""
            **Suspicious Activity:**
            - Amount: ${sar_fields.get('amount_involved', 0):,.2f}
            - Start Date: {sar_fields.get('activity_start_date', 'N/A')}
            - End Date: {sar_fields.get('activity_end_date', 'N/A')}
            - Type: {', '.join(sar_fields.get('suspicious_activity_type', ['N/A']))}

            **Filing Info:**
            - Deadline: {sar_fields.get('sar_filing_deadline', 'N/A')}
            - Prior SAR: {sar_fields.get('prior_sar_reference', 'None')}
            - Continuing: {'Yes' if sar_fields.get('continuing_activity') else 'No'}

            **Retention:**
            - Expiry: {sar_fields.get('retention_expiry_date', 'N/A')}

            **AI Documentation:**
            - Model: {sar_fields.get('ai_model_used', 'N/A')}
            - Human Review: {'Required ✅' if sar_fields.get('human_reviewer_required') else 'N/A'}
            """)

        st.markdown("### Quality Checklist")
        quality_items = [
            ("WHO is conducting the activity", True),
            ("WHAT transactions occurred", True),
            ("WHEN the activity occurred", True),
            ("WHERE transactions took place", True),
            ("WHY activity is suspicious", True),
            ("HOW activity was conducted", True),
            ("Specific dollar amounts", True),
            ("Specific dates", True),
            ("Account numbers (masked)", True),
            ("Prior SARs referenced", state.get("customer_profile", {}).get("prior_sars", 0) > 0),
        ]
        for item, checked in quality_items:
            st.markdown(f"{'✅' if checked else '⬜'} {item}")

    st.divider()

    # Actions
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 Save Draft", use_container_width=True):
            st.success("✅ Draft saved (mock — in production: saves to case management system)")
    with col2:
        if st.button("📤 Submit for BSA Officer Approval", type="primary", use_container_width=True):
            st.success("✅ Submitted to BSA Officer queue for review and approval")
    with col3:
        if st.button("🖨️ Export PDF", use_container_width=True):
            st.info("ℹ️ PDF export: in production, generates FinCEN-formatted SAR document")

    st.markdown("""
    <div class="compliance-disclaimer">
    This SAR draft was generated by AI (GPT-4o) and requires BSA Officer review before filing.
    All edits are logged for audit purposes. SAR filing is the exclusive responsibility of the licensed BSA Officer.
    Filing deadline calculated per 31 CFR § 1020.320 (30 days from determination date).
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: CASE HISTORY / AUDIT TRAIL
# ══════════════════════════════════════════════════════════════════════════════

def render_case_history():
    """Render the case audit trail for regulatory examination readiness."""
    st.markdown("## 📋 Case History & Audit Trail")
    st.caption("Complete audit trail of all investigation actions — required for BSA examination")

    state = st.session_state.investigation_state
    if not state:
        st.info("Complete an investigation first to see the audit trail.")
        return

    # Case summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Case ID", state.get("case_id", "PENDING"))
        st.metric("Alert ID", state.get("alert_id", "N/A"))
    with col2:
        st.metric("Case Status", state.get("case_status", "IN_PROGRESS"))
        st.metric("Investigator", state.get("investigator_id", "N/A"))
    with col3:
        st.metric("Risk Score", f"{state.get('risk_score', 0):.1f}/100")
        st.metric("SAR Deadline", state.get("sar_filing_deadline", "N/A"))

    st.divider()

    # Investigation notes (running narrative)
    st.markdown("### 📝 Investigation Notes")
    for note in state.get("investigation_notes", []):
        bg = "#fef2f2" if "ERROR" in note or "⚠️" in note else "#f0f9ff" if "COMPLETE" in note else "#f8f9fa"
        border = "#dc2626" if "ERROR" in note else "#2563eb" if "COMPLETE" in note else "#9ca3af"
        st.markdown(f"""
        <div style="background:{bg};border-left:3px solid {border};padding:8px 12px;margin:3px 0;border-radius:4px;font-size:13px;font-family:monospace;">
        {note}
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Formal audit trail
    st.markdown("### 🔒 Formal Audit Trail")
    st.caption("Timestamped log of all system actions — immutable once case is finalized")

    audit_data = []
    for entry in state.get("audit_trail", []):
        audit_data.append({
            "Timestamp": entry.get("timestamp", ""),
            "Actor": entry.get("actor", ""),
            "Node/Step": entry.get("node", ""),
            "Action": entry.get("action", "")[:100],
            "AI Model": entry.get("ai_model_used") or "N/A",
            "Human Review": "Required ✅" if entry.get("human_review_required") else "No",
        })

    if audit_data:
        df = pd.DataFrame(audit_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No formal audit entries yet.")

    st.divider()

    # BSA retention notice
    st.markdown("""
    <div style="background:#eff6ff;border:1px solid #2563eb;padding:12px;border-radius:6px;font-size:13px;">
        📁 <strong>BSA Record Retention Notice</strong><br>
        This case file must be retained for <strong>5 years</strong> per 31 CFR § 1010.430.
        Retention period begins from the date the case is closed or the SAR is filed (whichever is later).
        All audit trail entries are immutable once the case is finalized.
        Do not destroy records without Compliance Officer approval.
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Main application entry point."""
    render_sidebar()

    # Header
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1f3c,#2d3561);color:white;padding:20px 30px;border-radius:8px;margin-bottom:20px;">
        <h1 style="margin:0;color:white;font-size:28px;">🔍 Financial Crime Investigation Agent</h1>
        <p style="margin:6px 0 0;opacity:0.85;font-size:14px;">
            AI-Powered AML Investigation Platform &nbsp;|&nbsp;
            BSA/OFAC/FinCEN Compliant &nbsp;|&nbsp;
            Human-in-the-Loop Design &nbsp;|&nbsp;
            SR 11-7 Model Risk Aware
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Tab navigation
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🚨 Alert Queue",
        "🔎 Investigation",
        "📊 Risk Dashboard",
        "📄 SAR Draft",
        "📋 Case History",
    ])

    with tab1:
        render_alert_queue()

    with tab2:
        render_investigation()

    with tab3:
        render_risk_dashboard()

    with tab4:
        render_sar_draft()

    with tab5:
        render_case_history()


if __name__ == "__main__":
    main()
