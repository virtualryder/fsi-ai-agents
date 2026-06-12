# AWS-Native Rebuild — Regulatory Change Management

Native AWS rebuild of Agent 06 (alongside the container path), **Bedrock
(Strands)** + **Step Functions**. The **5-factor impact score, tier, and hard
overrides are deterministic Python** (SR 11-7 documented weights); the LLM only
drafts the gap analysis / remediation outline.

- Weights: authority_tier 0.25 · deadline_urgency 0.25 · scope_breadth 0.20 ·
  policy_count 0.15 · change_type_risk 0.15. Tiers CRITICAL ≥0.85 · HIGH ≥0.65 ·
  MEDIUM ≥0.40 · LOW.
- **Hard rules**: ENFORCEMENT_ACTION → mandatory HITL + HIGH floor; already-effective
  FINAL_RULE → CRITICAL; too-short compliance window for a MEDIUM change → HIGH.
- CRITICAL/HIGH (or enforcement) → **CCO review** at a `waitForTaskToken` gate.

```
Intake → Impact (deterministic) → Choice → {GapAnalysis → CCOReviewGate(waitForTaskToken) | Finalize} → Finalize
```

```bash
cd aws-native-reference/06-regulatory-change
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
