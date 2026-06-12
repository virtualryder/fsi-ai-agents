"""HITL gate notifier (waitForTaskToken) — OFAC/SAR/unauthorized/high-value review."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event)
    token = event.get("task_token", "")
    pid = payload.get("payment_event", {}).get("payment_id")
    try:
        import boto3
        table = os.getenv("HITL_TABLE", "")
        if table:
            boto3.resource("dynamodb").Table(table).put_item(Item={
                "payment_id": pid, "task_token": token,
                "triggers": "; ".join(payload.get("routing", {}).get("triggers", [])),
                "status": "PENDING_REVIEW"})
        return {"queued": True, "payment_id": pid}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "payment_id": pid, "error": type(exc).__name__}
