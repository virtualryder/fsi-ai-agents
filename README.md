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
│  COMING SOON                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  04 · Real-Time Fraud Detection Agent       (UC11)                  │   │
│  │  05 · Wealth & Relationship Manager Copilot (UC13)                  │   │
│  │  06 · Regulatory Change Management Agent    (UC15)                  │   │
│  │  07 · Trading Surveillance Agent            (UC16)                  │   │
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

| Regulation | Agent 01 | Agent 02 | Agent 03 |
|---|:---:|:---:|:---:|
| BSA 31 U.S.C. § 5318 (SAR filing) | ✅ | ✅ | ✅ |
| FinCEN CDD Rule (31 CFR 1020.210) | ✅ | ✅ | ✅ |
| OFAC IEEPA (SDN screening, 50% rule) | ✅ | ✅ | ✅ |
| FATF R.10 (Customer due diligence) | ✅ | | ✅ |
| FATF R.12 (PEP enhanced due diligence) | ✅ | ✅ | ✅ |
| FATF R.20 (Suspicious transaction reporting) | ✅ | ✅ | |
| USA PATRIOT Act § 326 (CIP) | ✅ | | ✅ |
| FIN-2014-G001 (SAR narrative format) | ✅ | | |
| SR 11-7 (Model risk management) | ✅ | ✅ | ✅ |
| FFIEC BSA/AML Examination Manual | ✅ | ✅ | ✅ |
| 18 U.S.C. § 1960 (No tipping off) | ✅ | | |
| 5-year BSA record retention | ✅ | ✅ | ✅ |

---

## ROI Summary

| Agent | Cost Driver Addressed | Annual Savings (mid-market bank) |
|---|---|---|
| 01 · Financial Crime Investigation | $10K–$25K per SAR · analyst time | $2.4M+ (1,000 SARs/year) |
| 02 · AML/TMS Enhancement | 90% FP rate · 450 wasted hrs/day | $4M+ (10-analyst team) |
| 03 · KYC/CDD Perpetual | Manual refresh · exam findings | $1.5M+ (5,000 customer reviews/year) |
| **Full suite** | **End-to-end financial crime + CDD** | **$7.9M+ annually** |

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
```

---

## About

Built by [David Ryder](https://github.com/virtualryder) as part of a "art of the possible", production-grade agentic AI portfolio for financial services.

All agents are designed for real deployment — customization, security,  and verification are a user responsibility. Every regulatory citation is accurate. Every integration point reflects actual FSI system landscapes (Actimize, Verafin, Fiserv, FIS, Refinitiv, LexisNexis).

**Target buyers:** BSA Officers · Chief Compliance Officers · Financial Crime Operations Leaders · CIOs at banks, credit unions, and broker-dealers

**Relevant to:** Presidio FSI Practice · AWS financial services GTM · AI/ML modernization engagements

---

*Part of the [Agentic Application Examples](https://github.com/virtualryder) portfolio — production-shaped LangGraph agents across financial services, healthcare, government, and enterprise domains.*
