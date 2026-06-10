# Agent 11 — Model Risk Management Agent
# ROI Analysis

## Executive Summary

Agent 11 replaces the most expensive, most manually intensive compliance function in a financial institution's AI governance stack: independent model validation. A single SR 11-7-compliant model validation event for a HIGH-risk model costs $18,000–$50,000 in senior quantitative analyst time alone, before factoring in Model Risk Officer review, legal review, and opportunity cost of delayed model deployment. Agent 11 reduces that to $3,500–$7,000 per event while generating a defensible, examiner-ready audit trail that manual processes cannot match.

The secondary ROI driver — and often the larger financial exposure — is early detection of model degradation. An undetected 12-point Gini decline in Agent 04 (Fraud Detection) over a 90-day monitoring gap translates directly to incremental fraud losses of $1.2M–$3.8M depending on portfolio size. Agent 11's monthly automated monitoring catches degradation at the first monitoring cycle, not after a scheduled annual review discovers the gap.

**Net present value (5-year, $10B community bank):** $4.2M–$8.7M
**Payback period:** 14–22 weeks

---

## Current State: What Manual Model Validation Costs

### Labor Cost per Validation Event (HIGH-Risk Model)

SR 11-7 requires that a HIGH-risk model validation event include: data pull and quality review, conceptual soundness review, back-testing against outcomes data, population stability analysis, sensitivity analysis / factor concentration review, benchmark comparison against challenger model, written validation report, and Model Risk Officer sign-off.

| Function | Role | Hours | Blended Rate | Cost |
|---|---|---|---|---|
| Data pull and quality review | Quant Analyst | 12–20 | $175/hr | $2,100–$3,500 |
| Conceptual soundness review | Senior Quant | 16–28 | $225/hr | $3,600–$6,300 |
| Back-testing and outcomes analysis | Senior Quant | 20–35 | $225/hr | $4,500–$7,875 |
| Population stability analysis | Quant Analyst | 8–14 | $175/hr | $1,400–$2,450 |
| Sensitivity / factor analysis | Senior Quant | 10–18 | $225/hr | $2,250–$4,050 |
| Benchmark / challenger analysis | Senior Quant | 8–16 | $225/hr | $1,800–$3,600 |
| Validation report drafting | Senior Quant | 12–20 | $225/hr | $2,700–$4,500 |
| MRO review and sign-off | Model Risk Officer | 6–12 | $275/hr | $1,650–$3,300 |
| **Total per validation event** | | **92–163 hrs** | | **$20,000–$35,575** |

For institutions using external validation vendors (common for initial validations and annual revalidations of HIGH-risk models), add 40–60% vendor margin → **$28,000–$56,900 per event at vendor rates**.

### Annual Validation Event Volume — Five-Model Suite

Each of the five models validated by Agent 11 (Agents 02, 03, 04, 07, 08) requires:

| Validation Type | Frequency | Events/Year (5 models) | Cost/Event | Annual Cost |
|---|---|---|---|---|
| Annual Revalidation | 12 months | 5 | $28,000–$56,900 | $140,000–$284,500 |
| Ongoing Monitoring | Monthly (HIGH tier) | 60 | $6,000–$9,000* | $360,000–$540,000 |
| Triggered Reviews | ~2/year/model | 10 | $20,000–$35,000 | $200,000–$350,000 |
| Change Validations | ~1/year/model | 5 | $28,000–$56,900 | $140,000–$284,500 |

*Ongoing monitoring at manual rates is typically a lighter-touch review but still requires 28–40 hours of quant time per model per month to produce a defensible monitoring report.

**Total annual manual validation cost for five HIGH-risk models: $840,000–$1,459,000**

The lower bound assumes an efficient, well-staffed internal MRM function. The upper bound assumes external vendor support for annual revalidations — which most community banks and regional banks require because they do not maintain a full internal quant MRM team.

---

## Agent 11 Cost

### Infrastructure (Monthly, AWS)

| Component | Purpose | Cost/Month |
|---|---|---|
| ECS Fargate (2 tasks, 2 vCPU / 8 GB each) | Agent 11 Streamlit + graph runner | $280–$420 |
| Aurora PostgreSQL Serverless v2 | LangGraph checkpoint / audit trail | $180–$280 |
| DynamoDB (model registry) | Validation status, approval state | $15–$40 |
| S3 Object Lock + Glacier Deep Archive | 10-year validation report retention | $25–$80 |
| CloudWatch + EventBridge | Monitoring alarms, automated triggers | $30–$60 |
| Secrets Manager (6 secrets) | API keys, DB credentials | $3–$5 |
| ALB + WAF | HTTPS termination, rate limiting | $60–$90 |
| **Total infrastructure** | | **$593–$975/month** |

**Annual infrastructure cost: $7,116–$11,700**

### Human Review Time with Agent 11

Agent 11 does not eliminate human review — SR 11-7 requires it, and Agent 11's architecture enforces it. What it eliminates is the computational and report-writing labor. The MRO still reviews findings, makes decisions, and signs off. Junior quant support is still needed to pull raw performance data and configure validation parameters.

