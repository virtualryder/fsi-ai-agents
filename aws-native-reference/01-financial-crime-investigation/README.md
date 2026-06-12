# AWS-Native Rebuild — Financial Crime Investigation (SAR)

A native AWS rebuild of Agent 01 alongside the lift-and-shift container path
(`Dockerfile`, `DEPLOY.md`). Same thesis as the LangGraph agent — **deterministic
Python decides, the model only drafts the SAR narrative, a BSA Officer approves
at a framework-enforced gate** — implemented with **Amazon Bedrock (Strands)** +
**AWS Step Functions**.

Improvement over the original: the composite risk score is computed in
**deterministic Python** here (the LangGraph node computes it via the LLM), so
no model output influences the SAR/route/close decision.

## Architecture

```
Step Functions state machine
  ├─ Screen        (Lambda · PII mask + deterministic OFAC/PEP watchlist screening)
  ├─ Score         (Lambda · deterministic composite risk: sanctions 30 · network 25
  │                  · transactions 25 · adverse_media 15 · profile 5 = 100)
  ├─ Route         (Lambda · deterministic routing + HITL decision)
  ├─ DispositionChoice (Choice on $.routing.next)
  │     ├─ GenerateSAR  (Lambda · Strands + Bedrock · DRAFTS narrative only) ─┐
  │     ├─ HumanReviewGate (lambda:invoke.waitForTaskToken · BSA Officer)  ◀──┤
  │     └─ CloseCase   (Lambda · documented closure, no SAR)                  │
  └─ Finalize      (Lambda · masked case record + audit)  ◀───────────────────┘
```

Routing (deterministic, faithful to Agent 01): **>70 → SAR**, **30–70 → human
review**, **<30 → close**. An **OFAC/SDN match is a hard override** → SAR path +
mandatory review regardless of score. A **PEP** match never auto-closes.

`interrupt_before` → `waitForTaskToken`: the BSA-Officer gate is framework-enforced;
the SAR is drafted but nothing is "filed" until a reviewer resumes the execution
(`SendTaskSuccess`/`SendTaskFailure`).

## Verified vs. needs-an-account

**Verified in CI (no AWS):** deterministic weights/thresholds, OFAC/PEP overrides,
the full Lambda chain in demo mode, the SAR drafter sets no routing fields, PII
masked in the audit, and the ASL is structurally valid (HITL `waitForTaskToken`,
Choice default, one terminal). — 19 tests.

**Needs an account:** `terraform apply`, real Bedrock inference (unset
`EXTRACT_MODE`), the review UI calling the HITL resume, and Guardrails.

## Run the demo (no AWS)

```bash
cd aws-native-reference/01-financial-crime-investigation
EXTRACT_MODE=demo python -m pytest tests/ -q          # 19 tests
```

## Deploy (with an account)

```bash
cd infra
terraform init
terraform apply -var="environment=dev" -var="extract_mode=demo"
# then enable Bedrock model access, set guardrail_id, re-apply with extract_mode=""
```

The container lift-and-shift path is in `DEPLOY.md` (run the original LangGraph
agent unchanged on AgentCore Runtime / Fargate). Use this native rebuild when you
want managed Step Functions orchestration and a durable `waitForTaskToken` gate.
