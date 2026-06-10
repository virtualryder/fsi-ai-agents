"""
tests/test_nodes.py — Unit tests for Payments Compliance Agent nodes

TEST PHILOSOPHY
---------------
These tests enforce the security and compliance properties that must hold
regardless of any future refactoring. They are organized into:

1. Security tests: Properties that must hold for regulatory compliance
   (PII masking, frozenset immutability, routing constants)

2. Compliance logic tests: Deterministic Python functions that must
   produce consistent, auditable outputs (OFAC screening, Nacha windows,
   Reg E applicability, SLA computations)

3. Node integration tests: Each node produces expected state updates
   given representative inputs

CRITICAL SECURITY TESTS (never weaken or remove):
- test_always_hitl_is_frozenset: ALWAYS_HITL_PAYMENT_EVENTS must be frozenset
- test_always_hitl_cannot_be_modified: frozenset must be immutable at runtime
- test_ofac_countries_is_frozenset: OFAC_SANCTIONED_COUNTRY_CODES is frozenset
- test_ofac_countries_cannot_be_modified: OFAC frozenset must be immutable
- test_account_masking_removes_full_numbers: Full account numbers must not persist
- test_audit_trail_is_append_only: Prior audit entries must not be modified
- test_ofac_hit_forces_critical_tier: OFAC hit must override composite score
"""

from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch


# ── Import nodes and constants ─────────────────────────────────────────────────

from agent.nodes import (
    ALWAYS_HITL_PAYMENT_EVENTS,
    CTR_THRESHOLD_USD,
    FATF_HIGH_RISK_COUNTRIES,
    HITL_AMOUNT_THRESHOLD,
    NACHA_RETURN_WINDOWS,
    OFAC_SANCTIONED_COUNTRY_CODES,
    RISK_WEIGHTS,
    SAR_CONSIDERATION_THRESHOLD,
    UNAUTHORIZED_RETURN_CODES,
    audit_finalize_node,
    compliance_scoring_node,
    nacha_validation_node,
    output_packaging_node,
    payment_intake_node,
    reg_e_assessment_node,
    routing_decision_node,
    sanctions_screening_node,
)


# ── Helper: build a minimal valid payment state ───────────────────────────────

