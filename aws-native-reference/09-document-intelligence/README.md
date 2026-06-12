# AWS-Native Reference — Document Intelligence (Agent 09)

A second, AWS-native implementation of Agent 09 that preserves the suite thesis —
**deterministic Python decides and routes; the model only drafts; a human is
accountable at a framework-enforced gate** — using **Amazon Bedrock (via the
Strands Agents SDK)** for drafting and **AWS Step Functions** for orchestration
and the HITL pause.

This is a *reference implementation* that sits alongside the portable LangGraph
agent — not a replacement. Keep LangGraph for demos and portability; offer this
to AWS-first customers who want a managed runtime, managed identity, and
managed governance.

## Why Agent 09 first

Agent 09 is the suite's front door (every other agent consumes its output) and
has the lowest data sensitivity, so it is the right first pilot and the cleanest
AWS-native reference. The connector layer (Phase 2, workstream 1) makes its real
document intake straightforward to wire.

## Architecture

```
S3 (intake) ─▶ Step Functions state machine
                   │
                   ├─ PiiMask        (Lambda · deterministic · platform PII middleware)
                   ├─ Extract        (Lambda · Strands + Bedrock · LLM DRAFTING ONLY)
                   ├─ Validate       (Lambda · deterministic field/business rules)
                   ├─ Route          (Lambda · deterministic routing + HITL decision)
                   ├─ DispositionChoice (Choice on $.routing.next)
                   │      ├─ HumanReviewGate  (lambda:invoke.waitForTaskToken)  ◀── reviewer resumes
                   │      └─ AutoRoute         (Pass)
                   └─ Finalize       (Lambda · structured JSON + masked audit)
```

The model never sees unmasked PII and never decides routing or HITL. Those are
`core.py` (deterministic), faithful to the LangGraph agent's constants
(`CONFIDENCE_HITL_THRESHOLD = 0.65`; always-HITL types: government ID, SAR, CTR,
consent order; the six HITL triggers).

## The key mapping: `interrupt_before` → `waitForTaskToken`

| LangGraph (portable) | AWS-native (this reference) |
|---|---|
| `StateGraph` DAG | Step Functions state machine (ASL) |
| Node functions | Lambda task states |
| LLM node (`llm_factory`) | Strands `Agent` + `BedrockModel` (Extract Lambda) |
| `interrupt_before=["human_review_gate"]` | `HumanReviewGate` with `lambda:invoke.waitForTaskToken` |
| Resume via checkpointer | `SendTaskSuccess` / `SendTaskFailure` (`hitl_callback`) |
| Conditional edges | `Choice` state on `$.routing.next` |
| Append-only DynamoDB audit | Same (PutItem-only IAM) |
| Bedrock Guardrails | Same — attached on the `BedrockModel` when `BEDROCK_GUARDRAIL_ID` is set |
| OTel tracing | CloudWatch + X-Ray (Step Functions native) |

Both enforce the human gate at the **framework** level — neither lets
application or model output skip it. This reference deliberately mirrors the
Phase 1 control-integrity fix (Agent 01) on the AWS side.

## What is verified here vs. needs an AWS account

**Verified in CI (no AWS, no network):**
- The deterministic core (tiering, routing, all six HITL triggers, PII masking).
- The full Lambda pipeline in demo mode (`EXTRACT_MODE=demo`), including that the
  LLM/extraction layer emits no routing/HITL fields.
- The Step Functions ASL is structurally valid: every transition resolves, the
  Choice has a default, the HITL gate uses `waitForTaskToken` with the task
  token from `$$.Task.Token`, and exactly one terminal state.
- The Terraform parses (HCL2) and references the ASL template correctly.

**Needs an AWS account (the integrator's step):**
- `terraform init/validate/apply` (provider download + credentials).
- Real Bedrock inference (enable model access; unset `EXTRACT_MODE`).
- Live S3 intake, the review UI calling `hitl_callback`, and Bedrock Guardrails.

So on the maturity ladder this reference is **Demonstrated** (runs end-to-end on
fixtures/demo) and **Deployable-by-design** (IaC + ASL present); it becomes
*Deployed* once an account runs the Terraform.

## Run the demo (no AWS)

```bash
cd aws-native-reference/09-document-intelligence
EXTRACT_MODE=demo python -m pytest tests/ -q      # 20 tests
# or exercise the pipeline directly:
EXTRACT_MODE=demo python -c "
from lambdas import pii_mask, extract, validate, route, finalize
ev={'document':{'doc_id':'D1','text':'FinCEN SAR suspicious activity report'}}
for fn in (pii_mask.handler,extract.handler,validate.handler,route.handler,finalize.handler): ev=fn(ev)
print(ev['routing']['next'], ev['routing']['human_review_reason'])
"
```

## Deploy (with an AWS account)

Full step-by-step is in **[`DEPLOYMENT-RUNBOOK.md`](./DEPLOYMENT-RUNBOOK.md)** (prerequisites, demo-mode-first apply, HITL walkthrough, the integration-test harness in [`tests/integration/`](./tests/integration/), a production-hardening checklist, rollback/teardown, and cost notes). In short:


```bash
cd infra
terraform init
terraform apply -var="environment=dev" -var="extract_mode=demo"   # demo inference first
# then enable Bedrock model access, set guardrail_id, and re-apply with extract_mode=""
```

`extract_mode=demo` lets you stand up the whole state machine and exercise the
HITL flow before enabling live Bedrock inference — de-risking the first deploy.

## Tradeoffs (when to use which)

- **LangGraph** wins on portability, fast local iteration, and demo-without-an-
  account. Default for demos and MVPs.
- **This AWS-native path** wins on managed scaling, managed identity, native
  observability (CloudWatch/X-Ray), durable long-running HITL (a `waitForTaskToken`
  task can wait up to a year), and examiner-grade operability. Best for AWS-first
  production. Strands agents can further deploy to **Bedrock AgentCore Runtime**.

The deterministic core (`core.py`) is identical in spirit across both, so the
controls an examiner cares about do not change with the runtime.

## Sibling native rebuilds

Agents **01 (SAR)** and **02 (AML/TMS)** now have the same Strands + Step Functions native rebuild — see [`../01-financial-crime-investigation/`](../01-financial-crime-investigation/) and [`../02-aml-tms-enhancement/`](../02-aml-tms-enhancement/). All three follow the identical pattern: deterministic core in Lambdas, Strands/Bedrock drafting, and a framework-enforced `waitForTaskToken` human gate.
