# User Guide: BSA Officers & AML Analysts (Agents 01 & 02)

*Builds on [REVIEWER-FUNDAMENTALS.md](REVIEWER-FUNDAMENTALS.md). Roles: `AML_SUPERVISOR`, `BSA_OFFICER`; analysts work and recommend, supervisors and officers disposition.*

---

## Agent 02 — Alert triage (your queue shrinks; your judgment doesn't)

**What it does with the TMS feed:** every alert gets a composite false-positive score from three components — rule-based prescore, **historical FP rates for this rule/customer profile**, and an AI contextual read. Thresholds then route it: clear FPs are suppressed *with full documentation*, mid-band alerts are downgraded in priority, genuine concerns escalate, and everything uncertain **passes through to you unchanged**.

**Guardrails you can rely on (and verify):**
- **Sanctions/PEP alerts are never auto-suppressed.** Hard rule in code, regardless of score.
- **Higher-risk customers are harder to suppress** — a VERY_HIGH-risk customer's alert needs 12 more points of FP confidence than baseline.
- **The AI cannot suppress alone.** Auto-suppression requires the deterministic components AND the AI read to agree; disagreement routes to an analyst. So when an alert reaches you marked "component disagreement," that's the system telling you the easy explanations failed — start there.

**What "suppressed" means for your exam file:** suppressed ≠ deleted. Every suppression carries its score breakdown, factors, and threshold math in the immutable audit trail, samplable by QA and producible to an examiner. Your monthly QA sample (≥10%) is the control that keeps suppression honest — take it seriously; it's your evidence the model isn't drifting (missed-SAR tolerance is **zero**; one confirmed miss is an incident, not a statistic).

**Your disposition on escalated alerts:** the score panel shows which component drove the escalation. Disagreeing with the system is fine and expected — your disposition is the ground truth that the model's agreement-rate monitoring runs against. Disposition honestly, not defensively.

## Agent 01 — Investigation & SAR drafting

**The case file you open** already contains: transaction assembly, KYC context, prior SAR history, screening results, and a draft narrative structured to FinCEN's expectations (who / what / when / where / why suspicious / disposition).

**Reviewing the draft narrative — the four-pass method:**
1. **Facts pass:** every amount, date, account, and name against the evidence panel. The grounding check flags anything it couldn't trace to case data — those flags are mandatory verification, but do your own spot-checks too; the check catches fabrication, not misemphasis.
2. **Suspicion pass:** does the "why suspicious" section reflect *your* assessment? The AI articulates patterns; **the suspicion determination is yours**. If you'd characterize it differently, Modify — your wording controls.
3. **Completeness pass:** what does the narrative omit that you know? Prior contacts, branch observations, context from the relationship — add it.
4. **Tipping-off pass:** confirm nothing in any customer-facing output references the SAR (the system enforces this separation; you're the backstop).

**Filing approval is `BSA_OFFICER`-only** and is the regulatory signature on the filing. The 30-day clock from detection is tracked on the case header; cases at 2× SLA age escalate automatically, but the clock is yours to manage — the system counts days, it doesn't own them.

**Confidentiality:** SAR cases are visible only to roles with BSA access. Don't export case content outside the system; the WORM audit trail is the official record and the examiner-production path.

## What to escalate to the platform team vs. work through

| Situation | Action |
|---|---|
| You disagree with a score | Disposition normally — that's data, not a defect |
| Same wrong pattern repeatedly (e.g., a merchant type always over-escalated) | Tell your lead → threshold-change process (controlled, documented) |
| A sanctions-flagged item appears suppressed, any screening looks wrong | **Stop. Incident, immediately.** (Fundamentals §6) |
| Draft cites facts not in evidence and not flagged | Reject, note it — it becomes a training case for the eval suite |
