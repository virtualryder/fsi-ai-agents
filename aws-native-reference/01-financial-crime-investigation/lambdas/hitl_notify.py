"""HITL gate notifier (waitForTaskToken). Persists the token + notifies the BSA queue."""
from . import _shared  # noqa: F401
import os


def handler(event, context=None):
    payload = event.get("input", event)
    token = event.get("task_token", "")
    case_id = payload.get("case", {}).get("case_id")
    try:
        import boto3
        table = os.getenv("HITL_TABLE", "")
        if table:
            boto3.resource("dynamodb").Table(table).put_item(Item={
                "case_id": case_id, "task_token": token,
                "decision": payload.get("routing", {}).get("decision"), "status": "PENDING_REVIEW",
            })
        return {"queued": True, "case_id": case_id}
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "case_id": case_id, "error": type(exc).__name__}
