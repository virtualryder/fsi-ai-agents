import core


def test_always_hitl_frozenset_has_9():
    assert len(core.ALWAYS_HITL_CONDITIONS) == 9
    assert "SCRA_DETECTED" in core.ALWAYS_HITL_CONDITIONS


def test_contact_time_unknown_tz_fails_safe():
    permitted, hour = core.check_contact_time("Not/AZone")
    assert permitted is False and hour == -1


def test_contact_time_valid_tz_returns_bool():
    permitted, hour = core.check_contact_time("America/New_York")
    assert isinstance(permitted, bool) and 0 <= hour <= 23


class TestAssess:
    def test_scra_triggers_review_and_cap(self):
        a = core.assess({"account_id": "A1", "scra_active_duty": True})
        assert "SCRA_DETECTED" in a["hitl_conditions"] and a["scra_rate_cap"] == 6.0
        assert a["next"] == "SupervisorReviewGate"

    def test_bankruptcy_halts_all_collection(self):
        a = core.assess({"account_id": "A2", "bankruptcy_stay": True})
        assert a["all_collection_halted"] is True and "BANKRUPTCY_STAY_DETECTED" in a["hitl_conditions"]

    def test_high_value_settlement_flags(self):
        assert "SETTLEMENT_HIGH_VALUE" in core.assess({"account_id": "A3", "settlement_amount": 15000})["hitl_conditions"]

    def test_high_discount_settlement_flags(self):
        assert "SETTLEMENT_HIGH_VALUE" in core.assess({"account_id": "A4", "settlement_discount": 0.5})["hitl_conditions"]

    def test_minor_account_flags(self):
        assert "MINOR_ACCOUNT" in core.assess({"account_id": "A5", "debtor_age": 16})["hitl_conditions"]

    def test_cease_desist_flags(self):
        assert "CEASE_DESIST_RECEIVED" in core.assess({"account_id": "A6", "cease_desist": True})["hitl_conditions"]

    def test_clean_account_drafts_letter(self):
        a = core.assess({"account_id": "A7", "consumer_timezone": "America/New_York"})
        assert a["human_review_required"] is False and a["next"] == "DraftLetter"


def test_required_disclosures_include_scra_when_active():
    d = core.required_disclosures({}, core.assess({"scra_active_duty": True}))
    assert any("SCRA" in x for x in d) and any("Mini-Miranda" in x for x in d)
