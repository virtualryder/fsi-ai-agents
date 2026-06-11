"""HITL resume — reviewer submits a decision; resume the paused state machine.

The HumanReviewGate state runs with `.waitForTaskToken`, pausing the workflow
(the AWS-native equivalent of LangGraph `interrupt_before`). The review UI/API
calls this with the task token and the reviewer's verified decision; we resume
via SendTaskSuccess (or SendTaskFailure on reject). The reviewer's identity is
carried into the resumed state for the audit trail.
"""
from __future__ import annotations
from . import _shared  # noqa: F401
import json
import os


def handler(event, context=None):
    task_token = event["task_token"]
    decision = event.get("decision", "approve")
    reviewer = event.get("reviewer", {})  # {sub, email} — verified upstream
    try:
        import boto3
        sfn = boto3.client("stepfunctions", region_name=os.getenv("AWS_REGION", "us-east-1"))
        if decision == "reject":
            sfn.send_task_failure(taskToken=task_token, error="ReviewerRejected",
                                  cause=json.dumps({"reviewer": reviewer}))
            return {"resumed": True, "decision": "reject"}
        sfn.send_task_success(taskToken=task_token,
                              output=json.dumps({"reviewer_decision": decision, "reviewer": reviewer}))
        return {"resumed": True, "decision": decision}
    except Exception as exc:  # pragma: no cover - requires AWS in real use
        return {"resumed": False, "error": type(exc).__name__, "detail": str(exc)}
