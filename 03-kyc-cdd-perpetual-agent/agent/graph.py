# agent/graph.py
# ============================================================
# LangGraph KYC/CDD Perpetual Review Workflow DAG
#
# Graph architecture:
#   trigger_evaluation → customer_risk_profile → document_collection →
#   watchlist_screening → adverse_media_check → risk_rescoring →
#   [routing_decision] → {
#     PASS           → kyc_record_update → finalize_review
#     RISK_UPGRADE   → edd_package_generation? → rm_notification →
#                      human_review_gate → kyc_record_update → finalize_review
#     RISK_DOWNGRADE → rm_notification → human_review_gate →
#                      kyc_record_update → finalize_review
#     EDD_REQUIRED   → edd_package_generation → rm_notification →
#                      human_review_gate → kyc_record_update → finalize_review
#     ESCALATE       → human_review_gate → finalize_review
#     REL_EXIT       → human_review_gate → finalize_review
#   }
#
# LangGraph concepts:
#   - StateGraph with KYCReviewState TypedDict
#   - add_conditional_edges: risk-based routing after scoring
#   - MemorySaver: enables human-in-the-loop interrupt at review gate
#   - compile(interrupt_before=["human_review_gate"]): pauses for officer review
#
# Regulatory rationale for this structure:
#   The sequential node order mirrors the FFIEC BSA/AML Examination Manual's
#   recommended KYC program workflow. The graph structure enforces that
#   watchlist screening and adverse media always precede risk rescoring —
#   you cannot compute a final risk score without screening all parties.
# ============================================================

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.persistence import get_checkpointer

from agent.state import KYCReviewState, ReviewOutcome
from agent.nodes import (
    trigger_evaluation,
    customer_risk_profile,
    document_collection,
    watchlist_screening,
    adverse_media_check,
    risk_rescoring,
    edd_package_generation,
    rm_notification,
    human_review_gate,
    kyc_record_update,
    finalize_review,
    initiate_relationship_exit,
)

logger = logging.getLogger(__name__)


def _route_after_scoring(state: KYCReviewState) -> str:
    """
    Conditional routing function called after risk_rescoring.

    Maps the agent's recommended_outcome to the appropriate next node.
    This is deterministic Python — not LLM output.

    Routing logic:
    - PASS:              Skip EDD and human review → directly update record
    - RISK_UPGRADE:      EDD may be required; RM notification; human review
    - RISK_DOWNGRADE:    RM notification; human review (downgrade needs approval too)
    - EDD_REQUIRED:      Generate EDD package → RM notification → human review
    - ESCALATE:          Direct to human review gate (senior compliance)
    - RELATIONSHIP_EXIT: Initiate exit process → human review gate
    """
    outcome = state.get("recommended_outcome")

    # Hard overrides: OFAC hit or PEP with adverse media → always escalate
    if state.get("ofac_hit"):
        logger.warning(f"Review {state.get('review_id')}: OFAC hit detected — forced ESCALATE")
        return "human_review_gate"

    if outcome == ReviewOutcome.PASS:
        return "kyc_record_update"
    elif outcome == ReviewOutcome.RISK_UPGRADE:
        return "edd_package_generation"   # risk upgrade may also trigger EDD
    elif outcome == ReviewOutcome.RISK_DOWNGRADE:
        return "rm_notification"
    elif outcome == ReviewOutcome.EDD_REQUIRED:
        return "edd_package_generation"
    elif outcome == ReviewOutcome.ESCALATE:
        return "human_review_gate"
    elif outcome == ReviewOutcome.RELATIONSHIP_EXIT:
        return "initiate_relationship_exit"
    else:
        # Default to human review for any unexpected outcome
        logger.warning(f"Review {state.get('review_id')}: Unexpected outcome {outcome} — routing to human review")
        return "human_review_gate"


