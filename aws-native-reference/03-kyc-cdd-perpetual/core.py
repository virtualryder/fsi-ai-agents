"""
Deterministic core for the AWS-native KYC/CDD Perpetual Monitoring agent.

Faithful to 03-kyc-cdd-perpetual-agent: screening and risk rescoring are
deterministic Python. OFAC hit → forced ESCALATE (overrides all routing); PEP hit
→ mandatory EDD (FATF R.12). A Compliance Officer approves before any risk-rating
change. The LLM only drafts the EDD package / RM communication.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

TIER_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERY_HIGH": 3}


def screen(parties: List[Dict[str, Any]], sanctions: Dict[str, Any], peps: Dict[str, Any]) -> Dict[str, Any]:
    hits, ofac_hit, pep_hit = [], False, False
    for p in parties:
        k = (p.get("name") or "").strip().lower()
        if k in sanctions:
            hits.append({"party": p.get("name"), "type": "OFAC_SDN", **sanctions[k]}); ofac_hit = True
        if k in peps:
            hits.append({"party": p.get("name"), "type": "PEP", **peps[k]}); pep_hit = True
    return {"hits": hits, "ofac_hit": ofac_hit, "pep_hit": pep_hit}


def rescore(current_tier: str, risk_score: float, pep_hit: bool, ofac_hit: bool,
            edd_current: bool = True) -> Dict[str, Any]:
    """
    Deterministic risk rescoring → review outcome. No model output participates.

    Outcomes: ESCALATE · RISK_UPGRADE · EDD_REQUIRED · DOWNGRADE · REL_EXIT · PASS.
    """
    tier = current_tier if current_tier in TIER_ORDER else "MEDIUM"
    reasons: List[str] = []

    if ofac_hit:
        outcome = "ESCALATE"
        reasons.append("OFAC/SDN match — escalation overrides all other routing")
    elif risk_score >= 90:
        outcome = "REL_EXIT"
        reasons.append(f"risk score {risk_score:.0f} >= 90 — relationship-exit review")
    elif pep_hit and not edd_current:
        outcome = "EDD_REQUIRED"
        reasons.append("PEP match without current EDD — mandatory EDD (FATF R.12)")
    elif risk_score >= 80 and TIER_ORDER[tier] < TIER_ORDER["VERY_HIGH"]:
        outcome = "RISK_UPGRADE"
        reasons.append(f"risk score {risk_score:.0f} >= 80 — risk-tier upgrade")
    elif risk_score < 30 and TIER_ORDER[tier] > TIER_ORDER["LOW"]:
        outcome = "DOWNGRADE"
        reasons.append(f"risk score {risk_score:.0f} < 30 — risk-tier downgrade")
    else:
        outcome = "PASS"
        reasons.append("no risk-rating change required")

    # Any risk-rating change or escalation requires Compliance Officer review.
    human_review_required = outcome != "PASS"
    nxt = "ComplianceReviewGate" if human_review_required else "Finalize"
    return {
        "outcome": outcome, "risk_score": risk_score, "current_tier": tier,
        "pep_hit": pep_hit, "ofac_hit": ofac_hit,
        "human_review_required": human_review_required, "reasons": reasons,
        "edd_required": outcome == "EDD_REQUIRED" or (pep_hit and not edd_current),
        "next": nxt,
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
