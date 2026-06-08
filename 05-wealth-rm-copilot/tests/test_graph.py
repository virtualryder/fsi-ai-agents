# tests/test_graph.py
# ============================================================
# Graph compilation, routing, and regulatory control tests
# Run: pytest tests/test_graph.py -v
# ============================================================

import pytest
from agent.graph import build_wealth_rm_graph, _route_after_suitability
from agent.state import WealthRMState, SuitabilityStatus, RequestType


class TestGraphCompilation:
    def test_graph_compiles_with_memory(self):
        graph = build_wealth_rm_graph(use_memory=True)
        assert graph is not None

    def test_graph_compiles_without_memory(self):
        graph = build_wealth_rm_graph(use_memory=False)
        assert graph is not None

    def test_graph_has_all_nodes(self):
        graph = build_wealth_rm_graph(use_memory=False)
        expected = {
            "trigger_intake", "client_profile_lookup", "portfolio_analysis",
            "market_intelligence", "suitability_check", "recommendation_engine",
            "content_drafting", "compliance_review", "rm_approval_gate",
            "finalize_output", "block_unsuitable",
        }
        assert expected.issubset(set(graph.nodes.keys()))


class TestSuitabilityRouting:
    """Verify _route_after_suitability deterministic logic."""

    def _state(self, status: SuitabilityStatus) -> WealthRMState:
        return {"request_id": "RM-TEST-001", "suitability_status": status}

    def test_unsuitable_routes_to_block(self):
        state = self._state(SuitabilityStatus.UNSUITABLE)
        assert _route_after_suitability(state) == "block_unsuitable"

    def test_suitable_routes_to_recommendations(self):
        state = self._state(SuitabilityStatus.SUITABLE)
        assert _route_after_suitability(state) == "recommendation_engine"

    def test_suitable_with_note_routes_to_recommendations(self):
        """Suitable with disclosure requirements still proceeds."""
        state = self._state(SuitabilityStatus.SUITABLE_WITH_NOTE)
        assert _route_after_suitability(state) == "recommendation_engine"

    def test_needs_review_routes_to_recommendations(self):
        """NEEDS_REVIEW proceeds with flagged open items."""
        state = self._state(SuitabilityStatus.NEEDS_REVIEW)
        assert _route_after_suitability(state) == "recommendation_engine"

    def test_unsuitable_never_proceeds_to_recommendations(self):
        """
        Critical regulatory test: UNSUITABLE must always block.
        Unsuitable recommendations must never be drafted or sent to clients.
        (FINRA 2111 / Reg BI care obligation)
        """
        state = self._state(SuitabilityStatus.UNSUITABLE)
        result = _route_after_suitability(state)
        assert result != "recommendation_engine"
        assert result == "block_unsuitable"


class TestRegulatoryControls:
    """Verify key regulatory controls are enforced."""

    def test_high_risk_product_conservative_client_unsuitable(self):
        """
        Leveraged/speculative product for conservative client must be UNSUITABLE.
        FINRA 2111 customer-specific suitability.
        """
        from agent.nodes import suitability_check
        state = {
            "request_id": "RM-TEST-SUIT",
            "rm_id": "RM-001",
            "client_id": "CUST-001",
            "request_type": RequestType.INVESTMENT_PROPOSAL,
            "investment_idea": "3x leveraged technology ETF",
            "client_profile": {
                "full_name": "Test Client",
                "age": 65,
                "risk_tolerance": "CONSERVATIVE",
                "time_horizon_years": 10,
                "is_retirement_account": False,
            },
            "ips_summary": {
                "prohibited_securities": [],
                "esg_screens": [],
                "last_updated": "2025-01-01",
                "ips_version": "v1.0",
            },
            "allocation_drift": {},
            "concentrated_positions": [],
            "completed_steps": [],
            "audit_trail": [],
        }
        result = suitability_check(state)
        assert result["suitability_status"] == SuitabilityStatus.UNSUITABLE

    def test_retirement_account_gets_erisa_disclosure(self):
        """ERISA accounts must receive fiduciary disclosure."""
        from agent.nodes import suitability_check
        state = {
            "request_id": "RM-TEST-ERISA",
            "rm_id": "RM-001",
            "client_id": "CUST-002",
            "request_type": RequestType.MEETING_PREP,
            "investment_idea": "",
            "client_profile": {
                "full_name": "Test Client",
                "age": 60,
                "risk_tolerance": "MODERATE",
                "time_horizon_years": 20,
                "is_retirement_account": True,
            },
            "ips_summary": {
                "prohibited_securities": [],
                "esg_screens": [],
                "last_updated": "2025-06-01",
                "ips_version": "v1.0",
            },
            "allocation_drift": {},
            "concentrated_positions": [],
            "completed_steps": [],
            "audit_trail": [],
        }
        result = suitability_check(state)
        disclosures = result["suitability_analysis"]["conflict_of_interest_disclosures"]
        assert any("ERISA" in d for d in disclosures)
        assert result["suitability_status"] in (
            SuitabilityStatus.SUITABLE_WITH_NOTE,
            SuitabilityStatus.SUITABLE,
        )

    def test_prohibited_security_routes_to_unsuitable(self):
        """IPS-prohibited security must return UNSUITABLE."""
        from agent.nodes import suitability_check
        state = {
            "request_id": "RM-TEST-PROHIBITED",
            "rm_id": "RM-001",
            "client_id": "CUST-003",
            "request_type": RequestType.INVESTMENT_PROPOSAL,
            "investment_idea": "tobacco company stock",
            "client_profile": {
                "full_name": "Test Client",
                "age": 50,
                "risk_tolerance": "MODERATE",
                "time_horizon_years": 15,
                "is_retirement_account": False,
            },
            "ips_summary": {
                "prohibited_securities": ["tobacco"],
                "esg_screens": ["tobacco"],
                "last_updated": "2025-06-01",
                "ips_version": "v1.0",
            },
            "allocation_drift": {},
            "concentrated_positions": [],
            "completed_steps": [],
            "audit_trail": [],
        }
        result = suitability_check(state)
        assert result["suitability_status"] == SuitabilityStatus.UNSUITABLE


class TestNodeImports:
    def test_all_nodes_importable(self):
        from agent.nodes import (
            trigger_intake, client_profile_lookup, portfolio_analysis,
            market_intelligence, suitability_check, recommendation_engine,
            content_drafting, compliance_review, rm_approval_gate,
            finalize_output, block_unsuitable,
        )

    def test_all_prompts_importable(self):
        from agent.prompts import (
            MEETING_BRIEFING_SYSTEM_PROMPT,
            INVESTMENT_PROPOSAL_SYSTEM_PROMPT,
            PORTFOLIO_REVIEW_SYSTEM_PROMPT,
            COMPLIANCE_CHECK_SYSTEM_PROMPT,
        )
        assert "DRAFT" in MEETING_BRIEFING_SYSTEM_PROMPT or "AI DRAFT" in MEETING_BRIEFING_SYSTEM_PROMPT or len(MEETING_BRIEFING_SYSTEM_PROMPT) > 100
