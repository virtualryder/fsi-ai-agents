# AWS-Native Reference Deployments

AWS-native deployment of every agent in the suite. The goal is **"keep
LangGraph, add AWS-native deployment and governance"** — not a rewrite. Each
agent gets its own folder with a Dockerfile, Terraform vars, a sample input, and
a step-by-step `DEPLOY.md`. The reusable engine lives in [`_shared/`](./_shared/).

## Two paths to AWS (per agent)

1. **Lift the LangGraph agent onto AWS** (all 12) — containerize the agent's
   existing compiled graph and run it on **Amazon Bedrock AgentCore Runtime**
   (or ECS Fargate). Implements the AgentCore container contract (`/invocations`,
   `/ping`, port 8080, ARM64). Inference runs in-account via **Amazon Bedrock**
   with **Guardrails**. Fastest route to AWS; the agent code is unchanged.
2. **Native rebuild** (Agent 09 reference) — the deterministic core in Lambdas +
   **Strands Agents SDK** drafting on Bedrock + **Step Functions** orchestration
   with a `waitForTaskToken` HITL gate. Highest fidelity to the managed,
   serverless target. **Available for ALL 12 agents.** Every agent ships both the container lift-and-shift path and a Strands + Step Functions native rebuild (deterministic core in Lambdas, Bedrock drafting, and a `waitForTaskToken` human gate). — see each agent's `README.md`. 

## Agent registry

| Agent | Folder | Source agent | Paths available |
|---|---|---|---|
| 01 · Financial Crime Investigation | [`01-financial-crime-investigation/`](./01-financial-crime-investigation/) | `01-financial-crime-investigation-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 02 · AML/TMS Enhancement | [`02-aml-tms-enhancement/`](./02-aml-tms-enhancement/) | `02-aml-tms-enhancement-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 03 · KYC/CDD Perpetual | [`03-kyc-cdd-perpetual/`](./03-kyc-cdd-perpetual/) | `03-kyc-cdd-perpetual-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 04 · Fraud Detection | [`04-fraud-detection/`](./04-fraud-detection/) | `04-fraud-detection-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 05 · Wealth & RM Copilot | [`05-wealth-rm-copilot/`](./05-wealth-rm-copilot/) | `05-wealth-rm-copilot` | **Container + Native rebuild (Strands + Step Functions)** |
| 06 · Regulatory Change | [`06-regulatory-change/`](./06-regulatory-change/) | `06-regulatory-change-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 07 · Trading Surveillance | [`07-trading-surveillance/`](./07-trading-surveillance/) | `07-trading-surveillance-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 08 · Credit Underwriting | [`08-credit-underwriting/`](./08-credit-underwriting/) | `08-credit-underwriting-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 09 · Document Intelligence | [`09-document-intelligence/`](./09-document-intelligence/) | `09-document-intelligence-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 10 · Payments Compliance | [`10-payments-compliance/`](./10-payments-compliance/) | `10-payments-compliance-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 11 · Model Risk Management | [`11-model-risk/`](./11-model-risk/) | `11-model-risk-agent` | **Container + Native rebuild (Strands + Step Functions)** |
| 12 · Collections & Recovery | [`12-collections-recovery/`](./12-collections-recovery/) | `12-collections-recovery-agent` | **Container + Native rebuild (Strands + Step Functions)** |

## Deploy

- One agent: open its folder and follow `DEPLOY.md`.
- All agents: see [`DEPLOY-ALL.md`](./DEPLOY-ALL.md).

## Maturity

The container kit is **Demonstrated** (all 12 agents load and run through the
shared runtime, verified in CI without AWS) and **Deployable-by-design** (ARM64
Dockerfiles + reusable Terraform + AgentCore steps). It becomes *Deployed* once
an account builds/pushes the images and applies the IaC. Live Bedrock inference,
a deployed environment, and a penetration test are the engagement's steps.
