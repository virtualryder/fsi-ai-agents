# Agent 11 — Model Risk Management Agent

**FSI AI Suite | Independent Model Validation | SR 11-7 Compliant**

Agent 11 is the independent model validation function for the FSI AI Suite. It validates the five scoring models used across Agents 02, 03, 04, 07, and 08 — ensuring ongoing SR 11-7 compliance, early degradation detection, and a tamper-evident audit trail that satisfies Federal Reserve and OCC examination requirements.

Every risk determination (tier assignment, degradation flags, PSI classification, HITL routing, validation outcome) is produced by deterministic Python. The LLM produces only written narratives — the conceptual soundness review text, outcomes analysis interpretation, and validation report prose that support the MRO's decision.

---

## Position in the FSI AI Suite

```
Agent 01  Agent 02  Agent 03  Agent 04  Agent 05  Agent 06  Agent 07  Agent 08  Agent 09  Agent 10
  SAR       AML      KYC      Fraud     Reg       Reg       Trading   Credit    Document  Payments
  Filing    TMS      Risk     Score     Filing    Change    Surv.     UW        Intel.    Dispute
            ↑        ↑        ↑                             ↑         ↑
            │        │        │                             │         │
            └────────┴────────┴─────────────────────────────┴─────────┘
                              Agent 11 validates these 5 scoring models
                              (AGT02, AGT03, AGT04, AGT07, AGT08)
```

Agent 11 is the risk management layer that makes all other agents defensible in front of examiners. Without Agent 11, the scoring models in the suite have no independent validation function — which is a regulatory gap under SR 11-7. With Agent 11, every production scoring model has:

- Monthly automated performance monitoring
- Annual full revalidation with MRO sign-off
- Change validation before any model modification goes live
- Triggered review when CloudWatch performance alarms fire
- 10-year tamper-evident record of every validation event

---

## Validation Pipeline — 12 Nodes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Agent 11 — Model Risk Validation Graph                │
└─────────────────────────────────────────────────────────────────────────┘

Node 1: model_inventory_lookup
  Pulls model metadata, weights, thresholds, and hard rules from
  MODEL_REGISTRY. Validates model ID. Adds initial audit entry.
  Python only.
        │
        ▼
Node 2: data_sample_pull
  Assembles performance data for the validation period. Computes
  raw metric deltas vs. baseline. No LLM involvement.
  Python only.
        │
        ▼
Node 3: conceptual_soundness_review     ← LLM (narrative only)
  Produces written review of theoretical basis, variable selection,
  weight rationale, assumption inventory, known limitations.
  LLM text only — does not determine soundness.
        │
        ▼
Node 4: outcomes_analysis               ← LLM + Python
  Python computes: accuracy Δ, Gini Δ, KS Δ, AUC-ROC Δ, FPR Δ, FNR Δ.
  Applies PERFORMANCE_DEGRADATION_THRESHOLDS to flag material decline.
  LLM produces metric interpretation narrative.
        │
        ▼
Node 5: population_stability_analysis
  Computes PSI = Σ(Actual% − Expected%) × ln(Actual% / Expected%).
  Classifies: STABLE (<0.10), WARNING (0.10-0.25), CRITICAL (>0.25).
  Python only — pure mathematics, no LLM.
        │
        ▼
Node 6: benchmark_comparison
  Compares production model vs. challenger: Gini point delta.
  Flags CHALLENGER_UNDERPERFORMS if challenger trails by >5 Gini points.
  Python only.
        │
        ▼
Node 7: sensitivity_analysis
  Validates: weight normalization (sum = 1.0 ± 0.001),
  concentration risk (no factor >50%), hard rule coverage (OFAC, PEP).
  Python only.
        │
        ▼
Node 8: risk_tier_determination
  Determines HITL conditions from frozenset membership checks.
  Sets human_review_required flag. Assigns escalation path.
  Python only — no LLM.
        │
        ▼
Node 9: validation_narrative             ← LLM (narrative only)
  Drafts complete SR 11-7 validation report covering all six
  analysis sections. LLM prose only — validation outcome set
  by Python in Node 8, confirmed by MRO in Node 10.
        │
        ▼
Node 10: routing_decision
  Routes to HITL gate or auto-completion. Explicit is False check —
  missing/None/falsy values default to HITL (fail-safe).
  Python only.
        │
        ├──► [HITL Required] ──► Node 11: human_review_gate
        │                         interrupt_before enforces framework-
        │                         level stop. MRO submits decision.
        │                         4 options: APPROVED / CONDITIONALLY_APPROVED
        │                         / REQUIRE_ADDITIONAL_REVIEW / REQUIRE_REMEDIATION
        │
        └──► [Auto] ──────────────────────────────────────┐
                                                          │
        ◄─────────────────────────────────────────────────┘
        │
        ▼
