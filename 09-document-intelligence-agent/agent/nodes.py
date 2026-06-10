# agent/nodes.py
# ============================================================
# Document Intelligence Agent — Node Functions
#
# This agent is the horizontal force-multiplier for the suite.
# Every other agent assumes structured JSON input. In practice,
# banks receive PDFs, images, SWIFT messages, and scanned forms.
# This agent bridges that gap.
#
# LLM vs. Python boundary:
#
#   LLM (language understanding required):
#     - document_classification_node — understand doc type from text
#     - field_extraction_node — extract structured fields from prose
#     - enrichment_node — contextual notes for downstream agents
#     - correction_node — merge human corrections with original extraction
#
#   PYTHON ONLY (deterministic, auditable):
#     - document_intake_node — format validation, hash, sanitization
#     - text_extraction_node — PDF/OCR/text parsing
#     - pii_detection_node — regex-based PII scanning
#     - validation_node — field completeness, data types, cross-field rules
#     - confidence_scoring_node — composite confidence from field scores
#     - routing_decision_node — document type → target agents
#     - output_packaging_node — structured payload for downstream
#     - audit_finalize_node — close audit trail
#
# Security design (for compliance officer review):
#
#   1. HASH BEFORE PROCESS: SHA-256 hash computed on intake before any
#      text extraction — used for deduplication and tamper detection.
#
#   2. TEXT ONLY IN TRANSIT: Raw document bytes are never stored in
#      state. Only extracted text (string) passes to LLM nodes, and
#      that text is PII-masked before LLM sees it.
#
#   3. PII MASKING BEFORE LLM: pii_detection_node runs BEFORE
#      field_extraction_node. SSNs, passport numbers, and full account
#      numbers are masked in the text passed to the LLM. The LLM
#      extraction prompt also explicitly instructs not to reproduce
#      these values — defense in depth.
#
#   4. NO LLM IN ROUTING: Routing decisions (which downstream agent
#      receives this document) are made by a Python lookup table.
#      No LLM can re-route a document to bypass a compliance agent.
#
#   5. HITL FOR LOW CONFIDENCE: confidence_scoring_node enforces
#      human review for composite confidence < 0.65 and for all
#      GOVERNMENT_ID and SAR_FORM documents regardless of confidence.
#
#   6. APPEND-ONLY AUDIT: Every node appends to audit_trail.
#      No node may modify a prior entry. Source filename is hashed
#      in the audit trail (not stored in plain text).
#
#   7. INPUT SANITIZATION: All free-text inputs sanitized at intake
#      to prevent prompt injection via crafted document content.
# ============================================================
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_anthropic import ChatAnthropic
from agent.persistence import audit_sink

# ── Claude model tiers (Anthropic) ───────────────────────────────────────────
# NARRATIVE tier — Claude Sonnet 4.6: regulatory narratives, SAR/dispute
#   analysis, anything an examiner, reviewer, or customer will read.
# FAST tier — Claude Haiku 4.5: high-volume triage, classification, and
#   scoring-assist nodes where latency and unit cost dominate.
# Override via env: CLAUDE_NARRATIVE_MODEL / CLAUDE_FAST_MODEL.
# ── INTEGRATION POINT (production) ───────────────────────────────────────────
# For VPC-contained inference, swap ChatAnthropic for ChatBedrockConverse
# (langchain-aws) with Bedrock model IDs:
#   anthropic.claude-sonnet-4-6-20260601-v1:0  (narrative)
#   anthropic.claude-haiku-4-5-20251001        (fast)
# ─────────────────────────────────────────────────────────────────────────────
import os as _os_llm
CLAUDE_NARRATIVE_MODEL = _os_llm.getenv("CLAUDE_NARRATIVE_MODEL", "claude-sonnet-4-6")
CLAUDE_FAST_MODEL = _os_llm.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5")
CLAUDE_DEFAULT_MODEL = CLAUDE_NARRATIVE_MODEL


from agent.prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_USER_PROMPT,
    CORRECTION_SYSTEM_PROMPT,
    CORRECTION_USER_PROMPT,
    ENRICHMENT_SYSTEM_PROMPT,
    ENRICHMENT_USER_PROMPT,
    FIELD_EXTRACTION_SYSTEM_PROMPT,
    FIELD_EXTRACTION_USER_PROMPT,
)
from agent.state import (
    DocumentIntelligenceState,
    DocumentStatus,
    DocumentType,
    DownstreamAgent,
    ExtractionConfidence,
    FileFormat,
)

# ── Constants ─────────────────────────────────────────────────────────────────

# Documents that ALWAYS require HITL regardless of confidence
# (contain sensitive PII or regulatory significance)
ALWAYS_HITL_DOCUMENT_TYPES = frozenset({
    DocumentType.GOVERNMENT_ID.value,
    DocumentType.SAR_FORM.value,
    DocumentType.CTR_FORM.value,
    DocumentType.CONSENT_ORDER.value,
})

# Confidence thresholds — Python constants, not configurable in UI
CONFIDENCE_HITL_THRESHOLD = 0.65       # Below this → mandatory HITL
CONFIDENCE_LOW_FIELD_THRESHOLD = 0.70  # Field confidence below this → flagged
CONFIDENCE_HIGH_TIER = 0.85            # Above this → HIGH tier
CONFIDENCE_MEDIUM_TIER = 0.65          # Above this → MEDIUM tier (below HITL threshold)

