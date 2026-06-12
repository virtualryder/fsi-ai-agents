import core


def test_psi_formula_and_thresholds():
    assert core.compute_psi({"a": 50, "b": 50}, {"a": 50, "b": 50}) == 0.0
    assert core.classify_psi(0.05) == "STABLE"
    assert core.classify_psi(0.15) == "WARNING"
    assert core.classify_psi(0.30) == "CRITICAL"


def test_always_hitl_frozenset_has_9():
    assert len(core.ALWAYS_HITL_CONDITIONS) == 9
    assert "PSI_CRITICAL" in core.ALWAYS_HITL_CONDITIONS


class TestAssess:
    def test_psi_critical_triggers_review(self):
        a = core.assess({"model_id": "M1", "risk_tier": "MEDIUM", "validation_type": "ANNUAL",
                         "current_dist": {"a": 85, "b": 15}, "baseline_dist": {"a": 50, "b": 50}})
        assert "PSI_CRITICAL" in a["hitl_conditions"] and a["human_review_required"] is True

    def test_high_tier_initial_always_hitl(self):
        a = core.assess({"model_id": "M2", "risk_tier": "HIGH", "validation_type": "INITIAL",
                         "current_dist": {"a": 50}, "baseline_dist": {"a": 50}})
        assert "HIGH_TIER_INITIAL_VALIDATION" in a["hitl_conditions"]

    def test_fair_lending_escalates_to_cro(self):
        a = core.assess({"model_id": "M3", "risk_tier": "MEDIUM", "fair_lending_flag": True,
                         "current_dist": {"a": 50}, "baseline_dist": {"a": 50}})
        assert a["reviewer"] == "CHIEF_RISK_OFFICER"

    def test_hard_rule_violation_escalates_to_cro(self):
        a = core.assess({"model_id": "M4", "risk_tier": "MEDIUM", "hard_rule_violation": True,
                         "current_dist": {"a": 50}, "baseline_dist": {"a": 50}})
        assert a["reviewer"] == "CHIEF_RISK_OFFICER"

    def test_gini_drop_triggers_degradation(self):
        a = core.assess({"model_id": "M5", "risk_tier": "MEDIUM", "metric_deltas": {"gini_coefficient": -8.0},
                         "current_dist": {"a": 50}, "baseline_dist": {"a": 50}})
        assert "GINI_DROP" in a["degradation_flags"] and "PERFORMANCE_DEGRADATION_TRIGGERED" in a["hitl_conditions"]

    def test_stable_low_tier_no_review(self):
        a = core.assess({"model_id": "M6", "risk_tier": "LOW", "validation_type": "ANNUAL",
                         "current_dist": {"a": 50}, "baseline_dist": {"a": 50}})
        assert a["human_review_required"] is False and a["next"] == "Finalize"
