# tools/watchlist_screener.py
# ============================================================
# Watchlist Screening for KYC/CDD Reviews
#
# Screens customer, beneficial owners, and counterparties against:
#   - OFAC SDN (Specially Designated Nationals) — MANDATORY
#   - OFAC Consolidated Sanctions List
#   - PEP lists (Refinitiv World-Check, LexisNexis Bridger, Dow Jones)
#   - EU Consolidated Financial Sanctions List
#   - UN Security Council Consolidated List
#   - HM Treasury Financial Sanctions (UK)
#   - Internal bank watchlist
#
# Production integration options:
#   - Refinitiv World-Check API (most comprehensive)
#   - LexisNexis Bridger Insight XG
#   - Dow Jones Risk & Compliance
#   - NICE Actimize Watchlist Management
#   - ComplyAdvantage
#
# Regulatory basis:
#   OFAC IEEPA — legal obligation to screen against SDN list
#   FATF R.12 — PEP identification and enhanced due diligence
#   USA PATRIOT Act § 326 — CIP screening requirements
# ============================================================

import logging
import random
import hashlib
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def screen_all_parties(
    customer_id: str,
    customer_name: str,
    beneficial_owners: List[Dict[str, Any]],
    account_ids: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Screen customer and all beneficial owners against all watchlists.

    Args:
        customer_id: Internal customer ID
        customer_name: Legal name to screen
        beneficial_owners: List of UBO dicts with 'name' and 'nationality'
        account_ids: Account numbers (for OFAC entity screening)

    Returns:
        List of screening hit dicts. Empty list = all clear.
    """
    # ── INTEGRATION POINT ────────────────────────────────────────────────────
    # Replace with production screening API:
    #   import requests
    #   payload = {"name": customer_name, "type": "individual_or_entity"}
    #   response = requests.post(
    #       f"{os.getenv('SCREENING_API_URL')}/screen",
    #       json=payload,
    #       headers={"x-api-key": os.getenv("SCREENING_API_KEY")},
    #       timeout=20,
    #   )
    #   hits = response.json().get("hits", [])
    # ─────────────────────────────────────────────────────────────────────────

    all_hits = []

    # Screen primary customer
    customer_hits = _screen_entity(customer_id, customer_name, "CUSTOMER")
    all_hits.extend(customer_hits)

    # Screen all beneficial owners (FinCEN CDD Rule — UBO screening required)
    for ubo in beneficial_owners:
        ubo_name = ubo.get("name", "")
        if ubo_name:
            ubo_hits = _screen_entity(customer_id + "_UBO_" + ubo_name[:8], ubo_name, "BENEFICIAL_OWNER")
            all_hits.extend(ubo_hits)

    if all_hits:
        logger.warning(f"Watchlist screening for {customer_name}: {len(all_hits)} hits found")
    else:
        logger.info(f"Watchlist screening for {customer_name}: All clear")

    return all_hits


def _screen_entity(seed_key: str, entity_name: str, entity_type: str) -> List[Dict[str, Any]]:
    """
    Simulate watchlist screening for a single entity.
    In production: replace with real API call to screening vendor.
    """
    # Deterministic simulation based on entity name + seed
    hash_val = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16)
    rng = random.Random(hash_val)

    hits = []

    # ~5% chance of a PEP hit (realistic PEP base rate in commercial portfolios)
    if rng.random() < 0.05:
        hits.append({
            "screened_entity": entity_name,
            "entity_type": entity_type,
            "list_name": "Refinitiv World-Check PEP List",
            "match_type": "PEP",
            "match_score": round(rng.uniform(0.75, 0.95), 2),
            "hit_type": "POTENTIAL_MATCH",
            "hit_details": {
                "matched_name": entity_name,
                "category": "DOMESTIC_PEP",
                "description": "Government official / politically connected individual",
                "list_date": "2024-01-15",
            },
        })

    # ~1% chance of OFAC hit (triggers mandatory escalation)
    if rng.random() < 0.01:
        hits.append({
            "screened_entity": entity_name,
            "entity_type": entity_type,
            "list_name": "OFAC SDN List",
            "match_type": "OFAC_SDN",
            "match_score": round(rng.uniform(0.85, 0.99), 2),
            "hit_type": "CONFIRMED_MATCH",
            "hit_details": {
                "matched_name": entity_name,
                "SDN_id": f"SDN-{rng.randint(10000, 99999)}",
                "designation_reason": "Designated under IEEPA/CACR",
                "program": "CUBA",
                "list_date": "2023-06-20",
            },
        })

    return hits
