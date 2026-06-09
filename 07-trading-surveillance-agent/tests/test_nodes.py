# tests/test_nodes.py
# ============================================================
# Unit tests for Trading Surveillance Agent node functions.
# Tests cover only deterministic Python logic — no LLM calls.
# ============================================================
import pytest
from datetime import datetime

from agent.nodes import (
    _compute_notional_score,
    _compute_recidivism_score,
    _compute_regulatory_exposure_score,
    _compute_evidence_quality_score,
    alert_intake_node,
    data_enrichment_node,
    pattern_detection_node,
    risk_scoring_node,
    routing_decision_node,
)
from agent.state import AlertType, AssetClass, CaseStatus, SeverityTier


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_state():
    """Minimal state for a layering alert on an equities trader."""
    return {
        "alert_type": AlertType.LAYERING_SPOOFING.value,
        "alert_source": "SURVEILLANCE_SYSTEM",
        "trader_id": "TRD-TEST-001",
        "trader_name": "Test Trader",
        "desk": "EQUITIES_PROP",
        "account_id": "ACCT-TEST-001",
        "instrument_id": "TEST",
        "instrument_name": "Test Corp",
        "asset_class": AssetClass.EQUITY.value,
        "trade_date": "2026-06-01",
        "notional_value": 1_500_000.0,
        "trade_direction": "BUY",
        "quantity": 30000,
        "price": 50.0,
        "venue": "NYSE",
        "raw_alert_data": {
            "cancel_rate": 0.85,
            "order_count": 12,
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


@pytest.fixture
def scored_state(base_state):
    """State after intake + enrichment + pattern detection + scoring."""
    state = alert_intake_node(base_state)
    state["prior_alert_count"] = 2
    state["restricted_list_hit"] = False
    state["watch_list_hit"] = False
    state["pep_flag"] = False
    state["account_risk_tier"] = "STANDARD"
    state["trader_history_summary"] = "2 prior alerts."
    state["corroborating_signals"] = ["HIGH_CANCEL_RATE", "LARGE_NOTIONAL"]
    state["pattern_confidence_scores"] = {AlertType.LAYERING_SPOOFING.value: 0.82}
    state["detected_patterns"] = [AlertType.LAYERING_SPOOFING.value]
    state["regulatory_flags"] = ["SEA Section 9(a)(2)", "Dodd-Frank Section 747"]
    return state


# ── TestAlertIntakeNode ───────────────────────────────────────────────────────

class TestAlertIntakeNode:
    def test_assigns_alert_id(self, base_state):
        result = alert_intake_node(base_state)
        assert result["alert_id"].startswith("SURV-")

    def test_preserves_provided_alert_id(self, base_state):
        base_state["alert_id"] = "SURV-CUSTOM-ID"
        result = alert_intake_node(base_state)
        assert result["alert_id"] == "SURV-CUSTOM-ID"

    def test_sets_case_status_open(self, base_state):
        result = alert_intake_node(base_state)
        assert result["case_status"] == CaseStatus.OPEN.value

    def test_initializes_audit_trail(self, base_state):
        result = alert_intake_node(base_state)
        assert len(result["audit_trail"]) >= 1
        assert result["audit_trail"][0]["node"] == "alert_intake"

    def test_marks_step_complete(self, base_state):
        result = alert_intake_node(base_state)
        assert "alert_intake" in result["completed_steps"]

    def test_assigns_alert_timestamp(self, base_state):
        result = alert_intake_node(base_state)
        assert "alert_timestamp" in result
        assert len(result["alert_timestamp"]) > 10


# ── TestPatternDetectionNode ──────────────────────────────────────────────────

class TestPatternDetectionNode:
    def test_detects_layering_from_alert_type(self, base_state):
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        result = pattern_detection_node(state)
        assert AlertType.LAYERING_SPOOFING.value in result["detected_patterns"]

    def test_detects_layering_from_raw_data(self, base_state):
        """High cancel rate + opposite side orders triggers layering without alert_type set."""
        base_state["alert_type"] = AlertType.UNUSUAL_ACTIVITY.value
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        result = pattern_detection_node(state)
        assert AlertType.LAYERING_SPOOFING.value in result["detected_patterns"]

    def test_detects_front_running(self, base_state):
        base_state["alert_type"] = AlertType.FRONT_RUNNING.value
        base_state["raw_alert_data"] = {
            "pre_customer_order_position": 10000,
            "customer_order_size": 1_000_000,
            "direction_matches_customer_order": True,
            "time_gap_seconds": 15,
        }
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        result = pattern_detection_node(state)
        assert AlertType.FRONT_RUNNING.value in result["detected_patterns"]

    def test_detects_wash_trading(self, base_state):
        base_state["alert_type"] = AlertType.WASH_TRADING.value
        base_state["raw_alert_data"] = {
            "related_accounts": ["ACCT-002", "ACCT-003"],
            "same_instrument_both_sides": True,
        }
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        result = pattern_detection_node(state)
        assert AlertType.WASH_TRADING.value in result["detected_patterns"]

    def test_detects_restricted_list_as_insider(self, base_state):
        state = alert_intake_node(base_state)
        state["restricted_list_hit"] = True
        state["pep_flag"] = False
        state["prior_alert_count"] = 0
        state["raw_alert_data"] = {"pre_trade_news": True, "material_nonpublic_information_flag": True}
        result = pattern_detection_node(state)
        assert any(
            p in result["detected_patterns"]
            for p in [AlertType.INSIDER_TRADING.value, AlertType.INFORMATION_BARRIER_BREACH.value]
        )

    def test_populates_regulatory_flags(self, base_state):
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        result = pattern_detection_node(state)
        assert len(result["regulatory_flags"]) > 0

    def test_pattern_confidence_scores_in_range(self, base_state):
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        result = pattern_detection_node(state)
        for score in result["pattern_confidence_scores"].values():
            assert 0.0 <= score <= 1.0


# ── TestNotionalScoring ───────────────────────────────────────────────────────

class TestNotionalScoring:
    def test_small_trade_low_score(self):
        assert _compute_notional_score(5_000) == 0.10

    def test_medium_trade_mid_score(self):
        score = _compute_notional_score(500_000)
        assert 0.40 <= score <= 0.60

    def test_large_trade_high_score(self):
        assert _compute_notional_score(20_000_000) == 0.95

    def test_boundary_100k(self):
        assert _compute_notional_score(99_999) == 0.25
        assert _compute_notional_score(100_001) == 0.50


# ── TestRecidivismScoring ─────────────────────────────────────────────────────

class TestRecidivismScoring:
    def test_no_prior_alerts_low_score(self):
        assert _compute_recidivism_score(0) == 0.10

    def test_one_prior_alert(self):
        assert _compute_recidivism_score(1) == 0.30

    def test_many_prior_alerts_high_score(self):
        assert _compute_recidivism_score(10) == 0.90

    def test_three_alerts_medium_score(self):
        score = _compute_recidivism_score(3)
        assert 0.50 <= score <= 0.60


# ── TestRiskScoringNode ───────────────────────────────────────────────────────

class TestRiskScoringNode:
    def test_score_in_valid_range(self, scored_state):
        result = risk_scoring_node(scored_state)
        assert 0.0 <= result["risk_score"] <= 1.0

    def test_layering_large_notional_scores_high(self, scored_state):
        """Layering + $1.5M + 2 prior alerts should score HIGH or above."""
        result = risk_scoring_node(scored_state)
        assert result["severity_tier"] in (SeverityTier.HIGH.value, SeverityTier.CRITICAL.value)

    def test_insider_trading_always_critical(self, scored_state):
        scored_state["alert_type"] = AlertType.INSIDER_TRADING.value
        scored_state["detected_patterns"] = [AlertType.INSIDER_TRADING.value]
        scored_state["pattern_confidence_scores"] = {AlertType.INSIDER_TRADING.value: 0.90}
        result = risk_scoring_node(scored_state)
        assert result["severity_tier"] == SeverityTier.CRITICAL.value

    def test_restricted_list_hit_escalates_to_high(self, scored_state):
        scored_state["notional_value"] = 25_000.0  # small notional → would be LOW/MEDIUM
        scored_state["prior_alert_count"] = 0
        scored_state["corroborating_signals"] = []
        scored_state["pattern_confidence_scores"] = {AlertType.LAYERING_SPOOFING.value: 0.30}
        scored_state["restricted_list_hit"] = True
        result = risk_scoring_node(scored_state)
        assert result["severity_tier"] in (SeverityTier.HIGH.value, SeverityTier.CRITICAL.value)

    def test_low_notional_no_history_scores_lower(self, base_state):
        state = alert_intake_node(base_state)
        state["alert_type"] = AlertType.UNUSUAL_ACTIVITY.value
        state["detected_patterns"] = [AlertType.UNUSUAL_ACTIVITY.value]
        state["pattern_confidence_scores"] = {AlertType.UNUSUAL_ACTIVITY.value: 0.30}
        state["prior_alert_count"] = 0
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        state["notional_value"] = 8_000.0
        state["corroborating_signals"] = []
        result = risk_scoring_node(state)
        assert result["severity_tier"] in (SeverityTier.LOW.value, SeverityTier.MEDIUM.value)

    def test_score_components_present(self, scored_state):
        result = risk_scoring_node(scored_state)
        components = result["risk_score_components"]
        assert "pattern_severity_score" in components
        assert "trade_size_score" in components
        assert "recidivism_score" in components
        assert "regulatory_exposure_score" in components
        assert "evidence_quality_score" in components

    def test_recidivist_with_6_plus_alerts_escalates(self, scored_state):
        scored_state["prior_alert_count"] = 7
        scored_state["alert_type"] = AlertType.LAYERING_SPOOFING.value
        scored_state["notional_value"] = 2_000_000.0
        result = risk_scoring_node(scored_state)
        assert result["severity_tier"] == SeverityTier.CRITICAL.value

    def test_composite_is_weighted_sum(self, scored_state):
        result = risk_scoring_node(scored_state)
        comps = result["risk_score_components"]
        expected = (
            comps["pattern_severity_score"] * 0.25
            + comps["trade_size_score"] * 0.25
            + comps["recidivism_score"] * 0.20
            + comps["regulatory_exposure_score"] * 0.15
            + comps["evidence_quality_score"] * 0.15
        )
        # Allow for override adjustments — check score is close to weighted sum or overridden
        assert abs(result["risk_score"] - expected) < 0.30


# ── TestRoutingDecisionNode ───────────────────────────────────────────────────

class TestRoutingDecisionNode:
    def _build_routable(self, base_state, tier):
        state = alert_intake_node(base_state)
        state["prior_alert_count"] = 1
        state["restricted_list_hit"] = False
        state["pep_flag"] = False
        state["corroborating_signals"] = []
        state["pattern_confidence_scores"] = {AlertType.LAYERING_SPOOFING.value: 0.75}
        state["detected_patterns"] = [AlertType.LAYERING_SPOOFING.value]
        state["severity_tier"] = tier
        state["risk_score"] = 0.75 if tier == SeverityTier.HIGH.value else 0.50
        state["sar_consideration"] = False
        return state

    def test_critical_requires_hitl(self, base_state):
        state = self._build_routable(base_state, SeverityTier.CRITICAL.value)
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_high_requires_hitl(self, base_state):
        state = self._build_routable(base_state, SeverityTier.HIGH.value)
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_medium_no_hitl(self, base_state):
        state = self._build_routable(base_state, SeverityTier.MEDIUM.value)
        result = routing_decision_node(state)
        assert result["human_review_required"] is False

    def test_equity_routes_to_equities_officer(self, base_state):
        state = self._build_routable(base_state, SeverityTier.HIGH.value)
        state["asset_class"] = AssetClass.EQUITY.value
        result = routing_decision_node(state)
        assert "EQUITIES" in result["primary_reviewer"]

    def test_insider_trading_always_hitl(self, base_state):
        state = self._build_routable(base_state, SeverityTier.MEDIUM.value)
        state["alert_type"] = AlertType.INSIDER_TRADING.value
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_critical_adds_legal_counsel(self, base_state):
        state = self._build_routable(base_state, SeverityTier.CRITICAL.value)
        result = routing_decision_node(state)
        assert "LEGAL_COUNSEL" in result["secondary_reviewers"]
