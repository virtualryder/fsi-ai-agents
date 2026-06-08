# Regulatory Compliance Framework
## Real-Time Fraud Detection Agent

---

## 1. Regulation E — Electronic Fund Transfer Act (EFTA) — 15 U.S.C. § 1693

### Overview

Regulation E (12 CFR Part 1005) governs consumer electronic fund transfers and imposes specific requirements on financial institutions when errors or unauthorized transactions occur. This agent directly affects Reg E compliance in three ways: transaction blocking, step-up authentication challenges, and disclosure timing.

### Error Resolution and Dispute Rights

When this agent blocks a consumer transaction (score ≥ 85), the consumer has the right to dispute that block as an "error" under Reg E. Implementation requirements:

| Reg E Obligation | Agent Implementation |
|-----------------|---------------------|
| Provide notice of block/hold | Reg E disclosure generated for every BLOCK decision — rendered at the digital channel or branch |
| Investigate within 10 business days | BLOCK decisions logged with timestamp to support dispute investigation window |
| Provisional credit within 10 days (if applicable) | Case record includes block reason codes for the fraud operations team's dispute workflow |
| Resolve within 45 days (complex cases) | Audit trail provides full decision record for dispute resolution |
| Written explanation if error not found | Score breakdown (rule 30% + LLM 50% + historical 20%) translates to plain-language block reason |

### Reg E Auto-Disclosure Requirement

Every BLOCK decision triggers an automatic disclosure event. The disclosure template is configurable per institution but must include:

- Transaction amount and merchant/payee
- Date and time of block
- Brief plain-language reason (not the raw score — a consumer-friendly explanation)
- Instructions for contacting the bank to resolve

```python
# From agent/nodes.py — finalize_decision_node()
# Reg E disclosure is non-optional for BLOCK decisions on consumer accounts

if decision == "BLOCK" and account_type in ["CONSUMER", "RETAIL"]:
    generate_reg_e_disclosure(
        transaction=tx,
        block_reason=generate_consumer_reason(composite_score, triggered_rules),
        channel=tx.channel  # SMS, email, push, or branch notification
    )
```

### Step-Up Authentication (STEP_UP_AUTH Decisions)

Score 65–84 → STEP_UP_AUTH: the transaction is held pending additional verification. Reg E implications:

- The hold period must be disclosed if it exceeds a reasonable delay for the transaction type
- If step-up fails and the transaction is blocked, Reg E disclosure requirements apply as above
- If step-up passes and the transaction completes, no Reg E obligation is triggered (transaction is authorized)

---

## 2. Nacha Operating Rules — ACH Transactions

### Fraud Obligations for ODFIs and RDFIs

For ACH transactions processed through this agent:

| Nacha Rule | Requirement | Agent Implementation |
|-----------|------------|---------------------|
| ODFI warranty | ODFI warrants that ACH entries are authorized | BLOCK on high-confidence unauthorized ACH protects ODFI warranty |
| Unauthorized returns (R10, R29) | RDFIs can return unauthorized ACH within 60 calendar days | BLOCK with reason code provides documentation for return decisions |
| Micro-entry authentication | Nacha micro-entry rule requires plausibility check on small-value entries | Rule engine includes micro-entry velocity check (RULE-087) |
| WEB debit authorization | Debit entries using WEB SEC code require annual authorization update | Agent flags WEB debits from accounts with stale authorization records |
| Fraud monitoring | Nacha requires ODFIs and RDFIs to implement fraud detection for ACH | This agent satisfies Nacha's fraud monitoring requirement for covered institutions |

### ACH-Specific Rule Codes

The agent's rule engine includes ACH-specific pre-score rules:

