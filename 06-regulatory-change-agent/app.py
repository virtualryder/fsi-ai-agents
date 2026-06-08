# app.py
# ============================================================
# Regulatory Change Management Agent — Streamlit Dashboard
#
# Dashboard tabs:
#   1. Regulatory Feed        — Incoming changes and processing status
#   2. Impact Analysis        — Gap analysis, scoring breakdown, gaps
#   3. Remediation Tracker    — Open tasks, deadlines, owners, progress
#   4. Policy Registry        — Current policies and regulatory mapping
#   5. Audit Trail            — Full decision and action log
#   6. Configuration          — Regulatory sources, routing, thresholds
#
# Human-in-the-loop:
#   CRITICAL/HIGH impact changes pause at the human_review_gate.
#   The Compliance Officer reviews the gap analysis in Tab 2, then
#   approves/modifies/marks as not applicable via the review panel.
#   The workflow resumes after the officer's decision is submitted.
#
# Port: 8506
# ============================================================

import os
import json
import uuid
import logging
from datetime import datetime, timedelta

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from agent.graph import build_regulatory_change_graph
from agent.state import (
    ChangeManagementState,
    ChangeType,
    RegulatoryDomain,
    ImpactTier,
    CaseStatus,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Regulatory Change Management",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #f8f9fa;
    border-left: 4px solid #2196F3;
    padding: 12px 16px;
    border-radius: 4px;
    margin-bottom: 8px;
}
.critical-badge { background:#dc3545; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.high-badge     { background:#fd7e14; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.medium-badge   { background:#ffc107; color:#212529; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.low-badge      { background:#28a745; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.status-badge   { background:#6c757d; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; }
.task-open      { border-left:4px solid #dc3545; }
.task-progress  { border-left:4px solid #fd7e14; }
.task-complete  { border-left:4px solid #28a745; }
</style>
""", unsafe_allow_html=True)

# ── Session State Initialization ─────────────────────────────────────────────
if "graph" not in st.session_state:
    st.session_state.graph = build_regulatory_change_graph(use_memory=True)

if "active_change" not in st.session_state:
    st.session_state.active_change = None

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "workflow_status" not in st.session_state:
    st.session_state.workflow_status = "idle"

if "change_register" not in st.session_state:
    # Seed with sample changes for demo
    st.session_state.change_register = _load_sample_register()

if "processing_log" not in st.session_state:
    st.session_state.processing_log = []


def _load_sample_register():
    """Load sample change register entries for demonstration."""
    try:
        fixtures_path = os.path.join("data", "fixtures", "sample_changes.json")
        with open(fixtures_path) as f:
            samples = json.load(f)
        # Convert to register entries
        register = {}
        for s in samples:
            entry = {
                **s,
                "impact_tier": "HIGH",
                "impact_score": 0.72,
                "primary_compliance_owner": "BSA_OFFICER" if s["regulatory_domain"] == "BSA_AML" else "CHIEF_COMPLIANCE_OFFICER",
                "is_applicable": True,
                "remediation_deadline": s.get("effective_date", "2025-12-31"),
                "task_count": 5,
                "case_status": "REMEDIATION_IN_PROGRESS",
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "human_review_completed": False,
            }
            register[s["change_id"]] = entry
        return register
    except Exception:
        return {}


def _load_policy_registry():
    """Load policy registry from fixtures."""
    try:
        with open(os.path.join("data", "fixtures", "policy_registry.json")) as f:
            return json.load(f)
    except Exception:
        return []


def _load_regulatory_sources():
    """Load regulatory sources from fixtures."""
    try:
        with open(os.path.join("data", "fixtures", "regulatory_sources.json")) as f:
            return json.load(f)
    except Exception:
        return []


def _impact_badge(tier: str) -> str:
    css = {"CRITICAL": "critical-badge", "HIGH": "high-badge",
           "MEDIUM": "medium-badge", "LOW": "low-badge"}.get(tier, "status-badge")
    return f'<span class="{css}">{tier}</span>'


def _days_label(date_str: str) -> str:
    """Return human-readable days until deadline."""
    if not date_str:
        return "N/A"
    try:
        target = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        days = (target - today).days
        if days < 0:
            return f"⚠️ {abs(days)}d overdue"
        elif days == 0:
            return "⚠️ Today"
        elif days <= 30:
            return f"🔴 {days}d"
        elif days <= 90:
            return f"🟡 {days}d"
        else:
            return f"🟢 {days}d"
    except Exception:
        return date_str


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📋 Reg Change Agent")
    st.markdown("*Regulatory Change Management*")
    st.divider()

    # Quick stats
    register = st.session_state.change_register
    critical_count = sum(1 for c in register.values() if c.get("impact_tier") == "CRITICAL")
    high_count = sum(1 for c in register.values() if c.get("impact_tier") == "HIGH")
    open_count = sum(1 for c in register.values() if c.get("case_status") == "REMEDIATION_IN_PROGRESS")

    st.metric("Active Changes", len(register))
    col1, col2 = st.columns(2)
    col1.metric("Critical", critical_count, delta=None)
    col2.metric("High", high_count, delta=None)
    st.metric("In Remediation", open_count)
    st.divider()

    # Workflow status indicator
    status = st.session_state.workflow_status
    status_color = {"idle": "🔵", "running": "🟡", "awaiting_review": "🟠",
                    "complete": "🟢", "error": "🔴"}.get(status, "⚪")
    st.markdown(f"**Workflow:** {status_color} {status.replace('_', ' ').title()}")

    if st.session_state.active_change:
        st.markdown(f"**Active:** `{st.session_state.active_change.get('change_id', 'N/A')}`")

    st.divider()
    st.markdown("**Quick Links**")
    st.markdown("- [FinCEN](https://www.fincen.gov)")
    st.markdown("- [OCC](https://www.occ.gov)")
    st.markdown("- [CFPB](https://www.consumerfinance.gov)")
    st.markdown("- [Federal Reserve](https://www.federalreserve.gov)")
    st.markdown("- [FDIC](https://www.fdic.gov)")
    st.markdown("- [SEC](https://www.sec.gov)")


# ── Main Tabs ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📥 Regulatory Feed",
    "🔍 Impact Analysis",
    "✅ Remediation Tracker",
    "📄 Policy Registry",
    "📋 Audit Trail",
    "⚙️ Configuration",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: REGULATORY FEED
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Regulatory Feed")
    st.caption("Submit regulatory changes for AI-powered impact analysis and remediation planning.")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("Submit New Regulatory Change")

        with st.form("new_change_form"):
            change_title = st.text_input(
                "Regulatory Change Title *",
                placeholder="E.g., FinCEN AML Program Effectiveness Final Rule",
            )
            col1, col2 = st.columns(2)
            regulatory_authority = col1.selectbox(
                "Issuing Authority *",
                ["FinCEN", "OCC", "Federal Reserve", "FDIC", "CFPB", "SEC", "FINRA",
                 "NCUA", "FATF", "State Banking Regulator", "Other"],
            )
            change_type = col2.selectbox(
                "Change Type *",
                [ct.value for ct in ChangeType],
                format_func=lambda x: x.replace("_", " ").title(),
            )
            regulatory_domain = st.selectbox(
                "Regulatory Domain *",
                [rd.value for rd in RegulatoryDomain],
                format_func=lambda x: x.replace("_", " ").title(),
            )
            col3, col4 = st.columns(2)
            publication_date = col3.date_input("Publication Date *", value=datetime.today())
            effective_date = col4.date_input(
                "Effective Date",
                value=datetime.today() + timedelta(days=180),
                help="Leave as today if already effective or unknown",
            )
            citation = st.text_input(
                "Regulatory Citation",
                placeholder="E.g., 31 CFR Part 1010, OCC Bulletin 2024-XX",
            )
            source_url = st.text_input(
                "Source URL",
                placeholder="https://www.fincen.gov/...",
            )
            summary_text = st.text_area(
                "Summary / Key Points *",
                height=120,
                placeholder="Paste the official summary or key points from the regulatory publication...",
            )
            full_text = st.text_area(
                "Full Text (optional — improves gap analysis quality)",
                height=200,
                placeholder="Paste the full regulatory text or relevant excerpts...",
            )

            submitted = st.form_submit_button("🚀 Analyze Regulatory Change", type="primary")

        if submitted and change_title and summary_text:
            # Build initial state
            initial_state: ChangeManagementState = {
                "change_title": change_title,
                "change_type": change_type,
                "regulatory_authority": regulatory_authority,
                "regulatory_domain": regulatory_domain,
                "publication_date": publication_date.isoformat(),
                "effective_date": effective_date.isoformat(),
                "citation": citation or "N/A",
                "source_url": source_url or "",
                "summary_text": summary_text,
                "full_text": full_text or "",
                "docket_number": None,
                "comment_deadline": None,
                "audit_trail": [],
                "completed_steps": [],
                "errors": [],
            }

            thread_id = str(uuid.uuid4())
            st.session_state.thread_id = thread_id
            st.session_state.workflow_status = "running"

            config = {"configurable": {"thread_id": thread_id}}

            with st.spinner("Analyzing regulatory change..."):
                try:
                    final_state = None
                    for event in st.session_state.graph.stream(initial_state, config):
                        for node_name, node_output in event.items():
                            st.session_state.processing_log.append({
                                "timestamp": datetime.utcnow().isoformat(),
                                "node": node_name,
                                "status": "completed",
                            })

                    # Check if paused at human_review_gate
                    snapshot = st.session_state.graph.get_state(config)
                    paused_at = snapshot.next

                    if paused_at and "human_review_gate" in paused_at:
                        st.session_state.workflow_status = "awaiting_review"
                        st.session_state.active_change = dict(snapshot.values)
                    else:
                        st.session_state.workflow_status = "complete"
                        st.session_state.active_change = dict(snapshot.values)

                    # Update change register
                    active = st.session_state.active_change
                    if active:
                        cid = active.get("change_id", f"REG-{thread_id[:8]}")
                        st.session_state.change_register[cid] = {
                            "change_id": cid,
                            "change_title": change_title,
                            "regulatory_authority": regulatory_authority,
                            "change_type": change_type,
                            "regulatory_domain": regulatory_domain,
                            "citation": citation,
                            "publication_date": publication_date.isoformat(),
                            "effective_date": effective_date.isoformat(),
                            "impact_tier": active.get("impact_tier", "MEDIUM"),
                            "impact_score": active.get("impact_score", 0.5),
                            "primary_compliance_owner": active.get("primary_compliance_owner", ""),
                            "is_applicable": active.get("is_applicable", True),
                            "remediation_deadline": active.get("remediation_deadline", ""),
                            "task_count": len(active.get("remediation_tasks", [])),
                            "case_status": active.get("case_status", "IN_PROGRESS"),
                            "last_updated": datetime.utcnow().isoformat() + "Z",
                            "human_review_completed": active.get("compliance_officer_decision") is not None,
                        }

                    st.rerun()
                except Exception as e:
                    st.error(f"Workflow error: {e}")
                    st.session_state.workflow_status = "error"
                    logger.exception(e)
        elif submitted:
            st.warning("Please fill in the required fields: Title, Summary, and select the Authority, Type, and Domain.")

    with col_right:
        st.subheader("Change Register")

        # Filter controls
        tier_filter = st.multiselect(
            "Filter by Impact",
            ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            default=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        )
        status_filter = st.multiselect(
            "Filter by Status",
            ["REMEDIATION_IN_PROGRESS", "PENDING_HUMAN_REVIEW", "CLOSED_COMPLIANT", "CLOSED_NOT_APPLICABLE"],
            default=["REMEDIATION_IN_PROGRESS", "PENDING_HUMAN_REVIEW"],
        )

        register = st.session_state.change_register
        filtered = [
            c for c in register.values()
            if c.get("impact_tier", "MEDIUM") in tier_filter
            and c.get("case_status", "") in status_filter
        ]

        if filtered:
            for change in sorted(filtered, key=lambda x: x.get("impact_score", 0), reverse=True):
                tier = change.get("impact_tier", "MEDIUM")
                days_label = _days_label(change.get("effective_date", ""))
                with st.expander(
                    f"{'🔴' if tier == 'CRITICAL' else '🟠' if tier == 'HIGH' else '🟡' if tier == 'MEDIUM' else '🟢'} "
                    f"{change.get('change_title', 'Unknown')[:55]}...",
                    expanded=False,
                ):
                    st.markdown(f"**Authority:** {change.get('regulatory_authority')} — {change.get('change_type', '').replace('_', ' ')}")
                    st.markdown(f"**Domain:** {change.get('regulatory_domain', '').replace('_', ' ')}")
                    st.markdown(f"**Impact:** {tier} ({change.get('impact_score', 0):.2f})")
                    st.markdown(f"**Effective:** {change.get('effective_date', 'TBD')} ({days_label})")
                    st.markdown(f"**Owner:** {change.get('primary_compliance_owner', 'TBD')}")
                    st.markdown(f"**Status:** `{change.get('case_status', 'N/A')}`")
                    if change.get("change_id") in st.session_state.change_register:
                        if st.button(f"Open Analysis", key=f"open_{change.get('change_id')}"):
                            st.session_state.active_change = change
        else:
            st.info("No changes match the current filters. Submit a new change above or adjust filters.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: IMPACT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Impact Analysis")

    active = st.session_state.active_change
    workflow_status = st.session_state.workflow_status

    if not active:
        st.info("No active regulatory change selected. Submit a change in the Regulatory Feed tab or select one from the register.")
        st.stop()

    change_id = active.get("change_id", "N/A")
    impact_tier = active.get("impact_tier", "MEDIUM")
    impact_score = active.get("impact_score", 0.0)

    # Header metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Change ID", change_id.split("-")[-1] if "-" in change_id else change_id)
    tier_colors = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
    col2.metric("Impact Tier", f"{tier_colors.get(impact_tier, '⚪')} {impact_tier}")
    col3.metric("Impact Score", f"{impact_score:.3f}")
    col4.metric(
        "Effective Date",
        active.get("effective_date", "TBD"),
        delta=_days_label(active.get("effective_date", "")).replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", ""),
    )

    st.markdown(f"**{active.get('change_title', 'Unknown')}**")
    st.markdown(f"*{active.get('regulatory_authority')} · {active.get('change_type', '').replace('_', ' ')} · {active.get('citation', '')}*")

    # ── HITL Review Panel ────────────────────────────────────────────────────
    if workflow_status == "awaiting_review":
        st.divider()
        st.subheader("⏸️ Compliance Officer Review Required")
        st.warning(
            f"This **{impact_tier}** impact regulatory change requires Compliance Officer review "
            "before proceeding to remediation planning. Review the gap analysis below and submit your decision."
        )

        with st.form("officer_review_form"):
            officer_id = st.text_input("Compliance Officer ID / Name *")
            decision = st.radio(
                "Decision *",
                ["APPROVED", "MODIFIED", "NOT_APPLICABLE", "ESCALATED"],
                horizontal=True,
                help="APPROVED: proceed as analyzed | MODIFIED: accept with changes | NOT_APPLICABLE: close case | ESCALATED: refer to senior management",
            )
            notes = st.text_area(
                "Review Notes",
                placeholder="Enter your review notes, modifications, or escalation rationale...",
            )
            submitted_review = st.form_submit_button("Submit Review Decision", type="primary")

        if submitted_review and officer_id:
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            st.session_state.graph.update_state(
                config,
                {
                    "compliance_officer_id": officer_id,
                    "compliance_officer_decision": decision,
                    "compliance_officer_notes": notes,
                },
                as_node="human_review_gate",
            )
            with st.spinner("Completing workflow..."):
                for event in st.session_state.graph.stream(None, config):
                    pass
            snapshot = st.session_state.graph.get_state(config)
            st.session_state.active_change = dict(snapshot.values)
            st.session_state.workflow_status = "complete"
            st.success(f"Review submitted: {decision}. Workflow complete.")
            st.rerun()
        elif submitted_review:
            st.warning("Please enter your Officer ID.")

    st.divider()

    # ── Score Breakdown ──────────────────────────────────────────────────────
    col_score, col_gap = st.columns([2, 3])

    with col_score:
        st.subheader("Impact Score Breakdown")
        components = active.get("impact_score_components", {})
        if components:
            labels = [k.replace("_score", "").replace("_", " ").title() for k in components]
            values = list(components.values())
            weights = [0.25, 0.25, 0.20, 0.15, 0.15]
            weighted = [v * w for v, w in zip(values, weights)]

            fig = go.Figure(go.Bar(
                x=values,
                y=labels,
                orientation="h",
                marker_color=["#dc3545" if v >= 0.85 else "#fd7e14" if v >= 0.65 else "#ffc107" if v >= 0.40 else "#28a745" for v in values],
                text=[f"{v:.2f}" for v in values],
                textposition="outside",
            ))
            fig.update_layout(
                height=250,
                margin=dict(l=0, r=40, t=20, b=20),
                xaxis=dict(range=[0, 1.1], title="Score"),
                yaxis=dict(title=""),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Weight table
            weight_data = {
                "Factor": labels,
                "Raw Score": [f"{v:.3f}" for v in values],
                "Weight": ["25%", "25%", "20%", "15%", "15%"],
                "Weighted": [f"{w:.3f}" for w in weighted],
            }
            import pandas as pd
            st.dataframe(pd.DataFrame(weight_data), use_container_width=True, hide_index=True)
        else:
            st.info("Impact score components will appear after analysis completes.")

        # Compliance window
        st.subheader("Compliance Window")
        adequate = active.get("compliance_window_adequate", True)
        complexity = active.get("implementation_complexity", "MODERATE")
        days_left = active.get("days_to_effective")

        st.markdown(f"**Implementation Complexity:** {complexity}")
        st.markdown(f"**Days to Effective Date:** {days_left or 'Unknown'}")
        if adequate:
            st.success("✅ Compliance window is adequate")
        else:
            st.error("⚠️ Compliance window is INADEQUATE — begin remediation immediately")

    with col_gap:
        st.subheader("Gap Analysis")
        gap_narrative = active.get("gap_analysis_narrative", "")
        if gap_narrative:
            st.markdown(gap_narrative)
        else:
            st.info("Gap analysis will appear here after the workflow processes the regulatory change.")

    # ── Policy Mapping ───────────────────────────────────────────────────────
    st.subheader("Mapped Policies")
    mapped = active.get("mapped_policies", [])
    if mapped:
        import pandas as pd
        df = pd.DataFrame(mapped)[["policy_id", "policy_name", "policy_owner", "last_review_date", "relevance_reason"]]
        df.columns = ["ID", "Policy Name", "Owner", "Last Review", "Relevance"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Policy mapping results will appear after analysis.")

    # ── Scope Summary ────────────────────────────────────────────────────────
    with st.expander("Scope Summary", expanded=False):
        col_a, col_b, col_c = st.columns(3)
        biz_lines = active.get("affected_business_lines", [])
        products = active.get("affected_products", [])
        ops = active.get("affected_operations", [])

        col_a.markdown("**Business Lines**")
        for bl in biz_lines:
            col_a.markdown(f"• {bl.replace('_', ' ').title()}")

        col_b.markdown("**Products**")
        for p in products[:10]:
            col_b.markdown(f"• {p.replace('_', ' ').title()}")

        col_c.markdown("**Operations**")
        for op in ops[:10]:
            col_c.markdown(f"• {op.replace('_', ' ').title()}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: REMEDIATION TRACKER
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Remediation Tracker")

    active = st.session_state.active_change

    if not active:
        st.info("Select or submit a regulatory change to view remediation tasks.")
        st.stop()

    tasks = active.get("remediation_tasks", [])
    remediation_deadline = active.get("remediation_deadline", "")
    estimated_effort = active.get("estimated_effort_hours", 0)

    col1, col2, col3, col4 = st.columns(4)
    open_tasks = sum(1 for t in tasks if t.get("status") == "OPEN")
    in_progress = sum(1 for t in tasks if t.get("status") == "IN_PROGRESS")
    complete = sum(1 for t in tasks if t.get("status") == "COMPLETE")

    col1.metric("Total Tasks", len(tasks))
    col2.metric("Open", open_tasks)
    col3.metric("In Progress", in_progress)
    col4.metric("Complete", complete)

    if remediation_deadline:
        st.metric(
            "Remediation Deadline",
            remediation_deadline,
            delta=_days_label(remediation_deadline),
        )

    if tasks:
        # Progress bar
        if len(tasks) > 0:
            progress = complete / len(tasks)
            st.progress(progress, text=f"Remediation Progress: {int(progress * 100)}%")

        st.subheader("Task List")
        for task in tasks:
            task_status = task.get("status", "OPEN")
            css_class = {"OPEN": "task-open", "IN_PROGRESS": "task-progress", "COMPLETE": "task-complete"}.get(task_status, "task-open")
            priority = task.get("priority", "MEDIUM")
            priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(priority, "⚪")

            with st.expander(
                f"{priority_icon} [{task.get('task_id')}] {task.get('task_description', 'Unknown task')[:70]}",
                expanded=False,
            ):
                col_a, col_b = st.columns(2)
                col_a.markdown(f"**Owner:** {task.get('task_owner', 'TBD')}")
                col_a.markdown(f"**Due Date:** {task.get('due_date', 'TBD')}")
                col_a.markdown(f"**Priority:** {priority}")
                col_b.markdown(f"**Status:** `{task_status}`")
                deps = task.get("dependencies", [])
                col_b.markdown(f"**Dependencies:** {', '.join(deps) if deps else 'None'}")
                if task.get("linked_gap_id"):
                    col_b.markdown(f"**Linked Gap:** {task.get('linked_gap_id')}")

                # Status update
                new_status = st.selectbox(
                    "Update Status",
                    ["OPEN", "IN_PROGRESS", "COMPLETE", "BLOCKED"],
                    index=["OPEN", "IN_PROGRESS", "COMPLETE", "BLOCKED"].index(task_status),
                    key=f"task_status_{task.get('task_id')}",
                )
                if new_status != task_status:
                    if st.button(f"Save", key=f"save_{task.get('task_id')}"):
                        for t in st.session_state.active_change.get("remediation_tasks", []):
                            if t.get("task_id") == task.get("task_id"):
                                t["status"] = new_status
                        st.success(f"Task {task.get('task_id')} updated to {new_status}")
                        st.rerun()

        st.divider()
        st.subheader("Remediation Plan Narrative")
        plan = active.get("remediation_plan_narrative", "")
        if plan:
            st.markdown(plan)
        else:
            st.info("Remediation plan narrative will appear after workflow completes.")

        if estimated_effort:
            st.metric("Estimated Total Effort", f"{estimated_effort} hours")
    else:
        st.info("Remediation tasks will appear after the workflow processes and analyzes the regulatory change.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: POLICY REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Policy Registry")
    st.caption("Institution's current policy inventory with regulatory citation mapping.")

    policies = _load_policy_registry()

    if policies:
        import pandas as pd

        # Summary by domain
        domains = {}
        for p in policies:
            d = p.get("domain", "OTHER")
            domains[d] = domains.get(d, 0) + 1

        # Domain distribution chart
        fig = px.bar(
            x=list(domains.keys()),
            y=list(domains.values()),
            labels={"x": "Domain", "y": "Policy Count"},
            title="Policies by Regulatory Domain",
            color=list(domains.values()),
            color_continuous_scale="Blues",
        )
        fig.update_layout(height=300, margin=dict(t=40, b=20), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Policy table
        st.subheader("All Policies")
        search = st.text_input("Search policies", placeholder="Search by name, owner, or citation...")
        domain_filter = st.multiselect(
            "Filter by Domain",
            list(set(p.get("domain", "") for p in policies)),
            default=[],
            format_func=lambda x: x.replace("_", " ").title(),
        )

        filtered_policies = [
            p for p in policies
            if (not search or search.lower() in p.get("name", "").lower()
                or search.lower() in p.get("owner", "").lower()
                or any(search.lower() in c.lower() for c in p.get("regulatory_citations", [])))
            and (not domain_filter or p.get("domain") in domain_filter)
        ]

        for policy in filtered_policies:
            status = policy.get("status", "CURRENT")
            status_icon = "✅" if status == "CURRENT" else "⚠️" if status == "NEEDS_REVIEW" else "🔴"
            with st.expander(
                f"{status_icon} [{policy.get('policy_id')}] {policy.get('name')}",
                expanded=False,
            ):
                col_a, col_b = st.columns(2)
                col_a.markdown(f"**Owner:** {policy.get('owner', 'N/A')}")
                col_a.markdown(f"**Domain:** {policy.get('domain', 'N/A').replace('_', ' ')}")
                col_a.markdown(f"**Version:** {policy.get('version', 'N/A')}")
                col_a.markdown(f"**Status:** {status}")
                col_b.markdown(f"**Last Review:** {policy.get('last_review_date', 'N/A')}")
                col_b.markdown(f"**Next Review:** {policy.get('next_review_date', 'N/A')}")
                col_b.markdown(f"**Board Approved:** {'✅' if policy.get('board_approved') else '❌'}")

                citations = policy.get("regulatory_citations", [])
                if citations:
                    st.markdown("**Regulatory Citations:**")
                    for c in citations:
                        st.markdown(f"  • {c}")
    else:
        st.warning("Policy registry not loaded. Check data/fixtures/policy_registry.json.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: AUDIT TRAIL
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("Audit Trail")
    st.caption("Append-only log of all workflow actions and decisions. Required for FFIEC examination evidence.")

    active = st.session_state.active_change
    audit_trail = active.get("audit_trail", []) if active else []

    if audit_trail:
        col1, col2 = st.columns([3, 1])
        col1.metric("Audit Entries", len(audit_trail))
        col2.metric("LLM Invocations", sum(1 for e in audit_trail if e.get("ai_model_used")))

        st.subheader(f"Change: {active.get('change_id', 'N/A')}")

        for i, entry in enumerate(reversed(audit_trail)):
            with st.expander(
                f"[{entry.get('timestamp', '')[:19]}] {entry.get('node', 'unknown')} — {entry.get('action', '')[:80]}",
                expanded=(i == 0),
            ):
                col_a, col_b = st.columns(2)
                col_a.markdown(f"**Node:** `{entry.get('node')}`")
                col_a.markdown(f"**Actor:** {entry.get('actor', 'ai_agent')}")
                col_a.markdown(f"**Timestamp:** {entry.get('timestamp')}")
                col_b.markdown(f"**LLM Used:** {'Yes — ' + entry.get('ai_model_used', '') if entry.get('ai_model_used') else 'No'}")
                col_b.markdown(f"**Human Review Required:** {entry.get('human_review_required', False)}")

                if entry.get("regulatory_basis"):
                    st.markdown(f"**Regulatory Basis:** {entry.get('regulatory_basis')}")

                data_sources = entry.get("data_sources_accessed", [])
                if data_sources:
                    st.markdown(f"**Data Sources:** {', '.join(data_sources)}")

                st.markdown(f"**Action:** {entry.get('action', '')}")
    else:
        st.info("Audit trail entries will appear after a regulatory change has been processed.")

    # Export button
    if audit_trail:
        audit_json = json.dumps(audit_trail, indent=2)
        st.download_button(
            "📥 Export Audit Trail (JSON)",
            data=audit_json,
            file_name=f"audit_{active.get('change_id', 'unknown')}_{datetime.utcnow().strftime('%Y%m%d')}.json",
            mime="application/json",
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6: CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("Configuration")
    st.caption("Manage regulatory sources, routing rules, and impact scoring thresholds.")

    config_tab1, config_tab2, config_tab3 = st.tabs(["Regulatory Sources", "Routing Matrix", "Impact Thresholds"])

    with config_tab1:
        st.subheader("Regulatory Sources")
        sources = _load_regulatory_sources()

        active_sources = [s for s in sources if s.get("active")]
        inactive_sources = [s for s in sources if not s.get("active")]

        st.metric("Active Sources", len(active_sources))

        for source in sources:
            status_icon = "🟢" if source.get("active") else "⚪"
            with st.expander(
                f"{status_icon} {source.get('authority')} — {source.get('full_name')}",
                expanded=False,
            ):
                col_a, col_b = st.columns(2)
                col_a.markdown(f"**Tier:** {source.get('tier', 'N/A')}")
                col_a.markdown(f"**Type:** {source.get('regulator_type', 'N/A')}")
                col_a.markdown(f"**Poll Frequency:** Every {source.get('poll_frequency_hours', 24)} hours")
                col_b.markdown(f"**Active:** {'Yes' if source.get('active') else 'No'}")
                domains = source.get("primary_domains", [])
                col_b.markdown(f"**Domains:** {', '.join(d.replace('_', ' ') for d in domains)}")
                if source.get("feed_url"):
                    st.markdown(f"**Feed URL:** `{source.get('feed_url')}`")
                if source.get("notes"):
                    st.info(source.get("notes"))

    with config_tab2:
        st.subheader("Compliance Routing Matrix")
        try:
            with open(os.path.join("data", "fixtures", "routing_matrix.json")) as f:
                routing_data = json.load(f)

            for domain, config in routing_data.items():
                if domain == "OTHER":
                    continue
                with st.expander(domain.replace("_", " ").title(), expanded=False):
                    col_a, col_b = st.columns(2)
                    col_a.markdown(f"**Primary Owner:** {config.get('primary')}")
                    col_a.markdown(f"**Secondary Owners:** {', '.join(config.get('secondary', []))}")
                    col_b.markdown(f"**Business Units:** {', '.join(config.get('business_units', []))}")
                    col_b.markdown(f"**Board Notification:** {config.get('board_notification_threshold', 'CRITICAL')} and above")
        except Exception:
            st.warning("Routing matrix not loaded. Check data/fixtures/routing_matrix.json.")

    with config_tab3:
        st.subheader("Impact Scoring Thresholds")
        st.info(
            "Impact tier thresholds are configurable here. Changing these affects how regulatory changes "
            "are classified and whether HITL review is triggered. Document all changes per SR 11-7 model risk management requirements."
        )

        col1, col2 = st.columns(2)
        critical_threshold = col1.slider("CRITICAL Threshold", 0.70, 0.95, 0.85, 0.01,
                                          help="Scores ≥ this value are CRITICAL")
        high_threshold = col2.slider("HIGH Threshold", 0.50, 0.84, 0.65, 0.01,
                                      help="Scores ≥ this value are HIGH")

        st.caption(
            f"Current: CRITICAL ≥ {critical_threshold:.2f} · HIGH ≥ {high_threshold:.2f} · "
            f"MEDIUM ≥ 0.40 · LOW < 0.40"
        )

        st.subheader("Component Weights (SR 11-7 Documentation)")
        st.info("These weights are fixed in code per SR 11-7 model risk management requirements. Changes require model validation and CCO approval.")

        weights_data = {
            "Factor": ["Authority Tier", "Deadline Urgency", "Scope Breadth", "Policy Depth", "Remediation Complexity"],
            "Weight": ["25%", "25%", "20%", "15%", "15%"],
            "Rationale": [
                "Primary regulator has highest enforcement authority",
                "Shorter implementation windows require immediate action",
                "More business lines = greater operational impact",
                "Number of policies requiring update",
                "System/process changes take more time and resources",
            ],
        }
        import pandas as pd
        st.dataframe(pd.DataFrame(weights_data), use_container_width=True, hide_index=True)

        st.subheader("API Keys")
        st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""),
                      help="Stored in environment variable OPENAI_API_KEY")
        st.caption("API keys are managed via environment variables and are not stored in the application.")
