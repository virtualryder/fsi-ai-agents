# app.py
# ============================================================
# KYC/CDD Perpetual Monitoring Agent — Streamlit Dashboard
#
# Tabs:
#   1. Review Queue  — load sample triggers or enter custom review
#   2. Investigation — real-time node execution with findings
#   3. Risk Assessment — 8-factor score breakdown (Plotly)
#   4. EDD Package — document checklist + RM outreach draft
#   5. Compliance Review — officer approval gate
#   6. Audit Trail — examination-ready log
# ============================================================

import streamlit as st
import json
import os
from datetime import datetime
from pathlib import Path

# ── Page configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KYC/CDD Perpetual Monitoring Agent",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load fixtures ─────────────────────────────────────────────────────────────
FIXTURES_DIR = Path("data/fixtures")

@st.cache_data
def load_sample_triggers():
    path = FIXTURES_DIR / "sample_review_triggers.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []

@st.cache_data
def load_sample_customers():
    path = FIXTURES_DIR / "sample_customers.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

# ── Initialize session state ──────────────────────────────────────────────────
if "review_state" not in st.session_state:
    st.session_state.review_state = None
if "review_running" not in st.session_state:
    st.session_state.review_running = False
if "graph_thread_id" not in st.session_state:
    st.session_state.graph_thread_id = None
if "awaiting_co_decision" not in st.session_state:
    st.session_state.awaiting_co_decision = False

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📋 KYC/CDD Agent")
    st.caption("Perpetual Monitoring · Automated CDD Refresh")
    st.divider()
    st.markdown("**Part of the FSI AI Suite**")
    st.markdown("- [01 · Financial Crime Investigation](../01-financial-crime-investigation-agent/)")
    st.markdown("- [02 · AML/TMS Enhancement](../02-aml-tms-enhancement-agent/)")
    st.markdown("- **03 · KYC/CDD** ← you are here")
    st.divider()
    st.markdown("**Stack**")
    st.markdown("LangGraph · GPT-4o · Streamlit")
    st.markdown("**Regulatory**")
    st.markdown("FinCEN CDD Rule · FATF R.10/R.12 · FFIEC · SR 11-7")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📋 KYC/CDD Perpetual Monitoring Agent")
