"""
Shared agent runtime handler (Phase 3 deploy kit).

Loads ANY of the 12 LangGraph agents by name and runs its compiled graph behind
one uniform interface, so every agent gets the same AWS-native container runtime
without rewriting it. This is the "keep LangGraph, add an AWS-native runtime"
path: the agent's deterministic gates, HITL logic, and regulatory controls are
unchanged — only the host changes (Amazon Bedrock AgentCore Runtime, ECS
Fargate, or local).

The container runs ONE agent (selected by the AGENT env var). Each agent's graph
is built WITHOUT a checkpointer so a single stateless /invocations call runs to
completion and reports `human_review_required` in its output; the actual human
pause/resume is owned by the orchestration layer (Step Functions waitForTaskToken
in the AWS-native reference, or the agent's review UI), not the container.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Where the 12 agent directories live. In the repo this is the repo root
# (handler.py is at aws-native-reference/_shared/runtime/handler.py -> parents[3]).
# In a container the agents are copied elsewhere; set FSI_REPO_ROOT to that path.
REPO_ROOT = Path(os.getenv("FSI_REPO_ROOT") or Path(__file__).resolve().parents[3])

# agent key -> (directory name, build function, build kwargs that yield a
# run-to-completion graph with NO interrupt — HITL surfaces in the output).
AGENT_REGISTRY: Dict[str, Tuple[str, str, Dict[str, Any]]] = {
    "01-financial-crime-investigation": ("01-financial-crime-investigation-agent", "build_investigation_graph", {"use_memory": False}),
    "02-aml-tms-enhancement":           ("02-aml-tms-enhancement-agent", "build_graph", {}),
    "03-kyc-cdd-perpetual":             ("03-kyc-cdd-perpetual-agent", "build_kyc_review_graph", {"use_memory": False}),
    "04-fraud-detection":               ("04-fraud-detection-agent", "build_fraud_detection_graph", {"use_memory": False}),
    "05-wealth-rm-copilot":             ("05-wealth-rm-copilot", "build_wealth_rm_graph", {"use_memory": False}),
    "06-regulatory-change":             ("06-regulatory-change-agent", "build_regulatory_change_graph", {"use_memory": False}),
    "07-trading-surveillance":          ("07-trading-surveillance-agent", "build_trading_surveillance_graph", {"use_memory": False}),
    "08-credit-underwriting":           ("08-credit-underwriting-agent", "build_underwriting_graph", {"checkpointer": None}),
    "09-document-intelligence":         ("09-document-intelligence-agent", "build_document_intelligence_graph", {"checkpointer": None}),
    "10-payments-compliance":           ("10-payments-compliance-agent", "build_payments_compliance_graph", {"checkpointer": None}),
    "11-model-risk":                    ("11-model-risk-agent", "build_model_risk_graph", {"checkpointer": None}),
    "12-collections-recovery":          ("12-collections-recovery-agent", "build_collections_graph", {"checkpointer": None}),
}

_VENDORED = ("agent", "tools", "scoring", "data")


def list_agents() -> List[str]:
    return list(AGENT_REGISTRY)


def _purge_vendored_modules() -> None:
    for m in [m for m in list(sys.modules) if m.split(".")[0] in _VENDORED]:
        del sys.modules[m]


def build_for(agent_key: str):
    """Load the named agent's compiled LangGraph graph (run-to-completion build)."""
    if agent_key not in AGENT_REGISTRY:
        raise KeyError(f"unknown agent {agent_key!r}; known: {', '.join(list_agents())}")
    dir_name, fn_name, kwargs = AGENT_REGISTRY[agent_key]
    agent_path = str(REPO_ROOT / dir_name)
    if agent_path not in sys.path:
        sys.path.insert(0, agent_path)
    _purge_vendored_modules()
    try:
        graph_mod = importlib.import_module("agent.graph")
        build = getattr(graph_mod, fn_name)
        return build(**kwargs)
    finally:
        # Leave the agent on sys.path for the running container (single agent);
        # tests purge between agents via build_for's re-entry.
        pass


def current_agent_key() -> str:
    return os.getenv("AGENT", "").strip()


def invoke(agent_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the agent graph on an input payload; return its final state."""
    graph = build_for(agent_key)
    result = graph.invoke(payload)
    return result


def ping() -> Dict[str, str]:
    """AgentCore /ping health contract."""
    return {"status": "Healthy"}


def handle_invocation(payload: Dict[str, Any], agent_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Uniform /invocations envelope. `agent_key` defaults to the AGENT env var
    (the agent this container serves). Returns {agent, status, output|error}.
    """
    key = agent_key or current_agent_key()
    if not key:
        return {"status": "ERROR", "error": "no agent selected (set AGENT env var)"}
    if key not in AGENT_REGISTRY:
        return {"status": "ERROR", "error": f"unknown agent {key!r}"}
    try:
        output = invoke(key, payload or {})
        return {"agent": key, "status": "OK", "output": output}
    except Exception as exc:  # never leak a stack trace to the caller
        return {"agent": key, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
