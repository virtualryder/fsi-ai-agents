# Agent 10 — Payments Compliance Agent

## What This Agent Does

The Payments Compliance Agent is a 12-node LangGraph workflow that automates the most
labor-intensive steps in payments compliance operations: Regulation E dispute processing,
Nacha return code validation, OFAC/FATF sanctions screening, SLA deadline management,
and compliance risk scoring.

Every compliance determination (OFAC match, Reg E applicability, provisional credit
obligation, SLA deadline, risk tier) is computed by deterministic Python. The LLM is
used only for narrative analysis that assists — but does not replace — the human reviewer's
judgment.

**The core problem it solves:** A payments compliance analyst today spends 143 minutes
per disputed ACH transaction manually looking up return codes, calculating SLA deadlines,
checking country codes, drafting Reg E notices, and writing compliance memos. With Agent 10,
that same workflow takes 35 seconds of automated processing and 12 minutes of focused human
review — a 92% time reduction per dispute.

---

## Who Should Use This Agent

| Role | What They Submit | What They Get |
|------|-----------------|---------------|
| Dispute Resolution Analysts | ACH return code events, customer dispute claims | Reg E assessment, SLA deadlines, provisional credit calculation, HITL queue |
| BSA Officers | ACH/wire events with OFAC matches | Sanctions hold confirmation, OFAC report SLA, SAR candidate flag |
| Wire Operations | International wire transactions | FATF country screening, high-risk flag, enhanced due diligence trigger |
| Payments Operations | NOC notifications (C01-C09) | Auto-resolved originator notification with correction details |
| Compliance Managers | Compliance event review | 5-factor risk score, regulatory citations, reviewer-ready narratives |

---

## How It Fits in the Suite

Agent 10 is the **payments regulatory layer** for the FSI AI Suite. It receives structured
payment data and produces compliance decisions, regulatory notices, and audit-ready records.

```
Agent 09 — Document Intelligence
    │  (SWIFT MT103/MT202 → structured JSON)
    │  (Wire instructions → structured JSON)
    ▼
Agent 10 — Payments Compliance ◄── Direct payment event submission
    │
    ├──► Agent 01 — Financial Crime Investigation (OFAC hits, SAR candidates)
    ├──► Core Banking System (provisional credit issuance)
    ├──► Customer (Reg E written notice — 12 CFR 1005.11(d))
    └──► Compliance Case Management (ServiceNow, Salesforce FSC)
```

**Recommended deployment order:** Deploy Agent 09 before Agent 10. Agent 09's structured
SWIFT and wire instruction outputs feed directly into Agent 10's payment intake — eliminating
the manual data re-keying step for international wires.

---

## Regulatory Coverage

| Regulation | Key Obligation Handled |
|-----------|----------------------|
| **Reg E (12 CFR Part 1005)** | Applicability check, SLA computation, provisional credit, written notice (1005.11(d)) |
| **Nacha Operating Rules** | Return window validation (R01-R77), unauthorized returns, NOC processing (C01-C09), late-return flagging |
| **OFAC (31 CFR Parts 500-598)** | Sanctioned-country detection, hard CRITICAL override, blocking report SLA (501.604) |
| **BSA / FinCEN (31 CFR 1020)** | SAR candidate flagging ($5K threshold), CTR detection ($10K), 5-year audit retention |
| **FATF Recommendations** | High-risk jurisdiction screening, enhanced due diligence trigger |
| **CFPB Prepaid Rule** | Reg E protections for prepaid card disputes |
| **UCC Article 4A** | Wire fraud inapplicability noted, UCC 4A-202/203 liability analysis flagged |
| **GLBA Safeguards** | Account masking at intake, no PII in checkpoint store, KMS encryption in production |
| **SR 11-7** | 5-factor scoring documented, LLM boundary explicit, mandatory human override |

---

## 12-Node Processing Pipeline

