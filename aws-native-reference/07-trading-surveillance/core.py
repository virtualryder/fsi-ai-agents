"""
Deterministic core for the AWS-native Trading Surveillance agent.

Faithful to 07-trading-surveillance-agent: pattern detection, severity scoring,
the SAR determination, and the always-HITL overrides are deterministic Python.
The LLM only drafts the disposition memo / SAR narrative — and (per the agent's
prompt) can never disclose a SAR to the subject (no tipping off, 31 U.S.C.
§ 5318(g)(2)).

ALWAYS_HITL alert types (immutable) → CRITICAL + mandatory compliance review:
INSIDER_TRADING, INFORMATION_BARRIER_BREACH, CROSS_MARKET_MANIPULATION.
SAR determination: amount >= $5,000 AND suspicious (Python rule, not LLM).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

ALWAYS_HITL_ALERT_TYPES = frozenset({
    "INSIDER_TRADING", "INFORMATION_BARRIER_BREACH", "CROSS_MARKET_MANIPULATION",
})

BASE_SEVERITY = {
    "INSIDER_TRADING": 0.95, "CROSS_MARKET_MANIPULATION": 0.88, "INFORMATION_BARRIER_BREACH": 0.85,
    "FRONT_RUNNING": 0.80, "LAYERING_SPOOFING": 0.78, "MARKING_THE_CLOSE": 0.70,
    "WASH_TRADING": 0.70, "BEST_EXECUTION_FAILURE": 0.55, "EXCESSIVE_TRADING": 0.50,
    "SHORT_SELLING_VIOLATION": 0.65, "UNUSUAL_ACTIVITY": 0.45,
}

SAR_AMOUNT_THRESHOLD = 5_000.0
CRITICAL_T, HIGH_T, MEDIUM_T = 0.85, 0.65, 0.40


def detect(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic pattern signals + Reg SHO check."""
    signals: List[str] = []
    raw = alert.get("raw", alert)
    if raw.get("cancel_rate", 0) >= 0.8:
        signals.append("HIGH_CANCEL_RATE (layering/spoofing indicator)")
    if raw.get("short_exempt") is False and raw.get("locate_obtained") is False:
        signals.append("REG_SHO_NO_LOCATE (Rule 203 locate failure)")
    if raw.get("pre_announcement_trade"):
        signals.append("PRE_ANNOUNCEMENT_TRADING (insider indicator)")
    if raw.get("crossed_information_barrier"):
        signals.append("INFO_BARRIER_CROSSED")
    reg_sho_violation = raw.get("short_exempt") is False and raw.get("locate_obtained") is False
    return {"signals": signals, "reg_sho_violation": reg_sho_violation}


def score_and_route(alert: Dict[str, Any], detection: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic severity tier + SAR determination + routing. No model output."""
    alert_type = (alert.get("alert_type") or "UNUSUAL_ACTIVITY").upper()
    base = BASE_SEVERITY.get(alert_type, 0.45)
    # Each detected signal nudges severity up (deterministic, capped).
    severity = min(1.0, base + 0.03 * len(detection.get("signals", [])))

    if alert_type in ALWAYS_HITL_ALERT_TYPES:
        tier = "CRITICAL"
    elif severity >= CRITICAL_T:
        tier = "CRITICAL"
    elif severity >= HIGH_T:
        tier = "HIGH"
    elif severity >= MEDIUM_T:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    amount = float(alert.get("amount", 0.0))
    suspicious = tier in ("CRITICAL", "HIGH") or alert_type in ALWAYS_HITL_ALERT_TYPES
    sar_required = amount >= SAR_AMOUNT_THRESHOLD and suspicious

    human_review_required = alert_type in ALWAYS_HITL_ALERT_TYPES or tier in ("CRITICAL", "HIGH")
    nxt = "ComplianceReviewGate" if human_review_required else "Disposition"
    reasons: List[str] = []
    if alert_type in ALWAYS_HITL_ALERT_TYPES:
        reasons.append(f"{alert_type} — always CRITICAL + mandatory compliance review")
    if detection.get("reg_sho_violation"):
        reasons.append("Reg SHO Rule 203 locate failure")
    if sar_required:
        reasons.append("SAR determination: amount >= $5,000 AND suspicious")
    return {
        "alert_type": alert_type, "severity": round(severity, 3), "tier": tier,
        "sar_required": sar_required, "reg_sho_violation": detection.get("reg_sho_violation", False),
        "human_review_required": human_review_required, "reasons": reasons, "next": nxt,
    }


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
