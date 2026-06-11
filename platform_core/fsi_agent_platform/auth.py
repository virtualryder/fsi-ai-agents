"""
Authentication & authorization — Rec 4 (finding C3).

The accelerator's Streamlit demos use mock auth. NOTHING in this module
changes that for demo mode — it provides the production primitives so that
every UI/API deployment fronts HITL actions with real identity:

    Okta (SAML/OIDC) ──► Cognito user pool ──► JWT (role claims) ──► this module

Two primitives:

1. `verify_jwt(token)` — signature verification against the issuer's JWKS
   (RS256), audience + expiry enforced. Returns the claims dict or raises
   AuthError. JWKS is fetched once and cached per kid.

2. `require_role(*roles)` — decorator for HITL approval handlers. The
   SERVER decides authorization from verified claims; a UI hiding a button
   is not a control. Roles are read from the configurable claim
   (AUTH_ROLE_CLAIM, default "custom:bsa_role" — Cognito custom attribute
   mapped from the Okta/AD group).

Reviewer identity binding: `record_reviewer_identity(state, claims)` stamps
the verified subject onto the HITL decision in graph state, so the audit
trail's reviewer_id is a cryptographically verified identity, not a text box.

Env reference:
    AUTH_ISSUER       e.g. https://cognito-idp.us-east-1.amazonaws.com/<pool>
    AUTH_AUDIENCE     Cognito app client id
    AUTH_ROLE_CLAIM   default custom:bsa_role
    AUTH_DISABLED     "true" ONLY in local demo — logs a loud warning

FastAPI wiring example (reference API in examples/hitl_api.py):

    @app.post("/cases/{case_id}/approve")
    @require_role("BSA_OFFICER", "SENIOR_ANALYST")
    def approve(case_id: str, *, claims: dict): ...
"""
from __future__ import annotations

import functools
import json
import logging
import os
import time
import urllib.request
from typing import Any, Callable, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised on any verification or authorization failure (fail-closed)."""


_jwks_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600


def _issuer() -> str:
    iss = os.getenv("AUTH_ISSUER", "")
    if not iss:
        raise AuthError("AUTH_ISSUER not configured — refusing to verify tokens (fail-closed)")
    return iss.rstrip("/")


def _fetch_jwks() -> Dict[str, Any]:
    now = time.time()
    if _jwks_cache["keys"] is not None and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS:
        return _jwks_cache["keys"]
    url = f"{_issuer()}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=5) as resp:  # nosec B310 — issuer is operator-configured https
        jwks = json.loads(resp.read().decode("utf-8"))
    _jwks_cache.update(keys=jwks, fetched_at=now)
    return jwks


def verify_jwt(token: str) -> Dict[str, Any]:
    """
    Verify an RS256 JWT against the issuer's JWKS. Enforces signature,
    issuer, audience, and expiry. Returns claims; raises AuthError otherwise.
    """
    if os.getenv("AUTH_DISABLED", "").lower() == "true":
        logger.warning("AUTH_DISABLED=true — token verification BYPASSED. Demo mode only.")
        return {"sub": "demo-user", "demo_mode": True}

    try:
        import jwt  # PyJWT — lazy: only required where auth is enabled
        from jwt import PyJWKClient
    except ImportError as exc:  # pragma: no cover
        raise AuthError("PyJWT not installed — pip install 'PyJWT[crypto]'") from exc

    try:
        jwks_url = f"{_issuer()}/.well-known/jwks.json"
        signing_key = PyJWKClient(jwks_url, cache_keys=True).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=os.getenv("AUTH_AUDIENCE") or None,
            issuer=_issuer(),
            options={"require": ["exp", "iss", "sub"]},
        )
        return claims
    except Exception as exc:
        # Single failure mode, no detail leakage to the caller
        logger.info("JWT verification failed: %s", type(exc).__name__)
        raise AuthError("token verification failed") from exc


def roles_from_claims(claims: Dict[str, Any]) -> Iterable[str]:
    claim_name = os.getenv("AUTH_ROLE_CLAIM", "custom:bsa_role")
    raw = claims.get(claim_name) or claims.get("cognito:groups") or []
    if isinstance(raw, str):
        return [r.strip() for r in raw.split(",") if r.strip()]
    return list(raw)


def require_role(*allowed_roles: str) -> Callable:
    """
    Server-side authorization for HITL approval actions.

    The wrapped callable must receive the bearer token via a `token` kwarg
    (or an `authorization` kwarg of the form "Bearer <token>"). On success
    the verified claims are injected as the `claims` kwarg. On ANY failure
    the call is rejected — fail-closed, no partial execution.
    """
    allowed = frozenset(allowed_roles)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            token: Optional[str] = kwargs.pop("token", None)
            authz: Optional[str] = kwargs.pop("authorization", None)
            if token is None and authz and authz.lower().startswith("bearer "):
                token = authz[7:]
            if not token:
                raise AuthError("missing bearer token")
            claims = verify_jwt(token)
            user_roles = set(roles_from_claims(claims))
            if claims.get("demo_mode"):
                user_roles = set(allowed)  # demo bypass already logged loudly
            if not user_roles & allowed:
                logger.warning(
                    "AUTHZ DENY sub=%s roles=%s needed_any_of=%s action=%s",
                    claims.get("sub"), sorted(user_roles), sorted(allowed), fn.__name__,
                )
                raise AuthError("insufficient role for this action")
            kwargs["claims"] = claims
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def record_reviewer_identity(state: Dict[str, Any], claims: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bind the VERIFIED reviewer identity to a HITL decision in graph state.
    Call this in the approval handler before graph.update_state(): the
    audit trail then carries a verified subject, not a self-asserted name.
    """
    return {
        **state,
        "reviewer_id": claims.get("sub", "UNKNOWN"),
        "reviewer_email": claims.get("email", ""),
        "reviewer_roles": sorted(roles_from_claims(claims)),
        "reviewer_identity_verified": not claims.get("demo_mode", False),
    }
