# tests/test_graph.py
# ============================================================
# Integration tests for the LangGraph investigation workflow.
# Tests graph construction and individual node execution without LLM calls.
# Run: pytest tests/ -v
# ============================================================

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from agent.state import InvestigationState, RecommendedAction
from agent.nodes import (
    alert_intake,
    customer_profile_lookup,
    watchlist_screening,
    risk_scoring,
    routing_decision,
    close_case,
    finalize_case,
    human_review_gate,
    _algorithmic_fallback_score,
)
from agent.graph import build_investigation_graph, get_graph_visualization


# ── SHARED FIXTURES ───────────────────────────────────────────────────────────

@pytest.fixture
def minimal_state():
    """Minimal valid investigation state for testing."""
    return {
        "alert_id": "ALT-TEST-001",
        "alert_type": "STRUCTURING",
        "alert_severity": "HIGH",
        "alert_source": "Rule-Based TMS",
        "alert_date": "2024-11-15",
        "triggered_rule": "CASH-STRUCT-001",
        "customer_id": "CUST-001",
        "account_ids": ["CUST-001-ACC001"],
        "investigator_id": "BSA_OFFICER",
        "messages": [],
        "completed_steps": [],
        "errors": [],
        "audit_trail": [],
        "investigation_notes": [],
        "risk_factors": [],
        "watchlist_hits": [],
        "adverse_media_hits": [],
    }


@pytest.fixture
def high_risk_state(minimal_state):
    """State with high-risk indicators for SAR routing test."""
    state = dict(minimal_state)
    state.update({
        "customer_profile": {
            "full_name": "Test Subject",
            "risk_tier": "HIGH",
            "edd_status": "ACTIVE",
            "pep_flag": False,
            "beneficial_owners": [],
            "prior_sars": 0,
        },
        "watchlist_hits": [
            {
                "list_type": "OFAC_SDN",
                "list_name": "OFAC SDN",
                "screened_name": "Test",
                "match_score": 90,
                "hit": True,
            }
        ],
        "transaction_patterns": {
            "structuring": {"detected": True, "confidence": "HIGH", "total_amount": 76450},
            "layering": {"detected": False},
            "velocity_anomalies": {"detected": True, "spike_ratio": 5.0},
            "summary": {
                "primary_typology": "Structuring",
                "total_suspicious_volume": 76450,
                "activity_start_date": "2024-11-04",
                "activity_end_date": "2024-11-14",
                "total_transactions_flagged": 8,
            },
        },
        "network_graph": {
            "shell_company_findings": {},
            "circular_flows": [],
            "high_risk_jurisdictions": [],
            "network_risk_score": {"score": 15},
        },
        "adverse_media_hits": [],
        "risk_score": 78.0,
        "recommended_action": RecommendedAction.FILE_SAR,
    })
    return state


@pytest.fixture
def low_risk_state(minimal_state):
    """State with low risk score for close case routing test."""
    state = dict(minimal_state)
    state.update({
        "customer_profile": {
            "full_name": "Clean Customer",
            "risk_tier": "LOW",
            "edd_status": "NOT_REQUIRED",
            "pep_flag": False,
            "beneficial_owners": [],
            "prior_sars": 0,
        },
        "watchlist_hits": [],
        "transaction_patterns": {
            "structuring": {"detected": False},
            "layering": {"detected": False},
            "velocity_anomalies": {"detected": False, "spike_ratio": 1.1},
            "summary": {
                "primary_typology": "None",
                "total_suspicious_volume": 0,
            },
        },
        "network_graph": {
            "shell_company_findings": {},
            "circular_flows": [],
            "high_risk_jurisdictions": [],
            "network_risk_score": {"score": 0},
        },
        "adverse_media_hits": [],
        "risk_score": 15.0,
        "recommended_action": RecommendedAction.CLOSE,
    })
    return state


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphConstruction:

    def test_graph_builds_without_error(self):
        """The investigation graph compiles without errors."""
        graph = build_investigation_graph(use_memory=False)
        assert graph is not None

    def test_graph_with_memory_builds(self):
        """The investigation graph with memory checkpointing compiles."""
        graph = build_investigation_graph(use_memory=True)
        assert graph is not None

    def test_graph_visualization_returns_string(self):
        """Graph visualization returns a Mermaid string."""
        viz = get_graph_visualization()
        assert isinstance(viz, str)
        assert "graph TD" in viz
        assert "alert_intake" in viz
        assert "risk_scoring" in viz
        assert "generate_sar" in viz


