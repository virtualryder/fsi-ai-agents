# tests/test_graph.py
# ============================================================
# Integration tests for the LangGraph workflow.
# LLM calls are mocked — these tests run without ANTHROPIC_API_KEY.
#
# Tests cover:
#   - Graph compilation
#   - Auto-approval path (no HITL)
#   - HITL interrupt and resume
#   - Adverse action path (decline)
#   - OFAC hard block propagates to final decision
#   - Fair lending flag forces HITL
# ============================================================
import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.graph import build_underwriting_graph
from agent.state import CollateralType, LoanDecision, LoanType, RiskTier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def graph():
    return build_underwriting_graph(checkpointer=MemorySaver())


@pytest.fixture
def thread_config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


@pytest.fixture
def strong_sba_state():
    """SBA 7(a) application that should auto-approve without HITL."""
    return {
        "application_id": f"TEST-{uuid.uuid4().hex[:6].upper()}",
        "applicant_id": "APP-004",
        "applicant_name": "Precision Machining Solutions Inc.",
        "applicant_type": "BUSINESS",
        "loan_type": LoanType.SBA_7A.value,
        "loan_purpose": "EQUIPMENT_PURCHASE",
        "application_source": "BRANCH",
        "requested_amount": 850000.0,
        "requested_term": 120,
        "quoted_rate": 0.1025,
        "collateral_type": CollateralType.SBA_GUARANTEE.value,
        "appraised_value": 980000.0,
        "annual_income": 2_100_000.0,
        "income_source": "BUSINESS",
        "monthly_debt_obligations": 22000.0,
        "net_operating_income": 340_000.0,
        "liquid_assets": 210_000.0,
        "credit_score": 781,
        "credit_score_model": "FICO_8",
        "derogatory_marks": 0,
        "bankruptcy_flag": False,
        "foreclosure_flag": False,
        "collections_count": 0,
        "collections_balance": 0.0,
        "thin_file_flag": False,
        "recent_inquiries_90d": 1,
        "ofac_hit": False,
        "property_state": "TX",
        "property_census_tract": None,
        "fair_lending_flags": [],
        "document_exceptions": [],
        "documents_received": [
            "GOVERNMENT_ID", "BUSINESS_TAX_RETURNS_3YR", "PERSONAL_TAX_RETURNS_2YR",
            "BUSINESS_FINANCIALS_3YR", "SBA_FORMS_1919_1920", "BUSINESS_PLAN",
            "COLLATERAL_DOCUMENTATION", "CREDIT_AUTHORIZATION",
        ],
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


@pytest.fixture
def decline_state():
    """Consumer loan that will decline (bankruptcy < 2 years)."""
    return {
        "application_id": f"TEST-{uuid.uuid4().hex[:6].upper()}",
        "applicant_id": "APP-002",
        "applicant_name": "Marcus D. Thompson",
        "applicant_type": "INDIVIDUAL",
        "loan_type": LoanType.CONSUMER_PERSONAL.value,
        "loan_purpose": "DEBT_CONSOLIDATION",
        "application_source": "ONLINE",
        "requested_amount": 22000.0,
        "requested_term": 60,
        "quoted_rate": 0.1299,
        "collateral_type": CollateralType.UNSECURED.value,
        "appraised_value": None,
        "annual_income": 61_000.0,
        "income_source": "W2",
        "monthly_debt_obligations": 1850.0,
        "liquid_assets": 1200.0,
        "credit_score": 598,
        "credit_score_model": "FICO_8",
        "derogatory_marks": 4,
        "bankruptcy_flag": True,
        "bankruptcy_chapter": "CHAPTER_7",
        "bankruptcy_discharge_years": 1.2,
        "foreclosure_flag": False,
        "collections_count": 3,
        "collections_balance": 8750.0,
        "thin_file_flag": False,
        "recent_inquiries_90d": 5,
        "ofac_hit": False,
        "property_state": None,
        "property_census_tract": None,
        "fair_lending_flags": [],
        "document_exceptions": [],
        "documents_received": [
            "GOVERNMENT_ID", "INCOME_VERIFICATION", "BANK_STATEMENTS_2MO",
            "CREDIT_AUTHORIZATION",
        ],
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


@pytest.fixture
def fair_lending_state():
    """Mortgage in flagged census tract — forces compliance officer HITL."""
    return {
        "application_id": f"TEST-{uuid.uuid4().hex[:6].upper()}",
        "applicant_id": "APP-001",
        "applicant_name": "James & Rachel Whitfield",
        "applicant_type": "INDIVIDUAL",
        "loan_type": LoanType.CONVENTIONAL_MORTGAGE.value,
        "loan_purpose": "PURCHASE",
        "application_source": "BRANCH",
        "requested_amount": 485000.0,
        "requested_term": 360,
        "quoted_rate": 0.0699,
        "collateral_type": CollateralType.PRIMARY_RESIDENCE.value,
        "appraised_value": 545000.0,
        "annual_income": 142_000.0,
        "income_source": "W2",
        "monthly_debt_obligations": 1250.0,
        "liquid_assets": 28000.0,
        "credit_score": 742,
        "credit_score_model": "FICO_8",
        "derogatory_marks": 1,
        "bankruptcy_flag": False,
        "foreclosure_flag": False,
        "collections_count": 1,
        "collections_balance": 850.0,
        "thin_file_flag": False,
        "recent_inquiries_90d": 2,
        "ofac_hit": False,
        "property_state": "IL",
        "property_census_tract": "17031838400",  # Flagged tract
        "fair_lending_flags": [],
        "document_exceptions": [],
        "documents_received": [
            "GOVERNMENT_ID", "INCOME_VERIFICATION", "TAX_RETURNS_2YR",
            "BANK_STATEMENTS_3MO", "PROPERTY_APPRAISAL", "PURCHASE_AGREEMENT",
            "CREDIT_AUTHORIZATION",
        ],
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }


# ── Graph Compilation ──────────────────────────────────────────────────────────

class TestGraphCompilation:
    def test_graph_compiles(self, graph):
        assert graph is not None

    def test_graph_has_expected_nodes(self, graph):
        node_names = set(graph.nodes.keys())
        expected = {
            "application_intake", "applicant_profile_lookup", "document_verification",
            "credit_bureau_pull", "financial_analysis", "fair_lending_check",
            "risk_scoring", "routing_decision", "human_review_gate",
            "credit_memo_drafting", "adverse_action_node", "finalize_decision",
        }
        for node in expected:
            assert node in node_names, f"Missing node: {node}"


# ── Auto-Approval Path ────────────────────────────────────────────────────────

class TestAutoApprovalPath:
    @patch("agent.nodes._get_llm")
    def test_strong_sba_auto_approves(self, mock_llm, graph, thread_config, strong_sba_state):
        """Strong SBA application should complete without HITL interrupt."""
        mock_llm.return_value.invoke.return_value = AIMessage(
            content="CREDIT MEMO: Approve. Strong DSCR and clean credit history."
        )
        final_state = None
        for event in graph.stream(strong_sba_state, thread_config):
            final_state = event

        snapshot = graph.get_state(thread_config)
        # Should not be interrupted at human_review_gate
        assert snapshot.next != ("human_review_gate",)
        final = snapshot.values
        assert final.get("final_decision") in (
            LoanDecision.APPROVED.value, LoanDecision.CONDITIONALLY_APPROVED.value
        )

    @patch("agent.nodes._get_llm")
    def test_completed_steps_populated(self, mock_llm, graph, thread_config, strong_sba_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Approved.")
        for _ in graph.stream(strong_sba_state, thread_config):
            pass
        snapshot = graph.get_state(thread_config)
        steps = snapshot.values.get("completed_steps", [])
        assert "application_intake" in steps
        assert "risk_scoring" in steps
        assert "finalize_decision" in steps


# ── HITL Interrupt and Resume ─────────────────────────────────────────────────

class TestHITLInterruptAndResume:
    @patch("agent.nodes._get_llm")
    def test_fair_lending_flag_interrupts_at_hitl(self, mock_llm, graph, thread_config, fair_lending_state):
        """Fair lending flag → mandatory HITL interrupt."""
        mock_llm.return_value.invoke.return_value = AIMessage(content="Memo draft.")
        for _ in graph.stream(fair_lending_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        # Should be paused at human_review_gate
        assert snapshot.next == ("human_review_gate",)
        assert snapshot.values.get("fair_lending_review_required") is True

    @patch("agent.nodes._get_llm")
    def test_hitl_resume_with_approve_decision(self, mock_llm, graph, thread_config, fair_lending_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Conditional approval memo.")
        for _ in graph.stream(fair_lending_state, thread_config):
            pass

        # Provide reviewer decision
        graph.update_state(
            thread_config,
            {
                "reviewer_id": "CO-FAIRLENDING-001",
                "reviewer_decision": "APPROVE_WITH_CONDITIONS",
                "reviewer_notes": "Fair lending review complete. Geographic flag documented. No discriminatory intent found.",
                "conditions_imposed": ["Provide written justification for property selection"],
            },
            as_node="human_review_gate",
        )

        # Resume
        for _ in graph.stream(None, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        assert snapshot.values.get("final_decision") == LoanDecision.CONDITIONALLY_APPROVED.value
        assert snapshot.values.get("reviewer_id") == "CO-FAIRLENDING-001"

    @patch("agent.nodes._get_llm")
    def test_hitl_resume_with_decline_generates_adverse_action(self, mock_llm, graph, thread_config, fair_lending_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Adverse action notice.")
        for _ in graph.stream(fair_lending_state, thread_config):
            pass

        graph.update_state(
            thread_config,
            {
                "reviewer_id": "UW-SENIOR-001",
                "reviewer_decision": "DECLINE",
                "reviewer_notes": "Inadequate collateral coverage after fair lending review.",
            },
            as_node="human_review_gate",
        )

        for _ in graph.stream(None, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        assert snapshot.values.get("final_decision") == LoanDecision.DECLINED.value
        assert snapshot.values.get("adverse_action_required") is True


# ── Decline and Adverse Action ────────────────────────────────────────────────

class TestDeclinePath:
    @patch("agent.nodes._get_llm")
    def test_bankruptcy_decline_generates_adverse_action(self, mock_llm, graph, thread_config, decline_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Adverse action notice text.")

        # Decline will trigger HITL (risk_tier=DECLINE requires review)
        for _ in graph.stream(decline_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        if snapshot.next == ("human_review_gate",):
            graph.update_state(
                thread_config,
                {
                    "reviewer_id": "UW-001",
                    "reviewer_decision": "DECLINE",
                    "reviewer_notes": "Hard decline: Chapter 7 bankruptcy less than 2 years.",
                },
                as_node="human_review_gate",
            )
            for _ in graph.stream(None, thread_config):
                pass

        snapshot = graph.get_state(thread_config)
        assert snapshot.values.get("final_decision") == LoanDecision.DECLINED.value
        assert snapshot.values.get("adverse_action_required") is True
        assert snapshot.values.get("hard_decline_triggered") is True

    @patch("agent.nodes._get_llm")
    def test_adverse_action_deadline_set(self, mock_llm, graph, thread_config, decline_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Notice.")
        for _ in graph.stream(decline_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        if snapshot.next == ("human_review_gate",):
            graph.update_state(
                thread_config,
                {"reviewer_id": "UW-001", "reviewer_decision": "DECLINE", "reviewer_notes": ""},
                as_node="human_review_gate",
            )
            for _ in graph.stream(None, thread_config):
                pass

        snapshot = graph.get_state(thread_config)
        # 30-day deadline must be present (Reg B § 1002.9)
        assert snapshot.values.get("adverse_action_deadline") is not None


# ── OFAC Hard Block ────────────────────────────────────────────────────────────

class TestOFACHardBlock:
    @patch("agent.nodes._get_llm")
    def test_ofac_hit_routes_to_bsa_officer(self, mock_llm, graph, thread_config, strong_sba_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="OFAC review memo.")
        strong_sba_state["ofac_hit"] = True

        for _ in graph.stream(strong_sba_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        # Should be paused at HITL (BSA officer review)
        assert snapshot.next == ("human_review_gate",)
        assert snapshot.values.get("assigned_underwriter") == "BSA_OFFICER"

    @patch("agent.nodes._get_llm")
    def test_ofac_hit_results_in_decline_after_review(self, mock_llm, graph, thread_config, strong_sba_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Decline memo.")
        strong_sba_state["ofac_hit"] = True

        for _ in graph.stream(strong_sba_state, thread_config):
            pass

        graph.update_state(
            thread_config,
            {
                "reviewer_id": "BSA-OFFICER-001",
                "reviewer_decision": "DECLINE",
                "reviewer_notes": "Confirmed OFAC SDN match. SAR referral initiated.",
            },
            as_node="human_review_gate",
        )

        for _ in graph.stream(None, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        assert snapshot.values.get("final_decision") == LoanDecision.DECLINED.value
        assert snapshot.values.get("sar_referral") is True


# ── Audit Trail Integrity ─────────────────────────────────────────────────────

class TestAuditTrailIntegrity:
    @patch("agent.nodes._get_llm")
    def test_audit_trail_populated_with_all_nodes(self, mock_llm, graph, thread_config, strong_sba_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Approved.")
        for _ in graph.stream(strong_sba_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        audit = snapshot.values.get("audit_trail", [])
        steps = {entry["step"] for entry in audit}
        expected_steps = {
            "application_intake", "applicant_profile_lookup", "document_verification",
            "credit_bureau_pull", "financial_analysis", "fair_lending_check",
            "risk_scoring", "routing_decision", "credit_memo_drafting", "finalize_decision",
        }
        for step in expected_steps:
            assert step in steps, f"Missing audit step: {step}"

    @patch("agent.nodes._get_llm")
    def test_audit_entries_have_timestamps(self, mock_llm, graph, thread_config, strong_sba_state):
        mock_llm.return_value.invoke.return_value = AIMessage(content="Approved.")
        for _ in graph.stream(strong_sba_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        audit = snapshot.values.get("audit_trail", [])
        for entry in audit:
            assert "timestamp" in entry
            assert "T" in entry["timestamp"]  # ISO-8601 with time component

    @patch("agent.nodes._get_llm")
    def test_no_ssn_in_audit_trail(self, mock_llm, graph, thread_config, strong_sba_state):
        """PII must not appear in audit trail."""
        mock_llm.return_value.invoke.return_value = AIMessage(content="Approved.")
        strong_sba_state["applicant_name"] = "Test 123-45-6789"  # Inject SSN pattern
        for _ in graph.stream(strong_sba_state, thread_config):
            pass

        snapshot = graph.get_state(thread_config)
        audit = snapshot.values.get("audit_trail", [])
        audit_str = str(audit)
        # SSN pattern should not appear in audit trail
        import re
        ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
        assert not re.search(ssn_pattern, audit_str), "SSN found in audit trail — PII leak"
