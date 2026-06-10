# Financial Services AI Agent Suite — Architecture Overview
### Full Platform Reference Architecture — 10 Agents

---

## Suite-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                          FINANCIAL SERVICES AI AGENT SUITE                               │
│                               AWS Production Architecture                                │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                           INGRESS / IDENTITY LAYER                                 │  │
│  │                                                                                    │  │
│  │  Users: BSA Officers · AML Investigators · Fraud Analysts · RMs · Dispute Teams   │  │
│  │         Payments Ops · Underwriters · Compliance Officers · Auditors               │  │
│  │              ↓                                                                     │  │
│  │  Active Directory ──(AD Agent)──► Okta (Enterprise SSO + MFA)                     │  │
│  │                                          ↓ SAML 2.0                               │  │
│  │  CloudFront CDN + WAF  ──────────► ALB (Cognito OIDC)  ──► ECS Fargate UI         │  │
│  │  (HTTPS / TLS 1.3)                 (JWT Session)                                  │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                       AGENT ORCHESTRATION LAYER (ECS Fargate)                     │  │
│  │                                                                                    │  │
│  │  ── FINANCIAL CRIME & AML ──────────────────────────────────────────────────────  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                            │  │
│  │  │ Agent 02     │  │ Agent 01     │  │ Agent 03     │                            │  │
│  │  │ TMS/AML      │→ │ Financial    │← │ KYC/CDD      │                            │  │
│  │  │ Enhancement  │  │ Crime Invest │  │ Perpetual    │                            │  │
│  │  │ Port 8502    │  │ Port 8501    │  │ Port 8503    │                            │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                            │  │
│  │                                                                                    │  │
│  │  ── FRAUD & PAYMENTS ──────────────────────────────────────────────────────────  │  │
│  │  ┌──────────────┐  ┌──────────────┐                                              │  │
│  │  │ Agent 04     │  │ Agent 10     │                                              │  │
│  │  │ Real-Time    │→ │ Payments     │                                              │  │
│  │  │ Fraud Detect │  │ Compliance   │                                              │  │
│  │  │ Port 8504    │  │ Port 8510    │                                              │  │
│  │  └──────────────┘  └──────────────┘                                              │  │
│  │                                                                                    │  │
│  │  ── WEALTH MANAGEMENT ─────────────────────────────────────────────────────────  │  │
│  │  ┌──────────────┐                                                                │  │
│  │  │ Agent 05     │                                                                │  │
│  │  │ Wealth RM    │                                                                │  │
│  │  │ Copilot      │                                                                │  │
│  │  │ Port 8505    │                                                                │  │
│  │  └──────────────┘                                                                │  │
│  │                                                                                    │  │
│  │  ── REGULATORY & COMPLIANCE ───────────────────────────────────────────────────  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                            │  │
│  │  │ Agent 06     │  │ Agent 07     │  │ Agent 08     │                            │  │
│  │  │ Regulatory   │  │ Trading      │  │ Credit       │                            │  │
│  │  │ Change Mgmt  │  │ Surveillance │  │ Underwriting │                            │  │
│  │  │ Port 8506    │  │ Port 8507    │  │ Port 8508    │                            │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                            │  │
│  │                                                                                    │  │
│  │  ── DOCUMENT INTELLIGENCE (HORIZONTAL — FEEDS ALL AGENTS) ─────────────────────  │  │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Agent 09 — Document Intelligence                       Port 8509          │  │  │
│  │  │  PDF · SWIFT · OCR · 25 document types · PII masking pre-LLM             │  │  │
│  │  │  Feeds: Agents 01 · 03 · 04 · 06 · 07 · 08 · 10                          │  │  │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                                    │  │
│  │  ┌────────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  MCP Authentication Gateway                             Port 8443          │  │  │
│  │  │  JWT Validation · Role Authorization · Audit Logging · Rate Limiting       │  │  │
│  │  └────────────────────────────────────────────────────────────────────────────┘  │  │
│  │                                       ↓                                           │  │
│  │               ┌───────────────────────────────────┐                              │  │
│  │               │  SQS Alert Queue (FIFO + DLQ)     │                              │  │
│  │               └───────────────────────────────────┘                              │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                         ↕                                                │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                           AI INFERENCE LAYER                                      │  │
│  │                                                                                    │  │
│  │  AWS Bedrock (VPC Endpoint — no internet egress) or OpenAI via NAT Gateway        │  │
│  │  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐    │  │
│  │  │ Claude Sonnet /      │  │ Claude Haiku /        │  │ Bedrock Guardrails   │    │  │
│  │  │ GPT-4o               │  │ GPT-4o-mini           │  │ PII protection       │    │  │
│  │  │ SAR drafting         │  │ Triage / scoring      │  │ Output filtering     │    │  │
│  │  │ Dispute analysis     │  │ Fast-path nodes       │  │ Hallucination guard  │    │  │
│  │  │ Compliance narrative │  │                       │  │                      │    │  │
│  │  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘    │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                         ↕                                                │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                     MCP TOOL SERVER LAYER (ECS Fargate)                           │  │
│  │                                                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │  │
│  │  │ TMS          │  │ Core Banking │  │ Watchlist    │  │ Adverse      │          │  │
│  │  │ Connector    │  │ Connector    │  │ Screener     │  │ Media        │          │  │
│  │  │ Port 8001    │  │ Port 8002    │  │ Port 8003    │  │ Port 8004    │          │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘          │  │
│  │                                                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │  │
│  │  │ Network      │  │ Case         │  │ Wealth/CRM   │  │ Regulatory   │          │  │
│  │  │ Intelligence │  │ Management   │  │ Connector    │  │ Feed         │          │  │
│  │  │ Port 8005    │  │ Port 8006    │  │ Port 8007    │  │ Port 8008    │          │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘          │  │
│  │                                                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                            │  │
│  │  │ Market Data  │  │ Loan/Credit  │  │ Payments/ACH │                            │  │
│  │  │ Connector    │  │ Connector    │  │ Connector    │                            │  │
│  │  │ Port 8009    │  │ Port 8010    │  │ Port 8011    │                            │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                            │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                        ↕ PrivateLink / VPN / Direct Connect                              │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              DATA LAYER                                           │  │
│  │                                                                                    │  │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐                │  │
│  │  │ Aurora           │  │ DynamoDB         │  │ S3 Object Lock   │                │  │
│  │  │ PostgreSQL       │  │ Audit Trail      │  │ SAR/CTR/Case     │                │  │
│  │  │ Multi-AZ         │  │ Append-only,     │  │ Documents        │                │  │
│  │  │ LangGraph HITL   │  │ IAM-enforced,    │  │ WORM / 5-year    │                │  │
│  │  │ checkpoint store │  │ examination-ready│  │ BSA retention    │                │  │
│  │  │ log_stmt=none    │  │                  │  │ Object Lock Gov. │                │  │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘                │  │
│  │                                                                                    │  │
│  │  ┌──────────────────┐  ┌──────────────────┐                                      │  │
│  │  │ ElastiCache      │  │ S3 (Audit        │                                      │  │
│  │  │ Redis            │  │  Archive,         │                                      │  │
│  │  │ Sessions / JWKS  │  │  Glacier 5yr     │                                      │  │
│  │  │ cache / Rate lmt │  │  Macie scanning) │                                      │  │
│  │  └──────────────────┘  └──────────────────┘                                      │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                 SECURITY & OPERATIONS LAYER (Cross-Cutting)                       │  │
│  │  Secrets Manager · KMS (per-agent CMKs) · CloudTrail · CloudWatch Alarms          │  │
│  │  AWS Config (compliance rules) · Security Hub · GuardDuty · Amazon Macie          │  │
│  └────────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────┘

