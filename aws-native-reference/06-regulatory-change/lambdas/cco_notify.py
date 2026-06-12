"""CCO review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    cid = payload.get("change", {}).get("change_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "change_id": cid, "task_token": token,
                "tier": payload.get("impact", {}).get("tier"), "status": "PENDING_CCO_REVIEW"})
        return {"queued": True, "change_id": cid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "change_id": cid, "error": type(exc).__name__}
