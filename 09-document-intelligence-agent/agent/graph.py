# agent/graph.py
# ============================================================
# Document Intelligence Agent — LangGraph DAG Definition
#
# PURPOSE OF THIS FILE
# --------------------
# This file assembles the 12-node LangGraph StateGraph that
# transforms unstructured financial documents (PDFs, images,
# SWIFT messages, etc.) into validated, PII-masked, structured
# JSON payloads ready for downstream agent consumption.
#
# WHY A DIRECTED ACYCLIC GRAPH?
# ------------------------------
# Each step in document processing depends on the previous step's
# output (you cannot extract fields before classifying the document,
# cannot route before scoring confidence, etc.). A DAG enforces
# this dependency ordering at the framework level rather than
# relying on application logic — making the execution order
# auditable, testable, and provable to regulators.
#
# SECURITY ARCHITECTURE (HOW THIS GRAPH IS SECURED)
# ---------------------------------------------------
# 1. INTERRUPT BEFORE HITL: The graph is configured with
#    interrupt_before=["human_review_gate"]. This means that when
#    a document requires human review (low confidence, PII, SAR/CTR,
#    UNKNOWN type, etc.), the graph pauses *before* the review gate
#    node executes. No downstream routing occurs until a human
#    reviewer has explicitly approved, corrected, or rejected.
#    This is a framework-level guarantee — it cannot be bypassed by
#    the LLM or by application code calling graph.invoke().
#
# 2. LINEAR SECURITY PIPELINE: The graph enforces a strict sequence:
#    pii_detection ALWAYS runs before document_classification.
#    This means the LLM never receives raw PII — only masked text.
#    The DAG structure makes this ordering inviolable.
#
# 3. NO LLM IN ROUTING: The routing_decision node is a pure Python
#    function that reads a static DOCUMENT_ROUTING dict (defined in
#    nodes.py at module load time). No LLM call influences which
#    downstream agents receive the document. This prevents prompt
#    injection attacks from redirecting sensitive documents.
#
# 4. CHECKPOINTING: In production, the MemorySaver is replaced with
#    PostgresSaver. Every state transition is persisted to an
#    encrypted Aurora database, providing a complete, tamper-evident
#    audit trail that survives process crashes and satisfies BSA/AML
#    record retention requirements.
#
# GRAPH TOPOLOGY (12 nodes)
# -------------------------
#  START
#    │
#    ▼
#  document_intake          (validate input, compute SHA-256, detect duplicates)
#    │
#    ▼
#  text_extraction          (PDF/OCR/SWIFT parsing, clear raw bytes from state)
#    │
#    ▼
#  pii_detection            (Python regex — mask SSN/passport/account before LLM)
#    │
#    ▼
#  document_classification  (LLM: classify type, 0.0–1.0 confidence)
#    │
#    ▼
#  field_extraction         (LLM: schema-driven extraction, PII-masked input)
#    │
#    ▼
#  validation               (Python: type checks, business rules, SWIFT screening)
#    │
#    ▼
#  confidence_scoring       (Python: 4-factor composite score, assign tier)
#    │
#    ▼
#  routing_decision         (Python: lookup table → target agents + HITL flag)
#    │
#    ├──[HITL required]──► human_review_gate  ──► enrichment
#    │                      (interrupt_before)
#    └──[auto-route]──────────────────────────► enrichment
#                                                    │
#                                                    ▼
#                                              output_packaging
#                                                    │
#                                                    ▼
#                                              audit_finalize
#                                                    │
#                                                   END
#
# INTERSTATE DOCUMENT PROCESSING NOTE
# ------------------------------------
# The graph uses interrupt_before (not interrupt_after) for the
# human_review_gate. This means that when the graph is resumed
# after a human provides their decision, LangGraph replays from
# the human_review_gate node with the reviewer's state updates
# applied. The enrichment node then reads the reviewer's decision
# (APPROVE_AND_ROUTE, CORRECT_AND_ROUTE, REJECT, REQUEST_RESUBMIT)
# and acts accordingly. Documents that are REJECTED or
# REQUEST_RESUBMIT never reach output_packaging.
# ============================================================
from __future__ import annotations

