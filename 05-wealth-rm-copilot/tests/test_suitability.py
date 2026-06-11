"""
Agent 05 — deterministic suitability + routing + HITL tests (Phase 2 test floor).

The field assessment flagged Agent 05 as the suite's weakest QA: 13 graph-only
tests, no assertions on the actual suitability logic — for an agent that makes
Reg BI / FINRA 2111 determinations. These tests exercise the deterministic
decision logic directly (no LLM, no mocks): `suitability_check` is pure Python,
so its determinations are unit-testable, and they must be, because an
UNSUITABLE recommendation must never reach a client.
"""
from __future__ import annotations

import pytest

from agent.nodes import block_unsuitable, suitability_check
from agent.graph import _route_after_suitability, build_wealth_rm_graph
from agent.state import RequestType, SuitabilityStatus


def _state(**overrides):
    base = {
        "request_id": "REQ-1",
        "client_id": "CL-1",
        "request_type": RequestType.INVESTMENT_PROPOSAL,
        "investment_idea": "",
        "client_profile": {"full_name": "Pat Client", "risk_tolerance": "MODERATE",
                            "time_horizon_years": 15, "is_retirement_account": False},
        "ips_summary": {"ips_version": "3", "last_updated": "2025-06-01",
                        "prohibited_securities": []},
        "allocation_drift": {},
        "concentrated_positions": [],
        "completed_steps": [],
        "audit_trail": [],
    }
    base.update(overrides)
    return base


def _status(result):
    s = result["suitability_status"]
    return s.value if hasattr(s, "value") else s


# ── suitability_check: the core determinations ────────────────────────────────
class TestSuitabilityDeterminations:
    def test_clean_case_is_suitable(self):
        r = suitability_check(_state(investment_idea="Add a diversified index fund"))
        assert _status(r) == "SUITABLE"

    def test_conservative_client_plus_leveraged_is_unsuitable(self):
        r = suitability_check(_state(
            client_profile={"full_name": "C", "risk_tolerance": "CONSERVATIVE",
                            "time_horizon_years": 5, "is_retirement_account": False},
            investment_idea="Buy a 3x leveraged ETF"))
        assert _status(r) == "UNSUITABLE"

    def test_moderate_conservative_plus_crypto_is_unsuitable(self):
        r = suitability_check(_state(
            client_profile={"full_name": "C", "risk_tolerance": "MODERATE_CONSERVATIVE",
                            "time_horizon_years": 7, "is_retirement_account": False},
            investment_idea="Allocate to cryptocurrency"))
        assert _status(r) == "UNSUITABLE"

    def test_aggressive_client_plus_leveraged_passes_risk_check(self):
        r = suitability_check(_state(
            client_profile={"full_name": "C", "risk_tolerance": "AGGRESSIVE",
                            "time_horizon_years": 25, "is_retirement_account": False},
            investment_idea="Buy a leveraged growth ETF"))
        assert _status(r) == "SUITABLE"

    def test_ips_prohibited_security_is_unsuitable(self):
        r = suitability_check(_state(
            investment_idea="Initiate a tobacco sector position",
            ips_summary={"ips_version": "3", "last_updated": "2025-01-01",
                         "prohibited_securities": ["tobacco"]}))
        assert _status(r) == "UNSUITABLE"

    def test_retirement_account_adds_erisa_note(self):
        r = suitability_check(_state(
            investment_idea="Add a diversified bond fund",
            client_profile={"full_name": "C", "risk_tolerance": "MODERATE",
                            "time_horizon_years": 15, "is_retirement_account": True}))
        assert _status(r) == "SUITABLE_WITH_NOTE"
        disclosures = r["suitability_analysis"]["conflict_of_interest_disclosures"]
        assert any("ERISA" in d for d in disclosures)

    def test_concentrated_positions_add_disclosure(self):
        r = suitability_check(_state(
            investment_idea="Add a diversified index fund",
            concentrated_positions=[{"name": "ACME", "symbol": "ACME"}]))
        assert _status(r) == "SUITABLE_WITH_NOTE"
        assert any("Concentration" in d for d in r["suitability_analysis"]["conflict_of_interest_disclosures"])

    def test_stale_ips_needs_review(self):
        r = suitability_check(_state(
            investment_idea="Add a diversified index fund",
            ips_summary={"ips_version": "1", "last_updated": "2022-03-01",
                         "prohibited_securities": []}))
        assert _status(r) == "NEEDS_REVIEW"

    def test_unsuitable_takes_precedence_over_with_note(self):
        # Conservative + leveraged (UNSUITABLE) on a retirement account (would add a
        # WITH_NOTE) must remain UNSUITABLE — a blocking determination is never
        # downgraded by a softer one.
        r = suitability_check(_state(
            client_profile={"full_name": "C", "risk_tolerance": "CONSERVATIVE",
                            "time_horizon_years": 5, "is_retirement_account": True},
            investment_idea="Buy a 3x leveraged ETF"))
        assert _status(r) == "UNSUITABLE"

    def test_non_investment_request_does_not_trip_risk_check(self):
        # Meeting prep with risky words in free text must not be judged UNSUITABLE on
        # the risk-product check (that guard is INVESTMENT_PROPOSAL-only).
        r = suitability_check(_state(
            request_type=RequestType.MEETING_PREP,
            investment_idea="discuss leveraged options strategies client asked about"))
        assert _status(r) != "UNSUITABLE"

    def test_rationale_and_checks_present(self):
        r = suitability_check(_state(investment_idea="Add a diversified index fund"))
        assert r["suitability_analysis"]["checks_performed"]
        assert "Reg BI Care Obligation" in r["reg_bi_rationale"]
        assert len(r["audit_trail"]) >= 1


# ── routing after suitability ─────────────────────────────────────────────────
class TestRoutingAfterSuitability:
    def test_unsuitable_routes_to_block(self):
        assert _route_after_suitability({"suitability_status": SuitabilityStatus.UNSUITABLE}) == "block_unsuitable"

    @pytest.mark.parametrize("status", [
        SuitabilityStatus.SUITABLE, SuitabilityStatus.SUITABLE_WITH_NOTE, SuitabilityStatus.NEEDS_REVIEW,
    ])
    def test_non_unsuitable_continues_to_recommendation(self, status):
        assert _route_after_suitability({"suitability_status": status}) == "recommendation_engine"


# ── HITL enforcement (agent-local, mirrors the suite-wide governance guard) ───
class TestHitlGate:
    def test_rm_approval_gate_is_framework_enforced(self):
        graph = build_wealth_rm_graph(use_memory=True)
        assert "rm_approval_gate" in list(graph.interrupt_before_nodes)

    def test_no_interrupt_without_checkpointer(self):
        graph = build_wealth_rm_graph(use_memory=False)
        assert "rm_approval_gate" not in list(getattr(graph, "interrupt_before_nodes", []))


# ── block_unsuitable surfaces the block and never drafts client content ───────
class TestBlockUnsuitable:
    def test_block_emits_unsuitable_block_not_client_content(self):
        analysis = {"checks_performed": [
            {"check": "RISK_TOLERANCE_ALIGNMENT", "passed": False, "note": "High-risk for CONSERVATIVE client"},
        ]}
        out = block_unsuitable(_state(suitability_analysis=analysis))
        assert out["output_type"] == "UNSUITABLE_BLOCK"
        assert "BLOCKED" in out["draft_content"]
        assert "RISK_TOLERANCE_ALIGNMENT" in out["draft_content"]
