# tools/document_checker.py
# ============================================================
# Document Gap Assessment for KYC/CDD Reviews
#
# Determines required documents based on:
#   - Customer type (individual, LLC, corporation, trust, etc.)
#   - Risk tier (higher risk = more documents required)
#   - PEP status (FATF R.12 — additional EDD documents for PEPs)
#   - EDD status (enhanced program requires additional documentation)
#   - Expiry rules (government IDs expire, UBO certs refreshed annually for HIGH)
#
# Regulatory basis:
#   FinCEN CDD Rule (31 CFR 1020.210) — required CDD elements per customer type
#   BSA CIP (31 CFR 1020.220) — Customer Identification Program requirements
#   FFIEC BSA/AML Examination Manual — documentation frequency by risk tier
# ============================================================

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Required Document Matrix ───────────────────────────────────────────────────
# Maps customer type + risk tier to required document list.
# Regulatory citations included for each document category.

REQUIRED_DOCUMENTS = {
    "INDIVIDUAL": {
        "ALL": [
            {"doc_type": "government_issued_photo_id", "regulatory_basis": "BSA CIP 31 CFR 1020.220", "validity_years": 10},
            {"doc_type": "proof_of_address", "regulatory_basis": "BSA CIP", "validity_years": 1},
            {"doc_type": "source_of_funds_declaration", "regulatory_basis": "FFIEC EDD guidance", "validity_years": 3},
        ],
        "HIGH": [
            {"doc_type": "source_of_wealth_statement", "regulatory_basis": "FATF R.12 EDD for higher-risk customers", "validity_years": 2},
            {"doc_type": "employment_verification", "regulatory_basis": "FFIEC risk-based CDD", "validity_years": 3},
        ],
        "VERY_HIGH": [
            {"doc_type": "independent_wealth_verification", "regulatory_basis": "FATF R.12 PEP EDD", "validity_years": 1},
            {"doc_type": "tax_return_last_2_years", "regulatory_basis": "FFIEC EDD — source of wealth", "validity_years": 2},
            {"doc_type": "reference_letter_financial_institution", "regulatory_basis": "FFIEC EDD", "validity_years": 2},
        ],
    },
    "LLC": {
        "ALL": [
            {"doc_type": "articles_of_organization", "regulatory_basis": "FinCEN CDD Rule 31 CFR 1020.210 — entity verification", "validity_years": 999},
            {"doc_type": "operating_agreement", "regulatory_basis": "FinCEN CDD Rule — business structure", "validity_years": 999},
            {"doc_type": "ein_verification", "regulatory_basis": "BSA CIP — TIN verification", "validity_years": 999},
            {"doc_type": "beneficial_ownership_certification", "regulatory_basis": "FinCEN CDD Rule — UBO ≥25% equity", "validity_years": 1},
            {"doc_type": "business_license_or_registration", "regulatory_basis": "FinCEN CDD Rule — nature of business", "validity_years": 1},
            {"doc_type": "principal_owner_government_id", "regulatory_basis": "FinCEN CDD Rule — individual UBO identity", "validity_years": 10},
        ],
        "HIGH": [
            {"doc_type": "audited_financial_statements", "regulatory_basis": "FFIEC EDD — source of funds", "validity_years": 1},
            {"doc_type": "business_activity_description", "regulatory_basis": "FinCEN CDD Rule — expected activity profile", "validity_years": 2},
            {"doc_type": "primary_counterparty_list", "regulatory_basis": "FFIEC EDD — transaction pattern verification", "validity_years": 1},
        ],
        "VERY_HIGH": [
            {"doc_type": "corporate_structure_chart", "regulatory_basis": "FinCEN CDD Rule — beneficial ownership transparency", "validity_years": 1},
            {"doc_type": "third_party_reference_letters", "regulatory_basis": "FFIEC EDD", "validity_years": 2},
            {"doc_type": "bank_reference_letter", "regulatory_basis": "FFIEC EDD", "validity_years": 2},
            {"doc_type": "source_of_initial_capital", "regulatory_basis": "FATF R.10 — source of funds verification", "validity_years": 999},
        ],
    },
    "CORPORATION": {
        "ALL": [
            {"doc_type": "certificate_of_incorporation", "regulatory_basis": "FinCEN CDD Rule — entity formation", "validity_years": 999},
            {"doc_type": "bylaws_or_articles", "regulatory_basis": "FinCEN CDD Rule — governance structure", "validity_years": 999},
            {"doc_type": "ein_verification", "regulatory_basis": "BSA CIP", "validity_years": 999},
            {"doc_type": "beneficial_ownership_certification", "regulatory_basis": "FinCEN CDD Rule — UBO ≥25% equity", "validity_years": 1},
            {"doc_type": "board_resolution_authorizing_account", "regulatory_basis": "FinCEN CDD Rule", "validity_years": 999},
            {"doc_type": "principal_officers_id", "regulatory_basis": "FinCEN CDD Rule — key principals", "validity_years": 10},
        ],
        "HIGH": [
            {"doc_type": "audited_financial_statements", "regulatory_basis": "FFIEC EDD", "validity_years": 1},
            {"doc_type": "annual_report_or_10k", "regulatory_basis": "FFIEC EDD — business activity", "validity_years": 1},
        ],
        "VERY_HIGH": [
            {"doc_type": "corporate_structure_chart_full_ownership", "regulatory_basis": "FinCEN CDD Rule UBO", "validity_years": 1},
            {"doc_type": "regulatory_license_or_registration", "regulatory_basis": "FFIEC EDD — regulated entities", "validity_years": 1},
        ],
    },
    "TRUST": {
        "ALL": [
            {"doc_type": "trust_agreement_or_deed", "regulatory_basis": "FinCEN CDD Rule — legal entity verification", "validity_years": 999},
            {"doc_type": "trustee_government_id", "regulatory_basis": "FinCEN CDD Rule — trustee identity", "validity_years": 10},
            {"doc_type": "beneficiary_list", "regulatory_basis": "FinCEN CDD Rule — beneficial ownership", "validity_years": 1},
            {"doc_type": "grantor_id_if_revocable", "regulatory_basis": "FinCEN CDD Rule", "validity_years": 10},
            {"doc_type": "ein_or_ssn_verification", "regulatory_basis": "BSA CIP", "validity_years": 999},
        ],
    },
}

