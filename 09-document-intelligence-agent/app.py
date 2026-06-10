# app.py
# ============================================================
# Document Intelligence Agent — Streamlit Dashboard
# Port: 8509
#
# PURPOSE
# -------
# This is the primary user interface for the Document Intelligence
# Agent. It allows bank staff to submit documents for processing,
# monitor extraction results, review documents flagged for human
# review, and inspect the audit trail.
#
# This agent is the ENTRY POINT for document-heavy workflows:
# any team that works with PDFs, images, SWIFT messages, or
# scanned forms should use this agent to convert those documents
# into structured JSON before feeding them to specialist agents.
#
# WHO USES THIS DASHBOARD
# -----------------------
# - Loan Officers: Submit 1003s, tax returns, bank statements for
#   automated data extraction before credit underwriting review.
# - Operations / Wire Desk: Submit SWIFT messages for automated
#   parsing and AML pre-screening before execution.
# - KYC / CDD Analysts: Submit identity and entity documents for
#   structured extraction prior to onboarding review.
# - BSA Officers: Review flagged SAR/CTR documents in the HITL
#   review queue before routing to financial crime investigation.
# - Compliance Officers: Submit regulatory exam letters and consent
#   orders for structured extraction and response tracking.
#
# TABS (6)
# --------
# Tab 1 — Submit Document: Upload or select a demo scenario
# Tab 2 — Extraction Results: View classified document and fields
# Tab 3 — Human Review Queue: Review and act on HITL documents
# Tab 4 — Routing & Downstream: See where documents are routed
# Tab 5 — Audit Trail: Complete processing history
# Tab 6 — About: Architecture, positioning, and getting started
#
# SECURITY NOTES FOR STREAMLIT DEPLOYMENT
# -----------------------------------------
# - API keys are loaded from environment variables (.env), never
#   entered via the UI.
# - Uploaded documents are processed in memory; no files are written
#   to disk unless explicitly configured.
# - PII masking is enforced by the agent graph before any UI display.
#   The audit trail shown in Tab 5 uses masked values.
# - In production, this app runs behind ALB authentication (Okta SAML)
#   so all users are authenticated before reaching this interface.
# ============================================================

import json
import os
import time
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

# ── Environment Setup ─────────────────────────────────────────────────────────
# Load environment variables from .env file (development only).
# In production (ECS), environment variables are injected by ECS task
# definition from AWS Secrets Manager — the .env file is never deployed.
load_dotenv()

# Check for OpenAI API key — required for LLM nodes (classification, extraction).
# If not present, the app runs in DEMO MODE using pre-computed scenario outputs.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEMO_MODE = not bool(OPENAI_API_KEY)

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Document Intelligence Agent | FSI AI Suite",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load Fixtures ─────────────────────────────────────────────────────────────
# Load the sample scenarios and routing matrix from the data fixtures directory.
# These are used in DEMO MODE and for the routing visualization in Tab 4.
FIXTURES_DIR = Path(__file__).parent / "data" / "fixtures"


@st.cache_data
def load_sample_documents() -> List[Dict[str, Any]]:
    """Load demo scenarios. Cached so the file is read once per session."""
    try:
        with open(FIXTURES_DIR / "sample_documents.json") as f:
            data = json.load(f)
        return data.get("scenarios", [])
    except FileNotFoundError:
        return []


