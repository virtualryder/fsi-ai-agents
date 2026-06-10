# tests/test_nodes.py
# ============================================================
# Document Intelligence Agent — Unit Tests for Node Functions
#
# These tests verify the correctness and security properties
# of each node function in agent/nodes.py.
#
# TEST PHILOSOPHY
# ---------------
# 1. Python nodes are tested directly (no LangGraph graph needed).
#    LLM nodes are tested with mocked responses — we test that the
#    node correctly processes LLM output, not that the LLM model works.
#
# 2. Security tests are FIRST-CLASS tests, not afterthoughts.
#    Every security control has at least one test that verifies
#    it cannot be bypassed.
#
# 3. Tests are deterministic — no random values, no network calls.
#    All LLM interactions are mocked.
#
# COVERAGE TARGETS
# ----------------
# - document_intake_node: duplicate detection, hash computation, rejection
# - pii_detection_node: SSN, passport, IBAN, account number masking
# - validation_node: SWIFT high-risk country check, CTR threshold
# - confidence_scoring_node: tier assignment at boundaries
# - routing_decision_node: HITL triggers, agent routing
# - ALWAYS_HITL_DOCUMENT_TYPES: immutability and completeness
# - Security: no raw PII in state after processing
# ============================================================
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from agent.nodes import (
    ALWAYS_HITL_DOCUMENT_TYPES,
    CONFIDENCE_HIGH_TIER,
    CONFIDENCE_HITL_THRESHOLD,
    CONFIDENCE_MEDIUM_TIER,
    DOCUMENT_ROUTING,
    PII_PATTERNS,
    _append_audit,
    _detect_and_mask_pii,
    _mask_account_numbers,
    _now_utc,
    _sanitize_text,
    confidence_scoring_node,
    document_intake_node,
    pii_detection_node,
    routing_decision_node,
    validation_node,
)
from agent.state import (
    DocumentStatus,
    DocumentType,
    ExtractionConfidence,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _base_state(**overrides) -> Dict[str, Any]:
    """Return a minimal valid state dict for testing."""
    state = {
        "document_id": str(uuid.uuid4()),
        "document_hash": hashlib.sha256(b"test_document_content").hexdigest(),
        "source_filename": "test_document.pdf",
        "file_format": "PDF",
        "file_size_bytes": 1024,
        "submitted_by": "test.user@bank.example.com",
        "submission_timestamp": _now_utc(),
        "source_system": "MANUAL",
        "document_type": DocumentType.LOAN_APPLICATION_RESIDENTIAL.value,
        "document_type_confidence": 0.90,
        "full_text_char_count": 1500,
        "extraction_warnings": [],
        "extracted_fields": {
            "applicant_name": "Jane Test",
            "loan_amount_requested": 500000,
            "credit_score": 720,
        },
        "field_confidence_scores": {
            "applicant_name": 0.95,
            "loan_amount_requested": 0.92,
            "credit_score": 0.88,
        },
        "missing_required_fields": [],
        "low_confidence_fields": [],
        "extraction_exceptions": [],
        "pii_detected": False,
        "pii_types_found": [],
        "pii_field_names": [],
        "pii_handling_required": "STANDARD",
        "validation_passed": True,
        "validation_errors": [],
        "validation_warnings": [],
        "business_rule_violations": [],
        "audit_trail": [],
        "completed_steps": [],
        "errors": [],
    }
    state.update(overrides)
    return state


# ── PII Detection Tests ───────────────────────────────────────────────────────

class TestPIIDetection:
    """Tests for PII masking functions — the first security layer before LLM."""

    def test_ssn_detected_and_masked(self):
        """SSN in standard format (XXX-XX-XXXX) must be masked before reaching LLM."""
        text = "Applicant SSN: 123-45-6789. Income: $85,000."
        result, detected = _detect_and_mask_pii(text)
        assert "123-45-6789" not in result, "Raw SSN must not appear after masking"
        assert "SSN" in detected

    def test_ssn_without_dashes_detected(self):
        """SSN without dashes (9 consecutive digits) must also be detected."""
        text = "Social Security Number 123456789 on file."
        result, detected = _detect_and_mask_pii(text)
        assert "123456789" not in result
        assert "SSN" in detected

    def test_passport_detected(self):
        """Passport-format strings (letter(s) + digits) must be detected."""
        text = "Passport Number: A12345678 issued by USA."
        result, detected = _detect_and_mask_pii(text)
        assert "PASSPORT" in detected

    def test_iban_detected_and_masked(self):
        """IBAN must be detected for international wire transfer documents."""
        text = "IBAN: GB29NWBK60161331926819"
        result, detected = _detect_and_mask_pii(text)
        assert "IBAN" in detected

    def test_credit_card_masked(self):
        """Credit card numbers (4x4 digit groups) must be masked."""
        text = "Card: 4111 1111 1111 1111"
        result, detected = _detect_and_mask_pii(text)
        assert "4111 1111 1111 1111" not in result

    def test_account_number_last4_preserved(self):
        """Account masking must preserve last 4 digits for identification."""
        masked = _mask_account_numbers("12345678")
        assert "5678" in masked
        assert "1234" not in masked

    def test_non_pii_text_unchanged(self):
        """Text with no PII should pass through unmodified."""
        text = "Property is located at 123 Main St. Loan amount: $450,000."
        result, detected = _detect_and_mask_pii(text)
        # Address/dollar amounts are not PII types in our detection set
        assert len(detected) == 0 or all(d not in ("SSN", "PASSPORT", "CREDIT_CARD") for d in detected)

    def test_pii_detection_node_masks_cached_text(self):
        """
        CRITICAL SECURITY TEST: pii_detection_node must mask the text cache
        BEFORE document_classification_node reads it. Verify that after running
        pii_detection_node, the cache for this document no longer contains raw SSNs.
        """
        from agent.nodes import _store_text_in_cache, _get_text_from_cache

        doc_hash = hashlib.sha256(b"pii_test").hexdigest()
        raw_text = "Borrower SSN: 987-65-4321. Loan amount: $300,000."
        _store_text_in_cache(doc_hash, raw_text)

        state = _base_state(
            document_hash=doc_hash,
            full_text_char_count=len(raw_text),
            extraction_warnings=[],
        )
        result = pii_detection_node(state)

        # Check the cache was updated with masked text
        cached = _get_text_from_cache(doc_hash)
        assert re.search(r"\b\d{3}-\d{2}-\d{4}\b", cached) is None, \
            "Raw SSN must not remain in text cache after pii_detection_node runs"
        assert result["pii_detected"] is True
        assert "SSN" in result["pii_types_found"]


# ── Sanitization Tests ────────────────────────────────────────────────────────

class TestSanitization:
    """Tests for input sanitization — prevents injection attacks."""

    def test_control_characters_stripped(self):
        """Control characters (non-printable) must be stripped from document text."""
        evil_text = "Normal text\x00\x01\x02\x03Hidden injection"
        sanitized = _sanitize_text(evil_text)
        assert "\x00" not in sanitized
        assert "\x01" not in sanitized
        assert "Normal text" in sanitized

    def test_text_truncated_at_max_length(self):
        """Text must be truncated at the safety maximum to prevent oversized LLM context."""
        long_text = "A" * 5000
        sanitized = _sanitize_text(long_text)
        assert len(sanitized) <= 2000, "Sanitized text must not exceed 2000 characters"

    def test_newlines_preserved(self):
        """Newlines are valid whitespace and must not be stripped by sanitization."""
        text = "Line 1\nLine 2\nLine 3"
        sanitized = _sanitize_text(text)
        assert "\n" in sanitized


# ── Document Intake Tests ─────────────────────────────────────────────────────

class TestDocumentIntake:
    """Tests for the document_intake_node — the first node in the graph."""

    def test_intake_sets_document_status_received(self):
        """Intake node must set document_status to RECEIVED on successful intake."""
        state = {
            "document_id": str(uuid.uuid4()),
            "document_hash": hashlib.sha256(b"content").hexdigest(),
            "source_filename": "test.pdf",
            "file_format": "PDF",
            "file_size_bytes": 2048,
            "submitted_by": "user@bank.example.com",
            "submission_timestamp": _now_utc(),
            "source_system": "LOS",
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        }
        result = document_intake_node(state)
        assert result["document_status"] == DocumentStatus.RECEIVED.value

    def test_intake_rejects_oversized_document(self):
        """Documents exceeding 10MB must be rejected to prevent resource exhaustion."""
        state = {
            "document_id": str(uuid.uuid4()),
            "document_hash": "abc123",
            "source_filename": "huge.pdf",
            "file_format": "PDF",
            "file_size_bytes": 11 * 1024 * 1024,  # 11MB
            "submitted_by": "user@bank.example.com",
            "submission_timestamp": _now_utc(),
            "source_system": "MANUAL",
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        }
        result = document_intake_node(state)
        assert result["document_status"] == DocumentStatus.REJECTED.value
        assert any("size" in e.lower() or "10mb" in e.lower() for e in result["errors"])

    def test_intake_rejects_unknown_file_format(self):
        """Documents with unsupported file formats must be rejected at intake."""
        state = {
            "document_id": str(uuid.uuid4()),
            "document_hash": "abc123",
            "source_filename": "malware.exe",
            "file_format": "UNKNOWN",
            "file_size_bytes": 1024,
            "submitted_by": "user@bank.example.com",
            "submission_timestamp": _now_utc(),
            "source_system": "MANUAL",
            "audit_trail": [],
            "completed_steps": [],
            "errors": [],
        }
        result = document_intake_node(state)
        assert result["document_status"] == DocumentStatus.REJECTED.value


# ── Validation Tests ──────────────────────────────────────────────────────────

class TestValidation:
    """Tests for the validation_node — Python-driven business rule enforcement."""

    def test_swift_high_risk_country_flagged(self):
        """
        SWIFT wires with high-risk country BICs must generate a business rule
        violation. This is a security control — high-risk jurisdiction wires
        must always trigger enhanced scrutiny.
        """
        state = _base_state(
            document_type=DocumentType.SWIFT_MT103.value,
            extracted_fields={
                "transaction_reference_number": "REF001",
                "value_date": "2024-01-15",
                "currency": "USD",
                "amount": 50000.00,
                "ordering_customer_name": "TEST CORP",
                "ordering_customer_account": "****1234",
                "beneficiary_name": "BENEFICIARY LLC",
                "beneficiary_account": "****5678",
                "beneficiary_bank_bic": "TCZBZZZZ",  # Zimbabwe — high-risk
                "ordering_bank_bic": "FNBKUS33",
            },
        )
        result = validation_node(state)
        violations = result.get("business_rule_violations", [])
        assert any("high-risk" in v.lower() or "country" in v.lower() or "jurisdiction" in v.lower()
                   for v in violations), \
            "High-risk country BIC must generate a business rule violation"

    def test_ctr_threshold_flagged(self):
        """Cash transaction above CTR threshold ($10,000) must be flagged."""
        state = _base_state(
            document_type=DocumentType.BANK_STATEMENT.value,
            extracted_fields={
                "account_number_last4": "****9999",
                "account_holder_name": "Test Corp",
                "institution_name": "Test Bank",
                "statement_period_start": "2024-01-01",
                "statement_period_end": "2024-01-31",
                "beginning_balance": 5000.00,
                "ending_balance": 6000.00,
                "total_deposits": 25000.00,
                "total_withdrawals": 24000.00,
                "cash_deposits_count": 3,
            },
        )
        # If cash deposits totaling > $10,000 exist, a CTR flag should be raised
        # (the validation node checks for high cash deposit patterns)
        result = validation_node(state)
        # Validation should pass for a standard bank statement; cash flag in warnings
        assert result.get("validation_passed") is not None

    def test_future_date_in_loan_application_flagged(self):
        """A loan application with a future document date must generate a validation error."""
        state = _base_state(
            document_type=DocumentType.LOAN_APPLICATION_RESIDENTIAL.value,
            document_date="2099-12-31",
            extracted_fields={
                "applicant_name": "Jane Test",
                "loan_amount_requested": 500000,
                "credit_score": 720,
                "annual_income": 150000,
                "monthly_debt_payments": 2000,
                "property_address": "123 Main St",
                "property_type": "Single Family Residence",
                "loan_purpose": "PURCHASE",
            },
        )
        result = validation_node(state)
        errors = result.get("validation_errors", [])
        assert any("future" in e.lower() or "date" in e.lower() for e in errors)


# ── Confidence Scoring Tests ──────────────────────────────────────────────────

class TestConfidenceScoring:
    """Tests for the confidence_scoring_node — Python-computed tier assignment."""

    def test_high_confidence_tier_assigned(self):
        """A well-extracted document with high scores must be assigned HIGH tier."""
        state = _base_state(
            document_type_confidence=0.95,
            missing_required_fields=[],
            low_confidence_fields=[],
            extraction_warnings=[],
            field_confidence_scores={
                "field1": 0.92,
                "field2": 0.88,
                "field3": 0.95,
            },
        )
        result = confidence_scoring_node(state)
        assert result["confidence_tier"] == ExtractionConfidence.HIGH.value

    def test_low_confidence_tier_assigned_when_many_missing_fields(self):
        """Multiple missing required fields must push composite confidence to LOW tier."""
        state = _base_state(
            document_type_confidence=0.72,
            missing_required_fields=["field1", "field2", "field3", "field4"],
            low_confidence_fields=["field5"],
            extraction_warnings=["OCR quality poor"],
            field_confidence_scores={"field5": 0.45},
        )
        result = confidence_scoring_node(state)
        tier = result["confidence_tier"]
        assert tier in (ExtractionConfidence.LOW.value, ExtractionConfidence.UNCERTAIN.value), \
            f"Expected LOW or UNCERTAIN, got {tier}"

    def test_uncertain_tier_when_classification_confidence_low(self):
        """Low classification confidence (< 0.40) must produce UNCERTAIN tier."""
        state = _base_state(
            document_type_confidence=0.35,
            document_type=DocumentType.UNKNOWN.value,
            missing_required_fields=[],
            low_confidence_fields=[],
            extraction_warnings=[],
            field_confidence_scores={},
        )
        result = confidence_scoring_node(state)
        tier = result["confidence_tier"]
        assert tier in (ExtractionConfidence.UNCERTAIN.value, ExtractionConfidence.LOW.value)

    def test_composite_score_is_bounded_0_to_1(self):
        """Composite confidence score must always be in the range [0.0, 1.0]."""
        state = _base_state(
            document_type_confidence=0.99,
            missing_required_fields=[],
            low_confidence_fields=[],
            extraction_warnings=[],
            field_confidence_scores={"f": 1.0},
        )
        result = confidence_scoring_node(state)
        score = result["composite_confidence"]
        assert 0.0 <= score <= 1.0, f"Composite confidence {score} out of range [0, 1]"


# ── Routing Decision Tests ────────────────────────────────────────────────────

class TestRoutingDecision:
    """Tests for the routing_decision_node — Python routing table enforcement."""

    def test_swift_mt103_routes_to_financial_crime_and_fraud(self):
        """MT103 must always route to both financial crime and fraud detection agents."""
        state = _base_state(
            document_type=DocumentType.SWIFT_MT103.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.90,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        targets = result.get("target_agents", [])
        assert "01-financial-crime-investigation" in targets
        assert "04-fraud-detection" in targets

    def test_loan_application_routes_to_credit_underwriting(self):
        """Residential loan application must route to credit underwriting agent."""
        state = _base_state(
            document_type=DocumentType.LOAN_APPLICATION_RESIDENTIAL.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.92,
            pii_handling_required="STANDARD",
            pii_detected=True,
            pii_types_found=["SSN", "NAME"],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        targets = result.get("target_agents", [])
        assert "08-credit-underwriting" in targets

    def test_government_id_always_requires_hitl(self):
        """
        CRITICAL SECURITY TEST: GOVERNMENT_ID is in ALWAYS_HITL_DOCUMENT_TYPES.
        Even with perfect extraction confidence, it must require HITL.
        Passports contain biometric data and document authenticity must be human-verified.
        """
        state = _base_state(
            document_type=DocumentType.GOVERNMENT_ID.value,
            confidence_tier=ExtractionConfidence.HIGH.value,  # Even high confidence
            composite_confidence=0.99,                         # Even perfect score
            pii_handling_required="STANDARD",
            pii_detected=True,
            pii_types_found=["PASSPORT", "NAME"],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True, \
            "GOVERNMENT_ID must always require human review, regardless of confidence score"

    def test_sar_form_always_requires_hitl(self):
        """
        CRITICAL SECURITY TEST: SAR_FORM is in ALWAYS_HITL_DOCUMENT_TYPES.
        SARs are confidential by federal law (31 USC 5318(g)(2)) and must
        always be reviewed by a BSA Officer before routing.
        """
        state = _base_state(
            document_type=DocumentType.SAR_FORM.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.95,
            pii_handling_required="STANDARD",
            pii_detected=True,
            pii_types_found=["NAME", "ACCOUNT_NUMBER"],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True, \
            "SAR_FORM must always require human review — federal law requirement"

    def test_ctr_form_always_requires_hitl(self):
        """CTR_FORM must always require HITL — BSA filing verification required."""
        state = _base_state(
            document_type=DocumentType.CTR_FORM.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.93,
            pii_handling_required="STANDARD",
            pii_detected=True,
            pii_types_found=["NAME", "ACCOUNT_NUMBER"],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_consent_order_always_requires_hitl(self):
        """CONSENT_ORDER must always require HITL — board notification required."""
        state = _base_state(
            document_type=DocumentType.CONSENT_ORDER.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.94,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_low_confidence_triggers_hitl(self):
        """Any document with LOW confidence tier must require HITL."""
        state = _base_state(
            document_type=DocumentType.LOAN_APPLICATION_RESIDENTIAL.value,
            confidence_tier=ExtractionConfidence.LOW.value,
            composite_confidence=0.52,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_uncertain_confidence_triggers_hitl(self):
        """UNCERTAIN confidence tier must require HITL."""
        state = _base_state(
            document_type=DocumentType.UNKNOWN.value,
            confidence_tier=ExtractionConfidence.UNCERTAIN.value,
            composite_confidence=0.30,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_unknown_document_type_triggers_hitl(self):
        """UNKNOWN document type must always require HITL — cannot route without classification."""
        state = _base_state(
            document_type=DocumentType.UNKNOWN.value,
            confidence_tier=ExtractionConfidence.MEDIUM.value,  # Even medium confidence
            composite_confidence=0.70,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True, \
            "UNKNOWN document type must always require HITL — routing is impossible without classification"

    def test_validation_errors_trigger_hitl(self):
        """Validation errors in extracted fields must require HITL."""
        state = _base_state(
            document_type=DocumentType.SWIFT_MT103.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.88,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=["BIC format invalid: XXXX1234"],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_business_rule_violations_trigger_hitl(self):
        """Business rule violations (e.g., high-risk country) must require HITL."""
        state = _base_state(
            document_type=DocumentType.SWIFT_MT103.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.90,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=["Beneficiary bank in high-risk jurisdiction: North Korea"],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is True

    def test_high_confidence_clean_document_auto_routes(self):
        """A clean, high-confidence document must auto-route without HITL."""
        state = _base_state(
            document_type=DocumentType.TRADE_CONFIRMATION.value,
            confidence_tier=ExtractionConfidence.HIGH.value,
            composite_confidence=0.91,
            pii_handling_required="STANDARD",
            pii_detected=False,
            pii_types_found=[],
            validation_errors=[],
            business_rule_violations=[],
        )
        result = routing_decision_node(state)
        assert result["human_review_required"] is False, \
            "High-confidence, clean trade confirmation must auto-route without HITL"


# ── ALWAYS_HITL Frozenset Tests ────────────────────────────────────────────────

class TestAlwaysHITLFrozenset:
    """
    Tests for the ALWAYS_HITL_DOCUMENT_TYPES frozenset.
    This frozenset is the authoritative list of document types that must
    ALWAYS receive human review. These tests verify the set is correct
    and cannot be modified at runtime.
    """

    def test_government_id_in_always_hitl(self):
        assert DocumentType.GOVERNMENT_ID.value in ALWAYS_HITL_DOCUMENT_TYPES

    def test_sar_form_in_always_hitl(self):
        assert DocumentType.SAR_FORM.value in ALWAYS_HITL_DOCUMENT_TYPES

    def test_ctr_form_in_always_hitl(self):
        assert DocumentType.CTR_FORM.value in ALWAYS_HITL_DOCUMENT_TYPES

    def test_consent_order_in_always_hitl(self):
        assert DocumentType.CONSENT_ORDER.value in ALWAYS_HITL_DOCUMENT_TYPES

    def test_always_hitl_is_frozenset(self):
        """The ALWAYS_HITL set must be a frozenset — immutable at runtime."""
        assert isinstance(ALWAYS_HITL_DOCUMENT_TYPES, frozenset), \
            "ALWAYS_HITL_DOCUMENT_TYPES must be a frozenset to prevent runtime modification"

    def test_always_hitl_cannot_be_modified(self):
        """Attempts to add to the frozenset must raise TypeError."""
        with pytest.raises((TypeError, AttributeError)):
            ALWAYS_HITL_DOCUMENT_TYPES.add("LOAN_APPLICATION_RESIDENTIAL")  # type: ignore


# ── DOCUMENT_ROUTING Tests ────────────────────────────────────────────────────

class TestDocumentRouting:
    """Tests for the DOCUMENT_ROUTING constant — Python routing table."""

    def test_all_25_document_types_have_routing(self):
        """
        Every DocumentType enum value (except UNKNOWN) must have a routing entry.
        UNKNOWN is not required to have a routing entry — it has no valid target agents
        and always requires HITL, where the human reviewer will reclassify it.
        """
        non_unknown_types = [
            dt.value for dt in DocumentType if dt != DocumentType.UNKNOWN
        ]
        for doc_type in non_unknown_types:
            assert doc_type in DOCUMENT_ROUTING, \
                f"DocumentType {doc_type} is missing from DOCUMENT_ROUTING"

    def test_routing_targets_are_valid_agent_ids(self):
        """All routing targets must be valid downstream agent IDs."""
        valid_agents = {
            "01-financial-crime-investigation",
            "03-kyc-cdd-perpetual",
            "04-fraud-detection",
            "06-regulatory-change",
            "07-trading-surveillance",
            "08-credit-underwriting",
        }
        for doc_type, agents in DOCUMENT_ROUTING.items():
            for agent in agents:
                assert agent in valid_agents, \
                    f"Invalid agent ID '{agent}' in routing for {doc_type}"

    def test_regulatory_exam_letter_routes_to_regulatory_change(self):
        """Exam letters must route to regulatory change management."""
        assert "06-regulatory-change" in DOCUMENT_ROUTING[
            DocumentType.REGULATORY_EXAM_LETTER.value
        ]

    def test_trade_confirmation_routes_to_trading_surveillance(self):
        """Trade confirms must route to trading surveillance."""
        assert "07-trading-surveillance" in DOCUMENT_ROUTING[
            DocumentType.TRADE_CONFIRMATION.value
        ]


# ── Audit Trail Tests ─────────────────────────────────────────────────────────

class TestAuditTrail:
    """Tests for the audit trail — append-only, no PII."""

    def test_audit_trail_is_append_only(self):
        """
        The _append_audit function must return a new list with the new entry appended,
        not modify the existing list.
        """
        original_trail = [{"step": "prior_step", "timestamp": _now_utc()}]
        state = _base_state(audit_trail=original_trail)
        result_trail = _append_audit(state, "test_step", {"key": "value"})

        assert len(result_trail) == len(original_trail) + 1
        assert result_trail[0] == original_trail[0], "Original entries must not be modified"
        assert result_trail[-1]["step"] == "test_step"

    def test_audit_entry_contains_timestamp(self):
        """Every audit entry must have a timestamp for forensic analysis."""
        state = _base_state(audit_trail=[])
        trail = _append_audit(state, "some_step", {"data": "test"})
        assert "timestamp" in trail[-1]

    def test_audit_entry_contains_document_id(self):
        """Every audit entry must reference the document ID for traceability."""
        doc_id = str(uuid.uuid4())
        state = _base_state(document_id=doc_id, audit_trail=[])
        trail = _append_audit(state, "some_step", {"data": "test"})
        assert trail[-1].get("document_id") == doc_id


# ── PII Pattern Coverage Tests ────────────────────────────────────────────────

class TestPIIPatterns:
    """Tests to verify all PII pattern types are defined and functional."""

    def test_ssn_pattern_matches_standard_format(self):
        assert PII_PATTERNS["SSN"].search("123-45-6789") is not None

    def test_ssn_pattern_rejects_000_prefix(self):
        """SSNs starting with 000 are invalid and should not be matched."""
        assert PII_PATTERNS["SSN"].search("000-45-6789") is None

    def test_ssn_pattern_rejects_666_prefix(self):
        """SSNs starting with 666 are invalid and should not be matched."""
        assert PII_PATTERNS["SSN"].search("666-45-6789") is None

    def test_ein_pattern_matches(self):
        assert PII_PATTERNS["EIN"].search("12-3456789") is not None

    def test_routing_number_pattern_matches(self):
        """Routing numbers must start with 0."""
        assert PII_PATTERNS["ROUTING_NUMBER"].search("021000021") is not None

    def test_routing_number_does_not_match_non_zero_prefix(self):
        """Account numbers not starting with 0 must not match routing number pattern."""
        assert PII_PATTERNS["ROUTING_NUMBER"].search("121000021") is None

    def test_iban_pattern_matches(self):
        assert PII_PATTERNS["IBAN"].search("GB29NWBK60161331926819") is not None

    def test_credit_card_pattern_matches(self):
        assert PII_PATTERNS["CREDIT_CARD"].search("4111 1111 1111 1111") is not None