```
START
 │
 ▼
[1] payment_intake          — Validate, SHA-256 hash, mask accounts to ****{last4}
 │
 ▼
[2] sanctions_screening     — OFAC SDN country check, FATF high-risk, PEP (Python only)
 │
 ▼
[3] nacha_validation        — Return window check, NOC C1-C9, CTR threshold, late-return flag
 │
 ▼
[4] reg_e_assessment        — Reg E applicability, SLA deadlines, provisional credit obligation
 │
 ▼
[5] dispute_analysis        — LLM: Customer claim narrative analysis (masked input)
 │
 ▼
[6] compliance_scoring      — Python: 5-factor composite, OFAC hard override to CRITICAL
 │
 ▼
[7] compliance_analysis     — LLM: Reviewer narrative synthesis, regulatory citations
 │
 ▼
[8] routing_decision        — Python: Target team, HITL flag, resolution type

         ┌──────────────────────────────────────────────────────────────┐
         │   Conditional Split (_route_after_routing_decision)          │
         └──────────────────────────────────────────────────────────────┘
              │                                    │
      [HITL required]                      [Auto-resolve]
              │                                    │
              ▼                                    │
[9] human_review_gate ←── PAUSE           [10] resolution_drafting
       │                                          │
  Reviewer submits                         [11] output_packaging
  APPROVE / OVERRIDE / ESCALATE / REJECT          │
              │                            [12] audit_finalize → END
    ──────────────────────────
    │                        │
APPROVE / OVERRIDE      ESCALATE / REJECT
    │                        │
[10] resolution_drafting  [12] audit_finalize → END
[11] output_packaging
[12] audit_finalize → END
```

---

## LLM vs. Python Boundary (SR 11-7 Design Principle)

This distinction is fundamental. The LLM is an external API with non-deterministic outputs.
All regulatory controls must be in deterministic Python.

| Task | LLM | Python |
|------|-----|--------|
| OFAC / FATF sanctions screening | | ✅ |
| Reg E applicability determination | | ✅ |
| SLA deadline computation | | ✅ |
| Provisional credit obligation | | ✅ |
| Risk score / risk tier calculation | | ✅ |
| Nacha return window validation | | ✅ |
| CTR / SAR threshold detection | | ✅ |
| Routing destination selection | | ✅ |
| HITL trigger decisions | | ✅ |
| Audit trail recording | | ✅ |
| Customer claim narrative analysis | ✅ | |
| Compliance narrative for reviewer | ✅ | |
| Customer notice drafting (Reg E) | ✅ | |
| Internal resolution memo drafting | ✅ | |

---

## Security Architecture

### 1. Account Number Masking at Intake
Full account numbers are masked to `****{last4}` in `payment_intake_node` before any
subsequent processing, state transition, or LLM API call. Full account numbers never
appear in the LangGraph checkpoint database.

### 2. OFAC Screening is Python-Only
`OFAC_SANCTIONED_COUNTRY_CODES` and `FATF_HIGH_RISK_COUNTRIES` are Python `frozenset`
constants defined at module load time. No LLM response can alter them. `frozenset.add()`
raises `TypeError` — immutability is enforced by Python itself, not application logic.

### 3. ALWAYS_HITL_PAYMENT_EVENTS frozenset
```python
ALWAYS_HITL_PAYMENT_EVENTS = frozenset({
    "OFAC_HOLD",
    "UNAUTHORIZED_WIRE",
    "SAR_CANDIDATE",
    "CTR_THRESHOLD",
    "HIGH_RISK_COUNTRY_WIRE",
    "LATE_RETURN_DISPUTE",
})
```
Immutable at runtime. Tests explicitly verify `frozenset.add()` raises `TypeError`.

### 4. Routing is a Python Constant
`TARGET_TEAMS` dict in `nodes.py` is set at module load time. Prompt injection in
customer claim narratives cannot redirect OFAC hits to AUTO_RESOLVE. Routing is
determined by reading Python-computed flags — not LLM text.

### 5. HITL at Framework Level
`interrupt_before=["human_review_gate"]` is a LangGraph framework instruction, not an
application `if` statement. The graph physically cannot execute `human_review_gate`
or any subsequent node without a human reviewer submitting a decision through the
checkpointer API.

### 6. Append-Only Audit Trail
Every node adds entries via `list(current) + [new_entry]`. State transitions replace
the entire list; prior entries are read-only. Tests verify no modification of prior entries.

---

## HITL Triggers

All human review decisions are Python-determined:

| Trigger | Regulatory Basis |
|---------|-----------------|
| OFAC sanctions match | OFAC regulations — human authorization required |
| SAR candidate | BSA — qualified BSA officer must determine SAR |
| CTR threshold ($10K+) | 31 CFR 1010.311 — verification before filing |
| High-risk country wire | FATF guidance — enhanced due diligence |
| Unauthorized return (R07/R10/R29) | Reg E — documented human review required |
| Late return flag | Nacha rule violation — legal review required |
| Amount > $50,000 | Institution escalation policy |
| Risk tier CRITICAL or HIGH | SR 11-7 model governance |
| SLA breach or ≤5 days remaining | Compliance deadline management |