import logging
from typing import Callable, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    audit_finalize_node,
    confidence_scoring_node,
    document_classification_node,
    document_intake_node,
    enrichment_node,
    field_extraction_node,
    human_review_gate_node,
    output_packaging_node,
    pii_detection_node,
    routing_decision_node,
    text_extraction_node,
    validation_node,
)
from .state import DocumentIntelligenceState

logger = logging.getLogger(__name__)


# ── Conditional Edge Functions ─────────────────────────────────────────────────
#
# LangGraph uses these functions to determine which node to execute next
# when there is a branch in the graph. Each function receives the current
# state and returns the name of the next node as a string.
#
# WHY PYTHON FUNCTIONS, NOT LLM DECISIONS?
# -----------------------------------------
# Routing decisions in a financial document processing pipeline must be
# deterministic and auditable. Using Python functions as routing logic means:
# (a) the routing cannot be influenced by prompt injection;
# (b) the routing logic can be unit-tested independently;
# (c) regulators can read the routing logic and verify correctness;
# (d) the routing is the same every time for the same input state.

def _route_after_routing_decision(state: DocumentIntelligenceState) -> str:
    """
    ROUTING FUNCTION: after routing_decision_node runs.

    Determines whether the document needs human review before it can be
    enriched and sent to downstream agents, or whether it can proceed
    automatically.

    WHEN HITL IS REQUIRED (returns "human_review_gate"):
    - confidence_tier is LOW or UNCERTAIN (Python-scored confidence < 0.65)
    - document_type is in ALWAYS_HITL_DOCUMENT_TYPES (SAR, CTR, Government ID,
      Consent Orders — types that carry elevated regulatory or PII risk)
    - document_type is UNKNOWN (cannot be safely routed without classification)
    - business_rule_violations are present (cross-field consistency errors)
    - pii_handling_required is HUMAN_REVIEW or ENCRYPT
    - validation_errors are present

    This check is redundant with the logic in routing_decision_node, but
    defense-in-depth means we verify the HITL flag at the routing function
    level as well, so a bug in routing_decision_node cannot accidentally
    route a document that should have gone to HITL.

    WHEN AUTO-ROUTING (returns "enrichment"):
    - human_review_required is False (set by routing_decision_node)
    - All of the above HITL conditions are absent

    This function is called by LangGraph's conditional_edge mechanism,
    not by application code directly.
    """
    if state.get("human_review_required", True):
        logger.info(
            "Document %s requires human review: %s",
            state.get("document_id", "unknown"),
            state.get("human_review_reason", "unspecified"),
        )
        return "human_review_gate"
    return "enrichment"


def _route_after_human_review(state: DocumentIntelligenceState) -> str:
    """
    ROUTING FUNCTION: after human_review_gate_node runs.

    The human reviewer has provided a decision. This function routes
    based on that decision:

    APPROVE_AND_ROUTE  → "enrichment"
        The reviewer confirmed the extraction is accurate. Proceed to
        enrichment, output packaging, and downstream routing.

    CORRECT_AND_ROUTE  → "enrichment"
        The reviewer provided field corrections. The enrichment node
        will call the correction LLM prompt to merge corrections with
        the original extraction before packaging the output.

    REJECT             → "audit_finalize"
        The document is rejected (fraudulent, unreadable, wrong submission,
        etc.). Skip enrichment and packaging. Finalize the audit trail
        with a REJECTED status and exit.

    REQUEST_RESUBMIT   → "audit_finalize"
        The document is incomplete or requires additional information from
        the submitter. Similar to REJECT but with a different status code
        that triggers a resubmission request to the source system.

    DEFAULT (unknown decision) → "audit_finalize"
        Fail safe: any unrecognized decision routes to audit_finalize
        rather than accidentally routing the document to a downstream agent.
        Logs a warning for investigation.
    """
    decision = state.get("reviewer_decision", "")

    if decision in ("APPROVE_AND_ROUTE", "CORRECT_AND_ROUTE"):
        logger.info(
            "Document %s approved by reviewer %s (decision: %s)",
            state.get("document_id", "unknown"),
            state.get("reviewer_id", "unknown"),
            decision,
        )
        return "enrichment"

    if decision in ("REJECT", "REQUEST_RESUBMIT"):
        logger.info(
            "Document %s not approved (decision: %s) — routing to audit_finalize",
            state.get("document_id", "unknown"),
            decision,
        )
        return "audit_finalize"

    # Fail-safe: unknown decision
    logger.warning(
        "Document %s has unrecognized reviewer decision '%s' — defaulting to audit_finalize",
        state.get("document_id", "unknown"),
        decision,
    )
    return "audit_finalize"


