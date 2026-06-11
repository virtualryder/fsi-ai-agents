# Operational Runbooks

Operational procedures for production deployments of the FSI AI Agent Suite. These close the "no runbooks" gap from the field assessment (§9) and supply the operating-effectiveness evidence behind the control architecture — examiners and SOC 2 auditors assess *operation*, not diagrams.

| Runbook | Covers | Primary owner |
|---|---|---|
| [INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md) | Control failures, AI output incidents (hallucination/injection), PII exposure, identity/authz, audit integrity, availability — classification, first-15-minutes, class procedures, regulatory comms posture | Platform on-call + compliance owner |
| [HITL-QUEUE-OPERATIONS.md](HITL-QUEUE-OPERATIONS.md) | Queue SLAs per agent, role matrix, daily/weekly rhythm, threshold-pressure signals, stuck-case sweeps, degraded-mode rules (incl. "never AUTH_DISABLED") | Review-team leads |
| [MODEL-DEGRADATION-RESPONSE.md](MODEL-DEGRADATION-RESPONSE.md) | Drift/eval/agreement monitoring for both model layers, triage tree, SR 11-7 recalibration path, prompt/model-version change procedure, monthly fairness AIR check | Model owner + compliance |
| [DR-RUNBOOK.md](DR-RUNBOOK.md) | RPO/RTO by component, AZ/component/region loss procedures, audit-trail-as-truth reconciliation, quarterly verification checklist | Platform lead |

## The operating calendar (one view)

| Cadence | Activity | Source |
|---|---|---|
| Daily | Queue age/depth check (15 min) | HITL §4 |
| Weekly | Stuck-case sweep · scorer drift metrics · SLA review | HITL §6 · Degradation §1 |
| Monthly | Compliance QA sampling · Agent 08 fairness AIR | HITL §4 · Degradation §1 |
| Quarterly | Access recertification · DR verification checklist (restore something real) | HITL §3 · DR §2 |
| Per change | Eval harness + prompt manifest + approval chain | Degradation §3–4 |
| Per incident | Post-incident review w/ compliance, ≤5 business days | Incident §6 |

## Relationship to the rest of the repo

These runbooks assume the reference deployment (`infra/terraform`), the persistence layer (`agent/persistence.py`: write-ahead audit, Aurora checkpoints), the platform auth primitives (`platform_core`), and the governance gates (`governance/`: evals, prompt manifest, fairness, grounding). Where a runbook names a behavior — "STRICT mode halts on audit write failure," "approvals stop when Okta is down" — that behavior is implemented and tested, not aspirational; the asset-classification table in the root README marks the boundary where roadmap begins.
