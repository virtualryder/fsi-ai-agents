# AWS-Native Rebuild — Credit Underwriting

Native AWS rebuild of Agent 08 (alongside the container path in `Dockerfile` /
`DEPLOY.md`), using **Amazon Bedrock (Strands)** + **AWS Step Functions**. All
credit decisioning is **deterministic Python**; the LLM only drafts the
adverse-action letter body or approval memo.

## What's deterministic (the examiner-critical parts)

- FICO-band credit factor + weighted composite (credit 30 · DTI 25 · LTV 20 ·
  income 15 · reserves 10).
- **Hard declines**: OFAC SDN match, DTI > 50%, FICO below the loan-type minimum,
  recent-bankruptcy seasoning — each mapped to **ECOA/Reg B reason codes in Python**.
- Tiers: ≥0.75 APPROVE · ≥0.55 conditions · ≥0.35 refer · else DECLINE.
- Adverse-action notice cites up to **4 principal reasons** (Reg B); the LLM
  renders prose only and a defensive check blocks prohibited-basis language.

## Architecture

```
Verify → Evaluate (deterministic) → FairLending → Route → Choice
  ├─ GenerateAdverseAction (Strands · letter body) ─┐  (DECLINE)
  ├─ UnderwriterReviewGate (waitForTaskToken)     ◀─┤  (REFER / conditions / fair-lending)
  └─ AutoApprove                                    │  (clean APPROVE)
                                       Finalize  ◀──┘
```

OFAC is a hard block; **fair-lending flags force the underwriter/compliance gate**.

## Verify / deploy

```bash
cd aws-native-reference/08-credit-underwriting
EXTRACT_MODE=demo python -m pytest tests/ -q       # core + pipeline + ASL
cd infra && terraform init && terraform apply -var=extract_mode=demo
```

Container lift-and-shift alternative: `DEPLOY.md`.
