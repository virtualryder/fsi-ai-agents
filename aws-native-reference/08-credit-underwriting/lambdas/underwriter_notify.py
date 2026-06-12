"""Underwriter/compliance review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event)
    token = event.get("task_token", "")
    app_id = payload.get("application", {}).get("application_id")
    try:
        import boto3
        table = os.getenv("HITL_TABLE", "")
        if table:
            boto3.resource("dynamodb").Table(table).put_item(Item={
                "application_id": app_id, "task_token": token,
                "tier": payload.get("evaluation", {}).get("tier"), "status": "PENDING_REVIEW"})
        return {"queued": True, "application_id": app_id}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "application_id": app_id, "error": type(exc).__name__}
