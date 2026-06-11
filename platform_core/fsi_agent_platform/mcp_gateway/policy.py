"""
MCP authorization policy (Phase 3).

The authorization decision is the heart of the gateway. It is **deny-by-default**
and enforces **least privilege as an intersection**: a tool call is permitted
only if BOTH the calling agent is granted the tool AND the acting user is
entitled to it. An agent can never do more than the human on whose behalf it
acts — even if the agent's own grant list is broader.

  permitted(tool) ⇔ tool ∈ AGENT_TOOL_GRANTS[agent] ∩ ⋃ ROLE_ENTITLEMENTS[user_roles]

High-risk (write / irreversible) tools additionally require human approval
before execution. Reads do not.

In production these tables live in a policy engine (OPA/Cedar) fed by the
enterprise IdP; here they are explicit Python so the model is testable and the
intersection semantics are unambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Tuple

# ── Tool registry: tool name -> (connector_kind, method, high_risk) ───────────
# Tool names are "<connector_kind>.<operation>" and map onto the Phase 2
# connector framework, so the gateway is the governed front door to those
# systems of record.
TOOL_REGISTRY: Dict[str, Tuple[str, str, bool]] = {
    "watchlist.screen":              ("watchlist", "screen", False),
    "tms.get_alert":                 ("tms", "get_alert", False),
    "tms.update_disposition":        ("tms", "update_disposition", True),   # write
    "core_banking.get_customer":     ("core_banking", "get_customer", False),
    "core_banking.get_transactions": ("core_banking", "get_transactions", False),
    "ach_operator.lookup_return_code": ("ach_operator", "lookup_return_code", False),
    "ach_operator.submit_return":    ("ach_operator", "submit_return", True),  # write
    "market_data.get_quote":         ("market_data", "get_quote", False),
    "market_data.get_trades":        ("market_data", "get_trades", False),
    "dmdc.check_scra_status":        ("dmdc", "check_scra_status", False),
}

HIGH_RISK_TOOLS: FrozenSet[str] = frozenset(t for t, (_, _, hr) in TOOL_REGISTRY.items() if hr)

# ── What each AGENT is allowed to call (its job description as code) ───────────
AGENT_TOOL_GRANTS: Dict[str, FrozenSet[str]] = {
    "01-financial-crime-investigation": frozenset({
        "watchlist.screen", "core_banking.get_customer", "core_banking.get_transactions",
        "tms.get_alert", "tms.update_disposition",
    }),
    "03-kyc-cdd-perpetual": frozenset({
        "watchlist.screen", "core_banking.get_customer", "dmdc.check_scra_status",
    }),
    "09-document-intelligence": frozenset({
        "core_banking.get_customer", "watchlist.screen",
    }),
    "07-trading-surveillance": frozenset({
        "market_data.get_quote", "market_data.get_trades",
    }),
    "10-payments-compliance": frozenset({
        "ach_operator.lookup_return_code", "ach_operator.submit_return",
        "core_banking.get_customer", "watchlist.screen",
    }),
    "12-collections-recovery": frozenset({
        "dmdc.check_scra_status", "core_banking.get_customer",
    }),
}

# ── What each USER ROLE is entitled to (the human's real permissions) ─────────
ROLE_ENTITLEMENTS: Dict[str, FrozenSet[str]] = {
    "BSA_ANALYST": frozenset({
        "watchlist.screen", "tms.get_alert",
        "core_banking.get_customer", "core_banking.get_transactions",
    }),
    "BSA_OFFICER": frozenset({  # everything an analyst can do, plus dispositions
        "watchlist.screen", "tms.get_alert", "tms.update_disposition",
        "core_banking.get_customer", "core_banking.get_transactions",
    }),
    "KYC_REVIEWER": frozenset({
        "watchlist.screen", "core_banking.get_customer", "dmdc.check_scra_status",
    }),
    "PAYMENTS_OPS": frozenset({
        "ach_operator.lookup_return_code", "core_banking.get_customer", "watchlist.screen",
    }),
    "PAYMENTS_OFFICER": frozenset({
        "ach_operator.lookup_return_code", "ach_operator.submit_return",
        "core_banking.get_customer", "watchlist.screen",
    }),
    "SURVEILLANCE_ANALYST": frozenset({"market_data.get_quote", "market_data.get_trades"}),
}


@dataclass
class PolicyDecision:
    allowed: bool
    tool: str
    reason: str
    requires_approval: bool = False
    connector_kind: str = ""
    method: str = ""
    # The scope granted is exactly this tool — least privilege, nothing wider.
    effective_scope: List[str] = field(default_factory=list)


def user_entitlements(roles: Iterable[str]) -> FrozenSet[str]:
    """Union of entitlements across the user's roles (unknown roles contribute nothing)."""
    out: set = set()
    for r in roles:
        out |= ROLE_ENTITLEMENTS.get(r, frozenset())
    return frozenset(out)


def decide(agent_id: str, user_roles: Iterable[str], tool: str) -> PolicyDecision:
    """Deny-by-default authorization with least-privilege intersection."""
    if tool not in TOOL_REGISTRY:
        return PolicyDecision(False, tool, f"unknown tool {tool!r}")

    connector_kind, method, high_risk = TOOL_REGISTRY[tool]
    agent_grants = AGENT_TOOL_GRANTS.get(agent_id, frozenset())
    if tool not in agent_grants:
        return PolicyDecision(False, tool,
                              f"agent {agent_id!r} is not granted {tool!r} (agent over-reach denied)",
                              connector_kind=connector_kind, method=method)

    ent = user_entitlements(user_roles)
    if tool not in ent:
        return PolicyDecision(False, tool,
                              f"acting user (roles={list(user_roles)}) is not entitled to {tool!r} "
                              f"(an agent may never exceed the user's own permissions)",
                              connector_kind=connector_kind, method=method)

    # Permitted = in the intersection. High-risk tools still need human approval.
    return PolicyDecision(
        True, tool,
        "permitted by agent grant ∩ user entitlement",
        requires_approval=tool in HIGH_RISK_TOOLS,
        connector_kind=connector_kind, method=method,
        effective_scope=[tool],
    )
