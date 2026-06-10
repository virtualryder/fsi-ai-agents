# Agent 10 — Regulatory Compliance Analysis

## Purpose of This Document

This document is written for compliance officers, BSA officers, and internal audit teams
reviewing the Payments Compliance Agent. It explains which regulations govern each aspect
of the agent's behavior, how the agent implements regulatory requirements, and where human
judgment is intentionally preserved.

---

## 1. Regulation E — Electronic Fund Transfer Act (12 CFR Part 1005)

### What Regulation E Requires

Regulation E (implementing the Electronic Fund Transfer Act, 15 U.S.C. § 1693 et seq.)
protects consumers from unauthorized electronic fund transfers, incorrect amounts,
duplicate transactions, and other errors in consumer electronic payment accounts.

### What the Agent Does for Regulation E

**Applicability Determination (Python — deterministic)**

The `reg_e_assessment_node` applies a Python-coded rule set to determine whether Reg E
applies to a given payment event. Reg E applies when:
- The payment involves a consumer account (not a corporate DDA or commercial account)
- The payment type is an Electronic Fund Transfer: ACH (PPD, TEL, WEB, CCD when consumer),
  debit card, prepaid card, ATM, or FedNow
- Reg E does NOT apply to wire transfers (12 CFR 1005.3(c)(4)), check conversions
  completed before they reach the consumer, or securities transactions

**SLA Deadline Computation (Python — deterministic)**

The agent computes all Reg E deadlines in Python using UTC timestamps:

| SLA | Timeframe | Extension | Regulatory Basis |
|-----|-----------|-----------|------------------|
| Provisional credit | 10 business days | 20 days: new account, POS, foreign | 12 CFR 1005.11(c)(2)(i) |
| Investigation completion | 45 calendar days | 90 days: new account, POS, foreign | 12 CFR 1005.11(c)(1) |
| Written notice to consumer | 3 business days after completion | — | 12 CFR 1005.11(d) |
| Provisional credit reversal notice | 5 business days before reversal | — | 12 CFR 1005.11(d)(2) |

Business day calculations use `python-dateutil` with Federal Reserve banking calendar
exclusions. All deadlines are stored as ISO-8601 UTC timestamps.

**Provisional Credit Obligation (Python — deterministic)**

The agent sets `provisional_credit_required=True` and computes `provisional_credit_amount`
when:
- Reg E applies
- A dispute is filed
- The dispute involves an unauthorized transaction (R10, R07, R11) or incorrect amount
- The 10-business-day window has not yet expired

The LLM does NOT determine provisional credit obligation. This is a statutory right —
if the conditions are met, provisional credit must be issued. The Python node sets this flag;
the human reviewer confirms it.

**Written Notice Drafting (LLM — with constraints)**

The `resolution_drafting_node` calls the LLM to draft the written notice required by
12 CFR 1005.11(d). The LLM prompt:
- Specifies the regulatory format requirements (subject, body, rights statement)
- Requires plain language at 6th-8th grade reading level (CFPB plain language guidance)
- Requires inclusion of the customer's specific rights under 12 CFR 1005.11(d)(1)
- Prohibits including full account numbers (only last-4 digits)
- Specifies the notice type (ERROR_FOUND, NO_ERROR, PROVISIONAL_CREDIT_REVERSAL,
  INVESTIGATION_EXTENDED)

The LLM drafts the notice; the human reviewer approves it before it is sent.

### What Reg E Does NOT Permit the Agent to Do

The agent does NOT:
- Make a final determination that an error did or did not occur (that is the human reviewer's
  determination after reviewing the investigation findings)
- Automatically deny a dispute claim without human review
- Send a customer notice without a human reviewer's `APPROVE_RESOLUTION` or
  `OVERRIDE_RESOLUTION` decision for HITL-flagged events

---

## 2. Nacha Operating Rules — ACH Return Processing

### What the Nacha Operating Rules Require

Nacha Operating Rules govern the ACH network: return windows, unauthorized return procedures,
NOC processing, and originator obligations.

### Return Code Validation (Python — deterministic)

The `nacha_validation_node` validates return codes against the `NACHA_RETURN_WINDOWS` dict:

```python
NACHA_RETURN_WINDOWS: Dict[str, int] = {
    "R01": 2,  # NSF — 2 banking days (Nacha OR Section 2.12.1)
    "R07": 60, # Authorization Revoked — 60 calendar days (Section 2.12.2)
    "R10": 60, # Customer Advises Not Authorized — 60 calendar days
    "R11": 60, # Not in Accordance with Authorization — 60 calendar days
    "R29": 60, # Corporate Not Authorized — 60 calendar days
    ...
}
```

