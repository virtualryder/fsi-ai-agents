# app.py — Credit Underwriting Agent Dashboard
# Port: 8508
# ============================================================
# 6-tab Streamlit interface for the credit underwriting workflow.
#
# Tabs:
#   1. Application Queue    — submit, pipeline status, loan register
#   2. Underwriting Analysis — financial ratios, credit profile, risk score
#   3. Fair Lending Review  — ECOA/FHA flags, HMDA, CRA, compliance notes
#   4. Credit Decision      — memo, conditions letter, adverse action notice
#   5. Loan Register        — all applications with status and HMDA tracking
#   6. Configuration        — guidelines, delegation of authority, model weights
#
# Security:
#   - SSN and raw credit data are never displayed; only masked metrics.
#   - Reviewer ID is required before decision submission.
#   - Pricing override is flagged for fair lending monitoring.
#   - All sensitive state keys excluded from raw state display.
# ============================================================
import json
import os
import uuid
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Credit Underwriting Agent",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
}
.approve-badge {
    background: #dcfce7; color: #166534;
    padding: 4px 12px; border-radius: 4px; font-weight: 600;
}
.conditions-badge {
    background: #fef9c3; color: #854d0e;
    padding: 4px 12px; border-radius: 4px; font-weight: 600;
}
.committee-badge {
    background: #dbeafe; color: #1e40af;
    padding: 4px 12px; border-radius: 4px; font-weight: 600;
}
.decline-badge {
    background: #fee2e2; color: #991b1b;
    padding: 4px 12px; border-radius: 4px; font-weight: 600;
}
.fair-lending-warning {
    background: #fef3c7;
    border: 2px solid #f59e0b;
    border-radius: 8px;
    padding: 16px;
    margin: 12px 0;
}
.adverse-action-box {
    background: #fef2f2;
    border: 2px solid #dc2626;
    border-radius: 8px;
    padding: 16px;
    margin: 12px 0;
}
.ofac-alert {
    background: #450a0a;
    color: #fef2f2;
    border-radius: 8px;
    padding: 16px;
    margin: 12px 0;
    font-weight: bold;
}
.sr117-note {
    background: #eff6ff;
    border-left: 4px solid #3b82f6;
    padding: 12px;
    margin: 8px 0;
    font-size: 0.85rem;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "graph" not in st.session_state:
    from agent.graph import build_underwriting_graph
    from langgraph.checkpoint.memory import MemorySaver
    st.session_state.graph = build_underwriting_graph(checkpointer=MemorySaver())

if "loan_register" not in st.session_state:
    st.session_state.loan_register = []

if "active_thread" not in st.session_state:
    st.session_state.active_thread = None

if "thread_configs" not in st.session_state:
    st.session_state.thread_configs = {}

graph = st.session_state.graph

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏦 Credit Underwriting")
    st.caption("AI-powered loan origination | Port 8508")
    st.divider()

    if st.session_state.active_thread:
        config = st.session_state.thread_configs.get(st.session_state.active_thread, {})
        try:
            snap = graph.get_state(config)
            vals = snap.values
            app_id = vals.get("application_id", "Unknown")
            risk_tier = vals.get("risk_tier", "—")
            score = vals.get("composite_score", 0)
            decision = vals.get("final_decision", "PENDING")
            needs_hitl = snap.next == ("human_review_gate",)

            st.subheader("Active Application")
            st.write(f"**ID:** {app_id}")
            st.write(f"**Score:** {score:.3f}")

            tier_colors = {
                "APPROVE": "🟢", "APPROVE_WITH_CONDITIONS": "🟡",
                "REFER_TO_COMMITTEE": "🔵", "DECLINE": "🔴",
            }
            st.write(f"**Tier:** {tier_colors.get(risk_tier, '⚪')} {risk_tier}")

            if needs_hitl:
                st.warning("⏸ Awaiting underwriter review")
            elif decision != "PENDING":
                st.success(f"✅ Decision: {decision}")
        except Exception:
            pass

    st.divider()
    st.caption("**Regulatory Coverage**")
    st.caption("ECOA / Reg B / Reg Z")
    st.caption("HMDA / CRA / Fair Housing")
    st.caption("BSA CIP / OFAC / SR 11-7")
    st.caption("SBA SOP 50 10 7 / HUD 4000.1")

# ── Load fixtures ─────────────────────────────────────────────────────────────
@st.cache_data
def load_sample_applications():
    p = os.path.join(os.path.dirname(__file__), "data", "fixtures", "sample_applications.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return []

@st.cache_data
def load_guidelines():
    p = os.path.join(os.path.dirname(__file__), "data", "fixtures", "underwriting_guidelines.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}

@st.cache_data
def load_routing_matrix():
    p = os.path.join(os.path.dirname(__file__), "data", "fixtures", "routing_matrix.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}

# ── Helpers ───────────────────────────────────────────────────────────────────
def mask_name(name: str) -> str:
    """Partial mask for display — show first name, mask last."""
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1][0]}***"
    return name[:3] + "***"

def badge(tier: str) -> str:
    classes = {
        "APPROVE": "approve-badge",
        "APPROVE_WITH_CONDITIONS": "conditions-badge",
        "REFER_TO_COMMITTEE": "committee-badge",
        "DECLINE": "decline-badge",
    }
    return f'<span class="{classes.get(tier, "committee-badge")}">{tier}</span>'

def run_pipeline(state: dict, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    st.session_state.thread_configs[thread_id] = config
    for event in graph.stream(state, config):
        pass
    return graph.get_state(config).values

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Application Queue",
    "📊 Underwriting Analysis",
    "⚖️ Fair Lending Review",
    "📄 Credit Decision",
    "🗃️ Loan Register",
    "⚙️ Configuration",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — APPLICATION QUEUE
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Application Queue")

    col_new, col_demo = st.columns([2, 1])
    with col_new:
        st.subheader("New Application")
    with col_demo:
        st.subheader("Demo Scenarios")
        samples = load_sample_applications()
        if samples:
            scenario_labels = [s.get("_scenario", f"Scenario {i+1}") for i, s in enumerate(samples)]
            selected_idx = st.selectbox("Load scenario", range(len(scenario_labels)),
                                        format_func=lambda i: scenario_labels[i], key="scenario_select")
            load_demo = st.button("Load Scenario", use_container_width=True)

    with st.form("application_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            loan_type = st.selectbox("Loan Type", [
                "CONVENTIONAL_MORTGAGE", "FHA_MORTGAGE", "VA_MORTGAGE", "JUMBO_MORTGAGE",
                "HELOC", "COMMERCIAL_REAL_ESTATE", "COMMERCIAL_TERM_LOAN",
                "SBA_7A", "SBA_504", "CONSUMER_PERSONAL", "AUTO", "CREDIT_CARD_LINE",
            ])
            loan_purpose = st.selectbox("Loan Purpose", [
                "PURCHASE", "REFINANCE", "CASH_OUT", "ACQUISITION",
                "WORKING_CAPITAL", "EQUIPMENT_PURCHASE", "DEBT_CONSOLIDATION",
            ])
            applicant_name = st.text_input("Applicant Name", value="")
            applicant_type = st.selectbox("Applicant Type", ["INDIVIDUAL", "BUSINESS", "TRUST"])

        with col2:
            requested_amount = st.number_input("Requested Amount ($)", min_value=1000, max_value=50_000_000, value=400_000, step=5000)
            requested_term = st.number_input("Term (months)", min_value=12, max_value=480, value=360)
            quoted_rate = st.number_input("Interest Rate (%)", min_value=0.5, max_value=30.0, value=7.00, step=0.125) / 100
            annual_income = st.number_input("Annual Income ($)", min_value=0, value=120_000, step=5000)

        with col3:
            monthly_debt = st.number_input("Monthly Debt Obligations ($)", min_value=0, value=1000, step=100)
            credit_score = st.number_input("Credit Score (FICO)", min_value=300, max_value=850, value=720)
            appraised_value = st.number_input("Appraised Value ($)", min_value=0, value=500_000, step=5000)
            collateral_type = st.selectbox("Collateral Type", [
                "PRIMARY_RESIDENCE", "INVESTMENT_PROPERTY", "COMMERCIAL_REAL_ESTATE",
                "EQUIPMENT", "INVENTORY", "ACCOUNTS_RECEIVABLE",
                "SBA_GUARANTEE", "VEHICLE", "UNSECURED",
            ])

        col4, col5 = st.columns(2)
        with col4:
            property_state = st.text_input("Property State (2-letter)", value="MA", max_chars=2)
            property_census_tract = st.text_input("Census Tract (optional)", value="")
            noi = st.number_input("Net Operating Income — Commercial ($)", min_value=0, value=0, step=5000)

        with col5:
            liquid_assets = st.number_input("Liquid Assets / Reserves ($)", min_value=0, value=30_000, step=1000)
            ofac_hit = st.checkbox("OFAC Match (test only)", value=False)
            bankruptcy_flag = st.checkbox("Bankruptcy Flag", value=False)
            bankruptcy_chapter = st.selectbox("Bankruptcy Chapter", ["CHAPTER_7", "CHAPTER_13"]) if bankruptcy_flag else None
            bankruptcy_discharge_years = st.number_input("Years Since Discharge", 0.0, 20.0, 3.0, 0.5) if bankruptcy_flag else 10.0

        st.write("**Documents Received:**")
        doc_cols = st.columns(4)
        all_docs = [
            "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR", "BANK_STATEMENTS_3MO",
            "BANK_STATEMENTS_6MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT", "CREDIT_AUTHORIZATION",
            "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR", "BUSINESS_FINANCIALS_3YR",
            "RENT_ROLLS", "ENVIRONMENTAL_REPORT", "ENTITY_DOCUMENTS", "SBA_FORMS_1919_1920",
            "BUSINESS_PLAN", "COLLATERAL_DOCUMENTATION", "CERTIFICATE_OF_ELIGIBILITY", "DD214_OR_COE",
        ]
        docs_selected = []
        for i, doc in enumerate(all_docs):
            col = doc_cols[i % 4]
            if col.checkbox(doc, value=(doc in ["GOVERNMENT_ID", "CREDIT_AUTHORIZATION"]), key=f"doc_{doc}"):
                docs_selected.append(doc)

        submitted = st.form_submit_button("Submit Application", type="primary", use_container_width=True)

    if load_demo and samples:
        demo = samples[selected_idx].copy()
        st.session_state.demo_state = demo
        st.info(f"Loaded: {samples[selected_idx].get('_description', '')}")

    if submitted and applicant_name:
        thread_id = str(uuid.uuid4())
        state = {
            "application_id": f"APP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}",
            "applicant_id": f"CUST-{uuid.uuid4().hex[:6].upper()}",
            "applicant_name": applicant_name,
            "applicant_type": applicant_type,
            "loan_type": loan_type,
            "loan_purpose": loan_purpose,
            "application_source": "ONLINE",
            "requested_amount": float(requested_amount),
            "requested_term": int(requested_term),
            "quoted_rate": float(quoted_rate),
            "collateral_type": collateral_type,
            "appraised_value": float(appraised_value) if appraised_value else None,
            "annual_income": float(annual_income),
            "income_source": "W2",
            "monthly_debt_obligations": float(monthly_debt),
            "credit_score": int(credit_score),
            "credit_score_model": "FICO_8",
            "derogatory_marks": 0,
            "bankruptcy_flag": bankruptcy_flag,
            "bankruptcy_chapter": bankruptcy_chapter,
            "bankruptcy_discharge_years": float(bankruptcy_discharge_years),
            "foreclosure_flag": False,
            "collections_count": 0,
            "collections_balance": 0.0,
            "thin_file_flag": False,
            "recent_inquiries_90d": 0,
            "ofac_hit": ofac_hit,
            "net_operating_income": float(noi) if noi else None,
            "liquid_assets": float(liquid_assets),
            "property_state": property_state.upper() if property_state else None,
            "property_census_tract": property_census_tract or None,
            "documents_received": docs_selected,
            "document_exceptions": [],
            "fair_lending_flags": [],
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        }

        with st.spinner("Running underwriting pipeline..."):
            try:
                config = {"configurable": {"thread_id": thread_id}}
                st.session_state.thread_configs[thread_id] = config
                for event in graph.stream(state, config):
                    pass
                snap = graph.get_state(config)
                vals = snap.values
                st.session_state.active_thread = thread_id

                # Register
                st.session_state.loan_register.append({
                    "thread_id": thread_id,
                    "application_id": vals.get("application_id"),
                    "applicant": mask_name(applicant_name),
                    "loan_type": loan_type,
                    "amount": requested_amount,
                    "risk_tier": vals.get("risk_tier", "—"),
                    "composite_score": vals.get("composite_score", 0),
                    "final_decision": vals.get("final_decision", "PENDING"),
                    "hmda_reportable": vals.get("hmda_reportable", False),
                    "fair_lending_flag": bool(vals.get("fair_lending_flags")),
                    "awaiting_review": snap.next == ("human_review_gate",),
                    "submitted_at": datetime.now().isoformat()[:16],
                })

                if snap.next == ("human_review_gate",):
                    st.warning(f"⏸ Application {vals.get('application_id')} requires underwriter review. See **Underwriting Analysis** tab.")
                else:
                    tier = vals.get("risk_tier", "")
                    st.markdown(f"Application processed — tier: {badge(tier)}", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Pipeline error: {e}")

    if hasattr(st.session_state, "demo_state") and st.button("Run Demo Scenario", type="primary"):
        demo = st.session_state.demo_state.copy()
        demo["audit_trail"] = []
        demo["completed_steps"] = []
        demo["errors"] = []
        thread_id = str(uuid.uuid4())
        with st.spinner("Running demo pipeline..."):
            try:
                config = {"configurable": {"thread_id": thread_id}}
                st.session_state.thread_configs[thread_id] = config
                for event in graph.stream(demo, config):
                    pass
                snap = graph.get_state(config)
                vals = snap.values
                st.session_state.active_thread = thread_id
                st.session_state.loan_register.append({
                    "thread_id": thread_id,
                    "application_id": vals.get("application_id"),
                    "applicant": mask_name(demo.get("applicant_name", "Demo")),
                    "loan_type": demo.get("loan_type"),
                    "amount": demo.get("requested_amount"),
                    "risk_tier": vals.get("risk_tier", "—"),
                    "composite_score": vals.get("composite_score", 0),
                    "final_decision": vals.get("final_decision", "PENDING"),
                    "hmda_reportable": vals.get("hmda_reportable", False),
                    "fair_lending_flag": bool(vals.get("fair_lending_flags")),
                    "awaiting_review": snap.next == ("human_review_gate",),
                    "submitted_at": datetime.now().isoformat()[:16],
                })
                if snap.next == ("human_review_gate",):
                    st.warning("⏸ Application requires underwriter review — see Analysis tab.")
                else:
                    st.success(f"Demo complete. Decision: {vals.get('final_decision', 'PENDING')}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Queue summary
    if st.session_state.loan_register:
        st.divider()
        st.subheader("Application Pipeline")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        total = len(st.session_state.loan_register)
        awaiting = sum(1 for r in st.session_state.loan_register if r.get("awaiting_review"))
        approved = sum(1 for r in st.session_state.loan_register if "APPROV" in (r.get("final_decision") or ""))
        declined = sum(1 for r in st.session_state.loan_register if r.get("final_decision") == "DECLINED")
        col_m1.metric("Total Applications", total)
        col_m2.metric("Awaiting Review", awaiting)
        col_m3.metric("Approved / Conditional", approved)
        col_m4.metric("Declined", declined)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — UNDERWRITING ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Underwriting Analysis")

    # Thread selector
    if st.session_state.loan_register:
        options = {r["application_id"]: r["thread_id"] for r in st.session_state.loan_register}
        selected_app = st.selectbox("Select Application", list(options.keys()), key="analysis_select")
        selected_thread = options[selected_app]
    else:
        st.info("No applications yet. Submit one in the Application Queue tab.")
        st.stop()

    config = st.session_state.thread_configs.get(selected_thread, {})
    try:
        snap = graph.get_state(config)
        vals = snap.values
    except Exception as e:
        st.error(f"Could not load application: {e}")
        st.stop()

    needs_hitl = snap.next == ("human_review_gate",)

    # OFAC alert
    if vals.get("ofac_hit"):
        st.markdown('<div class="ofac-alert">🚨 OFAC MATCH DETECTED — BSA Officer Review Required — Application Blocked</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Financial Ratios")
        total_dti = vals.get("total_dti_ratio", 0)
        front_dti = vals.get("front_end_dti", 0)
        ltv = vals.get("ltv_ratio", 0)
        dscr = vals.get("dscr")

        dti_color = "normal" if total_dti <= 0.43 else "inverse"
        ltv_color = "normal" if ltv <= 0.80 else "inverse"

        m1, m2 = st.columns(2)
        m1.metric("Front-End DTI", f"{front_dti:.1%}")
        m2.metric("Total DTI", f"{total_dti:.1%}", delta=f"{'✓ Within policy' if total_dti <= 0.43 else '✗ Exceeds 43% guideline'}")
        m3, m4 = st.columns(2)
        m3.metric("LTV Ratio", f"{ltv:.1%}", delta=f"{'✓' if ltv <= 0.80 else '⚠ PMI required'}")
        if dscr:
            m4.metric("DSCR", f"{dscr:.2f}x", delta=f"{'✓ ≥1.25' if dscr >= 1.25 else '✗ Below 1.25 minimum'}")
        else:
            m4.metric("DSCR", "N/A (consumer)")

        res_months = vals.get("reserves_months", 0)
        m5, m6 = st.columns(2)
        m5.metric("Reserves (months)", f"{res_months:.1f}")
        m6.metric("Cash Flow Adequate", "Yes" if vals.get("cash_flow_adequate") else "No")

    with col_b:
        st.subheader("Credit Profile")
        credit_score = vals.get("credit_score", 0)
        st.metric("FICO Score", credit_score, delta=f"Model: {vals.get('credit_score_model', 'FICO_8')}")

        # Score gauge
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=credit_score,
            domain={"x": [0, 1], "y": [0, 1]},
            gauge={
                "axis": {"range": [300, 850]},
                "bar": {"color": "#3b82f6"},
                "steps": [
                    {"range": [300, 580], "color": "#fca5a5"},
                    {"range": [580, 670], "color": "#fde68a"},
                    {"range": [670, 740], "color": "#86efac"},
                    {"range": [740, 850], "color": "#4ade80"},
                ],
                "threshold": {"line": {"color": "red", "width": 4}, "value": 580},
            },
            title={"text": "FICO Score"},
        ))
        fig.update_layout(height=200, margin=dict(l=20, r=20, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

        col_c1, col_c2 = st.columns(2)
        col_c1.metric("Derogatory Marks", vals.get("derogatory_marks", 0))
        col_c2.metric("Collections", f"{vals.get('collections_count', 0)} (${vals.get('collections_balance', 0):,.0f})")
        col_c3, col_c4 = st.columns(2)
        col_c3.metric("Bankruptcy", "Yes" if vals.get("bankruptcy_flag") else "No")
        col_c4.metric("Recent Inquiries (90d)", vals.get("recent_inquiries_90d", 0))

    # Risk Score Breakdown
    st.divider()
    st.subheader("Risk Score — SR 11-7 Documentation")
    st.markdown('<div class="sr117-note">Model: credit-underwriting-composite-v1.0 | Governance: SR 11-7 | Owner: Chief Credit Officer | Weights fixed in code — changes require re-deployment and CCO approval.</div>', unsafe_allow_html=True)

    score_data = {
        "Factor": ["Credit Score (30%)", "DTI (25%)", "LTV (20%)", "Cash Flow (15%)", "Collateral (10%)"],
        "Score": [
            vals.get("credit_score_factor", 0),
            vals.get("dti_factor", 0),
            vals.get("ltv_factor", 0),
            vals.get("cash_flow_factor", 0),
            vals.get("collateral_factor", 0),
        ],
        "Weight": [0.30, 0.25, 0.20, 0.15, 0.10],
    }
    weighted = [s * w for s, w in zip(score_data["Score"], score_data["Weight"])]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        name="Factor Score",
        x=score_data["Factor"],
        y=score_data["Score"],
        marker_color="#3b82f6",
    ))
    fig2.add_trace(go.Bar(
        name="Weighted Contribution",
        x=score_data["Factor"],
        y=weighted,
        marker_color="#10b981",
    ))
    fig2.update_layout(
        barmode="group",
        yaxis=dict(range=[0, 1.1], title="Score (0–1)"),
        legend=dict(orientation="h"),
        height=320,
        margin=dict(l=20, r=20, t=20, b=10),
    )
    st.plotly_chart(fig2, use_container_width=True)

    composite = vals.get("composite_score", 0)
    risk_tier = vals.get("risk_tier", "—")
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("Composite Score", f"{composite:.3f}")
    col_s2.metric("Risk Tier", risk_tier)
    col_s3.metric("Hard Decline", "Yes" if vals.get("hard_decline_triggered") else "No")

    if vals.get("hard_decline_triggered"):
        st.error(f"⛔ Hard Decline: {vals.get('hard_decline_reason')}")

    # HITL Review Panel
    if needs_hitl:
        st.divider()
        st.subheader("Underwriter Review")
        assigned = vals.get("assigned_underwriter", "UNDERWRITER")
        st.info(f"Assigned to: **{assigned}** | Escalation: **{vals.get('escalation_path', '—')}**")
        st.write(f"**Routing rationale:** {vals.get('routing_rationale', '—')}")

        with st.form("hitl_form"):
            reviewer_id = st.text_input("Reviewer ID *", placeholder="UW-001")
            reviewer_decision = st.radio(
                "Decision",
                ["APPROVE", "APPROVE_WITH_CONDITIONS", "DECLINE", "REQUEST_MORE_INFO"],
                horizontal=True,
            )
            reviewer_notes = st.text_area("Notes (required for exceptions and declines)", height=100)
            conditions_raw = st.text_area(
                "Conditions (one per line — required if APPROVE_WITH_CONDITIONS)",
                height=80,
            )
            pricing_override_pct = st.number_input(
                "Rate Override (% — leave 0 if no change)", min_value=0.0, max_value=30.0, value=0.0, step=0.125
            )
            hitl_submitted = st.form_submit_button("Submit Decision", type="primary", use_container_width=True)

        if hitl_submitted:
            if not reviewer_id:
                st.error("Reviewer ID is required.")
            else:
                conditions = [c.strip() for c in conditions_raw.split("\n") if c.strip()]
                override = pricing_override_pct / 100 if pricing_override_pct > 0 else None
                graph.update_state(
                    config,
                    {
                        "reviewer_id": reviewer_id,
                        "reviewer_decision": reviewer_decision,
                        "reviewer_notes": reviewer_notes,
                        "conditions_imposed": conditions,
                        "pricing_override": override,
                    },
                    as_node="human_review_gate",
                )
                with st.spinner("Resuming pipeline..."):
                    try:
                        for _ in graph.stream(None, config):
                            pass
                        # Update register
                        for r in st.session_state.loan_register:
                            if r["thread_id"] == selected_thread:
                                snap2 = graph.get_state(config)
                                r["final_decision"] = snap2.values.get("final_decision", "PENDING")
                                r["awaiting_review"] = False
                        st.success(f"Decision submitted. Workflow resumed.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error resuming: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FAIR LENDING REVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Fair Lending Review — ECOA / Reg B / FHA")
    st.caption("Flags are set by Python logic only. No LLM can clear a fair lending flag.")

    if not st.session_state.loan_register:
        st.info("No applications submitted yet.")
    else:
        options3 = {r["application_id"]: r["thread_id"] for r in st.session_state.loan_register}
        sel3 = st.selectbox("Select Application", list(options3.keys()), key="fl_select")
        cfg3 = st.session_state.thread_configs.get(options3[sel3], {})
        try:
            snap3 = graph.get_state(cfg3)
            v3 = snap3.values
        except Exception:
            st.error("Could not load state.")
            st.stop()

        fl_flags = v3.get("fair_lending_flags", [])
        geo_flag = v3.get("geographic_flag", False)
        steering = v3.get("steering_flag", False)
        pricing_exc = v3.get("pricing_exception_flag", False)
        hmda = v3.get("hmda_reportable", False)
        cra = v3.get("cra_eligible", False)
        review_req = v3.get("fair_lending_review_required", False)

        if review_req:
            st.markdown('<div class="fair-lending-warning">⚠️ <strong>FAIR LENDING REVIEW REQUIRED</strong> — Compliance officer must review before final disposition. This requirement cannot be waived.</div>', unsafe_allow_html=True)
        else:
            st.success("✓ No fair lending flags — standard underwriting applies.")

        col_fl1, col_fl2, col_fl3 = st.columns(3)
        col_fl1.metric("Geographic Flag", "🚩 YES" if geo_flag else "✓ NO")
        col_fl2.metric("Steering Flag", "🚩 YES" if steering else "✓ NO")
        col_fl3.metric("Pricing Exception", "🚩 YES" if pricing_exc else "✓ NO")

        col_fl4, col_fl5 = st.columns(2)
        col_fl4.metric("HMDA Reportable", "Yes" if hmda else "No")
        col_fl5.metric("CRA Eligible", "Yes" if cra else "No")

        if fl_flags:
            st.divider()
            st.subheader("Flag Details")
            for flag in fl_flags:
                st.warning(flag)

        st.divider()
        st.subheader("Regulatory Reference")
        with st.expander("ECOA / Reg B (12 CFR Part 1002)"):
            st.write("""
**Prohibition:** Creditors may not discriminate against applicants on the basis of race, color, religion,
national origin, sex, marital status, age, receipt of public assistance, or good-faith exercise
of rights under CCPA.

**Adverse Action Notice:** Required within 30 days for all declined or counter-offered applications.
Must state specific reasons from the Reg B standard list (max 4). Vague denials are violations.

**Credit Score Disclosure:** If a credit score was used in the decision, FCRA § 615 requires disclosure
of the score, the range, key factors, and the reporting agency.
""")
        with st.expander("Fair Housing Act (42 U.S.C. § 3601)"):
            st.write("""
**Prohibited Bases (residential mortgage):** Race, color, national origin, religion, sex,
familial status, disability.

**Redlining:** Denying loans based on the racial or ethnic composition of a neighborhood — illegal
regardless of the applicant's individual creditworthiness.

**Steering:** Directing qualified applicants to higher-cost or less favorable loan products based
on a prohibited basis.
""")
        with st.expander("HMDA (12 CFR Part 1003)"):
            st.write("""
**Coverage:** Depository institutions and non-depository mortgage lenders above the volume threshold
must collect and report HMDA data.

**Data Points:** Loan purpose, loan amount, loan type, property location (census tract), applicant
demographic data (race, ethnicity, sex), and action taken (originated, denied, withdrawn, etc.).

**Action Taken Codes:** 1=Originated, 2=Application approved not accepted, 3=Application denied,
4=Application withdrawn by applicant, 5=File closed for incompleteness, 6=Purchased loan,
7=Preapproval denied, 8=Preapproval approved not accepted.
""")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — CREDIT DECISION
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Credit Decision")

    if not st.session_state.loan_register:
        st.info("No applications submitted yet.")
    else:
        options4 = {r["application_id"]: r["thread_id"] for r in st.session_state.loan_register}
        sel4 = st.selectbox("Select Application", list(options4.keys()), key="decision_select")
        cfg4 = st.session_state.thread_configs.get(options4[sel4], {})
        try:
            snap4 = graph.get_state(cfg4)
            v4 = snap4.values
        except Exception:
            st.error("Could not load state.")
            st.stop()

        final_decision = v4.get("final_decision", "PENDING")
        risk_tier = v4.get("risk_tier", "—")
        composite = v4.get("composite_score", 0)

        # Decision header
        if final_decision == "APPROVED":
            st.success(f"✅ APPROVED | Score: {composite:.3f} | Tier: {risk_tier}")
        elif final_decision == "CONDITIONALLY_APPROVED":
            st.warning(f"🟡 CONDITIONALLY APPROVED | Score: {composite:.3f} | Tier: {risk_tier}")
        elif final_decision == "DECLINED":
            st.error(f"❌ DECLINED | Score: {composite:.3f} | Tier: {risk_tier}")
        elif snap4.next == ("human_review_gate",):
            st.info("⏸ Awaiting underwriter review — see Underwriting Analysis tab.")
        else:
            st.info(f"Status: {final_decision or 'IN PROGRESS'}")

        st.write(f"**Decision rationale:** {v4.get('decision_rationale', '—')}")
        if v4.get("reviewer_id"):
            st.write(f"**Reviewed by:** {v4.get('reviewer_id')} on {v4.get('review_timestamp', '—')[:16]}")

        # Conditions
        conditions = v4.get("final_conditions", [])
        if conditions:
            st.subheader("Conditions")
            for c in conditions:
                st.write(f"• {c}")

        # Credit memo
        memo = v4.get("credit_memo_draft", "")
        if memo:
            st.divider()
            with st.expander("Credit Memorandum (LLM-drafted, underwriter-reviewed)", expanded=True):
                st.text_area("Credit Memo", memo, height=350, disabled=True)

        # Conditions letter
        cond_letter = v4.get("loan_structure_recommendation", "")
        if cond_letter:
            with st.expander("Conditions / Approval Letter"):
                st.text_area("Letter", cond_letter, height=250, disabled=True)

        # Exception narrative
        exc_narrative = v4.get("exceptions_narrative", "")
        if exc_narrative:
            with st.expander("Policy Exception Documentation"):
                st.text_area("Exception Narrative", exc_narrative, height=200, disabled=True)

        # Adverse action
        if v4.get("adverse_action_required"):
            st.divider()
            st.markdown('<div class="adverse-action-box"><strong>⚠️ ADVERSE ACTION NOTICE REQUIRED</strong><br>Reg B (12 CFR § 1002.9) — Notice must be sent within 30 days of the decision date.</div>', unsafe_allow_html=True)

            aa_reasons = v4.get("adverse_action_reasons", [])
            st.write("**Adverse Action Reasons (Reg B standard list):**")
            for i, reason in enumerate(aa_reasons, 1):
                st.write(f"{i}. {reason}")

            aa_notice = v4.get("adverse_action_notice_draft", "")
            if aa_notice:
                with st.expander("Adverse Action Notice (LLM-drafted per Reg B)", expanded=True):
                    st.text_area("Notice", aa_notice, height=400, disabled=True)
                    st.write(f"**Notice Deadline:** {v4.get('adverse_action_deadline', '—')}")
                    st.write("**Credit Score Disclosure:** Included (FCRA § 615)")

        # SAR referral
        if v4.get("sar_referral"):
            st.error("🚨 SAR REFERRAL: BSA Officer must evaluate this application for Suspicious Activity Report filing.")

        # HMDA
        if v4.get("hmda_reportable"):
            st.info(f"📊 HMDA Reportable | Action Taken Code: {v4.get('hmda_action_taken', '—')}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — LOAN REGISTER
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("Loan Register")
    st.caption("All applications — HMDA LAR tracking | Append-only")

    if not st.session_state.loan_register:
        st.info("No applications in register.")
    else:
        import pandas as pd

        df = pd.DataFrame(st.session_state.loan_register)
        display_cols = ["application_id", "applicant", "loan_type", "amount",
                        "composite_score", "risk_tier", "final_decision",
                        "hmda_reportable", "fair_lending_flag", "awaiting_review", "submitted_at"]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available], use_container_width=True, hide_index=True)

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        col_r1.metric("Total", len(df))
        col_r2.metric("HMDA Reportable", df["hmda_reportable"].sum() if "hmda_reportable" in df else 0)
        col_r3.metric("Fair Lending Flags", df["fair_lending_flag"].sum() if "fair_lending_flag" in df else 0)
        col_r4.metric("Awaiting Review", df["awaiting_review"].sum() if "awaiting_review" in df else 0)

        if "risk_tier" in df.columns:
            tier_counts = df["risk_tier"].value_counts()
            fig_pie = go.Figure(go.Pie(
                labels=tier_counts.index.tolist(),
                values=tier_counts.values.tolist(),
                hole=0.4,
                marker_colors=["#4ade80", "#facc15", "#60a5fa", "#f87171"],
            ))
            fig_pie.update_layout(title="Decision Distribution", height=300)
            st.plotly_chart(fig_pie, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("Configuration")
    guidelines = load_guidelines()
    routing = load_routing_matrix()

    st.subheader("SR 11-7 Model Governance")
    if "sr_11_7_model_governance" in guidelines:
        gov = guidelines["sr_11_7_model_governance"]
        col_g1, col_g2, col_g3 = st.columns(3)
        col_g1.metric("Model Version", gov.get("model_version", "—"))
        col_g2.metric("Last Validated", gov.get("last_validated", "—"))
        col_g3.metric("Next Review", gov.get("next_validation", "—"))

        st.write("**Factor Weights (fixed in code — require re-deployment to change):**")
        weights = gov.get("weights", {})
        w_cols = st.columns(len(weights))
        for i, (k, v) in enumerate(weights.items()):
            w_cols[i].metric(k.replace("_", " ").title(), f"{v:.0%}")

        st.write("**Decision Thresholds:**")
        thresholds = gov.get("decision_thresholds", {})
        for tier, bounds in thresholds.items():
            st.write(f"• **{tier}**: {bounds['min']} – {bounds['max']}")

        st.write("**Hard Decline Rules (Python constants — cannot be configured in UI):**")
        for rule in gov.get("hard_decline_rules", []):
            st.code(rule, language="python")

    st.divider()
    st.subheader("Underwriting Guidelines by Loan Type")
    loan_type_filter = st.selectbox("Loan Type", [k for k in guidelines if not k.startswith("_") and k not in ("fair_lending_policy", "sr_11_7_model_governance")])
    if loan_type_filter in guidelines:
        st.json(guidelines[loan_type_filter])

    st.divider()
    st.subheader("Delegation of Authority")
    doa = routing.get("delegation_of_authority", {})
    for role, params in doa.items():
        with st.expander(role):
            st.json(params)

    st.divider()
    st.subheader("Fair Lending Policy")
    if "fair_lending_policy" in guidelines:
        st.json(guidelines["fair_lending_policy"])
