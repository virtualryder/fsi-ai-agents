# Deployment Runbook — AWS-Native Document Intelligence (Agent 09)

How an engagement takes this reference from repo to a running, governed
deployment in a customer's AWS account, and verifies the controls with the
integration-test harness. Demo mode lets you stand up the entire state machine
and exercise the HITL flow **before** enabling live Bedrock inference, so the
first deploy is low-risk.

**Audience:** delivery engineer / cloud architect. **Time:** ~2–4 hours first run.
**Positioning:** this makes the agent *Deployed*; it does not by itself make the
suite a production-regulated platform — the production-hardening checklist below
and the customer's own AWS posture do.

---

## 0. Prerequisites

- An AWS account (ideally the customer's, single-tenant) and credentials with
  permission to create IAM, Lambda, Step Functions, DynamoDB, S3, and Bedrock
  resources. Use a dedicated deploy role, not a personal admin.
- Terraform ≥ 1.5 and Python ≥ 3.11 locally.
- **Amazon Bedrock model access enabled** for the Claude model you will use
  (Console → Bedrock → Model access). Until then, run in `extract_mode=demo`.
- Decide the region (default `us-east-1`) and environment name (`dev`).

---

## 1. Enable Bedrock model access (one-time, per account/region)

Console → Amazon Bedrock → **Model access** → enable the Claude model id you will
pass as `bedrock_model_id` (default `us.anthropic.claude-sonnet-4-20250514-v1:0`).
Skip if you will only run demo mode at first.

## 2. Deploy in demo mode first (no live inference)

```bash
cd aws-native-reference/09-document-intelligence/infra
terraform init
terraform plan  -var="environment=dev" -var="extract_mode=demo"
terraform apply -var="environment=dev" -var="extract_mode=demo"
```

This provisions the six Lambdas, the state machine, the append-only DynamoDB
tables, and least-privilege IAM. `extract_mode=demo` makes the Extract Lambda
return deterministic stubs, so you can validate the whole pipeline and the HITL
gate with **zero Bedrock dependency**.

> If `terraform validate`/`apply` complains about the `archive` provider, run
> `terraform init -upgrade` (it is declared in `infra/main.tf`).

## 3. Capture outputs → export integration env

```bash
terraform output                       # state_machine_arn, hitl_table, lambda_function_names
export AWS_REGION=us-east-1
export DOCINTEL_STATE_MACHINE_ARN=$(terraform output -raw state_machine_arn)
export DOCINTEL_HITL_TABLE=$(terraform output -raw hitl_table)
export DOCINTEL_AUDIT_TABLE="fsi-docintel-dev-audit"   # from the audit table name
# Optional (enable the WORM/guardrail checks once configured):
# export DOCINTEL_AUDIT_BUCKET=...      DOCINTEL_GUARDRAIL_ID=...
export RUN_AWS_INTEGRATION=1
```

## 4. Smoke test the state machine

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$DOCINTEL_STATE_MACHINE_ARN" \
  --input '{"document":{"doc_id":"smoke-1","text":"FORM 1003 Uniform Residential Loan Application borrower loan_amount 250000"}}'
# describe-execution should reach SUCCEEDED with human_review_required=false
```

## 5. Exercise the HITL gate (waitForTaskToken)

Submit a sensitive document (always-HITL type) and confirm the execution
**pauses**:

```bash
aws stepfunctions start-execution --state-machine-arn "$DOCINTEL_STATE_MACHINE_ARN" \
  --input '{"document":{"doc_id":"sar-1","text":"FinCEN SAR suspicious activity report"}}'
# status stays RUNNING; a row appears in the HITL table with a task_token
```

Resume as a reviewer would (the review UI/API calls this in production):

```bash
# approve:
aws stepfunctions send-task-success --task-token "<token-from-hitl-table>" \
  --task-output '{"reviewer_decision":"approve","reviewer":{"sub":"reviewer-1"}}'
# or reject:  aws stepfunctions send-task-failure --task-token "<token>" --error ReviewerRejected
```

The execution then proceeds to `Finalize` and SUCCEEDS. This is the AWS-native
equivalent of the LangGraph `interrupt_before` gate.

## 6. Run the integration-test harness

```bash
cd aws-native-reference/09-document-intelligence
pip install boto3 pytest
RUN_AWS_INTEGRATION=1 pytest tests/integration -v
```

The harness (skipped automatically without `RUN_AWS_INTEGRATION`) verifies, against
the deployed environment:

- a clean document auto-routes to SUCCEEDED; a SAR/PII document **pauses** at the
  HITL gate and queues a task token;
- raw SSN never appears in the execution history (masking holds end-to-end);
- the **audit table is append-only** (overwrite rejected; delete denied);
- the **audit S3 bucket has Object Lock COMPLIANCE** (when configured);
- the **Bedrock Guardrail exists** with a PII/content policy (when configured);
- the deployed state machine still contains its `waitForTaskToken` HITL gate.

## 7. Enable live Bedrock inference

Once model access is on and a guardrail exists:

```bash
terraform apply -var="environment=dev" -var="extract_mode=" \
  -var="guardrail_id=<bedrock-guardrail-id>"
```

`extract_mode=""` switches the Extract Lambda from demo stubs to real Strands +
Bedrock inference, wrapped by the guardrail.

---

## Production-hardening checklist (before customer production)

- [ ] Deploy into the customer account (single-tenant), not a shared sandbox.
- [ ] VPC: Lambdas in private subnets; Bedrock via VPC endpoint; no internet
      egress from compute (mirror `infra/terraform/modules/network`).
- [ ] KMS CMK encrypting DynamoDB, S3, and logs; key rotation on.
- [ ] S3 audit bucket created with **Object Lock COMPLIANCE** + retention per
      artifact class (BSA 5yr / FCRA 7yr / SR 11-7 10yr).
- [ ] Bedrock Guardrail required (`REQUIRE_BEDROCK_GUARDRAIL`/`ENVIRONMENT=production`).
- [ ] Cognito/Okta authentication in front of the review UI; `require_role`
      enforced on resume; reviewer identity bound into the audit.
- [ ] Route real tool calls through the **MCP authorization gateway**
      (`platform_core/.../mcp_gateway`) — scoped tokens, least privilege, audit.
- [ ] CloudWatch alarms + X-Ray tracing (ADOT) on the state machine and Lambdas.
- [ ] CloudTrail on; GuardDuty/Security Hub enabled.
- [ ] pip-audit / SBOM / Checkov gates green in the deploy pipeline.
- [ ] DR: cross-region plan per `runbooks/DR-RUNBOOK.md`; restore tested.
- [ ] Run the integration harness in the target account; all checks green.

## Rollback / teardown

```bash
# rollback inference only (keep infra): re-apply with extract_mode=demo
terraform apply -var="environment=dev" -var="extract_mode=demo"

# full teardown of the reference (dev):
terraform destroy -var="environment=dev"
```

> The audit S3 bucket, if created with Object Lock COMPLIANCE and active
> retention, **cannot be deleted until retention expires** — by design (WORM).
> Plan dev/test buckets with short or GOVERNANCE-mode retention; use COMPLIANCE
> only where regulatory retention is intended.

## Cost notes (order-of-magnitude, dev)

Step Functions standard executions, six small Lambdas, two on-demand DynamoDB
tables, and S3 are cents-to-low-dollars per day at demo volume. **Bedrock
inference dominates** once live and scales with document volume × tokens — tune
model tiering (Haiku for triage, Sonnet for narrative) to control it. Get a
per-volume estimate from `offerings/COST-ROI-MODEL.md`.

## Troubleshooting

- **Execution fails at Extract in demo:** ensure `extract_mode=demo` env var is
  set on the Lambda (Terraform `extract_mode` variable).
- **HITL never resumes:** the token lives in the HITL table; confirm the review
  path calls `send-task-success` with that exact token before the
  `TimeoutSeconds` (default 7 days) elapses.
- **AccessDenied on audit write:** expected for delete/update (PutItem-only role)
  — that is the append-only control working.
- **Guardrail check fails:** confirm `guardrail_id` was passed on apply and the
  guardrail status is READY.
