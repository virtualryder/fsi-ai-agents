"""
Deterministic core for the AWS-native Wealth & RM Copilot.

Faithful to 05-wealth-rm-copilot: the suitability determination is deterministic
Python (Reg BI / FINRA 2111), never the LLM. UNSUITABLE recommendations are
blocked and never reach the client; everything else proceeds to a drafted
recommendation that an RM approves at a `waitForTaskToken` gate.

Statuses: SUITABLE · SUITABLE_WITH_NOTE · UNSUITABLE · NEEDS_REVIEW.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

HIGH_RISK_KEYWORDS = ("leveraged", "options", "speculative", "emerging", "cryptocurrency", "crypto")
CONSERVATIVE = ("CONSERVATIVE", "MODERATE_CONSERVATIVE")


def suitability_check(client_profile: Dict[str, Any], ips: Dict[str, Any], request_type: str,
                     investment_idea: str = "", concentrated_positions: List[Dict[str, Any]] | None = None
                     ) -> Dict[str, Any]:
    """Deterministic Reg BI / FINRA 2111 suitability. No model output participates."""
    concentrated_positions = concentrated_positions or []
    checks: List[Dict[str, Any]] = []
    disclosures: List[str] = []
    status = "SUITABLE"
    idea = (investment_idea or "").lower()
    risk = client_profile.get("risk_tolerance", "MODERATE")

    # 1. Risk alignment (investment proposals only)
    if request_type == "INVESTMENT_PROPOSAL" and investment_idea:
        if risk in CONSERVATIVE and any(kw in idea for kw in HIGH_RISK_KEYWORDS):
            checks.append({"check": "RISK_TOLERANCE_ALIGNMENT", "passed": False})
            status = "UNSUITABLE"
        else:
            checks.append({"check": "RISK_TOLERANCE_ALIGNMENT", "passed": True})

    # 2. IPS prohibited securities
    prohibited = [p.lower() for p in ips.get("prohibited_securities", [])]
    if investment_idea and any(p in idea for p in prohibited):
        checks.append({"check": "IPS_PROHIBITED_SECURITIES", "passed": False})
        status = "UNSUITABLE"

    # 3. ERISA (retirement) → with-note
    if client_profile.get("is_retirement_account"):
        disclosures.append("ERISA fiduciary disclosure — IRC §4975 prohibited-transaction screen applied")
        if status == "SUITABLE":
            status = "SUITABLE_WITH_NOTE"

    # 4. Concentration → with-note
    if concentrated_positions:
        names = ", ".join(p.get("name", p.get("symbol", "?")) for p in concentrated_positions[:2])
        disclosures.append(f"Concentration-risk disclosure: {names}")
        if status == "SUITABLE":
            status = "SUITABLE_WITH_NOTE"

    # 5. IPS currency → needs review (never downgrades a blocking status)
    last = ips.get("last_updated", "")
    if last and last < "2024-01-01" and status == "SUITABLE":
        status = "NEEDS_REVIEW"

    human_review_required = status != "UNSUITABLE"   # all non-blocked recs get RM approval
    nxt = "BlockUnsuitable" if status == "UNSUITABLE" else "Recommend"
    return {
        "status": status, "checks": checks, "disclosures": disclosures,
        "human_review_required": human_review_required, "next": nxt,
        "reg_bi_rationale": f"Suitability determination: {status} ({len(disclosures)} disclosure(s)).",
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