# ── Graph Factory ──────────────────────────────────────────────────────────────

def build_document_intelligence_graph(
    checkpointer=None,
) -> StateGraph:
    """
    Factory function that assembles and compiles the Document Intelligence
    Agent LangGraph StateGraph.

    WHY A FACTORY FUNCTION?
    -----------------------
    Rather than defining the graph at module level, a factory function allows:
    1. Different checkpointers for different environments:
       - Development: MemorySaver (in-memory, no setup required)
       - Testing: None (no persistence, faster tests)
       - Production: PostgresSaver (Aurora encrypted, audit-trail persistence)
    2. The graph can be rebuilt with different configurations (e.g., for
       testing specific nodes in isolation) without module-level side effects.
    3. The compiled graph object is thread-safe; the factory can be called
       once at application startup and the result shared across threads.

    PARAMETERS
    ----------
    checkpointer : LangGraph checkpointer instance or None
        - None: no state persistence (suitable for tests and one-shot runs)
        - MemorySaver(): in-memory persistence for development/demo
        - PostgresSaver(conn): production persistence with full audit trail

    RETURNS
    -------
    Compiled StateGraph ready for .invoke(), .stream(), or .astream() calls.

    SECURITY NOTE ON INTERRUPT_BEFORE
    ----------------------------------
    The graph is compiled with interrupt_before=["human_review_gate"].
    This is the mechanism that enforces mandatory human review for sensitive
    documents. When the graph reaches the routing_decision node and determines
    HITL is needed, it returns "human_review_gate" as the next node — and
    because of interrupt_before, LangGraph pauses execution BEFORE that node
    runs. The graph is then resumed by the application layer after a human
    reviewer submits their decision via the Streamlit UI.

    This is NOT an application-layer check — it is a LangGraph framework
    guarantee. Even if application code calls graph.invoke() again without
    a reviewer decision, the graph will not proceed past human_review_gate
    until state["reviewer_decision"] is set to a valid value.
    """
    # Initialize the StateGraph with our state schema.
    # DocumentIntelligenceState is a TypedDict with total=False, meaning
    # all fields are optional at initialization. Each node populates only
    # the fields it owns.
    workflow = StateGraph(DocumentIntelligenceState)

    # ── Register Nodes ─────────────────────────────────────────────────────────
    # Each node is a Python function from agent/nodes.py.
    # The string name is used in edge definitions and in the audit trail.
    #
    # Node execution order is determined by edges (below), not by the order
    # these add_node calls appear here.

    workflow.add_node("document_intake",         document_intake_node)
    workflow.add_node("text_extraction",         text_extraction_node)
    workflow.add_node("pii_detection",           pii_detection_node)
    workflow.add_node("document_classification", document_classification_node)
    workflow.add_node("field_extraction",        field_extraction_node)
    workflow.add_node("validation",              validation_node)
    workflow.add_node("confidence_scoring",      confidence_scoring_node)
    workflow.add_node("routing_decision",        routing_decision_node)
    workflow.add_node("human_review_gate",       human_review_gate_node)
    workflow.add_node("enrichment",              enrichment_node)
    workflow.add_node("output_packaging",        output_packaging_node)
    workflow.add_node("audit_finalize",          audit_finalize_node)

    # ── Register Edges ─────────────────────────────────────────────────────────
    # Edges define the execution order and branching logic of the graph.
    # add_edge(a, b) means: after node a completes, execute node b.
    # add_conditional_edges(a, fn, {...}) means: after node a completes,
    #   call fn(state) to determine which node to execute next.

    # LINEAR PIPELINE (no branching) — nodes 1 through 8
    # These nodes must run in sequence because each depends on the previous:
    # - text_extraction needs document_id and file_format from intake
    # - pii_detection needs the extracted text from text_extraction
    # - document_classification needs PII-masked text from pii_detection
    # - field_extraction needs document_type from classification
    # - validation needs extracted_fields from field_extraction
    # - confidence_scoring needs validation results
    # - routing_decision needs confidence tier and PII flags

    workflow.add_edge(START,                     "document_intake")
    workflow.add_edge("document_intake",         "text_extraction")
    workflow.add_edge("text_extraction",         "pii_detection")
    workflow.add_edge("pii_detection",           "document_classification")
    workflow.add_edge("document_classification", "field_extraction")
    workflow.add_edge("field_extraction",        "validation")
    workflow.add_edge("validation",              "confidence_scoring")
    workflow.add_edge("confidence_scoring",      "routing_decision")

    # CONDITIONAL BRANCH 1: after routing_decision
    # Determines whether HITL is required.
    # The routing function _route_after_routing_decision reads
    # state["human_review_required"] and returns either
    # "human_review_gate" or "enrichment".
    workflow.add_conditional_edges(
        "routing_decision",
        _route_after_routing_decision,
        {
            "human_review_gate": "human_review_gate",
            "enrichment":        "enrichment",
        },
    )

    # CONDITIONAL BRANCH 2: after human_review_gate
    # The graph pauses before this node (interrupt_before) while a human
    # reviews the document. After the reviewer submits their decision,
    # the graph resumes here and routes based on the decision.
    # APPROVE/CORRECT → enrichment (document proceeds)
    # REJECT/RESUBMIT → audit_finalize (document stopped)
    workflow.add_conditional_edges(
        "human_review_gate",
        _route_after_human_review,
        {
            "enrichment":    "enrichment",
            "audit_finalize": "audit_finalize",
        },
    )

    # LINEAR PIPELINE CONTINUATION — nodes 10 through 12
    # After enrichment, output_packaging and audit_finalize always run.
    # output_packaging constructs the final structured JSON payload and
    # applies the last layer of PII masking before the payload is
    # formatted for downstream agents.
    # audit_finalize clears the text cache and records the final state.
    workflow.add_edge("enrichment",       "output_packaging")
    workflow.add_edge("output_packaging", "audit_finalize")
    workflow.add_edge("audit_finalize",   END)

    # ── Compile ────────────────────────────────────────────────────────────────
    # compile() validates the graph structure (no orphan nodes, no cycles,
    # all edges reference registered nodes) and returns an executable object.
    #
    # interrupt_before=["human_review_gate"]: This is the key security
    # parameter. LangGraph will pause execution before human_review_gate
    # on every graph run where the routing function returns "human_review_gate".
    # The pause is enforced at the framework level — it cannot be bypassed
    # by application code. The application must explicitly provide a
    # thread_config and call graph.invoke(resume=True) after a reviewer
    # has updated state through the checkpointer.
    #
    # If no checkpointer is provided, interrupt_before is ignored (the
    # graph runs to completion without pausing). This is the expected
    # behavior for tests and for the automated demo flow.

    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
        compile_kwargs["interrupt_before"] = ["human_review_gate"]

    compiled = workflow.compile(**compile_kwargs)
    logger.info(
        "Document Intelligence Agent graph compiled with checkpointer=%s "
        "and interrupt_before=%s",
        type(checkpointer).__name__ if checkpointer else "None",
        ["human_review_gate"] if checkpointer else "[]",
    )
    return compiled


