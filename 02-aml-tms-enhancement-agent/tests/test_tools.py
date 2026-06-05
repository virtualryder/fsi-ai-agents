"""
Unit tests for integration tools: TMS connector, customer context,
historical patterns, suppression engine.
"""
import pytest
from tools.tms_connector import get_pending_alerts, get_alert_details, update_alert_disposition
from tools.customer_context import get_customer_summary
from tools.historical_patterns import get_historical_patterns, get_rule_fp_rate
from tools.suppression_engine import (
    record_suppression, record_downgrade, record_pass_through,
    record_escalation, get_suppression_stats,
)


class TestTmsConnector:
    def test_get_pending_alerts_returns_list(self):
        alerts = get_pending_alerts()
        assert isinstance(alerts, list)
        assert len(alerts) > 0

    def test_alerts_have_required_fields(self):
        alerts = get_pending_alerts()
        required = {"alert_id", "customer_id", "alert_type", "triggered_rule",
                    "severity", "amount", "currency", "alert_date"}
        for alert in alerts:
            assert required.issubset(alert.keys()), f"Missing fields in {alert['alert_id']}"

    def test_get_alert_details_returns_correct_alert(self):
        alerts = get_pending_alerts()
        first_id = alerts[0]["alert_id"]
        detail = get_alert_details(first_id)
        assert detail is not None
        assert detail["alert_id"] == first_id

    def test_get_alert_details_returns_none_for_unknown(self):
        result = get_alert_details("TMS-NONEXISTENT-9999")
        assert result is None

    def test_update_alert_disposition_returns_true(self):
        result = update_alert_disposition(
            alert_id="TMS-TEST-UPDATE",
            disposition="SUPPRESSED",
            new_priority=None,
            reason="Test suppression",
            fp_probability=91.5,
        )
        assert result is True

    def test_limit_parameter_respected(self):
        alerts = get_pending_alerts(limit=2)
        assert len(alerts) <= 2


class TestCustomerContext:
    def test_known_customer_returns_summary(self):
        customer = get_customer_summary("CUST-101")
        assert customer is not None
        assert customer["customer_id"] == "CUST-101"
        assert customer["risk_tier"] in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")

    def test_unknown_customer_returns_none(self):
        result = get_customer_summary("CUST-NONEXISTENT")
        assert result is None

    def test_customer_has_required_fields(self):
        customer = get_customer_summary("CUST-101")
        required = {
            "customer_id", "full_name", "risk_tier", "business_type",
            "account_age_days", "expected_monthly_cash_volume",
            "pep_flag", "edd_active", "prior_sars_filed", "historical_fp_rate",
        }
        assert required.issubset(customer.keys())

    def test_pep_flag_is_boolean(self):
        customer = get_customer_summary("CUST-101")
        assert isinstance(customer["pep_flag"], bool)

    def test_restaurant_customer_profile(self):
        customer = get_customer_summary("CUST-101")
        assert customer["business_type"] == "restaurant"
        assert customer["historical_fp_rate"] == 1.0  # All past alerts were FPs

    def test_shell_company_profile(self):
        customer = get_customer_summary("CUST-104")
        assert customer["business_type"] == "shell_company"
        assert customer["risk_tier"] == "VERY_HIGH"


