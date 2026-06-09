# tests/test_nodes.py
# ============================================================
# Unit tests for all deterministic Python logic.
# No LLM calls — these tests must run without OPENAI_API_KEY.
#
# Tests cover:
#   - Financial analysis calculations (DTI, LTV, DSCR, payment)
#   - Risk scoring factors (all 5 dimensions)
#   - Hard decline rules (6 scenarios)
#   - Fair lending flag detection (3 flag types)
#   - Document verification (required doc set per loan type)
#   - Routing decision logic (all escalation paths)
#   - PII sanitization and input sanitization
#   - Adverse action reason selection
# ============================================================
import pytest

from agent.nodes import (
    _calculate_monthly_payment,
    _mask_pii,
    _sanitize_text,
    application_intake_node,
    document_verification_node,
    fair_lending_check_node,
    financial_analysis_node,
    risk_scoring_node,
    routing_decision_node,
)
from agent.state import AdverseActionReason, CollateralType, LoanType, RiskTier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def conventional_mortgage_state():
    """Strong conventional mortgage application — target: APPROVE_WITH_CONDITIONS."""
    return {
        "application_id": "TEST-001",
        "loan_type": LoanType.CONVENTIONAL_MORTGAGE.value,
        "loan_purpose": "PURCHASE",
        "applicant_id": "TEST-APP-001",
        "applicant_name": "Test Applicant",
        "requested_amount": 400000.0,
        "requested_term": 360,
        "quoted_rate": 0.07,
        "collateral_type": CollateralType.PRIMARY_RESIDENCE.value,
        "appraised_value": 500000.0,
        "annual_income": 130000.0,
        "monthly_debt_obligations": 1000.0,
        "credit_score": 740,
        "credit_score_model": "FICO_8",
        "derogatory_marks": 0,
        "bankruptcy_flag": False,
        "foreclosure_flag": False,
        "collections_count": 0,
        "collections_balance": 0.0,
        "thin_file_flag": False,
        "recent_inquiries_90d": 1,
        "ofac_hit": False,
        "liquid_assets": 50000.0,
        "cash_flow_adequate": True,
        "documents_received": [
            "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
            "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT",
            "CREDIT_AUTHORIZATION",
        ],
        "document_exceptions": [],
        "fair_lending_flags": [],
        "fair_lending_review_required": False,
        "property_census_tract": "99999999999",
        "property_state": "MA",
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


@pytest.fixture
def scored_state(conventional_mortgage_state):
    """State after financial_analysis and risk_scoring have run."""
    fin = financial_analysis_node(conventional_mortgage_state)
    conventional_mortgage_state.update(fin)
    scored = risk_scoring_node(conventional_mortgage_state)
    conventional_mortgage_state.update(scored)
    return conventional_mortgage_state


@pytest.fixture
def commercial_state():
    """Commercial real estate application for DSCR testing."""
    return {
        "application_id": "TEST-CRE-001",
        "loan_type": LoanType.COMMERCIAL_REAL_ESTATE.value,
        "loan_purpose": "ACQUISITION",
        "applicant_id": "TEST-APP-CRE",
        "applicant_name": "TestCo LLC",
        "requested_amount": 2500000.0,
        "requested_term": 300,
        "quoted_rate": 0.075,
        "collateral_type": CollateralType.COMMERCIAL_REAL_ESTATE.value,
        "appraised_value": 3500000.0,
        "annual_income": 600000.0,
        "monthly_debt_obligations": 15000.0,
        "net_operating_income": 310000.0,
        "credit_score": 760,
        "credit_score_model": "FICO_8",
        "derogatory_marks": 0,
        "bankruptcy_flag": False,
        "foreclosure_flag": False,
        "collections_count": 0,
        "collections_balance": 0.0,
        "thin_file_flag": False,
        "recent_inquiries_90d": 0,
        "ofac_hit": False,
        "liquid_assets": 350000.0,
        "cash_flow_adequate": True,
        "documents_received": [
            "GOVERNMENT_ID", "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR",
            "RENT_ROLLS", "PROPERTY_APPRAISAL", "ENVIRONMENTAL_REPORT",
            "ENTITY_DOCUMENTS", "CREDIT_AUTHORIZATION",
        ],
        "document_exceptions": [],
        "fair_lending_flags": [],
        "fair_lending_review_required": False,
        "property_census_tract": None,
        "property_state": "MA",
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


# ── Payment Calculation ───────────────────────────────────────────────────────

class TestMonthlyPaymentCalculation:
    def test_standard_amortizing_payment(self):
        """$400K at 7% for 30 years ≈ $2,661."""
        payment = _calculate_monthly_payment(400_000, 0.07, 360)
        assert 2650 < payment < 2680

    def test_zero_rate_returns_principal_divided(self):
        payment = _calculate_monthly_payment(120_000, 0.0, 120)
        assert payment == pytest.approx(1000.0, abs=1)

    def test_zero_principal_returns_zero(self):
        assert _calculate_monthly_payment(0, 0.07, 360) == 0.0

    def test_zero_term_returns_zero(self):
        assert _calculate_monthly_payment(400_000, 0.07, 0) == 0.0

    def test_commercial_shorter_term(self):
        """$2.5M at 7.5% for 25 years."""
        payment = _calculate_monthly_payment(2_500_000, 0.075, 300)
        assert 17000 < payment < 19000


# ── Financial Analysis ────────────────────────────────────────────────────────

class TestFinancialAnalysis:
    def test_dti_calculation(self, conventional_mortgage_state):
        result = financial_analysis_node(conventional_mortgage_state)
        # Monthly income = 130000/12 ≈ 10833
        # Payment ≈ 2661; existing debt = 1000; total = 3661
        # Total DTI ≈ 3661 / 10833 ≈ 0.338
        assert 0.30 < result["total_dti_ratio"] < 0.40

    def test_ltv_calculation(self, conventional_mortgage_state):
        result = financial_analysis_node(conventional_mortgage_state)
        # $400K / $500K = 0.80
        assert result["ltv_ratio"] == pytest.approx(0.80, abs=0.01)

    def test_dscr_calculated_for_commercial(self, commercial_state):
        result = financial_analysis_node(commercial_state)
        # NOI $310K / annual_debt_service
        assert result["dscr"] is not None
        assert result["dscr"] > 1.0

    def test_dscr_not_calculated_for_consumer(self, conventional_mortgage_state):
        result = financial_analysis_node(conventional_mortgage_state)
        assert result["dscr"] is None

    def test_reserves_calculated(self, conventional_mortgage_state):
        result = financial_analysis_node(conventional_mortgage_state)
        assert result["reserves_months"] > 0

    def test_cash_flow_adequate_flag(self, conventional_mortgage_state):
        result = financial_analysis_node(conventional_mortgage_state)
        assert result["cash_flow_adequate"] is True

    def test_high_dti_cash_flow_inadequate(self, conventional_mortgage_state):
        conventional_mortgage_state["monthly_debt_obligations"] = 8000.0
        result = financial_analysis_node(conventional_mortgage_state)
        assert result["cash_flow_adequate"] is False


# ── Risk Scoring ──────────────────────────────────────────────────────────────

class TestRiskScoring:
    def test_strong_application_approves(self, scored_state):
        assert scored_state["risk_tier"] in (
            RiskTier.APPROVE.value, RiskTier.APPROVE_WITH_CONDITIONS.value
        )
        assert scored_state["composite_score"] >= 0.55

    def test_credit_score_factor_floors_at_zero(self, conventional_mortgage_state):
        conventional_mortgage_state["credit_score"] = 400
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["credit_score_factor"] == 0.0

    def test_credit_score_factor_maxes_at_one(self, conventional_mortgage_state):
        conventional_mortgage_state["credit_score"] = 820
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["credit_score_factor"] == 1.00

    def test_low_ltv_high_factor(self, conventional_mortgage_state):
        conventional_mortgage_state["appraised_value"] = 1_000_000.0
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        # LTV = 400K / 1M = 0.40 → ltv_factor should be 1.0
        assert result["ltv_factor"] == 1.00

    def test_composite_score_weighted_correctly(self, conventional_mortgage_state):
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        # Validate composite = weighted sum
        expected = (
            result["credit_score_factor"] * 0.30
            + result["dti_factor"] * 0.25
            + result["ltv_factor"] * 0.20
            + result["cash_flow_factor"] * 0.15
            + result["collateral_factor"] * 0.10
        )
        assert result["composite_score"] == pytest.approx(expected, abs=0.001)

    def test_score_breakdown_present_in_state(self, scored_state):
        breakdown = scored_state["score_breakdown"]
        assert "credit_score_factor" in breakdown
        assert "composite_score" in breakdown
        assert breakdown["model_governance"] == "SR 11-7"


# ── Hard Decline Rules ────────────────────────────────────────────────────────

class TestHardDeclineRules:
    def test_ofac_hit_always_declines(self, conventional_mortgage_state):
        conventional_mortgage_state["ofac_hit"] = True
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["risk_tier"] == RiskTier.DECLINE.value
        assert result["hard_decline_triggered"] is True
        assert "OFAC" in result["hard_decline_reason"]

    def test_ofac_decline_regardless_of_excellent_credit(self, conventional_mortgage_state):
        """OFAC override cannot be countered by perfect credit score."""
        conventional_mortgage_state["ofac_hit"] = True
        conventional_mortgage_state["credit_score"] = 850
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["risk_tier"] == RiskTier.DECLINE.value
        assert result["hard_decline_triggered"] is True

    def test_dti_above_50_pct_declines(self, conventional_mortgage_state):
        conventional_mortgage_state["monthly_debt_obligations"] = 9000.0
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["risk_tier"] == RiskTier.DECLINE.value
        assert result["hard_decline_triggered"] is True
        assert "DTI" in result["hard_decline_reason"]

    def test_fico_below_580_conventional_declines(self, conventional_mortgage_state):
        conventional_mortgage_state["credit_score"] = 560
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["risk_tier"] == RiskTier.DECLINE.value
        assert result["hard_decline_triggered"] is True

    def test_fico_below_580_consumer_does_not_hard_decline(self, conventional_mortgage_state):
        """FICO minimum is mortgage-specific. Consumer loans have lower floor."""
        conventional_mortgage_state["credit_score"] = 560
        conventional_mortgage_state["loan_type"] = LoanType.CONSUMER_PERSONAL.value
        conventional_mortgage_state["collateral_type"] = CollateralType.UNSECURED.value
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        # Should score to a tier based on composite, not hard decline
        assert result["hard_decline_triggered"] is False

    def test_jumbo_fico_below_680_declines(self, conventional_mortgage_state):
        conventional_mortgage_state["loan_type"] = LoanType.JUMBO_MORTGAGE.value
        conventional_mortgage_state["credit_score"] = 660
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["risk_tier"] == RiskTier.DECLINE.value
        assert result["hard_decline_triggered"] is True

    def test_chapter7_less_than_2_years_declines(self, conventional_mortgage_state):
        conventional_mortgage_state["bankruptcy_flag"] = True
        conventional_mortgage_state["bankruptcy_chapter"] = "CHAPTER_7"
        conventional_mortgage_state["bankruptcy_discharge_years"] = 1.5
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["risk_tier"] == RiskTier.DECLINE.value
        assert "bankruptcy" in result["hard_decline_reason"].lower()

    def test_chapter7_over_2_years_not_hard_decline(self, conventional_mortgage_state):
        """2+ years seasoned Chapter 7 should not trigger hard decline."""
        conventional_mortgage_state["bankruptcy_flag"] = True
        conventional_mortgage_state["bankruptcy_chapter"] = "CHAPTER_7"
        conventional_mortgage_state["bankruptcy_discharge_years"] = 2.5
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert result["hard_decline_triggered"] is False


# ── Fair Lending ──────────────────────────────────────────────────────────────

class TestFairLending:
    def test_flagged_census_tract_sets_geographic_flag(self, conventional_mortgage_state):
        conventional_mortgage_state["property_census_tract"] = "17031838400"
        result = fair_lending_check_node(conventional_mortgage_state)
        assert result["geographic_flag"] is True
        assert result["fair_lending_review_required"] is True
        assert len(result["fair_lending_flags"]) > 0

    def test_clean_census_tract_no_flag(self, conventional_mortgage_state):
        conventional_mortgage_state["property_census_tract"] = "25025000100"
        result = fair_lending_check_node(conventional_mortgage_state)
        assert result["geographic_flag"] is False

    def test_steering_flag_fha_when_qualifies_conventional(self, conventional_mortgage_state):
        conventional_mortgage_state["loan_type"] = LoanType.FHA_MORTGAGE.value
        conventional_mortgage_state["credit_score"] = 680
        conventional_mortgage_state["appraised_value"] = 500000.0
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = fair_lending_check_node(conventional_mortgage_state)
        assert result["steering_flag"] is True
        assert result["fair_lending_review_required"] is True

    def test_hmda_reportable_for_mortgage(self, conventional_mortgage_state):
        result = fair_lending_check_node(conventional_mortgage_state)
        assert result["hmda_reportable"] is True

    def test_hmda_not_reportable_for_consumer_loan(self, conventional_mortgage_state):
        conventional_mortgage_state["loan_type"] = LoanType.CONSUMER_PERSONAL.value
        conventional_mortgage_state["property_state"] = None
        result = fair_lending_check_node(conventional_mortgage_state)
        assert result["hmda_reportable"] is False

    def test_no_flags_no_review_required(self, conventional_mortgage_state):
        conventional_mortgage_state["property_census_tract"] = "25025000100"
        result = fair_lending_check_node(conventional_mortgage_state)
        assert result["fair_lending_review_required"] is False


# ── Document Verification ─────────────────────────────────────────────────────

class TestDocumentVerification:
    def test_complete_docs_verified(self, conventional_mortgage_state):
        result = document_verification_node(conventional_mortgage_state)
        assert result["documents_verified"] is True
        assert result["missing_documents"] == []

    def test_missing_appraisal_detected(self, conventional_mortgage_state):
        conventional_mortgage_state["documents_received"].remove("PROPERTY_APPRAISAL")
        result = document_verification_node(conventional_mortgage_state)
        assert result["documents_verified"] is False
        assert "PROPERTY_APPRAISAL" in result["missing_documents"]

    def test_no_government_id_fails_cip(self, conventional_mortgage_state):
        conventional_mortgage_state["documents_received"].remove("GOVERNMENT_ID")
        result = document_verification_node(conventional_mortgage_state)
        assert result["identity_verified"] is False
        assert result["documents_verified"] is False
        assert any("CIP" in e for e in result["document_exceptions"])

    def test_va_requires_coe(self, conventional_mortgage_state):
        conventional_mortgage_state["loan_type"] = LoanType.VA_MORTGAGE.value
        conventional_mortgage_state["documents_received"] = [
            "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
            "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT",
            "CREDIT_AUTHORIZATION",
        ]
        result = document_verification_node(conventional_mortgage_state)
        assert "CERTIFICATE_OF_ELIGIBILITY" in result["missing_documents"]
        assert "DD214_OR_COE" in result["missing_documents"]


# ── Routing Decision ──────────────────────────────────────────────────────────

class TestRoutingDecision:
    def test_refer_to_committee_requires_hitl(self, scored_state):
        scored_state["risk_tier"] = RiskTier.REFER_TO_COMMITTEE.value
        scored_state["fair_lending_review_required"] = False
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is True

    def test_fair_lending_flag_requires_hitl(self, scored_state):
        scored_state["risk_tier"] = RiskTier.APPROVE.value
        scored_state["fair_lending_review_required"] = True
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is True
        assert result["escalation_path"] == "CCO"

    def test_ofac_hit_routes_to_bsa_officer(self, scored_state):
        scored_state["ofac_hit"] = True
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is True
        assert result["escalation_path"] == "BSA_OFFICER"
        assert result["assigned_underwriter"] == "BSA_OFFICER"

    def test_large_loan_requires_committee(self, scored_state):
        scored_state["requested_amount"] = 6_000_000.0
        scored_state["risk_tier"] = RiskTier.APPROVE_WITH_CONDITIONS.value
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is True
        assert result["committee_required"] is True

    def test_clean_approve_no_hitl(self, scored_state):
        scored_state["risk_tier"] = RiskTier.APPROVE.value
        scored_state["fair_lending_review_required"] = False
        scored_state["ofac_hit"] = False
        scored_state["requested_amount"] = 400000.0
        scored_state["document_exceptions"] = []
        scored_state["bankruptcy_flag"] = False
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is False

    def test_decline_tier_requires_hitl(self, scored_state):
        scored_state["risk_tier"] = RiskTier.DECLINE.value
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is True


# ── Application Intake / Security ─────────────────────────────────────────────

class TestApplicationIntakeSecurity:
    def test_invalid_loan_type_defaults(self):
        result = application_intake_node({
            "loan_type": "INVALID_TYPE",
            "requested_amount": 100000.0,
            "applicant_name": "Test",
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        })
        assert result["loan_type"] == LoanType.CONSUMER_PERSONAL.value
        assert any("invalid_loan_type" in e.lower() or "invalid" in e.lower() for e in result["errors"])

    def test_negative_amount_flagged(self):
        result = application_intake_node({
            "loan_type": LoanType.CONSUMER_PERSONAL.value,
            "requested_amount": -5000.0,
            "applicant_name": "Test",
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        })
        assert any("requested_amount" in e for e in result["errors"])

    def test_application_id_generated_if_missing(self):
        result = application_intake_node({
            "loan_type": LoanType.CONSUMER_PERSONAL.value,
            "requested_amount": 10000.0,
            "applicant_name": "Test",
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        })
        assert result["application_id"].startswith("APP-")

    def test_pii_masker_removes_ssn(self):
        assert "***-**-****" in _mask_pii("SSN: 123-45-6789")

    def test_pii_masker_removes_9_digit_numbers(self):
        assert "*" * 9 in _mask_pii("123456789")

    def test_sanitize_strips_control_characters(self):
        dirty = "Normal text\x00\x01injected"
        clean = _sanitize_text(dirty)
        assert "\x00" not in clean
        assert "\x01" not in clean
        assert "Normal text" in clean

    def test_sanitize_caps_length(self):
        long_input = "A" * 5000
        result = _sanitize_text(long_input)
        assert len(result) <= 2000

    def test_audit_trail_populated(self, conventional_mortgage_state):
        result = application_intake_node(conventional_mortgage_state)
        assert len(result["audit_trail"]) > 0
        assert result["audit_trail"][-1]["step"] == "application_intake"


# ── Adverse Action Reasons ────────────────────────────────────────────────────

class TestAdverseActionReasons:
    def test_ofac_decline_uses_regulatory_restriction_reason(self, conventional_mortgage_state):
        conventional_mortgage_state["ofac_hit"] = True
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert AdverseActionReason.OFAC_MATCH.value in result["adverse_action_reasons"]

    def test_dti_decline_uses_excessive_obligations(self, conventional_mortgage_state):
        conventional_mortgage_state["monthly_debt_obligations"] = 9500.0
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert (
            AdverseActionReason.DTI_TOO_HIGH.value in result["adverse_action_reasons"]
            or AdverseActionReason.EXCESSIVE_OBLIGATIONS.value in result["adverse_action_reasons"]
        )

    def test_bankruptcy_decline_uses_bankruptcy_reason(self, conventional_mortgage_state):
        conventional_mortgage_state["bankruptcy_flag"] = True
        conventional_mortgage_state["bankruptcy_chapter"] = "CHAPTER_7"
        conventional_mortgage_state["bankruptcy_discharge_years"] = 1.0
        fin = financial_analysis_node(conventional_mortgage_state)
        conventional_mortgage_state.update(fin)
        result = risk_scoring_node(conventional_mortgage_state)
        assert AdverseActionReason.BANKRUPTCY.value in result["adverse_action_reasons"]
