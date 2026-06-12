"""Analyst review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    tid = payload.get("transaction", {}).get("transaction_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "transaction_id": tid, "task_token": token,
                "composite": str(payload.get("decision", {}).get("composite_score")), "status": "PENDING_REVIEW"})
        return {"queued": True, "transaction_id": tid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "transaction_id": tid, "error": type(exc).__name__}
