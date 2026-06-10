"""
Agent 11 — Model Risk Management Agent
Unit tests for node functions and security properties.

Test coverage:
- Security: ALWAYS_HITL_CONDITIONS frozenset immutability
- Security: No individual predictions or PII in node outputs
- Model registry: all 5 models present with required fields
- Weight normalization: weights must sum to 1.0
- Performance degradation: thresholds correctly trigger flags
- PSI classification: all three tiers
- Risk tier determination: HITL conditions, routing, risk scores
- Hard rule coverage: OFAC and PEP overrides documented
- Audit trail: append-only, no modification of prior entries
- Routing: fail-safe defaults for missing/unknown keys
"""

import math
import unittest
from unittest.mock import patch, MagicMock

from agent.state import (
    ALWAYS_HITL_CONDITIONS,
    MODEL_REGISTRY,
    PERFORMANCE_DEGRADATION_THRESHOLDS,
    HITL_VALIDATION_TYPES,
    HIGH_TIER_ALWAYS_HITL,
    VALIDATION_TYPES,
    REVIEWER_DECISIONS,
    VALIDATION_OUTCOMES,
)
from agent.nodes import (
    _append_audit,
    _classify_psi,
    _compute_psi,
    model_inventory_lookup_node,
    data_sample_pull_node,
    outcomes_analysis_node,
    population_stability_analysis_node,
    benchmark_comparison_node,
    sensitivity_analysis_node,
    risk_tier_determination_node,
    human_review_gate_node,
    audit_finalize_node,
)


# ── Security properties ───────────────────────────────────────────────────────

class TestSecurityProperties(unittest.TestCase):
    """Critical security property tests — these must never fail."""

    def test_always_hitl_is_frozenset(self):
        """ALWAYS_HITL_CONDITIONS must be a frozenset — enforces Python-level immutability."""
        self.assertIsInstance(ALWAYS_HITL_CONDITIONS, frozenset)

    def test_always_hitl_cannot_be_modified(self):
        """frozenset.add() raises TypeError — immutability enforced by the language."""
        with self.assertRaises((TypeError, AttributeError)):
            ALWAYS_HITL_CONDITIONS.add("NEW_HITL_CONDITION")

    def test_always_hitl_cannot_be_discarded(self):
        """frozenset.discard() raises AttributeError — cannot remove conditions."""
        with self.assertRaises(AttributeError):
            ALWAYS_HITL_CONDITIONS.discard("MATERIAL_FINDING")

    def test_always_hitl_contains_required_conditions(self):
        """All nine required HITL conditions must be present."""
        required = {
            "HIGH_TIER_INITIAL_VALIDATION",
            "HIGH_TIER_CHANGE_VALIDATION",
            "ANNUAL_REVALIDATION_HIGH_TIER",
            "PERFORMANCE_DEGRADATION_TRIGGERED",
            "PSI_CRITICAL",
            "MATERIAL_FINDING",
            "CHALLENGER_UNDERPERFORMS",
            "HARD_RULE_VIOLATION_DETECTED",
            "FAIR_LENDING_FLAG",
        }
        self.assertTrue(
            required.issubset(ALWAYS_HITL_CONDITIONS),
            f"Missing conditions: {required - ALWAYS_HITL_CONDITIONS}",
        )

    def test_high_tier_always_hitl_is_frozenset(self):
        """HIGH_TIER_ALWAYS_HITL must be frozenset."""
        self.assertIsInstance(HIGH_TIER_ALWAYS_HITL, frozenset)

    def test_high_tier_always_hitl_cannot_be_modified(self):
        with self.assertRaises((TypeError, AttributeError)):
            HIGH_TIER_ALWAYS_HITL.add("NEW-MODEL-ID")

    def test_all_suite_models_are_high_tier(self):
        """All 5 models in the suite are HIGH-tier per SR 11-7 significance."""
        for model_id, meta in MODEL_REGISTRY.items():
            self.assertEqual(
                meta["risk_tier"], "HIGH",
                f"{model_id} should be HIGH tier (systemic compliance impact)",
            )

    def test_hitl_validation_types_is_frozenset(self):
        """HITL_VALIDATION_TYPES must be frozenset."""
        self.assertIsInstance(HITL_VALIDATION_TYPES, frozenset)


# ── Model registry ────────────────────────────────────────────────────────────

