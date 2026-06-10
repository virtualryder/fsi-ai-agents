# Agent 11 — Model Risk Management Agent
# Regulatory Compliance Analysis

## Overview

Agent 11 implements the independent model validation function required by SR 11-7 (Guidance on Model Risk Management). It validates the five scoring models used across the FSI AI Suite: the AML/TMS false positive composite (Agent 02), the KYC customer risk score (Agent 03), the fraud detection composite (Agent 04), the trading surveillance risk score (Agent 07), and the credit underwriting composite (Agent 08).

The agent's design reflects SR 11-7's core requirements: conceptual soundness review, outcomes analysis, ongoing monitoring, independent validation, and documented human oversight. Every validation outcome is produced by deterministic Python. The LLM produces only the written narratives that support the validation report — it does not determine risk tier, performance flags, HITL conditions, or validation outcome.

---

## SR 11-7 — Federal Reserve / OCC Guidance on Model Risk Management

**Primary authority:** Board of Governors SR Letter 11-7 (April 4, 2011); OCC Bulletin 2011-12 (parallel guidance)

SR 11-7 is the primary model risk management framework for U.S. financial institutions. It applies to any "model" — a quantitative method, system, or approach that applies statistical, economic, financial, or mathematical theories to transform inputs into quantitative estimates. All five scoring models in the FSI AI Suite meet this definition.

### SR 11-7 §§ 5-7: Conceptual Soundness

**Obligation:** The model's theoretical basis, assumptions, and limitations must be documented and independently reviewed. The reviewer must assess whether the model is appropriate for its intended use and whether known limitations are adequately controlled.

**Agent 11 implementation:** The `conceptual_soundness_review_node` (Node 3) uses the LLM to produce a conceptual soundness narrative covering: theoretical basis, variable selection rationale, weight documentation, assumption inventory, known limitations, and fitness-for-purpose assessment. This narrative is LLM-drafted but human-reviewed at the HITL gate.

**Python boundary:** The LLM does not determine whether the model is sound. That determination is made by the Model Risk Officer at the human review gate, based on the Python-computed performance metrics and the LLM-drafted narrative.

### SR 11-7 § 8: Outcomes Analysis

**Obligation:** Model predictions must be compared against actual outcomes using appropriate statistical tests. Back-testing, benchmarking against alternative models, and stress testing are required components.

**Agent 11 implementation:**
- `outcomes_analysis_node` (Node 4): Computes accuracy, Gini, KS, AUC-ROC, FPR, FNR changes vs. baseline using Python arithmetic. Applies `PERFORMANCE_DEGRADATION_THRESHOLDS` constants to flag material degradation.
- `population_stability_analysis_node` (Node 5): Computes PSI using the mathematical formula: `PSI = Σ (Actual% - Expected%) × ln(Actual% / Expected%)`. Classifies as STABLE (<0.10), WARNING (0.10-0.25), or CRITICAL (>0.25) using Python thresholds.
- `benchmark_comparison_node` (Node 6): Compares production model against challenger using Python arithmetic (Gini point comparison). Material outperformance (>5 Gini points) triggers `CHALLENGER_UNDERPERFORMS` HITL condition.
- `sensitivity_analysis_node` (Node 7): Validates weight normalization (sum = 1.0 ± 0.001), concentration risk (no factor > 50%), and hard rule coverage (OFAC and PEP overrides documented).

**Degradation thresholds (Python constants — not configurable at runtime):**
- Accuracy decline > 5pp → `ACCURACY_DEGRADATION` flag
- Gini decline > 10 points → `GINI_DEGRADATION` flag
- KS decline > 8pp → `KS_DEGRADATION` flag
- FPR increase > 5pp → `FPR_INCREASE` flag
- FNR increase > 3pp → `FNR_INCREASE` flag (tighter than FPR — missing true positives has greater regulatory risk in compliance models)
- PSI > 0.10 → WARNING; PSI > 0.25 → CRITICAL + HITL trigger

### SR 11-7 §§ 10-11: Ongoing Monitoring

**Obligation:** Institutions must have a systematic process for ongoing monitoring of model performance. Monitoring frequency must be commensurate with the model's risk tier.

**Agent 11 implementation:**
- HIGH-tier models: monthly monitoring (`ONGOING_MONITORING` validation type, automated trigger)
- MEDIUM-tier: quarterly monitoring
- LOW-tier: semi-annual monitoring

Automated CloudWatch alarms (production) trigger `TRIGGERED_REVIEW` when performance metrics breach degradation thresholds between scheduled monitoring cycles. Metric degradation detected outside of scheduled monitoring cycles generates an automated `TRIGGERED_REVIEW` event, which always requires HITL.

### SR 11-7 § 4: Human Oversight and Governance

**Obligation:** Model risk management must be embedded in the institution's overall risk management framework with appropriate human oversight. Independence of validation from model development is required.

**Agent 11 implementation:** `interrupt_before=["human_review_gate"]` is a LangGraph framework directive — the graph physically cannot produce a final validation outcome without a human Model Risk Officer submitting a decision. HIGH-tier models require MRO sign-off at every validation event:
- INITIAL_VALIDATION, ANNUAL_REVALIDATION, CHANGE_VALIDATION: always MRO required
- TRIGGERED_REVIEW (performance degradation): MRO required; CRO for critical findings
- HARD_RULE_VIOLATION_DETECTED: escalates to CRO

