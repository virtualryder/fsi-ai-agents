"""
Deterministic core for the AWS-native Payments Compliance agent.

Faithful to 10-payments-compliance-agent: every compliance determination —
OFAC screening, Nacha return-code validation, Reg E assessment, the HITL
triggers, and auto-resolve — is deterministic Python. The LLM (Strands) only
drafts customer notices/narratives for reviewers. Immutable frozensets mirror
the agent's controls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Payment event types that ALWAYS require human review (immutable).
ALWAYS_HITL_PAYMENT_EVENTS = frozenset({
    "OFAC_HOLD", "UNAUTHORIZED_WIRE", "SAR_CANDIDATE", "CTR_THRESHOLD",
    "HIGH_RISK_COUNTRY_WIRE", "LATE_RETURN_DISPUTE",
})
# Nacha unauthorized return codes (consumer-protection significant).
UNAUTHORIZED_RETURN_CODES = frozenset({"R05", "R07", "R10", "R29"})
# OFAC-sanctioned country codes (ISO-3166-1 alpha-2 / SWIFT BIC prefix).
OFAC_SANCTIONED_COUNTRY_CODES = frozenset({"KP", "IR", "CU", "SY", "RU-DNR", "RU-LNR"})
# Auto-resolvable, low-risk administrative events.
AUTO_RESOLVE_EVENTS = frozenset({"NOC", "NOTIFICATION_OF_CHANGE", "ADMINISTRATIVE"})

HITL_AMOUNT_THRESHOLD = 50_000.00
CTR_THRESHOLD = 10_000.00


def screen(event: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic OFAC / Nacha / Reg E screening over a payment event."""
    country = (event.get("country") or "").upper()
    return_code = (event.get("return_code") or "").upper()
    amount = float(event.get("amount", 0.0))
    ofac_country_hit = country in OFAC_SANCTIONED_COUNTRY_CODES
    unauthorized_return = return_code in UNAUTHORIZED_RETURN_CODES
    reg_e_eligible = bool(event.get("consumer", False)) and unauthorized_return
    return {
        "ofac_country_hit": ofac_country_hit,
        "unauthorized_return": unauthorized_return,
        "reg_e_eligible": reg_e_eligible,
        "ctr_threshold_met": amount >= CTR_THRESHOLD,
        "amount": amount,
        "return_code": return_code,
    }


def routing_decision(event: Dict[str, Any], screening: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic routing + HITL triggers (no model output participates)."""
    event_type = (event.get("event_type") or "").upper()
    amount = float(screening.get("amount", 0.0))
    triggers: List[str] = []

    if event.get("ofac_hit") or screening.get("ofac_country_hit"):
        triggers.append("OFAC sanctions exposure — BSA Officer review + hold")
    if event_type in ALWAYS_HITL_PAYMENT_EVENTS:
        triggers.append(f"event type {event_type} always requires human review")
    if amount >= HITL_AMOUNT_THRESHOLD:
        triggers.append(f"amount ${amount:,.0f} >= ${HITL_AMOUNT_THRESHOLD:,.0f} threshold")
    if screening.get("unauthorized_return"):
        triggers.append(f"unauthorized Nacha return {screening.get('return_code')} — consumer protection")
    if event.get("sar_candidate"):
        triggers.append("SAR candidate flagged")
    if screening.get("ctr_threshold_met") and event_type == "CASH":
        triggers.append("CTR threshold met")

    human_review_required = bool(triggers)
    if human_review_required:
        nxt = "HumanReviewGate"
    elif event_type in AUTO_RESOLVE_EVENTS:
        nxt = "AutoResolve"
    else:
        nxt = "DraftNotice"
    return {
        "human_review_required": human_review_required,
        "triggers": triggers,
        "reg_e_eligible": screening.get("reg_e_eligible", False),
        "next": nxt,
    }


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    try:
        from fsi_agent_platform.pii import mask_obj
        return mask_obj(record)
    except Exception:
        import re
        ssn = re.compile(r"\b(?!000|666)\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
        acct = re.compile(r"\b(?:account|acct|routing|aba)\s*(?:no\.?|number|#)?[:\s]*\d{6,17}\b", re.I)
        found: List[str] = []

        def _walk(o):
            if isinstance(o, str):
                s = o
                if ssn.search(s):
                    found.append("SSN"); s = ssn.sub("[SSN-MASKED]", s)
                if acct.search(s):
                    found.append("ACCOUNT"); s = acct.sub("[ACCOUNT-MASKED]", s)
                return s
            if isinstance(o, dict):
                return {k: _walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_walk(v) for v in o]
            return o
        return _walk(record), sorted(set(found))
