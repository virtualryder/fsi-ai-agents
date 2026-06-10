# Agent 09 — Document Intelligence Agent

## What This Agent Does

The Document Intelligence Agent converts unstructured financial documents — PDFs, scanned images, SWIFT FIN messages, Word documents — into validated, PII-masked, structured JSON payloads that every other agent in the FSI AI Suite can consume.

**The core problem it solves:** Every other agent in the suite assumes it receives structured input. But banks live in a world of PDFs. A loan officer's 1003 is a scanned form. A SWIFT MT103 is a proprietary FIN-format text message. A government ID is a photograph. Without this agent, every team must manually re-key data before specialist agents can process it. With this agent, documents flow in and structured data flows out — automatically, with confidence scoring and PII protection built in.

---

## Who Should Use This Agent

| Team | Documents They Submit | Downstream Agent |
|---|---|---|
| Loan Officers | Form 1003, Tax Returns (1040/1065/1120), Bank Statements, Appraisals, SBA Forms | Agent 08 — Credit Underwriting |
| Wire / Treasury Desk | SWIFT MT103, MT202, Wire Instructions | Agent 01 — Financial Crime, Agent 04 — Fraud Detection |
| KYC / CDD Analysts | Government IDs, Entity Documents, Trust Documents, Beneficial Ownership Certs | Agent 03 — KYC/CDD Perpetual |
| Trading / Operations | Trade Confirmations, Brokerage Statements | Agent 07 — Trading Surveillance |
| Compliance Team | Regulatory Exam Letters, Consent Orders | Agent 06 — Regulatory Change Management |
| BSA Officers | SAR Forms, CTR Forms | Agent 01 — Financial Crime Investigation |

---

## How It Fits in the Suite

This agent is the **horizontal entry point** for the entire FSI AI Suite. Think of it as the intake layer:

```
Unstructured Documents (PDFs, images, SWIFT, Word)
    │
    ▼
Agent 09 — Document Intelligence
    ├──► Agent 01 — Financial Crime Investigation
    ├──► Agent 03 — KYC/CDD Perpetual
    ├──► Agent 04 — Fraud Detection
    ├──► Agent 06 — Regulatory Change Management
    ├──► Agent 07 — Trading Surveillance
    └──► Agent 08 — Credit Underwriting
```

Every specialist agent in the suite benefits from Agent 09 being deployed first. When a loan officer drops a document into Agent 09, the structured output is ready for Agent 08 without any manual re-keying. When a wire desk submits a SWIFT message, Agent 09's structured output is pre-formatted for Agent 01's AML investigation workflow.

---

## Supported Document Types (25 total)

### Lending
- `LOAN_APPLICATION_RESIDENTIAL` — Form 1003
- `LOAN_APPLICATION_COMMERCIAL` — Commercial credit applications
- `PROPERTY_APPRAISAL` — USPAP-compliant appraisal reports
- `TAX_RETURN_1040` — Individual income tax returns
- `TAX_RETURN_1065` — Partnership tax returns
- `TAX_RETURN_1120` — Corporation tax returns
- `FINANCIAL_STATEMENT` — Audited/reviewed/compiled financial statements
- `BANK_STATEMENT` — Account statements (2–3 months)
- `SBA_FORM_1919` — Borrower Information Form
- `SBA_FORM_1920` — Lender Application for Guaranty

### Payments / Wire Transfers
- `SWIFT_MT103` — Single Customer Credit Transfer
- `SWIFT_MT202` — Financial Institution Transfer
- `WIRE_INSTRUCTION` — Customer wire transfer instructions (BEC risk)

### Capital Markets / Trading
- `TRADE_CONFIRMATION` — Securities and derivatives trade confirms
- `BROKERAGE_STATEMENT` — Account statements with holdings

### Identity / KYC
- `GOVERNMENT_ID` — Passport, driver's license (always HITL)
- `ENTITY_DOCUMENT` — Articles of incorporation, operating agreements
- `TRUST_DOCUMENT` — Trust agreements and certifications
- `BENEFICIAL_OWNERSHIP_CERT` — FinCEN CDD certification