@st.cache_data
def load_routing_matrix() -> Dict[str, Any]:
    """Load routing matrix. Cached so the file is read once per session."""
    try:
        with open(FIXTURES_DIR / "routing_matrix.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


@st.cache_data
def load_document_schemas() -> Dict[str, Any]:
    """Load document type schemas. Cached so the file is read once per session."""
    try:
        with open(FIXTURES_DIR / "document_type_schemas.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


SAMPLE_DOCUMENTS = load_sample_documents()
ROUTING_MATRIX = load_routing_matrix()
DOCUMENT_SCHEMAS = load_document_schemas()


# ── Session State Initialization ──────────────────────────────────────────────
# Streamlit re-runs the entire script on every interaction.
# st.session_state preserves data across reruns within a single browser session.
def _init_session():
    """Initialize session state variables on first load."""
    if "processing_results" not in st.session_state:
        st.session_state.processing_results = {}   # doc_id → result dict
    if "review_queue" not in st.session_state:
        st.session_state.review_queue = []          # list of doc_ids pending HITL
    if "selected_doc_id" not in st.session_state:
        st.session_state.selected_doc_id = None
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = 0


_init_session()


# ── Helper Functions ──────────────────────────────────────────────────────────

def _confidence_color(tier: str) -> str:
    """Return a CSS color for the confidence tier badge."""
    return {
        "HIGH": "#28a745",
        "MEDIUM": "#fd7e14",
        "LOW": "#dc3545",
        "UNCERTAIN": "#6c757d",
    }.get(tier, "#6c757d")


def _priority_color(priority: str) -> str:
    """Return a CSS color for the priority badge."""
    return {
        "CRITICAL": "#dc3545",
        "HIGH": "#fd7e14",
        "NORMAL": "#0d6efd",
        "LOW": "#6c757d",
    }.get(priority, "#6c757d")


def _agent_display_name(agent_id: str) -> str:
    """Convert agent ID to a human-readable display name."""
    names = {
        "01-financial-crime-investigation": "01 — Financial Crime Investigation",
        "03-kyc-cdd-perpetual": "03 — KYC/CDD Perpetual",
        "04-fraud-detection": "04 — Fraud Detection",
        "06-regulatory-change": "06 — Regulatory Change Management",
        "07-trading-surveillance": "07 — Trading Surveillance",
        "08-credit-underwriting": "08 — Credit Underwriting",
    }
    return names.get(agent_id, agent_id)


def _simulate_processing(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simulate document processing for DEMO MODE.

    In production, this function would call:
        from agent.graph import graph
        result = graph.invoke(initial_state, thread_config)

    In DEMO MODE (no API key), we return pre-computed expected outputs
    from the sample_documents.json fixture, with a simulated delay
    to show the Streamlit progress indicators.
    """
    doc_id = str(uuid.uuid4())
    doc_hash = hashlib.sha256(
        scenario.get("raw_document_text", "").encode()
    ).hexdigest()

    metadata = scenario.get("document_metadata", {})
    expected = scenario.get("expected_extraction", {})

    time.sleep(0.5)  # Simulate text extraction
    time.sleep(0.5)  # Simulate PII detection
    time.sleep(0.5)  # Simulate LLM classification
    time.sleep(0.5)  # Simulate LLM field extraction

    return {
        "document_id": doc_id,
        "document_hash": doc_hash,
        "scenario_id": scenario.get("scenario_id"),
        "scenario_name": scenario.get("scenario_name"),
        "source_filename": metadata.get("source_filename"),
        "file_format": metadata.get("file_format"),
        "source_system": metadata.get("source_system"),
        "submitted_by": metadata.get("submitted_by"),
        "document_type": expected.get("document_type"),
        "document_type_confidence": expected.get("document_type_confidence"),
        "confidence_tier": expected.get("confidence_tier"),
        "extracted_fields": expected.get("extracted_fields", {}),
        "pii_detected": expected.get("pii_detected"),
        "pii_types_found": expected.get("pii_types_found", []),
        "target_agents": expected.get("target_agents", []),
        "anomaly_flags": expected.get("anomaly_flags", []),
        "regulatory_relevance": expected.get("regulatory_relevance", []),
        "human_review_required": expected.get("human_review_required", False),
        "routing_rationale": expected.get("routing_rationale"),
        "priority": expected.get("priority"),
        "document_status": "PENDING_REVIEW" if expected.get("human_review_required") else "ROUTED",
        "processing_timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://img.icons8.com/color/96/document--v1.png", width=60)
    st.title("Document Intelligence")
    st.caption("FSI AI Suite — Agent 09")

    st.divider()

    if DEMO_MODE:
        st.warning(
            "**DEMO MODE**\n\n"
            "No OpenAI API key detected. Running with pre-computed demo scenarios.\n\n"
            "Set `OPENAI_API_KEY` in `.env` for live processing.",
            icon="⚠️",
        )
    else:
        st.success("**LIVE MODE**\n\nConnected to OpenAI API.", icon="✅")

    st.divider()
    st.markdown("**Quick Stats**")
    total_processed = len(st.session_state.processing_results)
    pending_review = len(st.session_state.review_queue)
    st.metric("Documents Processed", total_processed)
    st.metric("Pending Human Review", pending_review)

    st.divider()
    st.markdown(
        "**Suite Agents**\n"
        "- 01 Financial Crime\n"
        "- 03 KYC/CDD\n"
        "- 04 Fraud Detection\n"
        "- 06 Regulatory Change\n"
        "- 07 Trading Surveillance\n"
        "- **09 Document Intelligence** ← You are here\n"
        "- 08 Credit Underwriting"
    )


# ── Main Header ───────────────────────────────────────────────────────────────

st.title("Document Intelligence Agent")
st.markdown(
    "**Converts unstructured financial documents into validated, PII-masked, structured JSON "
    "for every agent in the FSI AI Suite.** "
    "Submit a PDF, image, or SWIFT message — this agent classifies it, extracts structured fields, "
    "screens for PII, scores extraction confidence, and routes the output to the appropriate downstream agent."
)

if DEMO_MODE:
    st.info(
        "Running in **Demo Mode** — select a pre-built scenario below to see how the agent processes "
        "each document type. Results are pre-computed from realistic sample documents.",
        icon="ℹ️",
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📤 Submit Document",
    "📋 Extraction Results",
    "👤 Human Review Queue",
    "🔀 Routing & Downstream",
    "📜 Audit Trail",
    "ℹ️ About This Agent",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Submit Document
# ════════════════════════════════════════════════════════════════════════════

with tab1:
    st.header("Submit a Document for Processing")
    st.markdown(
        "Upload a document file or select one of the pre-built demo scenarios. "
        "The agent will extract text, detect PII, classify the document type, "
        "extract structured fields, score confidence, and route the result to "
        "the appropriate downstream agent."
    )

    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.subheader("Option A — Upload a Document")
        uploaded_file = st.file_uploader(
            "Upload PDF, image (PNG/JPG/TIFF), or text file",
            type=["pdf", "png", "jpg", "jpeg", "tiff", "txt"],
            help="Maximum file size: 10MB. Documents are processed in memory and not stored to disk.",
        )

        if uploaded_file:
            source_system = st.selectbox(
                "Source System",
                ["MANUAL", "LOS", "TMS", "CORE_BANKING", "EMAIL"],
                help="The originating system for compliance audit trail purposes.",
            )
            submitted_by = st.text_input(
                "Submitted By (user ID or email)",
                value="demo.user@bank.example.com",
            )

            if st.button("Process Document", type="primary", disabled=DEMO_MODE):
                if DEMO_MODE:
                    st.warning("Live processing requires an OpenAI API key.")
                else:
                    with st.spinner("Processing document..."):
                        # Production path: invoke the LangGraph agent
                        from agent.graph import graph
                        from agent.state import FileFormat

                        file_bytes = uploaded_file.read()
                        doc_hash = hashlib.sha256(file_bytes).hexdigest()
                        doc_id = str(uuid.uuid4())
                        ext = Path(uploaded_file.name).suffix.upper().lstrip(".")
                        fmt_map = {
                            "PDF": "PDF", "PNG": "IMAGE", "JPG": "IMAGE",
                            "JPEG": "IMAGE", "TIFF": "IMAGE", "TXT": "TEXT",
                        }
                        file_format = fmt_map.get(ext, "UNKNOWN")

                        initial_state = {
                            "document_id": doc_id,
                            "document_hash": doc_hash,
                            "source_filename": uploaded_file.name,
                            "file_format": file_format,
                            "file_size_bytes": len(file_bytes),
                            "submitted_by": submitted_by,
                            "submission_timestamp": datetime.now(timezone.utc).isoformat(),
                            "source_system": source_system,
                        }
                        thread_config = {"configurable": {"thread_id": doc_id}}
                        result = graph.invoke(initial_state, thread_config)
                        st.session_state.processing_results[doc_id] = result
                        st.session_state.selected_doc_id = doc_id
                        if result.get("human_review_required"):
                            st.session_state.review_queue.append(doc_id)
                        st.success(f"Document processed! ID: `{doc_id}`")

    with col_right:
        st.subheader("Option B — Select a Demo Scenario")
        st.markdown(
            "These pre-built scenarios demonstrate the four primary document "
            "processing paths in the FSI AI Suite."
        )

        for scenario in SAMPLE_DOCUMENTS:
            with st.expander(f"**{scenario['scenario_name']}**", expanded=False):
                st.markdown(scenario["scenario_description"])
                meta = scenario.get("document_metadata", {})
                st.caption(
                    f"Format: {meta.get('file_format')} | "
                    f"System: {meta.get('source_system')} | "
                    f"File: {meta.get('source_filename')}"
                )

                if st.button(
                    f"Run Demo: {scenario['scenario_id']}",
                    key=f"run_{scenario['scenario_id']}",
                    type="primary",
                ):
                    with st.spinner(f"Processing {scenario['scenario_id']}..."):
                        progress = st.progress(0, text="Extracting text...")
                        time.sleep(0.4)
                        progress.progress(20, text="Detecting PII...")
                        time.sleep(0.3)
                        progress.progress(40, text="Classifying document...")
                        time.sleep(0.4)
                        progress.progress(60, text="Extracting fields...")
                        time.sleep(0.4)
                        progress.progress(80, text="Scoring confidence...")
                        time.sleep(0.3)
                        progress.progress(100, text="Complete!")

                        result = _simulate_processing(scenario)
                        doc_id = result["document_id"]
                        st.session_state.processing_results[doc_id] = result
                        st.session_state.selected_doc_id = doc_id
                        if result.get("human_review_required"):
                            st.session_state.review_queue.append(doc_id)

                    st.success(
                        f"Processed! Document ID: `{doc_id[:8]}...`\n\n"
                        "View results in **Extraction Results** tab."
                    )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Extraction Results
# ════════════════════════════════════════════════════════════════════════════

with tab2:
    st.header("Extraction Results")

    if not st.session_state.processing_results:
        st.info("No documents processed yet. Submit a document in the **Submit Document** tab.")
    else:
        # Document selector
        doc_options = {
            v.get("scenario_name", v["document_id"][:12]): k
            for k, v in st.session_state.processing_results.items()
        }
        selected_name = st.selectbox(
            "Select Document",
            options=list(doc_options.keys()),
            index=list(doc_options.keys()).index(
                next(
                    (n for n, k in doc_options.items()
                     if k == st.session_state.selected_doc_id),
                    list(doc_options.keys())[0]
                )
            ) if st.session_state.selected_doc_id else 0,
        )
        doc_id = doc_options[selected_name]
        result = st.session_state.processing_results[doc_id]

        # Summary row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            tier = result.get("confidence_tier", "—")
            st.markdown(
                f"**Confidence Tier**\n\n"
                f"<span style='background:{_confidence_color(tier)};color:white;"
                f"padding:4px 12px;border-radius:12px;font-weight:700;'>{tier}</span>",
                unsafe_allow_html=True,
            )
        with col2:
            priority = result.get("priority", "—")
            st.markdown(
                f"**Priority**\n\n"
                f"<span style='background:{_priority_color(priority)};color:white;"
                f"padding:4px 12px;border-radius:12px;font-weight:700;'>{priority}</span>",
                unsafe_allow_html=True,
            )
        with col3:
            st.metric(
                "Confidence Score",
                f"{result.get('document_type_confidence', 0.0):.2f}",
            )
        with col4:
            hitl = result.get("human_review_required", False)
            st.markdown(
                f"**Human Review**\n\n"
                f"<span style='background:{'#dc3545' if hitl else '#28a745'};"
                f"color:white;padding:4px 12px;border-radius:12px;font-weight:700;'>"
                f"{'REQUIRED' if hitl else 'NOT REQUIRED'}</span>",
                unsafe_allow_html=True,
            )

        st.divider()

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("Document Classification")
            st.markdown(f"**Type:** `{result.get('document_type', '—')}`")
            st.markdown(f"**Source:** {result.get('source_filename', '—')}")
            st.markdown(f"**Format:** {result.get('file_format', '—')}")
            st.markdown(f"**Status:** `{result.get('document_status', '—')}`")

            st.subheader("PII Detection")
            if result.get("pii_detected"):
                pii_types = result.get("pii_types_found", [])
                st.warning(
                    f"PII Detected: {', '.join(pii_types)}\n\n"
                    "All PII has been masked before LLM processing and in the output payload.",
                    icon="🔒",
                )
            else:
                st.success("No PII detected in this document.", icon="✅")

            st.subheader("Target Agents")
            agents = result.get("target_agents", [])
            if agents:
                for agent in agents:
                    st.markdown(f"→ {_agent_display_name(agent)}")
            else:
                st.markdown("*None — pending human review*")

        with col_right:
            st.subheader("Extracted Fields")
            fields = result.get("extracted_fields", {})
            if fields:
                for field_name, value in fields.items():
                    st.markdown(f"**{field_name}:** `{value}`")
            else:
                st.info("No fields extracted yet.")

        st.divider()
        st.subheader("Anomaly Flags")
        flags = result.get("anomaly_flags", [])
        if flags:
            for flag in flags:
                st.warning(flag, icon="⚠️")
        else:
            st.success("No anomaly flags raised.", icon="✅")

        st.subheader("Regulatory Relevance")
        regs = result.get("regulatory_relevance", [])
        if regs:
            st.markdown(" | ".join([f"`{r}`" for r in regs]))
        else:
            st.markdown("*None identified*")

        st.subheader("Routing Rationale")
        st.info(result.get("routing_rationale", "No routing rationale available."))


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Human Review Queue
# ════════════════════════════════════════════════════════════════════════════

with tab3:
    st.header("Human Review Queue")
    st.markdown(
        "Documents requiring human review appear here. These include: SAR/CTR forms, "
        "Government IDs, Consent Orders, documents with low confidence extraction, "
        "documents with validation errors, or any document where the agent cannot "
        "determine the type with sufficient confidence."
    )

    pending = [
        doc_id for doc_id in st.session_state.review_queue
        if st.session_state.processing_results.get(doc_id, {}).get("document_status") == "PENDING_REVIEW"
    ]

    if not pending:
        st.success("No documents currently pending human review.", icon="✅")
    else:
        st.metric("Documents Pending Review", len(pending))

        for doc_id in pending:
            result = st.session_state.processing_results.get(doc_id, {})
            with st.expander(
                f"**{result.get('scenario_name', doc_id[:12])}** | "
                f"Type: {result.get('document_type', '?')} | "
                f"Priority: {result.get('priority', '?')}",
                expanded=True,
            ):
                st.markdown(f"**Document ID:** `{doc_id}`")
                st.markdown(f"**Review Required:** {result.get('human_review_reason', 'See above')}")

                fields = result.get("extracted_fields", {})
                if fields:
                    st.markdown("**Extracted Fields (for review):**")
                    for k, v in fields.items():
                        st.markdown(f"- **{k}:** `{v}`")

                st.divider()
                st.markdown("**Reviewer Decision**")

                decision = st.radio(
                    "Select Action",
                    [
                        "APPROVE_AND_ROUTE — Extraction is accurate. Route to downstream agents.",
                        "CORRECT_AND_ROUTE — Apply corrections below, then route.",
                        "REJECT — Document is unprocessable. Close.",
                        "REQUEST_RESUBMIT — Incomplete. Notify submitter.",
                    ],
                    key=f"decision_{doc_id}",
                )

                corrections_text = st.text_area(
                    "Field Corrections (JSON format)",
                    value="{}",
                    key=f"corrections_{doc_id}",
                    help="If CORRECT_AND_ROUTE, enter corrected fields as JSON: {\"field_name\": \"corrected_value\"}",
                )

                reviewer_notes = st.text_area(
                    "Reviewer Notes",
                    key=f"notes_{doc_id}",
                    placeholder="Add any notes for the downstream agent or for the audit trail...",
                )

                if st.button("Submit Review Decision", key=f"submit_{doc_id}", type="primary"):
                    decision_code = decision.split(" — ")[0]
                    try:
                        corrections = json.loads(corrections_text)
                    except json.JSONDecodeError:
                        corrections = {}

                    # Update state with reviewer decision
                    st.session_state.processing_results[doc_id].update({
                        "reviewer_id": "demo.reviewer@bank.example.com",
                        "reviewer_decision": decision_code,
                        "reviewer_corrections": corrections,
                        "reviewer_notes": reviewer_notes,
                        "review_timestamp": datetime.now(timezone.utc).isoformat(),
                        "document_status": "ROUTED" if "ROUTE" in decision_code else "REJECTED",
                    })

                    if "ROUTE" in decision_code:
                        st.success(
                            f"Decision submitted: **{decision_code}**\n\n"
                            "Document will be enriched and routed to: "
                            + ", ".join(_agent_display_name(a) for a in result.get("target_agents", []))
                        )
                    else:
                        st.info(f"Decision submitted: **{decision_code}**. Document closed.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Routing & Downstream
# ════════════════════════════════════════════════════════════════════════════

with tab4:
    st.header("Routing Matrix & Downstream Agents")
    st.markdown(
        "This tab shows the complete routing rules for all 25 document types supported "
        "by this agent. The routing is determined by a Python constant (not by the LLM) — "
        "ensuring deterministic, auditable, and tamper-proof routing decisions."
    )

    categories = ROUTING_MATRIX.get("routing_matrix", [])

    for category in categories:
        st.subheader(category["document_category"])
        docs = category.get("documents", [])

        for doc in docs:
            always_hitl = doc.get("hitl_always", False)
            hitl_badge = "🔴 ALWAYS HITL" if always_hitl else "🟢 Auto-Route"

            with st.expander(
                f"{hitl_badge} | **{doc['display_name']}** → "
                + " + ".join(doc.get("target_agents", ["—"])),
                expanded=False,
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Document Type:** `{doc['document_type']}`")
                    st.markdown(f"**Default Priority:** `{doc['default_priority']}`")
                    st.markdown(f"**SLA:** {doc['sla_hours']} hour(s)")
                    if always_hitl and "hitl_reason" in doc:
                        st.warning(f"**HITL Reason:** {doc['hitl_reason']}", icon="🔒")

                with col2:
                    st.markdown("**Target Agents:**")
                    for agent in doc.get("target_agents", []):
                        st.markdown(f"→ `{agent}`")
                    st.markdown("**Regulatory Tags:**")
                    tags = doc.get("regulatory_tags", [])
                    if tags:
                        st.markdown(", ".join([f"`{t}`" for t in tags]))

    st.divider()
    st.subheader("Confidence Tiers")
    tiers = ROUTING_MATRIX.get("confidence_tiers", [])
    for tier in tiers:
        color = _confidence_color(tier["tier"])
        st.markdown(
            f"<span style='background:{color};color:white;padding:4px 12px;"
            f"border-radius:12px;font-weight:700;'>{tier['tier']}</span> "
            f"**{tier['threshold']}** — {tier['action']}",
            unsafe_allow_html=True,
        )
        st.markdown("")


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Audit Trail
# ════════════════════════════════════════════════════════════════════════════

with tab5:
    st.header("Audit Trail")
    st.markdown(
        "The audit trail is append-only — entries are never modified or deleted. "
        "In production, the full audit trail is persisted to encrypted Aurora PostgreSQL "
        "with 7-year retention to satisfy BSA record-keeping requirements. "
        "PII values are masked in the audit trail before storage."
    )

    if not st.session_state.processing_results:
        st.info("No documents processed yet.")
    else:
        for doc_id, result in st.session_state.processing_results.items():
            with st.expander(
                f"**{result.get('scenario_name', doc_id[:12])}** | "
                f"Status: {result.get('document_status', '—')} | "
                f"ID: `{doc_id[:8]}...`",
                expanded=False,
            ):
                st.markdown(f"**Document ID:** `{doc_id}`")
                st.markdown(f"**Hash (SHA-256):** `{result.get('document_hash', '—')[:32]}...`")
                st.markdown(f"**Processed:** {result.get('processing_timestamp', '—')}")
                st.markdown(f"**Status:** `{result.get('document_status', '—')}`")
                st.markdown(f"**Submitted By:** `{result.get('submitted_by', '—')}`")
                st.markdown(f"**Source System:** `{result.get('source_system', '—')}`")

                if result.get("reviewer_id"):
                    st.divider()
                    st.markdown("**Human Review Record**")
                    st.markdown(f"- Reviewer: `{result.get('reviewer_id')}`")
                    st.markdown(f"- Decision: `{result.get('reviewer_decision')}`")
                    st.markdown(f"- Review Timestamp: `{result.get('review_timestamp')}`")
                    if result.get("reviewer_notes"):
                        st.markdown(f"- Notes: {result.get('reviewer_notes')}")

                st.divider()
                st.markdown("**Routing Record**")
                agents = result.get("target_agents", [])
                if agents:
                    for agent in agents:
                        st.markdown(f"→ `{agent}`")
                else:
                    st.markdown("*Not routed*")

                st.markdown(f"**Routing Rationale:** {result.get('routing_rationale', '—')}")


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — About This Agent
# ════════════════════════════════════════════════════════════════════════════

with tab6:
    st.header("About: Document Intelligence Agent")

    st.markdown("""
## What This Agent Does

The Document Intelligence Agent is the **horizontal foundation layer** of the FSI AI Suite.
Every other agent in the suite assumes it receives structured JSON as input. But banks live in
a world of PDFs, scanned images, SWIFT FIN messages, and Word documents. This agent bridges
that gap — it converts any unstructured financial document into the structured JSON payloads
that every other agent expects.

### The Core Value Proposition

Without this agent, each specialist agent would need its own document parsing logic.
Loan officers would need to manually re-key data from 1003s into the credit underwriting system.
Wire desk staff would need to parse SWIFT messages by hand before AML screening. KYC analysts
would manually transcribe passport data into onboarding systems.

With this agent, **every team that submits a document gets back structured data in seconds** —
classified, extracted, validated, PII-masked, and pre-routed to the right downstream agent.
The time savings compound across every team and every document type.

---

## How It Relates to Other Agents

This agent is the **entry point for document-heavy workflows** for every agent in the suite:

| Downstream Agent | Documents This Agent Feeds It |
|---|---|
| **01 — Financial Crime Investigation** | SWIFT MT103/MT202, Wire Instructions, Bank Statements, SAR/CTR, Adverse Media |
| **03 — KYC/CDD Perpetual** | Government IDs, Entity Documents, Trust Documents, Beneficial Ownership Certs, Brokerage Statements |
| **04 — Fraud Detection** | Wire Instructions, SWIFT MT103, Bank Statements |
| **06 — Regulatory Change Management** | Regulatory Exam Letters, Consent Orders |
| **07 — Trading Surveillance** | Trade Confirmations, Brokerage Statements |
| **08 — Credit Underwriting** | Loan Applications (1003/Commercial), Tax Returns (1040/1065/1120), Financial Statements, Bank Statements, Appraisals, SBA Forms |

**In practice:** A loan officer drops a 1003 PDF into this agent. Within seconds, the agent has
classified it as a residential loan application, extracted 12 structured fields, masked the SSN,
detected a geographic fair lending flag, and packaged a structured JSON payload ready for the
Credit Underwriting agent (Agent 08). The loan officer never re-keys data.

---

## Security Architecture

### Why These Security Decisions Were Made

This section explains each security control in terms that compliance and security officers
can evaluate against their own policies and regulatory requirements.

#### 1. PII Detection Runs Before LLM

**What:** Python regex-based PII detection (SSN, passport, account numbers, EIN, IBAN, credit
cards, routing numbers) runs and masks the extracted text *before* any LLM API call is made.
The LLM only ever sees masked text.

**Why:** The LLM is an external API call (OpenAI). Sending unmasked SSNs or passport numbers
to an external service would violate Gramm-Leach-Bliley Act (GLBA) data minimization requirements
and expose the institution to data breach liability. The extraction prompt *also* instructs the
LLM to return only the last 4 digits of SSNs — providing defense-in-depth. Even if the regex
layer missed a PII instance, the LLM would self-mask.

#### 2. Raw Document Bytes Are Never Stored in State

**What:** The LangGraph state (the data passed between nodes) never contains raw document bytes.
After the text extraction node reads and parses the document, the raw bytes are discarded.
Only extracted text (and then the PII-masked version of extracted text) passes through the graph.
The text is stored in a module-level Python dict (keyed by document SHA-256 hash) that is cleared
by the `audit_finalize` node at the end of processing.

**Why:** State can be persisted to the LangGraph checkpoint database (Aurora) and to logs.
Storing raw document bytes in state would mean that multi-megabyte PDFs or images would be
written to the database and logs on every state transition. This creates both a security risk
(sensitive documents in database logs) and a performance problem. The SHA-256 hash serves
as the immutable document identifier without storing the document content.

#### 3. Routing Is a Python Constant, Not an LLM Decision

**What:** The DOCUMENT_ROUTING dict in nodes.py is defined as a Python constant at module load
time. It maps each document type to its target downstream agents. No LLM call can alter this
mapping at runtime. The routing decision node reads this constant and sets target_agents — the
LLM is not involved in routing decisions.

**Why:** Prompt injection is a real attack vector. A malicious document could contain text
designed to manipulate an LLM into routing a SAR form to a non-BSA agent, or routing a wire
instruction to a different team. By making routing a Python constant, we eliminate this attack
surface entirely. Regulators can audit the routing logic by reading a single Python dict.

#### 4. HITL Is Enforced at the Graph Level

**What:** Documents that require human review are flagged by the `routing_decision_node` (Python
logic, not LLM). The LangGraph graph is compiled with `interrupt_before=["human_review_gate"]`,
which causes the graph to pause at the framework level before the HITL node runs. No downstream
routing occurs until a human reviewer submits a decision.

**Why:** A purely application-level check ("if human_review_required: show_review_UI()") can be
bypassed by code bugs or by calling the graph directly without the UI. The `interrupt_before`
mechanism is enforced by the LangGraph framework — even a direct `graph.invoke()` call will pause
at the interrupt point when the checkpoint shows human review is required. This is the only way
to provide a provable guarantee to regulators that SAR/CTR documents always receive human review.

#### 5. Document Hash for Tamper Detection and Deduplication

**What:** A SHA-256 hash of the raw document bytes is computed in the `document_intake` node
before any processing begins. This hash is stored in the audit trail and is used to detect
duplicate submissions (the same document submitted twice) and to detect document tampering
(if the submitted document's hash does not match the hash computed from the bytes as received).

**Why:** Banks receive documents through many channels (email, fax, LOS, manual upload).
Duplicate detection prevents double-processing of the same loan application or SWIFT message.
Tamper detection is relevant for high-value wire instructions where Business Email Compromise
(BEC) attacks may involve subtly altered PDFs. The SHA-256 hash provides cryptographic proof
that the document processed matches the document received.

---

## Getting Started

### For Compliance and Security Officers

Before deploying, review:
1. `docs/aws-deployment-guide.md` — the AWS security architecture with rationale
2. `docs/regulatory-compliance.md` — the regulatory framework mapping
3. `agent/nodes.py` — the `ALWAYS_HITL_DOCUMENT_TYPES` frozenset and `DOCUMENT_ROUTING` dict
4. `agent/prompts.py` — the LLM prompt constraints (what the LLM is and is not permitted to do)

### For Engineering Teams

```bash
# 1. Clone the repository
git clone https://github.com/virtualryder/fsi-ai-agents.git
cd fsi-ai-agents/09-document-intelligence-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 4. Run the Streamlit dashboard
streamlit run app.py --server.port 8509

# 5. Run the test suite
pytest tests/ -v
```

### For Business Leaders

The Document Intelligence Agent eliminates the #1 operational bottleneck in bank document
processing: manual data entry and re-keying. Every team that submits documents gains:

- **Speed:** Document classification and field extraction in under 30 seconds
- **Accuracy:** Structured extraction with per-field confidence scores — low-confidence fields
  are flagged automatically rather than silently passed through
- **Compliance:** PII is masked before any external API call; all HITL decisions are logged
  in an immutable audit trail; SAR/CTR documents are always escalated to a human reviewer
- **Integration:** Extracted data is pre-formatted for every downstream specialist agent —
  no custom integration code required per document type

**Time-to-value:** Teams can begin processing documents in demo mode immediately with no API key.
Full production deployment with live LLM extraction requires only an OpenAI API key and the
AWS infrastructure described in `docs/aws-deployment-guide.md`.
""")
