# Objection Handling — FSI Agentic AI Accelerator

For sellers, solution architects, and client principals. Each objection lists **who raises it**, the **honest response**, and the **proof point in this repo** the client's own technical team can verify. The asset's credibility is the differentiator — never answer an objection with a claim the code can't back.

> Standing frame: this is an **agentic AI modernization accelerator** — a repeatable demo, architecture, and GTM foundation — not a production-ready regulated platform. Most objections dissolve once the buyer understands you are selling a *governed path to production*, not a finished product.

---

## 1. "Isn't AI too risky in a regulated workflow? Our examiners will block it."
**Who:** CCO, BSA Officer, Chief Risk Officer.
**Response:** The risk people fear is an AI *making* a regulated decision. This architecture doesn't do that. The model only drafts evidence and narrative; every consequential decision — suppress, escalate, file, deny, charge — is deterministic Python, and a named human approves it at a framework-enforced gate. That is exactly what makes it examinable rather than a black box.
**Proof:** `governance/tests/test_hitl_gates.py` fails the build if any agent's human-review gate is bypassable; `01-financial-crime-investigation-agent` pauses before any SAR via `interrupt_before`; routing logic is Python (`02`'s deterministic suppression gate) with the model excluded.

## 2. "Why buy this when we could build it ourselves with Claude/Bedrock + LangGraph?"
**Who:** CIO, Chief Data/AI Officer, an internal platform team.
**Response:** You could — and you'd spend 12–18 months and several million dollars reproducing twelve domain agents, the deterministic control patterns, the governance harness, the runbooks, and the AWS reference architecture, then maintaining them as regulations change. This compresses that to a hardening-and-integration engagement on a tested base. You're buying the months and the domain encoding, not the model.
**Proof:** 700+ tests in CI; `governance/` (grounding, prompt-manifest drift gate, fairness/AIR harness, injection red-team); `infra/terraform` reference; `runbooks/`. See `offerings/COMPETITIVE-POSITIONING.md` for the build-vs-buy math.

## 3. "Our data can't leave our environment."
**Who:** CISO, data-governance lead.
**Response:** It doesn't have to. The reference deploys into your AWS account with Bedrock inference via a VPC endpoint (no internet egress from agent subnets), customer-managed KMS, and append-only WORM audit. Single-tenant, in-account, inheriting your own AWS posture.
**Proof:** `infra/terraform/modules/network` (no-internet agent subnets + Bedrock VPC endpoint), `modules/security` (KMS, Cognito/Okta), `modules/data` (S3 Object Lock COMPLIANCE, append-only DynamoDB). The `aws-native-reference/` shows the same controls under Step Functions + Bedrock.

## 4. "How do we know the AI didn't make up numbers in a SAR or an adverse-action letter?"
**Who:** BSA Officer, fair-lending officer, internal audit.
**Response:** Every figure and entity in a generated narrative is checked against the evidence actually in the case state before a human sees it; unsupported claims are flagged for the reviewer. Prompt versions are hashed and gated, so the language that produced any artifact is reconstructable.
**Proof:** `governance/grounding.py` + its tests; `governance/prompt_registry.py` + `prompt_manifest.json`; golden-case evals for SAR narratives (Agent 01) and adverse-action notices (Agent 08).

## 5. "Fair lending — can you prove the credit agent isn't discriminatory?"
**Who:** Fair-lending officer, CRO, regulator-facing counsel.
**Response:** The scoring is deterministic and blind to protected-class correlates by construction, and we ship a matched-pair + four-fifths adverse-impact harness that runs in CI on synthetic data and is designed to be re-run on your HMDA-coded data during the pilot. Adverse-action reasons are Python-mapped to ECOA codes, not model-authored.
**Proof:** `governance/fairness/test_agent08_disparate_impact.py`; `08-credit-underwriting-agent` adverse-action enum mapping; `docs/user-guides/GUIDE-CREDIT-FAIR-LENDING.md`.

## 6. "We've been burned by vendors who oversold. What's actually built vs. roadmap?"
**Who:** Everyone who has bought enterprise software before.
**Response:** We label it explicitly and hand you the table. Twelve agents and the governance/IaC/runbooks are built and tested; the MCP authorization gateway, live connectors, and a deployed environment are per-engagement or Phase-2. We price the gap; we don't hide it.
**Proof:** README "asset classification" table and maturity ladder; `ENTERPRISE-PLATFORM.md` implementation-state table; `offerings/TPRM-DUE-DILIGENCE-PACKET.md` (implemented ✅ vs roadmap ◻, STRIDE model, pen-test plan).

## 7. "It runs on fixtures. It won't connect to our Actimize/FIS/Fiserv stack."
**Who:** Integration architect, head of operations.
**Response:** Correct today — and the seam is explicit, not hidden. There's a connector interface with fixture and live implementations; going live is a configuration change plus mapping your vendor's API in one place, not an agent rewrite. Integration sizing is a named line item in the assessment.
**Proof:** `platform_core/fsi_agent_platform/connectors/` (interface + fixture + stub-real + factory; fails closed when an endpoint is unconfigured); `connectors/README.md` adoption guide.

## 8. "Is it production-ready?"
**Who:** Procurement, CIO.
**Response:** No — and anyone who says their accelerator is, is selling you something. It's production-shaped and hardening-scoped. The path to production is defined: identity, connectors, a deployed environment, observability, and a security validation pass. That path is the engagement.
**Proof:** The phased plan; `runbooks/` (incident, DR, HITL ops, model degradation); `CONTROL-INTEGRITY-CHANGELOG.md` showing control fixes already shipped.

## 9. "Why Presidio and not the model vendor or a Big-4 firm?"
**Who:** Executive sponsor.
**Response:** This is an integration problem — APIs, identity, cloud, data, security, governance, and managed operations — not a model problem. That's an SI's center of gravity. We show up with running software, an AWS reference architecture, and operational playbooks, and we can operate it afterwards. A model vendor sells you the engine; a strategy firm sells you a slide deck; we deliver and run the system.
**Proof:** The whole repo, plus the `aws-native-reference/` and the managed-service offering.

## 10. "What does this cost to run, and when does it pay back?"
**Who:** CFO, COO.
**Response:** Single-digit-thousands per agent per month in AWS, against six- to seven-figure annual labor and loss-avoidance per agent at mid-market scale — illustrative until rebuilt on your numbers in week 1 of the assessment, at which point they're yours and far more persuasive.
**Proof:** `offerings/COST-ROI-MODEL.md`; README ROI summary (explicitly labeled illustrative).

---

### How to use this in a call
Lead with the buyer's language (CFO → P&L, BSA → examinability, CISO → least-privilege). When you make a claim, name the file — invite their engineers to check it. The objection you *want* is "show me," because the code answers it.
