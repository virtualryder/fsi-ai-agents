"""
Common PII masking — Rec 4 (finding H3).

Consolidates the best of the per-agent regex sets into one layered masker:

  Layer 1 (always): regex patterns — SSN *including the ITIN 9xx range*
  (under-masking is the failure mode), EIN, passport, credit cards with
  Luhn validation (kills false positives on 16-digit reference numbers
  while still masking real PANs), IBAN, US account/routing patterns,
  email, US phone, and dates of birth in labeled contexts.

  Layer 2 (optional, env-activated): ML PII detection for names/addresses
  that regex cannot reliably catch —
      PII_ENGINE=comprehend  → Amazon Comprehend DetectPiiEntities
      PII_ENGINE=presidio    → Microsoft Presidio AnalyzerEngine
  Both are lazy imports; absence of the engine degrades to Layer 1 with a
  logged warning rather than crashing (the regex layer still runs).

Contract: `mask(text) -> (masked_text, sorted list of PII types found)`.
Mask at EVERY state-write boundary, not just intake (the Agent 09 preview
leak is the canonical example of why). For structured records, use
`scrub_for_persistence(record)` / `mask_obj(obj)` so masking is enforced by
the persistence path rather than left to per-field discipline. (Phase 1.4.)
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ── Layer 1: regex patterns ───────────────────────────────────────────────────
_PATTERNS = {
    # SSN/ITIN: 9xx prefixes are ITINs — sensitive taxpayer IDs, MASK THEM.
    # Only structurally-impossible prefixes (000, 666) are excluded.
    "SSN": re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "EIN": re.compile(r"\b\d{2}-\d{7}\b"),
    "PASSPORT": re.compile(r"\b(?:passport\s*(?:no\.?|number|#)?[:\s]*)([A-Z]?\d{8,9})\b", re.I),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE_US": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    "DOB": re.compile(r"\b(?:DOB|date of birth|born)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.I),
    "ROUTING_ABA": re.compile(r"\b(?:routing|ABA)\s*(?:no\.?|number|#)?[:\s]*(\d{9})\b", re.I),
    "ACCOUNT_NUMBER": re.compile(r"\b(?:account|acct)\s*(?:no\.?|number|#)?[:\s]*(\d{6,17})\b", re.I),
}
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_MASKS = {
    "SSN": "[SSN-MASKED]",
    "EIN": "[EIN-MASKED]",
    "PASSPORT": "[PASSPORT-MASKED]",
    "CREDIT_CARD": "[CARD-MASKED]",
    "IBAN": "[IBAN-MASKED]",
    "EMAIL": "[EMAIL-MASKED]",
    "PHONE_US": "[PHONE-MASKED]",
    "DOB": "[DOB-MASKED]",
    "ROUTING_ABA": "[ROUTING-MASKED]",
    "ACCOUNT_NUMBER": "[ACCOUNT-MASKED]",
    "NAME": "[NAME-MASKED]",
    "ADDRESS": "[ADDRESS-MASKED]",
}


def luhn_valid(number: str) -> bool:
    """Luhn checksum — distinguishes real card PANs from arbitrary digit runs."""
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if len(digits) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _mask_cards(text: str) -> Tuple[str, bool]:
    found = False

    def repl(m: re.Match) -> str:
        nonlocal found
        if luhn_valid(m.group(0)):
            found = True
            return _MASKS["CREDIT_CARD"]
        return m.group(0)  # not a valid PAN — leave reference numbers alone

    return _CARD_CANDIDATE.sub(repl, text), found


def _layer2(text: str, types_found: List[str]) -> Tuple[str, List[str]]:
    engine = os.getenv("PII_ENGINE", "").strip().lower()
    if not engine:
        return text, types_found
    try:
        if engine == "comprehend":
            import boto3

            client = boto3.client("comprehend")
            resp = client.detect_pii_entities(Text=text[:99_000], LanguageCode="en")
            # Replace back-to-front so offsets stay valid
            for ent in sorted(resp.get("Entities", []), key=lambda e: -e["BeginOffset"]):
                label = "NAME" if ent["Type"] == "NAME" else ("ADDRESS" if ent["Type"] == "ADDRESS" else None)
                if label and ent.get("Score", 0) >= 0.80:
                    text = text[: ent["BeginOffset"]] + _MASKS[label] + text[ent["EndOffset"]:]
                    if label not in types_found:
                        types_found.append(label)
        elif engine == "presidio":
            from presidio_analyzer import AnalyzerEngine

            analyzer = AnalyzerEngine()
            for res in sorted(analyzer.analyze(text=text, language="en"), key=lambda r: -r.start):
                label = "NAME" if res.entity_type == "PERSON" else ("ADDRESS" if res.entity_type == "LOCATION" else None)
                if label and res.score >= 0.80:
                    text = text[: res.start] + _MASKS[label] + text[res.end:]
                    if label not in types_found:
                        types_found.append(label)
    except Exception as exc:
        logger.warning("PII layer-2 engine '%s' unavailable (%s) — regex layer only", engine, type(exc).__name__)
    return text, types_found


def mask(text: str) -> Tuple[str, List[str]]:
    """Mask PII. Returns (masked_text, sorted PII type labels found)."""
    if not text:
        return "", []
    found: List[str] = []
    masked = text

    masked, card_found = _mask_cards(masked)
    if card_found:
        found.append("CREDIT_CARD")

    for label, pattern in _PATTERNS.items():
        if pattern.search(masked):
            found.append(label)
            masked = pattern.sub(_MASKS[label], masked)

    masked, found = _layer2(masked, found)
    return masked, sorted(set(found))


# ── Boundary enforcement middleware (Phase 1.4) ──────────────────────────────
# `mask()` only helps if it is actually called at every state-write boundary.
# These helpers make that a one-liner for structured records (audit entries,
# state snapshots, checkpoints) so raw PII cannot reach a durable sink simply
# because a developer forgot to mask an individual field. Wire
# `scrub_for_persistence()` into the audit/persistence layer so masking is the
# default path, not a discretionary call.

def mask_obj(obj):
    """
    Recursively mask PII in every string within a nested dict / list / tuple.

    Non-string scalars (int, float, bool, None) pass through unchanged. Dict
    KEYS are preserved (they are structural field names, not data); only VALUES
    are masked. Returns (masked_copy, sorted PII type labels found anywhere in
    the structure).
    """
    found: List[str] = []

    def _walk(o):
        if isinstance(o, str):
            m, f = mask(o)
            found.extend(f)
            return m
        if isinstance(o, dict):
            return {k: _walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_walk(v) for v in o]
        if isinstance(o, tuple):
            return tuple(_walk(v) for v in o)
        return o

    masked = _walk(obj)
    return masked, sorted(set(found))


def scrub_for_persistence(record):
    """
    Boundary helper: return a PII-masked deep copy of `record` that is safe to
    write to an audit log, checkpoint, or state store. Call this at EVERY
    state-write boundary (the Agent 09 preview leak is the canonical example of
    why intake-only masking is insufficient).
    """
    masked, _ = mask_obj(record)
    return masked
