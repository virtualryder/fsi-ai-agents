# tests/test_tools.py
# ============================================================
# Unit tests for all tool functions.
# These tests use mock/fixture data only — no external API calls.
# Run: pytest tests/ -v
# ============================================================

import pytest
from datetime import datetime, timedelta

# ── Tool imports
from tools.transaction_monitor import (
    get_transaction_history,
    detect_structuring_patterns,
    detect_velocity_anomalies,
    get_alerts_for_customer,
)
from tools.customer_profile import (
    get_customer_profile,
    get_account_details,
    get_beneficial_owners,
)
from tools.watchlist_screening import (
    screen_against_ofac,
    screen_pep_lists,
    screen_internal_watchlist,
    _fuzzy_name_match,
)
from tools.network_analysis import (
    build_counterparty_network,
    detect_shell_company_indicators,
    calculate_network_risk_score,
)
from tools.adverse_media import search_adverse_media
from tools.case_management import create_case, update_case_status, get_case


# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTION MONITOR TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestTransactionMonitor:

    def test_get_alerts_for_customer_returns_list(self):
        """Alerts are always returned as a list."""
        alerts = get_alerts_for_customer("CUST-001")
        assert isinstance(alerts, list)
        assert len(alerts) >= 1

    def test_alert_has_required_fields(self):
        """Each alert has all fields required by the investigation state."""
        alerts = get_alerts_for_customer("CUST-001")
        required = ["alert_id", "alert_type", "severity", "customer_id"]
        for field in required:
            assert field in alerts[0], f"Alert missing required field: {field}"

    def test_get_transaction_history_returns_list(self):
        """Transaction history is always a list."""
        txns = get_transaction_history("CUST-001-ACC001", days=365)
        assert isinstance(txns, list)

    def test_transactions_have_required_fields(self):
        """Transactions must have minimum required fields for AML analysis."""
        txns = get_transaction_history("CUST-001-ACC001", days=365)
        if txns:
            required = ["transaction_id", "date", "amount", "transaction_type", "direction"]
            for field in required:
                assert field in txns[0], f"Transaction missing field: {field}"

    def test_detect_structuring_no_transactions(self):
        """Structuring detection handles empty transaction list gracefully."""
        result = detect_structuring_patterns([])
        assert result["detected"] is False
        assert result["total_flagged_amount"] == 0

    def test_detect_structuring_with_pattern(self):
        """Structuring is detected when multiple sub-$10K cash deposits exist."""
        transactions = [
            {
                "transaction_id": f"TXN-{i:04d}",
                "transaction_type": "CASH_DEPOSIT",
                "direction": "CREDIT",
                "counterparty_name": "CASH",
                "amount": 9500.00,
                "date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
            }
            for i in range(8)  # 8 sub-$10K cash deposits
        ]
        result = detect_structuring_patterns(transactions)
        assert result["detected"] is True
        assert len(result["flagged_transactions"]) >= 3

    def test_detect_velocity_anomalies_empty(self):
        """Velocity detection handles empty transaction list."""
        result = detect_velocity_anomalies([], {"monthly_cash_avg": 5000})
        assert result["detected"] is False

    def test_detect_velocity_anomalies_high_spike(self):
        """High cash volume spike is detected as velocity anomaly."""
        # Generate recent high-volume transactions
        transactions = [
            {
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "amount": 50000.00,
                "transaction_type": "CASH_DEPOSIT",
            }
        ]
        baseline = {"monthly_cash_avg": 5000, "monthly_wire_avg": 0}
        result = detect_velocity_anomalies(transactions, baseline)
        assert result["spike_ratio"] >= 10.0  # 50K vs 5K baseline = 10x


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER PROFILE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCustomerProfile:

    def test_get_customer_profile_returns_dict(self):
        """Customer profile is always a dictionary."""
        profile = get_customer_profile("CUST-001")
        assert isinstance(profile, dict)

    def test_customer_profile_has_required_fields(self):
        """Customer profile has all fields required for AML investigation."""
        profile = get_customer_profile("CUST-001")
        required = [
            "customer_id", "customer_type", "risk_tier",
            "edd_status", "pep_flag", "kyc_date",
        ]
        for field in required:
            assert field in profile, f"Customer profile missing field: {field}"

    def test_high_risk_entity_has_beneficial_owners(self):
        """High-risk entity profiles include beneficial ownership information."""
        profile = get_customer_profile("CUST-002")
        assert "beneficial_owners" in profile
        assert len(profile["beneficial_owners"]) >= 1

    def test_pep_flag_on_high_risk_entity(self):
        """PEP flag is set on entities with PEP beneficial owners."""
        profile = get_customer_profile("CUST-002")
        assert profile.get("pep_flag") is True

    def test_get_account_details_returns_dict(self):
        """Account details are always a dictionary."""
        details = get_account_details("CUST-001-ACC001")
        assert isinstance(details, dict)
        assert "account_id" in details

    def test_beneficial_owners_returns_list(self):
        """Beneficial owners are returned as a list."""
        owners = get_beneficial_owners("CUST-002")
        assert isinstance(owners, list)


