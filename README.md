# Financial Services AI Agent Suite
### Agentic AI for Regulated Financial Institutions

> Built for banks, broker-dealers, credit unions, and wealth management firms navigating the intersection of AI capability and regulatory obligation. Every agent in this suite ships with working code, documented regulatory controls, AWS reference architecture, and illustrative ROI modeling.

> **The agents are not the product. The platform that makes them governable is the product.**
> Read [ENTERPRISE-PLATFORM.md](./ENTERPRISE-PLATFORM.md) for the full platform story: API modernization, MCP authorization gateway, federated identity, agent catalog governance, and A2A audit standards — and how each layer maps to SR 11-7, FFIEC, NIST AI RMF, and GLBA.

---

## The Suite

Financial crime compliance, KYC, and fraud together consume **$274 billion annually** across global institutions. AI agents don't eliminate that cost — they eliminate the manual, repetitive, low-judgment work so your best analysts can focus on the 5% of cases that require human expertise.

This repo is an art-of-the-possible suite showing how financial institutions can move from manual, document-heavy, queue-based operations to controlled agentic workflows. The key design pattern is that AI assists with evidence gathering, summarization, drafting, and context synthesis — while regulated decisions remain deterministic, auditable, and human-approved. Each agent is designed to support OCC, FDIC, FinCEN, and FATF examination readiness, not replace the compliance program itself.

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
│                                                                             │
│  MODEL GOVERNANCE                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  11 · Model Risk Management Agent                                   │   │
│  │       SR 11-7 §§ 4-11 · 5 models validated · Gini/KS/PSI/FNR       │   │
│  │       $735K–$1.28M/yr · ≤30-day degradation detection · 14-wk PBK  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  CONSUMER COLLECTIONS                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  12 · Collections & Recovery Agent                                  │   │
│  │       FDCPA · Reg F 7-in-7 · SCRA 6% · Bankruptcy § 362            │   │
│  │       $890K–$3.8M/yr · 9 HITL conditions · frozenset enforced       │   │
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

### 06 · Regulatory Change Management Agent
**[`06-regulatory-change-agent/`](./06-regulatory-change-agent/)**

Automated regulatory change monitoring, gap analysis, and remediation planning across 9 regulatory authorities (FinCEN, OCC, Federal Reserve, FDIC, CFPB, SEC, FINRA, NCUA, FATF). The 5-factor Python impact scoring model and gap analysis workflow replace 8–40 hours of manual compliance analyst work per regulatory change.

| What it does | The number |
|---|---|
| Manual hours per HIGH-impact change | 26 hrs → 2.5 hrs (90% reduction) |
| Regulatory sources monitored | 9 authorities, continuous |
| Annual savings (4-analyst regional bank) | $849K–$1.5M |
| 3-year NPV | $2.0M |
| Payback period | < 8 weeks |

**Workflow:** Change intake → source validation → scope determination → policy mapping → gap analysis (LLM) → impact scoring (Python: 5-factor, SR 11-7) → routing → **CCO review gate (HITL)** → remediation planning → stakeholder notification → tracking update → finalize

**Impact tiers:** CRITICAL ≥0.85 · HIGH 0.65–0.84 · MEDIUM 0.40–0.64 · LOW <0.40 — all Python, no LLM in routing

**Hard rules:** Enforcement actions → minimum HIGH + mandatory HITL. Already-effective Tier 1 regulations → CRITICAL. Compliance window too short for MEDIUM complexity → escalates to HIGH.

**Regulatory coverage:** FFIEC BSA/AML Examination Manual, OCC 12 CFR Part 30 App. D, FDIC FIL-44-2008, SR 11-7, all 9 monitored authority frameworks

---

### 07 · Trading Surveillance Agent
**[`07-trading-surveillance-agent/`](./07-trading-surveillance-agent/)**

Automated trading surveillance across 11 market abuse alert types: layering/spoofing, front running, wash trading, insider trading, marking the close, excessive trading, best execution failures, short selling violations, cross-market manipulation, information barrier breaches, and unusual activity. Python pattern detection scores every alert; the LLM assembles market context and drafts the disposition memo.

| What it does | The number |
|---|---|
| Hours per HIGH alert | 6 hrs → 1.2 hrs (80% reduction) |
| Alert types covered | 11 (FINRA 3110 / Dodd-Frank / SEC Rule 10b-5) |
| Annual savings (6-analyst BD) | $2.6M |
| 3-year NPV | $7.0M |
| SAR auto-generation | $5K BSA threshold — Python determination |

