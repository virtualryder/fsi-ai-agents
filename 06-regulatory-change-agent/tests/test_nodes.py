# tests/test_nodes.py
# ============================================================
# Unit tests for Regulatory Change Management Agent nodes
#
# Focuses on:
#   - Impact scoring determinism (Python-only, no LLM)
#   - Routing decision logic
#   - Scope determination
#   - Source validation
#   - Hard override rules (enforcement actions, already-effective rules)
# ============================================================

import pytest
from datetime import datetime, timedelta

from agent.state import ChangeType, RegulatoryDomain, ImpactTier
from agent.nodes import (
    change_intake_node,
    source_validation_node,
    scope_determination_node,
    impact_scoring_node,
    routing_decision_node,
    _compute_deadline_urgency_score,
    RECOGNIZED_AUTHORITIES,
    AUTHORITY_TIER_SCORES,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_state():
    """Minimal valid state for testing."""
    future_date = (datetime.utcnow() + timedelta(days=180)).date().isoformat()
    return {
        "change_title": "Test Regulatory Change",
        "change_type": ChangeType.FINAL_RULE,
        "regulatory_authority": "FinCEN",
        "regulatory_domain": RegulatoryDomain.BSA_AML,
        "publication_date": datetime.utcnow().date().isoformat(),
        "effective_date": future_date,
        "citation": "31 CFR Part 1010",
        "source_url": "https://www.fincen.gov/test",
        "summary_text": "Test summary",
        "full_text": "Test full text with regulatory requirements. Institutions MUST implement risk-based procedures.",
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


@pytest.fixture
def scored_state(base_state):
    """State after source validation and impact scoring."""
    return {
        **base_state,
        "source_tier": "TIER_2_FEDERAL_SECONDARY",
        "source_validated": True,
        "authority_applies_to_institution": True,
        "days_to_effective": 180,
        "affected_business_lines": ["retail_banking", "commercial_banking", "payments"],
        "affected_products": ["wire_transfers", "ACH_origination", "cash_management"],
        "affected_operations": ["KYC_onboarding", "SAR_filing", "transaction_monitoring"],
        "mapped_policies": [
            {"policy_id": "POL-001", "policy_name": "BSA/AML Policy"},
            {"policy_id": "POL-003", "policy_name": "CDD Policy"},
        ],
        "gap_analysis_narrative": "Institutions MUST update their AML programs. CRITICAL gap identified.",
        "compliance_window_adequate": True,
    }


# ── Change Intake Tests ───────────────────────────────────────────────────────

class TestChangeIntakeNode:

    def test_assigns_change_id(self, base_state):
        result = change_intake_node(base_state)
        assert "change_id" in result
        assert result["change_id"].startswith("REG-CHANGE-")

    def test_preserves_provided_change_id(self, base_state):
        base_state["change_id"] = "REG-CHANGE-TEST-0001"
        result = change_intake_node(base_state)
        assert result["change_id"] == "REG-CHANGE-TEST-0001"

    def test_calculates_days_to_effective(self, base_state):
        result = change_intake_node(base_state)
        assert "days_to_effective" in result
        assert result["days_to_effective"] > 0

    def test_sets_status_in_progress(self, base_state):
        result = change_intake_node(base_state)
        assert result["case_status"].value == "IN_PROGRESS"

    def test_appends_audit_entry(self, base_state):
        result = change_intake_node(base_state)
        assert len(result["audit_trail"]) == 1
        assert result["audit_trail"][0]["node"] == "change_intake_node"

    def test_effective_date_in_past_returns_zero_or_negative(self):
        past_date = (datetime.utcnow() - timedelta(days=10)).date().isoformat()
        state = {
            "change_title": "Past Rule",
            "regulatory_authority": "OCC",
            "effective_date": past_date,
            "audit_trail": [],
            "completed_steps": [],
        }
        result = change_intake_node(state)
        assert result["days_to_effective"] is not None
        assert result["days_to_effective"] < 0


# ── Source Validation Tests ───────────────────────────────────────────────────

class TestSourceValidationNode:

    def test_fincen_is_validated(self, base_state):
        result = source_validation_node(base_state)
        assert result["source_validated"] is True
        assert result["source_tier"] == "TIER_2_FEDERAL_SECONDARY"

    def test_occ_is_tier1(self, base_state):
        base_state["regulatory_authority"] = "OCC"
        result = source_validation_node(base_state)
        assert result["source_tier"] == "TIER_1_FEDERAL_PRIMARY"
        assert result["source_validated"] is True

    def test_cfpb_is_tier1(self, base_state):
        base_state["regulatory_authority"] = "CFPB"
        result = source_validation_node(base_state)
        assert result["source_tier"] == "TIER_1_FEDERAL_PRIMARY"

    def test_unknown_authority_not_validated(self, base_state):
        base_state["regulatory_authority"] = "Some Blog Post"
        result = source_validation_node(base_state)
        assert result["source_validated"] is False
        assert result["source_tier"] == "UNRECOGNIZED"

    def test_enforcement_action_flags_hitl(self, base_state):
        base_state["change_type"] = ChangeType.ENFORCEMENT_ACTION
        result = source_validation_node(base_state)
        assert result.get("human_review_required") is True

    def test_final_rule_does_not_force_hitl(self, base_state):
        base_state["change_type"] = ChangeType.FINAL_RULE
        result = source_validation_node(base_state)
        # human_review_required should not be set (routing_decision_node sets it)
        assert result.get("human_review_required") is not True


# ── Scope Determination Tests ─────────────────────────────────────────────────

class TestScopeDeterminationNode:

    def test_bsa_aml_scope(self, base_state):
        base_state["regulatory_domain"] = RegulatoryDomain.BSA_AML
        result = scope_determination_node(base_state)
        assert "retail_banking" in result["affected_business_lines"]
        assert "wire_transfers" in result["affected_products"]
        assert "KYC_onboarding" in result["affected_operations"]

    def test_consumer_compliance_scope(self, base_state):
        base_state["regulatory_domain"] = RegulatoryDomain.CONSUMER_COMPLIANCE
        result = scope_determination_node(base_state)
        assert "mortgage" in result["affected_business_lines"]
        assert "mortgage_loans" in result["affected_products"]

    def test_investment_products_scope(self, base_state):
        base_state["regulatory_domain"] = RegulatoryDomain.INVESTMENT_PRODUCTS
        result = scope_determination_node(base_state)
        assert "wealth_management" in result["affected_business_lines"]
        assert "trust_services" in result["affected_business_lines"]

    def test_scope_rationale_populated(self, base_state):
        result = scope_determination_node(base_state)
        assert result["scope_determination_rationale"]
        assert len(result["scope_determination_rationale"]) > 10


# ── Deadline Urgency Scoring Tests ────────────────────────────────────────────

class TestDeadlineUrgencyScoring:

    def test_past_effective_date_scores_maximum(self):
        score = _compute_deadline_urgency_score(-5, ChangeType.FINAL_RULE)
        assert score == 1.0

    def test_30_days_is_critical(self):
        score = _compute_deadline_urgency_score(25, ChangeType.FINAL_RULE)
        assert score >= 0.90

    def test_one_year_is_low(self):
        score = _compute_deadline_urgency_score(400, ChangeType.FINAL_RULE)
        assert score <= 0.25

    def test_none_returns_moderate_default(self):
        score = _compute_deadline_urgency_score(None, ChangeType.PROPOSED_RULE)
        assert score == 0.40

    def test_90_days_is_moderate_urgency(self):
        score = _compute_deadline_urgency_score(90, ChangeType.FINAL_RULE)
        assert 0.60 <= score <= 0.80


# ── Impact Scoring Tests ──────────────────────────────────────────────────────

class TestImpactScoringNode:

    def test_score_is_between_0_and_1(self, scored_state):
        result = impact_scoring_node(scored_state)
        assert 0.0 <= result["impact_score"] <= 1.0

    def test_tier1_authority_scores_higher_than_tier4(self, scored_state):
        tier1_state = {**scored_state, "source_tier": "TIER_1_FEDERAL_PRIMARY"}
        tier4_state = {**scored_state, "source_tier": "TIER_4_INTERNATIONAL"}

        tier1_result = impact_scoring_node(tier1_state)
        tier4_result = impact_scoring_node(tier4_state)

        assert tier1_result["impact_score"] > tier4_result["impact_score"]

    def test_enforcement_action_elevated_to_minimum_high(self, scored_state):
        scored_state["change_type"] = ChangeType.ENFORCEMENT_ACTION
        scored_state["source_tier"] = "TIER_3_STATE"  # Lower tier
        result = impact_scoring_node(scored_state)
        assert ImpactTier(result["impact_tier"]) in (ImpactTier.HIGH, ImpactTier.CRITICAL)

    def test_already_effective_tier1_rule_is_critical(self, scored_state):
        scored_state["days_to_effective"] = -1
        scored_state["source_tier"] = "TIER_1_FEDERAL_PRIMARY"
        result = impact_scoring_node(scored_state)
        assert ImpactTier(result["impact_tier"]) == ImpactTier.CRITICAL

    def test_score_components_sum_approximately_to_composite(self, scored_state):
        result = impact_scoring_node(scored_state)
        components = result["impact_score_components"]
        weighted_sum = (
            components.get("authority_tier_score", 0) * 0.25
            + components.get("deadline_urgency_score", 0) * 0.25
            + components.get("scope_breadth_score", 0) * 0.20
            + components.get("policy_depth_score", 0) * 0.15
            + components.get("remediation_complexity_score", 0) * 0.15
        )
        assert abs(weighted_sum - result["impact_score"]) < 0.01

    def test_faq_with_no_deadline_scores_low(self):
        faq_state = {
            "change_type": ChangeType.FAQ,
            "source_tier": "TIER_2_FEDERAL_SECONDARY",
            "days_to_effective": None,
            "affected_business_lines": ["retail_banking"],
            "affected_products": ["checking_accounts"],
            "affected_operations": ["consumer_disclosures"],
            "mapped_policies": [{"policy_id": "POL-001"}],
            "gap_analysis_narrative": "Minor clarification with no new requirements.",
            "compliance_window_adequate": True,
            "audit_trail": [],
            "completed_steps": [],
        }
        result = impact_scoring_node(faq_state)
        assert ImpactTier(result["impact_tier"]) in (ImpactTier.LOW, ImpactTier.MEDIUM)

    def test_critical_tier_requires_hitl_in_routing(self):
        """CRITICAL impact should result in human_review_required=True in routing_decision_node."""
        critical_state = {
            "impact_tier": ImpactTier.CRITICAL,
            "impact_score": 0.90,
            "regulatory_domain": RegulatoryDomain.BSA_AML,
            "source_validated": True,
            "is_applicable": True,
            "compliance_window_adequate": True,
            "human_review_required": False,
            "audit_trail": [],
            "completed_steps": [],
        }
        result = routing_decision_node(critical_state)
        assert result["human_review_required"] is True


# ── Routing Decision Tests ────────────────────────────────────────────────────

class TestRoutingDecisionNode:

    def test_bsa_aml_routes_to_bsa_officer(self, scored_state):
        scored_state["impact_tier"] = ImpactTier.MEDIUM
        result = routing_decision_node(scored_state)
        assert result["primary_compliance_owner"] == "BSA_OFFICER"

    def test_investment_routes_to_investment_compliance(self, base_state):
        base_state["regulatory_domain"] = RegulatoryDomain.INVESTMENT_PRODUCTS
        base_state["impact_tier"] = ImpactTier.MEDIUM
        base_state["impact_score"] = 0.55
        base_state["source_validated"] = True
        base_state["is_applicable"] = True
        base_state["compliance_window_adequate"] = True
        base_state["human_review_required"] = False
        base_state["audit_trail"] = []
        result = routing_decision_node(base_state)
        assert result["primary_compliance_owner"] == "INVESTMENT_COMPLIANCE_OFFICER"

    def test_medium_impact_does_not_require_hitl_by_default(self, scored_state):
        scored_state["impact_tier"] = ImpactTier.MEDIUM
        scored_state["human_review_required"] = False
        result = routing_decision_node(scored_state)
        assert result["human_review_required"] is False

    def test_inadequate_window_escalates_tier(self, scored_state):
        scored_state["impact_tier"] = ImpactTier.MEDIUM
        scored_state["compliance_window_adequate"] = False
        result = routing_decision_node(scored_state)
        # MEDIUM with inadequate window should escalate to HIGH
        assert ImpactTier(result["impact_tier"]) == ImpactTier.HIGH
        assert result["human_review_required"] is True

    def test_low_tier_with_inadequate_window_escalates_to_medium(self, scored_state):
        scored_state["impact_tier"] = ImpactTier.LOW
        scored_state["compliance_window_adequate"] = False
        result = routing_decision_node(scored_state)
        assert ImpactTier(result["impact_tier"]) == ImpactTier.MEDIUM
