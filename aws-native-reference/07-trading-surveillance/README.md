# AWS-Native Rebuild — Trading Surveillance

Native AWS rebuild of Agent 07 (alongside the container path), **Bedrock
(Strands)** + **Step Functions**. Pattern detection, severity, the **SAR
determination**, and the always-HITL overrides are **deterministic Python**; the
LLM only drafts the disposition memo / SAR narrative (and never tips off the
subject — 31 U.S.C. § 5318(g)(2)).

- **Always-HITL types** (immutable frozenset) → **CRITICAL + mandatory compliance
  review**: INSIDER_TRADING, INFORMATION_BARRIER_BREACH, CROSS_MARKET_MANIPULATION.
- **SAR determination**: amount ≥ $5,000 AND suspicious (Python rule).
- **Reg SHO** Rule 203 locate-failure detection; severity tiers CRITICAL/HIGH → review.

```
Intake → Detect → Score (severity + SAR) → Choice → {DraftMemo → ComplianceReviewGate(waitForTaskToken) | Disposition} → Finalize
```

```bash
cd aws-native-reference/07-trading-surveillance
EXTRACT_MODE=demo python -m pytest tests/ -q
cd infra && terraform init && terraform apply -var=extract_mode=demo
```