EXTERNAL INTEGRATIONS (via MCP Tool Servers + NAT Gateway)
├── TMS Platforms:      Actimize · Verafin · NICE · Oracle Mantas
├── Core Banking:       FIS · Fiserv · Jack Henry · Temenos T24
├── Watchlists:         Refinitiv World-Check · LexisNexis Bridger · ComplyAdvantage · OFAC SDN
├── Adverse Media:      Dow Jones Risk & Compliance · LexisNexis Nexis+
├── Network Intel:      Sayari Analytics · OpenCorporates · Quantexa
├── Case Management:    ServiceNow GRC · Actimize Case Manager · Salesforce FSC
├── Wealth/CRM:         Salesforce · Redtail · Orion · Tamarac
├── Regulatory Feeds:   FinCEN · OCC · Federal Reserve · FDIC · CFPB · SEC · FINRA
├── Market Data:        Bloomberg · Refinitiv · ICE Data Services
├── Loan/Credit:        Fiserv LoanServ · Encompass · nCino
└── Payments/ACH:       FedACH · EPN · Nacha · SWIFT · Fedwire
```

---

## Per-Agent Summary: What Each Agent Does and Why

### Agent 01 — Financial Crime Investigation
**Path:** `01-financial-crime-investigation-agent/` | **Port:** 8501

**Problem it solves:** A BSA analyst today spends 35-40 hours on a single SAR investigation:
pulling transaction history, checking watchlists, reviewing adverse media, mapping counterparty
networks. Most of that is data assembly. Agent 01 automates the assembly; the analyst makes
the judgment call.

**8-node workflow:**
```
TMS Alert → Customer Profile + KYC → 12-month Transaction Analysis
→ OFAC/PEP/Sanctions Screening → Adverse Media → Network Analysis
→ Composite Risk Score → SAR Generation → BSA OFFICER REVIEW GATE → Case Finalization
```

**LLM boundary:** LLM drafts the SAR narrative. The BSA Officer must approve before filing.
SAR threshold ($5,000) and tipping-off prohibition are enforced in Python.

**Key integrations:** Agent 02 escalates its highest-priority alerts to Agent 01.
Agent 03 KYC refresh findings (confirmed high-risk) feed Agent 01 as case triggers.
Agent 04 fraud detections with SAR indicators feed Agent 01.

---

### Agent 02 — AML/TMS Enhancement
**Path:** `02-aml-tms-enhancement-agent/` | **Port:** 8502

**Problem it solves:** TMS systems generate 85-92% false positives. Analysts spend 450+
hours per day working alerts that will be cleared. Agent 02 scores each alert before it
enters the analyst queue, suppressing obvious false positives with full audit trails and
passing genuine suspicious activity forward.

**Scoring pipeline:**
```
Alert Ingest → Customer Context → Historical FP Patterns
→ Feature Extraction → Rule Pre-Score (30%) + LLM Analysis (50%) + Historical Base Rates (20%)
→ Composite FP Probability → Route Decision
```

**Routing decisions (Python — not LLM):**
- SUPPRESS (FP ≥ 85%): Justification narrative required; 90-day BSA Officer review
- DOWNGRADE (FP 60-84%): Low-priority analyst queue
- PASS-THROUGH (FP 15-59%): Normal analyst queue
- ESCALATE (FP < 15%): Immediate Agent 01 referral

**Critical constraint:** PEP flags and OFAC proximity are hard overrides — they force
ESCALATE regardless of FP score.

---

### Agent 03 — KYC/CDD Perpetual Monitoring
**Path:** `03-kyc-cdd-perpetual-agent/` | **Port:** 8503

**Problem it solves:** KYC reviews happen on a calendar schedule (annual, triennial) regardless
of customer risk activity. Agent 03 monitors continuously, triggering refreshes when risk
events occur rather than waiting for the calendar.

**12-node workflow:**
```
Trigger Evaluation → Customer Risk Profile → Document Collection
→ Watchlist Screening → Adverse Media Check → Risk Rescoring (8 factors)
→ [Routing] → HUMAN REVIEW GATE → KYC Record Update → Finalize
```

**8-factor SR 11-7 scoring model:**
- Transaction behavior 20%, PEP status 15%, Adverse media 15%
- Jurisdiction risk 15%, Document completeness 10%, Beneficial ownership 10%
- Industry/product risk 10%, Account tenure 5%

**Hard overrides (Python frozensets):**
- OFAC hit → ESCALATE, always, no score combination overrides
- PEP flag → minimum EDD_REQUIRED, always

**Key integrations:** Feeds Agent 05 (Wealth RM Copilot) with current KYC status,
watchlist flags, and document completeness so RMs never propose action on a customer
with a pending EDD review.

---

### Agent 04 — Real-Time Fraud Detection
**Path:** `04-fraud-detection-agent/` | **Port:** 8504

**Problem it solves:** Card fraud, ACH fraud, and account takeover require sub-second
decisions at transaction time. But simple rule engines miss sophisticated attacks. Agent 04
runs a real-time rule engine path (<200ms) alongside an asynchronous enrichment path
(device intelligence, behavioral analysis, LLM synthesis) and merges both scores before
the transaction settles.

**Two-path 14-node architecture:**
```
Transaction Intake → Account Context → Feature Extraction → Rule Engine Pre-Score
                                               ↓ (async, parallel)
                              Device Intelligence + Behavioral Analysis + LLM Synthesis
                                               ↓
                              Composite Score (Rules 30% + LLM 50% + Historical 20%)
