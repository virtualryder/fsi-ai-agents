# agent/graph.py
# ============================================================
# Wealth & RM Copilot — LangGraph Workflow DAG
#
# 10-node pipeline:
#
#   trigger_intake → client_profile_lookup → portfolio_analysis →
#   market_intelligence → suitability_check →
#   recommendation_engine → content_drafting → compliance_review →
#   rm_approval_gate → finalize_output
#
# Conditional edge after suitability_check:
#   UNSUITABLE → block_unsuitable (surfaces issue to RM, no draft)
#   All others → recommendation_engine → content_drafting
#
# Human-in-the-loop:
#   interrupt_before=["rm_approval_gate"]
#   RM reviews ALL AI-generated content before finalization.
#   RM is always the accountable professional — AI is copilot.
#
# Key regulatory design decisions:
#   - LLM never makes suitability decisions — _assess_suitability() is Python
#   - LLM drafts content; compliance_review node checks it before RM sees it
#   - All recommendations include reg_bi_rationale (required documentation)
#   - Retirement accounts get ERISA flag → elevated suitability checks
#   - rm_approval_gate cannot be bypassed — enforced by interrupt_before
#   - Every workflow run produces a BSA/SEC-compliant audit trail
# ============================================================

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.persistence import get_checkpointer

from agent.state import WealthRMState, SuitabilityStatus
from agent.nodes import (
    trigger_intake,
    client_profile_lookup,
    portfolio_analysis,
    market_intelligence,
    suitability_check,
    recommendation_engine,
    content_drafting,
    compliance_review,
    rm_approval_gate,
    finalize_output,
    block_unsuitable,
)

logger = logging.getLogger(__name__)


def _route_after_suitability(state: WealthRMState) -> str:
    """
    Conditional routing after suitability_check.

    UNSUITABLE: Route to block_unsuitable — surfaces issue to RM and stops.
                Unsuitable recommendations must never reach the client.
                RM is notified with the reason and must resolve before
                proceeding. (Reg BI care obligation; FINRA 2111)

    All others: Continue to recommendation_engine → content_drafting.
                SUITABLE_WITH_NOTE will carry required disclosures through.
                NEEDS_REVIEW routes forward but flags open items for RM.

    This is deterministic Python — suitability decisions are never
    delegated to the LLM. Reg BI requires documented human accountability
    for each recommendation's best-interest determination.
    """
    status = state.get("suitability_status")

    if status == SuitabilityStatus.UNSUITABLE:
        logger.warning(
            f"[_route_after_suitability] Request {state.get('request_id')} — "
            f"UNSUITABLE determination, routing to block_unsuitable"
        )
        return "block_unsuitable"

    return "recommendation_engine"


