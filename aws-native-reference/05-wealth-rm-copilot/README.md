# AWS-Native Rebuild — Wealth & RM Copilot

Native AWS rebuild of Agent 05 (alongside the container path), **Bedrock
(Strands)** + **Step Functions**. The **suitability determination is
deterministic Python** (Reg BI / FINRA 2111), never the LLM.

- Conservative client + high-risk product → **UNSUITABLE** (blocked, never reaches
  the client); IPS-prohibited → UNSUITABLE; retirement → SUITABLE_WITH_NOTE +
  ERISA; concentration → with-note; stale IPS → NEEDS_REVIEW.
- Non-blocked recommendations are LLM-drafted and **approved by an RM** at a
  `waitForTaskToken` gate.

```
Intake → Suitability (deterministic) → Choice → {BlockUnsuitable | Recommend → RMApprovalGate(waitForTaskToken)} → Finalize
```

```bash
cd aws-native-reference/05-wealth-rm-copilot
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
