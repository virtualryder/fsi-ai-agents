# Regulatory Compliance Framework
## Financial Crime Investigation Agent

---

## 1. Bank Secrecy Act (BSA) — 31 U.S.C. §§ 5311-5336

### Core Requirements

**SAR Filing Obligation (31 CFR § 1020.320)**
- Banks must file a SAR for transactions of $5,000 or more where the bank "knows, suspects, or has reason to suspect" the transaction involves illegal funds, is designed to evade reporting requirements, or lacks a lawful purpose
- **Filing deadline:** 30 calendar days from the date the bank detects a suspicious transaction, with reasonable promptness to identify a suspect
- **Extended deadline:** 60 calendar days from initial detection if no subject has been identified
- **Retention:** SARs and supporting documentation must be retained 5 years from date of filing (31 CFR § 1010.430)
- **No tipping off:** 31 U.S.C. § 5318(g)(2) — financial institutions may not notify anyone involved in a reported transaction that a SAR has been filed. Violation is a federal crime.
- **Safe harbor:** 31 U.S.C. § 5318(g)(3) — institutions filing SARs in good faith are protected from civil liability

### How the Agent Addresses This
| BSA Requirement | Agent Implementation |
|-----------------|---------------------|
| Detect suspicious activity | TMS alert ingestion + AI pattern analysis |
| 30-day filing deadline | Automatic deadline calculation in `sar_generator.py` |
| Complete SAR narrative | GPT-4o generates FIN-2014-G001 quality draft |
| 5-year retention | Case record retention metadata automatically set |
| No tipping off | AI never contacts customers; strict access controls |
| Safe harbor documentation | Full audit trail of all investigation steps |

---

## 2. OFAC Regulations — International Emergency Economic Powers Act (IEEPA)

### Core Requirements
- **Zero tolerance:** Banks must not process transactions involving OFAC-sanctioned individuals, entities, or countries
- **No safe harbor for facilitation:** Unlike BSA, there is no good-faith safe harbor for OFAC violations
- **Civil penalties:** Up to $356,579 per violation (2024 inflation-adjusted) or twice the amount of the transaction
- **Criminal penalties:** Up to $1,000,000 and/or 20 years imprisonment for willful violations
- **Blocking requirement:** Property of SDNs must be blocked — not returned, not processed
- **OFAC reporting:** Blocked property must be reported within 10 business days

### OFAC 50% Rule (2014 Guidance)
Entities owned 50% or more by an SDN are themselves subject to OFAC sanctions, even if not named on the list. This makes beneficial ownership screening a legal requirement.

### How the Agent Addresses This
| OFAC Requirement | Agent Implementation |
|-----------------|---------------------|
| Customer screening | OFAC SDN API call in `watchlist_screening.py` |
| Counterparty screening | All transaction counterparties screened |
| Beneficial owner screening | UBOs from CDD Rule data screened |
| 50% Rule compliance | Entity ownership structure checked |
| Blocking flag | Automatic flag when OFAC hit detected |
| OFAC reporting | Agent flags for immediate human review |

---

## 3. FinCEN Guidance — SAR Narrative Quality

### FIN-2014-G001: "Guidance on Preparing a Complete & Sufficient SAR"

FinCEN's definitive guidance on SAR narrative quality identifies common deficiencies:
- Narratives that fail to answer the "5 W's + How"
- Vague language ("large amount" instead of specific dollar figures)
- Missing time periods ("recently" instead of specific dates)
- No explanation of why activity is suspicious relative to customer profile
- Failure to reference prior SARs on continuing activity

### FinCEN SAR Quality Standards (Agent Implementation)
| Quality Standard | Agent Implementation |
|-----------------|---------------------|
| WHO is conducting activity | Customer profile + beneficial owners documented |
| WHAT transactions occurred | Specific amounts, dates, account numbers in narrative |
| WHEN activity occurred | Date range automatically extracted from transactions |
| WHERE activity took place | Branches, accounts, jurisdictions documented |
| WHY activity is suspicious | AI compares activity to customer's expected profile |
| HOW activity was conducted | Transaction mechanisms identified and documented |
| Specific dollar amounts | All amounts formatted with exact figures |
| Prior SAR references | Prior SAR count from customer profile included |

---

## 4. USA PATRIOT Act — Customer Due Diligence

### Section 326: Customer Identification Program (CIP)
- Banks must collect and verify: name, date of birth, address, and SSN/EIN
- Verification must occur before account opening
- Agent uses CIP data as baseline for transaction anomaly detection

### Section 312: Enhanced Due Diligence for Foreign Banks
- EDD required for foreign correspondent banking relationships
- Agent includes EDD status check in customer profile lookup

### Section 314(b): Voluntary Information Sharing
- Banks may voluntarily share information about suspected ML with other FIs
- Agent flags cases appropriate for 314(b) inquiry
- Integration point: FinCEN 314(b) Portal at https://fincen.gov/314bportal

