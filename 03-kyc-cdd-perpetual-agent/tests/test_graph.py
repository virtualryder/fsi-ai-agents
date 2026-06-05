# tests/test_graph.py
# ============================================================
# Unit tests for the KYC/CDD Review LangGraph workflow
#
# Tests verify:
#   - Graph compiles without errors
#   - Correct node sequence for each trigger type
#   - Routing decisions match expected outcomes
#   - Hard regulatory overrides (OFAC → escalate, PEP → EDD)
#   - Human review gate is hit for non-PASS outcomes
#   - PASS outcomes skip human review and go directly to record update
# ============================================================

import pytest
from unittest.mock import patch, MagicMock

from agent.graph import build_kyc_review_graph, _route_after_scoring
from agent.state import KYCReviewState, RiskTier, ReviewOutcome, TriggerType


class TestGraphCompilation:
    """Tests that the graph structure is valid."""

    def test_graph_compiles_without_memory(self):
        """Graph should compile without errors in test mode."""
        graph = build_kyc_review_graph(use_memory=False)
        assert graph is not None

    def test_graph_compiles_with_memory(self):
        """Graph should compile with MemorySaver checkpointer."""
        graph = build_kyc_review_graph(use_memory=True)
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """Graph should contain all 12 nodes."""
        graph = build_kyc_review_graph(use_memory=False)
        node_names = set(graph.nodes.keys())
        expected_nodes = {
            "trigger_evaluation",
            "customer_risk_profile",
            "document_collection",
            "watchlist_screening",
            "adverse_media_check",
            "risk_rescoring",
            "edd_package_generation",
            "rm_notification",
            "human_review_gate",
            "initiate_relationship_exit",
            "kyc_record_update",
            "finalize_review",
        }
        for node in expected_nodes:
            assert node in node_names, f"Expected node '{node}' not found in graph"


class TestRoutingDecision:
    """Tests for the conditional routing function after risk rescoring."""

    def _make_state(self, outcome, ofac_hit=False):
        """Helper to create a minimal state dict for routing tests."""
        return {
            "recommended_outcome": outcome,
            "ofac_hit": ofac_hit,
            "review_id": "TEST-001",
        }

    def test_pass_routes_to_kyc_record_update(self):
        """PASS outcome should skip human review and go directly to record update."""
        state = self._make_state(ReviewOutcome.PASS)
        assert _route_after_scoring(state) == "kyc_record_update"

    def test_risk_upgrade_routes_to_edd_package(self):
        """RISK_UPGRADE should route to EDD package generation first."""
        state = self._make_state(ReviewOutcome.RISK_UPGRADE)
        assert _route_after_scoring(state) == "edd_package_generation"

    def test_risk_downgrade_routes_to_rm_notification(self):
        """RISK_DOWNGRADE should route to RM notification (then human review)."""
        state = self._make_state(ReviewOutcome.RISK_DOWNGRADE)
        assert _route_after_scoring(state) == "rm_notification"

    def test_edd_required_routes_to_edd_package(self):
        """EDD_REQUIRED should route to EDD package generation."""
        state = self._make_state(ReviewOutcome.EDD_REQUIRED)
        assert _route_after_scoring(state) == "edd_package_generation"

    def test_escalate_routes_to_human_review(self):
        """ESCALATE should go directly to human review gate."""
        state = self._make_state(ReviewOutcome.ESCALATE)
        assert _route_after_scoring(state) == "human_review_gate"

    def test_relationship_exit_routes_to_exit_node(self):
        """RELATIONSHIP_EXIT should route to exit initiation node."""
        state = self._make_state(ReviewOutcome.RELATIONSHIP_EXIT)
        assert _route_after_scoring(state) == "initiate_relationship_exit"

    def test_ofac_hit_overrides_all_routing(self):
        """OFAC hit should force escalation regardless of recommended_outcome."""
        # Even a PASS outcome should escalate if there's an OFAC hit
        state = self._make_state(ReviewOutcome.PASS, ofac_hit=True)
        assert _route_after_scoring(state) == "human_review_gate"

    def test_ofac_hit_overrides_risk_upgrade(self):
        """OFAC hit should force escalation even over risk upgrade recommendation."""
        state = self._make_state(ReviewOutcome.RISK_UPGRADE, ofac_hit=True)
        assert _route_after_scoring(state) == "human_review_gate"