Node 12: audit_finalize
  Appends final audit trail entry. Persists to DynamoDB model
  registry. Generates S3 Object Lock validation report.
  Python only.
```

---

## LLM vs. Python Boundary

This table is the key compliance document for SR 11-7 reviewers asking "does the AI make risk decisions?"

| Function | Implementation | Why |
|---|---|---|
| Risk tier assignment (HIGH/MEDIUM/LOW) | **Python** | Deterministic constant lookup in MODEL_REGISTRY |
| Performance degradation flags (Gini, KS, FPR, FNR) | **Python** | Arithmetic comparison vs. `PERFORMANCE_DEGRADATION_THRESHOLDS` constants |
| PSI computation and classification | **Python** | Mathematical formula; three-tier classification by numeric threshold |
| HITL condition determination | **Python** | `frozenset` membership check — immutable at runtime |
| Validation routing decision | **Python** | Explicit `is False` check on `human_review_required` |
| HITL gate (MRO decision) | **Human** | `interrupt_before=["human_review_gate"]` — framework-level stop |
| Validation outcome (APPROVED / SUSPENDED) | **Human + Python** | MRO selects decision; Python maps to outcome enum |
| Escalation path (MRO vs. CRO) | **Python** | `HARD_RULE_VIOLATION_DETECTED` → CRO; others → MRO |
| Model approval status in registry | **Python** | Set deterministically from MRO decision |
| Audit trail entries | **Python** | Append-only; no LLM involvement |
| S3 report generation and Object Lock | **Python** | No LLM involvement |
| Conceptual soundness review text | **LLM** | Written narrative for MRO to read — does not determine soundness |
| Outcomes analysis interpretation text | **LLM** | Prose narrative supporting Python-computed metrics |
| Validation report prose | **LLM** | Report draft — MRO reviews and accepts at HITL gate |
| Ongoing monitoring assessment text | **LLM** | Written summary of monitoring findings |

---

## Models Validated

| Model ID | Agent | Description | Risk Tier | Validation Frequency |
|---|---|---|---|---|
| `AGT02-FP-SCORE-v1` | Agent 02 AML/TMS | False positive composite: 30% rule-based pre-score, 50% LLM contextual, 20% historical FP rates | HIGH | Monthly monitoring, annual revalidation |
| `AGT03-KYC-RISK-v1` | Agent 03 KYC | Customer risk: transaction behavior, PEP, adverse media, jurisdiction, documents, BO, industry, tenure | HIGH | Monthly monitoring, annual revalidation |
| `AGT04-FRAUD-SCORE-v1` | Agent 04 Fraud | Fraud composite: velocity (35%), device (20%), behavioral (25%), merchant (20%) | HIGH | Monthly monitoring, annual revalidation |
| `AGT07-SURV-RISK-v1` | Agent 07 Trading | Trading surveillance: unusual volume (30%), timing (25%), cross-account (25%), comms (20%) | HIGH | Monthly monitoring, annual revalidation |
| `AGT08-CREDIT-SCORE-v1` | Agent 08 Credit | Credit underwriting: DTI (25%), payment history (30%), capacity (20%), collateral (15%), credit history (10%) | HIGH | Monthly monitoring, annual revalidation + ECOA fair lending review |

**All five models are HIGH-tier.** This means:
- Monthly automated monitoring (not quarterly or annual)
- MRO sign-off required at every validation event — no exceptions
- Annual full revalidation in addition to ongoing monitoring
- 10-year S3 Object Lock retention on all validation reports

---

## HITL Conditions — When Human Review Is Required

The following 9 conditions are members of `ALWAYS_HITL_CONDITIONS` frozenset — a Python immutable set that cannot be modified at runtime. Any application code attempting to `.add()` to this set raises `TypeError`. Tests verify this.

| Condition | When It Fires | Reviewer |
|---|---|---|
| `HIGH_TIER_INITIAL_VALIDATION` | First validation of any HIGH-tier model | MRO |
| `HIGH_TIER_CHANGE_VALIDATION` | Model weight or logic change validation | MRO |
| `ANNUAL_REVALIDATION_HIGH_TIER` | Annual revalidation of HIGH-tier model | MRO |
| `PERFORMANCE_DEGRADATION_TRIGGERED` | Any degradation threshold exceeded | MRO |
| `PSI_CRITICAL` | PSI > 0.25 (population has drifted significantly) | MRO |
| `MATERIAL_FINDING` | Any single flag exceeds material threshold | MRO |
| `CHALLENGER_UNDERPERFORMS` | Challenger model trails production by >5 Gini points | MRO |
| `HARD_RULE_VIOLATION_DETECTED` | OFAC bypass or PEP suppression without authorization | **CRO** |
| `FAIR_LENDING_FLAG` | AGT08 credit model: new feature with demographic proxy | MRO + Fair Lending Officer |

**Note on `HARD_RULE_VIOLATION_DETECTED`:** This is the most severe condition Agent 11 can generate. A hard rule violation means a regulatory bright-line was circumvented — potential BSA violation requiring immediate CRO review, BSA Officer notification, and potential regulatory disclosure.

---

## Security Architecture

### 1. Python/LLM Boundary (Primary Compliance Control)

All risk determinations are Python-only. This design satisfies SR 11-7's requirement for independent validation by ensuring the validation outcome cannot be influenced by LLM hallucination, prompt injection, or model drift. The LLM is a report-writing assistant, not a decision-maker.

### 2. Framework-Level HITL Enforcement

`interrupt_before=["human_review_gate"]` is a LangGraph directive, not application logic. The graph physically cannot produce a validation outcome for a HIGH-tier model without a human MRO submitting a decision. No application code path can bypass this.

### 3. Immutable Frozensets

`ALWAYS_HITL_CONDITIONS`, `HIGH_TIER_ALWAYS_HITL`, and `HITL_VALIDATION_TYPES` are Python `frozenset` objects. They are defined as module-level constants and cannot be modified after initialization. Runtime modification attempts raise `TypeError` — which is tested in `tests/test_nodes.py`.

### 4. Append-Only Audit Trail

The audit trail uses the pattern `list(current_trail) + [new_entry]` — prior entries are never modified. The Aurora PostgreSQL audit table has `no_update` and `no_delete` rules enforced at the database level. The S3 Object Lock provides a tamper-evident archive of every validation report.

### 5. Fail-Safe Routing

`_route_after_routing_decision` checks `human_review_required is False` (not falsy). This means `None`, `0`, and any other falsy value routes to HITL — not auto-completion. Only an explicit Python `False` (set intentionally by `risk_tier_determination_node`) bypasses the HITL gate. Missing state defaults safe.

### 6. S3 Object Lock GOVERNANCE

Validation reports are written to S3 with GOVERNANCE-mode Object Lock and a 10-year retention period. GOVERNANCE mode requires authenticated administrator credentials with `s3:BypassGovernanceRetention` permission to delete objects before expiry — and that bypass action itself creates an AWS CloudTrail audit event.

### 7. Container Security

- Non-root user (UID 1000) — principle of least privilege
- Read-only root filesystem — validation output goes to S3 and DynamoDB, not container storage
- Multi-stage Docker build — no build tools in runtime image
- ECR image scanning on push — blocks deployment with CRITICAL vulnerabilities

### 8. Secrets Management

All credentials retrieved from AWS Secrets Manager at runtime. No credentials in environment variables, Dockerfile, or application code. KMS encryption on all secrets.

---

## Regulatory Coverage

| Regulation | SR 11-7 Section | Agent 11 Implementation |
|---|---|---|
| **SR 11-7 §§ 5-7** — Conceptual soundness | Node 3 | LLM conceptual soundness narrative; MRO determines soundness at HITL gate |
| **SR 11-7 § 8** — Outcomes analysis | Nodes 4-7 | Python: accuracy, Gini, KS, AUC-ROC, FPR, FNR, PSI, benchmark, sensitivity |
| **SR 11-7 §§ 10-11** — Ongoing monitoring | EventBridge + Node 12 | Monthly automated triggers for HIGH-tier; CloudWatch performance alarms |
| **SR 11-7 § 4** — Human oversight | Node 11 + `interrupt_before` | Framework-level HITL; reviewer identity captured in audit trail |
| **ECOA / Regulation B** — Fair lending | `FAIR_LENDING_FLAG` condition | AGT08 credit model: demographic proxy detection triggers Fair Lending Officer review |
| **BSA / AML validation** | FNR threshold (3pp) | Missing genuine suspicious activity (FNR) flagged at tighter threshold than FPR |
| **BSA 5-year retention** | `audit_retention` field | 10-year S3 Object Lock GOVERNANCE (model life + BSA 5-year) |
| **OCC model risk guidance** | MODEL_REGISTRY | Risk tier, validation schedule, known limitations documented per model |

---

## Quick Start

### Demo Mode (no API key required)

```bash
cd 11-model-risk-agent
pip install -r requirements.txt
streamlit run app.py
# Open http://localhost:8511
```

Demo mode uses pre-computed narratives and synthetic performance data — no LLM API calls. All four demo scenarios are available and exercise the full 12-node pipeline.

### Demo Scenarios

| Scenario | Model | Validation Type | Key Moment |
|---|---|---|---|
| DEMO-001 | AGT02-FP-SCORE-v1 | Annual Revalidation | All metrics PASS; MRO required (HIGH tier); recommended APPROVED |
| DEMO-002 | AGT04-FRAUD-SCORE-v1 | Triggered Review | Gini declined 12.3 points — `GINI_DEGRADATION` + `PERFORMANCE_DEGRADATION_TRIGGERED`; CRO escalation; shows real-time remediation |
| DEMO-003 | AGT08-CREDIT-SCORE-v1 | Initial Validation | New feature with geographic proxy; `FAIR_LENDING_FLAG` triggers; requires Fair Lending Officer + MRO |
| DEMO-004 | AGT03-KYC-RISK-v1 | Ongoing Monitoring | All metrics stable; PSI STABLE; no HITL conditions; auto-resolves (show auto-completion path) |

**Key demo moment (DEMO-002):** Submit the triggered review, then navigate to Tab 3 (Model Performance) to show the Gini bar chart with the degradation threshold highlighted. Then go to Tab 4 (MRO Review) and submit `CONDITIONALLY_APPROVED` with a condition requiring remediation within 30 days. Tab 5 (Audit Trail) shows the full 12-node record.

### With LLM (real narratives)

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY or configure Bedrock
streamlit run app.py
```