### Section 314(a): Law Enforcement Information Sharing
- FinCEN periodically sends 314(a) requests asking banks to search their records
- Matching customers are added to internal watchlist for enhanced monitoring

---

## 5. FinCEN Customer Due Diligence Rule (31 CFR § 1010.230)

### Beneficial Ownership Requirements (Effective May 11, 2018)
Banks must collect and verify the identity of:
1. **Ownership prong:** All individuals who own 25%+ of a legal entity
2. **Control prong:** One individual with significant managerial control (if no owner meets 25% threshold)

### OFAC 50% Rule Interaction
The CDD Rule beneficial ownership data is used by the agent to apply the OFAC 50% Rule — if any beneficial owner is an SDN and holds 50%+ ownership, the entity itself is blocked.

### How the Agent Addresses This
- `get_beneficial_owners()` retrieves UBO structure from core banking/KYC system
- All UBOs are screened against OFAC and PEP lists
- Complex ownership structures (>2 layers) are flagged as shell company indicators

---

## 6. FATF 40 Recommendations

### Key Recommendations Addressed by the Agent

| FATF Rec. | Description | Agent Implementation |
|-----------|-------------|---------------------|
| R.1 | Risk-based approach | Weighted risk scoring (0-100) with documented methodology |
| R.10 | Customer due diligence | KYC/CDD data retrieval and assessment |
| R.12 | Politically Exposed Persons | PEP screening of customers and beneficial owners |
| R.13 | Correspondent banking | EDD flags for foreign bank relationships |
| R.17 | Reliance on third parties | Integration with third-party KYC/screening vendors |
| R.20 | Reporting suspicious transactions | Full SAR workflow with human-in-the-loop approval |
| R.24 | Transparency of legal persons | Beneficial ownership verification and shell company detection |
| R.25 | Transparency of legal arrangements | Trust structure and nominee detection |

---

## 7. Model Risk Management — SR 11-7 / OCC 2011-12

### Requirements for AI Models in Compliance Functions
The OCC's Supervisory Guidance on Model Risk Management (SR 11-7, adopted by OCC as OCC 2011-12) applies to all AI models used in compliance decisions. For this agent:

**Conceptual Soundness:**
- Risk scoring methodology is documented in `prompts.py` (RISK_SCORING_PROMPT)
- Factor weights have regulatory basis (OFAC = 30pts because of zero-tolerance obligation)
- All AI recommendations are advisory — human makes final decision

**Model Validation Requirements (Before Production Use):**
1. Backtesting against historical SAR population
2. Calibration of risk score thresholds against bank's historical false positive rate
3. Champion-challenger testing against current process
4. Fairness analysis (ECOA/Fair Lending — ensure no disparate impact)
5. Ongoing performance monitoring post-deployment

**Human Oversight Controls:**
- Every investigation requires human review at `human_review_gate` node
- AI never autonomously files SARs (only humans can submit to FinCEN)
- All AI decisions logged with model version, timestamp, and reasoning
- Human override capability on all AI recommendations

---

## 8. Fair Lending / ECOA Considerations

### Potential Disparate Impact
AI-powered AML systems carry Fair Lending risk if they inadvertently create disparate impact on protected classes. Banks using this agent should:
- Conduct regular disparate impact analysis of alert generation rates by geography/demographics
- Review whether watchlist screening creates disproportionate burden on specific communities
- Ensure human review step catches any systemic biases in AI recommendations
- Document the analysis for CRA examination purposes

---

## 9. Record Retention Requirements

| Document Type | Retention Period | Authority |
|--------------|-----------------|-----------|
| SARs and supporting documents | 5 years from filing date | 31 CFR § 1010.430 |
| Closed case files (no SAR) | 5 years from closure | 31 CFR § 1010.430 |
| CTR records | 5 years from filing date | 31 CFR § 1010.430 |
| CIP/KYC records | 5 years from account closure | 31 CFR § 1020.220 |
| OFAC blocked property records | 5 years | 31 CFR Part 501 |
| Audit trail (this agent) | 5 years minimum | 31 CFR § 1010.430 |
| Model validation documentation | Life of model + 5 years | SR 11-7 |

---

## 10. Examination Preparedness

### What OCC/FDIC Examiners Look For
During BSA/AML examinations, regulators assess:
- **Completeness:** Is every TMS alert investigated and resolved?
- **Timeliness:** Are SARs filed within the 30-day deadline?
- **Quality:** Are SAR narratives complete per FIN-2014-G001?
- **Documentation:** Is the rationale for case closure documented?
- **OFAC:** Were all required parties screened before transactions?
- **Model Risk:** Is the AI model validated per SR 11-7?
- **Human Oversight:** Are humans making final compliance decisions?

### How the Agent Supports Examination Readiness
- Full audit trail for every investigation step
- Documented rationale for every case disposition (SAR, escalate, or close)
- SAR filing deadline tracking with alerts for approaching deadlines
- Human-in-the-loop controls documented in code and audit trail
- Model risk documentation embedded in system documentation