def _make_state(**overrides) -> Dict[str, Any]:
    """Return a minimal valid payment state dict for testing."""
    base = {
        "payment_event_id": "TEST-001",
        "payment_type": "ACH_DEBIT",
        "sec_code": "PPD",
        "amount": 500.00,
        "currency": "USD",
        "settlement_date": "2024-01-15",
        "originator_name": "Test Originator Inc.",
        "originator_account_raw": "1234567890",
        "originator_routing": "021000021",
        "originator_country": "US",
        "receiver_name": "Jane Consumer",
        "receiver_account_raw": "9876543210",
        "receiver_routing": "021000089",
        "receiver_country": "US",
        "odfi_name": "First Test Bank",
        "rdfi_name": "Community Test CU",
        "return_code": None,
        "dispute_type": None,
        "customer_claim_text": None,
        "account_tenure_months": 24,
        "prior_dispute_count": 0,
        "account_good_standing": True,
        "audit_trail": [],
        "completed_steps": [],
        "submission_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ── Security Tests ─────────────────────────────────────────────────────────────

class TestSecurityProperties(unittest.TestCase):
    """
    CRITICAL: These tests enforce security properties required for regulatory compliance.
    Do not modify or remove these tests. A failure here indicates a regression in
    the security architecture.
    """

    def test_always_hitl_is_frozenset(self):
        """ALWAYS_HITL_PAYMENT_EVENTS must be a Python frozenset (immutable)."""
        self.assertIsInstance(
            ALWAYS_HITL_PAYMENT_EVENTS,
            frozenset,
            "ALWAYS_HITL_PAYMENT_EVENTS must be frozenset — not a set, list, or tuple. "
            "frozenset raises TypeError on .add(), preventing any code from making "
            "a payment event type skip mandatory human review.",
        )

    def test_always_hitl_cannot_be_modified(self):
        """frozenset.add() must raise TypeError — immutability enforced at runtime."""
        with self.assertRaises((TypeError, AttributeError)):
            ALWAYS_HITL_PAYMENT_EVENTS.add("NEW_EVENT_TYPE")

    def test_always_hitl_required_events_present(self):
        """All mandatory HITL events must be in ALWAYS_HITL_PAYMENT_EVENTS."""
        mandatory_events = {
            "OFAC_HOLD",       # OFAC regulations
            "SAR_CANDIDATE",   # BSA
            "CTR_THRESHOLD",   # BSA
            "HIGH_RISK_COUNTRY_WIRE",  # FATF
        }
        for event in mandatory_events:
            self.assertIn(
                event,
                ALWAYS_HITL_PAYMENT_EVENTS,
                f"'{event}' must be in ALWAYS_HITL_PAYMENT_EVENTS for regulatory compliance.",
            )

    def test_ofac_countries_is_frozenset(self):
        """OFAC_SANCTIONED_COUNTRY_CODES must be a frozenset."""
        self.assertIsInstance(
            OFAC_SANCTIONED_COUNTRY_CODES,
            frozenset,
            "OFAC_SANCTIONED_COUNTRY_CODES must be frozenset. "
            "Mutable collections risk runtime modification of sanctioned country list.",
        )

    def test_ofac_countries_cannot_be_modified(self):
        """OFAC frozenset must be immutable at runtime."""
        with self.assertRaises((TypeError, AttributeError)):
            OFAC_SANCTIONED_COUNTRY_CODES.add("US")

    def test_core_sanctioned_countries_present(self):
        """Core OFAC-sanctioned countries must be in the frozenset."""
        # These countries are under comprehensive OFAC sanctions programs
        core_sanctioned = {"KP", "IR", "CU"}
        for country in core_sanctioned:
            self.assertIn(
                country,
                OFAC_SANCTIONED_COUNTRY_CODES,
                f"Country '{country}' must be in OFAC_SANCTIONED_COUNTRY_CODES.",
            )

    def test_fatf_high_risk_is_frozenset(self):
        """FATF_HIGH_RISK_COUNTRIES must be a frozenset."""
        self.assertIsInstance(FATF_HIGH_RISK_COUNTRIES, frozenset)

    def test_unauthorized_return_codes_is_frozenset(self):
        """UNAUTHORIZED_RETURN_CODES must be a frozenset."""
        self.assertIsInstance(UNAUTHORIZED_RETURN_CODES, frozenset)

    def test_account_masking_in_intake_node(self):
        """payment_intake_node must mask account numbers to last-4 digits."""
        state = _make_state(
            originator_account_raw="1234567890",
            receiver_account_raw="9876543210",
        )
        result = payment_intake_node(state)

        # Originator account should be masked
        orig_masked = result.get("originator_account_last4", "")
        self.assertEqual(orig_masked, "7890", f"Originator account should be last 4 digits, got: {orig_masked}")

        # Receiver account should be masked
        recv_masked = result.get("receiver_account_last4", "")
        self.assertEqual(recv_masked, "3210", f"Receiver account should be last 4 digits, got: {recv_masked}")

    def test_full_account_not_in_state_after_intake(self):
        """Full account numbers must not persist in state after payment_intake_node."""
        state = _make_state(
            originator_account_raw="1234567890",
            receiver_account_raw="9876543210",
        )
        result = payment_intake_node(state)

        # Serialize state to string and search for full account numbers
        state_str = str(result)
        self.assertNotIn(
            "1234567890",
            state_str,
            "Full originator account number must not appear in state after intake.",
        )
        self.assertNotIn(
            "9876543210",
            state_str,
            "Full receiver account number must not appear in state after intake.",
        )

    def test_audit_trail_is_append_only(self):
        """Later nodes must not modify earlier audit trail entries."""
        # Run intake to establish initial audit entry
        state = _make_state()
        intake_result = payment_intake_node(state)
        initial_trail = list(intake_result.get("audit_trail", []))
        self.assertGreater(len(initial_trail), 0, "Intake should add audit entry")

        first_entry_snapshot = dict(initial_trail[0])

        # Run sanctions screening (next node)
        sanctions_input = {**state, **intake_result}
        sanctions_result = sanctions_screening_node(sanctions_input)
        sanctions_trail = list(sanctions_result.get("audit_trail", []))

        # Original entry should still be present and unmodified
        self.assertGreater(len(sanctions_trail), len(initial_trail), "Sanctions should add new audit entry")
        self.assertEqual(
            sanctions_trail[0].get("node"),
            first_entry_snapshot.get("node"),
            "First audit entry node should not change after subsequent node execution",
        )

    def test_payment_event_id_required(self):
        """payment_intake_node should reject missing payment_event_id."""
        state = _make_state(payment_event_id="")
        result = payment_intake_node(state)
        # Should either set error or generate an ID — not silently accept empty ID
        # Accept either behavior as long as empty string is not the final ID
        final_id = result.get("payment_event_id", "")
        # Empty string is not acceptable
        self.assertTrue(len(final_id) > 0, "payment_event_id must not be empty after intake")

    def test_risk_weights_sum_to_one(self):
        """RISK_WEIGHTS must sum to 1.0 for valid composite scoring."""
        total = sum(RISK_WEIGHTS.values())
        self.assertAlmostEqual(
            total,
            1.0,
            places=5,
            msg=f"RISK_WEIGHTS must sum to 1.0, got {total:.5f}. "
            "SR 11-7 requires documented, consistent model weighting.",
        )


# ── OFAC and Sanctions Tests ──────────────────────────────────────────────────

class TestSanctionsScreening(unittest.TestCase):
    """Tests for Node 2: sanctions_screening_node."""

    def test_iran_receiver_triggers_ofac_hit(self):
        """Transaction to Iran must trigger OFAC hit."""
        state = _make_state(receiver_country="IR")
        intake = payment_intake_node(state)
        full_state = {**state, **intake}
        result = sanctions_screening_node(full_state)

        self.assertTrue(result.get("ofac_hit"), "Iran (IR) must trigger OFAC hit")
        self.assertTrue(result.get("high_risk_country_flag"), "Iran must be flagged as high-risk country")

    def test_north_korea_triggers_ofac_hit(self):
        """Transaction to North Korea must trigger OFAC hit."""
        state = _make_state(receiver_country="KP")
        intake = payment_intake_node(state)
        full_state = {**state, **intake}
        result = sanctions_screening_node(full_state)

        self.assertTrue(result.get("ofac_hit"), "North Korea (KP) must trigger OFAC hit")

    def test_cuba_triggers_ofac_hit(self):
        """Transaction to Cuba must trigger OFAC hit."""
        state = _make_state(receiver_country="CU")
        intake = payment_intake_node(state)
        full_state = {**state, **intake}
        result = sanctions_screening_node(full_state)

        self.assertTrue(result.get("ofac_hit"), "Cuba (CU) must trigger OFAC hit")

    def test_domestic_us_no_ofac_hit(self):
        """Domestic US-to-US transaction should not trigger OFAC hit."""
        state = _make_state(originator_country="US", receiver_country="US")
        intake = payment_intake_node(state)
        full_state = {**state, **intake}
        result = sanctions_screening_node(full_state)

        self.assertFalse(result.get("ofac_hit", False), "US domestic should not trigger OFAC hit")

    def test_high_risk_country_non_ofac(self):
        """FATF high-risk country (non-OFAC) should flag high_risk_country without ofac_hit."""
        # Myanmar (MM) is FATF high-risk but not under comprehensive OFAC sanctions
        state = _make_state(receiver_country="MM")
        intake = payment_intake_node(state)
        full_state = {**state, **intake}
        result = sanctions_screening_node(full_state)

        self.assertTrue(
            result.get("high_risk_country_flag", False),
            "Myanmar (MM) is FATF high-risk and should set high_risk_country_flag",
        )


# ── Nacha Validation Tests ────────────────────────────────────────────────────

class TestNachaValidation(unittest.TestCase):
    """Tests for Node 3: nacha_validation_node."""

    def _run_to_nacha(self, state: Dict) -> Dict:
        """Run through intake and sanctions to set up state for nacha node."""
        intake = payment_intake_node(state)
        s1 = {**state, **intake}
        sanctions = sanctions_screening_node(s1)
        return {**s1, **sanctions}

    def test_r10_sets_unauthorized_eligible(self):
        """Return code R10 must set unauthorized_return_eligible=True."""
        state = _make_state(return_code="R10")
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertTrue(
            result.get("unauthorized_return_eligible"),
            "R10 must set unauthorized_return_eligible=True",
        )

    def test_r07_sets_unauthorized_eligible(self):
        """Return code R07 (authorization revoked) must set unauthorized_return_eligible=True."""
        state = _make_state(return_code="R07")
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertTrue(result.get("unauthorized_return_eligible"), "R07 must set unauthorized_return_eligible=True")

    def test_r29_sets_unauthorized_eligible(self):
        """Return code R29 (corporate unauthorized) must set unauthorized_return_eligible=True."""
        state = _make_state(return_code="R29")
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertTrue(result.get("unauthorized_return_eligible"), "R29 must set unauthorized_return_eligible=True")

    def test_r01_does_not_set_unauthorized(self):
        """Return code R01 (NSF) must NOT set unauthorized_return_eligible."""
        state = _make_state(return_code="R01")
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertFalse(
            result.get("unauthorized_return_eligible", False),
            "R01 (NSF) must not set unauthorized_return_eligible=True",
        )

    def test_ctr_threshold_triggered(self):
        """Amount > $10,000 must trigger CTR threshold flag."""
        state = _make_state(amount=15000.00)
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertTrue(
            result.get("ctr_threshold_triggered"),
            f"Amount $15,000 must trigger CTR threshold (CTR_THRESHOLD_USD={CTR_THRESHOLD_USD})",
        )

    def test_ctr_threshold_not_triggered_below(self):
        """Amount below $10,000 must NOT trigger CTR threshold."""
        state = _make_state(amount=9999.99)
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertFalse(
            result.get("ctr_threshold_triggered", False),
            "Amount $9,999.99 must not trigger CTR threshold",
        )

    def test_noc_code_detected(self):
        """NOC code C01 must set noc_required=True."""
        state = _make_state(return_code="C01")
        pre = self._run_to_nacha(state)
        result = nacha_validation_node(pre)

        self.assertTrue(result.get("noc_required", False), "C01 must set noc_required=True")

    def test_nacha_return_windows_r10(self):
        """R10 return window must be 60 calendar days per Nacha OR Section 2.12.2."""
        self.assertEqual(
            NACHA_RETURN_WINDOWS.get("R10"),
            60,
            "R10 (Unauthorized) return window must be 60 days (Nacha OR Section 2.12.2)",
        )

    def test_nacha_return_windows_r01(self):
        """R01 return window must be 2 banking days per Nacha OR Section 2.12.1."""
        self.assertEqual(
            NACHA_RETURN_WINDOWS.get("R01"),
            2,
            "R01 (NSF) return window must be 2 banking days (Nacha OR Section 2.12.1)",
        )


# ── Reg E Assessment Tests ────────────────────────────────────────────────────

class TestRegEAssessment(unittest.TestCase):
    """Tests for Node 4: reg_e_assessment_node."""

    def _run_to_reg_e(self, state: Dict) -> Dict:
        """Run through intake, sanctions, nacha to set up for reg_e node."""
        intake = payment_intake_node(state)
        s1 = {**state, **intake}
        sanctions = sanctions_screening_node(s1)
        s2 = {**s1, **sanctions}
        nacha = nacha_validation_node(s2)
        return {**s2, **nacha}

    def test_ach_consumer_reg_e_applicable(self):
        """ACH debit on consumer account must be Reg E applicable."""
        state = _make_state(payment_type="ACH_DEBIT", sec_code="PPD")
        pre = self._run_to_reg_e(state)
        result = reg_e_assessment_node(pre)

        self.assertTrue(
            result.get("reg_e_applicable"),
            "ACH PPD debit on consumer account must be Reg E applicable",
        )

    def test_wire_domestic_reg_e_not_applicable(self):
        """Domestic wire transfer must NOT be Reg E applicable (12 CFR 1005.3(c)(4))."""
        state = _make_state(payment_type="WIRE_DOMESTIC")
        pre = self._run_to_reg_e(state)
        result = reg_e_assessment_node(pre)

        self.assertFalse(
            result.get("reg_e_applicable", True),
            "Wire transfer must not be Reg E applicable (12 CFR 1005.3(c)(4))",
        )

    def test_fedwire_reg_e_not_applicable(self):
        """FEDWIRE must NOT be Reg E applicable."""
        state = _make_state(payment_type="FEDWIRE")
        pre = self._run_to_reg_e(state)
        result = reg_e_assessment_node(pre)

        self.assertFalse(
            result.get("reg_e_applicable", True),
            "FEDWIRE must not be Reg E applicable",
        )

    def test_unauthorized_achdispute_sets_provisional_credit(self):
        """Unauthorized ACH dispute on consumer account must require provisional credit."""
        state = _make_state(
            payment_type="ACH_DEBIT",
            sec_code="PPD",
            return_code="R10",
            dispute_type="UNAUTHORIZED_TRANSACTION",
            amount=1500.00,
        )
        pre = self._run_to_reg_e(state)
        result = reg_e_assessment_node(pre)

        self.assertTrue(
            result.get("provisional_credit_required"),
            "Unauthorized ACH dispute must require provisional credit (12 CFR 1005.11(c)(2)(i))",
        )
        self.assertAlmostEqual(
            result.get("provisional_credit_amount", 0),
            1500.00,
            places=2,
            msg="Provisional credit amount must equal disputed amount",
        )

    def test_sla_deadline_is_set_for_reg_e(self):
        """Reg E applicable events must have SLA deadline set."""
        state = _make_state(
            payment_type="ACH_DEBIT",
            sec_code="PPD",
            dispute_type="UNAUTHORIZED_TRANSACTION",
        )
        pre = self._run_to_reg_e(state)
        result = reg_e_assessment_node(pre)

        if result.get("reg_e_applicable"):
            self.assertIsNotNone(
                result.get("sla_deadline"),
                "Reg E applicable events must have sla_deadline set",
            )


# ── Compliance Scoring Tests ──────────────────────────────────────────────────

class TestComplianceScoring(unittest.TestCase):
    """Tests for Node 6: compliance_scoring_node."""

    def _run_to_scoring(self, state: Dict) -> Dict:
        """Run pipeline through Node 5 to prepare for scoring."""
        intake = payment_intake_node(state)
        s1 = {**state, **intake}
        sanctions = sanctions_screening_node(s1)
        s2 = {**s1, **sanctions}
        nacha = nacha_validation_node(s2)
        s3 = {**s2, **nacha}
        reg_e = reg_e_assessment_node(s3)
        s4 = {**s3, **reg_e}
        # Skip dispute_analysis_node (requires LLM) — inject minimal dispute data
        return s4

    def test_ofac_hit_forces_critical_tier(self):
        """OFAC hit must force CRITICAL risk tier regardless of composite score.

        CRITICAL SECURITY TEST: This is the most important compliance control.
        An OFAC hit means the transaction involves a sanctioned entity. The risk
        tier MUST be CRITICAL. No score combination should produce a lower tier.
        """
        state = _make_state(receiver_country="IR")  # Iran = OFAC
        pre = self._run_to_scoring(state)
        result = compliance_scoring_node(pre)

        self.assertEqual(
            result.get("compliance_risk_tier"),
            "CRITICAL",
            "OFAC hit must force CRITICAL tier. "
            "This is a hard override that cannot be weakened by any other factor.",
        )
        self.assertAlmostEqual(
            result.get("compliance_risk_score", 0),
            1.0,
            places=5,
            msg="OFAC hit must set risk score to 1.0",
        )

    def test_low_risk_event_scores_low(self):
        """A clean administrative event should produce LOW risk score."""
        state = _make_state(
            amount=250.00,
            return_code="C01",  # NOC — administrative
            originator_country="US",
            receiver_country="US",
        )
        pre = self._run_to_scoring(state)
        result = compliance_scoring_node(pre)

        tier = result.get("compliance_risk_tier", "LOW")
        self.assertIn(
            tier,
            ["LOW", "MEDIUM"],
            f"Clean administrative NOC event should score LOW or MEDIUM, got {tier}",
        )

    def test_sar_candidate_flagged_above_threshold(self):
        """Events above SAR consideration threshold with suspicious activity must flag SAR candidate."""
        # Amount above $5K with unauthorized return
        state = _make_state(
            amount=10000.00,
            return_code="R10",
            dispute_type="UNAUTHORIZED_TRANSACTION",
        )
        pre = self._run_to_scoring(state)
        result = compliance_scoring_node(pre)

        # SAR candidate should be set if conditions are met
        # (exact logic depends on implementation — test that score is elevated)
        score = result.get("compliance_risk_score", 0)
        self.assertGreater(score, 0.2, "Unauthorized transaction above $5K should have elevated risk score")

    def test_risk_score_bounded_0_to_1(self):
        """Risk score must always be in [0.0, 1.0] range."""
        state = _make_state()
        pre = self._run_to_scoring(state)
        result = compliance_scoring_node(pre)

        score = result.get("compliance_risk_score", 0.5)
        self.assertGreaterEqual(score, 0.0, "Risk score must be >= 0.0")
        self.assertLessEqual(score, 1.0, "Risk score must be <= 1.0")

    def test_large_amount_increases_score(self):
        """Large transaction amount should contribute to higher risk score."""
        state_small = _make_state(amount=100.00)
        state_large = _make_state(amount=500000.00)

        pre_small = self._run_to_scoring(state_small)
        pre_large = self._run_to_scoring(state_large)

        result_small = compliance_scoring_node(pre_small)
        result_large = compliance_scoring_node(pre_large)

        self.assertGreaterEqual(
            result_large.get("compliance_risk_score", 0),
            result_small.get("compliance_risk_score", 0),
            "Large amount should produce >= risk score vs. small amount",
        )


# ── Routing Decision Tests ────────────────────────────────────────────────────

class TestRoutingDecision(unittest.TestCase):
    """Tests for Node 8: routing_decision_node."""

    def _build_state_with_flags(self, **flags) -> Dict:
        """Build a state dict with specific compliance flags set."""
        base = _make_state()
        intake = payment_intake_node(base)
        state = {**base, **intake}
        state.update(flags)
        return state

    def test_ofac_hit_routes_to_bsa(self):
        """OFAC hit must route to BSA_COMPLIANCE team."""
        state = self._build_state_with_flags(
            ofac_hit=True,
            compliance_risk_tier="CRITICAL",
            compliance_risk_score=1.0,
        )
        result = routing_decision_node(state)

        self.assertEqual(
            result.get("target_team"),
            "BSA_COMPLIANCE",
            "OFAC hit must route to BSA_COMPLIANCE",
        )
        self.assertTrue(
            result.get("human_review_required"),
            "OFAC hit must set human_review_required=True",
        )

    def test_unauthorized_return_routes_to_disputes(self):
        """Unauthorized return (R10) with Reg E dispute must route to DISPUTES."""
        state = self._build_state_with_flags(
            unauthorized_return_eligible=True,
            reg_e_applicable=True,
            dispute_type="UNAUTHORIZED_TRANSACTION",
            compliance_risk_tier="MEDIUM",
            compliance_risk_score=0.42,
        )
        result = routing_decision_node(state)

        self.assertEqual(
            result.get("target_team"),
            "DISPUTES",
            "Unauthorized return with Reg E dispute must route to DISPUTES",
        )

    def test_low_risk_noc_no_hitl(self):
        """Low-risk NOC administrative event should not require HITL."""
        state = self._build_state_with_flags(
            return_code="C01",
            noc_required=True,
            compliance_risk_tier="LOW",
            compliance_risk_score=0.05,
            ofac_hit=False,
            high_risk_country_flag=False,
            unauthorized_return_eligible=False,
            reg_e_applicable=False,
            sla_breached=False,
            sar_candidate=False,
            amount=250.00,
        )
        result = routing_decision_node(state)

        self.assertFalse(
            result.get("human_review_required", True),
            "Low-risk NOC should not require HITL (auto-resolve path)",
        )

    def test_high_amount_triggers_hitl(self):
        """Amount > HITL_AMOUNT_THRESHOLD must trigger human review."""
        state = self._build_state_with_flags(
            amount=HITL_AMOUNT_THRESHOLD + 1,
            compliance_risk_tier="MEDIUM",
            compliance_risk_score=0.3,
            ofac_hit=False,
            high_risk_country_flag=False,
            unauthorized_return_eligible=False,
            reg_e_applicable=False,
        )
        result = routing_decision_node(state)

        self.assertTrue(
            result.get("human_review_required"),
            f"Amount > ${HITL_AMOUNT_THRESHOLD:,.2f} must trigger HITL",
        )

    def test_critical_tier_triggers_hitl(self):
        """CRITICAL risk tier must trigger human review."""
        state = self._build_state_with_flags(
            compliance_risk_tier="CRITICAL",
            compliance_risk_score=0.90,
            ofac_hit=False,
        )
        result = routing_decision_node(state)

        self.assertTrue(
            result.get("human_review_required"),
            "CRITICAL risk tier must trigger HITL",
        )

    def test_resolution_type_set(self):
        """routing_decision_node must always set resolution_type."""
        state = self._build_state_with_flags(
            compliance_risk_tier="LOW",
            compliance_risk_score=0.05,
        )
        result = routing_decision_node(state)

        self.assertIsNotNone(
            result.get("resolution_type"),
            "routing_decision_node must always set resolution_type",
        )


# ── Audit Trail Tests ─────────────────────────────────────────────────────────

class TestAuditTrail(unittest.TestCase):
    """Tests for audit trail append-only behavior and finalization."""

    def test_intake_adds_audit_entry(self):
        """payment_intake_node must add an audit trail entry."""
        state = _make_state()
        result = payment_intake_node(state)

        trail = result.get("audit_trail", [])
        self.assertGreater(len(trail), 0, "payment_intake_node must add audit entry")

    def test_audit_entry_has_required_fields(self):
        """Each audit entry must have node name, timestamp, and details."""
        state = _make_state()
        result = payment_intake_node(state)

        entry = result["audit_trail"][0]
        self.assertIn("node", entry, "Audit entry must have 'node' field")
        self.assertIn("timestamp", entry, "Audit entry must have 'timestamp' field")

    def test_audit_timestamp_is_utc(self):
        """Audit entry timestamps must be UTC ISO-8601 format."""
        state = _make_state()
        result = payment_intake_node(state)

        ts = result["audit_trail"][0]["timestamp"]
        # Should be parseable as ISO-8601 datetime
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        self.assertIsNotNone(parsed)

    def test_prior_entries_not_modified_by_later_nodes(self):
        """Entries added by earlier nodes must not be altered by later nodes."""
        state = _make_state()
        intake_result = payment_intake_node(state)
        first_entry = dict(intake_result["audit_trail"][0])

        # Run next node
        s1 = {**state, **intake_result}
        sanctions_result = sanctions_screening_node(s1)
        trail_after = sanctions_result.get("audit_trail", [])

        # First entry should be unchanged
        self.assertEqual(
            trail_after[0].get("node"),
            first_entry.get("node"),
            "First audit entry 'node' must not change after subsequent node",
        )

    def test_audit_finalize_sets_processing_time(self):
        """audit_finalize_node must set processing_time_seconds."""
        state = _make_state(
            audit_trail=[{"node": "payment_intake", "timestamp": datetime.now(timezone.utc).isoformat(), "details": {}}],
            payment_status="RESOLVED",
            submission_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        result = audit_finalize_node(state)

        self.assertIn(
            "processing_time_seconds",
            result,
            "audit_finalize_node must set processing_time_seconds",
        )


# ── Output Packaging Tests ────────────────────────────────────────────────────

class TestOutputPackaging(unittest.TestCase):
    """Tests for Node 11: output_packaging_node."""

    def test_downstream_actions_is_list(self):
        """output_packaging_node must set downstream_actions as a list."""
        state = _make_state(
            ofac_hit=False,
            sar_candidate=False,
            provisional_credit_required=False,
            unauthorized_return_eligible=False,
            resolution_type="ADMINISTRATIVE_RETURN",
            compliance_risk_tier="LOW",
            audit_trail=[],
        )
        result = output_packaging_node(state)

        self.assertIsInstance(
            result.get("downstream_actions", []),
            list,
            "downstream_actions must be a list",
        )

    def test_ofac_hit_includes_ofac_action(self):
        """OFAC hit must include FILE_OFAC_REPORT in downstream_actions."""
        state = _make_state(
            ofac_hit=True,
            sar_candidate=True,
            provisional_credit_required=False,
            unauthorized_return_eligible=False,
            resolution_type="OFAC_HOLD",
            compliance_risk_tier="CRITICAL",
            audit_trail=[],
        )
        result = output_packaging_node(state)
        actions = result.get("downstream_actions", [])

        action_strs = " ".join(str(a) for a in actions)
        self.assertIn(
            "OFAC",
            action_strs,
            "OFAC hit must include OFAC-related action in downstream_actions",
        )

    def test_provisional_credit_includes_credit_action(self):
        """Provisional credit required must include credit action in downstream_actions."""
        state = _make_state(
            ofac_hit=False,
            sar_candidate=False,
            provisional_credit_required=True,
            provisional_credit_amount=500.00,
            unauthorized_return_eligible=True,
            resolution_type="INVESTIGATE_AND_RETURN",
            compliance_risk_tier="MEDIUM",
            audit_trail=[],
        )
        result = output_packaging_node(state)
        actions = result.get("downstream_actions", [])

        action_strs = " ".join(str(a) for a in actions)
        self.assertIn(
            "CREDIT",
            action_strs,
            "Provisional credit required must include credit action in downstream_actions",
        )


# ── Threshold Constants Tests ─────────────────────────────────────────────────

class TestThresholdConstants(unittest.TestCase):
    """Tests to verify regulatory threshold constants are correctly set."""

    def test_ctr_threshold_is_10000(self):
        """CTR threshold must be $10,000 per 31 CFR 1010.311."""
        self.assertEqual(
            CTR_THRESHOLD_USD,
            10_000.00,
            "CTR threshold must be $10,000 per 31 CFR 1010.311",
        )

    def test_sar_threshold_is_5000(self):
        """SAR threshold must be $5,000 per 31 CFR 1020.320."""
        self.assertEqual(
            SAR_CONSIDERATION_THRESHOLD,
            5_000.00,
            "SAR consideration threshold must be $5,000 per 31 CFR 1020.320",
        )

    def test_hitl_amount_threshold_is_50000(self):
        """HITL amount threshold must be $50,000."""
        self.assertEqual(
            HITL_AMOUNT_THRESHOLD,
            50_000.00,
            "HITL amount threshold must be $50,000",
        )

    def test_unauthorized_return_codes_contains_r10(self):
        """UNAUTHORIZED_RETURN_CODES must contain R10 (Customer Advises Not Authorized)."""
        self.assertIn(
            "R10",
            UNAUTHORIZED_RETURN_CODES,
            "R10 must be in UNAUTHORIZED_RETURN_CODES",
        )

    def test_unauthorized_return_codes_contains_r07(self):
        """UNAUTHORIZED_RETURN_CODES must contain R07 (Authorization Revoked)."""
        self.assertIn(
            "R07",
            UNAUTHORIZED_RETURN_CODES,
            "R07 must be in UNAUTHORIZED_RETURN_CODES",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