**Workflow:** Alert intake → data enrichment → pattern detection (Python, 11 rules) → market context (LLM) → risk scoring (Python, 5 factors) → routing → **compliance officer review gate (HITL)** → investigation narrative (LLM) → disposition → case tracking → finalize

**Hard overrides:** INSIDER_TRADING, INFORMATION_BARRIER_BREACH, CROSS_MARKET_MANIPULATION → always CRITICAL + mandatory HITL. Python `frozenset` — cannot be configured away.

**SAR determination:** Python rule (`amount ≥ $5,000 AND suspicious_activity`), not LLM. Tipping-off prohibition (31 U.S.C. § 5318(g)(2)) enforced in system prompt — no LLM output can disclose SAR to subject.

**Regulatory coverage:** FINRA Rule 3110/4511/5210/5270/5310, SEC Rule 10b-5, Dodd-Frank § 747, Reg SHO Rules 203-204, BSA 31 CFR § 1023.320, SR 11-7

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

### 11 · Model Risk Management Agent
**[`11-model-risk-agent/`](./11-model-risk-agent/)**

The independent model validation function for the FSI AI Suite. Validates the five scoring models across Agents 02, 03, 04, 07, and 08 in full compliance with SR 11-7 (Federal Reserve / OCC Guidance on Model Risk Management). Every risk determination — tier assignment, degradation flags, PSI classification, HITL routing, validation outcome — is produced by deterministic Python. The LLM produces only written narratives. The Model Risk Officer always signs off before any HIGH-tier validation event produces a final outcome.

| What it does | The number |
|---|---|
| Manual validation cost (HIGH-risk model) | $20,000–$56,900 per event |
| Agent 11 cost per event | $3,500–$7,000 |
| Annual labor savings (5 models, full schedule) | $735K–$1.28M |
| Undetected Gini degradation exposure (90 days) | $345K–$11.7M in incremental losses |
| Detection window with Agent 11 | ≤ 30 days (monthly automated monitoring) |
| Payback period | 14–22 weeks |

**Validation pipeline (12 nodes):** Model inventory lookup → data sample pull → conceptual soundness review (LLM narrative) → outcomes analysis (Python: Gini, KS, AUC-ROC, FPR, FNR deltas) → population stability analysis (Python: PSI formula) → benchmark comparison → sensitivity analysis → risk tier determination (Python) → validation narrative (LLM) → routing decision (Python, fail-safe) → **HITL gate** (MRO/CRO decision) → audit finalization

**HITL triggers (9 conditions, Python frozenset — immutable at runtime):** HIGH-tier initial/change/annual validation · Performance degradation · PSI CRITICAL (>0.25) · Material finding · Challenger underperforms · Hard rule violation → CRO escalation · Fair lending flag (AGT08 credit model)

**Models validated:** AGT02-FP-SCORE-v1 (AML false positive composite) · AGT03-KYC-RISK-v1 (customer risk score) · AGT04-FRAUD-SCORE-v1 (fraud composite) · AGT07-SURV-RISK-v1 (trading surveillance risk) · AGT08-CREDIT-SCORE-v1 (credit underwriting composite)

**Regulatory coverage:** SR 11-7 §§ 4-11 (conceptual soundness, outcomes analysis, ongoing monitoring, human oversight) · ECOA/Regulation B (fair lending validation for AGT08) · BSA/AML model validation implications · OCC model risk retention guidance · 10-year S3 Object Lock GOVERNANCE retention

---

### 12 · Collections & Recovery Agent
**[`12-collections-recovery-agent/`](./12-collections-recovery-agent/)**

FDCPA/Reg F/SCRA-compliant debt collections automation. Enforces contact time restrictions (pytz UTC conversion), Regulation F 7-in-7 call limits, SCRA 6% interest rate caps, bankruptcy automatic stay detection, 50-state SOL computation, and Python-computed payment plan optimization — while routing all high-risk regulatory conditions to mandatory human review through an immutable frozenset that the LLM cannot modify.

