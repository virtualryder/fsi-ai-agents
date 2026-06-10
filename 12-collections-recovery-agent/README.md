# Agent 12 — Collections & Recovery Agent

**FSI AI Suite · FDCPA/Reg F/SCRA-Compliant Debt Collections Automation**

Agent 12 automates the debt collections decision pipeline — FDCPA contact compliance,
Regulation F enforcement, SCRA/bankruptcy detection, SOL computation, payment plan
optimization, and settlement offer generation — while enforcing mandatory human-in-the-loop
review for all high-risk regulatory conditions through a Python frozenset and LangGraph
interrupt mechanism that the LLM cannot bypass.

---

## What Agent 12 Does

| Function | Implementation | Regulatory Basis |
|----------|---------------|-----------------|
| Contact time check (8am–9pm local) | Python (pytz) | FDCPA § 805(a)(1) |
| Reg F 7-in-7 call limit enforcement | Python (integer) | 12 CFR 1006.14(b) |
| SCRA active military detection | Python (boolean) | 50 U.S.C. § 3937 |
| Bankruptcy automatic stay detection | Python (boolean) | 11 U.S.C. § 362 |
| SOL computation (50 states + DC) | Python (dict lookup) | State law |
| Collectability scoring (5-factor) | Python (weighted arithmetic) | SR 11-7 |
| Payment plan options | Python (balance ÷ term) | FDCPA § 808 |
| Settlement tier authorization | Python (frozenset constants) | Internal policy |
| HITL condition detection (9 conditions) | Python (frozenset membership) | ALWAYS_HITL_CONDITIONS |
| HITL routing (fail-safe `is False`) | Python (identity check) | Fail-safe design |
| Medical debt $500 threshold | Python (numeric comparison) | CFPB 2025 rule |
| IRS 1099-C threshold (≥$600) | Python (numeric comparison) | 26 U.S.C. § 6050P |
| Mini-Miranda injection | Python (verbatim string) | FDCPA § 807(11) |
| Validation notice injection | Python (verbatim string) | FDCPA § 809 |
| Hardship assessment narrative | LLM (GPT-4o) | Narrative only |
| Collections strategy narrative | LLM (GPT-4o) | Narrative only |
| Collection letter body | LLM (GPT-4o) | Narrative only — disclosures Python-injected |
| Audit trail | Python (append-only) | FCRA / FDCPA |

---

## 12-Node Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  1. debt_intake           PII masking (ACCT-****{last4}) · FDCPA flag        │
│  2. fdcpa_compliance_check  pytz time check · Reg F 7-in-7 · C&D · dispute  │
│  3. scra_bankruptcy_check  SCRA flag · bankruptcy stay · SOL 50-state matrix  │
│  4. consumer_profile       [LLM] Hardship narrative · plan eligibility       │
│  5. debt_validation        Days delinquent · FCRA · medical_debt · SOL       │
│  6. payment_plan_optimizer  Collectability score · payment plans · settlement │
│  7. collections_strategy   [LLM] Supervisor strategy narrative               │
│  8. risk_scoring           ALWAYS_HITL_CONDITIONS frozenset check            │
│  9. routing_decision       FDCPA violations force HITL · is False fail-safe  │
│       │                                                                      │
│       ├──[HITL]──▶ 10. human_review_gate   interrupt_before · 6 decisions   │
│       │                                                                      │
│       └──[auto]──▶ 11. communication_drafting  [LLM] + Python disclosures   │
│                    12. audit_finalize  Append-only · S3 Object Lock 7-yr     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 9 HITL Conditions — ALWAYS_HITL_CONDITIONS frozenset

```python
ALWAYS_HITL_CONDITIONS = frozenset({
    "SCRA_DETECTED",             # Active military — SCRA 6% rate cap
    "BANKRUPTCY_STAY_DETECTED",  # Automatic stay — ALL collection stops
    "DISPUTE_RECEIVED",          # Debt disputed — 30-day collection hold
    "CEASE_DESIST_RECEIVED",     # C&D — only legal notice permitted
    "DECEASED_ACCOUNT",          # Estate/executor procedures required
    "SETTLEMENT_HIGH_VALUE",     # >$10K or >40% discount — supervisor authorization
    "LITIGATION_HIGH_RISK",      # Low collectability + active SOL + >$5K
    "REGULATORY_COMPLAINT",      # CFPB/state AG — compliance officer review
    "MINOR_ACCOUNT",             # Under 18 — legal guardian required
})
# frozenset is immutable — .add() raises TypeError; LLM cannot modify
```

