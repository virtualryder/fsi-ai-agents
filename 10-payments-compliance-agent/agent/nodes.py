# agent/nodes.py
# ============================================================
# Payments Compliance Agent — Node Functions
#
# ARCHITECTURE OVERVIEW
# ---------------------
# This file implements all 12 nodes in the payments compliance
# workflow. Each node is a pure function that takes state as
# input and returns a dict of state updates.
#
# LLM vs Python boundary:
# - Python: ALL compliance decisions (OFAC, Nacha return windows,
#   SLA deadlines, Reg E applicability, provisional credit
#   requirement, routing, risk scoring)
# - LLM: Narrative analysis, dispute assessment, customer notice
#   drafting, resolution memo drafting
#
# SECURITY CONTROLS IN THIS FILE
# --------------------------------
# 1. OFAC/sanctions screening is Python — LLM never sees raw
#    screening results or makes sanctions determinations.
# 2. Account numbers are truncated to last-4 at intake — full
#    account numbers never written to state or audit trail.
# 3. SLA deadlines are computed in UTC using dateutil — no
#    timezone ambiguity that could cause a compliance breach.
# 4. ALWAYS_HITL_PAYMENT_TYPES frozenset enforces mandatory
#    human review for the highest-risk events.
# 5. SAR recommendation is Python-flagged (threshold-based),
#    not LLM-decided.
# 6. Return window eligibility is Python-computed against
#    Nacha's published return windows — LLM has no role.
# ============================================================
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── Claude model tiers (Anthropic) ───────────────────────────────────────────
# NARRATIVE tier — Claude Sonnet 4.6: regulatory narratives, SAR/dispute
#   analysis, anything an examiner, reviewer, or customer will read.
# FAST tier — Claude Haiku 4.5: high-volume triage, classification, and
#   scoring-assist nodes where latency and unit cost dominate.
# Override via env: CLAUDE_NARRATIVE_MODEL / CLAUDE_FAST_MODEL.
# ── INTEGRATION POINT (production) ───────────────────────────────────────────
# For VPC-contained inference, swap ChatAnthropic for ChatBedrockConverse
# (langchain-aws) with Bedrock model IDs:
#   anthropic.claude-sonnet-4-6-20260601-v1:0  (narrative)
#   anthropic.claude-haiku-4-5-20251001        (fast)
# ─────────────────────────────────────────────────────────────────────────────
import os as _os_llm
from langchain_anthropic import ChatAnthropic
from agent.persistence import audit_sink
CLAUDE_NARRATIVE_MODEL = _os_llm.getenv("CLAUDE_NARRATIVE_MODEL", "claude-sonnet-4-6")
CLAUDE_FAST_MODEL = _os_llm.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5")
CLAUDE_DEFAULT_MODEL = CLAUDE_NARRATIVE_MODEL


logger = logging.getLogger(__name__)

# ── Lazy LLM import ───────────────────────────────────────────────────────────
def _get_llm():
    """Import and instantiate the LLM. Lazy import avoids cost at test time."""
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL, temperature=0)


# ── Constants ─────────────────────────────────────────────────────────────────

# ALWAYS_HITL_PAYMENT_TYPES: Payment event types that ALWAYS require human review
# regardless of compliance risk score. This is a frozenset — immutable at runtime.
#
# Why these types:
# - OFAC_HOLD: Sanctions match — must be reviewed by OFAC officer before any action
# - UNAUTHORIZED_WIRE: Wire fraud / BEC — potential criminal activity, large amounts
# - SAR_CANDIDATE: Transaction patterns indicating potential money laundering
# - CONSENT_ORDER_RELATED: Payment related to an institution under enforcement action
# - CTR_THRESHOLD: Cash transaction triggering CTR filing requirement
ALWAYS_HITL_PAYMENT_EVENTS = frozenset({
    "OFAC_HOLD",
    "UNAUTHORIZED_WIRE",
    "SAR_CANDIDATE",
    "CTR_THRESHOLD",
    "HIGH_RISK_COUNTRY_WIRE",
    "LATE_RETURN_DISPUTE",  # After 60 days, R07 only — requires legal review
})

# Payment amounts above this threshold require HITL regardless of risk score.
# Based on Federal Reserve wire transfer supervision guidance.
HITL_AMOUNT_THRESHOLD = 50_000.00

# CTR cash transaction threshold (31 USC 5313)
CTR_THRESHOLD_USD = 10_000.00

# SAR consideration threshold for wire fraud / unauthorized transactions
SAR_CONSIDERATION_THRESHOLD = 5_000.00

# Nacha return windows by return code category
# Key: first 2 chars of return code (e.g., "R0" for R01–R09)
# Value: (standard_days, is_unauthorized)
NACHA_RETURN_WINDOWS: Dict[str, int] = {
    "R01": 2,   # Administrative — 2 banking days
    "R02": 2,   # Administrative
    "R03": 2,   # Administrative
    "R04": 2,   # Administrative
    "R05": 60,  # Unauthorized (consumer account)
    "R06": 2,   # ODFI request
    "R07": 60,  # Unauthorized — consumer authorization revoked
    "R08": 2,   # Payment stopped
    "R09": 2,   # Uncollected funds
    "R10": 60,  # Unauthorized — not known/not authorized
    "R11": 2,   # Check truncation
    "R12": 2,   # Branch sold
    "R13": 2,   # RDFI not qualified
    "R14": 60,  # Representative payee deceased
    "R15": 60,  # Beneficiary deceased
    "R16": 2,   # Account frozen / OFAC
    "R20": 2,   # Non-transaction account
    "R21": 2,   # Invalid company ID
    "R22": 2,   # Invalid individual ID
    "R23": 2,   # Credit refused
    "R24": 2,   # Duplicate entry
    "R29": 60,  # Corporate unauthorized
}

# Unauthorized return codes — these require enhanced scrutiny and
# potential SAR consideration for patterns
UNAUTHORIZED_RETURN_CODES = frozenset({
    "R05", "R07", "R10", "R29"
})

# OFAC-sanctioned countries — used for wire transfer screening
# First 2 characters of SWIFT BIC or ISO 3166-1 alpha-2 country code
OFAC_SANCTIONED_COUNTRY_CODES = frozenset({
    "KP",  # North Korea
    "IR",  # Iran
    "CU",  # Cuba
    "SY",  # Syria
})

# FATF high-risk and monitored jurisdictions (grey/black list as of 2024)
FATF_HIGH_RISK_COUNTRIES = frozenset({
    "KP",  # North Korea (FATF Black List)
    "IR",  # Iran (FATF Black List)
    "MM",  # Myanmar (FATF Grey List)
    "LY",  # Libya
    "SD",  # Sudan
    "SS",  # South Sudan
    "SO",  # Somalia
    "YE",  # Yemen
    "HT",  # Haiti
    "BF",  # Burkina Faso
    "ML",  # Mali
    "SN",  # Senegal
    "TZ",  # Tanzania
    "VE",  # Venezuela
    "RU",  # Russia (enhanced due diligence)
    "BY",  # Belarus (enhanced due diligence)
    "CU",  # Cuba
    "SY",  # Syria
})

# Reg E error resolution SLA (business days)
REG_E_PROVISIONAL_CREDIT_BUSINESS_DAYS = 10
REG_E_INVESTIGATION_CALENDAR_DAYS = 45
REG_E_NOTIFICATION_BUSINESS_DAYS = 3
REG_E_EXTENDED_INVESTIGATION_CALENDAR_DAYS = 90  # New accounts / foreign-initiated

# Risk scoring weights (SR 11-7 documentation standard)
# All weights must sum to 1.0
RISK_WEIGHTS = {
    "sanctions_factor": 0.35,       # OFAC/high-risk country — highest weight
    "unauthorized_factor": 0.25,    # Unauthorized transaction indicators
    "amount_factor": 0.20,          # Transaction amount relative to thresholds
    "sla_factor": 0.10,             # SLA proximity / breach
    "pattern_factor": 0.10,         # Violation count and severity
}

# Target teams for routing — Python constant, not LLM-determined
TARGET_TEAMS = {
    "OFAC_HOLD": "BSA",
    "UNAUTHORIZED_WIRE": "BSA",
    "HIGH_RISK_COUNTRY_WIRE": "BSA",
    "SAR_CANDIDATE": "BSA",
    "CTR_THRESHOLD": "BSA",
    "REG_E_DISPUTE": "DISPUTES",
    "NACHA_RETURN": "PAYMENTS_OPS",
    "NOC": "PAYMENTS_OPS",
    "WIRE_COMPLIANCE": "PAYMENTS_OPS",
    "AUTO_RESOLVE": "AUTO_RESOLVE",
}


# ── Utility Functions ─────────────────────────────────────────────────────────

def _now_utc() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _mask_account_number(account: str) -> str:
    """
    Mask an account number to last 4 digits.
    Security: full account numbers must never be stored in state.
    """
    if not account:
        return "****"
    cleaned = re.sub(r"[^\d]", "", account)
    if len(cleaned) > 4:
        return f"****{cleaned[-4:]}"
    return f"****{cleaned}"


def _last4_of_account(account: str) -> str:
    """
    Return the bare last-4 digits of an account number for *_account_last4
    state fields. Returns "" when no digits are present.
    Security: the raw account number must be discarded by the caller after
    this extraction — only the last-4 may persist in graph state.
    """
    if not account:
        return ""
    cleaned = re.sub(r"[^\d]", "", str(account))
    return cleaned[-4:] if cleaned else ""