| What it does | The number |
|---|---|
| Annual FDCPA violation exposure avoided | $340K–$2.4M per year |
| Collector compliance research eliminated | 25–49 min per account |
| Supervisor HITL review time reduction | 65–78% per case |
| Recovery rate improvement (payment plans) | 25–35% lower plan default rate |
| Agent 12 infrastructure cost | $6,200–$9,800/year |
| Payback period | 8–14 weeks |

**Collections pipeline (12 nodes):** PII masking → FDCPA contact check (pytz timezone) → SCRA/bankruptcy detection → hardship assessment (LLM narrative) → debt validation (FCRA, SOL, medical debt) → payment plan optimization (Python: balance ÷ term) + settlement tiers → collections strategy (LLM narrative) → HITL conditions (Python frozenset) → routing decision (fail-safe `is False`) → **HITL gate** (supervisor/compliance decision) → communication drafting (LLM + Python-injected disclosures) → audit finalization (7-year FCRA retention)

**HITL triggers (9 conditions, Python frozenset — immutable at runtime):** SCRA detected (6% rate cap) · Bankruptcy stay (ALL collection stops) · Dispute received (30-day hold) · Cease & desist (FDCPA § 805(c)) · Deceased account · Settlement high-value (>$10K or >40% discount) · Litigation high risk · Regulatory complaint · Minor account

**Python vs. LLM boundary:** Contact time check · Reg F 7-in-7 · SCRA rate cap · SOL matrix (all 50 states + DC) · Collectability score · Payment plan math · Settlement tier authorization · HITL condition detection · HITL routing — ALL Python. LLM produces: hardship narrative, strategy summary, letter body (with Python-injected mini-Miranda, validation notice, SCRA note, 1099-C notice).

**Regulatory coverage:** FDCPA 15 U.S.C. § 1692 · CFPB Regulation F 12 CFR Part 1006 · SCRA 50 U.S.C. § 3937 · Bankruptcy Code 11 U.S.C. § 362 · FCRA 15 U.S.C. § 1681 · UDAAP Dodd-Frank § 1031 · TCPA 47 U.S.C. § 227 · IRS § 6050P (1099-C) · 7-year S3 Object Lock GOVERNANCE retention

---

## Repository Contents

The 12 agents are the core of this suite, but the repository ships with a full platform layer designed to take those agents from demo to governed production. Here's what's here, who it's for, and why it matters.

### For Engineers and Architects

**[`platform_core/`](./platform_core/)** — Shared Python library used by all 11 LLM-bearing agents. Instead of each agent managing its own LLM connection, PII masking, and auth logic, `platform_core` provides one tested, consistent implementation:
- `llm_factory.py` — Bedrock/Guardrails LLM factory with documented Anthropic API fallback for local dev
- `auth.py` — fail-closed JWT verification with HITL role enforcement; verified reviewer identity bound into every audit record
- `pii.py` — consolidated PII masking (SSN, PAN, account/routing) applied at state-write boundaries before any LLM sees the data
- `secrets.py` — AWS Secrets Manager integration; no credentials in environment variables
- `tracing.py` — OpenTelemetry instrumentation scaffolding for A2A trace propagation
- `mcp_gateway/` — deny-by-default MCP authorization gateway: authenticates callers, authorizes via least-privilege-as-intersection (agent grants ∩ user entitlements), gates high-risk writes behind human approval, mints short-lived scoped tokens (5-min TTL), and writes every attempt to an append-only PII-masked audit log. Fails closed. Maps to Bedrock AgentCore Gateway / Amazon Verified Permissions (Cedar) / STS for production. 81 tests green across the full platform suite.

**[`infra/terraform/`](./infra/terraform/)** — AWS reference infrastructure as code, organized as composable modules:
- `modules/network/` — VPC with no internet route in agent subnets; egress via VPC endpoints only
- `modules/security/` — IAM task roles with least-privilege scoping (audit table: PutItem-only; Bedrock invoke: scoped to two model IDs)
- `modules/data/` — Aurora PostgreSQL (LangGraph checkpoints), DynamoDB (append-only audit), S3 Object Lock COMPLIANCE (WORM retention)
- `modules/agent_service/` — ECS Fargate task definition with Bedrock VPC endpoint, Cognito pre-auth at ALB
- `envs/dev/` — wired dev environment referencing all four modules

The Terraform enforces at the IAM level the controls the application code promises — the audit trail cannot be overwritten even under a compromised container.

### For Security, AI Risk, and Model Risk Reviewers

