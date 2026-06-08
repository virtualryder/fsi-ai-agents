# Agent 06 — Regulatory Change Management Agent

AI-powered regulatory change management for financial institutions. Automates the intake, impact analysis, gap assessment, remediation planning, and stakeholder notification workflow for regulatory changes from FinCEN, OCC, Federal Reserve, FDIC, CFPB, SEC, FINRA, and other authorities.

---

## The Problem

A mid-sized bank's compliance team receives 300+ regulatory updates per year across all agencies. Each update requires:

1. Determining if the change applies to the institution
2. Identifying which policies, procedures, and controls need updating
3. Writing a gap analysis comparing the new requirement to current practice
4. Drafting a remediation plan with tasks, owners, and deadlines
5. Notifying business unit leaders of their obligations
6. Tracking remediation progress against the compliance deadline

Manual processing takes 8–40 hours per significant change. Backlogs accumulate. Examination findings cite the same unclosed gaps repeatedly.

**This agent automates steps 1–5 and provides real-time tracking for step 6.**

---

## Architecture

**12-node LangGraph StateGraph** processing regulatory changes from intake through remediation planning:

```
change_intake → source_validation → scope_determination → policy_mapping →
gap_analysis [LLM] → impact_scoring [Python] → routing_decision [Python] →

CRITICAL/HIGH → human_review_gate [HITL] → remediation_planning [LLM] →
                stakeholder_notification [LLM] → tracking_update → finalize

MEDIUM/LOW   → remediation_planning [LLM] → stakeholder_notification [LLM] →
                tracking_update → finalize
```

**LLM vs. Python boundary:**
| Decision | Who Makes It | Why |
|---------|------------|-----|
| Does this change apply? | Python + LLM analysis | Both needed |
| Which policies are in scope? | Python (registry lookup) | Deterministic |
| What are the gaps? | LLM (Claude/GPT-4o) | Analytical |
| Impact score (0–1) | Python (5-factor model) | SR 11-7 requirement |
| HITL required? | Python (tier threshold) | Deterministic |
| Remediation plan | LLM | Drafting task |
| Route to which owner? | Python (routing matrix) | Deterministic |

---

## Impact Scoring Model

Composite score 0.0–1.0 from 5 weighted components (SR 11-7 documented):

| Factor | Weight | Description |
|--------|--------|-------------|
| Authority Tier | 25% | Primary federal regulator vs. advisory body |
| Deadline Urgency | 25% | Days until effective date; blended with change type urgency |
| Scope Breadth | 20% | Number of business lines and products affected |
| Policy Depth | 15% | Number of policies requiring change + gap severity keywords |
| Remediation Complexity | 15% | Number of operational areas requiring update |

**Impact Tiers:**
- **CRITICAL** (≥ 0.85): Immediate action. CCO escalation. Mandatory HITL.
- **HIGH** (0.65–0.84): Significant policy changes. Mandatory HITL.
- **MEDIUM** (0.40–0.64): Policy amendments. Compliance owner notification.
- **LOW** (< 0.40): FAQ/clarification. Auto-document and notify.

**Hard overrides:**
- Enforcement actions → always at least HIGH + mandatory HITL
- Already-effective Tier 1 rule → CRITICAL regardless of other factors

---

## Dashboard — 6 Tabs

| Tab | Purpose |
|-----|---------|
| **Regulatory Feed** | Submit changes manually; browse change register with filters |
| **Impact Analysis** | Gap analysis narrative, score breakdown chart, policy mapping, HITL review panel |
| **Remediation Tracker** | Task list with status updates, progress bar, remediation plan narrative |
| **Policy Registry** | Institution policy inventory with regulatory citations and review status |
| **Audit Trail** | Append-only log of all workflow actions — examination evidence |
| **Configuration** | Regulatory sources, routing matrix, impact score thresholds |

---

## Supported Regulatory Sources

