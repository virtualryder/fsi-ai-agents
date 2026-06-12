# AWS-Native Rebuild — Model Risk Management (SR 11-7)

Native AWS rebuild of Agent 11 (alongside the container path), **Bedrock
(Strands)** + **Step Functions**. Every risk determination is **deterministic
Python**; the LLM only writes the validation narrative; the Model Risk Officer
(or CRO) signs every HIGH-tier outcome at a `waitForTaskToken` gate.

- **PSI** = Σ (Actual−Expected)·ln(Actual/Expected); STABLE <0.10 · WARNING ·
  CRITICAL >0.25. Gini/KS/AUC drops and FNR increase drive degradation flags.
- **9 immutable `ALWAYS_HITL_CONDITIONS`** (HIGH-tier validations, PSI critical,
  degradation, material finding, challenger underperforms, hard-rule violation,
  fair-lending flag) → MRO review; **hard-rule violation / fair-lending → CRO**.

```
Inventory → Assess (Gini/KS/PSI) → Choice → {Narrative → ModelRiskReviewGate(waitForTaskToken) | Finalize} → Finalize
```

```bash
cd aws-native-reference/11-model-risk
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
