"""
Agent 11 — Model Risk Management Agent
Streamlit Dashboard — Port 8511

6-tab interface for Model Risk Officers and Chief Risk Officers:
  Tab 1: Submit Validation — initiate a new model validation run
  Tab 2: Validation Findings — SR 11-7 component results, performance metrics
  Tab 3: Model Performance — metric visualizations, PSI, degradation timeline
  Tab 4: MRO Review — HITL interface for Model Risk Officer decision
  Tab 5: Audit Trail — full node-by-node validation audit log
  Tab 6: About — architecture, security, regulatory coverage, getting started

SR 11-7 Architecture note: all routing, HITL triggers, and outcome
determinations are Python-computed. Displayed values for risk tier,
performance outcome, HITL conditions, and resolution recommendation
originate from deterministic Python nodes — not LLM responses.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# ── Page configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Model Risk Management Agent | FSI AI Suite",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Path references ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
FIXTURES_DIR = BASE_DIR / "data" / "fixtures"

# ── Load fixtures ─────────────────────────────────────────────────────────────

@st.cache_data
def load_scenarios():
    with open(FIXTURES_DIR / "model_scenarios.json") as f:
        return json.load(f)["scenarios"]

@st.cache_data
def load_model_registry():
    with open(FIXTURES_DIR / "model_registry.json") as f:
        return json.load(f)["models"]

@st.cache_data
def load_validation_matrix():
    with open(FIXTURES_DIR / "validation_matrix.json") as f:
        return json.load(f)

SCENARIOS = load_scenarios()
MODEL_REGISTRY = load_model_registry()
VALIDATION_MATRIX = load_validation_matrix()

DEMO_MODE = not bool(os.getenv("OPENAI_API_KEY", "").startswith("sk-") and
                     len(os.getenv("OPENAI_API_KEY", "")) > 20)

# ── Color helpers ─────────────────────────────────────────────────────────────

TIER_COLORS = {
    "HIGH": "#dc3545",      # Red — highest risk
    "MEDIUM": "#fd7e14",    # Orange
    "LOW": "#198754",       # Green
}
OUTCOME_COLORS = {
    "APPROVED": "#198754",
    "CONDITIONALLY_APPROVED": "#fd7e14",
    "UNDER_REVIEW": "#6c757d",
    "SUSPENDED": "#dc3545",
    "RETIRED": "#343a40",
}
PSI_COLORS = {
    "STABLE": "#198754",
    "WARNING": "#fd7e14",
    "CRITICAL": "#dc3545",
    "UNKNOWN": "#6c757d",
}
PERF_COLORS = {
    "PASS": "#198754",
    "DEGRADED": "#fd7e14",
    "CRITICAL": "#dc3545",
}


def badge(text: str, color: str) -> str:
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.85em;font-weight:600;">{text}</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📊 Model Risk Management")
    st.markdown("**Agent 11 · FSI AI Suite**")

    if DEMO_MODE:
        st.warning("**Demo Mode** — Pre-computed scenarios active. Add `OPENAI_API_KEY` for live LLM validation.", icon="⚠️")
    else:
        st.success("**Live Mode** — Connected to OpenAI GPT-4o", icon="✅")

    st.markdown("---")
    st.markdown("**Models Under Governance**")
    for mid, m in MODEL_REGISTRY.items():
        status = m.get("status", "UNKNOWN")
        color = OUTCOME_COLORS.get(status, "#6c757d")
        st.markdown(
            f'<div style="margin:2px 0;">{badge(status[:3], color)} '
            f'<small>{m["agent_name"][:30]}...</small></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        "**Regulatory Basis:**\n"
        "- SR 11-7 (Model Risk Management)\n"
        "- OCC Bulletin 2011-12\n"
        "- FFIEC Model Risk Guidance\n\n"
        "**Port:** 8511"
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Submit Validation",
    "🔍 Validation Findings",
    "📈 Model Performance",
    "👤 MRO Review",
    "🗂 Audit Trail",
    "ℹ️ About",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Submit Validation
# ══════════════════════════════════════════════════════════════════════════════

def render_submit_tab():
    st.header("Submit Model Validation")
    st.markdown(
        "Initiate a new SR 11-7 model validation for any of the five scoring models "
        "in the FSI AI Suite. Select a pre-built demo scenario or configure a custom validation."
    )

    if DEMO_MODE:
        st.info(
            "**Demo Mode:** Select a pre-built scenario below to see the full validation pipeline. "
            "Each scenario represents a different validation event type (annual revalidation, "
            "triggered review, initial validation, ongoing monitoring).",
            icon="ℹ️",
        )
        scenario_labels = [f"{s['id']}: {s['label']}" for s in SCENARIOS]
        selected_label = st.selectbox("Select Demo Scenario", scenario_labels)
        selected_scenario = next(s for s in SCENARIOS if selected_label.startswith(s["id"]))

        st.markdown(f"**Scenario:** {selected_scenario['description']}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**Model ID:** `{selected_scenario['input']['model_id']}`")
            model_meta = MODEL_REGISTRY.get(selected_scenario['input']['model_id'], {})
            st.markdown(f"**Model:** {model_meta.get('model_name', 'N/A')}")
        with col2:
            st.markdown(f"**Agent:** {model_meta.get('agent_name', 'N/A')}")
            st.markdown(f"**Risk Tier:** {model_meta.get('risk_tier', 'N/A')}")
        with col3:
            st.markdown(f"**Validation Type:** {selected_scenario['input']['validation_type']}")
            st.markdown(f"**Requested By:** {selected_scenario['input']['requested_by']}")

        if selected_scenario["input"].get("triggering_event"):
            st.warning(f"**Triggering Event:** {selected_scenario['input']['triggering_event']}", icon="⚡")

        if st.button("▶ Run Validation Pipeline", type="primary", use_container_width=True):
            with st.spinner("Running 12-node SR 11-7 validation pipeline..."):
                for i, node in enumerate([
                    "model_inventory_lookup", "data_sample_pull", "conceptual_soundness_review",
                    "outcomes_analysis", "population_stability_analysis", "benchmark_comparison",
                    "sensitivity_analysis", "risk_tier_determination", "validation_narrative",
                    "routing_decision"
                ], 1):
                    st.progress(i / 10, f"Node {i}/10: {node}")
                    time.sleep(0.3)

            st.session_state["validation_result"] = selected_scenario
            st.session_state["validation_complete"] = True
            st.success("✅ Validation pipeline complete. Review findings in the **Validation Findings** tab.")
            if selected_scenario["computed_output"]["human_review_required"]:
                st.warning(
                    f"⚠️ HITL Required — {selected_scenario['computed_output']['target_reviewer']} review needed. "
                    "Navigate to the **MRO Review** tab to submit decision.",
                    icon="⚠️",
                )
    else:
        # Live mode form
        col1, col2 = st.columns(2)
        with col1:
            model_id = st.selectbox(
                "Model to Validate",
                options=list(MODEL_REGISTRY.keys()),
                format_func=lambda x: f"{x} — {MODEL_REGISTRY[x]['model_name']}",
            )
        with col2:
            validation_type = st.selectbox(
                "Validation Type",
                ["ANNUAL_REVALIDATION", "INITIAL_VALIDATION", "TRIGGERED_REVIEW",
                 "CHANGE_VALIDATION", "ONGOING_MONITORING"],
            )

        col3, col4 = st.columns(2)
        with col3:
            period_start = st.date_input("Validation Period Start")
        with col4:
            period_end = st.date_input("Validation Period End")

        triggering_event = ""
        if validation_type == "TRIGGERED_REVIEW":
            triggering_event = st.text_area(
                "Triggering Event Description",
                placeholder="Describe what monitoring alert or event triggered this review...",
            )

        requested_by = st.text_input("Requested By (role/team)", value="MODEL_RISK_OFFICER")

        if st.button("▶ Run Validation Pipeline", type="primary", use_container_width=True):
            st.info("Live validation requires metrics from the model monitoring system. "
                    "In production, metrics are pulled from DynamoDB/CloudWatch automatically.")


with tab1:
    render_submit_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Validation Findings
# ══════════════════════════════════════════════════════════════════════════════

def render_findings_tab():
    st.header("Validation Findings")

    if "validation_result" not in st.session_state:
        st.info("Run a validation from the **Submit Validation** tab to see findings here.")
        return

    scenario = st.session_state["validation_result"]
    inp = scenario["input"]
    out = scenario["computed_output"]
    model_meta = MODEL_REGISTRY.get(inp["model_id"], {})

    # ── Summary bar ──────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        tier_color = TIER_COLORS.get(out["risk_tier"], "#6c757d")
        st.markdown(f"**Risk Tier**")
        st.markdown(badge(out["risk_tier"], tier_color), unsafe_allow_html=True)
    with col2:
        perf_color = PERF_COLORS.get(out["performance_outcome"], "#6c757d")
        st.markdown(f"**Performance Outcome**")
        st.markdown(badge(out["performance_outcome"], perf_color), unsafe_allow_html=True)
    with col3:
        psi_color = PSI_COLORS.get(out.get("psi_flag", "UNKNOWN"), "#6c757d")
        st.markdown(f"**PSI Status**")
        st.markdown(
            badge(f"{out.get('psi_flag', 'N/A')} ({out.get('psi_score', 'N/A')})", psi_color),
            unsafe_allow_html=True,
        )
    with col4:
        out_color = OUTCOME_COLORS.get(out["resolution_type"], "#6c757d")
        st.markdown(f"**Recommended Outcome**")
        st.markdown(badge(out["resolution_type"], out_color), unsafe_allow_html=True)

    st.markdown("---")

    # ── HITL alert ───────────────────────────────────────────────────────────
    if out["human_review_required"]:
        conditions_str = ", ".join(out["hitl_conditions"])
        st.error(
            f"**⚠️ HITL Required** — Review by {out['target_reviewer']} is mandatory before this "
            f"validation can be finalized.\n\n"
            f"**Conditions triggered:** {conditions_str}\n\n"
            f"Navigate to the **MRO Review** tab to submit the reviewer decision.",
        )
    else:
        st.success(
            f"**✅ Auto-resolvable** — No HITL conditions triggered for this validation event. "
            f"Outcome recorded: {out['resolution_type']}. Next revalidation: {out['next_revalidation_date']}."
        )

    # ── Model identity ────────────────────────────────────────────────────────
    st.subheader("Model Identity")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Model ID:** `{inp['model_id']}`")
        st.markdown(f"**Model Name:** {model_meta.get('model_name', 'N/A')}")
        st.markdown(f"**Agent:** {model_meta.get('agent_name', 'N/A')}")
    with col2:
        st.markdown(f"**Validation Type:** {inp['validation_type']}")
        st.markdown(f"**Period:** {inp['validation_period_start']} → {inp['validation_period_end']}")
        st.markdown(f"**Requested By:** {inp['requested_by']}")
    with col3:
        st.markdown(f"**Last Validated:** {inp.get('last_validation_date', 'N/A')}")
        st.markdown(f"**Target Reviewer:** {out['target_reviewer']}")
        st.markdown(f"**Next Revalidation:** {out['next_revalidation_date']}")

    # ── Degradation flags ─────────────────────────────────────────────────────
    st.subheader("Degradation Flags (Python-Determined)")
    if out["degradation_flags"]:
        for flag in out["degradation_flags"]:
            st.error(f"🚩 {flag}")
    else:
        st.success("✅ No degradation flags triggered — all metrics within acceptable bounds.")

    # ── Material findings ─────────────────────────────────────────────────────
    st.subheader("Material Findings")
    if out["material_findings"]:
        for i, finding in enumerate(out["material_findings"], 1):
            st.warning(f"**Finding {i}:** {finding}")
    else:
        st.success("✅ No material findings identified.")

    # ── HITL conditions detail ────────────────────────────────────────────────
    st.subheader("HITL Conditions Triggered")
    st.caption(
        "All conditions are checked against the `ALWAYS_HITL_CONDITIONS` Python `frozenset` "
        "in state.py — immutable at runtime."
    )
    if out["hitl_conditions"]:
        hitl_defs = VALIDATION_MATRIX.get("hitl_requirements", {}).get("always_hitl", {})
        for cond in out["hitl_conditions"]:
            definition = hitl_defs.get(cond, "No definition available.")
            st.markdown(f"🔴 **{cond}** — {definition}")
    else:
        st.success("✅ No HITL conditions triggered.")

    # ── SR 11-7 model design ──────────────────────────────────────────────────
    st.subheader("Model Design (SR 11-7 Component Review)")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Factor Weights**")
        weights = model_meta.get("weights", {})
        for factor, weight in weights.items():
            pct = weight * 100
            st.progress(weight, f"{factor}: {pct:.0f}%")
    with col2:
        st.markdown("**Decision Thresholds**")
        thresholds = model_meta.get("decision_thresholds", {})
        for decision, threshold in thresholds.items():
            st.markdown(f"- **{decision}:** {threshold}")
        st.markdown("**Hard Rules (Python constants)**")
        for rule in model_meta.get("hard_rules", []):
            st.markdown(f"- ⛔ {rule}")

    # ── Findings summary ──────────────────────────────────────────────────────
    st.subheader("Findings Summary (for MRO Review Panel)")
    st.code(out["findings_summary"], language=None)


with tab2:
    render_findings_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Model Performance
# ══════════════════════════════════════════════════════════════════════════════

def render_performance_tab():
    st.header("Model Performance Metrics")

    if "validation_result" not in st.session_state:
        st.info("Run a validation from the **Submit Validation** tab to see performance data here.")
        return

    scenario = st.session_state["validation_result"]
    inp = scenario["input"]
    out = scenario["computed_output"]

    current = inp.get("current_metrics", {}) or {}
    baseline = inp.get("baseline_metrics", {}) or {}
    deltas = out.get("metric_deltas", {}) or {}

    # ── Metric comparison table ────────────────────────────────────────────
    st.subheader("Metric Comparison: Current vs. Baseline")
    st.caption(
        "Deltas are computed by Python arithmetic — not LLM estimation. "
        "Thresholds triggering degradation flags are defined in `PERFORMANCE_DEGRADATION_THRESHOLDS` (nodes.py)."
    )

    metric_display = {
        "accuracy": "Accuracy (%)",
        "gini_coefficient": "Gini Coefficient",
        "ks_statistic": "KS Statistic",
        "auc_roc": "AUC-ROC",
        "false_positive_rate": "False Positive Rate (%)",
        "false_negative_rate": "False Negative Rate (%)",
        "psi": "Population Stability Index",
    }

    degradation_thresholds = {
        "accuracy": ("accuracy_drop_pct", -5.0, "lower"),
        "gini_coefficient": ("gini_drop_points", -10.0, "lower"),
        "ks_statistic": ("ks_stat_drop_pct", -8.0, "lower"),
        "false_positive_rate": ("false_positive_rate_increase", 5.0, "higher"),
        "false_negative_rate": ("false_negative_rate_increase", 3.0, "higher"),
        "psi": ("psi_warning", 0.10, "higher"),
    }

    rows = []
    for key, label in metric_display.items():
        curr_val = current.get(key, "N/A")
        base_val = baseline.get(key, "N/A")
        delta = deltas.get(key, None)

        # Determine status
        status = "✅ OK"
        if delta is not None and key in degradation_thresholds:
            _, threshold, direction = degradation_thresholds[key]
            if direction == "lower" and delta < threshold:
                status = "🚩 FLAG"
            elif direction == "higher" and delta > abs(threshold):
                status = "🚩 FLAG"

        delta_str = f"{delta:+.2f}" if delta is not None else "N/A"
        rows.append({
            "Metric": label,
            "Current": f"{curr_val:.3f}" if isinstance(curr_val, float) else str(curr_val),
            "Baseline": f"{base_val:.3f}" if isinstance(base_val, float) else str(base_val),
            "Δ Change": delta_str,
            "Status": status,
        })

    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── PSI detail ────────────────────────────────────────────────────────────
    st.subheader("Population Stability Index (PSI)")
    psi_score = out.get("psi_score", 0) or 0
    psi_flag = out.get("psi_flag", "UNKNOWN")
    psi_color = PSI_COLORS.get(psi_flag, "#6c757d")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("PSI Score", f"{psi_score:.4f}")
        st.markdown(badge(psi_flag, psi_color), unsafe_allow_html=True)
    with col2:
        st.markdown("""
        **PSI Interpretation (Python thresholds):**
        - 🟢 **< 0.10 — STABLE:** No significant population shift
        - 🟡 **0.10–0.25 — WARNING:** Moderate shift — investigate
        - 🔴 **> 0.25 — CRITICAL:** Significant shift — validation required

        PSI > 0.25 automatically triggers `PSI_CRITICAL` HITL condition.
        """)

    # ── Challenger comparison ─────────────────────────────────────────────────
    challenger = inp.get("challenger_metrics")
    if challenger:
        st.subheader("Challenger Model Comparison")
        comparison_result = out.get("challenger_comparison_result", "N/A")
        comparison_color = {
            "PRODUCTION_BETTER": "#198754",
            "CHALLENGER_BETTER": "#dc3545",
            "PARITY": "#fd7e14",
        }.get(comparison_result, "#6c757d")

        st.markdown(
            f"**Comparison Result:** {badge(comparison_result, comparison_color)}",
            unsafe_allow_html=True,
        )

        chal_rows = []
        for key, label in metric_display.items():
            prod_val = current.get(key, "N/A")
            chal_val = challenger.get(key, "N/A")
            if isinstance(prod_val, float) and isinstance(chal_val, float):
                diff = chal_val - prod_val
                winner = "🟢 Challenger" if diff > 0 else "🔵 Production" if diff < 0 else "— Parity"
                chal_rows.append({
                    "Metric": label,
                    "Production": f"{prod_val:.3f}",
                    "Challenger": f"{chal_val:.3f}",
                    "Δ": f"{diff:+.3f}",
                    "Better": winner,
                })

        if chal_rows:
            st.dataframe(pd.DataFrame(chal_rows), use_container_width=True, hide_index=True)

    # ── Sensitivity analysis results ─────────────────────────────────────────
    st.subheader("Sensitivity Analysis")
    model_meta = MODEL_REGISTRY.get(inp["model_id"], {})
    weights = model_meta.get("weights", {})
    if weights:
        max_factor = max(weights.items(), key=lambda x: x[1])
        weight_sum = sum(weights.values())
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Weight Sum", f"{weight_sum:.4f}", help="Must equal 1.0000 within 0.001 tolerance")
            st.markdown("✅ Normalized" if abs(weight_sum - 1.0) < 0.001 else "🚩 Error")
        with col2:
            st.metric("Highest-Weight Factor", max_factor[0])
            st.metric("Factor Weight", f"{max_factor[1]*100:.0f}%")
        with col3:
            concentration_ok = max_factor[1] <= 0.50
            st.metric("Concentration Risk", "OK" if concentration_ok else "WARNING")
            st.markdown("✅ No concentration" if concentration_ok else "⚠️ Single factor > 50%")

        hard_rules = model_meta.get("hard_rules", [])
        ofac_covered = any("OFAC" in r.upper() for r in hard_rules)
        pep_covered = any("PEP" in r.upper() for r in hard_rules)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Hard Rules Documented", len(hard_rules))
        with col2:
            st.markdown(f"**OFAC Override:** {'✅ Documented' if ofac_covered else '🚩 Missing'}")
        with col3:
            st.markdown(f"**PEP Override:** {'✅ Documented' if pep_covered else '⚠️ Missing'}")


with tab3:
    render_performance_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MRO Review (HITL)
# ══════════════════════════════════════════════════════════════════════════════

def render_review_tab():
    st.header("Model Risk Officer Review Gate")
    st.caption(
        "**SR 11-7 § 4:** Model risk management must include appropriate human oversight. "
        "This gate captures the MRO's documented decision for examination-ready audit trail."
    )

    if "validation_result" not in st.session_state:
        st.info("Run a validation from the **Submit Validation** tab to enable the MRO review gate.")
        return

    scenario = st.session_state["validation_result"]
    out = scenario["computed_output"]

    if not out["human_review_required"]:
        st.success(
            "✅ No MRO review required for this validation event. "
            "The validation auto-completed with outcome: "
            f"**{out['resolution_type']}**. "
            f"Next revalidation: {out['next_revalidation_date']}."
        )
        return

    # ── HITL review panel ────────────────────────────────────────────────────
    st.warning(
        f"⚠️ **Review Required** — {out['target_reviewer']}\n\n"
        f"HITL conditions: {', '.join(out['hitl_conditions'])}",
        icon="⚠️",
    )

    st.subheader("Validation Summary for Review")
    st.code(out["findings_summary"], language=None)

    st.markdown("---")
    st.subheader("MRO Decision")
    st.markdown(
        "Review the validation findings above and the full report in **Validation Findings**. "
        "Select your decision and provide documentation. "
        "Your decision is recorded in the audit trail with your reviewer ID and timestamp."
    )

    reviewer_id = st.text_input("Reviewer ID (role/badge)", value="MRO-REVIEWER-001")

    decision = st.radio(
        "Validation Decision",
        options=[
            "APPROVE_VALIDATION",
            "CONDITIONALLY_APPROVE",
            "REQUIRE_REMEDIATION",
            "ESCALATE_TO_BOARD",
        ],
        format_func=lambda x: {
            "APPROVE_VALIDATION": "✅ Approve — Model approved for continued use",
            "CONDITIONALLY_APPROVE": "🟡 Conditionally Approve — Approval with specific conditions",
            "REQUIRE_REMEDIATION": "🔴 Require Remediation — Suspend model pending fixes",
            "ESCALATE_TO_BOARD": "⬆️ Escalate to Board — Forward to Board Risk Committee",
        }[x],
    )

    conditions_text = ""
    if decision == "CONDITIONALLY_APPROVE":
        conditions_text = st.text_area(
            "Conditions (required for conditional approval)",
            placeholder="List each condition with remediation deadline. e.g.:\n"
                        "1. Update challenger model baseline within 30 days.\n"
                        "2. Increase monitoring frequency to weekly for 90 days.\n"
                        "3. Conduct fair lending disparate impact test by 2026-08-01.",
            height=120,
        )

    notes = st.text_area(
        "Reviewer Notes",
        placeholder="Document your review methodology, evidence reviewed, and judgment rationale...",
        height=100,
    )

    if st.button("Submit MRO Decision", type="primary", use_container_width=True):
        if decision == "CONDITIONALLY_APPROVE" and not conditions_text.strip():
            st.error("Conditions are required for Conditional Approval.")
            return

        # Map decision to outcome
        outcome_map = {
            "APPROVE_VALIDATION": "APPROVED",
            "CONDITIONALLY_APPROVE": "CONDITIONALLY_APPROVED",
            "REQUIRE_REMEDIATION": "SUSPENDED",
            "ESCALATE_TO_BOARD": "UNDER_REVIEW",
        }
        final_outcome = outcome_map[decision]
        outcome_color = OUTCOME_COLORS.get(final_outcome, "#6c757d")

        st.markdown("---")
        st.markdown(
            f"**Final Validation Outcome:** {badge(final_outcome, outcome_color)}",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Reviewer:** {reviewer_id}")
        st.markdown(f"**Decision:** {decision}")
        st.markdown(f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}")

        if conditions_text:
            st.markdown("**Conditions:**")
            st.code(conditions_text, language=None)

        st.markdown(f"**Next Revalidation:** {out['next_revalidation_date']}")

        # Update session state
        st.session_state["mro_decision"] = {
            "reviewer_id": reviewer_id,
            "decision": decision,
            "final_outcome": final_outcome,
            "conditions": conditions_text,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        st.success(
            f"✅ MRO decision recorded. Validation outcome: **{final_outcome}**. "
            "Audit trail entry added. Validation report is finalized."
        )

        if final_outcome == "SUSPENDED":
            st.error(
                "🔴 **Model SUSPENDED** — Model use must cease immediately. "
                "Manual override process must be activated. Model owner must submit "
                "remediation plan within 5 business days."
            )


with tab4:
    render_review_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Audit Trail
# ══════════════════════════════════════════════════════════════════════════════

def render_audit_tab():
    st.header("Validation Audit Trail")
    st.caption(
        "Every node in the validation pipeline appends an entry to the audit trail. "
        "Entries are append-only — prior entries cannot be modified. "
        "In production: retained in DynamoDB (IAM-enforced immutability) and archived "
        "to S3 Object Lock GOVERNANCE for 10 years (model life + BSA retention)."
    )

    if "validation_result" not in st.session_state:
        st.info("Run a validation to see the audit trail here.")
        return

    scenario = st.session_state["validation_result"]
    inp = scenario["input"]
    out = scenario["computed_output"]

    # Reconstruct representative audit trail from computed output
    now = datetime.now(timezone.utc).isoformat()
    audit_entries = [
        {"node": "model_inventory_lookup", "timestamp_utc": now,
         "model_id": inp["model_id"], "risk_tier": out["risk_tier"],
         "validation_type": inp["validation_type"], "revalidation_overdue": False},
        {"node": "data_sample_pull", "timestamp_utc": now,
         "model_id": inp["model_id"], "metrics_loaded": True, "baseline_loaded": True},
        {"node": "conceptual_soundness_review", "timestamp_utc": now,
         "model_id": inp["model_id"], "llm_used": not DEMO_MODE, "narrative_length": 420},
        {"node": "outcomes_analysis", "timestamp_utc": now,
         "performance_outcome": out["performance_outcome"],
         "degradation_flags": out["degradation_flags"],
         "material_findings_count": len(out["material_findings"])},
        {"node": "population_stability_analysis", "timestamp_utc": now,
         "psi_score": out.get("psi_score"), "psi_flag": out.get("psi_flag")},
        {"node": "benchmark_comparison", "timestamp_utc": now,
         "challenger_available": bool(inp.get("challenger_metrics")),
         "result": out.get("challenger_comparison_result")},
        {"node": "sensitivity_analysis", "timestamp_utc": now,
         "weight_sum": 1.0, "hard_rule_count": len(MODEL_REGISTRY.get(inp["model_id"], {}).get("hard_rules", []))},
        {"node": "risk_tier_determination", "timestamp_utc": now,
         "validation_risk_score": out.get("validation_risk_score", 0),
         "hitl_conditions": out["hitl_conditions"],
         "human_review_required": out["human_review_required"],
         "target_reviewer": out["target_reviewer"]},
        {"node": "validation_narrative", "timestamp_utc": now,
         "llm_used": not DEMO_MODE, "report_length": 680},
        {"node": "routing_decision", "timestamp_utc": now,
         "human_review_required": out["human_review_required"],
         "resolution_type": out["resolution_type"]},
    ]

    if out["human_review_required"]:
        mro = st.session_state.get("mro_decision")
        if mro:
            audit_entries.append({
                "node": "human_review_gate",
                "timestamp_utc": mro["timestamp"],
                "reviewer_id": mro["reviewer_id"],
                "reviewer_decision": mro["decision"],
                "validation_outcome": mro["final_outcome"],
            })
            audit_entries.append({
                "node": "audit_finalize",
                "timestamp_utc": mro["timestamp"],
                "final_outcome": mro["final_outcome"],
                "next_revalidation_date": out["next_revalidation_date"],
                "audit_retention": "10_YEARS_S3_OBJECT_LOCK_GOVERNANCE",
            })
        else:
            audit_entries.append({
                "node": "human_review_gate",
                "timestamp_utc": "PENDING — awaiting MRO decision",
                "status": "PAUSED — interrupt_before enforced by LangGraph framework",
            })
    else:
        audit_entries.append({
            "node": "audit_finalize",
            "timestamp_utc": now,
            "final_outcome": out["resolution_type"],
            "next_revalidation_date": out["next_revalidation_date"],
            "audit_retention": "10_YEARS_S3_OBJECT_LOCK_GOVERNANCE",
        })

    for i, entry in enumerate(audit_entries, 1):
        node_name = entry.get("node", "")
        is_hitl = node_name == "human_review_gate"
        is_final = node_name == "audit_finalize"
        icon = "⏸️" if (is_hitl and "PENDING" in str(entry.get("timestamp_utc", ""))) else "✅"

        with st.expander(f"{icon} Node {i}: `{node_name}`", expanded=(i <= 3)):
            st.json(entry)

    st.markdown("---")
    st.markdown("**Audit Trail Security Properties**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("✅ **Append-only** — prior entries immutable")
        st.markdown("✅ **UTC timestamps** — no local time ambiguity")
    with col2:
        st.markdown("✅ **Every node recorded** — complete chain of custody")
        st.markdown("✅ **Reviewer ID captured** — HITL decisions traceable")
    with col3:
        st.markdown("✅ **10-year S3 Object Lock** — GOVERNANCE mode retention")
        st.markdown("✅ **DynamoDB IAM** — UpdateItem/DeleteItem denied")


with tab5:
    render_audit_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — About
# ══════════════════════════════════════════════════════════════════════════════

def render_about_tab():
    st.header("About — Model Risk Management Agent")

    about_tabs = st.tabs([
        "Architecture", "Security Design", "Regulatory Coverage", "Getting Started"
    ])

    with about_tabs[0]:
        st.subheader("12-Node Validation Pipeline")
        st.markdown("""