- RULE-083: ACH debit to dormant account (>180 days inactive) → automatic ANALYST_REVIEW
- RULE-084: ACH velocity >3 debits in 24 hours from same originator → STEP_UP_AUTH
- RULE-085: ACH debit amount within 1% of account balance (account drain pattern) → ANALYST_REVIEW
- RULE-086: International ACH to high-risk jurisdiction → ANALYST_REVIEW minimum
- RULE-087: Micro-entry followed by large debit within 72 hours (micro-entry fraud) → BLOCK

---

## 3. Visa / Mastercard Zero Liability and Network Rules

### Network Fraud Liability Requirements

Card network participation requires financial institutions to implement fraud detection that meets network standards. BLOCK decisions on card transactions are logged with the reason codes required by Visa's Dispute Resolution Guidelines and Mastercard's Chargeback Guide:

| Network Requirement | Agent Implementation |
|--------------------|---------------------|
| Fraud indicator on authorization | Composite score ≥ 85 → auth decline with fraud indicator code |
| Transaction monitoring obligation | 14-node dual-path pipeline satisfies Visa's fraud monitoring program requirement |
| Card Verification Value enforcement | CVV mismatch is a hard-escalation rule (RULE-071) — BLOCK regardless of composite score |
| Card-not-present authentication | 3DS results incorporated into feature extraction node |
| Chargeback documentation | Full decision audit record supports chargeback representation |

### Hard Block Rules for Card Networks

```python
# From agent/nodes.py — rule_engine_prescoring_node()
# Card-specific hard blocks — override composite score

if transaction.cvv_result == "MISMATCH":
    return RuleResult(action="BLOCK", rule_id="RULE-071", score=1.0)

if transaction.avs_result == "NO_MATCH" and transaction.amount > 500:
    return RuleResult(action="BLOCK", rule_id="RULE-072", score=1.0)

if transaction.velocity_same_merchant_15min > 3:
    return RuleResult(action="BLOCK", rule_id="RULE-073", score=1.0)
```

---

## 4. Bank Secrecy Act — SAR Consideration Flagging

### When Fraud Becomes a BSA Event

Fraud and money laundering intersect in several typologies: structuring, bust-out fraud, account takeover with subsequent mule activity, and check kiting. This agent does not file SARs — but it flags transactions that should be reviewed for SAR consideration.

**SAR Consideration Logic:**

```python
# From agent/nodes.py — finalize_decision_node()

SAR_FLAG_CONDITIONS = [
    "structuring_pattern",       # Transactions just below BSA thresholds
    "mule_network_indicator",    # Multiple accounts receiving the same fraudulent funds
    "account_takeover_confirmed", # ATO with subsequent wire/ACH out
    "check_kiting_pattern",      # Float exploitation across accounts
    "wire_fraud_typology"         # Wire to new payee, unusual destination
]

if any(flag in triggered_rules for flag in SAR_FLAG_CONDITIONS):
    escalate_to_bsa_queue(
        transaction=tx,
        decision=decision,
        sar_flag_reason=[r for r in triggered_rules if r in SAR_FLAG_CONDITIONS]
    )
```

SAR-flagged cases are forwarded to Agent 01 (Financial Crime Investigation Agent) for investigation. The 30-day SAR filing clock starts when the bank detects the suspicious activity — this agent's timestamp is the detection record.

### OFAC Hard Block

```python
# OFAC hits override composite score at any level

if transaction.ofac_sdn_match:
    return FinalDecision(
        action="BLOCK",
        reason="OFAC SDN match — mandatory block",
        ofac_flag=True,
        notify_compliance_officer=True
    )
```

---

## 5. CFPB — Fair Lending and ECOA Compliance

### Non-Discriminatory Fraud Scoring

The CFPB's fair lending authority under ECOA (15 U.S.C. § 1691) and the Fair Housing Act applies to fraud detection when scoring models use proxy variables that correlate with protected class. This agent is designed to avoid this risk:

**Protected Class Exclusions from Feature Extraction:**

