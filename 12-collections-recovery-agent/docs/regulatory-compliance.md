# Agent 12 — Regulatory Compliance Guide

## Collections & Recovery Agent: Federal and State Consumer Protection Framework

**Document Purpose:** This guide explains every federal and state consumer protection law
enforced by Agent 12, how each law is technically implemented (Python vs. LLM), and the
evidence a compliance officer or regulator can review to verify correct enforcement.

**Intended Audience:** Chief Compliance Officers, Collections Compliance Officers, Legal Counsel,
State Banking Regulators, CFPB Examiners, and Audit teams.

---

## Table of Contents

1. [Fair Debt Collection Practices Act (FDCPA)](#1-fair-debt-collection-practices-act-fdcpa)
2. [CFPB Regulation F](#2-cfpb-regulation-f)
3. [Servicemembers Civil Relief Act (SCRA)](#3-servicemembers-civil-relief-act-scra)
4. [Bankruptcy Code — Automatic Stay](#4-bankruptcy-code--automatic-stay)
5. [Fair Credit Reporting Act (FCRA)](#5-fair-credit-reporting-act-fcra)
6. [Unfair, Deceptive, or Abusive Acts or Practices (UDAAP)](#6-udaap)
7. [Telephone Consumer Protection Act (TCPA)](#7-telephone-consumer-protection-act-tcpa)
8. [IRS Debt Forgiveness Reporting](#8-irs-debt-forgiveness-reporting)
9. [Statute of Limitations (All 50 States + DC)](#9-statute-of-limitations)
10. [Human-in-the-Loop (HITL) Enforcement Architecture](#10-human-in-the-loop-enforcement)
11. [Prohibited AI Representations](#11-prohibited-ai-representations)
12. [Compliance Officer Q&A](#12-compliance-officer-qa)

---

## 1. Fair Debt Collection Practices Act (FDCPA)

**Authority:** 15 U.S.C. § 1692 et seq. | **Regulator:** CFPB (primary), FTC

### 1.1 Scope and Applicability

The FDCPA covers third-party debt collectors collecting consumer debts. Agent 12 applies FDCPA
protections to all covered debt types and implements a "when in doubt, apply FDCPA" conservative
policy for borderline classifications.

**Python classification (Node 1 — `debt_intake_node`):**

```python
# Debt types explicitly excluded from FDCPA per 15 U.S.C. § 1692a(6)
NON_FDCPA_DEBT_TYPES = frozenset({
    "MORTGAGE",           # Covered by RESPA; CFPB has separate mortgage servicing rules
    "BUSINESS_DEBT",      # FDCPA covers only consumer debts (personal, family, household)
    "STUDENT_LOAN_FEDERAL", # DOE/PSLF rules; FDCPA excluded for government debt
})

fdcpa_applies = debt_type not in NON_FDCPA_DEBT_TYPES
```

This determination is made at case intake (Node 1) and logged in the audit trail. A compliance
officer can query the DynamoDB case registry filtered by `fdcpa_applies=True` to review all
FDCPA-covered accounts.

### 1.2 Contact Time Restrictions — FDCPA § 805(a)(1)

**Statutory requirement:** No contact before 8:00 a.m. or after 9:00 p.m. in the consumer's
LOCAL time zone.

**Technical implementation (Node 2 — `fdcpa_compliance_check_node`):**

```python
import pytz
from datetime import datetime

FDCPA_PROHIBITED_HOURS_BEFORE = 8   # Before 8:00 a.m. local time
FDCPA_PROHIBITED_HOURS_AFTER  = 21  # At or after 9:00 p.m. local time (21:00)

def _check_contact_time_fdcpa(consumer_timezone: str) -> tuple[bool, int]:
    """
    Returns (contact_permitted: bool, local_hour: int).
    Fail-safe: unknown timezone returns (False, -1) — contact blocked.
    """
    try:
        tz = pytz.timezone(consumer_timezone)
        local_now = datetime.now(tz)
        local_hour = local_now.hour
        contact_permitted = FDCPA_PROHIBITED_HOURS_BEFORE <= local_hour < FDCPA_PROHIBITED_HOURS_AFTER
        return contact_permitted, local_hour
    except Exception:
        return False, -1  # Fail-safe: block contact if timezone unknown or invalid
```

**Key compliance properties:**
- Uses pytz for accurate UTC-to-local conversion, including DST transitions
- Consumer's local timezone is stored in `consumer_timezone` (IANA timezone string, e.g., `America/Chicago`)
- Unknown or invalid timezone defaults to **contact blocked** (fail-safe design)
- The local hour at time of processing is recorded in the audit trail
- A cease & desist flag **overrides** the time check: if `cease_desist_received=True`, `contact_permitted_now` is set to `False` regardless of time

### 1.3 Debt Validation Notice — FDCPA § 809 / 12 CFR 1006.34

**Statutory requirement:** Within 5 days of initial communication, send a validation notice
containing: (1) amount of debt, (2) name of creditor, (3) consumer's 30-day dispute right,
(4) verification process, (5) name/address of original creditor on written request.

**Implementation:** Agent 12 checks `validation_notice_sent` (boolean) and `validation_notice_date`.
If the notice has not been sent, an `FDCPA_VIOLATION` issue is flagged in `fdcpa_compliance_issues`
and the regulatory risk tier escalates. The validation notice text itself is **Python-injected verbatim**
into every outbound letter — the LLM does not write the disclosure language.

```python
# Verbatim validation notice text — injected by Python, not LLM
VALIDATION_NOTICE_TEXT = """
NOTICE OF DEBT VALIDATION RIGHTS

This communication is from a debt collector. This is an attempt to collect a debt.
Any information obtained will be used for that purpose.

You have the right to dispute the validity of this debt, or any portion thereof,
within 30 days of receiving this notice. If you dispute the debt in writing within
30 days, we will obtain verification of the debt and mail it to you. Upon written
request within 30 days, we will provide you with the name and address of the original
creditor, if different from the current creditor.

If you do not dispute the validity of the debt within 30 days, we will assume the
debt is valid.
"""
```

### 1.4 FDCPA Mini-Miranda — § 807(11)

Every outbound communication must identify the communication as being from a debt collector
attempting to collect a debt.

**Implementation:** Python injects the following verbatim into all collection letters before
the LLM-generated body:

```python
MINI_MIRANDA = (
    "This communication is from a debt collector. "
    "This is an attempt to collect a debt. "
    "Any information obtained will be used for that purpose."
)
```

The LLM prompt explicitly instructs the model that the mini-Miranda has already been inserted
and must not be altered or removed.

### 1.5 Prohibited Representations — FDCPA § 807

The following representations are prohibited in any collection communication. Agent 12
implements a Python constant set of prohibited phrasings reviewed against LLM outputs:

```python
FDCPA_PROHIBITED_REPRESENTATIONS = frozenset({
    "we will sue you",
    "you will be arrested",
    "legal action has been filed",
    "we are attorneys",
    "your wages will be garnished immediately",
    "this debt will never expire",  # Time-barred debt misrepresentation
})
```

When a SOL-expired account is processed, the LLM prompt is explicitly instructed:
*"Do not threaten legal action on this account — the statute of limitations has expired
and threatening suit on a time-barred debt violates FDCPA § 807(2)(A)."*

### 1.6 Cease & Desist — FDCPA § 805(c)

When `cease_desist_received=True`:
- `contact_permitted_now` is forced to `False` (overrides time check)
- `CEASE_DESIST_RECEIVED` is added to `hitl_conditions` → mandatory HITL
- Permitted communications: notification of specific remedies the collector intends to pursue
  (e.g., legal action) — nothing else
- Audit trail entry records the date and C&D flag state

---

## 2. CFPB Regulation F

**Authority:** 12 CFR Part 1006 | **Effective:** November 30, 2021 | **Regulator:** CFPB

Regulation F is the CFPB's implementing regulation for the FDCPA, adding specific numerical
limits and modern communication rules that were absent from the original 1977 statute.

### 2.1 Seven-in-Seven Rule — 12 CFR 1006.14(b)(2)(i)

**Rule:** A debt collector may not place a telephone call to a consumer more than **7 times**
within any **7 consecutive day period**.

**Technical implementation:**

```python
REG_F_7_IN_7_LIMIT = 7  # Maximum calls per 7-day period

def _check_regulation_f_compliance(prior_contacts_7_days, days_since_last_conversation):
    violations = []
    if prior_contacts_7_days >= REG_F_7_IN_7_LIMIT:
        violations.append(
            f"REG_F_7_IN_7: {prior_contacts_7_days} calls in 7 days (limit: {REG_F_7_IN_7_LIMIT})"
        )
    return violations
```

`prior_contacts_7_days` is sourced from the institution's CRM or telephony system and is
required input to the agent. The check is a Python integer comparison — not LLM judgment.

### 2.2 Post-Conversation Wait — 12 CFR 1006.14(b)(2)(ii)

**Rule:** No telephone call within **7 days** after a telephone conversation with the consumer
about the particular debt.

```python
REG_F_POST_CONVERSATION_WAIT_DAYS = 7

if 0 < days_since_last_conversation < REG_F_POST_CONVERSATION_WAIT_DAYS:
    violations.append(
        f"REG_F_POST_CONVERSATION_WAIT: {days_since_last_conversation} days since last call "
        f"(minimum wait: {REG_F_POST_CONVERSATION_WAIT_DAYS} days)"
    )
```

`days_since_last_conversation = 999` is used for accounts with no recent conversation history,
which safely passes the wait requirement.

### 2.3 Electronic Communication — 12 CFR 1006.14(h)

When electronic communications (email, SMS, social media) are used:
- Consumer must be given a clear and conspicuous opt-out mechanism
- Opt-out must be honored within 3 business days
- Limited content messages (voicemail) may not reveal the debt collection purpose

Agent 12 records `electronic_opt_out_provided` in the case state and the collection letter
template includes an opt-out footer when electronic delivery is selected.

### 2.4 Limited Content Messages — 12 CFR 1006.2(j)

Voicemail messages left for consumers may use limited content messages that do not reveal
the debt collection purpose, pursuant to Regulation F's safe harbor. Agent 12's voicemail
script template is Python-generated (not LLM) using the limited content message format.

---

## 3. Servicemembers Civil Relief Act (SCRA)

**Authority:** 50 U.S.C. § 3937 | **Regulator:** DOJ Civil Rights Division, CFPB

### 3.1 Interest Rate Cap

**Requirement:** For pre-service debts, the interest rate must not exceed **6% per annum**
during the period of active military service.

**Implementation:**

```python
SCRA_MAX_INTEREST_RATE_PCT = 6.0  # Python constant — not configurable at runtime

if state["scra_active_military"]:
    hitl_conditions.append("SCRA_DETECTED")
    escalation_level = "SUPERVISOR"
    # Balance must be recalculated; supervisor must approve before any contact
```

The SCRA rate cap note is Python-injected into the collection letter:

```python
SCRA_RATE_CAP_NOTICE = (
    "NOTICE: This account is subject to the Servicemembers Civil Relief Act (SCRA), "
    "50 U.S.C. § 3937. The interest rate applied to this debt has been reduced to "
    "6% per annum from the date you entered active military service. "
    "Excess interest previously charged has been or will be credited to your account."
)
```

### 3.2 Documentation Requirements

The servicemember must provide written notice and a copy of military orders. Agent 12 records
`scra_check_performed` (boolean) and `scra_branch` (string) in the case state. The `scra_check_performed`
flag indicates that a DoD SCRA database lookup or equivalent verification was performed — this
lookup happens outside the agent in the institution's intake workflow.

### 3.3 HITL Enforcement

`SCRA_DETECTED` is in the `ALWAYS_HITL_CONDITIONS` frozenset. This is immutable — it cannot
be removed by configuration, environment variable, or LLM output. The frozenset raises
`TypeError` if `.add()` or `.remove()` is attempted at runtime.

The supervisor who reviews an SCRA case must confirm:
1. Active duty verification has been completed
2. Interest rate has been recalculated at 6% from the date of active duty
3. Excess interest has been identified for crediting
4. Payment plan modifications have been documented

---

## 4. Bankruptcy Code — Automatic Stay

**Authority:** 11 U.S.C. § 362 | **Regulator:** U.S. Bankruptcy Courts, DOJ EOUST

### 4.1 Automatic Stay Effect

Upon filing a bankruptcy petition, an automatic stay immediately arises that prohibits:
- Commencement or continuation of collection actions
- Enforcement of judgments
- Any act to obtain possession of property of the estate
- Any act to collect, assess, or recover a pre-petition debt

**Implementation:**

```python
if state["bankruptcy_stay_active"]:
    hitl_conditions.append("BANKRUPTCY_STAY_DETECTED")
    escalation_level = "COMPLIANCE"  # Highest escalation level
    contact_permitted_now = False     # Overrides time check
```

The audit trail records: *"Automatic stay in effect — ALL collection must stop (11 U.S.C. § 362)."*

### 4.2 Permitted Actions Under Stay

The following are permissible during an active bankruptcy stay (Python-generated, not LLM):
- File proof of claim with the bankruptcy court (Agent 12 generates proof-of-claim data extract)
- Monitor bankruptcy proceedings
- Contact debtor's attorney
- Seek stay relief under § 362(d) if creditor has sufficient grounds

### 4.3 Chapter-Specific Handling

Agent 12 records `bankruptcy_chapter` (Chapter 7, 11, 13) in the case state. The compliance
officer review checklist (displayed in Tab 4 of the UI) includes chapter-specific guidance:
- **Chapter 7:** Proof of claim deadline; discharge determination
- **Chapter 13:** Repayment plan; automatic stay during plan period
- **Chapter 11:** Business reorganization; creditor committee participation

### 4.4 HITL Enforcement

`BANKRUPTCY_STAY_DETECTED` triggers the `COMPLIANCE` escalation level — the highest level,
above standard `SUPERVISOR` escalation. This escalation maps to compliance officer review
before any action is taken.

---

## 5. Fair Credit Reporting Act (FCRA)

**Authority:** 15 U.S.C. § 1681 et seq. | **Regulator:** CFPB, FTC

### 5.1 Negative Information Reporting Limits

**7-year rule:** Most negative information (delinquency, charge-off, collections) may not
remain on a consumer credit report for more than 7 years.

**Agent 12 implementation:**

```python
CREDIT_REPORTING_THRESHOLDS = {
    "min_balance_report":       100.0,   # Minimum balance to report (de minimis)
    "charge_off_days_delinquent": 180,   # Days past due at charge-off
    "medical_debt_min_balance":  500.0,  # CFPB 2025 rule: <$500 not reportable
    "paid_in_full_remove_days":    7,    # Remove within 7 days of payoff
    "settled_report_years":         7,   # Settled accounts remain 7 years
}
```

The `credit_reporting_appropriate` determination is Python-computed (Node 5):

```python
credit_reporting_appropriate = (
    balance >= CREDIT_REPORTING_THRESHOLDS["min_balance_report"]
    and days_delinquent >= 0  # Any delinquency qualifies
    and not (
        medical_debt_flag
        and balance < CREDIT_REPORTING_THRESHOLDS["medical_debt_min_balance"]
    )
)
```

### 5.2 Medical Debt — CFPB 2025 Rule

The CFPB finalized a rule in 2025 removing medical debt under $500 from credit reports.
Agent 12 implements this threshold at intake:
- `medical_debt_flag = (debt_type == "MEDICAL_DEBT")`
- If `medical_debt_flag=True` and `balance < $500.00`: `credit_reporting_appropriate = False`

This is a Python threshold comparison — not an LLM determination.

### 5.3 Audit Trail — FCRA 7-Year Retention

All case records are retained for 7 years per FCRA requirements. In production:
- S3 Object Lock GOVERNANCE mode with 7-year retention period (2,556 days)
- DynamoDB case registry with Point-in-Time Recovery (PITR) enabled
- Append-only audit trail — `list(current) + [new_entry]` pattern prevents modification

---

## 6. UDAAP

**Authority:** Dodd-Frank § 1031 (12 U.S.C. § 5531) | **Regulator:** CFPB, State AGs

UDAAP prohibits unfair, deceptive, or abusive acts or practices in connection with consumer
financial products and services.

### 6.1 UDAAP-Relevant HITL Conditions

The following HITL conditions are partially motivated by UDAAP risk:

| Condition | UDAAP Concern |
|-----------|---------------|
| `REGULATORY_COMPLAINT` | CFPB or state AG complaint → supervisor review; potential deceptive/abusive finding |
| `LITIGATION_HIGH_RISK` | Threatening suit on time-barred debt → UDAAP § 1031(d)(2) "abusive" standard |
| `DECEASED_ACCOUNT` | Collecting from an estate without proper procedures → unfair practice |
| `MINOR_ACCOUNT` | Collecting from a minor without guardian → abusive practice |

### 6.2 SOL-Expired Debt

Threatening to sue on a time-barred debt violates both FDCPA § 807(2)(A) (false representation
of legal status) and UDAAP's prohibition on deceptive and abusive practices.

When `sol_expired=True`, Agent 12:
- Reduces the collectability score's debt_age_factor by 70% (Python arithmetic)
- Flags `LITIGATION_HIGH_RISK` as **False** (cannot litigate expired debt)
- Instructs the LLM prompt explicitly: *"Do not threaten legal action — SOL expired"*
- Records the SOL status in the audit trail for regulator review

---

## 7. Telephone Consumer Protection Act (TCPA)

**Authority:** 47 U.S.C. § 227 | **Regulator:** FCC

### 7.1 TCPA Intersection with Regulation F

The TCPA prohibits placing calls using automatic telephone dialing systems (ATDS) or
prerecorded voices to cellphone numbers without express written consent. Regulation F
cross-references TCPA by requiring opt-out mechanisms for electronic communications.

### 7.2 Agent 12 Implementation

Agent 12 records `electronic_opt_out_provided` and `tcpa_consent_obtained` in the case state.
The communication letter template Python-injects an opt-out footer for all electronic
communications. TCPA consent is a prerequisite check before the agent authorizes any
automated outreach channel.

---

## 8. IRS Debt Forgiveness Reporting

**Authority:** 26 U.S.C. § 6050P | **Regulator:** IRS

When a creditor forgives a debt of $600 or more, the creditor must file IRS Form 1099-C
(Cancellation of Debt) and provide a copy to the debtor.

### 8.1 Python Threshold Check

```python
IRS_1099C_THRESHOLD = 600.0  # 26 U.S.C. § 6050P

forgiven_amount = current_balance - settlement_amount
requires_1099c  = forgiven_amount >= IRS_1099C_THRESHOLD
```

This is a Python arithmetic comparison — not LLM judgment.

### 8.2 Automatic Letter Injection

When `requires_1099c=True`, Python injects the following notice into the settlement letter:

```python
IRS_1099C_NOTICE = (
    f"IMPORTANT TAX NOTICE: The forgiveness of ${forgiven_amount:,.2f} of your debt may "
    f"constitute taxable income. You will receive IRS Form 1099-C for the cancelled amount. "
    f"Please consult a tax professional regarding your tax obligations."
)
```

---

## 9. Statute of Limitations

### 9.1 SOL Overview

The statute of limitations limits the creditor's right to sue to collect a debt. It does
**not** eliminate the debt — voluntary payment is still permissible in most states. However,
threatening to sue after SOL expiration violates FDCPA § 807(2)(A).

### 9.2 State SOL Matrix

Agent 12 contains a Python constant `STATE_SOL_YEARS` covering all 50 states + DC with
four debt categories:
- `written_contract` — personal loans, auto loans, installment agreements
- `open_account` — credit cards, revolving credit, retail installment
- `oral_contract` — rare in commercial collections
- `judgment` — post-judgment renewal periods

**Example values:**

| State | Credit Card (Open Account) | Personal Loan (Written) | Judgment |
|-------|---------------------------|------------------------|----------|
| CA    | 4 years                   | 4 years                | 10 years |
| NY    | 6 years                   | 6 years                | 20 years |
| OH    | 6 years                   | 6 years                | 5 years  |
| TX    | 4 years                   | 4 years                | 10 years |
| FL    | 5 years                   | 5 years                | 20 years |

### 9.3 SOL Clock Reset

The SOL clock restarts from the **date of last payment** in most states. Agent 12 uses
`max(debt_origination_date, debt_date_of_last_payment)` as the SOL start date.

```python
sol_start = max(origination_date, last_payment_date)
sol_expiration = sol_start.replace(year=sol_start.year + sol_years)
sol_expired = today > sol_expiration
sol_warning = not sol_expired and (sol_expiration - today).days <= 90
```

### 9.4 SOL Warning (90-Day Horizon)

When `sol_warning=True`, the supervisor review includes a notice: *"SOL expires within 90
days — litigation decision must be made promptly or the right to sue will be lost."*

### 9.5 NY and WI Note

New York and Wisconsin have enacted statutes that bar collection activity entirely on
time-barred debt (not just limiting the right to sue). The LLM strategy prompt for NY/WI
accounts with expired SOL includes explicit guidance to review state-specific restrictions
with legal counsel.

---

## 10. Human-in-the-Loop Enforcement

### 10.1 Architecture Overview

Agent 12's HITL system has three independent enforcement layers:

**Layer 1 — ALWAYS_HITL_CONDITIONS frozenset (Python runtime)**

```python
ALWAYS_HITL_CONDITIONS = frozenset({
    "SCRA_DETECTED", "BANKRUPTCY_STAY_DETECTED", "DISPUTE_RECEIVED",
    "CEASE_DESIST_RECEIVED", "DECEASED_ACCOUNT", "SETTLEMENT_HIGH_VALUE",
    "LITIGATION_HIGH_RISK", "REGULATORY_COMPLAINT", "MINOR_ACCOUNT",
})
# frozenset is immutable — .add() raises TypeError at runtime
```

**Layer 2 — Routing fail-safe (Python identity check)**

```python
def _route_after_routing_decision(state) -> str:
    # Only explicit Python False bypasses HITL gate
    # None, 0, missing key, empty string → HITL
    if state.get("human_review_required") is False:
        return "communication_drafting"
    return "human_review_gate"
```

**Layer 3 — LangGraph compile-time interrupt**

```python
return workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_review_gate"],
)
```

The `interrupt_before` directive causes the LangGraph runtime to **physically pause** the
graph before executing `human_review_gate`. This is not application code — it is the
LangGraph checkpoint and interrupt mechanism. The graph cannot execute nodes 11 and 12
(`communication_drafting`, `audit_finalize`) until the human review gate runs.

### 10.2 HITL Conditions — Regulatory Mapping

| Condition | Regulatory Trigger | Escalation | Permitted Actions |
|-----------|-------------------|------------|-------------------|
| `SCRA_DETECTED` | 50 U.S.C. § 3937 | SUPERVISOR | Modified payment plan at 6%; recalculate balance |
| `BANKRUPTCY_STAY_DETECTED` | 11 U.S.C. § 362 | COMPLIANCE | Proof of claim; attorney contact only |
| `DISPUTE_RECEIVED` | FDCPA § 809 | SUPERVISOR | Validation materials; 30-day hold |
| `CEASE_DESIST_RECEIVED` | FDCPA § 805(c) | SUPERVISOR | Legal action notice only |
| `DECEASED_ACCOUNT` | State probate law | SUPERVISOR | Estate/executor contact only |
| `SETTLEMENT_HIGH_VALUE` | Internal policy | SUPERVISOR | Authorization per tier auth_level |
| `LITIGATION_HIGH_RISK` | Risk management | SUPERVISOR | Legal review before collection |
| `REGULATORY_COMPLAINT` | UDAAP / Dodd-Frank § 1031 | COMPLIANCE | Compliance officer review |
| `MINOR_ACCOUNT` | State consumer law | SUPERVISOR | Legal guardian contact only |

### 10.3 What LLM Cannot Do

The LLM (GPT-4o) in Agent 12 cannot:
- Set `human_review_required` to `True` or `False`
- Add or remove conditions from `ALWAYS_HITL_CONDITIONS`
- Determine `contact_permitted_now`
- Compute payment amounts or settlement discounts
- Set `collections_outcome`
- Override SOL status
- Bypass the HITL gate

The LLM can only produce: hardship assessment narrative, collections strategy narrative,
collection letter body (with Python-injected mandatory disclosures).

---

## 11. Prohibited AI Representations

### 11.1 Federal Standards

Per the CFPB's Circular 2023-2 (AI/ML in Consumer Financial Services), AI-generated
collection communications that are inaccurate or misleading may constitute UDAAP violations.

Agent 12 mitigates this risk through:
1. All financial amounts in letters are Python-computed values — not LLM text
2. All regulatory disclosures (mini-Miranda, validation notice, SCRA notice, 1099-C) are
   Python-injected verbatim strings — not LLM-generated
3. LLM prompts explicitly instruct the model not to state specific dollar amounts or
   payment terms — those are provided as structured variables
4. PII masking at intake ensures the LLM never sees raw account numbers or SSNs

### 11.2 Time-Barred Debt Prohibition

FDCPA § 807(2)(A) prohibits false representation of the character, amount, or legal status
of any debt. Threatening to sue on a time-barred debt is a per se violation.

When `sol_expired=True`, the LLM prompt includes:

```
CRITICAL COMPLIANCE CONSTRAINT: The statute of limitations on this debt has expired
(SOL expiration: {sol_expiration_date}). Under FDCPA § 807(2)(A), you MUST NOT
threaten, suggest, or imply that legal action is possible or likely. Do not use
language such as "legal action," "litigation," "court," "judgment," or "attorney"
in this communication.
```

---

## 12. Compliance Officer Q&A

**Q: Can the LLM decide whether to contact a consumer?**

No. Contact decisions are made by Python only:
- `contact_permitted_now` = `pytz` timezone check (FDCPA § 805(a)(1))
- `cease_desist_received = True` → contact blocked (FDCPA § 805(c))
- `bankruptcy_stay_active = True` → contact blocked (11 U.S.C. § 362)
- `scra_active_military = True` → supervisor must approve before contact

The LLM only generates letter content after the Python contact decision has been made.

---

**Q: How do we prove that HITL conditions cannot be bypassed?**

Three mechanisms provide evidence:
1. **frozenset immutability:** `ALWAYS_HITL_CONDITIONS` is a Python frozenset. Any code
   attempting `.add()` or `.remove()` raises `TypeError`. Unit test `TestSecurityProperties`
   verifies this: `pytest tests/test_nodes.py::TestSecurityProperties -v`
2. **Routing fail-safe:** `_route_after_routing_decision` uses `is False` identity check.
   Unit tests verify `None`, `0`, `""`, and missing key all route to HITL. Run:
   `pytest tests/test_graph.py::TestRoutingFunctions -v`
3. **LangGraph interrupt:** The compiled graph has `interrupt_before=["human_review_gate"]`.
   The LangGraph checkpoint log shows the pause before Node 10.

---

**Q: How is PII protected from appearing in LLM prompts?**

Node 1 (`debt_intake_node`) performs masking before any subsequent node executes:
- Account numbers → `ACCT-****{last4}` (e.g., `ACCT-****9874`)
- SSNs (when present) → `SSN-***-**-{last4}`
- Consumer names are stored only as masked first initial + last initial (e.g., `Jennifer M.`)

The masked identifiers are the only values passed to LLM prompts. Raw account numbers
and SSNs are never in any LLM prompt. This is verifiable in `agent/nodes.py` →
`debt_intake_node`.

---

**Q: What happens if OpenAI's API is unavailable?**

LLM nodes (`consumer_profile`, `collections_strategy`, `communication_drafting`) will raise
an exception. The LangGraph checkpointer preserves state at the last successful node.
When the LLM recovers, the pipeline can resume from the checkpoint without re-running
Python nodes. The HITL decision remains unaffected — it is made after the LLM nodes.

In production, set `llm=None` to run in fallback mode: LLM nodes return placeholder
narrative text, and the Python pipeline runs fully for routing, HITL, and compliance decisions.

---

**Q: How are audit records protected from tampering?**

1. **Append-only in memory:** `audit_trail = list(state["audit_trail"]) + [new_entry]`
   — the list is reconstructed (not mutated) at each node
2. **S3 Object Lock GOVERNANCE mode:** Objects cannot be deleted or overwritten for the
   retention period without explicit S3 administrator override with MFA
3. **DynamoDB PITR:** Point-in-Time Recovery enables restoration of any record to any
   second within the 35-day PITR window
4. **CloudTrail:** All S3 Object Lock API calls are logged in AWS CloudTrail for regulator
   access

---

**Q: How do we handle the CFPB's 2025 medical debt credit reporting rule?**

The $500 minimum balance threshold for medical debt credit reporting is implemented as a
Python constant (`medical_debt_min_balance = 500.0`) in `agent/state.py`. The check is:

```python
credit_reporting_appropriate = not (medical_debt_flag and balance < 500.0)
```

This runs in Node 5 (`debt_validation_node`). When `credit_reporting_appropriate=False`,
the communication letter template omits credit reporting references and the supervisor
review checklist notes the reporting restriction.

The threshold constant can be updated in `agent/state.py` if the CFPB modifies the rule —
no LLM prompt changes are required because the LLM does not make credit reporting decisions.

---

**Q: What is the evidence chain for FDCPA contact time compliance?**

For each case, the audit trail entry for Node 2 (`fdcpa_compliance_check`) records:
- `contact_permitted_now` (True/False)
- `local_hour` (integer, consumer's local time at processing)
- `consumer_timezone` (IANA string used for conversion)
- `regulation_f_violations` (list, may be empty)
- Timestamp of the check (UTC ISO 8601)

This provides a complete evidence chain: the consumer's timezone, the UTC time at
processing, the derived local hour, and the resulting contact permission decision —
all Python-computed and logged before any communication is drafted.

---

*Document version: 1.0 | Agent 12 — Collections & Recovery Agent | FSI AI Suite*
*Regulatory citations current as of: June 2026*
