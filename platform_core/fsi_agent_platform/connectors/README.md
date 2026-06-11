# Connector Framework

Gets the suite off hardcoded fixtures. Agents depend on an **interface**; a single
env var (`CONNECTOR_MODE`) binds that interface to **fixture** data (demo) or a
**live** vendor endpoint (pilot/prod). The agent's deterministic logic and HITL
gates never change — only the data source behind the interface does.

## Why

Today each agent imports a hardcoded fixture function, so it is *Demonstrated*
but not *Deployable* against a real institution. This framework makes the
integration seam explicit and testable, and makes "go live" a configuration
change instead of an agent rewrite.

## Interfaces

| Kind | Interface | Real-world binding (per engagement) |
|---|---|---|
| `watchlist` | `WatchlistConnector` | Refinitiv World-Check, LexisNexis, Dow Jones |
| `tms` | `TMSConnector` | Actimize, Verafin, NICE, Oracle Mantas |
| `core_banking` | `CoreBankingConnector` | FIS, Fiserv, Jack Henry |
| `ach_operator` | `ACHOperatorConnector` | Nacha ACH operator / processor |
| `market_data` | `MarketDataConnector` | Exchange / market-data feed |
| `dmdc` | `DMDCConnector` | DMDC / MilConnect (SCRA status) |

## Usage

```python
from fsi_agent_platform.connectors import get_connector

# Mode comes from CONNECTOR_MODE (default "fixture"); pass mode= to force one.
wl = get_connector("watchlist")
result = wl.screen("Ivan Petrov", country="RU")
if result["hit"]:
    ...  # deterministic escalation logic in the agent — unchanged
```

## Modes

- **`CONNECTOR_MODE=fixture`** (default) — deterministic canned data. No network,
  no credentials. The safe demo path; a typo in the env value also resolves here.
- **`CONNECTOR_MODE=live`** — calls the configured vendor endpoint. Each live
  connector reads its base URL from an env var and its credential from Secrets
  Manager (via `fsi_agent_platform.secrets`). If the endpoint is **not**
  configured it raises `ConnectorNotConfiguredError` naming the exact env var —
  it never silently returns fake data.

| Kind | URL env var | Credential (Secrets Manager key) |
|---|---|---|
| watchlist | `WATCHLIST_API_URL` | `WATCHLIST_API_KEY` |
| tms | `TMS_API_URL` | `TMS_API_KEY` |
| core_banking | `CORE_BANKING_API_URL` | `CORE_BANKING_API_KEY` |
| ach_operator | `ACH_OPERATOR_API_URL` | `ACH_OPERATOR_API_KEY` |
| market_data | `MARKET_DATA_API_URL` | `MARKET_DATA_API_KEY` |
| dmdc | `DMDC_API_URL` | `DMDC_API_KEY` |

## Adopting it in an agent (reference)

Agents currently call a vendored fixture, e.g. in
`01-financial-crime-investigation-agent/tools/watchlist_screening.py`:

```python
# BEFORE — hardcoded fixture binding
from data.fixtures import watchlist_hits
hits = watchlist_hits.lookup(customer_name)
```

```python
# AFTER — interface binding; demo vs. live is a CONNECTOR_MODE change
from fsi_agent_platform.connectors import get_connector
result = get_connector("watchlist").screen(customer_name, country=country)
hits = result["hits"]
```

The deterministic screening/escalation logic and the HITL gate are untouched.
In a pilot the team sets `CONNECTOR_MODE=live` + `WATCHLIST_API_URL` and maps the
vendor's response in `LiveWatchlist.screen` (see `live.py`).

## Rollout status

- **Framework + fixtures + stub-real + tests:** done (this package; 23 tests).
- **Per-agent adoption:** mechanical, done per engagement — replace each agent's
  hardcoded fixture import with `get_connector(...)`. Recommended order mirrors
  the pilot wedge: Agent 09 (document intake), then 02 → 01 (AML loop).
- **Live response mapping:** implemented against the customer's actual vendor API
  during the integration workstream.

## Testing

```bash
cd platform_core && pytest tests/test_connectors.py -q
```

Tests cover mode resolution, the registry/factory, every fixture's interface
contract, and that live connectors fail closed (with the offending env var named)
when unconfigured — all without network or AWS.