**[`governance/`](./governance/)** — The LLM governance suite that runs in CI on every commit, making AI quality and safety claims checkable rather than asserted:
- `grounding.py` — verifies LLM narrative outputs cite evidence actually present in the agent's state; flags unverifiable claims before they reach a human reviewer
- `prompt_registry.py` + `prompt_manifest.json` — every system prompt versioned and hashed; CI fails if a prompt changes without a manifest update (prevents silent prompt drift in SAR narratives or adverse action language)
- `redteam/test_prompt_injection.py` — 5 structural injection tests across the Agent 09 → downstream chain; validates that hostile document content cannot redirect agent routing or bypass HITL gates
- `fairness/test_agent08_disparate_impact.py` — matched-pair blindness tests and four-fifths AIR harness for Agent 08 (Credit Underwriting); designed to run against client HMDA-coded data during pilot
- `evals/` — golden-case eval harness with reference SAR narratives (Agent 01) and adverse action notices (Agent 08); structure, grounding, and reason-accuracy checked on every build

### For Operations and Compliance Teams

**[`runbooks/`](./runbooks/)** — Four executable operational procedures, each referencing mechanisms that actually exist in the codebase rather than describing hypothetical processes:
- [`INCIDENT-RESPONSE.md`](./runbooks/INCIDENT-RESPONSE.md) — AI-specific incident response: hallucinated filing content, injection detection, model outage → manual-queue fallback, regulator notification thresholds
- [`DR-RUNBOOK.md`](./runbooks/DR-RUNBOOK.md) — Disaster recovery: RTO/RPO definitions, Aurora failover, ECS multi-AZ cutover, audit trail reconstruction
- [`HITL-QUEUE-OPERATIONS.md`](./runbooks/HITL-QUEUE-OPERATIONS.md) — Day-to-day operations for BSA Officers, Compliance Officers, and supervisors managing the human review gates across all 12 agents
- [`MODEL-DEGRADATION-RESPONSE.md`](./runbooks/MODEL-DEGRADATION-RESPONSE.md) — What to do when Agent 11 flags PSI drift or performance degradation; escalation path to Model Risk Officer and CRO
- [`README.md`](./runbooks/README.md) — Index with unified operating calendar (daily checks, weekly reviews, monthly validation cycles, quarterly access reviews)

### For BSA Officers, Compliance Teams, Operations, and Auditors

**[`docs/user-guides/`](./docs/user-guides/)** — Five per-persona guides that tell reviewers exactly what to do at each human review gate and, critically, which claims they can verify rather than trust. Start with `REVIEWER-FUNDAMENTALS.md` — everyone reads it first.