# ══════════════════════════════════════════════════════════════════════════════
# NODE UNIT TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAlertIntakeNode:

    def test_alert_intake_updates_current_step(self, minimal_state):
        """Alert intake sets current_step correctly."""
        with patch("agent.nodes._get_llm") as mock_llm:
            mock_response = MagicMock()
            mock_response.content = '{"alert_classification": "STRUCTURING", "typology_match": "Structuring", "preliminary_risk": "HIGH", "risk_rationale": "Multiple sub-10K cash deposits", "investigation_priorities": ["Review transactions"], "regulatory_flags": [], "working_hypothesis": "Structuring to evade CTR", "estimated_investigation_complexity": "MODERATE"}'
            mock_llm.return_value.invoke.return_value = mock_response

            result = alert_intake(minimal_state)

        assert "completed_steps" in result
        assert "alert_intake" in result.get("completed_steps", [])

    def test_alert_intake_creates_audit_entry(self, minimal_state):
        """Alert intake creates an audit trail entry."""
        with patch("agent.nodes._get_llm") as mock_llm:
            mock_response = MagicMock()
            mock_response.content = '{"alert_classification": "STRUCTURING", "typology_match": "Structuring", "preliminary_risk": "HIGH", "risk_rationale": "test", "investigation_priorities": [], "regulatory_flags": [], "working_hypothesis": "test", "estimated_investigation_complexity": "SIMPLE"}'
            mock_llm.return_value.invoke.return_value = mock_response

            result = alert_intake(minimal_state)

        assert len(result.get("audit_trail", [])) >= 1

    def test_alert_intake_missing_required_fields(self):
        """Alert intake gracefully handles missing required fields."""
        bad_state = {
            "messages": [],
            "completed_steps": [],
            "errors": [],
            "audit_trail": [],
            "investigation_notes": [],
            "risk_factors": [],
        }
        result = alert_intake(bad_state)
        # Should not raise an exception — errors should be captured
        assert isinstance(result, dict)
        assert len(result.get("errors", [])) >= 1


class TestCustomerProfileNode:

    def test_customer_profile_lookup_completes(self, minimal_state):
        """Customer profile lookup completes successfully with fixture data."""
        result = customer_profile_lookup(minimal_state)
        assert "customer_profile_lookup" in result.get("completed_steps", [])
        assert result.get("customer_profile") is not None

    def test_customer_profile_has_risk_tier(self, minimal_state):
        """Customer profile includes risk tier after lookup."""
        result = customer_profile_lookup(minimal_state)
        profile = result.get("customer_profile", {})
        assert "risk_tier" in profile
        assert profile["risk_tier"] in ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]

    def test_entity_customer_gets_beneficial_owners(self):
        """Entity customer gets beneficial ownership data."""
        state = {
            "customer_id": "CUST-002",
            "account_ids": ["CUST-002-ACC001"],
            "investigator_id": "BSA_OFFICER",
            "messages": [],
            "completed_steps": [],
            "errors": [],
            "audit_trail": [],
            "investigation_notes": [],
            "risk_factors": [],
        }
        result = customer_profile_lookup(state)
        profile = result.get("customer_profile", {})
        assert "beneficial_owners" in profile or profile.get("customer_type") != "ENTITY"


