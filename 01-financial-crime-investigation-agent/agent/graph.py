# agent/graph.py
# ============================================================
# LangGraph Investigation Workflow DAG
#
# This file defines the directed acyclic graph (DAG) that orchestrates
# the complete AML investigation workflow. The graph mirrors the actual
# step-by-step process used by Financial Crimes Units at major US banks.
#
# Graph architecture:
#   alert_intake → customer_profile_lookup → transaction_analysis →
#   watchlist_screening → adverse_media_search → network_analysis →
#   risk_scoring → [routing_decision] → {
#     score > 70  → generate_sar → human_review_gate → finalize_case
#     score 30-70 → human_review_gate → finalize_case
#     score < 30  → close_case → finalize_case
#   }
#
# LangGraph concepts used:
#   - StateGraph: The main graph object
#   - add_node: Register each investigation step
#   - add_edge: Define sequential transitions
#   - add_conditional_edges: Route based on risk score
#   - compile: Create executable graph
#
# Regulatory context:
#   The graph structure ensures every investigation follows the same
#   documented process — a consistency requirement for BSA program
#   validation and OCC examination preparedness.
# ============================================================

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import InvestigationState
from agent.nodes import (
    alert_intake,
    customer_profile_lookup,
    transaction_analysis,
    watchlist_screening,
    adverse_media_search,
    network_analysis,
    risk_scoring,
    routing_decision,
    generate_sar,
    human_review_gate,
    close_case,
    finalize_case,
)

logger = logging.getLogger(__name__)