```

**Decision thresholds (Python — not LLM):**
- ≥ 85: BLOCK (hard block — no human override at transaction time)
- 65-84: STEP_UP_AUTH (challenge customer)
- 40-64: ANALYST_REVIEW
- < 40: ALLOW

**Hard block triggers (Python frozenset, override all scores):**
- Confirmed fraud IP (RULE-091)
- Tor exit node (RULE-092)

**Key integrations:**
- BEC fraud detections route to Agent 10 (Payments Compliance) for Reg E/UCC 4A processing
- SAR-threshold fraud events feed Agent 01 (Financial Crime Investigation)
- Reg E auto-disclosure on all BLOCK decisions

---

### Agent 05 — Wealth & RM Copilot
**Path:** `05-wealth-rm-copilot/` | **Port:** 8505

**Problem it solves:** Relationship managers spend 35-40% of their time on administrative
work: preparing for client meetings, writing investment proposals, documenting Reg BI
suitability rationale. Agent 05 automates that assembly; the RM makes the recommendation.

**11-node workflow:**
```
RM Request → Client Profile (CRM + IPS + Portfolio) → Portfolio Analysis
→ Market Intelligence → Suitability Check (Python — NOT LLM) → Recommendation Engine
→ Content Drafting (LLM) → FINRA 2210 Compliance Check → RM APPROVAL GATE → Archive
```

**Critical design decision:** Suitability determination is Python-only. This is an explicit
Reg BI architectural choice — an LLM output cannot constitute a documented suitability
analysis. The Python suitability engine generates the rationale; the LLM drafts the
client-facing communication.

**Key integrations:** Reads current KYC/watchlist status from Agent 03 before any
recommendation is drafted. If Agent 03 shows a pending EDD review, Agent 05 flags
the RM before they contact the client.

---

### Agent 06 — Regulatory Change Management
**Path:** `06-regulatory-change-agent/` | **Port:** 8506

**Problem it solves:** A mid-size bank receives 200-400 regulatory changes per year
from OCC, Federal Reserve, FDIC, FinCEN, CFPB, SEC, FINRA, NCUA, and FATF.
Manually triaging, assessing impact, mapping to policies, and tracking remediation takes
a 4-analyst compliance team most of their capacity. Agent 06 automates intake through
remediation planning.

**12-node workflow:**
```
Change Intake → Source Validation → Scope Determination → Policy Mapping
→ Gap Analysis (LLM) → Impact Scoring (Python) → Routing Decision (Python)
→ HUMAN REVIEW GATE → Remediation Planning (LLM) → Stakeholder Notification (LLM)
→ Tracking Update → Finalize
```

**5-factor Python impact scoring (SR 11-7):**
- Authority tier 25%, Deadline urgency 25%, Scope breadth 20%
- Policy depth 15%, Remediation complexity 15%

**Impact tiers:** CRITICAL ≥ 0.85 · HIGH 0.65-0.84 · MEDIUM 0.40-0.64 · LOW < 0.40

**Hard overrides:**
- Enforcement actions → minimum HIGH + mandatory HITL
- Already-effective Tier 1 regulations → CRITICAL
- MEDIUM with compliance window < 30 days → HIGH escalation

**Unique infrastructure:** EventBridge + Lambda for automated regulatory feed ingestion
from 9 regulatory sources. DynamoDB append-only audit trail. S3 Object Lock GOVERNANCE
5-year retention for regulatory correspondence.

---

### Agent 07 — Trading Surveillance
**Path:** `07-trading-surveillance-agent/` | **Port:** 8507

**Problem it solves:** A 6-analyst trading surveillance team reviews 800 alerts per month
with 90%+ false positive rates. FINRA examinations penalize both missed genuine violations
and inadequate documentation of dismissed alerts. Agent 07 automates pattern detection,
provides regulatory citations for every alert disposition, and maintains the case record
required under FINRA Rule 3110.

**12-node workflow:**
```
Alert Intake → Data Enrichment → Pattern Detection (Python, 11 alert types)
→ Market Context (LLM) → Risk Scoring (Python) → Routing Decision (Python)
→ HUMAN REVIEW GATE → Investigation (LLM) → Disposition (LLM)
→ Case Tracking Update → Finalize
```

**11 alert types:** Layering/Spoofing · Front Running · Wash Trading · Insider Trading
· Marking the Close · Excessive Trading · Best Execution Failure · Short Selling Violation
· Cross-Market Manipulation · Information Barrier Breach · Unusual Activity

**Hard overrides (Python frozenset):**
- INSIDER_TRADING, INFORMATION_BARRIER_BREACH, CROSS_MARKET_MANIPULATION
  → always CRITICAL + mandatory HITL, regardless of score

**Critical constraint:** SAR determination uses Python $5,000 threshold — never LLM.
Tipping-off prohibition (18 U.S.C. § 1960) enforced in LLM system prompt.

---

### Agent 08 — Credit Underwriting
**Path:** `08-credit-underwriting-agent/` | **Port:** 8508

**Problem it solves:** Loan decisions take 3-5 days. Most of that is document review,
credit calculation, fair lending checks, and generating the adverse action notice when
declined. Agent 08 runs all of this in minutes, with ECOA-compliant adverse action
reasons and fair lending flags computed in Python.

**12-node workflow:**
```
Application Intake → Document Verification → Credit Analysis
→ DTI/LTV Scoring (Python) → OFAC Hard Block → Fair Lending Flags (Python)
→ Risk Tier Assignment → UNDERWRITER REVIEW GATE → Decision Generation
→ ECOA Adverse Action (Python) → Disclosure Drafting (LLM) → Finalize
```

**12 loan types:** Conventional · FHA · VA · USDA · Jumbo · SBA 7(a) · SBA 504
· HELOC · Construction · Bridge · Commercial · Hard Money

**Hard decline rules (Python — not LLM, not configurable):**
- DTI > 50%
- FICO < 580 (conventional)
- Chapter 7 bankruptcy < 2 years
- OFAC hit (unresetable — overrides all other factors)

**ECOA compliance:** 12 mapped adverse action reason codes (Python frozensets).
Geographic census tract flagging for HMDA. The LLM does NOT determine adverse action
reasons — Python maps score factors to the required ECOA reason codes.

---

### Agent 09 — Document Intelligence
**Path:** `09-document-intelligence-agent/` | **Port:** 8509

**Problem it solves:** Every other agent in the suite assumes it receives structured
input. But banks live in a world of PDFs: a 1003 is a scanned form, a SWIFT MT103 is
a proprietary FIN-format text message, a government ID is a photograph. Without Agent 09,
each team manually re-keys data before specialist agents can process it. With Agent 09,
documents flow in and structured data flows out.

**12-node workflow:**
```
Document Intake (SHA-256 hash) → Text Extraction (PDF/OCR/SWIFT)
→ PII Detection (Python regex — BEFORE LLM) → Document Classification (LLM)
→ Field Extraction (LLM, on masked text) → Validation (Python rules + SWIFT screening)
→ Confidence Scoring (Python, 4-factor) → Routing Decision (Python constant)
→ HUMAN REVIEW GATE (low-confidence / sensitive doc types)
→ Enrichment (LLM) → Output Packaging → Audit Finalize
```

**25 document types across 5 categories:**
- Lending (10): Form 1003, Commercial apps, Appraisals, Tax Returns (1040/1065/1120),
  Financial Statements, Bank Statements, SBA Forms 1919/1920
- Payments (3): SWIFT MT103, SWIFT MT202, Wire Instructions
- Capital Markets (2): Trade Confirmations, Brokerage Statements
- KYC (4): Government IDs, Entity Documents, Trust Documents, Beneficial Ownership Certs
- Compliance (5): Regulatory Exam Letters, Consent Orders, Adverse Media, SAR Forms, CTRs

**ALWAYS_HITL document types (Python frozenset, immutable):**
- GOVERNMENT_ID, SAR_FORM, CTR_FORM, CONSENT_ORDER

**Security architecture:**
- PII masking (7 regex types: SSN, passport, account numbers, routing numbers, EIN,
  phone, email) runs before any LLM call
- Raw document bytes never stored in LangGraph state (only SHA-256 hash + 500-char preview)
- DOCUMENT_ROUTING dict is a Python constant — no LLM response can redirect routing
- Text cache cleared by audit_finalize (no residual PII after processing)

**Suite role:** Recommended first deployment. Every other agent benefits immediately
from Agent 09's structured output. Agent 09 feeds Agents 01, 03, 04, 06, 07, 08, 10.

---

### Agent 10 — Payments Compliance
**Path:** `10-payments-compliance-agent/` | **Port:** 8510

**Problem it solves:** A payments compliance analyst spends 143 minutes per disputed
ACH transaction manually looking up return codes, calculating Reg E SLA deadlines,
checking OFAC country codes, drafting customer notices, and writing compliance memos.
Every regulatory determination is time-sensitive (provisional credit due in 10 business
days; OFAC blocking report in 10 business days; SAR in 30 days). Agent 10 computes all
deadlines, validates all return codes, and drafts all notices in under 35 seconds.

**12-node workflow:**
```
Payment Intake (SHA-256, account masking) → Sanctions Screening (OFAC/FATF, Python only)
→ Nacha Validation (R01-R77, C01-C09, CTR threshold) → Reg E Assessment (SLA calc, Python)
→ Dispute Analysis (LLM, masked text) → Compliance Scoring (Python, 5-factor)
→ Compliance Analysis (LLM, reviewer narrative) → Routing Decision (Python)
→ HUMAN REVIEW GATE → Resolution Drafting (LLM notices) → Output Packaging → Audit Finalize
```

**ALWAYS_HITL payment events (Python frozenset, immutable):**
OFAC_HOLD · SAR_CANDIDATE · CTR_THRESHOLD · HIGH_RISK_COUNTRY_WIRE
· UNAUTHORIZED_WIRE · LATE_RETURN_DISPUTE

**5-factor SR 11-7 compliance risk scoring:**
- Sanctions/OFAC 35%, Unauthorized transaction 25%, Amount 20%, SLA status 10%, Pattern 10%
- OFAC hit is a hard override: forces score=1.0 and tier=CRITICAL regardless of other factors

**Nacha return code coverage:** All R01-R77 return codes (standard 2-day and unauthorized
60-day windows) + C01-C09 NOC codes with 6-banking-day originator update deadline.

**Key integrations:**
- Receives SWIFT MT103/MT202 structured output from Agent 09
- Receives BEC fraud flags from Agent 04 (wire fraud → UCC Article 4A review)
- OFAC hits and SAR candidates route to Agent 01 (Financial Crime Investigation)

---

### Agent 11 — Model Risk Management
**Path:** `11-model-risk-agent/` | **Port:** 8511

**Problem it solves:** SR 11-7 requires independent validation of every AI scoring model
in production. A single HIGH-tier model validation event — conceptual soundness review,
back-testing, population stability analysis, sensitivity analysis, benchmark comparison,
written report, MRO sign-off — costs $20,000–$57,000 in labor and takes 92–163 hours.
Five models on monthly monitoring + annual revalidation + triggered reviews costs
$840,000–$1.46M per year in pure labor. Agent 11 reduces cost per event to $3,500–$7,000
while producing a more defensible, examiner-ready audit trail than any manual process.

**12-node validation pipeline:**
```
Model Inventory Lookup (Python, MODEL_REGISTRY) → Data Sample Pull (Python, metric deltas)
→ Conceptual Soundness Review (LLM narrative only, §§ 5-7) → Outcomes Analysis (Python:
Gini/KS/FPR/FNR/AUC-ROC deltas + LLM interpretation) → Population Stability Analysis
(Python: PSI = Σ(Actual%−Expected%)×ln(Actual%/Expected%)) → Benchmark Comparison
(Python: Gini point delta vs. challenger) → Sensitivity Analysis (Python: weight
normalization, concentration, hard rule coverage) → Risk Tier Determination (Python,
HITL conditions from frozenset) → Validation Narrative (LLM report draft) → Routing
Decision (Python, explicit is False fail-safe) → HUMAN REVIEW GATE (MRO/CRO)
→ Audit Finalize (Python: DynamoDB registry + S3 Object Lock report)
```

**LLM vs. Python boundary (SR 11-7 compliance requirement):**
- **Python only:** risk tier, Gini/KS/FPR/FNR/PSI flags, HITL conditions, routing, validation outcome, registry update, audit trail, S3 retention
- **LLM only:** conceptual soundness review text, metric interpretation narrative, full validation report prose, monitoring assessment text
- **Human only:** final validation outcome for HIGH-tier models (MRO decision at interrupt gate)

**ALWAYS_HITL conditions (Python frozenset, 9 conditions, immutable at runtime):**
HIGH_TIER_INITIAL_VALIDATION · HIGH_TIER_CHANGE_VALIDATION · ANNUAL_REVALIDATION_HIGH_TIER
· PERFORMANCE_DEGRADATION_TRIGGERED · PSI_CRITICAL · MATERIAL_FINDING
· CHALLENGER_UNDERPERFORMS · HARD_RULE_VIOLATION_DETECTED (→ CRO) · FAIR_LENDING_FLAG

**Performance degradation thresholds (Python constants):**
- Accuracy decline >5pp, Gini decline >10 points, KS decline >8pp
- FPR increase >5pp, FNR increase >3pp (tighter — missing genuine suspicious activity has greater BSA risk)
- PSI: STABLE <0.10, WARNING 0.10-0.25, CRITICAL >0.25

**Models validated (all HIGH-tier):**
- AGT02-FP-SCORE-v1 (Agent 02 AML false positive composite)
- AGT03-KYC-RISK-v1 (Agent 03 KYC customer risk score)
- AGT04-FRAUD-SCORE-v1 (Agent 04 fraud composite)
- AGT07-SURV-RISK-v1 (Agent 07 trading surveillance risk)
- AGT08-CREDIT-SCORE-v1 (Agent 08 credit underwriting composite)

**Retention architecture:** S3 Object Lock GOVERNANCE mode, 10-year retention (model
life + BSA 5-year). GOVERNANCE mode: deletion requires authenticated administrator
credentials with `s3:BypassGovernanceRetention` — and that bypass creates a CloudTrail
audit event. Aurora PostgreSQL audit table has database-level `no_update` and `no_delete`
rules enforced as SQL rules, not application logic.

**Key integrations:**
- Validates scoring models of Agents 02, 03, 04, 07, 08
- Triggers MRO notification when validation event requires HITL
- Escalates to CRO on HARD_RULE_VIOLATION_DETECTED
- CloudWatch + EventBridge trigger monthly automated monitoring runs

---

## Agent Data Flow Diagram

```
EXTERNAL EVENTS AND DOCUMENTS
│
├── Unstructured Document Received ────────────────────────────────────────────┐
│   (PDF · SWIFT FIN · Scanned form · Word · Image)                            ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 09              │
│                                                               │  Document Intelligence  │
│                                                               │                        │
│                                                               │  PII mask (Python)     │
│                                                               │  → Classify (LLM)      │
│                                                               │  → Extract fields (LLM)│
│                                                               │  → Validate (Python)   │
│                                                               │  → Confidence score    │
│                                                               │  → Route to agent      │
│                                                               └────────────────────────┘
│                                                                        │
│     ┌──────────────────┬──────────────────┬──────────────────┬────────┴──────────┐
│     ▼                  ▼                  ▼                  ▼                  ▼
│  SWIFT/Wire          Loan App/       Gov't ID /       Exam Letter /      Trade Confirm /
│  → Agent 01/10       Tax Return      Beneficial       Consent Order       Brokerage Stmt
│                       → Agent 08      Ownership        → Agent 06          → Agent 07
│                                       → Agent 03
│
├── TMS Alert Fired ─────────────────────────────────────────────────────────────┐
│                                                                                 ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 02              │
│                                                               │  TMS Enhancement       │
│                                                               │                        │
│                                                               │  FP < 15%?  → ESCALATE │──► Agent 01
│                                                               │  FP 15-60%? → PASS-THR │──► Analyst Queue
│                                                               │  FP 60-85%? → DOWNGRADE│──► Low Priority Queue
│                                                               │  FP ≥ 85%?  → SUPPRESS │──► Audit Log (BSA review)
│                                                               └────────────────────────┘
│
├── Risk Event (Adverse media · Watchlist hit · SAR filed) ──────────────────────┐
│                                                                                 ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 03              │
│                                                               │  KYC/CDD Perpetual     │
│                                                               │                        │
│                                                               │  8-factor rescore      │
│                                                               │  OFAC → ESCALATE (hard)│
│                                                               │  PEP → EDD (hard)      │
│                                                               │  → KYC record update   │
│                                                               │  → RM alert → Agent 05 │
│                                                               └────────────────────────┘
│                                                                        │
│                                         Agent 01 SAR confirmation ────┘
│                                         feeds back as risk trigger
│
├── Transaction Processed ────────────────────────────────────────────────────────┐
│                                                                                  ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 04              │
│                                                               │  Real-Time Fraud       │
│                                                               │                        │
│                                                               │  <200ms: Rules + Feats │
│                                                               │  Async: Device+Behav+LLM│
│                                                               │                        │
│                                                               │  ≥85: BLOCK            │
│                                                               │  65-84: STEP_UP_AUTH   │
│                                                               │  40-64: ANALYST_REVIEW │
│                                                               │  <40: ALLOW            │
│                                                               │                        │
│                                                               │  BEC → Agent 10        │──► Payments Compliance
│                                                               │  SAR → Agent 01        │──► Financial Crime
│                                                               └────────────────────────┘
│
├── RM Request (Meeting prep · Proposal · Review · Communication) ────────────────┐
│                                                                                  ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 05              │
│                                                               │  Wealth RM Copilot     │
│                                                               │                        │
│                                                               │  Client profile + IPS  │
│                                                               │  Portfolio analysis    │
│                                                               │  Suitability (Python)  │──► Reg BI doc (LLM draft)
│                                                               │  Content drafting (LLM)│
│                                                               │  FINRA 2210 check      │
│                                                               │  RM approval gate      │
│                                                               └────────────────────────┘
│                                                                        ↑
│                                              KYC status + watchlist ───┘
│                                              from Agent 03
│
├── Regulatory Change Published ──────────────────────────────────────────────────┐
│   (FinCEN · OCC · Fed · FDIC · CFPB · SEC · FINRA · NCUA · FATF)                ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 06              │
│                                                               │  Regulatory Change Mgmt│
│                                                               │                        │
│                                                               │  EventBridge ingestion │
│                                                               │  Gap analysis (LLM)    │
│                                                               │  Impact score (Python) │
│                                                               │  Remediation plan (LLM)│
│                                                               │  → Stakeholder notify  │
│                                                               └────────────────────────┘
│
├── Trading Alert Generated ──────────────────────────────────────────────────────┐
│   (TMS · Surveillance system · Real-time rule engine)                            ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 07              │
│                                                               │  Trading Surveillance  │
│                                                               │                        │
│                                                               │  11 pattern types      │
│                                                               │  Market context (LLM)  │
│                                                               │  Risk score (Python)   │
│                                                               │  Insider trading? Hard │
│                                                               │  CRITICAL + HITL (always)│
│                                                               │  SAR > $5K (Python)    │──► Agent 01
│                                                               └────────────────────────┘
│
├── Loan Application Submitted ───────────────────────────────────────────────────┐
│   (Direct · Agent 09 structured output)                                          ▼
│                                                               ┌────────────────────────┐
│                                                               │  Agent 08              │
│                                                               │  Credit Underwriting   │
│                                                               │                        │
│                                                               │  12 loan types         │
│                                                               │  DTI/LTV (Python)      │
│                                                               │  OFAC hard block       │
│                                                               │  Fair lending (Python) │
│                                                               │  ECOA adverse action   │──► Applicant notice (LLM)
│                                                               │  Underwriter review    │
│                                                               └────────────────────────┘
│
└── Payment Event / ACH Return / Dispute Filed ───────────────────────────────────┐
    (Direct · Agent 04 BEC flag · Agent 09 SWIFT output)                           ▼
                                                               ┌────────────────────────┐
                                                               │  Agent 10              │
                                                               │  Payments Compliance   │
                                                               │                        │
                                                               │  OFAC/FATF (Python)    │──► BSA_COMPLIANCE team
                                                               │  Nacha R01-R77 (Python)│
                                                               │  Reg E SLA (Python)    │──► Customer notice (LLM)
                                                               │  Provisional credit    │──► Core banking
                                                               │  5-factor score        │
                                                               │  SAR candidate (Python)│──► Agent 01
                                                               └────────────────────────┘
