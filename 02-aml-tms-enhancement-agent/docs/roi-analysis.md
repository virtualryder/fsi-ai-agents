# ROI Analysis: AML/TMS Enhancement Agent
## Business Case for AI-Powered False Positive Reduction

---

## Executive Summary

A mid-sized bank with 10 AML analysts reviewing 500 alerts per day at a 90% false positive rate can expect **$3.8M–$4.2M in annual labor savings** from deploying the TMS Enhancement Agent. Payback occurs within **6–8 weeks** of go-live — faster than any other agent in the suite — because the savings are immediate and measurable from day one.

---

## 1. The False Positive Problem

### Industry Benchmarks

| Metric | Industry Average | Source |
|--------|-----------------|--------|
| TMS alert false positive rate | 85-95% | FinCEN SAR Activity Review; ACAMS surveys |
| Analyst time per alert review | 45-90 minutes | KPMG AML Benchmark Study 2023 |
| % of analyst time on false positives | 60-75% | Deloitte Financial Crime Survey 2023 |
| Annual AML compliance cost (US banks) | $25.3 billion | LexisNexis True Cost of AML 2023 |
| Alert volume growth (YoY) | 20-30% | NICE Actimize AML Trends 2024 |

### Why False Positive Rates Are This High

Modern TMS systems are tuned for recall — deliberately calibrated to catch every possible suspicious transaction at the cost of precision. The FFIEC Examination Manual supports this approach: "overly conservative tuning" is less problematic than under-reporting. The result is that 85-95% of analyst time goes to reviewing transactions that are not suspicious.

This is not a TMS failure. It is the intended design of transaction monitoring — and it creates the productivity problem this agent solves.

---

## 2. Analyst Cost Model

### Fully Loaded Annual Cost per AML Analyst

| Cost Component | Annual Amount |
|----------------|--------------|
| Base salary (mid-level AML Analyst) | $80,000 |
| Benefits (30% loading) | $24,000 |
| Overhead (office, tools, training) | $15,000 |
| Management/supervision (20%) | $23,800 |
| **Total fully loaded annual cost** | **$142,800** |
| **Effective hourly rate (2,000 hrs/year)** | **$71.40/hour** |

CAMS-certified senior analysts: $120,000 base → **$107/hour blended**

---

## 3. Time-Motion Study: Alert Review Workflow

### Current Manual Alert Review (Before AI)

| Step | Time per Alert |
|------|---------------|
| Open alert, review TMS record | 5 min |
| Pull customer profile from core banking | 8 min |
| Review transaction history | 10 min |
| Check customer risk tier and notes | 5 min |
| Apply judgment: FP or investigate? | 10 min |
| Document disposition and close | 7 min |
| **Total per alert** | **~45 minutes** |

### AI-Assisted Alert Review (After Deployment)

| Step | AI Processing | Human Review | Reduction |
|------|-------------|-------------|-----------|
| Alert triage and scoring | 8-12 seconds | — | 100% (SUPPRESS cases) |
| Review suppressed alert + narrative | — | 2 min | 96% |
| Review pass-through alert | — | 15 min | 67% |
| Review escalated alert | — | 5 min (hand-off) | 89% |
| **Effective time per queued alert** | — | **~15 min** | **67%** |
| **With ~50% queue reduction** | — | **~7.5 min effective** | **83%** |

Double savings: fewer alerts reach analysts (queue reduction) AND each alert that does reach analysts is pre-scored with assembled context (faster disposition).

---

## 4. Direct Cost Savings Analysis

### Scenario: 10-Analyst Team, 500 Alerts/Day, 90% FP Rate

**Before:**
- 500 alerts/day × 45 min = 375 analyst-hours/day
- 10 analysts × 7.5 productive hrs = 75 available hours
- Backlog accumulation and overtime are the current reality

**After:**
- ~50% queue reduction → 250 alerts reach analysts
- Each alert: ~15 min with AI-assembled context
- 250 alerts × 15 min = 62.5 analyst-hours/day
- 10 analysts handle workload with capacity to spare

### Annual Savings Calculation

| Metric | Before AI | After AI | Annual Impact |
|--------|----------|----------|--------------|
| Daily analyst-hours on alerts | 375 hrs | 62.5 hrs | 312.5 hrs/day saved |
| Annual analyst-hours saved | — | — | 78,125 hrs/year |
| Cost at $71.40/hour | — | — | $5.58M gross |
| Less: AWS infrastructure | — | — | ($128K/yr) |
| Less: BSA Officer 90-day review | — | — | (~$50K/yr) |
| **Gross savings** | | | **~$5.4M** |

Conservative realization rate (70-75% — analysts redirect to higher-value work):

**Realizable annual savings: $3.8M–$4.2M**

---

## 5. Savings by Institution Size

### Community Bank (3 analysts, 150 alerts/day, 88% FP rate)

| Metric | Value |
|--------|-------|
| Daily FP alerts suppressed (~50%) | 66 removed from queue |
| Annual analyst-hours saved | 12,500 hrs |
| Annual savings at $71.40/hr | $893,000 |
| Less infrastructure | ($64K) |
| **Net annual savings** | **~$829,000** |
| **Payback period** | **~8 weeks** |

