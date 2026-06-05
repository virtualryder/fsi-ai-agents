"""
Integration tests for the alert scoring graph.

Tests verify:
- Suppression fires for obvious false positives (restaurant + structuring)
- Escalation fires for regulatory overrides (PEP flag)
- Escalation fires for shell company + rapid movement
- Pass-through fires for uncertain cases
- Fallback to manual review on customer lookup failure
"""
import pytest
from unittest.mock import patch, MagicMock


RESTAURANT_STRUCTURING_ALERT = {
    "alert_id": "TMS-TEST-001",
    "customer_id": "CUST-101",
    "alert_type": "STRUCTURING",
    "triggered_rule": "CASH_STRUCTURING_10K",
    "severity": "HIGH",
    "amount": 19500.00,
    "currency": "USD",
    "alert_date": "2024-11-14",
    "transaction_ids": ["TXN-1", "TXN-2", "TXN-3"],
    "tms_vendor": "actimize",
    "raw_data": {"transaction_count": 3, "time_window_days": 5},
}

SHELL_COMPANY_ALERT = {
    "alert_id": "TMS-TEST-004",
    "customer_id": "CUST-104",
    "alert_type": "RAPID_MOVEMENT",
    "triggered_rule": "LAYERING_001",
    "severity": "HIGH",
    "amount": 475000.00,
    "currency": "USD",
    "alert_date": "2024-11-14",
    "transaction_ids": ["TXN-30", "TXN-31"],
    "tms_vendor": "actimize",
    "raw_data": {
        "transaction_count": 3,
        "time_window_days": 2,
        "account_dormancy_days": 180,
        "destination_countries": ["PA", "CY", "VG"],
    },
}


