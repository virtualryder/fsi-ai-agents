# Control-Integrity Hardening Changelog

**Date:** June 2026
**Scope:** Phase 0 (framing) and Phase 1 (control-integrity) of the accelerator hardening plan.
**Principle:** deterministic Python decides and routes; the LLM only drafts narratives; a human is accountable at every regulated decision; everything is auditable.

All changes below ship with tests and are gated in CI. Test counts after this pass:
Agent 01 = 59, Agent 02 = 56, platform_core = 32, governance = 36 (all green).

---

## Phase 1.1 — Agent 01 SAR gate is now framework-enforced

**Finding.** `01-financial-crime-investigation-agent` — the flagship SAR agent —
compiled with a checkpointer but **without** `interrupt_before`, leaving its
human-review gate procedural rather than framework-enforced. It was the only
deterministic-gate agent with this gap, and the highest-stakes one.

**Change.** `agent/graph.py` now compiles with
`interrupt_before=["human_review_gate"]` whenever a checkpointer is present
(the suite-wide pattern used by agents 03, 05, 06, 07, 08, 09, 10, 11, 12). The
low-risk auto-close path (score < 30) is unaffected — it never routes through
the gate. Tests/demo (no checkpointer) still run to completion.

**Tests.** `tests/test_graph.py::TestGraphConstruction::`
`test_human_review_gate_is_framework_enforced` and `test_no_interrupt_without_checkpointer`.

## Phase 1.2 — CI guard for HITL gates (whole suite)

**Change.** New `governance/tests/test_hitl_gates.py` builds every agent that
ships a human-review gate and asserts the gate node is registered in the
LangGraph runtime's `interrupt_before_nodes`. It also pins Agent 02 as the one
intentional no-gate agent and asserts no agent is left unclassified, so the
build fails on inventory drift. 13 tests.

## Phase 1.3 — Agent 02 deterministic suppression gate

**Finding.** The composite false-positive score that drove routing was
~50% LLM-weighted, so a model-generated number could push an alert into
SUPPRESS — the only disposition that removes an alert from human review.

**Change.** `scoring/false_positive_classifier.py` adds
`compute_deterministic_score()` (rule pre-score + historical base rates,
renormalized; LLM excluded). `agent/nodes.py::determine_routing` now applies a
**deterministic suppression gate**: an alert may be SUPPRESSED only if the
deterministic-only score independently clears the suppress threshold; otherwise
it is routed to a human-visible queue (DOWNGRADE, or PASS_THROUGH). The LLM can
still author the justification narrative and still force ESCALATE — it can never
remove an alert from review. The routing audit entry records
`deterministic_fp_score`, `routing_basis`, and `suppression_gate_applied`.

**Tests.** `tests/test_suppression_gate.py` (4 tests) proves an LLM-high /
deterministic-low alert cannot be suppressed, that suppression is allowed when
deterministic support exists, and that the gate + basis are recorded in the
audit trail. All 52 pre-existing Agent 02 tests still pass unchanged.

## Phase 1.4 — PII-masking boundary middleware

**Finding.** `platform_core` masking (`mask()`) was correct but discretionary —
useful only if a developer remembered to call it at each state-write boundary.

**Change.** `platform_core/fsi_agent_platform/pii.py` adds `mask_obj(obj)`
(recursively masks every string in a nested dict/list/tuple, preserving
structure and non-string scalars) and `scrub_for_persistence(record)` — a
one-line boundary helper for audit entries, checkpoints, and state snapshots.

**Tests.** `platform_core/tests/test_platform.py::TestPIIBoundary` (3 tests)
proves raw SSN/PAN cannot survive a nested record and that clean records are
lossless.

**Phase 2 follow-up (staged, mechanical):** wire `scrub_for_persistence` into
each agent's vendored `agent/persistence.py::AuditSink.record()` so masking is
the enforced default at the durable-write boundary across all 12 agents.

## Phase 1.5 — Secrets fail-closed + guardrails required in production

**Change.**
- `platform_core/.../secrets.py` adds `SECRETS_FAIL_CLOSED` (implied when
  `ENVIRONMENT=production`): a failed Secrets Manager lookup now raises
  `SecretsUnavailableError` instead of silently falling back to environment
  variables. Dev/demo behavior is unchanged.
- `platform_core/.../llm_factory.py`: when the Bedrock provider is active
  without `BEDROCK_GUARDRAIL_ID` in a production environment (or when
  `REQUIRE_BEDROCK_GUARDRAIL` is set), startup now fails rather than running
  un-guardrailed inference on regulated data. Dev/demo only warns.

**Tests.** `TestSecretsFailClosed` (3) and `TestGuardrailRequiredInProd` (2) in
`platform_core/tests/test_platform.py`.

---

## What this pass did NOT change

Consistent with the maturity ladder, the following remain Phase 2/3 (not yet
done): live connectors, the MCP authorization gateway build, an AWS-native
reference implementation (Bedrock Agents / Step Functions / Strands Agents SDK),
a deployed reference environment with end-to-end integration tests, observability
export wiring, and pen-test/SOC 2 progress. The suite remains an
**agentic AI modernization accelerator**, not a production-ready regulated platform.