If a return code is received after its allowable window (i.e., `days_since_settlement`
exceeds `NACHA_RETURN_WINDOWS[code]`), the agent sets `late_return_flag=True` and routes
to the LEGAL team. Late returns may constitute Nacha rule violations exposing the institution
to financial penalties under Nacha Rule 10000 ($100 per violation, $500,000 annual cap).

### Unauthorized Return Procedures (Python — deterministic)

For unauthorized return codes (R05, R07, R10, R11, R29, R33, R37, R38, R51), the agent:
1. Sets `unauthorized_return_eligible=True`
2. Triggers HITL (human review required for all unauthorized returns per Reg E)
3. Routes to the DISPUTES team
4. Notes that the RDFI must obtain a Written Statement Under Penalty of Perjury (WSUPOP)
   from the consumer (Nacha OR Section 2.12.2) — this is flagged for the reviewer

The agent does NOT automatically file the return. The human reviewer must confirm the
unauthorized return decision.

### NOC Processing (Python — deterministic)

NOC codes C01-C09 are detected by `nacha_validation_node`. The agent:
- Sets `noc_required=True`
- Records the correction data (corrected account number, routing number, etc.)
- Computes the 6-banking-day deadline for originator to update records
- Routes to PAYMENTS_OPS for automated notification

Low-risk NOC events (no concurrent Reg E dispute, no OFAC flags) are auto-resolved
without HITL. The originator is notified automatically.

### WEB SEC Code Annual Audit (Python — deterministic)

For WEB SEC code entries (Internet-initiated debits), the agent sets `web_annual_audit_flag=True`
to remind the originator of their annual Nacha-required audit of internet authorization procedures
(Nacha OR Section 2.5.5).

### IAT Enhanced Due Diligence (Python — deterministic)

International ACH Transactions (IAT SEC code) trigger `iat_enhanced_due_diligence=True`,
flagging the need for enhanced OFAC screening and correspondent bank AML review required
by Nacha OR Section 2.8.

---

## 3. OFAC Sanctions Regulations (31 CFR Parts 500-598)

### What OFAC Regulations Require

The Office of Foreign Assets Control (OFAC) administers U.S. economic sanctions programs.
Financial institutions must block or reject transactions involving Specially Designated
Nationals (SDNs) and sanctioned jurisdictions. OFAC violations carry civil penalties of
up to $356,579 per transaction under IEEPA (50 U.S.C. § 1705) and criminal penalties
up to $1,000,000 and 20 years imprisonment.

### OFAC Screening Architecture (Python — no LLM involvement)

**Critical design principle:** OFAC screening must be deterministic. The LLM is NOT used
for OFAC screening at any stage.

```python
OFAC_SANCTIONED_COUNTRY_CODES = frozenset({
    "KP",  # North Korea — DPRK Sanctions Regulations (31 CFR Part 510)
    "IR",  # Iran — Iranian Sanctions Regulations (31 CFR Part 561)
    "CU",  # Cuba — Cuban Assets Control Regulations (31 CFR Part 515)
    "SY",  # Syria — Syrian Sanctions Regulations (31 CFR Part 542)
})
```

This frozenset is immutable at runtime. Any attempt to call `.add()` raises `TypeError`.
Tests explicitly verify this immutability.

**What happens on an OFAC match:**

1. `sanctions_screening_node` sets `ofac_hit=True` (Python constant lookup — no API call)
2. `compliance_scoring_node` hard-overrides `compliance_risk_tier="CRITICAL"` and
   `compliance_risk_score=1.0` — no composite score can override this
3. `routing_decision_node` routes to `BSA_COMPLIANCE` with `resolution_type="OFAC_HOLD"`
4. Graph pauses at `human_review_gate` (framework-enforced HITL)
5. `output_packaging_node` includes `FILE_OFAC_REPORT` in `downstream_actions`

**Blocking Report Requirement:**

The OFAC blocking report SLA is computed as 10 business days from the blocking date
(31 CFR 501.604). This SLA is displayed in the dashboard and tracked in the audit trail.

**OFAC Compliance Contact:**

The agent's documentation and dashboard note OFAC's compliance hotline (1-800-540-6322)
for institutions that need guidance on handling a blocked transaction.

**Tipping-Off Prohibition:**

The LLM system prompts for compliance_analysis and resolution_drafting explicitly instruct
the LLM not to disclose the OFAC hold or SAR consideration to the customer or originator
(18 U.S.C. § 1960, 31 U.S.C. § 5318(g)(2)). Both the system prompt and the human reviewer
are reminded of this prohibition.