### Compliance / Regulatory
- `REGULATORY_EXAM_LETTER` — OCC/FDIC/Federal Reserve exam letters and MRAs
- `CONSENT_ORDER` — Formal enforcement actions (always HITL)
- `ADVERSE_MEDIA_ARTICLE` — Negative news screening results
- `SAR_FORM` — Suspicious Activity Reports (always HITL, BSA confidentiality)
- `CTR_FORM` — Currency Transaction Reports (always HITL)
- `UNKNOWN` — Unclassifiable documents (always HITL)

---

## 12-Node Processing Pipeline

```
START
 │
 ▼
[1] document_intake         — validate, compute SHA-256, detect duplicates
 │
 ▼
[2] text_extraction         — PDF/OCR/SWIFT parsing; raw bytes cleared from state
 │
 ▼
[3] pii_detection           — Python regex: mask SSN/passport/account BEFORE LLM
 │
 ▼
[4] document_classification — LLM: classify type, 0–1 confidence score
 │
 ▼
[5] field_extraction        — LLM: schema-driven field extraction (PII-masked input)
 │
 ▼
[6] validation              — Python: type checks, business rules, SWIFT screening
 │
 ▼
[7] confidence_scoring      — Python: 4-factor composite score → tier (HIGH/MEDIUM/LOW/UNCERTAIN)
 │
 ▼
[8] routing_decision        — Python: lookup table → target agents + HITL flag
 │
 ├──[HITL]──► [9] human_review_gate  (interrupt_before — graph pauses here)
 │                    │
 │            APPROVE_AND_ROUTE / CORRECT_AND_ROUTE → enrichment
 │            REJECT / REQUEST_RESUBMIT → audit_finalize
 │
 └──[auto]──► [10] enrichment       — LLM: anomaly flags, regulatory notes (PII-masked)
                    │
                    ▼
              [11] output_packaging  — final PII masking, structured JSON payload
                    │
                    ▼
              [12] audit_finalize    — clear text cache, record processing time
                    │
                   END
```

---

## What the LLM Does vs. What Python Does

This distinction is fundamental to regulatory compliance. The LLM is an external API — it is not a deterministic system and its outputs can vary. All regulatory controls must be implemented in deterministic Python.

| Task | LLM | Python |
|---|---|---|
| Classify document type | ✅ | |
| Extract field values from text | ✅ | |
| Generate enrichment notes / anomaly descriptions | ✅ | |
| Merge reviewer corrections | ✅ | |
| PII detection and masking | | ✅ |
| SHA-256 document hash | | ✅ |
| Confidence tier assignment | | ✅ |
| Routing decisions (which agent receives what) | | ✅ |
| HITL trigger decisions | | ✅ |
| SWIFT high-risk country screening | | ✅ |
| CTR threshold detection | | ✅ |
| Business rule validation | | ✅ |
| Audit trail recording | | ✅ |

---

## Security Architecture

### 1. PII Masking Before LLM (Defense-in-Depth)

The `pii_detection_node` runs before any LLM call. It detects 7 PII types using Python regex and masks the document text in the in-memory cache. Every subsequent LLM node reads the masked text — the LLM never receives raw SSNs, passport numbers, or account numbers.

A second masking layer exists in the LLM extraction prompt: the model is explicitly instructed to return SSNs as `XXX-XX-{last4}` and passport numbers as `PASSPORT_PRESENT`. Both layers protect against GLBA data minimization violations when using an external API.

### 2. Raw Bytes Never Stored in State

LangGraph state is persisted to Aurora PostgreSQL (the checkpoint database). If raw document bytes were stored in state, multi-megabyte PDFs would be written to the database on every state transition. The agent stores only the document hash (SHA-256) and a truncated text preview (500 characters). The full extracted text is in a module-level Python dict (keyed by hash), cleared when processing completes.

