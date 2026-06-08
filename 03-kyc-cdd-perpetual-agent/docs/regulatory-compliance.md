# Regulatory Compliance Framework
## KYC/CDD Perpetual Monitoring Agent

---

## 1. FinCEN Customer Due Diligence Rule — 31 CFR § 1020.210

### Overview

The FinCEN CDD Rule (effective May 11, 2018) requires covered financial institutions to establish and maintain written procedures to identify and verify beneficial owners of legal entity customers and to conduct ongoing monitoring to maintain and update customer information. This agent automates the "ongoing monitoring" obligation that banks historically satisfied only at periodic review intervals.

**FinCEN's four core CDD pillars and how the agent addresses each:**

| CDD Pillar | Requirement | Agent Implementation |
|-----------|------------|---------------------|
| Customer Identification | Collect and verify identifying information | Document collection node validates government ID, formation documents |
| Beneficial Ownership | Identify 25%+ owners and control persons | Beneficial ownership flag in AlertScoringState; BO changes trigger immediate review |
| Customer Risk Profile | Understand the nature and purpose of the customer relationship | 8-factor risk model produces customer risk tier (LOW/MEDIUM/HIGH/EDD_REQUIRED) |
| Ongoing Monitoring | Monitor for suspicious activity and update CIP information | EventBridge-triggered perpetual cycle; change-based triggers on any risk factor change |

### Ongoing Monitoring — the Key Obligation This Agent Fulfills

The CDD Rule's ongoing monitoring obligation is open-ended: institutions must monitor "on an ongoing basis" but the rule does not specify a method or frequency. The agent's response:

- **Periodic Review Scheduler:** HIGH risk = annual; MEDIUM = biennial; LOW = triennial (configurable per institution)
- **Event-Driven Triggers:** Address change, beneficial ownership change, PEP designation, adverse media hit, or large behavioral shift triggers an immediate out-of-cycle review
- **Score-Based Escalation:** Any 8-factor weighted risk rescore that crosses a tier boundary (e.g., MEDIUM → HIGH) automatically opens an EDD workflow without human scheduling

This approach provides continuous compliance rather than point-in-time snapshots.

### Beneficial Ownership Accuracy

31 CFR § 1020.230 requires institutions to maintain accurate beneficial ownership records. When the agent detects a beneficial ownership change:

1. Document collection node re-requests BO certification form
2. BO verification is flagged as PENDING until form received
3. Account risk tier is not reduced while BO verification is outstanding
4. If BO change involves a newly identified PEP, the alert is hard-escalated to EDD_REQUIRED (non-configurable)

---

## 2. Bank Secrecy Act — 31 U.S.C. § 5318(l)

### Customer Identification Program Requirements

The BSA requires financial institutions to implement a written CIP that includes procedures for verifying the identity of customers and maintaining records of the information used to verify identity. This agent does not replace a CIP — it automates the ongoing maintenance of CIP records post-onboarding.

**What the agent contributes to BSA/CIP compliance:**

| BSA/CIP Element | Agent Role |
|----------------|-----------|
| Document currency | Document collection node flags expired IDs, stale formation documents; collects renewals |
| Address verification | Change of address triggers out-of-cycle review and document re-verification |
| Record updating | KYC record update node writes refreshed data to customer profile with timestamp and operator |
| Retention | All review records written to DynamoDB with 5-year TTL; S3 Object Lock for EDD documents |

### 18 U.S.C. § 1956/1957 — No Tipping Off

When a KYC review opens because Agent 01 (Financial Crime Investigation Agent) filed a SAR on a customer, the agent must not reveal to the customer that a SAR was filed. Implementation:

- The KYC review reason displayed to the RM or branch is "Periodic Review — Scheduled" regardless of the triggering event
- SAR-related triggers arrive via an internal event queue, not through customer-facing or RM-facing systems
- The BSA Officer is the only role that can see the "SAR Filed — Triggered Review" origin in the compliance dashboard
- RM-facing document request templates contain no language referencing suspicious activity

---

## 3. FATF Recommendations — R.10, R.12, R.22

### FATF R.10 — Customer Due Diligence

FATF R.10 requires CDD measures to be applied: (1) when establishing a business relationship; (2) when there is a suspicion of ML/TF; (3) when there are doubts about previously obtained CDD information. This agent addresses conditions (2) and (3) via its trigger system.

**Trigger → FATF Condition Mapping:**

