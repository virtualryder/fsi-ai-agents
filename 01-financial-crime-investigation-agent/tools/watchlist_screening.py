# tools/watchlist_screening.py
# ============================================================
# Watchlist and Sanctions Screening Integration
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   Sanctions screening is a LEGAL REQUIREMENT for every US financial institution.
#   Transacting with an OFAC-designated entity — even unknowingly — can result in
#   enormous penalties. OFAC operates on a strict liability basis with very limited
#   safe harbor. Beyond OFAC, PEP and adverse list screening helps identify high-risk
#   customers who require Enhanced Due Diligence.
#
# REGULATORY REQUIREMENTS SERVED:
#   - OFAC SDN: Mandatory. Executive Order 13224 (terrorism), IEEPA (31 USC §§ 1701-1707)
#   - OFAC 50% Rule (2014): Entities majority-owned by SDNs are also blocked
#   - OFAC: Civil penalties up to $20M per violation; criminal penalties with imprisonment
#   - PEP Screening: FATF Recommendation 12 — EDD for politically exposed persons
#   - EU Sanctions: Binding on EU-connected transactions
#   - UN Consolidated List: International obligation under UN Charter
#   - USA PATRIOT Act § 312: EDD requirements for foreign bank accounts
#
# REAL VENDOR SYSTEMS THAT PROVIDE THIS:
#   Tier 1 — Enterprise (used by top 50 US banks):
#   - Refinitiv World-Check One (now LSEG): Gold standard, 6M+ risk profiles
#   - Dow Jones Risk & Compliance: High-quality journalism-sourced data
#   - LexisNexis Bridger Insight XG: Strong adverse media integration
#   - NICE Actimize Watch List Filtering (WLF): Integrated with TMS
#
#   Tier 2 — Regional/Community Banks:
#   - ComplyAdvantage: API-first, real-time screening
#   - Napier AI: ML-powered screening with lower false positive rates
#   - Accuity (Fircosoft): SWIFT-certified sanctions screening
#   - AML Partners: RegTek suite for community banks
#
#   Government / Free Sources:
#   - OFAC SDN: https://sanctionssearch.ofac.treas.gov/
#   - UN Consolidated List: https://www.un.org/securitycouncil/content/un-sc-consolidated-list
#   - EU Financial Sanctions: https://webgate.ec.europa.eu/fsd/fsf
#   - HM Treasury UK Sanctions: https://www.gov.uk/government/collections/financial-sanctions-regime
# ============================================================

import json
import logging
import random
from datetime import datetime
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
        return []


# ── INTEGRATION POINT ────────────────────────────────────────────────────────
# PRODUCTION: Replace mock screening with real vendor API calls.
#
# Refinitiv World-Check One API example:
#   import requests
#   api_key = os.getenv("WORLD_CHECK_API_KEY")
#   api_secret = os.getenv("WORLD_CHECK_API_SECRET")
#   # World-Check uses HMAC authentication
#   timestamp = int(time.time())
#   signature = generate_hmac_signature(api_key, api_secret, timestamp)
#   headers = {
#       "Authorization": f"Credential={api_key}, SignedHeaders=host;date, Signature={signature}",
#       "Date": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
#   }
#   payload = {
#       "entityType": "INDIVIDUAL" or "ORGANISATION",
#       "names": [{"name": name, "type": "PRIMARY"}],
#       "dateOfBirth": dob,  # Reduces false positives significantly
#       "nationality": country,
#       "groupIds": ["RISK_INTELLIGENCE"],  # World-Check group to search
#   }
#   response = requests.post(
#       "https://rms-world-check-one-api.thomsonreuters.com/v1/cases",
#       headers=headers, json=payload
#   )
#   return _parse_worldcheck_response(response.json())
#
# ComplyAdvantage API (simpler, REST-native):
#   response = requests.post(
#       "https://api.complyadvantage.com/searches",
#       json={"search_term": name, "fuzziness": 0.7, "filters": {"types": ["sanction", "pep"]}},
#       headers={"Authorization": f"Token {os.getenv('COMPLY_ADVANTAGE_API_KEY')}"}
#   )
#   hits = response.json()["content"]["data"]["hits"]
# ─────────────────────────────────────────────────────────────────────────────

