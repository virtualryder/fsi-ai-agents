# Shared AWS-Native Runtime (`_shared/`)

The reusable engine behind every per-agent folder, so the container runtime and
IaC are written once, not 12 times.

## `runtime/`
- **`handler.py`** — registry of all 12 agents and `build_for(key)` / `invoke()` /
  `handle_invocation()`. Loads any agent's existing compiled LangGraph graph
  (run-to-completion build; HITL surfaces in the output). Honors `FSI_REPO_ROOT`
  so it works both in-repo and in a container.
- **`serve.py`** — FastAPI server implementing the **Amazon Bedrock AgentCore
  Runtime contract**: `POST /invocations`, `GET /ping`, port **8080**. Also runs
  on ECS Fargate or locally (it's a plain HTTP server).
- **`Dockerfile`** — shared ARM64 base (AgentCore requires Graviton/ARM64).

## `infra/agent_runtime/`
A reusable Terraform module that deploys **one** agent's runtime container on
ECS Fargate with least-privilege IAM, in-account Bedrock invoke + Guardrails,
and append-only audit. Instantiate once per agent (`-var agent_key=...`). The
same image also deploys to AgentCore Runtime via the AgentCore toolkit — see any
agent's `DEPLOY.md`.

## `tests/`
`test_runtime.py` proves the container can host **every** agent (all 12 graphs
build through the handler) and that the `/invocations` + `/ping` envelope is
correct — run in CI without AWS.

## Two AWS-native paths (per agent)

| Path | What | When |
|---|---|---|
| **Lift the LangGraph agent** (this kit) | containerize the existing graph; run on AgentCore Runtime / Fargate; Bedrock inference + Guardrails; identity + audit | every agent, fastest route to AWS; keeps LangGraph |
| **Native rebuild** (Agents 01-05, 08, 09, 10) | deterministic core in Lambdas + Strands drafting + Step Functions HITL | when you want managed orchestration, durable `waitForTaskToken` HITL, per-node scaling |

Both preserve the thesis — deterministic Python decides, the model drafts,
humans are accountable — and map to the same AWS services.