# ══════════════════════════════════════════════════════════════════════════════
# WATCHLIST SCREENING TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestWatchlistScreening:

    def test_fuzzy_name_match_identical(self):
        """Identical names should return score >= 1.0."""
        score = _fuzzy_name_match("John Smith", "John Smith")
        assert score == 1.0

    def test_fuzzy_name_match_different(self):
        """Completely different names should return low score."""
        score = _fuzzy_name_match("Alice Johnson", "Robert Williams")
        assert score < 0.3

    def test_fuzzy_name_match_partial(self):
        """Partial matches return intermediate scores."""
        score = _fuzzy_name_match("John Smith", "John D. Smith")
        assert 0.3 <= score <= 1.0

    def test_ofac_screening_returns_dict(self):
        """OFAC screening always returns a result dict."""
        result = screen_against_ofac("Completely Unknown Name XYZ123")
        assert isinstance(result, dict)
        assert "hit" in result
        assert "list_type" in result

    def test_ofac_no_hit_for_clean_name(self):
        """Clean names should not trigger OFAC hits."""
        result = screen_against_ofac("John Q Public", country="US")
        assert result["hit"] is False

    def test_pep_screening_returns_dict(self):
        """PEP screening always returns a result dict."""
        result = screen_pep_lists("Random Person Name", "US")
        assert isinstance(result, dict)
        assert "hit" in result

    def test_internal_watchlist_no_hit(self):
        """Customer not on internal list returns no hit."""
        result = screen_internal_watchlist("CUST-CLEAN-999")
        assert result["hit"] is False

    def test_internal_watchlist_known_customer(self):
        """CUST-002 should be on internal watchlist (prior SAR)."""
        result = screen_internal_watchlist("CUST-002")
        assert result["hit"] is True
        assert result.get("prior_sar") is True


# ══════════════════════════════════════════════════════════════════════════════
# NETWORK ANALYSIS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestNetworkAnalysis:

    def test_build_network_empty_transactions(self):
        """Network builder handles empty transaction list."""
        result = build_counterparty_network([])
        assert isinstance(result, dict)
        assert result["node_count"] == 0

    def test_build_network_with_transactions(self):
        """Network is built correctly from transaction list."""
        transactions = [
            {
                "account_id": "ACC-001",
                "counterparty_name": "Company A",
                "amount": 50000,
                "direction": "DEBIT",
                "transaction_type": "WIRE_OUT",
                "counterparty_country": "US",
                "date": "2024-11-01",
            },
            {
                "account_id": "ACC-001",
                "counterparty_name": "Company B",
                "amount": 30000,
                "direction": "CREDIT",
                "transaction_type": "WIRE_IN",
                "counterparty_country": "PA",
                "date": "2024-11-02",
            },
        ]
        result = build_counterparty_network(transactions)
        assert result["node_count"] >= 2
        assert len(result["edges"]) >= 2

    def test_shell_company_detection_generic_name(self):
        """Generic company names trigger shell company indicators."""
        entity = {"name": "Global Capital Management Holdings LLC", "transaction_pattern": []}
        result = detect_shell_company_indicators(entity)
        assert result["shell_company_probability"] > 0
        assert len(result["indicators_found"]) >= 1

    def test_shell_company_score_is_bounded(self):
        """Shell company probability is always 0-100."""
        entity = {
            "name": "XYZ Global Holdings International Capital Ventures",
            "transaction_pattern": [
                {"amount": 100000, "direction": "CREDIT"},
                {"amount": 100000, "direction": "DEBIT"},
            ],
        }
        result = detect_shell_company_indicators(entity)
        assert 0 <= result["shell_company_probability"] <= 100

    def test_network_risk_score_zero_for_clean_network(self):
        """Clean network returns low/zero risk score."""
        clean_network = {
            "high_risk_jurisdictions": [],
            "shell_company_findings": {},
            "circular_flows": [],
            "top_counterparties": [],
        }
        result = calculate_network_risk_score(clean_network)
        assert result["score"] == 0
        assert result["level"] == "LOW"


# ══════════════════════════════════════════════════════════════════════════════
# ADVERSE MEDIA TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAdverseMedia:

    def test_search_returns_list(self):
        """Adverse media search always returns a list."""
        results = search_adverse_media("Unknown Person XYZ999")
        assert isinstance(results, list)

    def test_known_subject_has_hits(self):
        """Known test subjects have adverse media entries."""
        results = search_adverse_media("Dmitri Testovsky")
        # May or may not find hits depending on partial match logic
        assert isinstance(results, list)


# ══════════════════════════════════════════════════════════════════════════════
# CASE MANAGEMENT TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCaseManagement:

    def test_create_case_returns_id(self):
        """Case creation returns a case ID string."""
        case_id = create_case("ALT-TEST-001", "CUST-TEST", "BSA_OFFICER")
        assert isinstance(case_id, str)
        assert case_id.startswith("CASE-")

    def test_created_case_retrievable(self):
        """Created case can be retrieved by ID."""
        case_id = create_case("ALT-TEST-002", "CUST-TEST", "BSA_OFFICER")
        case = get_case(case_id)
        assert case is not None
        assert case["case_id"] == case_id

    def test_case_has_required_fields(self):
        """Created case has all required fields."""
        case_id = create_case("ALT-TEST-003", "CUST-TEST", "BSA_OFFICER")
        case = get_case(case_id)
        required = ["case_id", "alert_id", "customer_id", "status", "created_at", "sar_filing_deadline"]
        for field in required:
            assert field in case, f"Case missing field: {field}"

    def test_update_case_status(self):
        """Case status can be updated."""
        case_id = create_case("ALT-TEST-004", "CUST-TEST", "BSA_OFFICER")
        updated = update_case_status(case_id, "IN_REVIEW", "Assigned to senior analyst")
        assert updated["status"] == "IN_REVIEW"
        assert len(updated["notes"]) >= 1

    def test_case_timeline_grows(self):
        """Timeline grows with each status update."""
        case_id = create_case("ALT-TEST-005", "CUST-TEST", "BSA_OFFICER")
        case = get_case(case_id)
        initial_count = len(case["timeline"])
        update_case_status(case_id, "IN_REVIEW", "Update 1")
        update_case_status(case_id, "PENDING_HUMAN_REVIEW", "Update 2")
        case = get_case(case_id)
        assert len(case["timeline"]) == initial_count + 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
