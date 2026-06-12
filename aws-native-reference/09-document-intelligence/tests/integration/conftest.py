"""
Integration-test gate (Phase 3) — these run ONLY against a deployed environment.

They are skipped unless RUN_AWS_INTEGRATION is truthy AND boto3 is importable AND
the required environment is configured. This keeps them CI-safe (they collect and
skip with no AWS account) while being ready to run, unchanged, after
`terraform apply` (see ../DEPLOYMENT-RUNBOOK.md).

Required env (emit these from Terraform outputs):
    RUN_AWS_INTEGRATION=1
    AWS_REGION                       e.g. us-east-1
    DOCINTEL_STATE_MACHINE_ARN       output: state_machine_arn
    DOCINTEL_AUDIT_TABLE             the agent's append-only audit table
    DOCINTEL_HITL_TABLE              output: hitl_table
    DOCINTEL_AUDIT_BUCKET            the S3 Object Lock (WORM) audit bucket  [optional checks]
    DOCINTEL_GUARDRAIL_ID            the Bedrock guardrail id                [optional checks]
"""
from __future__ import annotations

import os

import pytest


def _enabled() -> bool:
    return os.getenv("RUN_AWS_INTEGRATION", "").strip().lower() in ("1", "true", "yes")


def _require(*env_keys):
    missing = [k for k in env_keys if not os.getenv(k)]
    if missing:
        pytest.skip(f"integration env not set: {', '.join(missing)}")


@pytest.fixture(scope="session")
def aws():
    """Session AWS clients, or skip if integration is not enabled/available."""
    if not _enabled():
        pytest.skip("AWS integration disabled (set RUN_AWS_INTEGRATION=1 against a deployed env)")
    try:
        import boto3  # noqa: F401
    except Exception:
        pytest.skip("boto3 not installed")
    import boto3
    region = os.getenv("AWS_REGION", "us-east-1")
    return {
        "region": region,
        "sfn": boto3.client("stepfunctions", region_name=region),
        "ddb": boto3.client("dynamodb", region_name=region),
        "s3": boto3.client("s3", region_name=region),
        "bedrock": boto3.client("bedrock", region_name=region),
    }


@pytest.fixture(scope="session")
def cfg():
    return {
        "state_machine_arn": os.getenv("DOCINTEL_STATE_MACHINE_ARN", ""),
        "audit_table": os.getenv("DOCINTEL_AUDIT_TABLE", ""),
        "hitl_table": os.getenv("DOCINTEL_HITL_TABLE", ""),
        "audit_bucket": os.getenv("DOCINTEL_AUDIT_BUCKET", ""),
        "guardrail_id": os.getenv("DOCINTEL_GUARDRAIL_ID", ""),
    }


@pytest.fixture()
def require(cfg):
    return _require
