"""
Grounding verification — Rec 6.

An examiner-facing narrative (SAR, adverse-action letter, dispute analysis)
must contain ONLY claims traceable to the case state that produced it. LLM
hallucination in a SAR narrative is a regulatory filing defect, not a
quality nit. This module gives every agent a deterministic, CI-runnable
grounding check:

    report = verify_grounding(narrative, state)
    report.ungrounded_numbers   -> numeric claims absent from state
    report.ungrounded_entities  -> capitalized entities absent from state
    report.grounded             -> True when both lists are empty

Method (deliberately conservative — flags for human review, never blocks):
  * NUMBERS: every monetary amount / bare number in the narrative is
    normalized (commas, $, %, decimals) and searched against the set of
    numbers appearing anywhere in the state tree (values AND inside
    strings). Day/date components and tiny integers (<= 12, e.g. "three
    transactions" written as 3) are exempt to avoid noise.
  * ENTITIES: capitalized multi-word spans (names, banks, locations) are
    matched case-insensitively against the state text corpus. Common
    narrative boilerplate (regulator names, month names, doc-type words)
    is allow-listed.

Wire-in: agents call this in their narrative node and attach the report to
the audit trail; HITL reviewers see the ungrounded list next to the draft.
The eval harness (governance/evals) runs the same check over golden cases.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

# Boilerplate every FinCEN/Reg-B narrative legitimately contains without
# those strings appearing in case state.
_ENTITY_ALLOWLIST = {
    "FinCEN", "SAR", "BSA", "AML", "OFAC", "USA PATRIOT Act", "Bank Secrecy Act",
    "Suspicious Activity Report", "CTR", "United States", "U.S.", "US",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "ECOA", "Regulation B", "FCRA", "Equal Credit Opportunity Act",
    "ACH", "Fedwire", "SWIFT", "IBAN", "Nacha", "The", "This", "These", "Per",
}

# Statutory thresholds a compliant narrative cites without them being case data:
# $10,000 CTR (31 CFR 1010.311), $5,000 SAR (1020.320), $3,000 funds-transfer
# recordkeeping (1010.410(e)). Keep this list SHORT — it is an allowlist of law,
# not a dumping ground for false positives.
_NUMBER_ALLOWLIST = {"10000", "5000", "3000"}

_NUMBER_RE = re.compile(r"\$?\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\$?\b\d+(?:\.\d+)?%?\b")
_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-zA-Z&'-]+(?:\s+[A-Z][a-zA-Z&'-]+)+)\b")


@dataclass
class GroundingReport:
    ungrounded_numbers: List[str] = field(default_factory=list)
    ungrounded_entities: List[str] = field(default_factory=list)
    checked_numbers: int = 0
    checked_entities: int = 0

    @property
    def grounded(self) -> bool:
        return not self.ungrounded_numbers and not self.ungrounded_entities

    def to_audit_dict(self) -> Dict[str, Any]:
        return {
            "grounded": self.grounded,
            "ungrounded_numbers": self.ungrounded_numbers,
            "ungrounded_entities": self.ungrounded_entities,
            "checked_numbers": self.checked_numbers,
            "checked_entities": self.checked_entities,
        }


def _normalize_number(tok: str) -> str:
    return tok.replace("$", "").replace(",", "").replace("%", "").rstrip(".")


def _state_number_corpus(state: Dict[str, Any]) -> Set[str]:
    """Every number reachable in the state tree, normalized, with float/int aliases."""
    blob = json.dumps(state, default=str)
    nums: Set[str] = set()
    for tok in _NUMBER_RE.findall(blob):
        n = _normalize_number(tok)
        nums.add(n)
        try:
            f = float(n)
            nums.add(f"{f:g}")          # 45000.0 ↔ 45000
            if f == int(f):
                nums.add(str(int(f)))
        except ValueError:
            pass
    return nums


def verify_grounding(narrative: str, state: Dict[str, Any]) -> GroundingReport:
    report = GroundingReport()
    if not narrative:
        return report

    state_numbers = _state_number_corpus(state)
    state_text = json.dumps(state, default=str).lower()

    for tok in _NUMBER_RE.findall(narrative):
        n = _normalize_number(tok)
        try:
            value = float(n)
        except ValueError:
            continue
        if value <= 12:  # counts, list ordinals, day-of-month noise
            continue
        if n in _NUMBER_ALLOWLIST or f"{value:g}" in _NUMBER_ALLOWLIST:
            continue
        report.checked_numbers += 1
        aliases = {n, f"{value:g}"}
        if value == int(value):
            aliases.add(str(int(value)))
        if not aliases & state_numbers:
            report.ungrounded_numbers.append(tok)

    leading_stop = {"Between", "On", "In", "At", "During", "After", "Before",
                    "Within", "The", "This", "These", "Per", "From", "By", "Under", "Each"}
    for ent in set(_ENTITY_RE.findall(narrative)):
        words = ent.split()
        while words and words[0] in leading_stop:
            words = words[1:]
        if len(words) < 2:
            continue
        ent = " ".join(words)
        if ent in _ENTITY_ALLOWLIST or any(ent.startswith(a + " ") for a in _ENTITY_ALLOWLIST):
            continue
        report.checked_entities += 1
        if ent.lower() not in state_text:
            report.ungrounded_entities.append(ent)

    report.ungrounded_numbers.sort()
    report.ungrounded_entities.sort()
    return report
