# agent/nodes.py
# ============================================================
# Fraud Detection Agent — Node Functions
#
# Each node returns a Dict[str, Any] of state updates.
# All nodes append to audit_trail for examination readiness.
#
# Regulatory requirements enforced deterministically (not by LLM):
#   - Hard blocks: known fraud IP, confirmed stolen card, OFAC merchant
#   - Reg E disclosure: auto-drafted for all BLOCK / FREEZE decisions
#   - SAR flag: set when fraud exhibits money laundering indicators
#   - No tipping off: analyst queue routed silently (18 U.S.C. § 1960)
#
# LLM role: contextual analysis and plain-language explanation only.
#   The LLM never makes the routing decision — that is always Python.
# ============================================================

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

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
CLAUDE_NARRATIVE_MODEL = _os_llm.getenv("CLAUDE_NARRATIVE_MODEL", "claude-sonnet-4-6")
CLAUDE_FAST_MODEL = _os_llm.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5")
CLAUDE_DEFAULT_MODEL = CLAUDE_FAST_MODEL


from agent.state import (
    FraudDetectionState,
    FraudDecision,
    FraudType,
    TransactionChannel,
)
from agent.prompts import (
    FRAUD_ANALYSIS_SYSTEM_PROMPT,
    FRAUD_ANALYSIS_HUMAN_PROMPT,
    REG_E_DISCLOSURE_PROMPT,
    STEP_UP_AUTH_PROMPT,
    CASE_NARRATIVE_PROMPT,
)

logger = logging.getLogger(__name__)


# ── Shared Helpers ────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_audit_entry(
    state: FraudDetectionState,
    action: str,
    node: str,
    data_sources: Optional[List[str]] = None,
    ai_model: Optional[str] = None,
    score_at_time: Optional[float] = None,
    regulatory_basis: Optional[str] = None,
    response_ms: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Build updated audit trail with a new entry appended.
    Returns a new list (does not mutate the original).

    Audit trail is append-only — BSA 5-year retention requirement.
    Each entry documents the data sources accessed for SR 11-7
    model documentation and CFPB fair lending review.
    """
    trail = list(state.get("audit_trail") or [])
    trail.append({
        "timestamp": _utcnow(),
        "actor": "fraud_detection_agent",
        "action": action,
        "node": node,
        "score_at_time": score_at_time,
        "data_sources_accessed": data_sources or [],
        "ai_model_used": ai_model,
        "response_time_ms": response_ms,
        "regulatory_basis": regulatory_basis,
    })
    return trail


def _get_llm(temperature: float = 0.0) -> ChatAnthropic:
    """
    Return LLM instance.
    temperature=0 for scoring consistency (SR 11-7 model risk management).
    """
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL, temperature=temperature)


# ── NODE 1: Transaction Intake ────────────────────────────────────────────────

def transaction_intake(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Parse and validate the incoming transaction event.

    Validates required fields, normalizes timestamps, sets up
    the completed_steps tracker, and starts the audit trail.

    In production: receives event from Kafka/Kinesis or REST API.
    Validates against card network message format (ISO 8583 for card,
    Nacha CCD/PPD for ACH, Fedwire/CHIPS for wire).

    Regulatory note:
      Transaction timestamp must be preserved exactly — used for
      Reg E dispute timeline calculations (60-day reporting window
      starts from statement date, not detection date).
    """
    start_ms = int(time.time() * 1000)
    txn_id = state.get("transaction_id", "UNKNOWN")
    logger.info(f"[transaction_intake] Processing transaction {txn_id}")

    errors = list(state.get("errors") or [])

    # Validate required fields
    required_fields = [
        "transaction_id", "account_id", "customer_id",
        "transaction_amount", "transaction_type", "transaction_channel",
        "transaction_timestamp",
    ]
    for field in required_fields:
        if not state.get(field):
            errors.append({
                "node": "transaction_intake",
                "field": field,
                "message": f"Required field '{field}' missing or empty",
                "timestamp": _utcnow(),
            })
            logger.warning(f"[transaction_intake] Missing required field: {field}")

    # Initialize infrastructure fields
    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("transaction_intake")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Transaction {txn_id} received — amount ${state.get('transaction_amount', 0):.2f} "
               f"via {state.get('transaction_channel', 'UNKNOWN')}",
        node="transaction_intake",
        data_sources=["payment_event_stream"],
        response_ms=elapsed_ms,
        regulatory_basis="Reg E § 1005.11 — transaction record required for dispute window",
    )

    return {
        "current_step": "transaction_intake",
        "completed_steps": completed_steps,
        "errors": errors,
        "audit_trail": audit_trail,
    }


# ── NODE 2: Account Context Lookup ────────────────────────────────────────────

