"""
HITL-gate integrity guard (Phase 1.2 — control-integrity).

The suite's core safety claim is that regulated, consequential decisions pause
for a human at a framework-enforced interrupt — not a procedural convention.
This test makes that claim CHECKABLE in CI for every agent that ships a human
review gate: each such agent, when compiled WITH a checkpointer, must register
its gate node in the LangGraph runtime's `interrupt_before_nodes`.

Why this exists: the field assessment found that Agent 01 (Financial Crime
Investigation — the flagship SAR agent) compiled WITHOUT `interrupt_before`,
leaving its SAR human-review gate procedural rather than framework-enforced.
This guard fails the build if Agent 01 — or any other gate-bearing agent —
regresses to a non-enforced gate.

Scope note: Agent 02 (AML/TMS Enhancement) is an upstream false-positive
SUPPRESSOR with no human-review gate by design; it is intentionally excluded
here and its suppression decisions are governed by an append-only audit trail
instead (see 02-aml-tms-enhancement-agent and its tests).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# (agent_dir, build_function, build_kind, expected_gate_node)
#   build_kind "use_memory"  -> build(use_memory=True)
#   build_kind "checkpointer"-> build(checkpointer=MemorySaver())
GATE_AGENTS = [
    ("01-financial-crime-investigation-agent", "build_investigation_graph", "use_memory", "human_review_gate"),
    ("03-kyc-cdd-perpetual-agent", "build_kyc_review_graph", "use_memory", "human_review_gate"),
    ("04-fraud-detection-agent", "build_fraud_detection_graph", "use_memory", "human_review_gate"),
    ("05-wealth-rm-copilot", "build_wealth_rm_graph", "use_memory", "rm_approval_gate"),
    ("06-regulatory-change-agent", "build_regulatory_change_graph", "use_memory", "human_review_gate"),
    ("07-trading-surveillance-agent", "build_trading_surveillance_graph", "use_memory", "human_review_gate"),
    ("08-credit-underwriting-agent", "build_underwriting_graph", "checkpointer", "human_review_gate"),
    ("09-document-intelligence-agent", "build_document_intelligence_graph", "checkpointer", "human_review_gate"),
    ("10-payments-compliance-agent", "build_payments_compliance_graph", "checkpointer", "human_review_gate"),
    ("11-model-risk-agent", "build_model_risk_graph", "checkpointer", "human_review_gate"),
    ("12-collections-recovery-agent", "build_collections_graph", "checkpointer", "human_review_gate"),
]

# Agents with NO human-review gate, asserted explicitly so the exclusion is
# a deliberate, reviewed decision rather than an accidental omission.
NO_GATE_AGENTS = ["02-aml-tms-enhancement-agent"]

_VENDORED_PKGS = ("agent", "tools", "scoring", "data")


def _purge_agent_modules() -> None:
    for mod in [m for m in list(sys.modules) if m.split(".")[0] in _VENDORED_PKGS]:
        del sys.modules[mod]


def _build_compiled(agent_dir: str, build_fn: str, kind: str):
    agent_path = str(REPO_ROOT / agent_dir)
    sys.path.insert(0, agent_path)
    _purge_agent_modules()
    try:
        graph_mod = importlib.import_module("agent.graph")
        build = getattr(graph_mod, build_fn)
        if kind == "use_memory":
            return build(use_memory=True)
        return build(checkpointer=MemorySaver())
    finally:
        if agent_path in sys.path:
            sys.path.remove(agent_path)
        _purge_agent_modules()


@pytest.mark.parametrize(
    "agent_dir,build_fn,kind,gate",
    GATE_AGENTS,
    ids=[a[0] for a in GATE_AGENTS],
)
def test_hitl_gate_is_framework_enforced(agent_dir, build_fn, kind, gate):
    """Every gate-bearing agent must register its gate in interrupt_before_nodes."""
    compiled = _build_compiled(agent_dir, build_fn, kind)
    interrupts = list(getattr(compiled, "interrupt_before_nodes", []))
    assert gate in interrupts, (
        f"{agent_dir}: human-review gate '{gate}' is NOT framework-enforced. "
        f"Compile the graph with interrupt_before=['{gate}'] when a checkpointer "
        f"is present. Found interrupt_before_nodes={interrupts}."
    )


@pytest.mark.parametrize("agent_dir", NO_GATE_AGENTS)
def test_known_no_gate_agents_are_documented(agent_dir):
    """Pin the set of agents intentionally shipped without a human-review gate."""
    assert (REPO_ROOT / agent_dir).is_dir(), f"{agent_dir} missing"


def test_every_agent_is_classified():
    """Each agent package is either a gate agent or an explicit no-gate agent."""
    on_disk = sorted(
        p.name for p in REPO_ROOT.iterdir()
        if p.is_dir() and p.name[:2].isdigit() and (p / "agent").is_dir()
    )
    classified = sorted([a[0] for a in GATE_AGENTS] + NO_GATE_AGENTS)
    assert on_disk == classified, (
        "Agent inventory drift: every agent must be classified as gate or "
        f"no-gate. On disk={on_disk}; classified={classified}."
    )
