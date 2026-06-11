# Competitive Positioning — FSI Agentic AI Accelerator

For client principals and sellers answering *"why this, and why Presidio, instead of ___?"*. Written evenhandedly: each alternative is genuinely good at something, and the honest move is to name where it wins and where this accelerator wins. Buyers trust a fair comparison and distrust a clean sweep.

> Frame: we are not competing with a TMS or a model. We position as the **integration and governance layer** that lets an institution use agentic AI on top of the systems and models it already has — deployed in its own AWS account, with humans accountable.

---

## The four alternatives a buyer is really weighing

| Alternative | What it is | Where it genuinely wins | Where this accelerator wins |
|---|---|---|---|
| **Build in-house** | Internal team builds agents on Bedrock/Claude + LangGraph | Full control; no license; deepest fit to internal systems | Time-to-value (months vs. 12–18); domain controls already encoded and test-verified; governance harness + runbooks already exist; no key-person risk |
| **Incumbent point solutions** (Verafin, Actimize/NICE, Hummingbird, vendor AML/credit modules) | Mature, single-domain SaaS | Deep single-domain features; established examiner familiarity; vendor owns the model risk | Cross-domain consistency (one control pattern across AML, KYC, fraud, credit, payments, collections); deploys in *your* account; you own the audit trail; not locked to one vendor's roadmap |
| **Horizontal LLM/copilot** (raw Bedrock, ChatGPT Enterprise, Copilot, a generic agent platform) | General-purpose assistant | Cheap, fast to start, broad utility | Regulated-workflow controls (deterministic gates, HITL enforcement, grounding, fair-lending tests) that a horizontal copilot simply does not have; FSI domain encoding |
| **Strategy / Big-4 advisory** | Assessment + roadmap consulting | Board relationships; change management; process redesign | Working software on day one; an AWS reference architecture and IaC; the ability to *deliver and operate*, not just advise |

---

## Build vs. buy — the math to put on the table

A from-scratch internal build that reaches parity with this accelerator needs, realistically:

- **12 domain agents**, each requiring a subject-matter expert (AML, KYC, fraud, surveillance, credit, payments, model risk, collections, …) working with engineers.
- **A platform layer:** deterministic-gate framework, HITL checkpointing, append-only audit, PII boundary, secrets/guardrail enforcement, a connector abstraction.
- **A governance harness:** grounding checks, prompt-version gating, fairness/AIR testing, injection red-team, golden-case evals — wired into CI.
- **Operational playbooks:** incident response, DR, HITL queue ops, model-degradation response.
- **An AWS reference architecture** with least-privilege IAM, WORM audit, VPC-contained inference.

Order-of-magnitude internal cost: **$3M–$5M over 12–18 months**, plus ongoing maintenance as regulations and models change, plus the key-person risk of the people who built it. The accelerator path is a **hardening + integration engagement on a tested base** — a fraction of the cost and time, with the domain knowledge already encoded. *Use the client's own loaded engineering rates from the assessment to make this their number, not ours.*

---

## Positioning against incumbents (don't fight the wrong battle)

Do **not** position this as a rip-and-replace of a working TMS or LOS. Position it as the **agentic layer on top**: the agent triages, assembles, and drafts; the incumbent system of record stays the system of record; the agent writes back only after a human approves. This makes the incumbent vendor a partner in the story, not the enemy, and it shortens the security review (read-mostly integration first).

When the incumbent has its own "AI" feature, the differentiators are: (1) it runs in *your* account on *your* models, not the vendor's; (2) cross-domain consistency instead of one more siloed model to govern; (3) you own the audit trail and the model-risk evidence; (4) you are not waiting on the vendor's roadmap.

---

## Talk tracks by buyer

- **CFO/COO:** *"Point solutions each carry a license and a separate integration and audit surface. One governed pattern across twelve workflows lowers integration cost and shrinks your model-risk inventory from many vendor black boxes to one auditable framework you control."*
- **CISO:** *"A horizontal copilot can't enforce least-privilege tool access or a framework-level human gate. This deploys least-privilege IAM, VPC-contained inference, and an append-only audit in your account — verifiable in the Terraform."*
- **CCO/CRO:** *"A model vendor owns the model risk and won't show you inside it. Here the decisions are deterministic and the model only drafts — your model-risk function can validate every control, and we ship the validation harness."*
- **CIO:** *"Build gives you control and an 18-month bill and a key-person dependency. This gives you the control of running it in your account with the domain work already done and tested. Buy the months."*

---

## Where we should concede (credibility check)

- If the client needs **one** deeply specialized capability (e.g., a mature, examiner-blessed sanctions-screening engine) and nothing else, a best-of-breed point solution may be the right call — position this accelerator as the layer that *orchestrates and governs* that engine, not a replacement for it.
- If the client has **no cloud footprint and no appetite to modernize**, they are not ready for a platform conversation; sell the assessment (or decline) rather than the suite.
- The accelerator is **not** production-ready out of the box. Against a shipping SaaS product on a "deploy tomorrow" timeline, we are honest that this is a governed path to production, and we compete on control, ownership, and cross-domain fit — not on being finished today.

> Sources for every capability claim are in the repo (`governance/`, `infra/terraform/`, `platform_core/`, `aws-native-reference/`). Invite verification — it is the whole point of leading with a tested asset.
