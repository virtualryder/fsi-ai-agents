# User Guide: Underwriters & Fair-Lending Officers (Agent 08)

*Builds on [REVIEWER-FUNDAMENTALS.md](REVIEWER-FUNDAMENTALS.md). Roles: `SENIOR_UNDERWRITER` (decision review), `FAIR_LENDING_OFFICER` (mandatory second review on flagged files).*

---

## How the recommendation is built (so you know what you're reviewing)

Five weighted factors — credit score 30%, total DTI 25%, LTV 20%, cash flow 15%, collateral 10% — produce a composite, with **hard declines in code that nothing can waive**: DTI > 50%, FICO floors by product, Chapter 7 < 2 years, OFAC match. The factor breakdown on your screen is the SR 11-7 documentation — every recommendation arrives explained, never as a bare score.

**What provably cannot move the score** (tested continuously, not just asserted): applicant name, census tract, ZIP. Matched-pair tests run in the build pipeline — two identical applications differing only in those attributes must score identically or the release is blocked. Geography has exactly one effect: flagged tracts add a **fair-lending review requirement**. Review is a control; a score change would be redlining.

## Underwriter review (`SENIOR_UNDERWRITER`)

1. **Trigger reasons first** — they tell you whether you're here for a fair-lending flag, a borderline composite, missing data, or an exception pattern.
2. **Factor panel against the file.** You're validating inputs as much as outputs: a wrong DTI in produces a wrong recommendation out, with perfect math in between. Bureau-pull anomalies and missing data route here *by design* (the system fails toward you, never past you).
3. **Your authority:** approve, modify terms, decline, or escalate. Where your judgment diverges from the composite, decide on your judgment and document why — your reasoning becomes part of the model's outcomes-analysis record, which is exactly how SR 11-7 wants override patterns captured.

## Adverse action — where precision is the legal requirement

When the outcome is a decline, the system drafts the Reg B notice. Your review checks three things, in order of regulatory consequence:

1. **Reason accuracy (CFPB Circular 2022-03):** each principal reason (1–4 of them) must be *specifically true of this applicant* — the system maps reasons to actual factor values and the eval suite tests that mapping, but you confirm against the file. "Excessive DTI" on a 38% DTI file is a violation even if the decline itself was right.
2. **Prohibited-basis language:** nothing referencing neighborhood, demographics, or any protected characteristic. The system screens for this; you're the backstop.
3. **The 30-day clock** runs from application completion regardless of anything — it's on the case header; manage it.

## Fair-lending second review (`FAIR_LENDING_OFFICER`)

Flagged files (geography, pattern triggers, or exception clusters) require your sign-off *in addition to* the underwriter's — the system enforces the sequence; neither approval alone releases the decision.

Your lens is the portfolio, not just the file:
- **Comparative context:** the case shows similarly-situated recent decisions. A decline that looks reasonable alone and inconsistent against its comparators is your call to make — Modify or Escalate with notes; your notes are the fair-lending file.
- **Monthly four-fifths review:** the adverse-impact-ratio report (selection rates by demographic coding) lands on your calendar monthly. **AIR < 0.80 on any segment is stop-the-line:** auto-dispositions on that segment halt (everything routes to human review) the same day, and a formal review opens. The threshold is the regulatory presumption line, not a dial.
- **Override-pattern watch:** if underwriter overrides cluster directionally on any protected-class-correlated dimension, raise it — human overrides are part of the fair-lending surface too, and the attributed audit trail makes the pattern visible.

## Escalation table

| Situation | Action |
|---|---|
| Disagree with a recommendation | Decide on your judgment, document — normal operation |
| Reason codes don't match file facts | Modify before any notice goes out; flag to lead (eval-suite case) |
| OFAC result looks wrong, or a hard-decline didn't fire | **Incident, immediately** (Fundamentals §6) |
| Suspected scoring pattern by geography/demographic | Fair-lending officer + lead, same day — runs through the degradation/fairness process with the platform team |
