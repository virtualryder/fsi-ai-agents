"""
Connector framework — base interfaces, errors, and mode resolution (Phase 2).

Why this exists
---------------
Today every agent reaches its systems of record through hardcoded fixture
functions, which is why the accelerator is "Demonstrated" but not "Deployable"
against a real institution. This package makes the integration seam *explicit*:

  - One abstract interface per system class (TMS, core banking, watchlist,
    ACH operator, market data, DMDC/SCRA).
  - Two implementations behind each interface:
      * fixture — deterministic canned data (what the demo runs on today).
      * live    — the real-integration SHAPE (auth via Secrets Manager, an HTTP
                  call to a configured endpoint). It FAILS CLOSED with a clear,
                  actionable error when the integrator has not yet wired the
                  endpoint, rather than silently returning fake data.
  - A factory (`get_connector`) that selects the implementation by
    CONNECTOR_MODE (default "fixture"), so an engagement flips one env var to
    move an agent from demo data to a real system — no code change in the agent.

Agents depend on the ABCs, never on a concrete implementation. That is the
whole point: the agent's deterministic logic and HITL gates are unchanged; only
the data source behind the interface changes between demo, pilot, and prod.
"""
from __future__ import annotations

import abc
import os
from typing import Any, Dict, List, Literal, Optional

Mode = Literal["fixture", "live"]


class ConnectorError(RuntimeError):
    """Base class for all connector errors."""


class ConnectorNotConfiguredError(ConnectorError):
    """
    Raised by a `live` connector when a required endpoint or credential is not
    configured. Fail-closed by design: a regulated workflow must not run on
    silently-faked data because an integration was forgotten.
    """


def resolve_mode(explicit: Optional[str] = None) -> Mode:
    """
    Resolve the connector mode.

    Precedence: explicit argument > CONNECTOR_MODE env var > "fixture".
    Any value other than "live" (case-insensitive) resolves to "fixture" so the
    safe demo path is the default and a typo never accidentally hits a real
    system.
    """
    raw = (explicit or os.getenv("CONNECTOR_MODE", "fixture")).strip().lower()
    return "live" if raw == "live" else "fixture"


class Connector(abc.ABC):
    """Common base. `kind` names the system class; `mode` records the binding."""

    kind: str = "connector"

    def __init__(self, mode: Mode = "fixture") -> None:
        self.mode: Mode = mode

    @abc.abstractmethod
    def health(self) -> Dict[str, Any]:
        """Lightweight readiness probe. Fixtures report ready; live probes the endpoint."""


# ── System-class interfaces ───────────────────────────────────────────────────
# Method surfaces are intentionally small and realistic — the operations the
# agents actually need — so a `live` implementation maps cleanly onto a vendor
# API (Actimize/Verafin TMS, FIS/Fiserv/Jack Henry core, Refinitiv/LexisNexis
# watchlist, a Nacha ACH operator, a market-data feed, DMDC/MilConnect SCRA).

class WatchlistConnector(Connector):
    kind = "watchlist"

    @abc.abstractmethod
    def screen(
        self,
        name: str,
        dob: Optional[str] = None,
        country: Optional[str] = None,
        entity_type: str = "individual",
    ) -> Dict[str, Any]:
        """Screen a party against sanctions/PEP/adverse lists. Returns hits + provenance."""


class TMSConnector(Connector):
    kind = "tms"

    @abc.abstractmethod
    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        """Fetch a transaction-monitoring alert by id."""

    @abc.abstractmethod
    def update_disposition(self, alert_id: str, disposition: str, reason: str) -> Dict[str, Any]:
        """Write back an alert disposition (suppress/escalate/close)."""


class CoreBankingConnector(Connector):
    kind = "core_banking"

    @abc.abstractmethod
    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Fetch a customer/KYC record (risk tier, EDD status, beneficial owners)."""

    @abc.abstractmethod
    def get_transactions(self, customer_id: str, months: int = 12) -> List[Dict[str, Any]]:
        """Fetch transaction history for the customer over a window."""


class ACHOperatorConnector(Connector):
    kind = "ach_operator"

    @abc.abstractmethod
    def lookup_return_code(self, code: str) -> Dict[str, Any]:
        """Resolve a Nacha return code (e.g. R10) to its meaning and handling."""

    @abc.abstractmethod
    def submit_return(self, payment_id: str, return_code: str, reason: str) -> Dict[str, Any]:
        """Submit an ACH return to the operator."""


class MarketDataConnector(Connector):
    kind = "market_data"

    @abc.abstractmethod
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch a current quote for a symbol."""

    @abc.abstractmethod
    def get_trades(self, account_id: str, window_minutes: int = 60) -> List[Dict[str, Any]]:
        """Fetch recent trades for an account over a window (surveillance)."""


class DMDCConnector(Connector):
    kind = "dmdc"

    @abc.abstractmethod
    def check_scra_status(self, identifier: str) -> Dict[str, Any]:
        """Check SCRA/active-duty military status (DMDC/MilConnect) for a debtor."""
