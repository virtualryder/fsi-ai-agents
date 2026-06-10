"""
Agent 11 — Model Risk Management Agent
LangGraph DAG assembly.

12-node graph with two conditional routing points:
  1. After routing_decision: HITL required → human_review_gate; else → audit_finalize
  2. After human_review_gate: APPROVE/CONDITIONALLY_APPROVE → audit_finalize;
     REQUIRE_REMEDIATION → audit_finalize (suspended);
     ESCALATE_TO_BOARD → audit_finalize (under review)

Security: the routing functions check `human_review_required is False` explicitly
(not falsy). A missing or undefined key defaults to human_review_gate (HITL),
ensuring fail-safe behavior. An unknown reviewer_decision → audit_finalize
without auto-approval — unknown decisions cannot trigger model approval.

HITL enforcement: interrupt_before=["human_review_gate"] is a LangGraph
framework-level directive. The graph physically cannot execute human_review_gate
or any subsequent node without a human reviewer submitting a decision via
graph.update_state() + graph.stream(None, config). This is not an application
if-statement — it is a framework constraint on graph execution.
"""

from typing import Any, Dict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.persistence import get_checkpointer

from .state import ModelRiskState
from .nodes import (
    model_inventory_lookup_node,
    data_sample_pull_node,
    conceptual_soundness_review_node,
    outcomes_analysis_node,
    population_stability_analysis_node,
    benchmark_comparison_node,
    sensitivity_analysis_node,
    risk_tier_determination_node,
    validation_narrative_node,
    routing_decision_node,
    human_review_gate_node,
    audit_finalize_node,
)


# ── Routing functions (Python-only — no LLM) ─────────────────────────────────

def _route_after_routing_decision(state: Dict[str, Any]) -> str:
    """
    Route after the routing_decision node.

    Explicit check for `is False` — not falsy. This means:
    - Missing key (None) → human_review_gate (fail-safe: HITL if unknown)
    - True → human_review_gate
    - False (explicitly set by Python) → audit_finalize (auto-complete)

    This design prevents undefined state from causing auto-completion of
    a model validation that should have had human review.
    """
    if state.get("human_review_required") is False:
        return "audit_finalize"
    return "human_review_gate"


def _route_after_human_review(state: Dict[str, Any]) -> str:
    """
    Route after the human_review_gate node.

    All reviewer decisions lead to audit_finalize — the difference is the
    validation_outcome set by human_review_gate_node:
    - APPROVE_VALIDATION → outcome=APPROVED → audit_finalize
    - CONDITIONALLY_APPROVE → outcome=CONDITIONALLY_APPROVED → audit_finalize
    - REQUIRE_REMEDIATION → outcome=SUSPENDED → audit_finalize
    - ESCALATE_TO_BOARD → outcome=UNDER_REVIEW → audit_finalize
    - Unknown/missing → outcome=UNDER_REVIEW → audit_finalize (fail-safe)

    Any unrecognized reviewer decision cannot trigger model approval.
    """
    return "audit_finalize"


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_model_risk_graph(checkpointer=None):
    """
    Construct and compile the 12-node Model Risk Management LangGraph DAG.

    Node execution order:
    1.  model_inventory_lookup   — load model from registry, compute schedule metadata
    2.  data_sample_pull         — load performance metrics for validation period
    3.  conceptual_soundness_review — LLM: design and assumption review
    4.  outcomes_analysis        — Python: compute degradation flags and material findings
    5.  population_stability_analysis — Python: PSI computation and classification
    6.  benchmark_comparison     — Python: challenger/benchmark comparison
    7.  sensitivity_analysis     — Python: weight, concentration, hard-rule coverage checks
    8.  risk_tier_determination  — Python: HITL conditions, routing, risk score
    9.  validation_narrative     — LLM: outcomes narrative + full validation report draft
    10. routing_decision         — Python: finalize routing flags
    11. human_review_gate        — HITL pause (interrupt_before) for MRO review
    12. audit_finalize           — compute next validation date, finalize audit trail

    interrupt_before=["human_review_gate"]: LangGraph framework instruction.
    The graph cannot execute node 11 or beyond without a human decision.
    """
    workflow = StateGraph(ModelRiskState)

    # Add all 12 nodes
    workflow.add_node("model_inventory_lookup", model_inventory_lookup_node)
    workflow.add_node("data_sample_pull", data_sample_pull_node)
    workflow.add_node("conceptual_soundness_review", conceptual_soundness_review_node)
    workflow.add_node("outcomes_analysis", outcomes_analysis_node)
    workflow.add_node("population_stability_analysis", population_stability_analysis_node)
    workflow.add_node("benchmark_comparison", benchmark_comparison_node)
    workflow.add_node("sensitivity_analysis", sensitivity_analysis_node)
    workflow.add_node("risk_tier_determination", risk_tier_determination_node)
    workflow.add_node("validation_narrative", validation_narrative_node)
    workflow.add_node("routing_decision", routing_decision_node)
    workflow.add_node("human_review_gate", human_review_gate_node)
    workflow.add_node("audit_finalize", audit_finalize_node)

    # Set entry point
    workflow.set_entry_point("model_inventory_lookup")

    # Linear edges: nodes 1-10
    workflow.add_edge("model_inventory_lookup", "data_sample_pull")
    workflow.add_edge("data_sample_pull", "conceptual_soundness_review")
    workflow.add_edge("conceptual_soundness_review", "outcomes_analysis")
    workflow.add_edge("outcomes_analysis", "population_stability_analysis")
    workflow.add_edge("population_stability_analysis", "benchmark_comparison")
    workflow.add_edge("benchmark_comparison", "sensitivity_analysis")
    workflow.add_edge("sensitivity_analysis", "risk_tier_determination")
    workflow.add_edge("risk_tier_determination", "validation_narrative")
    workflow.add_edge("validation_narrative", "routing_decision")

    # Conditional split at routing_decision
    workflow.add_conditional_edges(
        "routing_decision",
        _route_after_routing_decision,
        {
            "human_review_gate": "human_review_gate",
            "audit_finalize": "audit_finalize",
        },
    )

    # After human review: all paths → audit_finalize
    workflow.add_conditional_edges(
        "human_review_gate",
        _route_after_human_review,
        {
            "audit_finalize": "audit_finalize",
        },
    )

    # Terminal node
    workflow.add_edge("audit_finalize", END)

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review_gate"],
    )


def get_production_graph(postgres_connection_string: str):
    """
    Build graph with PostgresSaver for production use.

    PostgresSaver stores LangGraph checkpoints in Aurora PostgreSQL (multi-AZ).
    This enables:
    - Durable HITL pause state (MRO can close browser and resume)
    - Cross-instance resumption (any ECS Fargate task can resume any validation)
    - Checkpoint history for audit trail completeness

    The Aurora instance must have log_statement=none to prevent validation
    findings from appearing in database query logs. This is documented in the
    aws-deployment-guide.md and is a required pre-production configuration item.
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        checkpointer = PostgresSaver.from_conn_string(postgres_connection_string)
        return build_model_risk_graph(checkpointer=checkpointer)
    except ImportError:
        # Fall back to MemorySaver if postgres package not installed
        return build_model_risk_graph(checkpointer = get_checkpointer())


# ── Module-level graph instances ──────────────────────────────────────────────
# graph: development/demo instance with MemorySaver (in-process, non-durable)
# graph_no_checkpointer: for testing without state persistence

graph = build_model_risk_graph(checkpointer = get_checkpointer())
graph_no_checkpointer = build_model_risk_graph(checkpointer=None)