| Function | Role | Hours with Agent 11 | Cost |
|---|---|---|---|
| Data configuration and parameter input | Junior Analyst | 1–2 | $200–$400 |
| Agent 11 automated analysis | (automated) | — | Infrastructure cost |
| MRO review of findings and narrative | Model Risk Officer | 3–5 | $825–$1,375 |
| MRO decision + conditions | Model Risk Officer | 0.5–1 | $138–$275 |
| **Total per HIGH-risk validation event** | | **4.5–8 hrs** | **$1,163–$2,050** |

**Annual human review cost across all validation events (80 events): $93,040–$164,000**

### Total Annual Cost with Agent 11

| Cost Component | Annual Cost |
|---|---|
| Infrastructure | $7,116–$11,700 |
| Human review (80 events) | $93,040–$164,000 |
| Implementation / configuration (Year 1 only) | $25,000–$40,000 |
| **Year 1 total** | **$125,156–$215,700** |
| **Year 2+ (ongoing)** | **$100,156–$175,700** |

---

## Savings Summary

| | Manual Approach | Agent 11 | Annual Savings |
|---|---|---|---|
| Validation labor cost | $840,000–$1,459,000 | $93,040–$164,000 | **$746,960–$1,295,000** |
| Infrastructure cost | $0 (hidden in staff cost) | $7,116–$11,700 | — |
| **Net annual savings** | | | **$735,000–$1,283,300** |

**Year 1 net savings (after implementation): $695,000–$1,243,300**
**Year 2+ net savings: $735,000–$1,283,300**

---

## Secondary ROI: Early Degradation Detection

This is the ROI that compliance officers and CDOs care most about, but that is hardest to quantify in a traditional cost-savings model. It is also the largest potential savings category.

### Fraud Model Degradation Scenario (Agent 04)

**Scenario:** Agent 04's Fraud Detection composite Gini coefficient declines from a baseline of 68.4 to 56.1 — a 12.3-point decline. This is beyond Agent 11's `GINI_DEGRADATION` threshold of 10 points. Without Agent 11:

- Under a quarterly monitoring schedule, this could go undetected for up to 90 days
- Under an annual review schedule, this could go undetected for up to 12 months

**Fraud loss impact:**

| Institution Size | Monthly Fraud Losses at Baseline Gini (68.4) | Monthly Fraud Losses at Degraded Gini (56.1) | Incremental Monthly Loss | 90-Day Undetected Loss |
|---|---|---|---|---|
| $500M community bank | $180,000 | $295,000 | $115,000 | $345,000 |
| $5B regional bank | $1,400,000 | $2,280,000 | $880,000 | $2,640,000 |
| $25B mid-tier bank | $6,200,000 | $10,100,000 | $3,900,000 | $11,700,000 |

Agent 11's monthly automated monitoring detects the Gini decline at the first monitoring cycle (≤30 days), triggering `TRIGGERED_REVIEW` and MRO escalation. Maximum undetected exposure window: **30 days** instead of 90–365.

**Incremental fraud loss savings (30 vs. 90 days):** $230,000–$7,800,000 depending on institution size.

### AML Model Degradation Scenario (Agent 02)

**Scenario:** Agent 02's FP Rate false positive composite FNR increases by 4 percentage points — above Agent 11's `FNR_INCREASE` threshold of 3pp. FNR increase means genuine suspicious activity is being suppressed and not routed for SAR filing.

**Regulatory exposure:** A BSA examination that finds systematic failure to file SARs — even if model-driven — results in:

- Civil money penalties: $500/day per violation (31 U.S.C. § 5321), up to $1M per pattern of violations
- MRA (Matters Requiring Attention) or MRIA (Matters Requiring Immediate Attention) — which can trigger consent order proceedings
- Reputational harm: BSA enforcement actions are public (FinCEN enforcement list)

**Conservative regulatory exposure (FNR degradation undetected for 90 days):** $500,000–$5,000,000 in civil money penalties, legal fees, and remediation costs. Does not include consent order monitoring costs ($1M–$3M/year for external monitor).

Agent 11 detects FNR degradation in the first monthly monitoring cycle and triggers HITL + BSA Officer notification. This converts a potential regulatory enforcement action into a documented, controlled model performance event with a remediation plan.

### Credit Model Fair Lending Scenario (Agent 08)

**Scenario:** Agent 08's credit underwriting model is updated to include a new "rental payment history" feature. Agent 11's `FAIR_LENDING_FLAG` HITL condition triggers, requiring Fair Lending Officer review before the model is approved for production use.

**Without Agent 11:** The model goes live. An ECOA examination six months later identifies disparate impact on a protected class in approval rates. The institution faces:

- CFPB enforcement action: consent order, redress to affected applicants, civil money penalties
- Typical redress in disparate impact credit cases: $1M–$50M+ depending on portfolio volume and extent of impact
- Restitution calculation requires a statistical regression model across 24 months of application data
- Remediation plan and ongoing CFPB monitoring: 2–5 years

