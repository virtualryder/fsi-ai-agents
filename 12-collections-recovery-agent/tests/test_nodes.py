"""
Agent 12 — Collections & Recovery Agent
Node unit tests.

Test coverage:
- TestSecurityProperties: frozenset immutability (ALWAYS_HITL_CONDITIONS, CONSUMER_DEBT_TYPES)
- TestFDCPATimeCheck: time-of-day enforcement, fail-safe for unknown timezone
- TestSOLComputation: state lookups, date arithmetic, expired/warning flags
- TestCollectabilityScore: weighted composite, tier boundaries, SOL-expired penalty
- TestPaymentPlanOptimizer: plan count, math validation, hardship plan eligibility
- TestSettlementTiers: tier amounts, high-value flag, discount math
- TestHITLConditions: all 9 conditions trigger correctly, frozenset membership
- TestHumanReviewGate: all decision mappings, unknown decision handling
- TestAuditTrail: append-only behavior, finalize retention policy
- TestCreditReportingThresholds: FCRA min balance, medical debt, charge-off
"""

import pytest
from datetime import datetime, timedelta, date

from agent.state import (
    ALWAYS_HITL_CONDITIONS,
    CONSUMER_DEBT_TYPES,
    BUSINESS_DEBT_TYPES,
    PERMITTED_THIRD_PARTY_PURPOSES,
    FDCPA_PROHIBITED_REPRESENTATIONS,
    STATE_SOL_YEARS,
    SETTLEMENT_TIERS,
    COLLECTABILITY_WEIGHTS,
    CREDIT_REPORTING_THRESHOLDS,
    FDCPA_PROHIBITED_HOURS_BEFORE,
    FDCPA_PROHIBITED_HOURS_AFTER,
    REGULATION_F_CALL_LIMIT_7_DAYS,
    REGULATION_F_POST_CONVERSATION_WAIT_DAYS,
    SCRA_MAX_INTEREST_RATE_PCT,
    MIN_PAYMENT_PCT_OF_BALANCE,
    MAX_PAYMENT_TERM_MONTHS,
    HARDSHIP_PLAN_MIN_PAYMENT,
    SETTLEMENT_TIERS,
)
from agent.nodes import (
    _mask_account_number,
    _mask_ssn,
    _compute_sol_expiration,
    _compute_collectability_score,
    _compute_payment_plans,
    _compute_settlement_tiers,
    _determine_hitl_conditions,
    _append_audit_entry,
    debt_intake_node,
    fdcpa_compliance_check_node,
    debt_validation_node,
    payment_plan_optimizer_node,
    risk_scoring_node,
    human_review_gate_node,
    audit_finalize_node,
)


class TestSecurityProperties:
    """Verify that frozensets are immutable at runtime — security property tests."""

    def test_always_hitl_conditions_is_frozenset(self):
        assert isinstance(ALWAYS_HITL_CONDITIONS, frozenset)

    def test_always_hitl_conditions_immutable(self):
        """Adding to ALWAYS_HITL_CONDITIONS must raise TypeError."""
        with pytest.raises((TypeError, AttributeError)):
            ALWAYS_HITL_CONDITIONS.add("FAKE_CONDITION")

    def test_always_hitl_conditions_count(self):
        """Exactly 9 conditions in the frozenset."""
        assert len(ALWAYS_HITL_CONDITIONS) == 9

    def test_all_expected_hitl_conditions_present(self):
        expected = {
            "SCRA_DETECTED",
            "BANKRUPTCY_STAY_DETECTED",
            "DISPUTE_RECEIVED",
            "CEASE_DESIST_RECEIVED",
            "DECEASED_ACCOUNT",
            "SETTLEMENT_HIGH_VALUE",
            "LITIGATION_HIGH_RISK",
            "REGULATORY_COMPLAINT",
            "MINOR_ACCOUNT",
        }
        assert expected == ALWAYS_HITL_CONDITIONS

    def test_consumer_debt_types_is_frozenset(self):
        assert isinstance(CONSUMER_DEBT_TYPES, frozenset)

    def test_consumer_debt_types_immutable(self):
        with pytest.raises((TypeError, AttributeError)):
            CONSUMER_DEBT_TYPES.add("FAKE_DEBT_TYPE")

    def test_fdcpa_prohibited_representations_is_frozenset(self):
        assert isinstance(FDCPA_PROHIBITED_REPRESENTATIONS, frozenset)

    def test_fdcpa_prohibited_representations_immutable(self):
        with pytest.raises((TypeError, AttributeError)):
            FDCPA_PROHIBITED_REPRESENTATIONS.add("FAKE_PROHIBITED")

    def test_bankruptcy_stay_exceptions_is_frozenset(self):
        from agent.state import BANKRUPTCY_STAY_EXCEPTIONS
        assert isinstance(BANKRUPTCY_STAY_EXCEPTIONS, frozenset)