```

---

## Authentication Architecture (All 11 Agents)

All eleven agents share the same identity federation pattern. One Okta application per agent
is the recommended configuration — this allows separate group assignments (an RM should
access Agent 05, not Agent 01; a fraud analyst should not access Agent 07).

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       SHARED IDENTITY ARCHITECTURE                               │
│                                                                                  │
│  Customer Active Directory                                                       │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  GRP-BSA-Officers            → bsa_role: BSA_OFFICER                      │  │
│  │  GRP-AML-Investigators       → bsa_role: INVESTIGATOR                     │  │
│  │  GRP-AML-Auditors            → bsa_role: AUDITOR                          │  │
│  │  GRP-Fraud-Analysts          → fraud_role: ANALYST                        │  │
│  │  GRP-Wealth-RMs              → rm_role: RM                                │  │
│  │  GRP-Compliance-Officers     → compliance_role: OFFICER                   │  │
│  │  GRP-Trading-Surveillance    → trading_role: SURVEILLANCE_ANALYST         │  │
│  │  GRP-Credit-Underwriters     → credit_role: UNDERWRITER                   │  │
│  │  GRP-Dispute-Analysts        → payments_role: DISPUTE_ANALYST             │  │
│  │  GRP-Payments-Ops            → payments_role: PAYMENTS_OPS                │  │
│  │  GRP-Doc-Intelligence        → doc_role: DOC_REVIEWER                     │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                       │ Okta AD Agent (real-time sync)                           │
│                       ▼                                                          │
│  Okta SSO                                                                        │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  SAML App: Agent 01 — Financial Crime Investigation  (BSA_OFFICER, INVEST) │  │
│  │  SAML App: Agent 02 — AML/TMS Enhancement            (INVESTIGATOR, AUDIT) │  │
│  │  SAML App: Agent 03 — KYC/CDD Perpetual              (INVESTIGATOR, AUDIT) │  │
│  │  SAML App: Agent 04 — Real-Time Fraud Detection      (ANALYST)             │  │
│  │  SAML App: Agent 05 — Wealth RM Copilot              (RM)                  │  │
│  │  SAML App: Agent 06 — Regulatory Change Management   (OFFICER, AUDIT)      │  │
│  │  SAML App: Agent 07 — Trading Surveillance           (SURVEILLANCE_ANALYST)│  │
│  │  SAML App: Agent 08 — Credit Underwriting            (UNDERWRITER)         │  │
│  │  SAML App: Agent 09 — Document Intelligence          (DOC_REVIEWER)        │  │
│  │  SAML App: Agent 10 — Payments Compliance            (DISPUTE_ANALYST,     │  │
│  │                                                        PAYMENTS_OPS,        │  │
│  │                                                        BSA_OFFICER)         │  │
│  │                                                                             │  │
│  │  Attribute mapping: AD group → role claim in SAML assertion                │  │
│  │  MFA policy: Okta Verify Push or FIDO2 (enforced — no SMS OTP)             │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                       │ SAML 2.0 assertion                                       │
│                       ▼                                                          │
│  Amazon Cognito (one User Pool per agent)                                        │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Federation only — no credentials stored in Cognito                       │  │
│  │  Issues JWT (access_token + id_token, 8-hour expiry)                      │  │
│  │  JWT carries custom claims from Okta SAML:                                │  │
│  │    custom:bsa_role / custom:fraud_role / custom:rm_role                   │  │
│  │    custom:compliance_role / custom:trading_role / custom:credit_role      │  │
│  │    custom:payments_role / custom:doc_role                                 │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                       │ JWT                                                      │
│                       ▼                                                          │
│  ALB (per agent) → validates JWT → routes to ECS Fargate                         │
│  MCP Auth Gateway → validates JWT → authorizes tool calls by role                │
│                                                                                  │
│  OFFBOARDING: Remove user from AD group → Okta syncs immediately                │
│  Access revoked at next JWT refresh (max 8 hours) or sooner if AD account       │
│  is disabled (all active sessions fail on next request)                          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         AWS VPC (Per-Customer Isolated)                         │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                        PUBLIC SUBNETS (2 AZs)                             │  │
│  │  CloudFront Origin · ALB (per agent, 10 ALBs) · NAT Gateway               │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                               ↕                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    PRIVATE SUBNETS — APP TIER                             │  │
│  │  ECS Fargate: Agent UI tasks (01-10) · Agent Worker tasks                │  │
│  │  ECS Fargate: MCP Auth Gateway · MCP Tool Servers (01-11)                │  │
│  │  SQS Polling (no inbound needed) · VPC Endpoints (Bedrock, S3, etc.)     │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                               ↕                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    PRIVATE SUBNETS — DATA TIER                            │  │
│  │  Aurora PostgreSQL (Multi-AZ, log_statement=none, KMS CMK encrypted)      │  │
│  │  DynamoDB (VPC Endpoint — no internet routing)                            │  │
│  │  ElastiCache Redis (session + JWKS cache + rate limiting)                 │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  VPC Endpoints (private connectivity, no internet traffic):                     │
│  ├── com.amazonaws.*.bedrock-runtime  (LLM inference — Agents 01-10)           │
│  ├── com.amazonaws.*.secretsmanager   (API keys, DB credentials)               │
│  ├── com.amazonaws.*.s3               (document storage, audit trail)          │
│  ├── com.amazonaws.*.dynamodb         (audit trail, regulatory tracking)       │
│  └── com.amazonaws.*.sqs              (alert queues, inter-agent events)       │
└─────────────────────────────────────────────────────────────────────────────────┘
         ↕                                                    ↕
┌─────────────────┐                              ┌──────────────────────────────┐
│  Internet       │                              │  Customer On-Premise         │
│  (Watchlist,    │                              │  TMS · Core Banking ·        │
│  Adverse Media, │                              │  Case Management ·           │
│  OSINT, Reg     │                              │  Payments (FedACH/SWIFT) ·   │
│  feeds, OpenAI  │                              │  Loan Origination Systems    │
│  via NAT GW)    │                              │                              │
└─────────────────┘                              │  VPN / Direct Connect        │
                                                  └──────────────────────────────┘
```

