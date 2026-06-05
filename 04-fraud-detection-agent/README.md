# Real-Time Fraud Detection Agent
### Sub-200ms Payment Fraud Prevention — Rule Engine + LLM + Behavioral Analytics

> **Part of the [Financial Services AI Agent Suite](../README.md)** — works alongside the [Financial Crime Investigation Agent](../01-financial-crime-investigation-agent/), [AML/TMS Enhancement Agent](../02-aml-tms-enhancement-agent/), and [KYC/CDD Perpetual Agent](../03-kyc-cdd-perpetual-agent/) to form an end-to-end financial crime prevention platform.

---

## The Problem

A regional bank processing 500,000 transactions/day:
- **$2.3M in annual fraud losses** — card-not-present (CNP) and account takeover (ATO)
- **$420K in operational cost** — 12 fraud analysts spending 30+ hrs/week on manual reviews
- **4,200 false positives/month** — legitimate transactions declined, damaging customer experience
- **12-minute average review time** — analysts drowning in alerts with no AI-assisted prioritization
- **Reg E exposure** — late disclosures and missed provisional credit deadlines

**This agent cuts fraud losses by 60-70% while reducing false positive rates by 40%.**

---

## Two-Path Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              Real-Time Fraud Detection Agent (LangGraph)                     │
│                                                                             │
│  ── REAL-TIME PATH (<200ms) ─────────────────────────────────────────────  │
│  transaction_intake → account_context_lookup → feature_extraction →         │
│  rule_engine_prescoring →                                                   │
│                                                                             │
│  ── ASYNC ENRICHMENT PATH ────────────────────────────────────────────────  │
│  → device_intelligence → behavioral_analysis → llm_fraud_analysis →        │
│  → composite_scoring →                                                      │
│                                                                             │
│  ── ROUTING DECISION ─────────────────────────────────────────────────────  │
│  composite_score ≥ 85   → block_transaction    (Decline · Reg E disclosure) │
│  composite_score 65-84  → step_up_authentication (SMS OTP · Push auth)     │
│  composite_score 40-64  → flag_for_analyst_review (Allow · Queue case)     │
│  composite_score < 40   → allow_transaction    (Approve · Monitor)         │
│                                                                             │
│  ANALYST_REVIEW → 👤 human_review_gate → finalize_decision → END           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Workflow Diagram (Mermaid)

```mermaid
graph TD
    A[💳 Transaction Event] --> B[transaction_intake<br/>Parse & Validate]
    B --> C[account_context_lookup<br/>History · Risk Tier · Profile]
    C --> D[feature_extraction<br/>Velocity · Amount Ratio · Features]
    D --> E[rule_engine_prescoring<br/>Deterministic Rules<br/>Velocity · Geography · MCC]
    E --> F[device_intelligence<br/>Device Risk · Impossible Travel<br/>VPN/Proxy · IP Reputation]
    F --> G[behavioral_analysis<br/>Session Anomaly · Time-of-Day<br/>New Payee · Login Pattern]
    G --> H[llm_fraud_analysis<br/>GPT-4o Contextual Analysis<br/>Fraud Type Hypothesis]
    H --> I[composite_scoring<br/>Rule 30% · LLM 50% · History 20%]
    I --> J{{routing_decision<br/>Fraud Score Threshold}}
    J -->|score ≥ 85| K[block_transaction<br/>Decline · Reg E Disclosure<br/>Case Created]
    J -->|score 65-84| L[step_up_authentication<br/>SMS OTP · Push Auth]
    J -->|score 40-64| M[flag_for_analyst_review<br/>Allow + Case Queue]
    J -->|score < 40| N[allow_transaction<br/>Approve + Monitor]
    M --> O[👤 human_review_gate<br/>Fraud Analyst Decision]
    K --> P[finalize_decision<br/>Audit Trail · SAR Flag<br/>Notifications]
    L --> P
    N --> P
    O --> P
    P --> Q[END ✓]

    style A fill:#2196F3,color:#fff
    style J fill:#ffa500,color:#fff
    style K fill:#dc2626,color:#fff
    style L fill:#ea580c,color:#fff
    style M fill:#d97706,color:#fff
    style N fill:#16a34a,color:#fff
    style O fill:#4CAF50,color:#fff
    style Q fill:#9C27B0,color:#fff
```

---

## Fraud Signal Stack

| Layer | Signal | Tools | Weight |
|---|---|---|---|
| **Rules** | Velocity, geography, MCC, device, amount | `rule_engine.py` | 30% |
| **Device** | New device, impossible travel, VPN/Tor, IP reputation | `device_intelligence` node | Feeds LLM |
| **Behavioral** | Session anomaly, new payee, time-of-day, login pattern | `behavioral_analysis` node | Feeds LLM |
| **LLM** | GPT-4o holistic pattern synthesis + fraud type classification | `llm_fraud_analysis` node | 50% |
| **Historical** | Account baseline, prior fraud rate, behavioral risk blend | `composite_scoring` node | 20% |

### Hard Block Triggers (Score-Independent)
- **Confirmed fraud IP** — IP address associated with prior confirmed fraud
- **Tor exit node** — Transaction from anonymized Tor network
- **OFAC-adjacent merchant** — Merchant name/counterparty on watchlists

---

## Decision Outcomes