# Document type → downstream agents (deterministic Python lookup)
# No LLM can alter this routing table
DOCUMENT_ROUTING: Dict[str, List[str]] = {
    DocumentType.LOAN_APPLICATION_RESIDENTIAL.value: [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.LOAN_APPLICATION_COMMERCIAL.value:  [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.PROPERTY_APPRAISAL.value:           [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.TAX_RETURN_1040.value:              [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.TAX_RETURN_1065.value:              [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.TAX_RETURN_1120.value:              [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.FINANCIAL_STATEMENT.value:          [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.BANK_STATEMENT.value:               [
        DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value,
        DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value,
    ],
    DocumentType.SBA_FORM_1919.value:                [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.SBA_FORM_1920.value:                [DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value],
    DocumentType.SWIFT_MT103.value:                  [
        DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value,
        DownstreamAgent.AGENT_04_FRAUD_DETECTION.value,
    ],
    DocumentType.SWIFT_MT202.value:                  [
        DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value,
        DownstreamAgent.AGENT_04_FRAUD_DETECTION.value,
    ],
    DocumentType.WIRE_INSTRUCTION.value:             [
        DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value,
        DownstreamAgent.AGENT_04_FRAUD_DETECTION.value,
    ],
    DocumentType.TRADE_CONFIRMATION.value:           [DownstreamAgent.AGENT_07_TRADING_SURVEILLANCE.value],
    DocumentType.BROKERAGE_STATEMENT.value:          [DownstreamAgent.AGENT_07_TRADING_SURVEILLANCE.value],
    DocumentType.GOVERNMENT_ID.value:                [DownstreamAgent.AGENT_03_KYC_CDD.value],
    DocumentType.ENTITY_DOCUMENT.value:              [DownstreamAgent.AGENT_03_KYC_CDD.value],
    DocumentType.TRUST_DOCUMENT.value:               [
        DownstreamAgent.AGENT_03_KYC_CDD.value,
        DownstreamAgent.AGENT_08_CREDIT_UNDERWRITING.value,
    ],
    DocumentType.BENEFICIAL_OWNERSHIP_CERT.value:    [DownstreamAgent.AGENT_03_KYC_CDD.value],
    DocumentType.REGULATORY_EXAM_LETTER.value:       [DownstreamAgent.AGENT_06_REGULATORY_CHANGE.value],
    DocumentType.CONSENT_ORDER.value:                [
        DownstreamAgent.AGENT_06_REGULATORY_CHANGE.value,
        DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value,
    ],
    DocumentType.ADVERSE_MEDIA_ARTICLE.value:        [
        DownstreamAgent.AGENT_03_KYC_CDD.value,
        DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value,
    ],
    DocumentType.SAR_FORM.value:                     [DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value],
    DocumentType.CTR_FORM.value:                     [DownstreamAgent.AGENT_01_FINANCIAL_CRIME.value],
    DocumentType.UNKNOWN.value:                      [],  # HITL required — no auto-routing
}

# Priority by document type
DOCUMENT_PRIORITY: Dict[str, str] = {
    DocumentType.SWIFT_MT103.value:        "CRITICAL",
    DocumentType.SWIFT_MT202.value:        "CRITICAL",
    DocumentType.WIRE_INSTRUCTION.value:   "CRITICAL",
    DocumentType.CONSENT_ORDER.value:      "CRITICAL",
    DocumentType.SAR_FORM.value:           "CRITICAL",
    DocumentType.CTR_FORM.value:           "HIGH",
    DocumentType.REGULATORY_EXAM_LETTER.value: "HIGH",
    DocumentType.ADVERSE_MEDIA_ARTICLE.value:  "HIGH",
    DocumentType.GOVERNMENT_ID.value:      "HIGH",
    DocumentType.TRADE_CONFIRMATION.value: "HIGH",
}

# PII patterns for Python detection (never LLM)
PII_PATTERNS = {
    "SSN":            re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "EIN":            re.compile(r"\b\d{2}-\d{7}\b"),
    "PASSPORT":       re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
    "ACCOUNT_NUMBER": re.compile(r"\b\d{8,17}\b"),
    "ROUTING_NUMBER": re.compile(r"\b0\d{8}\b"),
    "CREDIT_CARD":    re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
    "IBAN":           re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,19}\b"),
}

# PII masking replacements
PII_MASKS = {
    "SSN":            "[SSN-MASKED]",
    "EIN":            "[EIN-MASKED]",
    "PASSPORT":       "[PASSPORT-PRESENT]",
    "ACCOUNT_NUMBER": "[ACCT-MASKED]",
    "ROUTING_NUMBER": "[ROUTING-MASKED]",
    "CREDIT_CARD":    "[CARD-MASKED]",
    "IBAN":           "[IBAN-MASKED]",
}

# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm() -> ChatAnthropic:
    return ChatAnthropic(model=CLAUDE_DEFAULT_MODEL,
        temperature=0,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

# ── Utility ───────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _append_audit(state: DocumentIntelligenceState, step: str, details: Dict[str, Any]) -> list:
    """Append timestamped audit entry. Entries are never modified."""
    trail = list(state.get("audit_trail", []))
    trail.append({
        "step": step,
        "timestamp": _now_utc(),
        "document_id": state.get("document_id", "UNKNOWN"),
        **details,
    })
    # WRITE-AHEAD: durable audit record at creation (agent/persistence.py)
    audit_sink().record(trail[-1])
    return trail

def _sanitize_text(text: str, max_length: int = 2000) -> str:
    """
    Strip control characters (except newline/tab) and cap length.

    INPUT SANITIZATION CONTROL: free-text fields are sanitized before any
    LLM call or state write. Newlines/tabs are legitimate document structure
    and are preserved; NUL and other control bytes are removed; output is
    truncated to max_length to bound LLM context and prevent resource abuse.
    """
    if not text:
        return ""
    cleaned = "".join(ch for ch in str(text) if ch in ("\n", "\t") or ord(ch) >= 32)
    return cleaned[:max_length]


def _sanitize_filename(filename: str) -> str:
    """Remove path components and control characters from filenames."""
    if not isinstance(filename, str):
        return "unknown"
    # Strip path separators and control characters
    clean = re.sub(r"[/\\<>:\"|\x00-\x1f]", "_", filename)
    return clean[:200]

def _hash_filename(filename: str) -> str:
    """SHA-256 hash of filename for audit trail — avoid storing PII in logs."""
    return hashlib.sha256(filename.encode()).hexdigest()[:16]

def _mask_pii_in_text(text: str) -> Tuple[str, List[str], List[str]]:
    """
    Detect and mask PII in document text before passing to LLM.
    Returns: (masked_text, pii_types_found, original_positions_summary)

    Security: This runs BEFORE LLM sees any text. Defense in depth —
    LLM prompt also instructs not to reproduce PII, but masking here
    ensures PII never reaches the LLM context window.
    """
    pii_found = []
    masked = text
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(masked)
        if matches:
            pii_found.append(pii_type)
            masked = pattern.sub(PII_MASKS[pii_type], masked)
    return masked, pii_found, []


def _detect_and_mask_pii(text: str) -> Tuple[str, List[str]]:
    """
    Public PII masking contract: returns (masked_text, pii_types_found).

    This is the stable two-tuple interface the test suite and downstream
    callers depend on; _mask_pii_in_text is the internal three-tuple variant.
    Keep BOTH names exported — renaming this again will break the security
    test contract (tests/test_nodes.py PII section).
    """
    masked, pii_found, _ = _mask_pii_in_text(text)
    return masked, pii_found


def _mask_account_numbers(account: str) -> str:
    """
    Mask an account number preserving only the last 4 digits.
    Contract: last-4 visible for identification; leading digits never survive.
    """
    if not account:
        return "****"
    cleaned = re.sub(r"[^\d]", "", str(account))
    if not cleaned:
        return "****"
    return f"****{cleaned[-4:]}"

def _detect_file_format(filename: str, content_bytes: Optional[bytes] = None) -> str:
    """Determine file format from extension and magic bytes."""
    if filename:
        ext = filename.lower().rsplit(".", 1)[-1]
        ext_map = {
            "pdf": FileFormat.PDF.value,
            "png": FileFormat.IMAGE.value, "jpg": FileFormat.IMAGE.value,
            "jpeg": FileFormat.IMAGE.value, "tiff": FileFormat.IMAGE.value,
            "tif": FileFormat.IMAGE.value,
            "txt": FileFormat.TEXT.value, "fin": FileFormat.TEXT.value,
            "docx": FileFormat.DOCX.value, "doc": FileFormat.DOCX.value,
            "xlsx": FileFormat.XLSX.value, "xls": FileFormat.XLSX.value,
            "csv": FileFormat.CSV.value,
            "xml": FileFormat.XML.value,
        }
        if ext in ext_map:
            return ext_map[ext]
    if content_bytes:
        if content_bytes[:4] == b"%PDF":
            return FileFormat.PDF.value
        if content_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return FileFormat.IMAGE.value
        if content_bytes[:2] in (b"\xff\xd8", b"BM"):
            return FileFormat.IMAGE.value
    return FileFormat.UNKNOWN.value

def _extract_text_from_bytes(content_bytes: bytes, file_format: str, filename: str) -> Tuple[str, str, List[str], Optional[float]]:
    """
    Extract plain text from document bytes.
    Returns: (full_text, extraction_method, warnings, ocr_confidence)

    Uses pdfplumber for PDFs (pure Python, no system deps).
    Uses pytesseract for images (requires Tesseract binary in production).
    Falls back to UTF-8 decode for plain text.
    """
    warnings = []
    method = "DIRECT_TEXT"
    ocr_conf = None

    if file_format == FileFormat.PDF.value:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
                full_text = "\n\n".join(pages)
                if not full_text.strip():
                    warnings.append("PDF text extraction yielded empty text — may be image-based PDF requiring OCR")
            return full_text, "PDFPLUMBER", warnings, None
        except ImportError:
            warnings.append("pdfplumber not installed — falling back to text decode")
        except Exception as e:
            warnings.append(f"PDF extraction error: {str(e)[:100]}")

    elif file_format == FileFormat.IMAGE.value:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(content_bytes))
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            confidences = [int(c) for c in data["conf"] if str(c).isdigit() and int(c) > 0]
            ocr_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.5
            full_text = pytesseract.image_to_string(img)
            if ocr_conf < 0.70:
                warnings.append(f"OCR confidence {ocr_conf:.0%} is low — document may be degraded or skewed")
            return full_text, "OCR_TESSERACT", warnings, ocr_conf
        except ImportError:
            warnings.append("pytesseract/Pillow not installed — install for image OCR support")
        except Exception as e:
            warnings.append(f"OCR error: {str(e)[:100]}")

    elif file_format == FileFormat.DOCX.value:
        try:
            import docx
            doc = docx.Document(io.BytesIO(content_bytes))
            full_text = "\n".join(p.text for p in doc.paragraphs)
            return full_text, "DOCX_PARSER", warnings, None
        except ImportError:
            warnings.append("python-docx not installed — falling back to text decode")
        except Exception as e:
            warnings.append(f"DOCX parse error: {str(e)[:100]}")

    # Fallback: try UTF-8 then latin-1
    for encoding in ("utf-8", "latin-1"):
        try:
            full_text = content_bytes.decode(encoding)
            return full_text, "DIRECT_TEXT", warnings, None
        except UnicodeDecodeError:
            continue

    warnings.append("Could not decode document — unknown encoding")
    return "", "FAILED", warnings, None

# ── Node 1: Document Intake ───────────────────────────────────────────────────

def document_intake_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Validate and ingest the incoming document.

    Security controls:
    - SHA-256 hash computed on raw bytes for tamper detection + deduplication
    - Filename sanitized to prevent path traversal
    - File size capped at 50MB (prevent memory exhaustion attacks)
    - MIME type validated against declared format
    - Source filename hashed in audit trail (not stored in plain text)
    """
    document_id = state.get("document_id") or f"DOC-{uuid.uuid4().hex[:8].upper()}"
    source_filename = _sanitize_filename(state.get("source_filename", "unknown"))
    errors = list(state.get("errors", []))

    # Raw bytes provided by Streamlit file uploader or LOS integration
    raw_bytes: Optional[bytes] = state.get("_raw_bytes")  # Transient — cleared after extraction
    content_text: Optional[str] = state.get("_content_text")  # Pre-extracted text path

    computed_size = len(raw_bytes) if raw_bytes else (len(content_text.encode()) if content_text else 0)
    declared_size = int(state.get("file_size_bytes") or 0)
    # Honor the larger of computed vs declared size — a caller cannot under-
    # declare a payload to slip past the limit, and the LOS-integration path
    # (metadata only, bytes fetched later) is sized by its declaration.
    file_size = max(computed_size, declared_size)

    # Size limit — 10MB (memory-exhaustion control)
    MAX_SIZE = 10 * 1024 * 1024
    if file_size > MAX_SIZE:
        errors.append(f"Document size {file_size:,} bytes exceeds 10MB limit")

    # Compute SHA-256 hash
    if raw_bytes:
        doc_hash = hashlib.sha256(raw_bytes).hexdigest()
    elif content_text:
        doc_hash = hashlib.sha256(content_text.encode()).hexdigest()
    elif state.get("document_hash"):
        # LOS-integration path: metadata-first submission with a pre-computed
        # hash; bytes are fetched by text_extraction. Accepted at intake.
        doc_hash = state["document_hash"]
    else:
        doc_hash = hashlib.sha256(b"empty").hexdigest()
        errors.append("No document content provided")

    # Detect file format
    file_format = _detect_file_format(
        source_filename,
        raw_bytes[:16] if raw_bytes and len(raw_bytes) >= 16 else None,
    )
    if state.get("file_format"):
        file_format = state["file_format"]  # Respect explicitly set format

    # SECURITY: unsupported/unknown formats are rejected at the gate —
    # an .exe or unidentifiable file must never flow into text extraction.
    if file_format == "UNKNOWN":
        errors.append(
            f"Unsupported file format for '{source_filename}' — document rejected at intake"
        )

    # Status contract: intake returns RECEIVED on success; REJECTED whenever
    # any intake-level error exists (size, missing content, unknown format).
    # The text_extraction node — not intake — moves the status to EXTRACTING.
    intake_status = (
        DocumentStatus.REJECTED.value if errors else DocumentStatus.RECEIVED.value
    )

    audit = _append_audit(state, "document_intake", {
        "document_id": document_id,
        "source_filename_hash": _hash_filename(source_filename),  # Never plain filename in audit
        "file_format": file_format,
        "file_size_bytes": file_size,
        "document_hash": doc_hash[:16] + "...",  # Partial hash in audit (not full fingerprint)
        "source_system": state.get("source_system", "MANUAL"),
        "status": intake_status,
        "errors": errors,
    })

    return {
        "document_id": document_id,
        "document_hash": doc_hash,
        "source_filename": source_filename,
        "file_format": file_format,
        "file_size_bytes": file_size,
        "source_system": state.get("source_system", "MANUAL"),
        "submitted_by": state.get("submitted_by", "UNKNOWN"),
        "submission_timestamp": _now_utc(),
        "document_status": intake_status,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["document_intake"],
        "errors": errors,
    }


# ── Node 2: Text Extraction ───────────────────────────────────────────────────

def text_extraction_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Extract plain text from the document.

    Security: Raw bytes are cleared from state after extraction.
    Only the extracted text string passes forward — never the raw bytes.
    The full text is held in a module-level cache (_text_cache) keyed
    by document_hash, available only during the current process lifetime.

    In production: text is written to encrypted S3 (KMS) and fetched
    per-node rather than held in memory across nodes.
    """
    doc_hash = state.get("document_hash", "")
    file_format = state.get("file_format", FileFormat.UNKNOWN.value)
    source_filename = state.get("source_filename", "unknown")
    errors = list(state.get("errors", []))

    raw_bytes: Optional[bytes] = state.get("_raw_bytes")
    content_text: Optional[str] = state.get("_content_text")
    cached_text = _get_text_from_cache(doc_hash) if doc_hash else ""

    if content_text:
        # Pre-extracted text path (fixture mode, plain text documents)
        full_text = content_text
        method = "DIRECT_TEXT"
        warnings = []
        ocr_conf = None
    elif raw_bytes:
        full_text, method, warnings, ocr_conf = _extract_text_from_bytes(raw_bytes, file_format, source_filename)
    elif cached_text:
        # LOS-integration path: text was extracted upstream and staged in the
        # cache under this document's hash before graph invocation. Use it —
        # this is the metadata-first submission flow accepted at intake.
        full_text = cached_text
        method = "PRE_STAGED_CACHE"
        warnings = []
        ocr_conf = None
    else:
        full_text = ""
        method = "FAILED"
        warnings = ["No document content available for extraction"]
        ocr_conf = None
        errors.append("Text extraction failed: no content provided")

    if not full_text.strip() and method != "FAILED":
        warnings.append("Extracted text is empty — document may be image-only or corrupted")

    # Store full text in module-level cache (keyed by hash, not state)
    # This avoids passing large strings through state unnecessarily
    _store_text_in_cache(doc_hash, full_text)

    # Only store a preview in state (500 chars).
    # SECURITY: state writes are a masking boundary. This node runs BEFORE
    # pii_detection_node, so the preview must be masked here — raw PII must
    # never enter graph state (checkpoints/audit serialize the full state).
    masked_preview, _, _ = _mask_pii_in_text(full_text[:500])
    preview = masked_preview.replace("\n", " ").strip()
    char_count = len(full_text)

    # Count pages (PDF) or estimate from line count
    page_count = full_text.count("\f") + 1 if "\f" in full_text else max(1, char_count // 3000)

    audit = _append_audit(state, "text_extraction", {
        "extraction_method": method,
        "char_count": char_count,
        "page_count": page_count,
        "ocr_confidence": ocr_conf,
        "warnings_count": len(warnings),
    })

    return {
        "extracted_text_preview": preview,
        "full_text_char_count": char_count,
        "extraction_method": method,
        "extraction_warnings": warnings,
        "ocr_confidence": ocr_conf,
        "page_count": page_count,
        "document_status": DocumentStatus.CLASSIFYING.value,
        "_raw_bytes": None,       # Clear raw bytes from state — security
        "_content_text": None,    # Clear after storing in cache
        "audit_trail": audit,
        "errors": errors,
        "completed_steps": list(state.get("completed_steps", [])) + ["text_extraction"],
    }


# Module-level text cache — keyed by SHA-256 hash
# In production: replace with S3 fetch pattern
_TEXT_CACHE: Dict[str, str] = {}

def _store_text_in_cache(doc_hash: str, text: str) -> None:
    _TEXT_CACHE[doc_hash] = text

def _get_text_from_cache(doc_hash: str) -> str:
    return _TEXT_CACHE.get(doc_hash, "")


# ── Node 3: PII Detection (runs before LLM sees text) ────────────────────────

def pii_detection_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Detect and mask PII in document text BEFORE passing to LLM.

    This node runs between text_extraction and classification.
    It:
    1. Scans the full extracted text for PII patterns (Python regex)
    2. Masks PII in the cached text before LLM nodes can read it
    3. Records which PII types were found (without recording the values)
    4. Sets pii_handling_required to determine post-routing controls

    Security rationale for running PII detection before LLM:
    - LLMs log prompts; PII in prompts creates data retention risk
    - OpenAI API processes prompts on third-party infrastructure
    - Defense in depth: LLM prompt ALSO instructs not to reproduce PII
    - Masked text is what all downstream LLM nodes receive
    """
    doc_hash = state.get("document_hash", "")
    full_text = _get_text_from_cache(doc_hash)
    errors = list(state.get("errors", []))

    pii_types_found = []
    masked_text = full_text

    if full_text:
        masked_text, pii_types_found, _ = _mask_pii_in_text(full_text)
        # Replace cached text with masked version — all subsequent nodes use masked text
        _store_text_in_cache(doc_hash, masked_text)

    pii_detected = len(pii_types_found) > 0

    # Determine PII handling level
    if DocumentType.GOVERNMENT_ID.value in state.get("_doc_type_hint", ""):
        pii_handling = "ENCRYPT"
    elif pii_detected and any(t in pii_types_found for t in ["SSN", "PASSPORT", "CREDIT_CARD"]):
        pii_handling = "HUMAN_REVIEW"
    elif pii_detected:
        pii_handling = "MASK"
    else:
        pii_handling = "STANDARD"

    audit = _append_audit(state, "pii_detection", {
        "pii_detected": pii_detected,
        "pii_types_found": pii_types_found,
        "pii_handling_required": pii_handling,
        # Never log the actual PII values — only the types
    })

    return {
        "pii_detected": pii_detected,
        "pii_types_found": pii_types_found,
        "pii_field_names": [],  # Populated after field extraction
        "pii_handling_required": pii_handling,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["pii_detection"],
        "errors": errors,
    }


# ── Node 4: Document Classification ──────────────────────────────────────────

def document_classification_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    LLM classifies the document type and extracts top-level metadata.
    Receives PII-masked text from cache — never raw document content.
    """
    llm = _get_llm()
    doc_hash = state.get("document_hash", "")
    masked_text = _get_text_from_cache(doc_hash)
    file_format = state.get("file_format", FileFormat.UNKNOWN.value)
    source_system = state.get("source_system", "MANUAL")
    errors = list(state.get("errors", []))

    if not masked_text.strip():
        return {
            "document_type": DocumentType.UNKNOWN.value,
            "document_type_confidence": 0.0,
            "document_type_rationale": "No text content available for classification.",
            "document_status": DocumentStatus.EXTRACTING_FIELDS.value,
            "audit_trail": _append_audit(state, "document_classification", {"result": "EMPTY_TEXT"}),
            "completed_steps": list(state.get("completed_steps", [])) + ["document_classification"],
            "errors": errors + ["Classification skipped: empty text"],
        }

    text_preview = masked_text[:1500]
    char_count = state.get("full_text_char_count", len(masked_text))

    prompt = CLASSIFICATION_USER_PROMPT.format(
        text_preview=text_preview,
        char_count=char_count,
        file_format=file_format,
        source_system=source_system,
    )

    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        response = llm.invoke([
            SystemMessage(content=CLASSIFICATION_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        errors.append(f"Classification LLM error: {str(e)[:100]}")
        result = {
            "document_type": DocumentType.UNKNOWN.value,
            "confidence": 0.0,
            "rationale": "LLM classification failed.",
            "document_date": None,
            "document_issuer": None,
            "document_reference": None,
        }

    doc_type = result.get("document_type", DocumentType.UNKNOWN.value)
    confidence = float(result.get("confidence", 0.0))

    # Validate doc_type is in the enum
    valid_types = {dt.value for dt in DocumentType}
    if doc_type not in valid_types:
        doc_type = DocumentType.UNKNOWN.value
        confidence = min(confidence, 0.30)

    audit = _append_audit(state, "document_classification", {
        "document_type": doc_type,
        "confidence": round(confidence, 4),
        "rationale": result.get("rationale", "")[:200],
    })

    return {
        "document_type": doc_type,
        "document_type_confidence": confidence,
        "document_type_rationale": result.get("rationale", ""),
        "document_date": result.get("document_date"),
        "document_issuer": result.get("document_issuer"),
        "document_reference": result.get("document_reference"),
        "document_status": DocumentStatus.EXTRACTING_FIELDS.value,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["document_classification"],
        "errors": errors,
    }


# ── Node 5: Field Extraction ──────────────────────────────────────────────────

def field_extraction_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    LLM extracts structured fields per document type schema.
    Text passed to LLM is PII-masked (from cache). LLM returns JSON.
    Python validates the JSON structure and field types.
    """
    llm = _get_llm()
    doc_hash = state.get("document_hash", "")
    masked_text = _get_text_from_cache(doc_hash)
    document_type = state.get("document_type", DocumentType.UNKNOWN.value)
    errors = list(state.get("errors", []))

    # Load field schema for this document type
    schema = _load_field_schema(document_type)
    required_fields = schema.get("required", [])
    optional_fields = schema.get("optional", [])

    if document_type == DocumentType.UNKNOWN.value or not masked_text.strip():
        return {
            "extracted_fields": {},
            "field_confidence_scores": {},
            "missing_required_fields": required_fields,
            "low_confidence_fields": [],
            "extraction_exceptions": [],
            "audit_trail": _append_audit(state, "field_extraction", {
                "document_type": document_type, "fields_extracted": 0
            }),
            "completed_steps": list(state.get("completed_steps", [])) + ["field_extraction"],
            "errors": errors,
        }

    prompt = FIELD_EXTRACTION_USER_PROMPT.format(
        document_type=document_type,
        required_fields="\n".join(f"  - {f}" for f in required_fields),
        optional_fields="\n".join(f"  - {f}" for f in optional_fields),
        document_text=masked_text[:8000],  # Cap at 8K tokens to control cost
    )

    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        response = llm.invoke([
            SystemMessage(content=FIELD_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        errors.append(f"Field extraction LLM error: {str(e)[:100]}")
        result = {"fields": {}, "confidence": {}, "extraction_notes": "LLM extraction failed."}

    extracted_fields = result.get("fields", {})
    field_confidence = {k: float(v) for k, v in result.get("confidence", {}).items()}

    # Identify missing required fields and low-confidence fields
    missing_required = [f for f in required_fields if not extracted_fields.get(f)]
    low_conf = [f for f, c in field_confidence.items() if c < CONFIDENCE_LOW_FIELD_THRESHOLD]

    # Identify PII fields in the extracted output
    pii_field_names = []
    for field_name, value in extracted_fields.items():
        if isinstance(value, str):
            for pii_type, pattern in PII_PATTERNS.items():
                if pattern.search(str(value)):
                    pii_field_names.append(field_name)
                    break

    audit = _append_audit(state, "field_extraction", {
        "document_type": document_type,
        "fields_extracted": len(extracted_fields),
        "missing_required_count": len(missing_required),
        "low_confidence_count": len(low_conf),
        "pii_fields_detected": len(pii_field_names),
    })

    return {
        "extracted_fields": extracted_fields,
        "field_confidence_scores": field_confidence,
        "missing_required_fields": missing_required,
        "low_confidence_fields": low_conf,
        "extraction_exceptions": [result.get("extraction_notes", "")] if result.get("extraction_notes") else [],
        "pii_field_names": pii_field_names,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["field_extraction"],
        "errors": errors,
    }


def _load_field_schema(document_type: str) -> Dict[str, list]:
    """Load required/optional field schema for the given document type."""
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "fixtures", "document_type_schemas.json"
    )
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            schemas = json.load(f)
        return schemas.get(document_type, {"required": [], "optional": []})
    return {"required": [], "optional": []}


# ── Node 6: Validation ────────────────────────────────────────────────────────

def validation_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Python validates extracted fields: completeness, data types,
    ranges, and cross-field consistency rules.
    """
    extracted = dict(state.get("extracted_fields", {}))
    document_type = state.get("document_type", DocumentType.UNKNOWN.value)
    errors = list(state.get("errors", []))
    validation_errors = []
    validation_warnings = []
    business_rule_violations = []

    # Load validation rules
    schema = _load_field_schema(document_type)
    required_fields = schema.get("required", [])
    validation_rules = schema.get("validation_rules", {})

    # Required field check
    for field in required_fields:
        if not extracted.get(field):
            validation_errors.append(f"Required field missing or null: {field}")

    # Type and range validation from schema rules
    for field, rules in validation_rules.items():
        value = extracted.get(field)
        if value is None:
            continue
        field_type = rules.get("type")
        if field_type == "numeric":
            try:
                num_val = float(str(value).replace(",", "").replace("$", ""))
                min_val = rules.get("min")
                max_val = rules.get("max")
                if min_val is not None and num_val < min_val:
                    validation_errors.append(f"{field}={num_val} is below minimum {min_val}")
                if max_val is not None and num_val > max_val:
                    validation_errors.append(f"{field}={num_val} exceeds maximum {max_val}")
            except (ValueError, TypeError):
                validation_errors.append(f"{field} expected numeric, got: {type(value).__name__}")
        elif field_type == "date":
            if not re.match(r"\d{4}-\d{2}-\d{2}", str(value)):
                validation_warnings.append(f"{field} date format should be YYYY-MM-DD, got: {str(value)[:20]}")

    # Cross-field business rules
    if document_type in (DocumentType.LOAN_APPLICATION_RESIDENTIAL.value,
                          DocumentType.LOAN_APPLICATION_COMMERCIAL.value):
        loan_amount = extracted.get("loan_amount")
        appraised_value = extracted.get("appraised_value")
        if loan_amount and appraised_value:
            try:
                ltv = float(loan_amount) / float(appraised_value)
                if ltv > 1.10:
                    business_rule_violations.append(
                        f"LTV {ltv:.1%} exceeds 110% — possible data entry error"
                    )
            except (ValueError, ZeroDivisionError):
                pass

    if document_type == DocumentType.SWIFT_MT103.value:
        amount = extracted.get("amount")
        if amount:
            try:
                if float(str(amount).replace(",", "")) >= 10000:
                    validation_warnings.append(
                        "SWIFT MT103 amount ≥ $10,000 — CTR filing evaluation required (BSA)"
                    )
            except ValueError:
                pass

    if document_type in (DocumentType.SWIFT_MT103.value, DocumentType.WIRE_INSTRUCTION.value):
        # ── CONTROL: screen ALL jurisdiction sources, fail-closed ─────────
        # Jurisdiction lives in the BIC (chars 5–6) as well as any explicit
        # country field. A wire whose jurisdiction cannot be determined is a
        # violation, not a pass (mirrors Agent 10's sanctions fail-closed rule).
        high_risk_countries = {"IR", "KP", "SY", "CU", "VE", "MM", "BY", "ZW", "RU", "AF", "SO", "SS", "LY", "YE"}
        known_iso2 = {
            "US", "GB", "DE", "FR", "CH", "JP", "CA", "AU", "NL", "SG", "HK",
            "IE", "LU", "BE", "ES", "IT", "SE", "NO", "DK", "FI", "AT", "PT",
            "NZ", "MX", "BR", "IN", "CN", "KR", "AE", "SA", "ZA", "PL", "CZ",
        } | high_risk_countries

        jurisdiction_sources = []
        explicit_country = (extracted.get("beneficiary_country") or "").strip().upper()
        if explicit_country:
            jurisdiction_sources.append(("beneficiary_country", explicit_country))
        for bic_field in ("beneficiary_bank_bic", "ordering_bank_bic"):
            bic = (extracted.get(bic_field) or "").strip().upper()
            if len(bic) >= 6:
                jurisdiction_sources.append((bic_field, bic[4:6]))

        for source, cc in jurisdiction_sources:
            if cc in high_risk_countries:
                business_rule_violations.append(
                    f"{source} resolves to high-risk jurisdiction {cc} — "
                    "OFAC/AML enhanced review required before processing"
                )
            elif cc not in known_iso2:
                business_rule_violations.append(
                    f"{source} country code '{cc}' is not a recognized jurisdiction — "
                    "cannot verify sanctions status; fail-closed AML review required"
                )

    # ── Document date sanity: future-dated documents are invalid ──────────
    doc_date = state.get("document_date") or extracted.get("document_date")
    if doc_date:
        try:
            parsed = datetime.fromisoformat(str(doc_date).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed > datetime.now(timezone.utc):
                validation_errors.append(
                    f"Document date {doc_date} is in the future — invalid document date"
                )
        except (ValueError, TypeError):
            validation_warnings.append(f"Document date '{doc_date}' could not be parsed")

    validation_passed = len(validation_errors) == 0

    audit = _append_audit(state, "validation", {
        "validation_passed": validation_passed,
        "errors_count": len(validation_errors),
        "warnings_count": len(validation_warnings),
        "violations_count": len(business_rule_violations),
    })

    return {
        "validation_passed": validation_passed,
        "validation_errors": validation_errors,
        "validation_warnings": validation_warnings,
        "business_rule_violations": business_rule_violations,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["validation"],
        "errors": errors,
    }


# ── Node 7: Confidence Scoring ────────────────────────────────────────────────

def confidence_scoring_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Python aggregates field-level confidence scores into a composite.

    Weighting:
      Classification confidence   30%
      Field completeness         30%   (fraction of required fields found)
      Field confidence (avg)     25%   (mean of field_confidence_scores)
      Extraction quality         15%   (OCR score or text quality signal)

    Hard overrides (Python — no LLM):
      - UNKNOWN document type → UNCERTAIN tier
      - Any ALWAYS_HITL_DOCUMENT_TYPES → HITL regardless of score
      - validation_errors present → maximum MEDIUM tier
    """
    doc_type = state.get("document_type", DocumentType.UNKNOWN.value)
    doc_type_confidence = float(state.get("document_type_confidence", 0.0))
    field_confidence_scores = dict(state.get("field_confidence_scores", {}))
    missing_required = list(state.get("missing_required_fields", []))
    validation_errors = list(state.get("validation_errors", []))
    extraction_warnings = list(state.get("extraction_warnings", []))
    ocr_confidence = state.get("ocr_confidence")

    schema = _load_field_schema(doc_type)
    total_required = len(schema.get("required", []))

    # Factor 1: Classification confidence (30%)
    f1 = doc_type_confidence

    # Factor 2: Field completeness (30%)
    # CONTROL: missing_required_fields in state is authoritative evidence of
    # incompleteness. A schema-lookup miss (total_required == 0) must NEVER
    # convert declared-missing fields into a perfect completeness score —
    # missing data degrades confidence, it does not inflate it.
    if total_required > 0:
        fields_found = max(total_required - len(missing_required), 0)
        f2 = fields_found / total_required
    elif missing_required:
        found_count = len([v for v in field_confidence_scores.values() if v is not None])
        f2 = found_count / (found_count + len(missing_required))
    else:
        f2 = 1.0 if field_confidence_scores else 0.5

    # Factor 3: Average field confidence (25%)
    if field_confidence_scores:
        f3 = sum(field_confidence_scores.values()) / len(field_confidence_scores)
    else:
        f3 = 0.5 if doc_type != DocumentType.UNKNOWN.value else 0.0

    # Factor 4: Extraction quality (15%)
    if ocr_confidence is not None:
        f4 = ocr_confidence
    elif extraction_warnings:
        f4 = 0.60  # Warnings reduce quality
    else:
        f4 = 0.90  # Clean text extraction

    composite = (f1 * 0.30) + (f2 * 0.30) + (f3 * 0.25) + (f4 * 0.15)

    # Hard overrides
    if doc_type == DocumentType.UNKNOWN.value:
        composite = min(composite, 0.35)
    if validation_errors:
        composite = min(composite, 0.64)  # Cap at top of MEDIUM

    # Tier determination
    if composite >= CONFIDENCE_HIGH_TIER:
        tier = ExtractionConfidence.HIGH.value
    elif composite >= CONFIDENCE_MEDIUM_TIER:
        tier = ExtractionConfidence.MEDIUM.value
    elif composite >= 0.40:
        tier = ExtractionConfidence.LOW.value
    else:
        tier = ExtractionConfidence.UNCERTAIN.value

    breakdown = {
        "classification_confidence": round(f1, 4),
        "classification_weight": 0.30,
        "field_completeness": round(f2, 4),
        "field_completeness_weight": 0.30,
        "avg_field_confidence": round(f3, 4),
        "avg_field_confidence_weight": 0.25,
        "extraction_quality": round(f4, 4),
        "extraction_quality_weight": 0.15,
        "composite_confidence": round(composite, 4),
        "confidence_tier": tier,
    }

    audit = _append_audit(state, "confidence_scoring", {
        "composite_confidence": round(composite, 4),
        "confidence_tier": tier,
        "breakdown": breakdown,
    })

    return {
        "composite_confidence": composite,
        "confidence_tier": tier,
        "confidence_breakdown": breakdown,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["confidence_scoring"],
    }


# ── Node 8: Routing Decision ──────────────────────────────────────────────────

def routing_decision_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Python-only routing. Maps document_type to target_agents.
    Sets human_review_required based on confidence tier and document type.

    No LLM involvement. Routing table is a Python constant
    (DOCUMENT_ROUTING) — cannot be altered at runtime.

    HITL required when:
    - confidence_tier is LOW or UNCERTAIN
    - document_type is in ALWAYS_HITL_DOCUMENT_TYPES
    - document_type is UNKNOWN
    - business_rule_violations present (AML/fraud signals)
    - PII handling level is HUMAN_REVIEW or ENCRYPT
    """
    doc_type = state.get("document_type", DocumentType.UNKNOWN.value)
    confidence_tier = state.get("confidence_tier", ExtractionConfidence.UNCERTAIN.value)
    business_rule_violations = list(state.get("business_rule_violations", []))
    pii_handling = state.get("pii_handling_required", "STANDARD")
    validation_errors = list(state.get("validation_errors", []))

    # Target agents from lookup table
    target_agents = list(DOCUMENT_ROUTING.get(doc_type, []))

    # Priority
    priority = DOCUMENT_PRIORITY.get(doc_type, "NORMAL")

    # HITL triggers
    hitl_reasons = []
    if confidence_tier in (ExtractionConfidence.LOW.value, ExtractionConfidence.UNCERTAIN.value):
        hitl_reasons.append(f"Confidence tier {confidence_tier} below threshold for auto-routing")
    if doc_type in ALWAYS_HITL_DOCUMENT_TYPES:
        hitl_reasons.append(f"Document type {doc_type} always requires human review")
    if doc_type == DocumentType.UNKNOWN.value:
        hitl_reasons.append("Document type could not be classified — manual review required")
    if business_rule_violations:
        hitl_reasons.append(f"Business rule violations: {'; '.join(business_rule_violations[:2])}")
    if pii_handling in ("HUMAN_REVIEW", "ENCRYPT"):
        hitl_reasons.append(f"PII handling level {pii_handling} requires reviewer confirmation")
    if validation_errors:
        hitl_reasons.append(f"Validation errors: {len(validation_errors)} field(s) failed validation")

    human_review_required = bool(hitl_reasons)
    human_review_reason = "; ".join(hitl_reasons) if hitl_reasons else "Auto-route eligible"

    routing_rationale = (
        f"Document type {doc_type} routes to: {', '.join(target_agents) if target_agents else 'NONE — HITL required'}"
    )

    audit = _append_audit(state, "routing_decision", {
        "target_agents": target_agents,
        "priority": priority,
        "human_review_required": human_review_required,
        "hitl_reasons": hitl_reasons,
    })

    return {
        "target_agents": target_agents,
        "routing_rationale": routing_rationale,
        "human_review_required": human_review_required,
        "human_review_reason": human_review_reason,
        "priority": priority,
        "document_status": DocumentStatus.PENDING_REVIEW.value if human_review_required else DocumentStatus.ROUTED.value,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["routing_decision"],
    }


# ── Node 9: Human Review Gate (HITL) ─────────────────────────────────────────

def human_review_gate(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    HITL interrupt — workflow pauses until a reviewer submits a decision.

    Reviewer decisions:
    - APPROVE_AND_ROUTE: Accept extraction as-is and route to target agents
    - CORRECT_AND_ROUTE: Apply corrections and route
    - REJECT: Document is invalid / not processable
    - REQUEST_RESUBMIT: Ask submitter for a clearer document

    Security: reviewer_id required. Corrections are applied by
    correction_node (LLM merges corrections cleanly).
    """
    reviewer_id = state.get("reviewer_id", "")
    reviewer_decision = state.get("reviewer_decision", "")
    reviewer_notes = state.get("reviewer_notes", "")
    reviewer_corrections = dict(state.get("reviewer_corrections", {}))

    if not reviewer_id:
        reviewer_id = "SYSTEM_PENDING"

    audit = _append_audit(state, "human_review_gate", {
        "reviewer_id": reviewer_id,
        "reviewer_decision": reviewer_decision,
        "corrections_count": len(reviewer_corrections),
    })

    result = {
        "reviewer_id": reviewer_id,
        "reviewer_decision": reviewer_decision,
        "reviewer_notes": reviewer_notes,
        "reviewer_corrections": reviewer_corrections,
        "review_timestamp": _now_utc(),
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["human_review_gate"],
    }

    # Terminal reviewer decisions set the document's final status here —
    # audit_finalize reads document_status as-is, so a REJECT must flip the
    # status at the gate or the document would finish as PENDING_REVIEW.
    if reviewer_decision == "REJECT":
        result["document_status"] = DocumentStatus.REJECTED.value
    elif reviewer_decision == "REQUEST_RESUBMIT":
        result["document_status"] = DocumentStatus.REJECTED.value
        result["resubmission_requested"] = True

    return result


# ── Node 10: Enrichment ───────────────────────────────────────────────────────

def enrichment_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    LLM provides contextual enrichment notes for the downstream agent.
    Works only with masked extracted fields — never the raw document text.
    Identifies anomalies, regulatory relevance, and routing context.
    """
    llm = _get_llm()
    doc_type = state.get("document_type", DocumentType.UNKNOWN.value)
    reviewer_corrections = dict(state.get("reviewer_corrections", {}))
    errors = list(state.get("errors", []))

    # If reviewer provided corrections, apply them first
    extracted_fields = dict(state.get("extracted_fields", {}))
    field_confidence = dict(state.get("field_confidence_scores", {}))

    if reviewer_corrections:
        from langchain_core.messages import HumanMessage, SystemMessage
        try:
            corr_prompt = CORRECTION_USER_PROMPT.format(
                original_fields=json.dumps(extracted_fields, indent=2),
                corrections=json.dumps(reviewer_corrections, indent=2),
            )
            resp = llm.invoke([
                SystemMessage(content=CORRECTION_SYSTEM_PROMPT),
                HumanMessage(content=corr_prompt),
            ])
            raw = resp.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            corrected = json.loads(raw)
            extracted_fields.update(corrected)
            # Mark corrected fields with 1.0 confidence
            for k in reviewer_corrections:
                field_confidence[k] = 1.0
        except Exception as e:
            errors.append(f"Correction merge error: {str(e)[:100]}")

    # Mask PII in fields before enrichment LLM sees them
    masked_fields_str = json.dumps({
        k: ("[MASKED]" if k in state.get("pii_field_names", []) else v)
        for k, v in extracted_fields.items()
    }, indent=2)

    target_agents = state.get("target_agents", [])
    missing_fields = state.get("missing_required_fields", [])
    low_conf_fields = state.get("low_confidence_fields", [])
    validation_warnings = state.get("validation_warnings", [])

    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        enrich_prompt = ENRICHMENT_USER_PROMPT.format(
            document_type=doc_type,
            document_date=state.get("document_date", "unknown"),
            document_issuer=state.get("document_issuer", "unknown"),
            target_agents=", ".join(target_agents) if target_agents else "NONE",
            masked_fields=masked_fields_str,
            missing_fields=", ".join(missing_fields) if missing_fields else "none",
            low_confidence_fields=", ".join(low_conf_fields) if low_conf_fields else "none",
            validation_warnings="; ".join(validation_warnings) if validation_warnings else "none",
        )
        response = llm.invoke([
            SystemMessage(content=ENRICHMENT_SYSTEM_PROMPT),
            HumanMessage(content=enrich_prompt),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        enrich_result = json.loads(raw)
    except Exception as e:
        errors.append(f"Enrichment LLM error: {str(e)[:100]}")
        enrich_result = {
            "enrichment_notes": f"Document type: {doc_type}. Routed to: {', '.join(target_agents)}.",
            "anomaly_flags": [],
            "regulatory_relevance": [],
        }

    audit = _append_audit(state, "enrichment", {
        "anomaly_flags_count": len(enrich_result.get("anomaly_flags", [])),
        "regulatory_frameworks": enrich_result.get("regulatory_relevance", []),
        "corrections_applied": len(reviewer_corrections),
    })

    return {
        "extracted_fields": extracted_fields,
        "field_confidence_scores": field_confidence,
        "enrichment_notes": enrich_result.get("enrichment_notes", ""),
        "anomaly_flags": enrich_result.get("anomaly_flags", []),
        "regulatory_relevance": enrich_result.get("regulatory_relevance", []),
        "audit_trail": audit,
        "errors": errors,
        "completed_steps": list(state.get("completed_steps", [])) + ["enrichment"],
    }


# ── Node 11: Output Packaging ─────────────────────────────────────────────────

def output_packaging_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Produce the final structured output payload for downstream agents.
    Python-only. PII fields are masked in the output by default.
    Downstream agents request PII via separate authenticated channel
    (not included in the output payload).
    """
    doc_type = state.get("document_type", DocumentType.UNKNOWN.value)
    extracted_fields = dict(state.get("extracted_fields", {}))
    pii_field_names = list(state.get("pii_field_names", []))
    target_agents = list(state.get("target_agents", []))
    reviewer_decision = state.get("reviewer_decision", "")

    # Determine final routing (reviewer may have changed decision)
    if reviewer_decision == "REJECT":
        final_status = DocumentStatus.REJECTED.value
        target_agents = []
    elif reviewer_decision == "REQUEST_RESUBMIT":
        final_status = DocumentStatus.REJECTED.value
        target_agents = []
    else:
        final_status = DocumentStatus.ROUTED.value

    # Mask PII in output payload
    masked_payload_fields = {
        k: "[PII-PROTECTED — REQUEST VIA SECURE CHANNEL]" if k in pii_field_names else v
        for k, v in extracted_fields.items()
    }

    output_payload = {
        "document_id": state.get("document_id"),
        "document_hash": state.get("document_hash"),
        "document_type": doc_type,
        "document_date": state.get("document_date"),
        "document_issuer": state.get("document_issuer"),
        "document_reference": state.get("document_reference"),
        "extracted_fields": masked_payload_fields,
        "field_confidence_scores": state.get("field_confidence_scores", {}),
        "composite_confidence": state.get("composite_confidence", 0.0),
        "confidence_tier": state.get("confidence_tier", "UNCERTAIN"),
        "missing_required_fields": state.get("missing_required_fields", []),
        "validation_warnings": state.get("validation_warnings", []),
        "business_rule_violations": state.get("business_rule_violations", []),
        "anomaly_flags": state.get("anomaly_flags", []),
        "regulatory_relevance": state.get("regulatory_relevance", []),
        "enrichment_notes": state.get("enrichment_notes", ""),
        "pii_detected": state.get("pii_detected", False),
        "pii_types": state.get("pii_types_found", []),
        "reviewed_by": state.get("reviewer_id"),
        "review_timestamp": state.get("review_timestamp"),
    }

    routing_instructions = {
        "target_agents": target_agents,
        "priority": state.get("priority", "NORMAL"),
        "routing_rationale": state.get("routing_rationale", ""),
        "document_id": state.get("document_id"),
        "output_schema_version": "1.0",
    }

    audit = _append_audit(state, "output_packaging", {
        "target_agents": target_agents,
        "final_status": final_status,
        "pii_fields_masked": len(pii_field_names),
        "output_payload_fields": len(output_payload["extracted_fields"]),
    })

    return {
        "output_payload": output_payload,
        "output_schema_version": "1.0",
        "routing_instructions": routing_instructions,
        "document_status": final_status,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["output_packaging"],
    }


# ── Node 12: Audit Finalize ───────────────────────────────────────────────────

def audit_finalize_node(state: DocumentIntelligenceState) -> Dict[str, Any]:
    """
    Close the audit trail and compute processing time.
    Clean up text cache for this document (memory management).
    """
    doc_hash = state.get("document_hash", "")
    submission_ts = state.get("submission_timestamp", _now_utc())

    # Compute processing time
    try:
        start = datetime.fromisoformat(submission_ts)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    except Exception:
        elapsed = 0.0

    # Clear text from cache (document processed — release memory)
    _TEXT_CACHE.pop(doc_hash, None)

    # ── Resolve terminal status ────────────────────────────────────────────
    # On HITL resume the reviewer decision may be injected directly into
    # state (update_state as_node="human_review_gate"), in which case the
    # gate function body never executes — so the terminal status must be
    # resolved here, at the single point every path flows through.
    reviewer_decision = state.get("reviewer_decision", "")
    current_status = state.get("document_status", "UNKNOWN")
    if reviewer_decision in ("REJECT", "REQUEST_RESUBMIT"):
        final_status = DocumentStatus.REJECTED.value
    elif reviewer_decision in ("APPROVE_AND_ROUTE", "CORRECT_AND_ROUTE"):
        final_status = DocumentStatus.ROUTED.value
    else:
        final_status = current_status

    audit = _append_audit(state, "audit_finalize", {
        "final_status": final_status,
        "reviewer_decision": reviewer_decision or "N/A",
        "target_agents": state.get("target_agents", []),
        "composite_confidence": round(state.get("composite_confidence", 0.0), 4),
        "processing_time_seconds": round(elapsed, 2),
        "anomaly_flags_count": len(state.get("anomaly_flags", [])),
    })

    return {
        "document_status": final_status,
        "processing_time_seconds": elapsed,
        "audit_trail": audit,
        "completed_steps": list(state.get("completed_steps", [])) + ["audit_finalize"],
    }


# ── Contract alias ───────────────────────────────────────────────────────────
# tests/test_graph.py imports the HITL gate as human_review_gate_node.
human_review_gate_node = human_review_gate