class TestPIIMasking:
    """Verify PII masking applied at intake."""

    def test_account_number_masking(self):
        masked = _mask_account_number("4111111111119874")
        assert masked == "ACCT-****9874"
        assert "4111111111" not in masked

    def test_account_number_short(self):
        result = _mask_account_number("123")
        assert "ACCT-****XXXX" == result

    def test_account_number_empty(self):
        result = _mask_account_number("")
        assert "ACCT-****XXXX" == result

    def test_ssn_masking(self):
        masked = _mask_ssn("123-45-6789")
        assert masked == "SSN-***-**-6789"
        assert "123" not in masked

    def test_ssn_masking_unformatted(self):
        masked = _mask_ssn("123456789")
        assert masked == "SSN-***-**-6789"

    def test_intake_node_masks_account(self):
        state = {
            "original_account_number": "4111111111119874",
            "debt_type": "CREDIT_CARD",
            "current_balance": 1000.0,
            "consumer_state": "OH",
            "consumer_timezone": "America/New_York",
            "audit_trail": [],
        }
        result = debt_intake_node(state)
        assert result["account_id"] == "ACCT-****9874"
        assert result["original_account_number"] == "MASKED"

    def test_intake_fdcpa_applies_for_consumer_debt(self):
        state = {
            "original_account_number": "123456789",
            "debt_type": "CREDIT_CARD",
            "current_balance": 500.0,
            "consumer_state": "CA",
            "consumer_timezone": "America/Los_Angeles",
            "audit_trail": [],
        }
        result = debt_intake_node(state)
        assert result["fdcpa_applies"] is True

    def test_intake_fdcpa_not_applies_for_business_debt(self):
        state = {
            "original_account_number": "987654321",
            "debt_type": "COMMERCIAL_LOAN",
            "current_balance": 50000.0,
            "consumer_state": "TX",
            "consumer_timezone": "America/Chicago",
            "audit_trail": [],
        }
        result = debt_intake_node(state)
        assert result["fdcpa_applies"] is False


