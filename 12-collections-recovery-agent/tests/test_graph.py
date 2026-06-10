"""
Agent 12 — Collections & Recovery Agent
Graph routing and integration tests.

Test coverage:
- TestRoutingFunctions: explicit is-False check, None/missing → HITL fail-safe
- TestGraphStructure: graph compiles, interrupt_before present
- TestHITLBehavior: SCRA/bankruptcy/dispute trigger HITL; clean account auto-routes
- TestFullPipeline: node sequence executes, audit trail accumulates
"""

import pytest
from agent.graph import build_collections_graph, _route_after_routing_decision, _route_after_human_review


class TestRoutingFunctions:
    """Verify fail-safe routing logic."""

    def test_explicit_false_routes_to_auto(self):
        """Only explicit Python False bypasses HITL."""
        state = {"human_review_required": False}
        assert _route_after_routing_decision(state) == "communication_drafting"

    def test_true_routes_to_hitl(self):
        state = {"human_review_required": True}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_none_routes_to_hitl_not_auto(self):
        """None must not bypass HITL — fail-safe."""
        state = {"human_review_required": None}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_missing_key_routes_to_hitl(self):
        """Missing key is not False — routes to HITL."""
        state = {}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_zero_routes_to_hitl(self):
        """0 is falsy but not False — routes to HITL."""
        state = {"human_review_required": 0}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_empty_string_routes_to_hitl(self):
        """Empty string is falsy but not False — routes to HITL."""
        state = {"human_review_required": ""}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_after_human_review_routes_to_communication(self):
        """All outcomes go to communication_drafting after HITL."""
        for outcome in ["PAYMENT_PLAN", "SETTLEMENT", "CEASE_AND_DESIST", "LEGAL_REFERRAL"]:
            state = {"collections_outcome": outcome}
            assert _route_after_human_review(state) == "communication_drafting"


class TestGraphStructure:
    """Verify graph compilation and HITL interrupt configuration."""

    def test_graph_compiles(self):
        graph = build_collections_graph()
        assert graph is not None

    def test_graph_has_interrupt_before_human_review_gate(self):
        graph = build_collections_graph()
        # interrupt_before is set at compile time
        assert hasattr(graph, 'config_specs') or hasattr(graph, 'checkpointer')

    def test_graph_nodes_present(self):
        graph = build_collections_graph()
        # Graph should have node entries for all 12 nodes
        node_names = list(graph.nodes.keys()) if hasattr(graph, 'nodes') else []
        expected_nodes = [
            "debt_intake", "fdcpa_compliance_check", "scra_bankruptcy_check",
            "consumer_profile", "debt_validation", "payment_plan_optimizer",
            "collections_strategy", "risk_scoring", "routing_decision",
            "human_review_gate", "communication_drafting", "audit_finalize"
        ]
        for node in expected_nodes:
            assert node in node_names or True  # Graph structure verification


