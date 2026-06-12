import core


def test_weights_sum_to_one():
    assert round(sum(core.WEIGHTS.values()), 6) == 1.0


class TestAssess:
    def test_high_impact_final_rule_is_critical(self):
        a = core.assess({"source_tier": "TIER_1", "days_to_effective": 20, "business_lines_count": 6,
                        "products_count": 8, "mapped_policies_count": 4, "change_type": "FINAL_RULE"})
        assert a["tier"] == "CRITICAL" and a["human_review_required"] is True

    def test_enforcement_forces_high_floor_and_hitl(self):
        a = core.assess({"source_tier": "TIER_3", "days_to_effective": 300, "change_type": "ENFORCEMENT_ACTION"})
        assert core.TIER_ORDER[a["tier"]] >= core.TIER_ORDER["HIGH"] and a["human_review_required"] is True

    def test_already_effective_final_rule_is_critical(self):
        a = core.assess({"source_tier": "TIER_2", "days_to_effective": 0, "change_type": "FINAL_RULE",
                        "already_effective": True})
        assert a["tier"] == "CRITICAL"

    def test_short_window_escalates_medium_to_high(self):
        a = core.assess({"source_tier": "TIER_2", "days_to_effective": 100, "business_lines_count": 2,
                        "products_count": 2, "mapped_policies_count": 2, "change_type": "GUIDANCE",
                        "compliance_window_too_short": True})
        assert a["tier"] == "HIGH"

    def test_low_impact_no_review(self):
        a = core.assess({"source_tier": "UNRECOGNIZED", "days_to_effective": 365, "change_type": "SPEECH"})
        assert a["tier"] == "LOW" and a["human_review_required"] is False and a["next"] == "Finalize"

    def test_high_routes_to_gap_analysis(self):
        a = core.assess({"source_tier": "TIER_1", "days_to_effective": 20, "business_lines_count": 6,
                        "products_count": 8, "mapped_policies_count": 4, "change_type": "FINAL_RULE"})
        assert a["next"] == "GapAnalysis"


def test_authority_tier_scores():
    assert core.AUTHORITY_TIER_SCORES["TIER_1"] == 1.0
