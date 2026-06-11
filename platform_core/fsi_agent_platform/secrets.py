"""
Secrets retrieval — Rec 4 (finding H1).

Order of precedence (first hit wins):
  1. AWS Secrets Manager, when SECRETS_MANAGER_PREFIX is set
     (secret name = f"{prefix}/{key}") — retrieved via the ECS task role,
     cached in-process with a short TTL.
  2. Environment variable of the same key — dev/demo fallback.

Rules this module enforces by existing:
  - No API keys typed into UI fields (remove key-entry sidebars; call
    get_secret("ANTHROPIC_API_KEY") instead).
  - No secrets in code, compose files, or .env committed to git.
  - Rotation-friendly: TTL cache means a rotated secret is picked up
    within SECRETS_CACHE_TTL seconds (default 300) without restart.
  - Fail-closed in production: if SECRETS_MANAGER_PREFIX is set and the
    lookup fails, the env fallback is a DEV convenience only. Set
    SECRETS_FAIL_CLOSED=true (implied when ENVIRONMENT=production) to raise
    instead of silently falling back — a missing task-role permission or a
    Secrets Manager outage must not cause the app to quietly run on whatever
    happens to be in the environment. (Control-integrity, Phase 1.5.)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_cache: Dict[str, Tuple[str, float]] = {}


def _fail_closed() -> bool:
    """True when a failed Secrets Manager lookup must raise, not fall back.

    Enabled explicitly via SECRETS_FAIL_CLOSED, or implicitly in production
    (ENVIRONMENT=production / prod). Dev and demo default to env fallback.
    """
    if os.getenv("SECRETS_FAIL_CLOSED", "").strip().lower() in ("1", "true", "yes"):
        return True
    return os.getenv("ENVIRONMENT", "").strip().lower() in ("production", "prod")


class SecretsUnavailableError(RuntimeError):
    """Raised in fail-closed mode when a configured secret cannot be retrieved."""


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    prefix = os.getenv("SECRETS_MANAGER_PREFIX", "")
    ttl = float(os.getenv("SECRETS_CACHE_TTL", "300"))

    if prefix:
        cached = _cache.get(key)
        if cached and time.time() - cached[1] < ttl:
            return cached[0]
        try:
            import boto3  # lazy — only when Secrets Manager is configured

            client = boto3.client("secretsmanager")
            resp = client.get_secret_value(SecretId=f"{prefix}/{key}")
            value = resp.get("SecretString", "")
            _cache[key] = (value, time.time())
            return value
        except Exception as exc:
            # In production (or when SECRETS_FAIL_CLOSED is set) a failed
            # lookup must NOT silently fall back to the environment — that path
            # could run the app on a stale or attacker-supplied env value and
            # masks a real misconfiguration (e.g. a missing task-role grant).
            if _fail_closed():
                logger.error(
                    "Secrets Manager lookup failed for %s/%s: %s — failing closed "
                    "(SECRETS_FAIL_CLOSED/ENVIRONMENT=production). No env fallback.",
                    prefix, key, type(exc).__name__,
                )
                raise SecretsUnavailableError(
                    f"Secret {prefix}/{key} unavailable and fail-closed mode is active"
                ) from exc
            # Dev/demo: log loudly and fall back to the environment.
            logger.warning("Secrets Manager lookup failed for %s/%s: %s", prefix, key, type(exc).__name__)

    return os.getenv(key, default)
