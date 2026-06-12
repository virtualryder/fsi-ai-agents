# AWS-Native Rebuild — KYC/CDD Perpetual Monitoring

Native AWS rebuild of Agent 03 (alongside the container path), using **Bedrock
(Strands)** + **Step Functions**. Screening and risk rescoring are deterministic
Python; the LLM only drafts the EDD package / RM communication.

- **OFAC** hit → forced **ESCALATE** (overrides all routing); **PEP** hit →
  mandatory **EDD** (FATF R.12).
- Rescore outcomes: ESCALATE · REL_EXIT · EDD_REQUIRED · RISK_UPGRADE · DOWNGRADE · PASS.
- **Any risk-rating change or escalation requires a Compliance Officer** at a
  `waitForTaskToken` gate; PASS auto-finalizes.

```
Screen → Rescore → ReviewChoice → {DraftEDD → ComplianceReviewGate(waitForTaskToken) | Finalize} → Finalize
```

```bash
cd aws-native-reference/03-kyc-cdd-perpetual
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