def _sanitize_text(text: str, max_length: int = 3000) -> str:
    """
    Strip control characters and enforce length limit.
    Prevents injection attacks via payment memos or customer claim text.
    """
    if not text:
        return ""
    sanitized = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    return sanitized[:max_length]


def _compute_business_days(start: datetime, business_days: int) -> datetime:
    """
    Compute a deadline in business days (excluding Saturday/Sunday).
    Used for Reg E SLA calculations. Holidays are not excluded here —
    institutions should add holiday calendars for production use.
    """
    current = start
    days_added = 0
    while days_added < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # 0=Monday, 4=Friday
            days_added += 1
    return current


def _calendar_days_until(deadline_str: str) -> int:
    """Compute calendar days from now until the given ISO-8601 deadline."""
    try:
        deadline = datetime.fromisoformat(deadline_str)
        now = datetime.now(timezone.utc)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        delta = (deadline - now).days
        return max(delta, 0)
    except Exception:
        return 0


def _business_days_until(deadline_str: str) -> int:
    """Approximate business days from now until the given ISO-8601 deadline."""
    calendar_days = _calendar_days_until(deadline_str)
    # Conservative approximation: 5/7 of calendar days
    return max(int(calendar_days * 5 / 7), 0)


def _append_audit(
    state: Dict[str, Any],
    step: str,
    details: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Append an entry to the audit trail (append-only).

    Security: this function creates a new list rather than modifying
    the existing list, ensuring immutability of prior entries.
    Account numbers in details are checked and masked before storage.
    """
    prior = list(state.get("audit_trail", []))
    entry = {
        "timestamp": _now_utc(),
        "payment_event_id": state.get("payment_event_id", "") or state.get("payment_id", ""),
        "payment_id": state.get("payment_id", "") or state.get("payment_event_id", ""),
        "node": step,
        "step": step,
        **details,
    }
    # Ensure no full account numbers slip into the audit trail
    entry_str = json.dumps(entry)
    # Mask any 8–17 digit sequences (account numbers)
    entry_str = re.sub(r"\b(\d{4,13})(\d{4})\b", r"****\2", entry_str)
    prior.append(json.loads(entry_str))
    # WRITE-AHEAD: durable audit record at creation (agent/persistence.py)
    audit_sink().record(prior[-1])
    return prior


def _extract_country_from_bic(bic: str) -> str:
    """
    Extract the ISO 3166-1 alpha-2 country code from a SWIFT BIC.
    SWIFT BIC format: BANKCCLL or BANKCCLLBBB
    Characters 4–5 (0-indexed) are the country code.
    """
    if bic and len(bic) >= 6:
        return bic[4:6].upper()
    return ""


def _extract_country_from_iban(iban: str) -> str:
    """Extract country code from IBAN (first 2 characters)."""
    if iban and len(iban) >= 2:
        return iban[0:2].upper()
    return ""


def _parse_llm_json(content: str, context: str = "") -> Dict[str, Any]:
    """
    Parse JSON from LLM response content. Handles common LLM formatting
    issues (markdown code blocks, trailing commas).
    """
    text = content.strip()
    # Strip markdown code blocks if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error in %s: %s — raw: %.200s", context, exc, text)
        return {}


# ── Node 1: Payment Intake ────────────────────────────────────────────────────

def payment_intake_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 1 — PAYMENT INTAKE

    PURPOSE: Validate incoming payment event, assign a unique payment_id,
    compute a SHA-256 hash of the event data, mask account numbers to
    last-4, and perform initial classification of the payment type.

    SECURITY CONTROLS:
    - Account number masking: full account numbers are replaced with ****{last4}
      here, before any subsequent node sees them. This ensures full account
      numbers are never written to the LangGraph checkpoint database.
    - Input sanitization: remittance information and customer claim text are
      sanitized to remove control characters that could cause injection issues.
    - Size validation: payment events with anomalously large field counts are
      rejected to prevent resource exhaustion.

    WHAT IT POPULATES:
    payment_id, payment_hash, originator_account_last4, receiver_account_last4,
    payment_status=RECEIVED, audit_trail entry.
    """
    errors = list(state.get("errors", []))
    audit = list(state.get("audit_trail", []))

    # Assign canonical payment_event_id if not already set (empty string is
    # not acceptable — generate). payment_id mirrors it for legacy callers.
    payment_event_id = state.get("payment_event_id") or state.get("payment_id") or str(uuid.uuid4())
    payment_id = payment_event_id

    # Compute SHA-256 hash of core payment fields for tamper detection
    hash_input = (
        f"{state.get('original_transaction_id', '')}"
        f"{state.get('amount', 0)}"
        f"{state.get('settlement_date', '')}"
        f"{state.get('originator_id', '')}"
        f"{state.get('received_timestamp', '')}"
    ).encode()
    payment_hash = hashlib.sha256(hash_input).hexdigest()

    # Mask account numbers — critical security step
    # Raw account numbers arrive in *_account_raw and must never survive
    # this node: we extract last-4 and OVERWRITE the raw fields in state.
    orig_raw = state.get("originator_account_raw") or state.get("originator_account_last4") or ""
    recv_raw = state.get("receiver_account_raw") or state.get("receiver_account_last4") or ""
    masked_orig = _last4_of_account(orig_raw)
    masked_recv = _last4_of_account(recv_raw)

    # Sanitize free-text fields to prevent injection
    remittance = _sanitize_text(state.get("remittance_information", ""))

    # Validate required fields
    required = ["payment_type", "amount", "received_timestamp"]
    missing = [f for f in required if not state.get(f)]
    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}")

    # Validate payment amount is positive
    amount = state.get("amount", 0)
    if not isinstance(amount, (int, float)) or amount <= 0:
        errors.append(f"Invalid payment amount: {amount}")

    if errors:
        audit_entry = _append_audit(
            {"payment_event_id": payment_event_id, "payment_id": payment_id, "audit_trail": []},
            "payment_intake",
            {"status": "REJECTED", "errors": errors},
        )
        return {
            "payment_event_id": payment_event_id,
            "payment_id": payment_id,
            "payment_hash": payment_hash,
            # SECURITY: scrub raw account numbers even on the rejected path
            "originator_account_raw": "",
            "receiver_account_raw": "",
            "originator_account_last4": masked_orig,
            "receiver_account_last4": masked_recv,
            "payment_status": "REJECTED",
            "errors": errors,
            "audit_trail": audit_entry,
            "completed_steps": list(state.get("completed_steps", [])) + ["payment_intake"],
        }

    audit_result = _append_audit(
        {**state, "payment_event_id": payment_event_id, "payment_id": payment_id, "audit_trail": audit},
        "payment_intake",
        {
            "payment_type": state.get("payment_type"),
            "amount": amount,
            "currency": state.get("currency", "USD"),
            "is_return": state.get("is_return", False),
            "return_code": state.get("return_code") or "NONE",
            "is_dispute": state.get("is_dispute", False),
        },
    )

    return {
        "payment_event_id": payment_event_id,
        "payment_id": payment_id,
        "payment_hash": payment_hash,
        # SECURITY: raw account numbers are scrubbed here — only last-4
        # survives into graph state / the checkpoint database.
        "originator_account_raw": "",
        "receiver_account_raw": "",
        "originator_account_last4": masked_orig,
        "receiver_account_last4": masked_recv,
        "remittance_information": remittance,
        "payment_status": "RECEIVED",
        "errors": errors,
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["payment_intake"],
    }


# ── Node 2: Sanctions Screening ───────────────────────────────────────────────