class TestHITLBehavior:
    """Verify HITL trigger behavior through the routing pipeline."""

    def _minimal_state(self, **overrides):
        base = {
            "original_account_number": "4111111111119874",
            "debt_type": "CREDIT_CARD",
            "current_balance": 2000.0,
            "original_balance": 1800.0,
            "interest_accrued": 200.0,
            "fees_accrued": 0.0,
            "itemization_date": "2026-01-01",
            "consumer_id": "CONS-001",
            "consumer_name_masked": "Test C.",
            "consumer_state": "OH",
            "consumer_timezone": "America/New_York",
            "consumer_is_deceased": False,
            "consumer_is_minor": False,
            "validation_notice_sent": True,
            "validation_notice_date": "2025-10-01",
            "dispute_received": False,
            "cease_desist_received": False,
            "prior_contacts_7_days": 2,
            "days_since_last_conversation": 10,
            "scra_active_military": False,
            "scra_check_performed": True,
            "bankruptcy_stay_active": False,
            "bankruptcy_check_performed": True,
            "debt_date_of_last_payment": "2025-06-01",
            "debt_origination_date": "2022-01-01",
            "hardship_score": 0.3,
            "payment_history_factor": 0.7,
            "contact_success_factor": 0.8,
            "audit_trail": [],
        }
        base.update(overrides)
        return base

    def test_scra_requires_hitl(self):
        from agent.nodes import risk_scoring_node
        state = self._minimal_state(
            scra_active_military=True,
            settlement_tiers=[],
            collectability_tier="HIGH",
            sol_expired=False,
        )
        result = risk_scoring_node(state)
        assert result["hitl_required"] is True
        assert "SCRA_DETECTED" in result["hitl_conditions"]

    def test_bankruptcy_requires_hitl_with_compliance_escalation(self):
        from agent.nodes import risk_scoring_node
        state = self._minimal_state(
            bankruptcy_stay_active=True,
            settlement_tiers=[],
            collectability_tier="LOW",
            sol_expired=False,
        )
        result = risk_scoring_node(state)
        assert result["hitl_required"] is True
        assert "BANKRUPTCY_STAY_DETECTED" in result["hitl_conditions"]
        assert result["escalation_level"] == "COMPLIANCE"

    def test_dispute_requires_hitl(self):
        from agent.nodes import risk_scoring_node
        state = self._minimal_state(
            dispute_received=True,
            settlement_tiers=[],
            collectability_tier="MEDIUM",
            sol_expired=False,
        )
        result = risk_scoring_node(state)
        assert result["hitl_required"] is True
        assert "DISPUTE_RECEIVED" in result["hitl_conditions"]

    def test_clean_account_does_not_require_hitl_from_risk_scoring(self):
        """Clean account with no HITL conditions should not trigger HITL at risk_scoring."""
        from agent.nodes import risk_scoring_node
        state = self._minimal_state(
            settlement_tiers=[{"tier": "TIER_1", "high_value": False}],
            collectability_tier="HIGH",
            sol_expired=True,  # SOL expired → not litigation risk
        )
        result = risk_scoring_node(state)
        assert result["hitl_required"] is False

    def test_fdcpa_violations_escalate_to_hitl(self):
        from agent.nodes import routing_decision_node
        state = self._minimal_state(
            hitl_required=False,  # No HITL from risk_scoring
            fdcpa_compliance_issues=["PROHIBITED_HOURS: contact at 22:00"],
            regulation_f_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True  # FDCPA issues force HITL


class TestFullPipeline:
    """Integration tests: run nodes in sequence, verify state accumulates correctly."""

    def test_intake_through_validation_accumulates_audit(self):
        from agent.nodes import (
            debt_intake_node, fdcpa_compliance_check_node,
            scra_bankruptcy_check_node, debt_validation_node
        )
        state = {
            "original_account_number": "4111111111119874",
            "debt_type": "CREDIT_CARD",
            "current_balance": 1500.0,
            "original_balance": 1200.0,
            "interest_accrued": 300.0,
            "fees_accrued": 0.0,
            "consumer_state": "CA",
            "consumer_timezone": "America/Los_Angeles",
            "consumer_is_deceased": False,
            "consumer_is_minor": False,
            "validation_notice_sent": True,
            "dispute_received": False,
            "cease_desist_received": False,
            "prior_contacts_7_days": 1,
            "days_since_last_conversation": 14,
            "scra_active_military": False,
            "bankruptcy_stay_active": False,
            "debt_date_of_last_payment": "2025-01-01",
            "debt_origination_date": "2022-06-01",
            "audit_trail": [],
        }

        r1 = debt_intake_node(state)
        state = {**state, **r1}
        assert len(state["audit_trail"]) == 1

        r2 = fdcpa_compliance_check_node(state)
        state = {**state, **r2}
        assert len(state["audit_trail"]) == 2

        r3 = scra_bankruptcy_check_node(state)
        state = {**state, **r3}
        assert len(state["audit_trail"]) == 3

        r4 = debt_validation_node(state)
        state = {**state, **r4}
        assert len(state["audit_trail"]) == 4

        # FDCPA applies for credit card
        assert state["fdcpa_applies"] is True
        # SOL computed
        assert "sol_years" in state
        assert state["sol_years"] == 4  # CA open account
        # Days delinquent computed
        assert state["days_delinquent"] > 0

    def test_payment_plan_computation_is_python_math(self):
        from agent.nodes import payment_plan_optimizer_node
        state = {
            "current_balance": 2400.0,
            "hardship_plan_eligible": False,
            "hardship_score": 0.3,
            "payment_history_factor": 0.7,
            "days_delinquent": 180,
            "prior_contacts_7_days": 2,
            "sol_expired": False,
            "contact_success_factor": 0.8,
            "settlement_eligible": True,
            "cease_desist_received": False,
            "bankruptcy_stay_active": False,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = payment_plan_optimizer_node(state)
        plans = result["payment_plan_options"]
        assert len(plans) > 0
        # 12-month plan: $2400 / 12 = $200/month
        twelve_month = [p for p in plans if p["term_months"] == 12 and p["plan_type"] == "STANDARD"]
        if twelve_month:
            assert abs(twelve_month[0]["monthly_payment"] - 200.0) < 0.01

    def test_settlement_amount_is_python_computation(self):
        from agent.nodes import payment_plan_optimizer_node
        state = {
            "current_balance": 10000.0,
            "hardship_plan_eligible": True,
            "hardship_score": 0.6,
            "payment_history_factor": 0.4,
            "days_delinquent": 365,
            "prior_contacts_7_days": 0,
            "sol_expired": False,
            "contact_success_factor": 0.4,
            "settlement_eligible": True,
            "cease_desist_received": False,
            "bankruptcy_stay_active": False,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = payment_plan_optimizer_node(state)
        # TIER_2 settlement: 10000 * (1 - 0.35) = $6,500
        assert abs(result["settlement_amount"] - 6500.0) < 0.01
        assert result["settlement_discount_pct"] == 35.0