### With Production Database (Aurora PostgreSQL)

```bash
# Set POSTGRES_CONNECTION_STRING in .env
# LangGraph will use PostgresSaver for checkpoint persistence
streamlit run app.py
```

---

## Project Structure

```
11-model-risk-agent/
├── app.py                          # Streamlit UI — 6 tabs (700 lines)
├── requirements.txt                # Pinned dependencies
├── Dockerfile                      # Multi-stage, non-root, read-only FS
├── railway.toml                    # Railway deployment (Streamlit)
├── .env.example                    # Environment variable template
├── .gitignore                      # Excludes .env, __pycache__, secrets.toml
│
├── agent/
│   ├── state.py                    # ModelRiskState TypedDict, MODEL_REGISTRY,
│   │                               # ALWAYS_HITL_CONDITIONS frozenset,
│   │                               # PERFORMANCE_DEGRADATION_THRESHOLDS
│   ├── prompts.py                  # 4 LLM prompts (narrative only)
│   ├── nodes.py                    # 12 node functions + PSI computation
│   └── graph.py                    # StateGraph, routing functions, build_model_risk_graph()
│
├── data/
│   └── fixtures/
│       ├── model_scenarios.json    # 4 demo validation scenarios
│       ├── model_registry.json     # Full metadata for all 5 models
│       └── validation_matrix.json  # SR 11-7 component requirements by type/tier
│
├── tests/
│   ├── test_nodes.py               # 8 test classes, frozenset immutability,
│   │                               # PSI math, degradation thresholds, audit trail
│   └── test_graph.py               # Routing logic, HITL behavior, full pipeline
│
└── docs/
    ├── regulatory-compliance.md    # SR 11-7, ECOA, BSA, retention — Compliance Officer Q&A
    ├── roi-analysis.md             # Cost of manual MRM vs. Agent 11; degradation detection ROI
    └── aws-deployment-guide.md     # 12-step production deployment; pre-go-live checklist
```

