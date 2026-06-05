"""
AML/TMS Enhancement Agent — LangGraph Workflow
Pre-queue false positive scoring graph.

Graph structure:
  ingest_raw_alert
    → customer_context_lookup
    → historical_pattern_check
    → extract_features_node
    → rule_based_prescoring
    → llm_false_positive_analysis
    → compute_composite_score_node
    → determine_routing
    → [conditional branch]
         SUPPRESS  → execute_suppression → finalize_scoring → END
         DOWNGRADE → execute_downgrade   → finalize_scoring → END
         PASS_THROUGH → enqueue_alert    → finalize_scoring → END
         ESCALATE  → execute_escalation  → finalize_scoring → END

Production checkpointing: replace MemorySaver with PostgresSaver
(psycopg2) for durable state across restarts and multi-instance deployments.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AlertScoringState
from agent.nodes import (
    ingest_raw_alert,
    customer_context_lookup,
    historical_pattern_check,
    extract_features_node,
    rule_based_prescoring,
    llm_false_positive_analysis,
    compute_composite_score_node,
    determine_routing,
    execute_suppression,
    execute_downgrade,
    enqueue_alert,
    execute_escalation,
    finalize_scoring,
)


def _route_alert(state: AlertScoringState) -> str:
    """
    Conditional edge: reads routing.decision to select the action branch.

    Falls back to 'enqueue_alert' (safe pass-through) if decision is missing.
    """
    decision = state.get("routing", {}).get("decision", "PASS_THROUGH")
    routing_map = {
        "SUPPRESS": "execute_suppression",
        "DOWNGRADE": "execute_downgrade",
        "PASS_THROUGH": "enqueue_alert",
        "ESCALATE": "execute_escalation",
    }
    return routing_map.get(decision, "enqueue_alert")


def build_graph():
    """
    Compile the alert scoring StateGraph.

    Returns a compiled LangGraph application ready to invoke with:
        app = build_graph()
        result = app.invoke({"raw_alert": alert}, config={"configurable": {"thread_id": alert_id}})
    """
    graph = StateGraph(AlertScoringState)

    # Register nodes
    graph.add_node("ingest_raw_alert", ingest_raw_alert)
    graph.add_node("customer_context_lookup", customer_context_lookup)
    graph.add_node("historical_pattern_check", historical_pattern_check)
    graph.add_node("extract_features_node", extract_features_node)
    graph.add_node("rule_based_prescoring", rule_based_prescoring)
    graph.add_node("llm_false_positive_analysis", llm_false_positive_analysis)
    graph.add_node("compute_composite_score_node", compute_composite_score_node)
    graph.add_node("determine_routing", determine_routing)
    graph.add_node("execute_suppression", execute_suppression)
    graph.add_node("execute_downgrade", execute_downgrade)
    graph.add_node("enqueue_alert", enqueue_alert)
    graph.add_node("execute_escalation", execute_escalation)
    graph.add_node("finalize_scoring", finalize_scoring)

    # Entry point
    graph.set_entry_point("ingest_raw_alert")

    # Linear edges (sequential scoring pipeline)
    graph.add_edge("ingest_raw_alert", "customer_context_lookup")
    graph.add_edge("customer_context_lookup", "historical_pattern_check")
    graph.add_edge("historical_pattern_check", "extract_features_node")
    graph.add_edge("extract_features_node", "rule_based_prescoring")
    graph.add_edge("rule_based_prescoring", "llm_false_positive_analysis")
    graph.add_edge("llm_false_positive_analysis", "compute_composite_score_node")
    graph.add_edge("compute_composite_score_node", "determine_routing")

    # Conditional routing branch
    graph.add_conditional_edges(
        "determine_routing",
        _route_alert,
        {
            "execute_suppression": "execute_suppression",
            "execute_downgrade": "execute_downgrade",
            "enqueue_alert": "enqueue_alert",
            "execute_escalation": "execute_escalation",
        },
    )

    # All action branches converge at finalize_scoring
    graph.add_edge("execute_suppression", "finalize_scoring")
    graph.add_edge("execute_downgrade", "finalize_scoring")
    graph.add_edge("enqueue_alert", "finalize_scoring")
    graph.add_edge("execute_escalation", "finalize_scoring")
    graph.add_edge("finalize_scoring", END)

    # In-memory checkpointing (swap to PostgresSaver in production)
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# Module-level singleton — import and reuse across Streamlit reruns
scoring_graph = build_graph()
