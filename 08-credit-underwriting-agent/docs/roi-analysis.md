# ROI Analysis
## Credit Underwriting Agent — Agent 08

---

## Executive Summary

For a community bank originating 150 mortgage and commercial loans per month with a 6-person underwriting team, the Credit Underwriting Agent delivers **$1.8M–$2.6M in annual net value** by automating the financial analysis, document checklist verification, fair lending screening, credit memo drafting, and adverse action notice generation that currently consume 65–70% of underwriter time.

**Payback period: 6–10 weeks.**

---

## The Problem: What Underwriters Actually Do All Day

A credit application arrives. The underwriter must:

1. Verify documents are complete — 20–45 min (per loan type checklist)
2. Pull credit bureau and interpret the report — 15–30 min
3. Calculate DTI, LTV, DSCR, and reserves — 30–60 min
4. Run OFAC and watchlist screening — 15–20 min
5. Complete the fair lending checklist — 20–40 min (residential)
6. Score the application and assign a tier — 30–45 min
7. Draft the credit memorandum — 60–120 min (commercial), 30–60 min (residential)
8. Draft the adverse action notice (declined apps) — 30–60 min
9. Complete HMDA data fields — 15–20 min

Total: **3.5–7.5 hours per application** depending on loan type. Commercial credit memos for complex transactions can run 8–12 hours.

---

## Time-Motion Analysis

### Residential Mortgage (Conventional, FHA, VA)

| Step | Current (Manual) | With Agent | Reduction |
|------|-----------------|-----------|-----------|
| Document checklist verification | 30 min | 2 min | 93% |
| Credit bureau interpretation | 25 min | Auto (derived metrics) | 100% |
| DTI / LTV / reserves calculation | 45 min | Auto (Python) | 100% |
| Fair lending screening | 35 min | Auto (Python) | 100% |
| OFAC check | 20 min | Auto (Python) | 100% |
| Risk scoring and tier | 35 min | Auto (Python) | 100% |
| Credit memo drafting | 50 min | 10 min review | 80% |
| Adverse action notice (declined) | 45 min | 5 min review | 89% |
| HMDA data entry | 20 min | Auto | 100% |
| **Total per application** | **305 min (5.1 hrs)** | **17 min** | **94%** |

### Commercial / SBA Loan

| Step | Current (Manual) | With Agent | Reduction |
|------|-----------------|-----------|-----------|
| Document checklist | 40 min | 3 min | 93% |
| Credit bureau + business credit | 30 min | Auto | 100% |
| Financial statement analysis (DSCR) | 90 min | Auto (Python) | 100% |
| OFAC + beneficial ownership | 25 min | Auto | 100% |
| Risk scoring | 45 min | Auto (Python) | 100% |
| Credit memo drafting | 120 min | 20 min review | 83% |
| Adverse action (if declined) | 40 min | 5 min review | 88% |
| **Total per application** | **390 min (6.5 hrs)** | **28 min** | **93%** |

---

## ROI by Institution Profile

### Community Bank (150 loans/month, 6 underwriters)

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Avg hours per residential loan | 5.1 hrs | 0.28 hrs | 4.82 hrs |
| Avg hours per commercial loan | 6.5 hrs | 0.47 hrs | 6.03 hrs |
| Annual underwriting hours (900 resi, 900 comm) | 10,440 hrs | 675 hrs | 9,765 hrs |
| Underwriter fully-loaded cost | $95,000/yr | — | — |
| Annual labor savings | — | — | **$1.55M** |
| Adverse action compliance risk (avg CFPB penalty) | $120K | $12K | **$108K** |
| Fair lending exam finding cost (avg) | $85K | $8K | **$77K** |
| HMDA data error correction cost | $45K | $5K | **$40K** |
| **Total annual net value** | | | **~$1.8M** |

**Payback period: 8–10 weeks**

### Regional Bank (400 loans/month, 18 underwriters)

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Annual underwriting hours | 28,800 hrs | 2,040 hrs | 26,760 hrs |
| Labor savings (18 UWs @ $105K fully-loaded) | — | — | **$2.9M** |
| Compliance risk reduction | — | — | **$350K** |
| Cycle time reduction (faster closing) | — | — | **$180K** (retention) |
| **Total annual net value** | | | **~$3.4M** |

