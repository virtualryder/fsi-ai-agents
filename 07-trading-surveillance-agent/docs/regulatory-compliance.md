# Regulatory Compliance Framework
## Trading Surveillance Agent

---

## 1. FINRA Rule 3110 — Supervisory Procedures

### Examiner Expectations

FINRA Rule 3110 requires every member firm to establish, maintain, and enforce a supervisory system reasonably designed to achieve compliance with applicable securities laws and regulations. For trading surveillance specifically, examiners look for:

- Written supervisory procedures (WSPs) covering each regulated activity
- Surveillance system that detects potential rule violations
- Timely review of flagged trading activity by qualified supervisors
- Documentation of review conclusions and rationale
- Escalation procedures for high-severity findings

**Agent's direct compliance function:**

| FINRA 3110 Requirement | Agent Implementation |
|------------------------|---------------------|
| Detect potentially violative trading | 8-rule Python rule engine; pattern detection across 11 alert types |
| Timely supervisor review | HITL gate with workflow pause — no HIGH/CRITICAL case proceeds without officer review |
| Document review conclusions | Disposition memorandum (LLM-drafted) + append-only audit trail |
| Escalation procedures | Deterministic routing by severity and asset class; legal escalation on CRITICAL |
| Written supervisory procedures | Surveillance rules fixture documents all detection thresholds and rationale |

---

## 2. SEC Rule 17a-4 — Books and Records

### Record Retention Requirements

SEC Rule 17a-4 requires broker-dealers to preserve specified records for defined periods. Trading surveillance records are required records:

| Record Type | Required Retention | Agent Implementation |
|------------|-------------------|---------------------|
| Surveillance alerts | 3 years (§ 17a-4(b)(7)) | Audit trail per alert; DynamoDB append-only |
| Review conclusions | 3 years | Disposition memorandum per case |
| Correspondence | 3 years | Stakeholder notification log |
| Order records | 3 years | Raw alert payload preserved in state |
| SAR documentation | 5 years (31 CFR § 1010.430) | Separate SAR record with tipping-off protection |

**Storage controls:**
- DynamoDB append-only table (IAM policy blocks UpdateItem/DeleteItem)
- S3 Object Lock COMPLIANCE mode — records cannot be deleted within retention period even by administrators
- All timestamps in UTC ISO-8601 format

---

## 3. FINRA Rule 4511 — Books and Records

FINRA Rule 4511 requires members to make and preserve books and records in conformity with SEC Rule 17a-3 and 17a-4. The surveillance agent produces the following records per Rule 4511:

- Alert identification and classification records
- Supervisory review documentation (reviewer ID, decision, timestamp, notes)
- Disposition memorandum
- SAR determination documentation

All records include the reviewer's identity and timestamp — establishing the chain of accountability required by FINRA examination staff.

---

## 4. SEC Rule 10b-5 and Section 9 — Market Manipulation and Fraud

### Pattern Detection and Regulatory Mapping

The agent's Python rule engine detects patterns associated with specific regulatory violations. The mapping is deterministic — no LLM is used for regulatory classification:

| Detected Pattern | Primary Regulations | HITL Required |
|-----------------|--------------------|--------------:|
| LAYERING_SPOOFING | SEA § 9(a)(2); Dodd-Frank § 747; CFTC 180.1 | Yes (HIGH+) |
| FRONT_RUNNING | SEA § 10(b); SEC Rule 10b-5; FINRA Rule 5270 | Yes (HIGH+) |
| WASH_TRADING | SEA § 9(a)(1); CFTC CEA § 4c(a); FINRA Rule 5210 | Yes (HIGH+) |
| INSIDER_TRADING | SEA § 10(b); SEC Rule 10b-5; 18 U.S.C. § 1348 | **Always** |
| INFORMATION_BARRIER_BREACH | Regulation FD; FINRA Rule 3110; SEA § 10(b) | **Always** |
| MARKING_THE_CLOSE | SEA § 9(a)(2); FINRA Rule 5210 | Yes (HIGH+) |
| CROSS_MARKET_MANIPULATION | SEA § 9(a)(2); CFTC CEA § 6(c); Dodd-Frank § 747 | **Always** |
| SHORT_SELLING_VIOLATION | Reg SHO Rule 203; Rule 204 | Yes (HIGH+) |
| EXCESSIVE_TRADING | FINRA Rule 2111; FINRA Rule 2010 | No (AUTO) |
| BEST_EXECUTION_FAILURE | FINRA Rule 5310; Reg NMS Rule 611 | No (AUTO) |

**Architectural enforcement:** INSIDER_TRADING, INFORMATION_BARRIER_BREACH, and CROSS_MARKET_MANIPULATION are defined in `ALWAYS_HITL_ALERT_TYPES` in `agent/nodes.py`. No code path allows these alert types to bypass human review — Python conditional logic, not LLM reasoning, enforces this constraint.

---

## 5. Dodd-Frank Section 747 — Spoofing Prohibition

Section 747 of the Dodd-Frank Act (7 U.S.C. § 6c(a)(5)) explicitly prohibits spoofing — "bidding or offering with the intent to cancel the bid or offer before execution." FINRA's parallel prohibition (Rule 5210) applies to securities markets.

**Agent's spoofing detection model (Python):**