### Regional Bank (10 analysts, 500 alerts/day, 90% FP rate)

| Metric | Value |
|--------|-------|
| Daily FP alerts suppressed (~50%) | 225 removed from queue |
| Annual analyst-hours saved | 56,250 hrs |
| Annual savings at $71.40/hr | $4.02M |
| Less infrastructure | ($128K) |
| **Net annual savings** | **~$3.9M** |
| **Payback period** | **~6 weeks** |

### Regional Bank (15 analysts, 800 alerts/day, 92% FP rate)

| Metric | Value |
|--------|-------|
| Daily FP alerts suppressed (~50%) | 368 removed from queue |
| Annual analyst-hours saved | 69,000 hrs |
| Annual savings at $75/hr (blended senior) | $5.18M |
| Less infrastructure | ($154K) |
| **Net annual savings** | **~$5.0M** |
| **Payback period** | **~5 weeks** |

### Credit Union (2 analysts, 80 alerts/day, 85% FP rate)

| Metric | Value |
|--------|-------|
| Daily FP alerts suppressed (~50%) | 34 removed from queue |
| Annual analyst-hours saved | 6,250 hrs |
| Annual savings at $68/hr | $425,000 |
| Less infrastructure | ($51K) |
| **Net annual savings** | **~$374,000** |
| **Payback period** | **~10 weeks** |

---

## 6. Investment and Payback Analysis

### Platform Investment

| Cost Item | One-Time | Annual |
|-----------|---------|--------|
| Implementation and TMS integration | $75,000–$200,000 | — |
| SR 11-7 model validation | $30,000–$75,000 | $15,000 |
| Training (BSA team + analysts) | $10,000 | $5,000 |
| AWS infrastructure | — | $64,000–$154,000 |
| Ongoing support | — | $25,000–$50,000 |
| **Year 1 total (10-analyst bank)** | **~$200,000** | **~$200,000** |

### Payback Period Summary

| Institution | Annual Savings | Year 1 Investment | Payback |
|-------------|--------------|-------------------|---------|
| Community Bank (3 analysts) | $829K | $225K | **~8 weeks** |
| Regional Bank (10 analysts) | $3.9M | $400K | **~6 weeks** |
| Regional Bank (15 analysts) | $5.0M | $500K | **~5 weeks** |
| Credit Union (2 analysts) | $374K | $150K | **~10 weeks** |

---

## 7. 3-Year NPV Analysis (10-Analyst Regional Bank)

Assumptions: 8% discount rate · 20% YoY alert volume growth · 4% analyst cost growth

| Year | Savings | Investment | Net Cash Flow | PV (8%) |
|------|---------|------------|--------------|---------|
| 1 | $3,900,000 | $400,000 | $3,500,000 | $3,240,741 |
| 2 | $4,680,000 | $215,000 | $4,465,000 | $3,826,474 |
| 3 | $5,616,000 | $225,000 | $5,391,000 | $4,279,166 |
| **Total** | **$14,196,000** | **$840,000** | **$13,356,000** | **$11,346,381** |

**3-Year NPV: $11.3M**

---

## 8. Sensitivity Analysis

| Scenario | Suppression Rate | Annual Savings | Payback |
|----------|-----------------|---------------|---------|
| Conservative | 40% suppressed | $2.4M | 10 wks |
| Base Case | 50% suppressed | $3.9M | 6 wks |
| Optimistic | 60% suppressed | $5.1M | 4 wks |

Conservative institutions can start with a high suppress threshold (e.g., 92% FP confidence required) and lower it as confidence builds. The BSA Officer Threshold Configuration tab allows in-production calibration without redeployment.

---

## 9. Suite Compounding Effect

Agent 02 + Agent 01 (Financial Crime Investigation) compound ROI:

- Agent 02 cuts queue 50% — fewer alerts reach investigators
- Agent 02 escalates the top 15% highest-risk alerts as HIGH priority to Agent 01
- Agent 01 investigators work only the right 15%, not a random 50%
- Combined annual savings for a 10-analyst team with 1,000 SARs/year: **~$8.2M**

---

## 10. Intangible Benefits

1. **Analyst retention:** AML turnover costs $30K–$60K per departure. Analysts working genuine investigations, not noise, stay longer.

2. **Detection quality:** With half the volume, analysts spend more time per true positive. SAR narrative quality improves. Examination findings decrease.

3. **Regulatory posture:** A documented, auditable, BSA Officer-reviewed suppression program signals rigor to examiners — the opposite of a black box.

4. **Scalability:** Alert volume grows 20-30% annually. Without Agent 02, headcount must grow proportionally. With Agent 02, the system absorbs that growth before it reaches analysts.

5. **Faster SAR escalation:** High-confidence suspicious alerts (FP ≤ 15%) are forwarded to investigators in real time — not buried in a 500-alert queue — reducing 30-day deadline exposure.
