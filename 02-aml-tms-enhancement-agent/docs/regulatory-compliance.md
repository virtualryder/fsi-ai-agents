# Regulatory Compliance Framework
## AML/TMS Enhancement Agent

---

## 1. Bank Secrecy Act (BSA) — 31 U.S.C. §§ 5311-5336

### Alert Disposition and Documentation Requirements

The BSA does not mandate a specific false positive suppression rate, but it does require that financial institutions maintain an AML program that is reasonably designed to detect and report suspicious activity. Suppressing alerts without documentation creates BSA exposure.

**FinCEN's position (2014 Examination Manual, Section IV):**
> "Financial institutions are expected to develop risk-based processes for evaluating transaction monitoring alerts... the institution's process for evaluating and closing alerts should be documented."

This means every suppressed alert must have:
- A documented reason for suppression
- The analyst (or system) that made the suppression decision
- The date of suppression
- A review mechanism (the BSA Officer 90-day review requirement in this agent)

### How the Agent Addresses This

| BSA Requirement | Agent Implementation |
|----------------|---------------------|
| Document alert disposition | Every SUPPRESS, DOWNGRADE, PASS-THROUGH, ESCALATE decision is logged to DynamoDB with timestamp, score, and justification narrative |
| Rationale for closing without investigation | LLM-generated justification narrative explains FP reasoning in plain language |
| No silent discards | DLQ catches failed processing; CloudWatch alarm fires when DLQ depth > 0 |
| Ongoing program review | 90-day suppression review queue surfaces all suppressions for BSA Officer review |
| BSA program integrity | Hard-coded escalation paths for PEP, OFAC, and high-risk geography patterns |

### 30-Day SAR Filing Deadline Interaction

Agent 02 does not generate SARs — it routes alerts to Agent 01 (Financial Crime Investigation Agent) for investigation. The 30-day SAR filing clock starts when the bank first "detects" suspicious activity. **This agent must not delay the clock:**

- An alert scored ESCALATE (FP ≤ 15%) is forwarded to Agent 01 in real time — the scoring adds seconds, not days.
- An alert scored SUPPRESS is not suspicious by definition. If a BSA Officer later overrides a suppression and opens an investigation, the 30-day clock starts at the date of override.
- All timestamps are recorded to support examination of the detection-to-filing timeline.

---

## 2. OFAC Regulations — Hard Block Requirements

OFAC compliance cannot be probabilistic. The 50% false positive suppression rate does not apply to sanctions screening.

### Non-Negotiable OFAC Rules in This Agent

```python
# From agent/nodes.py — determine_routing()
# These conditions override composite FP probability at any score

if alert.customer_pep_status == "PEP":
    return "ESCALATE"  # Hard-coded — PEPs are never suppressed

if (alert.geography_risk == "HIGH"
    and alert.amount > 50000
    and alert.account_age_days < 90):
    return "ESCALATE"  # High-risk geography + large wire + new account

if alert.ofac_proximity_flag:
    return "ESCALATE"  # Any OFAC-adjacent signal → investigation required
```

**Why these are non-configurable:** An OFAC violation carries penalties up to $356,579 per transaction (2024 adjusted) and potential criminal liability. The BSA Officer Threshold Configuration tab in the dashboard cannot override these hard escalation paths — they are Python code outside the scoring pipeline.

---

## 3. SR 11-7 / OCC 2011-12 — Model Risk Management

This agent uses a composite AI model (LLM + rules + historical statistics) to make routing decisions that affect the bank's AML compliance program. SR 11-7 applies.

### SR 11-7 Requirements and Implementation

**Conceptual Soundness:**
- The 30% rule / 50% LLM / 20% historical weight allocation is documented and justified
- Rule weights reflect relative reliability: rule-based features are deterministic and interpretable; LLM provides contextual reasoning; historical rates provide statistical grounding
- Threshold selection (85% suppress, 60% downgrade, 15% escalate) is configurable by BSA Officer and must be documented with rationale

**Ongoing Monitoring:**
- CloudWatch metric: suppress rate by rule typology (should be stable; sudden changes indicate model drift)
- CloudWatch metric: escalation rate vs. confirmed suspicious activity rate (measures calibration)
- Recommended: quarterly review of suppressed alerts against SAR outcomes

**Human Override:**
- BSA Officer can override any individual suppression decision in the dashboard
- BSA Officer can adjust thresholds in the Threshold Configuration tab
- All threshold changes are logged to the audit trail with the BSA Officer's identity