### 3. Routing Is a Python Constant

The `DOCUMENT_ROUTING` dict in `nodes.py` is defined at module load time. It maps each document type to its target agents. No LLM response can modify this mapping — prompt injection attacks cannot redirect SAR forms to non-BSA agents or wire instructions to the wrong queue.

### 4. HITL Enforced at the LangGraph Framework Level

`interrupt_before=["human_review_gate"]` is set in the compiled graph. This is not an application-level check — it is enforced by the LangGraph framework. The graph physically cannot proceed past `human_review_gate` without a human reviewer submitting a decision through the checkpointer. No code path bypasses this.

### 5. Document Hash for Tamper Detection

SHA-256 is computed in `document_intake_node` from the raw bytes before any processing. This hash is stored in the audit trail and in the checkpoint database. If a document is resubmitted with modified content (e.g., an altered wire instruction amount), the new hash will differ from any previously processed version, triggering duplicate detection logic.

### 6. ALWAYS_HITL_DOCUMENT_TYPES as a Python frozenset

```python
ALWAYS_HITL_DOCUMENT_TYPES = frozenset({
    DocumentType.GOVERNMENT_ID.value,
    DocumentType.SAR_FORM.value,
    DocumentType.CTR_FORM.value,
    DocumentType.CONSENT_ORDER.value,
})
```

This is a `frozenset` — immutable at runtime. Even if application code calls `ALWAYS_HITL_DOCUMENT_TYPES.add(...)`, Python raises a `TypeError`. Tests verify this immutability explicitly.

---

## Confidence Scoring

Confidence is computed by Python from four factors:

| Factor | Weight | What It Measures |
|---|---|---|
| Classification confidence | 30% | LLM's self-reported certainty about document type |
| Field completeness | 30% | Fraction of required fields successfully extracted |
| Average field confidence | 25% | Average per-field confidence score from LLM |
| Extraction quality | 15% | OCR confidence and absence of extraction warnings |

**Tier assignment:**
- `HIGH` (≥ 0.85): Auto-route to downstream agents
- `MEDIUM` (0.65–0.84): Auto-route with low-confidence fields flagged
- `LOW` (0.40–0.64): HITL required
- `UNCERTAIN` (< 0.40): HITL required; likely UNKNOWN document type

---

## Regulatory Coverage

| Regulation | How the Agent Addresses It |
|---|---|
| GLBA Safeguards Rule | PII masking, KMS encryption, least-privilege IAM |
| BSA / 31 CFR 1010 | ALWAYS_HITL for SAR/CTR; SWIFT country screening; audit trail retention |
| OFAC | High-risk country pre-screening in SWIFT validation |
| ECOA / Reg B | HMDA demographic fields extracted; geographic fair lending flags |
| HMDA | Full HMDA data element extraction for 1003 documents |
| FinCEN CDD Rule | BENEFICIAL_OWNERSHIP_CERT schema extracts all required fields |
| BSA CIP | GOVERNMENT_ID always HITL; passport numbers never extracted |
| SEC 17a / FINRA 4511 | TRADE_CONFIRMATION extracts all required trade record fields |

See `docs/regulatory-compliance.md` for the complete regulatory analysis.

---

## Quick Start

### Requirements
- Python 3.11+
- OpenAI API key (or run in demo mode without one)
- Tesseract OCR (for scanned document processing)

### Installation

```bash
# Clone the repository
git clone https://github.com/virtualryder/fsi-ai-agents.git
cd fsi-ai-agents/09-document-intelligence-agent

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add OPENAI_API_KEY

# Run the Streamlit dashboard (port 8509)
streamlit run app.py --server.port 8509
```

### Run in Demo Mode (No API Key Required)
Without an `OPENAI_API_KEY` in `.env`, the app runs in demo mode using pre-computed outputs from `data/fixtures/sample_documents.json`. All four primary document routing paths are demonstrated.

### Run Tests
```bash
pytest tests/ -v
```

