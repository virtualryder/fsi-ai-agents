"""
Connector factory (Phase 2).

`get_connector(kind, mode=None)` returns the fixture or live implementation for
a system class. Agents call this instead of importing a hardcoded fixture, so
moving from demo data to a real system is a CONNECTOR_MODE change, not a code
change.

    from fsi_agent_platform.connectors import get_connector
    wl = get_connector("watchlist")          # CONNECTOR_MODE-driven (default fixture)
    result = wl.screen("Ivan Petrov", country="RU")
"""
from __future__ import annotations

from typing import Dict, Optional, Type

from . import fixtures as _fx
from . import live as _lv
from .base import Connector, ConnectorError, Mode, resolve_mode

# kind -> (fixture_impl, live_impl)
_REGISTRY: Dict[str, Dict[str, Type[Connector]]] = {
    "watchlist":    {"fixture": _fx.FixtureWatchlist,   "live": _lv.LiveWatchlist},
    "tms":          {"fixture": _fx.FixtureTMS,         "live": _lv.LiveTMS},
    "core_banking": {"fixture": _fx.FixtureCoreBanking, "live": _lv.LiveCoreBanking},
    "ach_operator": {"fixture": _fx.FixtureACHOperator, "live": _lv.LiveACHOperator},
    "market_data":  {"fixture": _fx.FixtureMarketData,  "live": _lv.LiveMarketData},
    "dmdc":         {"fixture": _fx.FixtureDMDC,        "live": _lv.LiveDMDC},
}


def available_kinds() -> list[str]:
    """Return the registered connector kinds."""
    return sorted(_REGISTRY)


def get_connector(kind: str, mode: Optional[str] = None) -> Connector:
    """
    Return a connector instance for `kind`.

    mode precedence: explicit arg > CONNECTOR_MODE env > "fixture".
    Raises ConnectorError for an unknown kind.
    """
    if kind not in _REGISTRY:
        raise ConnectorError(
            f"unknown connector kind {kind!r}; available: {', '.join(available_kinds())}"
        )
    resolved: Mode = resolve_mode(mode)
    impl = _REGISTRY[kind][resolved]
    return impl(mode=resolved)
