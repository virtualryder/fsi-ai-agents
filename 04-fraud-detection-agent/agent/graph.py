# agent/graph.py
# ============================================================
# LangGraph Fraud Detection Workflow DAG
#
# Two-path architecture:
#
#   REAL-TIME PATH (target < 200ms — runs before transaction approval):
#     transaction_intake → account_context_lookup → feature_extraction →
#     rule_engine_prescoring → composite_scoring → [conditional route] →
#     {BLOCK → block_transaction | STEP_UP → step_up_auth |
#      ALLOW → allow_transaction | ANALYST_REVIEW → flag_for_review}
#     → finalize_decision
#
#   ASYNC ENRICHMENT PATH (runs after real-time decision — deeper analysis):
#     device_intelligence → behavioral_analysis → llm_fraud_analysis →
#     [human_review_gate if ANALYST_REVIEW] → finalize_decision
#
# For demo purposes (no live payment stream), both paths run sequentially.
# In production, the real-time path returns a decision in <200ms, then
# the enrichment path runs asynchronously and can upgrade a decision
# (e.g., ALLOW → retroactively flag for review or ANALYST_REVIEW → BLOCK).
#
# LangGraph concepts used:
#   - StateGraph with FraudDetectionState TypedDict
#   - Conditional edges: _route_after_scoring branches to 4 outcomes
#   - interrupt_before human_review_gate: analyst reviews ANALYST_REVIEW cases
#   - MemorySaver: enables HITL interrupt + resume pattern
# ============================================================

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.persistence import get_checkpointer

from agent.state import FraudDetectionState, FraudDecision
from agent.nodes import (
    transaction_intake,
    account_context_lookup,
    feature_extraction,
    rule_engine_prescoring,
    device_intelligence,
    behavioral_analysis,
    llm_fraud_analysis,
    composite_scoring,
    block_transaction,
    step_up_authentication,
    flag_for_analyst_review,
    allow_transaction,
    human_review_gate,
    finalize_decision,
)

logger = logging.getLogger(__name__)


def _route_after_scoring(state: FraudDetectionState) -> str:
    """
    Conditional routing after composite_scoring.

    Routes to the appropriate action node based on fraud_decision.
    This is deterministic Python — not LLM output.

    Thresholds:
      composite_fraud_score ≥ 85  → BLOCK
      composite_fraud_score 65-84 → STEP_UP_AUTH
      composite_fraud_score 40-64 → ANALYST_REVIEW
      composite_fraud_score < 40  → ALLOW

    Hard overrides (not threshold-based):
      hard_block_triggered = True → always BLOCK regardless of score
    """
    # Hard block override — triggered by specific rule hits
    # (confirmed stolen card, OFAC merchant, known fraud IP)
    if state.get("hard_block_triggered"):
        logger.warning(
            f"Transaction {state.get('transaction_id')}: hard_block_triggered — "
            f"routing to block regardless of composite score {state.get('composite_fraud_score')}"
        )
        return "block_transaction"

    decision = state.get("fraud_decision")

    if decision == FraudDecision.BLOCK or decision == FraudDecision.FREEZE_ACCOUNT:
        return "block_transaction"
    elif decision == FraudDecision.STEP_UP_AUTH:
        return "step_up_authentication"
    elif decision == FraudDecision.ANALYST_REVIEW:
        return "flag_for_analyst_review"
    else:
        return "allow_transaction"