class TestHistoricalPatterns:
    def test_returns_historical_patterns_dict(self):
        patterns = get_historical_patterns(
            customer_id="CUST-101",
            alert_type="STRUCTURING",
            triggered_rule="CASH_STRUCTURING_10K",
            business_type="restaurant",
            risk_tier="HIGH",
        )
        assert "rule_fp_rate" in patterns
        assert "typology_fp_rate" in patterns
        assert "peer_group_fp_rate" in patterns
        assert "customer_fp_rate" in patterns

    def test_rates_in_valid_range(self):
        patterns = get_historical_patterns(
            customer_id="CUST-101",
            alert_type="STRUCTURING",
            triggered_rule="CASH_STRUCTURING_10K",
            business_type="restaurant",
            risk_tier="HIGH",
        )
        for key in ("rule_fp_rate", "typology_fp_rate", "peer_group_fp_rate", "customer_fp_rate"):
            assert 0.0 <= patterns[key] <= 1.0, f"{key} out of range"

    def test_known_rule_fp_rate(self):
        rate = get_rule_fp_rate("CASH_STRUCTURING_10K")
        assert rate == 0.87

    def test_unknown_rule_returns_neutral(self):
        rate = get_rule_fp_rate("UNKNOWN_RULE_999")
        assert rate == 0.50  # Neutral fallback

    def test_customer_with_history_computes_fp_rate(self):
        patterns = get_historical_patterns(
            customer_id="CUST-101",
            alert_type="STRUCTURING",
            triggered_rule="CASH_STRUCTURING_10K",
            business_type="restaurant",
            risk_tier="HIGH",
        )
        # CUST-101 has 4 alerts, all FALSE_POSITIVE
        assert patterns["customer_fp_rate"] == 1.0
        assert len(patterns["customer_alert_history"]) == 4

    def test_new_customer_gets_neutral_fp_rate(self):
        patterns = get_historical_patterns(
            customer_id="CUST-NEW-9999",
            alert_type="STRUCTURING",
            triggered_rule="CASH_STRUCTURING_10K",
            business_type="retail",
            risk_tier="MEDIUM",
        )
        assert patterns["customer_fp_rate"] == 0.50  # Neutral
        assert patterns["customer_alert_history"] == []


class TestSuppressionEngine:
    def test_record_suppression_returns_record(self):
        record = record_suppression(
            alert_id="TMS-UNIT-001",
            customer_id="CUST-101",
            alert_type="STRUCTURING",
            fp_probability=91.0,
            confidence=0.87,
            primary_reason="High rule FP rate + known business pattern",
            suppression_factors=["Rule FP rate 87%", "4 prior FPs"],
            pass_through_factors=[],
            justification_narrative="Test justification narrative.",
            score_breakdown={"composite_fp_score": 91.0},
            thresholds_used={"effective_suppress_threshold": 85.0},
        )
        assert "suppression_id" in record
        assert record["suppression_id"].startswith("SUP-")
        assert record["mandatory_review_date"] is not None
        assert record["review_status"] == "PENDING"

    def test_record_downgrade_action_is_downgrade(self):
        record = record_downgrade(
            alert_id="TMS-UNIT-002",
            customer_id="CUST-101",
            original_priority="HIGH",
            new_priority="LOW",
            fp_probability=72.0,
            reason="Likely FP but retains analyst review",
            justification="Test downgrade justification.",
        )
        assert record["action"] == "DOWNGRADE"
        assert record["original_priority"] == "HIGH"
        assert record["new_priority"] == "LOW"

    def test_record_pass_through(self):
        record = record_pass_through(
            alert_id="TMS-UNIT-003",
            customer_id="CUST-102",
            priority="HIGH",
            fp_probability=30.0,
            reason="Uncertain — routing to analyst",
        )
        assert record["action"] == "PASS_THROUGH"

    def test_record_escalation(self):
        record = record_escalation(
            alert_id="TMS-UNIT-004",
            customer_id="CUST-104",
            fp_probability=8.0,
            reason="Shell company + high-risk geography",
        )
        assert record["action"] == "ESCALATE"

    def test_suppression_stats_returns_dict(self):
        stats = get_suppression_stats()
        required = {
            "total_processed", "suppressed", "downgraded",
            "passed_through", "escalated", "suppression_rate",
            "analyst_hours_saved",
        }
        assert required.issubset(stats.keys())

    def test_suppression_rate_in_valid_range(self):
        stats = get_suppression_stats()
        assert 0.0 <= stats["suppression_rate"] <= 1.0
