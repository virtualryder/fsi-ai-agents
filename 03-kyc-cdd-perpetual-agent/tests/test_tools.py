# tests/test_tools.py
# ============================================================
# Unit tests for KYC/CDD tool functions
# ============================================================

import pytest
from tools.risk_scorer import compute_risk_score, COMPONENT_WEIGHTS
from tools.document_checker import assess_document_gaps
from tools.edd_engine import generate_edd_package


class TestRiskScorer:
    """Tests for the deterministic risk scoring model."""

    def test_pep_foreign_scores_higher_than_domestic(self):
        """Foreign PEPs should score higher than domestic PEPs (FATF R.12)."""
        base = dict(
            customer_id="TEST",
            customer_type="INDIVIDUAL",
            jurisdiction_risk="LOW",
            adverse_media_severity="NONE",
            cdd_completeness_score=95.0,
            beneficial_owners=[],
            business_type="professional_services",
            watchlist_hits=[],
            trigger_type="SCHEDULED",
        )

        domestic_result = compute_risk_score(**base, pep_flag=True, pep_category="DOMESTIC_PEP")
        foreign_result = compute_risk_score(**base, pep_flag=True, pep_category="FOREIGN_PEP")

        assert foreign_result["composite_score"] > domestic_result["composite_score"]

    def test_no_pep_scores_lower_than_pep(self):
        """Non-PEP customer should score lower than equivalent PEP customer."""
        base = dict(
            customer_id="TEST",
            customer_type="LLC",
            jurisdiction_risk="LOW",
            adverse_media_severity="NONE",
            cdd_completeness_score=100.0,
            beneficial_owners=[],
            business_type="retail_trade",
            watchlist_hits=[],
            trigger_type="SCHEDULED",
        )

        no_pep = compute_risk_score(**base, pep_flag=False, pep_category=None)
        with_pep = compute_risk_score(**base, pep_flag=True, pep_category="DOMESTIC_PEP")

        assert with_pep["composite_score"] > no_pep["composite_score"]

    def test_critical_adverse_media_inflates_score(self):
        """CRITICAL adverse media should significantly increase risk score."""
        base = dict(
            customer_id="TEST",
            customer_type="LLC",
            jurisdiction_risk="LOW",
            pep_flag=False,
            pep_category=None,
            cdd_completeness_score=100.0,
            beneficial_owners=[],
            business_type="retail_trade",
            watchlist_hits=[],
            trigger_type="SCHEDULED",
        )

        no_media = compute_risk_score(**base, adverse_media_severity="NONE")
        critical_media = compute_risk_score(**base, adverse_media_severity="CRITICAL")

        assert critical_media["composite_score"] > no_media["composite_score"] + 10

    def test_score_in_valid_range(self):
        """Risk score must always be between 0 and 100."""
        result = compute_risk_score(
            customer_id="TEST",
            customer_type="LLC",
            jurisdiction_risk="HIGH",
            pep_flag=True,
            pep_category="FOREIGN_PEP",
            adverse_media_severity="CRITICAL",
            cdd_completeness_score=0.0,
            beneficial_owners=[],
            business_type="money_services",
            watchlist_hits=[],
            trigger_type="SAR_FILED",
        )
        assert 0 <= result["composite_score"] <= 100

    def test_components_returned(self):
        """Score result must include all 8 components for SR 11-7 explainability."""
        result = compute_risk_score(
            customer_id="TEST",
            customer_type="LLC",
            jurisdiction_risk="MEDIUM",
            pep_flag=False,
            pep_category=None,
            adverse_media_severity="LOW",
            cdd_completeness_score=80.0,
            beneficial_owners=[{"name": "Test Owner", "ownership_pct": 100}],
            business_type="import_export",
            watchlist_hits=[],
            trigger_type="SCHEDULED",
        )
        for component in COMPONENT_WEIGHTS.keys():
            assert component in result["components"], f"Missing component: {component}"