---

## Quick Start

### Requirements
- Python 3.11+
- OpenAI API key (optional — app runs in demo mode without it)

### Installation

```bash
# Clone
git clone https://github.com/virtualryder/fsi-ai-agents.git
cd fsi-ai-agents/10-payments-compliance-agent

# Install
pip install -r requirements.txt

# Configure (add OPENAI_API_KEY)
cp .env.example .env

# Run (port 8510)
streamlit run app.py --server.port 8510
```

### Demo Mode (No API Key Required)
Without `OPENAI_API_KEY`, the app uses 4 pre-computed scenarios:

| Demo | Regulatory Path | Key Concepts |
|------|----------------|--------------|
| ACH Unauthorized Return | Consumer dispute, R10 | Reg E, provisional credit, HITL |
| OFAC Wire Hold | Iran sanctions match | OFAC hard block, BSA, SAR |
| Business Email Compromise | Wire fraud | UCC Article 4A, IC3, commercial |
| ACH NOC Processing | Administrative C01 | Auto-resolve, LOW risk |

### Run Tests
```bash
pytest tests/ -v
```

Tests cover:
- frozenset immutability (ALWAYS_HITL, OFAC, FATF, unauthorized codes)
- Account masking (full numbers absent after intake)
- OFAC hard override (CRITICAL tier regardless of composite score)
- Nacha return windows (R10=60 days, R01=2 days)
- Reg E inapplicability for wires
- CTR threshold detection ($10K)
- SAR candidate thresholds ($5K)
- HITL routing functions (fail-safe defaults for unknown decisions)
- Audit trail append-only behavior
- Full pipeline integration with mocked LLM

---

## Project Structure

```
10-payments-compliance-agent/
├── agent/
│   ├── __init__.py
│   ├── state.py          — PaymentsComplianceState TypedDict, enums, SLAType
│   ├── prompts.py        — LLM prompt templates (4 prompts: dispute, compliance, notice, memo)
│   ├── nodes.py          — 12 node functions, Python constants, compliance logic
│   └── graph.py          — LangGraph DAG assembly, routing functions, factory functions
├── data/
│   └── fixtures/
│       ├── payment_scenarios.json      — 4 demo scenarios (pre-computed outputs)
│       ├── return_code_reference.json  — Complete Nacha return code + NOC reference
│       └── routing_matrix.json         — Team routing rules, HITL triggers, risk tiers
├── docs/
│   ├── aws-deployment-guide.md        — 12-step production deployment, security rationale
│   ├── regulatory-compliance.md       — Reg E, Nacha, OFAC, BSA, FATF compliance analysis
│   └── roi-analysis.md                — $1.8M–$2.6M annual value, 3-week payback
├── tests/
│   ├── __init__.py
│   ├── test_nodes.py     — 50+ unit tests (security + compliance logic)
│   └── test_graph.py     — Integration tests (routing, HITL, full pipeline)
├── app.py                — Streamlit dashboard (6 tabs, port 8510)
├── Dockerfile            — Multi-stage build, non-root user, read-only filesystem
├── railway.toml          — Railway.app deployment configuration
├── requirements.txt      — Pinned Python dependencies
└── .env.example          — Environment variable template
```

---

## Related Agents

Agent 10 is the **payments regulatory processing layer** in the FSI AI Suite.

**Feeds from:**
- **[Agent 09 — Document Intelligence](../09-document-intelligence-agent):**
  Provides structured SWIFT MT103/MT202, wire instructions, and payment documents
  as JSON inputs to Agent 10's payment intake node

**Feeds to / works alongside:**
- **[Agent 01 — Financial Crime Investigation](../01-financial-crime-investigation):**
  OFAC hits and SAR candidates from Agent 10 pass to Agent 01's AML investigation workflow
- **[Agent 04 — Fraud Detection](../04-fraud-detection-agent):**
  BEC fraud and account takeover detections from Agent 04 trigger Reg E dispute
  processing in Agent 10

**Related suite documentation:**
- `SOLUTION-FIELD-GUIDE.md` (root) — Sales positioning, buyer personas, demo flows
- `docs/SUITE-ARCHITECTURE.md` (root) — Full suite architecture and data flow

---

## Getting Help

See the **About** tab in the Streamlit dashboard for detailed explanations of the
security architecture, regulatory coverage, and getting started guide — written for
compliance officers and security teams.

For issues and feature requests: [github.com/virtualryder/fsi-ai-agents/issues](https://github.com/virtualryder/fsi-ai-agents/issues)
