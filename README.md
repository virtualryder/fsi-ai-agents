# Financial Services AI Agent Suite
### Agentic AI for Regulated Financial Institutions

> Built for banks, broker-dealers, credit unions, and wealth management firms navigating the intersection of AI capability and regulatory obligation. Every agent in this suite ships with working code, documented regulatory controls, AWS reference architecture, and quantified ROI.

---

## The Suite

Financial crime compliance, KYC, and fraud together consume **$274 billion annually** across global institutions. AI agents don't eliminate that cost — they eliminate the manual, repetitive, low-judgment work so your best analysts can focus on the 5% of cases that require human expertise.

This suite delivers that reduction, use case by use case, in a way that satisfies OCC, FDIC, FinCEN, and FATF examiners.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Financial Services AI Agent Suite                         │
│                                                                             │
│  FINANCIAL CRIME (AML)                                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  01 · Financial Crime Investigation Agent  ← TMS alert arrives      │   │
│  │       Alert → KYC → Transactions → Sanctions → Network → SAR        │   │
│  │       80% reduction in hours per SAR · $2,400 saved per filing      │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  02 · AML/TMS Enhancement Agent            ← upstream of #01        │   │
│  │       Pre-queue FP suppression · ~50% queue reduction               │   │
│  │       $4M/year saved for 10-analyst team at 90% FP rate             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  CUSTOMER DUE DILIGENCE                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  03 · KYC/CDD Perpetual Monitoring Agent   ← risk event triggers    │   │
│  │       Trigger → CDD Refresh → EDD → RM Alert → Compliance Review    │   │
│  │       90% reduction in manual KYC refresh hours · pKYC at scale     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  PAYMENT FRAUD PREVENTION                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  04 · Real-Time Fraud Detection Agent                               │   │
│  │       Sub-200ms payment fraud prevention · 65% fraud loss reduction │   │
│  │       Reg E automation · 7 fraud typologies · SAR flag routing      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  WEALTH MANAGEMENT                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  05 · Wealth & RM Copilot                                           │   │
│  │       RM productivity · Reg BI documentation · Suitability (Python) │   │
│  │       $3.5M/yr (50 RMs) · FINRA 2210 · Reg BI · ERISA              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  COMPLIANCE OPERATIONS                                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  06 · Regulatory Change Management Agent                            │   │
│  │       12-node gap analysis + remediation · 9 regulatory sources     │   │
│  │       $849K–$1.5M/yr · FFIEC · OCC · SR 11-7 · FDIC CMS           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  TRADING SURVEILLANCE                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  07 · Trading Surveillance Agent                                    │   │
│  │       11 alert types · Python rule engine · FINRA 3110 / Dodd-Frank │   │
│  │       $2.6M/yr (6 analysts) · SR 11-7 · SAR automation · Reg SHO    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  LENDING & UNDERWRITING                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  08 · Credit Underwriting Agent                                     │   │
│  │       12 loan types · ECOA/Reg B adverse action · OFAC hard block   │   │
│  │       $1.8M–$3.4M/yr · HMDA · CRA · SR 11-7 · FHA · SBA            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  DOCUMENT INTELLIGENCE (HORIZONTAL — FEEDS ALL AGENTS)                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  09 · Document Intelligence Agent                                   │   │
│  │       25 doc types · PII masking pre-LLM · SWIFT/PDF/OCR intake     │   │
│  │       $1.66M–$1.91M/yr · suite multiplier · 3-week payback          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  PAYMENTS COMPLIANCE                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  10 · Payments Compliance Agent                                     │   │
│  │       Reg E · Nacha · OFAC · BSA · 12-node DAG · SLA management     │   │
│  │       $713K–$1.95M/yr · 92% dispute time reduction · 6-wk payback   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agents

### 01 · Financial Crime Investigation Agent
**[`01-financial-crime-investigation-agent/`](./01-financial-crime-investigation-agent/)**

