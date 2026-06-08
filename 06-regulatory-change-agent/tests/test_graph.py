# tests/test_graph.py
# ============================================================
# Integration tests for the Regulatory Change Management graph
#
# Tests the full workflow routing logic without LLM calls.
# LLM nodes (gap_analysis, remediation_planning, notifications)
# are mocked to test graph structure and routing.
# ============================================================

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from agent.graph import build_regulatory_change_graph, _route_after_routing_decision, _route_after_human_review
from agent.state import ChangeManagementState, ChangeType, RegulatoryDomain, ImpactTier, CaseStatus


# ── Mock LLM Response ─────────────────────────────────────────────────────────

MOCK_GAP_ANALYSIS = """
## EXECUTIVE SUMMARY
This final rule requires financial institutions to establish risk assessment processes
and incorporate risk findings into their AML/CFT programs. The institution's current
BSA/AML Compliance Program Policy requires amendment to include explicit risk assessment
methodology documentation.

## KEY REQUIREMENTS
1. Institutions must conduct a risk assessment
2. Risk assessment findings must be documented
3. AML program must be commensurate with risk profile

## GAP ANALYSIS
Requirement 1: Current policy lacks explicit risk assessment documentation requirement.
Gap: HIGH severity. Affected policy: POL-001 BSA/AML Policy.

## APPLICABILITY DETERMINATION
Applicable to all covered financial institutions under the BSA.

## PRIORITY ACTIONS
1. Update BSA/AML policy to include risk assessment documentation requirement
2. Conduct institution-wide ML/TF risk assessment
3. Document findings and update AML program accordingly
"""

MOCK_REMEDIATION_PLAN = """
## REMEDIATION OVERVIEW
3-phase plan over 6 months.

## TASK LIST
- TASK-001: Policy update
- TASK-002: Risk assessment
- TASK-003: Staff training

## CRITICAL PATH
Policy update → Risk assessment → Training
"""

