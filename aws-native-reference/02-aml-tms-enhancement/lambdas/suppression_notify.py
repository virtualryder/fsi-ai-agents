"""Suppression review gate notifier (waitForTaskToken).

SUPPRESS removes an alert from the analyst queue, so it routes here: a BSA
Officer samples/approves the suppression (the 90-day suppression review made a
framework-enforced gate). Persists the task token + queues the suppression.
"""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event)
    token = event.get("task_token", "")
    alert_id = payload.get("alert", {}).get("alert_id")
    try:
        import boto3
        table = os.getenv("HITL_TABLE", "")
        if table:
            boto3.resource("dynamodb").Table(table).put_item(Item={
                "alert_id": alert_id, "task_token": token,
                "deterministic_fp": str(payload.get("routing", {}).get("deterministic_fp_score")),
                "status": "PENDING_SUPPRESSION_REVIEW",
            })
        return {"queued": True, "alert_id": alert_id}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "alert_id": alert_id, "error": type(exc).__name__}