| Excluded Signal | Why | What Is Used Instead |
|----------------|-----|---------------------|
| Race / ethnicity | Direct ECOA violation | Transaction behavioral pattern |
| Geographic redlining | Proxy for race | OFAC country risk (objective list), not neighborhood |
| Income level | Potential proxy | Account behavior vs. account-level baseline |
| Name / language | Proxy for national origin | No name-based features |

**What the model DOES use:**
- Transaction velocity against personal baseline (behavioral, not demographic)
- Device fingerprint consistency (technical signal, not identity)
- Merchant category risk (objective data, applied uniformly)
- IP geolocation vs. account history (behavioral pattern)
- Time-of-day consistency with account history (behavioral)

**Examiner-defensible position:** Every feature used in scoring can be demonstrated to be behaviorally derived and applied uniformly across all account holders regardless of protected class.

---

## 6. GLBA — Privacy and Data Protection

### Gramm-Leach-Bliley Act — 15 U.S.C. § 6801

GLBA requires financial institutions to protect the security and confidentiality of customer nonpublic personal information (NPI). This agent processes NPI (device identifiers, IP addresses, transaction data) and must comply with GLBA's Safeguards Rule (16 CFR Part 314).

**GLBA Safeguards Rule Compliance:**

| GLBA Requirement | Agent Implementation |
|-----------------|---------------------|
| Encryption in transit | TLS 1.3 on all API calls; SQS encryption with KMS |
| Encryption at rest | DynamoDB encrypted at rest (AES-256, AWS managed key) |
| Access controls | IAM roles with least-privilege; MCP Gateway enforces tool-level authorization |
| Vendor management | Device intelligence and IP reputation providers classified as service providers under GLBA; DPA agreements required |
| Incident response | CloudWatch alarm → SNS → fraud ops pager; DLQ triggers immediate alert |
| Data minimization | Device and IP signals are hashed before storage — raw PII not retained in fraud decision record |

### Device Fingerprint Hashing

```python
# From agent/nodes.py — device_intelligence_node()
# Raw device identifiers are hashed before storage — GLBA and CCPA data minimization

stored_device_id = hashlib.sha256(
    f"{raw_device_id}{institution_salt}".encode()
).hexdigest()
```

The hash is one-way — sufficient for velocity counting and pattern matching but not reconstructable to the raw device identifier.

---

## 7. SR 11-7 — Model Risk Management

This agent uses a composite AI model (LLM + rules + behavioral statistics) to make transaction-level decisions that directly affect customer access to funds. SR 11-7 applies.

### Conceptual Soundness

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Rule engine (RULE-001 to RULE-095) | 30% | Deterministic, auditable; encodes institution-specific fraud typologies |
| LLM behavioral analysis | 50% | Contextual reasoning across signals that rules cannot combine |
| Historical pattern score | 20% | Customer-specific baseline calibration; reduces false positives on known customers |

**Threshold rationale:**
- ≥ 85 BLOCK: High-confidence fraud; cost of false positive (customer friction) is lower than fraud loss
- 65–84 STEP_UP_AUTH: Uncertain; ask customer to verify rather than deny
- 40–64 ANALYST_REVIEW: Real-time pass but route to manual queue
- < 40 ALLOW: Low fraud probability; standard processing

These thresholds are configurable and must be documented with institution-specific backtesting results.

### Ongoing Monitoring

- CloudWatch metric: BLOCK rate by rule typology (sudden increase = possible model drift or new attack pattern)
- CloudWatch metric: false positive rate on BLOCKs (disputes filed / blocks issued)
- CloudWatch metric: real-time path latency (≥ 200ms SLA breach → alarm)
- Quarterly: review BLOCK/ALLOW decisions against confirmed fraud and chargeback outcomes

### Human Override

- Fraud Manager role can override any BLOCK decision with mandatory reason
- All overrides logged to the audit trail with the manager's identity
- Step-up authentication results are logged (pass/fail) for calibration review

---

## 8. Record Retention

