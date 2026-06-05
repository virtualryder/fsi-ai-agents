# tools/adverse_media.py
# ============================================================
# Adverse Media Search Integration
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   Public databases and sanctions lists are always lagging indicators — they
#   capture threats AFTER they've been formally identified and listed. Adverse
#   media screening is a forward-looking signal: news coverage of fraud, corruption,
#   criminal investigations, and regulatory actions often appears months or years
#   BEFORE a formal designation. For sophisticated investigations, OSINT (Open
#   Source Intelligence) from news sources can be the most revealing data point.
#   An investigator would ask: "Has anyone written anything bad about this person?"
#
# REGULATORY REQUIREMENTS SERVED:
#   - FATF R.12: EDD for PEPs specifically requires adverse media review
#   - OCC BSA/AML Examination Handbook: "Due diligence measures for high-risk
#     customers should include... adverse information searches"
#   - FinCEN CDD Rule: Risk-based approach — adverse media informs risk assessment
#   - FinCEN Advisory: Adverse media is specifically mentioned in EDD expectations
#   - EU AMLD5/6: Adverse media as part of enhanced due diligence
#
# REAL VENDOR SYSTEMS THAT PROVIDE THIS:
#   Tier 1 — Premium (with journalist-curated content):
#   - Dow Jones Risk & Compliance: Structured adverse media from DJ news archives
#     + bespoke financial crime data. 800M+ stories, 1,800 categories.
#   - LexisNexis Risk Solutions: Nexis+ adverse media, legal cases, court records
#   - Refinitiv World-Check: Adverse media integrated with risk profiles
#
#   Tier 2 — API-driven:
#   - ComplyAdvantage: AI-driven adverse media with entity disambiguation
#   - RDC (Regulatory DataCorp): Specialized adverse media for financial crime
#   - Acuris (Mergermarket): Financial crime, sanctions, enforcement data
#   - Sayari: Integrates corporate data with adverse media
#
#   Self-built options:
#   - Google News API / GDELT: Free, requires significant post-processing
#   - NewsAPI.org: Aggregated news, low cost
#   - Bing News Search API: Microsoft Azure Cognitive Services
#   - Custom web scraping: Requires significant engineering + legal review
#
#   Legal/Court Records:
#   - PACER (Public Access to Court Electronic Records): US federal courts
#   - LexisNexis CourtLink: US court records
#   - Westlaw/LexisNexis: Legal cases
# ============================================================

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ── INTEGRATION POINT ────────────────────────────────────────────────────────
# PRODUCTION: Replace mock data with real adverse media API calls.
#
# Dow Jones Risk & Compliance API example:
#   import requests
#   headers = {
#       "Authorization": f"Bearer {os.getenv('DOW_JONES_API_TOKEN')}",
#       "Content-Type": "application/json",
#   }
#   payload = {
#       "query": name,
#       "entityType": "individual" if not is_entity else "organization",
#       "categories": ["adverse-media", "financial-crime", "regulatory-enforcement"],
#       "dateRange": {"from": "2015-01-01", "to": datetime.now().strftime("%Y-%m-%d")},
#       "languages": ["en", "es", "ru", "zh"],
#       "maxResults": 50,
#   }
#   response = requests.post(
#       "https://api.dowjones.com/riskandcompliance/v1/search",
#       headers=headers, json=payload
#   )
#   return _parse_dj_response(response.json())
#
# ComplyAdvantage API example:
#   response = requests.post(
#       "https://api.complyadvantage.com/searches",
#       json={
#           "search_term": name,
#           "fuzziness": 0.6,
#           "filters": {"types": ["adverse-media"]},
#           "tags": ["adverse-media-financial-crime"],
#       },
#       headers={"Authorization": f"Token {os.getenv('COMPLY_ADVANTAGE_API_KEY')}"}
#   )
#   return _parse_complyadvantage_response(response.json())
# ─────────────────────────────────────────────────────────────────────────────


