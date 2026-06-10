# agent/state.py
# ============================================================
# Document Intelligence Agent — State Definitions
#
# DocumentIntelligenceState: TypedDict (total=False) so all
# fields are optional at initialization. Each node populates
# its section of state as the workflow progresses.
#
# This agent is a horizontal force-multiplier: it converts
# unstructured documents (PDF, image, text) into structured
# JSON payloads that feed every other agent in the suite.
#
# Security notes:
#   - Raw document bytes are never stored in state; only
#     extracted text and derived fields pass through.
#   - PII fields (SSN, passport, account numbers) are
#     detected and flagged by Python — masked in audit trail.
#   - Document hash is computed for deduplication and
#     tamper detection (SHA-256).
#   - Low-confidence extractions → mandatory HITL.
#   - HITL is also required for any document containing PII
#     that will be passed to a downstream agent.
# ============================================================
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


# ── Enumerations ──────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    """
    All document types this agent can classify and extract.
    Each type has a field schema in data/fixtures/document_type_schemas.json.
    """
    # Lending
    LOAN_APPLICATION_RESIDENTIAL = "LOAN_APPLICATION_RESIDENTIAL"
    LOAN_APPLICATION_COMMERCIAL  = "LOAN_APPLICATION_COMMERCIAL"
    PROPERTY_APPRAISAL           = "PROPERTY_APPRAISAL"
    TAX_RETURN_1040              = "TAX_RETURN_1040"
    TAX_RETURN_1065              = "TAX_RETURN_1065"
    TAX_RETURN_1120              = "TAX_RETURN_1120"
    FINANCIAL_STATEMENT          = "FINANCIAL_STATEMENT"
    BANK_STATEMENT               = "BANK_STATEMENT"
    SBA_FORM_1919                = "SBA_FORM_1919"
    SBA_FORM_1920                = "SBA_FORM_1920"

    # Payments / Wire
    SWIFT_MT103                  = "SWIFT_MT103"   # Customer credit transfer
    SWIFT_MT202                  = "SWIFT_MT202"   # Financial institution transfer
    WIRE_INSTRUCTION             = "WIRE_INSTRUCTION"

    # Capital markets / Trading
    TRADE_CONFIRMATION           = "TRADE_CONFIRMATION"
    BROKERAGE_STATEMENT          = "BROKERAGE_STATEMENT"

    # Identity / KYC
    GOVERNMENT_ID                = "GOVERNMENT_ID"   # Passport, DL — PII-sensitive
    ENTITY_DOCUMENT              = "ENTITY_DOCUMENT"  # Articles, operating agreement
    TRUST_DOCUMENT               = "TRUST_DOCUMENT"
    BENEFICIAL_OWNERSHIP_CERT    = "BENEFICIAL_OWNERSHIP_CERT"

    # Compliance / Regulatory
    REGULATORY_EXAM_LETTER       = "REGULATORY_EXAM_LETTER"
    CONSENT_ORDER                = "CONSENT_ORDER"
    ADVERSE_MEDIA_ARTICLE        = "ADVERSE_MEDIA_ARTICLE"
    SAR_FORM                     = "SAR_FORM"        # Internal — not FinCEN submission
    CTR_FORM                     = "CTR_FORM"

    # General
    UNKNOWN                      = "UNKNOWN"


class ExtractionConfidence(str, Enum):
    """
    Confidence tier — determined by Python from field-level scores.
    HITL required for LOW and UNCERTAIN.
    """
    HIGH      = "HIGH"       # ≥ 0.85 composite — auto-route to downstream agent
    MEDIUM    = "MEDIUM"     # 0.65–0.84 — auto-route with flagged fields
    LOW       = "LOW"        # 0.40–0.64 — HITL required before routing
    UNCERTAIN = "UNCERTAIN"  # < 0.40 — HITL required; may be UNKNOWN type


class DownstreamAgent(str, Enum):
    """FSI agents this document can feed."""
    AGENT_01_FINANCIAL_CRIME    = "01-financial-crime-investigation"
    AGENT_03_KYC_CDD            = "03-kyc-cdd-perpetual"
    AGENT_04_FRAUD_DETECTION    = "04-fraud-detection"
    AGENT_06_REGULATORY_CHANGE  = "06-regulatory-change"
    AGENT_07_TRADING_SURVEILLANCE = "07-trading-surveillance"
    AGENT_08_CREDIT_UNDERWRITING  = "08-credit-underwriting"


class DocumentStatus(str, Enum):
    RECEIVED        = "RECEIVED"
    EXTRACTING      = "EXTRACTING"
    CLASSIFYING     = "CLASSIFYING"
    EXTRACTING_FIELDS = "EXTRACTING_FIELDS"
    VALIDATING      = "VALIDATING"
    PENDING_REVIEW  = "PENDING_REVIEW"
    ROUTED          = "ROUTED"
    REJECTED        = "REJECTED"


class FileFormat(str, Enum):
    PDF   = "PDF"
    IMAGE = "IMAGE"   # PNG, JPG, TIFF
    TEXT  = "TEXT"    # Plain text, SWIFT FIN
    DOCX  = "DOCX"
    XLSX  = "XLSX"
    CSV   = "CSV"
    XML   = "XML"     # FpML, ISO 20022
    UNKNOWN = "UNKNOWN"


# ── State TypedDict ────────────────────────────────────────────────────────────

class DocumentIntelligenceState(TypedDict, total=False):
    """
    Complete state for the document intelligence workflow.
    total=False: every field is Optional at initialization.
    Nodes populate only the fields they own.

    Security design:
    - No raw document bytes in state (memory/security).
    - document_hash (SHA-256) for tamper detection and deduplication.
    - PII flags set by Python; masked in audit trail.
    - Low-confidence or PII-containing docs require HITL before routing.
    """

    # ── Document Identification ────────────────────────────────────────────
    document_id: str                     # UUID — never contains document content
    document_hash: str                   # SHA-256 of raw bytes — tamper detection
    source_filename: str                 # Original filename (masked in audit trail)
    file_format: str                     # FileFormat enum value
    file_size_bytes: int
    page_count: int
    submitted_by: str                    # Submitting user ID or system
    submission_timestamp: str            # ISO-8601 UTC
    source_system: str                   # LOS | TMS | CORE_BANKING | MANUAL | EMAIL

    # ── Text Extraction ────────────────────────────────────────────────────
    # Raw extracted text is held in memory only during extraction node.
    # Only a truncated preview (first 500 chars) is stored in state.
    extracted_text_preview: str          # First 500 chars — for display only
    full_text_char_count: int            # Length of full extracted text
    extraction_method: str               # PDFPLUMBER | OCR_TESSERACT | DIRECT_TEXT | DOCX_PARSER
    extraction_warnings: List[str]       # OCR quality warnings, encoding issues
    ocr_confidence: Optional[float]      # OCR engine confidence (0.0–1.0) if applicable

    # ── Document Classification ────────────────────────────────────────────
    document_type: str                   # DocumentType enum value — LLM-classified
    document_type_confidence: float      # 0.0–1.0 — LLM classification confidence
    document_type_rationale: str         # LLM explanation of classification
    document_date: Optional[str]         # Date of document (extracted)
    document_issuer: Optional[str]       # Issuing institution or agency
    document_reference: Optional[str]    # Reference number / case number

    # ── Field Extraction ──────────────────────────────────────────────────
    # Structured fields extracted by LLM, validated by Python.
    # Schema per document_type defined in document_type_schemas.json.
    extracted_fields: Dict[str, Any]     # All extracted key-value pairs
    field_confidence_scores: Dict[str, float]  # Per-field confidence 0.0–1.0
    missing_required_fields: List[str]   # Required fields not found
    low_confidence_fields: List[str]     # Fields with confidence < 0.70
    extraction_exceptions: List[str]     # Fields present but unparseable

    # ── PII Detection ─────────────────────────────────────────────────────
    # Python regex-based — never LLM (LLM must not log PII it finds)
    pii_detected: bool
    pii_types_found: List[str]           # SSN | PASSPORT | ACCOUNT_NUMBER | EIN | etc.
    pii_field_names: List[str]           # Which extracted_fields contain PII
    pii_handling_required: str           # MASK | ENCRYPT | HUMAN_REVIEW | STANDARD

    # ── Validation ────────────────────────────────────────────────────────
    validation_passed: bool
    validation_errors: List[str]         # Field-level validation failures
    validation_warnings: List[str]       # Non-blocking quality issues
    business_rule_violations: List[str]  # Cross-field consistency failures

    # ── Confidence Scoring ────────────────────────────────────────────────
    composite_confidence: float          # 0.0–1.0 Python-weighted aggregate
    confidence_tier: str                 # ExtractionConfidence enum value
    confidence_breakdown: Dict[str, Any] # Factor-by-factor detail

    # ── Routing ────────────────────────────────────────────────────────────
    target_agents: List[str]             # DownstreamAgent enum values
    routing_rationale: str
    human_review_required: bool
    human_review_reason: str
    priority: str                        # CRITICAL | HIGH | NORMAL | LOW

    # ── Human Review Gate ──────────────────────────────────────────────────
    reviewer_id: str
    reviewer_decision: str               # APPROVE_AND_ROUTE | CORRECT_AND_ROUTE | REJECT | REQUEST_RESUBMIT
    reviewer_corrections: Dict[str, Any] # Corrections to extracted_fields
    reviewer_notes: str
    review_timestamp: str

    # ── Enrichment ────────────────────────────────────────────────────────
    enrichment_notes: str                # LLM contextual notes for downstream agent
    anomaly_flags: List[str]             # Unusual patterns flagged for downstream
    regulatory_relevance: List[str]      # Regulatory frameworks this document implicates

    # ── Output Payload ────────────────────────────────────────────────────
    # Final structured JSON ready for downstream agent consumption.
    output_payload: Dict[str, Any]       # Structured, validated, PII-masked payload
    output_schema_version: str           # Schema version for downstream compatibility
    routing_instructions: Dict[str, Any] # Agent-specific routing metadata

    # ── Document Register ─────────────────────────────────────────────────
    document_status: str                 # DocumentStatus enum value
    processing_time_seconds: float

    # ── Audit Trail ───────────────────────────────────────────────────────
    audit_trail: List[Dict[str, Any]]    # Append-only — never modified
    completed_steps: List[str]
    errors: List[str]
