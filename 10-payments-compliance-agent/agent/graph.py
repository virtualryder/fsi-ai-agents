# agent/graph.py
# ============================================================
# Payments Compliance Agent — LangGraph DAG Assembly
#
# ARCHITECTURE OVERVIEW
# ---------------------
# This module assembles the 12-node LangGraph StateGraph that
# implements the Payments Compliance Agent.
#
# WHY LANGGRAPH:
# LangGraph provides checkpoint-based state persistence,
# interrupt_before for deterministic human-in-the-loop
# pausing, and append-only audit trail semantics that map
# directly to regulatory record-keeping requirements.
#
# HUMAN-IN-THE-LOOP (HITL) DESIGN
# --------------------------------
# The graph is compiled with:
#   interrupt_before=["human_review_gate"]
#
# This instruction is enforced by the LangGraph framework —
# it is NOT an application-level if-statement that could be
# bypassed by a code path, LLM response, or prompt injection.
#
# When the routing_decision_node sets human_review_required=True,
# the graph pauses BEFORE human_review_gate executes. The state
# is persisted to the checkpoint database. Processing cannot
# resume until a human reviewer submits a decision through the
# checkpointer API.
#
# HITL TRIGGERS (all Python-determined, not LLM-determined):
#   - OFAC sanctions hit (mandatory — OFAC regulations require
#     human review before any action on a sanctioned entity)
#   - High-risk country wire (FATF / correspondent banking policy)
#   - SAR candidate (BSA requires human judgment for SAR filing)
#   - Unauthorized return (Reg E consumer protection)
#   - Reg E dispute (consumer financial protection)
#   - Late return flag (Nacha rule violations require legal review)
#   - SLA breach or imminent breach
#   - CRITICAL or HIGH risk tier
#   - Amount > $50,000 (escalation threshold)
#
# ROUTING LOGIC
# -------------
# Two conditional routing points:
#
# 1. After routing_decision_node:
#    - HITL trigger → human_review_gate (graph pauses)
#    - No HITL trigger → resolution_drafting (automated)
#
# 2. After human_review_gate:
#    - APPROVE_RESOLUTION or OVERRIDE_RESOLUTION → resolution_drafting
#    - ESCALATE or REJECT_CLAIM → audit_finalize
#
# FAIL-SAFE DEFAULTS:
# All routing functions default to the most conservative path
# (human_review_gate or audit_finalize) if state is unexpected.
# A missing or invalid reviewer decision never causes the graph
# to auto-resolve a disputed payment.
# ============================================================

from __future__ import annotations

from typing import Any, Dict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    audit_finalize_node,
    compliance_analysis_node,
    compliance_scoring_node,
    dispute_analysis_node,
    human_review_gate_node,
    nacha_validation_node,
    output_packaging_node,
    payment_intake_node,
    reg_e_assessment_node,
    resolution_drafting_node,
    routing_decision_node,
    sanctions_screening_node,
)
from .state import PaymentsComplianceState


# ── Conditional Routing Functions ────────────────────────────────────────────


def _route_after_routing_decision(state: Dict[str, Any]) -> str:
    """Determine whether to pause for human review or proceed automatically.

    SECURITY RATIONALE:
    This function is the ONLY mechanism that decides whether human review
    is required. It reads the Python-computed 'human_review_required' flag
    set by routing_decision_node. That flag is set by deterministic Python
    code, not by an LLM response.

    The routing_decision_node sets human_review_required=True for:
    - OFAC hit: Mandatory. Sanctioned-entity transactions require human
      authorization before any action (OFAC regulations, BSA).
    - High-risk country wire: FATF guidance and correspondent banking policy
      require human oversight for high-risk jurisdiction transactions.
    - SAR candidate: BSA requires that a qualified BSA officer, not an
      automated system, make the final SAR filing determination.
    - Unauthorized return (R07/R10/R29): Consumer may be harmed; Reg E
      requires documented human review.
    - Reg E dispute: 12 CFR 1005.11 investigation must have a human
      reviewer responsible for the determination.
    - Late return flag: Potential Nacha rule violation; legal review required.
    - SLA breach: Missed regulatory deadline requires escalation.
    - CRITICAL or HIGH risk tier: Risk tier above threshold requires human
      oversight per SR 11-7 model governance requirements.
    - Amount > $50,000: Escalation threshold for large-value payments.

    FAIL-SAFE DEFAULT:
    If 'human_review_required' is missing or its value is anything other
    than False, this function routes to human_review_gate. An absent value
    is treated as True. This ensures that undefined state never causes an
    automated resolution of a payment that should have human oversight.

    Returns:
        "human_review_gate" if review is required (default).
        "resolution_drafting" only if human_review_required is explicitly False.
    """
    # Explicit check for False — missing key defaults to HITL
    if state.get("human_review_required") is False:
        return "resolution_drafting"
    return "human_review_gate"


