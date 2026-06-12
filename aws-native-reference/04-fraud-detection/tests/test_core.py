import core


class TestDecide:
    def test_known_fraud_ip_hard_blocks(self):
        d = core.decide(core.rule_engine({"ip": "203.0.113.66", "amount": 10}))
        assert d["decision"] == "BLOCK" and d["hard_block"] is True

    def test_ofac_merchant_hard_blocks(self):
        d = core.decide(core.rule_engine({"merchant_id": "MERCH-SDN-001"}))
        assert d["decision"] == "BLOCK"

    def test_high_composite_blocks(self):
        d = core.decide(core.rule_engine({"card_testing": True, "amount": 9999, "hourly_limit": 500, "mcc": "7995"}), 90)
        assert d["decision"] == "BLOCK"

    def test_step_up_band(self):
        d = core.decide({"rule_score": 70, "hard_block": False}, 70)
        assert d["decision"] == "STEP_UP"

    def test_review_band_requires_human(self):
        d = core.decide({"rule_score": 50, "hard_block": False}, 40)
        assert d["decision"] == "ANALYST_REVIEW" and d["human_review_required"] is True

    def test_low_allows(self):
        assert core.decide(core.rule_engine({"amount": 20}), 5)["decision"] == "ALLOW"

    def test_block_requires_reg_e(self):
        assert core.decide(core.rule_engine({"merchant_id": "MERCH-SDN-001"}))["reg_e_disclosure_required"] is True

    def test_hard_block_overrides_low_score(self):
        d = core.decide(core.rule_engine({"ip": "tor-exit", "amount": 1}), 0)
        assert d["decision"] == "BLOCK"


def test_composite_excludes_llm():
    assert core.composite_score(100, 0) == 60.0


def test_mask_pan_luhn():
    m, t = core.mask_record({"pan": "4111 1111 1111 1111"})
    assert "4111 1111 1111 1111" not in str(m) and "CREDIT_CARD" in t
