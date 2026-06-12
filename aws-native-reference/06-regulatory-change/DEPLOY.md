# Deploy — Regulatory Change Management (`06-regulatory-change`)

AWS-native deployment of this agent by **containerizing its existing LangGraph
graph** and running it on **Amazon Bedrock AgentCore Runtime** (or ECS Fargate).
The agent's deterministic gates, HITL logic, and regulatory controls are
unchanged — only the host changes. Inference runs in-account via Amazon Bedrock
(with Guardrails); the shared runtime is in [`../_shared/`](../_shared/).

> **This agent also has a full native rebuild** in this folder (`core.py`, `strands_agent.py`, `stepfunctions/`, `lambdas/`, `infra/`, `tests/`) using **Strands + Step Functions** with a `waitForTaskToken` HITL gate — see [`README.md`](./README.md). This container path is the lift-and-shift alternative.

## 1. Build the ARM64 image (from the repo root)

```bash
aws ecr create-repository --repository-name fsi-agents 2>/dev/null || true
AWS_REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/fsi-agents
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR

docker buildx build --platform linux/arm64 \
  -f aws-native-reference/06-regulatory-change/Dockerfile -t $ECR:06-regulatory-change --push .
```

## 2a. Deploy on Bedrock AgentCore Runtime (managed)

```bash
# Using the AgentCore starter toolkit (pip install bedrock-agentcore-starter-toolkit):
agentcore configure --entrypoint serve:app --container $ECR:06-regulatory-change --name fsi-06-regulatory-change
agentcore launch                 # creates the AgentCore Runtime from the ARM64 image
agentcore invoke '{"change_id": "REG-1", "source": "FinCEN", "title": "New CDD guidance"}'      # test /invocations through the runtime
```

AgentCore Runtime provides managed identity (AgentCore Identity), session
isolation, and observability out of the box. The image already satisfies the
runtime contract (POST `/invocations`, GET `/ping`, port 8080).

## 2b. Or deploy on ECS Fargate (Terraform)

```bash
cd aws-native-reference/_shared/infra/agent_runtime
terraform init
terraform apply \
  -var="agent_key=06-regulatory-change" \
  -var="image_uri=$ECR:06-regulatory-change" \
  -var='vpc_subnet_ids=["subnet-aaa","subnet-bbb"]' \
  -var="audit_table_arn=arn:aws:dynamodb:$AWS_REGION:$ACCOUNT:table/06-regulatory-change" \
  -var='bedrock_model_arns=["arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-20250514-v1:0"]'
# see deploy.auto.tfvars in this folder for the full variable set
```

## 3. Smoke test

```bash
# locally (no AWS): run the container and hit the contract endpoints
docker run --rm -p 8080:8080 -e AGENT=06-regulatory-change -e LLM_PROVIDER=anthropic $ECR:06-regulatory-change &
curl localhost:8080/ping
curl -XPOST localhost:8080/invocations -H 'content-type: application/json' \
  -d '{"input": {"change_id": "REG-1", "source": "FinCEN", "title": "New CDD guidance"}}'
```

`/ping` returns `{"status":"Healthy"}`. `/invocations` runs the agent graph and
returns `{"agent":"06-regulatory-change","status":"OK","output":{...}}`, where `output`
carries the agent's final state including `human_review_required`.

## Notes

- The sample input above is illustrative; the authoritative input shape is this
  agent's `agent/state.py` and `app.py` in [`../../06-regulatory-change-agent`](../../06-regulatory-change-agent).
- `CONNECTOR_MODE=fixture` by default; set `live` (and the connector endpoint
  env vars) to reach real systems of record via the connector layer.
- For governed tool access, route the agent's system-of-record calls through the
  MCP gateway (`platform_core/.../mcp_gateway`). Human review/pause-resume is
  owned by the orchestration layer, not the stateless container.