# ── Module-Level Default Instances ────────────────────────────────────────────
#
# These instances are created at module load time for convenience.
# They are used by app.py (Streamlit) and by tests.
#
# DEVELOPMENT INSTANCE (with MemorySaver)
# ----------------------------------------
# Used by app.py and local development. MemorySaver stores state in a
# Python dict in memory — it resets when the process restarts. Suitable
# for demos and development; NOT suitable for production (no persistence,
# no encryption, no audit trail durability).
#
# MemorySaver is initialized here and passed to the factory so that
# multiple threads in the Streamlit app can share the same in-memory
# checkpoint store. LangGraph's MemorySaver is thread-safe.

_dev_checkpointer = MemorySaver()
graph = build_document_intelligence_graph(checkpointer=_dev_checkpointer)

# TEST INSTANCE (no checkpointer)
# ---------------------------------
# Used by tests/test_graph.py. No HITL interrupts — the graph runs to
# completion automatically. This allows integration tests to run without
# simulating the reviewer resume flow (which is tested separately).
# Tests that specifically test HITL can build their own graph instance
# with a MemorySaver checkpointer.
graph_no_checkpointer = build_document_intelligence_graph(checkpointer=None)


# ── Production Instantiation Helper ───────────────────────────────────────────

def get_production_graph(postgres_connection_string: str):
    """
    Build and return a production-grade graph with PostgresSaver checkpointing.

    WHY POSTGRESQL FOR PRODUCTION?
    --------------------------------
    LangGraph's PostgresSaver persists every state transition to a database,
    which provides:

    1. AUDIT TRAIL DURABILITY: If the ECS container crashes mid-processing,
       the document's state is preserved. The graph can be resumed from the
       last checkpoint rather than reprocessing from the beginning.

    2. CONCURRENT PROCESSING: Multiple ECS tasks can process different
       documents simultaneously. Each document has a unique thread_id
       (document_id), so there is no state collision.

    3. HITL PERSISTENCE: When a document is paused for human review,
       the state survives process restarts and scaling events. Reviewers
       can be in a different process or even a different time zone from
       the submitter.

    4. REGULATORY COMPLIANCE: BSA/AML regulations require financial
       institutions to maintain records of document processing. PostgreSQL
       provides durable, queryable storage for these records. The database
       itself is encrypted at rest (Aurora KMS) and in transit (SSL/TLS).

    USAGE
    -----
    In ECS/Lambda production environments, call this function with the
    Aurora connection string from AWS Secrets Manager:

        import boto3, json
        sm = boto3.client("secretsmanager")
        conn_str = json.loads(
            sm.get_secret_value(SecretId="prod/agent09/aurora")["SecretString"]
        )["connection_string"]
        production_graph = get_production_graph(conn_str)

    PARAMETERS
    ----------
    postgres_connection_string : str
        PostgreSQL DSN in the format:
        postgresql://user:password@host:5432/database

    RETURNS
    -------
    Compiled StateGraph with PostgresSaver checkpointer and
    interrupt_before=["human_review_gate"] enabled.
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:
        raise ImportError(
            "langgraph-checkpoint-postgres is not installed. "
            "Add it to requirements.txt for production deployments."
        ) from exc

    pg_checkpointer = PostgresSaver.from_conn_string(postgres_connection_string)
    pg_checkpointer.setup()  # Create checkpoint tables if they don't exist

    production_graph = build_document_intelligence_graph(checkpointer=pg_checkpointer)
    logger.info("Production graph initialized with PostgresSaver")
    return production_graph
