# Agentic AI Managed Service — Offering Definition

**Term:** 12-month minimum, annual renewal · **Pricing:** monthly platform fee + per-agent operations fee + pass-through AWS · **Team:** named delivery lead + shared SRE/compliance-ops pool · **Model:** Presidio operates the agents in the client's AWS account

For institutions that want the outcomes of agentic AI without standing up a team to run prompts, model validations, regulatory updates, and incident response. This is the offering that expands the deal beyond a one-time build and the one most often missing from an SI's FSI motion.

## The problem it solves

After a pilot and scale-out, *someone* has to operate the system: monitor model drift, run SR 11-7 revalidations, update prompts and policy mappings as regulations change, manage the HITL queues' health, run incident and DR procedures, and keep the governance harness green. Many institutions don't want to hire that team. This offering provides it as a managed service — in their account, under their controls.

## Engagement models (pick one)

| Model | Who operates what | Best for |
|---|---|---|
| **Fully managed** | Presidio operates all deployed agents end-to-end; client provides reviewers for HITL gates | Institutions with no AI-platform team |
| **Co-managed (recommended)** | Presidio operates the platform, governance, and lower-sensitivity agents (e.g., 09, 06, 02); client operates the highest-stakes agents (e.g., 01 SAR, 08 credit) in-house | Most mid-market institutions |
| **Platform-only** | Presidio keeps the platform, IaC, governance harness, and runbooks healthy; client operates all agents | Institutions with their own ops team that want vendor backstop |

Human approval at every regulated gate **always remains the client's** — Presidio operates the system; the client's named officers make and own the regulated decisions.

## What's included

- **Run & monitor:** agent services, HITL queue health, CloudWatch/X-Ray dashboards and alarms, on-call for defined severities.
- **Model governance as a service:** scheduled SR 11-7 revalidations (the Agent 11 pattern), prompt-version management with the manifest gate, grounding/fairness/eval runs on every change, a quarterly model-risk report.
- **Regulatory currency:** prompt and policy-mapping updates as monitored regulations change (the Agent 06 capability, operated for the client).
- **Incident & resilience:** incident response, DR exercises, and post-incident reviews per the `runbooks/`.
- **Security upkeep:** dependency/SBOM scanning, IaC drift checks, guardrail and least-privilege posture maintenance, support for the client's TPRM and audit cycles.
- **Change management:** new connectors, new agents, and tuning delivered as scoped change requests.

## What stays with the client

Regulated decisions and HITL approvals · ownership of the AWS account, data, and audit trail · final say on thresholds and policy · their examiner relationships. Presidio operates; the client governs.

## Service levels (illustrative — set per contract)

| Dimension | Illustrative target |
|---|---|
| Platform availability | 99.9% (inherits client AWS multi-AZ posture) |
| Sev-1 (control failure / examinable artifact affected) response | ≤ 30 min, compliance in the room from minute zero |
| Model-degradation investigation start (PSI/agreement breach) | ≤ 1 business day |
| Prompt/policy update for a material regulatory change | ≤ 5 business days from publication |
| Quarterly model-risk + operations report | Every quarter |
| HITL queue SLA monitoring | Per `runbooks/HITL-QUEUE-OPERATIONS.md` thresholds |

## Pricing structure

- **Monthly platform fee** — governance harness, IaC upkeep, monitoring, on-call, reporting (fixed).
- **Per-agent operations fee** — scales with the number and sensitivity of deployed agents.
- **Pass-through AWS** — the client's account, billed to the client; Presidio optimizes model tiering and infra to control it.
- **Change requests** — new connectors/agents/tuning, scoped and quoted.

Anchor the fee against the client's alternative: the fully-loaded cost of the 2–4 FTE platform/ML-ops/compliance-ops team they would otherwise hire and retain — typically well above the managed fee, without the key-person risk.

## Why this matters to the GTM motion

It converts a one-time delivery into **recurring revenue**, deepens the account, and — critically — lets Presidio sell to **smaller institutions** that could never staff an AI-platform team ("we'll run 09 + 02 for you; you operate 01"). It is the natural Phase-3+ continuation after pilot and scale-out.

## Qualification

Best after a successful pilot or scale-out, when there's a running system to operate. Requires: a client executive owner for the service relationship, named client officers for HITL gates, and access to the client AWS account under agreed least-privilege roles.

## Honest-positioning rules

Presidio operates the platform; it does not assume the client's regulatory accountability. The managed service keeps the system healthy, current, and observable — the client's compliance program remains the client's. As everywhere in this repo: **accelerator operated to production standard**, with the controls verifiable in code and the run-book procedures executed, not asserted.
