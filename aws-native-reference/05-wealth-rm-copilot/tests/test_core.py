import core


class TestSuitability:
    def _c(self, **kw): return {"risk_tolerance": kw.get("risk", "MODERATE"), "is_retirement_account": kw.get("ret", False)}

    def test_conservative_plus_leveraged_unsuitable(self):
        s = core.suitability_check(self._c(risk="CONSERVATIVE"), {}, "INVESTMENT_PROPOSAL", "3x leveraged ETF")
        assert s["status"] == "UNSUITABLE" and s["next"] == "BlockUnsuitable"

    def test_clean_suitable(self):
        s = core.suitability_check(self._c(), {"last_updated": "2025-01-01"}, "INVESTMENT_PROPOSAL", "index fund")
        assert s["status"] == "SUITABLE" and s["next"] == "Recommend"

    def test_ips_prohibited_unsuitable(self):
        s = core.suitability_check(self._c(), {"prohibited_securities": ["tobacco"], "last_updated": "2025-01-01"},
                                   "INVESTMENT_PROPOSAL", "tobacco position")
        assert s["status"] == "UNSUITABLE"

    def test_retirement_with_note_and_erisa(self):
        s = core.suitability_check(self._c(ret=True), {"last_updated": "2025-01-01"}, "INVESTMENT_PROPOSAL", "bond fund")
        assert s["status"] == "SUITABLE_WITH_NOTE" and any("ERISA" in d for d in s["disclosures"])

    def test_concentration_with_note(self):
        s = core.suitability_check(self._c(), {"last_updated": "2025-01-01"}, "INVESTMENT_PROPOSAL", "index fund",
                                   concentrated_positions=[{"name": "ACME"}])
        assert s["status"] == "SUITABLE_WITH_NOTE"

    def test_stale_ips_needs_review(self):
        s = core.suitability_check(self._c(), {"last_updated": "2022-01-01"}, "INVESTMENT_PROPOSAL", "index fund")
        assert s["status"] == "NEEDS_REVIEW"

    def test_unsuitable_precedence_over_with_note(self):
        s = core.suitability_check(self._c(risk="CONSERVATIVE", ret=True), {}, "INVESTMENT_PROPOSAL", "leveraged ETF")
        assert s["status"] == "UNSUITABLE"

    def test_non_investment_request_not_unsuitable(self):
        s = core.suitability_check(self._c(risk="CONSERVATIVE"), {}, "MEETING_PREP", "discuss leveraged options")
        assert s["status"] != "UNSUITABLE"

    def test_non_unsuitable_requires_rm_approval(self):
        s = core.suitability_check(self._c(), {"last_updated": "2025-01-01"}, "INVESTMENT_PROPOSAL", "index fund")
        assert s["human_review_required"] is True


def test_mask_ssn():
    m, t = core.mask_record({"n": "SSN 123-45-6789"})
    assert "123-45-6789" not in str(m) and "SSN" in t