```python
# from agent/nodes.py — pattern_detection_node
cancel_rate = float(raw.get("cancel_rate", 0))
order_count = int(raw.get("order_count", 0))
opposite_side_orders = bool(raw.get("opposite_side_orders", False))

if cancel_rate >= 0.80 and order_count >= 5 and opposite_side_orders:
    confidence = min(1.0, 0.40 + cancel_rate * 0.40 + (0.20 if opposite_side_orders else 0))
    detected.append("LAYERING_SPOOFING")
```

The detection threshold (80% cancel rate, 5+ orders, opposite-side pattern) is documented in `data/fixtures/surveillance_rules.json` per FINRA Rule 3110 WSP documentation requirements.

---

## 6. SEC Regulation SHO — Short Selling

Regulation SHO (Rules 200-204) governs short selling. Key requirements:

- **Rule 203 (Locate requirement):** Broker-dealers must have reasonable grounds to believe the security can be borrowed before effecting a short sale.
- **Rule 204 (Close-out requirement):** Failure to deliver must be closed out within specified timeframes.

**Agent detection logic:**
```python
if short_sale and not locate_obtained:
    confidence = 0.85
    detected.append("SHORT_SELLING_VIOLATION")
```

The `locate_obtained` field from the order management system is a hard required input — if False, the pattern always triggers with 0.85 confidence.

---

## 7. BSA / SAR Requirements — 31 CFR § 1023.320

Broker-dealers subject to the Bank Secrecy Act must file Suspicious Activity Reports (SARs) for transactions involving $5,000 or more where the broker-dealer knows, suspects, or has reason to suspect that the transaction involves funds from illegal activity.

**Agent SAR determination (Python — not LLM):**

```python
sar_consideration = sar_threshold_met and tier in (
    SeverityTier.CRITICAL.value, SeverityTier.HIGH.value
)
```

Where `sar_threshold_met` is:
- Notional value ≥ $5,000, AND
- Alert type is INSIDER_TRADING, WASH_TRADING, CROSS_MARKET_MANIPULATION, or UNUSUAL_ACTIVITY

**Tipping-off protection:** Per 31 U.S.C. § 5318(g)(2), the SAR system does not notify the subject of the report. The disposition memo, stakeholder notifications, and all agent outputs are designed to avoid any communication that would alert the subject to SAR consideration. The LLM system prompt explicitly prohibits any output that could constitute tipping off.

**Filing deadline:** 30 days from the date suspicious activity is initially detected. For continuing activity, a SAR must be filed every 90 days. The agent records detection timestamps in the audit trail to support deadline tracking.

---

## 8. SR 11-7 — Model Risk Management (Impact Scoring Model)

The agent uses a composite 5-factor scoring model to classify alert severity. This constitutes a model under SR 11-7 guidance.

### Conceptual Soundness

The scoring model is Python-only — no LLM is involved in severity classification. All weights are fixed in code:

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Pattern Severity | 25% | Inherent regulatory seriousness of the detected alert type |
| Trade Size / Market Impact | 25% | Larger trades have greater enforcement significance |
| Recidivism / History | 20% | Prior alerts indicate supervision failure; recidivists warrant escalation |
| Regulatory Exposure | 15% | Mandatory reporting obligations drive institutional risk |
| Evidence Quality | 15% | Corroborating signals reduce false-positive probability |

### Hard Override Rules

Hard overrides are deterministic Python conditionals — they cannot be reasoned around:

1. `INSIDER_TRADING` / `INFORMATION_BARRIER_BREACH` / `CROSS_MARKET_MANIPULATION` → CRITICAL regardless of composite score
2. `restricted_list_hit` + MEDIUM tier → escalate to HIGH
3. `prior_alert_count ≥ 6` + HIGH → escalate to CRITICAL

### Ongoing Monitoring

- CloudWatch metric: alert tier distribution (stable distribution → model working as designed)
- CloudWatch metric: HITL completion rate (all CRITICAL/HIGH reviewed within 24h SLA)
- CloudWatch metric: SAR filing rate vs. alerts (anomaly detection)
- Recommended: annual back-test of scoring thresholds vs. regulatory enforcement outcomes

---

## 9. Examination Preparedness

**"How do you ensure all potentially suspicious trading is captured?"**
- 8-rule Python rule engine covers 11 alert type patterns
- Dead Letter Queue ensures no alert is silently dropped
- Manual alert intake for off-system tips, regulatory inquiries, and whistleblower referrals
- Cross-asset class coverage: equities, fixed income, derivatives, FX, commodities, crypto

**"How do you prevent false positives from overwhelming the compliance team?"**
- 5-factor composite scoring separates LOW/MEDIUM (auto-process) from HIGH/CRITICAL (HITL)
- Market context module provides legitimate-explanation assessment before HITL escalation
- Disposition options include CLOSE_EXPLAINED and CLOSE_NO_ACTION for resolved alerts

**"How do you document supervisory review?"**
- Append-only audit trail per case with reviewer identity, decision, timestamp, notes
- Disposition memorandum retained per SEC Rule 17a-4 / FINRA Rule 4511
- All HITL decisions include mandatory reviewer ID — no anonymous approvals

**"How are you managing model risk for your scoring model?"**
- 5-factor Python model — not LLM — documented in this file and `agent/nodes.py`
- Fixed weights require code change + re-deployment; no runtime modification
- Annual scoring model review recommended vs. FINRA examination findings
- All scoring decisions logged with factor-by-factor breakdown for auditability