def _route_after_human_review(state: Dict[str, Any]) -> str:
    """Route based on the human reviewer's decision.

    SECURITY RATIONALE:
    Only two reviewer decisions lead to resolution drafting:
    - APPROVE_RESOLUTION: Reviewer confirms the automated resolution
      recommendation is correct.
    - OVERRIDE_RESOLUTION: Reviewer disagrees with the automated
      recommendation and provides a different resolution.

    Two reviewer decisions lead directly to finalization (no drafting):
    - ESCALATE: Reviewer sends to a higher authority. The escalation
      destination is recorded; no automated notice is sent.
    - REJECT_CLAIM: Reviewer determines the dispute claim is invalid.
      A denial notice will be drafted, but the resolution_drafting node
      handles that path.

    FAIL-SAFE DEFAULT:
    Any unrecognized or missing reviewer_decision routes to audit_finalize,
    not to resolution_drafting. An automated system should never draft
    and send customer notices without a clear, recognized human decision.
    This prevents edge cases where an LLM-assisted review workflow might
    inject an unrecognized decision string to trigger auto-drafting.

    Returns:
        "resolution_drafting" for APPROVE_RESOLUTION or OVERRIDE_RESOLUTION.
        "audit_finalize" for ESCALATE, REJECT_CLAIM, or any unrecognized value.
    """
    decision = state.get("reviewer_decision", "")
    if decision in ("APPROVE_RESOLUTION", "OVERRIDE_RESOLUTION"):
        return "resolution_drafting"
    # ESCALATE, REJECT_CLAIM, and any unrecognized values → finalize without drafting
    return "audit_finalize"


# ── Graph Factory ─────────────────────────────────────────────────────────────


