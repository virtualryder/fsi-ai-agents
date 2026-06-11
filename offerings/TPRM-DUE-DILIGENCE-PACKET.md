# Third-Party Risk Management (TPRM) Due-Diligence Packet

**Audience:** the client's vendor risk, information security, and model risk teams.
**Scope:** the FSI AI Agent Suite deployed per `infra/terraform` (Bedrock in-VPC reference architecture).
**Posture statement:** this asset is a *production-shaped accelerator* (see README "Asset Classification"). This packet describes the controls of the **reference deployment**, distinguishes implemented-and-tested from roadmap, and is written to be attached directly to a vendor questionnaire response. Interagency third-party guidance (OCC 2023 / FRB / FDIC) treats this as a critical activity; plan due diligence accordingly.

---

## 1. System description & data flows

```
                          CLIENT AWS ACCOUNT (single-tenant)
 ┌────────────────────────────────────────────────────────────────────────────┐
 │  Corp network / VPN                                                        │
 │      │ HTTPS (TLS 1.3)                                                     │
 │      ▼                                                                     │
 │  [Internal ALB] ── authenticate-cognito (Okta SAML federated) ──┐          │
 │      │ authenticated only                                       │          │
 │      ▼                                                          ▼          │
 │  [ECS Fargate: agent task]                                [Cognito pool]   │
 │   · PII masked in-process BEFORE any LLM-bound text       custom:bsa_role  │
 │   · deterministic routing/controls (Python)               claim ◄── Okta   │
 │   · HITL approvals: server-side role check (JWT)                           │
 │      │                       │                    │                        │
 │      │ VPC endpoint          │ VPC endpoint       │ in-VPC                 │
 │      ▼                       ▼                    ▼                        │
 │  [Bedrock runtime]      [Secrets Manager]    [Aurora PostgreSQL]           │
 │   Claude + Guardrails    runtime creds        LangGraph checkpoints        │
 │   (PII anonymize,                             (HITL state survives         │
 │    prompt-attack HIGH)                         restarts)                   │
 │      │ gateway endpoints                                                   │
 │      ▼                                                                     │
 │  [DynamoDB audit: PutItem-only IAM]   [S3 Object Lock COMPLIANCE: WORM]    │
 │                                                                            │
 │  NO NAT · NO internet route in agent subnets · VPC flow logs 365d          │
 └────────────────────────────────────────────────────────────────────────────┘
```

**Data residency:** with `LLM_PROVIDER=bedrock` (the deployed default in the task definition), all inference traffic transits the `bedrock-runtime` VPC interface endpoint. No customer data leaves the client's AWS account for model processing. The accelerator's *local demo* default is the Anthropic API — that mode is for fixture data only and is stated as such in the field guide.

**Data classification handled:** customer PII (masked pre-LLM), transaction data, SAR-related material (confidential under 31 CFR 1020.320(e) — tipping-off prohibitions are encoded in agent prompts and access is role-restricted), credit application data (FCRA/ECOA).

---

## 2. Threat model (STRIDE × agent-specific)

| # | Threat | Vector | Controls (implemented = ✅ tested in CI; ◻ = deployment/roadmap) |
|---|---|---|---|
| T1 | **Prompt injection via hostile documents** | Uploaded PDFs/text steering LLM output (Agent 09 → downstream) | ✅ Deterministic routing unaffected by document text (`governance/redteam`, 5 structural tests) · ✅ PII masked before LLM-bound assembly · ◻ Bedrock Guardrail PROMPT_ATTACK filter at HIGH (IaC) · ◻ live-model red-team (see §4) |
| T2 | **Compromised/poisoned LLM output granting approvals** | Model returns attacker-shaped fields ("status: APPROVED") | ✅ LLM output cannot set decision fields — gates read schema-known, Python-computed values only (red-team test) · ✅ grounding verification flags unverifiable narrative claims |
| T3 | **Spoofed reviewer identity on HITL approvals** | Forged/absent identity approving SARs or credit actions | ✅ `require_role` fail-closed JWT verification (JWKS RS256, iss/aud/exp) · ✅ verified `sub` bound into audit trail (`record_reviewer_identity`) · ◻ ALB-level Cognito pre-auth (IaC) |
| T4 | **Audit-trail tampering / repudiation** | Insider or compromised task rewriting decision history | ✅ Write-ahead audit at entry creation · ◻ DynamoDB `attribute_not_exists` + **IAM task role grants PutItem only** (no Update/Delete — append-only even under code compromise) · ◻ S3 Object Lock COMPLIANCE (not deletable by root until retention expiry) |
| T5 | **PII exfiltration via model or logs** | "Repeat the SSN" injections; PII in traces | ✅ masking at state-write boundaries incl. ITIN range + Luhn'd PANs; leak assertions in agent tests · ◻ Guardrail ANONYMIZE on SSN/PAN/account/routing as second layer · ◻ log-redaction policy (roadmap §5) |
| T6 | **Data exfiltration from compute** | Compromised container calling out | ◻ No internet route in agent subnets; egress = VPC endpoints only; flow logs; GuardDuty |
| T7 | **Privilege escalation via tool calls** | Agent writing to systems of record beyond mandate | ✅ Accelerator has NO write-back connectors (fixtures only — stated honestly) · ◻ Phase-2 connectors require per-tool scopes + human confirmation on writes (design standard in ENTERPRISE-PLATFORM.md) |
| T8 | **Supply chain** | Malicious/vulnerable dependency | ✅ pip-audit strict in CI on all 12 agents · ✅ CycloneDX SBOM artifact per build · ◻ image signing (roadmap) |
| T9 | **Model drift / silent prompt change** | Prompt edit shifts SAR or adverse-action content without review | ✅ prompt manifest hash gate fails CI on unversioned change · ✅ golden-case evals (structure + grounding + reason-accuracy) on every build |
| T10 | **Fair-lending disparate impact (Agent 08)** | Protected-class-correlated pathway in scoring | ✅ matched-pair blindness tests through the real scorer · ✅ four-fifths AIR harness (runs on client HMDA-coded data in pilot) · ✅ flagged-tract mechanism adds *review*, provably cannot move score |