# Sample adverse media for known test subjects
MOCK_ADVERSE_MEDIA_DATABASE = {
    "Dmitri Testovsky": [
        {
            "source": "Financial Times",
            "headline": "Former Russian Deputy Minister Testovsky Under Investigation for Undisclosed Assets",
            "date": "2023-08-15",
            "category": "corruption",
            "severity": "HIGH",
            "url": "https://example-ft.com/testovsky-investigation",
            "summary": "European prosecutors have opened an investigation into Dmitri Testovsky, a former deputy minister, over allegations of undisclosed offshore assets held through Cypriot shell companies.",
            "source_credibility": "HIGH",
            "aml_relevant": True,
        },
        {
            "source": "Reuters",
            "headline": "Meridian Capital Holdings Linked to Sanctioned Russian Entities, Report Finds",
            "date": "2023-11-02",
            "category": "money_laundering",
            "severity": "CRITICAL",
            "url": "https://example-reuters.com/meridian-capital",
            "summary": "An investigative report by the Organized Crime and Corruption Reporting Project (OCCRP) identified Meridian Capital Holdings LLC as a vehicle used to move funds linked to sanctioned Russian entities through US correspondent banking.",
            "source_credibility": "HIGH",
            "aml_relevant": True,
        },
    ],
    "Carlos Testowner": [
        {
            "source": "Chicago Tribune",
            "headline": "El Sombrero Restaurant Owner Questioned in Cash Smuggling Probe",
            "date": "2024-01-20",
            "category": "money_laundering",
            "severity": "HIGH",
            "url": "https://example-chicago.com/el-sombrero",
            "summary": "Carlos Testowner, owner of El Sombrero Restaurant, was questioned by federal agents as part of a broader investigation into cash smuggling operations in the Chicago restaurant industry.",
            "source_credibility": "MEDIUM",
            "aml_relevant": True,
        },
    ],
    "Jennifer Testaccount": [],  # No adverse media for this subject
    "Meridian Capital Holdings": [
        {
            "source": "Wall Street Journal",
            "headline": "SEC Investigating Delaware LLCs Used in Russian Capital Flight",
            "date": "2022-09-30",
            "category": "regulatory_action",
            "severity": "HIGH",
            "url": "https://example-wsj.com/sec-investigation",
            "summary": "The SEC has subpoenaed records from multiple Delaware LLCs suspected of facilitating Russian capital flight following sanctions imposed in early 2022. Meridian Capital Holdings LLC was named among entities under review.",
            "source_credibility": "HIGH",
            "aml_relevant": True,
        },
    ],
}


def search_adverse_media(
    name: str,
    aliases: Optional[List[str]] = None,
    days_lookback: int = 3650,  # 10 years default
) -> List[Dict[str, Any]]:
    """
    Search for adverse media mentions of a subject.

    The search covers:
    - Major financial news outlets (FT, WSJ, Reuters, Bloomberg)
    - Investigative journalism (OCCRP, ICIJ, ProPublica)
    - Regulatory announcements (SEC, CFTC, OCC, FinCEN enforcement actions)
    - Court records (criminal indictments, civil judgments)
    - Government databases (debarment lists, enforcement actions)

    Args:
        name: Primary name to search
        aliases: Alternative names or DBA names (expands search coverage)
        days_lookback: How many days back to search (default: 10 years)

    Returns:
        List of adverse media hits, each containing:
        - source: Publication/outlet name
        - headline: Article headline
        - date: Publication date
        - category: Type of adverse information
        - severity: CRITICAL / HIGH / MEDIUM / LOW
        - url: Article URL (for investigator to review)
        - summary: Brief summary of the adverse information
        - source_credibility: HIGH / MEDIUM / LOW
        - aml_relevant: bool — directly relates to financial crime

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # In production, call your adverse media vendor API here.
    # Most vendors return ranked results with entity disambiguation scores.
    # Key consideration: Many common names will have many false positives.
    # Use DOB, country, and entity type to disambiguate.
    # Always verify hits are actually about YOUR customer before acting.
    # ──────────────────────────────────────────────────────────────────────────
    """
    all_hits = []
    search_terms = [name] + (aliases or [])

    # Search mock database for each name variant
    for search_term in search_terms:
        # Exact match first
        if search_term in MOCK_ADVERSE_MEDIA_DATABASE:
            all_hits.extend(MOCK_ADVERSE_MEDIA_DATABASE[search_term])
            continue

        # Partial name match (catches last name only, first name only)
        for db_name, hits in MOCK_ADVERSE_MEDIA_DATABASE.items():
            name_words = search_term.lower().split()
            db_words = db_name.lower().split()
            # If at least 2 words match (avoids single common word false positives)
            common_words = set(name_words) & set(db_words)
            if len(common_words) >= 2 or (len(common_words) >= 1 and len(name_words) <= 2):
                for hit in hits:
                    if hit not in all_hits:  # Deduplicate
                        all_hits.append(hit)

    # Filter by date lookback
    cutoff_date = datetime.utcnow() - timedelta(days=days_lookback)
    filtered_hits = []
    for hit in all_hits:
        try:
            hit_date = datetime.strptime(hit.get("date", "2000-01-01"), "%Y-%m-%d")
            if hit_date >= cutoff_date:
                filtered_hits.append(hit)
        except ValueError:
            filtered_hits.append(hit)  # Include if date parsing fails

    logger.debug(f"[adverse_media] Found {len(filtered_hits)} hits for '{name}'")
    return filtered_hits


