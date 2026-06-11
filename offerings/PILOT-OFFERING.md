# Agentic AI Production Pilot — Offering Definition

**Duration:** 8–12 weeks · **Price band:** $250K–$400K · **Team:** 1 engagement lead (0.5), 2 engineers (2.0), 1 compliance SME (0.5), 1 DevOps/cloud (0.5)

## Scope discipline: ONE agent, REAL data, MEASURED outcome

The pilot exists to convert one workflow from demo to defensible production candidate inside the client's AWS account, and to produce the evidence pack their model-risk and audit functions need to approve scale-out. One agent. Read-mostly integration. Human approval on every action. Numbers at the end.

## Lead-agent selection (pick ONE; this is the wedge)

| Wedge | Why it wins | Measured outcome |
|---|---|---|
| **02 — AML/TMS false-positive triage** | Highest-volume pain; suppression thresholds are deterministic and reviewable; analyst time is the cleanest baseline metric | FP-triage hours per 1,000 alerts, before vs. after; agreement rate between agent disposition and analyst disposition |
| **09 — Document intelligence** | Lowest regulatory sensitivity (extraction, not decisions); feeds every other agent later; OCR/extraction baselines are easy to measure | Docs/hour throughput; field-level extraction accuracy vs. dual-key baseline; % auto-routed at ≥ MEDIUM confidence |
| **06 — Regulatory change management** | No customer data at all (public regulatory text) — shortest security review on the board; visible to the chief compliance officer weekly | Time from publication to triaged-and-assigned, before vs. after; coverage vs. their current horizon-scanning vendor |

Client risk appetite picks the wedge: aggressive → 02 (biggest number), conservative → 06 (no customer data), platform-minded → 09 (foundation for the rest).

## Phase plan

| Weeks | Phase | Exit gate |
|---|---|---|
| 1–2 | **Foundation:** deploy `infra/terraform` to client account (VPC, Bedrock+Guardrails in-VPC, Aurora checkpoints, DynamoDB/S3 WORM audit, Cognito↔Okta); security review of the TPRM packet | Infra live; security sign-off to proceed with masked production data |
| 3–5 | **Integration:** read path from the system of record (TMS export / LOS API / regulator feeds); client-tuned thresholds & policy mappings; prompt-manifest baseline recorded | Agent processing real (masked) cases in shadow mode |
| 5–8 | **Shadow run:** agent disposition vs. analyst disposition on the same cases, double-blind; weekly calibration with the client's compliance SMEs; fairness/grounding evals on every prompt change | Agreement ≥ target (set in week 1, typically 85–90% on suppressions with ZERO missed escalations) |
| 8–12 | **Assisted production:** agent output enters the real queue WITH mandatory human approval (HITL gate on, role-enforced via Cognito claims); measurement window | Final metrics pack + scale-out architecture + Phase-2 SOW |

## Success criteria (set in week 1, in the SOW, with the client's numbers)

1. **Efficiency:** ≥ X% reduction in analyst-minutes per case on the pilot workflow (target set from assessment baseline).
2. **Safety:** ZERO control regressions — no missed OFAC escalations, no HITL bypasses, no audit-trail gaps. One miss is a pilot failure regardless of efficiency numbers; say this out loud in the kickoff.
3. **Auditability:** every pilot decision reconstructable end-to-end from the WORM audit trail by the client's internal audit team, unassisted, in under 15 minutes.
4. **Model governance:** evals green on every prompt version shipped (grounding, structural, fairness where applicable); prompt manifest history = the model change log SR 11-7 wants.

## What the pilot deliberately does NOT include

Write-back to systems of record (Phase 2, after audit signs off on the read-path evidence) · multiple agents · model fine-tuning · replacement of any human approval step. Scope creep on any of these converts a winnable pilot into an unwinnable program.

## Commercial structure

Fixed fee, milestone-gated (infra live / shadow start / production-assist start / final readout). Include a pre-priced Phase-2 option (scale-out SOW at a stated band) — pricing the expansion *before* the pilot succeeds removes the renegotiation stall at the moment of maximum momentum.
