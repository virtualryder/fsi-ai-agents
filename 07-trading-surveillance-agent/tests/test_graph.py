# tests/test_graph.py
# ============================================================
# Integration tests for the Trading Surveillance StateGraph.
# LLM calls are mocked. All Python logic runs live.
# ============================================================
import pytest
from unittest.mock import MagicMock, patch

from agent.graph import (
    build_trading_surveillance_graph,
    _route_after_routing_decision,
    _route_after_human_review,
)
from agent.nodes import alert_intake_node, risk_scoring_node
from agent.state import AlertType, AssetClass, CaseStatus, SeverityTier


# ── Mock LLM responses ────────────────────────────────────────────────────────

MOCK_MARKET_CONTEXT = (
    "No material corporate events were identified for TEST Corp on 2026-06-01. "
    "Broader markets were flat. No publicly available information explains "
    "the unusual order cancellation pattern detected."
)

MOCK_INVESTIGATION = """## Investigation Narrative

### Trading Activity Summary
Trader executed a series of large orders with an 85% cancellation rate.

### Pattern Analysis
Layering/spoofing pattern detected with high confidence.

### Evidence Assessment
**Supporting suspicious activity:**
- 85% order cancellation rate
- Opposite-side orders placed simultaneously

**Mitigating factors:**
- No prior enforcement actions

### Regulatory Considerations
SEA Section 9(a)(2); Dodd-Frank Section 747.

### Investigator Assessment
Activity warrants further review as potentially suspicious.
"""

MOCK_DISPOSITION = """## Surveillance Case Disposition Memorandum

**Case Reference:** SURV-TEST-001
**Disposition Date:** 2026-06-01

### Case Summary
Trading activity triggered layering/spoofing alert on 2026-06-01.

### Disposition
**Decision:** PENDING_INVESTIGATION

### Regulatory Reporting
FINRA notification under consideration.
"""


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def medium_alert_state():
    """UNUSUAL_ACTIVITY alert — low notional, no history — should not trigger HITL."""
    return {
        "alert_type": AlertType.UNUSUAL_ACTIVITY.value,
        "alert_source": "SURVEILLANCE_SYSTEM",
        "trader_id": "TRD-004",
        "trader_name": "Priya Patel",
        "desk": "EQUITIES_PROP",
        "account_id": "ACCT-31104",
        "instrument_id": "SAMPLE",
        "instrument_name": "Sample Corp",
        "asset_class": AssetClass.EQUITY.value,
        "trade_date": "2026-06-01",
        "notional_value": 12_000.0,
        "trade_direction": "BUY",
        "quantity": 500,
        "price": 24.0,
        "venue": "NYSE",
        "raw_alert_data": {"cancel_rate": 0.10, "order_count": 3},
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
        "corroborating_signals": [],
        "prior_alerts": [],
        "detected_patterns": [],
        "regulatory_flags": [],
        "secondary_reviewers": [],
        "evidence_summary": [],
        "regulatory_reporting_bodies": [],
    }


@pytest.fixture
def high_alert_state():
    """LAYERING_SPOOFING alert — large notional, prior history — should trigger HITL."""
    return {
        "alert_type": AlertType.LAYERING_SPOOFING.value,
        "alert_source": "SURVEILLANCE_SYSTEM",
        "trader_id": "TRD-001",
        "trader_name": "Alex Chen",
        "desk": "EQUITIES_PROP",
        "account_id": "ACCT-88421",
        "instrument_id": "GLOBEX",
        "instrument_name": "Globex Technologies Inc.",
        "asset_class": AssetClass.EQUITY.value,
        "trade_date": "2026-06-01",
        "notional_value": 3_500_000.0,
        "trade_direction": "BUY",
        "quantity": 50000,
        "price": 70.0,
        "venue": "NASDAQ",
        "raw_alert_data": {
            "cancel_rate": 0.87,
            "order_count": 24,
            "opposite_side_orders": True,
        },
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
        "corroborating_signals": [],
        "prior_alerts": [],
        "detected_patterns": [],
        "regulatory_flags": [],
        "secondary_reviewers": [],
        "evidence_summary": [],
        "regulatory_reporting_bodies": [],
    }


# ── TestGraphBuild ────────────────────────────────────────────────────────────

class TestGraphBuild:
    def test_builds_without_memory(self):
        graph = build_trading_surveillance_graph(use_memory=False)
        assert graph is not None

    def test_builds_with_memory(self):
        graph = build_trading_surveillance_graph(use_memory=True)
        assert graph is not None


# ── TestRoutingFunctions ──────────────────────────────────────────────────────