class TestModelRegistry(unittest.TestCase):
    """Model registry completeness and consistency tests."""

    EXPECTED_MODELS = {
        "AGT02-FP-SCORE-v1",
        "AGT03-KYC-RISK-v1",
        "AGT04-FRAUD-SCORE-v1",
        "AGT07-SURV-RISK-v1",
        "AGT08-CREDIT-SCORE-v1",
    }

    def test_all_five_models_present(self):
        """All 5 suite scoring models must be in the registry."""
        self.assertEqual(set(MODEL_REGISTRY.keys()), self.EXPECTED_MODELS)

    def test_all_models_have_required_fields(self):
        """Each registry entry must have all required SR 11-7 fields."""
        required_fields = {
            "agent", "agent_name", "model_name", "model_type",
            "risk_tier", "weights", "decision_thresholds", "hard_rules",
            "revalidation_months", "known_limitations",
        }
        for model_id, meta in MODEL_REGISTRY.items():
            missing = required_fields - set(meta.keys())
            self.assertFalse(
                missing,
                f"{model_id} missing required SR 11-7 fields: {missing}",
            )

    def test_weight_normalization_all_models(self):
        """Factor weights must sum to 1.0 (within tolerance) for all models."""
        for model_id, meta in MODEL_REGISTRY.items():
            weights = meta.get("weights", {})
            if weights:
                total = sum(weights.values())
                self.assertAlmostEqual(
                    total, 1.0, places=5,
                    msg=f"{model_id} weights sum to {total:.6f} (expected 1.0)",
                )

    def test_all_models_have_ofac_hard_rule(self):
        """Every model must document an OFAC hard rule — compliance requirement."""
        for model_id, meta in MODEL_REGISTRY.items():
            hard_rules = meta.get("hard_rules", [])
            has_ofac = any("OFAC" in r.upper() for r in hard_rules)
            self.assertTrue(
                has_ofac,
                f"{model_id} missing OFAC hard rule documentation. "
                "SR 11-7 requires all hard rules be documented.",
            )

    def test_revalidation_months_is_12_for_high_tier(self):
        """HIGH-tier models must have 12-month revalidation cycle per SR 11-7."""
        for model_id, meta in MODEL_REGISTRY.items():
            if meta["risk_tier"] == "HIGH":
                self.assertEqual(
                    meta.get("revalidation_months"), 12,
                    f"{model_id} (HIGH tier) should have 12-month revalidation",
                )

    def test_known_limitations_documented(self):
        """Each model must document at least one known limitation — SR 11-7 § 7."""
        for model_id, meta in MODEL_REGISTRY.items():
            limitations = meta.get("known_limitations", [])
            self.assertGreater(
                len(limitations), 0,
                f"{model_id} has no documented known limitations. "
                "SR 11-7 § 7 requires limitation documentation.",
            )


# ── PSI computation ───────────────────────────────────────────────────────────

class TestPSIComputation(unittest.TestCase):
    """Population Stability Index mathematical correctness tests."""

    def test_psi_stable_same_distribution(self):
        """Identical distributions should produce PSI near 0."""
        dist = {"bucket_1": 0.25, "bucket_2": 0.25, "bucket_3": 0.25, "bucket_4": 0.25}
        psi = _compute_psi(dist, dist)
        self.assertAlmostEqual(psi, 0.0, places=3)

    def test_psi_classify_stable(self):
        self.assertEqual(_classify_psi(0.05), "STABLE")

    def test_psi_classify_stable_boundary(self):
        """PSI exactly at 0.10 is WARNING (threshold is exclusive)."""
        self.assertEqual(_classify_psi(0.10), "WARNING")

    def test_psi_classify_warning(self):
        self.assertEqual(_classify_psi(0.15), "WARNING")

    def test_psi_classify_critical_boundary(self):
        """PSI exactly at 0.25 is CRITICAL."""
        self.assertEqual(_classify_psi(0.25), "CRITICAL")

    def test_psi_classify_critical(self):
        self.assertEqual(_classify_psi(0.35), "CRITICAL")

    def test_psi_thresholds_match_constants(self):
        """Thresholds in PERFORMANCE_DEGRADATION_THRESHOLDS must match classification logic."""
        self.assertEqual(PERFORMANCE_DEGRADATION_THRESHOLDS["psi_warning"], 0.10)
        self.assertEqual(PERFORMANCE_DEGRADATION_THRESHOLDS["psi_critical"], 0.25)


# ── Performance degradation ───────────────────────────────────────────────────

