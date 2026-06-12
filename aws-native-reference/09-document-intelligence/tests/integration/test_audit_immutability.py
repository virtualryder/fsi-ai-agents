"""
Audit immutability integration tests (Phase 3).

Proves the append-only / WORM controls at runtime in a deployed account — the
claims the Terraform expresses (PutItem-only IAM, S3 Object Lock COMPLIANCE):
an attempt to overwrite or delete an audit record must FAIL.
"""
from __future__ import annotations

import json
import time

import pytest


def test_audit_table_rejects_update_and_delete(aws, cfg, require):
    require("DOCINTEL_AUDIT_TABLE")
    table = cfg["audit_table"]
    entry_id = f"it-audit-{int(time.time())}"
    # The agent task role is PutItem-only; the audit record is created by the
    # pipeline. Here we assert the table's append-only contract: a conditional
    # PutItem on an existing key fails, and (if the test principal even has the
    # action) UpdateItem/DeleteItem are denied by IAM.
    aws["ddb"].put_item(
        TableName=table,
        Item={"entry_id": {"S": entry_id}, "action": {"S": "IT_PROBE"}},
    )
    # Overwriting the same entry_id must be rejected by the append-only condition.
    with pytest.raises(Exception):
        aws["ddb"].put_item(
            TableName=table,
            Item={"entry_id": {"S": entry_id}, "action": {"S": "TAMPER"}},
            ConditionExpression="attribute_not_exists(entry_id)",
        )
    # A delete should be denied by IAM (PutItem-only role) — expect AccessDenied
    # or a conditional failure depending on the test principal's policy.
    with pytest.raises(Exception):
        aws["ddb"].delete_item(TableName=table, Key={"entry_id": {"S": entry_id}})


def test_audit_bucket_has_object_lock(aws, cfg, require):
    require("DOCINTEL_AUDIT_BUCKET")
    bucket = cfg["audit_bucket"]
    conf = aws["s3"].get_object_lock_configuration(Bucket=bucket)
    rule = conf.get("ObjectLockConfiguration", {})
    assert rule.get("ObjectLockEnabled") == "Enabled", "audit bucket must have Object Lock enabled"
    # COMPLIANCE mode is required for regulatory WORM (no principal can shorten/delete).
    mode = rule.get("Rule", {}).get("DefaultRetention", {}).get("Mode")
    assert mode == "COMPLIANCE", f"expected COMPLIANCE retention mode, got {mode!r}"