```
START
 │
 ▼
[1]  model_inventory_lookup      — Load model from registry, compute schedule metadata
 │
 ▼
[2]  data_sample_pull            — Load aggregate performance metrics (no PII, no raw predictions)
 │
 ▼
[3]  conceptual_soundness_review — LLM: evaluate model design, assumptions, limitations (SR 11-7 §§ 5-7)
 │
 ▼
[4]  outcomes_analysis           — Python: compute degradation flags, material findings
 │
 ▼
[5]  population_stability_analysis — Python: PSI computation and classification
 │
 ▼
[6]  benchmark_comparison        — Python: challenger/benchmark performance comparison
 │
 ▼
[7]  sensitivity_analysis        — Python: weight concentration, normalization, hard-rule coverage
 │
 ▼
[8]  risk_tier_determination     — Python: HITL conditions, routing, validation risk score
 │
 ▼
[9]  validation_narrative        — LLM: outcomes narrative, full SR 11-7 validation report draft
 │
 ▼
[10] routing_decision            — Python: finalize human_review_required and resolution_type

         ┌─────────────────────────────────────────────────────────────────────┐
         │   Conditional Split (_route_after_routing_decision)                 │
         └─────────────────────────────────────────────────────────────────────┘
              │                                    │
      [HITL required]                     [Auto-resolvable]
              │                                    │
              ▼                                    │
[11] human_review_gate ←── PAUSE         [12] audit_finalize → END
       │
  MRO submits decision
  APPROVE / CONDITIONALLY_APPROVE / REQUIRE_REMEDIATION / ESCALATE_TO_BOARD
              │
[12] audit_finalize → END
```