The reviewer's identity (reviewer_id), decision, conditions, and timestamp are captured in the audit trail for examination review.

---

## ECOA / Regulation B — Fair Lending

**Primary authority:** Equal Credit Opportunity Act (15 U.S.C. § 1691 et seq.); Regulation B (12 CFR Part 202); CFPB examination procedures

**Applicability to Agent 11:** The `AGT08-CREDIT-SCORE-v1` model (Agent 08 Credit Underwriting) makes loan disposition decisions and generates adverse action reason codes. Agent 11 validates that this model does not produce disparate impact against protected classes.

**Agent 11 implementation:** The `FAIR_LENDING_FLAG` condition in `ALWAYS_HITL_CONDITIONS` frozenset triggers HITL whenever:
- A new scoring feature is introduced that may correlate with protected characteristics (e.g., geographic data, rental payment history)
- The outcomes analysis reveals disparate approval/denial rates that warrant disparate impact analysis
- The model change validation introduces any change that touches demographic data proxies

When triggered, the HITL gate requires a Fair Lending Officer review in addition to MRO sign-off. The validation report includes a fair lending assessment section.

---

## BSA/AML Model Validation Implications

**Primary authority:** Bank Secrecy Act (31 U.S.C. § 5318); FinCEN regulations; FFIEC BSA/AML Examination Manual

**Applicability to Agent 11:** The `AGT02-FP-SCORE-v1` (Agent 02), `AGT03-KYC-RISK-v1` (Agent 03), and `AGT04-FRAUD-SCORE-v1` (Agent 04) models produce outputs that directly influence SAR filing decisions, CDD refresh decisions, and fraud routing. Model degradation in these models creates BSA compliance risk — if the FP model incorrectly suppresses genuine SAR-required activity, that is a BSA compliance failure, not just a model performance issue.

**Agent 11 implementation:**
- FNR threshold (3pp) is set below FPR threshold (5pp) for all models. Missing genuine suspicious activity has greater BSA risk than generating excess false positives.
- `HARD_RULE_VIOLATION_DETECTED` condition escalates to CRO if production logs show that a hard rule (OFAC bypass, PEP suppression) was circumvented — this is a BSA violation that requires immediate escalation.
- Model suspension (`REQUIRE_REMEDIATION` decision) triggers immediate notification to the BSA Officer to activate manual override procedures for the affected agent.

---

## Record Retention — Model Validation Reports

**Primary authority:** BSA 5-year record retention (31 CFR 1020.230); SR 11-7 ongoing monitoring documentation; OCC model risk retention guidance

**Agent 11 implementation:** Validation reports are retained in S3 Object Lock GOVERNANCE mode for 10 years — the expected model operational life plus the BSA retention period. GOVERNANCE mode requires authenticated administrator credentials to delete objects before the retention period expires. The `audit_finalize_node` documents `audit_retention: "10_YEARS_S3_OBJECT_LOCK_GOVERNANCE"` in the audit trail entry.

---

## Compliance Officer Q&A

**Q: Can the LLM determine whether a model passes validation?**
A: No. The LLM produces narratives — conceptual soundness review text, outcomes analysis interpretation, and the validation report draft. The validation outcome (APPROVED / CONDITIONALLY_APPROVED / SUSPENDED) is determined by: (1) Python-computed performance metrics and HITL conditions, and (2) the Model Risk Officer's decision at the human review gate. No LLM output can produce an APPROVED status without MRO sign-off on HIGH-tier models.

**Q: What happens if a model is suspended?**
A: The MRO selects `REQUIRE_REMEDIATION` at the human review gate. The agent sets `validation_outcome=SUSPENDED` and `model_approval_status=SUSPENDED` in the model registry. The BSA Officer and relevant business owner are notified. The affected agent's operator must activate the manual override process for that agent's outputs until the suspension is cleared. Suspension requires a remediation plan within 5 business days.

**Q: How does Agent 11 handle fair lending model risk?**
A: The `FAIR_LENDING_FLAG` condition triggers HITL when the credit underwriting model (Agent 08) shows potential disparate impact — new features with demographic proxies, geographic concentration, or disparate approval rates. This condition cannot be overridden by any application code path — it is in the `ALWAYS_HITL_CONDITIONS` frozenset.

**Q: How do examiners access model validation records?**
A: Validation reports are in S3 Object Lock with 10-year retention. The DynamoDB model registry provides the current approval status, last validation date, and next revalidation schedule. The LangGraph audit trail in Aurora PostgreSQL provides the full node-by-node decision record for each validation event. Examiners can request all three layers.

**Q: What if a hard rule violation is found in production logs?**
A: The `HARD_RULE_VIOLATION_DETECTED` condition automatically escalates to `CHIEF_RISK_OFFICER` and always requires HITL. This is the most severe finding Agent 11 can generate. A hard rule violation (e.g., OFAC bypass, PEP suppression without authorization) means a regulatory bright-line was circumvented — this requires immediate CRO review, potential BSA Officer notification, and may require regulatory disclosure.
