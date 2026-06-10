"""
Agent 12 — Collections & Recovery Agent
LangGraph StateGraph construction and routing functions.

Routing security:
- _route_after_routing_decision: checks `human_review_required is False` explicitly.
  None, 0, missing, or any other falsy value routes to HITL (fail-safe).
  Only an explicit Python False bypasses the HITL gate.

- _route_after_human_review: all decisions route to communication_drafting,
  then audit_finalize. The human decision sets collections_outcome — the graph
  always produces a finalized audit record regardless of outcome.

HITL framework enforcement:
- interrupt_before=["human_review_gate"] is a LangGraph directive.
  The graph physically cannot advance past Node 9 (routing_decision) to
  Node 11 (communication_drafting) or Node 12 (audit_finalize) without
  the human_review_gate_node executing first when HITL is required.
  This is not application logic — it is the graph compiler's interrupt mechanism.
"""

from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.persistence import get_checkpointer

from .state import CollectionsState
from .nodes import (
    debt_intake_node,
    fdcpa_compliance_check_node,
    scra_bankruptcy_check_node,
    consumer_profile_node,
    debt_validation_node,
    payment_plan_optimizer_node,
    collections_strategy_node,
    risk_scoring_node,
    routing_decision_node,
    human_review_gate_node,
    communication_drafting_node,
    audit_finalize_node,
)

# ---------------------------------------------------------------------------
# Routing functions — Python only, no LLM
# ---------------------------------------------------------------------------

def _route_after_routing_decision(state: Dict[str, Any]) -> str:
    """
    Route to HITL gate or communication drafting.

    Security: checks `is False` explicitly.
    - None → "human_review_gate"   (missing state → fail-safe to HITL)
    - 0 → "human_review_gate"      (falsy int → fail-safe to HITL)
    - True → "human_review_gate"   (HITL required)
    - False → "communication_drafting" (explicit Python False = auto-process)
    """
    if state.get("human_review_required") is False:
        return "communication_drafting"
    return "human_review_gate"

def _route_after_human_review(state: Dict[str, Any]) -> str:
    """
    After HITL decision, route to communication drafting for all outcomes.
    CEASE_AND_DESIST and LEGAL_REFERRAL still need a confirmation/closure letter.
    audit_finalize always runs after communication_drafting.
    """
    return "communication_drafting"

# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_collections_graph(checkpointer=None, llm=None, institution_name: str = "Your Institution"):
    """
    Build the 12-node Collections & Recovery StateGraph.

    Node sequence:
    1.  debt_intake              — PII masking, FDCPA applicability
    2.  fdcpa_compliance_check   — Time-of-day, Reg F 7-in-7, C&D, dispute
    3.  scra_bankruptcy_check    — SCRA active military, bankruptcy stay, SOL
    4.  consumer_profile         — Hardship assessment (LLM narrative)
    5.  debt_validation          — Days delinquent, credit reporting eligibility
    6.  payment_plan_optimizer   — Payment plans + settlement tiers (Python math)
    7.  collections_strategy     — Strategy narrative (LLM narrative)
    8.  risk_scoring             — HITL conditions (frozenset check)
    9.  routing_decision         — Route to HITL or auto (Python, fail-safe)
    10. human_review_gate        — HITL: collector/supervisor decision
    11. communication_drafting   — Letter drafts (LLM, FDCPA disclosures injected)
    12. audit_finalize           — Append-only audit, S3 Object Lock

    HITL enforcement: interrupt_before=["human_review_gate"]
    """
    workflow = StateGraph(CollectionsState)

    # Register nodes with dependency injection for LLM and institution name
    workflow.add_node("debt_intake", debt_intake_node)
    workflow.add_node("fdcpa_compliance_check", fdcpa_compliance_check_node)
    workflow.add_node("scra_bankruptcy_check", scra_bankruptcy_check_node)
    workflow.add_node("consumer_profile", lambda s: consumer_profile_node(s, llm=llm))
    workflow.add_node("debt_validation", debt_validation_node)
    workflow.add_node("payment_plan_optimizer", payment_plan_optimizer_node)
    workflow.add_node("collections_strategy", lambda s: collections_strategy_node(s, llm=llm))
    workflow.add_node("risk_scoring", risk_scoring_node)
    workflow.add_node("routing_decision", routing_decision_node)
    workflow.add_node("human_review_gate", human_review_gate_node)
    workflow.add_node(
        "communication_drafting",
        lambda s: communication_drafting_node(s, llm=llm, institution_name=institution_name)
    )
    workflow.add_node("audit_finalize", audit_finalize_node)

    # Entry point
    workflow.set_entry_point("debt_intake")

    # Linear edges (Nodes 1-9)
    workflow.add_edge("debt_intake", "fdcpa_compliance_check")
    workflow.add_edge("fdcpa_compliance_check", "scra_bankruptcy_check")
    workflow.add_edge("scra_bankruptcy_check", "consumer_profile")
    workflow.add_edge("consumer_profile", "debt_validation")
    workflow.add_edge("debt_validation", "payment_plan_optimizer")
    workflow.add_edge("payment_plan_optimizer", "collections_strategy")
    workflow.add_edge("collections_strategy", "risk_scoring")
    workflow.add_edge("risk_scoring", "routing_decision")

    # Conditional edge: routing_decision → HITL gate OR communication_drafting
    workflow.add_conditional_edges(
        "routing_decision",
        _route_after_routing_decision,
        {
            "human_review_gate":      "human_review_gate",
            "communication_drafting": "communication_drafting",
        }
    )

    # HITL → communication_drafting
    workflow.add_conditional_edges(
        "human_review_gate",
        _route_after_human_review,
        {
            "communication_drafting": "communication_drafting",
        }
    )

    # Final linear edges
    workflow.add_edge("communication_drafting", "audit_finalize")
    workflow.add_edge("audit_finalize", END)

    # Use MemorySaver in dev; PostgresSaver in production
    if checkpointer is None:
        checkpointer = get_checkpointer()  # PostgresSaver when DATABASE_URL is set; MemorySaver fallback (dev)

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review_gate"],
    )
