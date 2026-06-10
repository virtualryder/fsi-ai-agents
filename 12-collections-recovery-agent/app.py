"""
Agent 12 — Collections & Recovery Agent
Streamlit Dashboard — Port 8512

6-tab interface for Collections Supervisors, Compliance Officers, and Legal Counsel:
  Tab 1: Submit Case   — Load a demo scenario or enter a debt account manually
  Tab 2: Case Findings — FDCPA compliance status, SCRA/bankruptcy flags, SOL timeline
  Tab 3: Collections Analysis — Collectability score, payment plan options, settlement tiers
  Tab 4: Collector Review — HITL gate: supervisor decision, outcome selection, notes
  Tab 5: Audit Trail  — Append-only node-by-node record with FDCPA compliance timestamps
  Tab 6: About        — 12-node pipeline diagram, LLM/Python boundary, regulatory coverage

FDCPA/Reg F Architecture note: all contact time checks, Reg F 7-in-7 enforcement,
SCRA rate cap application, SOL computation, payment plan math, settlement tier
authorization, and HITL routing are Python-computed deterministic results.
LLM (GPT-4o) produces NARRATIVE ONLY: hardship assessment, strategy summary, and
collection letter body — never routing decisions, HITL triggers, or financial amounts.
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
    page_title="Collections & Recovery Agent | FSI AI Suite",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Path references ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
FIXTURES_DIR = BASE_DIR / "data" / "fixtures"

# ── Load fixtures ─────────────────────────────────────────────────────────────

@st.cache_data
def load_scenarios():
    with open(FIXTURES_DIR / "debt_scenarios.json") as f:
        return json.load(f)["scenarios"]

@st.cache_data
def load_payment_plan_configs():
    with open(FIXTURES_DIR / "payment_plan_configs.json") as f:
        return json.load(f)

SCENARIOS = load_scenarios()
PAYMENT_CONFIGS = load_payment_plan_configs()

DEMO_MODE = not bool(
    os.getenv("OPENAI_API_KEY", "").startswith("sk-")
    and len(os.getenv("OPENAI_API_KEY", "")) > 20
)

# ── Color / badge helpers ─────────────────────────────────────────────────────

HITL_COLOR   = "#dc3545"   # Red — HITL required
AUTO_COLOR   = "#198754"   # Green — auto-route
WARN_COLOR   = "#fd7e14"   # Orange — warning
INFO_COLOR   = "#0d6efd"   # Blue — informational

TIER_COLORS = {
    "HIGH":   "#198754",
    "MEDIUM": "#fd7e14",
    "LOW":    "#dc3545",
}
REG_RISK_COLORS = {
    "LOW":      "#198754",
    "MODERATE": "#fd7e14",
    "HIGH":     "#dc3545",
    "CRITICAL": "#6f1920",
}
OUTCOME_COLORS = {
    "PAYMENT_PLAN":      "#198754",
    "SETTLEMENT":        "#0d6efd",
    "CEASE_AND_DESIST":  "#dc3545",
    "LEGAL_REFERRAL":    "#6f1920",
    "FULL_PAYMENT":      "#20c997",
    "HARDSHIP_PLAN":     "#fd7e14",
    "PENDING_REVIEW":    "#6c757d",
}


def badge(text: str, color: str = "#6c757d") -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 10px;'
        f'border-radius:4px;font-size:0.82em;font-weight:600;">{text}</span>'
    )


def alert_box(text: str, color: str, icon: str = "") -> str:
    return (
        f'<div style="background:{color}20;border-left:4px solid {color};'
        f'padding:12px 16px;border-radius:4px;margin:8px 0;">'
        f'{icon + " " if icon else ""}{text}</div>'
    )


def section_header(text: str) -> None:
    st.markdown(f"#### {text}")
    st.markdown("---")


# ── Session state defaults ────────────────────────────────────────────────────

def _init_session_state():
    defaults = {
        "case_state":          None,   # Full CollectionsState dict after pipeline run
        "pipeline_complete":   False,
        "hitl_decision_made":  False,
        "active_scenario_id":  None,
        "run_id":              None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session_state()


# ── Demo pipeline simulation ──────────────────────────────────────────────────
# In demo mode, we simulate the Python computation results that the LangGraph
# nodes would produce. This allows the UI to be demonstrated without requiring
# live OpenAI credentials or a running LangGraph runtime.

def _simulate_pipeline(scenario: Dict) -> Dict:
    """
    Produce a fully populated CollectionsState dict from a demo scenario.
    All numeric values are Python math — identical to what the real nodes compute.
    LLM narrative fields are pre-filled with representative text.
    """
    sf = scenario["state_fields"]
    balance     = sf.get("current_balance", 1000.0)
    debt_type   = sf.get("debt_type", "CREDIT_CARD")
    consumer_state = sf.get("consumer_state", "OH")
    is_scra     = sf.get("scra_active_military", False)
    is_bankrupt = sf.get("bankruptcy_stay_active", False)
    is_dispute  = sf.get("dispute_received", False)
    is_cd       = sf.get("cease_desist_received", False)
    hardship    = sf.get("hardship_score", 0.4)
    contacts_7  = sf.get("prior_contacts_7_days", 2)
    days_conv   = sf.get("days_since_last_conversation", 10)
    phf         = sf.get("payment_history_factor", 0.65)
    csf         = sf.get("contact_success_factor", 0.75)
    acct        = sf.get("original_account_number", "0000000000000000")
    orig_cred   = sf.get("original_creditor", "Unknown Creditor")

    # PII masking (mirrors debt_intake_node)
    account_id  = f"ACCT-****{acct[-4:]}"
    case_id     = f"COL-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # FDCPA applicability
    non_fdcpa = {"MORTGAGE", "BUSINESS_DEBT", "STUDENT_LOAN_FEDERAL"}
    fdcpa_applies = debt_type not in non_fdcpa

    # Reg F — 7-in-7 check
    reg_f_exceeded = contacts_7 >= 7
    conversation_wait = days_conv < 7
    reg_f_issues = []
    if reg_f_exceeded:
        reg_f_issues.append(f"REG_F_7_IN_7: {contacts_7} calls in 7 days")
    if conversation_wait:
        reg_f_issues.append(f"REG_F_POST_CONVERSATION_WAIT: only {days_conv} days since last call")

    # Contact time (simplified — demo assumes business hours)
    contact_permitted_now = True
    if is_cd or is_bankrupt:
        contact_permitted_now = False

    # Regulatory risk tier
    fdcpa_issues = []
    if is_cd:
        fdcpa_issues.append("CEASE_DESIST_ACTIVE")
    if not sf.get("validation_notice_sent", True):
        fdcpa_issues.append("VALIDATION_NOTICE_NOT_SENT")
    reg_issue_count = len(fdcpa_issues) + len(reg_f_issues)
    if reg_issue_count >= 3 or is_bankrupt:
        reg_risk_tier = "CRITICAL"
    elif reg_issue_count >= 2 or is_scra or is_cd:
        reg_risk_tier = "HIGH"
    elif reg_issue_count >= 1 or is_dispute:
        reg_risk_tier = "MODERATE"
    else:
        reg_risk_tier = "LOW"

    # SOL computation (simplified — demo uses common 6-year default and CA 4-year)
    sol_map = {"CA": 4, "NY": 6, "OH": 6, "TX": 4, "FL": 5, "IL": 5, "VA": 6}
    sol_years = sol_map.get(consumer_state, 6)
    dlp = sf.get("debt_date_of_last_payment", "2025-01-01")
    try:
        dlp_year = int(dlp[:4])
        sol_expiry_year = dlp_year + sol_years
        sol_expired = sol_expiry_year < datetime.now().year
        sol_warning = not sol_expired and (sol_expiry_year - datetime.now().year) <= 1
    except Exception:
        sol_expired = False
        sol_warning = False
        sol_expiry_year = datetime.now().year + sol_years

    # Days delinquent
    try:
        dlp_dt = datetime.strptime(dlp, "%Y-%m-%d")
        days_delinquent = (datetime.now() - dlp_dt).days
    except Exception:
        days_delinquent = 365

    # Medical debt flag
    medical_debt_flag = debt_type == "MEDICAL_DEBT"
    credit_reporting_appropriate = (
        balance >= 100.0
        and not (medical_debt_flag and balance < 500.0)
    )
    settlement_eligible = (
        not is_bankrupt
        and not is_cd
        and not sf.get("consumer_is_deceased", False)
    )

    # Collectability score (5-factor model)
    debt_age_factor = max(0.0, 1.0 - (days_delinquent / 1825.0))
    if sol_expired:
        debt_age_factor *= 0.3
    raw_score = (
        0.30 * phf
        + 0.25 * csf
        + 0.20 * (1.0 - hardship)
        + 0.15 * debt_age_factor
        + 0.10 * (1.0 - min(contacts_7, 7) / 7.0)
    )
    collectability_score = max(0.0, min(1.0, raw_score))
    if collectability_score >= 0.70:
        collectability_tier = "HIGH"
    elif collectability_score >= 0.40:
        collectability_tier = "MEDIUM"
    else:
        collectability_tier = "LOW"

    # Hardship eligibility
    hardship_plan_eligible = hardship >= 0.60

    # Payment plan options
    standard_terms = [12, 24, 36, 48, 60]
    payment_plan_options = []
    for t in standard_terms:
        monthly = round(balance / t, 2)
        if monthly >= balance * 0.015:
            payment_plan_options.append({
                "plan_type":      "STANDARD",
                "term_months":    t,
                "monthly_payment": monthly,
                "total_cost":     round(monthly * t, 2),
            })
    if hardship_plan_eligible:
        hardship_monthly = max(25.0, round(balance * 0.01, 2))
        hardship_term = min(60, int(balance / hardship_monthly) + 1)
        payment_plan_options.append({
            "plan_type":       "HARDSHIP",
            "term_months":     hardship_term,
            "monthly_payment": hardship_monthly,
            "total_cost":      round(hardship_monthly * hardship_term, 2),
        })
    payment_plan_options = payment_plan_options[:6]

    # Settlement tiers
    tiers_def = {
        "TIER_1": {"max_discount_pct": 20.0, "min_balance": 0,     "auth_level": "COLLECTOR"},
        "TIER_2": {"max_discount_pct": 35.0, "min_balance": 1000,  "auth_level": "SUPERVISOR"},
        "TIER_3": {"max_discount_pct": 50.0, "min_balance": 5000,  "auth_level": "MANAGER"},
        "TIER_4": {"max_discount_pct": 70.0, "min_balance": 10000, "auth_level": "VP_COLLECTIONS"},
    }
    settlement_tiers = []
    for tier_name, td in tiers_def.items():
        if balance >= td["min_balance"] and settlement_eligible:
            amount = round(balance * (1.0 - td["max_discount_pct"] / 100.0), 2)
            high_value = amount > 10000 or td["max_discount_pct"] > 40.0
            settlement_tiers.append({
                "tier":             tier_name,
                "max_discount_pct": td["max_discount_pct"],
                "settlement_amount": amount,
                "auth_level":       td["auth_level"],
                "high_value":       high_value,
            })

    # Recommended settlement tier
    rec_tier = settlement_tiers[-1] if settlement_tiers else None
    settlement_amount   = rec_tier["settlement_amount"] if rec_tier else None
    settlement_discount = rec_tier["max_discount_pct"] if rec_tier else None
    settlement_high_val = rec_tier["high_value"] if rec_tier else False

    # HITL conditions
    always_hitl = {
        "SCRA_DETECTED":         is_scra,
        "BANKRUPTCY_STAY_DETECTED": is_bankrupt,
        "DISPUTE_RECEIVED":      is_dispute,
        "CEASE_DESIST_RECEIVED": is_cd,
        "DECEASED_ACCOUNT":      sf.get("consumer_is_deceased", False),
        "SETTLEMENT_HIGH_VALUE": settlement_high_val,
        "LITIGATION_HIGH_RISK":  (
            collectability_tier == "LOW"
            and not sol_expired
            and balance > 5000
        ),
        "MINOR_ACCOUNT":         sf.get("consumer_is_minor", False),
    }
    hitl_conditions = [k for k, v in always_hitl.items() if v]
    hitl_required   = len(hitl_conditions) > 0 or bool(fdcpa_issues) or bool(reg_f_issues)

    if is_bankrupt:
        escalation_level = "COMPLIANCE"
    elif is_scra:
        escalation_level = "SUPERVISOR"
    elif hitl_conditions:
        escalation_level = "SUPERVISOR"
    else:
        escalation_level = "STANDARD"

    # Human review routing
    human_review_required = hitl_required or bool(fdcpa_issues) or bool(reg_f_issues)

    # Routing outcome (Python fail-safe: only explicit False bypasses HITL)
    routed_to_hitl = human_review_required is not False

    # Pre-filled narrative (demo)
    if is_bankrupt:
        strategy_summary = (
            "BANKRUPTCY STAY ACTIVE — ALL collection activity must immediately cease. "
            "File proof of claim with bankruptcy court if applicable. No contact with consumer. "
            "Compliance officer must review under 11 U.S.C. § 362."
        )
    elif is_scra:
        strategy_summary = (
            "ACTIVE MILITARY SERVICEMEMBER — SCRA interest rate cap of 6% applies "
            "retroactively to date of active duty. Recalculate balance; credit excess interest. "
            "Supervisor must approve modified payment plan before any contact."
        )
    elif is_dispute:
        strategy_summary = (
            "DISPUTE RECEIVED — All collection activity suspended. "
            "Send debt validation materials within 5 business days. "
            "30-day collection hold begins from dispute receipt date."
        )
    elif collectability_tier == "HIGH" and not hitl_required:
        strategy_summary = (
            f"High collectability account ({collectability_score:.0%} score). "
            f"Consumer is reachable and has payment history. "
            f"Recommend {payment_plan_options[1]['term_months'] if len(payment_plan_options) > 1 else 12}-month standard payment plan "
            f"at ${payment_plan_options[1]['monthly_payment'] if len(payment_plan_options) > 1 else 'TBD'}/month. "
            f"FDCPA mini-Miranda and validation notice will be injected automatically."
        )
    elif medical_debt_flag:
        strategy_summary = (
            f"Medical debt account — CFPB 2025 rules apply. "
            f"Balance ${balance:,.2f} {'EXCEEDS' if balance >= 500 else 'IS BELOW'} $500 credit reporting threshold. "
            f"Settlement at {rec_tier['max_discount_pct'] if rec_tier else 35}% discount recommended "
            f"({rec_tier['auth_level'] if rec_tier else 'SUPERVISOR'} authorization required). "
            f"IRS Form 1099-C required for forgiven amount if ≥$600."
        )
    else:
        strategy_summary = (
            f"Collectability tier: {collectability_tier} ({collectability_score:.0%} score). "
            f"Standard payment plan or settlement offer recommended. "
            f"Proceed per FDCPA guidelines with supervisor approval."
        )

    # 1099-C applicability
    forgiven = (balance - settlement_amount) if settlement_amount else 0
    requires_1099c = forgiven >= 600.0

    # Audit trail (simulated nodes)
    now_iso = datetime.now(timezone.utc).isoformat()
    audit_trail = [
        {
            "node":      "debt_intake",
            "timestamp": now_iso,
            "message":   f"Case {case_id} opened. Account {account_id} ingested. FDCPA applies: {fdcpa_applies}.",
        },
        {
            "node":      "fdcpa_compliance_check",
            "timestamp": now_iso,
            "message":   f"Contact permitted: {contact_permitted_now}. Reg F issues: {len(reg_f_issues)}. Regulatory risk: {reg_risk_tier}.",
        },
        {
            "node":      "scra_bankruptcy_check",
            "timestamp": now_iso,
            "message":   f"SCRA: {is_scra}. Bankruptcy stay: {is_bankrupt}. SOL: {sol_years} years (expires {sol_expiry_year}). SOL expired: {sol_expired}.",
        },
        {
            "node":      "consumer_profile",
            "timestamp": now_iso,
            "message":   f"Hardship score: {hardship:.2f}. Hardship plan eligible: {hardship_plan_eligible}. (LLM narrative generated.)",
        },
        {
            "node":      "debt_validation",
            "timestamp": now_iso,
            "message":   f"Days delinquent: {days_delinquent}. Medical debt: {medical_debt_flag}. Credit reporting appropriate: {credit_reporting_appropriate}.",
        },
        {
            "node":      "payment_plan_optimizer",
            "timestamp": now_iso,
            "message":   f"Collectability: {collectability_tier} ({collectability_score:.0%}). Payment plans: {len(payment_plan_options)}. Settlement tiers: {len(settlement_tiers)}.",
        },
        {
            "node":      "collections_strategy",
            "timestamp": now_iso,
            "message":   "Collections strategy narrative generated by LLM. Python-computed tiers and plans provided to LLM as structured input.",
        },
        {
            "node":      "risk_scoring",
            "timestamp": now_iso,
            "message":   f"HITL required: {hitl_required}. Conditions: {hitl_conditions if hitl_conditions else 'none'}. Escalation: {escalation_level}.",
        },
        {
            "node":      "routing_decision",
            "timestamp": now_iso,
            "message":   f"human_review_required = {human_review_required} (explicit is-False check). "
                         + ("→ Routed to human_review_gate." if routed_to_hitl else "→ Auto-routed to communication_drafting."),
        },
    ]

    return {
        # Identification
        "case_id":                case_id,
        "account_id":             account_id,
        "original_creditor":      orig_cred,
        "debt_type":              debt_type,
        "consumer_id":            sf.get("consumer_id", "CONS-UNKNOWN"),
        "consumer_name_masked":   sf.get("consumer_name_masked", "Consumer C."),
        "consumer_state":         consumer_state,
        # Balances
        "current_balance":        balance,
        "original_balance":       sf.get("original_balance", balance),
        "interest_accrued":       sf.get("interest_accrued", 0.0),
        "fees_accrued":           sf.get("fees_accrued", 0.0),
        # FDCPA
        "fdcpa_applies":          fdcpa_applies,
        "contact_permitted_now":  contact_permitted_now,
        "fdcpa_compliance_issues": fdcpa_issues,
        "regulation_f_violations": reg_f_issues,
        "regulatory_risk_tier":   reg_risk_tier,
        "cease_desist_received":  is_cd,
        "dispute_received":       is_dispute,
        "validation_notice_sent": sf.get("validation_notice_sent", True),
        # SCRA / Bankruptcy
        "scra_active_military":   is_scra,
        "scra_branch":            sf.get("scra_branch", ""),
        "bankruptcy_stay_active": is_bankrupt,
        "bankruptcy_chapter":     sf.get("bankruptcy_chapter", ""),
        "bankruptcy_case_number": sf.get("bankruptcy_case_number", ""),
        # SOL
        "sol_years":              sol_years,
        "sol_expiration_date":    str(sol_expiry_year),
        "sol_expired":            sol_expired,
        "sol_warning":            sol_warning,
        # Consumer flags
        "consumer_is_deceased":   sf.get("consumer_is_deceased", False),
        "consumer_is_minor":      sf.get("consumer_is_minor", False),
        # Debt validation
        "days_delinquent":        days_delinquent,
        "medical_debt_flag":      medical_debt_flag,
        "credit_reporting_appropriate": credit_reporting_appropriate,
        "settlement_eligible":    settlement_eligible,
        # Collectability
        "collectability_score":   collectability_score,
        "collectability_tier":    collectability_tier,
        # Plans & settlement
        "payment_plan_options":   payment_plan_options,
        "settlement_tiers":       settlement_tiers,
        "settlement_amount":      settlement_amount,
        "settlement_discount_pct": settlement_discount,
        "settlement_high_value":  settlement_high_val,
        "requires_1099c":         requires_1099c,
        "forgiven_amount":        round(forgiven, 2),
        # HITL
        "hitl_required":          hitl_required,
        "hitl_conditions":        hitl_conditions,
        "human_review_required":  human_review_required,
        "escalation_level":       escalation_level,
        "routed_to_hitl":         routed_to_hitl,
        # Narrative
        "hardship_plan_eligible": hardship_plan_eligible,
        "hardship_score":         hardship,
        "strategy_summary":       strategy_summary,
        # Outcome (pre-decision)
        "collections_outcome":    None,
        "reviewer_decision":      None,
        "reviewer_id":            None,
        "reviewer_notes":         None,
        # Audit
        "audit_trail":            audit_trail,
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚖️ Collections & Recovery")
    st.markdown("**Agent 12 · FSI AI Suite**")

    if DEMO_MODE:
        st.warning(
            "**Demo Mode** — Pre-computed scenarios active. "
            "Add `OPENAI_API_KEY` for live LLM narratives.",
            icon="⚠️",
        )
    else:
        st.success("**Live Mode** — Connected to OpenAI GPT-4o", icon="✅")

    st.markdown("---")

    cs = st.session_state.case_state
    if cs:
        st.markdown("**Active Case**")
        st.markdown(f"Case: `{cs['case_id']}`")
        st.markdown(f"Account: `{cs['account_id']}`")
        st.markdown(f"Balance: **${cs['current_balance']:,.2f}**")

        hitl_color = HITL_COLOR if cs["hitl_required"] else AUTO_COLOR
        hitl_label = "HITL REQUIRED" if cs["hitl_required"] else "AUTO-ROUTE"
        st.markdown(badge(hitl_label, hitl_color), unsafe_allow_html=True)

        if cs["collections_outcome"]:
            oc = cs["collections_outcome"]
            st.markdown(badge(oc, OUTCOME_COLORS.get(oc, "#6c757d")), unsafe_allow_html=True)

        st.markdown("---")

    st.markdown("**Regulatory Basis:**")
    st.markdown(
        "- FDCPA — 15 U.S.C. § 1692\n"
        "- CFPB Reg F — 12 CFR Part 1006\n"
        "- SCRA — 50 U.S.C. § 3937\n"
        "- Bankruptcy Code § 362\n"
        "- FCRA — 15 U.S.C. § 1681\n"
        "- UDAAP — Dodd-Frank § 1031\n\n"
        "**Port:** 8512"
    )


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Submit Case",
    "🔍 Case Findings",
    "📊 Collections Analysis",
    "👤 Collector Review",
    "🗂 Audit Trail",
    "ℹ️ About",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Submit Case
# ══════════════════════════════════════════════════════════════════════════════

def render_submit_tab():
    st.header("Submit Collections Case")
    st.markdown(
        "Select a pre-built demo scenario to walk through the FDCPA/Reg F compliance "
        "pipeline, or enter a debt account manually. All contact time checks, SOL "
        "computation, payment plan math, and HITL routing are **Python-computed** "
        "— the LLM generates narrative only."
    )

    if DEMO_MODE:
        st.info(
            "**Demo Mode:** Pre-computed results are shown. Connect `OPENAI_API_KEY` "
            "to generate live LLM hardship assessments, strategy summaries, and "
            "collection letter drafts.",
            icon="ℹ️",
        )

    st.markdown("---")

    # ── Demo scenario selection ────────────────────────────────────────────
    st.subheader("Demo Scenarios")
    st.markdown(
        "Each scenario demonstrates a distinct regulatory situation. "
        "HITL conditions, FDCPA compliance status, and SOL are all Python-enforced."
    )

    cols = st.columns(2)
    for idx, scenario in enumerate(SCENARIOS):
        col = cols[idx % 2]
        with col:
            exp_hitl = scenario.get("expected_hitl", False)
            hitl_badge = badge("HITL", HITL_COLOR) if exp_hitl else badge("AUTO", AUTO_COLOR)
            hitl_conds = scenario.get("hitl_conditions_expected", [])
            cond_text  = " · ".join(hitl_conds) if hitl_conds else "Standard routing"

            st.markdown(
                f"**{scenario['label']}**  \n"
                f"{hitl_badge} &nbsp; {cond_text}",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<small>{scenario['description']}</small>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<small>💡 <em>{scenario['key_demo_moment']}</em></small>",
                unsafe_allow_html=True,
            )

            if st.button(f"Run {scenario['id']}", key=f"run_{scenario['id']}"):
                with st.spinner(f"Running {scenario['id']} through 12-node pipeline..."):
                    time.sleep(1.2)
                    state = _simulate_pipeline(scenario)
                    st.session_state.case_state = state
                    st.session_state.pipeline_complete = True
                    st.session_state.hitl_decision_made = False
                    st.session_state.active_scenario_id = scenario["id"]
                    st.session_state.run_id = state["case_id"]
                st.success(f"Pipeline complete — Case `{state['case_id']}` created.")
                st.rerun()

            st.markdown("---")

    # ── Manual entry ───────────────────────────────────────────────────────
    with st.expander("Manual Case Entry", expanded=False):
        st.markdown("Enter debt account details to run a custom case through the pipeline.")

        c1, c2, c3 = st.columns(3)
        with c1:
            acct_num   = st.text_input("Account Number (will be masked)", value="1234567890123456")
            debt_type  = st.selectbox(
                "Debt Type",
                ["CREDIT_CARD", "PERSONAL_LOAN", "MEDICAL_DEBT", "AUTO_LOAN",
                 "STUDENT_LOAN_PRIVATE", "RETAIL_INSTALLMENT", "UTILITIES"],
            )
            orig_cred  = st.text_input("Original Creditor", value="First Regional Bank")
        with c2:
            balance    = st.number_input("Current Balance ($)", min_value=0.0, value=2500.0, step=100.0)
            orig_bal   = st.number_input("Original Balance ($)", min_value=0.0, value=2000.0, step=100.0)
            interest   = st.number_input("Interest Accrued ($)", min_value=0.0, value=400.0, step=10.0)
        with c3:
            cons_state  = st.selectbox("Consumer State", ["OH", "CA", "TX", "FL", "NY", "IL", "VA", "WA"])
            cons_tz     = st.selectbox(
                "Consumer Timezone",
                ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
            )
            dlp         = st.date_input("Date of Last Payment")

        c4, c5 = st.columns(2)
        with c4:
            st.markdown("**Protective Flags**")
            is_scra_m  = st.checkbox("SCRA Active Military")
            is_bank_m  = st.checkbox("Bankruptcy Stay Active")
            is_disp_m  = st.checkbox("Dispute Received")
            is_cd_m    = st.checkbox("Cease & Desist Received")
        with c5:
            st.markdown("**Scoring Factors**")
            hardship_m = st.slider("Hardship Score", 0.0, 1.0, 0.35, 0.05)
            phf_m      = st.slider("Payment History Factor", 0.0, 1.0, 0.65, 0.05)
            csf_m      = st.slider("Contact Success Factor", 0.0, 1.0, 0.75, 0.05)
            contacts_m = st.number_input("Calls in Last 7 Days", 0, 20, 2)

        if st.button("Submit Manual Case", type="primary"):
            manual_scenario = {
                "id": "MANUAL",
                "label": "Manual Entry",
                "description": "Manually entered case",
                "key_demo_moment": "",
                "expected_hitl": False,
                "state_fields": {
                    "original_account_number":  acct_num,
                    "debt_type":                debt_type,
                    "original_creditor":        orig_cred,
                    "current_balance":          balance,
                    "original_balance":         orig_bal,
                    "interest_accrued":         interest,
                    "fees_accrued":             0.0,
                    "consumer_state":           cons_state,
                    "consumer_timezone":        cons_tz,
                    "consumer_is_deceased":     False,
                    "consumer_is_minor":        False,
                    "scra_active_military":     is_scra_m,
                    "bankruptcy_stay_active":   is_bank_m,
                    "dispute_received":         is_disp_m,
                    "cease_desist_received":    is_cd_m,
                    "validation_notice_sent":   True,
                    "prior_contacts_7_days":    contacts_m,
                    "days_since_last_conversation": 10,
                    "debt_date_of_last_payment": str(dlp),
                    "debt_origination_date":    "2022-01-01",
                    "hardship_score":           hardship_m,
                    "payment_history_factor":   phf_m,
                    "contact_success_factor":   csf_m,
                },
            }
            with st.spinner("Running case through 12-node pipeline..."):
                time.sleep(1.0)
                state = _simulate_pipeline(manual_scenario)
                st.session_state.case_state = state
                st.session_state.pipeline_complete = True
                st.session_state.hitl_decision_made = False
                st.session_state.active_scenario_id = "MANUAL"
                st.session_state.run_id = state["case_id"]
            st.success(f"Pipeline complete — Case `{state['case_id']}` created.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Case Findings
# ══════════════════════════════════════════════════════════════════════════════

def render_findings_tab():
    st.header("Case Findings")

    cs = st.session_state.case_state
    if not cs:
        st.info("Run a scenario from the **Submit Case** tab to see findings.", icon="ℹ️")
        return

    # ── Header metrics ────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Current Balance", f"${cs['current_balance']:,.2f}")
    with m2:
        st.metric("Debt Type", cs["debt_type"].replace("_", " ").title())
    with m3:
        st.metric("Consumer State", cs["consumer_state"])
    with m4:
        st.metric("Days Delinquent", f"{cs['days_delinquent']:,}")
    with m5:
        reg_color = REG_RISK_COLORS.get(cs["regulatory_risk_tier"], "#6c757d")
        st.markdown(
            f"**Regulatory Risk**  \n"
            + badge(cs["regulatory_risk_tier"], reg_color),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── HITL alert (most important) ────────────────────────────────────────
    if cs["hitl_required"]:
        cond_list = ", ".join(cs["hitl_conditions"]) if cs["hitl_conditions"] else "FDCPA/Reg F violations"
        st.markdown(
            alert_box(
                f"**HUMAN REVIEW REQUIRED** — Escalation Level: **{cs['escalation_level']}**  \n"
                f"Conditions: {cond_list}  \n"
                f"This case **cannot proceed to communication drafting** until a supervisor "
                f"completes the review in the **Collector Review** tab.  \n"
                f"This routing decision is enforced by LangGraph "
                f"`interrupt_before=[\"human_review_gate\"]` — it is not configurable.",
                HITL_COLOR,
                "🛑",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            alert_box(
                "Auto-route: No HITL conditions detected. "
                "Pipeline will proceed to communication drafting without supervisor review. "
                "(`human_review_required is False` — explicit Python check.)",
                AUTO_COLOR,
                "✅",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Two-column layout ─────────────────────────────────────────────────
    left, right = st.columns(2)

    with left:
        # FDCPA Compliance
        section_header("📋 FDCPA Compliance Status")

        fdcpa_color = AUTO_COLOR if cs["fdcpa_applies"] else "#6c757d"
        st.markdown(
            f"**FDCPA Applies:** {badge('YES' if cs['fdcpa_applies'] else 'NOT COVERED', fdcpa_color)}  ",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**Contact Permitted Now:** "
            + badge("YES" if cs["contact_permitted_now"] else "NO — CONTACT BLOCKED",
                    AUTO_COLOR if cs["contact_permitted_now"] else HITL_COLOR),
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**Validation Notice Sent:** "
            + badge("YES" if cs["validation_notice_sent"] else "NOT SENT — REQUIRED",
                    AUTO_COLOR if cs["validation_notice_sent"] else WARN_COLOR),
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**Dispute Received:** "
            + badge("YES — COLLECTION HOLD" if cs["dispute_received"] else "NO",
                    HITL_COLOR if cs["dispute_received"] else AUTO_COLOR),
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**Cease & Desist:** "
            + badge("YES — C&D IN EFFECT" if cs["cease_desist_received"] else "NO",
                    HITL_COLOR if cs["cease_desist_received"] else AUTO_COLOR),
            unsafe_allow_html=True,
        )

        if cs["fdcpa_compliance_issues"]:
            st.markdown("**FDCPA Issues Detected:**")
            for issue in cs["fdcpa_compliance_issues"]:
                st.markdown(f"- {badge('ISSUE', HITL_COLOR)} {issue}", unsafe_allow_html=True)

        if cs["regulation_f_violations"]:
            st.markdown("**Regulation F Violations:**")
            for viol in cs["regulation_f_violations"]:
                st.markdown(f"- {badge('REG F', WARN_COLOR)} {viol}", unsafe_allow_html=True)

        # SCRA Status
        st.markdown("")
        section_header("🪖 SCRA Status")
        scra_color = HITL_COLOR if cs["scra_active_military"] else AUTO_COLOR
        scra_label = f"ACTIVE MILITARY — {cs.get('scra_branch', 'Branch Unknown')}" if cs["scra_active_military"] else "NOT ACTIVE MILITARY"
        st.markdown(badge(scra_label, scra_color), unsafe_allow_html=True)

        if cs["scra_active_military"]:
            st.markdown(
                alert_box(
                    "**SCRA 6% Rate Cap Applies** — Per 50 U.S.C. § 3937, interest rate "
                    "must be reduced to 6% maximum. Excess interest must be credited retroactively "
                    "to the date active duty began. Supervisor must approve all collection activity.",
                    HITL_COLOR,
                    "⚠️",
                ),
                unsafe_allow_html=True,
            )

    with right:
        # Bankruptcy Status
        section_header("⚖️ Bankruptcy Status")
        bk_color = HITL_COLOR if cs["bankruptcy_stay_active"] else AUTO_COLOR
        bk_label = (
            f"AUTOMATIC STAY ACTIVE — {cs.get('bankruptcy_chapter', '')}"
            if cs["bankruptcy_stay_active"]
            else "NO BANKRUPTCY STAY"
        )
        st.markdown(badge(bk_label, bk_color), unsafe_allow_html=True)

        if cs["bankruptcy_stay_active"]:
            case_num = cs.get("bankruptcy_case_number", "Unknown")
            st.markdown(
                alert_box(
                    f"**ALL collection must stop immediately** — 11 U.S.C. § 362 automatic stay.  \n"
                    f"Bankruptcy Case: `{case_num}`  \n"
                    f"Permitted actions: file proof of claim with court, monitor proceedings, "
                    f"contact debtor's attorney.  \n"
                    f"Escalation level: **COMPLIANCE OFFICER REVIEW REQUIRED**.",
                    HITL_COLOR,
                    "🛑",
                ),
                unsafe_allow_html=True,
            )

        # SOL Status
        st.markdown("")
        section_header("⏱ Statute of Limitations")
        sol_color = HITL_COLOR if cs["sol_expired"] else (WARN_COLOR if cs["sol_warning"] else AUTO_COLOR)
        sol_label = "SOL EXPIRED" if cs["sol_expired"] else ("SOL EXPIRING SOON" if cs["sol_warning"] else "SOL ACTIVE")
        st.markdown(badge(sol_label, sol_color), unsafe_allow_html=True)

        st.markdown(
            f"- **SOL Period:** {cs['sol_years']} years ({cs['consumer_state']} — open account)  \n"
            f"- **SOL Expiration:** {cs['sol_expiration_date']}  \n"
            f"- **Days Delinquent:** {cs['days_delinquent']:,}"
        )

        if cs["sol_expired"]:
            st.markdown(
                alert_box(
                    "**Time-barred debt** — SOL has expired. Threatening to sue violates "
                    "FDCPA § 807(2)(A). Voluntary payment is permissible in most states. "
                    "Collectability score has been reduced to reflect litigation infeasibility.",
                    WARN_COLOR,
                    "⚠️",
                ),
                unsafe_allow_html=True,
            )

        # Consumer flags
        st.markdown("")
        section_header("👤 Consumer Flags")
        flags = [
            ("Deceased Account", cs.get("consumer_is_deceased", False), "DECEASED — Estate procedures required"),
            ("Minor Account",    cs.get("consumer_is_minor", False),    "MINOR — Legal guardian required"),
            ("Medical Debt",     cs.get("medical_debt_flag", False),    "CFPB 2025 — Check $500 threshold"),
        ]
        for label, flag, detail in flags:
            color = HITL_COLOR if flag else AUTO_COLOR
            text  = detail if flag else "CLEAR"
            st.markdown(f"**{label}:** {badge(text, color)}", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Collections Analysis
# ══════════════════════════════════════════════════════════════════════════════

def render_analysis_tab():
    st.header("Collections Analysis")

    cs = st.session_state.case_state
    if not cs:
        st.info("Run a scenario from the **Submit Case** tab first.", icon="ℹ️")
        return

    # ── Collectability score ───────────────────────────────────────────────
    section_header("📈 Collectability Score")
    st.caption(
        "5-factor weighted model (SR 11-7 documented). "
        "Payment history 30% · Contact success 25% · Hardship 20% · Debt age 15% · Contact frequency 10%. "
        "Python-computed — not LLM."
    )

    tier_color = TIER_COLORS.get(cs["collectability_tier"], "#6c757d")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Collectability Score", f"{cs['collectability_score']:.0%}")
    with c2:
        st.markdown(f"**Tier:** {badge(cs['collectability_tier'], tier_color)}", unsafe_allow_html=True)
    with c3:
        st.metric("Hardship Score", f"{cs['hardship_score']:.0%}")
    with c4:
        hp_color = WARN_COLOR if cs["hardship_plan_eligible"] else AUTO_COLOR
        hp_label = "ELIGIBLE" if cs["hardship_plan_eligible"] else "STANDARD"
        st.markdown(f"**Hardship Plan:** {badge(hp_label, hp_color)}", unsafe_allow_html=True)

    st.markdown("---")

    # ── Strategy summary ───────────────────────────────────────────────────
    section_header("🎯 Collections Strategy")
    st.caption("Collections strategy narrative generated by LLM based on Python-computed tiers and collectability score.")
    st.info(cs.get("strategy_summary", "No strategy available."), icon="🎯")

    st.markdown("---")

    # ── Payment plan options ───────────────────────────────────────────────
    section_header("💳 Payment Plan Options")
    st.caption(
        "Monthly payment = Balance ÷ Term. Minimum payment ≥1.5% of balance. "
        "Hardship plan: $25/month minimum (threshold: hardship_score ≥ 0.60). "
        "All math is Python — not LLM."
    )

    plans = cs.get("payment_plan_options", [])
    if plans:
        plan_rows = []
        for p in plans:
            plan_rows.append({
                "Plan Type":       p["plan_type"],
                "Term (Months)":   p["term_months"],
                "Monthly Payment": f"${p['monthly_payment']:,.2f}",
                "Total Cost":      f"${p['total_cost']:,.2f}",
                "Auth Level":      "COLLECTOR" if p["plan_type"] == "STANDARD" else "SUPERVISOR",
            })
        st.dataframe(plan_rows, use_container_width=True, hide_index=True)
    else:
        st.warning("No payment plan options available for this account.", icon="⚠️")

    st.markdown("---")

    # ── Settlement tiers ───────────────────────────────────────────────────
    section_header("🤝 Settlement Analysis")
    st.caption(
        "Settlement tiers are Python constants (SETTLEMENT_TIERS dict — not LLM). "
        "High-value threshold: settlement amount >$10K OR discount >40% "
        "→ triggers SETTLEMENT_HIGH_VALUE HITL condition requiring supervisor authorization."
    )

    tiers = cs.get("settlement_tiers", [])
    if tiers and cs.get("settlement_eligible", False):
        tier_rows = []
        for t in tiers:
            tier_rows.append({
                "Tier":             t["tier"],
                "Max Discount":     f"{t['max_discount_pct']:.0f}%",
                "Settlement Amount": f"${t['settlement_amount']:,.2f}",
                "Discount Amount":  f"${cs['current_balance'] - t['settlement_amount']:,.2f}",
                "Auth Level":       t["auth_level"],
                "High-Value Flag":  "🔴 YES — HITL" if t["high_value"] else "✅ No",
            })
        st.dataframe(tier_rows, use_container_width=True, hide_index=True)

        # Recommended settlement
        if cs.get("settlement_amount"):
            sa = cs["settlement_amount"]
            sd = cs["settlement_discount_pct"]
            forgiven = cs["forgiven_amount"]

            cols = st.columns(3)
            with cols[0]:
                st.metric("Recommended Settlement", f"${sa:,.2f}",
                          delta=f"-{sd:.0f}% off ${cs['current_balance']:,.2f}")
            with cols[1]:
                st.metric("Forgiven Amount", f"${forgiven:,.2f}")
            with cols[2]:
                irs_color = WARN_COLOR if cs["requires_1099c"] else AUTO_COLOR
                irs_label = "IRS 1099-C REQUIRED" if cs["requires_1099c"] else "Under $600 threshold"
                st.markdown(
                    f"**IRS 1099-C:** {badge(irs_label, irs_color)}",
                    unsafe_allow_html=True,
                )

            if cs["requires_1099c"]:
                st.markdown(
                    alert_box(
                        f"**IRS Form 1099-C Required** — Forgiven debt of ${forgiven:,.2f} meets "
                        f"the ≥$600 threshold (26 U.S.C. § 6050P). The 1099-C notice will be "
                        f"automatically injected into the settlement letter by Python — not LLM.",
                        WARN_COLOR,
                        "📄",
                    ),
                    unsafe_allow_html=True,
                )
    elif not cs.get("settlement_eligible", True):
        st.markdown(
            alert_box(
                "Settlement not eligible — active bankruptcy stay, cease & desist, "
                "or deceased account prevents settlement offer.",
                HITL_COLOR,
                "🛑",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.warning("No settlement tiers available for this balance.", icon="⚠️")

    # ── Credit reporting ───────────────────────────────────────────────────
    st.markdown("---")
    section_header("📁 Credit Reporting Determination")
    st.caption("Python-computed per FCRA 15 U.S.C. § 1681 and CFPB 2025 medical debt rule.")

    cr_color = AUTO_COLOR if cs["credit_reporting_appropriate"] else WARN_COLOR
    cr_label = "ELIGIBLE TO REPORT" if cs["credit_reporting_appropriate"] else "NOT ELIGIBLE — DO NOT REPORT"
    st.markdown(badge(cr_label, cr_color), unsafe_allow_html=True)

    rules = [
        (f"Balance ≥ $100.00", cs["current_balance"] >= 100.0),
        (f"Medical debt: balance ≥ $500.00 (CFPB 2025)",
         not cs["medical_debt_flag"] or cs["current_balance"] >= 500.0),
        (f"Days delinquent: {cs['days_delinquent']} (charge-off threshold: 180 days)",
         cs["days_delinquent"] >= 180),
        ("Bankruptcy stay: NOT active", not cs["bankruptcy_stay_active"]),
    ]
    for rule_text, passed in rules:
        icon = "✅" if passed else "❌"
        st.markdown(f"{icon} {rule_text}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Collector Review (HITL Gate)
# ══════════════════════════════════════════════════════════════════════════════

def render_hitl_tab():
    st.header("Collector Review — HITL Gate")
    st.caption(
        "This is the LangGraph `human_review_gate` node (`interrupt_before=[\"human_review_gate\"]`). "
        "The graph physically cannot advance to communication drafting or audit finalization "
        "until this node executes. This is a LangGraph compile-time directive — not application logic."
    )

    cs = st.session_state.case_state
    if not cs:
        st.info("Run a scenario from the **Submit Case** tab first.", icon="ℹ️")
        return

    # ── Already decided ────────────────────────────────────────────────────
    if st.session_state.hitl_decision_made and cs.get("collections_outcome"):
        outcome = cs["collections_outcome"]
        oc_color = OUTCOME_COLORS.get(outcome, "#6c757d")
        st.markdown(
            alert_box(
                f"**Decision recorded.** Outcome: **{outcome}**  \n"
                f"Reviewer: `{cs.get('reviewer_id', 'UNKNOWN')}`  \n"
                f"Notes: {cs.get('reviewer_notes', 'None')}  \n"
                f"Communication drafting and audit finalization have been triggered.",
                AUTO_COLOR,
                "✅",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(f"#### Final Outcome: {badge(outcome, oc_color)}", unsafe_allow_html=True)

        if st.button("Reset — Enter New Decision"):
            st.session_state.hitl_decision_made = False
            cs["collections_outcome"] = None
            cs["reviewer_decision"]   = None
            st.rerun()
        return

    # ── HITL conditions display ────────────────────────────────────────────
    if cs["hitl_required"]:
        st.markdown(
            alert_box(
                f"**Review required.** This case has {len(cs['hitl_conditions'])} HITL condition(s). "
                f"Escalation: **{cs['escalation_level']}**. "
                f"Review all findings before entering a decision.",
                HITL_COLOR,
                "🛑",
            ),
            unsafe_allow_html=True,
        )

        if cs["hitl_conditions"]:
            st.markdown("**Active HITL Conditions (Python `ALWAYS_HITL_CONDITIONS` frozenset):**")
            condition_details = {
                "SCRA_DETECTED":             "Active military — SCRA 6% rate cap applies. Supervisor must approve.",
                "BANKRUPTCY_STAY_DETECTED":  "Automatic stay (11 U.S.C. § 362) — ALL collection must stop.",
                "DISPUTE_RECEIVED":          "Debt disputed — 30-day collection hold; send validation materials.",
                "CEASE_DESIST_RECEIVED":     "C&D in effect — only legal action notice permitted (FDCPA § 805(c)).",
                "DECEASED_ACCOUNT":          "Consumer deceased — estate/executor procedures; state probate law.",
                "SETTLEMENT_HIGH_VALUE":     "Settlement >$10K or discount >40% — supervisor authorization required.",
                "LITIGATION_HIGH_RISK":      "High litigation risk — legal review before any further collection.",
                "REGULATORY_COMPLAINT":      "CFPB/state AG complaint — compliance officer review required.",
                "MINOR_ACCOUNT":             "Debtor under 18 — legal guardian required; consumer protection law.",
            }
            for cond in cs["hitl_conditions"]:
                detail = condition_details.get(cond, "Human review required.")
                st.markdown(
                    f"- {badge(cond, HITL_COLOR)} {detail}",
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            alert_box(
                "No HITL conditions detected on this case. Decision can still be entered "
                "to override the auto-route, or close without supervisor review.",
                AUTO_COLOR,
                "✅",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── HITL decision form ─────────────────────────────────────────────────
    st.subheader("Enter Decision")

    c1, c2 = st.columns(2)
    with c1:
        reviewer_id = st.text_input(
            "Reviewer ID (Employee / Badge Number)",
            placeholder="e.g., EMP-00147 or SUP-00823",
        )
        decision = st.radio(
            "Decision",
            options=[
                "PAYMENT_PLAN",
                "SETTLEMENT",
                "HARDSHIP_PLAN",
                "FULL_PAYMENT",
                "CEASE_AND_DESIST",
                "LEGAL_REFERRAL",
            ],
            captions=[
                "Approve standard or hardship payment arrangement",
                "Approve settlement offer (requires settlement_eligible=True)",
                "Approve hardship-modified plan (reduced payments)",
                "Consumer paid in full",
                "Issue cease & desist acknowledgment letter",
                "Refer to legal counsel or outside collections attorney",
            ],
        )

    with c2:
        reviewer_notes = st.text_area(
            "Reviewer Notes (required for CEASE_AND_DESIST and LEGAL_REFERRAL)",
            height=160,
            placeholder="Enter compliance rationale, authorization level, "
                        "approval chain, or escalation notes...",
        )

        # Validation warnings
        if decision == "SETTLEMENT" and not cs.get("settlement_eligible", True):
            st.warning(
                "Settlement not eligible — bankruptcy stay, C&D, or deceased account active.", icon="⚠️"
            )
        if decision in ("CEASE_AND_DESIST", "LEGAL_REFERRAL") and not reviewer_notes.strip():
            st.warning(f"Reviewer notes are required for {decision}.", icon="⚠️")
        if decision == "SETTLEMENT" and cs.get("settlement_high_value", False):
            st.markdown(
                alert_box(
                    "HIGH-VALUE SETTLEMENT — Amount >$10K or discount >40%. "
                    "Ensure your authorization level matches the required tier.",
                    WARN_COLOR,
                    "⚠️",
                ),
                unsafe_allow_html=True,
            )

    submit_ok = True
    if not reviewer_id.strip():
        submit_ok = False
    if decision in ("CEASE_AND_DESIST", "LEGAL_REFERRAL") and not reviewer_notes.strip():
        submit_ok = False

    if st.button("Submit Decision", type="primary", disabled=not submit_ok):
        cs["reviewer_id"]       = reviewer_id.strip()
        cs["reviewer_decision"] = decision
        cs["reviewer_notes"]    = reviewer_notes.strip()
        cs["collections_outcome"] = decision
        cs["human_review_required"] = False  # Explicit False — gate passed

        # Add HITL audit entry
        cs["audit_trail"].append({
            "node":      "human_review_gate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message":   (
                f"HITL decision by {reviewer_id}: {decision}. "
                f"Notes: {reviewer_notes.strip() or 'none'}. "
                f"human_review_required set to False (explicit Python False — gate cleared)."
            ),
        })
        # Add communication drafting entry
        cs["audit_trail"].append({
            "node":      "communication_drafting",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message":   (
                f"Collection letter drafted for outcome: {decision}. "
                f"FDCPA mini-Miranda injected by Python. "
                f"{'IRS 1099-C notice injected. ' if cs.get('requires_1099c') else ''}"
                f"SCRA 6% rate cap note injected. " if cs["scra_active_military"] else ""
                f"(LLM produced letter body — Python injected all required disclosures.)"
            ),
        })
        # Add audit finalize entry
        cs["audit_trail"].append({
            "node":      "audit_finalize",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message":   (
                f"Case {cs['case_id']} finalized. Outcome: {decision}. "
                f"Retention policy: 7 years (FCRA). "
                f"Audit trail append-only — stored to S3 Object Lock GOVERNANCE mode."
            ),
        })

        st.session_state.hitl_decision_made = True
        st.session_state.case_state = cs
        st.success(f"Decision '{decision}' recorded by {reviewer_id}.")
        st.rerun()

    if not submit_ok:
        if not reviewer_id.strip():
            st.caption("⚠ Enter Reviewer ID to enable submission.")
        elif decision in ("CEASE_AND_DESIST", "LEGAL_REFERRAL"):
            st.caption("⚠ Reviewer notes required for this decision.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Audit Trail
# ══════════════════════════════════════════════════════════════════════════════

def render_audit_tab():
    st.header("Audit Trail")
    st.caption(
        "Append-only audit trail — each node appends one entry using `list(current) + [new_entry]`. "
        "Prior entries are never modified. Stored with 7-year retention policy per FCRA 15 U.S.C. § 1681. "
        "In production: S3 Object Lock GOVERNANCE mode; DynamoDB case registry with stream for replication."
    )

    cs = st.session_state.case_state
    if not cs:
        st.info("Run a scenario from the **Submit Case** tab first.", icon="ℹ️")
        return

    trail = cs.get("audit_trail", [])

    # ── Summary metrics ────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Case ID", cs["case_id"])
    with m2:
        st.metric("Audit Entries", len(trail))
    with m3:
        outcome = cs.get("collections_outcome", "PENDING")
        oc_color = OUTCOME_COLORS.get(outcome, "#6c757d")
        st.markdown(f"**Final Outcome:** {badge(outcome or 'PENDING', oc_color)}", unsafe_allow_html=True)
    with m4:
        st.metric("FCRA Retention", "7 years")

    st.markdown("---")

    # ── Node-by-node entries ───────────────────────────────────────────────
    node_icons = {
        "debt_intake":            "1️⃣",
        "fdcpa_compliance_check": "2️⃣",
        "scra_bankruptcy_check":  "3️⃣",
        "consumer_profile":       "4️⃣",
        "debt_validation":        "5️⃣",
        "payment_plan_optimizer": "6️⃣",
        "collections_strategy":   "7️⃣",
        "risk_scoring":           "8️⃣",
        "routing_decision":       "9️⃣",
        "human_review_gate":      "🔟",
        "communication_drafting": "1️⃣1️⃣",
        "audit_finalize":         "1️⃣2️⃣",
    }
    node_colors = {
        "debt_intake":            "#0d6efd",
        "fdcpa_compliance_check": "#6610f2",
        "scra_bankruptcy_check":  "#d63384",
        "consumer_profile":       "#0dcaf0",
        "debt_validation":        "#198754",
        "payment_plan_optimizer": "#20c997",
        "collections_strategy":   "#fd7e14",
        "risk_scoring":           "#dc3545",
        "routing_decision":       "#dc3545",
        "human_review_gate":      "#ffc107",
        "communication_drafting": "#0d6efd",
        "audit_finalize":         "#198754",
    }

    for entry in trail:
        node = entry.get("node", "unknown")
        icon = node_icons.get(node, "▪️")
        color = node_colors.get(node, "#6c757d")
        ts   = entry.get("timestamp", "")
        msg  = entry.get("message", "")

        with st.container():
            st.markdown(
                f'<div style="border-left:4px solid {color};padding:8px 16px;margin:6px 0;">'
                f'<strong>{icon} {node.replace("_", " ").title()}</strong>'
                f'<br><small style="color:#6c757d;">{ts}</small>'
                f'<br>{msg}'
                f'</div>',
                unsafe_allow_html=True,
            )

    if not trail:
        st.info("No audit entries yet.", icon="ℹ️")

    # ── Raw JSON export ────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Export Audit Trail (JSON)", expanded=False):
        audit_export = {
            "case_id":          cs["case_id"],
            "account_id":       cs["account_id"],
            "generated_at":     datetime.now(timezone.utc).isoformat(),
            "retention_policy": "7 years (FCRA 15 U.S.C. § 1681)",
            "storage":          "S3 Object Lock GOVERNANCE mode",
            "entries":          trail,
        }
        st.json(audit_export)
        st.download_button(
            label="Download Audit Trail JSON",
            data=json.dumps(audit_export, indent=2),
            file_name=f"audit_{cs['case_id']}.json",
            mime="application/json",
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — About
# ══════════════════════════════════════════════════════════════════════════════

def render_about_tab():
    st.header("About — Collections & Recovery Agent")
    st.markdown(
        "Agent 12 in the FSI AI Suite. A FDCPA/Reg F/SCRA-compliant LangGraph agent "
        "that automates the debt collections decision pipeline while enforcing mandatory "
        "human-in-the-loop review for all high-risk regulatory conditions."
    )

    st.markdown("---")

    # ── 12-node pipeline ───────────────────────────────────────────────────
    section_header("🏗 12-Node Pipeline")
    st.markdown("""
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                AGENT 12 — COLLECTIONS & RECOVERY PIPELINE                   │
│                                                                             │
│  1. debt_intake           PII masking · FDCPA applicability · case_id       │
│       │                                                                     │
│  2. fdcpa_compliance_check  8am–9pm local time (pytz) · Reg F 7-in-7        │
│       │                     C&D check · dispute flag · regulatory_risk_tier │
│  3. scra_bankruptcy_check  SCRA active military · bankruptcy § 362 stay     │
│       │                    SOL computation (50-state matrix + DC)           │
│  4. consumer_profile      [LLM] Hardship assessment narrative               │
│       │                   hardship_plan_eligible (threshold: score ≥ 0.60)  │
│  5. debt_validation       Days delinquent · medical_debt_flag               │
│       │                   credit_reporting (FCRA) · settlement_eligible     │
│  6. payment_plan_optimizer  Collectability score (5-factor weighted)        │
│       │                     Payment plans (Python: balance ÷ term)          │
│       │                     Settlement tiers (TIER_1–TIER_4, frozenset)     │
│  7. collections_strategy  [LLM] Supervisor-facing strategy narrative        │
│       │                                                                     │
│  8. risk_scoring          ALWAYS_HITL_CONDITIONS frozenset membership check  │
│       │                   9 conditions · immutable (TypeError on .add())    │
│  9. routing_decision      FDCPA violations force HITL regardless            │
│       │                   human_review_required is False → auto-route       │
│       │                   None / 0 / missing → HITL (fail-safe)             │
│       │                                                                     │
│       ├─────── HITL ──▶  10. human_review_gate   [interrupt_before]        │
│       │                       Supervisor: 6 valid decisions                 │
│       │                       human_review_required = False (explicit)      │
│       └─── auto ──────▶                                                     │
│                           11. communication_drafting  [LLM]                 │
│                               Python injects: mini-Miranda, validation       │
│                               notice, SCRA note, 1099-C notice              │
│                                                                             │
│                           12. audit_finalize  Append-only · 7-yr retention │
└─────────────────────────────────────────────────────────────────────────────┘
```
""")

    # ── LLM / Python boundary ──────────────────────────────────────────────
    section_header("🔒 LLM / Python Boundary")
    st.caption(
        "This is the most important security and compliance distinction in Agent 12. "
        "All routing decisions, HITL triggers, financial amounts, and regulatory determinations "
        "are Python-computed and auditable. LLM produces narrative only."
    )

    boundary_data = [
        ("Contact time enforcement (8am–9pm)",          "Python — pytz UTC conversion",    "FDCPA § 805(a)(1)"),
        ("Reg F 7-in-7 call limit",                     "Python — integer comparison",      "12 CFR 1006.14(b)"),
        ("SCRA 6% rate cap detection",                  "Python — boolean flag check",      "50 U.S.C. § 3937"),
        ("Bankruptcy stay enforcement",                  "Python — boolean flag check",      "11 U.S.C. § 362"),
        ("SOL computation (50 states + DC)",            "Python — STATE_SOL_YEARS dict",    "State law"),
        ("Collectability score (5-factor)",             "Python — weighted arithmetic",     "SR 11-7"),
        ("Payment plan amounts (balance ÷ term)",       "Python — division",                "FDCPA § 808"),
        ("Settlement tier authorization levels",        "Python — SETTLEMENT_TIERS dict",   "Internal policy"),
        ("HITL conditions (9 conditions)",              "Python — frozenset membership",    "ALWAYS_HITL_CONDITIONS"),
        ("HITL routing (is False check)",               "Python — identity comparison",     "Fail-safe design"),
        ("Medical debt $500 threshold",                 "Python — numeric comparison",      "CFPB 2025 rule"),
        ("IRS 1099-C threshold (≥$600)",               "Python — numeric comparison",      "26 U.S.C. § 6050P"),
        ("FDCPA mini-Miranda language",                 "Python — verbatim string inject",  "FDCPA § 807(11)"),
        ("Validation notice text",                      "Python — verbatim string inject",  "FDCPA § 809"),
        ("Hardship assessment narrative",               "LLM (GPT-4o)",                     "Narrative only"),
        ("Collections strategy narrative",              "LLM (GPT-4o)",                     "Narrative only"),
        ("Collection letter body",                      "LLM (GPT-4o)",                     "Narrative only — disclosures Python-injected"),
        ("Audit trail entries",                         "Python — append-only list",        "FCRA / FDCPA"),
    ]

    boundary_rows = []
    for decision, engine, regulation in boundary_data:
        is_llm = "LLM" in engine
        boundary_rows.append({
            "Decision / Computation": decision,
            "Engine":                 engine,
            "Regulation":             regulation,
            "Auditable?":             "✅ Deterministic" if not is_llm else "📝 Narrative",
        })

    st.dataframe(boundary_rows, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── HITL conditions ────────────────────────────────────────────────────
    section_header("🛑 9 HITL Conditions (ALWAYS_HITL_CONDITIONS frozenset)")
    st.caption(
        "Python frozenset — immutable at runtime. Attempting `.add()` raises TypeError. "
        "All 9 conditions are Python boolean flag checks against the CollectionsState dict. "
        "LLM cannot trigger, suppress, or modify these conditions."
    )

    hitl_data = [
        ("SCRA_DETECTED",            "Active military — SCRA 6% rate cap, supervisor required",      "50 U.S.C. § 3937"),
        ("BANKRUPTCY_STAY_DETECTED", "Automatic stay — ALL collection must stop; escalate to compliance", "11 U.S.C. § 362"),
        ("DISPUTE_RECEIVED",         "Debt disputed — 30-day collection hold; send validation notice",  "FDCPA § 809"),
        ("CEASE_DESIST_RECEIVED",    "C&D active — only legal action notice permitted",               "FDCPA § 805(c)"),
        ("DECEASED_ACCOUNT",         "Consumer deceased — estate/executor procedures",                 "State probate law"),
        ("SETTLEMENT_HIGH_VALUE",    "Settlement >$10K or discount >40% — supervisor authorization",   "Internal policy"),
        ("LITIGATION_HIGH_RISK",     "Low collectability + active SOL + balance >$5K — legal review",  "Risk management"),
        ("REGULATORY_COMPLAINT",     "CFPB/state AG complaint — compliance officer review",           "Dodd-Frank § 1031"),
        ("MINOR_ACCOUNT",            "Debtor under 18 — legal guardian required",                     "State consumer law"),
    ]

    hitl_rows = [
        {"Condition": c, "Description": d, "Regulatory Basis": r}
        for c, d, r in hitl_data
    ]
    st.dataframe(hitl_rows, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Security architecture ──────────────────────────────────────────────
    section_header("🔐 Security Architecture")
    st.markdown("""
**Data Encryption**
- TLS 1.3 in transit (ALB → ECS → Streamlit)
- AWS KMS customer-managed key for S3 Object Lock (7-year FCRA retention), DynamoDB case registry, and Secrets Manager (OpenAI key + DB credentials)
- No PII in environment variables — Secrets Manager only

**PII Masking at Intake (Node 1)**
- Account numbers → `ACCT-****{last4}` before any LLM prompt or log entry
- SSNs → `SSN-***-**-{last4}` (when present)
- Masked IDs used in all LLM prompts, CloudWatch logs, and audit trail

**HITL Enforcement**
- LangGraph `interrupt_before=["human_review_gate"]` at compile time
- Routing: `human_review_required is False` explicit identity check
- `ALWAYS_HITL_CONDITIONS` frozenset — immutable at runtime (TypeError on `.add()`)
- 9 conditions cover all major federal consumer protection scenarios

**Audit Integrity**
- Append-only audit trail: `list(current) + [new_entry]` — prior entries never modified
- S3 Object Lock GOVERNANCE mode — 7-year retention (FCRA 15 U.S.C. § 1681)
- DynamoDB case registry with PITR and Streams for cross-region replication
- CloudWatch Logs → S3 export with immutable retention for discovery/litigation hold

**Network Isolation**
- VPC with private subnets; ECS tasks have no public IP
- WAF rule: max 30 HITL review submissions per 5 minutes per IP (prevents automation bypass)
- Security Groups: ALB port 8512 → ECS only; ECS → Secrets Manager/S3/DynamoDB only
- Non-root UID 1000; read-only root filesystem in container
""")

    # ── Regulatory coverage ────────────────────────────────────────────────
    section_header("⚖️ Regulatory Coverage")
    reg_data = [
        ("FDCPA", "Fair Debt Collection Practices Act — 15 U.S.C. § 1692",
         "Contact hours, mini-Miranda, validation notice, prohibited representations"),
        ("CFPB Regulation F", "12 CFR Part 1006 (Nov 2021)",
         "7-in-7 call limit, post-conversation wait, limited content messages, e-comm opt-out"),
        ("SCRA", "Servicemembers Civil Relief Act — 50 U.S.C. § 3937",
         "6% interest rate cap, retroactive to active duty date, supervisor approval required"),
        ("Bankruptcy Code", "11 U.S.C. § 362 — Automatic Stay",
         "All collection activity stops; proof of claim; no consumer contact"),
        ("FCRA", "Fair Credit Reporting Act — 15 U.S.C. § 1681",
         "7-year negative reporting; medical debt <$500 not reportable (CFPB 2025)"),
        ("UDAAP", "Dodd-Frank § 1031",
         "CFPB/state AG complaint → HITL; unfair/deceptive/abusive acts enforced"),
        ("IRS 26 U.S.C. § 6050P", "Debt forgiveness reporting",
         "IRS Form 1099-C for forgiven debt ≥$600; Python-injected into settlement letter"),
        ("TCPA", "Telephone Consumer Protection Act — 47 U.S.C. § 227",
         "Electronic communication opt-out required (Reg F); no auto-dial to cell without consent"),
    ]

    reg_rows = [
        {"Regulation": r, "Authority": a, "Agent 12 Coverage": c}
        for r, a, c in reg_data
    ]
    st.dataframe(reg_rows, use_container_width=True, hide_index=True)

    # ── Quick start ────────────────────────────────────────────────────────
    st.markdown("---")
    section_header("🚀 Quick Start")
    st.code("""
# 1. Clone and navigate
git clone https://github.com/virtualryder/fsi-ai-agents
cd fsi-ai-agents/12-collections-recovery-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env: OPENAI_API_KEY, INSTITUTION_NAME, COLLECTIONS_COMPLIANCE_EMAIL

# 4. Run (demo mode — no API key required for UI)
streamlit run app.py --server.port 8512

# 5. Run with live LLM narratives
OPENAI_API_KEY=sk-... streamlit run app.py --server.port 8512

# 6. Run tests
pytest tests/ -v
""", language="bash")

    # ── Related agents ─────────────────────────────────────────────────────
    st.markdown("---")
    section_header("🔗 Related Agents in FSI AI Suite")
    st.markdown("""
| Agent | Function | Integration with Agent 12 |
|-------|----------|--------------------------|
| **Agent 01** | Financial Crime Investigation | Provides fraud disposition that may trigger collections referral |
| **Agent 04** | Fraud Detection | Fraud-confirmed accounts may be excluded from standard collections |
| **Agent 08** | Credit Underwriting | Collectability inputs (payment_history_factor, hardship_score) sourced from underwriting model |
| **Agent 09** | Document Intelligence | Dispute letter and validation document extraction |
| **Agent 10** | Payments Compliance | Confirms ACH authorization for payment plan agreements |
| **Agent 11** | Model Risk Management | Validates collectability scoring model under SR 11-7 (FAIR_LENDING_FLAG check) |
""")


# ── Render tabs ───────────────────────────────────────────────────────────────
with tab1:
    render_submit_tab()
with tab2:
    render_findings_tab()
with tab3:
    render_analysis_tab()
with tab4:
    render_hitl_tab()
with tab5:
    render_audit_tab()
with tab6:
    render_about_tab()
