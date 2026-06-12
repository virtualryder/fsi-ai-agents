"""Compliance Officer review gate notifier (waitForTaskToken)."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event); token = event.get("task_token", "")
    cid = payload.get("customer", {}).get("customer_id")
    try:
        import boto3
        t = os.getenv("HITL_TABLE", "")
        if t:
            boto3.resource("dynamodb").Table(t).put_item(Item={
                "customer_id": cid, "task_token": token,
                "outcome": payload.get("rescore", {}).get("outcome"), "status": "PENDING_REVIEW"})
        return {"queued": True, "customer_id": cid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "customer_id": cid, "error": type(exc).__name__}