---

## Security Architecture

### 1. PII Masking at Intake (Node 1)
Account numbers are masked to `ACCT-****{last4}` before any LLM prompt or log entry.
No raw PII appears in CloudWatch, DynamoDB, S3, or any LLM call.

### 2. HITL Fail-Safe Routing
```python
def _route_after_routing_decision(state) -> str:
    # Only explicit Python False bypasses HITL gate
    # None, 0, missing key, empty string → all route to HITL
    if state.get("human_review_required") is False:
        return "communication_drafting"
    return "human_review_gate"
```

### 3. LangGraph Interrupt Enforcement
```python
workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_review_gate"],  # Graph pauses at Node 10
)
```
The graph physically cannot advance to Node 11 (communication drafting) or Node 12
(audit finalization) until the human review gate node executes.

### 4. Append-Only Audit Trail
```python
# Each node uses this pattern — prior entries are never mutated
audit_trail = list(state["audit_trail"]) + [new_entry]
```

### 5. AWS Production Security
- KMS customer-managed key for all storage (S3, DynamoDB, Secrets Manager, Aurora)
- S3 Object Lock GOVERNANCE mode — 7-year FCRA retention (2,556 days)
- Aurora PostgreSQL: `log_statement=none` — no PII in query logs
- ECS Fargate: UID 1000, read-only root filesystem
- WAF: 30 HITL submissions per 5 minutes (prevents automated bypass)
- VPC private subnets; ECS tasks have no public IP

---

## Regulatory Coverage

| Regulation | Authority | Coverage |
|------------|-----------|---------|
| FDCPA | 15 U.S.C. § 1692 | Contact hours, mini-Miranda, validation notice, prohibited representations |
| CFPB Regulation F | 12 CFR Part 1006 | 7-in-7 limit, post-conversation wait, electronic opt-out |
| SCRA | 50 U.S.C. § 3937 | 6% rate cap, retroactive, supervisor approval |
| Bankruptcy Code | 11 U.S.C. § 362 | Automatic stay, compliance escalation, permitted actions |
| FCRA | 15 U.S.C. § 1681 | 7-year retention; medical debt $500 threshold (CFPB 2025) |
| UDAAP | Dodd-Frank § 1031 | CFPB/AG complaint HITL; SOL-expired collection restrictions |
| TCPA | 47 U.S.C. § 227 | Electronic opt-out; consent tracking |
| IRS § 6050P | 26 U.S.C. | 1099-C for forgiven debt ≥$600; Python-injected notice |
| State SOL | 50 states + DC | 4-category matrix; SOL restart from last payment |

---

## Demo Scenarios

| Scenario | Account | Balance | Key Conditions | Demo Point |
|----------|---------|---------|---------------|------------|
| DEMO-001 | Credit card · OH | $3,247.55 | Standard FDCPA | 24-month plan, mini-Miranda injection, validation notice |
| DEMO-002 | Personal loan · VA | $8,750.00 | SCRA active military (U.S. Army) | SCRA_DETECTED HITL, 6% rate cap, supervisor approval |
| DEMO-003 | Credit card · IL | $15,420.00 | Chapter 7 bankruptcy | BANKRUPTCY_STAY_DETECTED, COMPLIANCE escalation, ALL collection stops |
| DEMO-004 | Medical debt · TX | $22,000.00 | Settlement $14,300 | SETTLEMENT_HIGH_VALUE, 1099-C $7,700, CFPB 2025 medical debt |

---

## Quick Start

```bash
# Clone the FSI AI Suite
git clone https://github.com/virtualryder/fsi-ai-agents
cd fsi-ai-agents/12-collections-recovery-agent

# Install dependencies
pip install -r requirements.txt

# Run in demo mode (no API key required — UI only)
streamlit run app.py --server.port 8512

# Run with live LLM narratives
cp .env.example .env
# Edit .env: add OPENAI_API_KEY, INSTITUTION_NAME
streamlit run app.py --server.port 8512

# Run tests
pytest tests/ -v
```

