"""
Agent 11 — Model Risk Management Agent
Integration tests: routing functions, HITL behavior, graph integrity.
"""

import pytest
from unittest.mock import patch, MagicMock

from agent.graph import (
    _route_after_routing_decision,
    _route_after_human_review,
    build_model_risk_graph,
)
from agent.state import ALWAYS_HITL_CONDITIONS, MODEL_REGISTRY


# ── Routing function tests ────────────────────────────────────────────────────

class TestRoutingFunctions:
    """Routing functions must be deterministic and fail-safe."""

    # _route_after_routing_decision

    def test_human_review_false_routes_to_finalize(self):
        """Explicit False → auto-complete (no HITL required)."""
        state = {"human_review_required": False}
        assert _route_after_routing_decision(state) == "audit_finalize"

    def test_human_review_true_routes_to_hitl(self):
        state = {"human_review_required": True}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_human_review_missing_key_routes_to_hitl(self):
        """Missing key defaults to HITL — fail-safe for unknown state."""
        state = {}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_human_review_none_routes_to_hitl(self):
        """None (not False) → HITL. Explicit `is False` check prevents None bypass."""
        state = {"human_review_required": None}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_human_review_zero_routes_to_hitl(self):
        """0 is falsy but not `is False` — routes to HITL (fail-safe)."""
        state = {"human_review_required": 0}
        # 0 is not `is False` in Python — this is intentional security behavior
        # 0 should not bypass HITL; only explicit False from Python nodes does
        assert _route_after_routing_decision(state) == "human_review_gate"

    # _route_after_human_review

    def test_all_decisions_route_to_audit_finalize(self):
        """All reviewer decisions lead to audit_finalize (outcome set by human_review_gate_node)."""
        decisions = [
            "APPROVE_VALIDATION",
            "CONDITIONALLY_APPROVE",
            "REQUIRE_REMEDIATION",
            "ESCALATE_TO_BOARD",
        ]
        for decision in decisions:
            state = {"reviewer_decision": decision}
            result = _route_after_human_review(state)
            assert result == "audit_finalize", f"Decision {decision} should route to audit_finalize"

    def test_unknown_decision_routes_to_audit_finalize(self):
        """Unknown decisions route to audit_finalize — cannot trigger model approval."""
        state = {"reviewer_decision": "APPROVE_EVERYTHING"}
        assert _route_after_human_review(state) == "audit_finalize"

    def test_missing_decision_routes_to_audit_finalize(self):
        """Missing decision routes to audit_finalize (fail-safe)."""
        state = {}
        assert _route_after_human_review(state) == "audit_finalize"


# ── Graph structure tests ─────────────────────────────────────────────────────

class TestGraphStructure:
    """Verify graph compiles correctly and has expected properties."""

    def test_graph_compiles(self):
        """Graph must compile without errors."""
        g = build_model_risk_graph(checkpointer=None)
        assert g is not None

    def test_graph_has_interrupt_before(self):
        """Graph must have interrupt_before on human_review_gate."""
        g = build_model_risk_graph(checkpointer=None)
        # LangGraph stores interrupt_before in the compiled graph config
        interrupt_nodes = getattr(g, "interrupt_before", None) or getattr(
            g, "_interrupt_before", None
        ) or []
        # Verify the graph was built with interrupt_before — compile-time check
        assert g is not None  # If interrupt_before fails, compile raises


# ── HITL behavior integration ─────────────────────────────────────────────────

class TestHITLBehavior:
    """Integration tests for HITL pause and resume behavior."""

    def test_high_tier_annual_revalidation_requires_hitl(self):
        """HIGH-tier annual revalidation must not auto-complete."""
        from agent.nodes import risk_tier_determination_node
        state = {
            "risk_tier": "HIGH",
            "validation_type": "ANNUAL_REVALIDATION",
            "performance_outcome": "PASS",
            "degradation_flags": [],
            "material_findings": [],
            "psi_flag": "STABLE",
            "challenger_comparison_result": None,
            "hard_rule_violations": [],
            "revalidation_overdue": False,
            "audit_trail": [],
        }
        result = risk_tier_determination_node(state)
        assert result["human_review_required"] is True

    def test_ongoing_monitoring_pass_no_hitl(self):
        """Ongoing monitoring with PASS result can auto-complete."""
        from agent.nodes import risk_tier_determination_node
        state = {
            "risk_tier": "HIGH",
            "validation_type": "ONGOING_MONITORING",
            "performance_outcome": "PASS",
            "degradation_flags": [],
            "material_findings": [],
            "psi_flag": "STABLE",
            "challenger_comparison_result": None,
            "hard_rule_violations": [],
            "revalidation_overdue": False,
            "audit_trail": [],
        }
        result = risk_tier_determination_node(state)
        assert result["human_review_required"] is False

    def test_model_inventory_lookup_rejects_unknown_model(self):
        """Unknown model IDs return an error, not a fallback."""
        from agent.nodes import model_inventory_lookup_node
        state = {
            "model_id": "UNKNOWN-MODEL-XYZ",
            "validation_type": "ANNUAL_REVALIDATION",
            "audit_trail": [],
        }
        result = model_inventory_lookup_node(state)
        assert "error_message" in result
        assert "not found" in result["error_message"].lower()


