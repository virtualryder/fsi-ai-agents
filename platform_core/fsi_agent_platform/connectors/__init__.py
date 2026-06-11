"""
Connector framework for the FSI AI Agent Suite (Phase 2).

Public API:
    get_connector(kind, mode=None)  -> Connector
    available_kinds()               -> list[str]
    resolve_mode(explicit=None)     -> "fixture" | "live"

Interfaces (depend on these, not on concrete impls):
    WatchlistConnector, TMSConnector, CoreBankingConnector,
    ACHOperatorConnector, MarketDataConnector, DMDCConnector

Errors:
    ConnectorError, ConnectorNotConfiguredError
"""
from .base import (
    ACHOperatorConnector,
    Connector,
    ConnectorError,
    ConnectorNotConfiguredError,
    CoreBankingConnector,
    DMDCConnector,
    MarketDataConnector,
    Mode,
    TMSConnector,
    WatchlistConnector,
    resolve_mode,
)
from .factory import available_kinds, get_connector

__all__ = [
    "get_connector",
    "available_kinds",
    "resolve_mode",
    "Connector",
    "Mode",
    "ConnectorError",
    "ConnectorNotConfiguredError",
    "WatchlistConnector",
    "TMSConnector",
    "CoreBankingConnector",
    "ACHOperatorConnector",
    "MarketDataConnector",
    "DMDCConnector",
]
