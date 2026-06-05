# tests/test_tools.py
# ============================================================
# Tool unit tests with regulatory assertions
#
# Run: pytest tests/test_tools.py -v
# ============================================================

import pytest
from tools.rule_engine import (
    evaluate_velocity_rules,
    evaluate_geography_rules,
    evaluate_amount_rules,
    evaluate_mcc_rules,
    evaluate_hard_block_rules,
    compute_rule_score,
    HIGH_RISK_COUNTRIES,
    RESTRICTED_MCCS,
    VELOCITY_THRESHOLDS,
)


class TestVelocityRules:
    """Velocity rule threshold tests."""

    def _velocity(self, **kwargs):
        base = {
            "txn_count_1min": 0,
            "txn_count_5min": 0,
            "txn_count_1hr": 0,
            "txn_count_24hr": 0,
            "amount_sum_1hr": 0,
            "amount_sum_24hr": 0,
            "unique_countries_1hr": 1,
            "velocity_flag": False,
        }
        base.update(kwargs)
        return base

    def test_card_testing_detected_at_threshold(self):
        """txn_count_1min >= 3 triggers CARD_TESTING_VELOCITY rule."""
        signals = self._velocity(txn_count_1min=3)
        hits = evaluate_velocity_rules(signals, 1.00)
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-001" in rule_ids

    def test_card_testing_not_triggered_below_threshold(self):
        """txn_count_1min < 3 does not trigger card testing rule."""
        signals = self._velocity(txn_count_1min=2)
        hits = evaluate_velocity_rules(signals, 1.00)
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-001" not in rule_ids

    def test_hourly_amount_limit(self):
        """amount_sum_1hr >= 5000 triggers HOURLY_AMOUNT_LIMIT rule."""
        signals = self._velocity(amount_sum_1hr=5001)
        hits = evaluate_velocity_rules(signals, 100.0)
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-004" in rule_ids

    def test_multi_country_velocity(self):
        """unique_countries_1hr >= 2 triggers MULTI_COUNTRY_VELOCITY rule."""
        signals = self._velocity(unique_countries_1hr=2)
        hits = evaluate_velocity_rules(signals, 50.0)
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-005" in rule_ids

    def test_clean_transaction_no_velocity_hits(self):
        """Normal transaction with all signals below thresholds: no velocity hits."""
        signals = self._velocity(
            txn_count_1min=0,
            txn_count_1hr=2,
            amount_sum_1hr=150.0,
            unique_countries_1hr=1,
        )
        hits = evaluate_velocity_rules(signals, 75.0)
        assert len(hits) == 0


class TestGeographyRules:
    """Geography rule tests including high-risk jurisdiction list."""

    def test_high_risk_country_triggers_rule(self):
        """Transaction in high-risk jurisdiction triggers RULE-011."""
        hits = evaluate_geography_rules("NG", ["US"], "ONLINE_BANKING")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-011" in rule_ids

    def test_ofac_sanctioned_country_triggers_rule(self):
        """OFAC-sanctioned country (North Korea) triggers high-risk rule."""
        hits = evaluate_geography_rules("KP", ["US"], "ONLINE_BANKING")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-011" in rule_ids

    def test_domestic_us_transaction_no_geography_hit(self):
        """US domestic transaction with US typical geography: no geography hits."""
        hits = evaluate_geography_rules("US", ["US"], "POS_CHIP")
        assert len(hits) == 0

    def test_new_country_triggers_rule(self):
        """First transaction in a non-US country customer hasn't visited: RULE-012."""
        hits = evaluate_geography_rules("GB", ["US"], "ONLINE_BANKING")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-012" in rule_ids

    def test_typical_geography_no_new_country_hit(self):
        """Transaction in customer's typical geography: no new country rule."""
        hits = evaluate_geography_rules("GB", ["US", "GB"], "ONLINE_BANKING")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-012" not in rule_ids


class TestAmountRules:
    """Amount anomaly rule tests."""

    def test_extreme_outlier_detected(self):
        """Amount 10x average triggers EXTREME_AMOUNT_OUTLIER rule."""
        hits = evaluate_amount_rules(1000.0, 10.5, "PURCHASE")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-021" in rule_ids

    def test_elevated_outlier_detected(self):
        """Amount 5x-9x average triggers ELEVATED_AMOUNT_OUTLIER rule."""
        hits = evaluate_amount_rules(500.0, 5.5, "PURCHASE")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-022" in rule_ids

    def test_structuring_amount_detected(self):
        """
        Amount $9,000-$9,999 triggers STRUCTURING_INDICATOR rule.

        Critical: BSA requires SAR consideration for structuring activity
        to avoid $10,000 Currency Transaction Report (CTR) threshold.
        """
        hits = evaluate_amount_rules(9450.0, 1.2, "WIRE")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-023" in rule_ids

    def test_amount_exactly_10000_no_structuring_hit(self):
        """Amount exactly $10,000 is over the threshold — not structuring."""
        hits = evaluate_amount_rules(10000.0, 1.0, "WIRE")
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-023" not in rule_ids

    def test_typical_amount_no_hits(self):
        """Amount 1.5x average: no amount rules triggered."""
        hits = evaluate_amount_rules(150.0, 1.5, "PURCHASE")
        assert len(hits) == 0