- [`REVIEWER-FUNDAMENTALS.md`](./docs/user-guides/REVIEWER-FUNDAMENTALS.md) — The two-layer mental model (Python decides, LLM drafts), what an approval legally constitutes, the "unsure routes up, never through" rule, and the evidence-preserving "stop, don't retry" procedure. Mandatory reading before any role-specific guide.
- [`GUIDE-BSA-AML.md`](./docs/user-guides/GUIDE-BSA-AML.md) — For BSA Officers and AML analysts: reading "component disagreement" flags, the four-pass SAR narrative review, and the operationally important distinction that suppressed ≠ deleted in the exam file.
- [`GUIDE-CREDIT-FAIR-LENDING.md`](./docs/user-guides/GUIDE-CREDIT-FAIR-LENDING.md) — For credit reviewers and fair-lending officers: reason-accuracy per CFPB Circular 2022-03 as the first-order check, the portfolio-level lens, and the 0.80 AIR stop-the-line rule stated as non-negotiable.
- [`GUIDE-OPERATIONS.md`](./docs/user-guides/GUIDE-OPERATIONS.md) — For payments and collections ops teams: OFAC hold semantics ("the system holds when it can't clear, not only when it can match") and the insight that a blocked action is usually the law enforcing itself, not a bug.
- [`GUIDE-AUDITOR.md`](./docs/user-guides/GUIDE-AUDITOR.md) — For internal audit and examiners: the 15-minute decision-reconstruction procedure (pilot success criterion #3, documented so auditors can execute it unassisted), five sampling programs, and a findings taxonomy keyed to the incident classes.

### For Practice Leads, Sales, and TPRM Reviewers

**[`offerings/`](./offerings/)** — SI engagement and sales-enablement documents designed to be used directly in customer conversations:
- [`EXECUTIVE-BRIEFING.pptx`](./offerings/EXECUTIVE-BRIEFING.pptx) — 9-slide deck. Problem stats → "AI drafts, rules decide, humans approve" thesis → 12-agent map → examiner-grade controls → in-account data-residency architecture → honest built-vs-roadmap slide → priced assessment/pilot/scale path → the 3–4-week ask. Every claim traces to something in this repo. Share before an executive briefing.
- [`ASSESSMENT-OFFERING.md`](./offerings/ASSESSMENT-OFFERING.md) — The entry-point engagement: what a structured assessment covers, what it delivers, and how it sets up a pilot.
- [`PILOT-OFFERING.md`](./offerings/PILOT-OFFERING.md) — Pilot scope, workstreams, success criteria, and the transition path to a production-assist engagement.
- [`TPRM-DUE-DILIGENCE-PACKET.md`](./offerings/TPRM-DUE-DILIGENCE-PACKET.md) — Pre-answered vendor risk questionnaire covering data residency, encryption, auth, least privilege, audit retention, subprocessors, AI governance, vulnerability management, and BCP/DR. Includes the full STRIDE threat model and penetration test plan. Attach directly to a client's vendor questionnaire response.
- [`POC-OFFERING.md`](./offerings/POC-OFFERING.md) — 2-week proof-of-concept (one agent, sanitized data, one measured outcome). The low-commitment door-opener for buyers not yet ready to fund an assessment.
- [`MANAGED-SERVICE-OFFERING.md`](./offerings/MANAGED-SERVICE-OFFERING.md) — Presidio operates the deployed agents in the client's account (fully-managed / co-managed / platform-only). Converts a one-time build into recurring revenue and opens smaller institutions.
- [`COST-ROI-MODEL.md`](./offerings/COST-ROI-MODEL.md) — Transparent, rebuild-on-client-data ROI model with an $8B-bank worked example. The structure to turn illustrative numbers into the client's own.
- [`COMPETITIVE-POSITIONING.md`](./offerings/COMPETITIVE-POSITIONING.md) — Evenhanded build-vs-buy and vs-point-solution / vs-copilot / vs-advisory framing, with talk tracks by buyer.
- [`OBJECTION-HANDLING.md`](./offerings/OBJECTION-HANDLING.md) — The ten objections by buyer persona, each answered with the repo proof point their engineers can verify.

### For CIOs, CCOs, and Executive Sponsors

**[`ENTERPRISE-PLATFORM.md`](./ENTERPRISE-PLATFORM.md)** — The platform vision document. Explains the five-layer infrastructure that turns AI agents from experimental pilots into governed operating infrastructure: API access, MCP authorization gateway, federated identity, agent catalog, and A2A communication standards. Maps each layer to its regulatory requirement (SR 11-7, FFIEC, NIST AI RMF, GLBA, NIST SP 800-207). Includes an implementation-state table distinguishing what's built today from what's designed for Phase-2. This is the document to share before an executive briefing.

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

| Regulation | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| BSA 31 U.S.C. § 5318 (SAR filing) | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | — | ✅ | ✅ | ✅ | — |
| FinCEN CDD Rule (31 CFR 1020.210) | ✅ | ✅ | ✅ | — | — | ✅ | — | — | ✅ | ✅ | — | — |
| OFAC IEEPA (SDN screening, 50% rule) | ✅ | ✅ | ✅ | ✅ | — | — | — | ✅ | ✅ | ✅ | — | — |
| FATF R.10 (Customer due diligence) | ✅ | — | ✅ | — | — | — | — | — | — | ✅ | — | — |
| FATF R.12 (PEP enhanced due diligence) | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — | — |
| FATF R.20 (Suspicious transaction reporting) | ✅ | ✅ | — | ✅ | — | — | ✅ | — | — | ✅ | — | — |
| USA PATRIOT Act § 326 (CIP) | ✅ | — | ✅ | — | — | — | — | ✅ | ✅ | — | — | — |
| FIN-2014-G001 (SAR narrative format) | ✅ | — | — | — | — | — | ✅ | — | — | ✅ | — | — |
| SR 11-7 (Model risk management) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| FFIEC BSA/AML Examination Manual | ✅ | ✅ | ✅ | — | — | ✅ | — | — | — | — | ✅ | — |
| 18 U.S.C. § 1960 (No tipping off) | ✅ | — | — | — | ✅ | — | ✅ | — | — | ✅ | — | — |
| 5-year BSA record retention | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| 10-year model validation retention | — | — | — | — | — | — | — | — | — | — | ✅ | — |
| 7-year FCRA record retention | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| FDCPA (15 U.S.C. § 1692) | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| CFPB Regulation F (12 CFR Part 1006) | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| SCRA (50 U.S.C. § 3937) | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| Bankruptcy Code 11 U.S.C. § 362 | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| FCRA (15 U.S.C. § 1681) | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| UDAAP / Dodd-Frank § 1031 | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| TCPA (47 U.S.C. § 227) | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| IRS 26 U.S.C. § 6050P (1099-C) | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| Reg E (EFTA) — provisional credit / disputes | — | — | — | ✅ | — | — | — | — | — | ✅ | — | — |
| Nacha Operating Rules (ACH return / NOC) | — | — | — | ✅ | — | — | — | — | — | ✅ | — | — |
| Reg BI (17 CFR 240.15l-1) | — | — | — | — | ✅ | — | — | — | — | — | — | — |
| FINRA Rule 2111 (Suitability) | — | — | — | — | ✅ | — | ✅ | — | — | — | — | — |
| FINRA Rule 2210 (Communications) | — | — | — | — | ✅ | — | — | — | — | — | — | — |
| FINRA Rule 3110 (Supervisory procedures) | — | — | — | — | — | — | ✅ | — | — | — | — | — |
| FINRA Rule 4511 (Books and records) | — | — | — | — | — | — | ✅ | — | — | — | — | — |
| ERISA (retirement account fiduciary) | — | — | — | — | ✅ | — | — | — | — | — | — | — |
| GLBA (data privacy / PII safeguards) | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | ✅ | ✅ | — | ✅ |
| Dodd-Frank § 747 (Spoofing ban) | — | — | — | — | — | — | ✅ | — | — | — | — | — |
| SEC Regulation SHO (Short selling) | — | — | — | — | — | — | ✅ | — | — | — | — | — |
| SEC Rule 10b-5 (Market manipulation) | — | — | — | — | — | — | ✅ | — | — | — | — | — |
| ECOA / Reg B (Fair lending, adverse action) | — | — | — | — | — | — | — | ✅ | ✅ | — | ✅ | — |
| HMDA (Home Mortgage Disclosure Act) | — | — | — | — | — | — | — | ✅ | ✅ | — | — | — |
| CRA (Community Reinvestment Act) | — | — | — | — | — | — | — | ✅ | — | — | — | — |
| Reg Z / TILA (Truth in Lending) | — | — | — | — | — | — | — | ✅ | — | — | — | — |
| SBA 7(a) / 504 Program Rules | — | — | — | — | — | — | — | ✅ | — | — | — | — |
| CFPB Prepaid Rule (12 CFR Part 1005) | — | — | — | — | — | — | — | — | — | ✅ | — | — |
| UCC Article 4A (Wire transfer liability) | — | — | — | — | — | — | — | — | — | ✅ | — | — |
| OFAC Blocking Report (501.604 SLA) | — | — | — | — | — | — | — | — | — | ✅ | — | — |
| CTR (31 CFR 1010.311 — $10K threshold) | ✅ | — | — | — | — | — | — | — | — | ✅ | — | — |

---

## ROI Summary

> All figures are illustrative estimates based on publicly available industry benchmarks and common operating assumptions (analyst hourly rates, alert volumes, FP rates). Actual savings will vary by institution size, workflow maturity, and implementation scope. Treat these as directional inputs for a business case, not independently validated guarantees.

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
| 11 · Model Risk Management | $20K–$57K per manual validation · undetected degradation losses · SR 11-7 exam gaps | $735K–$1.28M (5 models) |
| 12 · Collections & Recovery | $340K–$2.4M FDCPA violations · 25–49 min/account compliance research · SCRA/bankruptcy mishandling | $890K–$3.8M (5K accounts/year) |
| **Full suite** | **End-to-end financial crime + fraud + wealth + compliance ops + model governance + collections** | **$27M+ annually** |

Payback period for full suite deployment: **< 6 months**

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent orchestration | LangGraph 0.2.28+ |
| LLM — primary (analysis/narrative) | OpenAI GPT-4o · AWS Bedrock **Claude Sonnet 4.6** (`anthropic.claude-sonnet-4-6-20260601-v1:0`) |
| LLM — fast-path (triage/scoring) | AWS Bedrock **Claude Haiku 4.5** (`anthropic.claude-haiku-4-5-20251001`) |
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

# ── RECOMMENDED: Start with Agent 09 (Document Intelligence) ──────────────
# Deploy first — its structured output immediately benefits every other agent.
cd 09-document-intelligence-agent
cp .env.example .env
# Add OPENAI_API_KEY to .env (optional — demo mode works without it)
docker compose up
# Open: http://localhost:8509

# ── FINANCIAL CRIME LOOP ──────────────────────────────────────────────────
# Agent 02 first (upstream FP suppressor), then Agent 01 (investigation)
cd ../02-aml-tms-enhancement-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8502

cd ../01-financial-crime-investigation-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8501

cd ../03-kyc-cdd-perpetual-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8503

# ── FRAUD & PAYMENTS ──────────────────────────────────────────────────────
cd ../04-fraud-detection-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8504

cd ../10-payments-compliance-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8510

# ── CUSTOMER INTELLIGENCE ────────────────────────────────────────────────
cd ../05-wealth-rm-copilot
cp .env.example .env
docker compose up
# Open: http://localhost:8505

# ── COMPLIANCE OPERATIONS ────────────────────────────────────────────────
cd ../06-regulatory-change-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8506

cd ../07-trading-surveillance-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8507

# ── LENDING ──────────────────────────────────────────────────────────────
cd ../08-credit-underwriting-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8508

# ── MODEL RISK MANAGEMENT ────────────────────────────────────────────────
# Deploy last — validates all scoring models; requires other agents to have
# production performance baselines before validation runs are meaningful.
cd ../11-model-risk-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8511

cd ../12-collections-recovery-agent
cp .env.example .env
docker compose up
# Open: http://localhost:8512
```

> **Demo mode:** All agents run with pre-computed scenarios when `OPENAI_API_KEY` is absent. Start any agent without an API key to explore the full UI and all regulatory decision paths.

**Port reference:**

| Agent | Port |
|---|---|
| 01 · Financial Crime Investigation | 8501 |
| 02 · AML/TMS Enhancement | 8502 |
| 03 · KYC/CDD Perpetual Monitoring | 8503 |
| 04 · Real-Time Fraud Detection | 8504 |
| 05 · Wealth & RM Copilot | 8505 |
| 06 · Regulatory Change Management | 8506 |
| 07 · Trading Surveillance | 8507 |
| 08 · Credit Underwriting | 8508 |
| 09 · Document Intelligence | 8509 |
| 10 · Payments Compliance | 8510 |
| 11 · Model Risk Management | 8511 |
| 12 · Collections & Recovery | 8512 |

---

## Asset Classification: Accelerator / Reference Implementation

This suite is a production-shaped accelerator, not a production product. The regulatory control patterns, LangGraph architecture, and platform collateral are designed to compress an SI engagement by months — but a hardening sprint is in scope before any customer production deployment.

| Implemented and tested | Designed — built per engagement or Phase-2 |
|---|---|
| All 12 agent suites — deterministic regulatory controls as code (OFAC hard overrides, fail-safe HITL routing, FDCPA/Reg F/SCRA/Reg E rules) | Real connectors (TMS, core banking, watchlist vendors) — all integrations run on fixtures in the accelerator |
| 712 tests green in CI across all 12 suites, platform library, and governance; control tests gate merges | MCP server connectors (per-system integrations — TMS, core banking, watchlist — built per engagement using the `platform_core/connectors/` abstraction layer) |
| `platform_core/mcp_gateway/` — deny-by-default authorization gateway reference implementation: least-privilege-as-intersection enforcement, scoped HMAC tokens, append-only PII-masked audit, fail-closed; 26 tests + 81-test platform suite | Production MCP gateway deployment (wired to real IdP, Amazon Verified Permissions / Cedar, DynamoDB PutItem-only + S3 Object Lock) — stand-up in pilot sprint |
| `governance/` — grounding verification, prompt manifest gate, structural injection red-team, Agent 08 fairness/disparate-impact testing, golden-case eval harness | Bedrock + Guardrails in-VPC inference (required for data-residency guarantee; IaC reference in `infra/terraform/`) |
| `platform_core/` — shared LLM factory, fail-closed JWT auth, PII masking, Secrets Manager, OTel tracing | Cognito/Okta authentication, full observability stack — described in architecture; not pre-wired |
| `infra/terraform/` — five AWS reference modules (network, security, data, agent_service, dev env) | Operational runbooks and DR procedures — now shipped in `runbooks/`; RTO/RPO defined per client tier in pilot |
| `runbooks/` — incident response, DR, HITL queue ops, model degradation response | Live-model red-team against production deployment (pen-test plan in `offerings/TPRM-DUE-DILIGENCE-PACKET.md §4`) |
| `docs/user-guides/` — five per-persona reviewer guides (BSA/AML, credit/fair-lending, ops, auditor) + fundamentals | SOC 2 report — roadmap; single-tenant in-client-account deployment inherits most controls from client's own AWS posture |
| `offerings/EXECUTIVE-BRIEFING.pptx` — 9-slide exec deck, every claim traced to the repo | — |
| Demo mode without API keys for every regulatory decision path | — |

In customer conversations: **"production-shaped, hardening-scoped"** — bank technical evaluators will verify claims against the code, and credibility is the asset.


## How to Evaluate This Repository

> **This repository should be evaluated as a financial services agentic AI modernization accelerator: a repeatable demo, architecture, and GTM foundation showing how regulated workflows can be redesigned with secure agents, governed tool access, AWS-native deployment patterns, human review, and auditable modernization.**

It is a **production-shaped accelerator**, not a production-ready regulated platform. Read every capability below against this maturity ladder:

| Level | Meaning |
|---|---|
| **Documented** | Described in the README or docs; not necessarily implemented. |
| **Demonstrated** | Implemented enough to run in a local demo (this is where most agents sit today). |
| **Deployable** | Can be deployed to AWS with documented, repeatable steps (Terraform reference + per-agent guides). |
| **Production-ready** | Security hardening, identity, authorization, observability, testing, CI/CD, runbooks, auditability, failure handling, and customer-specific integrations are all present. The suite reaches this only after the per-engagement hardening sprint. |

Use the phrase **agentic AI modernization accelerator** in leadership and customer conversations unless specific repository evidence supports a stronger claim. Do not position the suite as a production-ready regulated platform.

### Control-integrity hardening (June 2026)

A structured review hardened the two highest-stakes control gaps and added a CI guard so they cannot regress. See [`CONTROL-INTEGRITY-CHANGELOG.md`](./CONTROL-INTEGRITY-CHANGELOG.md) for details.

- **Agent 01 (Financial Crime Investigation)** now compiles with `interrupt_before=["human_review_gate"]`, so its SAR human-review gate is framework-enforced — matching the rest of the suite. A new CI guard (`governance/tests/test_hitl_gates.py`) fails the build if any gate-bearing agent regresses to a procedural-only gate.
- **Agent 02 (AML/TMS Enhancement)** now gates suppression on a **deterministic-only** score (rule pre-score + historical base rates, LLM excluded). The model can author justification and escalate, but can never be the reason an alert is removed from human review. Every routing decision records the deterministic basis in the audit trail.
- **Platform** adds PII-masking boundary middleware (`scrub_for_persistence`), secrets fail-closed mode, and mandatory Bedrock Guardrails in production.

---
## About

Built by [David Ryder](https://github.com/virtualryder) as an art-of-the-possible, production-shaped agentic AI accelerator portfolio for financial services.

All agents are designed for real deployment — customization, security, and independent verification remain the responsibility of the implementing institution. Regulatory citations reflect the relevant framework requirements as understood at time of writing; institutions should validate applicability to their specific charter, jurisdiction, and examiner expectations. Integration points reference actual FSI system landscapes (Actimize, Verafin, Fiserv, FIS, Refinitiv, LexisNexis) and are illustrative of how these agents would connect in a production environment.

**Target buyers:** BSA Officers · Chief Compliance Officers · Financial Crime Operations Leaders · CIOs at banks, credit unions, and broker-dealers


*Part of the [Agentic Application Examples](https://github.com/virtualryder) portfolio — production-shaped LangGraph agents across financial services, healthcare, government, and enterprise domains.*
