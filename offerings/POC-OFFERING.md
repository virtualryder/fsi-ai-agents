# Agentic AI Proof-of-Concept — Offering Definition

**Duration:** 2 weeks · **Price band:** $40K–$60K · **Team:** 1 solution architect (1.0), 0.5 compliance SME · **Environment:** Presidio-hosted sandbox or client dev account

The entry point for a risk-averse buyer who wants proof before committing to an assessment or pilot. Cheaper, faster, and lower-commitment than the assessment — one agent, the client's *sanitized* scenarios, a measured before/after, in two weeks.

## Why this exists

Some buyers won't fund a 3–4 week assessment on the strength of a demo. The POC gives them a hands-on result against their own (sanitized) cases for the price of a workshop. It is a **door-opener**, not a deployment — it de-risks the *decision to assess*, not the decision to go to production.

## Scope discipline: ONE agent, SANITIZED data, ONE measured outcome

- **One agent**, chosen for the client's loudest pain (see selection below).
- **Sanitized or synthetic scenarios** the client provides or approves — no production data, no system integration, no security review required.
- **One headline metric** measured before/after, agreed on day 1.
- Runs in a Presidio-hosted sandbox (fastest) or the client's dev account (if they prefer).

## Agent selection (pick ONE)

| Agent | Best when the buyer cares about | Headline metric |
|---|---|---|
| **09 · Document Intelligence** | Throughput / backlog; lowest sensitivity; fastest to show | Docs/hour and % auto-routed at ≥ MEDIUM confidence vs. manual baseline |
| **02 · AML/TMS triage** | Analyst overload and false positives | FP-suppression rate with full audit, and agent-vs-analyst agreement on sanitized cases |
| **06 · Regulatory change** | Compliance horizon-scanning; zero customer data | Time from publication to triaged-and-assigned vs. current process |

## Two-week plan

| Days | Activity | Output |
|---|---|---|
| 1–2 | Kickoff: pick the agent, agree the single metric and the sanitized scenario set, stand up the sandbox | Agreed success metric + scenarios |
| 3–7 | Run the agent against the scenarios; tune thresholds/prompts to the client's policy language; capture the deterministic gates firing | Working demo on the client's cases; before/after data |
| 8–9 | Compliance walkthrough: show the HITL gate, the grounding check, the audit trail; capture objections | Control walkthrough + objection log |
| 10 | Readout (exec + technical): the metric, what it would take to go further, the assessment SOW | One-page result + assessment SOW draft |

## Deliverables

1. **A working agent** running on the client's sanitized scenarios, demonstrable live.
2. **A one-page result:** the agreed metric, before vs. after, with assumptions stated.
3. **A control walkthrough:** HITL gate, grounding/fairness checks, audit trail — the examinability story made concrete.
4. **An assessment SOW draft:** the next step, scoped and priced.

## What the POC deliberately does NOT include

No production data · no integration with any system of record · no security review or TPRM process · no deployment to a production account · no claim of production-readiness. Any of these converts a 2-week door-opener into an unscoped project. The POC's honest promise is *"see it work on your cases in two weeks,"* nothing more.

## Success criteria

1. The chosen metric is measured and shown before/after on the client's scenarios.
2. A compliance stakeholder watches the human-review gate and grounding check fire and signs off that the *control model* is credible (not that the system is approved).
3. The client agrees the next step (assessment) or explicitly declines — either is a successful POC.

## Qualification

Right for a curious buyer who is **not yet ready to fund an assessment** but will engage with a concrete result. If the client is already convinced, **skip to the assessment** — don't slow a hot deal down with a POC. If the client needs production data or integration to be convinced, that's a pilot, not a POC.

## Honest-positioning rules

Same as every offering in this repo: **production-shaped accelerator**, not a product. The POC proves the *pattern* on sanitized cases. Numbers are illustrative until rebuilt on real data in the assessment. Never let a successful POC be mistaken for a deployment decision.

## Path to pilot

POC → Assessment (real baseline + prioritization) → Pilot (one agent to production candidate, real data) → Phase-1 scale-out. The POC's job is only to earn the assessment.