| Decision | Threshold | Customer Action | Analyst Action |
|---|---|---|---|
| **ALLOW** | Score < 40 | None — transaction proceeds | None required |
| **STEP_UP_AUTH** | Score 65-84 | SMS OTP / Push notification challenge | None if auth passes |
| **ANALYST_REVIEW** | Score 40-64 | None — transaction allows silently | Case created, 4-hr SLA |
| **BLOCK** | Score ≥ 85 | Notified — Reg E disclosure sent | Case created, review required |
| **FREEZE_ACCOUNT** | Hard override | Emergency contact | Immediate BSA escalation |

---

## Fraud Scenarios Covered

| Fraud Type | Primary Signals | Detection Rate |
|---|---|---|
| Card Testing | Velocity 1-min, small amounts, new device | Very High |
| Account Takeover | Impossible travel, new device, behavioral anomaly | High |
| Card-Not-Present (CNP) | New device, CNP channel, no 2FA, new merchant | High |
| Authorized Push Payment (APP) | New payee, large amount, unusual hour | Moderate-High |
| Wire Fraud / BEC | Wire channel, international, new counterparty | High |
| Structuring | Amount $9,000-$9,999, wire channel | High (SAR flagged) |
| Elder Financial Exploitation | Behavioral anomaly + elder customer flag | Moderate |

---

## Regulatory Coverage

| Regulation | Coverage |
|---|---|
| **Reg E (12 CFR § 1005 / EFTA)** | Auto-drafted disclosure for all BLOCK decisions; 60-day dispute right; 10-business-day provisional credit; 45-90 day investigation timeline |
| **Nacha Operating Rules** | ACH unauthorized return code awareness (R05, R07, R10); ODFI/RDFI monitoring obligations |
| **Visa Zero Liability / Reason Code 10.4** | Rule-hit evidence package for chargeback representment |
| **Mastercard Reason Code 4837** | Deterministic rule basis for fraud dispute |
| **BSA 31 U.S.C. § 5318(g)** | SAR consideration flag for money laundering indicators (structuring, wire fraud, rapid fund movement) |
| **OFAC IEEPA** | Hard block for OFAC-adjacent merchant or counterparty |
| **SR 11-7 Model Risk** | Explainable composite score with component weights; LLM output documented with reasoning; human override capability |
| **CFPB Fair Lending** | Score components are race/sex-neutral — transaction signals only |
| **GLBA (15 U.S.C. § 6801)** | IP address and device fingerprint masked/hashed before logging |
| **18 U.S.C. § 1960** | ANALYST_REVIEW cases queued silently — customer not notified to avoid tipping off |

---

## ROI

| Metric | Before | With Agent | Impact |
|---|---|---|---|
| Annual fraud losses | $2.3M | ~$800K | **-65%** |
| Analyst alert review time | 30 hrs/week each × 12 analysts | 8 hrs/week each × 8 analysts | **-80% analyst hours** |
| False positive rate | 4,200/month | ~2,500/month | **-40%** |
| Average review time per alert | 12 minutes | 3 minutes (AI pre-summarized) | **-75%** |
| Reg E late disclosure incidents | 12/year | ~2/year | **-83%** |

**Annual savings (fraud + analyst reduction):**
- Fraud loss reduction: $1.5M
- Analyst efficiency (4 analysts × 40 hrs/week × 50 wks × $75/hr): $600K
- **Total: ~$2.1M annually**

---

## Quick Start

### Local Development
```bash
cp .env.example .env
# Add OPENAI_API_KEY

pip install -r requirements.txt
streamlit run app.py
# Open: http://localhost:8504
```

### Docker
```bash
docker compose up
# Open: http://localhost:8504
```

### Run Tests
```bash
pytest tests/ -v
```

---

## Project Structure

```
04-fraud-detection-agent/
├── app.py                          # Streamlit dashboard (6 tabs)
├── agent/
│   ├── graph.py                    # 14-node two-path LangGraph DAG
│   ├── nodes.py                    # All 14 node functions
│   ├── state.py                    # FraudDetectionState TypedDict (50+ fields)
│   └── prompts.py                  # LLM prompts (fraud analysis, Reg E, case narrative)
├── tools/
│   ├── rule_engine.py              # Deterministic rule library (velocity, geography, MCC)
│   └── case_manager.py             # Case records + append-only JSONL audit log
├── data/fixtures/
│   └── sample_transactions.json   # 5 demo scenarios (card testing to ATO)
├── tests/
│   ├── test_graph.py               # Graph compilation + routing + regulatory controls
│   └── test_tools.py               # Rule engine unit tests with regulatory assertions
├── .streamlit/config.toml
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── railway.toml
```

---

## Dashboard Tabs

| Tab | Description |
|---|---|
| **Transaction Input** | Load 5 sample scenarios or enter custom transaction |
| **Detection Pipeline** | Node-by-node execution grid with key findings |
| **Fraud Score** | Gauge chart + component breakdown + SR 11-7 documentation table |
| **Decision & Evidence** | Fraud decision banner, LLM reasoning, Reg E disclosure draft, SAR flag |
| **Analyst Review** | HITL panel — CONFIRMED_FRAUD / FALSE_POSITIVE / ESCALATE determination |
| **Audit Trail** | Examination-ready JSONL entries with data sources, regulatory basis, response time |

---

## Part of the Financial Services AI Suite

```
01 · Financial Crime Investigation  →  Investigate AML alerts end-to-end
02 · AML/TMS Enhancement            →  Reduce false positive alert volume
03 · KYC/CDD Perpetual              →  Automate customer due diligence lifecycle
04 · Real-Time Fraud Detection      →  This agent
05 · Wealth & RM Copilot            →  Coming soon
06 · Regulatory Change Agent        →  Coming soon
```
