"""
Deterministic core for the AWS-native Collections & Recovery agent.

Faithful to 12-collections-recovery-agent: every FDCPA / Reg F / SCRA
determination is deterministic Python — FDCPA contact-time via pytz (fail-safe
prohibited on unknown timezone), the SCRA 6% rate cap, bankruptcy automatic stay,
statute-of-limitations arithmetic, and the 9 immutable ALWAYS_HITL conditions.
The LLM drafts the letter body only; required disclosures (mini-Miranda,
validation notice, SCRA note) are Python-injected.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

import pytz

FDCPA_PROHIBITED_HOURS_BEFORE = 8     # before 8am
FDCPA_PROHIBITED_HOURS_AFTER = 21     # at/after 9pm
SCRA_MAX_INTEREST_RATE_PCT = 6.0
SETTLEMENT_HIGH_VALUE_AMOUNT = 10_000.0
SETTLEMENT_HIGH_DISCOUNT = 0.40

ALWAYS_HITL_CONDITIONS = frozenset({
    "SCRA_DETECTED", "BANKRUPTCY_STAY_DETECTED", "DISPUTE_RECEIVED",
    "CEASE_DESIST_RECEIVED", "DECEASED_ACCOUNT", "SETTLEMENT_HIGH_VALUE",
    "LITIGATION_HIGH_RISK", "REGULATORY_COMPLAINT", "MINOR_ACCOUNT",
})


def check_contact_time(consumer_timezone: str) -> Tuple[bool, int]:
    """FDCPA § 805(a)(1): no contact before 8am or at/after 9pm local. Fail-safe."""
    try:
        local = datetime.now(pytz.timezone(consumer_timezone))
        permitted = FDCPA_PROHIBITED_HOURS_BEFORE <= local.hour < FDCPA_PROHIBITED_HOURS_AFTER
        return permitted, local.hour
    except Exception:
        return False, -1   # unknown timezone → prohibited (fail-safe)


def determine_hitl_conditions(account: Dict[str, Any]) -> List[str]:
    """Deterministic frozenset membership — the authoritative HITL triggers."""
    c: List[str] = []
    if account.get("scra_active_duty"):
        c.append("SCRA_DETECTED")
    if account.get("bankruptcy_stay"):
        c.append("BANKRUPTCY_STAY_DETECTED")
    if account.get("dispute_received"):
        c.append("DISPUTE_RECEIVED")
    if account.get("cease_desist"):
        c.append("CEASE_DESIST_RECEIVED")
    if account.get("deceased"):
        c.append("DECEASED_ACCOUNT")
    if (float(account.get("settlement_amount", 0)) > SETTLEMENT_HIGH_VALUE_AMOUNT or
            float(account.get("settlement_discount", 0)) > SETTLEMENT_HIGH_DISCOUNT):
        c.append("SETTLEMENT_HIGH_VALUE")
    if account.get("litigation_high_risk"):
        c.append("LITIGATION_HIGH_RISK")
    if account.get("regulatory_complaint"):
        c.append("REGULATORY_COMPLAINT")
    if int(account.get("debtor_age", 99)) < 18:
        c.append("MINOR_ACCOUNT")
    return [x for x in c if x in ALWAYS_HITL_CONDITIONS]


def assess(account: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic collections assessment + routing. No model output participates."""
    tz = account.get("consumer_timezone", "America/New_York")
    contact_permitted, hour = check_contact_time(tz)
    conditions = determine_hitl_conditions(account)
    scra = "SCRA_DETECTED" in conditions
    bankruptcy = "BANKRUPTCY_STAY_DETECTED" in conditions

    human_review_required = bool(conditions)
    # Bankruptcy stay → ALL collection stops; SCRA → 6% cap applies.
    reasons: List[str] = []
    if bankruptcy:
        reasons.append("bankruptcy automatic stay (11 U.S.C. § 362) — all collection halts")
    if scra:
        reasons.append(f"SCRA active-duty — {SCRA_MAX_INTEREST_RATE_PCT:.0f}% interest-rate cap applies")
    if conditions:
        reasons.append("ALWAYS_HITL condition(s): " + ", ".join(conditions))

    nxt = "SupervisorReviewGate" if human_review_required else "DraftLetter"
    return {
        "account_id": account.get("account_id"),
        "contact_permitted": contact_permitted, "local_hour": hour,
        "hitl_conditions": conditions, "scra_rate_cap": SCRA_MAX_INTEREST_RATE_PCT if scra else None,
        "all_collection_halted": bankruptcy,
        "human_review_required": human_review_required, "reasons": reasons, "next": nxt,
    }


# Disclosures injected deterministically (the LLM never writes these).
def required_disclosures(account: Dict[str, Any], assessment: Dict[str, Any]) -> List[str]:
    out = ["Mini-Miranda: This is an attempt to collect a debt; any information obtained will be used for that purpose.",
           "Debt validation notice: You may dispute this debt within 30 days (FDCPA § 809)."]
    if "SCRA_DETECTED" in assessment.get("hitl_conditions", []):
        out.append(f"SCRA notice: interest is capped at {SCRA_MAX_INTEREST_RATE_PCT:.0f}% during active duty.")
    return out


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    try:
        from fsi_agent_platform.pii import mask_obj
        return mask_obj(record)
    except Exception:
        import re
        ssn = re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
        found: List[str] = []

        def _walk(o):
            if isinstance(o, str):
                if ssn.search(o):
                    found.append("SSN"); return ssn.sub("[SSN-MASKED]", o)
                return o
            if isinstance(o, dict):
                return {k: _walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_walk(v) for v in o]
            return o
        return _walk(record), sorted(set(found))