---

## Security Controls Summary

| Control | Implementation | Regulatory Basis |
|---------|---------------|-----------------|
| **Encryption at rest** | KMS CMK per agent, per data store | PCI DSS, GLBA, SOC 2 |
| **Encryption in transit** | TLS 1.3 on all connections | PCI DSS, GLBA |
| **Identity federation** | Cognito + Okta SAML + AD | FFIEC authentication guidance |
| **MFA enforcement** | Okta Verify Push or FIDO2 (no SMS) | FFIEC CAT, NIST 800-63B AAL2 |
| **Account number masking** | ****{last4} at Agent 09/10 intake — never in checkpoint DB | GLBA, PCI DSS |
| **PII masking pre-LLM** | Python regex (7 types) before any LLM API call | GLBA Safeguards Rule |
| **Immutable audit trail** | DynamoDB / JSONL append-only; IAM blocks UpdateItem/DeleteItem | BSA 5-year retention (31 CFR 1010.430) |
| **WORM document storage** | S3 Object Lock GOVERNANCE mode, 5-year | BSA 31 U.S.C. § 5318 |
| **Routing as Python constant** | TARGET_TEAMS, DOCUMENT_ROUTING — no LLM can alter | SR 11-7, prompt injection defense |
| **HITL frozensets** | ALWAYS_HITL_* as Python frozensets, immutable at runtime | SR 11-7, Reg E, BSA, OFAC |
| **OFAC hard override** | Python `if ofac_hit: tier=CRITICAL, score=1.0` — not a model parameter | IEEPA 50 U.S.C. § 1705 |
| **Aurora log_statement=none** | No payment data written to query logs | GLBA, PCI DSS data minimization |
| **Tipping-off prohibition** | LLM system prompts explicit; dashboard warning displayed | 31 U.S.C. § 5318(g)(2), 18 U.S.C. § 1960 |
| **Data residency** | Bedrock VPC endpoint — LLM inference stays in AWS account | Bank data privacy requirements |
| **Network isolation** | Per-customer VPC; no shared infrastructure | Multi-tenant data isolation |
| **Secrets management** | Secrets Manager; auto-rotation; no env vars | SOC 2, GLBA |
| **Container hardening** | Non-root (uid=1000), read-only filesystem, multi-stage build | NIST 800-190, CIS Docker Benchmark |
| **Threat detection** | GuardDuty + Security Hub + Amazon Macie (PII scanning on S3) | SOC 2, OCC expectations |
| **Configuration compliance** | AWS Config rules with auto-remediation | SOC 2, OCC 12 CFR Part 30 |