def build_payments_compliance_graph(checkpointer=None):
    """Build and compile the 12-node Payments Compliance LangGraph DAG.

    GRAPH STRUCTURE
    ---------------
    Linear backbone (all payments traverse these nodes in order):

      payment_intake
          │
      sanctions_screening      ← OFAC/FATF (Python only — no LLM)
          │
      nacha_validation         ← Return windows, NOC codes, CTR threshold
          │
      reg_e_assessment         ← SLA deadlines, provisional credit, business-day calc
          │
      dispute_analysis         ← LLM: customer claim narrative analysis
          │
      compliance_scoring       ← Python: 5-factor composite, OFAC hard override
          │
      compliance_analysis      ← LLM: reviewer narrative synthesis
          │
      routing_decision         ← Python: target team + HITL flag

    Conditional split (routing function: _route_after_routing_decision):

      ├──[HITL required]──► human_review_gate  ← graph PAUSES here
      │                           │
      │                    reviewer submits decision
      │                           │
      │       ─────────────────────────────────────────────
      │       │                                           │
      │  APPROVE_RESOLUTION                         ESCALATE /
      │  OVERRIDE_RESOLUTION                        REJECT_CLAIM
      │       │                                           │
      │       ▼                                           │
      └──[auto-resolve]──► resolution_drafting            │
                                  │                       │
                              output_packaging             │
                                  │                       │
                              audit_finalize ◄─────────────
                                  │
                                 END

    HITL FRAMEWORK NOTE:
    interrupt_before=["human_review_gate"] is passed to graph.compile().
    This is a LangGraph framework instruction, not application code.
    The framework physically prevents the graph from executing
    human_review_gate (or any subsequent node) until a human decision
    is written to the checkpointer. No code path bypasses this.

    Args:
        checkpointer: LangGraph checkpointer instance.
            - MemorySaver (default): Suitable for development, single-process
              deployments, and tests. State is stored in memory — not durable.
            - PostgresSaver: Required for production. Provides durable state
              persistence so HITL reviews survive process restarts, horizontal
              scaling, and the multi-hour gaps typical in compliance workflows.

    Returns:
        Compiled LangGraph CompiledStateGraph instance.
    """
    builder = StateGraph(PaymentsComplianceState)

    # ── Add all 12 processing nodes ───────────────────────────────────────────

    # Node 1: Intake and validation
    # Validates the payment event, computes SHA-256 hash, masks account numbers
    # to last-4 digits. Account masking at intake ensures full account numbers
    # never appear in the LangGraph checkpoint database.
    builder.add_node("payment_intake", payment_intake_node)

    # Node 2: Sanctions screening (OFAC + FATF)
    # Pure Python — no LLM involvement. OFAC screening must be deterministic.
    # Checks originator/receiver countries against OFAC SDN list and FATF
    # high-risk/monitored jurisdictions. Sets ofac_hit flag and pep_flag.
    builder.add_node("sanctions_screening", sanctions_screening_node)

    # Node 3: Nacha validation
    # Checks return codes against NACHA_RETURN_WINDOWS dict. Detects NOC
    # (Notification of Change) codes. Flags CTR threshold ($10,000). Sets
    # unauthorized_return_eligible and late_return_flag.
    builder.add_node("nacha_validation", nacha_validation_node)

    # Node 4: Reg E assessment
    # Determines Reg E applicability (consumer EFT on consumer account).
    # Computes SLA deadlines: provisional credit (10 business days),
    # investigation (45/90 calendar days). Flags SLA breaches.
    # All computation in deterministic Python — no LLM.
    builder.add_node("reg_e_assessment", reg_e_assessment_node)

    # Node 5: Dispute analysis (LLM)
    # LLM-assisted analysis of the customer claim narrative. Assesses
    # dispute strength, identifies evidence present and needed, evaluates
    # unauthorized transaction indicators. LLM provides analysis to ASSIST
    # the human reviewer — LLM does NOT make the final determination.
    # PII is masked before this node via reg_e_assessment_node's masking pass.
    builder.add_node("dispute_analysis", dispute_analysis_node)

    # Node 6: Compliance scoring
    # Computes 5-factor composite risk score:
    #   sanctions_factor (35%), unauthorized_factor (25%), amount_factor (20%),
    #   sla_factor (10%), pattern_factor (10%)
    # OFAC hit is a hard override to CRITICAL — no score combination can
    # produce a lower tier. All scoring in Python, not LLM.
    builder.add_node("compliance_scoring", compliance_scoring_node)

    # Node 7: Compliance analysis (LLM)
    # LLM generates a reviewer-readable narrative summarizing the compliance
    # findings from Python nodes. Includes regulatory citations, anomaly flags,
    # SAR consideration rationale. Written to assist the reviewer, not to
    # replace reviewer judgment.
    builder.add_node("compliance_analysis", compliance_analysis_node)

    # Node 8: Routing decision
    # Python lookup table determines: target team, HITL flag, resolution type.
    # All routing logic is in Python constants (TARGET_TEAMS dict, ALWAYS_HITL
    # frozenset). No LLM response can alter routing.
    builder.add_node("routing_decision", routing_decision_node)

    # Node 9: Human review gate (HITL — framework-enforced pause point)
    # The graph PAUSES before this node (interrupt_before=["human_review_gate"]).
    # When resumed, this node processes the reviewer's decision:
    #   APPROVE_RESOLUTION, OVERRIDE_RESOLUTION, ESCALATE, REJECT_CLAIM
    # Reviewer can modify resolution type and provide notes.
    builder.add_node("human_review_gate", human_review_gate_node)

    # Node 10: Resolution drafting (LLM)
    # LLM drafts two outputs:
    #   1. Customer notice: Reg E required written notice (12 CFR 1005.11(d))
    #      Plain language, last-4 account numbers only, customer rights included.
    #   2. Internal memo: compliance findings, resolution rationale, follow-up
    #      actions, SAR recommendation.
    # LLM uses only masked data — full account numbers excluded from context.
    builder.add_node("resolution_drafting", resolution_drafting_node)

    # Node 11: Output packaging
    # Final PII masking verification pass. Assembles downstream_actions list.
    # Structures the output payload for downstream systems and case management.
    builder.add_node("output_packaging", output_packaging_node)

    # Node 12: Audit finalization
    # Records processing time, final status, resolution. Closes the audit
    # trail entry. Immutable after this node — append-only JSONL.
    builder.add_node("audit_finalize", audit_finalize_node)

    # ── Define the linear backbone edges ──────────────────────────────────────

    builder.add_edge(START, "payment_intake")
    builder.add_edge("payment_intake", "sanctions_screening")
    builder.add_edge("sanctions_screening", "nacha_validation")
    builder.add_edge("nacha_validation", "reg_e_assessment")
    builder.add_edge("reg_e_assessment", "dispute_analysis")
    builder.add_edge("dispute_analysis", "compliance_scoring")
    builder.add_edge("compliance_scoring", "compliance_analysis")
    builder.add_edge("compliance_analysis", "routing_decision")

    # ── Conditional split after routing_decision ───────────────────────────────

    builder.add_conditional_edges(
        "routing_decision",
        _route_after_routing_decision,
        {
            "human_review_gate": "human_review_gate",
            "resolution_drafting": "resolution_drafting",
        },
    )

    # ── Conditional split after human_review_gate ──────────────────────────────

    builder.add_conditional_edges(
        "human_review_gate",
        _route_after_human_review,
        {
            "resolution_drafting": "resolution_drafting",
            "audit_finalize": "audit_finalize",
        },
    )

    # ── Linear edges in the resolution path ───────────────────────────────────

    builder.add_edge("resolution_drafting", "output_packaging")
    builder.add_edge("output_packaging", "audit_finalize")
    builder.add_edge("audit_finalize", END)

    # ── Compile with HITL interrupt ────────────────────────────────────────────
    #
    # interrupt_before=["human_review_gate"] instructs the LangGraph framework
    # to pause graph execution before the human_review_gate node runs.
    # The state is checkpointed (persisted) at this point.
    #
    # Why this design:
    # - "interrupt_before" is framework-enforced — no application code bypasses it.
    # - The pause point is BEFORE the node runs, ensuring the human reviewer
    #   sees all compliance findings before making a decision.
    # - State durability (PostgresSaver in production) means the review queue
    #   survives process restarts, serverless cold starts, and scaling events.
    # - Thread IDs (config["configurable"]["thread_id"]) isolate each payment
    #   event in the checkpoint database — reviewers never see another event's state.
    #
    # interrupt_before only activates when human_review_required=True causes
    # _route_after_routing_decision to return "human_review_gate". For
    # auto-resolved payments, the graph bypasses human_review_gate entirely
    # and interrupt_before never fires.

    if checkpointer is None:
        checkpointer = MemorySaver()

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review_gate"],
    )


