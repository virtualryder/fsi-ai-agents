"""
Shared runtime tests (Phase 3 deploy kit) — prove the container can host EVERY
agent, and that the AgentCore /invocations + /ping envelope is correct.
Run in CI without AWS or a web server.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import handler

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_registry_has_all_12_agents():
    assert len(handler.list_agents()) == 12


def test_every_registered_agent_dir_exists():
    for key, (dir_name, _fn, _kw) in handler.AGENT_REGISTRY.items():
        assert (REPO_ROOT / dir_name).is_dir(), f"{key} -> {dir_name} missing"


@pytest.mark.parametrize("key", list(handler.AGENT_REGISTRY))
def test_every_agent_graph_builds(key):
    """Each agent's compiled LangGraph graph loads via the shared handler."""
    graph = handler.build_for(key)
    assert hasattr(graph, "invoke"), f"{key} did not build an invokable graph"


def test_ping_contract():
    assert handler.ping() == {"status": "Healthy"}


def test_invocations_unknown_agent_is_error_envelope():
    out = handler.handle_invocation({"x": 1}, agent_key="nope")
    assert out["status"] == "ERROR" and "unknown agent" in out["error"]


def test_invocations_no_agent_selected_is_error():
    out = handler.handle_invocation({"x": 1}, agent_key="")
    assert out["status"] == "ERROR"


def test_invocations_envelope_wraps_graph_output(monkeypatch):
    """The /invocations envelope passes input to the graph and wraps its output."""
    class _FakeGraph:
        def invoke(self, payload):
            return {"echo": payload, "human_review_required": True}
    monkeypatch.setattr(handler, "build_for", lambda key: _FakeGraph())
    out = handler.handle_invocation({"document": {"doc_id": "d1"}}, agent_key="09-document-intelligence")
    assert out["status"] == "OK" and out["agent"] == "09-document-intelligence"
    assert out["output"]["echo"]["document"]["doc_id"] == "d1"


def test_invocations_masks_internal_errors(monkeypatch):
    def _boom(key):
        raise ValueError("boom")
    monkeypatch.setattr(handler, "build_for", _boom)
    out = handler.handle_invocation({}, agent_key="01-financial-crime-investigation")
    assert out["status"] == "ERROR" and "ValueError" in out["error"]