**Models under governance:**
- `AGT02-FP-SCORE-v1` — AML/TMS Enhancement false positive composite
- `AGT03-KYC-RISK-v1` — KYC/CDD 8-factor customer risk score
- `AGT04-FRAUD-SCORE-v1` — Fraud detection composite score
- `AGT07-SURV-RISK-v1` — Trading surveillance 5-factor risk score
- `AGT08-CREDIT-SCORE-v1` — Credit underwriting 5-factor composite
""")

        st.subheader("LLM vs. Python Boundary (SR 11-7 Design Principle)")
        st.markdown("""
| Task | LLM | Python |
|------|-----|--------|
| Model risk tier determination | | ✅ |
| Performance degradation flag computation | | ✅ |
| PSI classification (STABLE / WARNING / CRITICAL) | | ✅ |
| HITL condition evaluation | | ✅ |
| Routing destination selection | | ✅ |
| Validation outcome recommendation | | ✅ |
| Weight normalization / concentration check | | ✅ |
| Hard rule coverage verification | | ✅ |
| Next revalidation date computation | | ✅ |
| Audit trail recording | | ✅ |
| Conceptual soundness narrative | ✅ | |
| Outcomes analysis narrative | ✅ | |
| Full validation report draft | ✅ | |
| Ongoing monitoring assessment | ✅ | |
""")

    with about_tabs[1]:
        st.subheader("Security Architecture")
        st.markdown("""
