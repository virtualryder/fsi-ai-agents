"""
Persistence layer — durable audit sink + persistent HITL checkpointing.

This module addresses the two highest-priority compliance gaps identified in
the field assessment:

1. AUDIT DURABILITY (write-ahead). Audit entries previously lived only inside
   graph state (an in-memory Python list) — lost on crash, mutable by any
   code path, and absent from any retention store. `AuditSink.record()` is
   called at the moment each entry is created (write-ahead, not end-of-graph):
     - Local JSONL  (always on): append-only file per day under AUDIT_LOG_DIR
       (default: <agent>/var/audit/). Dev/demo durability + grep-able trail.
     - DynamoDB     (when AUDIT_DYNAMODB_TABLE is set): PutItem with a
       condition expression (attribute_not_exists) so an entry can never be
       overwritten — append-only at the database level. STRICT mode: a failed
       durable write raises, halting the pipeline (write-ahead semantics —
       processing must not outrun the audit record).
     - S3 Object Lock (when AUDIT_S3_BUCKET is set): `snapshot()` writes the
       full trail as a WORM object. The bucket MUST be created with Object
       Lock enabled in COMPLIANCE mode (not GOVERNANCE) for regulatory
       retention (BSA 5yr / FCRA 7yr / SR 11-7 10yr per artifact class) —
       see docs/aws-deployment-guide.md.

2. PERSISTENT HITL STATE. `get_checkpointer()` returns a PostgresSaver when
   DATABASE_URL is set (Aurora PostgreSQL in production) so human-review
   pauses survive process restarts. Without DATABASE_URL it falls back to
   MemorySaver with a logged warning — acceptable ONLY for dev/demo, where a
   killed process abandons any paused review.

Environment variables:
    AUDIT_LOG_DIR          Local JSONL directory (default: ./var/audit)
    AUDIT_DYNAMODB_TABLE   DynamoDB table name (PK: entry_id) — strict mode
    AUDIT_S3_BUCKET        S3 bucket (Object Lock COMPLIANCE) for snapshots
    DATABASE_URL           postgresql://... — activates PostgresSaver
    AGENT_ID               Logical agent identifier stamped on every record

This file is identical across all 12 agents (vendored, not shared-installed,
so each agent remains independently deployable). Treat it as platform code:
changes belong in every copy. A shared platform library is the roadmap home.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_AGENT_ID = os.getenv("AGENT_ID", Path(__file__).resolve().parent.parent.name)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── PII masking at the audit-write boundary (Phase 1.4, suite-wide rollout) ───
# Every durable audit write is masked here so raw PII can never reach the JSONL,
# DynamoDB, or S3 WORM sink — masking is the enforced default of the persistence
# path, not a per-field discretionary call. Prefers the shared platform boundary
# middleware (fsi_agent_platform.pii.mask_obj); falls back to a self-contained
# recursive masker so each agent remains independently deployable.
import re as _re

_PII_SSN = _re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_PII_ACCT = _re.compile(r"\b(?:account|acct|routing|aba)\s*(?:no\.?|number|#)?[:\s]*\d{6,17}\b", _re.I)
_PII_EMAIL = _re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PII_CARD = _re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in digits if c.isdigit()]
    if len(ds) < 13:
        return False
    checksum, parity = 0, len(ds) % 2
    for i, d in enumerate(ds):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _mask_str(text: str) -> str:
    text = _PII_SSN.sub("[SSN-MASKED]", text)
    text = _PII_ACCT.sub("[ACCOUNT-MASKED]", text)
    text = _PII_EMAIL.sub("[EMAIL-MASKED]", text)
    text = _PII_CARD.sub(lambda m: "[CARD-MASKED]" if _luhn_ok(m.group(0)) else m.group(0), text)
    return text


def _local_mask(obj):
    if isinstance(obj, str):
        return _mask_str(obj)
    if isinstance(obj, dict):
        return {k: _local_mask(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_local_mask(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_local_mask(v) for v in obj)
    return obj


def _scrub_pii(obj):
    """Return a PII-masked copy of a structured record for durable persistence.

    Fail-open to the local masker (never raise) — an audit write must not be
    blocked — but it must never persist raw PII.
    """
    try:
        from fsi_agent_platform.pii import mask_obj  # shared boundary middleware
        return mask_obj(obj)[0]
    except Exception:
        return _local_mask(obj)


class AuditSink:
    """Write-ahead audit sink. Thread-safe. Fail-closed in DynamoDB mode."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._log_dir = Path(os.getenv("AUDIT_LOG_DIR", Path(__file__).resolve().parent.parent / "var" / "audit"))
        self._ddb_table = os.getenv("AUDIT_DYNAMODB_TABLE", "")
        self._s3_bucket = os.getenv("AUDIT_S3_BUCKET", "")
        self._ddb = None
        self._s3 = None
        if self._ddb_table or self._s3_bucket:
            import boto3  # Lazy: boto3 only required when AWS sinks are configured

            if self._ddb_table:
                self._ddb = boto3.resource("dynamodb").Table(self._ddb_table)
            if self._s3_bucket:
                self._s3 = boto3.client("s3")

    # ── Write-ahead: one entry, durable BEFORE the pipeline proceeds ─────────
    def record(self, entry: Dict[str, Any]) -> None:
        """
        Persist a single audit entry. Called at entry-creation time.

        Local JSONL is best-effort (a dev disk problem must not kill a demo).
        DynamoDB is STRICT: if the configured durable store rejects the write,
        the exception propagates and the node fails — which, suite-wide, routes
        to human review via the fail-safe node pattern. An unauditable action
        must not complete silently.
        """
        record = {
            "entry_id": entry.get("entry_id") or str(uuid.uuid4()),
            "agent_id": _AGENT_ID,
            "recorded_at": _now_utc(),
            **entry,
        }
        # Boundary enforcement: mask PII before any durable write (Phase 1.4).
        record = _scrub_pii(record)
        payload = json.dumps(record, default=str, separators=(",", ":"))

        # Best-effort local JSONL (always on)
        try:
            with self._lock:
                self._log_dir.mkdir(parents=True, exist_ok=True)
                fname = self._log_dir / f"audit-{datetime.now(timezone.utc):%Y%m%d}.jsonl"
                with open(fname, "a", encoding="utf-8") as f:
                    f.write(payload + "\n")
        except OSError as exc:  # pragma: no cover — disk-level dev failures
            logger.warning("Local audit JSONL write failed (non-fatal in dev): %s", exc)

        # Strict append-only durable store
        if self._ddb is not None:
            # ConditionExpression makes the table append-only: an existing
            # entry_id can never be overwritten by any code path.
            self._ddb.put_item(
                Item={k: (v if isinstance(v, (str, int, bool)) else json.dumps(v, default=str))
                      for k, v in record.items()},
                ConditionExpression="attribute_not_exists(entry_id)",
            )

    # ── Periodic / terminal WORM snapshot of the full trail ──────────────────
    def snapshot(self, case_id: str, audit_trail: List[Dict[str, Any]]) -> Optional[str]:
        """
        Write the full audit trail as a WORM object (S3 Object Lock bucket).
        Returns the object key, or None when no S3 sink is configured.
        Call from the agent's finalize node and at HITL pause points.
        """
        if self._s3 is None:
            return None
        key = f"{_AGENT_ID}/{case_id or 'unknown'}/{_now_utc()}-audit.json"
        self._s3.put_object(
            Bucket=self._s3_bucket,
            Key=key,
            Body=json.dumps(_scrub_pii(audit_trail), default=str).encode("utf-8"),
            ContentType="application/json",
            # Retention is enforced by the bucket's Object Lock COMPLIANCE-mode
            # default retention policy — set per artifact class in IaC.
        )
        return key