def build_kyc_review_graph(use_memory: bool = True):
    """
    Build and compile the KYC/CDD perpetual review LangGraph workflow.

    Args:
        use_memory: If True, use in-memory checkpointing for human-in-the-loop
                    review gates. In production, replace with PostgresSaver for
                    durable state persistence across sessions.

    Returns:
        Compiled LangGraph StateGraph.

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Production deployment:
    #   from langgraph.checkpoint.postgres import PostgresSaver
    #   checkpointer = PostgresSaver(conn)
    # Enables:
    #   - Pause a review for days while awaiting EDD documents
    #   - Resume after Compliance Officer returns from leave
    #   - Full audit trail persistence (FFIEC expects records for 5+ years)
    # ──────────────────────────────────────────────────────────────────────────
    """
    logger.info("Building KYC/CDD perpetual review workflow graph...")

    workflow = StateGraph(KYCReviewState)

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTER REVIEW NODES
    # ══════════════════════════════════════════════════════════════════════════

    # NODE 1: Trigger Evaluation
    # Parse the review trigger, determine urgency level and review deadline.
    # Event-driven triggers (adverse media, OFAC hit) get tighter deadlines
    # than scheduled periodic reviews.
    workflow.add_node("trigger_evaluation", trigger_evaluation)

    # NODE 2: Customer Risk Profile
    # Load the current CDD record: risk tier, EDD status, PEP flag,
    # beneficial owners, expected transaction profile, document inventory.
    # This is the "pull the customer file" step.
    workflow.add_node("customer_risk_profile", customer_risk_profile)

    # NODE 3: Document Collection Assessment
    # Identify required documents for this customer type and risk tier.
    # Flag expired, missing, or soon-to-expire documents.
    # Generate document gap narrative for RM outreach.
    # Regulatory basis: FinCEN CDD Rule requires refreshing CDD records
    # on a risk-based schedule with updated, current documentation.
    workflow.add_node("document_collection", document_collection)

    # NODE 4: Watchlist Screening
    # Re-screen customer, all beneficial owners, and recent counterparties
    # against OFAC SDN, PEP lists, EU/UN sanctions, and internal watchlists.
    # This is NOT optional — OFAC screening is a continuous legal obligation,
    # not a one-time check at account opening.
    workflow.add_node("watchlist_screening", watchlist_screening)

    # NODE 5: Adverse Media Check
    # Search for negative news, regulatory actions, court records.
    # Required for EDD customers (FATF R.12) and triggered by adverse media events.
    # News often precedes list additions by months — this is an early warning system.
    workflow.add_node("adverse_media_check", adverse_media_check)

    # NODE 6: Risk Rescoring
    # Compute updated composite risk score (0-100) from all review findings.
    # Score drives the routing_decision conditional edge.
    # SR 11-7: score must be explainable — every component documented.
    workflow.add_node("risk_rescoring", risk_rescoring)

    # NODE 7: EDD Package Generation (conditional)
    # When EDD is required: generate the EDD document checklist and
    # draft the RM outreach communication requesting documents from the customer.
    # Only executed when routing_decision → edd_package_generation path.
    workflow.add_node("edd_package_generation", edd_package_generation)

    # NODE 8: RM Notification
    # Draft notification to the Relationship Manager summarizing:
    # - Review outcome, risk tier change (if any)
    # - Documents needed from customer (if any)
    # - Suggested customer-facing talking points
    workflow.add_node("rm_notification", rm_notification)

    # NODE 9: Human Review Gate
    # MANDATORY pause point for Compliance Officer review and approval.
    # Required for: risk tier changes, EDD triggers, escalations, exits.
    # The AI's recommended outcome is advisory — the Compliance Officer decides.
    # Implements LangGraph interrupt_before pattern.
    workflow.add_node("human_review_gate", human_review_gate)

    # NODE 10: Initiate Relationship Exit (conditional)
    # When risk exceeds institutional appetite: prepare exit documentation,
    # notify RM, calculate exit timeline per contractual obligations.
    workflow.add_node("initiate_relationship_exit", initiate_relationship_exit)

    # NODE 11: KYC Record Update
    # Write the approved risk tier and review findings to the official KYC record.
    # Set next scheduled review date based on approved risk tier.
    # Only executes AFTER human approval (or for PASS outcomes that skip review).
    workflow.add_node("kyc_record_update", kyc_record_update)

    # NODE 12: Finalize Review
    # Lock the audit trail, send final notifications, close the case.
    # Append-only audit log entry created — examination-ready.
    workflow.add_node("finalize_review", finalize_review)

    # ══════════════════════════════════════════════════════════════════════════
    # DEFINE GRAPH EDGES
    # ══════════════════════════════════════════════════════════════════════════

    # Entry point: every review starts with trigger evaluation
    workflow.set_entry_point("trigger_evaluation")

    # Sequential investigation pipeline
    # These four steps always execute in order before risk rescoring.
    # Regulatory rationale: FFIEC expects a documented, consistent sequence.
    workflow.add_edge("trigger_evaluation", "customer_risk_profile")
    workflow.add_edge("customer_risk_profile", "document_collection")
    workflow.add_edge("document_collection", "watchlist_screening")
    workflow.add_edge("watchlist_screening", "adverse_media_check")
    workflow.add_edge("adverse_media_check", "risk_rescoring")

    # Conditional routing after risk rescoring
    # The _route_after_scoring function determines the next node
    # based on recommended_outcome and hard-coded regulatory overrides (OFAC hits).
    workflow.add_conditional_edges(
        source="risk_rescoring",
        path=_route_after_scoring,
        path_map={
            "kyc_record_update": "kyc_record_update",       # PASS path
            "edd_package_generation": "edd_package_generation",   # EDD / risk upgrade
            "rm_notification": "rm_notification",           # risk downgrade
            "human_review_gate": "human_review_gate",       # escalate / OFAC
            "initiate_relationship_exit": "initiate_relationship_exit",  # exit
        },
    )

    # EDD package → RM notification → human review gate
    workflow.add_edge("edd_package_generation", "rm_notification")
    workflow.add_edge("rm_notification", "human_review_gate")

    # Relationship exit → human review gate (exit requires senior approval)
    workflow.add_edge("initiate_relationship_exit", "human_review_gate")

    # Human review gate → KYC record update (after approval)
    workflow.add_edge("human_review_gate", "kyc_record_update")

    # KYC record update → finalize (both PASS and approved-outcome paths)
    workflow.add_edge("kyc_record_update", "finalize_review")

    # End
    workflow.add_edge("finalize_review", END)

    # ══════════════════════════════════════════════════════════════════════════
    # COMPILE
    # ══════════════════════════════════════════════════════════════════════════
    if use_memory:
        checkpointer = get_checkpointer()  # PostgresSaver when DATABASE_URL is set; MemorySaver fallback (dev)
        # interrupt_before human_review_gate: the graph pauses here,
        # Streamlit UI collects the Compliance Officer's decision,
        # then graph.update_state() injects it before resuming.
        compiled_graph = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["human_review_gate"],
        )
    else:
        compiled_graph = workflow.compile()

    logger.info("KYC/CDD perpetual review graph built successfully.")
    return compiled_graph


