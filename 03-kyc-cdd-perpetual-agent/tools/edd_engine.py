# tools/edd_engine.py
# ============================================================
# Enhanced Due Diligence (EDD) Package Generator
#
# Generates structured EDD document checklists and collection
# timelines when EDD is triggered during a KYC review.
#
# EDD is required (per FATF R.12 and FFIEC guidance) for:
#   - Politically Exposed Persons (PEPs) — MANDATORY, no exceptions
#   - Customers with OFAC/sanctions proximity risk
#   - High-risk industries (money services, crypto, cannabis)
#   - Customers with adverse media of HIGH or CRITICAL severity
#   - Customers in FATF grey/black list jurisdictions
#   - Customers with significant unexplained transaction spikes
#
# Regulatory basis:
#   FATF R.12 — Enhanced due diligence measures for PEPs and
#               other higher-risk categories
#   FFIEC BSA/AML Examination Manual — EDD program requirements
#   OCC Heightened Standards — enhanced controls for high-risk customers
# ============================================================

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ── EDD Document Templates by Trigger Type ────────────────────────────────────
# Each trigger type has specific additional documents required beyond standard CDD.
# Regulatory basis cited per document.

EDD_DOCUMENT_TEMPLATES = {
    "PEP": [
        {
            "document": "Source of Wealth Statement (sworn declaration)",
            "reason_required": "FATF R.12 requires verification of the source of wealth for PEPs",
            "priority": "HIGH",
            "deadline_days": 30,
        },
        {
            "document": "Source of Funds Verification (bank statements / financial records)",
            "reason_required": "FATF R.12 requires corroboration of declared source of funds for PEP relationships",
            "priority": "HIGH",
            "deadline_days": 30,
        },
        {
            "document": "Senior Management Approval Memo (signed by CCO or equivalent)",
            "reason_required": "FATF R.12 requires senior management sign-off before establishing or continuing PEP relationships",
            "priority": "HIGH",
            "deadline_days": 14,
        },
        {
            "document": "Public Role Declaration and Timeline (current and prior government positions)",
            "reason_required": "FATF R.12 — define scope of PEP status and any applicable cooling-off period",
            "priority": "MEDIUM",
            "deadline_days": 45,
        },
    ],
    "HIGH_RISK_JURISDICTION": [
        {
            "document": "Business Purpose in High-Risk Jurisdiction (signed statement with supporting contracts)",
            "reason_required": "FFIEC EDD — documented legitimate business rationale for transactions in high-risk jurisdictions",
            "priority": "HIGH",
            "deadline_days": 30,
        },
        {
            "document": "Key Counterparty Identification (names, addresses, relationship description)",
            "reason_required": "FFIEC EDD — understanding transaction counterparties in high-risk jurisdictions",
            "priority": "HIGH",
            "deadline_days": 30,
        },
        {
            "document": "Transaction Contract Documentation (copies of key commercial contracts)",
            "reason_required": "FFIEC EDD — corroboration of stated business purpose",
            "priority": "MEDIUM",
            "deadline_days": 45,
        },
    ],
    "ADVERSE_MEDIA": [
        {
            "document": "Written Explanation of Media Coverage (customer's account of events)",
            "reason_required": "FFIEC EDD — customer explanation of adverse media findings",
            "priority": "HIGH",
            "deadline_days": 21,
        },
        {
            "document": "Legal Disposition Documentation (court orders, settlement agreements, regulatory finding outcomes)",
            "reason_required": "FFIEC EDD — current status of any legal/regulatory proceedings",
            "priority": "HIGH",
            "deadline_days": 30,
        },
        {
            "document": "Updated Financial Statements (audited, within last 12 months)",
            "reason_required": "FFIEC EDD — financial health verification following adverse media",
            "priority": "MEDIUM",
            "deadline_days": 45,
        },
    ],
    "TRANSACTION_SPIKE": [
        {
            "document": "Transaction Explanation and Supporting Documentation",
            "reason_required": "FFIEC EDD — explanation of activity outside expected transaction profile",
            "priority": "HIGH",
            "deadline_days": 14,
        },
        {
            "document": "Updated Expected Activity Profile (customer declaration of revised business volumes)",
            "reason_required": "FinCEN CDD Rule — updated expected activity profile when business changes significantly",
            "priority": "HIGH",
            "deadline_days": 21,
        },
    ],
    "BENEFICIAL_OWNER_CHANGE": [
        {
            "document": "Updated Beneficial Ownership Certification (new ≥25% owners)",
            "reason_required": "FinCEN CDD Rule 31 CFR 1020.210 — must update UBO records when ownership changes",
            "priority": "HIGH",
            "deadline_days": 14,
        },
        {
            "document": "New Beneficial Owner Government-Issued Photo ID",
            "reason_required": "FinCEN CDD Rule — identity verification for new UBOs",
            "priority": "HIGH",
            "deadline_days": 21,
        },
        {
            "document": "Ownership Transfer Documentation (purchase agreement, gift deed, or similar)",
            "reason_required": "FinCEN CDD Rule — evidence of legitimate ownership transfer",
            "priority": "MEDIUM",
            "deadline_days": 30,
        },
    ],
    "DEFAULT": [
        {
            "document": "Updated Account Purpose Statement",
            "reason_required": "FinCEN CDD Rule — periodic refresh of account purpose documentation",
            "priority": "MEDIUM",
            "deadline_days": 45,
        },
        {
            "document": "Updated Source of Funds Declaration",
            "reason_required": "FFIEC EDD program — ongoing source of funds verification for higher-risk customers",
            "priority": "MEDIUM",
            "deadline_days": 45,
        },
    ],
}


