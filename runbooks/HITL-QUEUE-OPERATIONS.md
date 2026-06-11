# Runbook: HITL Queue Operations

**Scope:** day-to-day operation of human-in-the-loop review queues across all 12 agents.
**Audience:** review-team leads (BSA officers, fair-lending officers, surveillance leads, ops supervisors) and the platform team supporting them.
**Why this runbook exists:** the HITL gate is the suite's load-bearing control. A gate nobody staffs, monitors, or drains is a control on paper only — examiner findings cite *operation*, not architecture.

---

## 1. The operating model

Every agent pauses consequential cases at `human_review_gate` via a LangGraph interrupt. The paused state lives in **Aurora (PostgresSaver)** — it survives restarts, deployments, and failovers. A review is completed by an authenticated reviewer whose decision resumes the graph (`update_state(as_node="human_review_gate")`), with identity bound into the audit trail by `record_reviewer_identity` (verified JWT subject, never a typed name).

**Non-negotiable invariants:**
1. Approval requires a role the action demands (`require_role` server-side — see matrix §3). UI affordances are not controls.
2. Every decision writes a reviewer-attributed, write-ahead audit entry before the graph resumes.
3. **No bulk approve.** There is deliberately no "approve all" pathway; if reviewers ask for one, the agent's thresholds are mis-tuned — fix that instead (see §5).

## 2. Queue SLAs and monitoring

| Queue (agent) | Decision type | Review SLA | Regulatory clock behind it |
|---|---|---|---|
| 10 — Payments | OFAC hold disposition | **4 business hours** | Blocked-property reporting; funds-availability pressure |
| 04 — Fraud | High-risk transaction review | 4 business hours | Reg E provisional-credit timelines downstream |
| 08 — Credit | Fair-lending flagged application | 1 business day | ECOA 30-day notification clock runs regardless |
| 01 — FinCrime | SAR narrative approval | 2 business days | 30-day SAR filing deadline (from detection) |
| 02 — AML | Escalated alert disposition | 2 business days | Case-aging expectations in BSA exams |
| 12 — Collections | Hardship/SCRA/dispute paths | 1 business day | FDCPA/Reg F timing rules |
| 07 — Surveillance | Escalated trade alerts | 2 business days | FINRA 3110 supervision evidence |
| 03/05/06/09/11 | Standard reviews | 3 business days | Internal policy |

**Dashboards/alarms (CloudWatch, per agent):** queue depth · oldest-item age vs SLA (alarm at 75%, page at 100% for the 4-hour queues) · decisions/reviewer/day · approval-vs-modify-vs-reject mix · `reviewer_identity_verified=false` count (**alarm at ≥1** — that's a C4 incident, see `INCIDENT-RESPONSE.md`).

## 3. Role matrix (enforced by `require_role`, mirrored in Cognito `custom:bsa_role`)

| Action | Permitted roles |
|---|---|
| Approve SAR filing (01) | `BSA_OFFICER` |
| Disposition OFAC hold (10) | `BSA_OFFICER`, `SANCTIONS_OFFICER` |
| Approve flagged credit decision (08) | `SENIOR_UNDERWRITER` + second review by `FAIR_LENDING_OFFICER` when `geographic_flag` or fair-lending HITL reason present |
| Suppress/downgrade escalated alert (02) | `AML_SUPERVISOR` (analysts recommend; supervisors disposition) |
| Collections hardship/SCRA path (12) | `COLLECTIONS_SUPERVISOR` |
| View-only / QA sampling | `AUDITOR` (read access everywhere, approve nowhere) |

Quarterly access recertification: export role assignments from Okta, review against this matrix, file with internal audit.

## 4. Daily/weekly operating rhythm

**Daily (lead, 15 min):** check oldest-item age per queue against §2; rebalance assignments; eyeball the approval-mix trend (see §5 signals).
**Weekly (lead + platform, 30 min):** SLA attainment; stuck-case sweep (§6); threshold-pressure review (§5); reviewer-load fairness.
**Monthly (compliance QA):** sample ≥10% of approvals per queue for decision quality; sample audit trails for completeness (decision → entry → WORM snapshot); results feed the SR 11-7 ongoing-monitoring file (Agent 11 pattern).

## 5. Threshold pressure — the signal that tuning, not staffing, is the fix

| Signal | Reading | Action |
|---|---|---|
| Approval rate > 95% sustained 2+ weeks | Gate is rubber-stamping; thresholds too conservative — humans add no information | Propose threshold change through the model-change process (`MODEL-DEGRADATION-RESPONSE.md` §4); never widen auto-disposition informally |
| Rejection/modification rate > 30% | Agent recommendations diverging from human judgment — quality problem upstream | Open a degradation investigation; check eval results and recent prompt-manifest history |
| Queue growth despite SLA staffing | Volume shift or upstream rule change | Capacity plan; verify intake filters before adding reviewers |
| Reviewers report "approving without reading" | Control theater — worse than no control in an exam | Reduce queue volume via thresholds; rotate reviewers; this observation goes in the monthly QA file, not a hallway conversation |

## 6. Stuck and orphaned cases

A case is **stuck** when paused at the gate > 2× its SLA. Sweep weekly:
1. List paused threads (Aurora checkpoint query by agent + `interrupted_at` age).
2. Classify: unassigned (assign) · assigned-but-idle (reassign + note) · **resume-failure** (decision recorded but graph didn't advance — platform investigates checkpoint vs audit-entry mismatch; treat as C5 if entries are missing) · **upstream-data-wait** (e.g., bureau re-pull) — annotate with expected unblock date.
3. Cases stuck past a regulatory clock (SAR 30-day, ECOA 30-day) escalate to the compliance owner *that day* with the clock math attached.

**Orphaned reviewer:** departures/role changes — reassign their open cases the same day (Okta deprovisioning revokes approval ability immediately; the queue does not reassign itself).

## 7. Degraded-mode operation

- **Aurora failover (60–120s):** in-flight reviews are safe; reviewers may see one failed submit — resubmit after failover completes. No data loss; verify with a checkpoint read.
- **Agent service down:** paused cases remain reviewable is FALSE if the UI is the same service — follow `DR-RUNBOOK.md` §4; the SLA clocks in §2 do NOT pause, so leads escalate staffing on the manual fallback process.
- **Auth provider outage (Okta):** approvals stop — by design. Never set `AUTH_DISABLED` to keep a queue moving; route to the manual (pre-agent) process and record decisions there until SSO recovers. This is the documented answer to "can't we just bypass login for an hour."