class TestScoringGraph:
    """Integration tests — mock LLM, use real fixture data."""

    def _make_mock_llm_response(self, fp_probability: int, recommendation: str) -> MagicMock:
        import json
        payload = {
            "fp_probability": fp_probability,
            "confidence": 0.85,
            "recommendation": recommendation,
            "primary_reason": f"Test reason for {recommendation}",
            "suppression_factors": ["Test factor A", "Test factor B"],
            "pass_through_factors": [],
            "regulatory_override": False,
            "regulatory_override_reason": "",
            "recommended_priority": "LOW" if recommendation == "SUPPRESS" else "MEDIUM",
            "analysis_narrative": "Test narrative for regulatory audit.",
        }
        mock_response = MagicMock()
        mock_response.content = json.dumps(payload)
        return mock_response

    @patch("agent.nodes._llm")
    def test_restaurant_structuring_suppressed(self, mock_llm):
        """Restaurant + structuring + high rule FP rate → SUPPRESS."""
        mock_llm.invoke.return_value = self._make_mock_llm_response(92, "SUPPRESS")

        from agent.graph import build_graph
        app = build_graph()
        result = app.invoke(
            {"raw_alert": RESTAURANT_STRUCTURING_ALERT},
            config={"configurable": {"thread_id": "test-001"}},
        )

        assert result["routing"]["decision"] == "SUPPRESS"
        assert result["queue_action"] == "suppressed"
        assert result["suppression_id"] is not None
        assert result["suppression_review_date"] is not None
        assert result["tms_updated"] is True

    @patch("agent.nodes._llm")
    def test_shell_company_escalated(self, mock_llm):
        """Shell company + rapid movement + high-risk geography → ESCALATE."""
        mock_llm.invoke.return_value = self._make_mock_llm_response(10, "ESCALATE")

        from agent.graph import build_graph
        app = build_graph()
        result = app.invoke(
            {"raw_alert": SHELL_COMPANY_ALERT},
            config={"configurable": {"thread_id": "test-004"}},
        )

        assert result["routing"]["decision"] == "ESCALATE"
        assert result["queue_action"] == "escalated"
        assert result["tms_updated"] is True

    @patch("agent.nodes._llm")
    def test_pep_forces_escalation(self, mock_llm):
        """PEP flag on customer must force ESCALATE regardless of FP score."""
        # LLM recommends suppression but PEP override should win
        mock_llm.invoke.return_value = self._make_mock_llm_response(90, "SUPPRESS")

        pep_alert = {**RESTAURANT_STRUCTURING_ALERT, "customer_id": "CUST-PEP-TEST"}

        # Patch customer lookup to return a PEP customer
        pep_customer = {
            "customer_id": "CUST-PEP-TEST",
            "full_name": "Test PEP Customer",
            "risk_tier": "VERY_HIGH",
            "business_type": "individual_consumer",
            "account_age_days": 365,
            "expected_monthly_cash_volume": 5000.0,
            "expected_monthly_wire_volume": 0.0,
            "open_investigation_count": 0,
            "prior_sars_filed": 0,
            "prior_ctrs_filed": 0,
            "pep_flag": True,    # ← PEP
            "edd_active": True,
            "beneficial_owners": [],
            "historical_fp_rate": 0.5,
        }

        with patch("agent.nodes.get_customer_summary", return_value=pep_customer):
            from agent.graph import build_graph
            app = build_graph()
            result = app.invoke(
                {"raw_alert": pep_alert},
                config={"configurable": {"thread_id": "test-pep"}},
            )

        assert result["routing"]["decision"] == "ESCALATE"
        assert result["routing"]["regulatory_override"] is True
        assert "PEP" in result["routing"]["regulatory_override_reason"]

    @patch("agent.nodes._llm")
    def test_pass_through_uncertain_case(self, mock_llm):
        """Uncertain case (FP ~45%) → PASS_THROUGH at MEDIUM priority."""
        mock_llm.invoke.return_value = self._make_mock_llm_response(45, "PASS_THROUGH")

        from agent.graph import build_graph
        app = build_graph()
        result = app.invoke(
            {"raw_alert": RESTAURANT_STRUCTURING_ALERT},
            config={"configurable": {"thread_id": "test-pt"}},
        )

        assert result["routing"]["decision"] == "PASS_THROUGH"
        assert result["queue_action"] == "queued"
        assert result["downstream_queue_notified"] is True

    @patch("agent.nodes.get_customer_summary", return_value=None)
    @patch("agent.nodes._llm")
    def test_customer_not_found_manual_fallback(self, mock_llm, mock_customer):
        """Customer lookup failure → fallback to manual review (PASS_THROUGH HIGH)."""
        from agent.graph import build_graph
        app = build_graph()
        result = app.invoke(
            {"raw_alert": RESTAURANT_STRUCTURING_ALERT},
            config={"configurable": {"thread_id": "test-fallback"}},
        )

        assert result["fallback_to_manual"] is True
        assert result["routing"]["decision"] == "PASS_THROUGH"
        assert result["routing"]["recommended_priority"] == "HIGH"

    @patch("agent.nodes._llm")
    def test_audit_trail_populated(self, mock_llm):
        """Audit trail must contain entries from all executed nodes."""
        mock_llm.invoke.return_value = self._make_mock_llm_response(88, "SUPPRESS")

        from agent.graph import build_graph
        app = build_graph()
        result = app.invoke(
            {"raw_alert": RESTAURANT_STRUCTURING_ALERT},
            config={"configurable": {"thread_id": "test-audit"}},
        )

        trail = result.get("audit_trail", [])
        actions = {entry["action"] for entry in trail}
        assert "ALERT_INGESTED" in actions
        assert "CUSTOMER_CONTEXT_LOADED" in actions
        assert "LLM_ANALYSIS_COMPLETE" in actions
        assert "SCORING_FINALIZED" in actions

    @patch("agent.nodes._llm")
    def test_processing_time_recorded(self, mock_llm):
        """Processing time should be measured and stored in ms."""
        mock_llm.invoke.return_value = self._make_mock_llm_response(88, "SUPPRESS")

        from agent.graph import build_graph
        app = build_graph()
        result = app.invoke(
            {"raw_alert": RESTAURANT_STRUCTURING_ALERT},
            config={"configurable": {"thread_id": "test-timing"}},
        )

        assert result.get("processing_time_ms") is not None
        assert isinstance(result["processing_time_ms"], int)
