# agent/graph.py
# ============================================================
# LangGraph Regulatory Change Management Workflow DAG
#
# Graph architecture:
#   change_intake → source_validation → scope_determination →
#   policy_mapping → gap_analysis → impact_scoring →
#   routing_decision → {
#     CRITICAL / HIGH → human_review_gate (HITL interrupt) →
#                       remediation_planning → stakeholder_notification →
#                       tracking_update → finalize
#     MEDIUM / LOW    → remediation_planning → stakeholder_notification →
#                       tracking_update → finalize
#     NOT_APPLICABLE  → tracking_update → finalize
#   }
#
# LangGraph concepts:
#   - StateGraph with ChangeManagementState TypedDict
#   - add_conditional_edges: impact-tier-based routing after scoring
#   - MemorySaver: enables HITL interrupt at human_review_gate
#   - compile(interrupt_before=["human_review_gate"]): pauses for officer review
#
# Regulatory rationale:
#   The sequential node order mirrors the FFIEC Regulatory Change
#   Management program best practice: identify → scope → analyze →
#   assess → assign → implement → document.
# ============================================================

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import ChangeManagementState, ImpactTier, CaseStatus
from agent.nodes import (
    change_intake_node,
    source_validation_node,
    scope_determination_node,
    policy_mapping_node,
    gap_analysis_node,
    impact_scoring_node,
    routing_decision_node,
    human_review_gate,
    remediation_planning_node,
    stakeholder_notification_node,
    tracking_update_node,
    finalize_node,
)

logger = logging.getLogger(__name__)


def _route_after_routing_decision(state: ChangeManagementState) -> str:
    """
    Conditional routing function called after routing_decision_node.

    Determines whether the workflow requires a human review gate
    (CRITICAL/HIGH/enforcement actions) or can proceed directly
    to remediation planning (MEDIUM/LOW).

    Also handles:
    - Source not validated: route to tracking_update to log and close
    - Not applicable: route to tracking_update to log

    This is deterministic Python — not LLM output.
    """
    # Source not validated or not applicable → skip to tracking
    if not state.get("source_validated", True):
        logger.warning(
            f"Change {state.get('change_id')}: Unvalidated source — routing to tracking for review"
        )
        return "tracking_update_node"

    if state.get("is_applicable") is False:
        logger.info(f"Change {state.get('change_id')}: Not applicable — routing to tracking")
        return "tracking_update_node"

    # Compliance officer already decided NOT_APPLICABLE in a previous run (resumed workflow)
    if state.get("compliance_officer_decision") == "NOT_APPLICABLE":
        return "tracking_update_node"

    # HITL required for CRITICAL, HIGH, or enforcement actions
    if state.get("human_review_required", False):
        return "human_review_gate"

    # MEDIUM and LOW skip directly to remediation
    return "remediation_planning_node"


def _route_after_human_review(state: ChangeManagementState) -> str:
    """
    Conditional routing after the human review gate completes.

    The Compliance Officer may decide:
    - APPROVED / MODIFIED → proceed to remediation planning
    - NOT_APPLICABLE → skip remediation, go to tracking
    - ESCALATED → skip remediation, go to tracking (as escalated case)
    """
    decision = state.get("compliance_officer_decision", "APPROVED")

    if decision in ("NOT_APPLICABLE", "ESCALATED"):
        return "tracking_update_node"

    return "remediation_planning_node"