class TestRoutingDecision:

    def test_high_score_routes_to_sar(self, high_risk_state):
        """Risk score > 70 routes to generate_sar."""
        high_risk_state["risk_score"] = 80.0
        high_risk_state["recommended_action"] = RecommendedAction.FILE_SAR
        result = routing_decision(high_risk_state)
        assert result == "generate_sar"

    def test_medium_score_routes_to_review(self, minimal_state):
        """Risk score 30-70 routes to human_review_gate."""
        minimal_state["risk_score"] = 50.0
        minimal_state["recommended_action"] = RecommendedAction.ESCALATE
        result = routing_decision(minimal_state)
        assert result == "human_review_gate"

    def test_low_score_routes_to_close(self, low_risk_state):
        """Risk score < 30 routes to close_case."""
        low_risk_state["risk_score"] = 15.0
        low_risk_state["recommended_action"] = RecommendedAction.CLOSE
        result = routing_decision(low_risk_state)
        assert result == "close_case"


class TestCloseCaseNode:

    def test_close_case_sets_status(self, low_risk_state):
        """Close case sets case status to CLOSED."""
        result = close_case(low_risk_state)
        assert result.get("case_status") == "CLOSED"

    def test_close_case_adds_note(self, low_risk_state):
        """Close case adds a note explaining the closure."""
        result = close_case(low_risk_state)
        notes = result.get("investigation_notes", [])
        assert any("CLOSED" in note for note in notes)

    def test_close_case_sets_recommended_action(self, low_risk_state):
        """Close case sets recommended action to CLOSE."""
        result = close_case(low_risk_state)
        assert result.get("recommended_action") == RecommendedAction.CLOSE


class TestHumanReviewGateNode:

    def test_human_review_gate_sets_pending_status(self, high_risk_state):
        """Human review gate sets case status to PENDING_HUMAN_REVIEW."""
        result = human_review_gate(high_risk_state)
        assert result.get("case_status") == "PENDING_HUMAN_REVIEW"

    def test_human_review_gate_adds_step(self, high_risk_state):
        """Human review gate adds itself to completed steps."""
        result = human_review_gate(high_risk_state)
        assert "human_review_gate" in result.get("completed_steps", [])


class TestFinalizeCaseNode:

    def test_finalize_case_creates_case_id(self, minimal_state):
        """Finalize case creates a case ID."""
        minimal_state["recommended_action"] = RecommendedAction.ESCALATE
        minimal_state["case_status"] = "PENDING_REVIEW"
        minimal_state["risk_score"] = 45.0
        result = finalize_case(minimal_state)
        assert result.get("case_id") is not None
        assert result["case_id"].startswith("CASE-")

    def test_finalize_case_adds_step(self, minimal_state):
        """Finalize case adds itself to completed steps."""
        minimal_state["recommended_action"] = RecommendedAction.ESCALATE
        minimal_state["case_status"] = "PENDING_REVIEW"
        minimal_state["risk_score"] = 45.0
        result = finalize_case(minimal_state)
        assert "finalize_case" in result.get("completed_steps", [])


class TestAlgorithmicFallbackScore:

    def test_fallback_returns_dict(self, minimal_state):
        """Fallback scoring returns a valid scoring dictionary."""
        result = _algorithmic_fallback_score(minimal_state)
        assert isinstance(result, dict)
        assert "total_score" in result
        assert "recommended_action" in result

    def test_fallback_score_bounded(self, minimal_state):
        """Fallback score is between 0 and 100."""
        result = _algorithmic_fallback_score(minimal_state)
        assert 0 <= result["total_score"] <= 100

    def test_fallback_ofac_hits_drive_high_score(self, high_risk_state):
        """OFAC hits drive high scores in fallback scoring."""
        result = _algorithmic_fallback_score(high_risk_state)
        assert result["total_score"] >= 25  # OFAC hits add 28 pts

    def test_fallback_clean_state_low_score(self, low_risk_state):
        """Clean state produces low fallback score."""
        result = _algorithmic_fallback_score(low_risk_state)
        assert result["total_score"] <= 25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