def build_investigation_graph(use_memory: bool = True):
    """
    Build and compile the AML investigation LangGraph workflow.

    This function creates the complete investigation workflow DAG.
    Call this once at application startup and reuse the compiled graph.

    Args:
        use_memory: If True, use in-memory checkpointing for conversation history.
                    In production, replace MemorySaver with PostgresSaver for
                    persistent state across sessions and system restarts.

    Returns:
        A compiled LangGraph StateGraph ready to invoke.

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # For production deployment with persistent state:
    # Replace MemorySaver with PostgresSaver:
    #   from langgraph.checkpoint.postgres import PostgresSaver
    #   from psycopg2 import connect
    #   conn = connect(os.getenv("DATABASE_URL"))
    #   checkpointer = PostgresSaver(conn)
    # This enables:
    #   - Resume interrupted investigations
    #   - Audit trail persistence across restarts
    #   - Multi-session investigation collaboration
    #   - 5-year BSA record retention requirement
    # ──────────────────────────────────────────────────────────────────────────
    """
    logger.info("Building AML investigation workflow graph...")

    # ── INITIALIZE THE STATE GRAPH ───────────────────────────────────────────
    # StateGraph takes the TypedDict that defines the investigation state.
    # Every node receives and returns this state — it's the "case file"
    # that accumulates evidence as the investigation progresses.
    workflow = StateGraph(InvestigationState)

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTER INVESTIGATION NODES
    # Each node represents one step in the FCU investigation workflow.
    # Order of registration doesn't determine execution order — that's set
    # by the edges defined below.
    # ══════════════════════════════════════════════════════════════════════════

    # NODE 1: Alert Intake
    # Parses the incoming TMS alert, extracts entities, forms initial hypothesis.
    # This is the "opening the case file" step.
    workflow.add_node("alert_intake", alert_intake)

    # NODE 2: Customer Profile Lookup
    # Retrieves KYC data, risk tier, EDD status, beneficial ownership.
    # Who is the subject? What do we already know about them?
    workflow.add_node("customer_profile_lookup", customer_profile_lookup)

    # NODE 3: Transaction Analysis
    # Analyzes 12 months of transaction history for AML typologies.
    # The core evidentiary step — "follow the money."
    workflow.add_node("transaction_analysis", transaction_analysis)

    # NODE 4: Watchlist Screening
    # OFAC SDN, PEP, EU/UN sanctions, and internal watchlist screening.
    # Legally required — not optional. OFAC hits require immediate action.
    workflow.add_node("watchlist_screening", watchlist_screening)

    # NODE 5: Adverse Media Search
    # Open-source intelligence — news, court records, regulatory actions.
    # Regulators expect this as part of a robust EDD program.
    workflow.add_node("adverse_media_search", adverse_media_search)

    # NODE 6: Network Analysis
    # Maps counterparty network, detects shell companies, circular flows.
    # The "who are they transacting with?" investigative deep-dive.
    workflow.add_node("network_analysis", network_analysis)

    # NODE 7: Risk Scoring
    # Aggregates all findings into a weighted composite 0-100 risk score.
    # Must be explainable and defensible (SR 11-7 model risk management).
    workflow.add_node("risk_scoring", risk_scoring)

    # NODE 8: Generate SAR (conditional — only if score > 70)
    # Produces a BSA-compliant SAR narrative draft for human review.
    # AI draft only — human BSA Officer must approve before filing.
    workflow.add_node("generate_sar", generate_sar)

    # NODE 9: Human Review Gate (all paths pass through this)
    # Creates a pause point for human-in-the-loop review and approval.
    # Ensures AI findings are always reviewed by a licensed BSA professional.
    workflow.add_node("human_review_gate", human_review_gate)

    # NODE 10: Close Case (low-risk path only)
    # Documents case closure with rationale for BSA records.
    # Even false positives need documented closure (5-year retention).
    workflow.add_node("close_case", close_case)

    # NODE 11: Finalize Case
    # Creates formal case record, logs audit trail, sends notifications.
    # The "filing the investigation report" final step.
    workflow.add_node("finalize_case", finalize_case)

    # ══════════════════════════════════════════════════════════════════════════
    # DEFINE GRAPH EDGES (INVESTIGATION FLOW)
    # Edges define the order of investigation steps.
    # Sequential edges represent the logical flow of an investigation.
    # ══════════════════════════════════════════════════════════════════════════

    # ── SET ENTRY POINT ───────────────────────────────────────────────────────
    # The graph always starts with alert_intake — this is the "new case" trigger.
    # In production, this is called when a TMS alert is assigned to the agent.
    workflow.set_entry_point("alert_intake")

    # ── STEP 1 → 2: Alert Intake → Customer Profile Lookup ────────────────────
    # After parsing the alert, immediately pull the customer's KYC record.
    # We need customer context before we can evaluate transaction patterns.
    # Regulatory reason: CDD Rule requires knowing your customer before assessing
    # whether their activity is suspicious (activity must be evaluated against
    # the customer's expected behavior profile).
    workflow.add_edge("alert_intake", "customer_profile_lookup")

    # ── STEP 2 → 3: Customer Profile → Transaction Analysis ───────────────────
    # With customer context established (who they are, expected behavior),
    # now analyze their actual transaction history.
    # Regulatory reason: Suspicious activity is defined relative to the customer's
    # normal behavior — a $50K wire is suspicious from a pizza restaurant,
    # normal from an import/export business.
    workflow.add_edge("customer_profile_lookup", "transaction_analysis")

    # ── STEP 3 → 4: Transaction Analysis → Watchlist Screening ───────────────
    # After identifying suspicious transaction patterns, screen all parties
    # involved (customer, counterparties) against sanctions lists.
    # Regulatory reason: OFAC screening must cover transactions, not just
    # account opening. A customer may be clean at onboarding but transact
    # with an SDN entity later.
    workflow.add_edge("transaction_analysis", "watchlist_screening")

    # ── STEP 4 → 5: Watchlist Screening → Adverse Media Search ───────────────
    # After formal list screening, check for reputational/open-source intelligence.
    # Regulatory reason: FATF and OCC expect adverse media as part of EDD.
    # Watchlists lag behind — a criminal may not be listed yet but have news coverage.
    workflow.add_edge("watchlist_screening", "adverse_media_search")

    # ── STEP 5 → 6: Adverse Media → Network Analysis ─────────────────────────
    # With individual entity checks complete, map the broader network.
    # Regulatory reason: FATF R.20 expects consideration of the transaction network.
    # Shell company detection and proximity analysis often reveals the most
    # compelling evidence of sophisticated money laundering.
    workflow.add_edge("adverse_media_search", "network_analysis")

    # ── STEP 6 → 7: Network Analysis → Risk Scoring ──────────────────────────
    # All evidence gathered — now synthesize into a composite risk score.
    # Regulatory reason: OCC expects a documented, consistent risk assessment
    # methodology. The score must be explainable (SR 11-7).
    workflow.add_edge("network_analysis", "risk_scoring")

    # ── STEP 7 → ROUTING: Risk Scoring → Conditional Routing ─────────────────
    # Based on the composite risk score, route to appropriate next step.
    # This conditional logic mirrors the three-way decision a senior analyst
    # makes after reviewing all investigation findings.
    workflow.add_conditional_edges(
        source="risk_scoring",
        path=routing_decision,
        path_map={
            # Score > 70: High confidence of suspicious activity → draft SAR
            "generate_sar": "generate_sar",
            # Score 30-70: Ambiguous → send to human review for decision
            "human_review_gate": "human_review_gate",
            # Score < 30: Low risk → close case with documented rationale
            "close_case": "close_case",
        },
    )

    # ── SAR PATH: Generate SAR → Human Review Gate ────────────────────────────
    # After SAR draft is generated, it MUST go to human review.
    # Regulatory reason: AI cannot autonomously file SARs. A licensed BSA Officer
    # must review, edit if needed, and approve before FinCEN electronic filing.
    # This is a non-negotiable human-in-the-loop control.
    workflow.add_edge("generate_sar", "human_review_gate")

    # ── CLOSE PATH: Close Case → Finalize ─────────────────────────────────────
    # Low-risk cases go directly from closure to finalization.
    # The finalize_case node creates the BSA-required case record.
    workflow.add_edge("close_case", "finalize_case")

    # ── HUMAN REVIEW → FINALIZE ───────────────────────────────────────────────
    # After human review and approval (or modification), finalize the case.
    # The human's decision is recorded in the state before this edge is taken.
    workflow.add_edge("human_review_gate", "finalize_case")

    # ── FINALIZE → END ────────────────────────────────────────────────────────
    # Finalization is the last step — case record created, audit trail locked,
    # notifications sent. The graph terminates here.
    workflow.add_edge("finalize_case", END)

    # ══════════════════════════════════════════════════════════════════════════
    # COMPILE THE GRAPH
    # The compile step validates the graph structure (no orphan nodes,
    # valid edge targets) and creates the executable runnable.
    # ══════════════════════════════════════════════════════════════════════════

    if use_memory:
        # MemorySaver enables checkpointing — state is persisted between
        # graph invocations, enabling human-in-the-loop interrupts.
        # In production, use PostgresSaver for durable persistence.
        checkpointer = MemorySaver()
        compiled_graph = workflow.compile(checkpointer=checkpointer)
    else:
        # No checkpointing — used for testing
        compiled_graph = workflow.compile()

    logger.info("AML investigation workflow graph built successfully.")
    logger.info("Nodes: alert_intake → customer_profile_lookup → transaction_analysis → "
                "watchlist_screening → adverse_media_search → network_analysis → "
                "risk_scoring → [routing] → {generate_sar → human_review_gate | "
                "human_review_gate | close_case} → finalize_case → END")

    return compiled_graph


