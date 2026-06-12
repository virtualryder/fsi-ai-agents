"""
End-to-end gateway adoption test (Phase 3) — agent -> MCP gateway -> connector.

Proves the full stack with Agent 01's gateway-backed tools
(01-financial-crime-investigation-agent/tools/gateway_tools.py): a real agent
tool call is authorized for the ACTING USER, scoped, approved-if-high-risk,
executed against the connector, and audited — fail-closed without user context.

Loaded by file path so the test does not depend on the agent's package layout.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GW_TOOLS = REPO_ROOT / "01-financial-crime-investigation-agent" / "tools" / "gateway_tools.py"


@pytest.fixture()
def gt():
    spec = importlib.util.spec_from_file_location("agent01_gateway_tools", GW_TOOLS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._gateway = None  # fresh gateway (clean audit) per test
    return mod


ANALYST = {"sub": "u-analyst", "custom:bsa_role": "BSA_ANALYST"}
OFFICER = {"sub": "u-officer", "custom:bsa_role": "BSA_OFFICER"}
APPROVAL = {"approved": True, "reviewer": {"sub": "supervisor-1"}}


def test_screen_watchlist_allowed_returns_connector_data(gt):
    r = gt.screen_watchlist(ANALYST, "Ivan Petrov", country="RU")
    assert r["allowed"] and r["decision"] == "ALLOW"
    assert r["data"]["hit"] is True and r["audit_id"]


def test_get_customer_allowed(gt):
    r = gt.get_customer(ANALYST, "CUST-001")
    assert r["allowed"] and r["data"]["risk_tier"] == "MEDIUM"


def test_missing_user_context_is_denied(gt):
    r = gt.screen_watchlist(None, "Ivan Petrov")
    assert not r["allowed"] and r["decision"] == "DENY"
    assert r["data"] is None and "authenticated" in r["reason"]


def test_disposition_write_pends_for_analyst_then_blocked_by_entitlement(gt):
    # An analyst is not entitled to write a disposition — denied (least privilege),
    # even though the agent itself is granted that tool.
    r = gt.update_alert_disposition(ANALYST, "ALERT-1001", "CLOSE", "false positive")
    assert not r["allowed"] and r["decision"] == "DENY" and "not entitled" in r["reason"]


def test_disposition_write_requires_approval_for_officer(gt):
    r = gt.update_alert_disposition(OFFICER, "ALERT-1001", "ESCALATE", "structuring")
    assert r["decision"] == "PENDING_APPROVAL" and r["requires_approval"] and r["data"] is None


def test_disposition_write_executes_with_verified_approval(gt):
    r = gt.update_alert_disposition(OFFICER, "ALERT-1001", "ESCALATE", "structuring", approval=APPROVAL)
    assert r["allowed"] and r["data"]["accepted"] is True


def test_every_call_is_audited_with_lineage(gt):
    gt.screen_watchlist(ANALYST, "Ivan Petrov")
    gt.get_customer(ANALYST, "CUST-001")
    gt.update_alert_disposition(ANALYST, "ALERT-1001", "CLOSE", "x")  # denied, still audited
    audit = gt._gw().audit
    entries = audit.entries()
    assert len(entries) == 3
    assert {e["decision"] for e in entries} == {"ALLOW", "DENY"}
    allow = [e for e in entries if e["decision"] == "ALLOW"][0]
    assert allow["agent_id"] == "01-financial-crime-investigation"
    assert allow["lineage"]["connector"] in {"watchlist", "core_banking"}


def test_pii_in_query_is_masked_in_audit(gt):
    gt.screen_watchlist(ANALYST, "subject SSN 123-45-6789")
    assert "123-45-6789" not in repr(gt._gw().audit.entries())