def categorize_media_hits(hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Categorize and assess the severity of adverse media hits.

    After retrieving raw media hits, this function:
    1. Filters out irrelevant hits (name disambiguation)
    2. Categorizes each hit by type of adverse information
    3. Assesses severity relative to AML investigation
    4. Determines overall adverse media risk level

    Categories:
    - money_laundering: Direct ML allegations
    - fraud: Financial fraud (securities, wire, bank fraud)
    - corruption: Bribery, embezzlement, public corruption
    - drug_trafficking: Drug money, cartel connections
    - terrorism: Terrorist financing, terrorist associations
    - sanctions_evasion: Attempts to evade OFAC or other sanctions
    - regulatory_action: SEC/OCC/FinCEN enforcement actions
    - criminal_conviction: Actual convictions (highest weight)
    - civil_litigation: Civil lawsuits (lower weight)

    Args:
        hits: List of adverse media hit dictionaries

    Returns:
        Categorized hits with overall risk assessment

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Dow Jones and LexisNexis both provide pre-categorized adverse media.
    # Their categories align with FinCEN SAR filing categories:
    # - BSA/Structuring/Money Laundering
    - Fraud/Embezzlement
    - Terrorist Financing
    This simplifies mapping their output to SAR filing requirements.
    # ──────────────────────────────────────────────────────────────────────────
    """
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}

    categorized = {
        "money_laundering": [],
        "fraud": [],
        "corruption": [],
        "drug_trafficking": [],
        "terrorism": [],
        "sanctions_evasion": [],
        "regulatory_action": [],
        "criminal_conviction": [],
        "other": [],
    }

    max_severity = "NONE"

    for hit in hits:
        category = hit.get("category", "other")
        if category not in categorized:
            category = "other"
        categorized[category].append(hit)

        hit_severity = hit.get("severity", "LOW")
        if severity_order.get(hit_severity, 0) > severity_order.get(max_severity, 0):
            max_severity = hit_severity

    # Determine overall risk level
    if max_severity in ["CRITICAL"]:
        overall_risk = "CRITICAL"
    elif max_severity == "HIGH" or len(hits) >= 3:
        overall_risk = "HIGH"
    elif max_severity == "MEDIUM" or len(hits) >= 1:
        overall_risk = "MEDIUM"
    elif len(hits) > 0:
        overall_risk = "LOW"
    else:
        overall_risk = "NONE"

    return {
        "total_hits": len(hits),
        "categorized_hits": {k: v for k, v in categorized.items() if v},
        "overall_risk_level": overall_risk,
        "most_severe_hit": max(hits, key=lambda h: severity_order.get(h.get("severity", "LOW"), 0)) if hits else None,
        "aml_relevant_hits": [h for h in hits if h.get("aml_relevant", False)],
        "high_credibility_hits": [h for h in hits if h.get("source_credibility") == "HIGH"],
        "summary": f"{len(hits)} adverse media hits found — overall risk: {overall_risk}",
    }
