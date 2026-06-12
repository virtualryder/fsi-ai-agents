"""RM approval gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    rid = payload.get("request", {}).get("request_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "request_id": rid, "task_token": token,
                "status_": payload.get("suitability", {}).get("status"), "status": "PENDING_RM_APPROVAL"})
        return {"queued": True, "request_id": rid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "request_id": rid, "error": type(exc).__name__}
