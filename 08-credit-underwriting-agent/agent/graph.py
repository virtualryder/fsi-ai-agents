# agent/graph.py
# ============================================================
# Credit Underwriting Agent — LangGraph StateGraph
#
# 12-node DAG:
#
#   application_intake → applicant_profile_lookup →
#   document_verification → credit_bureau_pull →
#   financial_analysis → fair_lending_check →
#   risk_scoring → routing_decision →
#
#   [human_review_required=True]  → human_review_gate →
#   [human_review_required=False] ─────────────────────→
#
#   credit_memo_drafting →
#
#   [adverse_action_required=True]  → adverse_action_node →
#   [adverse_action_required=False] ────────────────────────→
#
#   finalize_decision → END
#
# HITL: interrupt_before=["human_review_gate"]
#   Resume: graph.stream(None, config) after updating state
#   with reviewer_id, reviewer_decision, reviewer_notes,
#   conditions_imposed, and optionally pricing_override.
#
# Checkpointing:
#   Development: MemorySaver (in-process)
#   Production:  PostgresSaver (Aurora) — durable across restarts
# ============================================================
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agent.nodes import (
    adverse_action_node,
    applicant_profile_lookup_node,
    application_intake_node,
    credit_bureau_pull_node,
    credit_memo_drafting_node,
    document_verification_node,
    fair_lending_check_node,
    finalize_decision_node,
    financial_analysis_node,
    human_review_gate,
    risk_scoring_node,
    routing_decision_node,
)
from agent.state import CreditUnderwritingState


# ── Conditional Routing Functions ─────────────────────────────────────────────

def _route_after_routing_decision(state: CreditUnderwritingState) -> str:
    """
    Route to HITL gate or skip directly to memo drafting.
    Python-only — no LLM involvement in this decision.

    FAIL-SAFE (Agent 12 idiom): only an EXPLICIT False skips human review.
    None / missing / 0 / any truthy value all route to the HITL gate, so a
    dropped or corrupted flag can never bypass mandatory review.
    """
    if state.get("human_review_required") is False:
        return "credit_memo_drafting"
    return "human_review_gate"


def _route_after_human_review(state: CreditUnderwritingState) -> str:
    """
    After HITL, always proceed to credit memo drafting.
    Reviewer decision is captured in state; memo node reads it.
    """
    return "credit_memo_drafting"


def _route_after_credit_memo(state: CreditUnderwritingState) -> str:
    """
    If the effective decision is a decline, generate the Reg B adverse action notice.
    Otherwise proceed directly to finalization.
    """
    if state.get("adverse_action_required"):
        return "adverse_action_node"
    return "finalize_decision"


# ── Graph Builder ──────────────────────────────────────────────────────────────

def build_underwriting_graph(checkpointer=None):
    """
    Build and compile the credit underwriting LangGraph.

    Args:
        checkpointer: LangGraph checkpointer instance.
                      Defaults to MemorySaver for development.
                      Pass PostgresSaver for production deployments.

    Returns:
        Compiled LangGraph application with HITL interrupt.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder = StateGraph(CreditUnderwritingState)

    # ── Register Nodes ────────────────────────────────────────────────────
    builder.add_node("application_intake", application_intake_node)
    builder.add_node("applicant_profile_lookup", applicant_profile_lookup_node)
    builder.add_node("document_verification", document_verification_node)
    builder.add_node("credit_bureau_pull", credit_bureau_pull_node)
    builder.add_node("financial_analysis", financial_analysis_node)
    builder.add_node("fair_lending_check", fair_lending_check_node)
    builder.add_node("risk_scoring", risk_scoring_node)
    builder.add_node("routing_decision", routing_decision_node)
    builder.add_node("human_review_gate", human_review_gate)
    builder.add_node("credit_memo_drafting", credit_memo_drafting_node)
    builder.add_node("adverse_action_node", adverse_action_node)
    builder.add_node("finalize_decision", finalize_decision_node)

    # ── Linear Edges ──────────────────────────────────────────────────────
    builder.set_entry_point("application_intake")
    builder.add_edge("application_intake", "applicant_profile_lookup")
    builder.add_edge("applicant_profile_lookup", "document_verification")
    builder.add_edge("document_verification", "credit_bureau_pull")
    builder.add_edge("credit_bureau_pull", "financial_analysis")
    builder.add_edge("financial_analysis", "fair_lending_check")
    builder.add_edge("fair_lending_check", "risk_scoring")
    builder.add_edge("risk_scoring", "routing_decision")

    # ── Conditional: HITL gate or direct to memo ──────────────────────────
    builder.add_conditional_edges(
        "routing_decision",
        _route_after_routing_decision,
        {
            "human_review_gate": "human_review_gate",
            "credit_memo_drafting": "credit_memo_drafting",
        },
    )

    # ── After HITL → always credit memo ──────────────────────────────────
    builder.add_conditional_edges(
        "human_review_gate",
        _route_after_human_review,
        {"credit_memo_drafting": "credit_memo_drafting"},
    )

    # ── Conditional: adverse action or finalize ───────────────────────────
    builder.add_conditional_edges(
        "credit_memo_drafting",
        _route_after_credit_memo,
        {
            "adverse_action_node": "adverse_action_node",
            "finalize_decision": "finalize_decision",
        },
    )

    builder.add_edge("adverse_action_node", "finalize_decision")
    builder.add_edge("finalize_decision", END)

    # ── Compile with HITL interrupt ───────────────────────────────────────
    app = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review_gate"],
    )

    return app


# ── Module-level default instance (development) ───────────────────────────────
_default_checkpointer = MemorySaver()
graph = build_underwriting_graph(checkpointer=_default_checkpointer)
