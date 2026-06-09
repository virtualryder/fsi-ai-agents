# Agent 08 — Credit Underwriting Agent

AI-powered credit origination for banks, credit unions, and non-bank lenders. Automates financial analysis, fair lending screening, risk scoring, credit memo drafting, and ECOA-compliant adverse action notices across 12 loan types. Connects underwriting to the KYC/CDD (Agent 03) and Financial Crime (Agent 01) pipelines.

---

## The Problem

A community bank originating 150 loans per month employs 6 underwriters. Each spends:

- **30–90 min** calculating DTI, LTV, DSCR, and reserves — spreadsheet math that is deterministic and error-prone
- **45–120 min** drafting the credit memorandum — a structured narrative with the same sections every time
- **30–45 min** completing the fair lending checklist — a manual form that examiners find inconsistently applied
- **30–60 min** drafting the adverse action notice — a legally precise document with specific Reg B language requirements

Total: **5–7 hours per application**. Of that, approximately **1 hour** requires credit judgment. The rest is structured data extraction, calculation, and templated writing.

**This agent automates the 4–6 hours of structured work and sharpens the 1 hour of judgment.**

---

## Architecture

**12-node LangGraph StateGraph** processing loan applications from intake through final decision:

```
application_intake → applicant_profile_lookup → document_verification →
credit_bureau_pull → financial_analysis [Python] → fair_lending_check [Python] →
risk_scoring [Python] → routing_decision [Python] →

HITL required → human_review_gate [HITL] → credit_memo_drafting [LLM] →
No HITL       ─────────────────────────── → credit_memo_drafting [LLM] →

Decline       → adverse_action_node [LLM] → finalize_decision
Approve       ──────────────────────────── → finalize_decision
```

**LLM vs. Python boundary:**

| Decision | Who Makes It | Why |
|---------|------------|-----|
| DTI / LTV / DSCR calculation | Python | Deterministic math — no LLM opacity |
| OFAC match | Python (credit bureau node) | Hard block — cannot be waived by LLM |
| Fair lending flag | Python (ECOA/FHA screening) | Mandatory HITL — no LLM override |
| Risk score (0.0–1.0) | Python (5-factor model) | SR 11-7 — documented, auditable |
| HITL routing | Python (tier threshold) | No LLM can waive compliance review |
| Adverse action reasons | Python (Reg B standard list) | Reg B specific-reason requirement |
| HMDA action taken code | Python | Regulatory reporting — deterministic |
| SAR referral flag | Python (OFAC = SAR) | BSA bright-line rule |
| Credit memo narrative | LLM (GPT-4o) | Structured drafting task |
| Adverse action notice | LLM | Drafting task with pre-selected reasons |
| Conditions letter | LLM | Drafting task |
| Exception narrative | LLM | Documentation task |

---

## Risk Scoring Model

Composite score 0.0–1.0 from 5 weighted factors (SR 11-7 documented):

| Factor | Weight | Measurement |
|--------|--------|------------|
| Credit Score | 30% | FICO to normalized curve (300–850 → 0.0–1.0) |
| DTI | 25% | Total DTI including proposed payment |
| LTV | 20% | Loan-to-value at origination |
| Cash Flow / DSCR | 15% | DSCR ≥ 1.25 (commercial) or residual income (consumer) |
| Collateral | 10% | Collateral type risk weight (PRIMARY_RESIDENCE = 0.90 … UNSECURED = 0.30) |

**Decision Thresholds:**
- **APPROVE** (≥ 0.75): Proceed to credit memo — may be auto-decision or underwriter review
- **APPROVE WITH CONDITIONS** (0.55–0.74): Underwriter-defined conditions required
- **REFER TO COMMITTEE** (0.35–0.54): Mandatory credit committee HITL
- **DECLINE** (< 0.35): Adverse action notice required within 30 days (Reg B)

**Hard decline rules (Python constants — not configurable in UI):**
- Total DTI > 50%
- FICO < 580 (conventional/FHA mortgage)
- FICO < 680 (jumbo mortgage)
- Chapter 7 bankruptcy discharged < 2 years
- Chapter 13 bankruptcy discharged < 1 year
- OFAC SDN match (hard block + SAR referral)

---

## Loan Types Covered (12)