---

## 4. Bank Secrecy Act — SAR and CTR Filing (31 CFR Part 1020)

### SAR Filing Requirement (31 CFR 1020.320)

A financial institution must file a Suspicious Activity Report with FinCEN when it knows,
suspects, or has reason to suspect a transaction involves funds derived from illegal activity
and involves $5,000 or more.

**SAR Threshold (Python — deterministic):**
```python
SAR_CONSIDERATION_THRESHOLD = 5_000.00  # 31 CFR 1020.320
```

The `compliance_scoring_node` sets `sar_candidate=True` when:
- Amount ≥ $5,000, AND
- One or more suspicious activity indicators are present: OFAC match, unauthorized
  wire transfer, business email compromise fraud, structuring indicators, or unusual
  pattern with high-risk country involvement

**BSA Requires Human Judgment for SAR Filing:**
The agent flags SAR candidates — it does NOT file SARs automatically. BSA requires that
a qualified BSA officer make the SAR determination. The `ALWAYS_HITL_PAYMENT_EVENTS`
frozenset includes `"SAR_CANDIDATE"`, ensuring every SAR candidate receives mandatory
human review.

**30-Day SAR Filing Window:**
The SAR filing SLA is computed as 30 calendar days from the date suspicious activity is
first detected (31 CFR 1020.320(b)(3)). A 60-day extension is available if law enforcement
requests a delay.

### CTR Filing Requirement (31 CFR 1010.311)

Currency Transaction Reports must be filed for cash transactions exceeding $10,000.
For ACH and electronic payment purposes, the `nacha_validation_node` flags transactions
that meet or exceed the CTR threshold:

```python
CTR_THRESHOLD_USD = 10_000.00  # 31 CFR 1010.311
```

`CTR_THRESHOLD` is included in `ALWAYS_HITL_PAYMENT_EVENTS` — every CTR-threshold
event receives mandatory HITL review. The 15-calendar-day CTR filing SLA is computed
and tracked.

---

## 5. FATF Recommendations — High-Risk Jurisdiction Monitoring

### What FATF Requires

The Financial Action Task Force (FATF) publishes lists of high-risk and monitored
jurisdictions. Financial institutions are expected to apply enhanced due diligence (EDD)
for transactions involving these jurisdictions.

### Implementation (Python — deterministic)

```python
FATF_HIGH_RISK_COUNTRIES = frozenset({
    "KP", "IR",  # FATF-identified non-cooperative (also OFAC)
    "MM",  # Myanmar — FATF grey list
    "LY",  # Libya — FATF grey list
    "SD",  # Sudan — FATF grey list
    "SS",  # South Sudan — FATF grey list
    "SO",  # Somalia — FATF grey list
    "YE",  # Yemen — FATF grey list
    "HT",  # Haiti — FATF grey list
    ...
})
```

When a wire transfer involves a FATF high-risk country, the agent:
1. Sets `high_risk_country_flag=True` and records `high_risk_country_name`
2. Triggers HITL via `HIGH_RISK_COUNTRY_WIRE` in `ALWAYS_HITL_PAYMENT_EVENTS`
3. Routes to BSA_COMPLIANCE for enhanced due diligence review

---

## 6. CFPB Prepaid Rule — Prepaid Card Disputes

For `CARD_PREPAID` payment types, the agent applies Reg E error resolution procedures.
The CFPB Prepaid Account Rule (12 CFR Part 1005, Subpart E, effective 2019) extends
Reg E protections to general-purpose prepaid accounts. The agent treats prepaid card
disputes identically to standard ACH consumer disputes for Reg E purposes.

---

## 7. UCC Article 4A — Wire Transfer Liability

Wire transfers (WIRE_DOMESTIC, WIRE_INTERNATIONAL, FEDWIRE) are governed by UCC
Article 4A (Funds Transfers), not Reg E. UCC 4A creates a different liability framework:

- The institution is liable for unauthorized payment orders only if the security procedure
  agreed with the customer was not followed (UCC 4A-202/203)
- If the customer authorized the wire (e.g., was deceived by BEC fraud), the customer
  may bear the loss if the institution followed its security procedure
- Reg E inapplicability is noted explicitly in `reg_e_assessment_node`

For commercial wire fraud (BEC), the agent routes to FRAUD_OPERATIONS and sets
`resolution_type="FRAUD_INVESTIGATION"`. The reviewer is advised to attempt a Fedwire
recall (RTRN message) within 24-48 hours of the fraud discovery.

---

## 8. SR 11-7 — Model Risk Management