---

## Regulatory Coverage Matrix (Full Suite — All 11 Agents)

| Regulation | Ag01 | Ag02 | Ag03 | Ag04 | Ag05 | Ag06 | Ag07 | Ag08 | Ag09 | Ag10 | Ag11 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| BSA 31 U.S.C. § 5318 (SAR filing) | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | — | — | ✅ | ✅ |
| FinCEN CDD Rule (31 CFR 1020.210) | ✅ | ✅ | ✅ | — | — | — | — | — | ✅ | — | — |
| OFAC / IEEPA (SDN screening) | ✅ | ✅ | ✅ | ✅ | — | — | — | ✅ | ✅ | ✅ | — |
| FATF R.10 (Customer due diligence) | ✅ | — | ✅ | — | — | — | — | — | — | ✅ | — |
| FATF R.12 (PEP enhanced due diligence) | ✅ | ✅ | ✅ | — | — | — | — | — | — | ✅ | — |
| FATF R.20 (Suspicious transaction reporting) | ✅ | ✅ | — | ✅ | — | — | ✅ | — | — | ✅ | — |
| USA PATRIOT Act § 326 (CIP) | ✅ | — | ✅ | — | — | — | — | ✅ | ✅ | — | — |
| FIN-2014-G001 (SAR narrative format) | ✅ | — | — | — | — | — | ✅ | — | — | — | — |
| SR 11-7 (Model risk management — all agents) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SR 11-7 (Model validation — Agent 11 primary) | — | — | — | — | — | — | — | — | — | — | ✅ |
| FFIEC BSA/AML Examination Manual | ✅ | ✅ | ✅ | — | — | ✅ | — | — | — | — | ✅ |
| OCC Model Risk Guidance (2011-12) | — | — | — | — | — | — | — | — | — | — | ✅ |
| 18 U.S.C. § 1960 (No tipping off) | ✅ | — | — | — | — | — | ✅ | — | — | ✅ | — |
| 5-year BSA record retention (31 CFR 1010.430) | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | — | ✅ | ✅ |
| 10-year model validation retention (Agent 11) | — | — | — | — | — | — | — | — | — | — | ✅ |
| Reg E (12 CFR Part 1005) — EFT disputes | — | — | — | ✅ | — | — | — | — | — | ✅ | — |
| Nacha Operating Rules (R01-R77, NOC C01-C09) | — | — | — | ✅ | — | — | — | — | — | ✅ | — |
| CFPB Prepaid Rule (12 CFR Part 1005 Subpt E) | — | — | — | — | — | — | — | — | — | ✅ | — |
| UCC Article 4A (Wire transfer liability) | — | — | — | — | — | — | — | — | — | ✅ | — |
| 31 CFR 501.604 (OFAC blocking report) | — | — | — | — | — | — | — | — | — | ✅ | — |
| 31 CFR 1010.311 (CTR filing $10K) | ✅ | — | — | — | — | — | — | — | — | ✅ | — |
| Reg BI (17 CFR 240.15l-1) | — | — | — | — | ✅ | — | — | — | — | — | — |
| FINRA Rule 2111 (Suitability) | — | — | — | — | ✅ | — | — | — | — | — | — |
| FINRA Rule 2210 (Communications) | — | — | — | — | ✅ | — | ✅ | — | — | — | — |
| FINRA Rule 3110 (Supervisory procedures) | — | — | — | — | — | — | ✅ | — | — | — | — |
| FINRA Rule 4511 (Books and records) | — | — | — | — | — | — | ✅ | — | ✅ | — | — |
| ERISA (retirement account fiduciary) | — | — | — | — | ✅ | — | — | — | — | — | — |
| SEC Rule 10b-5 (Market manipulation) | — | — | — | — | — | — | ✅ | — | — | — | — |
| Dodd-Frank § 747 (Spoofing ban) | — | — | — | — | — | — | ✅ | — | — | — | — |
| Reg SHO Rules 203-204 (Short selling) | — | — | — | — | — | — | ✅ | — | — | — | — |
| ECOA / Reg B (Equal Credit Opportunity) | — | — | — | — | — | — | — | ✅ | ✅ | — | ✅ |
| HMDA (Home Mortgage Disclosure) | — | — | — | — | — | — | — | ✅ | ✅ | — | — |
| CRA (Community Reinvestment Act) | — | — | — | — | — | — | — | ✅ | — | — | — |
| Reg Z / TILA (Truth in Lending) | — | — | — | — | — | — | — | ✅ | — | — | — |
| SBA Loan Program (7(a) / 504) | — | — | — | — | — | — | — | ✅ | ✅ | — | — |
| FFIEC / OCC 12 CFR Part 30 (Safety & Soundness) | — | — | — | — | — | ✅ | — | — | — | — | ✅ |
| GLBA Safeguards Rule (PII / data security) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |

