"""
Gateway-backed tools for the Financial Crime Investigation Agent (Phase 3 adoption).

These are the production-path replacements for the demo fixture tools in this
package. Instead of reading a system of record directly, each function routes the
call through the **MCP authorization gateway** (platform_core), which enforces —
for the ACTING USER, not the agent — deny-by-default authorization, least
privilege (agent grant ∩ user entitlement), short-lived scoped tokens, human
approval for write/irreversible actions, and an append-only PII-masked audit.

Adoption pattern (what an engagement does):

    # BEFORE — direct fixture/vendor call, no user context, no authz, no audit
    hits = screen_against_ofac(name, country)

    # AFTER — authorized, scoped, approved-if-needed, audited, on behalf of the user
    res = screen_watchlist(state["acting_user_claims"], name, country=country)
    hits = res["data"]["hits"] if res["allowed"] else []

The acting user's verified IdP claims travel in agent state as
`acting_user_claims` (see agent/state.py). Without them the gateway denies the
call — fail-closed, by design.

This module imports the shared platform. If `fsi-agent-platform` is not
installed, the gateway functions raise GatewayUnavailable (fail-closed) rather
than silently falling back to fixtures — a regulated call must never run
un-governed because a dependency is missing.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

AGENT_ID = "01-financial-crime-investigation"


class GatewayUnavailable(RuntimeError):
    """Raised when the shared MCP gateway platform is not installed."""


_gateway = None


def _gw():
    """Lazily construct a shared gateway (one audit log for the process)."""
    global _gateway
    if _gateway is not None:
        return _gateway
    try:
        from fsi_agent_platform.mcp_gateway import MCPGateway
    except Exception as exc:  # fail closed — never fall back to ungoverned fixtures
        raise GatewayUnavailable(
            "fsi-agent-platform is required for gateway-backed tools. Install it "
            "(pip install ./platform_core) or run the demo fixture tools instead."
        ) from exc
    _gateway = MCPGateway()
    return _gateway


def _call(user_claims: Optional[Dict[str, Any]], tool: str, args: Dict[str, Any],
          approval: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Invoke a tool through the gateway and normalize the result for nodes."""
    res = _gw().invoke(user_claims=user_claims or {}, agent_id=AGENT_ID,
                       tool=tool, args=args, approval=approval)
    return {
        "allowed": res.allowed,
        "decision": res.decision,
        "data": res.result,
        "reason": res.reason,
        "audit_id": res.audit_id,
        "requires_approval": res.requires_approval,
    }


# ── Read tools (no human approval required) ───────────────────────────────────
def screen_watchlist(user_claims, name: str, country: Optional[str] = None,
                     entity_type: str = "individual") -> Dict[str, Any]:
    """OFAC/PEP/sanctions screening via the gateway → watchlist connector."""
    return _call(user_claims, "watchlist.screen",
                 {"name": name, "country": country, "entity_type": entity_type})


def get_customer(user_claims, customer_id: str) -> Dict[str, Any]:
    """Customer/KYC lookup via the gateway → core-banking connector."""
    return _call(user_claims, "core_banking.get_customer", {"customer_id": customer_id})


def get_transactions(user_claims, customer_id: str, months: int = 12) -> Dict[str, Any]:
    """Transaction history via the gateway → core-banking connector."""
    return _call(user_claims, "core_banking.get_transactions",
                 {"customer_id": customer_id, "months": months})


def get_alert(user_claims, alert_id: str) -> Dict[str, Any]:
    """TMS alert fetch via the gateway → TMS connector."""
    return _call(user_claims, "tms.get_alert", {"alert_id": alert_id})


# ── Write tool (high-risk → requires human approval at the gateway) ───────────
def update_alert_disposition(user_claims, alert_id: str, disposition: str, reason: str,
                             approval: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Write back a TMS alert disposition. High-risk: the gateway returns
    PENDING_APPROVAL until `approval={"approved": True, "reviewer": {"sub": ...}}`
    carries a verified reviewer. Composes with the agent's own HITL gate.
    """
    return _call(user_claims, "tms.update_disposition",
                 {"alert_id": alert_id, "disposition": disposition, "reason": reason},
                 approval=approval)
