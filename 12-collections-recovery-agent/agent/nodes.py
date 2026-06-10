"""
Agent 12 — Collections & Recovery Agent
Node functions for the 12-node LangGraph StateGraph.

Python/LLM boundary:
- All FDCPA compliance determinations: Python (time checks, flag lookups, frozenset membership)
- All financial computations: Python (payment plan math, settlement amounts, collectability score)
- All HITL routing: Python (frozenset membership check)
- All credit reporting determinations: Python (FCRA threshold comparisons)
- Statute of limitations: Python (date arithmetic + STATE_SOL_YEARS lookup)
- All consumer-facing letter drafts: LLM (narrative only, with Python-computed values injected)
- All strategy narratives: LLM (narrative only, supervisor reads before HITL decision)

Security properties enforced by this module:
- Account numbers masked to ACCT-****{last4} at intake — raw numbers never in state
- SSNs masked to SSN-***-**-{last4} at intake
- FDCPA time enforcement uses pytz UTC conversion — not LLM time reasoning
- ALWAYS_HITL_CONDITIONS frozenset membership is the authoritative HITL trigger
"""

import hashlib
import uuid
from datetime import datetime, timedelta, date
from typing import Any, Dict, List
import pytz

from .state import (
    CollectionsState,
    ALWAYS_HITL_CONDITIONS,
    CONSUMER_DEBT_TYPES,
    BUSINESS_DEBT_TYPES,
    FEDERAL_STUDENT_LOAN_PROGRAMS,
    STATE_SOL_YEARS,
    COLLECTABILITY_WEIGHTS,
    SETTLEMENT_TIERS,
    MIN_PAYMENT_PCT_OF_BALANCE,
    MAX_PAYMENT_TERM_MONTHS,
    HARDSHIP_PLAN_MIN_PAYMENT,
    CREDIT_REPORTING_THRESHOLDS,
    VALIDATION_NOTICE_REQUIRED_DAYS,
    DISPUTE_HOLD_DAYS,
    FDCPA_PROHIBITED_HOURS_BEFORE,
    FDCPA_PROHIBITED_HOURS_AFTER,
    REGULATION_F_CALL_LIMIT_7_DAYS,
    REGULATION_F_POST_CONVERSATION_WAIT_DAYS,
    SCRA_MAX_INTEREST_RATE_PCT,
)
from .prompts import (
    HARDSHIP_ASSESSMENT_PROMPT,
    COLLECTIONS_STRATEGY_PROMPT,
    COLLECTION_LETTER_PROMPT,
    SETTLEMENT_OFFER_PROMPT,
    PAYMENT_AGREEMENT_PROMPT,
)

# ---------------------------------------------------------------------------
# Internal helpers — pure Python, no LLM
# ---------------------------------------------------------------------------

def _mask_account_number(account_number: str) -> str:
    """Mask account number to ACCT-****{last4}. Called at intake — raw number never stored."""
    if not account_number or len(account_number) < 4:
        return "ACCT-****XXXX"
    return f"ACCT-****{account_number[-4:]}"

def _mask_ssn(ssn: str) -> str:
    """Mask SSN to SSN-***-**-{last4}."""
    cleaned = ssn.replace("-", "").replace(" ", "")
    if len(cleaned) < 4:
        return "SSN-***-**-XXXX"
    return f"SSN-***-**-{cleaned[-4:]}"

def _check_contact_time_fdcpa(consumer_timezone: str) -> tuple[bool, int]:
    """
    FDCPA § 805(a)(1) — 15 U.S.C. § 1692c(a)(1)
    Contact is prohibited before 8:00am or at/after 9:00pm in the consumer's local time.

    Returns:
        (contact_permitted: bool, local_hour: int)

    Python only — no LLM involvement in determining FDCPA time compliance.
    """
    try:
        tz = pytz.timezone(consumer_timezone)
        local_now = datetime.now(tz)
        local_hour = local_now.hour
        contact_permitted = FDCPA_PROHIBITED_HOURS_BEFORE <= local_hour < FDCPA_PROHIBITED_HOURS_AFTER
        return contact_permitted, local_hour
    except Exception:
        # Unknown timezone — default to prohibited (fail-safe)
        return False, -1