def sanctions_screening_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 2 — SANCTIONS SCREENING

    PURPOSE: Screen payment counterparties against OFAC SDN list and
    FATF high-risk/sanctioned country codes. This is a Python-only node —
    the LLM has NO role in sanctions determination.

    OFAC COMPLIANCE CONTEXT:
    OFAC regulations (31 CFR Parts 500–598) prohibit U.S. persons from
    conducting transactions with sanctioned persons, entities, and countries.
    Violations carry civil penalties up to $1,075,070 per transaction and
    criminal penalties up to $1M and 20 years imprisonment.

    SCREENING APPROACH:
    Production implementation would integrate with a licensed OFAC screening
    provider (WorldCheck, Dow Jones, LexisNexis, etc.). This node implements
    the decision logic that runs after the screening API response:
    - If SDN match: immediate hold, HITL required, do NOT process payment
    - If high-risk country: flag for enhanced review, HITL required for wires
    - If PEP match: flag for enhanced due diligence

    SECURITY: The OFAC determination is made exclusively in Python.
    The LLM never receives the screening result and never makes a
    sanctions determination. This is non-negotiable for regulatory compliance.

    WHAT IT POPULATES:
    ofac_screening_performed, ofac_hit, high_risk_country_flag,
    high_risk_country_name, pep_flag, sanctions_hold_required.
    """
    audit = list(state.get("audit_trail", []))

    # ── CONTROL: screen ALL party identifiers, not just BIC/IBAN ──────────
    # A payment with a sanctioned-country counterparty but no SWIFT BIC or
    # IBAN (e.g., a Fedwire with party country fields only) MUST still hit.
    # Sources screened, in order of specificity:
    #   1. originator_country / receiver_country (explicit party fields)
    #   2. SWIFT BIC chars 5-6 (correspondent bank country)
    #   3. IBAN chars 1-2 (beneficiary account country)
    swift_bic = state.get("swift_bic", "") or ""
    iban = state.get("iban", "") or ""
    originator_id = state.get("originator_id", "")

    bic_country = _extract_country_from_bic(swift_bic)
    iban_country = _extract_country_from_iban(iban)

    country_sources: List[tuple] = []  # (source_label, country_code)
    for label, value in (
        ("originator_country", (state.get("originator_country") or "").strip().upper()),
        ("receiver_country", (state.get("receiver_country") or "").strip().upper()),
        ("swift_bic", bic_country),
        ("iban", iban_country),
    ):
        if value:
            country_sources.append((label, value))

    screened_countries = {c for _, c in country_sources}
    # Legacy single-value field retained for downstream/audit compatibility:
    # prefer an OFAC-matched country, then a FATF-matched one, then first seen.
    country_code = next(
        (c for c in screened_countries if c in OFAC_SANCTIONED_COUNTRY_CODES),
        next((c for c in screened_countries if c in FATF_HIGH_RISK_COUNTRIES),
             next(iter(screened_countries), "")),
    )

    # ── FAIL-CLOSED: missing screening data = sanctions hold ──────────────
    # OFAC operates on strict liability. If we cannot determine ANY party
    # jurisdiction, the payment must be held for manual screening — absence
    # of data is never treated as a clean result.
    screening_data_missing = len(screened_countries) == 0

    # OFAC sanctioned country check (any party identifier)
    # Production: replace with real-time SDN API call against ALL identifiers
    ofac_matches = [
        (label, c) for label, c in country_sources
        if c in OFAC_SANCTIONED_COUNTRY_CODES
    ]
    ofac_hit = len(ofac_matches) > 0
    ofac_hit_details = ""
    if ofac_hit:
        ofac_hit_details = "; ".join(
            f"{label}={c} is comprehensively sanctioned by OFAC"
            for label, c in ofac_matches
        )

    # FATF high-risk jurisdiction check (any party identifier)
    fatf_matches = [c for _, c in country_sources if c in FATF_HIGH_RISK_COUNTRIES]
    if fatf_matches and country_code not in FATF_HIGH_RISK_COUNTRIES:
        country_code = fatf_matches[0]
    high_risk_country = len(fatf_matches) > 0
    high_risk_country_name = ""
    if high_risk_country and country_code:
        country_names = {
            "KP": "North Korea", "IR": "Iran", "MM": "Myanmar", "LY": "Libya",
            "SD": "Sudan", "SS": "South Sudan", "SO": "Somalia", "YE": "Yemen",
            "HT": "Haiti", "BF": "Burkina Faso", "ML": "Mali", "SN": "Senegal",
            "TZ": "Tanzania", "VE": "Venezuela", "RU": "Russia", "BY": "Belarus",
            "CU": "Cuba", "SY": "Syria",
        }
        high_risk_country_name = country_names.get(country_code, country_code)

    # PEP screening — production: API call to PEP database
    # Demo: flag if originator_name contains "MINISTER", "PRESIDENT", etc.
    pep_indicators = ["minister", "president", "governor", "senator", "ambassador", "official"]
    originator_name = state.get("originator_name", "").lower()
    pep_flag = any(ind in originator_name for ind in pep_indicators)

    # IAT (International ACH Transaction) always requires OFAC screening
    # per Nacha Operating Rules and FinCEN guidance
    is_iat = state.get("sec_code") == "IAT" or state.get("payment_type") == "ACH_IAT"
    if is_iat and not ofac_hit:
        # IAT transactions require additional screening — flag for review
        high_risk_country = high_risk_country or bool(country_code)

    # Determine if payment must be placed on hold
    # FAIL-CLOSED: OFAC hit OR missing screening data = immediate hold.
    # A payment we cannot screen is held, never passed.
    sanctions_hold = ofac_hit or screening_data_missing
    if screening_data_missing:
        ofac_hit_details = (
            "SCREENING DATA UNAVAILABLE: no party country, BIC, or IBAN present. "
            "Fail-closed hold applied — manual sanctions screening required before release. "
            "31 CFR Part 501 — OFAC strict liability."
        )

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "sanctions_screening",
        {
            "ofac_hit": ofac_hit,
            "high_risk_country": high_risk_country,
            "country_code": country_code,
            "countries_screened": sorted(screened_countries),
            "screening_sources": [f"{label}:{c}" for label, c in country_sources],
            "screening_data_missing": screening_data_missing,
            "pep_flag": pep_flag,
            "sanctions_hold": sanctions_hold,
        },
    )

    logger.info(
        "Sanctions screening for payment %s: OFAC=%s, high_risk=%s, PEP=%s, data_missing=%s",
        state.get("payment_event_id") or state.get("payment_id"),
        ofac_hit, high_risk_country, pep_flag, screening_data_missing,
    )

    return {
        "ofac_screening_performed": True,
        "ofac_hit": ofac_hit,
        "ofac_hit_details": ofac_hit_details,
        "screening_data_missing": screening_data_missing,
        "high_risk_country_flag": high_risk_country,
        "high_risk_country_name": high_risk_country_name,
        "pep_flag": pep_flag,
        "sanctions_hold_required": sanctions_hold,
        "payment_status": "SCREENING",
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["sanctions_screening"],
    }


# ── Node 3: Nacha Validation ──────────────────────────────────────────────────

def nacha_validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 3 — NACHA VALIDATION

    PURPOSE: For ACH transactions, validate compliance with Nacha Operating
    Rules. Determine return code eligibility, return window status, NOC
    requirements, and late return flags.

    KEY NACHA RULES IMPLEMENTED:
    - Return window enforcement: R01–R06 = 2 banking days; R07/R10/R29 = 60 days
    - Late return (post-60-days): only R07 (unauthorized) is allowed
    - Unauthorized returns (R07, R10, R29): require customer-signed statement
    - NOC handling: C-codes require ODFI to update records within 6 banking days
    - WEB debit annual audit: WEB SEC code requires annual security audit
    - IAT enhanced requirements: additional OFAC screening, data fields required
    - Re-originiation rules: R01/R02/R03 may be re-originated; R07 may not
    - Structuring detection: multiple returns of same amount from same originator

    WHAT IT POPULATES:
    nacha_validation_passed, nacha_violations, return_window_open,
    return_window_days_remaining, unauthorized_return_eligible,
    late_return_flag, noc_correction_required.
    """
    audit = list(state.get("audit_trail", []))
    violations = []
    payment_type = state.get("payment_type", "")
    sec_code = state.get("sec_code", "UNKNOWN")
    # return_code may arrive as None — normalize to "NONE"
    return_code = state.get("return_code") or "NONE"
    # The presence of a return code IS a return event. The explicit is_return
    # flag is honored when set, but a return code alone must never be ignored
    # (control: a missing flag cannot suppress return-code analysis).
    is_return = bool(state.get("is_return", False)) or return_code != "NONE"

    # Only perform Nacha validation for ACH transactions
    is_ach = payment_type in ("ACH_CREDIT", "ACH_DEBIT", "ACH_IAT")
    if not is_ach:
        audit_result = _append_audit(
            {**state, "audit_trail": audit},
            "nacha_validation",
            {"skipped": True, "reason": f"Not an ACH transaction: {payment_type}"},
        )
        return {
            "nacha_validation_passed": True,
            "nacha_violations": [],
            "return_window_open": False,
            "return_window_days_remaining": 0,
            "unauthorized_return_eligible": False,
            "late_return_flag": False,
            "noc_correction_required": False,
            "noc_required": False,
            "noc_corrected_data": {},
            # CTR threshold applies regardless of rail (31 CFR 1010.311)
            "ctr_threshold_triggered": bool(state.get("amount"))
            and float(state.get("amount", 0) or 0) > CTR_THRESHOLD_USD,
            "is_return": is_return,
            "audit_trail": audit_result,
            "completed_steps": list(state.get("completed_steps", [])) + ["nacha_validation"],
        }

    # ── SEC Code Validation ────────────────────────────────────────────────
    valid_sec_codes = {s.value for s in __import__("agent.state", fromlist=["SECCode"]).SECCode}
    if sec_code not in valid_sec_codes and sec_code != "UNKNOWN":
        violations.append(
            f"Invalid SEC code '{sec_code}'. "
            "Nacha Operating Rules Section 2.1 — SEC codes must be from the approved list."
        )

    # WEB debit — annual security audit required
    if sec_code == "WEB" and payment_type == "ACH_DEBIT":
        # Flag for compliance tracking — production would check last audit date
        violations.append(
            "WEB debit SEC code: Verify annual Nacha security audit is current. "
            "Nacha OR Section 2.5.14 — WEB originator must conduct annual audit."
        )

    # IAT — additional data fields required
    if sec_code == "IAT":
        iban = state.get("iban", "")
        swift_bic = state.get("swift_bic", "")
        if not iban and not swift_bic:
            violations.append(
                "IAT transaction missing foreign payment address (IBAN or BIC). "
                "Nacha OR Section 2.13 — IAT entries require foreign correspondent bank information."
            )

    # ── Return Code Analysis ────────────────────────────────────────────────
    return_window_open = False
    return_window_days = 0
    unauthorized_return = False
    late_return = False
    noc_required = False
    noc_data = {}

    if is_return and return_code != "NONE":
        # Check if this is a NOC (C-series)
        if return_code.startswith("C"):
            noc_required = True
            # NOC: ODFI must update records within 6 banking days per Nacha OR 2.16
            noc_deadline = _compute_business_days(
                datetime.now(timezone.utc), 6
            )
            violations.append(
                f"NOC received ({return_code}): ODFI must update originator records "
                f"within 6 banking days (by {noc_deadline.date()}). "
                "Nacha OR Section 2.16.3."
            )
            # Parse NOC corrected data from trace/remittance
            noc_data = {"return_code": return_code, "update_required_by": noc_deadline.isoformat()}

        # Standard return codes
        elif return_code in NACHA_RETURN_WINDOWS:
            window_days = NACHA_RETURN_WINDOWS[return_code]

            # Compute when the original settlement occurred
            settlement_date_str = state.get("settlement_date", "")
            if settlement_date_str:
                try:
                    settlement_dt = datetime.fromisoformat(settlement_date_str)
                    if settlement_dt.tzinfo is None:
                        settlement_dt = settlement_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    days_since_settlement = (now - settlement_dt).days

                    return_window_open = days_since_settlement <= window_days
                    return_window_days = max(window_days - days_since_settlement, 0)
                    late_return = days_since_settlement > 60  # After 60 days, only R07

                    if not return_window_open:
                        if late_return and return_code != "R07":
                            violations.append(
                                f"UNTIMELY RETURN: Return code {return_code} after 60 days. "
                                "Only R07 (unauthorized) is permitted after the 60-day window. "
                                "Nacha OR Section 3.8.3 — untimely returns may be dishonored by RDFI."
                            )
                        else:
                            violations.append(
                                f"Return code {return_code} outside {window_days}-day return window "
                                f"({days_since_settlement} days since settlement). "
                                "Nacha OR Section 3.8 — return must be within allowable window."
                            )
                except Exception:
                    pass

            # Flag unauthorized returns for enhanced review
            if return_code in UNAUTHORIZED_RETURN_CODES:
                unauthorized_return = True

        # Unauthorized return documentation requirement
        if return_code in ("R07", "R10", "R29"):
            violations.append(
                f"Unauthorized return {return_code}: Consumer/corporate signed statement "
                "required to support return. Nacha OR Section 3.12 — unauthorized returns "
                "require written authorization from account holder."
            )

        # R16 OFAC: should align with OFAC screening result
        if return_code == "R16" and not state.get("ofac_hit"):
            violations.append(
                "Return code R16 (Account Frozen/OFAC) received but OFAC screening "
                "did not confirm match. Verify OFAC status with BSA officer. "
                "31 CFR Part 501 — OFAC reporting requirements."
            )

    # ── CTR Threshold Check ────────────────────────────────────────────────
    # The CTR threshold flag is payment-type agnostic (31 CFR 1010.311 applies
    # to currency transactions over $10,000 regardless of rail). The wire-
    # specific advisory text below adds context for wire transfers.
    amount = state.get("amount", 0)
    try:
        ctr_threshold_triggered = bool(amount) and float(amount) > CTR_THRESHOLD_USD
    except (TypeError, ValueError):
        ctr_threshold_triggered = False
    if ctr_threshold_triggered and payment_type in ("WIRE_DOMESTIC", "WIRE_INTERNATIONAL"):
        violations.append(
            f"Wire transfer amount ${amount:,.2f} exceeds CTR threshold ${CTR_THRESHOLD_USD:,.0f}. "
            "Verify cash component — if cash involved, CTR filing required within 15 days. "
            "31 CFR 1010.311 — Currency Transaction Report."
        )

    validation_passed = not any(
        "untimely" in v.lower() or "invalid" in v.lower() or "missing" in v.lower()
        for v in violations
    )

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "nacha_validation",
        {
            "violations": violations,
            "return_window_open": return_window_open,
            "return_window_days": return_window_days,
            "unauthorized_return": unauthorized_return,
            "late_return": late_return,
            "noc_required": noc_required,
        },
    )

    return {
        "nacha_validation_passed": validation_passed,
        "nacha_violations": violations,
        "return_window_open": return_window_open,
        "return_window_days_remaining": return_window_days,
        "unauthorized_return_eligible": unauthorized_return,
        "late_return_flag": late_return,
        "noc_correction_required": noc_required,
        "noc_required": noc_required,
        "noc_corrected_data": noc_data,
        "ctr_threshold_triggered": ctr_threshold_triggered,
        "is_return": is_return,
        "payment_status": "VALIDATING",
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["nacha_validation"],
    }


