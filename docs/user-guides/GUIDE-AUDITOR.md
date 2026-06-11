# User Guide: Internal Audit & Examination Support (`AUDITOR` role)

*Builds on [REVIEWER-FUNDAMENTALS.md](REVIEWER-FUNDAMENTALS.md). The `AUDITOR` role reads everything and approves nothing — enforced server-side, so your independence is structural, not procedural.*

---

## What you can rely on (the audit substrate)

1. **Write-ahead audit entries.** Every node in every case writes its audit entry *at the moment it acts* — not batched at case end. Entries are append-only at the database level (an entry, once written, cannot be overwritten by any code path or administrator) and carry: timestamp, agent, node, inputs summary, outputs, data sources used, and for human decisions the **verified reviewer identity** (SSO subject, not a typed name).
2. **WORM snapshots.** Full case trails snapshot to write-once storage in COMPLIANCE mode — not deletable or shortenable by anyone, including account root, until retention expires (BSA 5-year default; longer per artifact class).
3. **Model-change history.** Threshold/weight changes are code commits with approvals; prompt changes are gated by a hash manifest, so every change to what the AI was told is an explicit, dated, attributable event. "What version made this decision" always has an answer.

## The 15-minute decision reconstruction (the core procedure)

The pilot's success criterion #3 is that you can do this unassisted. For any decision — a suppressed alert, a filed SAR, a declined application, a released payment:

1. **Pull the case trail** by case/alert/application ID (UI export or DynamoDB query by entry prefix). Sort by `recorded_at`.
2. **Walk the spine:** intake → deterministic checks → scoring (with factor breakdown) → routing (with threshold values *as configured that day*) → any HITL pause → human decision → terminal action. Each hop is one entry; a missing hop is a finding (see below).
3. **Verify the human link:** the decision entry's reviewer identity is verified (`reviewer_identity_verified: true`), the role held permitted the action (role matrix in the HITL runbook), and notes/corrections are present where the decision was Modify.
4. **Verify the narrative link (AI-drafted artifacts):** the grounding report attached to the case shows the draft's claims traced to case data; reviewer corrections show what the human changed.
5. **Cross-check the WORM snapshot** object key recorded at finalization against the live trail — byte-equivalent content in immutable storage closes the loop.

## Sampling programs worth running

| Program | Question it answers | Cadence |
|---|---|---|
| Suppression sample (Agent 02) | Are auto-suppressed alerts genuinely FPs? (Re-review blind, compare) | Monthly, ≥10% |
| Reviewer-quality sample | Are approvals substantive? (Time-to-decision outliers, correction rates, identical-notes patterns) | Monthly |
| Access recertification | Do role holders match the matrix? (Okta export vs HITL role matrix) | Quarterly |
| Model-change review | Did every threshold/prompt change carry its approvals and eval evidence? (Commit + manifest history) | Quarterly |
| Fairness file (Agent 08) | AIR reports reviewed, sub-0.80 responses documented? | Monthly, with the fair-lending officer |

## Findings taxonomy — what severity to assign what you see

| Observation | Treat as |
|---|---|
| Decision entry without verified identity | **Critical** — control failure (authn), incident-class C4 |
| Gap in a case's entry spine (state moved, no entry) | **Critical** — audit-integrity, incident-class C5 |
| Terminal action with no preceding HITL entry where the trigger list required one | **Critical** — gate bypass, C1 |
| Approval pattern suggesting non-review (sub-second decisions, batch-identical notes) | High — control operating ineffectively; threshold-pressure review per HITL runbook §5 |
| Grounding flags present and approved without reviewer note | Medium — review-quality coaching + QA-sample expansion |
| Threshold change without the documented approval chain | High — model governance (SR 11-7 change control) |

## For examination support

Production posture: export the case trail(s) and WORM object references; do **not** screenshot UIs as primary evidence — the immutable record is the record. For "show me your model governance," the package is: per-agent compliance mapping (`regulatory-compliance.md`) + factor documentation (on every scored case) + the change history (commits/manifest) + the monitoring file (degradation runbook §5 records + your sampling results). You hold the last piece — keep the sampling programs current; they're the operating-effectiveness half of every control story above.
