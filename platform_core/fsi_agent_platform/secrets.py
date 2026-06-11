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
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_cache: Dict[str, Tuple[str, float]] = {}


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
            # Fail toward env fallback in dev; in production the task role
            # should always reach Secrets Manager — log loudly either way.
            logger.warning("Secrets Manager lookup failed for %s/%s: %s", prefix, key, type(exc).__name__)

    return os.getenv(key, default)