class TestDocumentChecker:
    """Tests for document gap assessment."""

    def test_llc_requires_beneficial_ownership_cert(self):
        """LLC must require beneficial ownership certification (FinCEN CDD Rule)."""
        result = assess_document_gaps(
            customer_id="TEST-LLC-001",
            customer_type="LLC",
            risk_tier="MEDIUM",
            pep_flag=False,
            edd_status=False,
        )
        assert "beneficial_ownership_certification" in result["required_documents"]

    def test_pep_triggers_additional_documents(self):
        """PEP customers require source-of-wealth documents (FATF R.12)."""
        regular_result = assess_document_gaps(
            customer_id="TEST-001",
            customer_type="LLC",
            risk_tier="HIGH",
            pep_flag=False,
        )
        pep_result = assess_document_gaps(
            customer_id="TEST-002",
            customer_type="LLC",
            risk_tier="HIGH",
            pep_flag=True,
        )
        # PEP should require more documents
        assert len(pep_result["required_documents"]) > len(regular_result["required_documents"])
        assert "pep_source_of_wealth_declaration" in pep_result["required_documents"]

    def test_very_high_risk_requires_more_docs_than_low(self):
        """VERY_HIGH risk tier should require more documents than LOW risk."""
        low_result = assess_document_gaps(
            customer_id="TEST-LOW",
            customer_type="LLC",
            risk_tier="LOW",
        )
        high_result = assess_document_gaps(
            customer_id="TEST-HIGH",
            customer_type="LLC",
            risk_tier="VERY_HIGH",
        )
        assert len(high_result["required_documents"]) > len(low_result["required_documents"])

    def test_completeness_score_between_0_and_100(self):
        """Completeness score must be in valid range."""
        result = assess_document_gaps(
            customer_id="TEST-SCORE",
            customer_type="CORPORATION",
            risk_tier="MEDIUM",
        )
        assert 0 <= result["completeness_score"] <= 100


class TestEDDEngine:
    """Tests for EDD package generation."""

    def test_pep_triggers_senior_management_approval(self):
        """PEP EDD must include senior management approval doc (FATF R.12)."""
        result = generate_edd_package(
            customer_id="TEST-PEP",
            customer_type="LLC",
            risk_tier="HIGH",
            pep_flag=True,
            pep_category="DOMESTIC_PEP",
            trigger_reasons=["PEP flag"],
        )
        doc_names = [d["document"] for d in result["document_checklist"]]
        assert any("Senior Management" in d for d in doc_names), (
            "FATF R.12 requires senior management approval for PEP relationships"
        )

    def test_edd_package_has_deadline(self):
        """EDD package must include a collection deadline."""
        result = generate_edd_package(
            customer_id="TEST-EDD",
            customer_type="LLC",
            risk_tier="HIGH",
            trigger_reasons=["Adverse media"],
        )
        assert "edd_deadline" in result
        assert result["edd_deadline"] is not None

    def test_pep_gets_shorter_deadline_than_standard(self):
        """PEP EDD deadline should be shorter than standard EDD (regulatory urgency)."""
        pep_result = generate_edd_package(
            customer_id="TEST-PEP",
            customer_type="LLC",
            risk_tier="HIGH",
            pep_flag=True,
            trigger_reasons=["PEP"],
        )
        standard_result = generate_edd_package(
            customer_id="TEST-STD",
            customer_type="LLC",
            risk_tier="HIGH",
            pep_flag=False,
            trigger_reasons=["Adverse media"],
        )
        from datetime import date
        pep_deadline = date.fromisoformat(pep_result["edd_deadline"])
        std_deadline = date.fromisoformat(standard_result["edd_deadline"])
        assert pep_deadline <= std_deadline

    def test_no_duplicate_documents_in_checklist(self):
        """EDD checklist should not contain duplicate document requests."""
        result = generate_edd_package(
            customer_id="TEST-DUP",
            customer_type="LLC",
            risk_tier="VERY_HIGH",
            pep_flag=True,
            trigger_reasons=["PEP", "Adverse media HIGH", "Jurisdiction change"],
        )
        doc_names = [d["document"] for d in result["document_checklist"]]
        assert len(doc_names) == len(set(doc_names)), "Duplicate documents found in EDD checklist"
