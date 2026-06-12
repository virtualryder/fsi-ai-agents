import core


def _go(a): return core.score_and_route(a, core.detect(a))


class TestScoreAndRoute:
    def test_always_hitl_types_are_critical(self):
        for t in ["INSIDER_TRADING", "INFORMATION_BARRIER_BREACH", "CROSS_MARKET_MANIPULATION"]:
            r = _go({"alert_type": t, "amount": 100})
            assert r["tier"] == "CRITICAL" and r["human_review_required"] is True

    def test_sar_requires_amount_and_suspicious(self):
        assert _go({"alert_type": "INSIDER_TRADING", "amount": 20000})["sar_required"] is True
        assert _go({"alert_type": "INSIDER_TRADING", "amount": 100})["sar_required"] is False  # below $5k
        assert _go({"alert_type": "UNUSUAL_ACTIVITY", "amount": 20000})["sar_required"] is False  # not suspicious

    def test_layering_high_cancel_is_high(self):
        r = _go({"alert_type": "LAYERING_SPOOFING", "amount": 6000, "raw": {"cancel_rate": 0.9}})
        assert r["tier"] in ("HIGH", "CRITICAL") and r["human_review_required"] is True

    def test_reg_sho_locate_failure_detected(self):
        r = _go({"alert_type": "SHORT_SELLING_VIOLATION", "amount": 1000,
                 "raw": {"short_exempt": False, "locate_obtained": False}})
        assert r["reg_sho_violation"] is True

    def test_low_unusual_dispositions(self):
        r = _go({"alert_type": "UNUSUAL_ACTIVITY", "amount": 100})
        assert r["human_review_required"] is False and r["next"] == "Disposition"

    def test_critical_routes_to_review(self):
        assert _go({"alert_type": "INSIDER_TRADING", "amount": 100})["next"] == "ComplianceReviewGate"


def test_always_hitl_frozenset():
    assert "INSIDER_TRADING" in core.ALWAYS_HITL_ALERT_TYPES
    assert core.SAR_AMOUNT_THRESHOLD == 5000.0