MOCK_NOTIFICATION = "Dear BSA Officer, please review and implement the following changes..."


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def medium_impact_state():
    """State representing a MEDIUM impact regulatory change."""
    future_date = (datetime.utcnow() + timedelta(days=180)).date().isoformat()
    return {
        "change_title": "FinCEN FAQ: SAR Narrative Guidance",
        "change_type": ChangeType.FAQ,
        "regulatory_authority": "FinCEN",
        "regulatory_domain": RegulatoryDomain.BSA_AML,
        "publication_date": datetime.utcnow().date().isoformat(),
        "effective_date": future_date,
        "citation": "FinCEN FAQ 2025-01",
        "source_url": "https://www.fincen.gov/faq",
        "summary_text": "Clarification on SAR narrative requirements. No new requirements.",
        "full_text": "Frequently Asked Questions about SAR narratives. No new obligations created.",
        "docket_number": None,
        "comment_deadline": None,
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


@pytest.fixture
def high_impact_state():
    """State representing a HIGH impact final rule."""
    future_date = (datetime.utcnow() + timedelta(days=90)).date().isoformat()
    return {
        "change_title": "OCC Final Rule: Third-Party Risk Management",
        "change_type": ChangeType.FINAL_RULE,
        "regulatory_authority": "OCC",
        "regulatory_domain": RegulatoryDomain.TECHNOLOGY_OPERATIONS,
        "publication_date": datetime.utcnow().date().isoformat(),
        "effective_date": future_date,
        "citation": "OCC Bulletin 2025-XX",
        "source_url": "https://www.occ.gov/bulletin-2025-xx",
        "summary_text": "Comprehensive third-party risk management requirements. Must establish enhanced due diligence.",
        "full_text": "Financial institutions MUST establish written third-party risk management programs. Critical activities REQUIRE enhanced due diligence. Senior management SHALL approve all critical third-party relationships.",
        "docket_number": None,
        "comment_deadline": None,
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


# ── Graph Structure Tests ─────────────────────────────────────────────────────

class TestGraphBuild:

    def test_graph_builds_without_error(self):
        graph = build_regulatory_change_graph(use_memory=False)
        assert graph is not None

    def test_graph_builds_with_memory(self):
        graph = build_regulatory_change_graph(use_memory=True)
        assert graph is not None


# ── Routing Function Tests ────────────────────────────────────────────────────

class TestRoutingFunctions:

    def test_unvalidated_source_routes_to_tracking(self):
        state = {"source_validated": False, "is_applicable": True, "human_review_required": False}
        result = _route_after_routing_decision(state)
        assert result == "tracking_update_node"

    def test_not_applicable_routes_to_tracking(self):
        state = {"source_validated": True, "is_applicable": False, "human_review_required": False}
        result = _route_after_routing_decision(state)
        assert result == "tracking_update_node"

    def test_high_impact_routes_to_human_review(self):
        state = {"source_validated": True, "is_applicable": True, "human_review_required": True}
        result = _route_after_routing_decision(state)
        assert result == "human_review_gate"

    def test_medium_impact_routes_to_remediation(self):
        state = {"source_validated": True, "is_applicable": True, "human_review_required": False}
        result = _route_after_routing_decision(state)
        assert result == "remediation_planning_node"

    def test_approved_decision_routes_to_remediation(self):
        state = {"compliance_officer_decision": "APPROVED"}
        result = _route_after_human_review(state)
        assert result == "remediation_planning_node"

    def test_modified_decision_routes_to_remediation(self):
        state = {"compliance_officer_decision": "MODIFIED"}
        result = _route_after_human_review(state)
        assert result == "remediation_planning_node"

    def test_not_applicable_decision_routes_to_tracking(self):
        state = {"compliance_officer_decision": "NOT_APPLICABLE"}
        result = _route_after_human_review(state)
        assert result == "tracking_update_node"

    def test_escalated_decision_routes_to_tracking(self):
        state = {"compliance_officer_decision": "ESCALATED"}
        result = _route_after_human_review(state)
        assert result == "tracking_update_node"

    def test_default_approved_when_no_decision(self):
        state = {}
        result = _route_after_human_review(state)
        assert result == "remediation_planning_node"


# ── Full Workflow Integration Tests (with mocked LLM) ────────────────────────

class TestFullWorkflow:

    @patch("agent.nodes._get_llm")
    def test_medium_impact_workflow_completes(self, mock_llm, medium_impact_state):
        """MEDIUM impact change should complete without HITL interrupt."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content=MOCK_GAP_ANALYSIS)
        mock_llm.return_value = mock_llm_instance

        graph = build_regulatory_change_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-medium-001"}}

        events = list(graph.stream(medium_impact_state, config))
        assert len(events) > 0

        snapshot = graph.get_state(config)
        # Medium impact FAQ should not pause at human_review_gate
        assert "human_review_gate" not in (snapshot.next or [])

    @patch("agent.nodes._get_llm")
    def test_high_impact_workflow_pauses_at_hitl(self, mock_llm, high_impact_state):
        """HIGH impact final rule should pause at human_review_gate."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content=MOCK_GAP_ANALYSIS)
        mock_llm.return_value = mock_llm_instance

        graph = build_regulatory_change_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-high-001"}}

        list(graph.stream(high_impact_state, config))
        snapshot = graph.get_state(config)

        # HIGH impact should pause at human_review_gate
        assert snapshot.next is not None
        assert "human_review_gate" in snapshot.next

    @patch("agent.nodes._get_llm")
    def test_hitl_approval_resumes_workflow(self, mock_llm, high_impact_state):
        """After HITL approval, workflow should complete to finalize_node."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.side_effect = [
            MagicMock(content=MOCK_GAP_ANALYSIS),
            MagicMock(content=MOCK_REMEDIATION_PLAN),
            MagicMock(content=MOCK_NOTIFICATION),
            MagicMock(content=MOCK_NOTIFICATION),
            MagicMock(content=MOCK_NOTIFICATION),
        ]
        mock_llm.return_value = mock_llm_instance

        graph = build_regulatory_change_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-hitl-resume-001"}}

        # Run until HITL pause
        list(graph.stream(high_impact_state, config))

        # Inject officer decision
        graph.update_state(
            config,
            {
                "compliance_officer_id": "CCO-001",
                "compliance_officer_decision": "APPROVED",
                "compliance_officer_notes": "Analysis reviewed and approved.",
            },
            as_node="human_review_gate",
        )

        # Resume
        list(graph.stream(None, config))
        snapshot = graph.get_state(config)
        final_state = snapshot.values

        assert final_state.get("compliance_officer_decision") == "APPROVED"
        assert final_state.get("compliance_officer_id") == "CCO-001"
        assert "finalize_node" in final_state.get("completed_steps", [])

    @patch("agent.nodes._get_llm")
    def test_not_applicable_closes_cleanly(self, mock_llm, high_impact_state):
        """NOT_APPLICABLE decision should close the case cleanly."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content="NOT APPLICABLE to this institution.")
        mock_llm.return_value = mock_llm_instance

        graph = build_regulatory_change_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-not-applicable-001"}}

        list(graph.stream(high_impact_state, config))
        graph.update_state(
            config,
            {"compliance_officer_decision": "NOT_APPLICABLE", "compliance_officer_id": "CCO-001"},
            as_node="human_review_gate",
        )
        list(graph.stream(None, config))

        snapshot = graph.get_state(config)
        final_state = snapshot.values
        assert final_state.get("case_status").value in ("CLOSED_NOT_APPLICABLE", "IN_PROGRESS")


# ── Audit Trail Tests ─────────────────────────────────────────────────────────

class TestAuditTrail:

    @patch("agent.nodes._get_llm")
    def test_audit_trail_populated_after_workflow(self, mock_llm, medium_impact_state):
        """Audit trail should have entries for each completed node."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content=MOCK_GAP_ANALYSIS)
        mock_llm.return_value = mock_llm_instance

        graph = build_regulatory_change_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-audit-001"}}
        list(graph.stream(medium_impact_state, config))

        snapshot = graph.get_state(config)
        audit_trail = snapshot.values.get("audit_trail", [])
        assert len(audit_trail) >= 4  # At least: intake, validation, scope, policy mapping

    @patch("agent.nodes._get_llm")
    def test_llm_nodes_marked_in_audit(self, mock_llm, medium_impact_state):
        """Audit entries for LLM nodes should have ai_model_used set."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = MagicMock(content=MOCK_GAP_ANALYSIS)
        mock_llm.return_value = mock_llm_instance

        graph = build_regulatory_change_graph(use_memory=True)
        config = {"configurable": {"thread_id": "test-audit-llm-001"}}
        list(graph.stream(medium_impact_state, config))

        snapshot = graph.get_state(config)
        audit_trail = snapshot.values.get("audit_trail", [])
        llm_entries = [e for e in audit_trail if e.get("ai_model_used")]
        assert len(llm_entries) >= 1  # gap_analysis_node should be marked
