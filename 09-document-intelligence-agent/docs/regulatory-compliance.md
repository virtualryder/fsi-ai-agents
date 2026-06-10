# Regulatory Compliance Guide — Document Intelligence Agent (Agent 09)

## Purpose of This Document

This guide explains the regulatory framework that governs how the Document Intelligence Agent processes financial documents. It is written for compliance officers, BSA officers, and legal/regulatory teams who need to evaluate whether the agent's design meets their institution's obligations.

**The core compliance design principle:** Every regulatory requirement is enforced by deterministic Python code — not by an LLM. The LLM performs only classification and field extraction (inherently ambiguous tasks). All regulatory controls (HITL triggers, PII masking, routing rules, retention requirements) are Python functions that the LLM cannot influence or override.

---

## Regulatory Framework Coverage

### 1. Gramm-Leach-Bliley Act (GLBA) — Data Security

**The Requirement:** GLBA Safeguards Rule (16 CFR Part 314, updated 2023) requires financial institutions to protect customers' nonpublic personal information (NPI/PII) throughout its lifecycle.

**Specific GLBA Safeguards Rule Requirements and Agent Controls:**

| GLBA Requirement | Agent Control | Location in Code |
|---|---|---|
| Identify and classify NPI | Python regex PII detection (7 pattern types) | `nodes.py: pii_detection_node()` |
| Limit access to NPI on need-to-know basis | LLM receives only masked text — never raw PII | `nodes.py: _detect_and_mask_pii()` |
| Encrypt NPI in transit | TLS 1.3 at ALB; encrypted SQS/Aurora/S3 | `aws-deployment-guide.md: Steps 3, 6, 7, 8` |
| Encrypt NPI at rest | KMS CMK encryption for all storage | `aws-deployment-guide.md: Step 3` |
| Implement access controls | Least-privilege IAM; Okta SAML authentication | `aws-deployment-guide.md: Steps 2, 4` |
| Monitor and test security | WAF, CloudWatch alarms, Macie scanning | `aws-deployment-guide.md: Steps 2, 7, 10` |
| Develop an incident response plan | CloudWatch alarm → SNS → incident response | `aws-deployment-guide.md: Step 10` |
| Implement multi-factor authentication | Okta SAML MFA enforced at ALB | `aws-deployment-guide.md: Step 2` |

**PII Types Detected and Masked:**

The agent automatically detects and masks the following PII types before any LLM processing:

| PII Type | Pattern | Masking Behavior |
|---|---|---|
| Social Security Number | `\d{3}-\d{2}-\d{4}` | Replaced with `[SSN REDACTED]` in cached text |
| Employer Identification Number (EIN) | `\d{2}-\d{7}` | Replaced with `[EIN REDACTED]` |
| Passport Number | `[A-Z]{1,2}\d{6,9}` | LLM instructed to return `PASSPORT_PRESENT` only |
| Bank Account Number | 8–17 consecutive digits | Last 4 preserved: `****{last4}` |
| Routing Number | 9-digit number starting with 0 | Replaced with `[ROUTING REDACTED]` |
| Credit Card Number | 16 digits in 4×4 groups | Replaced with `****-****-****-****` |
| IBAN | `[A-Z]{2}\d{2}...` | Replaced with `[IBAN REDACTED]` |

**Defense-in-Depth:** The LLM extraction prompt includes a second layer of PII constraints — even if the regex layer missed a PII instance, the LLM is instructed to mask SSNs (last 4 only) and return `PASSPORT_PRESENT` instead of the passport number. Two independent masking layers.

---

### 2. Bank Secrecy Act (BSA) / Anti-Money Laundering

**The Requirement:** BSA (31 USC 5311 et seq.) requires financial institutions to maintain programs to detect and report suspicious activity, file Currency Transaction Reports (CTRs) for cash transactions exceeding $10,000, and file Suspicious Activity Reports (SARs) within 30 days of detection.

**BSA-Specific Controls in the Agent:**

#### SAR Form Processing — 31 USC 5318(g)(2) Tipping-Off Prohibition

SARs are protected by federal law: the institution, its officers, employees, and agents may not disclose to any person involved in the suspicious transaction that a SAR has been filed. This is the "tipping-off" prohibition.

