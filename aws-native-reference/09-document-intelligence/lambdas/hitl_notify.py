"""HITL gate notifier — invoked by the waitForTaskToken state.

Its only job is to persist the task token alongside the case and notify the
review queue (e.g. write to DynamoDB + EventBridge). It returns immediately; the
state machine stays PAUSED until a reviewer resumes it via hitl_callback ->
SendTaskSuccess. The pause is enforced by Step Functions, not by this code — the
AWS-native equivalent of LangGraph `interrupt_before`.
"""
from __future__ import annotations
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event)
    task_token = event.get("task_token", "")
    doc_id = payload.get("document", {}).get("doc_id")
    reason = payload.get("routing", {}).get("human_review_reason", "")
    try:
        import boto3
        table = os.getenv("HITL_TABLE", "")
        if table:
            boto3.resource("dynamodb").Table(table).put_item(Item={
                "doc_id": doc_id, "task_token": task_token, "reason": reason,
                "status": "PENDING_REVIEW",
            })
        return {"queued": True, "doc_id": doc_id}
    except Exception as exc:  # pragma: no cover - requires AWS
        return {"queued": False, "doc_id": doc_id, "error": type(exc).__name__}