def build_regulatory_change_graph(use_memory: bool = True):
    """
    Build and compile the Regulatory Change Management LangGraph workflow.

    Args:
        use_memory: If True, use MemorySaver for HITL interrupt support.
                    In production, replace with PostgresSaver for durable
                    state persistence (changes may take weeks to implement).

    Returns:
        Compiled LangGraph StateGraph.

    # ── INTEGRATION POINT ──────────────────────────────────────────────────
    # Production deployment:
    #   from langgraph.checkpoint.postgres import PostgresSaver
    #   checkpointer = PostgresSaver(conn)
    # Enables:
    #   - Pause a change review for days while awaiting policy drafts
    #   - Resume after Compliance Officer returns from an examination trip
    #   - Full audit trail persistence (FFIEC expects records for 5+ years)
    # ──────────────────────────────────────────────────────────────────────
    """
    logger.info("Building Regulatory Change Management workflow graph...")

    workflow = StateGraph(ChangeManagementState)

    # ══════════════════════════════════════════════════════════════════════
    # REGISTER NODES
    # ══════════════════════════════════════════════════════════════════════

    # NODE 1: Change Intake
    # Normalize incoming regulatory change data (feed or manual entry).
    # Assigns change_id, calculates days_to_effective.
    workflow.add_node("change_intake_node", change_intake_node)

    # NODE 2: Source Validation
    # Confirm the issuing authority is a recognized regulator.
    # Assigns authority tier (TIER_1_FEDERAL_PRIMARY through UNRECOGNIZED).
    # Flags enforcement actions for mandatory HITL.
    workflow.add_node("source_validation_node", source_validation_node)

    # NODE 3: Scope Determination
    # Identify business lines, products, and operations potentially in scope.
    # Rule-based lookup against domain → scope mapping table.
    workflow.add_node("scope_determination_node", scope_determination_node)

    # NODE 4: Policy Mapping
    # Map the regulatory change to the institution's policy registry.
    # Identifies which policies/procedures may need updating.
    workflow.add_node("policy_mapping_node", policy_mapping_node)

    # NODE 5: Gap Analysis (LLM)
    # Compare regulatory requirements against current policies.
    # LLM produces the gap narrative and identified gaps list.
    # This is the core analytical value of the agent.
    workflow.add_node("gap_analysis_node", gap_analysis_node)

    # NODE 6: Impact Scoring (Python)
    # Compute composite impact score from 5 weighted components.
    # Assigns CRITICAL / HIGH / MEDIUM / LOW impact tier.
    # SR 11-7: deterministic, documented, explainable.
    workflow.add_node("impact_scoring_node", impact_scoring_node)

    # NODE 7: Routing Decision (Python)
    # Assign compliance owner(s) and determine HITL requirement.
    # Escalates tier if compliance window is inadequate.
    workflow.add_node("routing_decision_node", routing_decision_node)

    # NODE 8: Human Review Gate (HITL interrupt)
    # Compliance Officer reviews gap analysis and approves/modifies/overrides.
    # LangGraph interrupt_before pauses the graph here for Streamlit UI interaction.
    # The AI's recommended outcome is advisory — the human decides.
    workflow.add_node("human_review_gate", human_review_gate)

    # NODE 9: Remediation Planning (LLM)
    # Draft a structured remediation plan with tasks, owners, and deadlines.
    # LLM produces the narrative; Python generates the structured task list.
    workflow.add_node("remediation_planning_node", remediation_planning_node)

    # NODE 10: Stakeholder Notification
    # Draft role-appropriate notifications for compliance owners,
    # business unit heads, and (for CRITICAL/HIGH) senior management/board.
    workflow.add_node("stakeholder_notification_node", stakeholder_notification_node)

    # NODE 11: Tracking Update
    # Write the summary record to the regulatory change register.
    # Sets the case as REMEDIATION_IN_PROGRESS or CLOSED_NOT_APPLICABLE.
    workflow.add_node("tracking_update_node", tracking_update_node)

    # NODE 12: Finalize
    # Complete the workflow — lock audit trail, set final status.
    workflow.add_node("finalize_node", finalize_node)

    # ══════════════════════════════════════════════════════════════════════
    # DEFINE GRAPH EDGES
    # ══════════════════════════════════════════════════════════════════════

    # Entry point
    workflow.set_entry_point("change_intake_node")

    # Sequential investigation pipeline — always executes in this order
    workflow.add_edge("change_intake_node", "source_validation_node")
    workflow.add_edge("source_validation_node", "scope_determination_node")
    workflow.add_edge("scope_determination_node", "policy_mapping_node")
    workflow.add_edge("policy_mapping_node", "gap_analysis_node")
    workflow.add_edge("gap_analysis_node", "impact_scoring_node")
    workflow.add_edge("impact_scoring_node", "routing_decision_node")

    # Conditional routing after routing_decision_node
    # CRITICAL/HIGH → human_review_gate
    # MEDIUM/LOW    → remediation_planning_node
    # Not applicable / unvalidated source → tracking_update_node
    workflow.add_conditional_edges(
        source="routing_decision_node",
        path=_route_after_routing_decision,
        path_map={
            "human_review_gate": "human_review_gate",
            "remediation_planning_node": "remediation_planning_node",
            "tracking_update_node": "tracking_update_node",
        },
    )

    # Conditional routing after human review gate
    # APPROVED/MODIFIED → remediation_planning_node
    # NOT_APPLICABLE/ESCALATED → tracking_update_node
    workflow.add_conditional_edges(
        source="human_review_gate",
        path=_route_after_human_review,
        path_map={
            "remediation_planning_node": "remediation_planning_node",
            "tracking_update_node": "tracking_update_node",
        },
    )

    # Remediation path → notifications → tracking → finalize
    workflow.add_edge("remediation_planning_node", "stakeholder_notification_node")
    workflow.add_edge("stakeholder_notification_node", "tracking_update_node")
    workflow.add_edge("tracking_update_node", "finalize_node")
    workflow.add_edge("finalize_node", END)

    # ══════════════════════════════════════════════════════════════════════
    # COMPILE
    # ══════════════════════════════════════════════════════════════════════
    if use_memory:
        checkpointer = MemorySaver()
        compiled_graph = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["human_review_gate"],
        )
    else:
        compiled_graph = workflow.compile()

    logger.info("Regulatory Change Management graph built successfully.")
    return compiled_graph


def get_graph_visualization() -> str:
    """Return Mermaid diagram for the workflow. Used in README."""
    return """
graph TD
    A[📋 Regulatory Change Input<br/>Feed / Manual Entry] --> B[change_intake_node<br/>Assign ID · Calculate Deadline]
    B --> C[source_validation_node<br/>Authority Tier · Jurisdiction]
    C --> D[scope_determination_node<br/>Business Lines · Products<br/>Operations]
    D --> E[policy_mapping_node<br/>Policy Registry Match<br/>Procedure Mapping]
    E --> F[gap_analysis_node 🤖<br/>LLM Gap Analysis<br/>Requirement vs. Policy]
    F --> G[impact_scoring_node<br/>Composite Score · Tier<br/>Authority + Urgency + Scope]
    G --> H[routing_decision_node<br/>Assign Owner · HITL Check]
    H -->|CRITICAL / HIGH| I[👤 human_review_gate<br/>Compliance Officer Review<br/>APPROVE / MODIFY / N/A]
    H -->|MEDIUM / LOW| J[remediation_planning_node 🤖<br/>LLM Remediation Plan<br/>Tasks · Owners · Timeline]
    H -->|Not Applicable| M[tracking_update_node<br/>Change Register Entry]
    I -->|Approved / Modified| J
    I -->|N/A / Escalated| M
    J --> K[stakeholder_notification_node 🤖<br/>Role-Tailored Notifications<br/>Compliance + BU + Exec]
    K --> M
    M --> N[finalize_node<br/>Audit Trail Lock · Status]
    N --> O[END ✓]

    style A fill:#2196F3,color:#fff
    style H fill:#ffa500,color:#fff
    style I fill:#4CAF50,color:#fff
    style O fill:#9C27B0,color:#fff
"""
