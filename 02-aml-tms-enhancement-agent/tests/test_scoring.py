"""
Unit tests for scoring modules: feature extractor, classifier, threshold manager.
"""
import pytest
from scoring.false_positive_classifier import (
    check_regulatory_override,
    compute_rule_based_score,
    compute_composite_score,
)
from scoring.threshold_manager import ThresholdManager
from scoring.feature_extractor import extract_features


def _make_features(**overrides) -> dict:
    base = {
        "alert_type": "STRUCTURING",
        "triggered_rule": "CASH_STRUCTURING_10K",
        "tms_severity": "HIGH",
        "amount_usd": 19500.0,
        "transaction_count": 3,
        "time_window_days": 5,
        "risk_tier": "HIGH",
        "account_age_days": 2190,
        "business_type": "restaurant",
        "amount_vs_expected_ratio": 0.43,
        "pep_flag": False,
        "edd_active": False,
        "prior_sars_filed": 0,
        "prior_ctrs_filed": 18,
        "rule_fp_rate": 0.87,
        "typology_fp_rate": 0.84,
        "peer_group_fp_rate": 0.89,
        "customer_historical_fp_rate": 1.0,
        "customer_prior_alert_count": 4,
        "days_since_last_similar_alert": 63,
        "has_open_investigation": False,
        "high_risk_geography": False,
        "is_weekend": False,
        "is_month_end": True,
    }
    base.update(overrides)
    return base


class TestRegulatoryOverride:
    def test_pep_always_overrides(self):
        features = _make_features(pep_flag=True)
        override, reason = check_regulatory_override(features)
        assert override is True
        assert "PEP" in reason

    def test_open_investigation_overrides(self):
        features = _make_features(has_open_investigation=True)
        override, reason = check_regulatory_override(features)
        assert override is True
        assert "investigation" in reason.lower()

    def test_ofac_adjacent_overrides(self):
        features = _make_features(
            high_risk_geography=True,
            amount_usd=75_000,
            account_age_days=90,
            prior_sars_filed=0,
        )
        override, reason = check_regulatory_override(features)
        assert override is True

    def test_normal_restaurant_no_override(self):
        features = _make_features()
        override, reason = check_regulatory_override(features)
        assert override is False
        assert reason == ""


class TestRuleBasedScoring:
    def test_high_rule_fp_rate_scores_high(self):
        features = _make_features(rule_fp_rate=0.92)
        score, factors = compute_rule_based_score(features)
        assert score >= 60
        assert any("FP rate" in f for f in factors)

    def test_shell_company_rapid_movement_scores_low(self):
        features = _make_features(
            business_type="shell_company",
            alert_type="RAPID_MOVEMENT",
            rule_fp_rate=0.22,
            high_risk_geography=True,
            amount_vs_expected_ratio=9.5,
        )
        score, factors = compute_rule_based_score(features)
        assert score < 40

    def test_restaurant_structuring_scores_high(self):
        features = _make_features()
        score, factors = compute_rule_based_score(features)
        assert score >= 55

    def test_score_clamped_to_100(self):
        # Stack all positive signals
        features = _make_features(
            rule_fp_rate=0.99,
            customer_historical_fp_rate=1.0,
            customer_prior_alert_count=10,
            amount_vs_expected_ratio=0.1,
            prior_ctrs_filed=20,
            is_month_end=True,
            peer_group_fp_rate=0.95,
        )
        score, _ = compute_rule_based_score(features)
        assert score <= 100.0

    def test_score_clamped_to_zero(self):
        features = _make_features(
            rule_fp_rate=0.05,
            business_type="shell_company",
            alert_type="RAPID_MOVEMENT",
            high_risk_geography=True,
            amount_vs_expected_ratio=10.0,
        )
        score, _ = compute_rule_based_score(features)
        assert score >= 0.0


class TestCompositeScoring:
    def test_composite_weights_sum(self):
        from scoring.false_positive_classifier import WEIGHT_RULE_BASED, WEIGHT_LLM, WEIGHT_HISTORICAL
        assert abs(WEIGHT_RULE_BASED + WEIGHT_LLM + WEIGHT_HISTORICAL - 1.0) < 0.0001

    def test_composite_in_range(self):
        features = _make_features()
        composite, breakdown = compute_composite_score(70.0, 85.0, features)
        assert 0 <= composite <= 100

    def test_high_llm_score_drives_composite_up(self):
        features = _make_features()
        composite_high, _ = compute_composite_score(50.0, 95.0, features)
        composite_low, _ = compute_composite_score(50.0, 20.0, features)
        assert composite_high > composite_low

    def test_breakdown_contains_all_components(self):
        features = _make_features()
        _, breakdown = compute_composite_score(60.0, 75.0, features)
        assert "rule_based_score" in breakdown
        assert "llm_score" in breakdown
        assert "historical_score" in breakdown
        assert "composite_fp_score" in breakdown


class TestThresholdManager:
    def setup_method(self):
        self.mgr = ThresholdManager()

    def test_default_suppress_threshold(self):
        decision, thresholds = self.mgr.route(90, "STRUCTURING", "HIGH")
        assert decision == "SUPPRESS"

    def test_default_downgrade_threshold(self):
        decision, thresholds = self.mgr.route(70, "STRUCTURING", "MEDIUM")
        assert decision == "DOWNGRADE"

    def test_default_pass_through(self):
        decision, thresholds = self.mgr.route(45, "STRUCTURING", "MEDIUM")
        assert decision == "PASS_THROUGH"

    def test_default_escalate_threshold(self):
        decision, thresholds = self.mgr.route(10, "STRUCTURING", "HIGH")
        assert decision == "ESCALATE"

    def test_regulatory_override_forces_escalate(self):
        decision, _ = self.mgr.route(
            95, "STRUCTURING", "HIGH",
            regulatory_override=True,
            regulatory_override_reason="PEP"
        )
        assert decision == "ESCALATE"

    def test_very_high_risk_harder_to_suppress(self):
        t_high = self.mgr.get_thresholds("STRUCTURING", "HIGH")
        t_very_high = self.mgr.get_thresholds("STRUCTURING", "VERY_HIGH")
        assert t_very_high.suppress > t_high.suppress

    def test_pep_related_never_suppressed(self):
        # PEP_RELATED override threshold is 999
        decision, _ = self.mgr.route(99, "PEP_RELATED", "HIGH")
        # With threshold 999 and no override flag, score 99 should downgrade or pass-through
        assert decision in ("DOWNGRADE", "PASS_THROUGH", "ESCALATE")
        assert decision != "SUPPRESS"

    def test_explain_thresholds_returns_dict(self):
        explanation = self.mgr.explain_thresholds("VELOCITY", "MEDIUM")
        assert "effective_suppress_threshold" in explanation
        assert "effective_downgrade_threshold" in explanation
        assert explanation["alert_type"] == "VELOCITY"
