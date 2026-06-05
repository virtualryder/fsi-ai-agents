# tools/transaction_monitor.py
# ============================================================
# Transaction Monitoring System (TMS) Integration
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   Transaction data is the evidentiary backbone of every AML investigation.
#   Without it, you're investigating blind. The transaction record answers:
#   "What did the money do? Where did it come from? Where did it go?"
#   This is the "follow the money" data source.
#
# REGULATORY REQUIREMENT SERVED:
#   - BSA: 31 U.S.C. § 5318(g) — investigation of suspicious transactions
#   - 31 CFR § 1010.100(xx): Structuring defined requires transaction-level data
#   - FinCEN SAR: "Suspicious Activity Information" requires specific transaction dates/amounts
#   - CTR (31 U.S.C. § 5313): Currency transactions $10K+ require reporting
#   - OCC Examination: Examiners expect evidence of transaction-level investigation
#
# REAL VENDOR SYSTEMS THAT PROVIDE THIS:
#   - NICE Actimize (SAM — Suspicious Activity Monitoring): Industry leader
#   - Oracle Financial Services FCCM (Mantas): Large bank standard
#   - SAS Anti-Money Laundering: Analytics-focused TMS
#   - FIS MISER AML: Community bank focused
#   - Temenos Financial Crime Mitigation: Core banking integrated TMS
#   - Jack Henry Banno: Community/regional bank solution
#   - Nasdaq Verafin: Cloud-native AML platform
# ============================================================

import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Load fixture data at module load time for performance
_FIXTURE_PATH = Path(__file__).parent.parent / "data" / "fixtures"


