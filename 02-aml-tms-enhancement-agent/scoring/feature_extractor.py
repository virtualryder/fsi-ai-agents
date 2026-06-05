"""
Feature Extractor — transforms raw TMS alert + customer/historical data
into a structured ScoringFeatures dict for the scoring pipeline.

Features are designed to be interpretable by the LLM and usable by the
rule-based pre-filter without additional processing.
"""
from __future__ import annotations

import logging
from datetime import datetime, date

from agent.state import RawAlert, CustomerSummary, HistoricalPatterns, ScoringFeatures

logger = logging.getLogger(__name__)

# Countries classified as high-risk by FinCEN, FATF, or OFAC
HIGH_RISK_COUNTRIES = {
    "AF", "BY", "BI", "CF", "CN", "CD", "CU", "ER", "ET", "GN", "GW",
    "HT", "IR", "IQ", "KP", "LB", "LY", "ML", "MM", "NI", "PA", "PK",
    "RU", "SO", "SS", "SD", "SY", "TZ", "UG", "UA", "VE", "VG", "YE",
    # Offshore financial centers with secrecy concerns
    "KY", "BZ", "BS", "CY", "MT", "SC", "MU",
}

MONTH_END_DAYS = {28, 29, 30, 31}  # last 4 days of month flagged as month-end


def extract_features(
    raw_alert: RawAlert,
    customer: CustomerSummary,
    history: HistoricalPatterns,
) -> ScoringFeatures:
    """
    Build the full ScoringFeatures dict from raw inputs.

    All derived values are explicit and traceable — no black-box transformations.
    """
    raw_data = raw_alert.get("raw_data", {})
    alert_date_str = raw_alert.get("alert_date", "")
    alert_date = _parse_date(alert_date_str)

    # ── Amount vs. expected volume ratio ────────────────────────────────────
    expected = _expected_volume_for_alert_type(
        raw_alert["alert_type"], customer
    )
    amount_vs_expected = (
        raw_alert["amount"] / expected if expected > 0 else 10.0
    )

    # ── High-risk geography ──────────────────────────────────────────────────
    destination_countries: list[str] = raw_data.get("destination_countries", [])
    origin_countries: list[str] = raw_data.get("countries", [])
    all_countries = set(destination_countries + origin_countries)
    high_risk_geo = bool(all_countries & HIGH_RISK_COUNTRIES)

    # ── Temporal signals ─────────────────────────────────────────────────────
    is_weekend = alert_date.weekday() >= 5 if alert_date else False
    is_month_end = alert_date.day in MONTH_END_DAYS if alert_date else False

    # ── Customer FP rate from history ────────────────────────────────────────
    customer_fp_rate = _compute_customer_fp_rate(history.get("customer_alert_history", []))

    # ── Days since last similar alert ────────────────────────────────────────
    days_since = _days_since_last_similar(
        history.get("customer_alert_history", []),
        raw_alert["alert_type"],
        alert_date,
    )

    return ScoringFeatures(
        # Alert characteristics
        alert_type=raw_alert["alert_type"],
        triggered_rule=raw_alert["triggered_rule"],
        tms_severity=raw_alert["severity"],
        amount_usd=raw_alert["amount"],
        transaction_count=raw_data.get("transaction_count", 1),
        time_window_days=raw_data.get("time_window_days", 1),

        # Customer characteristics
        risk_tier=customer["risk_tier"],
        account_age_days=customer["account_age_days"],
        business_type=customer["business_type"],
        amount_vs_expected_ratio=round(amount_vs_expected, 4),
        pep_flag=customer["pep_flag"],
        edd_active=customer["edd_active"],
        prior_sars_filed=customer["prior_sars_filed"],
        prior_ctrs_filed=customer["prior_ctrs_filed"],

        # Historical signals
        rule_fp_rate=history.get("rule_fp_rate", 0.5),
        typology_fp_rate=history.get("typology_fp_rate", 0.5),
        peer_group_fp_rate=history.get("peer_group_fp_rate", 0.5),
        customer_historical_fp_rate=customer_fp_rate,
        customer_prior_alert_count=len(history.get("customer_alert_history", [])),
        days_since_last_similar_alert=days_since,

        # Contextual signals
        has_open_investigation=customer["open_investigation_count"] > 0,
        high_risk_geography=high_risk_geo,
        is_weekend=is_weekend,
        is_month_end=is_month_end,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _expected_volume_for_alert_type(alert_type: str, customer: CustomerSummary) -> float:
    """Return the most relevant expected volume benchmark for the alert type."""
    wire_types = {"HIGH_RISK_GEOGRAPHY", "RAPID_MOVEMENT", "LAYERING"}
    if alert_type in wire_types:
        return customer.get("expected_monthly_wire_volume", 0.0)
    return customer.get("expected_monthly_cash_volume", 0.0)


def _compute_customer_fp_rate(alert_history: list[dict]) -> float:
    """Compute fraction of past alerts that were false positives."""
    if not alert_history:
        return 0.5  # unknown — treat as neutral
    fp_count = sum(1 for a in alert_history if a.get("outcome") == "FALSE_POSITIVE")
    return fp_count / len(alert_history)


def _days_since_last_similar(
    alert_history: list[dict],
    alert_type: str,
    reference_date: date | None,
) -> int:
    """
    Return days since the customer's most recent alert of the same typology.
    Returns -1 if no prior similar alert exists.
    """
    if not reference_date:
        return -1

    similar_dates: list[date] = []
    for a in alert_history:
        if a.get("alert_type") == alert_type:
            d = _parse_date(a.get("date", ""))
            if d:
                similar_dates.append(d)

    if not similar_dates:
        return -1

    most_recent = max(similar_dates)
    return (reference_date - most_recent).days


def _parse_date(date_str: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None