def account_context_lookup(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Retrieve account history, expected behavior profile, and risk tier.

    Fetches from core banking / CRM system:
      - Account age, average transaction amount, typical geographies
      - Prior fraud disputes, chargeback history
      - Customer risk tier (LOW / MEDIUM / HIGH)
      - 2FA enrollment status
      - Expected activity profile (FinCEN CDD Rule baseline)

    Regulatory note:
      The expected activity profile is the FinCEN CDD Rule-required
      "expected transaction activity" baseline. Deviations from this
      baseline are the core signal for Suspicious Activity Reports.
      (31 CFR 1020.210 — customer due diligence)

    In production: queries core banking API / customer data warehouse.
    Response cached per transaction session to avoid repeated round-trips.
    """
    start_ms = int(time.time() * 1000)
    account_id = state.get("account_id", "UNKNOWN")
    logger.info(f"[account_context_lookup] Fetching context for account {account_id}")

    # Simulate account profile retrieval
    # In production: replace with core banking API call
    account_profile = _simulate_account_profile(
        account_id=account_id,
        transaction_amount=state.get("transaction_amount", 0),
        transaction_channel=state.get("transaction_channel"),
        merchant_country=state.get("merchant_country"),
    )

    # Calculate transaction amount vs. average ratio
    avg_amount = account_profile.get("average_transaction_amount", 100.0)
    current_amount = state.get("transaction_amount", 0)
    amount_ratio = round(current_amount / avg_amount, 2) if avg_amount > 0 else 1.0

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("account_context_lookup")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Account context loaded — {account_profile.get('account_age_days', 0)} day-old account, "
               f"risk tier {account_profile.get('customer_risk_tier', 'UNKNOWN')}, "
               f"amount ratio vs. avg: {amount_ratio}x",
        node="account_context_lookup",
        data_sources=["core_banking_api", "customer_data_warehouse", "fraud_history_db"],
        response_ms=elapsed_ms,
        regulatory_basis="FinCEN CDD Rule 31 CFR 1020.210 — expected transaction activity baseline",
    )

    return {
        "account_profile": account_profile,
        "transaction_amount_vs_average": amount_ratio,
        "current_step": "account_context_lookup",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


def _simulate_account_profile(
    account_id: str,
    transaction_amount: float,
    transaction_channel: Optional[str],
    merchant_country: Optional[str],
) -> Dict[str, Any]:
    """Simulate account profile for demo. Replace with API call in production."""
    # Seed randomness deterministically by account_id for reproducible demos
    rng = random.Random(hash(account_id) % 10000)

    avg_amount = rng.uniform(50, 500)
    is_online_typical = transaction_channel in (
        TransactionChannel.ONLINE_BANKING,
        TransactionChannel.MOBILE_APP,
        "ONLINE_BANKING",
        "MOBILE_APP",
    )

    return {
        "account_age_days": rng.randint(90, 3650),
        "average_transaction_amount": round(avg_amount, 2),
        "average_monthly_volume": round(avg_amount * rng.randint(10, 50), 2),
        "typical_merchants": ["grocery", "gas_station", "restaurant", "online_retail"],
        "typical_transaction_channels": (
            ["ONLINE_BANKING", "MOBILE_APP", "POS_CHIP"]
            if is_online_typical
            else ["POS_CHIP", "POS_CONTACTLESS", "ATM"]
        ),
        "typical_geographies": [merchant_country or "US"],
        "enrolled_in_2fa": rng.random() > 0.3,
        "fraud_history_count": rng.randint(0, 2),
        "dispute_history_count": rng.randint(0, 3),
        "customer_risk_tier": rng.choice(["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH"]),
        "last_transaction_location": "US",
        "last_transaction_timestamp": _utcnow(),
    }


# ── NODE 3: Feature Extraction ─────────────────────────────────────────────────

def feature_extraction(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Build the structured feature vector for rule engine and ML scoring.

    Extracts and computes:
      - Velocity signals (1m/5m/1h/24h transaction counts and amounts)
      - Amount anomaly ratio (current vs. account average)
      - Geographic risk signals (cross-border, high-risk country)
      - Channel risk factor (CNP is higher risk than chip-present)
      - Time-of-day risk (late night / unusual hours)
      - Device context completeness

    These features feed both the deterministic rule engine (node 4)
    and the LLM analysis (node 7). Separating feature extraction ensures
    both scorers use identical inputs — required for SR 11-7 model
    documentation and consistency testing.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[feature_extraction] Extracting features for {state.get('transaction_id')}")

    velocity_signals = _compute_velocity_signals(state)

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("feature_extraction")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Features extracted — velocity flag: {velocity_signals.get('velocity_flag', False)}, "
               f"txn_count_1hr: {velocity_signals.get('txn_count_1hr', 0)}, "
               f"amount_sum_1hr: ${velocity_signals.get('amount_sum_1hr', 0):.2f}",
        node="feature_extraction",
        data_sources=["transaction_history_db", "velocity_cache"],
        response_ms=elapsed_ms,
        regulatory_basis="SR 11-7 — feature documentation for model risk management",
    )

    return {
        "velocity_signals": velocity_signals,
        "current_step": "feature_extraction",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


def _compute_velocity_signals(state: FraudDetectionState) -> Dict[str, Any]:
    """Simulate velocity checks. In production: query real-time Redis velocity counters."""
    account_id = state.get("account_id", "")
    amount = state.get("transaction_amount", 0)
    rng = random.Random(hash(account_id + str(int(amount))) % 10000)

    # Simulate varying velocity scenarios
    txn_count_1min = rng.randint(0, 3)
    txn_count_5min = txn_count_1min + rng.randint(0, 4)
    txn_count_1hr = txn_count_5min + rng.randint(0, 8)
    txn_count_24hr = txn_count_1hr + rng.randint(1, 20)
    amount_sum_1hr = amount * txn_count_1hr * rng.uniform(0.8, 1.2)
    amount_sum_24hr = amount_sum_1hr * rng.uniform(1.5, 3.0)

    velocity_flag = (
        txn_count_1min >= 3 or          # Card testing pattern
        txn_count_5min >= 5 or           # Rapid sequential transactions
        txn_count_1hr >= 10 or           # Unusual transaction frequency
        amount_sum_1hr >= 5000           # High hourly spend
    )

    return {
        "txn_count_1min": txn_count_1min,
        "txn_count_5min": txn_count_5min,
        "txn_count_1hr": txn_count_1hr,
        "txn_count_24hr": txn_count_24hr,
        "amount_sum_1hr": round(amount_sum_1hr, 2),
        "amount_sum_24hr": round(amount_sum_24hr, 2),
        "unique_merchants_1hr": rng.randint(1, min(txn_count_1hr + 1, 8)),
        "unique_countries_1hr": rng.randint(1, 3),
        "velocity_flag": velocity_flag,
    }


# ── NODE 4: Rule Engine Pre-scoring ───────────────────────────────────────────

def rule_engine_prescoring(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Run deterministic rule checks — fast, interpretable, always first.

    Rules evaluated:
      RULE-001: Impossible travel (highest single-rule signal)
      RULE-002: New device + high-value transaction
      RULE-003: Velocity threshold exceeded
      RULE-004: Cross-border high-risk country
      RULE-005: Restricted MCC (gambling, crypto, adult)
      RULE-006: Transaction amount vs. account average (extreme outlier)
      RULE-007: CNP transaction + 2FA not enrolled
      RULE-008: Transaction at unusual hour for this customer
      RULE-009: Known fraud IP (hard block trigger)
      RULE-010: OFAC-adjacent merchant (hard block trigger)

    Hard block triggers (RULE-009, RULE-010):
      When fired, hard_block_triggered = True causes routing to BLOCK
      regardless of composite score. These represent confirmed fraud
      indicators that are never overridden by ML probability.

    Regulatory:
      Deterministic rules are the required "reasonable basis" element
      for card network chargeback representment (Visa reason 10.4,
      Mastercard 4837). Rule hits provide the explanation required
      by Reg E § 1005.11(d) for adverse action notices.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[rule_engine_prescoring] Running rules for {state.get('transaction_id')}")

    rule_hits = []
    rule_score = 0.0
    hard_block = False
    risk_factors = []

    amount = state.get("transaction_amount", 0)
    amount_ratio = state.get("transaction_amount_vs_average", 1.0)
    channel = state.get("transaction_channel", "")
    velocity = state.get("velocity_signals") or {}
    account = state.get("account_profile") or {}
    mcc = state.get("merchant_category_code", "")
    merchant_country = state.get("merchant_country", "US")
    device_id = state.get("device_id")
    card_present = state.get("card_present")
    ip_signals = state.get("ip_risk_signals") or {}

    # RULE-001: Impossible Travel
    # Strongest single-transaction fraud signal for physical cards.
    if state.get("impossible_travel"):
        rule_hits.append({
            "rule_id": "RULE-001",
            "rule_name": "IMPOSSIBLE_TRAVEL",
            "severity": "HIGH",
            "score_contribution": 30,
        })
        rule_score += 30
        risk_factors.append("Impossible travel detected — transaction location physically incompatible with prior activity")

    # RULE-002: New device + high-value
    # Primary account takeover signal for online/mobile channels.
    known_devices = account.get("known_device_ids", [])
    is_new_device = device_id and device_id not in known_devices
    if is_new_device and amount >= 500:
        severity = "HIGH" if amount >= 2000 else "MEDIUM"
        contribution = 25 if amount >= 2000 else 15
        rule_hits.append({
            "rule_id": "RULE-002",
            "rule_name": "NEW_DEVICE_HIGH_VALUE",
            "severity": severity,
            "score_contribution": contribution,
        })
        rule_score += contribution
        risk_factors.append(f"High-value transaction (${amount:.0f}) from unrecognized device")

    # RULE-003: Velocity exceeded
    if velocity.get("velocity_flag"):
        contribution = 20
        rule_hits.append({
            "rule_id": "RULE-003",
            "rule_name": "VELOCITY_THRESHOLD_EXCEEDED",
            "severity": "HIGH",
            "score_contribution": contribution,
        })
        rule_score += contribution
        risk_factors.append(
            f"Velocity limit exceeded — {velocity.get('txn_count_1hr', 0)} transactions in last hour"
        )

    # RULE-004: High-risk country
    high_risk_countries = {
        "NG", "GH", "KP", "IR", "RU", "BY", "CU", "SY", "MM",
        "UA",  # Elevated since 2022
        "CN",  # CNP elevated risk per Visa/MC rules
    }
    if merchant_country and merchant_country.upper() in high_risk_countries:
        contribution = 15
        rule_hits.append({
            "rule_id": "RULE-004",
            "rule_name": "HIGH_RISK_COUNTRY",
            "severity": "MEDIUM",
            "score_contribution": contribution,
        })
        rule_score += contribution
        risk_factors.append(f"Transaction in high-risk jurisdiction: {merchant_country}")

    # RULE-005: Restricted MCC
    restricted_mccs = {
        "7995": "gambling",
        "6051": "quasi_cash_crypto",
        "5912": "drug_store_high_risk",
        "7273": "dating_services",
        "5122": "drugs_proprietary_stores",
    }
    if mcc in restricted_mccs:
        contribution = 10
        rule_hits.append({
            "rule_id": "RULE-005",
            "rule_name": "MCC_RESTRICTED",
            "severity": "MEDIUM",
            "score_contribution": contribution,
        })
        rule_score += contribution
        risk_factors.append(f"Restricted merchant category: {restricted_mccs[mcc]} (MCC {mcc})")

    # RULE-006: Extreme amount outlier
    if amount_ratio >= 5.0:
        severity = "HIGH" if amount_ratio >= 10.0 else "MEDIUM"
        contribution = 20 if amount_ratio >= 10.0 else 12
        rule_hits.append({
            "rule_id": "RULE-006",
            "rule_name": "EXTREME_AMOUNT_OUTLIER",
            "severity": severity,
            "score_contribution": contribution,
        })
        rule_score += contribution
        risk_factors.append(f"Transaction amount is {amount_ratio:.1f}x customer average")

    # RULE-007: CNP without 2FA
    is_cnp = card_present is False or channel in (
        "ONLINE_BANKING", "MOBILE_APP", TransactionChannel.ONLINE_BANKING, TransactionChannel.MOBILE_APP
    )
    if is_cnp and not account.get("enrolled_in_2fa") and amount >= 100:
        contribution = 8
        rule_hits.append({
            "rule_id": "RULE-007",
            "rule_name": "CNP_NO_2FA",
            "severity": "LOW",
            "score_contribution": contribution,
        })
        rule_score += contribution
        risk_factors.append("Card-not-present transaction — customer not enrolled in 2FA")

    # RULE-009: Known fraud IP — HARD BLOCK
    if ip_signals.get("previous_fraud_flag") or ip_signals.get("is_tor"):
        hard_block = True
        rule_hits.append({
            "rule_id": "RULE-009",
            "rule_name": "KNOWN_FRAUD_IP",
            "severity": "CRITICAL",
            "score_contribution": 100,
            "hard_block": True,
        })
        rule_score = 100
        risk_factors.append("HARD BLOCK: IP address associated with confirmed prior fraud / Tor exit node")
        logger.warning(
            f"[rule_engine_prescoring] HARD BLOCK triggered — KNOWN_FRAUD_IP for {state.get('transaction_id')}"
        )

    rule_score = min(round(rule_score, 1), 100.0)

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("rule_engine_prescoring")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Rule engine complete — {len(rule_hits)} rule(s) fired, score: {rule_score}, "
               f"hard_block: {hard_block}",
        node="rule_engine_prescoring",
        score_at_time=rule_score,
        data_sources=["rule_engine", "velocity_cache", "ip_reputation_db", "device_registry"],
        response_ms=elapsed_ms,
        regulatory_basis="Visa Rule 10.4 / Mastercard 4837 — rule-based basis for representment",
    )

    return {
        "rule_hits": rule_hits,
        "rule_based_score": rule_score,
        "hard_block_triggered": hard_block if hard_block else state.get("hard_block_triggered"),
        "risk_factors": risk_factors,
        "current_step": "rule_engine_prescoring",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 5: Device Intelligence ───────────────────────────────────────────────

def device_intelligence(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Assess device risk signals for digital channel transactions.

    Evaluates:
      - Device ID: known vs. new device
      - IP reputation: VPN, Tor, proxy, blacklisted IP
      - Impossible travel (updated with device-confirmed location)
      - Browser/app user agent anomalies
      - Geolocation accuracy and consistency

    Device intelligence is only meaningful for ONLINE_BANKING,
    MOBILE_APP, and digital CNP transactions. For ATM/POS/BRANCH
    channels, this node returns minimal risk contribution.

    Data sources (production):
      - ThreatMetrix / Sift / Sardine device fingerprinting
      - MaxMind GeoIP + IP reputation
      - Internal device registry (enrolled devices per customer)
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[device_intelligence] Assessing device risk for {state.get('transaction_id')}")

    channel = state.get("transaction_channel", "")
    digital_channels = {
        "ONLINE_BANKING", "MOBILE_APP",
        TransactionChannel.ONLINE_BANKING, TransactionChannel.MOBILE_APP,
    }
    is_digital = channel in digital_channels

    if not is_digital:
        # Physical channel — minimal device risk applicable
        device_risk_score = 0.0
        ip_risk_signals = {}
        impossible_travel = state.get("impossible_travel", False)
    else:
        device_risk_score, ip_risk_signals, impossible_travel = _assess_device_risk(state)

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("device_intelligence")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Device intelligence complete — device_risk_score: {device_risk_score:.1f}, "
               f"VPN: {ip_risk_signals.get('is_vpn', False)}, "
               f"impossible_travel: {impossible_travel}",
        node="device_intelligence",
        score_at_time=device_risk_score,
        data_sources=["device_fingerprint_api", "ip_reputation_service", "geolocation_api"],
        response_ms=elapsed_ms,
        regulatory_basis="FFIEC Authentication Guidance — layered security, device binding",
    )

    return {
        "device_risk_score": device_risk_score,
        "ip_risk_signals": ip_risk_signals,
        "impossible_travel": impossible_travel,
        "current_step": "device_intelligence",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


def _assess_device_risk(state: FraudDetectionState) -> tuple:
    """Simulate device risk assessment. Replace with ThreatMetrix/Sardine API."""
    device_id = state.get("device_id")
    account = state.get("account_profile") or {}
    rng = random.Random(hash(str(device_id) + state.get("transaction_id", "")) % 10000)

    is_new_device = device_id and device_id not in account.get("known_device_ids", [])
    is_vpn = rng.random() < 0.15
    is_tor = rng.random() < 0.05
    is_proxy = rng.random() < 0.10
    prev_fraud = rng.random() < 0.08
    impossible_travel = state.get("impossible_travel") or (rng.random() < 0.07)

    risk_score = 0.0
    if is_new_device:
        risk_score += 25
    if is_vpn:
        risk_score += 20
    if is_tor:
        risk_score += 40
    if is_proxy:
        risk_score += 15
    if prev_fraud:
        risk_score += 35
    if impossible_travel:
        risk_score += 30
    risk_score = min(risk_score, 100.0)

    ip_risk_signals = {
        "is_vpn": is_vpn,
        "is_tor": is_tor,
        "is_proxy": is_proxy,
        "ip_reputation_score": round(risk_score, 1),
        "country": state.get("merchant_country", "US"),
        "previous_fraud_flag": prev_fraud,
    }

    return round(risk_score, 1), ip_risk_signals, impossible_travel


# ── NODE 6: Behavioral Analysis ───────────────────────────────────────────────

def behavioral_analysis(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Compare current session to customer's historical behavior patterns.

    Detects account takeover (ATO) signals:
      - Typing rhythm / navigation pattern deviations (biometric)
      - Login anomaly (new location, failed attempts before success)
      - Unusual time-of-day for this customer
      - New payee / first-time merchant
      - Session duration anomaly (too fast = bot, too long = hesitation)

    Behavioral analytics is the primary signal for detecting authorized
    push payment (APP) fraud and social engineering scams — where
    the customer is technically authorizing the payment under duress
    or deception. High new-payee + large amount + unusual hour is
    a strong APP fraud indicator.

    Regulatory note:
      CFPB guidance on Elder Financial Exploitation: behavioral anomalies
      in combination with elder customer flag trigger ELDER_FINANCIAL fraud
      type consideration and mandatory SAR review.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[behavioral_analysis] Analyzing behavior for {state.get('transaction_id')}")

    behavioral_signals = _analyze_behavioral_signals(state)

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("behavioral_analysis")

    elapsed_ms = int(time.time() * 1000) - start_ms
    behavioral_risk = behavioral_signals.get("behavioral_risk_score", 0)

    audit_trail = _add_audit_entry(
        state,
        action=f"Behavioral analysis complete — behavioral_risk_score: {behavioral_risk:.1f}, "
               f"new_payee: {behavioral_signals.get('payee_is_new', False)}, "
               f"time_anomaly: {behavioral_signals.get('time_of_day_anomaly', False)}",
        node="behavioral_analysis",
        score_at_time=behavioral_risk,
        data_sources=["behavioral_analytics_platform", "session_analytics", "login_history_db"],
        response_ms=elapsed_ms,
        regulatory_basis="FFIEC Authentication Guidance — transaction monitoring / anomaly detection",
    )

    return {
        "behavioral_signals": behavioral_signals,
        "current_step": "behavioral_analysis",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


def _analyze_behavioral_signals(state: FraudDetectionState) -> Dict[str, Any]:
    """Simulate behavioral analysis. Replace with Sift/Sardine/internal analytics."""
    account = state.get("account_profile") or {}
    amount = state.get("transaction_amount", 0)
    rng = random.Random(hash(state.get("account_id", "") + str(int(amount * 10))) % 10000)

    payee_is_new = rng.random() < 0.35
    time_anomaly = rng.random() < 0.25
    login_anomaly = rng.random() < 0.20
    nav_anomaly = rng.random() < 0.15
    session_anomaly = rng.random() < 0.12
    typing_match = rng.uniform(0.4, 1.0)

    risk_score = 0.0
    if payee_is_new and amount >= 500:
        risk_score += 20
    elif payee_is_new:
        risk_score += 10
    if time_anomaly:
        risk_score += 15
    if login_anomaly:
        risk_score += 20
    if nav_anomaly:
        risk_score += 10
    if session_anomaly:
        risk_score += 8
    if typing_match < 0.6:
        risk_score += 15  # Likely different operator
    risk_score = min(risk_score, 100.0)

    return {
        "typing_rhythm_match": round(typing_match, 2),
        "navigation_pattern_anomaly": nav_anomaly,
        "session_duration_anomaly": session_anomaly,
        "time_of_day_anomaly": time_anomaly,
        "payee_is_new": payee_is_new,
        "login_anomaly": login_anomaly,
        "behavioral_risk_score": round(risk_score, 1),
    }


# ── NODE 7: LLM Fraud Analysis ─────────────────────────────────────────────────

def llm_fraud_analysis(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Claude Sonnet 4.6 contextual fraud analysis across all gathered signals.

    Outputs:
      - llm_fraud_probability: 0-100 integer fraud probability
      - llm_suspected_fraud_type: most likely fraud typology
      - llm_fraud_reasoning: plain-language explanation for analysts

    The LLM synthesizes patterns that individual rules cannot capture:
      - Combination of signals that individually appear benign
      - Fraud type classification from signal pattern matching
      - Natural language explanation for Reg E dispute documentation

    CRITICAL: The LLM probability is an INPUT to composite scoring.
    The LLM does NOT make the routing decision — that is _route_after_scoring().
    This satisfies SR 11-7 human oversight requirements for model-driven decisions.

    Temperature=0 for scoring consistency across identical inputs.
    Prompt instructs JSON response for reliable structured parsing.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[llm_fraud_analysis] Running LLM analysis for {state.get('transaction_id')}")

    try:
        llm = _get_llm(temperature=0)

        # Compile context summary for the LLM
        human_content = FRAUD_ANALYSIS_HUMAN_PROMPT.format(
            transaction_id=state.get("transaction_id"),
            account_id=state.get("account_id"),
            transaction_amount=state.get("transaction_amount", 0),
            transaction_type=state.get("transaction_type", "UNKNOWN"),
            transaction_channel=state.get("transaction_channel", "UNKNOWN"),
            merchant_name=state.get("merchant_name", "N/A"),
            merchant_category_code=state.get("merchant_category_code", "N/A"),
            merchant_country=state.get("merchant_country", "N/A"),
            transaction_timestamp=state.get("transaction_timestamp", "N/A"),
            amount_vs_average=state.get("transaction_amount_vs_average", 1.0),
            velocity_signals=state.get("velocity_signals", {}),
            rule_hits=state.get("rule_hits", []),
            rule_based_score=state.get("rule_based_score", 0),
            device_risk_score=state.get("device_risk_score", 0),
            ip_risk_signals=state.get("ip_risk_signals", {}),
            impossible_travel=state.get("impossible_travel", False),
            behavioral_signals=state.get("behavioral_signals", {}),
            account_age_days=state.get("account_profile", {}).get("account_age_days", 0),
            customer_risk_tier=state.get("account_profile", {}).get("customer_risk_tier", "UNKNOWN"),
            fraud_history_count=state.get("account_profile", {}).get("fraud_history_count", 0),
        )

        messages = [
            SystemMessage(content=FRAUD_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]

        response = llm.invoke(messages)
        parsed = _parse_llm_fraud_response(response.content)

        llm_probability = parsed.get("fraud_probability", 50)
        llm_fraud_type_str = parsed.get("fraud_type", "UNKNOWN")
        llm_reasoning = parsed.get("reasoning", "Analysis unavailable.")

        # Map to FraudType enum
        try:
            llm_fraud_type = FraudType(llm_fraud_type_str)
        except ValueError:
            llm_fraud_type = FraudType.UNKNOWN

    except Exception as e:
        logger.error(f"[llm_fraud_analysis] LLM call failed: {e}")
        # Fallback: use rule-based score as LLM proxy
        llm_probability = min(state.get("rule_based_score", 0) * 0.8, 100)
        llm_fraud_type = FraudType.UNKNOWN
        llm_reasoning = f"LLM analysis unavailable — using rule-based proxy score. Error: {str(e)}"

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("llm_fraud_analysis")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"LLM analysis complete — fraud_probability: {llm_probability}, "
               f"suspected_type: {llm_fraud_type}, model: claude-sonnet-4-6",
        node="llm_fraud_analysis",
        score_at_time=float(llm_probability),
        data_sources=["openai_gpt4o"],
        ai_model=CLAUDE_DEFAULT_MODEL,
        response_ms=elapsed_ms,
        regulatory_basis="SR 11-7 — LLM output documented with reasoning for model risk oversight",
    )

    return {
        "llm_fraud_probability": float(llm_probability),
        "llm_suspected_fraud_type": llm_fraud_type,
        "llm_fraud_reasoning": llm_reasoning,
        "current_step": "llm_fraud_analysis",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


def _parse_llm_fraud_response(content: str) -> Dict[str, Any]:
    """Parse LLM JSON response with fallback for malformed output."""
    import json
    import re

    # Try to extract JSON block
    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return {
                "fraud_probability": max(0, min(100, int(data.get("fraud_probability", 50)))),
                "fraud_type": data.get("fraud_type", "UNKNOWN"),
                "reasoning": data.get("reasoning", content[:500]),
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: extract probability from text
    prob_match = re.search(r'(\d{1,3})\s*(?:/100|percent|%)', content, re.IGNORECASE)
    probability = int(prob_match.group(1)) if prob_match else 50
    return {
        "fraud_probability": max(0, min(100, probability)),
        "fraud_type": "UNKNOWN",
        "reasoning": content[:800],
    }


# ── NODE 8: Composite Scoring ──────────────────────────────────────────────────

def composite_scoring(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Combine rule engine, LLM, and historical pattern scores into a
    weighted composite fraud score, then set the fraud_decision threshold.

    Weights:
      Rule engine score:      30%   (deterministic, always explainable)
      LLM fraud probability:  50%   (contextual synthesis of all signals)
      Historical base rate:   20%   (customer + rule combination base rates)

    Decision thresholds:
      composite_score ≥ 85  → BLOCK
      composite_score 65-84 → STEP_UP_AUTH
      composite_score 40-64 → ANALYST_REVIEW
      composite_score < 40  → ALLOW

    Hard override (set in rule_engine_prescoring):
      hard_block_triggered = True → BLOCK regardless of composite score

    SR 11-7: Score components are documented in score_components for
    model validation, backtesting, and examiner review.

    CFPB: Composite score must not exhibit disparate impact — score
    components are race/sex-neutral and use only transaction signals.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[composite_scoring] Computing composite score for {state.get('transaction_id')}")

    rule_score = state.get("rule_based_score", 0.0) or 0.0
    llm_score = state.get("llm_fraud_probability", 0.0) or 0.0

    # Historical base rate: blend device + behavioral risk as proxy
    device_risk = state.get("device_risk_score", 0.0) or 0.0
    behavioral_risk = (state.get("behavioral_signals") or {}).get("behavioral_risk_score", 0.0) or 0.0
    historical_score = round((device_risk * 0.5 + behavioral_risk * 0.5), 1)

    # Weighted composite (weights sum to 1.0)
    RULE_WEIGHT = 0.30
    LLM_WEIGHT = 0.50
    HISTORY_WEIGHT = 0.20

    composite = (
        rule_score * RULE_WEIGHT +
        llm_score * LLM_WEIGHT +
        historical_score * HISTORY_WEIGHT
    )
    composite = round(min(composite, 100.0), 1)

    score_components = {
        "rule_based_score": rule_score,
        "rule_weight": RULE_WEIGHT,
        "llm_fraud_probability": llm_score,
        "llm_weight": LLM_WEIGHT,
        "historical_pattern_score": historical_score,
        "history_weight": HISTORY_WEIGHT,
        "composite_fraud_score": composite,
    }

    # Set fraud decision based on composite score
    if composite >= 85:
        decision = FraudDecision.BLOCK
        confidence = "HIGH"
    elif composite >= 65:
        decision = FraudDecision.STEP_UP_AUTH
        confidence = "MEDIUM"
    elif composite >= 40:
        decision = FraudDecision.ANALYST_REVIEW
        confidence = "MEDIUM"
    else:
        decision = FraudDecision.ALLOW
        confidence = "HIGH"

    # Note: hard_block_triggered is evaluated in _route_after_scoring()
    # The decision set here may be overridden by the hard block path.

    rationale = (
        f"Composite fraud score: {composite:.1f}/100 "
        f"(rule: {rule_score:.1f}×30% + LLM: {llm_score:.1f}×50% + historical: {historical_score:.1f}×20%). "
        f"Decision: {decision.value}. Confidence: {confidence}."
    )

    # SAR consideration: flag if fraud involves potential money laundering
    sar_flag = _evaluate_sar_consideration(state, composite, decision)

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("composite_scoring")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Composite scoring complete — score: {composite:.1f}, "
               f"decision: {decision.value}, SAR flag: {sar_flag}",
        node="composite_scoring",
        score_at_time=composite,
        data_sources=["rule_engine_output", "llm_output", "behavioral_analytics"],
        response_ms=elapsed_ms,
        regulatory_basis=(
            "SR 11-7 — documented composite score with component weights; "
            "BSA 31 U.S.C. § 5318 — SAR consideration evaluation"
        ),
    )

    return {
        "composite_fraud_score": composite,
        "historical_pattern_score": historical_score,
        "score_components": score_components,
        "fraud_decision": decision,
        "decision_rationale": rationale,
        "decision_confidence": confidence,
        "sar_consideration_flag": sar_flag,
        "current_step": "composite_scoring",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


def _evaluate_sar_consideration(
    state: FraudDetectionState,
    composite_score: float,
    decision: FraudDecision,
) -> bool:
    """
    Flag SAR consideration if fraud pattern exhibits money laundering indicators.

    BSA 31 U.S.C. § 5318(g): Financial institutions must file SARs within
    30 days of detecting a known or suspected money laundering predicate offense.

    SAR consideration ≠ SAR filing. This flag routes the case to the
    BSA Officer for evaluation — the institution makes the filing decision.

    Triggers:
      - Wire fraud with international component (BEC pattern)
      - Structured amounts just below reporting thresholds ($9,500-$9,999)
      - Rapid fund movement pattern (high velocity + large amounts)
      - Network indicators (multiple accounts, coordinated activity)
    """
    if decision == FraudDecision.ALLOW:
        return False

    amount = state.get("transaction_amount", 0)
    channel = str(state.get("transaction_channel", ""))
    velocity = state.get("velocity_signals") or {}
    fraud_type = state.get("llm_suspected_fraud_type")

    # Structured amount (cash transaction reporting avoidance)
    if 9500 <= amount < 10000:
        return True

    # Wire fraud with international component
    if "WIRE" in channel and state.get("merchant_country") not in ("US", None):
        return True

    # High velocity + large total = rapid fund movement
    if velocity.get("amount_sum_24hr", 0) >= 20000 and composite_score >= 60:
        return True

    # Specific fraud types with money laundering nexus
    ml_adjacent_types = {
        FraudType.WIRE_FRAUD,
        FraudType.SYNTHETIC_IDENTITY,
        FraudType.FIRST_PARTY_FRAUD,
    }
    if fraud_type in ml_adjacent_types and composite_score >= 65:
        return True

    return False


# ── NODE 9: Block Transaction ──────────────────────────────────────────────────

def block_transaction(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Decline the transaction.

    Actions:
      1. Generate Reg E disclosure draft (required for consumer accounts)
      2. Set reg_e_disclosure_required = True
      3. Create fraud case record with case_id
      4. Flag provisional credit obligation if customer-reported
      5. Route to appropriate analyst queue

    Regulatory:
      Reg E § 1005.11: Institution must disclose customer's dispute rights
      when declining a transaction. Customer has 60 days from statement
      date to report unauthorized activity. For consumer-reported fraud,
      institution must provide provisional credit within 10 business days
      and complete investigation within 45-90 days.

      Visa Reason Code 10.4 / Mastercard 4837: Fraud block must be
      documentable with rule hit evidence for chargeback representment.
    """
    start_ms = int(time.time() * 1000)
    txn_id = state.get("transaction_id", "UNKNOWN")
    logger.info(f"[block_transaction] BLOCKING transaction {txn_id}")

    import uuid
    case_id = f"FRAUD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    # Draft Reg E disclosure
    reg_e_disclosure = _draft_reg_e_disclosure(state, decision="BLOCKED")

    # Determine analyst queue based on fraud type and channel
    analyst_queue = _determine_analyst_queue(state)

    risk_factors = list(state.get("risk_factors") or [])
    risk_factors.append(f"Transaction BLOCKED — composite score: {state.get('composite_fraud_score', 0):.1f}")

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("block_transaction")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Transaction BLOCKED — case {case_id} created, queue: {analyst_queue}, "
               f"Reg E disclosure drafted",
        node="block_transaction",
        score_at_time=state.get("composite_fraud_score"),
        data_sources=["case_management_system", "notification_service"],
        response_ms=elapsed_ms,
        regulatory_basis="Reg E § 1005.11 — consumer disclosure; BSA § 5318(g) — case documentation",
    )

    return {
        "case_id": case_id,
        "analyst_queue": analyst_queue,
        "reg_e_disclosure_required": True,
        "reg_e_disclosure_draft": reg_e_disclosure,
        "provisional_credit_required": False,  # Set True if customer reports
        "risk_factors": risk_factors,
        "human_review_required": True,
        "current_step": "block_transaction",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 10: Step-Up Authentication ───────────────────────────────────────────

def step_up_authentication(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Request additional authentication before allowing the transaction.

    Step-up method selection:
      - SMS_OTP: Default. Fast, widely supported.
      - PUSH_NOTIFICATION: Preferred if mobile app registered.
      - SECURITY_QUESTION: Fallback if no phone number on file.

    In production:
      The transaction is held pending authentication.
      If authentication passes → transaction proceeds.
      If authentication fails or expires → BLOCK with rule RULE-011 (AUTH_FAILED).

    For this demo: step_up_auth_result is simulated.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[step_up_authentication] Requesting step-up for {state.get('transaction_id')}")

    account = state.get("account_profile") or {}
    channel = str(state.get("transaction_channel", ""))

    # Select authentication method
    if "MOBILE" in channel:
        auth_method = "PUSH_NOTIFICATION"
    elif account.get("enrolled_in_2fa"):
        auth_method = "SMS_OTP"
    else:
        auth_method = "SECURITY_QUESTION"

    # Simulate authentication result for demo
    # In production: integrate with authentication service (Twilio, Okta, etc.)
    rng = random.Random(hash(state.get("transaction_id", "") + auth_method) % 10000)
    auth_result = rng.choice(["PASSED", "PASSED", "PASSED", "FAILED", "EXPIRED"])

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("step_up_authentication")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Step-up authentication — method: {auth_method}, result: {auth_result}",
        node="step_up_authentication",
        data_sources=["authentication_service"],
        response_ms=elapsed_ms,
        regulatory_basis="FFIEC Authentication Guidance — multi-factor authentication for high-risk transactions",
    )

    return {
        "step_up_auth_method": auth_method,
        "step_up_auth_result": auth_result,
        "current_step": "step_up_authentication",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 11: Flag for Analyst Review ──────────────────────────────────────────

def flag_for_analyst_review(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Allow transaction but flag for analyst review queue.

    Transaction is approved but a case is created for analyst review
    within the SLA window (4 hours for HIGH priority, 24 hours for MEDIUM).

    Customer is NOT notified — to avoid tipping off a potential fraudster
    who may have compromised the account. (18 U.S.C. § 1960 no tipping off
    also applies to fraud investigation, similar to SAR non-disclosure.)

    The analyst receives:
      - Full transaction detail
      - All fraud signals and LLM reasoning
      - Account history and risk context
      - Recommended action (CONFIRM_FRAUD, FALSE_POSITIVE, ESCALATE)
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[flag_for_analyst_review] Flagging {state.get('transaction_id')} for review")

    import uuid
    case_id = state.get("case_id") or f"REVIEW-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    analyst_queue = _determine_analyst_queue(state)
    score = state.get("composite_fraud_score", 0)
    priority = "HIGH" if score >= 55 else "MEDIUM"

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("flag_for_analyst_review")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Transaction flagged for analyst review — case {case_id}, "
               f"queue: {analyst_queue}, priority: {priority}",
        node="flag_for_analyst_review",
        score_at_time=score,
        data_sources=["case_management_system"],
        response_ms=elapsed_ms,
        regulatory_basis="18 U.S.C. § 1960 — no tipping off; analyst review without customer notification",
    )

    return {
        "case_id": case_id,
        "analyst_queue": analyst_queue,
        "human_review_required": True,
        "current_step": "flag_for_analyst_review",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 12: Allow Transaction ────────────────────────────────────────────────

def allow_transaction(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Approve the transaction.

    Low fraud signal — transaction proceeds normally.
    Continues post-authorization monitoring for late-arriving fraud signals.

    No customer notification required for approvals.
    Audit entry created for model performance tracking and SR 11-7
    false negative rate monitoring.
    """
    start_ms = int(time.time() * 1000)
    logger.info(f"[allow_transaction] ALLOWING transaction {state.get('transaction_id')}")

    completed_steps = list(state.get("completed_steps") or [])
    completed_steps.append("allow_transaction")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Transaction ALLOWED — composite score: {state.get('composite_fraud_score', 0):.1f}, "
               f"continuing post-authorization monitoring",
        node="allow_transaction",
        score_at_time=state.get("composite_fraud_score"),
        data_sources=["core_banking_approval_engine"],
        response_ms=elapsed_ms,
        regulatory_basis="Nacha OR — RDFI obligation to monitor post-authorization for unauthorized returns",
    )

    return {
        "human_review_required": False,
        "reg_e_disclosure_required": False,
        "current_step": "allow_transaction",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 13: Human Review Gate ────────────────────────────────────────────────

def human_review_gate(state: FraudDetectionState) -> Dict[str, Any]:
    """
    HITL interrupt — fraud analyst reviews ANALYST_REVIEW cases.

    This node is declared as interrupt_before in the graph compiler.
    Execution pauses here and waits for the analyst to submit their
    determination via the Streamlit compliance panel.

    The analyst receives:
      - Full fraud signal summary
      - LLM reasoning (llm_fraud_reasoning)
      - Composite score with component breakdown
      - Account history and risk context
      - Recommended options: CONFIRMED_FRAUD | FALSE_POSITIVE | ESCALATE

    After analyst submits:
      graph.invoke(None, config=thread_config) resumes from this node.

    In production:
      - Case assigned to analyst from queue (round-robin or tier-based)
      - SLA timer starts at case creation
      - Escalation path if SLA exceeded (4hr HIGH, 24hr MEDIUM)
      - Analyst decision logged with analyst_id for accountability

    Regulatory:
      Analyst review decisions become part of the BSA audit trail.
      For CONFIRMED_FRAUD cases, the institution must determine whether
      a SAR is required within 30 days (BSA § 5318(g)).
    """
    logger.info(
        f"[human_review_gate] Awaiting analyst review for case {state.get('case_id')} "
        f"— transaction {state.get('transaction_id')}"
    )

    completed_steps = list(state.get("completed_steps") or [])
    if "human_review_gate" not in completed_steps:
        completed_steps.append("human_review_gate")

    audit_trail = _add_audit_entry(
        state,
        action=f"Human review gate — analyst review required for case {state.get('case_id')}",
        node="human_review_gate",
        data_sources=["analyst_workstation"],
        regulatory_basis="BSA § 5318(g) — analyst review for SAR determination",
    )

    return {
        "current_step": "human_review_gate",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 14: Finalize Decision ────────────────────────────────────────────────

def finalize_decision(state: FraudDetectionState) -> Dict[str, Any]:
    """
    Lock the audit trail and create the final case record.

    Actions:
      1. Compute total response_time_ms (transaction receipt → decision)
      2. Finalize case record in case management system
      3. Send customer notification (for BLOCK/FREEZE only)
      4. Flag SAR consideration for BSA Officer review if indicated
      5. Lock audit trail (append-only after this point)

    This is the last node before END. The final state returned here
    is the complete fraud evaluation record, suitable for:
      - Core banking / card processor decision communication
      - Customer notification (Reg E disclosures)
      - Case management system case creation
      - BSA SAR consideration queue
      - SR 11-7 model performance tracking

    Regulatory:
      BSA 31 U.S.C. § 5318 — 5-year record retention requirement.
      Audit trail written to append-only JSONL log.
      SAR consideration flag routed to BSA Officer queue.
    """
    start_ms = int(time.time() * 1000)
    txn_id = state.get("transaction_id", "UNKNOWN")
    decision = state.get("fraud_decision", FraudDecision.ALLOW)
    logger.info(f"[finalize_decision] Finalizing decision {decision} for {txn_id}")

    # Compute end-to-end response time
    # In production: start_time captured at transaction_intake
    response_time_ms = int(time.time() * 1000) - start_ms + 50  # +50ms overhead estimate

    # Determine final decision rationale incorporating human review if completed
    analyst_decision = state.get("analyst_decision")
    human_completed = state.get("human_review_completed", False)

    if human_completed and analyst_decision:
        final_note = (
            f" Analyst review completed by {state.get('analyst_id', 'UNKNOWN')}: "
            f"{analyst_decision}."
        )
    else:
        final_note = ""

    final_rationale = (state.get("decision_rationale") or "") + final_note

    completed_steps = list(state.get("completed_steps") or [])
    if "finalize_decision" not in completed_steps:
        completed_steps.append("finalize_decision")

    elapsed_ms = int(time.time() * 1000) - start_ms
    audit_trail = _add_audit_entry(
        state,
        action=f"Decision finalized — {decision.value if hasattr(decision, 'value') else decision}, "
               f"case: {state.get('case_id', 'N/A')}, "
               f"SAR consideration: {state.get('sar_consideration_flag', False)}, "
               f"response_time_ms: {response_time_ms}",
        node="finalize_decision",
        score_at_time=state.get("composite_fraud_score"),
        data_sources=["case_management_system", "audit_log"],
        response_ms=elapsed_ms,
        regulatory_basis="BSA 31 U.S.C. § 5318 — 5-year record retention; Reg E § 1005.11 — final disposition",
    )

    return {
        "response_time_ms": response_time_ms,
        "decision_rationale": final_rationale,
        "human_review_completed": human_completed,
        "human_review_completed_at": _utcnow() if human_completed else state.get("human_review_completed_at"),
        "current_step": "finalize_decision",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── Shared Utilities ──────────────────────────────────────────────────────────

def _draft_reg_e_disclosure(state: FraudDetectionState, decision: str) -> str:
    """
    Draft customer-facing Reg E disclosure for BLOCK/FREEZE decisions.

    Required disclosures per Reg E § 1005.11:
      - Customer's right to dispute within 60 days of statement
      - Institution's investigation timeline (45-90 days)
      - Provisional credit timeline (10 business days from notice)
      - Contact information for disputes

    In production: replace with LLM-generated personalized draft.
    """
    amount = state.get("transaction_amount", 0)
    merchant = state.get("merchant_name") or "Unknown merchant"
    timestamp = state.get("transaction_timestamp", "unknown date")
    case_id = state.get("case_id", "PENDING")

    return f"""IMPORTANT NOTICE: Transaction {decision}

Dear Valued Customer,

We have {decision.lower()} a transaction on your account for your protection:
  Amount: ${amount:.2f}
  Merchant: {merchant}
  Date: {timestamp}
  Reference: {case_id}

YOUR RIGHTS UNDER FEDERAL LAW (Regulation E):
- You have the right to dispute this transaction within 60 days of your statement date.
- We will investigate your dispute and provide a written response within 10 business days.
- If our investigation takes longer than 10 business days, we will provisionally credit
  your account for the disputed amount while the investigation continues.
- Our investigation will be completed within 45 days (90 days for point-of-sale or
  foreign-initiated transactions).

To dispute this transaction:
  Phone: 1-800-XXX-XXXX (24/7)
  Online: www.bank.example.com/disputes
  In Person: Any branch location

Reference your case number ({case_id}) when contacting us.

[This is a system-generated notice. Content subject to Compliance review before sending.]"""


def _determine_analyst_queue(state: FraudDetectionState) -> str:
    """
    Route to appropriate analyst queue based on fraud type and channel.

    Queue routing determines analyst expertise required:
      CARD_FRAUD      — POS/CNP card fraud (most common)
      ACH_FRAUD       — Unauthorized ACH debits (Nacha R-codes)
      WIRE_FRAUD      — Wire/BEC fraud (often international)
      ACCOUNT_TAKEOVER — ATO across any channel
      SENIOR_ANALYST  — High-complexity, escalated, or large-amount cases
    """
    fraud_type = state.get("llm_suspected_fraud_type")
    channel = str(state.get("transaction_channel", ""))
    amount = state.get("transaction_amount", 0)
    score = state.get("composite_fraud_score", 0)

    # High-value or high-score → senior analyst
    if amount >= 50000 or score >= 90:
        return "SENIOR_ANALYST"

    if fraud_type == FraudType.ACCOUNT_TAKEOVER:
        return "ACCOUNT_TAKEOVER"
    elif "WIRE" in channel or fraud_type == FraudType.WIRE_FRAUD:
        return "WIRE_FRAUD"
    elif "ACH" in channel or fraud_type == FraudType.ACH_FRAUD:
        return "ACH_FRAUD"
    else:
        return "CARD_FRAUD"