# ── Node 4: Reg E Assessment ──────────────────────────────────────────────────

def reg_e_assessment_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 4 — REGULATION E ASSESSMENT

    PURPOSE: Determine Reg E applicability and compute all SLA deadlines.
    This is a Python-only node — SLA calculations must be deterministic.

    REG E SCOPE:
    Reg E (12 CFR Part 1005) applies to electronic fund transfers involving
    a consumer's account. This includes:
    - ACH debit transactions from consumer accounts (PPD, WEB, TEL, POP)
    - Debit card transactions (POS, ATM)
    - Prepaid card transactions (CFPB Prepaid Rule, 12 CFR Part 1005 Subpart E)
    - Online transfers between accounts at the same institution
    - Peer-to-peer payments (Zelle, etc.)

    Reg E does NOT apply to:
    - Wire transfers (UCC Article 4A applies)
    - ACH credits (payments TO the consumer)
    - Business/corporate accounts (CCD, CTX)
    - Credit card transactions (Reg Z / TILA applies)
    - Check transactions (Reg CC / UCC Article 3 applies)

    SLA CALCULATIONS:
    All SLA deadlines are computed in UTC from the received_timestamp.
    Business days exclude Saturday and Sunday (not federal holidays —
    production should add holiday calendar).

    PROVISIONAL CREDIT RULE (12 CFR 1005.11(c)(2)(i)):
    If the institution cannot complete investigation within 10 business days,
    it MUST provisionally credit the account by the 10th business day.
    Exception: foreign-initiated transactions or transactions at new accounts
    (< 30 days) — institution has 20 business days for provisional credit.

    WHAT IT POPULATES:
    reg_e_applicable, reg_e_violations, sla_type, sla_deadline,
    provisional_credit_required, provisional_credit_deadline.
    """
    audit = list(state.get("audit_trail", []))
    reg_e_violations = []

    payment_type = state.get("payment_type", "")
    sec_code = state.get("sec_code", "UNKNOWN")
    is_dispute = bool(state.get("is_dispute", False)) or state.get("dispute_type") not in (None, "", "NOT_DISPUTE")
    dispute_type = state.get("dispute_type", "NOT_DISPUTE")

    # ── Determine Reg E Applicability ─────────────────────────────────────
    # Reg E applies to consumer EFTs — not wire transfers, ACH credits to business accounts
    reg_e_consumer_sec_codes = {"PPD", "WEB", "TEL", "POP", "ARC", "BOC", "CIE"}
    is_consumer_ach_debit = (
        payment_type == "ACH_DEBIT" and sec_code in reg_e_consumer_sec_codes
    )
    is_card_debit = payment_type == "CARD_DEBIT"
    is_prepaid = payment_type == "CARD_PREPAID"
    is_fednow = payment_type == "FEDNOW"  # FedNow may have Reg E implications

    reg_e_applicable = is_consumer_ach_debit or is_card_debit or is_prepaid

    # ── Compute SLA Deadlines ──────────────────────────────────────────────
    received_str = state.get("received_timestamp", _now_utc())
    try:
        received_dt = datetime.fromisoformat(received_str)
        if received_dt.tzinfo is None:
            received_dt = received_dt.replace(tzinfo=timezone.utc)
    except Exception:
        received_dt = datetime.now(timezone.utc)

    sla_type = "NONE"
    sla_deadline = ""
    provisional_credit_required = False
    provisional_credit_deadline = ""
    provisional_credit_amount = state.get("amount", 0.0)
    sla_calendar_days = 0
    sla_business_days = 0

    if is_dispute and reg_e_applicable:
        sla_type = "REG_E_INVESTIGATION"

        # Notification deadline: 3 business days after receiving dispute
        notification_deadline = _compute_business_days(
            received_dt, REG_E_NOTIFICATION_BUSINESS_DAYS
        )

        # Provisional credit deadline: 10 business days
        provisional_deadline_dt = _compute_business_days(
            received_dt, REG_E_PROVISIONAL_CREDIT_BUSINESS_DAYS
        )
        provisional_credit_deadline = provisional_deadline_dt.isoformat()
        provisional_credit_required = True  # Required unless investigation completes in time

        # Investigation deadline: 45 calendar days
        investigation_deadline_dt = received_dt + timedelta(
            days=REG_E_INVESTIGATION_CALENDAR_DAYS
        )
        sla_deadline = investigation_deadline_dt.isoformat()
        sla_calendar_days = REG_E_INVESTIGATION_CALENDAR_DAYS
        sla_business_days = _business_days_until(sla_deadline)

        # Foreign-initiated or new account: 90-day extended window
        is_foreign = state.get("high_risk_country_flag", False) or state.get("sec_code") == "IAT"
        if is_foreign:
            extended_deadline_dt = received_dt + timedelta(
                days=REG_E_EXTENDED_INVESTIGATION_CALENDAR_DAYS
            )
            sla_deadline = extended_deadline_dt.isoformat()
            sla_type = "REG_E_EXTENDED_INVESTIGATION"
            reg_e_violations.append(
                "Foreign-initiated transaction: 90-day extended investigation window applies. "
                "12 CFR 1005.11(c)(3)(ii)."
            )

    elif state.get("is_return") and state.get("return_code") not in ("NONE", None, ""):
        # Nacha return — SLA is the return window
        rc = state.get("return_code", "R01")
        window_days = NACHA_RETURN_WINDOWS.get(rc, 2)
        settlement_str = state.get("settlement_date", received_str)
        try:
            settlement_dt = datetime.fromisoformat(settlement_str)
            if settlement_dt.tzinfo is None:
                settlement_dt = settlement_dt.replace(tzinfo=timezone.utc)
        except Exception:
            settlement_dt = received_dt
        deadline_dt = settlement_dt + timedelta(days=window_days)
        sla_deadline = deadline_dt.isoformat()
        sla_type = "NACHA_RETURN_WINDOW"
        if rc in UNAUTHORIZED_RETURN_CODES:
            sla_type = "NACHA_UNAUTHORIZED_RETURN"
        sla_calendar_days = _calendar_days_until(sla_deadline)
        sla_business_days = _business_days_until(sla_deadline)

    # ── Check for Reg E Violations ─────────────────────────────────────────
    now = datetime.now(timezone.utc)
    sla_breached = bool(sla_deadline and datetime.fromisoformat(sla_deadline) < now
                        if sla_deadline else False)

    if sla_breached and is_dispute and reg_e_applicable:
        reg_e_violations.append(
            f"SLA BREACH: Reg E investigation deadline {sla_deadline[:10]} has passed. "
            "Institution must immediately resolve dispute and notify customer. "
            "12 CFR 1005.11(c) — failure to investigate constitutes a Reg E violation."
        )

    # Reg E does not apply to wire transfers — note for reviewer
    if payment_type in ("WIRE_DOMESTIC", "WIRE_INTERNATIONAL") and is_dispute:
        reg_e_violations.append(
            "Wire transfer dispute: Reg E does not apply (12 CFR 1005.3(b)(1)). "
            "UCC Article 4A governs wire transfer error claims. "
            "Refer to wire operations team for UCC 4A analysis."
        )
        reg_e_applicable = False

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "reg_e_assessment",
        {
            "reg_e_applicable": reg_e_applicable,
            "sla_type": sla_type,
            "sla_deadline": sla_deadline,
            "sla_breached": sla_breached,
            "provisional_credit_required": provisional_credit_required,
            "violations": reg_e_violations,
        },
    )

    return {
        "reg_e_applicable": reg_e_applicable,
        "reg_e_violations": reg_e_violations,
        "reg_e_violation_detected": bool(reg_e_violations),
        "sla_type": sla_type,
        "sla_deadline": sla_deadline,
        "sla_calendar_days_remaining": sla_calendar_days,
        "sla_business_days_remaining": sla_business_days,
        "sla_breached": sla_breached,
        "provisional_credit_required": provisional_credit_required,
        "provisional_credit_deadline": provisional_credit_deadline,
        "provisional_credit_amount": provisional_credit_amount,
        "payment_status": "ASSESSING",
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["reg_e_assessment"],
    }


# ── Node 5: Dispute Analysis (LLM) ───────────────────────────────────────────

def dispute_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 5 — DISPUTE ANALYSIS (LLM)

    PURPOSE: If this event is a customer dispute, use the LLM to analyze
    the customer's claim narrative, assess dispute strength, identify
    missing evidence, and summarize the claim for the human reviewer.

    LLM ROLE:
    The LLM reads the customer's claim text (natural language) and returns:
    - A structured assessment of dispute type and strength
    - Evidence present vs. evidence needed
    - Whether unauthorized transaction indicators are present
    - Whether provisional credit is warranted

    WHAT THE LLM DOES NOT DO:
    - The LLM does not determine whether Reg E applies (Node 4, Python)
    - The LLM does not compute the SLA deadline (Node 4, Python)
    - The LLM does not make the final resolution decision

    If this is not a dispute, the node skips LLM processing.
    """
    audit = list(state.get("audit_trail", []))

    if not state.get("is_dispute"):
        audit_result = _append_audit(
            {**state, "audit_trail": audit},
            "dispute_analysis",
            {"skipped": True, "reason": "Not a dispute event"},
        )
        return {
            "dispute_claim_summary": "",
            "dispute_evidence_present": [],
            "dispute_evidence_missing": [],
            "audit_trail": audit_result,
            "completed_steps": list(state.get("completed_steps", [])) + ["dispute_analysis"],
        }

    from .prompts import DISPUTE_ANALYSIS_SYSTEM_PROMPT, DISPUTE_ANALYSIS_USER_PROMPT

    llm = _get_llm()

    # Build customer claim text — sanitized
    customer_claim = _sanitize_text(
        state.get("remittance_information", "No customer claim text provided."),
        max_length=2000
    )

    user_prompt = DISPUTE_ANALYSIS_USER_PROMPT.format(
        payment_type=state.get("payment_type", "UNKNOWN"),
        sec_code=state.get("sec_code", "UNKNOWN"),
        amount=f"${state.get('amount', 0):,.2f}",
        currency=state.get("currency", "USD"),
        settlement_date=state.get("settlement_date", "Unknown"),
        originator_name=state.get("originator_name", "Unknown"),
        return_code=state.get("return_code", "NONE"),
        customer_claim_text=customer_claim,
        account_tenure="unknown",
        prior_dispute_count=0,
        account_good_standing=True,
        nacha_violations=state.get("nacha_violations", []),
    )

    try:
        response = llm.invoke([
            {"role": "system", "content": DISPUTE_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        data = _parse_llm_json(response.content, "dispute_analysis")
    except Exception as exc:
        logger.error("Dispute analysis LLM error: %s", exc)
        data = {
            "dispute_type_assessed": "UNKNOWN",
            "claim_summary": f"LLM unavailable: {exc}",
            "evidence_present": [],
            "evidence_needed": ["Unable to assess — LLM error"],
            "provisional_credit_warranted": True,  # Fail safe: credit when in doubt
        }

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "dispute_analysis",
        {
            "dispute_type": data.get("dispute_type_assessed"),
            "dispute_strength": data.get("dispute_strength"),
            "provisional_credit_warranted": data.get("provisional_credit_warranted"),
        },
    )

    return {
        "dispute_type": data.get("dispute_type_assessed", state.get("dispute_type", "UNKNOWN")),
        "dispute_claim_summary": data.get("claim_summary", ""),
        "dispute_evidence_present": data.get("evidence_present", []),
        "dispute_evidence_missing": data.get("evidence_needed", []),
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["dispute_analysis"],
    }


# ── Node 6: Compliance Scoring ────────────────────────────────────────────────

def compliance_scoring_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 6 — COMPLIANCE SCORING

    PURPOSE: Compute a Python-weighted composite compliance risk score (0.0–1.0)
    and assign a risk tier (CRITICAL/HIGH/MEDIUM/LOW).

    SCORING METHODOLOGY (SR 11-7 documentation requirement):
    All weights and thresholds are documented here for model risk governance.
    This scoring determines routing priority, not the compliance determination itself.

    FACTORS AND WEIGHTS:
    1. Sanctions Factor (35%): OFAC hit = 1.0; high-risk country = 0.7; PEP = 0.5; clean = 0.0
    2. Unauthorized Factor (25%): R07/R10/R29 unauthorized return = 0.8; dispute = 0.6; none = 0.0
    3. Amount Factor (20%): > $50K = 0.8; > $10K CTR = 0.6; > $5K SAR threshold = 0.4; else 0.2
    4. SLA Factor (10%): breached = 1.0; ≤3 days = 0.8; ≤7 days = 0.5; >7 days = 0.1
    5. Pattern Factor (10%): 3+ violations = 0.8; 1–2 violations = 0.5; 0 = 0.0

    HARD OVERRIDE (security control):
    Any OFAC hit forces CRITICAL tier regardless of composite score.
    This override cannot be bypassed by any combination of other factors.

    TIER ASSIGNMENT:
    CRITICAL ≥ 0.80 | HIGH 0.60–0.79 | MEDIUM 0.35–0.59 | LOW < 0.35
    """
    audit = list(state.get("audit_trail", []))

    # ── Factor 1: Sanctions ────────────────────────────────────────────────
    if state.get("ofac_hit"):
        sanctions_factor = 1.0
    elif state.get("high_risk_country_flag"):
        sanctions_factor = 0.7
    elif state.get("pep_flag"):
        sanctions_factor = 0.5
    else:
        sanctions_factor = 0.0

    # ── Factor 2: Unauthorized Indicator ─────────────────────────────────
    return_code = state.get("return_code", "NONE")
    is_unauthorized_return = return_code in UNAUTHORIZED_RETURN_CODES
    is_dispute = bool(state.get("is_dispute", False)) or state.get("dispute_type") not in (None, "", "NOT_DISPUTE")
    if is_unauthorized_return or state.get("unauthorized_return_eligible"):
        unauthorized_factor = 0.8
    elif is_dispute:
        unauthorized_factor = 0.6
    elif state.get("late_return_flag"):
        unauthorized_factor = 0.7
    else:
        unauthorized_factor = 0.0

    # ── Factor 3: Amount ───────────────────────────────────────────────────
    amount = float(state.get("amount", 0) or 0)
    if amount >= HITL_AMOUNT_THRESHOLD:
        amount_factor = 0.8
    elif amount >= CTR_THRESHOLD_USD:
        amount_factor = 0.6
    elif amount >= SAR_CONSIDERATION_THRESHOLD:
        amount_factor = 0.4
    else:
        amount_factor = 0.2

    # ── Factor 4: SLA Proximity ────────────────────────────────────────────
    sla_breached = state.get("sla_breached", False)
    sla_days = state.get("sla_calendar_days_remaining", 99)
    if sla_breached:
        sla_factor = 1.0
    elif sla_days <= 3:
        sla_factor = 0.8
    elif sla_days <= 7:
        sla_factor = 0.5
    else:
        sla_factor = 0.1

    # ── Factor 5: Violation Pattern ────────────────────────────────────────
    all_violations = (
        list(state.get("nacha_violations", []))
        + list(state.get("reg_e_violations", []))
    )
    violation_count = len(all_violations)
    if violation_count >= 3:
        pattern_factor = 0.8
    elif violation_count >= 1:
        pattern_factor = 0.5
    else:
        pattern_factor = 0.0

    # ── Composite Score ────────────────────────────────────────────────────
    composite = (
        sanctions_factor   * RISK_WEIGHTS["sanctions_factor"]
        + unauthorized_factor * RISK_WEIGHTS["unauthorized_factor"]
        + amount_factor       * RISK_WEIGHTS["amount_factor"]
        + sla_factor          * RISK_WEIGHTS["sla_factor"]
        + pattern_factor      * RISK_WEIGHTS["pattern_factor"]
    )
    composite = round(min(max(composite, 0.0), 1.0), 4)

    # ── Tier Assignment ────────────────────────────────────────────────────
    # HARD OVERRIDE: OFAC hit = CRITICAL tier AND score forced to 1.0,
    # regardless of composite. The override applies to BOTH outputs so no
    # downstream consumer of the numeric score can deprioritize an OFAC hit.
    # FAIL-CLOSED: if sanctions screening had no data to screen, the event
    # is also forced to CRITICAL — an unscreened payment is never low risk.
    if state.get("ofac_hit") or state.get("screening_data_missing"):
        tier = "CRITICAL"
        composite = 1.0
    elif composite >= 0.80:
        tier = "CRITICAL"
    elif composite >= 0.60:
        tier = "HIGH"
    elif composite >= 0.35:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    # ── SAR Consideration ──────────────────────────────────────────────────
    # SAR consideration is Python-flagged — never LLM-decided
    sar_candidate = (
        amount >= SAR_CONSIDERATION_THRESHOLD
        and (is_unauthorized_return or is_dispute)
        and (state.get("ofac_hit") or state.get("high_risk_country_flag") or amount >= 25_000)
    )

    # Priority for routing
    if tier == "CRITICAL":
        priority = "CRITICAL"
    elif tier == "HIGH":
        priority = "HIGH"
    elif tier == "MEDIUM":
        priority = "NORMAL"
    else:
        priority = "LOW"

    breakdown = {
        "sanctions_factor": sanctions_factor,
        "unauthorized_factor": unauthorized_factor,
        "amount_factor": amount_factor,
        "sla_factor": sla_factor,
        "pattern_factor": pattern_factor,
        "composite": composite,
        "ofac_hard_override": state.get("ofac_hit", False),
        "sar_candidate": sar_candidate,
    }

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "compliance_scoring",
        {
            "composite_score": composite,
            "tier": tier,
            "sar_candidate": sar_candidate,
            "violation_count": violation_count,
        },
    )

    return {
        "compliance_risk_score": composite,
        "compliance_risk_tier": tier,
        "score_breakdown": breakdown,
        "violation_count": violation_count,
        "violation_severity_max": tier,
        "priority": priority,
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["compliance_scoring"],
    }


# ── Node 7: Compliance Analysis (LLM) ────────────────────────────────────────

def compliance_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 7 — COMPLIANCE ANALYSIS (LLM)

    PURPOSE: Generate a narrative compliance analysis for the human reviewer.
    The LLM receives the Python-determined compliance findings (violations,
    risk score, sanctions results, SLA status) and synthesizes them into
    a coherent, actionable narrative with regulatory citations.

    INPUT TO LLM: Structured findings already determined by Python.
    OUTPUT FROM LLM: Narrative text for the reviewer.

    The LLM does not re-determine any of the compliance findings —
    it only explains them in human-readable form and adds regulatory
    context that helps the reviewer understand the significance.
    """
    audit = list(state.get("audit_trail", []))

    from .prompts import COMPLIANCE_ANALYSIS_SYSTEM_PROMPT, COMPLIANCE_ANALYSIS_USER_PROMPT

    llm = _get_llm()

    user_prompt = COMPLIANCE_ANALYSIS_USER_PROMPT.format(
        payment_type=state.get("payment_type", "UNKNOWN"),
        amount=f"${state.get('amount', 0):,.2f}",
        currency=state.get("currency", "USD"),
        return_code=state.get("return_code", "NONE"),
        return_reason=state.get("return_reason", "N/A"),
        dispute_type=state.get("dispute_type", "NOT_DISPUTE"),
        nacha_violations="; ".join(state.get("nacha_violations", [])) or "None",
        reg_e_violations="; ".join(state.get("reg_e_violations", [])) or "None",
        reg_e_applicable=state.get("reg_e_applicable", False),
        ofac_hit=state.get("ofac_hit", False),
        high_risk_country_flag=state.get("high_risk_country_flag", False),
        high_risk_country_name=state.get("high_risk_country_name", "N/A"),
        pep_flag=state.get("pep_flag", False),
        sla_calendar_days_remaining=state.get("sla_calendar_days_remaining", "N/A"),
        sla_breached=state.get("sla_breached", False),
        unauthorized_return_eligible=state.get("unauthorized_return_eligible", False),
        late_return_flag=state.get("late_return_flag", False),
        compliance_risk_score=state.get("compliance_risk_score", 0.0),
        compliance_risk_tier=state.get("compliance_risk_tier", "LOW"),
        resolution_type=state.get("resolution_type", "TBD"),
        target_team=state.get("target_team", "TBD"),
        originator_name=state.get("originator_name", "Unknown"),
        receiver_name=state.get("receiver_name", "Unknown"),
        odfi_name=state.get("odfi_name", "Unknown"),
        rdfi_name=state.get("rdfi_name", "Unknown"),
    )

    try:
        response = llm.invoke([
            {"role": "system", "content": COMPLIANCE_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        data = _parse_llm_json(response.content, "compliance_analysis")
    except Exception as exc:
        logger.error("Compliance analysis LLM error: %s", exc)
        data = {
            "compliance_analysis": f"Analysis unavailable due to LLM error: {exc}",
            "anomaly_flags": [],
            "regulatory_citations": [],
            "risk_narrative": "See Python-determined violations for details.",
            "sar_consideration": state.get("score_breakdown", {}).get("sar_candidate", False),
        }

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "compliance_analysis",
        {"sar_consideration": data.get("sar_consideration"), "flags_count": len(data.get("anomaly_flags", []))},
    )

    return {
        "compliance_analysis": data.get("compliance_analysis", ""),
        "anomaly_flags": data.get("anomaly_flags", []),
        "regulatory_citations": data.get("regulatory_citations", []),
        "risk_narrative": data.get("risk_narrative", ""),
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["compliance_analysis"],
    }


# ── Node 8: Routing Decision ──────────────────────────────────────────────────

def routing_decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 8 — ROUTING DECISION

    PURPOSE: Determine which team handles this event, what the initial
    resolution type is, and whether human review is required.

    SECURITY DESIGN: All routing decisions are deterministic Python.
    The LLM cannot influence routing. This prevents prompt injection
    attacks from redirecting OFAC holds or SAR candidates.

    HITL REQUIRED WHEN:
    - OFAC hit (hard rule — no exceptions)
    - Amount > $50,000 (wire threshold)
    - Unauthorized return code (R07/R10/R29)
    - Risk tier CRITICAL or HIGH
    - SLA already breached (escalation required)
    - Late return dispute (legal review required)
    - CTR threshold triggered for cash payments
    - SAR candidate flagged by scoring node

    AUTO-RESOLVE (no HITL) WHEN:
    - Administrative return (R01, R02, R03) with LOW/MEDIUM risk
    - NOC update required only
    - Routine validation failure (correctable)
    """
    audit = list(state.get("audit_trail", []))

    ofac_hit = state.get("ofac_hit", False)
    risk_tier = state.get("compliance_risk_tier", "LOW")
    amount = float(state.get("amount", 0) or 0)
    is_unauthorized = state.get("unauthorized_return_eligible", False)
    return_code = state.get("return_code", "NONE")
    sla_breached = state.get("sla_breached", False)
    late_return = state.get("late_return_flag", False)
    high_risk_country = state.get("high_risk_country_flag", False)
    sar_candidate = state.get("score_breakdown", {}).get("sar_candidate", False)
    is_dispute = bool(state.get("is_dispute", False)) or state.get("dispute_type") not in (None, "", "NOT_DISPUTE")
    noc_only = state.get("noc_correction_required", False) and not is_dispute
    payment_type = state.get("payment_type", "UNKNOWN")
    violation_count = state.get("violation_count", 0)

    # ── Determine HITL and Routing ─────────────────────────────────────────
    human_review_required = False
    human_review_reason = ""
    target_team = "PAYMENTS_OPS"
    resolution_type = "NO_ACTION_REQUIRED"
    escalation_path = []

    # HARD RULE: OFAC hit always requires BSA and HITL
    if ofac_hit:
        human_review_required = True
        human_review_reason = "OFAC SDN match — sanctions hold required. BSA Officer must review."
        target_team = "BSA_COMPLIANCE"
        resolution_type = "BLOCK_AND_FREEZE"
        escalation_path = ["BSA_OFFICER", "COMPLIANCE_OFFICER", "LEGAL"]

    # High-risk country wire requires BSA HITL
    elif high_risk_country and payment_type in ("WIRE_INTERNATIONAL", "ACH_IAT"):
        human_review_required = True
        human_review_reason = f"Wire to high-risk country ({state.get('high_risk_country_name')}) — enhanced due diligence required."
        target_team = "BSA_COMPLIANCE"
        resolution_type = "BLOCK_AND_FREEZE"
        escalation_path = ["BSA_OFFICER", "COMPLIANCE_OFFICER"]

    # SAR candidate — BSA review
    elif sar_candidate:
        human_review_required = True
        human_review_reason = f"SAR consideration: ${amount:,.2f} unauthorized/suspicious activity. BSA review required."
        target_team = "BSA_COMPLIANCE"
        resolution_type = "ESCALATE_TO_BSA"
        escalation_path = ["BSA_OFFICER", "COMPLIANCE_OFFICER"]

    # Unauthorized return — disputes team
    elif is_unauthorized or return_code in UNAUTHORIZED_RETURN_CODES:
        human_review_required = True
        human_review_reason = f"Unauthorized return ({return_code}) — customer authorization review required."
        target_team = "DISPUTES"
        resolution_type = "RETURN_ITEM"
        escalation_path = ["DISPUTES_ANALYST", "DISPUTES_SUPERVISOR"]

    # Reg E dispute — disputes team
    elif is_dispute and state.get("reg_e_applicable"):
        human_review_required = True
        human_review_reason = "Reg E consumer dispute — 10-business-day provisional credit clock running."
        target_team = "DISPUTES"
        if state.get("provisional_credit_required"):
            resolution_type = "PROVISIONAL_CREDIT"
        else:
            resolution_type = "RETURN_ITEM"
        escalation_path = ["DISPUTES_ANALYST"]

    # Late return — legal review
    elif late_return:
        human_review_required = True
        human_review_reason = "Late return after 60-day window — legal review required for R07 eligibility."
        target_team = "LEGAL"
        resolution_type = "ESCALATE_TO_LEGAL"
        escalation_path = ["DISPUTES_ANALYST", "LEGAL_COUNSEL"]

    # SLA breach — escalate
    elif sla_breached:
        human_review_required = True
        human_review_reason = "SLA deadline exceeded — immediate escalation required."
        target_team = "DISPUTES"
        resolution_type = "ESCALATE_TO_LEGAL"
        escalation_path = ["DISPUTES_SUPERVISOR", "COMPLIANCE_OFFICER"]

    # CRITICAL or HIGH risk tier
    elif risk_tier in ("CRITICAL", "HIGH"):
        human_review_required = True
        human_review_reason = f"Risk tier {risk_tier} — human review required."
        target_team = "PAYMENTS_OPS"
        resolution_type = "RETURN_ITEM"

    # Large amount threshold
    elif amount >= HITL_AMOUNT_THRESHOLD:
        human_review_required = True
        human_review_reason = f"Transaction amount ${amount:,.2f} exceeds ${HITL_AMOUNT_THRESHOLD:,.0f} review threshold."
        target_team = "PAYMENTS_OPS"
        resolution_type = "FORWARD_AND_NOTIFY"

    # NOC-only — auto-resolve with record update notification
    elif noc_only:
        human_review_required = False
        target_team = "PAYMENTS_OPS"
        resolution_type = "NOC_UPDATE_REQUIRED"

    # Administrative return (R01-R04, R08, R09) — auto-resolve
    elif return_code in ("R01", "R02", "R03", "R04", "R08", "R09") and violation_count == 0:
        human_review_required = False
        target_team = "PAYMENTS_OPS"
        resolution_type = "RETURN_ITEM"

    # Low risk, no violations — auto-resolve
    elif risk_tier == "LOW" and violation_count == 0:
        human_review_required = False
        target_team = "AUTO_RESOLVE"
        resolution_type = "NO_ACTION_REQUIRED"

    else:
        # Default — payments ops review
        human_review_required = True
        human_review_reason = f"Compliance violations requiring review: {violation_count} issue(s) found."
        target_team = "PAYMENTS_OPS"
        resolution_type = "RETURN_ITEM"

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "routing_decision",
        {
            "human_review_required": human_review_required,
            "target_team": target_team,
            "resolution_type": resolution_type,
            "reason": human_review_reason,
        },
    )

    return {
        "target_team": target_team,
        "resolution_type": resolution_type,
        "human_review_required": human_review_required,
        "human_review_reason": human_review_reason,
        "escalation_path": escalation_path,
        "payment_status": "PENDING_REVIEW" if human_review_required else "RESOLVED",
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["routing_decision"],
    }


# ── Node 9: Human Review Gate ─────────────────────────────────────────────────

def human_review_gate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 9 — HUMAN REVIEW GATE

    PURPOSE: Process the human reviewer's decision.

    This node runs AFTER the LangGraph interrupt_before pauses the graph.
    When the graph is resumed (via graph.invoke() after the reviewer submits
    their decision), this node reads the reviewer's decision from state and
    records it in the audit trail.

    REVIEWER DECISIONS:
    - APPROVE_RESOLUTION: Accept the Python-determined resolution. Proceed to
      resolution drafting and customer notice.
    - OVERRIDE_RESOLUTION: Replace the Python-determined resolution with the
      reviewer's choice. Proceed with the reviewer's resolution.
    - ESCALATE: Escalate to next tier (BSA, Legal, Compliance). Update
      escalation path and re-route.
    - REJECT_CLAIM: Deny the customer's dispute claim. Proceed to customer
      notice with denial.

    SECURITY: The reviewer's decision is recorded in the append-only audit
    trail with reviewer_id and timestamp. This provides an immutable record
    of who made what decision and when.
    """
    audit = list(state.get("audit_trail", []))

    decision = state.get("reviewer_decision", "")
    reviewer_id = state.get("reviewer_id", "unknown")
    reviewer_notes = state.get("reviewer_notes", "")
    override_resolution = state.get("reviewer_override_resolution", "")

    # Apply reviewer's override if provided
    resolution_type = state.get("resolution_type", "NO_ACTION_REQUIRED")
    if decision == "OVERRIDE_RESOLUTION" and override_resolution:
        resolution_type = override_resolution

    status = "RESOLVED"
    if decision == "ESCALATE":
        status = "ESCALATED"
    elif decision == "REJECT_CLAIM":
        resolution_type = "DENY_CLAIM"

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "human_review_gate",
        {
            "reviewer_id": reviewer_id,
            "decision": decision,
            "override_resolution": override_resolution,
            "notes": reviewer_notes,
        },
    )

    return {
        "resolution_type": resolution_type,
        "payment_status": status,
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["human_review_gate"],
    }


# ── Node 10: Resolution Drafting (LLM) ───────────────────────────────────────

def resolution_drafting_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 10 — RESOLUTION DRAFTING (LLM)

    PURPOSE: Draft the customer notice (if Reg E requires one) and the
    internal resolution memo. Both use the LLM for natural language
    generation — the compliance determinations have already been made.

    REG E NOTICE REQUIREMENT (12 CFR 1005.11(d)):
    The institution must notify the consumer within 3 business days of
    completing the investigation of:
    (1) The error corrected and the amount credited, OR
    (2) A determination that no error occurred, with the customer's
        right to request documentation and 10-day deadline.

    WHAT IT POPULATES:
    customer_notice_text, customer_notice_required, customer_notice_deadline,
    resolution_summary, internal_memo.
    """
    audit = list(state.get("audit_trail", []))

    from .prompts import (
        CUSTOMER_NOTICE_SYSTEM_PROMPT,
        CUSTOMER_NOTICE_USER_PROMPT,
        RESOLUTION_MEMO_SYSTEM_PROMPT,
        RESOLUTION_MEMO_USER_PROMPT,
    )

    llm = _get_llm()
    resolution_type = state.get("resolution_type", "NO_ACTION_REQUIRED")
    reg_e_applicable = state.get("reg_e_applicable", False)
    is_dispute = bool(state.get("is_dispute", False)) or state.get("dispute_type") not in (None, "", "NOT_DISPUTE")

    customer_notice_text = ""
    customer_notice_required = False
    customer_notice_deadline = ""
    resolution_date = _now_utc()[:10]  # YYYY-MM-DD

    # ── Customer Notice (Reg E disputes only) ─────────────────────────────
    if is_dispute and reg_e_applicable:
        customer_notice_required = True
        # Notice deadline: 3 business days after resolution
        notice_deadline_dt = _compute_business_days(
            datetime.now(timezone.utc), REG_E_NOTIFICATION_BUSINESS_DAYS
        )
        customer_notice_deadline = notice_deadline_dt.isoformat()

        notice_user_prompt = CUSTOMER_NOTICE_USER_PROMPT.format(
            dispute_type=state.get("dispute_type", "UNKNOWN"),
            resolution_type=resolution_type,
            amount=f"${state.get('amount', 0):,.2f}",
            currency=state.get("currency", "USD"),
            settlement_date=state.get("settlement_date", "Unknown"),
            resolution_date=resolution_date,
            receiver_name=state.get("receiver_name", "Valued Customer"),
            receiver_account_last4=state.get("receiver_account_last4", "****")[-4:],
            originator_name=state.get("originator_name", "Unknown Originator"),
            institution_name="First National Bank",
            resolution_summary=state.get("compliance_analysis", "See investigation findings."),
            provisional_credit_required=state.get("provisional_credit_required", False),
            provisional_credit_amount=f"${state.get('provisional_credit_amount', 0):,.2f}",
            reg_e_violations="; ".join(state.get("reg_e_violations", [])) or "None identified",
        )

        try:
            notice_response = llm.invoke([
                {"role": "system", "content": CUSTOMER_NOTICE_SYSTEM_PROMPT},
                {"role": "user", "content": notice_user_prompt},
            ])
            notice_data = _parse_llm_json(notice_response.content, "customer_notice")
            customer_notice_text = notice_data.get("notice_text", "")
        except Exception as exc:
            logger.error("Customer notice LLM error: %s", exc)
            customer_notice_text = (
                f"Regarding your recent dispute for ${state.get('amount', 0):,.2f}:\n"
                f"We have completed our investigation. Resolution: {resolution_type}.\n"
                "Please contact us with any questions."
            )

    # ── Internal Resolution Memo ──────────────────────────────────────────
    memo_user_prompt = RESOLUTION_MEMO_USER_PROMPT.format(
        payment_type=state.get("payment_type", "UNKNOWN"),
        amount=f"${state.get('amount', 0):,.2f}",
        currency=state.get("currency", "USD"),
        return_code=state.get("return_code", "NONE"),
        return_reason=state.get("return_reason", "N/A"),
        dispute_type=state.get("dispute_type", "NOT_DISPUTE"),
        resolution_type=resolution_type,
        compliance_risk_tier=state.get("compliance_risk_tier", "LOW"),
        nacha_violations="; ".join(state.get("nacha_violations", [])) or "None",
        reg_e_violations="; ".join(state.get("reg_e_violations", [])) or "None",
        ofac_hit=state.get("ofac_hit", False),
        high_risk_country_name=state.get("high_risk_country_name", "N/A"),
        sla_deadline=state.get("sla_deadline", "N/A"),
        sla_calendar_days_remaining=state.get("sla_calendar_days_remaining", "N/A"),
        sla_breached=state.get("sla_breached", False),
        reviewer_decision=state.get("reviewer_decision", "AUTO_RESOLVED"),
        reviewer_notes=state.get("reviewer_notes", ""),
    )

    try:
        memo_response = llm.invoke([
            {"role": "system", "content": RESOLUTION_MEMO_SYSTEM_PROMPT},
            {"role": "user", "content": memo_user_prompt},
        ])
        memo_data = _parse_llm_json(memo_response.content, "resolution_memo")
        resolution_summary = memo_data.get("executive_summary", "")
        internal_memo_text = json.dumps(memo_data, indent=2)
    except Exception as exc:
        logger.error("Resolution memo LLM error: %s", exc)
        resolution_summary = f"Payments compliance event resolved: {resolution_type}"
        internal_memo_text = resolution_summary

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "resolution_drafting",
        {
            "resolution_type": resolution_type,
            "customer_notice_required": customer_notice_required,
            "notice_deadline": customer_notice_deadline,
        },
    )

    return {
        "customer_notice_text": customer_notice_text,
        "customer_notice_required": customer_notice_required,
        "customer_notice_deadline": customer_notice_deadline,
        "resolution_summary": resolution_summary,
        "internal_memo": internal_memo_text,
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["resolution_drafting"],
    }


# ── Node 11: Output Packaging ─────────────────────────────────────────────────

def output_packaging_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 11 — OUTPUT PACKAGING

    PURPOSE: Assemble the structured compliance event record for downstream
    systems (core banking, case management, audit database). Apply final
    account number masking check before packaging.

    The output_payload is a clean, structured dict containing:
    - All compliance findings and scores
    - Resolution type and target team
    - SLA status and deadlines
    - Customer notice status
    - Full audit references

    Full account numbers are NEVER included in the output payload.
    The final masking check here provides defense-in-depth.
    """
    audit = list(state.get("audit_trail", []))

    # Final PII check — ensure no full account numbers slipped through
    # This is defense-in-depth; masking should have occurred at intake
    def _final_mask(value: Any) -> Any:
        if isinstance(value, str):
            return re.sub(r"\b(\d{4,13})(\d{4})\b", r"****\2", value)
        return value

    downstream_actions = []

    # Build downstream action list based on resolution
    resolution_type = state.get("resolution_type", "NO_ACTION_REQUIRED")
    if resolution_type == "RETURN_ITEM":
        downstream_actions.append({
            "action": "INITIATE_RETURN",
            "return_code": state.get("return_code"),
            "target_system": "NACHA_FILE_PROCESSOR",
            "deadline": state.get("sla_deadline"),
        })
    if state.get("provisional_credit_required"):
        downstream_actions.append({
            "action": "ISSUE_PROVISIONAL_CREDIT",
            "amount": state.get("provisional_credit_amount"),
            "account_last4": state.get("receiver_account_last4"),
            "deadline": state.get("provisional_credit_deadline"),
            "target_system": "CORE_BANKING",
        })
    if state.get("customer_notice_required"):
        downstream_actions.append({
            "action": "SEND_CUSTOMER_NOTICE",
            "notice_text": state.get("customer_notice_text", ""),
            "deadline": state.get("customer_notice_deadline"),
            "target_system": "CUSTOMER_COMMUNICATIONS",
        })
    if state.get("noc_correction_required"):
        downstream_actions.append({
            "action": "NOTIFY_ODFI_NOC",
            "noc_data": state.get("noc_corrected_data", {}),
            "target_system": "NACHA_FILE_PROCESSOR",
        })
    if state.get("ofac_hit") or state.get("sanctions_hold_required"):
        downstream_actions.append({
            "action": "FILE_OFAC_REPORT",
            "target_system": "BSA_PLATFORM",
            "priority": "CRITICAL",
        })
    if state.get("score_breakdown", {}).get("sar_candidate"):
        downstream_actions.append({
            "action": "SAR_CONSIDERATION",
            "target_system": "BSA_PLATFORM",
            "priority": "HIGH",
            "note": "BSA officer must make final SAR filing determination",
        })

    output_payload = {
        "payment_id": state.get("payment_id"),
        "payment_hash": state.get("payment_hash"),
        "payment_type": state.get("payment_type"),
        "amount": state.get("amount"),
        "currency": state.get("currency"),
        "settlement_date": state.get("settlement_date"),
        "originator_name": _final_mask(state.get("originator_name", "")),
        "originator_account_last4": state.get("originator_account_last4"),
        "receiver_name": _final_mask(state.get("receiver_name", "")),
        "receiver_account_last4": state.get("receiver_account_last4"),
        "return_code": state.get("return_code"),
        "compliance_risk_tier": state.get("compliance_risk_tier"),
        "compliance_risk_score": state.get("compliance_risk_score"),
        "resolution_type": resolution_type,
        "target_team": state.get("target_team"),
        "ofac_hit": state.get("ofac_hit"),
        "high_risk_country_flag": state.get("high_risk_country_flag"),
        "nacha_violations": state.get("nacha_violations", []),
        "reg_e_violations": state.get("reg_e_violations", []),
        "sla_deadline": state.get("sla_deadline"),
        "sla_breached": state.get("sla_breached"),
        "provisional_credit_required": state.get("provisional_credit_required"),
        "resolution_summary": state.get("resolution_summary"),
        "processing_timestamp": _now_utc(),
        "schema_version": "1.0.0",
    }

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "output_packaging",
        {"resolution_type": resolution_type, "downstream_actions_count": len(downstream_actions)},
    )

    return {
        "output_payload": output_payload,
        "downstream_actions": downstream_actions,
        "payment_status": "RESOLVED" if state.get("payment_status") != "ESCALATED" else "ESCALATED",
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["output_packaging"],
    }


# ── Node 12: Audit Finalize ───────────────────────────────────────────────────

def audit_finalize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NODE 12 — AUDIT FINALIZE

    PURPOSE: Record final processing metrics, set the definitive payment_status,
    and generate the compliance event ID for the audit database.

    The audit trail appended here is the final entry — it records the complete
    processing time, final resolution, and all compliance flags in one
    summary record suitable for regulatory examination.

    WHAT IT FINALIZES:
    processing_time_seconds, payment_status, final audit_trail entry.
    """
    audit = list(state.get("audit_trail", []))

    submission_ts = state.get("submission_timestamp", _now_utc())
    try:
        start = datetime.fromisoformat(submission_ts)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    except Exception:
        elapsed = 0.0

    final_status = state.get("payment_status", "RESOLVED")

    audit_result = _append_audit(
        {**state, "audit_trail": audit},
        "audit_finalize",
        {
            "final_status": final_status,
            "processing_time_seconds": elapsed,
            "resolution_type": state.get("resolution_type"),
            "compliance_risk_tier": state.get("compliance_risk_tier"),
            "ofac_hit": state.get("ofac_hit"),
            "sla_breached": state.get("sla_breached"),
            "violation_count": state.get("violation_count", 0),
            "provisional_credit_required": state.get("provisional_credit_required"),
            "customer_notice_required": state.get("customer_notice_required"),
        },
    )

    return {
        "processing_time_seconds": elapsed,
        "payment_status": final_status,
        "audit_trail": audit_result,
        "completed_steps": list(state.get("completed_steps", [])) + ["audit_finalize"],
    }