The Federal Reserve's SR 11-7 (Guidance on Model Risk Management) requires that financial
institutions with material models maintain:
- Model documentation (purpose, assumptions, limitations)
- Validation by independent parties
- Human oversight of model-driven decisions

### How the Agent Satisfies SR 11-7

**Documented methodology:**
The 5-factor compliance risk scoring model is fully documented with weights and thresholds.
Each factor's weight, the reasoning for that weight, and the boundary conditions are
documented in `agent/nodes.py` comments and in this document.

| Factor | Weight | Regulatory Basis |
|--------|--------|-----------------|
| Sanctions / OFAC | 35% | OFAC regulations — highest severity |
| Unauthorized transaction | 25% | Reg E consumer protection |
| Transaction amount | 20% | CTR/SAR thresholds, escalation policy |
| SLA status | 10% | Compliance deadline management |
| Pattern / history | 10% | Prior disputes, suspicious patterns |

**Mandatory human override:**
CRITICAL and HIGH risk tier events require human review (`interrupt_before` HITL).
The human reviewer can override any automated recommendation (`OVERRIDE_RESOLUTION`).
The reviewer's decision and notes are recorded in the append-only audit trail.

**LLM boundary documentation:**
This document and the code explicitly identify which decisions are LLM-assisted vs.
Python-deterministic. The LLM is used only for narrative synthesis and document drafting
where language understanding is required and where the LLM's output assists (not replaces)
a human reviewer's judgment.

---

## 9. GLBA Safeguards Rule — Customer Information Security

The Gramm-Leach-Bliley Act Safeguards Rule (16 CFR Part 314) requires financial institutions
to implement administrative, technical, and physical safeguards for customer information.

### How the Agent Addresses GLBA

**Account number masking at intake:**
Full account numbers are masked to `****{last4}` in `payment_intake_node` before any
subsequent processing, state storage, or LLM API call. This ensures full account numbers
never appear in the LangGraph checkpoint database.

**Routing number masking:**
Routing numbers are not stored in state after intake — only the bank name (ODFI/RDFI) is
carried forward for display purposes.

**LLM API data minimization:**
LLM prompts are constructed after masking. The OpenAI API receives only masked data.
LLM system prompts explicitly instruct the model to never include full account numbers
in responses.

**At-rest encryption in production:**
See `docs/aws-deployment-guide.md` for KMS CMK encryption of Aurora (checkpoint database)
and S3 (audit trail storage).

---

## Compliance Officer Q&A

**Q: Can the LLM make a final decision on a dispute?**

A: No. The LLM provides analysis to assist the human reviewer. The human reviewer submits
the final decision (`APPROVE_RESOLUTION`, `OVERRIDE_RESOLUTION`, `ESCALATE`, or
`REJECT_CLAIM`) through the HITL interface. The graph does not proceed past the review
gate without a recognized human decision.

**Q: Can an OFAC hit be overridden by the composite risk score?**

A: No. An OFAC hit forces `compliance_risk_tier="CRITICAL"` and `compliance_risk_score=1.0`
as a hard override in `compliance_scoring_node`. No combination of other factors can produce
a lower tier. This override is implemented as a Python `if` statement, not as a parameter
in a model, so it cannot be trained away or drift over time.

**Q: How is the SAR determination made?**

A: The agent flags SAR candidates using Python (amount ≥ $5,000 + suspicious activity
indicators). It does not file SARs automatically. A BSA officer must review the SAR
candidate flag and make the filing decision. The agent's compliance narrative (LLM)
provides supporting analysis for the BSA officer's review, but the officer's judgment
is required.

**Q: Does the agent comply with the tipping-off prohibition?**

A: Yes. LLM system prompts for compliance analysis and resolution drafting explicitly
prohibit the model from disclosing an OFAC hold or SAR consideration to the customer
or originator. The HITL interface also warns the reviewer of this prohibition.
See 31 U.S.C. § 5318(g)(2) and 18 U.S.C. § 1960.

**Q: How is the audit trail protected from modification?**

A: The audit trail uses an append-only pattern. Each node creates a new list:
`list(current_trail) + [new_entry]`. LangGraph state transitions store the new list;
the previous list is read-only in the checkpoint database. Tests explicitly verify
that prior audit entries are not modified by later nodes.

**Q: What record retention applies to audit trail data?**

A: BSA requires 5-year retention for records related to SARs, CTRs, and suspicious
activity (31 CFR 1010.430). Reg E requires 2-year retention for EFT records
(12 CFR 1005.13). In production, audit trails should be exported to S3 with Object Lock
(GOVERNANCE mode, 5-year retention) to satisfy the longer BSA requirement.