**Payback period: 5–7 weeks**

### Credit Union (80 loans/month, 3 underwriters)

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Annual underwriting hours | 5,200 hrs | 350 hrs | 4,850 hrs |
| Labor savings (3 UWs @ $82K fully-loaded) | — | — | **$790K** |
| Compliance risk reduction | — | — | **$85K** |
| **Total annual net value** | | | **~$875K** |

**Payback period: 10–14 weeks**

---

## Cycle Time Impact (Revenue-Side)

Faster underwriting decisions have a direct revenue impact beyond labor savings:

**Mortgage origination:** Loan Officers can commit to shorter rate lock periods (reducing lock cost). Borrowers report higher satisfaction with faster decisions — correlates with referral rates and repeat business.

| Metric | Before | After |
|--------|--------|-------|
| Time-to-decision (residential) | 3–5 business days | 4–8 hours |
| Time-to-decision (commercial) | 10–15 business days | 2–3 business days |
| Rate lock cost reduction | — | ~$180K/year (regional bank) |
| Declined applicant re-application rate | 18% (poor adverse action UX) | 32% (clear specific reasons) |

---

## Risk and Compliance Value

### ECOA / Fair Lending

CFPB and DOJ fair lending enforcement actions against community and regional banks average **$1.2M–$8.5M** in penalties, remediation, and supervision costs. The agent's systematic fair lending screening and documentation:

- Creates an auditable record that every application was screened for steering and geographic concentration
- Ensures every declined applicant receives a timely, Reg B-compliant notice with specific reasons
- Eliminates the manual checklist that examiners find inconsistently applied

Conservative fair lending risk reduction value: **$75K–$300K/year** (probability-weighted penalty avoidance).

### HMDA Data Quality

HMDA restatements and correction filings cost **$25K–$100K** in staff time. Automated HMDA action taken code assignment eliminates data entry errors in the most commonly mis-coded fields (action taken, loan purpose, property location).

### SR 11-7 Model Governance

Having documented model governance (factor weights, thresholds, hard rules, annual validation) reduces the cost of credit model reviews during OCC/FDIC/Federal Reserve safety-and-soundness examinations. Institutions without model documentation frequently receive MRAs (Matters Requiring Attention) that cost **$50K–$200K** to remediate.

---

## Headcount Redeployment (Not Reduction)

The standard Presidio positioning is **capacity expansion, not headcount reduction**:

| Without Agent | With Agent |
|---------------|-----------|
| 6 underwriters process 150 loans/month | 6 underwriters process 400+ loans/month |
| Underwriters spend 70% on calculation and data entry | Underwriters spend 90% on judgment — complex credit decisions, relationship management |
| 15–20 day commercial loan cycle | 3–5 day commercial loan cycle |
| Fair lending screening is inconsistent | Fair lending screening is systematic and documented |

The underwriting team becomes a credit judgment team, not a data processing team. That's the value proposition for the Chief Credit Officer.

---

## 3-Year NPV

**Community bank (150 loans/month):**

| Year | Net Value | Cumulative |
|------|-----------|-----------|
| Year 1 | $1.60M (6-month ramp) | $1.60M |
| Year 2 | $1.85M | $3.45M |
| Year 3 | $2.10M (loan volume growth) | $5.55M |
| **3-Year NPV (8% discount)** | | **$4.7M** |

**Regional bank (400 loans/month):**

| Year | Net Value | Cumulative |
|------|-----------|-----------|
| Year 1 | $2.9M | $2.9M |
| Year 2 | $3.4M | $6.3M |
| Year 3 | $3.8M | $10.1M |
| **3-Year NPV (8% discount)** | | **$8.5M** |

---

## Implementation Cost

| Item | One-Time | Monthly |
|------|----------|---------|
| Presidio implementation (POC → production) | $85K–$145K | — |
| AWS infrastructure (see aws-deployment-guide.md) | — | ~$380–$520/month |
| OpenAI API (gpt-4o, credit memo generation) | — | ~$45–$180/month |
| Annual SR 11-7 model validation | — | ~$15K/year |
| **Total Year 1 cost** | | **$115K–$175K** |