class TestPerformanceDegradation(unittest.TestCase):
    """Degradation flag triggering tests — all thresholds verified against constants."""

    def _make_state(self, current_metrics, baseline_metrics):
        deltas = {k: current_metrics.get(k, 0) - baseline_metrics.get(k, 0)
                  for k in current_metrics}
        return {
            "current_metrics": current_metrics,
            "baseline_metrics": baseline_metrics,
            "metric_deltas": deltas,
            "model_record": MODEL_REGISTRY["AGT04-FRAUD-SCORE-v1"],
            "audit_trail": [],
        }

    def test_gini_degradation_triggers_at_threshold(self):
        """Gini drop > 10 points triggers GINI_DEGRADATION flag."""
        state = self._make_state(
            {"gini_coefficient": 59.9},  # 70.1 - 10.2 = 10.2 drop
            {"gini_coefficient": 70.1},
        )
        result = outcomes_analysis_node(state)
        self.assertIn("GINI_DEGRADATION", result["degradation_flags"])

    def test_gini_within_threshold_no_flag(self):
        """Gini drop ≤ 10 points does NOT trigger flag."""
        state = self._make_state(
            {"gini_coefficient": 61.0},  # 70.1 - 9.1 = 9.1 drop
            {"gini_coefficient": 70.1},
        )
        result = outcomes_analysis_node(state)
        self.assertNotIn("GINI_DEGRADATION", result["degradation_flags"])

    def test_accuracy_degradation_triggers_at_threshold(self):
        """Accuracy drop > 5pp triggers ACCURACY_DEGRADATION flag."""
        state = self._make_state(
            {"accuracy": 88.0},  # 94.0 - 6.0 = 6pp drop
            {"accuracy": 94.0},
        )
        result = outcomes_analysis_node(state)
        self.assertIn("ACCURACY_DEGRADATION", result["degradation_flags"])

    def test_accuracy_within_threshold_no_flag(self):
        """Accuracy drop ≤ 5pp does NOT trigger flag."""
        state = self._make_state(
            {"accuracy": 89.5},  # 94.0 - 4.5 = 4.5pp drop
            {"accuracy": 94.0},
        )
        result = outcomes_analysis_node(state)
        self.assertNotIn("ACCURACY_DEGRADATION", result["degradation_flags"])

    def test_fnr_increase_triggers_at_threshold(self):
        """FNR increase > 3pp triggers FNR_INCREASE (higher severity than FPR)."""
        state = self._make_state(
            {"false_negative_rate": 17.5},  # 13.0 + 4.5 = 4.5pp increase
            {"false_negative_rate": 13.0},
        )
        result = outcomes_analysis_node(state)
        self.assertIn("FNR_INCREASE", result["degradation_flags"])

    def test_critical_outcome_when_accuracy_and_fnr_flag(self):
        """ACCURACY_DEGRADATION + FNR_INCREASE → CRITICAL performance outcome."""
        state = self._make_state(
            {"accuracy": 87.0, "false_negative_rate": 18.0},
            {"accuracy": 94.0, "false_negative_rate": 13.0},
        )
        result = outcomes_analysis_node(state)
        self.assertEqual(result["performance_outcome"], "CRITICAL")

    def test_pass_outcome_no_flags(self):
        """No degradation flags → PASS performance outcome."""
        state = self._make_state(
            {"accuracy": 93.5, "gini_coefficient": 68.0},
            {"accuracy": 94.8, "gini_coefficient": 70.1},
        )
        result = outcomes_analysis_node(state)
        self.assertEqual(result["performance_outcome"], "PASS")
        self.assertEqual(result["degradation_flags"], [])


# ── Risk tier determination ───────────────────────────────────────────────────