---

## 3. Vendor questionnaire pre-answers (the ten always-asked)

1. **Where is customer data processed?** Entirely within the client's AWS account (single-tenant deployment); inference via Bedrock VPC endpoint. No vendor-side processing or telemetry.
2. **Encryption?** At rest: KMS CMK (rotation enabled) across Aurora/DynamoDB/S3/logs. In transit: TLS 1.3 at the ALB; AWS-internal TLS on endpoint traffic.
3. **Authentication?** Okta SAML → Cognito federation; ALB authenticates before traffic reaches containers; application enforces role claims server-side on every HITL action.
4. **Least privilege?** Per-agent IAM task roles; audit table PutItem-only; Bedrock invoke scoped to two model IDs + named guardrail; secrets scoped to env prefix.
5. **Audit & retention?** Write-ahead audit entries (DynamoDB, append-only) + WORM snapshots (S3 Object Lock COMPLIANCE, default 5-yr BSA; 7-yr FCRA / 10-yr MRM per artifact class). NYDFS 500.06 reconstruction supported by design.
6. **Subprocessors?** AWS only in the reference deployment. Anthropic API appears ONLY in local demo mode with fixture data.
7. **AI governance?** Prompt versioning with CI gate; golden-case evals; grounding verification; fairness testing; HITL on consequential decisions; SR 11-7 mapping per agent (`regulatory-compliance.md`) and self-validation patterns (Agent 11). The platform design defines an agent catalog (SR 11-7 model inventory extension) covering agent ID/version, owner, regulatory scope, data access, LLM role boundaries, HITL conditions, model risk tier, validation schedule, and retirement criteria — see `ENTERPRISE-PLATFORM.md §Layer 3` for the full catalog schema and approval workflow.
8. **Vulnerability management?** pip-audit (strict) + SBOM in CI; checkov on IaC; pen-test plan in §4. SLA: critical findings 7 days, high 30.
9. **BCP/DR?** Aurora multi-AZ capable, 35-day backups, deletion protection; ECS multi-AZ; RTO/RPO definitions are a pilot-week-1 deliverable per client tier. ◻ DR runbook is roadmap (§5).
10. **SOC 2?** Roadmap in §5 — single-tenant in-client-account deployment means most trust-service criteria are inherited from the client's own AWS controls; SOC 2 applies to the managed-service offering when launched.

---

## 4. Penetration test plan (pilot weeks 2–3, client-witnessed)

| Phase | Scope | Method |
|---|---|---|
| P1 External | ALB, Cognito flows | OWASP ASVS L2: authN bypass, session fixation, header/TLS config, SSRF toward endpoints |
| P2 AppSec | Reviewer UI/API | AuthZ matrix per role (analyst vs BSA officer vs auditor) on every HITL action; IDOR on case IDs; mass-assignment on `update_state` paths |
| P3 **LLM red-team (live model)** | Agents 09→08/01 chain | OWASP LLM Top-10: direct + indirect injection corpora (hostile PDFs), system-prompt extraction, guardrail evasion, PII-echo attempts, cross-document context bleed; success criterion = the structural invariants from `governance/redteam` hold against a live model |
| P4 Cloud | Account config | Prowler/ScoutSuite vs CIS AWS; IAM privilege-escalation pathfinding from the task role; endpoint policy review |
| P5 Audit-integrity | DynamoDB/S3 | Attempt entry overwrite/delete with task credentials (must fail at IAM); Object Lock retention shortening attempt (must fail in COMPLIANCE mode) |

Findings feed a remediation log with severity SLAs; re-test on criticals before production-assist phase begins.

---

## 5. SOC 2 roadmap & control gaps (honest list)

**Quarter 1 (pilot-concurrent):** security policies + SDLC documentation; log-redaction standard for narrative text; DR runbook + RTO/RPO; incident response runbook *including AI incidents* (hallucinated filing content, injection detection, model outage → manual-queue fallback).
**Quarter 2:** SOC 2 Type I readiness for the managed-service variant (Security + Availability + Confidentiality); image signing + admission policy; evidence automation (audit-trail exports, eval history, manifest history as model-change log).
**Quarter 3–4:** Type II observation window; FFIEC CAT / NIST 800-53 control-ID mapping layered onto the per-agent compliance docs.

**Known gaps stated plainly:** no SOC 2 report exists today; live connectors to TMS/core/LOS are built per engagement (fixtures in the accelerator); operational runbooks are roadmap; the LLM red-team in §4 P3 has not yet been executed against a live deployment. These are priced into the pilot, not discovered during it.