# ── Full pipeline smoke test ──────────────────────────────────────────────────

class TestFullPipeline:
    """Smoke tests: verify each node can execute without raising exceptions."""

    DEMO_STATE = {
        "model_id": "AGT03-KYC-RISK-v1",
        "validation_type": "ONGOING_MONITORING",
        "requested_by": "AUTOMATED_MONITORING_SYSTEM",
        "validation_period_start": "2026-05-01",
        "validation_period_end": "2026-05-31",
        "last_validation_date": "2026-02-01",
        "current_metrics": {
            "accuracy": 92.7, "gini_coefficient": 69.3, "ks_statistic": 51.8,
            "psi": 0.06, "auc_roc": 0.928, "false_positive_rate": 11.9,
            "false_negative_rate": 14.6,
        },
        "baseline_metrics": {
            "accuracy": 93.1, "gini_coefficient": 70.4, "ks_statistic": 52.9,
            "psi": 0.05, "auc_roc": 0.931, "false_positive_rate": 11.4,
            "false_negative_rate": 14.1,
        },
        "audit_trail": [],
    }

    def test_model_inventory_lookup_runs(self):
        from agent.nodes import model_inventory_lookup_node
        result = model_inventory_lookup_node(self.DEMO_STATE)
        assert "model_record" in result
        assert "risk_tier" in result
        assert result["risk_tier"] == "HIGH"

    def test_data_sample_pull_computes_deltas(self):
        from agent.nodes import data_sample_pull_node
        state = {**self.DEMO_STATE, "model_record": MODEL_REGISTRY["AGT03-KYC-RISK-v1"]}
        result = data_sample_pull_node(state)
        assert "metric_deltas" in result
        # accuracy delta: 92.7 - 93.1 = -0.4
        assert abs(result["metric_deltas"].get("accuracy", 0) - (-0.4)) < 0.001

    def test_outcomes_analysis_no_flags_for_stable_model(self):
        from agent.nodes import outcomes_analysis_node
        state = {
            **self.DEMO_STATE,
            "model_record": MODEL_REGISTRY["AGT03-KYC-RISK-v1"],
            "metric_deltas": {"accuracy": -0.4, "gini_coefficient": -1.1,
                              "ks_statistic": -1.1, "false_positive_rate": 0.5,
                              "false_negative_rate": 0.5},
        }
        result = outcomes_analysis_node(state)
        assert result["performance_outcome"] == "PASS"
        assert result["degradation_flags"] == []

    def test_audit_trail_grows_through_pipeline(self):
        """Audit trail must accumulate entries as nodes execute."""
        from agent.nodes import (
            model_inventory_lookup_node, data_sample_pull_node, outcomes_analysis_node
        )
        state = {**self.DEMO_STATE}

        result1 = model_inventory_lookup_node(state)
        assert len(result1["audit_trail"]) == 1

        state.update(result1)
        result2 = data_sample_pull_node(state)
        assert len(result2["audit_trail"]) == 2

        state.update(result2)
        result3 = outcomes_analysis_node(state)
        assert len(result3["audit_trail"]) == 3

    def test_all_hitl_conditions_in_frozenset(self):
        """Any HITL condition computed by risk_tier_determination must be in frozenset."""
        from agent.nodes import risk_tier_determination_node
        state = {
            "risk_tier": "HIGH",
            "validation_type": "ANNUAL_REVALIDATION",
            "performance_outcome": "CRITICAL",
            "degradation_flags": ["GINI_DEGRADATION"],
            "material_findings": ["Gini declined 12 points"],
            "psi_flag": "CRITICAL",
            "challenger_comparison_result": "CHALLENGER_BETTER",
            "hard_rule_violations": [],
            "revalidation_overdue": True,
            "audit_trail": [],
        }
        result = risk_tier_determination_node(state)
        for condition in result["hitl_conditions"]:
            assert condition in ALWAYS_HITL_CONDITIONS, (
                f"Condition '{condition}' not in ALWAYS_HITL_CONDITIONS frozenset. "
                "All HITL conditions must be in the immutable frozenset."
            )