# Mock SDN-like entries for demonstration
MOCK_SDN_ENTRIES = [
    {
        "sdn_id": "SDN-12847",
        "name": "Al-Nusra Financial Services",
        "aliases": ["Al Nusra FS", "ANF Ltd"],
        "designation_reason": "SDGT — Material support to designated terrorist organization",
        "designation_date": "2019-03-15",
        "country": "SY",
        "type": "ENTITY",
        "programs": ["SDGT"],
    },
    {
        "sdn_id": "SDN-09234",
        "name": "Viktor Testperson",
        "aliases": ["V. Testperson", "Viktor T."],
        "designation_reason": "EO 13685 — Crimea-related sanctions",
        "designation_date": "2022-04-01",
        "country": "RU",
        "type": "INDIVIDUAL",
        "programs": ["UKRAINE-EO13685"],
    },
]

MOCK_PEP_ENTRIES = [
    {
        "pep_id": "PEP-44521",
        "name": "Dmitri A. Testovsky",
        "aliases": ["D. Testovsky"],
        "position": "Former Deputy Minister of Economic Development, Russia",
        "country": "RU",
        "start_date": "2015-01-01",
        "end_date": "2019-12-31",
        "pep_tier": "TIER_1",  # Senior government official
        "family_members": ["Elena V. Testovsky (spouse)"],
    },
]


def _fuzzy_name_match(name1: str, name2: str, threshold: float = 0.75) -> float:
    """
    Simple fuzzy name matching for demonstration.
    In production, use a proper fuzzy matching library with transliteration support.

    Real screening tools use:
    - Jaro-Winkler distance for name similarity
    - Soundex/Metaphone for phonetic matching
    - Transliteration for Cyrillic, Arabic, Chinese names
    - Nickname/alias expansion tables

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with:
    #   from fuzzywuzzy import fuzz
    #   return fuzz.ratio(name1.lower(), name2.lower()) / 100
    # Or for more accurate results:
    #   import jellyfish
    #   return jellyfish.jaro_winkler_similarity(name1.lower(), name2.lower())
    # ──────────────────────────────────────────────────────────────────────────
    """
    name1_tokens = set(name1.lower().split())
    name2_tokens = set(name2.lower().split())

    if not name1_tokens or not name2_tokens:
        return 0.0

    intersection = name1_tokens & name2_tokens
    union = name1_tokens | name2_tokens

    jaccard_score = len(intersection) / len(union)
    return jaccard_score