**With Agent 11:** Fair lending review happens before model deployment. Discriminatory features are identified at validation, not after examiner discovery. The difference between detecting fair lending risk before vs. after deployment is the difference between a $50,000 validation finding and a $5M–$50M+ enforcement action.

---

## Exam Readiness ROI

### Current State: SR 11-7 Exam Preparation

A typical SR 11-7 examination request for the model validation function requires producing:

- Validation reports for all HIGH-risk models (past 3 years)
- Ongoing monitoring reports (past 24 months)
- Evidence of human sign-off for each validation event
- Model change log and change validation documentation
- Model inventory with current approval status for all production models

Manual processes produce this in 3–6 weeks of emergency document assembly, typically requiring 2–3 senior staff members. SR 11-7 examinations are stressful events that expose gaps in documentation and escalation trails.

**Exam preparation cost (manual):** $45,000–$120,000 in staff time per examination, plus consultant fees if documentation is incomplete.

### Agent 11 Exam Readiness

Agent 11 produces an exam-ready documentation package as a byproduct of its normal operation:

- **DynamoDB model registry:** Current approval status, last validation date, next revalidation schedule for all 5 models — queryable in seconds
- **Aurora PostgreSQL audit trail:** Full node-by-node decision record for every validation event (12 nodes × event count) with reviewer identity, decision, timestamp, and conditions
- **S3 Object Lock:** All validation reports retained in read-only, tamper-evident storage for 10 years
- **Automated completeness:** Every validation event generates a structured audit trail entry — no gaps from staff transitions or informal approvals

**Exam preparation cost with Agent 11:** 1–2 days to pull reports, not 3–6 weeks. Savings: $40,000–$115,000 per examination cycle.

---

## Suite Multiplier ROI

Agent 11 protects the value of all other agents in the FSI AI Suite. Without Agent 11:

- Agent 02's FP model can degrade silently — generating excess false positives that drive up operational cost (analyst review backlog) or generating false negatives that create BSA exposure
- Agent 04's fraud model can degrade and increase losses — with no automated detection
- Agent 08's credit model can introduce fair lending risk via model changes — with no pre-deployment validation gate

**Agent 11 is the risk management layer that makes the rest of the suite defensible in front of examiners and boards.**

The 10% of the suite budget spent on Agent 11 protects 100% of the suite's regulatory defensibility.

### ROI Summary by Scenario

| Savings Category | Annual Savings |
|---|---|
| Labor reduction (validation + monitoring) | $735,000–$1,283,300 |
| Fraud loss detection (Agent 04 30-day vs. 90-day detection) | $230,000–$7,800,000* |
| AML regulatory penalty avoidance | $500,000–$5,000,000* |
| Fair lending penalty avoidance | $1,000,000–$50,000,000* |
| Exam preparation cost reduction | $40,000–$115,000 per exam |
| **Total addressable savings** | **$2.5M–$64M+ over 5 years** |

*Penalty avoidance is probabilistic — not every degradation event becomes an enforcement action. Conservative weighting (5% annual probability of enforcement event on each model) produces an expected value of $250,000–$3,500,000/year in risk-adjusted savings.

---

## Payback Period

| Institution Type | Year 1 Implementation Cost | Annual Net Savings (Labor Only) | Payback Period |
|---|---|---|---|
| $500M community bank | $125,156–$165,000 | $735,000 | 8–11 weeks |
| $5B regional bank | $150,000–$215,700 | $950,000 | 10–14 weeks |
| $25B mid-tier bank | $175,000–$250,000 | $1,283,300 | 10–15 weeks |

Including one avoided regulatory finding (conservative: $500,000) shortens payback to 4–6 weeks at any institution size.

---

## Objection Handling

**"We already have a model validation team — this replaces their jobs."**

Agent 11 does not replace MROs or quant analysts. It eliminates the repetitive computational work — data pull, PSI calculation, metric comparison, report drafting — so the team can focus on the judgment work that SR 11-7 actually requires: conceptual soundness assessment, challenger design, and conditions setting. Most institutions with manual MRM functions are understaffed for the model portfolio they carry; Agent 11 lets them scale validation coverage without headcount.

**"Our examiners will want to see human-generated reports, not AI output."**

Agent 11 produces LLM narratives, but all compliance decisions (tier, flags, outcome, conditions) are Python-deterministic. The MRO signs off on every HIGH-tier validation event. The validation report lists the reviewer's identity, decision, and timestamp. This is more auditable than a Word document signed by a VP — it is a tamper-evident, timestamped record in a GOVERNANCE-mode S3 object. Examiners reviewing the audit trail will see more rigor, not less.

**"What if the LLM makes a wrong determination?"**

It cannot. The LLM does not make determinations. Degradation flags, HITL conditions, risk tier, PSI classification, routing, and validation outcome are all Python constants, arithmetic, and frozenset membership checks. The LLM produces only written narrative — the "report" prose. SR 11-7 allows and expects professional judgment to inform validation reports; Agent 11 applies that judgment in the Python layer, and the MRO applies it at the human review gate.
