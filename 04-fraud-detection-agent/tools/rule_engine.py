# tools/rule_engine.py
# ============================================================
# Deterministic Rule Engine
#
# Rules are the first line of defense — fast, interpretable, and
# always explainable for regulatory representment purposes.
#
# Each rule returns:
#   - rule_id, rule_name, severity, score_contribution
#   - Optional: hard_block (True for confirmed fraud indicators)
#
# Rule categories:
#   - Velocity rules (RULE-001 to RULE-003)
#   - Geography / jurisdiction rules (RULE-010 to RULE-019)
#   - Account anomaly rules (RULE-020 to RULE-029)
#   - Device / IP rules (RULE-030 to RULE-039)
#   - Channel / MCC rules (RULE-040 to RULE-049)
#   - Hard block triggers (RULE-090 to RULE-099)
# ============================================================

from typing import Any, Dict, List, Optional, Tuple


# ── Rule Configurations ───────────────────────────────────────────────────────

# High-risk MCC codes: gambling, crypto, adult, quasi-cash
# Visa/MC require elevated monitoring for these categories
RESTRICTED_MCCS = {
    "7995": "gambling",
    "6051": "quasi_cash_crypto_exchange",
    "7273": "dating_services",
    "5912": "drug_stores",
    "6211": "securities_brokers",
    "4829": "wire_transfer_money_orders",
    "6010": "banks_cash_disbursements",
    "6012": "financial_institutions_merchandise",
}

# FATF grey-listed and high-risk jurisdictions
# FinCEN advisories + Visa/MC elevated risk countries
HIGH_RISK_COUNTRIES = {
    # OFAC sanctioned
    "KP",  # North Korea
    "IR",  # Iran
    "CU",  # Cuba
    "SY",  # Syria
    # FATF black/grey list
    "MM",  # Myanmar
    "PK",  # Pakistan (grey)
    "YE",  # Yemen
    "SD",  # Sudan
    "SS",  # South Sudan
    # Elevated card fraud rates (Visa/MC data)
    "NG",  # Nigeria
    "GH",  # Ghana
    "RO",  # Romania
    "BG",  # Bulgaria
    # Post-2022 elevated risk
    "RU",  # Russia (SWIFT restrictions)
    "BY",  # Belarus
}

# Fraud velocity thresholds
# Calibrated to detect card testing (many small rapid transactions)
# and account draining (fewer but larger)
VELOCITY_THRESHOLDS = {
    "txn_count_1min": 3,      # >3 in 1 min = card testing
    "txn_count_5min": 5,      # >5 in 5 min = automated fraud
    "txn_count_1hr": 10,      # >10 in 1 hr = unusual frequency
    "amount_sum_1hr": 5000,   # >$5K in 1 hr = high-value drain
    "amount_sum_24hr": 15000, # >$15K in 24 hr = daily limit breach
    "unique_countries_1hr": 2,  # Multi-country in 1 hr = cloned card
}


# ── Rule Evaluation Functions ─────────────────────────────────────────────────

def evaluate_velocity_rules(
    velocity_signals: Dict[str, Any],
    transaction_amount: float,
) -> List[Dict[str, Any]]:
    """
    Check transaction frequency and cumulative amount velocity.

    Velocity rules are the primary defense against:
      - Card testing: Fraudster verifies stolen card with many small purchases
      - Account draining: Multiple large withdrawals in rapid succession
      - Fraud ring activity: Many accounts transacting simultaneously

    Returns list of triggered rule dicts.
    """
    hits = []

    count_1min = velocity_signals.get("txn_count_1min", 0)
    count_5min = velocity_signals.get("txn_count_5min", 0)
    count_1hr = velocity_signals.get("txn_count_1hr", 0)
    amount_1hr = velocity_signals.get("amount_sum_1hr", 0)
    amount_24hr = velocity_signals.get("amount_sum_24hr", 0)
    countries_1hr = velocity_signals.get("unique_countries_1hr", 1)

    if count_1min >= VELOCITY_THRESHOLDS["txn_count_1min"]:
        hits.append({
            "rule_id": "RULE-001",
            "rule_name": "CARD_TESTING_VELOCITY",
            "severity": "HIGH",
            "score_contribution": 35,
            "detail": f"{count_1min} transactions in 1 minute — card testing pattern",
        })

    if count_5min >= VELOCITY_THRESHOLDS["txn_count_5min"] and count_1min < VELOCITY_THRESHOLDS["txn_count_1min"]:
        hits.append({
            "rule_id": "RULE-002",
            "rule_name": "RAPID_SEQUENTIAL_VELOCITY",
            "severity": "HIGH",
            "score_contribution": 25,
            "detail": f"{count_5min} transactions in 5 minutes",
        })

    if count_1hr >= VELOCITY_THRESHOLDS["txn_count_1hr"]:
        hits.append({
            "rule_id": "RULE-003",
            "rule_name": "HOURLY_FREQUENCY_EXCEEDED",
            "severity": "MEDIUM",
            "score_contribution": 18,
            "detail": f"{count_1hr} transactions in last hour",
        })

    if amount_1hr >= VELOCITY_THRESHOLDS["amount_sum_1hr"]:
        hits.append({
            "rule_id": "RULE-004",
            "rule_name": "HOURLY_AMOUNT_LIMIT",
            "severity": "HIGH" if amount_1hr >= 10000 else "MEDIUM",
            "score_contribution": 22 if amount_1hr >= 10000 else 15,
            "detail": f"${amount_1hr:.0f} cumulative in last hour",
        })

    if countries_1hr >= VELOCITY_THRESHOLDS["unique_countries_1hr"]:
        hits.append({
            "rule_id": "RULE-005",
            "rule_name": "MULTI_COUNTRY_VELOCITY",
            "severity": "HIGH",
            "score_contribution": 28,
            "detail": f"Transactions in {countries_1hr} different countries in last hour",
        })

    return hits