---

## Technology Stack Reference

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Agent orchestration | LangGraph | ≥ 0.2.28 | StateGraph DAG; deterministic routing; HITL interrupt_before |
| LLM (primary) | OpenAI GPT-4o | Latest | Default for local/POC/demo deployments (temperature=0) |
| LLM (enterprise) | Claude Sonnet via AWS Bedrock | Latest | Production option; VPC endpoint, no internet egress |
| LLM (fast-path) | Claude Haiku / GPT-4o-mini | Latest | Low-latency triage and scoring nodes |
| LLM Guardrails | Bedrock Guardrails | — | PII protection, output filtering (production) |
| UI | Streamlit | ≥ 1.40 | Demo/POC dashboard per agent |
| API layer | FastAPI | ≥ 0.115 | MCP Gateway, agent REST APIs |
| HITL Checkpoint | LangGraph MemorySaver (dev) | — | Single-process, not persistent |
| HITL Checkpoint | LangGraph PostgresSaver (prod) | — | Aurora PostgreSQL; durable HITL queue |
| Databases | Aurora PostgreSQL + DynamoDB | PG 15+ | Cases + checkpoint + immutable audit |
| Vector store | pgvector (Aurora) | — | Production; ChromaDB for local dev |
| Cache | ElastiCache Redis | — | Session, JWKS, rate limiting |
| Container runtime | ECS Fargate | — | Non-root (uid=1000), read-only filesystem |
| IaC | Terraform | ≥ 1.6 | Per-customer module; ~15 min full-suite deploy |
| CI/CD | AWS CodePipeline + CodeBuild | — | ECR image scan + rolling ECS deploy |
| Auth | Cognito + Okta + Active Directory | — | SAML 2.0 federation; no credentials in application |
| Secrets | AWS Secrets Manager | — | Auto-rotation; no env var secrets |
| Encryption | AWS KMS (CMK per agent) | — | Per-datastore keys; key revocation |
| Monitoring | CloudWatch + X-Ray | — | SLA alarms, distributed tracing |
| PII scanning | Amazon Macie | — | S3 audit trail scanning for PII leakage |
| Threat detection | GuardDuty + Security Hub | — | Automated compliance rules, anomaly detection |
| Configuration | AWS Config | — | Compliance rule enforcement with auto-remediation |
| Document OCR | Tesseract (Agent 09) | 5.x | Open-source OCR for scanned documents |