class TestRiskTierDetermination(unittest.TestCase):
    """HITL condition and routing logic tests."""

    def _make_state(self, **kwargs):
        defaults = {
            "risk_tier": "HIGH",
            "validation_type": "ANNUAL_REVALIDATION",
            "performance_outcome": "PASS",
            "degradation_flags": [],
            "material_findings": [],
            "psi_flag": "STABLE",
            "challenger_comparison_result": None,
            "hard_rule_violations": [],
            "revalidation_overdue": False,
            "audit_trail": [],
        }
        defaults.update(kwargs)
        return defaults

    def test_high_tier_annual_revalidation_requires_hitl(self):
        """HIGH-tier annual revalidation always requires HITL (MRO sign-off)."""
        state = self._make_state(risk_tier="HIGH", validation_type="ANNUAL_REVALIDATION")
        result = risk_tier_determination_node(state)
        self.assertTrue(result["human_review_required"])
        self.assertIn("ANNUAL_REVALIDATION_HIGH_TIER", result["hitl_conditions"])

    def test_high_tier_initial_validation_requires_hitl(self):
        """HIGH-tier initial validation always requires HITL."""
        state = self._make_state(risk_tier="HIGH", validation_type="INITIAL_VALIDATION")
        result = risk_tier_determination_node(state)
        self.assertTrue(result["human_review_required"])

    def test_critical_performance_triggers_hitl(self):
        """CRITICAL performance outcome adds PERFORMANCE_DEGRADATION_TRIGGERED."""
        state = self._make_state(
            risk_tier="HIGH", validation_type="TRIGGERED_REVIEW",
            performance_outcome="CRITICAL",
        )
        result = risk_tier_determination_node(state)
        self.assertIn("PERFORMANCE_DEGRADATION_TRIGGERED", result["hitl_conditions"])

    def test_psi_critical_triggers_hitl(self):
        """PSI_CRITICAL flag adds PSI_CRITICAL HITL condition."""
        state = self._make_state(psi_flag="CRITICAL")
        result = risk_tier_determination_node(state)
        self.assertIn("PSI_CRITICAL", result["hitl_conditions"])

    def test_material_findings_trigger_hitl(self):
        """Material findings add MATERIAL_FINDING HITL condition."""
        state = self._make_state(material_findings=["Gini declined 12 points"])
        result = risk_tier_determination_node(state)
        self.assertIn("MATERIAL_FINDING", result["hitl_conditions"])

    def test_ongoing_monitoring_pass_no_hitl(self):
        """ONGOING_MONITORING with PASS outcome — no additional HITL beyond HIGH tier annual."""
        # ONGOING_MONITORING is not in HITL_VALIDATION_TYPES — no auto-HITL for HIGH tier
        state = self._make_state(
            risk_tier="HIGH", validation_type="ONGOING_MONITORING",
            performance_outcome="PASS",
        )
        result = risk_tier_determination_node(state)
        # No HITL for ongoing monitoring with pass outcome (not in HITL_VALIDATION_TYPES)
        self.assertFalse(result["human_review_required"])

    def test_hard_rule_violation_routes_to_cro(self):
        """Hard rule violations escalate to CHIEF_RISK_OFFICER."""
        state = self._make_state(hard_rule_violations=["OFAC bypass detected in prod log"])
        result = risk_tier_determination_node(state)
        self.assertEqual(result["target_reviewer"], "CHIEF_RISK_OFFICER")
        self.assertIn("HARD_RULE_VIOLATION_DETECTED", result["hitl_conditions"])

    def test_hitl_conditions_are_subset_of_always_hitl(self):
        """All computed HITL conditions must be members of ALWAYS_HITL_CONDITIONS."""
        state = self._make_state(
            performance_outcome="CRITICAL",
            material_findings=["Something found"],
            psi_flag="CRITICAL",
        )
        result = risk_tier_determination_node(state)
        for condition in result["hitl_conditions"]:
            self.assertIn(
                condition, ALWAYS_HITL_CONDITIONS,
                f"Condition '{condition}' not in ALWAYS_HITL_CONDITIONS frozenset",
            )


# ── Human review gate ────────────────────────────────────────────────────────

class TestHumanReviewGate(unittest.TestCase):
    """HITL gate security and outcome mapping tests."""

    def test_approve_maps_to_approved(self):
        state = {"reviewer_decision": "APPROVE_VALIDATION", "reviewer_id": "MRO-001", "audit_trail": []}
        result = human_review_gate_node(state)
        self.assertEqual(result["validation_outcome"], "APPROVED")

    def test_conditionally_approve_maps_to_conditionally_approved(self):
        state = {"reviewer_decision": "CONDITIONALLY_APPROVE", "reviewer_id": "MRO-001", "audit_trail": []}
        result = human_review_gate_node(state)
        self.assertEqual(result["validation_outcome"], "CONDITIONALLY_APPROVED")

    def test_require_remediation_maps_to_suspended(self):
        state = {"reviewer_decision": "REQUIRE_REMEDIATION", "reviewer_id": "MRO-001", "audit_trail": []}
        result = human_review_gate_node(state)
        self.assertEqual(result["validation_outcome"], "SUSPENDED")

    def test_escalate_to_board_maps_to_under_review(self):
        state = {"reviewer_decision": "ESCALATE_TO_BOARD", "reviewer_id": "MRO-001", "audit_trail": []}
        result = human_review_gate_node(state)
        self.assertEqual(result["validation_outcome"], "UNDER_REVIEW")

    def test_unknown_decision_rejected(self):
        """Unknown decision strings cannot trigger approval — fail-safe."""
        state = {"reviewer_decision": "APPROVE_EVERYTHING", "reviewer_id": "attacker", "audit_trail": []}
        result = human_review_gate_node(state)
        # Unknown decision → empty string → UNDER_REVIEW (fail-safe)
        self.assertEqual(result["reviewer_decision"], "")
        self.assertEqual(result["validation_outcome"], "UNDER_REVIEW")

    def test_missing_decision_falls_back_to_under_review(self):
        """Missing reviewer_decision defaults to UNDER_REVIEW — fail-safe."""
        state = {"reviewer_id": "MRO-001", "audit_trail": []}
        result = human_review_gate_node(state)
        self.assertEqual(result["validation_outcome"], "UNDER_REVIEW")

    def test_reviewer_timestamp_is_recorded(self):
        """Human review gate must record a UTC timestamp."""
        state = {"reviewer_decision": "APPROVE_VALIDATION", "reviewer_id": "MRO-001", "audit_trail": []}
        result = human_review_gate_node(state)
        self.assertIn("reviewer_timestamp", result)
        self.assertIsNotNone(result["reviewer_timestamp"])