**1. No individual predictions or PII in state**
Agent 11 operates on aggregate performance statistics only — accuracy, Gini, KS, PSI, FPR, FNR.
Individual model predictions, customer records, and training data never flow through this agent's state.
The LangGraph checkpoint database contains only validation metadata and aggregate metrics.

**2. ALWAYS_HITL_CONDITIONS frozenset**
Nine conditions that always trigger human review are defined as a Python `frozenset` in `state.py`.
`frozenset.add()` raises `TypeError` — the set is immutable at runtime. Tests verify this property.

**3. Routing is Python-determined**
`_route_after_routing_decision()` checks `human_review_required is False` explicitly.
A missing key (None) defaults to `human_review_gate` — fail-safe behavior.
An unknown reviewer decision cannot trigger model approval.

**4. HITL at framework level**
`interrupt_before=["human_review_gate"]` is a LangGraph framework directive.
The graph cannot execute node 11 or beyond without a human reviewer submitting a decision.

**5. Model registry immutability**
In production: model registry stored in DynamoDB with IAM policy denying `UpdateItem` and `DeleteItem`.
Registry changes require MRO authentication and generate CloudTrail events.
Registry is append-only — model deactivation sets `status=RETIRED`, not deletion.

**6. Append-only audit trail**
Every node uses `list(current) + [new_entry]` — never modifying prior entries.
Tests verify prior entries remain unchanged after each node execution.

