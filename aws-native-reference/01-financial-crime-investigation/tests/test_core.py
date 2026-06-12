"""Deterministic core tests — faithful to Agent 01 weights/thresholds + OFAC override."""
import core


def test_weights_sum_to_100():
    assert sum(core.RISK_WEIGHTS.values()) == 100.0


def test_composite_score_is_weighted_sum():
    s, b = core.compute_risk_score({"sanctions": 1.0, "network": 1.0, "transactions": 1.0,
                                    "adverse_media": 1.0, "customer_profile": 1.0})
    assert s == 100.0
    assert b["sanctions"] == 30.0 and b["network"] == 25.0


class TestRouting:
    def test_high_score_drafts_sar(self):
        r = core.routing_decision(80.0)
        assert r["next"] == "GenerateSAR" and r["human_review_required"] is True

    def test_mid_score_human_review(self):
        r = core.routing_decision(45.0)
        assert r["next"] == "HumanReviewGate" and r["human_review_required"] is True

    def test_low_score_closes(self):
        r = core.routing_decision(12.0)
        assert r["next"] == "CloseCase" and r["human_review_required"] is False

    def test_ofac_hit_forces_sar_even_at_low_score(self):
        r = core.routing_decision(5.0, ofac_hit=True)
        assert r["next"] == "GenerateSAR" and r["human_review_required"] is True

    def test_pep_hit_forces_review_not_close(self):
        r = core.routing_decision(10.0, pep_hit=True)
        assert r["next"] == "HumanReviewGate"


def test_screen_detects_ofac_and_pep():
    sanc = {"ivan petrov": {"program": "X"}}
    peps = {"maria gonzalez": {"role": "Y"}}
    out = core.screen_parties([{"name": "Ivan Petrov"}, {"name": "Maria Gonzalez"}], sanc, peps)
    assert out["ofac_hit"] is True and out["pep_hit"] is True and len(out["hits"]) == 2


def test_mask_record_masks_ssn():
    masked, types = core.mask_record({"note": "SSN 123-45-6789"})
    assert "123-45-6789" not in str(masked) and "SSN" in types
