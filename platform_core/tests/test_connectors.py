"""
Connector framework tests (Phase 2) — run in CI without network or AWS.

They prove the three properties that make the abstraction safe:
  1. Fixture is the default and every fixture honors its interface contract.
  2. Mode resolution is safe (default fixture; only "live" opts in).
  3. Live connectors FAIL CLOSED when unconfigured — never silent fake data.
"""
from __future__ import annotations

import pytest

from fsi_agent_platform.connectors import (
    ConnectorError,
    ConnectorNotConfiguredError,
    available_kinds,
    get_connector,
    resolve_mode,
)
from fsi_agent_platform.connectors.base import (
    ACHOperatorConnector,
    CoreBankingConnector,
    DMDCConnector,
    MarketDataConnector,
    TMSConnector,
    WatchlistConnector,
)

ALL_KINDS = ["ach_operator", "core_banking", "dmdc", "market_data", "tms", "watchlist"]


# ── mode resolution ───────────────────────────────────────────────────────────
class TestModeResolution:
    def test_default_is_fixture(self, monkeypatch):
        monkeypatch.delenv("CONNECTOR_MODE", raising=False)
        assert resolve_mode() == "fixture"

    def test_env_live_opts_in(self, monkeypatch):
        monkeypatch.setenv("CONNECTOR_MODE", "live")
        assert resolve_mode() == "live"

    def test_typo_falls_back_to_fixture(self, monkeypatch):
        monkeypatch.setenv("CONNECTOR_MODE", "liev")
        assert resolve_mode() == "fixture"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("CONNECTOR_MODE", "live")
        assert resolve_mode("fixture") == "fixture"


# ── registry / factory ────────────────────────────────────────────────────────
class TestFactory:
    def test_all_kinds_registered(self):
        assert available_kinds() == ALL_KINDS

    def test_unknown_kind_raises(self):
        with pytest.raises(ConnectorError):
            get_connector("nope")

    def test_default_mode_is_fixture(self, monkeypatch):
        monkeypatch.delenv("CONNECTOR_MODE", raising=False)
        assert get_connector("watchlist").mode == "fixture"

    @pytest.mark.parametrize("kind,iface", [
        ("watchlist", WatchlistConnector),
        ("tms", TMSConnector),
        ("core_banking", CoreBankingConnector),
        ("ach_operator", ACHOperatorConnector),
        ("market_data", MarketDataConnector),
        ("dmdc", DMDCConnector),
    ])
    def test_fixture_implements_interface(self, kind, iface, monkeypatch):
        monkeypatch.delenv("CONNECTOR_MODE", raising=False)
        c = get_connector(kind)
        assert isinstance(c, iface)
        assert c.health()["ready"] is True and c.health()["source"] == "fixture"


# ── fixture behavior contracts ────────────────────────────────────────────────
class TestFixtureContracts:
    def test_watchlist_hit_and_miss(self):
        wl = get_connector("watchlist", mode="fixture")
        assert wl.screen("Ivan Petrov")["hit"] is True
        clean = wl.screen("Jane Q. Public")
        assert clean["hit"] is False and clean["hits"] == []

    def test_tms_alert_and_disposition(self):
        tms = get_connector("tms", mode="fixture")
        assert tms.get_alert("ALERT-1001")["alert_type"] == "STRUCTURING"
        assert tms.update_disposition("ALERT-1001", "ESCALATE", "PEP")["accepted"] is True

    def test_core_banking_customer_and_txns(self):
        cb = get_connector("core_banking", mode="fixture")
        assert cb.get_customer("CUST-001")["risk_tier"] == "MEDIUM"
        assert len(cb.get_transactions("CUST-001", months=12)) >= 1

    def test_ach_return_codes(self):
        ach = get_connector("ach_operator", mode="fixture")
        assert ach.lookup_return_code("R10")["unauthorized"] is True
        assert ach.lookup_return_code("R01")["unauthorized"] is False

    def test_market_data(self):
        md = get_connector("market_data", mode="fixture")
        assert md.get_quote("ACME")["symbol"] == "ACME"
        assert len(md.get_trades("ACC-1")) >= 1

    def test_dmdc_scra(self):
        dmdc = get_connector("dmdc", mode="fixture")
        assert dmdc.check_scra_status("SCRA-ACTIVE")["active_duty"] is True
        assert dmdc.check_scra_status("civilian-123")["active_duty"] is False


# ── live connectors fail closed when unconfigured ─────────────────────────────
class TestLiveFailsClosed:
    @pytest.fixture(autouse=True)
    def _clear_endpoints(self, monkeypatch):
        for var in ["WATCHLIST_API_URL", "TMS_API_URL", "CORE_BANKING_API_URL",
                    "ACH_OPERATOR_API_URL", "MARKET_DATA_API_URL", "DMDC_API_URL"]:
            monkeypatch.delenv(var, raising=False)

    def test_live_watchlist_unconfigured_raises(self):
        wl = get_connector("watchlist", mode="live")
        assert wl.mode == "live"
        with pytest.raises(ConnectorNotConfiguredError):
            wl.screen("Ivan Petrov")

    def test_live_tms_unconfigured_raises(self):
        with pytest.raises(ConnectorNotConfiguredError):
            get_connector("tms", mode="live").get_alert("ALERT-1001")

    def test_live_health_probe_fails_closed(self):
        with pytest.raises(ConnectorNotConfiguredError):
            get_connector("dmdc", mode="live").health()

    def test_error_message_names_the_env_var(self):
        with pytest.raises(ConnectorNotConfiguredError) as ei:
            get_connector("core_banking", mode="live").get_customer("CUST-001")
        assert "CORE_BANKING_API_URL" in str(ei.value)
