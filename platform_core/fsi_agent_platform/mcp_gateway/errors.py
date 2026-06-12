"""MCP gateway errors — all fail-closed (deny by default)."""
from __future__ import annotations


class GatewayError(RuntimeError):
    """Base class for all gateway errors."""


class PolicyDenied(GatewayError):
    """The tool call is not permitted (deny-by-default outcome)."""


class ApprovalRequired(GatewayError):
    """A high-risk tool call requires human approval before it may execute."""


class TokenError(GatewayError):
    """A scoped capability token is missing, malformed, tampered, or expired."""