def generate_edd_package(
    customer_id: str,
    customer_type: str,
    risk_tier: str,
    pep_flag: bool = False,
    pep_category: str = None,
    trigger_reasons: List[str] = None,
    missing_documents: List[str] = None,
) -> Dict[str, Any]:
    """
    Generate the EDD document checklist and deadline for a triggered EDD review.

    Args:
        customer_id: Customer identifier
        customer_type: Entity type
        risk_tier: Current/proposed risk tier
        pep_flag: PEP indicator (FATF R.12 mandatory EDD)
        pep_category: Type of PEP
        trigger_reasons: List of strings explaining why EDD was triggered
        missing_documents: Standard CDD docs that are missing (add to checklist)

    Returns:
        Dict with document_checklist, edd_deadline.
    """
    checklist = []

    # PEP triggers (FATF R.12 — mandatory EDD, no exceptions)
    if pep_flag:
        checklist.extend(EDD_DOCUMENT_TEMPLATES["PEP"])
        logger.info(f"EDD for {customer_id}: PEP triggers added (FATF R.12 mandatory)")

    # Trigger-specific documents
    trigger_reasons = trigger_reasons or []
    trigger_str = " ".join(trigger_reasons).upper()

    if "JURISDICTION" in trigger_str:
        checklist.extend(EDD_DOCUMENT_TEMPLATES["HIGH_RISK_JURISDICTION"])

    if "ADVERSE MEDIA" in trigger_str or "ADVERSE_MEDIA" in trigger_str:
        checklist.extend(EDD_DOCUMENT_TEMPLATES["ADVERSE_MEDIA"])

    if "TRANSACTION" in trigger_str:
        checklist.extend(EDD_DOCUMENT_TEMPLATES["TRANSACTION_SPIKE"])

    if "BENEFICIAL OWNER" in trigger_str or "BENEFICIAL_OWNER" in trigger_str or "UBO" in trigger_str:
        checklist.extend(EDD_DOCUMENT_TEMPLATES["BENEFICIAL_OWNER_CHANGE"])

    # Default EDD docs if list is empty or tier is VERY_HIGH
    if not checklist or risk_tier == "VERY_HIGH":
        checklist.extend(EDD_DOCUMENT_TEMPLATES["DEFAULT"])

    # Deduplicate by document name
    seen = set()
    deduped = []
    for item in checklist:
        key = item["document"]
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    checklist = deduped

    # Calculate EDD deadline
    # Shorter for PEPs and OFAC proximity (regulatory urgency)
    if pep_flag or "OFAC" in trigger_str:
        deadline_days = 21
    elif risk_tier == "VERY_HIGH":
        deadline_days = 30
    else:
        deadline_days = 45

    edd_deadline = (datetime.utcnow() + timedelta(days=deadline_days)).date().isoformat()

    logger.info(f"EDD package for {customer_id}: {len(checklist)} documents, deadline {edd_deadline}")

    return {
        "document_checklist": checklist,
        "edd_deadline": edd_deadline,
        "total_documents_requested": len(checklist),
    }
