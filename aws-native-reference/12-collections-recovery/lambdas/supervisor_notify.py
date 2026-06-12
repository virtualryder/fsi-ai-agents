"""Supervisor/compliance review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    aid = payload.get("account", {}).get("account_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "account_id": aid, "task_token": token,
                "conditions": "; ".join(payload.get("assessment", {}).get("hitl_conditions", [])),
                "status": "PENDING_REVIEW"})
        return {"queued": True, "account_id": aid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "account_id": aid, "error": type(exc).__name__}