# ── Singletons (lazy) ─────────────────────────────────────────────────────────
_audit_sink: Optional[AuditSink] = None
_checkpointer = None
_warned_memory = False


def audit_sink() -> AuditSink:
    global _audit_sink
    if _audit_sink is None:
        _audit_sink = AuditSink()
    return _audit_sink


def get_checkpointer():
    """
    Durable-first checkpointer factory.

    DATABASE_URL set → PostgresSaver (HITL pauses survive restarts).
    Otherwise → MemorySaver with a logged warning: a paused human review
    dies with the process. Dev/demo only.
    """
    global _checkpointer, _warned_memory
    if _checkpointer is not None:
        return _checkpointer

    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        _checkpointer = PostgresSaver.from_conn_string(db_url).__enter__()
        _checkpointer.setup()
        logger.info("Checkpointer: PostgresSaver (durable HITL state) — %s", db_url.split("@")[-1])
    else:
        from langgraph.checkpoint.memory import MemorySaver

        if not _warned_memory:
            logger.warning(
                "Checkpointer: MemorySaver (NON-DURABLE). Paused human reviews will NOT "
                "survive a restart. Set DATABASE_URL for PostgresSaver in any shared or "
                "production environment."
            )
            _warned_memory = True
        _checkpointer = MemorySaver()
    return _checkpointer