# PEP-specific additional documents (FATF R.12)
PEP_ADDITIONAL_DOCUMENTS = [
    {"doc_type": "pep_source_of_wealth_declaration", "regulatory_basis": "FATF R.12 — PEP EDD source of wealth", "validity_years": 1},
    {"doc_type": "pep_source_of_funds_verification", "regulatory_basis": "FATF R.12 — PEP EDD source of funds", "validity_years": 1},
    {"doc_type": "senior_management_approval", "regulatory_basis": "FATF R.12 — senior management sign-off for PEP relationships", "validity_years": 1},
]


def assess_document_gaps(
    customer_id: str,
    customer_type: str,
    risk_tier: str,
    pep_flag: bool = False,
    edd_status: bool = False,
) -> dict:
    """
    Assess the current CDD document file and identify gaps.

    Args:
        customer_id: Customer identifier
        customer_type: INDIVIDUAL | LLC | CORPORATION | TRUST | etc.
        risk_tier: LOW | MEDIUM | HIGH | VERY_HIGH
        pep_flag: Whether customer is a PEP (triggers additional docs)
        edd_status: Whether EDD is currently active

    Returns:
        Dict with required_documents, documents_on_file, missing_documents,
        completeness_score.
    """
    # Build required document list for this customer type + risk tier
    type_docs = REQUIRED_DOCUMENTS.get(customer_type, REQUIRED_DOCUMENTS.get("LLC", {}))
    required = []

    # Always include base documents
    required.extend(type_docs.get("ALL", []))

    # Add risk-tier-specific documents
    if risk_tier in ["HIGH", "VERY_HIGH"]:
        required.extend(type_docs.get("HIGH", []))
    if risk_tier == "VERY_HIGH":
        required.extend(type_docs.get("VERY_HIGH", []))

    # Add PEP-specific documents (FATF R.12)
    if pep_flag:
        required.extend(PEP_ADDITIONAL_DOCUMENTS)

    # Simulate what's on file vs. missing (in production: query document vault)
    documents_on_file = _simulate_documents_on_file(customer_id, required)

    # Identify missing and expired
    on_file_types = {d["doc_type"]: d for d in documents_on_file}
    missing = [
        r["doc_type"] for r in required
        if r["doc_type"] not in on_file_types
        or on_file_types[r["doc_type"]]["status"] == "EXPIRED"
    ]

    # Completeness score: weighted by regulatory importance
    completeness = ((len(required) - len(missing)) / max(len(required), 1)) * 100

    return {
        "required_documents": [d["doc_type"] for d in required],
        "documents_on_file": documents_on_file,
        "missing_documents": missing,
        "completeness_score": round(completeness, 1),
    }


def _simulate_documents_on_file(customer_id: str, required: list) -> list:
    """
    Simulate the document vault state for development.
    In production: query document management system API.
    """
    import random
    import hashlib

    # Use customer_id as seed for consistent simulation
    seed = int(hashlib.md5(customer_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    today = datetime.utcnow().date()
    on_file = []

    for doc in required:
        # 75% chance document is on file
        if rng.random() < 0.75:
            collected_days_ago = rng.randint(30, 800)
            collected_date = today - timedelta(days=collected_days_ago)
            validity_days = doc.get("validity_years", 1) * 365

            if validity_days < 9000:  # Documents with finite validity
                expiry = collected_date + timedelta(days=validity_days)
                if expiry < today:
                    status = "EXPIRED"
                elif expiry < today + timedelta(days=90):
                    status = "EXPIRING_SOON"
                else:
                    status = "CURRENT"
            else:
                status = "CURRENT"  # Permanent documents (articles of incorporation, etc.)
                expiry = None

            on_file.append({
                "doc_type": doc["doc_type"],
                "date_collected": collected_date.isoformat(),
                "expiry_date": expiry.isoformat() if expiry else None,
                "status": status,
                "regulatory_basis": doc.get("regulatory_basis"),
            })

    return on_file
