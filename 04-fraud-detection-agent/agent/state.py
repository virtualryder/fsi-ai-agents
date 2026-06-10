# agent/state.py
# ============================================================
# FraudDetectionState — Complete state for a real-time fraud evaluation
#
# Regulatory context:
#   - Reg E (12 CFR Part 1005 / EFTA): Consumer liability caps, unauthorized
#     transaction dispute rights, 10-business-day provisional credit obligation
#   - Nacha Operating Rules: ACH unauthorized return codes (R05, R07, R10),
#     ODFI/RDFI fraud obligations, Same Day ACH risk controls
#   - Visa/Mastercard Zero Liability: Cardholder fraud liability limits,
#     chargeback reason codes (10.4 fraud, 11.1 card recovery bulletin)
#   - BSA 31 U.S.C. § 5318: Fraud as SAR predicate offense — if fraud
#     involves money laundering indicators, must file SAR within 30 days
#   - CFPB: Fair and transparent dispute resolution, no disparate impact
#     in fraud decline decisions
#   - GLBA: Security of financial data accessed during fraud investigation
#
# Architecture notes:
#   This state supports two execution paths:
#   1. REAL-TIME PATH (sub-200ms): rule_engine → composite_score → routing_decision
#      Runs synchronously on every transaction before approval/decline
#   2. ASYNC ENRICHMENT PATH: device_intelligence → behavioral_analysis →
#      llm_fraud_analysis → analyst_review
#      Runs asynchronously after real-time decision for deeper investigation
#
# Human-in-the-loop:
#   ANALYST_REVIEW decisions pause at human_review_gate for fraud analyst
#   to make final determination. BLOCK decisions never reversed automatically.
# ============================================================

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class TransactionChannel(str, Enum):
    """
    The channel through which the transaction was initiated.
    Channel is a primary risk signal — online/mobile have different
    fraud profiles than in-branch or POS.
    """
    ONLINE_BANKING = "ONLINE_BANKING"
    MOBILE_APP = "MOBILE_APP"
    ATM = "ATM"
    POS_CHIP = "POS_CHIP"           # EMV chip — lower fraud risk
    POS_SWIPE = "POS_SWIPE"         # Magnetic stripe — higher fraud risk
    POS_CONTACTLESS = "POS_CONTACTLESS"
    ACH_CREDIT = "ACH_CREDIT"
    ACH_DEBIT = "ACH_DEBIT"
    WIRE = "WIRE"
    ZELLE = "ZELLE"                  # P2P — high fraud velocity
    CHECK = "CHECK"
    TELEPHONE = "TELEPHONE"
    BRANCH = "BRANCH"


class FraudDecision(str, Enum):
    """
    The real-time fraud disposition for the transaction.

    ALLOW:          Low fraud signal. Approve transaction. Continue monitoring.
    STEP_UP_AUTH:   Moderate fraud signal. Challenge customer with additional
                    authentication (SMS OTP, push notification, security question)
                    before allowing. If auth fails → BLOCK.
    ANALYST_REVIEW: Elevated fraud signal. Allow transaction but flag for
                    manual analyst review within SLA window. Customer not notified
                    (to avoid tipping off potential fraudster).
    BLOCK:          High confidence of fraud. Decline transaction. Customer
                    notified. Case created. Reg E dispute rights disclosed.
    FREEZE_ACCOUNT: Extreme fraud signal (account takeover, mass credential
                    stuffing). Freeze all transactions. Emergency customer contact.
                    Reg E provisional credit may be required.
    """
    ALLOW = "ALLOW"
    STEP_UP_AUTH = "STEP_UP_AUTH"
    ANALYST_REVIEW = "ANALYST_REVIEW"
    BLOCK = "BLOCK"
    FREEZE_ACCOUNT = "FREEZE_ACCOUNT"


