"""Deterministic core — OFAC/Nacha/Reg E + HITL frozenset triggers (faithful)."""
import core


def test_frozensets_present():
    assert "OFAC_HOLD" in core.ALWAYS_HITL_PAYMENT_EVENTS
    assert core.UNAUTHORIZED_RETURN_CODES == frozenset({"R05", "R07", "R10", "R29"})
    assert "IR" in core.OFAC_SANCTIONED_COUNTRY_CODES


class TestRouting:
    def _go(self, ev):
        return core.routing_decision(ev, core.screen(ev))

    def test_unauthorized_return_forces_hitl(self):
        r = self._go({"event_type": "ACH_RETURN", "return_code": "R10", "consumer": True, "amount": 1200})
        assert r["next"] == "HumanReviewGate" and r["human_review_required"] is True

    def test_ofac_country_wire_forces_hitl(self):
        assert self._go({"event_type": "WIRE", "country": "IR", "amount": 5000})["next"] == "HumanReviewGate"

    def test_amount_over_threshold_forces_hitl(self):
        assert self._go({"event_type": "WIRE", "amount": 75000})["next"] == "HumanReviewGate"

    def test_always_hitl_event_type(self):
        assert self._go({"event_type": "SAR_CANDIDATE", "amount": 100})["next"] == "HumanReviewGate"

    def test_noc_auto_resolves(self):
        assert self._go({"event_type": "NOC", "amount": 0})["next"] == "AutoResolve"

    def test_normal_dispute_drafts_notice(self):
        assert self._go({"event_type": "ACH_DISPUTE", "return_code": "R01", "amount": 200})["next"] == "DraftNotice"


def test_reg_e_eligibility():
    s = core.screen({"return_code": "R10", "consumer": True})
    assert s["reg_e_eligible"] is True
    s2 = core.screen({"return_code": "R01", "consumer": True})
    assert s2["reg_e_eligible"] is False


def test_mask_account_and_ssn():
    masked, types = core.mask_record({"note": "account 12345678 SSN 123-45-6789"})
    assert "12345678" not in str(masked) and "123-45-6789" not in str(masked)
    assert "SSN" in types and "ACCOUNT" in types
