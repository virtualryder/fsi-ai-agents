# tools/adverse_media.py
# ============================================================
# Adverse Media Search for KYC/CDD Reviews
#
# Searches for negative news, regulatory actions, and court records
# involving the customer and their beneficial owners.
#
# Production integrations:
#   - LexisNexis Adverse Media (most comprehensive)
#   - Dow Jones Risk & Compliance
#   - Refinitiv World-Check (includes adverse media)
#   - ComplyAdvantage (real-time adverse media monitoring)
#   - Factiva / Dow Jones News Feed
#
# Regulatory basis:
#   FATF R.12 — adverse media screening as part of PEP EDD
#   OCC Heightened Standards — expected for high-risk customers
#   FFIEC BSA/AML Examination Manual — adverse media as CDD element
# ============================================================

import logging
import random
import hashlib
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

SEVERITY_LEVELS = ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

SAMPLE_ADVERSE_CATEGORIES = [
    "fraud", "money_laundering", "tax_evasion", "corruption",
    "regulatory_action", "sanctions_violation", "criminal_investigation",
    "civil_lawsuit", "reputational_risk",
]


def search_adverse_media(
    customer_id: str,
    customer_name: str,
    beneficial_owners: List[Dict[str, Any]],
    trigger_type: str = None,
) -> Dict[str, Any]:
    """
    Search for adverse media on the customer and beneficial owners.

    Args:
        customer_id: Internal customer ID
        customer_name: Legal name to search
        beneficial_owners: List of UBO dicts
        trigger_type: The review trigger (ADVERSE_MEDIA triggers = more thorough search)

    Returns:
        Dict with 'hits' (list) and 'severity' (NONE/LOW/MEDIUM/HIGH/CRITICAL)
    """
    # ── INTEGRATION POINT ────────────────────────────────────────────────────
    # Production: call adverse media API
    #   import requests
    #   response = requests.post(
    #       f"{os.getenv('ADVERSE_MEDIA_API_URL')}/search",
    #       json={"name": customer_name, "include_associates": True},
    #       headers={"Authorization": f"Bearer {os.getenv('ADVERSE_MEDIA_API_KEY')}"},
    #       timeout=30,
    #   )
    #   return response.json()
    # ─────────────────────────────────────────────────────────────────────────

    hits = []

    # If trigger was adverse media, always return at least one finding
    if trigger_type == "ADVERSE_MEDIA":
        hits.extend(_generate_adverse_media_hits(customer_id, customer_name, force=True))
    else:
        hits.extend(_generate_adverse_media_hits(customer_id, customer_name, force=False))

    # Search UBOs (critical for FATF R.12 PEP EDD)
    for ubo in beneficial_owners[:3]:  # Cap at 3 UBOs for performance
        ubo_name = ubo.get("name", "")
        if ubo_name:
            ubo_hits = _generate_adverse_media_hits(
                customer_id + "_UBO_" + ubo_name[:6], ubo_name, force=False, entity_type="UBO"
            )
            hits.extend(ubo_hits)

    # Calculate overall severity
    if not hits:
        severity = "NONE"
    else:
        max_score = max(h.get("relevance_score", 0) for h in hits)
        if max_score >= 0.9 or any(h.get("category") in ["regulatory_action", "criminal_investigation"] for h in hits):
            severity = "CRITICAL"
        elif max_score >= 0.75 or any(h.get("category") in ["fraud", "money_laundering"] for h in hits):
            severity = "HIGH"
        elif max_score >= 0.55:
            severity = "MEDIUM"
        else:
            severity = "LOW"

    return {"hits": hits, "severity": severity}


def _generate_adverse_media_hits(
    seed_key: str,
    entity_name: str,
    force: bool = False,
    entity_type: str = "CUSTOMER",
) -> List[Dict[str, Any]]:
    """Simulate adverse media results. Replace with real API in production."""
    hash_val = int(hashlib.md5(seed_key.encode()).hexdigest()[:8], 16)
    rng = random.Random(hash_val)

    # 8% base rate for adverse media findings; 100% if forced (trigger was adverse media)
    if not force and rng.random() > 0.08:
        return []

    category = rng.choice(SAMPLE_ADVERSE_CATEGORIES)
    relevance = round(rng.uniform(0.55, 0.95), 2)

    return [{
        "source": rng.choice(["Reuters", "Bloomberg", "WSJ", "SEC EDGAR", "DOJ Press Release", "FinCEN Enforcement"]),
        "headline": f"{entity_name} named in {category.replace('_', ' ')} proceedings",
        "date": f"202{rng.randint(3, 5)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "category": category,
        "url": "https://example.com/article",
        "relevance_score": relevance,
        "entity_matched": entity_name,
        "entity_type": entity_type,
    }]