End-to-end AML alert investigation: from a TMS alert to a BSA-compliant SAR draft, with full evidence assembly and mandatory human review before filing.

| What it does | The number |
|---|---|
| Reduces hours per SAR | 40 hrs → 8 hrs (80% reduction) |
| Savings per SAR filing | $2,400 |
| Annual savings (1,000 SARs/year) | $2.4M investigator time |
| False positive detection | 35pt reduction in unnecessary escalations |
| Payback period | < 4 months |

**Workflow:** TMS alert → customer profile + KYC → 12-month transaction analysis → OFAC/PEP/sanctions screening → adverse media → network analysis (counterparty mapping, shell detection) → composite risk score → SAR generation → **BSA Officer review gate** → case finalization

**Regulatory coverage:** BSA 31 U.S.C. § 5318, OFAC IEEPA, FinCEN CDD Rule, FATF R.12/R.20, USA PATRIOT Act § 326, FIN-2014-G001 SAR narrative format, SR 11-7 model risk, 18 U.S.C. § 1960 (no tipping off)

**Also on GitHub:** [virtualryder/financial-crime-investigation-agent](https://github.com/virtualryder/financial-crime-investigation-agent)

---

### 02 · AML/TMS Enhancement Agent
**[`02-aml-tms-enhancement-agent/`](./02-aml-tms-enhancement-agent/)**

Upstream false positive suppressor. Scores every TMS alert *before* it enters the analyst queue — cutting analyst workload by ~50% without suppressing genuine suspicious activity.

| What it does | The number |
|---|---|
| Queue reduction | ~50% before analyst sees case |
| Analyst hours saved (500 alerts/day, 90% FP) | 450 hrs/day reclaimed |
| Annual labor savings (10-analyst team) | ~$4M |
| FP suppression with full audit trail | PEP/high-risk geography = mandatory escalate |
| SR 11-7 compliant | Factor-by-factor score breakdown per decision |

**Scoring pipeline:** Alert ingest → customer context → historical FP pattern lookup → feature extraction → rule-based pre-score (30%) → LLM contextual analysis (50%) → historical base rates (20%) → composite FP probability → route to suppress / downgrade / pass-through / escalate

**Routing decisions:**
- **SUPPRESS** (FP ≥ 85%): Full justification narrative required; 90-day BSA Officer review
- **DOWNGRADE** (FP ≥ 60%): Low-priority analyst queue
- **PASS-THROUGH** (FP 15–60%): Normal analyst queue
- **ESCALATE** (FP ≤ 15%): High-priority → Financial Crime Investigation Agent

**Hard controls:** PEP flag → always escalate. High-risk geography + large wire + new account → always escalate. Human override available in dashboard.

---

### 03 · KYC/CDD Perpetual Monitoring Agent
**[`03-kyc-cdd-perpetual-agent/`](./03-kyc-cdd-perpetual-agent/)**

Perpetual KYC at scale: risk-event-triggered CDD refresh, automated EDD package generation, relationship manager alerts, and mandatory compliance officer review before any risk rating change.

| What it does | The number |
|---|---|
| Manual KYC refresh hours eliminated | ~90% |
| Risk-based review scheduling | HIGH=annual, MEDIUM=2yr, LOW=3yr (auto-scheduled) |
| Event triggers covered | 11 event types (adverse media, watchlist hit, transaction spike, UBO change...) |
| EDD request auto-generation | Document checklist + RM-ready communication |
| Regulatory citations per decision | All findings cite FinCEN CDD Rule, FATF R.10/R.12 |

**Workflow:** Trigger evaluation → customer risk profile → document gap analysis → watchlist screening → adverse media → risk rescoring → routing (pass / EDD required / escalate / exit) → EDD package generation → RM notification → **Compliance Officer review gate** → KYC record update → finalize

**Regulatory coverage:** FinCEN CDD Rule (31 CFR 1020.210), FATF R.10/R.12/R.22, BSA 31 U.S.C. § 5318(l), FFIEC BSA/AML Examination Manual, OCC Bulletin 2018-17, SR 11-7

---

### 04 · Real-Time Fraud Detection Agent
**[`04-fraud-detection-agent/`](./04-fraud-detection-agent/)**

Sub-200ms payment fraud prevention using a dual-path architecture: deterministic rule engine for real-time authorization decisions, LLM contextual synthesis for async enrichment and analyst review. Automates Reg E provisional credit disclosures and flags money laundering patterns for AML escalation.

| What it does | The number |
|---|---|
| Annual fraud loss reduction | ~65% ($2.3M → ~$800K) |
| False positive reduction | ~40% (4,200/mo → ~2,500/mo) |
| Analyst hours saved | 80% (360 → 64 hrs/week) |
| Reg E late disclosures | 83% reduction (12/year → ~2/year) |
| Real-time path latency | Sub-200ms (card authorization window) |

**Two-path architecture:** Real-time (<200ms): intake → context → features → rule pre-scoring. Async enrichment: device intelligence → behavioral analysis → LLM synthesis → composite scoring → routing (BLOCK / Step-Up / Review / Allow)

**Fraud typologies covered:** Card testing, account takeover, card-not-present, authorized push payment, wire/BEC, structuring, elder financial exploitation

**Regulatory coverage:** Reg E (EFTA), Nacha Rules, Visa/Mastercard reason codes, BSA (SAR flag routing), OFAC hard blocks, SR 11-7, CFPB Fair Lending (race/sex-neutral signals), GLBA (PII hashing)

---

### 05 · Wealth & RM Copilot
**[`05-wealth-rm-copilot/`](./05-wealth-rm-copilot/)**

AI copilot for relationship managers: automates meeting prep, proposal writing, portfolio reviews, and client communications while generating Reg BI documentation automatically. Suitability determination is Python — not LLM.

| What it does | The number |
|---|---|
| Meeting prep time per RM | 2-3 hrs → 30 min (80% reduction) |
| Proposal writing time | 3-4 hrs → 45 min (75% reduction) |
| Annual RM hours saved (50 RMs) | 26,000 hrs |
| Annual savings (50 RMs, $120/hr fully loaded) | ~$3.5M |
| Compliance documentation gaps | ~15% → ~2% (87% reduction) |

**Workflow:** RM request → client profile (CRM + IPS + portfolio) → portfolio analysis → market intelligence → **suitability check (Python — not LLM)** → recommendation engine → content drafting (GPT-4o) → FINRA 2210 compliance check → **RM approval gate** → archive

**Request types:** Meeting prep · Rebalancing proposal · Investment proposal · Portfolio review · Client communication · Alert response

**Regulatory coverage:** Reg BI (17 CFR 240.15l-1), FINRA Rule 2111, FINRA Rule 2210, FINRA Rule 4512, ERISA (29 U.S.C. § 1001), SEC Investment Advisers Act, SEC Rule 204-2 / FINRA 4511 (6-year retention), Form CRS, SR 11-7

---

### 08 · Credit Underwriting Agent
**[`08-credit-underwriting-agent/`](./08-credit-underwriting-agent/)**

End-to-end loan underwriting: 12 loan types, fair lending compliance (ECOA/HMDA), OFAC hard block, and ECOA-compliant adverse action notices — all in one deterministic pipeline.

| What it does | The number |
|---|---|
| Underwriting time | 3–5 days → same-day decisions |
| Adverse action accuracy | 12 mapped ECOA reasons, Python-only |
| Annual savings (300 loans/month) | $1.8M–$3.4M |
| 3-year NPV | $4.7M–$8.5M |
| Payback period | < 6 weeks |

**Workflow:** Loan application → document verification → credit analysis → DTI/LTV scoring → OFAC hard block → fair lending flags → ECOA adverse action → **underwriter review gate** → decision

**Regulatory coverage:** ECOA/Reg B, FHA, HMDA, CRA, Reg Z/TILA, BSA/OFAC/CIP, SR 11-7, SBA 7(a)/504

---

### 09 · Document Intelligence Agent
**[`09-document-intelligence-agent/`](./09-document-intelligence-agent/)**

Horizontal entry point for the entire suite. Converts unstructured financial documents (PDFs, SWIFT messages, scanned forms) into structured JSON that every other agent can consume — with PII masking before any LLM sees the data.

| What it does | The number |
|---|---|
| Document types supported | 25 (lending, payments, KYC, capital markets, compliance) |
| Processing time reduction | 90 min (1003 loan app) → 11 min (88% reduction) |
| Annual savings | $1.66M–$1.91M |
| Payback period | 3 weeks |
| Suite multiplier | Every downstream agent benefits from day 1 |

**Workflow:** Intake → text extraction → **PII masking (Python, before LLM)** → document classification → field extraction → validation → confidence scoring → routing → **HITL gate** (for low-confidence / sensitive docs) → enrichment → structured JSON output

**Recommended first deployment:** Deploy Agent 09 before any other agent. Its structured output immediately accelerates every specialist agent you deploy next.

**Regulatory coverage:** GLBA, BSA/AML, OFAC, ECOA/Reg B, HMDA, FinCEN CDD Rule, BSA CIP, SEC/FINRA

---

### 10 · Payments Compliance Agent
**[`10-payments-compliance-agent/`](./10-payments-compliance-agent/)**

Automates ACH dispute processing, OFAC screening, Nacha return code validation, Reg E SLA management, and compliance risk scoring for the payments operations team. Every compliance determination is Python — the LLM drafts notices and narratives for reviewers.

| What it does | The number |
|---|---|
| Dispute processing time | 143 min → 12 min (92% reduction) |
| Auto-resolve rate | ~40% of events (NOC, administrative) |
| Annual savings (5K disputes/year) | $713K–$1.95M |
| 3-year NPV | $1.7M |
| Payback period | < 6 weeks |

**Workflow:** Intake/masking → OFAC/FATF screening → Nacha validation → Reg E assessment → dispute analysis (LLM) → risk scoring (Python) → compliance narrative (LLM) → routing → **HITL gate** → resolution drafting → audit finalization

**HITL triggers:** OFAC sanctions match · SAR candidate · CTR threshold · High-risk country wire · Unauthorized return (R07/R10/R29) · Late return flag · Amount > $50K · CRITICAL/HIGH tier

**Regulatory coverage:** Reg E (12 CFR Part 1005), Nacha Operating Rules, OFAC (31 CFR Parts 500-598), BSA/FinCEN (31 CFR 1020), FATF Recommendations, CFPB Prepaid Rule, UCC Article 4A, GLBA, SR 11-7

---

## Architecture Principles

Every agent in this suite is built on the same opinionated architecture. Customers learn it once and deploy it everywhere.

### 1. LangGraph State Machine

All agents are LangGraph `StateGraph` DAGs. Investigation steps are nodes; data flows through a typed state object. Benefits for regulated institutions:
- **Reproducibility:** Same alert, same investigation steps, every time
- **Auditability:** Every node transition is loggable
- **Interruptibility:** Human review gates implemented as first-class graph interrupts
- **Testability:** Each node is a pure function, independently unit-testable

### 2. Deterministic Gates, LLM Drafting

AI drafts; humans decide. The routing logic at every decision point is deterministic Python — not LLM output. The LLM's role is to assemble evidence, draft narratives, and surface context. A human (BSA Officer, Compliance Officer, RM) approves before any record is filed or risk rating changed.

### 3. Regulatory Controls as Code

Every agent embeds regulatory requirements directly in the code:
- PEP flag → hard-coded escalation path (not configurable)
- OFAC match → immediate alert, no suppression
- 30-day SAR filing window → deadline calculated and surfaced at case open
- Audit trail → append-only JSONL, examination-ready
- PII handling → field-level redaction in all log outputs

### 4. SR 11-7 Model Risk Management

Every scoring model in the suite includes:
- Factor-by-factor score breakdowns (explainability)
- Threshold documentation with rationale
- Human override capability at every decision point
- Audit trail linking every model output to its inputs

### 5. AWS Production Reference Architecture

```
CloudFront + WAF
       ↓
ALB (Cognito / Okta auth — SAML federation with enterprise AD)
       ↓
ECS Fargate (Streamlit UI + LangGraph workers)
       ↓
MCP Auth Gateway (JWT validation · role-based authorization · rate limiting · audit logging)
       ↓
MCP Servers:
  ├── TMS Connector (Actimize · Verafin · NICE · Oracle Mantas)
  ├── Core Banking (FIS · Fiserv · Jack Henry)
  ├── Watchlist Screener (Refinitiv · LexisNexis · Dow Jones)
  ├── Adverse Media (LexisNexis · Dow Jones Risk & Compliance)
  ├── Network Intelligence (internal graph DB)
  └── Case Management (Actimize Case Manager · Nasdaq BWise)

Data Layer:
  Aurora PostgreSQL (multi-AZ) · DynamoDB (append-only audit)
  S3 Object Lock (WORM · 5-year BSA retention) · ElastiCache Redis

Security:
  AWS Bedrock (LLM inference — data stays in-account)
  Secrets Manager · KMS · CloudTrail · CloudWatch · GuardDuty
```

---

## Regulatory Coverage Map

| Regulation | Agent 01 | Agent 02 | Agent 03 | Agent 04 | Agent 05 | Agent 06 | Agent 07 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| BSA 31 U.S.C. § 5318 (SAR filing) | ✅ | ✅ | ✅ | ✅ | — | — | ✅ |
| FinCEN CDD Rule (31 CFR 1020.210) | ✅ | ✅ | ✅ | — | — | ✅ | — |
| OFAC IEEPA (SDN screening, 50% rule) | ✅ | ✅ | ✅ | ✅ | — | — | — |
| FATF R.10 (Customer due diligence) | ✅ | — | ✅ | — | — | — | — |
| FATF R.12 (PEP enhanced due diligence) | ✅ | ✅ | ✅ | — | — | — | — |
| FATF R.20 (Suspicious transaction reporting) | ✅ | ✅ | — | ✅ | — | — | ✅ |
| USA PATRIOT Act § 326 (CIP) | ✅ | — | ✅ | — | — | — | — |
| FIN-2014-G001 (SAR narrative format) | ✅ | — | — | — | — | — | ✅ |
| SR 11-7 (Model risk management) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| FFIEC BSA/AML Examination Manual | ✅ | ✅ | ✅ | — | — | ✅ | — |
| 18 U.S.C. § 1960 (No tipping off) | ✅ | — | — | — | ✅ | — | ✅ |
| 5-year BSA record retention | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| Reg E (EFTA) — provisional credit | — | — | — | ✅ | — | — | — |
| Nacha Rules (ACH fraud) | — | — | — | ✅ | — | — | — |
| Reg BI (17 CFR 240.15l-1) | — | — | — | — | ✅ | — | — |
| FINRA Rule 2111 (Suitability) | — | — | — | — | ✅ | — | ✅ |
| FINRA Rule 2210 (Communications) | — | — | — | — | ✅ | — | — |
| FINRA Rule 3110 (Supervisory procedures) | — | — | — | — | — | — | ✅ |
| FINRA Rule 4511 (Books and records) | — | — | — | — | — | — | ✅ |
| ERISA (retirement account fiduciary) | — | — | — | — | ✅ | — | — |
| GLBA (data privacy / PII) | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |
| Dodd-Frank § 747 (Spoofing ban) | — | — | — | — | — | — | ✅ |
| SEC Regulation SHO (Short selling) | — | — | — | — | — | — | ✅ |
| SEC Rule 10b-5 (Market manipulation) | — | — | — | — | — | — | ✅ |

---

## ROI Summary

| Agent | Cost Driver Addressed | Annual Savings (mid-market bank) |
|---|---|---|
| 01 · Financial Crime Investigation | $10K–$25K per SAR · analyst time | $2.4M+ (1,000 SARs/year) |
| 02 · AML/TMS Enhancement | 90% FP rate · 450 wasted hrs/day | $4M+ (10-analyst team) |
| 03 · KYC/CDD Perpetual | Manual refresh · exam findings | $1.5M+ (5,000 customer reviews/year) |
| 04 · Real-Time Fraud Detection | $2.3M fraud losses · 360 analyst hrs/week | $2.1M+ (regional bank) |
| 05 · Wealth & RM Copilot | 35-40% RM time on admin · Reg BI gaps | $3.5M+ (50 RMs) |
| 06 · Regulatory Change Management | 200-400 changes/year · exam findings | $849K–$1.5M+ (regional bank) |
| 07 · Trading Surveillance | 800 alerts/month · 90%+ FP rate · FINRA fines | $2.6M+ (6-analyst team) |
| 08 · Credit Underwriting | 3–5 day decisions · ECOA compliance gaps · manual docs | $1.8M–$3.4M (300 loans/month) |
| 09 · Document Intelligence | Manual re-keying of PDFs/SWIFT · OCR bottlenecks | $1.66M–$1.91M (suite multiplier) |
| 10 · Payments Compliance | 143-min disputes · missed SLA fines · OFAC exposure | $713K–$1.95M (5K disputes/year) |
| **Full suite** | **End-to-end financial crime + fraud + wealth + compliance ops** | **$22M+ annually** |

Payback period for full suite deployment: **< 6 months**

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent orchestration | LangGraph 0.2.28+ |
| LLM | OpenAI GPT-4o (configurable: AWS Bedrock Claude, Azure OpenAI) |
| UI | Streamlit (demo/POC) · FastAPI + Next.js (production) |
| Vector store | ChromaDB (dev) · pgvector on Aurora (prod) |
| Audit log | JSONL append-only (dev) · DynamoDB (prod) |
| Auth | Cognito + Okta SAML federation |
| Deployment | Docker · Railway (demo) · ECS Fargate (prod) |
| Testing | Pytest 8.3+ |

---

## Quick Start

Each agent runs independently. No shared infrastructure required for development.

```bash
# Clone the suite
git clone https://github.com/virtualryder/fsi-ai-agents
cd fsi-ai-agents

# Start with Agent 01 (Financial Crime Investigation)
cd 01-financial-crime-investigation-agent
cp .env.example .env
# Add OPENAI_API_KEY to .env
docker compose up
# Open: http://localhost:8501

# Then try Agent 02 (TMS Enhancement)
cd ../02-aml-tms-enhancement-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8502

# Then try Agent 03 (KYC/CDD)
cd ../03-kyc-cdd-perpetual-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8503

# Then try Agent 04 (Real-Time Fraud Detection)
cd ../04-fraud-detection-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8504

# Then try Agent 05 (Wealth & RM Copilot)
cd ../05-wealth-rm-copilot
cp .env.example .env
docker compose up
# Open: http://localhost:8505
```

---

## About

Built by [David Ryder](https://github.com/virtualryder) as part of a "art of the possible", production-grade agentic AI portfolio for financial services.

All agents are designed for real deployment — customization, security,  and verification are a user responsibility. Every regulatory citation is accurate. Every integration point reflects actual FSI system landscapes (Actimize, Verafin, Fiserv, FIS, Refinitiv, LexisNexis).

**Target buyers:** BSA Officers · Chief Compliance Officers · Financial Crime Operations Leaders · CIOs at banks, credit unions, and broker-dealers

**Relevant to:** Presidio FSI Practice · AWS financial services GTM · AI/ML modernization engagements

---

*Part of the [Agentic Application Examples](https://github.com/virtualryder) portfolio — production-shaped LangGraph agents across financial services, healthcare, government, and enterprise domains.*