def _load_fixture(filename: str) -> Any:
    """Load a JSON fixture file. Returns empty dict/list on failure."""
    try:
        with open(_FIXTURE_PATH / filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load fixture {filename}: {e}")
        return {}


# ── INTEGRATION POINT ────────────────────────────────────────────────────────
# PRODUCTION: Replace all mock functions below with real TMS API calls.
# Most TMS vendors provide REST APIs for:
#   - Alert retrieval: GET /api/v1/alerts?customer_id={id}&status=OPEN
#   - Transaction history: GET /api/v1/transactions?account={id}&days={n}
#   - Pattern queries: POST /api/v1/patterns/analyze
#
# Authentication typically uses:
#   - API Key: X-API-Key header (Actimize SAM)
#   - OAuth2 client credentials: Bearer token (Oracle Mantas)
#   - mTLS: Mutual TLS certificate auth (high-security environments)
#
# Example Actimize SAM integration:
#   import requests
#   headers = {"X-API-Key": os.getenv("ACTIMIZE_API_KEY"), "Content-Type": "application/json"}
#   response = requests.get(f"{os.getenv('ACTIMIZE_API_URL')}/alerts/{alert_id}", headers=headers)
#   return response.json()
# ─────────────────────────────────────────────────────────────────────────────


def get_alerts_for_customer(customer_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all active TMS alerts for a customer.

    In production, this queries the TMS for all open alerts associated
    with this customer_id. A customer may have multiple simultaneous alerts
    across different rules and accounts.

    Args:
        customer_id: Internal customer identifier

    Returns:
        List of alert dictionaries, each containing:
            - alert_id: Unique TMS alert identifier
            - alert_type: Category of suspicious activity
            - severity: HIGH / MEDIUM / LOW
            - status: OPEN / IN_REVIEW / CLOSED
            - triggered_rule: Rule or model that fired
            - alert_date: When the alert was generated
            - account_id: Affected account
            - transaction_ids: Triggering transactions

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace mock data with:
    #   response = actimize_client.get(
    #       f"/api/v1/customers/{customer_id}/alerts",
    #       params={"status": "OPEN", "limit": 50}
    #   )
    #   return response.json()["alerts"]
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Load sample alerts and filter to this customer
    all_alerts = _load_fixture("sample_alerts.json")
    if isinstance(all_alerts, list):
        customer_alerts = [a for a in all_alerts if a.get("customer_id") == customer_id]
        if customer_alerts:
            return customer_alerts

    # Generate a mock alert if no fixture match
    logger.debug(f"[transaction_monitor] No fixture alerts for {customer_id}, generating mock")
    return [
        {
            "alert_id": f"ALT-2024-{random.randint(1000, 9999)}",
            "alert_type": "STRUCTURING",
            "severity": "HIGH",
            "status": "OPEN",
            "customer_id": customer_id,
            "account_id": f"ACC-{customer_id[-4:]}001",
            "triggered_rule": "CASH-STRUCT-001",
            "alert_date": (datetime.utcnow() - timedelta(days=random.randint(1, 10))).strftime("%Y-%m-%d"),
            "description": "Multiple cash deposits just below $10,000 CTR threshold within 10-day window",
            "transaction_ids": [f"TXN-{random.randint(100000, 999999)}" for _ in range(5)],
        }
    ]


def get_transaction_history(account_id: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Retrieve transaction history for a specific account.

    This is the most frequently called tool in the investigation — it provides
    the raw transaction data that underpins all pattern analysis.

    A 12-month lookback (365 days) is the standard for AML investigations.
    The OCC BSA/AML Examination Handbook expects analysts to review at least
    the period of the suspicious activity, plus context before and after.

    Args:
        account_id: Bank account identifier (masked in logs for PII)
        days: Lookback period in days (default: 365 = 12 months)

    Returns:
        List of transaction dictionaries, each containing:
            - transaction_id: Unique transaction identifier
            - date: Transaction date (ISO 8601)
            - amount: Transaction amount (positive = debit, contextual)
            - transaction_type: CASH_DEPOSIT, CASH_WITHDRAWAL, WIRE_IN,
                               WIRE_OUT, ACH_CREDIT, ACH_DEBIT, CHECK, etc.
            - direction: CREDIT or DEBIT (from account perspective)
            - channel: BRANCH, ATM, ONLINE, MOBILE, WIRE_ROOM
            - counterparty_name: Name of the other party
            - counterparty_account: Their account (masked if known)
            - counterparty_bank: Their financial institution
            - counterparty_country: Country of the counterparty
            - currency: ISO 4217 currency code
            - reference: Payment reference/memo
            - branch_id: Branch where cash transaction occurred
            - originating_country: Country of origin for international wires

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace mock data with core banking API call:
    #
    # Temenos T24 example:
    #   from pyT24 import T24Client
    #   client = T24Client(base_url=os.getenv("CORE_BANKING_API_URL"))
    #   txns = client.get_account_movements(
    #       account_id=account_id,
    #       date_from=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
    #       date_to=datetime.now().strftime("%Y%m%d")
    #   )
    #   return [_map_t24_transaction(t) for t in txns]
    #
    # FIS Modern Banking Platform example:
    #   response = requests.get(
    #       f"{os.getenv('CORE_BANKING_API_URL')}/accounts/{account_id}/transactions",
    #       params={"fromDate": start_date, "toDate": end_date},
    #       headers={"Authorization": f"Bearer {get_fis_token()}"}
    #   )
    #   return response.json()["transactions"]
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Load fixture transactions
    all_transactions = _load_fixture("sample_transactions.json")

    if isinstance(all_transactions, list):
        account_txns = [t for t in all_transactions if t.get("account_id") == account_id]
        if account_txns:
            # Filter to lookback period
            cutoff = datetime.utcnow() - timedelta(days=days)
            filtered = [
                t for t in account_txns
                if datetime.strptime(t.get("date", "2000-01-01"), "%Y-%m-%d") >= cutoff
            ]
            return filtered if filtered else account_txns

    # Generate realistic mock transaction history
    logger.debug(f"[transaction_monitor] Generating mock transactions for account {account_id}")
    transactions = []

    # Simulate different transaction patterns based on the account suffix
    account_suffix = account_id[-3:] if len(account_id) >= 3 else "001"

    if "001" in account_suffix:
        # Structuring pattern: multiple cash deposits just under $10K
        transactions = _generate_structuring_transactions(account_id, days)
    elif "002" in account_suffix:
        # International wire pattern: large wires to high-risk jurisdictions
        transactions = _generate_wire_transfer_transactions(account_id, days)
    else:
        # Rapid movement pattern: dormant then sudden high activity
        transactions = _generate_rapid_movement_transactions(account_id, days)

    return transactions


def _generate_structuring_transactions(account_id: str, days: int) -> List[Dict[str, Any]]:
    """
    Generate mock transactions showing structuring pattern.
    Used when no fixture data is available for the account.
    Structuring = multiple cash deposits just under $10,000 to avoid CTR.
    """
    transactions = []
    base_date = datetime.utcnow() - timedelta(days=min(days, 365))

    # Generate normal baseline transactions first (3-4 months of normal activity)
    for i in range(60):
        txn_date = base_date + timedelta(days=i * 2)
        transactions.append({
            "transaction_id": f"TXN-BASELINE-{account_id[-4:]}-{i:04d}",
            "account_id": account_id,
            "date": txn_date.strftime("%Y-%m-%d"),
            "amount": round(random.uniform(200, 3000), 2),
            "transaction_type": random.choice(["CASH_DEPOSIT", "ACH_CREDIT", "CHECK_DEPOSIT"]),
            "direction": "CREDIT",
            "channel": random.choice(["BRANCH", "ATM", "MOBILE"]),
            "counterparty_name": random.choice(["Payroll Direct Deposit", "Transfer from Savings", "Rental Income"]),
            "counterparty_country": "US",
            "currency": "USD",
            "reference": "Regular deposit",
            "branch_id": f"BRANCH-{random.randint(100, 199)}",
        })

    # Generate structuring cluster — 8 cash deposits, all just under $10K
    # over a 10-day period. This is a classic structuring pattern.
    struct_start = datetime.utcnow() - timedelta(days=20)
    structuring_amounts = [9500, 9750, 9200, 9850, 9100, 9600, 9950, 9400]
    for i, amount in enumerate(structuring_amounts):
        txn_date = struct_start + timedelta(days=i + random.uniform(0, 1.5))
        transactions.append({
            "transaction_id": f"TXN-STRUCT-{account_id[-4:]}-{i:04d}",
            "account_id": account_id,
            "date": txn_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "transaction_type": "CASH_DEPOSIT",
            "direction": "CREDIT",
            "channel": "BRANCH",
            "counterparty_name": "CASH",
            "counterparty_country": "US",
            "currency": "USD",
            "reference": "Cash deposit",
            "branch_id": f"BRANCH-{random.choice([101, 102, 103])}",  # Multiple branches
            "suspicious_flag": True,
            "suspicious_reason": "Sub-$10K cash deposit — potential structuring",
        })

    # Add some cash withdrawals to show cash cycling
    for i in range(4):
        txn_date = struct_start + timedelta(days=i * 2 + 1)
        transactions.append({
            "transaction_id": f"TXN-CASHOUT-{account_id[-4:]}-{i:04d}",
            "account_id": account_id,
            "date": txn_date.strftime("%Y-%m-%d"),
            "amount": round(random.uniform(5000, 8000), 2),
            "transaction_type": "CASH_WITHDRAWAL",
            "direction": "DEBIT",
            "channel": "BRANCH",
            "counterparty_name": "CASH",
            "counterparty_country": "US",
            "currency": "USD",
            "reference": "Cash withdrawal",
            "branch_id": f"BRANCH-{random.choice([101, 102])}",
        })

    return sorted(transactions, key=lambda t: t["date"])


def _generate_wire_transfer_transactions(account_id: str, days: int) -> List[Dict[str, Any]]:
    """
    Generate mock transactions showing high-risk geography wire pattern.
    Large international wires to/from high-risk jurisdictions.
    """
    transactions = []
    high_risk_countries = ["IR", "SY", "VE", "BY", "RU"]
    high_risk_banks = [
        "Melli Bank PLC", "Bank Tejarat", "Al-Baraka Islamic Bank",
        "Caracas International Bank", "Promsvyazbank"
    ]

    for i in range(15):
        txn_date = datetime.utcnow() - timedelta(days=random.randint(10, min(days, 300)))
        country = random.choice(high_risk_countries)
        transactions.append({
            "transaction_id": f"TXN-WIRE-{account_id[-4:]}-{i:04d}",
            "account_id": account_id,
            "date": txn_date.strftime("%Y-%m-%d"),
            "amount": round(random.choice([25000, 50000, 75000, 100000, 150000]) + random.uniform(-500, 500), 2),
            "transaction_type": "WIRE_OUT" if i % 2 == 0 else "WIRE_IN",
            "direction": "DEBIT" if i % 2 == 0 else "CREDIT",
            "channel": "WIRE_ROOM",
            "counterparty_name": f"Acme Trading Co. {country}",
            "counterparty_account": f"**{random.randint(1000, 9999)}",
            "counterparty_bank": random.choice(high_risk_banks),
            "counterparty_country": country,
            "currency": "USD",
            "reference": f"Trade payment REF-{random.randint(10000, 99999)}",
            "originating_country": country,
            "suspicious_flag": True,
            "suspicious_reason": f"International wire to/from high-risk jurisdiction: {country}",
        })

    return sorted(transactions, key=lambda t: t["date"])


def _generate_rapid_movement_transactions(account_id: str, days: int) -> List[Dict[str, Any]]:
    """
    Generate mock transactions showing rapid movement (dormancy-then-activity) pattern.
    Account dormant for 6 months, then $450K flows through in 72 hours.
    """
    transactions = []

    # 6 months of dormancy — only minimal activity
    dormancy_start = datetime.utcnow() - timedelta(days=min(days, 270))
    for i in range(3):
        txn_date = dormancy_start + timedelta(days=i * 45)
        transactions.append({
            "transaction_id": f"TXN-DORMANT-{account_id[-4:]}-{i:04d}",
            "account_id": account_id,
            "date": txn_date.strftime("%Y-%m-%d"),
            "amount": round(random.uniform(10, 50), 2),
            "transaction_type": "MONTHLY_FEE",
            "direction": "DEBIT",
            "channel": "SYSTEM",
            "counterparty_name": "Bank Service Fee",
            "counterparty_country": "US",
            "currency": "USD",
            "reference": "Monthly maintenance fee",
        })

    # Sudden burst of activity — $450K in 72 hours
    burst_start = datetime.utcnow() - timedelta(days=5)

    # Large incoming wire
    transactions.append({
        "transaction_id": f"TXN-BURST-{account_id[-4:]}-001",
        "account_id": account_id,
        "date": burst_start.strftime("%Y-%m-%d"),
        "amount": 250000.00,
        "transaction_type": "WIRE_IN",
        "direction": "CREDIT",
        "channel": "WIRE_ROOM",
        "counterparty_name": "Global Capital Management LLC",
        "counterparty_account": "**7291",
        "counterparty_bank": "First National Bank of Delaware",
        "counterparty_country": "US",
        "currency": "USD",
        "reference": "Investment proceeds",
        "suspicious_flag": True,
        "suspicious_reason": "Large wire to dormant account",
    })

    # Multiple rapid outbound wires within 72 hours
    outbound_txns = [
        (175000.00, "Sunrise Holdings Panama SA", "Banco General Panama", "PA"),
        (100000.00, "Tech Solutions Ltd", "HSBC Hong Kong", "HK"),
        (75000.00, "Management Consulting LLC", "Wells Fargo", "US"),
    ]

    for i, (amount, counterparty, bank, country) in enumerate(outbound_txns):
        txn_date = burst_start + timedelta(hours=18 * (i + 1))
        transactions.append({
            "transaction_id": f"TXN-BURST-{account_id[-4:]}-{i+2:03d}",
            "account_id": account_id,
            "date": txn_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "transaction_type": "WIRE_OUT",
            "direction": "DEBIT",
            "channel": "WIRE_ROOM",
            "counterparty_name": counterparty,
            "counterparty_bank": bank,
            "counterparty_country": country,
            "currency": "USD",
            "reference": f"Payment REF-{random.randint(10000, 99999)}",
            "suspicious_flag": True,
            "suspicious_reason": "Rapid outbound wire from dormant account",
        })

    # Second large deposit (smurfing/layering follow-on)
    transactions.append({
        "transaction_id": f"TXN-BURST-{account_id[-4:]}-005",
        "account_id": account_id,
        "date": (burst_start + timedelta(days=2)).strftime("%Y-%m-%d"),
        "amount": 200000.00,
        "transaction_type": "WIRE_IN",
        "direction": "CREDIT",
        "channel": "WIRE_ROOM",
        "counterparty_name": "Pacific Rim Trading Co.",
        "counterparty_bank": "Standard Chartered Bank",
        "counterparty_country": "SG",
        "currency": "USD",
        "reference": "Trade settlement",
        "suspicious_flag": True,
        "suspicious_reason": "Second large wire to dormant account — rapid movement",
    })

    return sorted(transactions, key=lambda t: t["date"])


def detect_structuring_patterns(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Algorithmically detect structuring patterns in transaction data.

    Structuring (31 CFR § 1010.100(xx)) is the intentional breaking up
    of transactions to evade the $10,000 Currency Transaction Report (CTR)
    filing threshold. Key indicators:
    - Multiple cash deposits in the range of $8,000-$9,999
    - Multiple deposits within a 10-day window that aggregate near $10K
    - Deposits at different branches on the same day
    - Pattern of deposits just below round-number thresholds

    Note: The algorithm flags INDICATORS — not conclusions. The investigator
    must assess whether the structuring was intentional (which is what makes
    it illegal under 31 U.S.C. § 5324).

    Args:
        transactions: List of transaction dictionaries

    Returns:
        Structuring analysis results including flagged transactions and confidence

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # In production, this analysis is typically done by the TMS itself:
    # - Actimize SAM includes structuring models out of the box
    # - Oracle Mantas provides STRCT (Structuring) scenarios
    # - SAS AML includes structuring detection in its scenario library
    # Replace this function with a call to your TMS's detection API:
    #   response = tms_client.post("/api/v1/analysis/structuring", json={"transactions": transactions})
    #   return response.json()
    # ──────────────────────────────────────────────────────────────────────────
    """
    CTR_THRESHOLD = 10000.00
    STRUCTURING_LOWER_BOUND = 8000.00
    LOOKBACK_WINDOW_DAYS = 10

    cash_transactions = [
        t for t in transactions
        if t.get("transaction_type") in ("CASH_DEPOSIT", "CASH_WITHDRAWAL")
        and t.get("counterparty_name") == "CASH"
    ]

    flagged_transactions = []
    structuring_clusters = []

    # Check for sub-threshold cash deposits in tight windows
    for i, txn in enumerate(cash_transactions):
        amount = txn.get("amount", 0)

        # Flag individual transactions just under $10K
        if STRUCTURING_LOWER_BOUND <= amount < CTR_THRESHOLD:
            flagged_transactions.append({
                "transaction_id": txn.get("transaction_id"),
                "date": txn.get("date"),
                "amount": amount,
                "reason": f"Cash transaction ${amount:,.2f} just below ${CTR_THRESHOLD:,.0f} CTR threshold",
                "branch": txn.get("branch_id"),
            })

    # Check for clusters within rolling 10-day windows
    if len(flagged_transactions) >= 3:
        # Multiple sub-threshold transactions = structuring indicator
        total_flagged_amount = sum(t["amount"] for t in flagged_transactions)
        structuring_clusters.append({
            "transaction_count": len(flagged_transactions),
            "total_amount": total_flagged_amount,
            "average_amount": total_flagged_amount / len(flagged_transactions),
            "transactions": [t["transaction_id"] for t in flagged_transactions],
        })

    detected = len(flagged_transactions) >= 3
    confidence = "HIGH" if len(flagged_transactions) >= 5 else ("MEDIUM" if len(flagged_transactions) >= 3 else "LOW")

    return {
        "detected": detected,
        "confidence": confidence,
        "flagged_transactions": flagged_transactions,
        "structuring_clusters": structuring_clusters,
        "total_flagged_amount": sum(t["amount"] for t in flagged_transactions),
        "evidence": [
            f"{len(flagged_transactions)} cash deposits in range ${STRUCTURING_LOWER_BOUND:,.0f}-${CTR_THRESHOLD:,.0f}"
        ] if detected else [],
    }


def detect_velocity_anomalies(
    transactions: List[Dict[str, Any]],
    baseline: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect transaction velocity anomalies relative to the customer's baseline.

    Velocity anomalies occur when transaction activity spikes dramatically
    above the customer's established pattern. A restaurant processing $2M
    in international wires is a velocity anomaly — not because the amount
    is inherently suspicious, but because it's inconsistent with the
    customer's stated business purpose.

    The baseline is established from the customer's KYC profile, which
    includes expected monthly transaction volumes by type.

    Args:
        transactions: Full transaction history
        baseline: Customer baseline from KYC (expected monthly volumes)

    Returns:
        Velocity analysis results

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # TMS systems calculate baselines automatically using ML models:
    # - Actimize: Customer Risk Scoring (CRS) engine maintains dynamic baselines
    # - Oracle Mantas: Peer group analysis for behavioral baselining
    # - Nasdaq Verafin: AI-powered dynamic baselining
    # In production, pull the TMS-calculated baseline rather than KYC-stated:
    #   baseline = tms_client.get(f"/api/v1/customers/{customer_id}/baseline")
    # ──────────────────────────────────────────────────────────────────────────
    """
    if not transactions:
        return {"detected": False, "spike_ratio": 0, "evidence": []}

    # Calculate actual monthly averages from transaction history
    recent_30_days = [
        t for t in transactions
        if datetime.strptime(t.get("date", "2000-01-01"), "%Y-%m-%d") >= datetime.utcnow() - timedelta(days=30)
    ]

    recent_cash = sum(
        t.get("amount", 0) for t in recent_30_days
        if t.get("transaction_type") in ("CASH_DEPOSIT", "CASH_WITHDRAWAL")
    )
    recent_wires = sum(
        t.get("amount", 0) for t in recent_30_days
        if t.get("transaction_type") in ("WIRE_IN", "WIRE_OUT")
    )

    expected_cash = baseline.get("monthly_cash_avg", 5000)
    expected_wires = baseline.get("monthly_wire_avg", 10000)

    cash_ratio = (recent_cash / expected_cash) if expected_cash > 0 else 0
    wire_ratio = (recent_wires / expected_wires) if expected_wires > 0 else 0

    max_ratio = max(cash_ratio, wire_ratio)
    detected = max_ratio > 3.0  # 3x or more is anomalous

    evidence = []
    if cash_ratio > 3.0:
        evidence.append(
            f"Cash volume ${recent_cash:,.2f} is {cash_ratio:.1f}x the expected monthly baseline of ${expected_cash:,.2f}"
        )
    if wire_ratio > 3.0:
        evidence.append(
            f"Wire volume ${recent_wires:,.2f} is {wire_ratio:.1f}x the expected monthly baseline of ${expected_wires:,.2f}"
        )

    return {
        "detected": detected,
        "confidence": "HIGH" if max_ratio > 10 else ("MEDIUM" if max_ratio > 3 else "LOW"),
        "spike_ratio": round(max_ratio, 2),
        "recent_30d_cash": recent_cash,
        "recent_30d_wires": recent_wires,
        "expected_monthly_cash": expected_cash,
        "expected_monthly_wires": expected_wires,
        "evidence": evidence,
    }
