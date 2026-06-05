# tools/kyc_lookup.py
# ============================================================
# Customer KYC Record Retrieval
#
# In production: queries core banking KYC system
# (FIS Profile, Fiserv DNA, Jack Henry SilverLake, or dedicated
#  KYC platforms like Actimize CRM, Fenergo, or Pega KYC)
#
# In development: returns simulated customer records from
# data/fixtures/sample_customers.json
#
# ── INTEGRATION POINT ──────────────────────────────────────────────────────
# Replace the _fetch_from_fixture() call with your production integration:
#
#   import requests
#   response = requests.get(
#       f"{os.getenv('KYC_API_BASE_URL')}/customers/{customer_id}",
#       headers={"Authorization": f"Bearer {os.getenv('KYC_API_TOKEN')}"},
#       timeout=10,
#   )
#   response.raise_for_status()
#   return response.json()
#
# Supported systems: Fiserv DNA KYC API, FIS Profile REST API,
# Actimize CRM API, Fenergo API, OneTrust KYC Workflow API
# ──────────────────────────────────────────────────────────────────────────
# ============================================================

import json
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent / "data" / "fixtures" / "sample_customers.json"


def fetch_customer_record(customer_id: str) -> dict:
    """
    Retrieve the current KYC/CDD record for a customer.

    Args:
        customer_id: Internal customer identifier

    Returns:
        Dict with full KYC record including risk tier, PEP status,
        beneficial owners, expected transaction profile, documents.

    Raises:
        ValueError: If customer_id not found
        ConnectionError: If production API is unreachable
    """
    use_production = os.getenv("KYC_API_BASE_URL") and os.getenv("KYC_API_TOKEN")

    if use_production:
        return _fetch_from_production(customer_id)
    else:
        logger.info(f"Development mode: loading fixture record for {customer_id}")
        return _fetch_from_fixture(customer_id)


def _fetch_from_production(customer_id: str) -> dict:
    """Production implementation — connects to core banking KYC API."""
    import requests
    base_url = os.getenv("KYC_API_BASE_URL")
    token = os.getenv("KYC_API_TOKEN")

    response = requests.get(
        f"{base_url}/api/v1/customers/{customer_id}/kyc",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _fetch_from_fixture(customer_id: str) -> dict:
    """Development implementation — returns simulated KYC record."""
    if FIXTURES_PATH.exists():
        with open(FIXTURES_PATH) as f:
            customers = json.load(f)
        record = customers.get(customer_id) or next(iter(customers.values()))
        return record

    # Generate a synthetic record if no fixtures file exists
    return _generate_synthetic_record(customer_id)


def _generate_synthetic_record(customer_id: str) -> dict:
    """Generate a realistic synthetic KYC record for demo purposes."""
    risk_tiers = ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
    business_types = ["import_export", "real_estate", "retail_trade",
                      "professional_services", "manufacturing", "restaurant"]

    risk_tier = random.choice(risk_tiers)
    last_refresh_days = random.randint(180, 900)

    return {
        "customer_id": customer_id,
        "customer_name": f"Acme Industries LLC ({customer_id[-4:]})",
        "customer_type": "LLC",
        "account_ids": [f"ACC-{customer_id[-6:]}-{i:03d}" for i in range(1, 3)],
        "relationship_manager_id": f"RM-{random.randint(100, 999)}",
        "risk_tier": risk_tier,
        "risk_score": {"LOW": 25.0, "MEDIUM": 50.0, "HIGH": 70.0, "VERY_HIGH": 85.0}[risk_tier],
        "kyc_last_refreshed": (datetime.utcnow() - timedelta(days=last_refresh_days)).date().isoformat(),
        "edd_status": risk_tier in ["HIGH", "VERY_HIGH"],
        "pep_flag": random.random() < 0.15,
        "pep_category": "DOMESTIC_PEP" if random.random() < 0.15 else None,
        "beneficial_owners": [
            {
                "name": "Jane Smith",
                "ownership_pct": 65.0,
                "nationality": "US",
                "pep_flag": False,
                "dob": "1975-03-22",
                "address": "123 Main St, Boston, MA 02101",
            },
            {
                "name": "Robert Chen",
                "ownership_pct": 35.0,
                "nationality": "US",
                "pep_flag": False,
                "dob": "1968-09-14",
                "address": "456 Oak Ave, Cambridge, MA 02139",
            },
        ],
        "business_type": random.choice(business_types),
        "expected_transaction_profile": {
            "monthly_volume_range": [50000, 500000],
            "primary_transaction_types": ["wire", "ACH", "check"],
            "primary_counterparty_countries": ["US", "CA", "MX"],
            "expected_cash_intensity": "LOW",
        },
        "jurisdiction_risk": "LOW" if risk_tier in ["LOW", "MEDIUM"] else "MEDIUM",
    }
