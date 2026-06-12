# AWS-Native Rebuild — Payments Compliance

Native AWS rebuild of Agent 10 (alongside the container path in `Dockerfile` /
`DEPLOY.md`), using **Amazon Bedrock (Strands)** + **AWS Step Functions**. Every
compliance determination is **deterministic Python**; the LLM only drafts
customer notices.

## What's deterministic

- **OFAC** screening (sanctioned-country frozenset), **Nacha** return-code
  validation (R05/R07/R10/R29 unauthorized), **Reg E** eligibility, CTR threshold.
- **HITL triggers** (immutable): `ALWAYS_HITL_PAYMENT_EVENTS` (OFAC_HOLD,
  UNAUTHORIZED_WIRE, SAR_CANDIDATE, CTR_THRESHOLD, HIGH_RISK_COUNTRY_WIRE,
  LATE_RETURN_DISPUTE), OFAC exposure, amount ≥ $50,000, unauthorized return, SAR
  candidate.
- **Auto-resolve** for NOC / administrative events.

## Architecture

```
Intake → Screen (OFAC/Nacha/Reg E) → Route → Choice
  ├─ HumanReviewGate (waitForTaskToken · BSA/compliance)   (any HITL trigger)
  ├─ AutoResolve                                           (NOC / administrative)
  └─ DraftNotice (Strands · Reg E / dispute notice)        (normal dispute)
                                        Finalize ◀──────────┘
```

## Verify / deploy

```bash
cd aws-native-reference/10-payments-compliance
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```

Container lift-and-shift alternative: `DEPLOY.md`.