| Loan Type | Key Policy Constraints | Regulatory Basis |
|-----------|----------------------|-----------------|
| Conventional Mortgage | Max 97% LTV; Min FICO 580; Max DTI 43% | FNMA B3-6-02; HMDA; Reg Z |
| FHA Mortgage | Max 96.5% LTV; Min FICO 580; FHA case number required | HUD 4000.1; HMDA |
| VA Mortgage | Max 100% LTV; Min FICO 620; DD214/COE required | VA Lender Handbook; HMDA |
| Jumbo Mortgage | Max 85% LTV; Min FICO 680; 6 months reserves | OCC 12 CFR Part 34 |
| HELOC | Max 85% CLTV; Min FICO 660 | 12 CFR 1026.40 (Reg Z) |
| Commercial Real Estate | Min DSCR 1.25; Max LTV 75%; Environmental required | FDIC Part 365; FFIEC CRE |
| Commercial Term Loan | Min DSCR 1.25; 2+ years in business | OCC 12 CFR Part 30 |
| SBA 7(a) | Min DSCR 1.15; Max $5M; SBA forms 1919/1920 | 13 CFR Part 120; SOP 50 10 7 |
| SBA 504 | First lien ≤ 50% LTV; 10% equity required | 13 CFR Part 120 Subpart D |
| Consumer Personal | Max 43% DTI; Min FICO 600; Max $50K | Reg Z; ECOA |
| Auto | Max 125% LTV; Max 84-month term | Reg Z; ECOA |
| Credit Card Line | Max 40% DTI; Min FICO 620; Max $30K | Card Act; Reg Z |

---

## Fair Lending Controls

Three fair lending flags are detected by Python logic. **Any flag makes `fair_lending_review_required = True` and routes to Compliance Officer HITL — this cannot be bypassed by LLM or configuration.**

| Flag | Detection Logic | Regulatory Basis |
|------|----------------|-----------------|
| Geographic Flag | Census tract in FFIEC-flagged LMI / high-denial concentration area | FHA; CRA |
| Steering Flag | FHA routing for applicant who qualifies for lower-cost conventional | CFPB UDAAP; Reg B |
| Pricing Exception | Quoted rate > 150bps above risk-based pricing schedule | Reg B; ECOA |

HMDA and CRA eligibility are also determined automatically:
- **HMDA reportable:** Residential mortgage loans with property state
- **CRA eligible:** Loans in LMI geography or small business loans ≤ $1M

---

## Dashboard — 6 Tabs

| Tab | Purpose |
|-----|---------|
| **Application Queue** | Submit applications; load demo scenarios; pipeline status |
| **Underwriting Analysis** | Financial ratios, credit profile, risk score breakdown, HITL review panel |
| **Fair Lending Review** | ECOA/FHA flags, HMDA action taken, CRA eligibility, regulatory reference |
| **Credit Decision** | Credit memo, conditions letter, adverse action notice, SAR referral |
| **Loan Register** | All applications with HMDA tracking, fair lending flags, decision distribution |
| **Configuration** | SR 11-7 model governance, underwriting guidelines by loan type, delegation of authority |

---

## Regulatory Coverage

- **ECOA / Regulation B (12 CFR Part 1002)** — Fair lending, adverse action notice, credit score disclosure
- **Fair Housing Act (42 U.S.C. § 3601)** — Anti-discrimination in residential mortgage
- **HMDA (12 CFR Part 1003)** — LAR data collection, action taken codes
- **CRA (12 U.S.C. § 2901)** — LMI lending tracking
- **TILA / Regulation Z (12 CFR Part 1026)** — Loan structure documentation
- **BSA / OFAC (31 CFR Chapter X)** — OFAC screening, SAR referral, CIP
- **SR 11-7** — Model risk management for 5-factor scoring model
- **SBA SOP 50 10 7** — SBA 7(a) underwriting requirements
- **HUD Handbook 4000.1** — FHA mortgage underwriting
- **FNMA B3-6-02 / FHLMC 5306.1** — Conventional mortgage DTI/LTV guidelines
- **OCC 12 CFR Part 34** — Real estate lending standards

---

## Security

Security is embedded in the architecture, not bolted on:

- **No PII in audit trail:** `_mask_pii()` strips SSN and account number patterns from any text entering the audit trail
- **No raw PII in state:** Credit bureau data is reduced to derived metrics only (FICO score, DTI) — no raw report stored
- **OFAC cannot be bypassed:** `ofac_hit = True` is set by `credit_bureau_pull_node` and only read (never written) by downstream nodes — no LLM path can clear it
- **Fair lending cannot be waived:** Fair lending flags force HITL — no LLM call, no reviewer decision, no configuration change can bypass the compliance officer review gate
- **Input sanitization:** `_sanitize_text()` strips control characters and caps field lengths at intake — prevents prompt injection
- **Production AWS:** WAF + KMS envelope encryption + Macie PII detection + encrypted logs (no PII in CloudWatch)