class TestRoutingFunctions:
    def test_high_severity_routes_to_hitl(self):
        state = {"human_review_required": True, "severity_tier": SeverityTier.HIGH.value}
        assert _route_after_routing_decision(state) == "human_review_gate"

    def test_medium_severity_skips_hitl(self):
        state = {"human_review_required": False, "severity_tier": SeverityTier.MEDIUM.value}
        assert _route_after_routing_decision(state) == "investigation_node"

    def test_low_severity_skips_hitl(self):
        state = {"human_review_required": False, "severity_tier": SeverityTier.LOW.value}
        assert _route_after_routing_decision(state) == "investigation_node"

    def test_after_human_review_goes_to_investigation(self):
        for decision in ["INVESTIGATE", "ESCALATE", "CLOSE_EXPLAINED", "CLOSE_NO_ACTION"]:
            state = {"reviewer_decision": decision}
            assert _route_after_human_review(state) == "investigation_node"


# ── TestFullWorkflow ──────────────────────────────────────────────────────────

class TestFullWorkflow:
    @patch("agent.nodes._get_llm")
    def test_medium_alert_completes_without_hitl(self, mock_llm, medium_alert_state):
        """UNUSUAL_ACTIVITY with low notional should complete without pausing."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = MagicMock(content=MOCK_INVESTIGATION)
        mock_llm.return_value = mock_instance

        graph = build_trading_surveillance_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-medium-001"}}

        for _ in graph.stream(medium_alert_state, config):
            pass

        snapshot = graph.get_state(config)
        assert not snapshot.next or "human_review_gate" not in snapshot.next
        assert snapshot.values.get("case_status") == CaseStatus.CLOSED.value

    @patch("agent.nodes._get_llm")
    def test_high_alert_pauses_at_hitl(self, mock_llm, high_alert_state):
        """LAYERING_SPOOFING with large notional should pause at human_review_gate."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = MagicMock(content=MOCK_INVESTIGATION)
        mock_llm.return_value = mock_instance

        graph = build_trading_surveillance_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-high-001"}}

        for _ in graph.stream(high_alert_state, config):
            pass

        snapshot = graph.get_state(config)
        assert snapshot.next and "human_review_gate" in snapshot.next

    @patch("agent.nodes._get_llm")
    def test_hitl_approval_resumes_workflow(self, mock_llm, high_alert_state):
        """After HITL decision injected, workflow completes to CLOSED."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = MagicMock(content=MOCK_INVESTIGATION)
        mock_llm.return_value = mock_instance

        graph = build_trading_surveillance_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-hitl-approve-001"}}

        for _ in graph.stream(high_alert_state, config):
            pass

        # Inject compliance officer decision
        graph.update_state(
            config,
            {
                "reviewer_id": "CO-001",
                "reviewer_decision": "INVESTIGATE",
                "reviewer_notes": "Proceed with full investigation.",
            },
            as_node="human_review_gate",
        )

        for _ in graph.stream(None, config):
            pass

        snapshot = graph.get_state(config)
        assert snapshot.values.get("case_status") == CaseStatus.CLOSED.value
        assert snapshot.values.get("reviewer_decision") == "INVESTIGATE"

    @patch("agent.nodes._get_llm")
    def test_close_no_action_closes_cleanly(self, mock_llm, high_alert_state):
        """CLOSE_NO_ACTION decision should close the case correctly."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = MagicMock(content=MOCK_INVESTIGATION)
        mock_llm.return_value = mock_instance

        graph = build_trading_surveillance_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-close-no-action-001"}}

        for _ in graph.stream(high_alert_state, config):
            pass

        graph.update_state(
            config,
            {
                "reviewer_id": "CO-002",
                "reviewer_decision": "CLOSE_NO_ACTION",
                "reviewer_notes": "Reviewed — market-making activity, no manipulation.",
            },
            as_node="human_review_gate",
        )

        for _ in graph.stream(None, config):
            pass

        snapshot = graph.get_state(config)
        assert snapshot.values.get("case_status") == CaseStatus.CLOSED.value


# ── TestAuditTrail ────────────────────────────────────────────────────────────

class TestAuditTrail:
    @patch("agent.nodes._get_llm")
    def test_audit_trail_populated(self, mock_llm, medium_alert_state):
        """At least 8 audit entries should be written for a full non-HITL workflow."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = MagicMock(content=MOCK_INVESTIGATION)
        mock_llm.return_value = mock_instance

        graph = build_trading_surveillance_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-audit-001"}}

        for _ in graph.stream(medium_alert_state, config):
            pass

        snapshot = graph.get_state(config)
        audit = snapshot.values.get("audit_trail", [])
        assert len(audit) >= 8

    @patch("agent.nodes._get_llm")
    def test_llm_nodes_marked_in_audit(self, mock_llm, medium_alert_state):
        """LLM-using nodes (market_context, investigation, disposition) should have ai_model_used set."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = MagicMock(content=MOCK_INVESTIGATION)
        mock_llm.return_value = mock_instance

        graph = build_trading_surveillance_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-audit-llm-001"}}

        for _ in graph.stream(medium_alert_state, config):
            pass

        snapshot = graph.get_state(config)
        audit = snapshot.values.get("audit_trail", [])
        llm_entries = [e for e in audit if e.get("ai_model_used")]
        assert len(llm_entries) >= 1
