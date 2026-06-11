"""
Live (stub-real) connector implementations (Phase 2).

These show the SHAPE of a real integration without shipping a live binding:

  * The endpoint base URL comes from an env var (e.g. WATCHLIST_API_URL).
  * The credential comes from Secrets Manager via the platform secrets module
    (never from a literal in code).
  * The call is a plain HTTPS request to the configured endpoint.

If the endpoint is not configured, the connector FAILS CLOSED with
ConnectorNotConfiguredError naming the exact env var to set — a regulated
workflow must never silently run on fake data because an integration was
forgotten. This is the seam an engagement implements per the customer's vendor
(Actimize/Verafin, FIS/Fiserv/Jack Henry, Refinitiv/LexisNexis, the ACH
operator, the market-data feed, DMDC/MilConnect).

The HTTP plumbing is deliberately thin and uncoupled from any one vendor; an
implementer maps request/response to their API in `_request` or per method.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .base import (
    ACHOperatorConnector,
    Connector,
    ConnectorNotConfiguredError,
    CoreBankingConnector,
    DMDCConnector,
    MarketDataConnector,
    TMSConnector,
    WatchlistConnector,
)


class _LiveBase(Connector):
    """Shared config resolution + a thin HTTPS helper for live connectors."""

    #: env var holding the base URL for this connector's endpoint
    url_env: str = ""
    #: Secrets Manager key (and env fallback) holding the API credential
    secret_key: str = ""

    def _base_url(self) -> str:
        url = os.getenv(self.url_env, "").strip()
        if not url:
            raise ConnectorNotConfiguredError(
                f"{self.kind} live connector is not configured: set {self.url_env} to the "
                f"vendor endpoint base URL (and provide credential {self.secret_key!r} via "
                f"Secrets Manager). Until then, run with CONNECTOR_MODE=fixture."
            )
        return url.rstrip("/")

    def _credential(self) -> Optional[str]:
        # Lazy import so the connector package has no hard dependency on the
        # rest of the platform when only fixtures are used.
        from fsi_agent_platform import secrets

        return secrets.get_secret(self.secret_key) if self.secret_key else None

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base = self._base_url()              # raises ConnectorNotConfiguredError if unset
        token = self._credential()
        try:
            import requests  # lazy — only needed on the live path
        except Exception as exc:  # pragma: no cover - environment without requests
            raise ConnectorNotConfiguredError(
                f"{self.kind} live connector needs the 'requests' package installed."
            ) from exc
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.request(method, f"{base}{path}", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def health(self) -> Dict[str, Any]:
        # Resolving the base URL is the readiness check: configured or fail-closed.
        return {"kind": self.kind, "mode": self.mode, "ready": True,
                "source": "live", "endpoint": self._base_url()}


class LiveWatchlist(_LiveBase, WatchlistConnector):
    kind = "watchlist"
    url_env = "WATCHLIST_API_URL"
    secret_key = "WATCHLIST_API_KEY"

    def screen(self, name, dob=None, country=None, entity_type="individual") -> Dict[str, Any]:
        return self._request("POST", "/screen", {
            "name": name, "dob": dob, "country": country, "entity_type": entity_type,
        })


class LiveTMS(_LiveBase, TMSConnector):
    kind = "tms"
    url_env = "TMS_API_URL"
    secret_key = "TMS_API_KEY"

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/alerts/{alert_id}")

    def update_disposition(self, alert_id: str, disposition: str, reason: str) -> Dict[str, Any]:
        return self._request("POST", f"/alerts/{alert_id}/disposition",
                             {"disposition": disposition, "reason": reason})


class LiveCoreBanking(_LiveBase, CoreBankingConnector):
    kind = "core_banking"
    url_env = "CORE_BANKING_API_URL"
    secret_key = "CORE_BANKING_API_KEY"

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/customers/{customer_id}")

    def get_transactions(self, customer_id: str, months: int = 12) -> List[Dict[str, Any]]:
        out = self._request("GET", f"/customers/{customer_id}/transactions?months={months}")
        return out.get("transactions", []) if isinstance(out, dict) else out


class LiveACHOperator(_LiveBase, ACHOperatorConnector):
    kind = "ach_operator"
    url_env = "ACH_OPERATOR_API_URL"
    secret_key = "ACH_OPERATOR_API_KEY"

    def lookup_return_code(self, code: str) -> Dict[str, Any]:
        return self._request("GET", f"/return-codes/{code}")

    def submit_return(self, payment_id: str, return_code: str, reason: str) -> Dict[str, Any]:
        return self._request("POST", f"/payments/{payment_id}/return",
                             {"return_code": return_code, "reason": reason})


class LiveMarketData(_LiveBase, MarketDataConnector):
    kind = "market_data"
    url_env = "MARKET_DATA_API_URL"
    secret_key = "MARKET_DATA_API_KEY"

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", f"/quote/{symbol}")

    def get_trades(self, account_id: str, window_minutes: int = 60) -> List[Dict[str, Any]]:
        out = self._request("GET", f"/accounts/{account_id}/trades?window={window_minutes}")
        return out.get("trades", []) if isinstance(out, dict) else out


class LiveDMDC(_LiveBase, DMDCConnector):
    kind = "dmdc"
    url_env = "DMDC_API_URL"
    secret_key = "DMDC_API_KEY"

    def check_scra_status(self, identifier: str) -> Dict[str, Any]:
        return self._request("POST", "/scra/status", {"identifier": identifier})
