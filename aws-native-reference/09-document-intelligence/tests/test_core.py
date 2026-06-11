"""Deterministic core tests — the 'Python decides' layer (faithful to Agent 09)."""
import core


class TestConfidenceTier:
    def test_tiers(self):
        assert core.confidence_tier(0.90) == "HIGH"
        assert core.confidence_tier(0.70) == "MEDIUM"
        assert core.confidence_tier(0.40) == "LOW"
        assert core.confidence_tier(0.0) == "UNCERTAIN"


class TestRouting:
    def test_high_conf_known_type_auto_routes(self):
        r = core.routing_decision("loan_application_1003", 0.95)
        assert r["human_review_required"] is False and r["next"] == "AutoRoute"
        assert "08-credit-underwriting" in r["target_agents"]

    def test_always_hitl_type_forces_review_even_at_high_conf(self):
        for dt in ["government_id", "sar_form", "ctr_form", "consent_order"]:
            r = core.routing_decision(dt, 0.99)
            assert r["human_review_required"] is True, dt
            assert r["next"] == "HumanReviewGate"

    def test_low_confidence_forces_review(self):
        r = core.routing_decision("bank_statement", 0.40)
        assert r["human_review_required"] is True

    def test_unknown_type_forces_review(self):
        r = core.routing_decision("unknown", 0.95)
        assert r["human_review_required"] is True

    def test_business_rule_violation_forces_review(self):
        r = core.routing_decision("wire_instruction", 0.95,
                                   business_rule_violations=["missing beneficiary"])
        assert r["human_review_required"] is True

    def test_sensitive_pii_forces_review(self):
        r = core.routing_decision("bank_statement", 0.95, pii_handling="HUMAN_REVIEW")
        assert r["human_review_required"] is True

    def test_validation_errors_force_review(self):
        r = core.routing_decision("loan_application_1003", 0.95,
                                   validation_errors=["missing required field: borrower"])
        assert r["human_review_required"] is True


class TestPiiBoundary:
    def test_ssn_masked_in_record(self):
        masked, types = core.mask_record({"text": "SSN 123-45-6789", "k": 1})
        assert "123-45-6789" not in str(masked) and "SSN" in types
        assert masked["k"] == 1