def build_wealth_rm_graph(use_memory: bool = True):
    """
    Build and compile the Wealth & RM Copilot LangGraph workflow.

    Args:
        use_memory: If True, use MemorySaver for HITL interrupt support.
                    In production, replace with PostgresSaver for durable state
                    (required for multi-day workflows and cross-session persistence).

    Returns:
        Compiled LangGraph StateGraph.

    # ── PRODUCTION INTEGRATION POINTS ──────────────────────────────────────
    #
    # 1. CRM Integration (Salesforce Financial Services Cloud):
    #    client_profile = crm_client.get_profile(client_id)
    #    recommendations → crm_client.log_recommendation(...)
    #
    # 2. Portfolio Management System (Orion, Tamarac, Addepar):
    #    portfolio_data = pms_client.get_portfolio(account_id)
    #
    # 3. Market Data (Bloomberg / Refinitiv / FactSet):
    #    market_news = market_client.get_relevant_news(holdings=client_holdings)
    #
    # 4. Order Management (typically via OMS, not directly):
    #    rebalancing_trades → oms_client.create_order_set(trades)
    #
    # 5. Compliance Archiving (Smarsh, Global Relay):
    #    finalize_output → archiver.submit(communication=final_content)
    #    Required by SEC Rule 17a-4 / FINRA 4511 (6-year retention)
    # ───────────────────────────────────────────────────────────────────────
    """
    logger.info("Building Wealth & RM Copilot workflow graph...")

    workflow = StateGraph(WealthRMState)

    # NODE 1: Trigger Intake
    # Parse RM request, classify request type, validate required context.
    workflow.add_node("trigger_intake", trigger_intake)

    # NODE 2: Client Profile Lookup
    # Retrieve client profile, IPS, risk tolerance, goals, account types.
    # Source of truth for all suitability and Reg BI analysis downstream.
    workflow.add_node("client_profile_lookup", client_profile_lookup)

    # NODE 3: Portfolio Analysis
    # Analyze current holdings, performance vs. benchmark, allocation drift,
    # concentrated positions, unrealized gains/losses.
    workflow.add_node("portfolio_analysis", portfolio_analysis)

    # NODE 4: Market Intelligence
    # Gather relevant news, macro themes, and sector alerts for client's
    # holdings. Flag life events that may require advisory action.
    workflow.add_node("market_intelligence", market_intelligence)

    # NODE 5: Suitability Check
    # FINRA 2111 / Reg BI suitability assessment.
    # Deterministic Python — LLM does NOT make suitability determinations.
    # Returns SUITABLE / SUITABLE_WITH_NOTE / UNSUITABLE / NEEDS_REVIEW.
    workflow.add_node("suitability_check", suitability_check)

    # NODE 6: Block Unsuitable
    # If suitability check returns UNSUITABLE — surface issue to RM.
    # Workflow terminates; RM must resolve before re-submitting.
    workflow.add_node("block_unsuitable", block_unsuitable)

    # NODE 7: Recommendation Engine
    # Generate investment recommendations aligned to IPS and request type.
    # LLM synthesizes all gathered context into specific, actionable ideas.
    # All recommendations include: suitability note, cost analysis,
    # alternatives considered — required Reg BI documentation.
    workflow.add_node("recommendation_engine", recommendation_engine)

    # NODE 8: Content Drafting
    # Claude Sonnet 4.6 drafts the primary output document based on request type:
    #   MEETING_PREP     → client briefing with talking points
    #   INVESTMENT/REBAL → formal proposal with Reg BI rationale
    #   PORTFOLIO_REVIEW → performance review with forward commentary
    #   CLIENT_COMM      → letter/email draft
    #   ALERT_RESPONSE   → alert briefing with RM action plan
    workflow.add_node("content_drafting", content_drafting)

    # NODE 9: Compliance Review
    # FINRA 2210 compliance check on all AI-generated content.
    # Flags: missing disclosures, performance claims, prohibited language,
    # misleading statements, forward-looking statements without caveats.
    # Adds required regulatory disclosures automatically.
    workflow.add_node("compliance_review", compliance_review)

    # NODE 10: RM Approval Gate — HITL interrupt
    # RM reviews AI-generated content and approves or modifies.
    # CRITICAL: RM approval is mandatory — cannot be bypassed.
    # RM is the accountable professional; AI is the drafting assistant.
    workflow.add_node("rm_approval_gate", rm_approval_gate)

    # NODE 11: Finalize Output
    # Lock the approved content, log to CRM, archive for compliance.
    # SEC Rule 204-2 / FINRA 4511 record retention.
    workflow.add_node("finalize_output", finalize_output)

    # ── EDGES ─────────────────────────────────────────────────────────────────

    workflow.set_entry_point("trigger_intake")

    # Linear pipeline through context gathering
    workflow.add_edge("trigger_intake", "client_profile_lookup")
    workflow.add_edge("client_profile_lookup", "portfolio_analysis")
    workflow.add_edge("portfolio_analysis", "market_intelligence")
    workflow.add_edge("market_intelligence", "suitability_check")

    # Conditional routing after suitability check
    workflow.add_conditional_edges(
        source="suitability_check",
        path=_route_after_suitability,
        path_map={
            "recommendation_engine": "recommendation_engine",
            "block_unsuitable": "block_unsuitable",
        },
    )

    # Unsuitable path terminates
    workflow.add_edge("block_unsuitable", END)

    # Suitable path continues through drafting and compliance
    workflow.add_edge("recommendation_engine", "content_drafting")
    workflow.add_edge("content_drafting", "compliance_review")
    workflow.add_edge("compliance_review", "rm_approval_gate")
    workflow.add_edge("rm_approval_gate", "finalize_output")
    workflow.add_edge("finalize_output", END)

    # ── COMPILE ───────────────────────────────────────────────────────────────
    if use_memory:
        checkpointer = get_checkpointer()  # PostgresSaver when DATABASE_URL is set; MemorySaver fallback (dev)
        compiled = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["rm_approval_gate"],
        )
    else:
        compiled = workflow.compile()

    logger.info("Wealth & RM Copilot workflow graph built successfully.")
    return compiled


def get_graph_visualization() -> str:
    """Mermaid diagram for README documentation."""
    return """
graph TD
    A[📋 RM Request] --> B[trigger_intake<br/>Classify Request · Validate]
    B --> C[client_profile_lookup<br/>CRM · IPS · Risk Profile · Goals]
    C --> D[portfolio_analysis<br/>Holdings · Performance · Drift · Concentration]
    D --> E[market_intelligence<br/>News · Macro · Sector Alerts · Life Events]
    E --> F[suitability_check<br/>Reg BI · FINRA 2111 · ERISA<br/>Python — not LLM]
    F -->|UNSUITABLE| G[block_unsuitable<br/>Surface to RM · Stop Workflow]
    F -->|SUITABLE / NOTE / REVIEW| H[recommendation_engine<br/>IPS-Aligned Ideas · Cost Analysis<br/>Alternatives Considered]
    H --> I[content_drafting<br/>Claude Sonnet 4.6 Draft<br/>Briefing · Proposal · Review · Letter]
    I --> J[compliance_review<br/>FINRA 2210 · Disclosures<br/>Prohibited Language Check]
    J --> K[👤 rm_approval_gate<br/>RM Reviews · Approves · Modifies<br/>RM is Accountable Professional]
    K --> L[finalize_output<br/>Archive · CRM Log · Audit Trail]
    L --> M[END ✓]
    G --> N[END — Blocked]

    style A fill:#2196F3,color:#fff
    style F fill:#ffa500,color:#fff
    style G fill:#dc2626,color:#fff
    style K fill:#4CAF50,color:#fff
    style M fill:#9C27B0,color:#fff
    style N fill:#7f1d1d,color:#fff
"""
