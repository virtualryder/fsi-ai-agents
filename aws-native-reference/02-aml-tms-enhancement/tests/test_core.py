"""Deterministic core tests — suppression gate + 4-way routing (faithful to Phase 1.3)."""
import core


def test_deterministic_score_excludes_llm():
    # rule 100, historical 0 -> 60; rule 0 historical 100 -> 40 (0.6/0.4 renorm)
    assert core.deterministic_score(100, 0) == 60.0
    assert core.deterministic_score(0, 100) == 40.0


class TestRouting:
    def test_high_deterministic_suppresses_with_review_gate(self):
        r = core.routing_decision(95, 95, 95, {})
        assert r["decision"] == "SUPPRESS" and r["next"] == "SuppressionReviewGate"
        assert r["human_review_required"] is True

    def test_llm_high_but_deterministic_low_cannot_suppress(self):
        r = core.routing_decision(50, 99, 50, {})   # det=50 < suppress line
        assert r["decision"] != "SUPPRESS"

    def test_pep_forces_escalate_over_suppress(self):
        r = core.routing_decision(99, 99, 99, {"pep_flag": True})
        assert r["decision"] == "ESCALATE" and r["regulatory_override"] is True

    def test_open_investigation_escalates(self):
        r = core.routing_decision(99, 99, 99, {"has_open_investigation": True})
        assert r["decision"] == "ESCALATE"

    def test_mid_downgrades(self):
        assert core.routing_decision(70, 70, 70, {}).get("decision") == "DOWNGRADE"

    def test_low_deterministic_escalates(self):
        assert core.routing_decision(10, 90, 10, {})["decision"] == "ESCALATE"

    def test_normal_band_passes_through(self):
        assert core.routing_decision(40, 40, 40, {})["decision"] == "PASS_THROUGH"

    def test_only_suppress_requires_review(self):
        for rule, hist, exp in [(95, 95, True), (70, 70, False), (40, 40, False)]:
            assert core.routing_decision(rule, 50, hist, {})["human_review_required"] is exp


def test_routing_records_deterministic_basis():
    assert core.routing_decision(95, 95, 95, {})["routing_basis"] == "deterministic_suppression_gate"
