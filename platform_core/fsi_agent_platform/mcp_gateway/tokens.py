"""
Short-lived scoped capability tokens (Phase 3).

After the gateway authorizes a call it mints a token scoped to exactly one
tool+operation, carrying the acting user's identity, with a short TTL (minutes).
The downstream connector/tool trusts only this token — not a standing service
account. This is the "no standing credentials; least-privilege, user-context,
time-boxed" property of the security model.

Reference implementation: a self-contained HMAC-signed token (stdlib only) so
the model is testable with no external dependency. **In production this is an
AWS STS short-lived credential / Amazon Cognito token exchange / Bedrock
AgentCore Identity workload token** — the gateway mints the downscoped token,
the tool validates it. The claims and TTL semantics are identical.

Fail-closed: any tampering, expiry, or malformed input raises TokenError.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from .errors import TokenError

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300  # 5 minutes — short by design


def _signing_key() -> bytes:
    key = os.getenv("MCP_GATEWAY_SIGNING_KEY", "")
    if not key:
        # Dev/demo only. Loud: a static dev key must never be used in production,
        # where this is replaced by STS/Cognito/AgentCore Identity anyway.
        logger.warning(
            "MCP_GATEWAY_SIGNING_KEY unset — using a non-secret dev key. Set it in any "
            "shared environment, or (preferred) use STS/Cognito token exchange in production."
        )
        key = "dev-only-insecure-key"
    return key.encode("utf-8")


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def mint_scoped_token(
    *,
    subject: str,
    agent_id: str,
    tool: str,
    scope: List[str],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Mint a signed, short-lived token scoped to one tool, carrying user context."""
    if not subject or not agent_id or not tool:
        raise TokenError("subject, agent_id and tool are required to mint a scoped token")
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject,            # the acting USER — context propagation
        "agent_id": agent_id,      # the agent acting on their behalf
        "tool": tool,              # exactly one tool
        "scope": list(scope),      # least privilege
        "iat": now,
        "exp": now + int(ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64u(hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_scoped_token(token: str, *, expected_tool: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify signature + expiry (+ optional tool binding). Returns claims or raises
    TokenError. Constant-time signature comparison; fail-closed on every error.
    """
    if not token or token.count(".") != 1:
        raise TokenError("malformed token")
    body, sig = token.split(".")
    expected_sig = _b64u(hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected_sig):
        raise TokenError("bad signature — token tampered or wrong signing key")
    try:
        claims = json.loads(_b64u_decode(body))
    except Exception as exc:
        raise TokenError("undecodable token body") from exc
    if int(claims.get("exp", 0)) < int(time.time()):
        raise TokenError("token expired")
    if expected_tool is not None and claims.get("tool") != expected_tool:
        raise TokenError(f"token scoped to {claims.get('tool')!r}, not {expected_tool!r}")
    return claims
