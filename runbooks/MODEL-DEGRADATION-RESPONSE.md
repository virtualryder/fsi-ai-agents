# Runbook: Model Degradation Response

**Scope:** gradual quality decline in either model layer — the deterministic Python scorers (Agent 11's SR 11-7 territory) or the LLM narrative/analysis layer (prompt + model version + grounding behavior).
**Distinction from incidents:** a control that *failed* is `INCIDENT-RESPONSE.md` C1/C2. Degradation is the slow version — drift, eroding agreement rates, eval slippage — caught by monitoring before it becomes an incident. The regulatory frame is SR 11-7 *ongoing monitoring* and *outcomes analysis*; this runbook is the operational half of the per-agent `regulatory-compliance.md` mappings.

---

## 1. What we watch (detection)

### Deterministic scorers (weekly, automated — Agent 11 patterns applied to the suite itself)
| Metric | Healthy | Investigate | Act |
|---|---|---|---|
| PSI (input population stability) per factor | < 0.10 | 0.10–0.25 | > 0.25 — population shifted; revalidate before trusting scores |
| Score distribution drift (KS vs validation baseline) | p > 0.05 | borderline 2 wks | significant — recalibration candidate |
| HITL agreement rate (human disposition == agent recommendation) | ≥ 90% | 85–90% | < 85% sustained 2 wks |
| Missed-escalation rate (QA-sampled) | **0** | — | any miss = C1 incident, not degradation |

### LLM layer (every build + weekly sampled production)
| Metric | Source | Act when |
|---|---|---|
| Golden eval pass rate | `governance/evals` in CI | any failure blocks merge (already enforced); a *production* sample failing while CI passes ⇒ golden set is stale — add cases |
| Grounding: ungrounded claims per narrative | `verify_grounding` on sampled production artifacts | > 0 on any examiner-facing artifact ⇒ pull sample wider; if confirmed, treat as C2 |
| Reviewer modification rate on narratives | HITL queue stats (§5 of queue runbook) | > 30% sustained ⇒ prompt or model-version investigation |
| Bedrock model-version change notices | AWS notifications | always: schedule a full eval run BEFORE the cutover date, never after |

### Fairness (Agent 08 — monthly, mandatory)
Four-fifths AIR on the month's decisions using the institution's demographic codings (`governance/fairness` harness, production mode). AIR < 0.90: investigate with the fair-lending officer. AIR < 0.80: stop auto-dispositions on the affected segment (all to HITL) the same day and open a formal fair-lending review — this is the regulatory presumption threshold, not a tuning knob.

## 2. Triage decision tree

```
Signal fired
 ├─ Output is WRONG on a regulatory control (missed OFAC, skipped HITL)?
 │    └─ STOP → INCIDENT-RESPONSE.md C1. Not this runbook.
 ├─ Inputs drifted (PSI/KS) but agreement still healthy?
 │    └─ §3 — population drift path (recalibrate against new population)
 ├─ Agreement/modification rates eroding, inputs stable?
 │    ├─ prompt_manifest changed recently? → §4 prompt-version path (likeliest)
 │    ├─ Bedrock model version changed?    → §4 model-version path
 │    └─ neither?                          → upstream data quality review
 │         (vendor feed change, schema drift at intake — check Agent 09 first;
 │          it feeds everyone)
 └─ Fairness AIR slipped? → §1 fairness procedure + §3 with FL officer in the room
```

## 3. Deterministic-layer recalibration (the SR 11-7 path)

1. **Freeze intent:** no informal threshold edits, ever — thresholds are code (`scoring/threshold_manager.py` etc.) guarded by direction tests (the suite's history includes a sign inversion that made high-risk alerts easiest to suppress; the tests that caught it are the precedent).
2. Re-run the validation battery on current data (Gini/KS discrimination, calibration, stability) — Agent 11's harness applied to the affected scorer.
3. Propose changes as a PR: changed weights/thresholds + updated tests + a one-page change memo (what moved, why, expected effect on suppression/escalation mix, fairness re-check for Agent 08).
4. Approval chain: model owner → compliance owner of the workflow → (Agent 08 only) fair-lending officer. The merge IS the change record; CI green is the precondition.
5. Post-change: 2-week heightened monitoring with the §1 metrics; revert path is `git revert` plus the same approvals — rollback is a model change too.

## 4. LLM-layer changes (prompt or model version)

**Prompt changes** are model-configuration changes (SR 11-7 scope — OCC has signaled LLMs are in MRM scope):
1. Edit prompt → run full eval harness locally → update `prompt_manifest.json` via `python -m governance.prompt_registry --update` **in the same PR** (CI fails otherwise, by design).
2. PR must show: eval results (all golden cases), grounding spot-check on 5+ realistic cases, and for Agent 08 the reason-accuracy eval specifically.
3. Same approval chain as §3.4. The manifest history is the model change log examiners ask for.

**Model-version changes** (e.g., Bedrock retiring a Claude snapshot):
1. Stand up the candidate version in a sandbox env var set (`BEDROCK_*_MODEL_ID`); run the FULL eval harness + a 100-case shadow comparison (old vs new on identical inputs; diff dispositions and narratives).
2. Material narrative-style shifts are fine; *disposition* shifts are not — any case where the recommendation flips goes to the workflow's compliance owner before cutover.
3. Cut over per agent, fast agents (02/04) first (cheapest blast radius), narrative agents (01/08) last; 2-week heightened monitoring each.

## 5. Degradation review record

Every closed degradation investigation files: trigger metric + values · diagnosis · change made (PR link) or "no action — monitored to recovery" · post-change monitoring outcome. Filed in the model-risk repository per agent; Agent 11's MODEL_REGISTRY `known_limitations` is updated when the investigation revealed a new one. This file is what turns "we monitor our models" from a claim into evidence.