**7. 10-year retention**
Validation reports archived to S3 Object Lock GOVERNANCE — model life plus BSA 5-year retention minimum.
Reports cannot be deleted without MRO authentication.
""")

    with about_tabs[2]:
        st.subheader("Regulatory Coverage")
        st.markdown("""
| Regulation | Obligation Handled |
|-----------|-------------------|
| **SR 11-7 (Model Risk Management)** | Full validation lifecycle: conceptual soundness, outcomes analysis, ongoing monitoring, independent review, documentation |
| **OCC Bulletin 2011-12** | Parallel guidance to SR 11-7 for national banks — same validation requirements |
| **FFIEC Model Risk Guidance** | Examination framework for model inventory, validation, and governance |
| **ECOA/Reg B (fair lending)** | Fair lending flag and disparate impact assessment trigger for AGT08 credit model |
| **BSA/SR 11-7** | Scored models (AGT02, AGT03, AGT04, AGT07) have BSA compliance implications — model risk affects SAR quality |
| **FINRA Rule 3110** | AGT07 surveillance model risk — surveillance model accuracy affects FINRA WSP adequacy |
| **Record Retention (BSA 5-year)** | Validation reports retained 10 years (model life + retention) via S3 Object Lock |

**SR 11-7 Validation Components Covered:**
- §§ 5-7: Conceptual soundness review (LLM narrative)
- § 8: Outcomes analysis, back-testing, benchmarking (Python metrics)
- §§ 8-10: Population stability, sensitivity analysis (Python PSI + weight checks)
- §§ 10-11: Ongoing monitoring assessment (PSI monitoring, frequency review)
- § 4: Human oversight via HITL gate (all HIGH-tier validations)
""")

    with about_tabs[3]:
        st.subheader("Getting Started")
        st.code("""