def build_fraud_detection_graph(use_memory: bool = True):
    """
    Build and compile the fraud detection LangGraph workflow.

    Args:
        use_memory: If True, use MemorySaver for HITL interrupt support.
                    In production, replace with PostgresSaver for durable state.

    Returns:
        Compiled LangGraph StateGraph.

    # ── PRODUCTION INTEGRATION POINT ────────────────────────────────────────
    # For real-time payment processing integration:
    #
    #   1. Kafka / Kinesis trigger:
    #      consumer = KafkaConsumer("payment-events")
    #      for msg in consumer:
    #          result = graph.invoke(json.loads(msg.value), config=thread_config)
    #
    #   2. REST API (FastAPI):
    #      @app.post("/fraud/evaluate")
    #      async def evaluate(txn: Transaction):
    #          result = await graph.ainvoke(txn.dict(), config=thread_config)
    #          return {"decision": result["fraud_decision"], "score": result["composite_fraud_score"]}
    #
    #   3. PostgresSaver for durable state (analyst review cases can span days):
    #      from langgraph.checkpoint.postgres import PostgresSaver
    #      checkpointer = PostgresSaver(conn)
    # ─────────────────────────────────────────────────────────────────────────
    """
    logger.info("Building fraud detection workflow graph...")

    workflow = StateGraph(FraudDetectionState)

    # ── REAL-TIME PATH NODES ─────────────────────────────────────────────────
    # These nodes form the <200ms real-time decision path.

    # NODE 1: Transaction Intake
    # Parse and validate the incoming transaction event. Extract all
    # available signals from the transaction payload.
    workflow.add_node("transaction_intake", transaction_intake)

    # NODE 2: Account Context Lookup
    # Retrieve account history, expected behavior profile, and customer
    # risk tier. Critical context for anomaly detection.
    workflow.add_node("account_context_lookup", account_context_lookup)

    # NODE 3: Feature Extraction
    # Build the structured feature vector used by both rule engine and ML.
    # Compute velocity signals and transaction-vs-baseline ratios.
    workflow.add_node("feature_extraction", feature_extraction)

    # NODE 4: Rule Engine Pre-scoring
    # Run deterministic rule checks: velocity limits, amount thresholds,
    # geography restrictions, MCC restrictions, known fraud indicators.
    # Fires before any ML/LLM — fast, interpretable, always explainable.
    workflow.add_node("rule_engine_prescoring", rule_engine_prescoring)

    # ── ASYNC ENRICHMENT PATH NODES ──────────────────────────────────────────
    # These nodes run after initial scoring for deeper contextual analysis.

    # NODE 5: Device Intelligence
    # Assess device risk: new device, impossible travel, VPN/proxy/Tor,
    # device fingerprint match, IP reputation.
    workflow.add_node("device_intelligence", device_intelligence)

    # NODE 6: Behavioral Analysis
    # Compare current session behavior to customer's historical patterns.
    # Detects account takeover signals: unusual login, typing rhythm mismatch,
    # unusual time-of-day, new payee pattern.
    workflow.add_node("behavioral_analysis", behavioral_analysis)

    # NODE 7: LLM Fraud Analysis
    # Claude Sonnet 4.6 contextual analysis across all gathered signals.
    # Generates: fraud probability (0-100), fraud type hypothesis,
    # plain-language reasoning for analyst review.
    workflow.add_node("llm_fraud_analysis", llm_fraud_analysis)

    # NODE 8: Composite Scoring
    # Combine rule engine (30%), LLM (50%), and historical patterns (20%)
    # into a weighted composite fraud score. Set fraud_decision threshold.
    workflow.add_node("composite_scoring", composite_scoring)

    # ── DECISION ACTION NODES ────────────────────────────────────────────────

    # NODE 9: Block Transaction
    # Decline the transaction. Create fraud case. Trigger customer notification
    # with Reg E disclosures. Set provisional credit flag if consumer-reported.
    workflow.add_node("block_transaction", block_transaction)

    # NODE 10: Step-Up Authentication
    # Request additional authentication from customer before allowing.
    # SMS OTP, push notification, or security question.
    workflow.add_node("step_up_authentication", step_up_authentication)

    # NODE 11: Flag for Analyst Review
    # Allow transaction but create flagged case for analyst queue.
    # SLA: analyst reviews within 4 hours for HIGH priority.
    workflow.add_node("flag_for_analyst_review", flag_for_analyst_review)

    # NODE 12: Allow Transaction
    # Approve transaction. Log for continuous monitoring.
    # Continue monitoring for post-authorization fraud signals.
    workflow.add_node("allow_transaction", allow_transaction)

    # NODE 13: Human Review Gate
    # HITL interrupt for ANALYST_REVIEW cases.
    # Fraud analyst reviews evidence and makes final determination.
    workflow.add_node("human_review_gate", human_review_gate)

    # NODE 14: Finalize Decision
    # Lock audit trail. Create case record. Send notifications.
    # Flag SAR consideration if money laundering indicators present.
    workflow.add_node("finalize_decision", finalize_decision)

    # ── GRAPH EDGES ──────────────────────────────────────────────────────────

    # Entry point
    workflow.set_entry_point("transaction_intake")

    # Real-time pipeline: intake → context → features → rules
    workflow.add_edge("transaction_intake", "account_context_lookup")
    workflow.add_edge("account_context_lookup", "feature_extraction")
    workflow.add_edge("feature_extraction", "rule_engine_prescoring")

    # Enrichment pipeline: rules → device → behavioral → LLM → composite
    workflow.add_edge("rule_engine_prescoring", "device_intelligence")
    workflow.add_edge("device_intelligence", "behavioral_analysis")
    workflow.add_edge("behavioral_analysis", "llm_fraud_analysis")
    workflow.add_edge("llm_fraud_analysis", "composite_scoring")

    # Conditional routing after scoring
    workflow.add_conditional_edges(
        source="composite_scoring",
        path=_route_after_scoring,
        path_map={
            "block_transaction": "block_transaction",
            "step_up_authentication": "step_up_authentication",
            "flag_for_analyst_review": "flag_for_analyst_review",
            "allow_transaction": "allow_transaction",
        },
    )

    # BLOCK and ALLOW paths go directly to finalize
    workflow.add_edge("block_transaction", "finalize_decision")
    workflow.add_edge("allow_transaction", "finalize_decision")

    # Step-up auth leads to finalize (result recorded in state)
    workflow.add_edge("step_up_authentication", "finalize_decision")

    # Analyst review flag → human review gate → finalize
    workflow.add_edge("flag_for_analyst_review", "human_review_gate")
    workflow.add_edge("human_review_gate", "finalize_decision")

    # End
    workflow.add_edge("finalize_decision", END)

    # ── COMPILE ───────────────────────────────────────────────────────────────
    if use_memory:
        checkpointer = get_checkpointer()  # PostgresSaver when DATABASE_URL is set; MemorySaver fallback (dev)
        compiled_graph = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["human_review_gate"],
        )
    else:
        compiled_graph = workflow.compile()

    logger.info("Fraud detection workflow graph built successfully.")
    return compiled_graph


