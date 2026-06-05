# tools/customer_profile.py
# ============================================================
# Core Banking / KYC System Integration
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   The customer profile is the context layer for every investigation.
#   Suspicious activity is defined RELATIVE to the customer's expected behavior.
#   A $100K wire is suspicious from a barber shop, routine from a real estate LLC.
#   Without the customer profile, you cannot assess whether transactions are anomalous.
#   This is the "KNOW your customer" in KYC.
#
# REGULATORY REQUIREMENT SERVED:
#   - BSA CDD Rule (31 CFR § 1010.230): Customer Due Diligence final rule
#     requires banks to collect and verify: name, DOB/EIN, address, beneficial owners
#   - FATF R.10: Customer due diligence measures
#   - FATF R.12: EDD for Politically Exposed Persons
#   - FATF R.17: Beneficial ownership identification
#   - USA PATRIOT Act § 326: Customer Identification Program (CIP)
#   - OCC: Periodic risk-based CDD refresh requirements
#
# REAL VENDOR SYSTEMS THAT PROVIDE THIS:
#   Core Banking (source of truth for account data):
#   - Temenos T24 / Transact: Used by 50+ of top 150 banks globally
#   - FIS Modern Banking Platform: North American community/regional banks
#   - Jack Henry Symitar: Credit unions, community banks
#   - Fiserv DNA: Community bank focused
#   - Finacle (Infosys): Large international banks
#   - Oracle FLEXCUBE: Global tier-1 banks
#
#   KYC / CDD Platforms (may be separate from core banking):
#   - Acuant: Digital KYC/ID verification
#   - Jumio: AI-powered identity verification
#   - Refinitiv World-Check One: KYC risk intelligence + screening
#   - NICE Actimize KYC: Integrated with TMS
#   - ComplyAdvantage: AI-driven KYC risk platform
# ============================================================

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).parent.parent / "data" / "fixtures"


