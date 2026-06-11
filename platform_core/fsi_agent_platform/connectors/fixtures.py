"""
Fixture connector implementations (Phase 2).

Deterministic, in-memory data — the safe default the demo runs on. No network,
no credentials. Each method returns data shaped exactly like the ABC contract so
an agent written against the interface behaves identically whether it is bound to
a fixture or a live connector.

These fixtures are intentionally small and illustrative. An engagement replaces
the BINDING (CONNECTOR_MODE=live), not the agent code.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import (
    ACHOperatorConnector,
    CoreBankingConnector,
    DMDCConnector,
    MarketDataConnector,
    TMSConnector,
    WatchlistConnector,
)

# A tiny sanctions/PEP list used only to demonstrate a hit vs. no-hit path.
_DEMO_SANCTIONS = {
    "ivan petrov": {"list": "OFAC_SDN", "program": "RUSSIA-EO14024", "match_score": 0.97},
    "globex shell ltd": {"list": "OFAC_SDN", "program": "NPWMD", "match_score": 0.91},
}
_DEMO_PEPS = {"maria gonzalez": {"list": "PEP", "role": "Deputy Finance Minister", "match_score": 0.88}}


class FixtureWatchlist(WatchlistConnector):
    def health(self) -> Dict[str, Any]:
        return {"kind": self.kind, "mode": self.mode, "ready": True, "source": "fixture"}

    def screen(self, name, dob=None, country=None, entity_type="individual") -> Dict[str, Any]:
        key = (name or "").strip().lower()
        hits: List[Dict[str, Any]] = []
        if key in _DEMO_SANCTIONS:
            hits.append({"type": "SANCTIONS", **_DEMO_SANCTIONS[key]})
        if key in _DEMO_PEPS:
            hits.append({"type": "PEP", **_DEMO_PEPS[key]})
        return {
            "query": {"name": name, "dob": dob, "country": country, "entity_type": entity_type},
            "hit": bool(hits),
            "hits": hits,
            "source": "fixture",
            "provider": "demo-watchlist",
        }


class FixtureTMS(TMSConnector):
    _ALERTS = {
        "ALERT-1001": {"alert_id": "ALERT-1001", "alert_type": "STRUCTURING", "amount": 9500.0,
                        "customer_id": "CUST-001", "triggered_rule": "CASH-SUB-10K"},
    }

    def health(self) -> Dict[str, Any]:
        return {"kind": self.kind, "mode": self.mode, "ready": True, "source": "fixture"}

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        return dict(self._ALERTS.get(alert_id, {"alert_id": alert_id, "alert_type": "UNKNOWN", "amount": 0.0}))

    def update_disposition(self, alert_id: str, disposition: str, reason: str) -> Dict[str, Any]:
        return {"alert_id": alert_id, "disposition": disposition, "reason": reason,
                "accepted": True, "source": "fixture"}


class FixtureCoreBanking(CoreBankingConnector):
    _CUSTOMERS = {
        "CUST-001": {"customer_id": "CUST-001", "full_name": "Acme Imports LLC", "risk_tier": "MEDIUM",
                      "business_type": "import_export", "edd_status": "current", "beneficial_owners": []},
    }

    def health(self) -> Dict[str, Any]:
        return {"kind": self.kind, "mode": self.mode, "ready": True, "source": "fixture"}

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        return dict(self._CUSTOMERS.get(customer_id,
                    {"customer_id": customer_id, "full_name": "Unknown", "risk_tier": "MEDIUM"}))

    def get_transactions(self, customer_id: str, months: int = 12) -> List[Dict[str, Any]]:
        return [
            {"txn_id": "T-1", "customer_id": customer_id, "amount": 9500.0, "type": "cash_deposit",
             "counterparty": "self", "date": "2026-05-01"},
            {"txn_id": "T-2", "customer_id": customer_id, "amount": 9800.0, "type": "cash_deposit",
             "counterparty": "self", "date": "2026-05-02"},
        ]


class FixtureACHOperator(ACHOperatorConnector):
    _RETURN_CODES = {
        "R10": {"code": "R10", "title": "Customer Advises Not Authorized",
                 "unauthorized": True, "consumer": True, "handling": "Reg E dispute"},
        "R01": {"code": "R01", "title": "Insufficient Funds", "unauthorized": False, "handling": "retry"},
    }

    def health(self) -> Dict[str, Any]:
        return {"kind": self.kind, "mode": self.mode, "ready": True, "source": "fixture"}

    def lookup_return_code(self, code: str) -> Dict[str, Any]:
        return dict(self._RETURN_CODES.get((code or "").upper(),
                    {"code": code, "title": "Unknown", "unauthorized": False, "handling": "manual_review"}))

    def submit_return(self, payment_id: str, return_code: str, reason: str) -> Dict[str, Any]:
        return {"payment_id": payment_id, "return_code": return_code, "reason": reason,
                "accepted": True, "source": "fixture"}


class FixtureMarketData(MarketDataConnector):
    def health(self) -> Dict[str, Any]:
        return {"kind": self.kind, "mode": self.mode, "ready": True, "source": "fixture"}

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return {"symbol": (symbol or "").upper(), "bid": 100.0, "ask": 100.05, "last": 100.02,
                "source": "fixture"}

    def get_trades(self, account_id: str, window_minutes: int = 60) -> List[Dict[str, Any]]:
        return [
            {"trade_id": "X-1", "account_id": account_id, "symbol": "ACME", "side": "BUY",
             "qty": 1000, "price": 100.0, "ts": "2026-06-01T14:30:00Z"},
            {"trade_id": "X-2", "account_id": account_id, "symbol": "ACME", "side": "SELL",
             "qty": 1000, "price": 100.40, "ts": "2026-06-01T14:31:00Z"},
        ]


class FixtureDMDC(DMDCConnector):
    # One demo identifier flagged as active-duty (SCRA protections apply).
    _ACTIVE_DUTY = {"SCRA-ACTIVE": True}

    def health(self) -> Dict[str, Any]:
        return {"kind": self.kind, "mode": self.mode, "ready": True, "source": "fixture"}

    def check_scra_status(self, identifier: str) -> Dict[str, Any]:
        active = bool(self._ACTIVE_DUTY.get((identifier or "").upper(), False))
        return {"identifier": identifier, "active_duty": active,
                "protections": ["6% interest cap", "stay of proceedings"] if active else [],
                "source": "fixture"}