---

## Quick Start

```bash
cd 08-credit-underwriting-agent
cp .env.example .env
# Add your OPENAI_API_KEY to .env

pip install -r requirements.txt
streamlit run app.py
# Dashboard: http://localhost:8508
```

**Run tests:**
```bash
pytest tests/ -v
```

**Docker:**
```bash
docker build -t credit-underwriting-agent .
docker run -p 8508:8508 --env-file .env credit-underwriting-agent
```

---

## Configuration

### Underwriting Guidelines (`data/fixtures/underwriting_guidelines.json`)
Per-loan-type policy thresholds: max DTI, min FICO, max LTV, min DSCR, required documentation. The `sr_11_7_model_governance` section documents the scoring model for examiner review.

### Applicant Profiles (`data/fixtures/applicant_profiles.json`)
4 sample applicants covering: APPROVE_WITH_CONDITIONS (good credit, minor collection), DECLINE (Chapter 7 < 2 years), REFER_TO_COMMITTEE (CRE, borderline DSCR), APPROVE (SBA 7(a), strong DSCR).

### Routing Matrix (`data/fixtures/routing_matrix.json`)
Delegation of authority: consumer underwriter, residential underwriter, senior underwriter, commercial underwriter, credit committee, compliance officer, BSA officer — with loan amount and risk tier constraints.

---

## ROI

**6-underwriter community bank, 150 loans/month:**

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Hours per residential application | 5.1 hrs | 0.28 hrs | 94% |
| Hours per commercial application | 6.5 hrs | 0.47 hrs | 93% |
| Annual underwriting hours | 10,440 hrs | 675 hrs | 9,765 hrs |
| Annual labor savings | — | — | **$1.55M** |
| ECOA/fair lending risk reduction | — | — | **$185K** |
| HMDA data quality | — | — | **$40K** |
| **Total annual net value** | | | **~$1.8M** |

**Payback period:** 8–10 weeks

See `docs/roi-analysis.md` for full analysis by institution profile and 3-year NPV ($4.7M–$8.5M).

---

## Suite Integration

Agent 08 connects to the broader FSI AI Agent Suite:

- **New business application → Agent 03 (KYC/CDD):** When Agent 08 receives a new commercial application, it triggers Agent 03 to initiate perpetual KYC monitoring for the new business relationship simultaneously with underwriting
- **OFAC match → Agent 01 (Financial Crime Investigation):** When Agent 08's credit bureau pull returns an OFAC hit, it cross-notifies Agent 01 to begin BSA investigation — the SAR referral is coordinated across both agents
- **Adverse action demographic data → Agent 06 (Regulatory Change Management):** HMDA LAR data feeds Agent 06's CRA and fair lending regulatory change monitoring — rule changes affecting HMDA reporting are automatically flagged

---

## Project Structure

```
08-credit-underwriting-agent/
├── agent/
│   ├── state.py           # CreditUnderwritingState TypedDict + Enums
│   ├── nodes.py           # 12 node functions + security utilities
│   ├── graph.py           # LangGraph StateGraph DAG
│   └── prompts.py         # LLM prompts (credit memo, adverse action, conditions)
├── data/
│   └── fixtures/
│       ├── applicant_profiles.json     # 4 sample applicant profiles with bureau data
│       ├── underwriting_guidelines.json # Per-loan-type thresholds + SR 11-7 governance
│       ├── routing_matrix.json          # Delegation of authority matrix
│       └── sample_applications.json    # 4 demo scenarios
├── docs/
│   ├── aws-deployment-guide.md         # Production AWS deployment with security
│   ├── regulatory-compliance.md        # ECOA, HMDA, BSA, SR 11-7 mapping
│   └── roi-analysis.md                 # ROI by institution profile, 3-year NPV
├── tests/
│   ├── test_nodes.py      # Unit tests (financial analysis, scoring, hard rules, security)
│   └── test_graph.py      # Integration tests (mocked LLM, HITL flows, audit trail)
├── app.py                 # Streamlit dashboard (port 8508)
├── Dockerfile
├── railway.toml
└── requirements.txt
```