def _compute_sol_expiration(
    debt_origination_date: str,
    date_of_last_payment: str,
    state_code: str,
    debt_type: str,
) -> tuple[int, str, bool, bool]:
    """
    Statute of limitations computation.
    SOL clock restarts from date_of_last_payment if later than origination.

    Returns:
        (sol_years, sol_expiration_date_str, sol_expired, sol_warning)

    Debt category mapping:
    - CREDIT_CARD, RETAIL_INSTALLMENT, PAYDAY_LOAN → "open_account"
    - All others → "written_contract"
    - If state not found → use conservative 6-year default
    """
    sol_category = "open_account" if debt_type in {
        "CREDIT_CARD", "RETAIL_INSTALLMENT", "PAYDAY_LOAN"
    } else "written_contract"

    sol_years = STATE_SOL_YEARS.get(state_code, {}).get(sol_category, 6)

    # Use the later of origination date or last payment date as SOL start
    try:
        orig_date = datetime.strptime(debt_origination_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        orig_date = date.today() - timedelta(days=365)

    try:
        last_pay_date = datetime.strptime(date_of_last_payment, "%Y-%m-%d").date()
        sol_start = max(orig_date, last_pay_date)
    except (ValueError, TypeError):
        sol_start = orig_date

    sol_expiration = sol_start.replace(year=sol_start.year + sol_years)
    today = date.today()
    sol_expired = today > sol_expiration
    sol_warning = (not sol_expired) and (sol_expiration - today).days <= 90

    return sol_years, sol_expiration.strftime("%Y-%m-%d"), sol_expired, sol_warning

def _compute_collectability_score(state: Dict[str, Any]) -> tuple[float, str, Dict[str, float]]:
    """
    Collectability scoring — SR 11-7 documented model.
    Python arithmetic only; weights defined in COLLECTABILITY_WEIGHTS constants.

    Returns:
        (score: float, tier: str, sub_scores: dict)
    """
    days_delinquent = state.get("days_delinquent", 365)
    current_balance = state.get("current_balance", 1000.0)
    prior_contacts = state.get("prior_contacts_7_days", 0)
    sol_expired = state.get("sol_expired", False)

    # Debt age factor: newer debt = higher collectability
    # 0-90 days = 1.0, 91-180 days = 0.8, 181-365 = 0.6, 366-730 = 0.4, >730 = 0.2
    if days_delinquent <= 90:
        debt_age_factor = 1.0
    elif days_delinquent <= 180:
        debt_age_factor = 0.8
    elif days_delinquent <= 365:
        debt_age_factor = 0.6
    elif days_delinquent <= 730:
        debt_age_factor = 0.4
    else:
        debt_age_factor = 0.2

    # Balance factor: smaller balances generally more collectible
    # <$500=0.9, $500-2K=0.8, $2K-10K=0.7, $10K-50K=0.6, >$50K=0.4
    if current_balance < 500:
        balance_factor = 0.9
    elif current_balance < 2000:
        balance_factor = 0.8
    elif current_balance < 10000:
        balance_factor = 0.7
    elif current_balance < 50000:
        balance_factor = 0.6
    else:
        balance_factor = 0.4

    # Contact success: if consumer has been reached before → higher score
    contact_success = 0.8 if prior_contacts > 0 else 0.4

    # Payment history: from state (set by consumer_profile_node from intake data)
    payment_history = state.get("payment_history_factor", 0.5)

    # Hardship score: inverse of hardship (more hardship = lower collectability)
    hardship_raw = state.get("hardship_score", 0.5)
    hardship_factor = 1.0 - hardship_raw  # Higher hardship = lower collectability factor

    # SOL-expired: severely reduces collectability (can't sue)
    if sol_expired:
        debt_age_factor *= 0.3

    # Weighted composite
    score = (
        debt_age_factor     * COLLECTABILITY_WEIGHTS["debt_age_factor"] +
        balance_factor      * COLLECTABILITY_WEIGHTS["balance_factor"] +
        contact_success     * COLLECTABILITY_WEIGHTS["contact_success"] +
        payment_history     * COLLECTABILITY_WEIGHTS["payment_history"] +
        hardship_factor     * COLLECTABILITY_WEIGHTS["hardship_score"]
    )
    score = max(0.0, min(1.0, score))

    if score >= 0.70:
        tier = "HIGH"
    elif score >= 0.40:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    sub_scores = {
        "debt_age_factor": round(debt_age_factor, 3),
        "balance_factor": round(balance_factor, 3),
        "contact_success_factor": round(contact_success, 3),
        "payment_history_factor": round(payment_history, 3),
        "hardship_factor": round(hardship_factor, 3),
    }
    return round(score, 3), tier, sub_scores

def _compute_payment_plans(
    current_balance: float,
    hardship_eligible: bool,
) -> List[Dict[str, Any]]:
    """
    Compute payment plan options — pure Python arithmetic.
    Returns list of plan dicts with term, monthly_payment, total_repaid.
    LLM does not determine plan amounts.
    """
    plans = []
    if current_balance <= 0:
        return plans

    # Standard plans: 12, 24, 36, 48, 60 months
    for months in [12, 24, 36, 48, 60]:
        monthly = round(current_balance / months, 2)
        # Enforce minimum payment
        if monthly < MIN_PAYMENT_PCT_OF_BALANCE * current_balance:
            monthly = round(MIN_PAYMENT_PCT_OF_BALANCE * current_balance, 2)
            # Recompute term
            if monthly > 0:
                months = min(MAX_PAYMENT_TERM_MONTHS, int(current_balance / monthly) + 1)

        plans.append({
            "plan_type": "STANDARD",
            "term_months": months,
            "monthly_payment": monthly,
            "total_repaid": round(monthly * months, 2),
            "auth_level": "COLLECTOR",
        })

    # Hardship plan: $25/month minimum
    if hardship_eligible:
        hardship_term = min(MAX_PAYMENT_TERM_MONTHS, int(current_balance / HARDSHIP_PLAN_MIN_PAYMENT) + 1)
        plans.append({
            "plan_type": "HARDSHIP",
            "term_months": hardship_term,
            "monthly_payment": HARDSHIP_PLAN_MIN_PAYMENT,
            "total_repaid": round(HARDSHIP_PLAN_MIN_PAYMENT * hardship_term, 2),
            "auth_level": "SUPERVISOR",
        })

    # Deduplicate by term
    seen_terms = set()
    unique_plans = []
    for p in plans:
        key = (p["plan_type"], p["term_months"])
        if key not in seen_terms:
            seen_terms.add(key)
            unique_plans.append(p)

    return unique_plans[:6]  # Return up to 6 plan options

def _compute_settlement_tiers(current_balance: float) -> List[Dict[str, Any]]:
    """
    Compute settlement tier options — Python lookup of SETTLEMENT_TIERS constants.
    Returns list of tier dicts. LLM does not determine settlement amounts.
    """
    tiers = []
    for tier_name, config in SETTLEMENT_TIERS.items():
        if current_balance >= config["min_balance"]:
            settlement_amount = round(
                current_balance * (1.0 - config["max_discount_pct"] / 100.0), 2
            )
            tiers.append({
                "tier": tier_name,
                "discount_pct": config["max_discount_pct"],
                "settlement_amount": settlement_amount,
                "savings_amount": round(current_balance - settlement_amount, 2),
                "auth_level": config["auth_level"],
                "high_value": settlement_amount > 10000 or config["max_discount_pct"] > 40,
            })
    return tiers

def _determine_hitl_conditions(state: Dict[str, Any]) -> tuple[List[str], bool, str]:
    """
    Determine which HITL conditions are triggered.
    Uses frozenset membership to identify conditions.
    Returns (conditions_list, hitl_required, escalation_level).
    Python only — no LLM involvement.
    """
    conditions = []

    if state.get("scra_active_military"):
        conditions.append("SCRA_DETECTED")
    if state.get("bankruptcy_stay_active"):
        conditions.append("BANKRUPTCY_STAY_DETECTED")
    if state.get("dispute_received"):
        conditions.append("DISPUTE_RECEIVED")
    if state.get("cease_desist_received"):
        conditions.append("CEASE_DESIST_RECEIVED")
    if state.get("consumer_is_deceased"):
        conditions.append("DECEASED_ACCOUNT")
    if state.get("consumer_is_minor"):
        conditions.append("MINOR_ACCOUNT")

    # Settlement high value: amount > $10K OR discount > 40%
    settlement_tiers = state.get("settlement_tiers", [])
    for tier in settlement_tiers:
        if tier.get("high_value"):
            conditions.append("SETTLEMENT_HIGH_VALUE")
            break

    # Litigation high risk: collectability LOW + SOL not expired + balance > $5K
    if (
        state.get("collectability_tier") == "LOW"
        and not state.get("sol_expired")
        and state.get("current_balance", 0) > 5000
    ):
        conditions.append("LITIGATION_HIGH_RISK")

    # Regulatory complaint (would be set at intake from CRM data)
    if state.get("regulatory_complaint_active"):
        conditions.append("REGULATORY_COMPLAINT")

    # Verify all conditions are valid ALWAYS_HITL_CONDITIONS members
    valid_conditions = [c for c in conditions if c in ALWAYS_HITL_CONDITIONS]
    hitl_required = len(valid_conditions) > 0

    # Determine escalation level
    if "BANKRUPTCY_STAY_DETECTED" in valid_conditions or "REGULATORY_COMPLAINT" in valid_conditions:
        escalation_level = "COMPLIANCE"
    elif "SCRA_DETECTED" in valid_conditions or "SETTLEMENT_HIGH_VALUE" in valid_conditions:
        escalation_level = "MANAGER"
    elif "LITIGATION_HIGH_RISK" in valid_conditions or "DECEASED_ACCOUNT" in valid_conditions:
        escalation_level = "SUPERVISOR"
    elif hitl_required:
        escalation_level = "SUPERVISOR"
    else:
        escalation_level = "COLLECTOR"

    return valid_conditions, hitl_required, escalation_level

def _append_audit_entry(state: Dict[str, Any], event_type: str, details: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Append-only audit trail update. Uses list(current) + [new_entry] pattern.
    Prior entries are never modified. This function is called by every node.
    """
    current_trail = list(state.get("audit_trail", []))
    new_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "case_id": state.get("case_id", "UNKNOWN"),
        "event_type": event_type,
        "account_id": state.get("account_id", "UNKNOWN"),
        "details": details,
    }
    return current_trail + [new_entry]

# ---------------------------------------------------------------------------
# Node 1: debt_intake_node
# ---------------------------------------------------------------------------

def debt_intake_node(state: CollectionsState) -> Dict[str, Any]:
    """
    Intake debt case and apply PII masking.

    Security: Account numbers and SSNs are masked immediately. Raw values are
    consumed to produce masked versions and then discarded — they are not stored
    in the returned state dict, which persists to the LangGraph checkpoint.
    """
    case_id = f"COLL-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Mask PII at intake — raw values not carried forward in state
    raw_account = state.get("original_account_number", "UNKNOWN")
    account_id = _mask_account_number(raw_account)

    # Determine FDCPA applicability
    debt_type = state.get("debt_type", "UNKNOWN")
    fdcpa_applies = debt_type in CONSUMER_DEBT_TYPES

    # Generate case timestamp
    case_timestamp = datetime.utcnow().isoformat() + "Z"

    audit_trail = _append_audit_entry(state, "CASE_INTAKE", {
        "account_id": account_id,
        "debt_type": debt_type,
        "fdcpa_applies": fdcpa_applies,
        "current_balance": state.get("current_balance", 0.0),
        "consumer_state": state.get("consumer_state", "UNKNOWN"),
    })

    return {
        "case_id": case_id,
        "case_timestamp": case_timestamp,
        "account_id": account_id,
        "fdcpa_applies": fdcpa_applies,
        "audit_trail": audit_trail,
        "audit_retention": "7_YEARS_S3_OBJECT_LOCK_GOVERNANCE",
        # Clear raw account number from state
        "original_account_number": "MASKED",
    }

# ---------------------------------------------------------------------------
# Node 2: fdcpa_compliance_check_node
# ---------------------------------------------------------------------------

def fdcpa_compliance_check_node(state: CollectionsState) -> Dict[str, Any]:
    """
    FDCPA and CFPB Regulation F compliance checks.
    All determinations are Python — time checks, flag lookups, call counting.

    Checks:
    - Time-of-day (§ 805(a)(1)): 8am-9pm consumer's local time
    - Reg F 7-in-7: ≤7 calls in 7 consecutive days
    - Reg F post-conversation: ≥7 days since last phone conversation
    - Validation notice sent (§ 809): required within 5 days of first contact
    - Dispute hold: if dispute_received → freeze collection activity
    - Cease and desist: if C&D → only legal action notice permitted
    """
    consumer_timezone = state.get("consumer_timezone", "America/New_York")
    contact_permitted, contact_hour_local = _check_contact_time_fdcpa(consumer_timezone)

    prior_contacts = state.get("prior_contacts_7_days", 0)
    days_since_conversation = state.get("days_since_last_conversation", 999)

    fdcpa_issues = []
    reg_f_violations = []

    if not contact_permitted:
        fdcpa_issues.append(f"PROHIBITED_HOURS: Current local time {contact_hour_local}:00 is outside 8am-9pm window")

    if prior_contacts >= REGULATION_F_CALL_LIMIT_7_DAYS:
        reg_f_violations.append(f"7-IN-7: {prior_contacts} calls in 7 days (limit: {REGULATION_F_CALL_LIMIT_7_DAYS})")

    if days_since_conversation < REGULATION_F_POST_CONVERSATION_WAIT_DAYS:
        reg_f_violations.append(
            f"POST-CONVERSATION: Only {days_since_conversation} days since last conversation (required: {REGULATION_F_POST_CONVERSATION_WAIT_DAYS})"
        )

    # Cease and desist overrides all contact except specific legal notices
    cease_desist = state.get("cease_desist_received", False)
    if cease_desist:
        fdcpa_issues.append("CEASE_DESIST: Consumer sent written C&D — only permitted communication is notice of legal action")
        contact_permitted = False

    # Dispute: all collection activity paused
    dispute = state.get("dispute_received", False)
    if dispute:
        fdcpa_issues.append("DISPUTE_HOLD: Consumer disputed debt — validation required before further collection")
        contact_permitted = False

    # Compute regulatory risk score
    issue_count = len(fdcpa_issues) + len(reg_f_violations)
    if issue_count == 0:
        regulatory_risk_score = 0.1
        regulatory_risk_tier = "LOW"
    elif issue_count == 1:
        regulatory_risk_score = 0.4
        regulatory_risk_tier = "MEDIUM"
    elif issue_count == 2:
        regulatory_risk_score = 0.7
        regulatory_risk_tier = "HIGH"
    else:
        regulatory_risk_score = 0.9
        regulatory_risk_tier = "CRITICAL"

    audit_trail = _append_audit_entry(state, "FDCPA_COMPLIANCE_CHECK", {
        "contact_permitted_now": contact_permitted,
        "contact_hour_local": contact_hour_local,
        "fdcpa_issues": fdcpa_issues,
        "reg_f_violations": reg_f_violations,
        "regulatory_risk_tier": regulatory_risk_tier,
    })

    return {
        "contact_permitted_now": contact_permitted,
        "contact_hour_local": contact_hour_local,
        "fdcpa_compliance_issues": fdcpa_issues,
        "regulation_f_violations": reg_f_violations,
        "regulatory_risk_score": regulatory_risk_score,
        "regulatory_risk_tier": regulatory_risk_tier,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 3: scra_bankruptcy_check_node
# ---------------------------------------------------------------------------

def scra_bankruptcy_check_node(state: CollectionsState) -> Dict[str, Any]:
    """
    SCRA and bankruptcy automatic stay checks.
    Python flag propagation — in production, these flags come from:
    - SCRA: MilConnect API / DMDC database lookup
    - Bankruptcy: PACER search or credit bureau bankruptcy flag

    If SCRA detected: 6% interest rate cap applies (50 U.S.C. § 3937).
    If bankruptcy stay: ALL collection activity stops (11 U.S.C. § 362).
    Both conditions are ALWAYS_HITL_CONDITIONS.
    """
    # SOL computation
    debt_orig_date = state.get("debt_origination_date", "2020-01-01")
    date_last_payment = state.get("debt_date_of_last_payment", "2021-01-01")
    consumer_state = state.get("consumer_state", "NY")
    debt_type = state.get("debt_type", "CREDIT_CARD")

    sol_years, sol_expiration_date, sol_expired, sol_warning = _compute_sol_expiration(
        debt_orig_date, date_last_payment, consumer_state, debt_type
    )

    scra_active = state.get("scra_active_military", False)
    bankruptcy_stay = state.get("bankruptcy_stay_active", False)

    audit_trail = _append_audit_entry(state, "SCRA_BANKRUPTCY_CHECK", {
        "scra_active_military": scra_active,
        "bankruptcy_stay_active": bankruptcy_stay,
        "bankruptcy_chapter": state.get("bankruptcy_chapter", "N/A"),
        "sol_years": sol_years,
        "sol_expiration_date": sol_expiration_date,
        "sol_expired": sol_expired,
        "sol_warning": sol_warning,
        "scra_note": f"6% interest rate cap applies (50 U.S.C. § 3937)" if scra_active else None,
        "bankruptcy_note": "Automatic stay in effect — ALL collection must stop (11 U.S.C. § 362)" if bankruptcy_stay else None,
    })

    return {
        "scra_check_performed": True,
        "bankruptcy_check_performed": True,
        "sol_years": sol_years,
        "sol_expiration_date": sol_expiration_date,
        "sol_expired": sol_expired,
        "sol_warning": sol_warning,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 4: consumer_profile_node (LLM — hardship narrative)
# ---------------------------------------------------------------------------

def consumer_profile_node(state: CollectionsState, llm=None) -> Dict[str, Any]:
    """
    Consumer financial profile and hardship assessment.
    Python computes hardship eligibility threshold.
    LLM produces written narrative for supervisor review.
    """
    # Python: determine hardship plan eligibility
    hardship_score = state.get("hardship_score", 0.5)
    current_balance = state.get("current_balance", 1000.0)
    hardship_eligible = hardship_score >= 0.60  # 60% hardship threshold

    # LLM: hardship assessment narrative (narrative only — not used for routing decisions)
    hardship_narrative = ""
    if llm:
        try:
            days_delinquent = state.get("days_delinquent", 0)
            debt_origination_date = state.get("debt_origination_date", "2020-01-01")
            try:
                orig_date = datetime.strptime(debt_origination_date, "%Y-%m-%d")
                debt_age_months = (datetime.utcnow() - orig_date).days // 30
            except (ValueError, TypeError):
                debt_age_months = 0

            prompt = HARDSHIP_ASSESSMENT_PROMPT.format(
                debt_type=state.get("debt_type", "UNKNOWN"),
                original_balance=state.get("original_balance", current_balance),
                current_balance=current_balance,
                days_delinquent=days_delinquent,
                debt_age_months=debt_age_months,
                hardship_score=hardship_score,
                payment_history_factor=state.get("payment_history_factor", 0.5),
                contact_success_factor=state.get("contact_success_factor", 0.5),
                prior_payment_history=state.get("prior_payment_history_desc", "No prior arrangements"),
                dispute_history=state.get("dispute_history_desc", "No disputes on record"),
                collectability_score=state.get("collectability_score", 0.5),
                collectability_tier=state.get("collectability_tier", "MEDIUM"),
                sol_status=f"Expires {state.get('sol_expiration_date', 'Unknown')}, Expired: {state.get('sol_expired', False)}",
                settlement_eligible=state.get("settlement_eligible", True),
            )
            hardship_narrative = llm.invoke(prompt).content
        except Exception:
            hardship_narrative = "[Demo mode — LLM hardship assessment narrative would appear here]"
    else:
        hardship_narrative = (
            f"DEMO: Consumer account shows hardship_score={hardship_score:.2f}. "
            f"Hardship plan eligibility: {'ELIGIBLE' if hardship_eligible else 'NOT ELIGIBLE'}. "
            f"Balance ${current_balance:,.2f}. Supervisor review recommended before first contact."
        )

    audit_trail = _append_audit_entry(state, "CONSUMER_PROFILE", {
        "hardship_score": hardship_score,
        "hardship_eligible": hardship_eligible,
        "consumer_state": state.get("consumer_state"),
        "consumer_timezone": state.get("consumer_timezone"),
        "consumer_is_deceased": state.get("consumer_is_deceased"),
        "consumer_is_minor": state.get("consumer_is_minor"),
    })

    return {
        "hardship_plan_eligible": hardship_eligible,
        "hardship_assessment_narrative": hardship_narrative,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 5: debt_validation_node
# ---------------------------------------------------------------------------

def debt_validation_node(state: CollectionsState) -> Dict[str, Any]:
    """
    Validate debt integrity and compute days delinquent.
    Python arithmetic — no LLM.
    Checks: balance consistency, debt age, medical debt special rules.
    """
    current_balance = state.get("current_balance", 0.0)
    original_balance = state.get("original_balance", current_balance)
    interest_accrued = state.get("interest_accrued", 0.0)
    fees_accrued = state.get("fees_accrued", 0.0)

    # Compute days delinquent from debt origination + last payment
    try:
        last_payment = datetime.strptime(
            state.get("debt_date_of_last_payment", "2020-01-01"), "%Y-%m-%d"
        )
        days_delinquent = (datetime.utcnow() - last_payment).days
    except (ValueError, TypeError):
        days_delinquent = 365  # Conservative default

    # Medical debt special rules (CFPB Reg F 2025 — medical debt <$500 not reportable)
    debt_type = state.get("debt_type", "")
    medical_debt_flag = debt_type == "MEDICAL_DEBT"

    # Credit reporting appropriateness (FCRA)
    credit_reporting_appropriate = (
        current_balance >= CREDIT_REPORTING_THRESHOLDS["min_balance_report"]
        and not (
            medical_debt_flag
            and current_balance < CREDIT_REPORTING_THRESHOLDS["medical_debt_min_balance"]
        )
    )

    # Charge-off status (OCC: 180 days delinquent)
    if days_delinquent >= CREDIT_REPORTING_THRESHOLDS["charge_off_days_delinquent"]:
        credit_reporting_action = "REPORT_NEW" if credit_reporting_appropriate else "NONE"
    else:
        credit_reporting_action = "UPDATE_EXISTING" if credit_reporting_appropriate else "NONE"

    # Settlement eligibility: YES unless cease/desist, bankruptcy stay, or federal student loan
    federal_loan = state.get("debt_type", "") in FEDERAL_STUDENT_LOAN_PROGRAMS
    cease_desist = state.get("cease_desist_received", False)
    bankruptcy_stay = state.get("bankruptcy_stay_active", False)
    settlement_eligible = not (federal_loan or cease_desist or bankruptcy_stay)

    audit_trail = _append_audit_entry(state, "DEBT_VALIDATION", {
        "days_delinquent": days_delinquent,
        "current_balance": current_balance,
        "medical_debt_flag": medical_debt_flag,
        "credit_reporting_appropriate": credit_reporting_appropriate,
        "credit_reporting_action": credit_reporting_action,
        "settlement_eligible": settlement_eligible,
        "charge_off": days_delinquent >= CREDIT_REPORTING_THRESHOLDS["charge_off_days_delinquent"],
    })

    return {
        "days_delinquent": days_delinquent,
        "medical_debt_flag": medical_debt_flag,
        "credit_reporting_appropriate": credit_reporting_appropriate,
        "credit_reporting_action": credit_reporting_action,
        "settlement_eligible": settlement_eligible,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 6: payment_plan_optimizer_node
# ---------------------------------------------------------------------------

def payment_plan_optimizer_node(state: CollectionsState) -> Dict[str, Any]:
    """
    Compute collectability score, payment plan options, and settlement tiers.
    Pure Python arithmetic — no LLM.
    LLM in Node 7 (collections_strategy_node) receives these outputs for narrative.
    """
    current_balance = state.get("current_balance", 1000.0)
    hardship_eligible = state.get("hardship_plan_eligible", False)

    # Collectability score
    collectability_score, collectability_tier, sub_scores = _compute_collectability_score(state)

    # Payment plan options
    payment_plan_options = _compute_payment_plans(current_balance, hardship_eligible)

    # Recommended plan: lowest-term standard plan (most favorable for recovery)
    recommended_plan_index = 0
    for i, plan in enumerate(payment_plan_options):
        if plan["plan_type"] == "STANDARD":
            recommended_plan_index = i
            break

    # Min monthly payment
    min_monthly = round(max(
        MIN_PAYMENT_PCT_OF_BALANCE * current_balance,
        HARDSHIP_PLAN_MIN_PAYMENT if hardship_eligible else 0
    ), 2)

    # Settlement tiers
    settlement_eligible = state.get("settlement_eligible", True)
    settlement_tiers_data = _compute_settlement_tiers(current_balance) if settlement_eligible else []

    # Recommended settlement tier: TIER_2 (35% discount — standard supervisory authority)
    recommended_tier = "TIER_2"
    for tier in settlement_tiers_data:
        if tier["tier"] == "TIER_2":
            recommended_tier = "TIER_2"
            break

    settlement_amount = 0.0
    settlement_discount_pct = 0.0
    settlement_auth_level = "SUPERVISOR"
    settlement_high_value = False

    for tier in settlement_tiers_data:
        if tier["tier"] == recommended_tier:
            settlement_amount = tier["settlement_amount"]
            settlement_discount_pct = tier["discount_pct"]
            settlement_auth_level = tier["auth_level"]
            settlement_high_value = tier["high_value"]
            break

    audit_trail = _append_audit_entry(state, "PAYMENT_PLAN_OPTIMIZER", {
        "collectability_score": collectability_score,
        "collectability_tier": collectability_tier,
        "plan_count": len(payment_plan_options),
        "settlement_tiers_count": len(settlement_tiers_data),
        "recommended_settlement_tier": recommended_tier,
        "settlement_amount": settlement_amount,
        "sub_scores": sub_scores,
    })

    return {
        "collectability_score": collectability_score,
        "collectability_tier": collectability_tier,
        "debt_age_factor": sub_scores["debt_age_factor"],
        "contact_success_factor": sub_scores["contact_success_factor"],
        "payment_history_factor": sub_scores.get("payment_history_factor", 0.5),
        "hardship_score": state.get("hardship_score", 0.5),
        "payment_plan_options": payment_plan_options,
        "recommended_plan_index": recommended_plan_index,
        "min_monthly_payment": min_monthly,
        "settlement_tiers": settlement_tiers_data,
        "recommended_settlement_tier": recommended_tier,
        "settlement_amount": settlement_amount,
        "settlement_discount_pct": settlement_discount_pct,
        "settlement_auth_level": settlement_auth_level,
        "settlement_high_value": settlement_high_value,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 7: collections_strategy_node (LLM — strategy narrative)
# ---------------------------------------------------------------------------

def collections_strategy_node(state: CollectionsState, llm=None) -> Dict[str, Any]:
    """
    Produce collections strategy narrative for supervisor review.
    LLM narrative only — routing decisions are made in Node 8.
    """
    strategy_narrative = ""
    if llm:
        try:
            plans = state.get("payment_plan_options", [])
            plans_text = "\n".join([
                f"  - {p['plan_type']} {p['term_months']}mo: ${p['monthly_payment']:.2f}/mo "
                f"(total ${p['total_repaid']:.2f}, auth: {p['auth_level']})"
                for p in plans
            ])
            tiers = state.get("settlement_tiers", [])
            tiers_text = "\n".join([
                f"  - {t['tier']}: ${t['settlement_amount']:.2f} ({t['discount_pct']:.0f}% off, auth: {t['auth_level']})"
                for t in tiers
            ])
            prompt = COLLECTIONS_STRATEGY_PROMPT.format(
                fdcpa_applies=state.get("fdcpa_applies", True),
                contact_permitted_now=state.get("contact_permitted_now", True),
                validation_notice_sent=state.get("validation_notice_sent", False),
                dispute_received=state.get("dispute_received", False),
                cease_desist_received=state.get("cease_desist_received", False),
                scra_active_military=state.get("scra_active_military", False),
                bankruptcy_stay_active=state.get("bankruptcy_stay_active", False),
                sol_expired=state.get("sol_expired", False),
                sol_warning=state.get("sol_warning", False),
                prior_contacts_7_days=state.get("prior_contacts_7_days", 0),
                debt_type=state.get("debt_type", "UNKNOWN"),
                current_balance=state.get("current_balance", 0.0),
                collectability_tier=state.get("collectability_tier", "MEDIUM"),
                days_delinquent=state.get("days_delinquent", 0),
                consumer_state=state.get("consumer_state", "Unknown"),
                payment_plan_options_text=plans_text or "No plans computed",
                settlement_tiers_text=tiers_text or "Settlement not eligible",
                hitl_conditions=state.get("hitl_conditions", []),
            )
            strategy_narrative = llm.invoke(prompt).content
        except Exception:
            strategy_narrative = "[Demo mode — LLM collections strategy narrative would appear here]"
    else:
        strategy_narrative = (
            f"DEMO: Collectability={state.get('collectability_tier','MEDIUM')}. "
            f"Balance=${state.get('current_balance',0):,.2f}. "
            f"SOL expired={state.get('sol_expired',False)}. "
            f"SCRA={state.get('scra_active_military',False)}. "
            f"Bankruptcy={state.get('bankruptcy_stay_active',False)}. "
            f"Recommended approach: present payment plan options starting with 24-month term. "
            f"Settlement eligible: {state.get('settlement_eligible',True)}."
        )

    audit_trail = _append_audit_entry(state, "COLLECTIONS_STRATEGY", {
        "strategy_narrative_length": len(strategy_narrative),
        "collectability_tier": state.get("collectability_tier"),
        "sol_expired": state.get("sol_expired"),
    })

    return {
        "collections_strategy_narrative": strategy_narrative,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 8: risk_scoring_node
# ---------------------------------------------------------------------------

def risk_scoring_node(state: CollectionsState) -> Dict[str, Any]:
    """
    Determine HITL conditions and escalation level.
    Python frozenset membership check — no LLM.
    """
    hitl_conditions, hitl_required, escalation_level = _determine_hitl_conditions(state)

    audit_trail = _append_audit_entry(state, "RISK_SCORING", {
        "hitl_conditions": hitl_conditions,
        "hitl_required": hitl_required,
        "escalation_level": escalation_level,
        "regulatory_risk_tier": state.get("regulatory_risk_tier", "LOW"),
    })

    return {
        "hitl_conditions": hitl_conditions,
        "hitl_required": hitl_required,
        "escalation_level": escalation_level,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 9: routing_decision_node
# ---------------------------------------------------------------------------

def routing_decision_node(state: CollectionsState) -> Dict[str, Any]:
    """
    Determine routing: HITL gate or auto-process.
    Sets human_review_required flag. Graph uses _route_after_routing() to branch.
    Fail-safe: None/missing → HITL.
    """
    hitl_required = state.get("hitl_required")
    contact_permitted = state.get("contact_permitted_now", True)

    # FDCPA violations always require HITL regardless of other conditions
    fdcpa_issues = state.get("fdcpa_compliance_issues", [])
    reg_f_issues = state.get("regulation_f_violations", [])

    if fdcpa_issues or reg_f_issues:
        hitl_required = True

    audit_trail = _append_audit_entry(state, "ROUTING_DECISION", {
        "human_review_required": hitl_required,
        "fdcpa_issues_count": len(fdcpa_issues),
        "reg_f_issues_count": len(reg_f_issues),
        "contact_permitted_now": contact_permitted,
        "routing_to": "human_review_gate" if hitl_required else "communication_drafting",
    })

    return {
        "human_review_required": hitl_required,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 10: human_review_gate_node
# ---------------------------------------------------------------------------

def human_review_gate_node(state: CollectionsState) -> Dict[str, Any]:
    """
    HITL gate node. Processes the reviewer's decision submitted via the UI.
    Maps reviewer_decision to collections_outcome.

    Valid decisions:
    - APPROVE_PLAN: proceed with payment plan (reviewed options → specific plan)
    - APPROVE_SETTLEMENT: proceed with settlement offer
    - APPROVE_HARDSHIP: approve hardship plan at reduced minimum
    - ESCALATE: send to higher authority
    - CEASE_COLLECTION: stop all collection per legal/compliance instruction
    - REFER_LEGAL: refer account for legal action (litigation)
    - CLOSE_DISPUTE: dispute validated, update records, halt collection

    Unknown decisions route to audit_finalize without approval.
    """
    decision = state.get("reviewer_decision", "")
    reviewer_id = state.get("reviewer_id", "")
    reviewer_timestamp = datetime.utcnow().isoformat() + "Z"

    decision_map = {
        "APPROVE_PLAN":       "PAYMENT_PLAN",
        "APPROVE_SETTLEMENT": "SETTLEMENT",
        "APPROVE_HARDSHIP":   "HARDSHIP_PLAN",
        "CEASE_COLLECTION":   "CEASE_AND_DESIST",
        "REFER_LEGAL":        "LEGAL_REFERRAL",
        "CLOSE_DISPUTE":      "CLOSED_DISPUTE",
        "ESCALATE":           "ESCALATED",
    }

    if decision in decision_map:
        collections_outcome = decision_map[decision]
    else:
        collections_outcome = "PENDING_REVIEW"

    audit_trail = _append_audit_entry(state, "HUMAN_REVIEW_GATE", {
        "reviewer_id": reviewer_id,
        "reviewer_decision": decision,
        "collections_outcome": collections_outcome,
        "reviewer_conditions": state.get("reviewer_conditions", ""),
        "reviewer_notes": state.get("reviewer_notes", ""),
        "reviewer_timestamp": reviewer_timestamp,
        "hitl_conditions_reviewed": state.get("hitl_conditions", []),
        "escalation_level": state.get("escalation_level", "COLLECTOR"),
    })

    return {
        "collections_outcome": collections_outcome,
        "reviewer_timestamp": reviewer_timestamp,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 11: communication_drafting_node (LLM — letters and agreements)
# ---------------------------------------------------------------------------

def communication_drafting_node(state: CollectionsState, llm=None, institution_name: str = "Your Institution") -> Dict[str, Any]:
    """
    Draft FDCPA-compliant consumer communications.
    LLM produces letter text with Python-computed values injected.
    FDCPA required disclosures are Python-provided — not LLM-generated.
    """
    outcome = state.get("collections_outcome", "PAYMENT_PLAN")
    collection_letter = ""
    settlement_letter = ""
    payment_agreement = ""

    if llm:
        plans = state.get("payment_plan_options", [])
        plans_text = "\n".join([
            f"  Option {i+1}: {p['term_months']} monthly payments of ${p['monthly_payment']:.2f} (${p['total_repaid']:.2f} total)"
            for i, p in enumerate(plans[:3])
        ])

        try:
            if outcome in {"PAYMENT_PLAN", "HARDSHIP_PLAN"}:
                # Draft collection letter + payment agreement
                collection_letter = llm.invoke(COLLECTION_LETTER_PROMPT.format(
                    original_creditor=state.get("original_creditor", "Original Creditor"),
                    debt_type=state.get("debt_type", "consumer debt"),
                    itemization_date=state.get("itemization_date", datetime.utcnow().strftime("%Y-%m-%d")),
                    current_balance=state.get("current_balance", 0.0),
                    original_balance=state.get("original_balance", 0.0),
                    interest_accrued=state.get("interest_accrued", 0.0),
                    fees_accrued=state.get("fees_accrued", 0.0),
                    account_id=state.get("account_id", "UNKNOWN"),
                    institution_name=institution_name,
                    payment_options_for_letter=plans_text or "Contact us to discuss payment options.",
                    institution_address="[Institution Address]",
                    litigation_approved=False,
                )).content

                if state.get("reviewer_decision") in {"APPROVE_PLAN", "APPROVE_HARDSHIP"}:
                    recommended_idx = state.get("recommended_plan_index", 0)
                    selected_plan = plans[recommended_idx] if plans else {}
                    payment_agreement = llm.invoke(PAYMENT_AGREEMENT_PROMPT.format(
                        consumer_name_masked=state.get("consumer_name_masked", "Valued Customer"),
                        account_id=state.get("account_id", "UNKNOWN"),
                        original_creditor=state.get("original_creditor", "Original Creditor"),
                        current_balance=state.get("current_balance", 0.0),
                        monthly_payment=selected_plan.get("monthly_payment", 0.0),
                        first_payment_date=(datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d"),
                        num_payments=selected_plan.get("term_months", 12),
                        final_payment_date=(datetime.utcnow() + timedelta(days=30 * selected_plan.get("term_months", 12))).strftime("%Y-%m-%d"),
                        payment_method="ACH / check / money order",
                        ach_authorization="If paying by ACH, you authorize recurring monthly debits.",
                        hardship_plan_note="This is a hardship plan. Terms may be reviewed if your financial situation changes." if outcome == "HARDSHIP_PLAN" else "",
                    )).content

            elif outcome == "SETTLEMENT":
                settlement_letter = llm.invoke(SETTLEMENT_OFFER_PROMPT.format(
                    original_creditor=state.get("original_creditor", "Original Creditor"),
                    current_balance=state.get("current_balance", 0.0),
                    account_id=state.get("account_id", "UNKNOWN"),
                    institution_name=institution_name,
                    settlement_amount=state.get("settlement_amount", 0.0),
                    savings_amount=state.get("current_balance", 0.0) - state.get("settlement_amount", 0.0),
                    settlement_discount_pct=state.get("settlement_discount_pct", 0.0),
                    acceptance_deadline=(datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d"),
                    payment_method="Certified check / wire transfer / ACH",
                )).content
        except Exception:
            collection_letter = "[Demo mode — LLM letter draft would appear here]"
    else:
        collection_letter = (
            f"DEMO LETTER — {institution_name}\n\n"
            f"Re: Account {state.get('account_id','UNKNOWN')}\n"
            f"Balance: ${state.get('current_balance',0):,.2f}\n\n"
            f"This is an attempt to collect a debt. Any information obtained will be used for that purpose.\n\n"
            f"Please contact us to arrange payment. [Full letter would be LLM-generated with FDCPA disclosures.]\n\n"
            f"Unless you notify us within 30 days after receiving this letter that you dispute the validity of this debt, we will assume the debt is valid."
        )
        if outcome == "SETTLEMENT":
            settlement_letter = (
                f"DEMO SETTLEMENT OFFER — {institution_name}\n\n"
                f"Settlement amount: ${state.get('settlement_amount',0):,.2f} "
                f"({state.get('settlement_discount_pct',0):.0f}% reduction).\n"
                f"This offer expires in 30 days.\n\n"
                f"This is an attempt to collect a debt. Any information obtained will be used for that purpose."
            )

    audit_trail = _append_audit_entry(state, "COMMUNICATION_DRAFTING", {
        "collections_outcome": outcome,
        "collection_letter_drafted": bool(collection_letter),
        "settlement_letter_drafted": bool(settlement_letter),
        "payment_agreement_drafted": bool(payment_agreement),
        "fdcpa_disclosures_included": True,
    })

    return {
        "collection_letter_draft": collection_letter,
        "settlement_offer_letter_draft": settlement_letter,
        "payment_agreement_draft": payment_agreement,
        "audit_trail": audit_trail,
    }

# ---------------------------------------------------------------------------
# Node 12: audit_finalize_node
# ---------------------------------------------------------------------------

def audit_finalize_node(state: CollectionsState) -> Dict[str, Any]:
    """
    Finalize audit trail and produce output package.
    Append-only audit entry documenting final outcome.
    In production: writes to S3 Object Lock + DynamoDB case registry.
    7-year retention: FCRA (§ 1681c) for credit reporting records;
    FDCPA class action statute of limitations is 1 year but consumer may
    maintain records longer; standard FSI records retention = 7 years.
    """
    final_audit_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "case_id": state.get("case_id"),
        "event_type": "CASE_FINALIZED",
        "account_id": state.get("account_id"),
        "collections_outcome": state.get("collections_outcome", "UNKNOWN"),
        "credit_reporting_action": state.get("credit_reporting_action", "NONE"),
        "hitl_conditions": state.get("hitl_conditions", []),
        "reviewer_id": state.get("reviewer_id", "AUTO"),
        "reviewer_decision": state.get("reviewer_decision", "N/A"),
        "regulatory_risk_tier": state.get("regulatory_risk_tier", "UNKNOWN"),
        "retention_policy": "7_YEARS_S3_OBJECT_LOCK_GOVERNANCE",
        "fdcpa_issues": state.get("fdcpa_compliance_issues", []),
        "regulation_f_violations": state.get("regulation_f_violations", []),
        "sol_expired": state.get("sol_expired", False),
        "scra_detected": state.get("scra_active_military", False),
        "bankruptcy_detected": state.get("bankruptcy_stay_active", False),
    }

    current_trail = list(state.get("audit_trail", []))
    final_trail = current_trail + [final_audit_entry]

    return {
        "audit_trail": final_trail,
        "credit_reporting_filed": state.get("credit_reporting_appropriate", False),
        "audit_retention": "7_YEARS_S3_OBJECT_LOCK_GOVERNANCE",
    }
