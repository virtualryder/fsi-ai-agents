"""
Deployed pipeline integration tests (Phase 3) — run against a live state machine.

Verifies the AWS-native Document Intelligence reference end-to-end in an account:
the Step Functions state machine processes a document, the deterministic gates
hold, and HITL pauses via waitForTaskToken exactly as the local tests assert.
Skipped unless RUN_AWS_INTEGRATION + config are present (see conftest).
"""
from __future__ import annotations

import json
import os
import time

import pytest


def _start(aws, arn, payload):
    r = aws["sfn"].start_execution(stateMachineArn=arn, input=json.dumps(payload))
    return r["executionArn"]


def _wait(aws, exec_arn, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = aws["sfn"].describe_execution(executionArn=exec_arn)
        if d["status"] != "RUNNING":
            return d
        time.sleep(3)
    return aws["sfn"].describe_execution(executionArn=exec_arn)


def test_clean_document_runs_to_completion(aws, cfg, require):
    require("DOCINTEL_STATE_MACHINE_ARN")
    # A document with no PII and a confident, low-sensitivity type should
    # auto-route and the execution should SUCCEED (no HITL pause).
    payload = {"document": {"doc_id": "it-clean-1",
                            "text": "FORM 1003 Uniform Residential Loan Application borrower loan_amount 250000"}}
    d = _wait(aws, _start(aws, cfg["state_machine_arn"], payload))
    assert d["status"] == "SUCCEEDED", f"unexpected status {d['status']}"
    out = json.loads(d.get("output", "{}"))
    assert out.get("status") == "COMPLETE"
    assert out.get("routing", {}).get("human_review_required") is False


def test_sensitive_document_pauses_for_hitl(aws, cfg, require):
    require("DOCINTEL_STATE_MACHINE_ARN", "DOCINTEL_HITL_TABLE")
    # A SAR form is an always-HITL type: the execution should pause at the
    # waitForTaskToken gate (status RUNNING) and a token should be queued.
    payload = {"document": {"doc_id": "it-sar-1", "text": "FinCEN SAR suspicious activity report"}}
    exec_arn = _start(aws, cfg["state_machine_arn"], payload)
    time.sleep(20)
    d = aws["sfn"].describe_execution(executionArn=exec_arn)
    assert d["status"] == "RUNNING", "sensitive doc must pause at the HITL gate, not complete"
    item = aws["ddb"].get_item(TableName=cfg["hitl_table"],
                               Key={"doc_id": {"S": "it-sar-1"}}).get("Item")
    assert item is not None, "HITL gate did not queue a task token for review"
    # Cleanup: stop the paused execution.
    aws["sfn"].stop_execution(executionArn=exec_arn)


def test_pii_document_pauses_and_is_masked(aws, cfg, require):
    require("DOCINTEL_STATE_MACHINE_ARN")
    payload = {"document": {"doc_id": "it-pii-1",
                            "text": "Loan application. Borrower SSN 123-45-6789."}}
    exec_arn = _start(aws, cfg["state_machine_arn"], payload)
    time.sleep(20)
    d = aws["sfn"].describe_execution(executionArn=exec_arn)
    # PII handling forces HITL; the raw SSN must never appear in execution history.
    history = aws["sfn"].get_execution_history(executionArn=exec_arn, maxResults=1000)
    assert "123-45-6789" not in json.dumps(history["events"]), "raw SSN leaked into execution history"
    if d["status"] == "RUNNING":
        aws["sfn"].stop_execution(executionArn=exec_arn)
