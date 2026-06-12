# Deploy — Financial Crime Investigation (SAR) (`01-financial-crime-investigation`)

AWS-native deployment of this agent by **containerizing its existing LangGraph
graph** and running it on **Amazon Bedrock AgentCore Runtime** (or ECS Fargate).
The agent's deterministic gates, HITL logic, and regulatory controls are
unchanged — only the host changes. Inference runs in-account via Amazon Bedrock
(with Guardrails); the shared runtime is in [`../_shared/`](../_shared/).

## 1. Build the ARM64 image (from the repo root)

```bash
aws ecr create-repository --repository-name fsi-agents 2>/dev/null || true
AWS_REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/fsi-agents
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR

docker buildx build --platform linux/arm64 \
  -f aws-native-reference/01-financial-crime-investigation/Dockerfile -t $ECR:01-financial-crime-investigation --push .
```

## 2a. Deploy on Bedrock AgentCore Runtime (managed)

```bash
# Using the AgentCore starter toolkit (pip install bedrock-agentcore-starter-toolkit):
agentcore configure --entrypoint serve:app --container $ECR:01-financial-crime-investigation --name fsi-01-financial-crime-investigation
agentcore launch                 # creates the AgentCore Runtime from the ARM64 image
agentcore invoke '{"alert_id": "ALERT-1001", "alert_type": "STRUCTURING", "customer_id": "CUST-001"}'      # test /invocations through the runtime
```

AgentCore Runtime provides managed identity (AgentCore Identity), session
isolation, and observability out of the box. The image already satisfies the
runtime contract (POST `/invocations`, GET `/ping`, port 8080).

## 2b. Or deploy on ECS Fargate (Terraform)

```bash
cd aws-native-reference/_shared/infra/agent_runtime
terraform init
terraform apply \
  -var="agent_key=01-financial-crime-investigation" \
  -var="image_uri=$ECR:01-financial-crime-investigation" \
  -var='vpc_subnet_ids=["subnet-aaa","subnet-bbb"]' \
  -var="audit_table_arn=arn:aws:dynamodb:$AWS_REGION:$ACCOUNT:table/01-financial-crime-investigation" \
  -var='bedrock_model_arns=["arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-20250514-v1:0"]'
# see deploy.auto.tfvars in this folder for the full variable set
```

## 3. Smoke test

```bash
# locally (no AWS): run the container and hit the contract endpoints
docker run --rm -p 8080:8080 -e AGENT=01-financial-crime-investigation -e LLM_PROVIDER=anthropic $ECR:01-financial-crime-investigation &
curl localhost:8080/ping
curl -XPOST localhost:8080/invocations -H 'content-type: application/json' \
  -d '{"input": {"alert_id": "ALERT-1001", "alert_type": "STRUCTURING", "customer_id": "CUST-001"}}'
```

`/ping` returns `{"status":"Healthy"}`. `/invocations` runs the agent graph and
returns `{"agent":"01-financial-crime-investigation","status":"OK","output":{...}}`, where `output`
carries the agent's final state including `human_review_required`.

## Notes

- The sample input above is illustrative; the authoritative input shape is this
  agent's `agent/state.py` and `app.py` in [`../../01-financial-crime-investigation-agent`](../../01-financial-crime-investigation-agent).
- `CONNECTOR_MODE=fixture` by default; set `live` (and the connector endpoint
  env vars) to reach real systems of record via the connector layer.
- For governed tool access, route the agent's system-of-record calls through the
  MCP gateway (`platform_core/.../mcp_gateway`). Human review/pause-resume is
  owned by the orchestration layer, not the stateless container.
