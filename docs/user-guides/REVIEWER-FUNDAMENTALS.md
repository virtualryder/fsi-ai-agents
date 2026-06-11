# Reviewer Fundamentals — Read This First

**Who this is for:** anyone who reviews, approves, or works cases produced by any of the 12 agents. Your persona guide (BSA/AML, credit, operations, auditor) builds on this one.

---

## 1. What the agent does — and what it never does

The agent **prepares** your decision: it gathers the case, runs the deterministic checks (sanctions screens, threshold math, timing rules), and drafts the narrative or letter. It **never takes** the consequential action. Every SAR filed, payment held or released, credit decision issued, or collection path chosen passes through a human gate — usually you.

Two layers do the work, and knowing which produced what tells you how to read it:

- **Deterministic layer (Python rules):** screening results, scores, threshold routing, regulatory timing checks. These are exact, version-controlled, and tested. If a sanctions flag shows on your screen, code set it — the AI cannot set or clear it.
- **Drafting layer (the AI):** narratives, summaries, letters. Useful, usually accurate, **and reviewable precisely because it can be wrong.** That's why you're here.

## 2. Your queue, your decisions

Cases reach you because a rule said they must (a "HITL trigger" — e.g., OFAC hold, fair-lending flag, low confidence, high amount). The trigger reasons are listed on the case — read them first; they tell you what the system is unsure about or required to escalate.

Your decision options (names vary slightly by agent):
- **Approve / Approve & Route** — you reviewed it and the recommendation and draft are right.
- **Modify / Correct & Route** — right outcome, wrong details; your corrections are saved and attributed to you.
- **Reject** — wrong outcome or unusable draft; the case exits with REJECTED status and your notes.
- **Escalate** — outside your authority or judgment call you shouldn't make alone; routes upward.

**There is no bulk approve, deliberately.** If your queue feels like rubber-stamping, tell your lead — the fix is tuning the system's thresholds (a controlled change), not clicking faster. A gate everyone clicks through without reading is worse than no gate in an examination.

## 3. Your identity is part of the record

You sign in through the institution's SSO (Okta). Every decision you make is recorded with your **verified identity** — not a typed name — plus timestamp, the case state you saw, and your notes/corrections, in an audit trail that cannot be edited afterward by anyone, including administrators. Treat every approval as the regulatory signature it is.

Practical consequences:
- Never share a session or approve "for" someone else.
- Never approve from a screen you didn't read. "The AI is usually right" is not a review.
- If you're asked to work around the login or the gate "just this once" — that's a reportable event, not a favor. (Operations has a documented "no" for this; see your lead.)

## 4. Reading an AI draft like a reviewer

1. **Check the trigger reasons first** — they frame what to scrutinize.
2. **Verify the numbers against the case facts panel.** The system runs an automatic grounding check and flags claims it can't trace to case data — anything flagged is YOUR verification burden before approval. An unflagged draft is not a guarantee; it's a head start.
3. **Check what's missing**, not just what's there. The AI drafts from the data it was given; if you know context the case lacks, Modify and add it.
4. **Names, dates, amounts get character-level attention.** These are where a wrong draft does regulatory damage.

## 5. When unsure — the standing rule

**Unsure routes up, never through.** Escalate is always a correct answer; a wrong Approve never is. Nobody's metrics are damaged by escalation — the SLA framework expects it, and the audit trail makes thoughtful escalation look exactly like what it is.

## 6. If something looks broken

Wrong screening result, a case that won't load, a decision that didn't "take," a draft containing someone else's data — **stop, don't retry around it,** note the case ID and time, and contact your lead/platform support. Retrying can complicate the evidence trail; reporting preserves it. (Behind the scenes this triggers the incident runbook — your case ID and timestamp are exactly what responders need.)
