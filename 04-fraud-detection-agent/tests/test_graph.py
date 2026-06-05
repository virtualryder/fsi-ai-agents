# tests/test_graph.py
# ============================================================
# Graph compilation, routing logic, and regulatory control tests
#
# Run: pytest tests/test_graph.py -v
# ============================================================

import pytest
from agent.graph import build_fraud_detection_graph, _route_after_scoring
from agent.state import FraudDetectionState, FraudDecision


class TestGraphCompilation:
    """Verify the LangGraph compiles without errors."""

    def test_graph_compiles_with_memory(self):
        """Graph with MemorySaver compiles successfully."""
        graph = build_fraud_detection_graph(use_memory=True)
        assert graph is not None

    def test_graph_compiles_without_memory(self):
        """Graph without checkpointer compiles successfully."""
        graph = build_fraud_detection_graph(use_memory=False)
        assert graph is not None

    def test_graph_has_correct_nodes(self):
        """All 14 nodes are present in the compiled graph."""
        graph = build_fraud_detection_graph(use_memory=False)
        node_names = set(graph.nodes.keys())
        expected_nodes = {
            "transaction_intake",
            "account_context_lookup",
            "feature_extraction",
            "rule_engine_prescoring",
            "device_intelligence",
            "behavioral_analysis",
            "llm_fraud_analysis",
            "composite_scoring",
            "block_transaction",
            "step_up_authentication",
            "flag_for_analyst_review",
            "allow_transaction",
            "human_review_gate",
            "finalize_decision",
        }
        assert expected_nodes.issubset(node_names)


class TestRoutingDecision:
    """Verify _route_after_scoring deterministic routing."""

    def _state(self, score: float, decision: FraudDecision, hard_block: bool = False) -> FraudDetectionState:
        return {
            "transaction_id": "TXN-TEST-001",
            "composite_fraud_score": score,
            "fraud_decision": decision,
            "hard_block_triggered": hard_block,
        }

    def test_route_block_high_score(self):
        """Score >= 85 routes to block_transaction."""
        state = self._state(90, FraudDecision.BLOCK)
        assert _route_after_scoring(state) == "block_transaction"

    def test_route_block_at_threshold(self):
        """Score exactly 85 routes to block_transaction."""
        state = self._state(85, FraudDecision.BLOCK)
        assert _route_after_scoring(state) == "block_transaction"

    def test_route_step_up(self):
        """Score 65-84 routes to step_up_authentication."""
        state = self._state(70, FraudDecision.STEP_UP_AUTH)
        assert _route_after_scoring(state) == "step_up_authentication"

    def test_route_analyst_review(self):
        """Score 40-64 routes to flag_for_analyst_review."""
        state = self._state(55, FraudDecision.ANALYST_REVIEW)
        assert _route_after_scoring(state) == "flag_for_analyst_review"

    def test_route_allow_low_score(self):
        """Score < 40 routes to allow_transaction."""
        state = self._state(25, FraudDecision.ALLOW)
        assert _route_after_scoring(state) == "allow_transaction"

    def test_hard_block_overrides_low_score(self):
        """
        Hard block triggered routes to block regardless of low score.

        CRITICAL regulatory test: hard block from known fraud IP or
        OFAC-adjacent merchant must route to block even if ML score is low.
        """
        state = self._state(20, FraudDecision.ALLOW, hard_block=True)
        assert _route_after_scoring(state) == "block_transaction"

    def test_hard_block_overrides_step_up(self):
        """Hard block overrides STEP_UP_AUTH decision."""
        state = self._state(70, FraudDecision.STEP_UP_AUTH, hard_block=True)
        assert _route_after_scoring(state) == "block_transaction"

    def test_freeze_account_routes_to_block(self):
        """FREEZE_ACCOUNT decision routes to block_transaction."""
        state = self._state(95, FraudDecision.FREEZE_ACCOUNT)
        assert _route_after_scoring(state) == "block_transaction"


class TestRegulatoryControls:
    """Verify regulatory hard controls are enforced correctly."""

    def test_hard_block_never_overridable_by_score(self):
        """
        Ensure no composite score prevents a hard block.
        This tests the OFAC/confirmed fraud IP guarantee.
        """
        for score in [0, 10, 20, 30, 40]:
            state = {
                "transaction_id": f"TXN-TEST-HARDBLOCK-{score}",
                "composite_fraud_score": float(score),
                "fraud_decision": FraudDecision.ALLOW,
                "hard_block_triggered": True,
            }
            result = _route_after_scoring(state)
            assert result == "block_transaction", (
                f"Hard block should route to block_transaction regardless of score {score}"
            )

    def test_allow_decision_never_hard_blocks_without_trigger(self):
        """ALLOW decision without hard_block_triggered routes to allow_transaction."""
        state = {
            "transaction_id": "TXN-TEST-ALLOW",
            "composite_fraud_score": 15.0,
            "fraud_decision": FraudDecision.ALLOW,
            "hard_block_triggered": False,
        }
        assert _route_after_scoring(state) == "allow_transaction"


class TestNodeImports:
    """Verify all node functions are importable (catches import errors early)."""

    def test_all_nodes_importable(self):
        from agent.nodes import (
            transaction_intake,
            account_context_lookup,
            feature_extraction,
            rule_engine_prescoring,
            device_intelligence,
            behavioral_analysis,
            llm_fraud_analysis,
            composite_scoring,
            block_transaction,
            step_up_authentication,
            flag_for_analyst_review,
            allow_transaction,
            human_review_gate,
            finalize_decision,
        )
        # All imports successful — no assertion needed

    def test_all_prompts_importable(self):
        from agent.prompts import (
            FRAUD_ANALYSIS_SYSTEM_PROMPT,
            FRAUD_ANALYSIS_HUMAN_PROMPT,
            REG_E_DISCLOSURE_PROMPT,
            CASE_NARRATIVE_PROMPT,
        )
        assert len(FRAUD_ANALYSIS_SYSTEM_PROMPT) > 100
        assert "{transaction_id}" in FRAUD_ANALYSIS_HUMAN_PROMPT
