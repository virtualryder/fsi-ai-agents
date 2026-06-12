"""
MCP authorization gateway for the FSI AI Agent Suite (Phase 3).

The governed front door between agents and systems of record: deny-by-default
authorization, least-privilege as agent-grant ∩ user-entitlement, short-lived
scoped tokens with user-context propagation, human approval for high-risk tools,
and an append-only PII-masked audit of every attempt — fail-closed throughout.

Public API:
    MCPGateway(audit=None, connector_mode=None).invoke(user_claims, agent_id, tool, args, approval)
    GatewayResult
    policy.decide(agent_id, user_roles, tool) -> PolicyDecision
    tokens.mint_scoped_token / tokens.verify_scoped_token
    GatewayAuditLog
    errors: GatewayError, PolicyDenied, ApprovalRequired, TokenError
"""
from . import policy, tokens
from .audit import GatewayAuditLog
from .errors import ApprovalRequired, GatewayError, PolicyDenied, TokenError
from .gateway import GatewayResult, MCPGateway

__all__ = [
    "MCPGateway",
    "GatewayResult",
    "GatewayAuditLog",
    "policy",
    "tokens",
    "GatewayError",
    "PolicyDenied",
    "ApprovalRequired",
    "TokenError",
]
