# app.py
# ============================================================
# Real-Time Fraud Detection Agent — Streamlit Dashboard
#
# Run: streamlit run app.py
# Port: 8504 (see .streamlit/config.toml)
#
# Tabs:
#   1. Transaction Input    — Load sample or enter custom transaction
#   2. Detection Pipeline   — Real-time node-by-node execution
#   3. Fraud Score          — Composite score breakdown with charts
#   4. Decision & Evidence  — Fraud decision, Reg E draft, LLM reasoning
#   5. Analyst Review       — HITL panel for ANALYST_REVIEW cases
#   6. Audit Trail          — Examination-ready JSONL log
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

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Real-Time Fraud Detection Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State Initialization ──────────────────────────────────────────────
if "graph" not in st.session_state:
    st.session_state.graph = None
if "thread_config" not in st.session_state:
    st.session_state.thread_config = None
if "evaluation_result" not in st.session_state:
    st.session_state.evaluation_result = None
if "evaluation_running" not in st.session_state:
    st.session_state.evaluation_running = False
if "analyst_review_pending" not in st.session_state:
    st.session_state.analyst_review_pending = False
if "selected_transaction" not in st.session_state:
    st.session_state.selected_transaction = None


# ── Graph Initialization ───────────────────────────────────────────────────────
@st.cache_resource
def get_graph():
    from agent.graph import build_fraud_detection_graph
    return build_fraud_detection_graph(use_memory=True)


# ── Sample Transaction Loader ──────────────────────────────────────────────────
@st.cache_data
def load_sample_transactions():
    fixture_path = Path("data/fixtures/sample_transactions.json")
    if fixture_path.exists():
        with open(fixture_path) as f:
            return json.load(f)
    return []


# ── Helper: Decision Color & Badge ────────────────────────────────────────────
DECISION_COLORS = {
    "BLOCK": "#dc2626",
    "FREEZE_ACCOUNT": "#7f1d1d",
    "STEP_UP_AUTH": "#ea580c",
    "ANALYST_REVIEW": "#d97706",
    "ALLOW": "#16a34a",
}

DECISION_ICONS = {
    "BLOCK": "🚫",
    "FREEZE_ACCOUNT": "🔒",
    "STEP_UP_AUTH": "🔐",
    "ANALYST_REVIEW": "🔍",
    "ALLOW": "✅",
}


def decision_badge(decision: str) -> str:
    icon = DECISION_ICONS.get(decision, "❓")
    return f"{icon} **{decision}**"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.shields.io/badge/Fraud%20Detection-Agent-blue?style=for-the-badge", use_column_width=True)
    st.markdown("## 🛡️ Fraud Detection Agent")
    st.markdown("""
    **Real-Time Payment Fraud Prevention**

    Architecture:
    - Real-time path: <200ms decision
    - Async enrichment: LLM + behavioral
    - HITL: Analyst review gate
    - Reg E compliance: Auto-disclosure

    **Regulatory Coverage:**
    - Reg E (12 CFR § 1005)
    - Nacha Operating Rules
    - Visa/MC Zero Liability
    - BSA SAR consideration
    - SR 11-7 model risk
    """)

    st.divider()

    # API Key
    api_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        help="Required for LLM fraud analysis node",
    )
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    st.divider()
    st.markdown("**Decision Thresholds:**")
    st.markdown("""
    | Score | Decision |
    |-------|----------|
    | ≥ 85 | 🚫 BLOCK |
    | 65-84 | 🔐 STEP_UP |
    | 40-64 | 🔍 REVIEW |
    | < 40 | ✅ ALLOW |
    """)