**Demo mode:** All 4 scenarios run without an API key. Python computation results
(contact time, SOL, payment plans, settlement tiers, HITL conditions, routing) are
shown exactly as the production pipeline produces them. LLM narrative fields are pre-filled
with representative text.

---

## UI Tabs

| Tab | Contents |
|-----|---------|
| 📋 Submit Case | 4 demo scenarios or manual case entry |
| 🔍 Case Findings | FDCPA compliance, SCRA/bankruptcy flags, SOL status, HITL alert |
| 📊 Collections Analysis | Collectability score, payment plan table, settlement tiers, 1099-C |
| 👤 Collector Review | HITL gate — reviewer ID, 6 decision options, HITL conditions display |
| 🗂 Audit Trail | Node-by-node append-only record with JSON export |
| ℹ️ About | 12-node pipeline diagram, LLM/Python boundary table, regulatory coverage |

---

## Positioning in the FSI AI Suite

Agent 12 is the collections and recovery entry point. It receives referrals from:
- **Agent 01 (Financial Crime):** Fraud-confirmed accounts may be referred for collections
- **Agent 04 (Fraud Detection):** Non-fraud-confirmed delinquent accounts enter standard pipeline
- **Agent 08 (Credit Underwriting):** Hardship and payment history scoring feeds from underwriting model
- **Agent 09 (Document Intelligence):** Dispute letters and bankruptcy filing documents extracted
- **Agent 10 (Payments Compliance):** ACH authorization confirmed before payment plan execution
- **Agent 11 (Model Risk):** Validates the collectability scoring model under SR 11-7 (FAIR_LENDING_FLAG)

**Port:** 8512 | **Suite:** [FSI AI Agents](https://github.com/virtualryder/fsi-ai-agents)

---

## Files

```
12-collections-recovery-agent/
├── app.py                        # Streamlit UI — 6 tabs, port 8512
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Multi-stage, UID 1000, readonlyRootFilesystem
├── .env.example                  # Environment variable template
├── railway.toml                  # Railway deployment config
├── agent/
│   ├── state.py                  # CollectionsState TypedDict, ALWAYS_HITL_CONDITIONS,
│   │                             #   STATE_SOL_YEARS, SETTLEMENT_TIERS, constants
│   ├── nodes.py                  # 12 nodes — Python compliance + LLM narrative
│   ├── graph.py                  # StateGraph, routing functions, interrupt_before
│   └── prompts.py                # 5 LLM prompts (narrative only)
├── data/fixtures/
│   ├── debt_scenarios.json       # 4 demo scenarios with expected HITL outcomes
│   └── payment_plan_configs.json # Reference documentation for all Python constants
├── docs/
│   ├── regulatory-compliance.md  # FDCPA/Reg F/SCRA/FCRA compliance guide + CCO Q&A
│   ├── roi-analysis.md           # ROI analysis: $890K–$3.8M annual benefit
│   └── aws-deployment-guide.md   # 12-step AWS deployment guide
└── tests/
    ├── test_nodes.py             # 12 test classes (60+ assertions)
    └── test_graph.py             # 4 test classes (routing, structure, HITL, pipeline)
```

---

## Test Suite

```bash
# Run all tests
pytest tests/ -v

# Key security tests
pytest tests/test_nodes.py::TestSecurityProperties -v    # frozenset immutability
pytest tests/test_graph.py::TestRoutingFunctions -v      # fail-safe routing

# HITL condition tests
pytest tests/test_nodes.py::TestHITLConditions -v        # all 9 conditions

# Compliance enforcement tests
pytest tests/test_nodes.py::TestFDCPATimeCheck -v        # pytz time enforcement
pytest tests/test_nodes.py::TestSOLComputation -v        # 50-state SOL matrix

# Financial math tests
pytest tests/test_nodes.py::TestPaymentPlanOptimizer -v  # payment plan math
pytest tests/test_nodes.py::TestSettlementTiers -v       # settlement computation
```

---

*Agent 12 · Collections & Recovery Agent · FSI AI Suite*
*FDCPA | Reg F | SCRA | Bankruptcy § 362 | FCRA | UDAAP | TCPA | IRS § 6050P*
