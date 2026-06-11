# User Guide: Operations Teams — Documents, Payments, Collections (Agents 09, 10, 12)

*Builds on [REVIEWER-FUNDAMENTALS.md](REVIEWER-FUNDAMENTALS.md). Roles: ops analysts, `SANCTIONS_OFFICER`/`BSA_OFFICER` (OFAC holds), `COLLECTIONS_SUPERVISOR`.*

---

## Agent 09 — Document intake review

**What happens before you see anything:** classification (what kind of document), extraction (fields + per-field confidence), validation, and **PII masking** — sensitive identifiers are masked before the AI ever reads the text and before anything lands in stored state. The masked tokens you see (`[SSN-MASKED]`, `[CARD-MASKED]`) are the system working, not a display bug.

**Your queue = the uncertainty:** UNKNOWN types, low-confidence extractions, validation failures, and oversized/unsupported intakes. Confident documents route straight through — by design, you see the hard 10–20%, not the easy 80.

**Reviewing an extraction:** the panel shows each field, its confidence, and the source snippet it came from. Correct fields inline (**Correct & Route**) — your corrections are attributed and feed accuracy measurement. Two habits that matter:
- Low-confidence fields are flagged, but *verify a sample of confident fields too* — confidence is the model's self-assessment, and your corrections are how we find out where it's overconfident.
- **Reject** unusable documents (illegible, wrong document entirely, suspected tampering) rather than heroically correcting them — REJECTED status with your notes triggers re-request workflows; a heavily hand-corrected garbage document poisons downstream agents that trust routed data.

**A document with weird embedded instructions** ("ignore previous instructions…", system-prompt-looking text): route it as its facts dictate — the routing provably ignores such text — but flag it to your lead; attempted injections are tracked.

## Agent 10 — Payment disputes & OFAC holds

**Dispute intake (Reg E):** the system assembles the dispute, checks the timing rules (notification windows, the 10-business-day provisional-credit clock), drafts the analysis, and routes anything ambiguous to you. The Reg E clocks on the case header are computed by code from the notification date — if a date looks wrong, fix the *date*; the clock math recomputes. Never hand-calculate around it.

**OFAC holds — the 4-hour queue (`SANCTIONS_OFFICER`/`BSA_OFFICER` only):**
- A hold means screening matched a party OR **screening data was missing** — the system holds when it *can't clear*, not only when it can match. "Insufficient data to screen" is a real hold reason; the resolution is obtaining the data, never waving the payment through.
- Your dispositions: confirm match (→ blocking/reporting procedures), reject as false positive (with your reasoning — name-similarity logic, not vibes), or request more information.
- **Nothing un-holds a sanctions hold except your explicit disposition.** No score, no AI output, no downstream process clears it. If you ever observe a held payment moving without a disposition in its trail — incident, immediately.

## Agent 12 — Collections oversight (`COLLECTIONS_SUPERVISOR`)

This agent is pure rules — FDCPA contact-frequency math (7-in-7), permissible-hours by the debtor's timezone, state statute-of-limitations tables, SCRA rate caps, bankruptcy-stay handling. **No AI drafts collection strategy.** Your queue is the paths the rules require a human on:

- **Hardship/dispute/cease-communication requests:** the rules stop automated contact instantly; your judgment sets the human path.
- **SCRA flags:** verify service status, apply the 6% cap workflow, document.
- **Bankruptcy notices:** confirm the stay is honored end-to-end (all automated contact halted) and route to the appropriate handling.
- **SOL-expired or near-expiry debt:** the state-by-state computation is on the case; expired debt routes to you because *collecting on it has legal exposure* — the system will not pursue it automatically, and reviving it is a documented supervisory decision, not a queue click.

**The thing to internalize:** in this agent, a blocked action is almost always the law, not a bug. When an account "won't let you" schedule a contact, read the rule citation on the block before asking for an override — the override request you'd be making is usually "may I violate Reg F," and the answer is in the citation.

## Shared escalation table

| Situation | Action |
|---|---|
| Field extraction wrong | Correct & Route — normal operation, attributed |
| Reg E / FDCPA clock looks wrong | Check the input date first; if math itself is wrong → lead + platform same day |
| Sanctions hold cleared without disposition, PII visible unmasked, payment moved past a hold | **Incident, immediately** (Fundamentals §6) |
| Same document type failing repeatedly | Lead → likely a schema/template addition, a controlled change |
