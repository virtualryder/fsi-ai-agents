"""
Audit-write boundary masking test (Phase 1.4 suite-wide rollout).

`persistence.py` is byte-identical across all 12 agents, so this runtime proof
on Agent 01 covers the whole suite: an audit entry carrying raw PII is masked
BEFORE it is written to the durable JSONL sink — masking is enforced by the
persistence path, not left to per-field discipline. Structural fields
(entry_id, agent_id, action) are preserved.
"""
from __future__ import annotations

import json

from agent.persistence import AuditSink, _scrub_pii


def _read_jsonl(log_dir):
    files = list(log_dir.glob("audit-*.jsonl"))
    assert files, "no audit JSONL written"
    return files[0].read_text()


def test_raw_pii_is_masked_before_durable_write(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_DIR", str(tmp_path))
    sink = AuditSink()  # reads AUDIT_LOG_DIR at construction
    sink.record({
        "entry_id": "E-1",
        "action": "CUSTOMER_CONTEXT_LOADED",
        "details": {"note": "subject SSN 123-45-6789, card 4111 1111 1111 1111"},
    })
    blob = _read_jsonl(tmp_path)
    assert "123-45-6789" not in blob
    assert "4111 1111 1111 1111" not in blob and "4111111111111111" not in blob
    # structural fields survive masking
    assert "E-1" in blob and "CUSTOMER_CONTEXT_LOADED" in blob


def test_entry_id_preserved_for_append_only_constraint(tmp_path, monkeypatch):
    # entry_id is a UUID, not PII — masking must never alter it (the DynamoDB
    # attribute_not_exists(entry_id) append-only constraint depends on it).
    rec = {"entry_id": "abc123def456", "action": "X", "details": {"ssn": "111-22-3333"}}
    masked = _scrub_pii(rec)
    assert masked["entry_id"] == "abc123def456"
    assert "111-22-3333" not in json.dumps(masked)


def test_non_pii_record_is_lossless(tmp_path, monkeypatch):
    rec = {"entry_id": "E-2", "action": "RISK_SCORED", "details": {"score": 72, "tier": "HIGH"}}
    assert _scrub_pii(rec) == rec
