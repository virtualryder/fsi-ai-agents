# agent/graph.py
# ============================================================
# Trading Surveillance Agent — LangGraph StateGraph
#
# 12-node DAG:
#
#   alert_intake → data_enrichment → pattern_detection →
#   market_context → risk_scoring → routing_decision →
#
#   CRITICAL/HIGH → human_review_gate [HITL] →
#                   investigation → disposition →
#                   case_tracking_update → finalize
#
#   MEDIUM/LOW    → investigation → disposition →
#                   case_tracking_update → finalize
#
#   CLOSE_EXPLAINED / CLOSE_NO_ACTION (post-HITL) →
#                   investigation (abbreviated) →
#                   disposition → case_tracking_update → finalize
# ============================================================
from __future__ import annotations

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from agent.persistence import get_checkpointer

from agent.nodes import (
    alert_intake_node,
    case_tracking_update_node,
    data_enrichment_node,
    disposition_node,
    finalize_node,
    human_review_gate,
    investigation_node,
    market_context_node,
    pattern_detection_node,
    risk_scoring_node,
    routing_decision_node,
)
from agent.state import TradingSurveillanceState


# ── Conditional Routing Functions ─────────────────────────────────────────────

def _route_after_routing_decision(state: TradingSurveillanceState) -> str:
    """
    After scoring and routing:
    - human_review_required → pause at human_review_gate (CRITICAL/HIGH)
    - otherwise → proceed directly to investigation
    """
    if state.get("human_review_required"):
        return "human_review_gate"
    return "investigation_node"


def _route_after_human_review(state: TradingSurveillanceState) -> str:
    """
    After compliance officer submits decision:
    - All decisions proceed to investigation (which handles CLOSE decisions internally)
    """
    return "investigation_node"


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_trading_surveillance_graph(use_memory: bool = True):
    """
    Compile and return the trading surveillance StateGraph.

    Args:
        use_memory: If True, uses MemorySaver for HITL interrupt support.
                    Set False for testing without checkpoint persistence.
                    Production: use PostgresSaver for durable state.

    Returns:
        Compiled LangGraph application.
    """
    builder = StateGraph(TradingSurveillanceState)

    # Register nodes
    builder.add_node("alert_intake", alert_intake_node)
    builder.add_node("data_enrichment", data_enrichment_node)
    builder.add_node("pattern_detection", pattern_detection_node)
    builder.add_node("market_context", market_context_node)
    builder.add_node("risk_scoring", risk_scoring_node)
    builder.add_node("routing_decision", routing_decision_node)
    builder.add_node("human_review_gate", human_review_gate)
    builder.add_node("investigation_node", investigation_node)
    builder.add_node("disposition", disposition_node)
    builder.add_node("case_tracking_update", case_tracking_update_node)
    builder.add_node("finalize", finalize_node)

    # Linear sequence through analysis pipeline
    builder.set_entry_point("alert_intake")
    builder.add_edge("alert_intake", "data_enrichment")
    builder.add_edge("data_enrichment", "pattern_detection")
    builder.add_edge("pattern_detection", "market_context")
    builder.add_edge("market_context", "risk_scoring")
    builder.add_edge("risk_scoring", "routing_decision")

    # Conditional: route to HITL gate or skip directly to investigation
    builder.add_conditional_edges(
        "routing_decision",
        _route_after_routing_decision,
        {
            "human_review_gate": "human_review_gate",
            "investigation_node": "investigation_node",
        },
    )

    # After HITL decision: always proceed to investigation
    builder.add_conditional_edges(
        "human_review_gate",
        _route_after_human_review,
        {
            "investigation_node": "investigation_node",
        },
    )

    # Linear through disposition and close
    builder.add_edge("investigation_node", "disposition")
    builder.add_edge("disposition", "case_tracking_update")
    builder.add_edge("case_tracking_update", "finalize")
    builder.set_finish_point("finalize")

    # Compile with or without memory checkpointer
    if use_memory:
        checkpointer = get_checkpointer()  # PostgresSaver when DATABASE_URL is set; MemorySaver fallback (dev)
        app = builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["human_review_gate"],
        )
    else:
        app = builder.compile()

    return app


def get_graph_visualization() -> str:
    """Return a Mermaid diagram of the surveillance workflow."""
    return """
graph TD
    A[alert_intake] --> B[data_enrichment]
    B --> C[pattern_detection]
    C --> D[market_context]
    D --> E[risk_scoring]
    E --> F[routing_decision]
    F -->|CRITICAL/HIGH| G[human_review_gate HITL]
    F -->|MEDIUM/LOW| H[investigation_node LLM]
    G --> H
    H --> I[disposition LLM]
    I --> J[case_tracking_update]
    J --> K[finalize]

    style G fill:#ff9800,color:#fff
    style H fill:#2196F3,color:#fff
    style I fill:#2196F3,color:#fff
    style E fill:#4CAF50,color:#fff
    style F fill:#4CAF50,color:#fff
"""
