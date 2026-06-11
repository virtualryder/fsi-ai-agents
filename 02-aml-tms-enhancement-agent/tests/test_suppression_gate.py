"""
Deterministic suppression-gate control tests (Phase 1.3).

Control claim: SUPPRESS is the only disposition that removes an alert from
human review, and it may fire ONLY when the deterministic-only score (rule
pre-score + historical base rates, LLM EXCLUDED) independently clears the
suppress threshold. A model-generated number can never be the reason an alert
disappears from the analyst queue.

These tests drive determine_routing directly with hand-built state so the
deterministic score and the (LLM-influenced) composite can be set independently.
"""
from __future__ import annotations

import pytest

from agent.nodes import determine_routing


def _features(alert_type="WIRE_ROUND_TRIP", risk_tier="LOW"):
    # A clean feature set: no regulatory-override trigger (no PEP, no open
    # investigation, no OFAC-adjacent combo), default thresholds apply
    # (suppress=85, downgrade=60, escalate=15).
    return {
        "alert_type": alert_type,
        "risk_tier": risk_tier,
        "pep_flag": False,
        "has_open_investigation": False,
        "high_risk_geography": False,
        "amount_usd": 5_000,
        "account_age_days": 4_000,
        "prior_sars_filed": 0,
        "rule_fp_rate": 0.5,
        "typology_fp_rate": 0.5,
        "peer_group_fp_rate": 0.5,
        "customer_historical_fp_rate": 0.5,
    }


def _state(composite, deterministic, llm_fp):
    return {
        "scoring_features": _features(),
        "composite_fp_score": composite,
        "deterministic_fp_score": deterministic,
        "llm_fp_probability": llm_fp,
        "llm_confidence": 0.9,
        "llm_primary_reason": "test",
        "llm_suppression_factors": [],
        "llm_pass_through_factors": [],
        "llm_regulatory_override": False,
        "llm_regulatory_override_reason": "",
        "scoring_notes": [],
        "audit_trail": [],
    }


def test_llm_cannot_suppress_without_deterministic_support():
    """
    Composite is over the suppress line (90) ONLY because the LLM said 90, but
    the deterministic-only score (50) does not clear suppress. The alert must
    NOT be suppressed — it stays human-visible.
    """
    result = determine_routing(_state(composite=90.0, deterministic=50.0, llm_fp=90.0))
    decision = result["routing"]["decision"]
    assert decision != "SUPPRESS", f"LLM-only score must not suppress (got {decision})"
    assert decision in ("DOWNGRADE", "PASS_THROUGH")


def test_suppression_allowed_when_deterministic_supports_it():
    """When the deterministic score itself clears suppress, SUPPRESS is valid."""
    result = determine_routing(_state(composite=92.0, deterministic=90.0, llm_fp=92.0))
    assert result["routing"]["decision"] == "SUPPRESS"


def test_gate_is_recorded_in_audit_trail():
    """When the gate downgrades a would-be suppression, the audit says so."""
    result = determine_routing(_state(composite=90.0, deterministic=50.0, llm_fp=90.0))
    routing_entries = [a for a in result["audit_trail"] if a.get("action") == "ROUTING_DECISION_MADE"]
    assert routing_entries, "routing audit entry missing"
    entry = routing_entries[-1]
    details = entry.get("details", entry)
    # The audit must carry the deterministic score and flag the gate intervention.
    assert details.get("suppression_gate_applied") is True
    assert "deterministic_fp_score" in details


def test_deterministic_routing_basis_is_recorded():
    """Every routing decision records that suppression is deterministically gated."""
    result = determine_routing(_state(composite=40.0, deterministic=40.0, llm_fp=40.0))
    routing_entries = [a for a in result["audit_trail"] if a.get("action") == "ROUTING_DECISION_MADE"]
    details = routing_entries[-1].get("details", routing_entries[-1])
    assert details.get("routing_basis") == "deterministic_suppression_gate"