# ── Main Header ───────────────────────────────────────────────────────────────
st.title("🛡️ Real-Time Fraud Detection Agent")
st.markdown(
    "**LangGraph Two-Path Architecture** · Rule Engine + LLM Analysis + Behavioral Signals · "
    "Reg E · BSA · SR 11-7"
)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "💳 Transaction Input",
    "⚙️ Detection Pipeline",
    "📊 Fraud Score",
    "⚖️ Decision & Evidence",
    "👤 Analyst Review",
    "📋 Audit Trail",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: Transaction Input
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Load Transaction for Evaluation")

    input_mode = st.radio(
        "Input Method",
        ["Sample Scenarios", "Custom Transaction"],
        horizontal=True,
    )

    if input_mode == "Sample Scenarios":
        samples = load_sample_transactions()
        if samples:
            scenario_labels = {
                s.get("transaction_id"): s.get("_scenario", s.get("transaction_id"))
                for s in samples
            }
            selected_id = st.selectbox(
                "Select Scenario",
                options=list(scenario_labels.keys()),
                format_func=lambda x: scenario_labels[x],
            )
            selected_txn = next((s for s in samples if s.get("transaction_id") == selected_id), None)
            if selected_txn:
                st.session_state.selected_transaction = {
                    k: v for k, v in selected_txn.items()
                    if not k.startswith("_")
                }
                st.json(st.session_state.selected_transaction)
        else:
            st.warning("Sample transaction fixtures not found.")

    else:
        col1, col2 = st.columns(2)
        with col1:
            txn_id = st.text_input("Transaction ID", value=f"TXN-{datetime.now().strftime('%Y%m%d')}-CUSTOM001")
            account_id = st.text_input("Account ID", value="ACCT-123456")
            customer_id = st.text_input("Customer ID", value="CUST-78901")
            amount = st.number_input("Amount (USD)", min_value=0.01, value=500.00, step=0.01)
            txn_type = st.selectbox("Transaction Type", ["PURCHASE", "WIRE", "TRANSFER", "WITHDRAWAL", "PAYMENT"])
            channel = st.selectbox(
                "Channel",
                ["ONLINE_BANKING", "MOBILE_APP", "POS_CHIP", "POS_SWIPE", "ATM", "WIRE", "ZELLE"],
            )
        with col2:
            merchant = st.text_input("Merchant Name", value="Amazon")
            mcc = st.text_input("MCC Code", value="5999", max_chars=4)
            country = st.text_input("Merchant Country (ISO)", value="US", max_chars=2)
            timestamp = st.text_input("Timestamp (ISO 8601)", value=datetime.now(timezone.utc).isoformat())
            device_id = st.text_input("Device ID (optional)", value="DEV-REG-4421")
            impossible_travel = st.checkbox("Impossible Travel Detected", value=False)

        if st.button("Use This Transaction"):
            st.session_state.selected_transaction = {
                "transaction_id": txn_id,
                "account_id": account_id,
                "customer_id": customer_id,
                "transaction_amount": amount,
                "transaction_currency": "USD",
                "transaction_type": txn_type,
                "transaction_channel": channel,
                "merchant_name": merchant,
                "merchant_category_code": mcc,
                "merchant_country": country.upper(),
                "transaction_timestamp": timestamp,
                "card_present": channel in ["POS_CHIP", "POS_SWIPE", "ATM"],
                "device_id": device_id or None,
                "impossible_travel": impossible_travel,
            }
            st.success("Transaction loaded. Switch to Detection Pipeline tab to run evaluation.")

    st.divider()

    # Run button
    if st.session_state.selected_transaction:
        if st.button("🚀 Run Fraud Evaluation", type="primary", use_container_width=True):
            if not os.getenv("ANTHROPIC_API_KEY"):
                st.warning("OpenAI API key required. Enter it in the sidebar.")
            else:
                st.session_state.evaluation_running = True
                st.session_state.evaluation_result = None
                st.session_state.analyst_review_pending = False

                try:
                    graph = get_graph()
                    import uuid
                    thread_id = str(uuid.uuid4())
                    config = {"configurable": {"thread_id": thread_id}}
                    st.session_state.thread_config = config

                    with st.spinner("Running fraud evaluation pipeline..."):
                        result = graph.invoke(
                            st.session_state.selected_transaction,
                            config=config,
                        )

                    decision = result.get("fraud_decision")
                    decision_val = decision.value if hasattr(decision, "value") else str(decision)

                    # Check if paused at human_review_gate
                    if decision_val == "ANALYST_REVIEW":
                        st.session_state.analyst_review_pending = True

                    st.session_state.evaluation_result = result
                    st.session_state.evaluation_running = False
                    st.success(f"Evaluation complete — Decision: {decision_val}")
                    st.rerun()

                except Exception as e:
                    st.session_state.evaluation_running = False
                    st.error(f"Evaluation failed: {e}")
                    logger.exception("Evaluation error")
    else:
        st.info("Load a transaction above to run fraud evaluation.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: Detection Pipeline
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Fraud Detection Pipeline")

    result = st.session_state.evaluation_result

    if not result:
        st.info("Run a transaction evaluation to see pipeline results.")
    else:
        completed = result.get("completed_steps") or []

        pipeline_nodes = [
            ("transaction_intake", "💳 Transaction Intake", "Parse & validate transaction event"),
            ("account_context_lookup", "👤 Account Context", "Retrieve history, risk tier, profile"),
            ("feature_extraction", "📐 Feature Extraction", "Compute velocity & anomaly features"),
            ("rule_engine_prescoring", "⚙️ Rule Engine", "Deterministic rules — velocity, geography, MCC"),
            ("device_intelligence", "📱 Device Intelligence", "Device risk, IP reputation, impossible travel"),
            ("behavioral_analysis", "🧠 Behavioral Analysis", "Session anomaly, new payee, ATO signals"),
            ("llm_fraud_analysis", "🤖 LLM Analysis (Claude Sonnet 4.6)", "Contextual fraud pattern synthesis"),
            ("composite_scoring", "📊 Composite Scoring", "Weighted score: rule 30% + LLM 50% + history 20%"),
        ]

        # Decision routing
        decision = result.get("fraud_decision")
        decision_val = decision.value if hasattr(decision, "value") else str(decision)

        action_nodes = {
            "BLOCK": ("block_transaction", "🚫 Block Transaction", "Decline + Reg E disclosure"),
            "FREEZE_ACCOUNT": ("block_transaction", "🔒 Freeze Account", "Emergency freeze"),
            "STEP_UP_AUTH": ("step_up_authentication", "🔐 Step-Up Authentication", "SMS OTP / Push challenge"),
            "ANALYST_REVIEW": ("flag_for_analyst_review", "🔍 Flag for Review", "Allow + analyst queue"),
            "ALLOW": ("allow_transaction", "✅ Allow Transaction", "Approve + continue monitoring"),
        }

        if decision_val in action_nodes:
            node_id, label, desc = action_nodes[decision_val]
            pipeline_nodes.append((node_id, label, desc))
            if decision_val == "ANALYST_REVIEW":
                pipeline_nodes.append(("human_review_gate", "👤 Human Review Gate", "Fraud analyst determination"))
        pipeline_nodes.append(("finalize_decision", "🏁 Finalize Decision", "Audit trail + case record"))

        # Render pipeline grid
        cols = st.columns(4)
        for idx, (node_id, label, desc) in enumerate(pipeline_nodes):
            col = cols[idx % 4]
            with col:
                is_done = node_id in completed
                status = "✅" if is_done else ("⏳" if st.session_state.evaluation_running else "⬜")
                bg = "#1a3a1a" if is_done else "#1a1a2e"
                st.markdown(
                    f"""<div style="background:{bg};border:1px solid {'#4CAF50' if is_done else '#333'};
                    border-radius:8px;padding:10px;margin:4px;min-height:80px">
                    <b>{status} {label}</b><br>
                    <small style="color:#aaa">{desc}</small></div>""",
                    unsafe_allow_html=True,
                )

        st.divider()

        # Key findings summary
        st.markdown("### Key Findings")

        col1, col2, col3, col4 = st.columns(4)

        score = result.get("composite_fraud_score", 0)
        col1.metric("Composite Score", f"{score:.1f}/100")

        rule_hits = result.get("rule_hits") or []
        col2.metric("Rules Fired", len(rule_hits))

        device_risk = result.get("device_risk_score", 0) or 0
        col3.metric("Device Risk", f"{device_risk:.1f}/100")

        beh = result.get("behavioral_signals") or {}
        beh_risk = beh.get("behavioral_risk_score", 0) or 0
        col4.metric("Behavioral Risk", f"{beh_risk:.1f}/100")

        # Rule hits detail
        if rule_hits:
            st.markdown("#### Rule Engine Hits")
            for hit in rule_hits:
                severity = hit.get("severity", "MEDIUM")
                color = {"CRITICAL": "red", "HIGH": "orange", "MEDIUM": "orange", "LOW": "blue"}.get(severity, "orange")
                st.markdown(
                    f"**:{color}[{hit.get('severity')}]** `{hit.get('rule_id')}` — "
                    f"{hit.get('rule_name')} (+{hit.get('score_contribution', 0)} pts)"
                )

        # Velocity signals
        velocity = result.get("velocity_signals") or {}
        if velocity:
            with st.expander("Velocity Signals"):
                vcol1, vcol2, vcol3 = st.columns(3)
                vcol1.metric("Txn (1 min)", velocity.get("txn_count_1min", 0))
                vcol2.metric("Txn (1 hr)", velocity.get("txn_count_1hr", 0))
                vcol3.metric("Amount (1 hr)", f"${velocity.get('amount_sum_1hr', 0):.0f}")

        # LLM reasoning
        llm_reasoning = result.get("llm_fraud_reasoning")
        if llm_reasoning:
            with st.expander("LLM Analysis Reasoning"):
                st.markdown(llm_reasoning)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: Fraud Score
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Fraud Score Analysis")

    result = st.session_state.evaluation_result
    if not result:
        st.info("Run a transaction evaluation to see score analysis.")
    else:
        score = result.get("composite_fraud_score", 0) or 0
        decision = result.get("fraud_decision")
        decision_val = decision.value if hasattr(decision, "value") else str(decision)
        color = DECISION_COLORS.get(decision_val, "#888")

        col1, col2 = st.columns([1, 1])

        # Gauge chart
        with col1:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                title={"text": "Composite Fraud Score", "font": {"size": 20}},
                number={"font": {"size": 40, "color": color}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1},
                    "bar": {"color": color},
                    "steps": [
                        {"range": [0, 40], "color": "#1a3a1a"},
                        {"range": [40, 65], "color": "#3a2a00"},
                        {"range": [65, 85], "color": "#3a1500"},
                        {"range": [85, 100], "color": "#3a0000"},
                    ],
                    "threshold": {
                        "line": {"color": "white", "width": 2},
                        "thickness": 0.75,
                        "value": score,
                    },
                },
            ))
            fig_gauge.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_gauge, use_container_width=True)

        # Score components bar chart
        with col2:
            components = result.get("score_components") or {}
            if components:
                fig_bar = go.Figure(go.Bar(
                    x=[
                        f"Rule Engine<br>(×{components.get('rule_weight', 0.3):.0%})",
                        f"LLM Analysis<br>(×{components.get('llm_weight', 0.5):.0%})",
                        f"Historical<br>(×{components.get('history_weight', 0.2):.0%})",
                        "Composite",
                    ],
                    y=[
                        components.get("rule_based_score", 0),
                        components.get("llm_fraud_probability", 0),
                        components.get("historical_pattern_score", 0),
                        components.get("composite_fraud_score", 0),
                    ],
                    marker_color=["#3b82f6", "#8b5cf6", "#10b981", color],
                    text=[
                        f"{components.get('rule_based_score', 0):.1f}",
                        f"{components.get('llm_fraud_probability', 0):.1f}",
                        f"{components.get('historical_pattern_score', 0):.1f}",
                        f"{components.get('composite_fraud_score', 0):.1f}",
                    ],
                    textposition="outside",
                ))
                fig_bar.update_layout(
                    title="Score Component Breakdown",
                    yaxis_range=[0, 110],
                    height=300,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="white",
                )
                st.plotly_chart(fig_bar, use_container_width=True)

        # Score components table (SR 11-7 documentation)
        st.markdown("### Score Components (SR 11-7 Model Documentation)")
        if components:
            st.table({
                "Component": ["Rule Engine", "LLM Analysis", "Historical Pattern", "**Composite**"],
                "Raw Score": [
                    f"{components.get('rule_based_score', 0):.1f}",
                    f"{components.get('llm_fraud_probability', 0):.1f}",
                    f"{components.get('historical_pattern_score', 0):.1f}",
                    f"**{components.get('composite_fraud_score', 0):.1f}**",
                ],
                "Weight": ["30%", "50%", "20%", "100%"],
                "Weighted Contribution": [
                    f"{components.get('rule_based_score', 0) * 0.3:.1f}",
                    f"{components.get('llm_fraud_probability', 0) * 0.5:.1f}",
                    f"{components.get('historical_pattern_score', 0) * 0.2:.1f}",
                    f"**{components.get('composite_fraud_score', 0):.1f}**",
                ],
            })

        # Risk factors
        risk_factors = result.get("risk_factors") or []
        if risk_factors:
            st.markdown("### Top Risk Factors")
            for i, factor in enumerate(risk_factors[:8], 1):
                st.markdown(f"{i}. {factor}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: Decision & Evidence
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Fraud Decision & Evidence Package")

    result = st.session_state.evaluation_result
    if not result:
        st.info("Run a transaction evaluation to see the decision.")
    else:
        decision = result.get("fraud_decision")
        decision_val = decision.value if hasattr(decision, "value") else str(decision)
        color = DECISION_COLORS.get(decision_val, "#888")
        icon = DECISION_ICONS.get(decision_val, "❓")

        # Decision banner
        st.markdown(
            f"""<div style="background:{color}22;border:2px solid {color};border-radius:12px;
            padding:20px;text-align:center;margin-bottom:20px">
            <h1 style="color:{color};margin:0">{icon} {decision_val}</h1>
            <p style="color:#ccc;margin:5px 0">Composite Score: {result.get('composite_fraud_score', 0):.1f}/100 ·
            Confidence: {result.get('decision_confidence', 'N/A')} ·
            Response Time: {result.get('response_time_ms', 'N/A')} ms</p>
            </div>""",
            unsafe_allow_html=True,
        )

        # Decision rationale
        rationale = result.get("decision_rationale")
        if rationale:
            st.markdown("**Decision Rationale:**")
            st.info(rationale)

        # LLM fraud analysis
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### LLM Analysis")
            llm_prob = result.get("llm_fraud_probability", 0)
            fraud_type = result.get("llm_suspected_fraud_type")
            fraud_type_val = fraud_type.value if hasattr(fraud_type, "value") else str(fraud_type or "UNKNOWN")
            st.metric("LLM Fraud Probability", f"{llm_prob:.1f}/100")
            st.metric("Suspected Fraud Type", fraud_type_val)

            reasoning = result.get("llm_fraud_reasoning")
            if reasoning:
                st.markdown("**LLM Reasoning:**")
                st.markdown(reasoning)

        with col2:
            st.markdown("### Case Details")
            case_id = result.get("case_id")
            if case_id:
                st.metric("Case ID", case_id)
            queue = result.get("analyst_queue")
            if queue:
                st.metric("Analyst Queue", queue)
            sar = result.get("sar_consideration_flag", False)
            if sar:
                st.warning("⚠️ SAR Consideration Flagged — BSA Officer evaluation required within 30 days")

        # Reg E Disclosure
        reg_e = result.get("reg_e_disclosure_draft")
        if reg_e:
            st.divider()
            st.markdown("### Reg E Customer Disclosure (Draft)")
            st.markdown("*Subject to Compliance review before sending*")
            st.text_area("Disclosure Text", value=reg_e, height=300, disabled=False)

        # Step-up auth result
        auth_method = result.get("step_up_auth_method")
        auth_result = result.get("step_up_auth_result")
        if auth_method:
            st.divider()
            st.markdown("### Step-Up Authentication")
            col1, col2 = st.columns(2)
            col1.metric("Method", auth_method)
            if auth_result:
                auth_color = "green" if auth_result == "PASSED" else "red"
                col2.metric("Result", auth_result)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: Analyst Review
# ═══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("👤 Fraud Analyst Review")

    result = st.session_state.evaluation_result

    if not result:
        st.info("Run a transaction evaluation to see analyst review.")
    else:
        decision = result.get("fraud_decision")
        decision_val = decision.value if hasattr(decision, "value") else str(decision)

        if decision_val != "ANALYST_REVIEW":
            st.info(
                f"Analyst review is only required for ANALYST_REVIEW decisions. "
                f"Current decision: **{decision_val}**"
            )
        else:
            st.markdown("### Case Evidence Summary")
            st.markdown(f"**Case ID:** `{result.get('case_id', 'PENDING')}`")
            st.markdown(f"**Transaction:** `{result.get('transaction_id')}`")
            st.markdown(f"**Composite Score:** {result.get('composite_fraud_score', 0):.1f}/100")
            st.markdown(f"**Suspected Fraud Type:** {result.get('llm_suspected_fraud_type', 'UNKNOWN')}")

            # LLM reasoning for analyst
            reasoning = result.get("llm_fraud_reasoning")
            if reasoning:
                with st.expander("LLM Analysis Reasoning", expanded=True):
                    st.markdown(reasoning)

            # Risk factors
            risk_factors = result.get("risk_factors") or []
            if risk_factors:
                with st.expander("Risk Factors"):
                    for factor in risk_factors:
                        st.markdown(f"• {factor}")

            st.divider()
            st.markdown("### Analyst Determination")

            if not st.session_state.get("analyst_decision_submitted"):
                with st.form("analyst_review_form"):
                    analyst_id = st.text_input("Analyst ID", value="ANALYST-001")
                    analyst_decision = st.selectbox(
                        "Determination",
                        ["CONFIRMED_FRAUD", "FALSE_POSITIVE", "NEEDS_MORE_INFO", "ESCALATE"],
                    )
                    analyst_notes = st.text_area(
                        "Analyst Notes",
                        placeholder="Document your findings, evidence reviewed, and rationale...",
                        height=150,
                    )
                    submitted = st.form_submit_button("Submit Determination", type="primary")

                    if submitted:
                        # Update state with analyst decision
                        result["analyst_id"] = analyst_id
                        result["analyst_decision"] = analyst_decision
                        result["analyst_notes"] = analyst_notes
                        result["human_review_completed"] = True
                        result["human_review_completed_at"] = datetime.now(timezone.utc).isoformat()

                        # Resume LangGraph from human_review_gate
                        try:
                            graph = get_graph()
                            config = st.session_state.thread_config
                            if config:
                                final_result = graph.invoke(
                                    {
                                        "analyst_id": analyst_id,
                                        "analyst_decision": analyst_decision,
                                        "analyst_notes": analyst_notes,
                                        "human_review_completed": True,
                                        "human_review_completed_at": result["human_review_completed_at"],
                                    },
                                    config=config,
                                )
                                st.session_state.evaluation_result = final_result
                        except Exception as e:
                            logger.warning(f"Graph resume failed (demo mode): {e}")
                            st.session_state.evaluation_result = result

                        st.session_state.analyst_decision_submitted = True
                        st.session_state.analyst_review_pending = False
                        st.success(f"Determination recorded: {analyst_decision}")
                        st.rerun()
            else:
                st.success(f"✅ Analyst determination submitted: {result.get('analyst_decision')}")
                st.info(f"Analyst notes: {result.get('analyst_notes', 'N/A')}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6: Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("Examination-Ready Audit Trail")
    st.markdown(
        "*Append-only JSONL log — BSA 5-year retention requirement (31 U.S.C. § 5318)*"
    )

    result = st.session_state.evaluation_result

    if result:
        audit_trail = result.get("audit_trail") or []
        if audit_trail:
            st.markdown(f"**{len(audit_trail)} entries** for this transaction")

            for i, entry in enumerate(audit_trail):
                with st.expander(
                    f"{i+1}. [{entry.get('node', 'UNKNOWN')}] {entry.get('action', '')[:80]}...",
                    expanded=(i == len(audit_trail) - 1),
                ):
                    col1, col2 = st.columns(2)
                    col1.markdown(f"**Timestamp:** {entry.get('timestamp', 'N/A')}")
                    col1.markdown(f"**Actor:** {entry.get('actor', 'N/A')}")
                    col1.markdown(f"**Node:** `{entry.get('node', 'N/A')}`")
                    if entry.get("score_at_time") is not None:
                        col1.markdown(f"**Score at time:** {entry.get('score_at_time'):.1f}")
                    col2.markdown(f"**Data Sources:** {', '.join(entry.get('data_sources_accessed') or [])}")
                    if entry.get("ai_model_used"):
                        col2.markdown(f"**AI Model:** {entry.get('ai_model_used')}")
                    if entry.get("response_time_ms"):
                        col2.markdown(f"**Response Time:** {entry.get('response_time_ms')} ms")
                    if entry.get("regulatory_basis"):
                        st.markdown(f"**Regulatory Basis:** *{entry.get('regulatory_basis')}*")

            # Download audit trail
            st.divider()
            st.download_button(
                label="📥 Download Audit Trail (JSON)",
                data=json.dumps(audit_trail, indent=2, default=str),
                file_name=f"audit_trail_{result.get('transaction_id', 'txn')}.json",
                mime="application/json",
            )
        else:
            st.info("No audit trail entries for this evaluation.")
    else:
        # Show historical log
        from tools.case_manager import get_audit_log
        try:
            historical = get_audit_log(limit=50)
            if historical:
                st.markdown(f"**{len(historical)} historical log entries (last 50)**")
                st.json(historical)
            else:
                st.info("No audit log entries yet. Run a transaction evaluation.")
        except Exception:
            st.info("Run a transaction evaluation to see the audit trail.")
