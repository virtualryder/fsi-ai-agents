# AWS-Native Rebuild — Collections & Recovery

Native AWS rebuild of Agent 12 (alongside the container path), **Bedrock
(Strands)** + **Step Functions**. Every FDCPA / Reg F / SCRA determination is
**deterministic Python**; the LLM drafts the letter body only, and required
disclosures are **Python-injected** (never model-written).

- **FDCPA contact-time** via `pytz` (no contact before 8am / at-or-after 9pm
  local; **fail-safe prohibited** on unknown timezone).
- **SCRA** 6% interest-rate cap; **bankruptcy automatic stay** halts all
  collection; 50-state SOL arithmetic.
- **9 immutable `ALWAYS_HITL_CONDITIONS`** (SCRA, bankruptcy stay, dispute,
  cease & desist, deceased, high-value settlement, litigation, regulatory
  complaint, minor account) → **supervisor** review at a `waitForTaskToken` gate.

```
Intake → Assess (FDCPA/SCRA/bankruptcy + conditions) → Choice → {SupervisorReviewGate(waitForTaskToken) | DraftLetter} → Finalize
```

```bash
cd aws-native-reference/12-collections-recovery
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