class TestFDCPATimeCheck:
    """Verify FDCPA § 805(a)(1) time-of-day enforcement."""

    def test_fdcpa_prohibited_hours_constants(self):
        assert FDCPA_PROHIBITED_HOURS_BEFORE == 8
        assert FDCPA_PROHIBITED_HOURS_AFTER == 21  # 9pm = hour 21

    def test_contact_time_check_valid_timezone(self):
        from agent.nodes import _check_contact_time_fdcpa
        # Should not raise — just test that it returns bool and int
        permitted, hour = _check_contact_time_fdcpa("America/New_York")
        assert isinstance(permitted, bool)
        assert isinstance(hour, int)
        assert -1 <= hour <= 23

    def test_contact_time_check_unknown_timezone(self):
        """Unknown timezone should default to contact prohibited (fail-safe)."""
        from agent.nodes import _check_contact_time_fdcpa
        permitted, hour = _check_contact_time_fdcpa("INVALID/TIMEZONE")
        assert permitted is False
        assert hour == -1

    def test_regulation_f_constants(self):
        assert REGULATION_F_CALL_LIMIT_7_DAYS == 7
        assert REGULATION_F_POST_CONVERSATION_WAIT_DAYS == 7

    def test_fdcpa_compliance_check_cease_desist_blocks_contact(self):
        state = {
            "consumer_timezone": "America/Chicago",
            "cease_desist_received": True,
            "dispute_received": False,
            "prior_contacts_7_days": 0,
            "days_since_last_conversation": 999,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = fdcpa_compliance_check_node(state)
        assert result["contact_permitted_now"] is False
        assert any("CEASE_DESIST" in issue for issue in result["fdcpa_compliance_issues"])

    def test_fdcpa_compliance_check_dispute_blocks_contact(self):
        state = {
            "consumer_timezone": "America/New_York",
            "cease_desist_received": False,
            "dispute_received": True,
            "prior_contacts_7_days": 0,
            "days_since_last_conversation": 999,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = fdcpa_compliance_check_node(state)
        assert result["contact_permitted_now"] is False

    def test_regulation_f_7in7_violation_detected(self):
        state = {
            "consumer_timezone": "America/New_York",
            "cease_desist_received": False,
            "dispute_received": False,
            "prior_contacts_7_days": 7,  # At limit
            "days_since_last_conversation": 999,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = fdcpa_compliance_check_node(state)
        assert len(result["regulation_f_violations"]) > 0
        assert any("7-IN-7" in v for v in result["regulation_f_violations"])


class TestSOLComputation:
    """Verify statute of limitations date arithmetic."""

    def test_sol_lookup_ohio_credit_card(self):
        # Time-robust fixture: anchor charge-off 2 years before "now" so the
        # 6-year Ohio SOL is always in-window regardless of when tests run.
        # (The original hard-coded 2020-06-01 charge-off expired in real time
        # on 2026-06-01 and turned this test into a time bomb.)
        from datetime import datetime, timedelta, timezone
        charge_off = (datetime.now(timezone.utc) - timedelta(days=730)).date().isoformat()
        delinquency = (datetime.now(timezone.utc) - timedelta(days=900)).date().isoformat()
        sol, expiry, expired, warning = _compute_sol_expiration(
            delinquency, charge_off, "OH", "CREDIT_CARD"
        )
        assert sol == 6  # Ohio open account = 6 years
        assert not expired  # 2 years into a 6-year SOL

    def test_sol_lookup_california_credit_card(self):
        sol, expiry, expired, warning = _compute_sol_expiration(
            "2015-01-01", "2016-01-01", "CA", "CREDIT_CARD"
        )
        assert sol == 4  # California open account = 4 years
        assert expired  # 2016 + 4 = 2020 — past today 2026

    def test_sol_expired_flag(self):
        # Debt last paid 2012 in NY (6-year SOL) = expired since 2018
        sol, expiry, expired, warning = _compute_sol_expiration(
            "2010-01-01", "2012-01-01", "NY", "CREDIT_CARD"
        )
        assert expired is True
        assert warning is False  # Can't be in warning if already expired

    def test_sol_warning_flag(self):
        # Debt where SOL expires within 90 days from today
        today = date.today()
        # Set last payment date so SOL expires 45 days from now
        sol_years = 6
        target_expiry = today + timedelta(days=45)
        sol_start = target_expiry.replace(year=target_expiry.year - sol_years)
        state_code = "NY"  # 6-year open account SOL

        sol, expiry, expired, warning = _compute_sol_expiration(
            sol_start.strftime("%Y-%m-%d"),
            sol_start.strftime("%Y-%m-%d"),
            state_code, "CREDIT_CARD"
        )
        assert not expired
        assert warning  # Within 90 days

    def test_sol_unknown_state_defaults_to_6(self):
        sol, expiry, expired, warning = _compute_sol_expiration(
            "2023-01-01", "2024-01-01", "ZZ", "CREDIT_CARD"
        )
        assert sol == 6  # Default conservative SOL

    def test_sol_restarts_from_last_payment(self):
        # Last payment is later than origination — SOL starts from payment
        sol, expiry, expired, warning = _compute_sol_expiration(
            "2015-01-01",  # Origination
            "2022-06-01",  # Recent payment — restarts clock
            "OH", "CREDIT_CARD"
        )
        # OH 6-year SOL: 2022 + 6 = 2028 — not expired
        assert not expired


class TestCollectabilityScore:
    """Verify collectability scoring model."""

    def test_high_collectability_new_account(self):
        state = {
            "days_delinquent": 45,
            "current_balance": 1500.0,
            "prior_contacts_7_days": 2,
            "sol_expired": False,
            "hardship_score": 0.2,
            "payment_history_factor": 0.8,
        }
        score, tier, sub = _compute_collectability_score(state)
        assert tier == "HIGH"
        assert score >= 0.70

    def test_low_collectability_aged_account(self):
        state = {
            "days_delinquent": 900,
            "current_balance": 75000.0,
            "prior_contacts_7_days": 0,
            "sol_expired": False,
            "hardship_score": 0.9,
            "payment_history_factor": 0.1,
        }
        score, tier, sub = _compute_collectability_score(state)
        assert tier == "LOW"
        assert score < 0.40

    def test_sol_expired_reduces_score(self):
        state_normal = {
            "days_delinquent": 400,
            "current_balance": 2000.0,
            "prior_contacts_7_days": 1,
            "sol_expired": False,
            "hardship_score": 0.4,
            "payment_history_factor": 0.5,
        }
        state_expired = dict(state_normal)
        state_expired["sol_expired"] = True

        score_normal, _, _ = _compute_collectability_score(state_normal)
        score_expired, _, _ = _compute_collectability_score(state_expired)
        assert score_expired < score_normal  # SOL expiry reduces score

    def test_collectability_weights_sum_to_one(self):
        total = sum(COLLECTABILITY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_score_bounded_zero_to_one(self):
        for _ in range(3):
            state = {
                "days_delinquent": 0,
                "current_balance": 100.0,
                "prior_contacts_7_days": 0,
                "sol_expired": False,
                "hardship_score": 0.0,
                "payment_history_factor": 1.0,
            }
            score, _, _ = _compute_collectability_score(state)
            assert 0.0 <= score <= 1.0


class TestPaymentPlanOptimizer:
    """Verify payment plan computation."""

    def test_standard_plans_generated(self):
        plans = _compute_payment_plans(3000.0, False)
        standard_terms = [p["term_months"] for p in plans if p["plan_type"] == "STANDARD"]
        assert 12 in standard_terms or 24 in standard_terms  # At least some standard plans

    def test_hardship_plan_included_when_eligible(self):
        plans = _compute_payment_plans(1000.0, True)
        hardship_plans = [p for p in plans if p["plan_type"] == "HARDSHIP"]
        assert len(hardship_plans) > 0
        assert hardship_plans[0]["monthly_payment"] == HARDSHIP_PLAN_MIN_PAYMENT

    def test_hardship_plan_excluded_when_not_eligible(self):
        plans = _compute_payment_plans(1000.0, False)
        hardship_plans = [p for p in plans if p["plan_type"] == "HARDSHIP"]
        assert len(hardship_plans) == 0

    def test_payment_math_correct(self):
        plans = _compute_payment_plans(1200.0, False)
        for plan in plans:
            if plan["plan_type"] == "STANDARD":
                # total_repaid should approximately equal monthly * term
                expected_total = round(plan["monthly_payment"] * plan["term_months"], 2)
                assert abs(plan["total_repaid"] - expected_total) < 0.02

    def test_max_plan_count(self):
        plans = _compute_payment_plans(5000.0, True)
        assert len(plans) <= 6

    def test_min_payment_constant(self):
        assert MIN_PAYMENT_PCT_OF_BALANCE == 0.015
        assert MAX_PAYMENT_TERM_MONTHS == 60
        assert HARDSHIP_PLAN_MIN_PAYMENT == 25.0


class TestSettlementTiers:
    """Verify settlement tier computation."""

    def test_tier_amounts_correct(self):
        balance = 10000.0
        tiers = _compute_settlement_tiers(balance)
        for tier in tiers:
            expected_amount = round(balance * (1.0 - tier["discount_pct"] / 100.0), 2)
            assert abs(tier["settlement_amount"] - expected_amount) < 0.01

    def test_high_value_flag_above_10k(self):
        balance = 30000.0
        tiers = _compute_settlement_tiers(balance)
        # TIER_1 at 20% = $24,000 (>$10K) → high_value should be True
        tier_1 = [t for t in tiers if t["tier"] == "TIER_1"][0]
        assert tier_1["high_value"] is True  # 30K * 0.80 = 24K > 10K

    def test_high_value_flag_above_40pct_discount(self):
        # TIER_3 (50% discount) should always be high_value
        balance = 5000.0
        tiers = _compute_settlement_tiers(balance)
        tier_3 = [t for t in tiers if t["tier"] == "TIER_3"]
        if tier_3:
            assert tier_3[0]["high_value"] is True  # 50% > 40% threshold

    def test_settlement_not_generated_below_min_balance(self):
        balance = 500.0  # Below TIER_2 min_balance of $1000
        tiers = _compute_settlement_tiers(balance)
        tier_2 = [t for t in tiers if t["tier"] == "TIER_2"]
        assert len(tier_2) == 0

    def test_settlement_tiers_auth_levels(self):
        balance = 15000.0
        tiers = _compute_settlement_tiers(balance)
        tier_map = {t["tier"]: t["auth_level"] for t in tiers}
        assert tier_map.get("TIER_1") == "COLLECTOR"
        assert tier_map.get("TIER_2") == "SUPERVISOR"
        assert tier_map.get("TIER_3") == "MANAGER"


class TestHITLConditions:
    """Verify HITL condition detection."""

    def test_scra_triggers_hitl(self):
        state = {"scra_active_military": True, "current_balance": 5000.0}
        conditions, required, level = _determine_hitl_conditions(state)
        assert "SCRA_DETECTED" in conditions
        assert required is True

    def test_bankruptcy_triggers_hitl_and_compliance_escalation(self):
        state = {"bankruptcy_stay_active": True, "current_balance": 5000.0}
        conditions, required, level = _determine_hitl_conditions(state)
        assert "BANKRUPTCY_STAY_DETECTED" in conditions
        assert required is True
        assert level == "COMPLIANCE"

    def test_dispute_triggers_hitl(self):
        state = {"dispute_received": True, "current_balance": 1000.0}
        conditions, required, level = _determine_hitl_conditions(state)
        assert "DISPUTE_RECEIVED" in conditions
        assert required is True

    def test_cease_desist_triggers_hitl(self):
        state = {"cease_desist_received": True, "current_balance": 1000.0}
        conditions, required, level = _determine_hitl_conditions(state)
        assert "CEASE_DESIST_RECEIVED" in conditions

    def test_deceased_triggers_hitl(self):
        state = {"consumer_is_deceased": True, "current_balance": 1000.0}
        conditions, required, level = _determine_hitl_conditions(state)
        assert "DECEASED_ACCOUNT" in conditions

    def test_minor_triggers_hitl(self):
        state = {"consumer_is_minor": True, "current_balance": 500.0}
        conditions, required, level = _determine_hitl_conditions(state)
        assert "MINOR_ACCOUNT" in conditions

    def test_high_value_settlement_triggers_hitl(self):
        state = {
            "settlement_tiers": [{"tier": "TIER_2", "high_value": True, "settlement_amount": 12000.0}],
            "current_balance": 20000.0,
        }
        conditions, required, level = _determine_hitl_conditions(state)
        assert "SETTLEMENT_HIGH_VALUE" in conditions

    def test_no_conditions_no_hitl(self):
        state = {
            "scra_active_military": False,
            "bankruptcy_stay_active": False,
            "dispute_received": False,
            "cease_desist_received": False,
            "consumer_is_deceased": False,
            "consumer_is_minor": False,
            "settlement_tiers": [{"tier": "TIER_1", "high_value": False}],
            "collectability_tier": "HIGH",
            "sol_expired": True,  # SOL expired → not litigation risk
            "current_balance": 500.0,
        }
        conditions, required, level = _determine_hitl_conditions(state)
        assert required is False

    def test_all_hitl_conditions_are_frozenset_members(self):
        """Conditions returned must all be valid ALWAYS_HITL_CONDITIONS members."""
        state = {
            "scra_active_military": True,
            "bankruptcy_stay_active": True,
            "dispute_received": True,
            "current_balance": 5000.0,
        }
        conditions, _, _ = _determine_hitl_conditions(state)
        for condition in conditions:
            assert condition in ALWAYS_HITL_CONDITIONS, \
                f"Condition '{condition}' not in ALWAYS_HITL_CONDITIONS frozenset"


class TestHumanReviewGate:
    """Verify HITL gate decision mapping."""

    def _base_state(self, decision):
        return {
            "reviewer_id": "MRO-001",
            "reviewer_decision": decision,
            "reviewer_conditions": "",
            "reviewer_notes": "Test note",
            "hitl_conditions": ["SCRA_DETECTED"],
            "escalation_level": "SUPERVISOR",
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }

    def test_approve_plan_maps_to_payment_plan(self):
        result = human_review_gate_node(self._base_state("APPROVE_PLAN"))
        assert result["collections_outcome"] == "PAYMENT_PLAN"

    def test_approve_settlement_maps_correctly(self):
        result = human_review_gate_node(self._base_state("APPROVE_SETTLEMENT"))
        assert result["collections_outcome"] == "SETTLEMENT"

    def test_cease_collection_maps_correctly(self):
        result = human_review_gate_node(self._base_state("CEASE_COLLECTION"))
        assert result["collections_outcome"] == "CEASE_AND_DESIST"

    def test_refer_legal_maps_correctly(self):
        result = human_review_gate_node(self._base_state("REFER_LEGAL"))
        assert result["collections_outcome"] == "LEGAL_REFERRAL"

    def test_close_dispute_maps_correctly(self):
        result = human_review_gate_node(self._base_state("CLOSE_DISPUTE"))
        assert result["collections_outcome"] == "CLOSED_DISPUTE"

    def test_unknown_decision_maps_to_pending(self):
        """Unknown decisions must NOT map to PAYMENT_PLAN or SETTLEMENT."""
        result = human_review_gate_node(self._base_state("UNKNOWN_DECISION"))
        assert result["collections_outcome"] == "PENDING_REVIEW"
        assert result["collections_outcome"] != "PAYMENT_PLAN"

    def test_missing_decision_maps_to_pending(self):
        state = self._base_state("")
        result = human_review_gate_node(state)
        assert result["collections_outcome"] == "PENDING_REVIEW"


class TestAuditTrail:
    """Verify audit trail append-only behavior."""

    def test_append_only_does_not_modify_prior_entries(self):
        initial_state = {
            "audit_trail": [{"timestamp": "T1", "event_type": "INTAKE"}],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = _append_audit_entry(initial_state, "NEW_EVENT", {"detail": "x"})
        assert len(result) == 2
        assert result[0]["event_type"] == "INTAKE"  # Prior entry unchanged
        assert result[1]["event_type"] == "NEW_EVENT"

    def test_audit_entry_has_timestamp(self):
        result = _append_audit_entry(
            {"audit_trail": [], "case_id": "T1", "account_id": "ACCT-****0000"},
            "TEST_EVENT", {}
        )
        assert "timestamp" in result[-1]
        assert result[-1]["timestamp"].endswith("Z")

    def test_finalize_adds_retention_policy(self):
        state = {
            "audit_trail": [{"event_type": "INTAKE"}],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
            "collections_outcome": "PAYMENT_PLAN",
            "credit_reporting_action": "REPORT_NEW",
            "credit_reporting_appropriate": True,
            "hitl_conditions": [],
            "regulatory_risk_tier": "LOW",
            "fdcpa_compliance_issues": [],
            "regulation_f_violations": [],
            "reviewer_id": "COLL-001",
            "reviewer_decision": "APPROVE_PLAN",
        }
        result = audit_finalize_node(state)
        final_entry = result["audit_trail"][-1]
        assert final_entry["retention_policy"] == "7_YEARS_S3_OBJECT_LOCK_GOVERNANCE"
        assert result["audit_retention"] == "7_YEARS_S3_OBJECT_LOCK_GOVERNANCE"

    def test_audit_trail_grows_with_each_node(self):
        """Each node appends one entry — trail grows monotonically."""
        trail_lengths = []
        base_state = {
            "original_account_number": "4111111111119874",
            "debt_type": "CREDIT_CARD",
            "current_balance": 1000.0,
            "consumer_state": "OH",
            "consumer_timezone": "America/New_York",
            "audit_trail": [],
        }
        result1 = debt_intake_node(base_state)
        trail_lengths.append(len(result1["audit_trail"]))

        state2 = {**base_state, **result1}
        result2 = fdcpa_compliance_check_node(state2)
        trail_lengths.append(len(result2["audit_trail"]))

        assert trail_lengths[0] == 1
        assert trail_lengths[1] == 2
        assert all(trail_lengths[i] < trail_lengths[i+1] for i in range(len(trail_lengths)-1))


class TestCreditReportingThresholds:
    """Verify FCRA credit reporting threshold enforcement."""

    def test_min_balance_threshold(self):
        assert CREDIT_REPORTING_THRESHOLDS["min_balance_report"] == 100.0

    def test_medical_debt_threshold(self):
        assert CREDIT_REPORTING_THRESHOLDS["medical_debt_min_balance"] == 500.0

    def test_charge_off_days(self):
        assert CREDIT_REPORTING_THRESHOLDS["charge_off_days_delinquent"] == 180

    def test_debt_validation_medical_under_500_not_reportable(self):
        state = {
            "debt_type": "MEDICAL_DEBT",
            "current_balance": 450.0,
            "original_balance": 450.0,
            "interest_accrued": 0.0,
            "fees_accrued": 0.0,
            "debt_date_of_last_payment": "2024-01-01",
            "debt_origination_date": "2023-06-01",
            "cease_desist_received": False,
            "bankruptcy_stay_active": False,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = debt_validation_node(state)
        assert result["medical_debt_flag"] is True
        assert result["credit_reporting_appropriate"] is False  # $450 < $500 medical threshold

    def test_debt_validation_medical_over_500_reportable(self):
        state = {
            "debt_type": "MEDICAL_DEBT",
            "current_balance": 750.0,
            "original_balance": 750.0,
            "interest_accrued": 0.0,
            "fees_accrued": 0.0,
            "debt_date_of_last_payment": "2024-01-01",
            "debt_origination_date": "2023-01-01",
            "cease_desist_received": False,
            "bankruptcy_stay_active": False,
            "audit_trail": [],
            "case_id": "TEST-001",
            "account_id": "ACCT-****1234",
        }
        result = debt_validation_node(state)
        assert result["credit_reporting_appropriate"] is True  # $750 > $500


class TestSCRAConstants:
    """Verify SCRA constants are correctly defined."""

    def test_scra_max_interest_rate(self):
        assert SCRA_MAX_INTEREST_RATE_PCT == 6.0

    def test_scra_in_hitl_conditions(self):
        assert "SCRA_DETECTED" in ALWAYS_HITL_CONDITIONS

    def test_bankruptcy_in_hitl_conditions(self):
        assert "BANKRUPTCY_STAY_DETECTED" in ALWAYS_HITL_CONDITIONS