def screen_against_ofac(
    name: str,
    dob: Optional[str] = None,
    country: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Screen a name against the OFAC Specially Designated Nationals (SDN) list.

    OFAC screening is binary — there is no "good enough" compliance.
    Facilitating a transaction with an SDN, even unknowingly, can result in:
    - Civil monetary penalty: $20M+ per transaction
    - Criminal penalty: Up to 20 years imprisonment for willful violations
    - Asset blocking: Requirement to freeze blocked property
    - OFAC reporting: Must report blocked property within 10 business days

    The match threshold is critically important:
    - Too strict (exact only): Misses common name variations, transliterations
    - Too loose (high fuzzy): Massive false positive rate, investigation gridlock
    - Industry standard: 85%+ fuzzy match triggers a hit requiring human review

    Args:
        name: Full legal name to screen (individual or entity)
        dob: Date of birth in YYYY-MM-DD format (reduces false positives)
        country: Country of residence/incorporation (two-letter ISO code)

    Returns:
        Dictionary with screening result:
        - hit: bool — whether a match was found
        - list_type: "OFAC_SDN" if hit
        - match_score: 0-100 confidence in the match
        - sdn_id: OFAC's unique identifier for the designated entity
        - matched_name: The name on the SDN list that matched
        - designation_reason: Why this entity was designated
        - programs: OFAC programs (SDGT, EO-13685, etc.)
        - requires_blocking: bool — must block assets immediately

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Production OFAC screening options:
    # 1. OFAC's own API (free, limited): https://sanctionssearch.ofac.treas.gov/
    # 2. Refinitiv World-Check (paid, comprehensive):
    #    Covers OFAC + 800+ lists globally + adverse media
    # 3. LexisNexis Bridger (paid):
    #    Strong US focus, integrated with legal database
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Check fixture data for specific test scenarios
    watchlist_hits = _load_fixture("watchlist_hits.json")
    if isinstance(watchlist_hits, list):
        for hit in watchlist_hits:
            if (hit.get("list_type") == "OFAC_SDN" and
                hit.get("screened_name", "").lower() in name.lower()):
                return hit

    # Screen against mock SDN entries
    for sdn_entry in MOCK_SDN_ENTRIES:
        score = _fuzzy_name_match(name, sdn_entry["name"])
        for alias in sdn_entry.get("aliases", []):
            alias_score = _fuzzy_name_match(name, alias)
            score = max(score, alias_score)

        # Country match boosts confidence
        if country and sdn_entry.get("country") == country:
            score = min(1.0, score * 1.2)

        if score >= 0.75:  # 75% threshold for demonstration
            return {
                "hit": True,
                "list_type": "OFAC_SDN",
                "list_name": "OFAC Specially Designated Nationals List",
                "match_score": round(score * 100),
                "screened_name": name,
                "matched_name": sdn_entry["name"],
                "sdn_id": sdn_entry["sdn_id"],
                "designation_reason": sdn_entry["designation_reason"],
                "designation_date": sdn_entry["designation_date"],
                "programs": sdn_entry["programs"],
                "country": sdn_entry["country"],
                "entity_type": sdn_entry["type"],
                "requires_blocking": True,
                "requires_ofac_report": True,
                "screening_date": datetime.utcnow().isoformat() + "Z",
                "screening_system": "MOCK_OFAC_SCREEN_v1.0",
                "action_required": "IMMEDIATE_BLOCK_AND_REPORT",
            }

    return {
        "hit": False,
        "list_type": "OFAC_SDN",
        "screened_name": name,
        "match_score": 0,
        "screening_date": datetime.utcnow().isoformat() + "Z",
    }


def screen_pep_lists(name: str, country: str) -> Dict[str, Any]:
    """
    Screen a name against Politically Exposed Person (PEP) lists.

    PEPs are individuals who hold or have held prominent public positions —
    they carry elevated corruption risk by virtue of access to public funds
    and decision-making authority. Key categories:
    - Senior government officials (ministers, presidents, governors)
    - Senior military officials (generals, admirals)
    - Senior judiciary (supreme court judges, attorney generals)
    - Leaders of state-owned enterprises
    - Immediate family members and close associates of the above

    FATF R.12 requires EDD for foreign PEPs.
    FATF R.13 extends this to domestic PEPs in high-risk situations.

    Args:
        name: Full name to screen
        country: Country of political activity (ISO 2-letter code)

    Returns:
        Screening result with PEP details if found

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # PEP data sources:
    # - Refinitiv World-Check: 1.4M+ PEP records globally
    # - Dow Jones Risk & Compliance: Journalist-curated PEP database
    # - LexisNexis Bridger: Strong emerging market PEP coverage
    # - OpenSanctions (open source): Free PEP data for public lists
    # ──────────────────────────────────────────────────────────────────────────
    """
    for pep_entry in MOCK_PEP_ENTRIES:
        score = _fuzzy_name_match(name, pep_entry["name"])
        for alias in pep_entry.get("aliases", []):
            alias_score = _fuzzy_name_match(name, alias)
            score = max(score, alias_score)

        if score >= 0.70:
            is_foreign_pep = pep_entry.get("country") != "US"
            return {
                "hit": True,
                "list_type": "PEP",
                "list_name": f"{'Foreign ' if is_foreign_pep else 'Domestic '}PEP Database",
                "match_score": round(score * 100),
                "screened_name": name,
                "matched_name": pep_entry["name"],
                "pep_id": pep_entry["pep_id"],
                "position": pep_entry["position"],
                "country": pep_entry["country"],
                "pep_tier": pep_entry["pep_tier"],
                "is_foreign_pep": is_foreign_pep,
                "is_active_pep": pep_entry.get("end_date") is None,
                "edd_required": True,
                "edd_level": "ENHANCED" if is_foreign_pep else "STANDARD",
                "family_members": pep_entry.get("family_members", []),
                "regulatory_basis": "FATF Recommendation 12" if is_foreign_pep else "FATF Recommendation 13",
                "screening_date": datetime.utcnow().isoformat() + "Z",
                "action_required": "ENHANCED_DUE_DILIGENCE",
            }

    return {
        "hit": False,
        "list_type": "PEP",
        "screened_name": name,
        "screening_date": datetime.utcnow().isoformat() + "Z",
    }


def screen_eu_un_sanctions(name: str) -> Dict[str, Any]:
    """
    Screen against EU Consolidated Sanctions List and UN Security Council list.

    For banks with international operations, EU and UN sanctions are
    binding regardless of OFAC status. Some entities are on EU/UN lists
    but not OFAC — particularly in Russia, Iran, Belarus, and Myanmar.

    The UN Consolidated List is maintained by the UN Security Council
    Committee under resolutions 1267 (Al-Qaeda), 1988 (Taliban), 2253, etc.

    Args:
        name: Full name to screen

    Returns:
        Screening result with sanctions details if found

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Free APIs for EU/UN sanctions:
    # - EU: https://webgate.ec.europa.eu/fsd/fsf#!/consolidated-list/
    # - UN: https://scsanctions.un.org/resources/xml/en/consolidated.xml
    # Paid vendors (Refinitiv, Dow Jones) consolidate all these into one API call.
    # ──────────────────────────────────────────────────────────────────────────
    """
    # For demo purposes, return no hit — real implementation screens EU/UN lists
    # In a real demo with specific test names, we'd match them here
    return {
        "hit": False,
        "list_type": "EU_UN_SANCTIONS",
        "screened_name": name,
        "screening_date": datetime.utcnow().isoformat() + "Z",
    }


def screen_internal_watchlist(customer_id: str) -> Dict[str, Any]:
    """
    Screen against the bank's internal watchlist of flagged customers.

    Banks maintain internal lists that go beyond public sanctions lists:
    - Prior SAR subjects: Customers on whom SARs have been filed
    - Declined applicants: Customers whose account opening was denied for risk reasons
    - Exit-banked customers: Customers whose accounts were closed for compliance reasons
    - High-risk flagged: Customers flagged by investigators for ongoing monitoring
    - Law enforcement holds: Customers subject to active law enforcement requests
    - 314(a) matches: Customers who matched FinCEN 314(a) requests from law enforcement

    This is proprietary bank intelligence that vendors can't provide.

    Args:
        customer_id: Internal customer identifier

    Returns:
        Internal watchlist screening result

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Internal watchlist is bank-proprietary — no vendor provides this.
    # Typical implementation:
    # - Stored in compliance database (PostgreSQL, Oracle, or case management system)
    # - Accessed via internal API or direct database query
    # - Populated by compliance operations team
    # - Integrated with TMS for real-time screening
    #
    # Example direct database query:
    #   from sqlalchemy import create_engine, text
    #   engine = create_engine(os.getenv("COMPLIANCE_DB_URL"))
    #   with engine.connect() as conn:
    #       result = conn.execute(
    #           text("SELECT * FROM internal_watchlist WHERE customer_id = :cid"),
    #           {"cid": customer_id}
    #       )
    #       row = result.fetchone()
    #       if row:
    #           return {"hit": True, "reason": row["reason"], "prior_sar": row["prior_sar"]}
    # ──────────────────────────────────────────────────────────────────────────
    """
    # Check fixture data
    watchlist_hits = _load_fixture("watchlist_hits.json")
    if isinstance(watchlist_hits, list):
        for hit in watchlist_hits:
            if (hit.get("list_type") == "INTERNAL" and
                hit.get("customer_id") == customer_id):
                return hit

    # Mock: flag one specific test customer as being on internal list
    if "CUST-002" in customer_id:
        return {
            "hit": True,
            "list_type": "INTERNAL",
            "customer_id": customer_id,
            "list_name": "Internal Watchlist — Prior SAR Subject",
            "reason": "Customer subject of prior SAR (SAR-2023-04821). Original alert: large unexplained international wires.",
            "added_date": "2023-09-15",
            "added_by": "Compliance Operations",
            "prior_sar": True,
            "prior_sar_id": "SAR-2023-04821",
            "prior_sar_date": "2023-09-15",
            "monitoring_level": "ENHANCED",
            "review_due_date": "2024-09-15",
            "screening_date": datetime.utcnow().isoformat() + "Z",
            "action_required": "MANDATORY_ESCALATION",
        }

    return {
        "hit": False,
        "list_type": "INTERNAL",
        "customer_id": customer_id,
        "screening_date": datetime.utcnow().isoformat() + "Z",
    }