| Record Type | Retention Period | Authority |
|------------|-----------------|-----------|
| All transaction scoring decisions (BLOCK/ALLOW/etc.) | 5 years | 31 CFR § 1010.430 / Reg E |
| Reg E disclosure records | 2 years (Reg E) — retain 5 years for BSA | 12 CFR § 1005.13 / 31 CFR § 1010.430 |
| SAR consideration flag records | 5 years from date of filing | 31 CFR § 1010.430 |
| OFAC hit records | 5 years | OFAC record-keeping rule |
| Device intelligence logs (hashed) | 2 years | GLBA Safeguards Rule |
| Fraud Manager override log | 5 years | SR 11-7 / BSA program documentation |
| Threshold calibration records | Life of model + 5 years | SR 11-7 |
| Model validation records | Life of model + 5 years | SR 11-7 |

---

## 9. Dual-Path Architecture and Regulatory Timing

### Real-Time Path (< 200ms) and Reg E Timing

The Reg E error resolution timeline starts from when the bank "receives" an error notice. This is distinct from when the bank processes the transaction. The real-time path decision (BLOCK, ALLOW, STEP_UP) is made before transaction completion — so a block prevents the error from occurring rather than responding to it. Regulatory implications:

- **BLOCK on real-time path:** No unauthorized transaction occurs. Reg E dispute rights do not attach to a blocked transaction, though the customer must be able to report a perceived error if they believe the block was in error.
- **ALLOW on real-time path, fraud confirmed later:** Reg E dispute rights attach. The async enrichment path may flag the transaction for ANALYST_REVIEW, but the transaction has already been authorized. The fraud operations team handles the dispute workflow using the audit trail.

### SLA Breach Handling

If the real-time path exceeds 200ms, the transaction defaults to the rule engine's fast-path decision (score based on synchronous rule results only). This prevents latency from creating regulatory exposure — no transaction is held indefinitely by the AI processing:

```python
# From agent/graph.py — real_time_path_timeout_handler()
# If real-time composite score is not available within SLA, use rule-only score

async def get_decision_with_timeout(state, timeout_ms=200):
    try:
        return await asyncio.wait_for(
            compute_composite_score(state), timeout=timeout_ms/1000
        )
    except asyncio.TimeoutError:
        return compute_rule_only_fallback(state)
```

---

## 10. Examination Preparedness

### What Examiners Will Ask About This Agent

**"How do you ensure your fraud model doesn't discriminate against protected classes?"**
- No demographic, geographic-proxy, or name-based features in the model
- Features are behavioral (velocity, device consistency, merchant pattern) and applied uniformly
- CFPB fair lending analysis is documented in the model validation report
- Adverse action codes comply with ECOA and FCRA requirements

**"How do you handle Reg E obligations when you block a legitimate transaction?"**
- Every BLOCK on a consumer account generates a Reg E disclosure automatically
- Disclosure is delivered via the customer's preferred channel
- Block reason is recorded in plain language (not raw score) for dispute investigation
- Audit trail provides complete decision record for the 10/45-day investigation windows

**"How do you prevent your fraud model from being used to launder money?"**
- SAR consideration flags are generated for structuring, mule network, and account takeover typologies
- SAR-flagged cases are forwarded to Agent 01 (BSA/AML Investigation Agent)
- OFAC SDN matches are hard-blocked regardless of composite fraud score

**"What happens if your AI model makes the wrong call?"**
- Human override available for every BLOCK decision — Fraud Manager role with mandatory reason
- Step-up authentication gives customers a chance to self-authenticate before a block occurs
- Dispute workflow accepts customer-reported errors with Reg E protection
- CloudWatch monitors false positive rate; threshold calibration is documented and reviewed quarterly

**"How are you managing model risk under SR 11-7?"**
- Factor weights and threshold selection documented with backtesting rationale
- Quarterly monitoring cadence against confirmed fraud and chargeback data
- All threshold changes require Fraud Manager authentication and are logged
- Model validation report available to examiners on request