class TestMCCRules:
    """MCC restriction rule tests."""

    def test_gambling_mcc_triggers_rule(self):
        """MCC 7995 (gambling) triggers RESTRICTED_MCC rule."""
        hits = evaluate_mcc_rules("7995")
        assert len(hits) == 1
        assert hits[0]["rule_id"] == "RULE-041"

    def test_crypto_quasi_cash_mcc_triggers_rule(self):
        """MCC 6051 (crypto/quasi-cash) triggers RESTRICTED_MCC rule."""
        hits = evaluate_mcc_rules("6051")
        assert len(hits) == 1

    def test_normal_grocery_mcc_no_hit(self):
        """MCC 5411 (grocery) does not trigger RESTRICTED_MCC rule."""
        hits = evaluate_mcc_rules("5411")
        assert len(hits) == 0

    def test_none_mcc_no_hit(self):
        """None MCC does not trigger any rule."""
        hits = evaluate_mcc_rules(None)
        assert len(hits) == 0


class TestHardBlockRules:
    """Hard block trigger tests — critical regulatory controls."""

    def test_fraud_ip_triggers_hard_block(self):
        """
        IP with previous_fraud_flag triggers hard block.
        This ensures confirmed fraud IPs are always blocked
        regardless of ML score.
        """
        ip_signals = {"previous_fraud_flag": True, "is_tor": False}
        hard_block, hits = evaluate_hard_block_rules(ip_signals, None, [])
        assert hard_block is True
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-091" in rule_ids

    def test_tor_node_triggers_hard_block(self):
        """Tor exit node triggers hard block — RULE-092."""
        ip_signals = {"previous_fraud_flag": False, "is_tor": True}
        hard_block, hits = evaluate_hard_block_rules(ip_signals, None, [])
        assert hard_block is True
        rule_ids = [h["rule_id"] for h in hits]
        assert "RULE-092" in rule_ids

    def test_clean_ip_no_hard_block(self):
        """Clean IP signals do not trigger hard block."""
        ip_signals = {"previous_fraud_flag": False, "is_tor": False, "is_vpn": True}
        hard_block, hits = evaluate_hard_block_rules(ip_signals, None, [])
        assert hard_block is False

    def test_hard_block_hits_preserve_original_hits(self):
        """Existing rule hits are preserved when hard block is added."""
        existing = [{"rule_id": "RULE-001", "rule_name": "CARD_TESTING_VELOCITY", "score_contribution": 35}]
        ip_signals = {"previous_fraud_flag": True, "is_tor": False}
        hard_block, all_hits = evaluate_hard_block_rules(ip_signals, None, existing)
        assert hard_block is True
        rule_ids = [h["rule_id"] for h in all_hits]
        assert "RULE-001" in rule_ids
        assert "RULE-091" in rule_ids


class TestRuleScoreComputation:
    """Rule score aggregation tests."""

    def test_score_caps_at_100(self):
        """Multiple high-severity rules cannot push score above 100."""
        hits = [
            {"rule_id": f"RULE-{i:03}", "rule_name": f"RULE_{i}", "score_contribution": 50}
            for i in range(10)
        ]
        score = compute_rule_score(hits)
        assert score <= 100.0

    def test_empty_hits_zero_score(self):
        """No rule hits returns 0.0 score."""
        assert compute_rule_score([]) == 0.0

    def test_single_high_hit_returns_full_contribution(self):
        """Single rule hit returns its full contribution."""
        hits = [{"rule_id": "RULE-001", "rule_name": "CARD_TESTING", "score_contribution": 35}]
        score = compute_rule_score(hits)
        assert score == 35.0

    def test_second_rule_adds_diminished_contribution(self):
        """Second rule adds less than its full contribution (diminishing returns)."""
        hits = [
            {"rule_id": "RULE-001", "score_contribution": 30},
            {"rule_id": "RULE-002", "score_contribution": 30},
        ]
        score = compute_rule_score(hits)
        # Score should be > 30 but < 60 due to diminishing returns
        assert 30 < score < 60
