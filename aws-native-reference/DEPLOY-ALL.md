# Deploy All 12 Agents on AWS

End-to-end rollout of every agent's runtime container. Each agent is independent;
deploy any subset (the pilot wedge is 09 → 02 → 01). Per-agent specifics are in
each folder's `DEPLOY.md`.

## Prerequisites

- AWS account + credentials that can create ECR, ECS/Fargate (or AgentCore
  Runtime), DynamoDB, S3, IAM, and Bedrock resources.
- Docker with **buildx** (ARM64), Terraform ≥ 1.5, the AWS CLI.
- **Amazon Bedrock model access** enabled for your Claude model id.
- (Recommended) the suite's shared infra from `infra/terraform/` (VPC with
  private subnets + Bedrock VPC endpoint, KMS, Cognito/Okta, append-only audit,
  S3 Object Lock) — the runtime module consumes those outputs.

## 1. Build + push all images (ARM64)

```bash
AWS_REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/fsi-agents
aws ecr create-repository --repository-name fsi-agents 2>/dev/null || true
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR

# from the repo root:
for KEY in 01-financial-crime-investigation 02-aml-tms-enhancement 03-kyc-cdd-perpetual \
           04-fraud-detection 05-wealth-rm-copilot 06-regulatory-change \
           07-trading-surveillance 08-credit-underwriting 09-document-intelligence \
           10-payments-compliance 11-model-risk 12-collections-recovery; do
  docker buildx build --platform linux/arm64 \
    -f aws-native-reference/$KEY/Dockerfile -t $ECR:$KEY --push .
done
```

## 2a. Deploy on Bedrock AgentCore Runtime (managed)

```bash
pip install bedrock-agentcore-starter-toolkit
for KEY in 09-document-intelligence 02-aml-tms-enhancement 01-financial-crime-investigation; do
  agentcore configure --entrypoint serve:app --container $ECR:$KEY --name fsi-$KEY
  agentcore launch
done
```

## 2b. Or deploy on ECS Fargate (Terraform, per agent)

```bash
cd aws-native-reference/_shared/infra/agent_runtime
for KEY in 09-document-intelligence 02-aml-tms-enhancement 01-financial-crime-investigation; do
  terraform workspace new $KEY 2>/dev/null || terraform workspace select $KEY
  terraform apply -var="agent_key=$KEY" -var="image_uri=$ECR:$KEY" \
    -var='vpc_subnet_ids=["subnet-aaa","subnet-bbb"]' \
    -var="audit_table_arn=arn:aws:dynamodb:$AWS_REGION:$ACCOUNT:table/$KEY" \
    -var='bedrock_model_arns=["arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-20250514-v1:0"]'
done
```

## 3. Smoke test each agent

```bash
# locally per agent (no AWS):
docker run --rm -p 8080:8080 -e AGENT=$KEY -e LLM_PROVIDER=anthropic $ECR:$KEY &
curl localhost:8080/ping                                   # {"status":"Healthy"}
curl -XPOST localhost:8080/invocations -H 'content-type: application/json' \
  -d "{\"input\": $(cat aws-native-reference/$KEY/sample_input.json)}"
```

## Production hardening

Use the checklist in
[`09-document-intelligence/DEPLOYMENT-RUNBOOK.md`](./09-document-intelligence/DEPLOYMENT-RUNBOOK.md):
private subnets + Bedrock VPC endpoint, KMS, S3 Object Lock COMPLIANCE, required
Guardrails, Cognito/Okta auth, the MCP authorization gateway in front of tool
calls, CloudWatch/X-Ray, CloudTrail/GuardDuty, and the integration-test harness.

## Notes

- `CONNECTOR_MODE=fixture` by default; switch to `live` (with the connector
  endpoint env vars) to reach real systems of record.
- The container runs each agent **to completion** and reports
  `human_review_required` in the output; the actual human pause/resume is owned
  by the orchestration layer (Step Functions `waitForTaskToken` in the native
  rebuild) or the agent's review UI — not the stateless container.
