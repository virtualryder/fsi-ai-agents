"""Compliance officer review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    aid = payload.get("alert", {}).get("alert_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "alert_id": aid, "task_token": token,
                "tier": payload.get("scoring", {}).get("tier"), "status": "PENDING_REVIEW"})
        return {"queued": True, "alert_id": aid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "alert_id": aid, "error": type(exc).__name__}
