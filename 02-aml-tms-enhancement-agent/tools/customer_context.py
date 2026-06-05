"""
Customer Context Tool — lightweight customer profile lookup for alert scoring.

This is intentionally lighter than the investigation agent's full customer_profile.py.
We only fetch what we need to score the alert (risk tier, expected volume, FP history).
A full KYC deep-dive happens in the investigation agent if the alert survives.

Production integration: Temenos T24 | FIS Modern Banking | Jack Henry | Fiserv
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from agent.state import CustomerSummary

logger = logging.getLogger(__name__)

_FIXTURES_DIR = Path(__file__).parent.parent / "data" / "fixtures"
_CUSTOMERS_FIXTURE = _FIXTURES_DIR / "sample_customers.json"


def get_customer_summary(customer_id: str) -> Optional[CustomerSummary]:
    """
    Return a lightweight customer profile for alert scoring.

    Fetched fields: risk_tier, business_type, expected monthly volumes,
    account age, open investigations, prior SARs/CTRs, PEP/EDD status.

    Production integration:
      Temenos T24:    GET /party/{customer_id}/riskProfile
      FIS:            GET /customers/{customer_id}/summary
      Jack Henry:     GET /v1/customers/{customer_id}?fields=risk,edd,volumes

    Returns None if customer is not found (alert will fall back to manual review).
    """
    customers = _load_fixture_customers()
    profile = customers.get(customer_id)

    if not profile:
        logger.warning("Customer %s not found — alert will route to manual review", customer_id)
        return None

    logger.info(
        "Customer loaded | id=%s name=%s risk_tier=%s fp_rate=%.0f%%",
        customer_id,
        profile.get("full_name", "Unknown"),
        profile.get("risk_tier", "UNKNOWN"),
        profile.get("historical_fp_rate", 0.5) * 100,
    )
    return CustomerSummary(**profile)


def get_open_investigation_count(customer_id: str) -> int:
    """
    Return the count of open AML investigations for this customer.

    An open investigation is a strong signal against suppression — if analysts
    are already looking at this customer, new alerts should reach them.

    Production integration: Case management system (NICE Actimize Case Manager,
    ServiceNow GRC) or investigation agent database.
    """
    profile = _load_fixture_customers().get(customer_id, {})
    return profile.get("open_investigation_count", 0)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _load_fixture_customers() -> dict:
    try:
        with open(_CUSTOMERS_FIXTURE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Fixture file not found: %s", _CUSTOMERS_FIXTURE)
        return {}