Test coverage includes:
- PII detection and masking (all 7 PII types)
- Input sanitization (control character stripping, length truncation)
- Document intake (size limits, format validation)
- SWIFT validation (high-risk country screening, CTR threshold)
- Confidence scoring (tier boundary conditions)
- Routing decisions (all HITL trigger conditions)
- ALWAYS_HITL frozenset immutability
- DOCUMENT_ROUTING completeness (all 24 non-UNKNOWN types have entries)
- Full pipeline integration (with mocked LLM)
- Security: no raw PII in final state after processing
- Security: LLM cannot alter routing targets
- Security: text cache cleared after processing
- HITL interrupt, approve, reject workflows

### Docker Deployment

```bash
# Build the image
docker build -t agent09-document-intelligence .

# Run locally
docker run -p 8509:8509 \
  -e OPENAI_API_KEY=sk-your-key-here \
  agent09-document-intelligence
```

See `docs/aws-deployment-guide.md` for production deployment with WAF, KMS, and Aurora.

---

## Project Structure

```
09-document-intelligence-agent/
├── agent/
│   ├── __init__.py
│   ├── state.py          — DocumentIntelligenceState TypedDict, 25 DocumentType enums
│   ├── prompts.py        — LLM prompt templates (5 prompts with security constraints)
│   ├── nodes.py          — 12 node functions (processing pipeline)
│   └── graph.py          — LangGraph DAG assembly and factory functions
├── data/
│   └── fixtures/
│       ├── document_type_schemas.json  — Required/optional fields for all 25 document types
│       ├── sample_documents.json       — 4 demo scenarios (SWIFT, loan app, trade confirm, exam letter)
│       └── routing_matrix.json         — Complete routing rules for UI display
├── docs/
│   ├── aws-deployment-guide.md     — 12-step production deployment with security rationale
│   ├── regulatory-compliance.md    — GLBA, BSA, ECOA, HMDA, FinCEN CDD compliance analysis
│   └── roi-analysis.md             — Time-motion analysis, $1.66M–$1.91M annual value
├── tests/
│   ├── __init__.py
│   ├── test_nodes.py    — 40+ unit tests (includes security tests)
│   └── test_graph.py    — Integration tests (HITL workflow, security properties)
├── app.py               — Streamlit dashboard (6 tabs, port 8509)
├── Dockerfile           — Multi-stage build, non-root user, read-only filesystem
├── railway.toml         — Railway.app deployment configuration
├── requirements.txt     — Pinned Python dependencies
└── .env.example         — Environment variable template
```

---

## Related Agents

This agent is Agent 09 in the FSI AI Suite. It feeds structured data to:

- **[Agent 01 — Financial Crime Investigation](../01-financial-crime-investigation)**: Receives SWIFT, wire instructions, SAR/CTR, bank statements
- **[Agent 03 — KYC/CDD Perpetual](../03-kyc-cdd-perpetual)**: Receives government IDs, entity documents, trust documents, beneficial ownership certs
- **[Agent 04 — Fraud Detection](../04-fraud-detection)**: Receives wire instructions, SWIFT MT103, bank statements
- **[Agent 06 — Regulatory Change Management](../06-regulatory-change-management)**: Receives exam letters and consent orders
- **[Agent 07 — Trading Surveillance](../07-trading-surveillance)**: Receives trade confirmations and brokerage statements
- **[Agent 08 — Credit Underwriting](../08-credit-underwriting-agent)**: Receives loan applications, tax returns, financial statements, bank statements, appraisals, SBA forms

**Recommended deployment order:** Deploy Agent 09 first. Its structured output immediately accelerates every other agent you deploy subsequently — no custom integration work required between Agent 09 and the suite.

---

## Getting Help

See the **About** tab in the Streamlit dashboard for detailed explanations of the security architecture and compliance posture, written for compliance officers and security teams.

For issues and feature requests: [github.com/virtualryder/fsi-ai-agents/issues](https://github.com/virtualryder/fsi-ai-agents/issues)