---

## Running Tests

```bash
cd 11-model-risk-agent
pip install pytest
pytest tests/ -v
```

Expected output: all tests pass, including:
- `TestSecurityProperties::test_always_hitl_conditions_is_frozenset`
- `TestSecurityProperties::test_always_hitl_conditions_immutable`
- `TestPSIComputation::test_psi_mathematical_correctness`
- `TestRoutingFunctions::test_explicit_false_bypasses_hitl`
- `TestRoutingFunctions::test_none_routes_to_hitl_not_auto_complete`

---

## Related Agents

| Agent | Model Validated by Agent 11 | Relationship |
|---|---|---|
| [Agent 02 — AML/TMS False Positive Reduction](../02-aml-tms-agent/) | AGT02-FP-SCORE-v1 | Agent 11 validates the composite scoring model; model suspension triggers Agent 02 manual override |
| [Agent 03 — KYC Risk Scoring](../03-kyc-risk-agent/) | AGT03-KYC-RISK-v1 | Agent 11 validates the customer risk scoring model |
| [Agent 04 — Fraud Detection](../04-fraud-detection-agent/) | AGT04-FRAUD-SCORE-v1 | Agent 11 validates the fraud composite; Gini degradation triggers triggered review |
| [Agent 07 — Trading Surveillance](../07-trading-surveillance-agent/) | AGT07-SURV-RISK-v1 | Agent 11 validates the trading risk score; hard rule (INSIDER_TRADING) coverage verified |
| [Agent 08 — Credit Underwriting](../08-credit-underwriting-agent/) | AGT08-CREDIT-SCORE-v1 | Agent 11 validates credit model; FAIR_LENDING_FLAG protects against ECOA violations |

---

## License

MIT License. See [LICENSE](../LICENSE).

---

*Agent 11 is part of the FSI AI Suite — a 11-agent portfolio of production-ready, compliance-by-design AI agents for financial services.*