class FraudType(str, Enum):
    """
    Detected or suspected fraud typology.
    Drives alert category, case routing, and SAR consideration.
    """
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"       # Credential compromise
    CARD_NOT_PRESENT = "CARD_NOT_PRESENT"        # CNP fraud (e-commerce)
    CARD_PRESENT = "CARD_PRESENT"                # Counterfeit/skimming
    SYNTHETIC_IDENTITY = "SYNTHETIC_IDENTITY"    # Fabricated identity
    FIRST_PARTY_FRAUD = "FIRST_PARTY_FRAUD"      # Customer committing fraud
    AUTHORIZED_PUSH = "AUTHORIZED_PUSH"          # APP fraud (scam)
    ELDER_FINANCIAL = "ELDER_FINANCIAL"          # Exploitation of elderly
    NEW_ACCOUNT_FRAUD = "NEW_ACCOUNT_FRAUD"      # Bust-out / credit fraud
    CHECK_FRAUD = "CHECK_FRAUD"                  # Altered/counterfeit checks
    ACH_FRAUD = "ACH_FRAUD"                      # Unauthorized ACH debits
    WIRE_FRAUD = "WIRE_FRAUD"                    # Wire fraud / BEC
    PHISHING = "PHISHING"                        # Credential phishing
    UNKNOWN = "UNKNOWN"


