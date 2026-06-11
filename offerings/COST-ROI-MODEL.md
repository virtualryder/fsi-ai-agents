# Cost / ROI Model — FSI Agentic AI Accelerator

A transparent, rebuild-on-client-data model for sizing the business case. For solution architects and client principals building a board-ready number.

> **Read this first.** Every figure below is **illustrative** — built from publicly available industry benchmarks and common operating assumptions, not a guarantee. The model's value is its *structure*: in week 1 of the assessment you replace these inputs with the client's real volumes and fully-loaded rates, and the output becomes *their* number, which is far more persuasive than ours. Treat outputs as directional inputs to a business case, not validated savings.

---

## How the model works (the structure that matters)

For each agent, annual value = **labor avoided** + **loss/penalty avoided**, minus **AWS run cost** and **amortized build/integration**.

```
labor_avoided   = cases_per_year × minutes_saved_per_case ÷ 60 × loaded_hourly_rate
loss_avoided    = baseline_annual_loss_or_penalty × expected_reduction_%
aws_run_cost    = per-agent infra + Bedrock inference (volume-driven)
net_annual      = labor_avoided + loss_avoided − aws_run_cost
payback_months  = engagement_cost ÷ (net_annual ÷ 12)
```

The only inputs that move the answer materially are **case volume**, **minutes saved per case**, **loaded analyst rate**, and **baseline loss**. Collect those four per workflow and the rest follows.

---

## Editable input sheet (fill in during discovery)

| Input | Symbol | Example ($8B regional bank) | Client value |
|---|---|---|---|
| TMS alerts / month | A | 12,000 | |
| AML/financial-crime FTE | F | 18 | |
| Loaded analyst rate ($/hr) | R | 95 | |
| SARs filed / year | S | 900 | |
| Baseline annual fraud loss | L | $4.0M | |
| KYC periodic reviews / year | K | 6,000 | |
| Documents re-keyed / year | D | 180,000 | |

---

## Worked example — $8B regional bank, Phase-1 bundle (Agents 09 + 02 + 01 + 03)

Phase-1 wedge: Document Intelligence (09, the foundation), AML/TMS triage (02), Financial Crime Investigation (01), KYC/CDD (03). Illustrative, assistive deployment (human approval on every regulated action).

| Agent | Cost driver | Illustrative annual value | Basis |
|---|---|---|---|
| 09 · Document Intelligence | Manual re-keying of PDFs/SWIFT/forms | **$1.6M–$1.9M** | ~180K docs/yr, ~80 min → ~11 min, R≈$95/hr; also the multiplier that speeds 01/02/03 |
| 02 · AML/TMS triage | 90%+ false-positive rate consuming analyst hours | **$3.5M–$4.0M** | ~50% pre-queue suppression with full audit, 18-FTE team |
| 01 · Financial Crime Investigation | 40 hrs/SAR investigator time | **$2.0M–$2.4M** | 900 SARs/yr, 40→~8 hrs |
| 03 · KYC/CDD perpetual | Manual periodic-review hours; exam findings | **$1.2M–$1.5M** | ~90% reduction in manual refresh hours, 6,000 reviews/yr |
| **Phase-1 subtotal** | | **~$8.3M–$9.8M / yr** | illustrative, assistive |

**AWS run cost (Phase-1, in-account):** order of **$8K–$20K per agent per month** all-in (Fargate/Lambda, Bedrock inference at volume, Aurora/DynamoDB/S3, observability) → roughly **$0.4M–$1.0M / yr** for the four. Inference dominates and scales with volume; tune model tiering (Haiku for triage, Sonnet for narrative) to control it.

**Net Phase-1 value:** ~**$7M–$9M / yr** illustrative, before counting penalty/loss avoidance beyond fraud.

---

## Engagement cost and payback (illustrative)

| Stage | Cost band | What it buys |
|---|---|---|
| Readiness Assessment | $75K–$150K | The baseline + prioritization + pilot SOW (replaces these inputs with real ones) |
| Production Pilot (1 agent) | $250K–$400K | One workflow to defensible production candidate + evidence pack |
| Phase-1 scale-out (4 agents) | engagement-scoped | The bundle above, integrated and governed |

With Phase-1 net value in the **$7M–$9M/yr** range (illustrative) against a low-seven-figure all-in first-year cost, modeled **payback lands inside the first year** — frequently in the 3–6 month range once a wedge agent is in assisted production. The README's "full suite $27M+ / < 6-month payback" figure is the 12-agent extrapolation; **lead with the 4-agent Phase-1 number** — it is more credible and still compelling.

---

## Three-year illustrative shape

| Year | Scope | Net value (illustrative) | Cumulative |
|---|---|---|---|
| 1 | Assess → pilot → Phase-1 (4 agents) | $4M–$6M (partial-year ramp) | $4M–$6M |
| 2 | Phase-1 full year + 3–4 more agents | $9M–$14M | $13M–$20M |
| 3 | Toward full suite + managed operation | $14M–$22M | $27M–$42M |

Against a cumulative investment in the low-to-mid seven figures, the modeled 3-year return is multiples of cost. **State the assumptions on the same slide as the number** — an unhedged ROI claim is the fastest way to lose a CFO's trust; a transparent model earns it.

---

## Sensitivities (what to stress-test in front of the CFO)

- **Volume** is linear: halve alert/document volume and the labor-avoided line roughly halves.
- **Minutes-saved** is the softest input — anchor it to the pilot's measured before/after, not to this sheet.
- **Loss avoidance** (fraud, FDCPA/Reg E penalties, exam findings) is lumpy and institution-specific — present it as a separate, clearly-labeled upside, never blended into the core labor case.
- **Inference cost** rises with volume and model tier — show the Haiku/Sonnet tiering lever.

> Pair this with `offerings/ASSESSMENT-OFFERING.md` (which produces the real baseline) and `offerings/COMPETITIVE-POSITIONING.md` (the build-vs-buy denominator). The number that closes deals is the client's own, computed in week 1.
