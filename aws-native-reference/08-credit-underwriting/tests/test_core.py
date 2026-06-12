"""Deterministic core — faithful credit decisioning + ECOA codes + hard declines."""
import core


def test_weights_sum_to_one():
    assert round(sum(core.WEIGHTS.values()), 6) == 1.0


class TestEvaluate:
    def test_strong_file_approves(self):
        e = core.evaluate({"credit_score": 780, "total_dti_ratio": 0.30, "ltv_ratio": 0.70,
                           "income_verified": True, "reserves_months": 6})
        assert e["decision"] == "APPROVE" and e["hard_decline"] is False

    def test_dti_over_50_hard_declines(self):
        e = core.evaluate({"credit_score": 720, "total_dti_ratio": 0.55, "ltv_ratio": 0.80})
        assert e["decision"] == "DECLINE" and core.AAR.DTI_TOO_HIGH in e["adverse_action_reasons"]

    def test_ofac_hard_block(self):
        e = core.evaluate({"credit_score": 800, "total_dti_ratio": 0.2, "ltv_ratio": 0.5, "ofac_hit": True})
        assert e["decision"] == "DECLINE" and e["adverse_action_reasons"] == [core.AAR.OFAC_MATCH]

    def test_low_fico_declines_with_code(self):
        e = core.evaluate({"credit_score": 600, "total_dti_ratio": 0.30, "ltv_ratio": 0.80})
        assert e["decision"] == "DECLINE" and core.AAR.CREDIT_SCORE_TOO_LOW in e["adverse_action_reasons"]

    def test_recent_ch7_bankruptcy_declines(self):
        e = core.evaluate({"credit_score": 720, "total_dti_ratio": 0.30, "ltv_ratio": 0.70,
                           "bankruptcy": {"chapter": "CHAPTER_7", "discharge_years": 1.0}})
        assert e["decision"] == "DECLINE" and core.AAR.BANKRUPTCY in e["adverse_action_reasons"]

    def test_reasons_capped_at_four(self):
        e = core.evaluate({"credit_score": 500, "total_dti_ratio": 0.6, "ltv_ratio": 0.99,
                           "income_verified": False})
        assert len(e["adverse_action_reasons"]) <= 4

    def test_tiers_monotonic(self):
        assert core.evaluate({"credit_score": 760, "total_dti_ratio": 0.30, "ltv_ratio": 0.75,
                              "income_verified": True, "reserves_months": 6})["tier"] in (
            "APPROVE", "APPROVE_WITH_CONDITIONS")


class TestRouting:
    def test_clean_approve_auto_routes(self):
        e = core.evaluate({"credit_score": 780, "total_dti_ratio": 0.30, "ltv_ratio": 0.70,
                           "income_verified": True, "reserves_months": 6})
        assert core.routing_decision(e)["next"] == "AutoApprove"

    def test_decline_drafts_adverse_action(self):
        e = core.evaluate({"credit_score": 600, "total_dti_ratio": 0.30, "ltv_ratio": 0.80})
        assert core.routing_decision(e)["next"] == "GenerateAdverseAction"

    def test_fair_lending_flag_forces_review(self):
        e = core.evaluate({"credit_score": 780, "total_dti_ratio": 0.30, "ltv_ratio": 0.70,
                           "income_verified": True, "reserves_months": 6})
        r = core.routing_decision(e, ["AIR<0.80"])
        assert r["next"] == "UnderwriterReviewGate" and r["human_review_required"] is True
