"""
Append-only gateway audit log (Phase 3).

Every tool-call attempt — ALLOW, DENY, PENDING_APPROVAL, or ERROR — is recorded,
PII-masked, with the acting user, the agent, the tool, the decision, the scoped
token id, and a lineage pointer to the system of record reached. Denials are
recorded too: "the agent tried X and was refused" is exactly what an
investigation needs. Entries are immutable once appended.

Reference: an in-process append-only list with an optional sink hook. In
production this writes to append-only DynamoDB (PutItem-only IAM) + S3 Object
Lock, the same controls the suite already expresses in infra/terraform.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:  # reuse the shared PII boundary middleware (Phase 1)
    from fsi_agent_platform.pii import mask_obj as _mask_obj
except Exception:  # pragma: no cover - platform always present here
    def _mask_obj(o):
        return o, []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GatewayAuditLog:
    """Append-only, PII-masked audit log for gateway decisions."""

    def __init__(self, sink: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._sink = sink  # e.g. a DynamoDB/S3 writer in production

    def record(self, entry: Dict[str, Any]) -> str:
        masked, _ = _mask_obj(entry)
        record = {
            "audit_id": uuid.uuid4().hex,
            "recorded_at": _now(),
            **masked,
        }
        self._entries.append(record)        # append-only; never mutated
        if self._sink is not None:
            self._sink(record)              # durable, append-only store in prod
        return record["audit_id"]

    def entries(self) -> List[Dict[str, Any]]:
        return list(self._entries)          # read-only copy

    def for_user(self, subject: str) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e.get("user") == subject]

    def denials(self) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e.get("decision") == "DENY"]
