# Agent 07 — Trading Surveillance Agent

AI-powered trading surveillance for broker-dealers and banks with trading desks. Automates pattern detection, risk scoring, investigation narrative synthesis, and disposition documentation across 11 market abuse alert types. Covers equity, fixed income, derivatives, FX, commodities, and crypto.

---

## The Problem

A mid-size broker-dealer's surveillance team receives 800+ alerts per month. Each requires:

1. Retrieving the order blotter and enriching with trader history
2. Running pattern analysis to determine which manipulation behavior is indicated
3. Assessing market context — was there news that explains the trading?
4. Scoring severity and routing to the appropriate compliance reviewer
5. Writing an investigation narrative and disposition memo
6. Determining SAR filing obligations and regulatory reporting requirements

Manual processing takes 2–6 hours per significant alert. False positive rates of 90–97% cause fatigue. Documentation quality is inconsistent. And the one real case in 20 looks identical to the other 19.

**This agent automates steps 1–3 and steps 5–6, and cuts HITL review time for step 4 by 70%.**

---

## Architecture

**12-node LangGraph StateGraph** processing trading alerts from intake through disposition:

```
alert_intake → data_enrichment → pattern_detection [Python] →
market_context [LLM] → risk_scoring [Python] → routing_decision [Python] →

CRITICAL/HIGH → human_review_gate [HITL] → investigation [LLM] →
                disposition [LLM] → case_tracking_update → finalize

MEDIUM/LOW   → investigation [LLM] → disposition [LLM] →
               case_tracking_update → finalize
```

**LLM vs. Python boundary:**
| Decision | Who Makes It | Why |
|---------|------------|-----|
| What patterns are present? | Python rule engine | Deterministic; SR 11-7 / FINRA 3110 |
| Risk score (0–1)? | Python (5-factor model) | SR 11-7 requirement; no LLM opacity |
| HITL required? | Python (tier threshold) | No LLM can waive compliance review |
| SAR threshold met? | Python ($5,000 threshold) | BSA bright-line rule |
| Investigation narrative | LLM (Claude/GPT-4o) | Analysis and synthesis |
| Disposition memo | LLM | Drafting task |
| SAR narrative | LLM | Drafting task (filed by human) |
| Market context | LLM | Research synthesis |

---

## Risk Scoring Model

Composite score 0.0–1.0 from 5 weighted components (SR 11-7 / FINRA Rule 3110 documented):

| Factor | Weight | Description |
|--------|--------|-------------|
| Pattern Severity | 25% | Inherent regulatory seriousness of detected alert type |
| Trade Size / Market Impact | 25% | Notional value and relative market significance |
| Recidivism / History | 20% | Prior alerts for this trader in the past 12 months |
| Regulatory Exposure | 15% | Mandatory reporting obligations (SAR, FINRA, SEC, CFTC) |
| Evidence Quality | 15% | Number and strength of corroborating signals |

**Severity Tiers:**
- **CRITICAL** (≥ 0.85): Immediate HITL. Legal escalation. SAR evaluation mandatory.
- **HIGH** (0.65–0.84): Mandatory compliance officer HITL review.
- **MEDIUM** (0.40–0.64): Auto-investigation + supervisor review.
- **LOW** (< 0.40): Auto-document and close.

**Hard overrides (deterministic Python — never LLM):**
- `INSIDER_TRADING` / `INFORMATION_BARRIER_BREACH` / `CROSS_MARKET_MANIPULATION` → always CRITICAL + mandatory HITL
- `restricted_list_hit` + MEDIUM → escalate to HIGH
- Prior alerts ≥ 6 + HIGH → escalate to CRITICAL

---

## Alert Types Covered

| Alert Type | Regulatory Basis | Default HITL |
|-----------|-----------------|:------------:|
| Layering / Spoofing | Dodd-Frank § 747; SEA § 9(a)(2); CFTC 180.1 | HIGH+ |
| Front Running | FINRA Rule 5270; SEA § 10(b) | HIGH+ |
| Wash Trading | SEA § 9(a)(1); CFTC CEA § 4c(a) | HIGH+ |
| Insider Trading | SEA § 10(b); SEC Rule 10b-5; 18 U.S.C. § 1348 | **Always** |
| Marking the Close | SEA § 9(a)(2); FINRA Rule 5210 | HIGH+ |
| Excessive Trading | FINRA Rule 2111; FINRA Rule 2010 | MEDIUM+ |
| Best Execution Failure | FINRA Rule 5310; Reg NMS Rule 611 | MEDIUM+ |
| Short Selling Violation | SEC Regulation SHO Rules 203–204 | HIGH+ |
| Cross-Market Manipulation | SEA § 9(a)(2); CFTC CEA § 6(c); Dodd-Frank § 747 | **Always** |
| Information Barrier Breach | Regulation FD; FINRA Rule 3110; SEA § 10(b) | **Always** |
| Unusual Activity | FINRA Rule 3110; BSA SAR evaluation | MEDIUM+ |

