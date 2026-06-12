# Integration Tests (deployed-environment)

These run **only** against a deployed AWS environment and are **skipped by
default** so they are safe in CI and on a laptop with no account.

## Run

```bash
# after `terraform apply` (see ../../DEPLOYMENT-RUNBOOK.md), export the outputs:
export RUN_AWS_INTEGRATION=1
export AWS_REGION=us-east-1
export DOCINTEL_STATE_MACHINE_ARN=$(terraform -chdir=../../infra output -raw state_machine_arn)
export DOCINTEL_HITL_TABLE=$(terraform -chdir=../../infra output -raw hitl_table)
export DOCINTEL_AUDIT_TABLE=fsi-docintel-dev-audit
# optional: DOCINTEL_AUDIT_BUCKET, DOCINTEL_GUARDRAIL_ID

pytest tests/integration -v
```

Without `RUN_AWS_INTEGRATION` (or without boto3 / required env), every test
skips — verify with `pytest tests/integration -q` (expect all skipped).

## What they check

| File | Verifies (in a live account) |
|---|---|
| `test_deployed_pipeline.py` | clean doc → SUCCEEDED auto-route; SAR/PII doc → pauses at the `waitForTaskToken` HITL gate + token queued; raw SSN never in execution history |
| `test_audit_immutability.py` | audit DynamoDB is append-only (overwrite rejected, delete denied); audit S3 bucket has Object Lock COMPLIANCE |
| `test_guardrails_and_identity.py` | a Bedrock Guardrail exists with a PII/content policy; the deployed state machine still contains its HITL gate |

These are the runtime proofs of the controls the Terraform expresses and the
local tests assert in demo mode.