| Authority | Tier | Primary Domains |
|-----------|------|----------------|
| OCC | Tier 1 Federal Primary | BSA/AML, Safety & Soundness, Consumer, Technology |
| Federal Reserve | Tier 1 Federal Primary | BSA/AML, Capital, Consumer, Technology |
| FDIC | Tier 1 Federal Primary | BSA/AML, Capital, Consumer, Technology |
| CFPB | Tier 1 Federal Primary | Consumer, Fair Lending, Privacy, Fraud/Payments |
| FinCEN | Tier 2 Federal Secondary | BSA/AML, Cross-Border |
| SEC | Tier 2 Federal Secondary | Investment Products |
| FINRA | Tier 2 Self-Regulatory | Investment Products |
| FATF | Tier 4 International | BSA/AML (advisory) |

---

## Regulatory Coverage

This agent's workflow is designed to satisfy:

- **FFIEC BSA/AML Examination Manual** — regulatory change management program requirements
- **OCC Safety and Soundness Standards** (12 CFR Part 30, App. D) — change management
- **SR 11-7** — model risk management for the impact scoring model
- **FDIC Compliance Management System** — regulatory change identification and implementation

---

## Quick Start

```bash
cd 06-regulatory-change-agent
cp .env.example .env
# Add your OPENAI_API_KEY to .env

pip install -r requirements.txt
streamlit run app.py
# Dashboard: http://localhost:8506
```

**Run tests:**
```bash
pytest tests/ -v
```

**Docker:**
```bash
docker build -t reg-change-agent .
docker run -p 8506:8506 --env-file .env reg-change-agent
```

---

## Configuration

### Institution Profile (`.env`)
```
INSTITUTION_TYPE=Commercial Bank
INSTITUTION_CHARTER=State-chartered, Federal Reserve member
PRIMARY_REGULATOR=Federal Reserve / State Banking Department
```

### Regulatory Sources (`data/fixtures/regulatory_sources.json`)
Add/enable regulatory sources. Each source has a feed URL, authority tier, and polling frequency.

### Policy Registry (`data/fixtures/policy_registry.json`)
Load your institution's policy inventory. The agent maps regulatory changes to policies in this registry.

### Routing Matrix (`data/fixtures/routing_matrix.json`)
Configure which compliance role owns each regulatory domain. Drives notification targeting.

---

## ROI

**50-change per year baseline, 6 compliance analysts:**

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Hours per regulatory change (HIGH impact) | 32 hrs | 5 hrs | 27 hrs |
| Hours per regulatory change (MEDIUM impact) | 12 hrs | 2 hrs | 10 hrs |
| Annual compliance staff hours saved | 1,250 hrs | — | — |
| Cost at $95/hr (blended senior analyst) | — | — | **$1.3M/year** |
| Examination findings from missed changes | 3–5/year | Near-zero | **$150K–$500K** |
| **Total annual value** | | | **~$1.5M–$1.8M** |

**Payback period:** 10–14 weeks

See `docs/roi-analysis.md` for full analysis by institution size.

---

## Suite Integration

Agent 06 connects to the broader FSI AI Agent Suite:

- When Agent 06 identifies a BSA/AML regulatory change requiring program updates → notifies Agent 01 (Financial Crime Investigation) and Agent 02 (TMS Enhancement) owners that model thresholds may need recalibration
- When a new privacy regulation affects data handling → coordinates with Agent 03 (KYC/CDD) compliance owner to update EDD data governance procedures
- When a Reg BI change affects suitability documentation → coordinates with Agent 05 (Wealth RM Copilot) compliance owner

---

## Project Structure

```
06-regulatory-change-agent/
├── agent/
│   ├── state.py           # ChangeManagementState TypedDict + Enums
│   ├── nodes.py           # 12 node functions
│   ├── graph.py           # LangGraph StateGraph DAG
│   └── prompts.py         # System prompts (gap analysis, remediation, notifications)
├── data/
│   └── fixtures/
│       ├── regulatory_sources.json   # 9 regulatory authorities
│       ├── policy_registry.json      # 12 sample institution policies
│       ├── routing_matrix.json       # Domain → compliance owner mapping
│       └── sample_changes.json       # 3 sample regulatory changes for demo
├── docs/
│   ├── aws-deployment-guide.md
│   ├── regulatory-compliance.md
│   └── roi-analysis.md
├── tests/
│   ├── test_nodes.py      # Unit tests (scoring, routing, scope — no LLM)
│   └── test_graph.py      # Integration tests (mocked LLM)
├── app.py                 # Streamlit dashboard (port 8506)
├── Dockerfile
├── railway.toml
└── requirements.txt
```