def get_graph_visualization() -> str:
    """Mermaid diagram for README documentation."""
    return """
graph TD
    A[💳 Transaction Event] --> B[transaction_intake<br/>Parse & Validate]
    B --> C[account_context_lookup<br/>History · Risk Tier · Profile]
    C --> D[feature_extraction<br/>Velocity · Amount Ratio · Features]
    D --> E[rule_engine_prescoring<br/>Deterministic Rules<br/>Velocity · Geography · MCC]
    E --> F[device_intelligence<br/>Device Risk · Impossible Travel<br/>VPN/Proxy · IP Reputation]
    F --> G[behavioral_analysis<br/>Session Anomaly · Time-of-Day<br/>New Payee · Login Pattern]
    G --> H[llm_fraud_analysis<br/>Claude Sonnet 4.6 Contextual Analysis<br/>Fraud Type Hypothesis]
    H --> I[composite_scoring<br/>Rule 30% · LLM 50% · History 20%]
    I --> J{{routing_decision<br/>Fraud Score Threshold}}
    J -->|score ≥ 85| K[block_transaction<br/>Decline · Reg E Disclosure<br/>Case Created]
    J -->|score 65-84| L[step_up_authentication<br/>SMS OTP · Push Auth]
    J -->|score 40-64| M[flag_for_analyst_review<br/>Allow + Case Queue]
    J -->|score < 40| N[allow_transaction<br/>Approve + Monitor]
    M --> O[👤 human_review_gate<br/>Fraud Analyst Decision]
    K --> P[finalize_decision<br/>Audit Trail · SAR Flag<br/>Notifications]
    L --> P
    N --> P
    O --> P
    P --> Q[END ✓]

    style A fill:#2196F3,color:#fff
    style J fill:#ffa500,color:#fff
    style K fill:#dc2626,color:#fff
    style L fill:#ea580c,color:#fff
    style M fill:#d97706,color:#fff
    style N fill:#16a34a,color:#fff
    style O fill:#4CAF50,color:#fff
    style Q fill:#9C27B0,color:#fff
"""