def get_graph_visualization() -> str:
    """
    Return a Mermaid diagram string representing the investigation workflow.
    Used in the README and documentation.

    Returns:
        Mermaid diagram markup string.
    """
    return """
graph TD
    A[🚨 TMS Alert Trigger] --> B[alert_intake<br/>Parse & Classify Alert]
    B --> C[customer_profile_lookup<br/>KYC / EDD / PEP Status]
    C --> D[transaction_analysis<br/>12-Month History<br/>Structuring · Layering · Velocity]
    D --> E[watchlist_screening<br/>OFAC SDN · PEP<br/>EU/UN Sanctions]
    E --> F[adverse_media_search<br/>News · Court Records<br/>Regulatory Actions]
    F --> G[network_analysis<br/>Counterparty Network<br/>Shell Companies · Circular Flows]
    G --> H[risk_scoring<br/>Composite 0-100 Score<br/>Weighted Methodology]
    H --> I{{routing_decision<br/>Score Threshold}}
    I -->|Score > 70| J[generate_sar<br/>BSA-Compliant SAR Draft]
    I -->|Score 30-70| K[human_review_gate<br/>👤 BSA Officer Review]
    I -->|Score < 30| L[close_case<br/>Document & Close]
    J --> K
    L --> M[finalize_case<br/>Case Record · Audit Trail<br/>Notifications]
    K --> M
    M --> N[END ✓]

    style A fill:#ff4444,color:#fff
    style I fill:#ffa500,color:#fff
    style J fill:#ff6b6b,color:#fff
    style K fill:#4CAF50,color:#fff
    style N fill:#2196F3,color:#fff
"""
