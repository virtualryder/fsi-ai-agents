# AWS-Native Rebuild — AML/TMS False-Positive Triage

A native AWS rebuild of Agent 02 alongside the lift-and-shift container path
(`Dockerfile`, `DEPLOY.md`), using **Amazon Bedrock (Strands)** + **AWS Step
Functions**. Faithful to the Phase 1.3 control-integrity design.

## The control that matters

**SUPPRESS** — the only disposition that removes an alert from the analyst queue
— is gated on a **deterministic-only** score (rule pre-score + historical base
rates, **LLM excluded**). The model writes an *advisory* justification and a
non-binding FP probability; it can never be the reason an alert disappears. A
high model probability with a low deterministic score does **not** suppress.

## Architecture

```
Step Functions state machine
  ├─ Ingest    (Lambda · PII mask + features: rule pre-score, historical base rates)
  ├─ Justify   (Lambda · Strands + Bedrock · advisory FP + narrative — NO routing)
  ├─ Route     (Lambda · deterministic suppression gate + 4-way routing)
  ├─ DispositionChoice (Choice on $.routing.next)
  │     ├─ SuppressionReviewGate (lambda:invoke.waitForTaskToken · sampled BSA review)
  │     ├─ Escalate          (Lambda · hand to Agent 01)
  │     └─ RecordDisposition (Lambda · downgrade / pass-through — stays visible)
  └─ Finalize  (Lambda · masked disposition record + audit)
```

Routing (deterministic): **ESCALATE** (regulatory override — PEP/open-investigation/
OFAC-adjacent — or deterministic ≤ 15) · **SUPPRESS** (deterministic ≥ 85, → review
gate) · **DOWNGRADE** (≥ 60) · **PASS_THROUGH**. Only SUPPRESS routes to a human
gate, because only SUPPRESS removes an alert from review.

## Verified vs. needs-an-account

**Verified in CI (no AWS):** the deterministic suppression gate (incl. the
LLM-high/deterministic-low cannot-suppress control), the regulatory overrides,
the full Lambda chain, the justifier sets no routing, PII masked in audit, and
the ASL is structurally valid. **Needs an account:** `terraform apply`, live
Bedrock inference, the suppression-review UI, and Guardrails.

## Run the demo (no AWS)

```bash
cd aws-native-reference/02-aml-tms-enhancement
EXTRACT_MODE=demo python -m pytest tests/ -q
```

Deploy via `infra/` (Terraform) like the other native rebuilds; the container
lift-and-shift alternative is in `DEPLOY.md`.