def evaluate_geography_rules(
    merchant_country: Optional[str],
    customer_typical_geographies: List[str],
    transaction_channel: str,
) -> List[Dict[str, Any]]:
    """
    Check merchant country against customer typical geographies
    and regulatory watchlists.
    """
    hits = []

    if not merchant_country:
        return hits

    country = merchant_country.upper()

    # High-risk jurisdiction
    if country in HIGH_RISK_COUNTRIES:
        hits.append({
            "rule_id": "RULE-011",
            "rule_name": "HIGH_RISK_JURISDICTION",
            "severity": "HIGH",
            "score_contribution": 20,
            "detail": f"Transaction in high-risk jurisdiction: {country}",
        })

    # New geography for this customer
    typical = [c.upper() for c in customer_typical_geographies]
    if country not in typical and country != "US":
        hits.append({
            "rule_id": "RULE-012",
            "rule_name": "NEW_GEOGRAPHY",
            "severity": "MEDIUM",
            "score_contribution": 12,
            "detail": f"First transaction in {country} for this customer",
        })

    return hits


def evaluate_amount_rules(
    transaction_amount: float,
    amount_vs_average: float,
    transaction_type: str,
) -> List[Dict[str, Any]]:
    """
    Check for amount anomalies relative to customer baseline.

    SR 11-7: Amount deviation from baseline is a top predictor in
    validated fraud models across all major card networks.
    """
    hits = []

    if amount_vs_average >= 10.0:
        hits.append({
            "rule_id": "RULE-021",
            "rule_name": "EXTREME_AMOUNT_OUTLIER",
            "severity": "HIGH",
            "score_contribution": 25,
            "detail": f"Transaction is {amount_vs_average:.1f}x customer average",
        })
    elif amount_vs_average >= 5.0:
        hits.append({
            "rule_id": "RULE-022",
            "rule_name": "ELEVATED_AMOUNT_OUTLIER",
            "severity": "MEDIUM",
            "score_contribution": 14,
            "detail": f"Transaction is {amount_vs_average:.1f}x customer average",
        })

    # Structuring detection: amounts just below $10,000
    # BSA Currency Transaction Report threshold
    if 9000 <= transaction_amount < 10000:
        hits.append({
            "rule_id": "RULE-023",
            "rule_name": "STRUCTURING_INDICATOR",
            "severity": "HIGH",
            "score_contribution": 30,
            "detail": f"Amount ${transaction_amount:.2f} — potential structuring below CTR threshold",
        })

    return hits


def evaluate_mcc_rules(mcc: Optional[str]) -> List[Dict[str, Any]]:
    """Check merchant category code against restricted categories."""
    if not mcc or mcc not in RESTRICTED_MCCS:
        return []

    return [{
        "rule_id": "RULE-041",
        "rule_name": "RESTRICTED_MCC",
        "severity": "MEDIUM",
        "score_contribution": 12,
        "detail": f"Restricted merchant category: {RESTRICTED_MCCS[mcc]} (MCC {mcc})",
    }]


def evaluate_hard_block_rules(
    ip_risk_signals: Dict[str, Any],
    merchant_name: Optional[str],
    rule_hits: List[Dict[str, Any]],
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Evaluate conditions that trigger hard blocks regardless of composite score.

    Hard block triggers:
      - IP address confirmed associated with prior fraud
      - Tor exit node (anonymized, high-risk)
      - Merchant name on internal fraud registry

    These blocks are not configurable and cannot be overridden by
    ML probability — they represent confirmed fraud indicators.

    Returns:
      (hard_block_triggered: bool, additional_rule_hits: list)
    """
    new_hits = list(rule_hits)
    hard_block = False

    if ip_risk_signals.get("previous_fraud_flag"):
        hard_block = True
        new_hits.append({
            "rule_id": "RULE-091",
            "rule_name": "CONFIRMED_FRAUD_IP",
            "severity": "CRITICAL",
            "score_contribution": 100,
            "hard_block": True,
            "detail": "IP address confirmed associated with prior fraud cases",
        })

    if ip_risk_signals.get("is_tor"):
        hard_block = True
        new_hits.append({
            "rule_id": "RULE-092",
            "rule_name": "TOR_EXIT_NODE",
            "severity": "CRITICAL",
            "score_contribution": 100,
            "hard_block": True,
            "detail": "Transaction originated from Tor exit node — anonymized high-risk connection",
        })

    return hard_block, new_hits


def compute_rule_score(rule_hits: List[Dict[str, Any]]) -> float:
    """
    Aggregate rule hits into a single 0-100 score.

    Uses diminishing returns for multiple rule hits — the first
    high-severity rule dominates, additional rules add incrementally.
    This prevents over-stacking on routine multi-rule cases.
    """
    if not rule_hits:
        return 0.0

    # Sort by contribution descending
    sorted_hits = sorted(rule_hits, key=lambda x: x.get("score_contribution", 0), reverse=True)

    score = 0.0
    for i, hit in enumerate(sorted_hits):
        contribution = hit.get("score_contribution", 0)
        # Apply diminishing weight for additional rules (first rule full weight)
        weight = 1.0 / (1 + i * 0.3)
        score += contribution * weight

    return round(min(score, 100.0), 1)
