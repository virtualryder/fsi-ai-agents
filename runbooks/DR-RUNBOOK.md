# Runbook: Disaster Recovery

**Scope:** loss of infrastructure components or the full region for an agent deployment (reference: `infra/terraform`).
**Prime directive:** the agents are *decision-support with human gates*, and every institution retains its pre-agent manual process as a deployment precondition (pilot SOW term). DR for this system therefore optimizes for two things in order: **(1) zero loss of audit/decision evidence, (2) clean failback** — raw speed of restoring the agents is third, because the manual fallback bounds business impact from minute one.

---

## 1. Objectives by component

| Component | RPO | RTO | Mechanism |
|---|---|---|---|
| Audit entries (DynamoDB) | ~0 (write-ahead; STRICT mode halts on write failure) | 1 h read access | PITR (enabled in IaC) + on-demand backups |
| WORM snapshots (S3 Object Lock) | 0 (versioned, COMPLIANCE-locked) | n/a (read-anywhere) | Cross-region replication to a second Object Lock bucket (enable per client tier) |
| HITL/graph state (Aurora) | ≤ 5 min | 2 h | Multi-AZ failover (auto, 60–120 s) for AZ loss; snapshots + 35-day PITR for worse |
| Agent services (ECS) | n/a (stateless) | 2 h | Redeploy from ECR images via Terraform |
| Inference (Bedrock) | n/a | n/a | AWS-managed; regional outage handled in §5 |
| Identity (Cognito/Okta) | n/a | per IdP | Okta outage ⇒ approvals stop by design (see queue runbook §7 — never AUTH_DISABLED) |

**Declared tiers:** AZ loss → automatic, verify only (§3). Single-component corruption → §4. Region loss → §5 (decision: restore-in-region-B vs ride-out-on-manual, made by the business owner using §5's table).

## 2. What must be true BEFORE an event (quarterly verification checklist)

- [ ] Aurora automated snapshots present and restorable (actually restore one to a scratch cluster quarterly — an unrestored backup is a hope, not a control)
- [ ] DynamoDB PITR enabled; one point-in-time restore exercised to a scratch table
- [ ] ECR images for current task definitions replicated to the DR region (ECR replication rule)
- [ ] Terraform state backend versioned + replicated; `terraform plan` runs clean against prod (no drift)
- [ ] Cross-region S3 replication healthy for the WORM bucket (where enabled)
- [ ] Manual-fallback contact tree current (the people who run the pre-agent process)
- [ ] This runbook exercised as a game-day (at minimum tabletop) — date recorded: ______

## 3. AZ loss (automatic — verify, don't act)

1. Aurora fails over automatically (60–120 s). Verify: writer endpoint resolves; a HITL submit succeeds.
2. ECS reschedules tasks onto the surviving AZ subnets; verify ALB healthy-host count.
3. Audit sink: confirm zero STRICT-mode write failures in the window (`persistence.py` logs); any node that halted mid-write resumes from its checkpoint. A re-run appends NEW entries rather than mutating old ones — the trail visibly shows the re-execution, which is the correct audit posture (append-only means the history of the recovery is itself recorded; nothing is deduplicated away).
4. Note the event; no recovery actions required.

## 4. Single-component loss/corruption

### Aurora cluster unrecoverable
1. Stop agent services (prevents new graph activity against a dead checkpointer).
2. Business switches to manual fallback for NEW work; SLA clocks keep running (queue runbook §7).
3. Restore cluster from latest snapshot/PITR to the RPO point; update the `DATABASE_URL` secret; restart services.
4. **Reconcile the RPO gap (the important step):** the write-ahead audit trail in DynamoDB is the source of truth for everything that happened — including the ≤5 min Aurora may have lost. For each case with audit entries newer than the restored checkpoint: if the audit shows a completed terminal node, mark/complete it from evidence; if it shows a HITL decision the checkpoint lacks, re-apply via `update_state`; if mid-pipeline, re-run from intake (idempotent audit makes the re-run safe). Log every reconciled case.

### DynamoDB audit table impaired
1. STRICT mode means agents are already halting on write failure — this is correct behavior, not the problem. Manual fallback for new work.
2. Restore via PITR to a new table; repoint `AUDIT_DYNAMODB_TABLE`; restart.
3. Gap check: local JSONL write-ahead files (the always-on layer) cover the window — replay any entries missing from the restored table, then snapshot the reconciled trail to WORM.

### ECS/agent compromise or bad deploy
Stateless: `terraform apply` with the last-known-good image tag. For suspected compromise, follow `INCIDENT-RESPONSE.md` first (preserve, then rebuild from clean images — never patch a suspect container in place).

## 5. Regional loss

**The decision, not the procedure, is the hard part.** Convene: business owner + compliance owner + platform lead. Inputs:

| Factor | Ride out on manual | Restore in region B |
|---|---|---|
| Expected AWS region recovery | < 1 business day | multi-day |
| Queue regulatory clocks | none near breach | SAR/ECOA/Reg E clocks at risk |
| Data residency constraints | — | confirm region B is contractually/regulatorily permitted BEFORE restoring (some client agreements pin the region; check the SOW) |

**Restore-in-B procedure (target: 1 business day):**
1. `terraform apply` the env composition in region B (modules are region-agnostic; provider var). Bedrock model IDs and the Guardrail must exist in B — the quarterly checklist verifies model availability there.
2. Restore Aurora from cross-region snapshot copy; restore DynamoDB from backup; WORM replica bucket becomes primary (its COMPLIANCE locks traveled with replication).
3. Repoint Okta SAML to the new Cognito endpoints (pre-staged second IdP app keeps this to minutes).
4. Reconcile per §4-Aurora step 4 (the audit trail is region-portable truth).
5. Resume agents in the pilot-wedge order (06 → 09 → 02 → rest): lowest-sensitivity first proves the stack before payments/credit traffic returns.

## 6. Failback and evidence

Failback to the home region is a planned change (normal CI/CD path), never an emergency. Within 5 business days of any DR event, file: timeline, RPO/RTO achieved vs target, reconciliation log (every case touched in §4/§5 step 4), and checklist deltas — this file is the operational-resilience evidence FFIEC examiners ask for, and the reason §2 gets exercised quarterly rather than admired annually.