**Model Documentation for Examiners:**
| SR 11-7 Element | Where Documented |
|----------------|-----------------|
| Model purpose and scope | This document + README.md |
| Methodology (scoring weights) | `agent/nodes.py` (compute_composite_score_node) |
| Data inputs | `agent/state.py` (AlertScoringState TypedDict) |
| Validation approach | `tests/` pytest suite |
| Human oversight controls | BSA Officer review gate + threshold config |
| Ongoing monitoring | CloudWatch dashboard + quarterly review protocol |

---

## 4. FATF Recommendations

### FATF R.20 — Suspicious Transaction Reporting
FATF R.20 requires financial institutions to promptly file reports when they suspect money laundering or terrorist financing. This agent's role is to ensure genuine suspicious activity is **not suppressed** — it does not file reports, but it gates what reaches investigators.

**Control:** FP ≤ 15% → mandatory ESCALATE. This means the top ~15% of true-positive-probability alerts are always investigated. The threshold is configurable by the BSA Officer downward (more conservative), but the BSA Officer cannot configure a threshold that would allow genuinely suspicious alerts to be suppressed without review.

### FATF R.12 — Politically Exposed Persons
PEP status requires Enhanced Due Diligence. **This agent hard-codes PEP → ESCALATE regardless of FP score.** A PEP customer with a 96% FP probability alert is still escalated to Agent 01 for full investigation. This is a non-negotiable implementation detail.

---

## 5. FFIEC BSA/AML Examination Manual — Alert Management

The FFIEC Examination Manual's "Transaction Monitoring" section describes what examiners assess:

> "Examiners should review whether the bank's alert management process includes... adequate documentation of how alerts were evaluated and why they were closed without further action."

### Examination-Ready Audit Trail

Every alert processed by this agent generates an audit record containing:
```
{
  "alert_id": "TMS-2024-001234",
  "processing_timestamp": "2024-01-15T10:30:00.123Z",
  "fp_probability": 0.89,
  "routing_decision": "SUPPRESS",
  "score_breakdown": {
    "rule_based_score": 0.92,
    "llm_analysis_score": 0.87,
    "historical_pattern_score": 0.88,
    "weights": {"rule": 0.30, "llm": 0.50, "historical": 0.20}
  },
  "justification_narrative": "Customer John Smith has 36 months of consistent
    payroll deposits in this range. The alert was triggered by rule STR-001
    (cash deposit velocity), however the customer's KYC profile documents
    regular payroll direct deposits from Employer A. Historical FP rate for
    rule STR-001 on this customer segment is 94%.",
  "hard_override_checked": true,
  "pep_status": false,
  "ofac_proximity": false,
  "operator": "SYSTEM",
  "review_due_date": "2024-04-15",  // 90-day BSA Officer review
  "bso_reviewed": false
}
```

This record is written to DynamoDB with IAM-enforced append-only access (no UpdateItem or DeleteItem) and is retrievable by alert_id, customer_id, or date range for examiner review.

---

## 6. Record Retention

| Record Type | Retention Period | Authority |
|------------|-----------------|-----------|
| Alert scoring decisions (all) | 5 years | 31 CFR § 1010.430 |
| Suppression justification narratives | 5 years | 31 CFR § 1010.430 |
| BSA Officer threshold change log | 5 years | SR 11-7 / BSA program documentation |
| BSA Officer suppression override log | 5 years | 31 CFR § 1010.430 |
| 90-day review completions | 5 years | BSA program documentation |
| Model validation records | Life of model + 5 years | SR 11-7 |

---

## 7. Examination Preparedness

### What Examiners Will Ask About This Agent

**"How do you ensure you're not suppressing genuine suspicious activity?"**
- Three-tier defense: rule-based pre-filter calibrated to known FP patterns; LLM reviews full customer context; historical base rates weight toward institution's own experience
- Hard escalation paths for PEP, OFAC proximity, high-risk geography
- BSA Officer 90-day review of all suppressions
- Suppression audit tab in dashboard provides instant visibility

**"What happens if the model is wrong?"**
- Human override available on every suppression decision
- 90-day review queue catches systematic errors before they compound
- CloudWatch alarm fires if suppression rate deviates materially from baseline
- Dead Letter Queue ensures no alert is silently discarded

**"How are you managing model risk?"**
- SR 11-7 documentation embedded in system docs
- Threshold changes require BSA Officer authentication and are logged
- Quarterly review cadence recommended in this document
- Factor-by-factor score breakdown allows examiners to understand any decision
