"""
Historical Patterns Tool — retrieves alert outcome data for scoring signals.

The strongest predictors of false positives are historical FP rates:
- Rule-level FP rate (e.g., CASH_STRUCTURING_10K fires at 87% FP)
- Typology-level FP rate (e.g., all STRUCTURING alerts are 84% FP bank-wide)
- Customer-level outcomes (this customer has 4 prior alerts, all false positives)
- Peer group FP rate (restaurants at HIGH risk = 89% FP)

Production integration: data warehouse query or pre-computed feature store.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from agent.state import HistoricalPatterns

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).parent.parent / "data" / "fixtures"
_HISTORY_FIXTURE = _FIXTURES_DIR / "historical_outcomes.json"


def get_historical_patterns(
    customer_id: str,
    alert_type: str,
    triggered_rule: str,
    business_type: str,
    risk_tier: str,
) -> HistoricalPatterns:
    """
    Assemble all historical pattern signals needed for false positive scoring.

    Production integration:
      - rule_fp_rate / typology_fp_rate: pre-computed nightly in data warehouse,
        cached in Redis or DynamoDB for sub-millisecond lookup during scoring
      - customer_alert_history: AML case management system query
      - peer_group_fp_rate: pre-computed peer cohort table (business_type + risk_tier)

    Falls back to conservative neutral rates (0.5) if data is unavailable.
    """
    data = _load_fixture_history()

    rule_fp_rate = data.get("rule_fp_rates", {}).get(triggered_rule, 0.50)
    typology_fp_rate = data.get("typology_fp_rates", {}).get(alert_type, 0.50)

    peer_key = f"{business_type}_{risk_tier}"
    peer_group_fp_rate = data.get("peer_group_fp_rates", {}).get(peer_key, 0.50)

    customer_history: list[dict] = (
        data.get("customer_alert_history", {}).get(customer_id, [])
    )

    # Customer FP rate derived from history
    customer_fp_rate = _compute_fp_rate(customer_history)

    # Days since most recent similar alert for this customer
    days_since = _days_since_similar(customer_history, alert_type)

    logger.info(
        "Historical patterns | rule_fp=%.0f%% typology_fp=%.0f%% "
        "customer_fp=%.0f%% peer_fp=%.0f%% days_since=%d",
        rule_fp_rate * 100, typology_fp_rate * 100,
        customer_fp_rate * 100, peer_group_fp_rate * 100, days_since,
    )

    return HistoricalPatterns(
        rule_fp_rate=rule_fp_rate,
        typology_fp_rate=typology_fp_rate,
        peer_group_fp_rate=peer_group_fp_rate,
        customer_alert_history=customer_history,
        customer_fp_rate=customer_fp_rate,
        days_since_last_similar_alert=days_since,
    )


def get_rule_fp_rate(rule_id: str) -> float:
    """Look up a single rule's historical FP rate. Returns 0.5 if unknown."""
    data = _load_fixture_history()
    return data.get("rule_fp_rates", {}).get(rule_id, 0.50)


def get_typology_fp_rate(alert_type: str) -> float:
    """Look up a typology's bank-wide historical FP rate. Returns 0.5 if unknown."""
    data = _load_fixture_history()
    return data.get("typology_fp_rates", {}).get(alert_type, 0.50)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_fp_rate(history: list[dict]) -> float:
    if not history:
        return 0.50  # unknown — neutral
    fp_count = sum(1 for a in history if a.get("outcome") == "FALSE_POSITIVE")
    return fp_count / len(history)


def _days_since_similar(history: list[dict], alert_type: str) -> int:
    """Returns -1 if no prior alert of this type exists."""
    from datetime import datetime, date

    similar_dates = []
    for entry in history:
        if entry.get("alert_type") == alert_type:
            try:
                d = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                similar_dates.append(d)
            except (ValueError, KeyError):
                continue

    if not similar_dates:
        return -1

    most_recent = max(similar_dates)
    today = date.today()
    return (today - most_recent).days


def _load_fixture_history() -> dict:
    try:
        with open(_HISTORY_FIXTURE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Fixture file not found: %s", _HISTORY_FIXTURE)
        return {}
