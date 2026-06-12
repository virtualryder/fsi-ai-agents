# AWS-Native Rebuild — Real-Time Fraud Detection

Native AWS rebuild of Agent 04 (alongside the container path), **Bedrock
(Strands)** + **Step Functions**. The authorization decision is **deterministic
Python**; the LLM only drafts Reg E / analyst context (off the routing path).

- **Hard-block rules** RULE-009 (known-fraud IP / Tor) and RULE-010 (OFAC-adjacent
  merchant) force **BLOCK** regardless of score.
- Deterministic composite (rule 60% + behavioral 40%, **LLM excluded**):
  ≥85 BLOCK · 65–84 STEP_UP · 40–64 ANALYST_REVIEW · <40 ALLOW.
- **Reg E disclosure** auto-flagged on BLOCK; the analyst-review band uses a
  `waitForTaskToken` gate.

```
Intake → Score (rules + composite) → Choice → {DraftRegE | StepUp | AnalystReviewGate(waitForTaskToken) | Allow} → Finalize
```

```bash
cd aws-native-reference/04-fraud-detection
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