| Trigger Type | FATF Condition | Agent Response |
|-------------|---------------|----------------|
| SAR filed by Agent 01 | Suspicion of ML/TF | Immediate out-of-cycle review, minimum EDD_REQUIRED |
| Adverse media hit (high severity) | Doubts about existing CDD | Out-of-cycle review, re-verification of KYC profile |
| Beneficial ownership change | Doubts about existing CDD | Immediate BO re-verification |
| Jurisdiction change (high-risk country added) | Doubts about existing CDD | Risk rescoring + potential tier elevation |
| PEP designation detected | FATF R.12 (see below) | Immediate EDD_REQUIRED escalation |

### FATF R.12 — Politically Exposed Persons

FATF R.12 requires Enhanced Due Diligence for PEPs: identifying senior management approval, establishing source of wealth, conducting enhanced ongoing monitoring.

**Hard override in this agent:**

```python
# From agent/nodes.py — risk_rescoring_node()
# PEP designation is non-configurable — cannot be tuned or overridden by BSA Officer config

if customer_profile.get("pep_status") == "PEP":
    return {
        "review_outcome": "EDD_REQUIRED",
        "review_reason": "PEP designation requires Enhanced Due Diligence per FATF R.12",
        "senior_approval_required": True,
        "source_of_wealth_required": True
    }
```

The EDD workflow for PEPs generates a structured checklist including: senior management approval gate (HITL interrupt), source of wealth documentation, source of funds documentation, and enhanced monitoring frequency (minimum annual regardless of base risk tier).

### FATF R.22 — DNFBPs

For institutions that service Designated Non-Financial Businesses and Professions (casinos, real estate agents, dealers in precious metals), FATF R.22 requires the same CDD standards. The agent's industry risk scoring includes elevated weights for DNFBP industries:

- Industry risk factor weight: 10% of composite score
- DNFBP industry codes → industry_risk = HIGH regardless of other factors
- HIGH industry risk combined with any other elevated factor → automatic MEDIUM tier floor

---

## 4. FFIEC BSA/AML Examination Manual — Customer Due Diligence

The FFIEC Examination Manual's CDD section describes what examiners assess during a BSA examination. Key examiner focus areas and agent responses:

### Risk-Based CDD Program

Examiners expect institutions to demonstrate a risk-based approach: higher-risk customers receive more intensive ongoing monitoring. The agent's 8-factor weighted model directly maps to this expectation:

| Risk Factor | Weight | Why Examiner-Defensible |
|------------|--------|------------------------|
| Transaction behavior deviation | 20% | Behavioral analytics directly linked to SAR-filing triggers |
| PEP status | 15% | FATF R.12 mandated; hard-coded non-configurable |
| Adverse media | 15% | Independent third-party signal; not self-reported |
| Jurisdiction risk | 15% | FATF/OFAC country risk classification |
| Document status | 10% | Document currency is a direct CIP compliance measure |
| Beneficial ownership | 10% | CDD Rule requirement; cannot be waived |
| Industry type | 10% | DNFBP/high-risk industry classification |
| Customer tenure | 5% | Behavioral baseline calibration |

The weight allocation is documented, justified, and fixed in code — not an LLM judgment call.

### Enhanced Due Diligence Documentation

For EDD_REQUIRED customers, examiners will want to see the enhanced monitoring record. The agent generates an EDD package containing:

- Risk tier escalation rationale (factor scores at time of escalation)
- Document collection checklist and completion status
- Senior management approval record (HITL audit trail)
- Source of wealth and source of funds documentation links
- Enhanced monitoring schedule (frequency and method)
- Review completion record with analyst identity and findings

All EDD packages are stored in S3 with GOVERNANCE mode Object Lock — examiners can retrieve any EDD package by customer ID or date range.

---

## 5. OCC Bulletin 2018-17 — Third-Party Risk and Model Risk

### Applicability

OCC 2018-17 governs third-party risk management. This agent uses external data sources (adverse media vendors, watchlist screening providers, jurisdiction risk feeds). Each is treated as a third-party model input:

- **Adverse media API:** Classified as a data vendor; responses are logged with provider name, response timestamp, and raw output for audit
- **Watchlist screening:** OFAC and PEP list hits are logged with the screening provider's response payload; no suppression of hits is permitted at the API layer
- **Jurisdiction risk scoring:** Based on FATF grey/black lists and OFAC SDN country risk — sourced from configurable reference data updated at least quarterly

### SR 11-7 Model Risk Management

This agent uses an AI/ML scoring model (LLM + rule weights) to make risk tier decisions. SR 11-7 applies.

**Conceptual Soundness:**
- The 8-factor weighted model is documented with factor selection rationale
- Weights reflect relative regulatory priority (PEP and adverse media at 15% each reflects FATF/FinCEN guidance)
- LLM is used for advisory analysis only — the routing decision (review outcome) is made by Python code comparing the composite score to configurable thresholds