def get_graph_visualization() -> str:
    """
    Return Mermaid diagram for the KYC review workflow.
    Used in README and documentation.
    """
    return """
graph TD
    A[📋 KYC Review Trigger] --> B[trigger_evaluation<br/>Parse Trigger · Set Deadline]
    B --> C[customer_risk_profile<br/>CDD Record · PEP Status<br/>Beneficial Owners]
    C --> D[document_collection<br/>Required Docs · Gap Analysis]
    D --> E[watchlist_screening<br/>OFAC SDN · PEP Lists<br/>EU/UN Sanctions]
    E --> F[adverse_media_check<br/>News · Court Records<br/>Regulatory Actions]
    F --> G[risk_rescoring<br/>Composite 0-100 Score<br/>8-Factor Breakdown]
    G --> H{{routing_decision}}
    H -->|PASS| L[kyc_record_update<br/>Update Record · Set Next Review]
    H -->|RISK_UPGRADE / EDD| I[edd_package_generation<br/>Document Checklist<br/>RM Draft Communication]
    H -->|RISK_DOWNGRADE| J[rm_notification<br/>Portfolio Summary<br/>Customer Talking Points]
    H -->|ESCALATE / OFAC Hit| K[👤 human_review_gate<br/>Compliance Officer Approval]
    H -->|RELATIONSHIP_EXIT| M[initiate_relationship_exit<br/>Exit Documentation<br/>Timeline Calculation]
    I --> J
    J --> K
    M --> K
    K --> L
    L --> N[finalize_review<br/>Audit Trail · Notifications<br/>Case Close]
    N --> O[END ✓]

    style A fill:#2196F3,color:#fff
    style H fill:#ffa500,color:#fff
    style K fill:#4CAF50,color:#fff
    style M fill:#ff4444,color:#fff
    style O fill:#9C27B0,color:#fff
"""