st.markdown(
    "Automated customer due diligence refresh — event-driven and scheduled. "
    "Every review follows the same 12-step documented process. "
    "Compliance Officer approves all risk tier changes."
)
st.divider()

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📥 Review Queue",
    "🔍 Investigation",
    "📊 Risk Assessment",
    "📄 EDD Package",
    "👤 Compliance Review",
    "📋 Audit Trail",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1: REVIEW QUEUE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.header("KYC Review Queue")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Load a Sample Scenario")
        triggers = load_sample_triggers()
        customers = load_sample_customers()

        if triggers:
            trigger_options = {
                f"{t['customer_id']} — {t['trigger_type']} ({t.get('scenario', '')[:50]})": t
                for t in triggers
            }
            selected_label = st.selectbox("Select scenario", list(trigger_options.keys()))
            selected_trigger = trigger_options[selected_label]

            # Show scenario details
            customer_data = customers.get(selected_trigger["customer_id"], {})
            with st.expander("Customer & Trigger Details", expanded=True):
                scol1, scol2 = st.columns(2)
                with scol1:
                    st.metric("Customer", customer_data.get("customer_name", selected_trigger["customer_id"]))
                    st.metric("Current Risk Tier", customer_data.get("risk_tier", "MEDIUM"))
                    st.metric("EDD Active", "Yes" if customer_data.get("edd_status") else "No")
                    st.metric("PEP Flag", "Yes" if customer_data.get("pep_flag") else "No")
                with scol2:
                    st.metric("Trigger Type", selected_trigger["trigger_type"])
                    st.metric("Trigger Date", selected_trigger["trigger_event_date"])
                    st.metric("Customer Type", customer_data.get("customer_type", "LLC"))
                    st.metric("Business Type", customer_data.get("business_type", "N/A"))

                st.info(f"**Trigger:** {selected_trigger['trigger_description']}")
                if selected_trigger.get("scenario"):
                    st.caption(f"Scenario notes: {selected_trigger['scenario']}")

            if st.button("🚀 Start KYC Review", type="primary", use_container_width=True):
                _run_review(selected_trigger, customer_data)
        else:
            st.warning("No sample triggers found. Check data/fixtures/sample_review_triggers.json")

    with col2:
        st.subheader("Manual Review Entry")
        st.caption("Enter a custom customer ID and trigger to run a review")

        with st.form("manual_review"):
            manual_customer_id = st.text_input("Customer ID", placeholder="CUST-001234")
            manual_trigger_type = st.selectbox(
                "Trigger Type",
                ["SCHEDULED", "ADVERSE_MEDIA", "WATCHLIST_HIT", "TRANSACTION_SPIKE",
                 "BENEFICIAL_OWNER_CHANGE", "SAR_FILED", "MANUAL", "RISK_MODEL_FLAG"],
            )
            manual_trigger_desc = st.text_area(
                "Trigger Description",
                placeholder="Describe the specific event that triggered this review...",
                height=100,
            )
            submitted = st.form_submit_button("Start Manual Review", use_container_width=True)
            if submitted and manual_customer_id:
                manual_trigger = {
                    "customer_id": manual_customer_id,
                    "trigger_type": manual_trigger_type,
                    "trigger_description": manual_trigger_desc or f"Manual {manual_trigger_type} review",
                    "trigger_event_date": datetime.utcnow().date().isoformat(),
                }
                manual_customer = customers.get(manual_customer_id, {
                    "customer_id": manual_customer_id,
                    "customer_type": "LLC",
                    "risk_tier": "MEDIUM",
                })
                _run_review(manual_trigger, manual_customer)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2: INVESTIGATION PROGRESS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.header("Investigation Progress")

    if not st.session_state.review_state:
        st.info("No review running. Go to **Review Queue** to start a review.")
    else:
        state = st.session_state.review_state
        completed = state.get("completed_steps", [])
        current = state.get("current_step", "")
        errors = state.get("errors", [])

        # Progress summary
        all_steps = [
            "trigger_evaluation", "customer_risk_profile", "document_collection",
            "watchlist_screening", "adverse_media_check", "risk_rescoring",
            "edd_package_generation", "rm_notification", "human_review_gate",
            "kyc_record_update", "finalize_review",
        ]

        progress_pct = len(completed) / len(all_steps)
        st.progress(progress_pct)

        # Step status grid
        st.subheader("Step Execution")
        step_cols = st.columns(4)
        step_labels = {
            "trigger_evaluation": "1. Trigger Eval",
            "customer_risk_profile": "2. Customer Profile",
            "document_collection": "3. Doc Assessment",
            "watchlist_screening": "4. Watchlist Screen",
            "adverse_media_check": "5. Adverse Media",
            "risk_rescoring": "6. Risk Rescoring",
            "edd_package_generation": "7. EDD Package",
            "rm_notification": "8. RM Notification",
            "human_review_gate": "9. CO Review Gate",
            "kyc_record_update": "10. Record Update",
            "finalize_review": "11. Finalize",
        }
        for i, (step_key, step_label) in enumerate(step_labels.items()):
            with step_cols[i % 4]:
                if step_key in completed:
                    st.success(f"✅ {step_label}")
                elif step_key == current:
                    st.warning(f"⏳ {step_label}")
                else:
                    st.markdown(f"⬜ {step_label}")

        if errors:
            st.warning(f"{len(errors)} non-fatal error(s) during review:")
            for err in errors:
                st.error(f"Step: {err.get('step')} — {err.get('error')}")

        # Key findings display
        st.subheader("Key Findings")
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            score = state.get("new_risk_score", 0)
            delta = state.get("risk_score_delta", 0)
            st.metric("Risk Score", f"{score:.0f}/100", delta=f"{delta:+.0f}" if delta else None)
        with f_col2:
            outcome = state.get("recommended_outcome", "—")
            outcome_val = outcome.value if hasattr(outcome, "value") else str(outcome)
            outcome_color = {
                "PASS": "normal", "RISK_UPGRADE": "off", "EDD_REQUIRED": "off",
                "ESCALATE": "off", "RELATIONSHIP_EXIT": "off",
            }.get(outcome_val, "normal")
            st.metric("Recommended Outcome", outcome_val)
        with f_col3:
            ofac = "🚨 HIT" if state.get("ofac_hit") else "✅ Clear"
            pep = "⚠️ YES" if state.get("pep_flag") else "✅ No"
            st.metric("OFAC", ofac)
            st.metric("PEP Flag", pep)
        with f_col4:
            completeness = state.get("cdd_completeness_score", 0)
            missing = len(state.get("missing_documents", []))
            st.metric("Doc Completeness", f"{completeness:.0f}%")
            st.metric("Missing Documents", missing)

        if state.get("risk_narrative"):
            with st.expander("Risk Narrative (for Compliance Officer)", expanded=False):
                st.markdown(state["risk_narrative"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3: RISK ASSESSMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.header("Risk Assessment")

    if not st.session_state.review_state:
        st.info("No review running.")
    else:
        state = st.session_state.review_state
        components = state.get("risk_score_components", {})
        new_score = state.get("new_risk_score", 0)
        prev_score = state.get("previous_risk_score", 0)

        if components:
            import plotly.graph_objects as go
            import plotly.express as px

            # Score gauge
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=new_score,
                delta={"reference": prev_score, "valueformat": ".1f"},
                title={"text": "Composite Risk Score"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 35], "color": "lightgreen"},
                        {"range": [35, 60], "color": "yellow"},
                        {"range": [60, 80], "color": "orange"},
                        {"range": [80, 100], "color": "red"},
                    ],
                    "threshold": {"line": {"color": "black", "width": 4}, "thickness": 0.75, "value": new_score},
                },
            ))
            fig_gauge.update_layout(height=300)

            # Component bar chart
            from tools.risk_scorer import COMPONENT_WEIGHTS
            component_labels = [k.replace("_", " ").title() for k in components.keys()]
            component_scores = list(components.values())
            weight_pcts = [COMPONENT_WEIGHTS.get(k, 0) * 100 for k in components.keys()]
            weighted_contributions = [
                components.get(k, 0) * COMPONENT_WEIGHTS.get(k, 0)
                for k in components.keys()
            ]

            fig_bar = px.bar(
                x=component_labels,
                y=component_scores,
                color=component_scores,
                color_continuous_scale=["green", "yellow", "red"],
                range_color=[0, 100],
                labels={"x": "Risk Factor", "y": "Component Score (0-100)"},
                title="Risk Score Components (SR 11-7 Explainability)",
            )
            fig_bar.update_layout(showlegend=False, height=350)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.plotly_chart(fig_gauge, use_container_width=True)
                st.metric("Previous Score", f"{prev_score:.0f}")
                st.metric("Score Change", f"{new_score - prev_score:+.0f} points")
                tier = state.get("proposed_risk_tier")
                tier_val = tier.value if hasattr(tier, "value") else str(tier)
                st.metric("Proposed Risk Tier", tier_val)
            with col2:
                st.plotly_chart(fig_bar, use_container_width=True)

            # Detailed component table
            st.subheader("Component Detail (SR 11-7 Model Documentation)")
            for k, score in components.items():
                weight = COMPONENT_WEIGHTS.get(k, 0)
                contribution = score * weight
                label = k.replace("_", " ").title()
                col_l, col_s, col_w, col_c = st.columns([3, 1, 1, 1])
                with col_l:
                    st.markdown(f"**{label}**")
                with col_s:
                    color = "🔴" if score >= 70 else "🟡" if score >= 40 else "🟢"
                    st.markdown(f"{color} {score:.0f}/100")
                with col_w:
                    st.markdown(f"Weight: {weight*100:.0f}%")
                with col_c:
                    st.markdown(f"Contribution: {contribution:.1f}")
        else:
            st.info("Risk scoring not yet complete.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4: EDD PACKAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    st.header("EDD Package")

    if not st.session_state.review_state:
        st.info("No review running.")
    elif not st.session_state.review_state.get("edd_required"):
        state = st.session_state.review_state
        outcome = state.get("recommended_outcome")
        outcome_val = outcome.value if hasattr(outcome, "value") else str(outcome)
        if outcome_val == "PASS":
            st.success("✅ EDD not required for this review. Outcome: PASS")
        else:
            st.info(f"EDD package not generated. Outcome: {outcome_val}")
    else:
        state = st.session_state.review_state

        st.success(f"⚠️ EDD Required | Deadline: {state.get('edd_deadline', 'TBD')}")

        if state.get("edd_trigger_reasons"):
            st.subheader("EDD Trigger Reasons")
            for reason in state["edd_trigger_reasons"]:
                st.markdown(f"- {reason}")

        checklist = state.get("edd_document_checklist", [])
        if checklist:
            st.subheader(f"Document Checklist ({len(checklist)} documents)")
            for i, doc in enumerate(checklist, 1):
                priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(doc.get("priority", "MEDIUM"), "⬜")
                with st.expander(f"{priority_icon} {i}. {doc['document']}", expanded=doc.get("priority") == "HIGH"):
                    st.markdown(f"**Regulatory basis:** {doc.get('reason_required', 'N/A')}")
                    if doc.get("deadline_days"):
                        st.markdown(f"**Deadline:** {doc['deadline_days']} days from review initiation")
                    st.markdown(f"**Priority:** {doc.get('priority', 'MEDIUM')}")

        if state.get("edd_outreach_draft"):
            st.subheader("RM Outreach Draft")
            st.info("Review this communication before sending to the customer. Edit as needed.")
            edited_draft = st.text_area(
                "Customer Outreach Draft (for RM review)",
                value=state["edd_outreach_draft"],
                height=300,
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📋 Copy to Clipboard"):
                    st.code(edited_draft)
            with col2:
                st.download_button(
                    "⬇️ Download Draft",
                    data=edited_draft,
                    file_name=f"edd_outreach_{state.get('customer_id', 'customer')}.txt",
                    mime="text/plain",
                )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 5: COMPLIANCE REVIEW (Human-in-the-Loop Gate)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.header("Compliance Officer Review")

    if not st.session_state.review_state:
        st.info("No review running.")
    elif st.session_state.review_state.get("compliance_officer_decision"):
        decision = st.session_state.review_state.get("compliance_officer_decision")
        st.success(f"✅ Review completed. Compliance Officer decision: **{decision}**")
        st.markdown(f"**Notes:** {st.session_state.review_state.get('compliance_officer_notes', 'None')}")
    elif not st.session_state.awaiting_co_decision:
        state = st.session_state.review_state
        outcome = state.get("recommended_outcome")
        outcome_val = outcome.value if hasattr(outcome, "value") else str(outcome)
        if outcome_val == "PASS":
            st.success("✅ PASS outcome — no Compliance Officer review required for this review.")
            st.markdown("The KYC record will be updated automatically with the next review date.")
        else:
            st.info(f"Review in progress (current outcome: {outcome_val}). Complete the review pipeline before the CO gate appears here.")
    else:
        state = st.session_state.review_state
        st.warning("⚠️ **Compliance Officer Review Required** — This review cannot be finalized without your approval.")
        st.divider()

        # Executive summary for CO
        outcome = state.get("recommended_outcome")
        outcome_val = outcome.value if hasattr(outcome, "value") else str(outcome)

        co_col1, co_col2, co_col3 = st.columns(3)
        with co_col1:
            st.metric("Customer", state.get("customer_name", "N/A"))
            st.metric("Trigger", state.get("trigger_type", "N/A"))
        with co_col2:
            st.metric("Risk Score", f"{state.get('new_risk_score', 0):.0f}/100",
                      delta=f"{state.get('risk_score_delta', 0):+.0f}")
            st.metric("Current Tier", str(state.get("current_risk_tier", "N/A")))
        with co_col3:
            st.metric("Recommended Outcome", outcome_val)
            proposed = state.get("proposed_risk_tier")
            st.metric("Proposed Tier", proposed.value if hasattr(proposed, "value") else str(proposed))

        if state.get("risk_narrative"):
            with st.expander("Risk Assessment Narrative", expanded=True):
                st.markdown(state["risk_narrative"])

        if state.get("rm_notification_draft"):
            with st.expander("RM Notification Draft"):
                st.markdown(state["rm_notification_draft"])

        st.divider()
        st.subheader("Your Decision")

        co_officer_id = st.text_input("Compliance Officer ID", placeholder="CO-001")
        co_decision = st.radio(
            "Decision",
            ["APPROVED", "OVERRIDDEN", "ESCALATED_FURTHER"],
            captions=[
                "Accept the recommended outcome and proposed risk tier",
                "Change the outcome or risk tier (provide rationale below)",
                "Refer to BSA Committee or Senior Management",
            ],
        )

        override_outcome = None
        override_tier = None
        if co_decision == "OVERRIDDEN":
            from agent.state import ReviewOutcome, RiskTier
            override_outcome = st.selectbox(
                "Override Outcome",
                [o.value for o in ReviewOutcome],
                index=0,
            )
            override_tier = st.selectbox(
                "Override Risk Tier",
                [t.value for t in RiskTier],
                index=1,
            )

        co_notes = st.text_area("Notes / Rationale", placeholder="Document your decision rationale...")

        if st.button("✅ Submit Compliance Decision", type="primary", disabled=not co_officer_id):
            # Update state with compliance officer decision
            state_updates = {
                "compliance_officer_id": co_officer_id,
                "compliance_officer_decision": co_decision,
                "compliance_officer_notes": co_notes,
            }
            if co_decision == "OVERRIDDEN" and override_outcome:
                from agent.state import ReviewOutcome, RiskTier
                state_updates["compliance_officer_override_outcome"] = ReviewOutcome(override_outcome)
                state_updates["compliance_officer_override_tier"] = RiskTier(override_tier)

            for k, v in state_updates.items():
                st.session_state.review_state[k] = v

            st.session_state.awaiting_co_decision = False
            st.success(f"Decision recorded: **{co_decision}**. Completing review pipeline...")
            st.rerun()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 6: AUDIT TRAIL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    st.header("Audit Trail")
    st.caption("Append-only examination-ready audit log. Every action is logged with timestamp, data sources, and regulatory basis.")

    if not st.session_state.review_state:
        st.info("No review running.")
    else:
        audit_trail = st.session_state.review_state.get("audit_trail", [])
        if not audit_trail:
            st.info("No audit entries yet.")
        else:
            st.metric("Total Audit Entries", len(audit_trail))
            for i, entry in enumerate(reversed(audit_trail)):
                with st.expander(
                    f"[{i+1}] {entry.get('timestamp', 'N/A')[:19]} — {entry.get('node', 'N/A')} — {entry.get('actor', 'N/A')}",
                    expanded=i == 0,
                ):
                    st.markdown(f"**Action:** {entry.get('action', '')}")
                    if entry.get("data_sources_accessed"):
                        st.markdown(f"**Data sources:** {', '.join(entry['data_sources_accessed'])}")
                    if entry.get("regulatory_basis"):
                        st.markdown(f"**Regulatory basis:** {entry['regulatory_basis']}")
                    if entry.get("ai_model_used"):
                        st.markdown(f"**AI model:** {entry['ai_model_used']}")
                    if entry.get("human_review_required"):
                        st.warning("⚠️ Human review required for this step")

            st.download_button(
                "⬇️ Download Audit Trail (JSON)",
                data=json.dumps(audit_trail, indent=2, default=str),
                file_name=f"audit_trail_{st.session_state.review_state.get('review_id', 'review')}.json",
                mime="application/json",
            )


# ── Review execution helper ───────────────────────────────────────────────────
def _run_review(trigger: dict, customer_data: dict):
    """Execute the KYC review pipeline and update session state."""
    from agent.graph import build_kyc_review_graph
    from agent.state import TriggerType, RiskTier

    try:
        graph = build_kyc_review_graph(use_memory=True)

        initial_state = {
            "customer_id": trigger["customer_id"],
            "customer_name": customer_data.get("customer_name", trigger["customer_id"]),
            "trigger_type": TriggerType(trigger["trigger_type"]),
            "trigger_description": trigger.get("trigger_description", ""),
            "trigger_event_date": trigger.get("trigger_event_date", datetime.utcnow().date().isoformat()),
            "current_risk_tier": RiskTier(customer_data.get("risk_tier", "MEDIUM")),
            "pep_flag": customer_data.get("pep_flag", False),
            "beneficial_owners": customer_data.get("beneficial_owners", []),
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        }

        thread_config = {"configurable": {"thread_id": f"review-{trigger['customer_id']}-{datetime.utcnow().timestamp()}"}}

        with st.spinner("Running KYC review pipeline..."):
            for chunk in graph.stream(initial_state, config=thread_config):
                for node_name, node_output in chunk.items():
                    if isinstance(node_output, dict):
                        if st.session_state.review_state is None:
                            st.session_state.review_state = {}
                        st.session_state.review_state.update(node_output)

                    # Check if paused at human review gate
                    if node_name == "human_review_gate":
                        review_state = st.session_state.review_state or {}
                        if review_state.get("human_review_required") and not review_state.get("compliance_officer_decision"):
                            st.session_state.awaiting_co_decision = True
                            break

        st.session_state.graph_thread_id = thread_config["configurable"]["thread_id"]
        st.success("✅ Review pipeline complete. See tabs for results.")
        st.rerun()

    except Exception as e:
        st.error(f"Review failed: {e}")
        import traceback
        st.code(traceback.format_exc())