def _load_fixture(filename: str) -> Any:
    """Load a JSON fixture file."""
    try:
        with open(_FIXTURE_PATH / filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load fixture {filename}: {e}")
        return {}


# ── INTEGRATION POINT ────────────────────────────────────────────────────────
# PRODUCTION: Replace mock functions with real core banking API calls.
#
# Temenos T24 REST API example:
#   from requests import Session
#   session = Session()
#   session.headers.update({
#       "Authorization": f"Bearer {get_t24_token()}",
#       "Content-Type": "application/json"
#   })
#   base_url = os.getenv("CORE_BANKING_API_URL")  # e.g., https://bank.temenos.com/api/v1
#
# FIS Modern Banking Platform:
#   api_key = os.getenv("CORE_BANKING_API_KEY")
#   response = requests.get(
#       f"{os.getenv('CORE_BANKING_API_URL')}/customers/{customer_id}",
#       headers={"X-API-Key": api_key}
#   )
#
# Authentication considerations for core banking:
#   - Most core banking APIs use OAuth 2.0 with short-lived tokens (1-4 hours)
#   - mTLS is required in many high-security environments
#   - IP whitelisting is standard — ensure agent's egress IP is whitelisted
# ─────────────────────────────────────────────────────────────────────────────


def get_customer_profile(customer_id: str) -> Dict[str, Any]:
    """
    Retrieve the complete KYC/CDD profile for a customer.

    This function returns everything the bank knows about the customer:
    - Identity information (name, DOB, address, ID documents)
    - Risk classification (risk tier, EDD status, onboarding date)
    - Regulatory flags (PEP status, high-risk industry, adverse action history)
    - Business information for entities (type, industry, revenue, employees)
    - Account relationships (all accounts at this institution)
    - Expected activity profile (the baseline for anomaly detection)

    Args:
        customer_id: Internal customer identifier (e.g., "CUST-001234")

    Returns:
        Dictionary containing full customer profile. Key fields:
        - customer_id: Internal ID
        - customer_type: "INDIVIDUAL" or "ENTITY"
        - full_name / entity_name: Legal name
        - risk_tier: "LOW" / "MEDIUM" / "HIGH" / "VERY_HIGH"
        - edd_status: "NOT_REQUIRED" / "ACTIVE" / "LAPSED" / "COMPLETED"
        - pep_flag: bool — Politically Exposed Person status
        - kyc_date: Date of last KYC review (ISO 8601)
        - accounts: List of account IDs at this institution
        - beneficial_owners: UBO list (for legal entities)
        - expected_monthly_cash: Stated expected monthly cash activity
        - expected_monthly_wires: Stated expected monthly wire activity
        - business_type: Industry / NAICS code description
        - onboarding_date: Date account relationship was established
        - prior_sars: Count of prior SARs filed on this customer
        - ctrs_filed: Count of CTRs filed on this customer

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with real core banking API call:
    #   response = session.get(f"{base_url}/customers/{customer_id}")
    #   raw_profile = response.json()
    #   return _normalize_customer_profile(raw_profile)  # Field mapping function
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Load from fixture data first
    all_customers = _load_fixture("sample_customers.json")
    if isinstance(all_customers, list):
        for customer in all_customers:
            if customer.get("customer_id") == customer_id:
                logger.debug(f"[customer_profile] Found fixture data for {customer_id}")
                return customer

    # Generate mock profile if no fixture match
    logger.debug(f"[customer_profile] Generating mock profile for {customer_id}")

    # Different profiles based on customer ID pattern
    if "CUST-001" in customer_id:
        return _build_cash_intensive_individual_profile(customer_id)
    elif "CUST-002" in customer_id:
        return _build_high_risk_entity_profile(customer_id)
    elif "CUST-003" in customer_id:
        return _build_dormant_individual_profile(customer_id)
    else:
        return _build_generic_profile(customer_id)


def _build_cash_intensive_individual_profile(customer_id: str) -> Dict[str, Any]:
    """Profile for a cash-intensive business owner (restaurant)."""
    return {
        "customer_id": customer_id,
        "customer_type": "INDIVIDUAL",
        "full_name": "Carlos M. Testowner",
        "aliases": ["Carlos Testowner", "C. Testowner"],
        "date_of_birth": "1975-03-15",
        "ssn_masked": "***-**-4521",
        "address": "742 Evergreen Terrace, Springfield, IL 62701",
        "country_of_residence": "US",
        "citizenship": "US",
        "risk_tier": "HIGH",  # High due to cash-intensive business
        "edd_status": "ACTIVE",
        "edd_open_date": "2023-06-15",
        "edd_notes": "Cash-intensive business (restaurant). EDD opened due to high cash volumes relative to peer group.",
        "pep_flag": False,
        "kyc_date": "2023-06-15",
        "onboarding_date": "2018-09-01",
        "customer_since_years": 6,
        "id_document_type": "US_PASSPORT",
        "id_document_number": "***6821",
        "id_expiry": "2030-03-14",
        "occupation": "Restaurant Owner",
        "employer": "El Sombrero Restaurant LLC",
        "business_type": "Food Service / Restaurant (NAICS 722511)",
        "annual_revenue_stated": 850000,
        "expected_monthly_cash": 45000,  # Restaurant — high cash expected
        "expected_monthly_wires": 5000,  # Low wire expectation for a restaurant
        "accounts": [f"{customer_id}-ACC001", f"{customer_id}-ACC002"],
        "beneficial_owners": [],  # Individual account — no UBO structure
        "prior_sars": 0,
        "ctrs_filed": 12,  # 12 CTRs in prior years — consistent with restaurant business
        "risk_factors_on_file": [
            "Cash-intensive business (restaurant)",
            "Multiple branch deposits",
            "High annual cash volume relative to stated revenue",
        ],
        "last_enhanced_review_date": "2024-01-10",
        "relationship_manager": "RM-Sarah Johnson",
        "account_purpose": "Business operating account for restaurant revenue",
    }


def _build_high_risk_entity_profile(customer_id: str) -> Dict[str, Any]:
    """Profile for a high-risk legal entity with complex beneficial ownership."""
    return {
        "customer_id": customer_id,
        "customer_type": "ENTITY",
        "entity_name": "Meridian Capital Holdings LLC",
        "aliases": ["Meridian Capital", "MCH LLC"],
        "entity_type": "Limited Liability Company",
        "formation_state": "Delaware",
        "formation_date": "2021-11-30",  # Relatively new entity
        "formation_country": "US",
        "registered_agent": "Corporate Services of Delaware Inc.",  # Registered agent = shell indicator
        "registered_address": "1209 Orange Street, Wilmington, DE 19801",  # Common registered agent address
        "operating_address": "45 Wall Street Suite 1200, New York, NY 10005",
        "ein_masked": "**-***4721",
        "risk_tier": "VERY_HIGH",
        "edd_status": "ACTIVE",
        "edd_open_date": "2022-03-01",
        "pep_flag": True,  # UBO is a PEP
        "pep_basis": "Beneficial owner Dmitri Testovsky held ministerial position in prior government",
        "kyc_date": "2022-03-01",  # KYC is 2+ years old — may be stale
        "onboarding_date": "2022-01-15",
        "business_type": "Investment Holding Company / Private Equity",
        "industry_code": "NAICS 523910",
        "annual_revenue_stated": 5000000,
        "expected_monthly_cash": 0,  # Investment company — no cash expected
        "expected_monthly_wires": 500000,
        "employees_stated": 3,  # Very few employees for stated revenue = shell indicator
        "beneficial_owners": [
            {
                "name": "Dmitri A. Testovsky",
                "date_of_birth": "1968-07-22",
                "country_of_residence": "CY",  # Cyprus — offshore jurisdiction
                "citizenship": "RU",  # Russian citizen
                "ownership_percentage": 65,
                "control_type": "DIRECT_OWNERSHIP",
                "pep_flag": True,
                "pep_position": "Former Deputy Minister of Economic Development, Russia (2015-2019)",
                "id_verified": True,
                "address": "123 Nicosia Drive, Nicosia, Cyprus",
            },
            {
                "name": "Elena V. Testovsky",
                "date_of_birth": "1972-04-11",
                "country_of_residence": "CY",
                "citizenship": "RU",
                "ownership_percentage": 35,
                "control_type": "DIRECT_OWNERSHIP",
                "pep_flag": False,
                "relationship_to_pep": "Spouse of Dmitri Testovsky (associated PEP)",
                "id_verified": True,
            },
        ],
        "accounts": [f"{customer_id}-ACC001"],
        "prior_sars": 1,  # Prior SAR filed on this entity
        "ctrs_filed": 0,
        "risk_factors_on_file": [
            "Beneficial owner is a Foreign PEP (former Russian government minister)",
            "Beneficial owner resides in Cyprus (offshore financial center)",
            "Complex beneficial ownership structure",
            "Recently formed Delaware LLC (2021) with minimal operational footprint",
            "Prior SAR filed (2023)",
        ],
        "relationship_manager": "RM-Michael Chen",
        "account_purpose": "Holding company for international investment portfolio",
    }


def _build_dormant_individual_profile(customer_id: str) -> Dict[str, Any]:
    """Profile for a previously dormant individual account."""
    return {
        "customer_id": customer_id,
        "customer_type": "INDIVIDUAL",
        "full_name": "Jennifer L. Testaccount",
        "aliases": ["Jennifer Testaccount", "J. Testaccount"],
        "date_of_birth": "1988-11-02",
        "ssn_masked": "***-**-8832",
        "address": "2847 Maple Avenue, Apartment 4B, Chicago, IL 60601",
        "country_of_residence": "US",
        "citizenship": "US",
        "risk_tier": "MEDIUM",
        "edd_status": "NOT_REQUIRED",
        "pep_flag": False,
        "kyc_date": "2019-07-20",  # 5+ year old KYC — stale!
        "onboarding_date": "2019-07-20",
        "business_type": "Individual / Personal Account",
        "occupation": "Marketing Consultant",
        "annual_revenue_stated": 95000,
        "expected_monthly_cash": 500,
        "expected_monthly_wires": 0,  # No wire capability at onboarding
        "accounts": [f"{customer_id}-ACC001"],
        "beneficial_owners": [],
        "prior_sars": 0,
        "ctrs_filed": 0,
        "last_activity_before_dormancy": "2023-11-15",
        "dormancy_period_months": 6,
        "wire_capability_added": "2024-05-01",  # Wire capability recently added — unusual
        "wire_capability_added_notes": "Customer requested international wire capability via online banking. Not reviewed by relationship manager.",
        "risk_factors_on_file": [
            "Account dormant for 6+ months",
            "International wire capability recently added without RM review",
            "KYC file over 5 years old — refresh overdue for MEDIUM risk",
        ],
        "relationship_manager": None,  # No RM assigned for retail account
        "account_purpose": "Personal checking account",
    }


def _build_generic_profile(customer_id: str) -> Dict[str, Any]:
    """Generic fallback profile for unrecognized customer IDs."""
    return {
        "customer_id": customer_id,
        "customer_type": "INDIVIDUAL",
        "full_name": f"Test Customer {customer_id}",
        "aliases": [],
        "date_of_birth": "1985-01-01",
        "country_of_residence": "US",
        "citizenship": "US",
        "risk_tier": "MEDIUM",
        "edd_status": "NOT_REQUIRED",
        "pep_flag": False,
        "kyc_date": (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"),
        "onboarding_date": "2020-01-01",
        "expected_monthly_cash": 3000,
        "expected_monthly_wires": 0,
        "accounts": [f"{customer_id}-ACC001"],
        "beneficial_owners": [],
        "prior_sars": 0,
        "ctrs_filed": 0,
        "business_type": "Individual / Personal Account",
    }


def get_account_details(account_id: str) -> Dict[str, Any]:
    """
    Retrieve detailed information for a specific account.

    Account-level data provides context beyond the customer profile:
    - What type of account is this? (checking, savings, business)
    - When was it opened? (recently opened accounts are higher risk)
    - What is the current balance vs. typical balance?
    - Who are the authorized signatories? (for business accounts)
    - Has the account been flagged before?

    Args:
        account_id: Bank account identifier

    Returns:
        Dictionary with account details

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with core banking API call:
    #   response = session.get(f"{base_url}/accounts/{account_id}")
    #   return response.json()
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Extract account type from ID suffix if using mock data
    account_type = "BUSINESS_CHECKING" if "ACC001" in account_id else "SAVINGS"

    return {
        "account_id": account_id,
        "account_type": account_type,
        "account_status": "ACTIVE",
        "open_date": "2019-07-20",
        "current_balance": round(50000 + (hash(account_id) % 200000), 2),
        "average_monthly_balance_ytd": round(25000 + (hash(account_id) % 100000), 2),
        "currency": "USD",
        "signatories": [
            {
                "name": f"Primary Signatory for {account_id}",
                "authority_level": "FULL",
                "added_date": "2019-07-20",
            }
        ],
        "international_wire_enabled": True,
        "cash_limit_daily": 25000,
        "wire_limit_daily": 500000,
        "last_statement_date": (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "overdraft_count_ytd": 0,
        "frozen": False,
        "frozen_reason": None,
        "branch_of_record": "Main Branch",
    }


def get_beneficial_owners(entity_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve Ultimate Beneficial Owners (UBOs) for a legal entity.

    The FinCEN Customer Due Diligence (CDD) Rule (31 CFR § 1010.230) requires
    banks to collect and verify the identity of all beneficial owners who:
    1. Own 25%+ of the entity's equity interests (ownership prong)
    2. Exercise control over the entity (control prong — one person required)

    OFAC's 50% Rule extends this: entities owned 50%+ by an SDN are
    themselves subject to OFAC sanctions — even if not named on the list.
    This makes accurate UBO data critical for sanctions screening.

    Args:
        entity_id: Internal identifier for the legal entity customer

    Returns:
        List of beneficial owner dictionaries

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # In production, UBO data may come from multiple sources:
    # 1. Bank's KYC system (what the customer self-reported + your verification)
    # 2. Corporate registry APIs:
    #    - OpenCorporates API: Global corporate registry data
    #    - Dun & Bradstreet / Hoovers: Corporate intelligence
    #    - Sayari: Network intelligence for complex structures
    #    - BvD Orbis: Global company ownership data
    # 3. FinCEN Beneficial Ownership Registry (effective 2024):
    #    - New BOI reporting requirement — FinCEN's new registry
    #    - API: https://boiefiling.fincen.gov/api/v1/
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Get from the customer profile which already has this data
    customer_profile = get_customer_profile(entity_id)
    return customer_profile.get("beneficial_owners", [])
