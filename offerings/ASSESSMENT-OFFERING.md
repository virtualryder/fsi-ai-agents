# Agentic AI Readiness Assessment — Offering Definition

**Duration:** 3–4 weeks · **Price band:** $75K–$150K (scale by institution size and agent scope) · **Team:** 1 engagement lead (0.5 FTE), 1 solution architect (1.0), 1 compliance SME (0.5)

## What the client buys

A board-ready answer to: *"Where can agentic AI remove cost from our compliance operations without creating regulatory exposure — and what exactly would it take?"* Delivered against their real volumes, their real systems, and their examiners' expectations — anchored by working software they can see running on day one, not slideware.

## Why this accelerator changes the assessment economics

A from-scratch assessment spends weeks 1–2 building strawmen. This engagement starts from 12 working agents with documented regulatory controls (OFAC hard overrides, fair-lending HITL gates, FDCPA timing rules — all test-verified in CI), so client workshops react to running software. Reaction extracts requirements 5× faster than elicitation.

## Week-by-week

| Week | Activity | Output |
|---|---|---|
| 1 | Discovery: alert volumes, FP rates, analyst loading, SAR/case cycle times, current TMS/KYC/LOS stack, model inventory (SR 11-7 tiers) | Baseline cost-of-compliance model from THEIR numbers |
| 2 | Demo-driven workshops: run agents 01/02/09 against sanitized client scenarios; compliance + audit + tech in the room | Fit/gap matrix per use case; control-mapping draft against their exam findings (MRAs/MRIAs if shared) |
| 3 | Architecture fit: data residency posture (Bedrock in-VPC reference from `infra/terraform`), identity (Okta/AD → Cognito), integration inventory (TMS/core/LOS APIs vs file drops) | Target architecture; integration effort sizing per system |
| 3–4 | Business case + roadmap: prioritized agent sequence, pilot definition, TCO vs. status quo | Final readout (exec + technical tracks) |

## Deliverables

1. **Cost-of-compliance baseline** — their volumes, their fully-loaded rates; the denominator every later ROI claim divides into.
2. **Use-case prioritization** — all 12 agent patterns scored on value, integration effort, regulatory sensitivity, data readiness; top 3 sequenced.
3. **Control mapping** — agent control patterns mapped to the institution's own policy framework and recent exam findings (BSA/AML, ECOA/Reg B, SR 11-7, FDCPA/Reg F as applicable).
4. **Target architecture** — deployment reference (this repo's Terraform as the starting point), identity flow, integration approach per system of record.
5. **Pilot SOW draft** — scoped, priced, success-criteria'd; the assessment's last deliverable is the pilot's first.

## Qualification gates (don't sell this to the wrong client)

- ≥ $5B assets OR ≥ 50 FTE in financial-crime/compliance ops (smaller: point solution, not a platform conversation)
- A named executive owner in compliance ops or risk technology
- Willingness to share volumes/metrics under NDA — without their numbers this is generic consulting
- No active enforcement action that freezes new-technology adoption (an MRA on *manual process failures* is a tailwind, not a blocker)

## Honest-positioning rules (non-negotiable)

The asset classification banner in this repo's README is the script: this is a **production-shaped accelerator**. The assessment prices the hardening, never hides it. ROI figures presented are *illustrative until rebuilt on client data in week 1* — and then they are theirs, which is far more persuasive anyway.
