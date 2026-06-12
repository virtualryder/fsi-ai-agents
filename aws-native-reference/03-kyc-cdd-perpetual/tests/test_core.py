import core


class TestRescore:
    def test_ofac_forces_escalate(self):
        r = core.rescore("MEDIUM", 20, False, True)
        assert r["outcome"] == "ESCALATE" and r["next"] == "ComplianceReviewGate"

    def test_pep_without_edd_requires_edd(self):
        r = core.rescore("MEDIUM", 50, True, False, edd_current=False)
        assert r["outcome"] == "EDD_REQUIRED" and r["edd_required"] is True

    def test_high_score_upgrades(self):
        assert core.rescore("MEDIUM", 85, False, False)["outcome"] == "RISK_UPGRADE"

    def test_very_high_not_upgraded(self):
        assert core.rescore("VERY_HIGH", 85, False, False)["outcome"] != "RISK_UPGRADE"

    def test_low_score_downgrades(self):
        assert core.rescore("HIGH", 20, False, False)["outcome"] == "DOWNGRADE"

    def test_extreme_score_relationship_exit(self):
        assert core.rescore("HIGH", 95, False, False)["outcome"] == "REL_EXIT"

    def test_pass_needs_no_review(self):
        r = core.rescore("MEDIUM", 50, False, False)
        assert r["outcome"] == "PASS" and r["human_review_required"] is False and r["next"] == "Finalize"

    def test_any_change_requires_review(self):
        for sc, ofac, pep, edd in [(85, False, False, True), (20, False, False, True), (95, False, False, True)]:
            assert core.rescore("MEDIUM", sc, pep, ofac, edd_current=edd)["human_review_required"] is True


def test_screen_detects_hits():
    out = core.screen([{"name": "Ivan Petrov"}, {"name": "Maria Gonzalez"}],
                      {"ivan petrov": {"program": "X"}}, {"maria gonzalez": {"role": "Y"}})
    assert out["ofac_hit"] and out["pep_hit"]


def test_mask_ssn():
    m, t = core.mask_record({"n": "SSN 123-45-6789"})
    assert "123-45-6789" not in str(m) and "SSN" in t