class TestTriggerEvaluation:
    """Tests for the trigger_evaluation node."""

    def test_scheduled_trigger_gets_60_day_deadline(self):
        """Scheduled reviews should have a 60-day completion deadline."""
        from agent.nodes import trigger_evaluation
        state = {
            "customer_id": "CUST-TEST-001",
            "trigger_type": TriggerType.SCHEDULED,
            "trigger_description": "Annual scheduled review",
        }
        result = trigger_evaluation(state)
        assert "review_deadline" in result
        # Verify deadline is in the future
        from datetime import date
        deadline = date.fromisoformat(result["review_deadline"])
        assert deadline > date.today()
        assert result["case_status"] == "IN_PROGRESS"

    def test_ofac_trigger_gets_urgent_deadline(self):
        """Watchlist hit should get a 3-day deadline."""
        from agent.nodes import trigger_evaluation
        state = {
            "customer_id": "CUST-TEST-002",
            "trigger_type": TriggerType.WATCHLIST_HIT,
            "trigger_description": "OFAC screening match",
        }
        result = trigger_evaluation(state)
        from datetime import date, timedelta
        deadline = date.fromisoformat(result["review_deadline"])
        # Should be within 4 days of today (3 days + 1 day buffer)
        assert deadline <= date.today() + timedelta(days=4)

    def test_review_id_generated_if_missing(self):
        """Review ID should be auto-generated if not provided."""
        from agent.nodes import trigger_evaluation
        state = {
            "customer_id": "CUST-TEST-003",
            "trigger_type": TriggerType.SCHEDULED,
            "trigger_description": "Scheduled review",
        }
        result = trigger_evaluation(state)
        assert result.get("review_id") is not None
        assert "KYC-REVIEW" in result["review_id"]

    def test_audit_trail_entry_created(self):
        """Trigger evaluation should create an audit trail entry."""
        from agent.nodes import trigger_evaluation
        state = {
            "customer_id": "CUST-TEST-004",
            "trigger_type": TriggerType.ADVERSE_MEDIA,
            "trigger_description": "Reuters article",
        }
        result = trigger_evaluation(state)
        assert len(result.get("audit_trail", [])) > 0
        entry = result["audit_trail"][0]
        assert entry["node"] == "trigger_evaluation"
        assert entry["actor"] == "ai_agent"


class TestRegulatoryControls:
    """Tests for hard-coded regulatory override controls."""

    def test_pep_flag_preserved_through_watchlist(self):
        """PEP flag should be preserved or upgraded, never cleared by watchlist node."""
        from agent.nodes import watchlist_screening

        initial_pep_flag = True
        state = {
            "review_id": "TEST-REG-001",
            "customer_id": "CUST-PEP-001",
            "customer_name": "Jane Political Figure",
            "beneficial_owners": [],
            "account_ids": [],
            "pep_flag": initial_pep_flag,
            "audit_trail": [],
        }
        result = watchlist_screening(state)
        # PEP flag should never be cleared
        resulting_pep = result.get("pep_flag", state.get("pep_flag"))
        assert resulting_pep is True or resulting_pep == initial_pep_flag

    def test_human_review_required_for_escalate(self):
        """ESCALATE outcome should set human_review_required=True."""
        from agent.nodes import human_review_gate

        state = {
            "review_id": "TEST-REG-002",
            "recommended_outcome": ReviewOutcome.ESCALATE,
            "compliance_officer_decision": None,
            "audit_trail": [],
        }
        result = human_review_gate(state)
        assert result.get("human_review_required") is True
        assert result.get("case_status") == "PENDING_HUMAN_REVIEW"

    def test_risk_score_component_weights_sum_to_one(self):
        """SR 11-7: scoring model weights must sum to 1.0."""
        from tools.risk_scorer import COMPONENT_WEIGHTS
        total_weight = sum(COMPONENT_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001, (
            f"Risk score component weights sum to {total_weight}, expected 1.0. "
            "SR 11-7 requires a documented, complete scoring methodology."
        )