class FraudDetectionState(TypedDict, total=False):
    """
    Complete state for a single fraud detection evaluation.

    Flows through the LangGraph DAG. Fields populated incrementally
    as the evaluation progresses — both in real-time and async paths.

    total=False: all fields optional at initialization.
    """

    # ── Transaction / Event Information ───────────────────────────────────────
    # The raw transaction data received from the payment processing system.
    # In production: arrives via Kafka/Kinesis event stream or REST API.

    transaction_id: str
    # Unique transaction identifier. Format: "TXN-YYYYMMDD-XXXXXXXXXX"
    # Links to core banking, card processor, or ACH system records.

    account_id: str
    # The account being debited/credited

    customer_id: str
    # Customer identifier — links to CRM, KYC, and fraud history records

    transaction_amount: float
    # Transaction amount in USD

    transaction_currency: str
    # ISO 4217 currency code. Cross-currency transactions get risk uplift.

    transaction_type: str
    # DEBIT | CREDIT | TRANSFER | PAYMENT | WITHDRAWAL | PURCHASE

    transaction_channel: TransactionChannel
    # Channel of transaction — major risk discriminator

    merchant_name: Optional[str]
    # Merchant name (card transactions). None for wire/ACH.

    merchant_category_code: Optional[str]
    # MCC code — maps to risk category (gambling, crypto exchange, etc.)

    merchant_country: Optional[str]
    # ISO 3166-1 alpha-2 country code of merchant

    counterparty_account: Optional[str]
    # For transfers/wires: receiving account number

    counterparty_institution: Optional[str]
    # For ACH/wire: receiving financial institution

    transaction_timestamp: str
    # ISO 8601 UTC timestamp of the transaction

    card_present: Optional[bool]
    # True for POS transactions; False for CNP (e-commerce, phone)

    card_entry_method: Optional[str]
    # CHIP | SWIPE | CONTACTLESS | MANUAL_ENTRY | TOKEN (Apple/Google Pay)

    # ── Device & Session Intelligence ─────────────────────────────────────────
    # Device signals are critical for online/mobile fraud detection.
    # Absent for ATM/POS/branch transactions.

    device_id: Optional[str]
    # Device fingerprint or registered device ID

    ip_address: Optional[str]
    # IP address (masked/hashed before logging — GLBA/PCI DSS)

    user_agent: Optional[str]
    # Browser/app user agent string

    session_id: Optional[str]
    # Online/mobile session identifier

    geolocation: Optional[Dict[str, Any]]
    # Current transaction location: {lat, lon, city, country, accuracy_meters}

    device_risk_score: Optional[float]
    # 0-100 device risk score from device intelligence tool
    # Factors: new device, impossible travel, VPN/proxy, rooted device

    ip_risk_signals: Optional[Dict[str, Any]]
    # IP reputation signals:
    #   - is_vpn: bool
    #   - is_tor: bool
    #   - is_proxy: bool
    #   - ip_reputation_score: float
    #   - country: str
    #   - isp: str
    #   - previous_fraud_flag: bool

    impossible_travel: Optional[bool]
    # True if current location is physically impossible given last transaction
    # (e.g., last txn in Boston 5 min ago, current txn in Dubai)
    # Strongest single fraud signal for card transactions

    # ── Customer / Account Context ────────────────────────────────────────────
    # Account history and expected behavior profile for anomaly detection.
    # Suspicious activity is always relative to the individual's baseline.

    account_profile: Optional[Dict[str, Any]]
    # Full account context:
    #   - account_age_days: int
    #   - average_transaction_amount: float
    #   - average_monthly_volume: float
    #   - typical_merchants: list[str] (MCC codes)
    #   - typical_transaction_channels: list[TransactionChannel]
    #   - typical_geographies: list[str] (country codes)
    #   - enrolled_in_2fa: bool
    #   - fraud_history_count: int
    #   - dispute_history_count: int
    #   - customer_risk_tier: str

    transaction_amount_vs_average: Optional[float]
    # Ratio of this transaction to account's average: 1.0 = typical, 5.0 = 5x average
    # High ratio is a strong fraud signal

    # ── Velocity Signals ──────────────────────────────────────────────────────
    # Velocity checks detect rapid sequential transactions — a key fraud pattern
    # (card testing, account draining, automated fraud rings).

    velocity_signals: Optional[Dict[str, Any]]
    # Velocity analysis results:
    #   - txn_count_1min: int — transactions in last 1 minute
    #   - txn_count_5min: int — transactions in last 5 minutes
    #   - txn_count_1hr: int — transactions in last 1 hour
    #   - txn_count_24hr: int — transactions in last 24 hours
    #   - amount_sum_1hr: float — total amount in last 1 hour
    #   - amount_sum_24hr: float — total amount in last 24 hours
    #   - unique_merchants_1hr: int
    #   - unique_countries_1hr: int
    #   - velocity_flag: bool — any velocity threshold exceeded

    # ── Behavioral Signals ────────────────────────────────────────────────────
    # Behavioral analytics compares this session to the customer's typical
    # interaction patterns. Deviations suggest account takeover.

    behavioral_signals: Optional[Dict[str, Any]]
    # Behavioral analysis results:
    #   - typing_rhythm_match: float (0-1, biometric match if available)
    #   - navigation_pattern_anomaly: bool
    #   - session_duration_anomaly: bool
    #   - time_of_day_anomaly: bool (transaction at unusual hour for this customer)
    #   - payee_is_new: bool (first time paying this merchant/counterparty)
    #   - login_anomaly: bool (unusual login pattern before this session)
    #   - behavioral_risk_score: float (0-100)

    # ── Rule Engine Results ────────────────────────────────────────────────────
    # Deterministic rule checks — fast, interpretable, always runs first.
    # Rules fire before any ML/LLM scoring.

    rule_hits: Optional[List[Dict[str, Any]]]
    # List of triggered rules:
    #   Each: {rule_id, rule_name, severity: HIGH|MEDIUM|LOW, score_contribution}
    # Example hits: "IMPOSSIBLE_TRAVEL", "NEW_DEVICE_HIGH_VALUE",
    #               "MCC_RESTRICTED", "VELOCITY_EXCEEDED", "AMOUNT_LIMIT"

    rule_based_score: Optional[float]
    # 0-100 score from deterministic rule engine (30% weight in composite)

    hard_block_triggered: Optional[bool]
    # True if any rule triggers a hard block regardless of composite score
    # Hard blocks: OFAC-adjacent merchant, known fraud IP, confirmed stolen card

    # ── ML / LLM Scoring ──────────────────────────────────────────────────────

    llm_fraud_probability: Optional[float]
    # 0-100 fraud probability from Claude Sonnet 4.6 contextual analysis (50% weight)

    llm_fraud_reasoning: Optional[str]
    # Plain-language explanation of why the LLM assigned this probability
    # Surfaces for analyst review and Reg E dispute documentation

    llm_suspected_fraud_type: Optional[FraudType]
    # The fraud typology the LLM believes is most likely

    historical_pattern_score: Optional[float]
    # 0-100 score from historical base rates for this customer/rule combination (20%)

    # ── Composite Score ────────────────────────────────────────────────────────

    composite_fraud_score: Optional[float]
    # Weighted composite: rule (30%) + LLM (50%) + historical (20%)
    # Thresholds: <40=ALLOW, 40-65=ANALYST_REVIEW, 65-85=STEP_UP, ≥85=BLOCK

    score_components: Optional[Dict[str, float]]
    # Breakdown for SR 11-7 model risk documentation

    risk_factors: Optional[List[str]]
    # Human-readable list of the top risk factors driving the score

    # ── Fraud Decision ─────────────────────────────────────────────────────────

    fraud_decision: Optional[FraudDecision]
    # The real-time fraud disposition

    decision_rationale: Optional[str]
    # Plain-language explanation of why this decision was made

    decision_confidence: Optional[str]
    # HIGH | MEDIUM | LOW — confidence in the fraud decision

    response_time_ms: Optional[int]
    # Milliseconds from transaction receipt to decision — target < 200ms

    # ── Step-Up Authentication ─────────────────────────────────────────────────

    step_up_auth_method: Optional[str]
    # If STEP_UP_AUTH: method requested (SMS_OTP | PUSH_NOTIFICATION | SECURITY_Q)

    step_up_auth_result: Optional[str]
    # PASSED | FAILED | EXPIRED — result of step-up authentication challenge

    # ── Case Management ────────────────────────────────────────────────────────

    case_id: Optional[str]
    # Fraud case ID created for BLOCK and ANALYST_REVIEW decisions

    analyst_queue: Optional[str]
    # Which analyst queue the case was routed to:
    # CARD_FRAUD | ACH_FRAUD | WIRE_FRAUD | ACCOUNT_TAKEOVER | SENIOR_ANALYST

    analyst_id: Optional[str]
    # Assigned analyst ID (if human review completed)

    analyst_decision: Optional[str]
    # CONFIRMED_FRAUD | FALSE_POSITIVE | NEEDS_MORE_INFO

    analyst_notes: Optional[str]

    # ── Reg E / Customer Notification ─────────────────────────────────────────
    # Reg E (12 CFR § 1005.11) requires specific disclosures when a consumer
    # transaction is declined or when consumer reports unauthorized activity.

    reg_e_disclosure_required: Optional[bool]
    # True when transaction is BLOCK/FREEZE and consumer must be notified

    reg_e_disclosure_draft: Optional[str]
    # Draft customer notification text with Reg E-required disclosures:
    #   - Right to dispute within 60 days (Reg E § 1005.11(b))
    #   - Provisional credit timeline (10 business days max)
    #   - Institution's investigation timeline (45-90 days)
    #   - Contact information for disputes

    provisional_credit_required: Optional[bool]
    # True if consumer has reported unauthorized transaction
    # Reg E requires provisional credit within 10 business days of notice

    # ── SAR Consideration ──────────────────────────────────────────────────────
    # BSA: Fraud with money laundering indicators may require SAR filing.
    # SAR consideration is NOT the same as SAR filing — it's a flag for
    # the BSA Officer to evaluate.

    sar_consideration_flag: Optional[bool]
    # True when fraud pattern suggests possible money laundering predicate:
    #   - Structured fraud amounts (sub-$10K)
    #   - Network of coordinated fraud accounts
    #   - Wire fraud with international components
    #   - Rapid fund movement post-fraud

    # ── Human Review ──────────────────────────────────────────────────────────

    human_review_required: Optional[bool]

    human_review_completed: Optional[bool]

    human_review_completed_at: Optional[str]

    # ── LangGraph Infrastructure ───────────────────────────────────────────────

    current_step: Optional[str]

    completed_steps: Optional[List[str]]

    errors: Optional[List[Dict[str, Any]]]

    # ── Audit Trail ────────────────────────────────────────────────────────────
    # Every fraud decision must be logged for:
    #   - Reg E dispute investigation (45-90 day resolution window)
    #   - Fair lending / disparate impact analysis (CFPB)
    #   - SR 11-7 model risk documentation
    #   - BSA SAR support documentation
    #   - Card network dispute representment

    audit_trail: Optional[List[Dict[str, Any]]]
    # Each entry: {
    #   "timestamp": ISO 8601,
    #   "actor": "fraud_detection_agent" | analyst_id,
    #   "action": description,
    #   "node": graph node name,
    #   "score_at_time": float,
    #   "data_sources_accessed": list,
    #   "ai_model_used": str or None,
    #   "response_time_ms": int or None,
    #   "regulatory_basis": str,
    # }