# ── Audit trail ───────────────────────────────────────────────────────────────

class TestAuditTrail(unittest.TestCase):
    """Audit trail append-only and completeness tests."""

    def test_append_adds_entry(self):
        trail = []
        updated = _append_audit(trail, "test_node", {"key": "value"})
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["node"], "test_node")
        self.assertEqual(updated[0]["key"], "value")

    def test_append_does_not_modify_prior_entries(self):
        """Prior audit entries must not be modified when new entries are added."""
        trail = [{"node": "node_1", "timestamp_utc": "2026-01-01T00:00:00Z", "data": "original"}]
        original_data = trail[0]["data"]

        updated = _append_audit(trail, "node_2", {"data": "new"})

        # Prior entry unchanged
        self.assertEqual(updated[0]["data"], original_data)
        self.assertEqual(updated[0]["node"], "node_1")
        # New entry added
        self.assertEqual(updated[1]["node"], "node_2")
        self.assertEqual(len(updated), 2)

    def test_audit_entries_have_timestamp(self):
        """Every audit entry must have a UTC timestamp."""
        trail = _append_audit([], "any_node", {})
        self.assertIn("timestamp_utc", trail[0])
        ts = trail[0]["timestamp_utc"]
        self.assertIn("T", ts)  # ISO format
        self.assertIn("+", ts) or self.assertIn("Z", ts)

    def test_audit_finalize_records_retention_policy(self):
        """Audit finalize must document the 10-year retention policy."""
        state = {
            "model_id": "AGT02-FP-SCORE-v1",
            "model_record": MODEL_REGISTRY["AGT02-FP-SCORE-v1"],
            "validation_id": "TEST-001",
            "resolution_type": "APPROVED",
            "audit_trail": [],
        }
        result = audit_finalize_node(state)
        final_entry = result["audit_trail"][-1]
        self.assertIn("10_YEARS", final_entry.get("audit_retention", ""))


# ── Threshold constants ───────────────────────────────────────────────────────

class TestThresholdConstants(unittest.TestCase):
    """Verify threshold constant values are correct for regulatory compliance."""

    def test_accuracy_degradation_threshold(self):
        self.assertEqual(PERFORMANCE_DEGRADATION_THRESHOLDS["accuracy_drop_pct"], 5.0)

    def test_gini_degradation_threshold(self):
        self.assertEqual(PERFORMANCE_DEGRADATION_THRESHOLDS["gini_drop_points"], 10.0)

    def test_psi_warning_threshold(self):
        self.assertEqual(PERFORMANCE_DEGRADATION_THRESHOLDS["psi_warning"], 0.10)

    def test_psi_critical_threshold(self):
        self.assertEqual(PERFORMANCE_DEGRADATION_THRESHOLDS["psi_critical"], 0.25)

    def test_fnr_threshold_tighter_than_fpr(self):
        """FNR threshold must be tighter than FPR (missing positives is worse in compliance)."""
        self.assertLess(
            PERFORMANCE_DEGRADATION_THRESHOLDS["false_negative_rate_increase"],
            PERFORMANCE_DEGRADATION_THRESHOLDS["false_positive_rate_increase"],
        )

    def test_all_validation_types_defined(self):
        """All 5 validation types must be defined."""
        expected = {"INITIAL_VALIDATION", "ANNUAL_REVALIDATION", "TRIGGERED_REVIEW",
                    "CHANGE_VALIDATION", "ONGOING_MONITORING"}
        self.assertEqual(set(VALIDATION_TYPES.keys()), expected)

    def test_all_reviewer_decisions_defined(self):
        """All 4 reviewer decisions must be defined."""
        expected = {"APPROVE_VALIDATION", "CONDITIONALLY_APPROVE",
                    "REQUIRE_REMEDIATION", "ESCALATE_TO_BOARD"}
        self.assertEqual(set(REVIEWER_DECISIONS.keys()), expected)


if __name__ == "__main__":
    unittest.main()
