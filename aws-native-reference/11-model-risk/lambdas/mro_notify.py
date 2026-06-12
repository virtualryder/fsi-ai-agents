"""Model Risk Officer / CRO review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    mid = payload.get("model", {}).get("model_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "model_id": mid, "task_token": token,
                "reviewer": payload.get("validation", {}).get("reviewer"), "status": "PENDING_REVIEW"})
        return {"queued": True, "model_id": mid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "model_id": mid, "error": type(exc).__name__}