**Agent Control:** SAR_FORM is in the `ALWAYS_HITL_DOCUMENT_TYPES` frozenset. The routing table for SAR_FORM routes exclusively to `01-financial-crime-investigation` (the BSA investigation queue). Output payloads for SAR documents are flagged `sar_confidentiality: true` — downstream agents that are not the financial crime agent will not receive SAR content. The enrichment node reads the `target_agents` list; if it includes only the financial crime agent, the enrichment payload is marked restricted.

**Code Reference:** `nodes.py: ALWAYS_HITL_DOCUMENT_TYPES`, `DOCUMENT_ROUTING[DocumentType.SAR_FORM.value]`

#### CTR Processing — 31 CFR 1010.311, 15-Day Filing Requirement

CTRs must be filed within 15 calendar days of the triggering transaction. The agent extracts the transaction date and computes the filing deadline (transaction_date + 15 days). If the deadline is within 3 days, the output payload priority is escalated to `CRITICAL`.

**Structuring Detection:** The validation node checks bank statements for cash deposit patterns that may indicate structuring (multiple deposits below $10,000 that collectively exceed $10,000). A structuring indicator flag is added as a business rule violation if detected.

**Code Reference:** `nodes.py: validation_node()` — CTR threshold check and structuring detection

#### Transaction Monitoring — SWIFT High-Risk Country Screening

SWIFT MT103 and MT202 messages are screened against a list of high-risk jurisdiction BIC prefixes (first 2 characters of the BIC correspond to the ISO 3166-1 alpha-2 country code). Countries on FATF's "grey list" and "black list" trigger a business rule violation that requires HITL before routing.

**Code Reference:** `nodes.py: HIGH_RISK_COUNTRY_CODES` frozenset, `validation_node()` SWIFT screening section

#### BSA Record Retention — 31 CFR 1010.430 (5-Year Retention)

BSA requires financial institutions to retain records related to currency transactions and suspicious activity for 5 years. The agent's audit trail is stored in Aurora PostgreSQL with a minimum retention period enforced by the database parameter group (`rds:backupRetentionPeriod=35` days for rolling backups, supplemented by S3 Object Lock on staged documents with COMPLIANCE mode for the 5-year statutory period).

---

### 3. OFAC — Office of Foreign Assets Control

**The Requirement:** OFAC regulations prohibit U.S. persons from conducting transactions with sanctioned persons, entities, and jurisdictions. The SDN (Specially Designated Nationals) list must be screened for all SWIFT payments and wire instructions.

**Agent Control:** The agent does not perform real-time OFAC database lookup (this requires a subscription to an OFAC screening service, which is handled by Agent 01 — Financial Crime Investigation). The Document Intelligence Agent's role is to extract and structure the counterparty names and BICs that Agent 01 will screen.

**High-Risk Country Pre-Screening:** As a pre-screening measure, the validation node checks BIC codes in SWIFT messages against a list of comprehensively sanctioned jurisdictions (North Korea, Iran, Cuba, Syria, Crimea). Documents with these BICs are immediately flagged with a business rule violation and require HITL before routing.

**Code Reference:** `nodes.py: HIGH_RISK_COUNTRY_CODES`

---

### 4. Equal Credit Opportunity Act (ECOA) / Regulation B — Fair Lending

**The Requirement:** ECOA (15 USC 1691) prohibits discrimination in credit decisions based on race, color, religion, national origin, sex, marital status, age, or receipt of public assistance. The agent processes loan applications that feed into credit underwriting decisions.

**Agent Controls:**

#### HMDA Data Extraction
For residential loan applications (LOAN_APPLICATION_RESIDENTIAL), the agent extracts the HMDA demographic data fields if present (race, ethnicity, sex — which borrowers may decline to provide). These fields are passed to the Credit Underwriting agent (Agent 08), which uses them only for fair lending monitoring — not for the credit decision itself.

**Why This Matters:** The extracted demographic data enables the institution to run HMDA LAR (Loan Application Register) analysis and detect potential disparate impact patterns. Failure to extract and report this data accurately is an HMDA violation.

#### Geographic Fair Lending Flag
The validation node checks property addresses for census tract numbers that have been flagged in prior HMDA analysis as having potential disparate impact patterns. When a property address falls in a flagged census tract, a business rule violation is added and the anomaly is passed to Agent 08 for enhanced underwriting documentation.