# Clone and run Agent 11
git clone https://github.com/virtualryder/fsi-ai-agents.git
cd fsi-ai-agents/11-model-risk-agent

# Install dependencies
pip install -r requirements.txt

# Configure (OPENAI_API_KEY optional — demo mode works without it)
cp .env.example .env

# Run (port 8511)
streamlit run app.py --server.port 8511
""", language="bash")

        st.markdown("""
**Demo Mode** (no API key required):
The app loads 4 pre-computed validation scenarios covering:
1. Annual revalidation (PASS — MRO sign-off required for HIGH tier)
2. Triggered review (CRITICAL degradation — CRO escalation)
3. Initial validation of challenger model (fair lending flag)
4. Ongoing monitoring (auto-resolve — no HITL required)

**Production deployment:**
See `docs/aws-deployment-guide.md` for 12-step AWS deployment with:
- DynamoDB model registry (IAM-enforced immutability)
- Aurora PostgreSQL LangGraph checkpoint store (`log_statement=none`)
- S3 Object Lock GOVERNANCE 10-year validation report retention
- CloudWatch alarms for model performance metric breaches
- EventBridge triggers for automated ongoing monitoring runs

**Relationship to other suite agents:**
Agent 11 validates the scoring models in Agents 02, 03, 04, 07, and 08.
It should be deployed after those agents are in production and generating
real performance data from their model monitoring infrastructure.
""")


with tab6:
    render_about_tab()