---

## Dashboard — 6 Tabs

| Tab | Purpose |
|-----|---------|
| **Alert Queue** | Submit alerts; severity distribution chart; case register with filters |
| **Case Investigation** | Pattern analysis, risk score breakdown, evidence assembly, HITL review panel |
| **Disposition** | SAR determination, disposition memo, regulatory reporting requirements |
| **Trader Registry** | Trader profiles, prior alert history, restricted/watch list, risk tier |
| **Audit Trail** | Append-only case log — FINRA 4511 / SEC 17a-4 examination evidence |
| **Configuration** | Surveillance rules, routing matrix, SR 11-7 scoring weights |

---

## Regulatory Coverage

- **FINRA Rule 3110** — Written supervisory procedures; supervisory system requirements
- **FINRA Rule 4511** — Books and records retention
- **FINRA Rule 5210** — Publication of transactions and quotations
- **FINRA Rule 5270** — Front running prohibition
- **FINRA Rule 5310** — Best execution
- **SEC Rule 10b-5** — Anti-fraud; market manipulation
- **SEC Regulation SHO** — Short selling (Rules 203, 204)
- **Dodd-Frank Section 747** — Spoofing prohibition
- **BSA / 31 CFR § 1023.320** — SAR filing for broker-dealers
- **SR 11-7** — Model risk management for the impact scoring model

---

## Quick Start

```bash
cd 07-trading-surveillance-agent
cp .env.example .env
# Add your OPENAI_API_KEY to .env

pip install -r requirements.txt
streamlit run app.py
# Dashboard: http://localhost:8507
```

**Run tests:**
```bash
pytest tests/ -v
```

**Docker:**
```bash
docker build -t trading-surveillance-agent .
docker run -p 8507:8507 --env-file .env trading-surveillance-agent
```

---

## Configuration

### Surveillance Rules (`data/fixtures/surveillance_rules.json`)
8 detection rules covering all primary market manipulation patterns. Thresholds are documented per FINRA Rule 3110 written supervisory procedure requirements.

### Trader Registry (`data/fixtures/trader_registry.json`)
Trader profiles with account risk tier, prior alerts, restricted/watch instrument lists, and supervisor assignment.

### Routing Matrix (`data/fixtures/routing_matrix.json`)
Asset-class-based routing to the appropriate surveillance officer, with alert-type overrides for INSIDER_TRADING, INFORMATION_BARRIER_BREACH, and CROSS_MARKET_MANIPULATION.

---

## ROI

**6-analyst surveillance team, 800 alerts/month:**

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Hours per HIGH alert | 5.8 hrs | 1.0 hr | 83% |
| Hours per MEDIUM alert | 1.7 hrs | 0.33 hr | 81% |
| Annual surveillance hours | 11,404 hrs | 2,003 hrs | 9,401 hrs |
| False-positive processing cost | $650K | $85K | **$565K** |
| Enforcement action avoidance | — | — | **$1.8M/year** |
| **Total annual net value** | | | **~$2.6M** |

**Payback period:** 8–12 weeks

See `docs/roi-analysis.md` for full analysis by firm size and 3-year NPV.

---

## Suite Integration

Agent 07 connects to the broader FSI AI Agent Suite:

- When Agent 07 detects **layering/spoofing** → notifies Agent 06 (Regulatory Change Management) to monitor related CFTC/FINRA rule changes
- When Agent 07 flags **potential insider trading** → cross-notifies Agent 01 (Financial Crime Investigation) for BSA/SAR assessment
- When Agent 07 identifies **wash trading** → triggers Agent 03 (KYC/CDD) to expedite perpetual monitoring review for implicated accounts

---

## Project Structure

```
07-trading-surveillance-agent/
├── agent/
│   ├── state.py           # TradingSurveillanceState TypedDict + Enums
│   ├── nodes.py           # 12 node functions
│   ├── graph.py           # LangGraph StateGraph DAG
│   └── prompts.py         # LLM prompts (investigation, disposition, SAR, market context)
├── data/
│   └── fixtures/
│       ├── trader_registry.json      # 4 sample trader profiles with alert history
│       ├── surveillance_rules.json   # 8 detection rules with thresholds
│       ├── routing_matrix.json       # Asset-class and alert-type routing
│       └── sample_alerts.json        # 3 sample alerts for demo
├── docs/
│   ├── aws-deployment-guide.md
│   ├── regulatory-compliance.md
│   └── roi-analysis.md
├── tests/
│   ├── test_nodes.py      # Unit tests (pattern detection, scoring, routing — no LLM)
│   └── test_graph.py      # Integration tests (mocked LLM)
├── app.py                 # Streamlit dashboard (port 8507)
├── Dockerfile
├── railway.toml
└── requirements.txt
```