def get_production_graph(postgres_connection_string: str):
    """Build the payments compliance graph with PostgresSaver for production.

    WHY POSTGRESQL FOR PRODUCTION:
    MemorySaver (in-memory) is suitable only for development and testing.
    Production payments compliance workflows require:

    1. DURABILITY: A Reg E investigation takes up to 45 calendar days.
       The reviewer queue must survive process restarts, deployments,
       and infrastructure events during that window.

    2. SCALABILITY: Multiple compliance analysts review payments
       simultaneously. PostgreSQL provides the ACID guarantees needed
       for concurrent checkpoint reads and writes without race conditions.

    3. AUDITABILITY: The checkpoint database provides a complete record
       of when each state transition occurred, which reviewer submitted
       which decision, and what the state was at every step. This is
       required for regulatory examination by OCC, CFPB, and FDIC.

    4. RECOVERY: If an analyst's workstation fails mid-review, their
       work-in-progress state is preserved in PostgreSQL and can be
       resumed from another workstation.

    SECURITY NOTE:
    The PostgreSQL instance should use:
    - SSL/TLS (sslmode=require or sslmode=verify-full)
    - Aurora with at-rest encryption (KMS CMK)
    - log_statement=none (no query logging of payment data)
    - VPC-private subnet (no public internet access)
    - IAM database authentication where possible
    See docs/aws-deployment-guide.md for full configuration.

    Args:
        postgres_connection_string: PostgreSQL DSN with credentials.
            Format: postgresql://user:password@host:5432/dbname
            Prefer AWS Secrets Manager retrieval over hardcoded credentials.

    Returns:
        Compiled LangGraph CompiledStateGraph with PostgresSaver.
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        checkpointer = PostgresSaver.from_conn_string(postgres_connection_string)
        checkpointer.setup()  # Creates checkpoint tables if not present
        return build_payments_compliance_graph(checkpointer=checkpointer)
    except ImportError as exc:
        raise ImportError(
            "PostgresSaver requires langgraph-checkpoint-postgres. "
            "Install with: pip install langgraph-checkpoint-postgres psycopg2-binary"
        ) from exc


# ── Module-Level Graph Instances ──────────────────────────────────────────────
#
# Two module-level instances are provided for convenience:
#
# graph: Uses MemorySaver checkpointer — suitable for development,
#   single-process deployments, and the Streamlit demo app.
#   State is stored in memory and does NOT persist across process restarts.
#
# graph_no_checkpointer: Compiled without a checkpointer — used in unit tests
#   to test node logic without checkpoint overhead. interrupt_before is NOT
#   active without a checkpointer, so HITL pause is not enforced in this mode.
#   Use only for testing node logic, never in production.
#
# For production deployment, use get_production_graph() with a PostgresSaver.

graph = build_payments_compliance_graph(checkpointer=MemorySaver())

graph_no_checkpointer = StateGraph(PaymentsComplianceState)
# Assemble without checkpointer for testing
graph_no_checkpointer.add_node("payment_intake", payment_intake_node)
graph_no_checkpointer.add_node("sanctions_screening", sanctions_screening_node)
graph_no_checkpointer.add_node("nacha_validation", nacha_validation_node)
graph_no_checkpointer.add_node("reg_e_assessment", reg_e_assessment_node)
graph_no_checkpointer.add_node("dispute_analysis", dispute_analysis_node)
graph_no_checkpointer.add_node("compliance_scoring", compliance_scoring_node)
graph_no_checkpointer.add_node("compliance_analysis", compliance_analysis_node)
graph_no_checkpointer.add_node("routing_decision", routing_decision_node)
graph_no_checkpointer.add_node("human_review_gate", human_review_gate_node)
graph_no_checkpointer.add_node("resolution_drafting", resolution_drafting_node)
graph_no_checkpointer.add_node("output_packaging", output_packaging_node)
graph_no_checkpointer.add_node("audit_finalize", audit_finalize_node)
graph_no_checkpointer.add_edge(START, "payment_intake")
graph_no_checkpointer.add_edge("payment_intake", "sanctions_screening")
graph_no_checkpointer.add_edge("sanctions_screening", "nacha_validation")
graph_no_checkpointer.add_edge("nacha_validation", "reg_e_assessment")
graph_no_checkpointer.add_edge("reg_e_assessment", "dispute_analysis")
graph_no_checkpointer.add_edge("dispute_analysis", "compliance_scoring")
graph_no_checkpointer.add_edge("compliance_scoring", "compliance_analysis")
graph_no_checkpointer.add_edge("compliance_analysis", "routing_decision")
graph_no_checkpointer.add_conditional_edges(
    "routing_decision",
    _route_after_routing_decision,
    {
        "human_review_gate": "human_review_gate",
        "resolution_drafting": "resolution_drafting",
    },
)
graph_no_checkpointer.add_conditional_edges(
    "human_review_gate",
    _route_after_human_review,
    {
        "resolution_drafting": "resolution_drafting",
        "audit_finalize": "audit_finalize",
    },
)
graph_no_checkpointer.add_edge("resolution_drafting", "output_packaging")
graph_no_checkpointer.add_edge("output_packaging", "audit_finalize")
graph_no_checkpointer.add_edge("audit_finalize", END)
graph_no_checkpointer = graph_no_checkpointer.compile()