**Code Reference:** `nodes.py: FLAGGED_CENSUS_TRACTS` (populated from Agent 08's fair lending data)

---

### 5. Home Mortgage Disclosure Act (HMDA)

**The Requirement:** HMDA (12 USC 2801) requires financial institutions to collect and report data on mortgage loan applications and originations, including applicant demographics and loan characteristics.

**Agent Controls:** The LOAN_APPLICATION_RESIDENTIAL schema in `document_type_schemas.json` includes all HMDA-required data elements as optional fields. The extraction instructions include proper HMDA action-taken codes for declined and withdrawn applications. The enrichment node notes missing HMDA fields as data quality issues for the receiving agent.

---

### 6. FinCEN Customer Due Diligence (CDD) Final Rule

**The Requirement:** 31 CFR 1010.230 requires financial institutions to collect and verify the identity of beneficial owners of legal entity customers — individuals who own 25%+ of the entity and one control person.

**Agent Controls:** The `BENEFICIAL_OWNERSHIP_CERT` document type schema extracts beneficial owner names and ownership percentages. The validation node checks that the sum of ownership percentages does not exceed 100% (a basic sanity check; does not validate completeness of the beneficial ownership structure). BENEFICIAL_OWNERSHIP_CERT documents route to Agent 03 (KYC/CDD Perpetual) for ongoing monitoring.

**Trust Documents:** The `TRUST_DOCUMENT` schema captures trustee and beneficiary names. Complex trust structures (discretionary trusts, layered trusts) are flagged as requiring enhanced due diligence in the enrichment notes.

---

### 7. Identity Verification — BSA Customer Identification Program (CIP)

**The Requirement:** 31 CFR 1020.220 requires financial institutions to collect and verify identifying information for all customers, including name, date of birth, address, and identification number (SSN for U.S. individuals, passport for foreign individuals).

**Agent Controls for GOVERNMENT_ID Documents:**

The `GOVERNMENT_ID` document type is in `ALWAYS_HITL_DOCUMENT_TYPES` for three reasons:

1. **Document authenticity cannot be verified by OCR**: Security features of passports and driver's licenses (holograms, UV-reactive ink, microprinting) are not visible in a standard scan or photograph. A human reviewer must physically examine the document or use a dedicated document authentication device.

2. **Identity verification requires human judgment**: Matching a document holder's photo to the customer appearing in person or via video KYC requires human assessment. The LLM is not suitable for facial matching.

3. **Passport number extraction is prohibited**: The agent never extracts passport numbers. The LLM prompt instructs the model to return `PASSPORT_PRESENT` as a flag indicating the field exists, without extracting the actual number. This limits exposure if the output payload is ever improperly accessed.

**Code Reference:** `agent/prompts.py: FIELD_EXTRACTION_SYSTEM_PROMPT` — constraint 4 on PII handling

---

### 8. Securities Regulations — Trade Documentation

**The Requirement:** SEC Rule 17a-3 and 17a-4 (broker-dealer records), FINRA Rule 4511, and CFTC swap reporting rules require broker-dealers to maintain accurate records of all securities transactions.

**Agent Controls:** The `TRADE_CONFIRMATION` schema extracts all required trade record fields: trade date, settlement date, instrument identifier (CUSIP/ISIN/LEI), quantity, price, counterparty, and trader ID. Trade confirmations route directly to Agent 07 (Trading Surveillance) for pattern analysis. Settlement date validation checks that settlement is T+2 for equities and T+1 for government securities; exceptions are flagged as business rule violations.

---

## Audit Trail and Record Retention

### What the Audit Trail Contains

Every document processed by the agent generates an append-only audit trail. Each audit trail entry records:

- **timestamp**: ISO-8601 UTC — when the step occurred
- **document_id**: UUID — unique identifier for this processing run
- **step**: Which node executed
- **key facts**: What the node determined (document type, confidence tier, routing decision, reviewer decision, etc.)

**What the audit trail does NOT contain:**
- Raw document bytes (never in state)
- Raw extracted text (stored in module-level cache only during processing, cleared at completion)
- Unmasked PII values
- OpenAI API responses (full LLM responses are not logged)

### Retention Schedule

| Record Type | Retention Period | Storage | Authority |
|---|---|---|---|
| Audit trail (LangGraph checkpoint) | 7 years | Aurora PostgreSQL → S3 Glacier | BSA 31 CFR 1010.430 |
| Staged documents (S3) | 5 years (COMPLIANCE mode) | S3 with Object Lock | BSA 31 CFR 1010.430 |
| SAR-related processing records | 5 years | Aurora + S3 | 31 CFR 1020.320 |
| CTR-related processing records | 5 years | Aurora + S3 | 31 CFR 1010.311 |
| HMDA loan application data | 3 years (LAR) + 1 year (files) | Aurora | Reg C / HMDA |
| CloudWatch Logs | 90 days (rolling) | CloudWatch | Operational |

---

## Model Governance — SR 11-7 Applicability

**Is This Agent a "Model" Under SR 11-7?**

Federal Reserve Supervisory Guidance SR 11-7 defines a "model" as a quantitative method, system, or approach that applies statistical, economic, financial, or mathematical theories and translates inputs into quantitative outputs that are used in decision-making.

**Assessment:** The Document Intelligence Agent is an **operational tool**, not a model under SR 11-7. It does not produce a quantitative output (score, rating, or probability) that is used directly in a credit or risk decision. It produces structured data (field extraction) that is then consumed by downstream agents (such as Agent 08, Credit Underwriting) that may themselves be SR 11-7 models.

**However:** The LLM-based classification and extraction components should be periodically validated to ensure accuracy does not degrade. Recommended validation approach:
- Quarterly: Sample 100 documents from each document type; compare LLM extraction to human-verified gold standard. Track precision/recall by document type and field.
- Annually: Full accuracy review across all 25 document types. Recalibrate the classification prompt if accuracy on any type falls below 85%.

The validation results should be documented in the Model Risk Management framework even if this agent is not formally a SR 11-7 model, as the LLM extraction accuracy directly affects the quality of inputs to SR 11-7 models downstream.

---

## Compliance Questions and Answers

**Q: Can the LLM route a SAR to a non-BSA agent?**

No. The routing decision in `routing_decision_node()` reads from a Python constant (`DOCUMENT_ROUTING`) that maps `SAR_FORM` to `["01-financial-crime-investigation"]` only. This constant is defined at module load time and cannot be modified at runtime by any LLM response. The LLM has no visibility into the routing table.

**Q: How do we demonstrate that PII was not sent to OpenAI?**

The `pii_detection_node()` runs before `document_classification_node()`. The node logs that it has masked the cached text (the log entry appears in CloudWatch Logs). An examiner can trace a specific document_id through the CloudWatch log stream to see the pii_detection step with the list of PII types found and confirm it ran before any LLM call. The application-level unit test `test_pii_detection_node_masks_cached_text` in `tests/test_nodes.py` provides automated regression testing for this control.

**Q: What happens if the OpenAI API is unavailable?**

LLM nodes catch API exceptions and add the error to `state["errors"]`. The document is routed to HITL (via the routing_decision_node checking for validation errors). The document does not proceed to downstream agents with incomplete extraction. Operations is alerted by the `LLMApiErrors` CloudWatch alarm.

**Q: Who can access documents in the HITL review queue?**

The Streamlit application requires Okta SAML authentication. The HITL queue shows documents pending review. The Okta application configuration should restrict access to specific groups (e.g., BSA Officers for SAR/CTR review, Compliance Officers for Consent Orders, Operations staff for routine confidence reviews). Group-based access ensures segregation of duties.

**Q: How are reviewer decisions audited?**

Every reviewer decision (APPROVE_AND_ROUTE, CORRECT_AND_ROUTE, REJECT, REQUEST_RESUBMIT) is recorded in the audit trail with the reviewer_id, review_timestamp, and reviewer_notes. The audit trail is append-only and stored in Aurora PostgreSQL — it cannot be modified by application code or by the reviewer after submission.

**Q: Does the agent comply with the EU General Data Protection Regulation (GDPR)?**

The agent is designed for U.S. financial institutions under U.S. law (GLBA, BSA, ECOA). For institutions with EU operations or EU counterparty data, additional controls would be needed: data residency (EU AWS regions), right-to-erasure workflows (which conflict with BSA retention requirements and would require legal analysis), and data processing agreements with OpenAI. Consult legal counsel before using this agent with EU personal data.