---

## Deployment Topology Options

### Option 1: Separate AWS Accounts (Recommended for Large Institutions)
```
AWS Organizations
├── Management Account (billing consolidation, AWS SSO)
├── Shared Services Account (ECR, CodePipeline, Terraform state)
├── Institution A Account
│   └── VPC → All 10 agent stacks, fully isolated
├── Institution B Account
│   └── VPC → All 10 agent stacks, fully isolated
└── Institution C Account
    └── VPC → Selected agents (e.g., 02 + 01 + 10 for AML + payments focus)
```
**Best for:** Institutions with contractual requirements for account-level isolation;
large banks with strict data governance; multi-bank holding companies.

### Option 2: Single Account, Multiple VPCs (Cost-Optimized)
```
Single AWS Account
├── VPC: Institution A (10.10.0.0/16)
│   ├── ECS Cluster: institution-a (all 10 agent tasks)
│   ├── RDS Aurora: institution-a-db (LangGraph checkpoint + cases)
│   ├── DynamoDB: institution-a-audit (append-only audit trail)
│   └── KMS, Secrets, S3: customer-a-namespaced
└── VPC: Institution B (10.20.0.0/16)
    ├── ECS Cluster: institution-b
    ├── RDS Aurora: institution-b-db
    └── KMS, Secrets, S3: customer-b-namespaced
```
**Best for:** Smaller institutions; POC environments; customers comfortable with
VPC-level isolation; Presidio-managed deployments across multiple customers.

### Option 3: Single Institution, Self-Managed (Direct Deployment)
```
Institution's Own AWS Account
└── VPC → All 11 agents deployed by institution's IT/cloud team
    Terraform modules provided; institution owns and operates
    Presidio provides integration support and agent customization
```
**Best for:** Institutions with mature AWS practices who want full ownership;
avoids any managed service arrangement; common for Tier 1 banks.

### Recommended Deployment Order
Deploy agents in this sequence to maximize immediate value and suite integration:

```
1. Agent 09 — Document Intelligence (horizontal, feeds all others)
2. Agent 01 — Financial Crime Investigation (foundation AML workflow)
3. Agent 02 — AML/TMS Enhancement (immediately reduces analyst workload)
4. Agent 03 — KYC/CDD Perpetual (feeds Agent 01 + Agent 05)
5. Agent 10 — Payments Compliance (Reg E + Nacha + OFAC payments layer)
6. Agent 04 — Real-Time Fraud Detection (connects to Agent 10 for BEC)
7. Agent 06 — Regulatory Change Management (compliance operations)
8. Agent 07 — Trading Surveillance (capital markets compliance)
9. Agent 08 — Credit Underwriting (lending workflow)
10. Agent 05 — Wealth RM Copilot (revenue-generating advisory support)
11. Agent 11 — Model Risk Management (deploy last; validates scoring models of Agents 02, 03, 04, 07, 08 once they have production performance baselines)
```

Each step delivers standalone value. The suite multiplier grows with each agent added.
Agent 11 is the governance capstone — it protects the defensibility of every scoring model
deployed in steps 3, 4, 6, 8, and 9.