**Ongoing Monitoring:**
- CloudWatch metric: tier distribution (should be stable; sudden shifts indicate model drift or data quality issue)
- CloudWatch metric: EDD completion rate (EDD packages opened vs. closed within SLA)
- Recommended: quarterly review of tier change history against SAR outcomes

**Human Override:**
- Compliance Officer can override any review outcome in the dashboard (with mandatory reason)
- All overrides are logged to the audit trail with the reviewer's identity
- Threshold adjustments require Compliance Officer authentication

---

## 6. OFAC Regulations — Watchlist Screening

### Screening Requirements

OFAC requires financial institutions to screen customers against the SDN list and blocked persons lists. This agent integrates watchlist screening into the perpetual review cycle.

**OFAC Controls in This Agent:**

```python
# From agent/nodes.py — watchlist_screening_node()
# OFAC hits are never suppressed — they always produce EDD_REQUIRED regardless of composite score

if screening_result.get("ofac_sdn_hit"):
    return {
        "review_outcome": "ESCALATE",  # Routes to Agent 01 for investigation
        "ofac_flag": True,
        "hard_block": True,
        "reason": "OFAC SDN match — mandatory escalation"
    }

if screening_result.get("pep_hit"):
    return {
        "review_outcome": "EDD_REQUIRED",
        "pep_flag": True,
        "reason": "PEP designation — EDD required per FATF R.12"
    }
```

**Why non-configurable:** An OFAC violation carries penalties up to $356,579 per transaction (2024 adjusted) and potential criminal liability. These paths are outside the scoring pipeline and cannot be adjusted through the BSA Officer Threshold Configuration tab.

**Screening Frequency:**
- All customers: screened at every periodic review cycle
- Event triggers: any name change, address change, or beneficial ownership change triggers immediate re-screening
- Daily batch option: configurable to run OFAC screening daily on the full customer book (recommended for high-risk institutions)

---

## 7. Record Retention

| Record Type | Retention Period | Authority |
|------------|-----------------|-----------|
| Customer risk tier history (all changes) | 5 years | 31 CFR § 1010.430 |
| KYC review records (all outcomes) | 5 years | 31 CFR § 1010.430 |
| EDD packages and supporting documents | 5 years from account close | 31 CFR § 1020.210 |
| Beneficial ownership certifications | 5 years from account close | 31 CFR § 1020.230 |
| Watchlist screening results | 5 years | BSA program documentation |
| Compliance Officer override log | 5 years | 31 CFR § 1010.430 |
| Threshold change log | 5 years | SR 11-7 / BSA program documentation |
| Model validation records | Life of model + 5 years | SR 11-7 |
| Adverse media hits (all, including cleared) | 5 years | BSA program documentation |

**Storage:** DynamoDB (review records) + S3 Object Lock GOVERNANCE mode (EDD documents). IAM policy blocks DeleteItem and UpdateItem on the DynamoDB audit table.

---

## 8. FFIEC / OCC Examination Preparedness

### What Examiners Will Ask About This Agent

**"How do you ensure high-risk customers receive enhanced monitoring?"**
- 8-factor weighted model produces a composite risk score; tier thresholds are configurable but documented and justified
- PEP and OFAC hits are hard-coded escalations — not subject to threshold adjustment
- EDD workflow generates a structured package that examiners can retrieve by customer
- EventBridge enforces review frequency: HIGH customers are reviewed annually regardless of BSA staff workload

**"How do you handle the ongoing monitoring obligation under the CDD Rule?"**
- Three trigger types: periodic schedule (configurable frequency), event-based (any risk factor change), and SAR-driven (Agent 01 cross-integration)
- No customer exceeds their scheduled review date without a CloudWatch alarm firing
- All review completions are timestamped and attributed to the reviewing officer

**"What happens if the model mis-tiers a customer?"**
- Compliance Officer override available on any review outcome — mandatory reason required
- All overrides logged with reviewer identity and timestamp
- 8-factor score breakdown allows examiner or auditor to understand any tier decision
- Quarterly trend review catches systematic mis-tiering before examination

**"How do you prevent tipping off SAR subjects?"**
- SAR-triggered review origins are visible only to BSA Officer role in the compliance dashboard
- RM and branch-facing review notifications display "Periodic Review — Scheduled" regardless of trigger
- Architectural separation: SAR events flow through an internal queue inaccessible to RM-facing services

**"How are you managing model risk under SR 11-7?"**
- Factor weights are documented with selection rationale in this document and `agent/nodes.py`
- LLM is advisory only — routing decisions are made by Python code against configurable thresholds
- Threshold changes require Compliance Officer authentication and are logged
- Quarterly monitoring cadence recommended; CloudWatch dashboards support ongoing oversight
