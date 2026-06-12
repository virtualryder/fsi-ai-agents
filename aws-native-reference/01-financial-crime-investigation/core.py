"""
Deterministic core for the AWS-native Financial Crime Investigation (SAR) agent.

The "Python decides" layer — faithful to 01-financial-crime-investigation-agent's
weighting and thresholds, but with the composite risk score computed in
DETERMINISTIC Python (the original computes it via the LLM; here the model only
drafts the SAR narrative — an improvement that aligns with the suite thesis).

Weights (sum 100): sanctions 30 · network 25 · transactions 25 · adverse_media 15
· customer_profile 5. Thresholds: >70 → SAR · 30–70 → human review · <30 → close.
An OFAC/SDN sanctions match is a HARD override: it forces the SAR path and
mandatory BSA-Officer review regardless of the numeric score (zero-tolerance).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

RISK_WEIGHTS = {
    "sanctions": 30.0,
    "network": 25.0,
    "transactions": 25.0,
    "adverse_media": 15.0,
    "customer_profile": 5.0,
}
SAR_THRESHOLD = 70.0
REVIEW_THRESHOLD = 30.0


def compute_risk_score(factors: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    """
    Composite 0–100 AML risk score from per-dimension sub-scores in [0,1].
    Deterministic weighted sum. Returns (score, contribution_breakdown).
    """
    breakdown: Dict[str, float] = {}
    score = 0.0
    for dim, weight in RISK_WEIGHTS.items():
        sub = max(0.0, min(1.0, float(factors.get(dim, 0.0))))
        contribution = round(sub * weight, 2)
        breakdown[dim] = contribution
        score += contribution
    return round(score, 1), breakdown


def routing_decision(
    composite_score: float,
    ofac_hit: bool = False,
    pep_hit: bool = False,
) -> Dict[str, Any]:
    """
    Deterministic routing + HITL decision. No model output participates.

    OFAC/SDN match → hard override to the SAR path + mandatory review.
    Otherwise: >70 → generate_sar (+review); 30–70 → human_review; <30 → close.
    A PEP hit forces at least human review (never auto-close).
    """
    reasons: List[str] = []
    if ofac_hit:
        reasons.append("OFAC/SDN sanctions match — mandatory SAR consideration and BSA review (zero-tolerance)")
        decision = "generate_sar"
    elif composite_score > SAR_THRESHOLD:
        reasons.append(f"composite risk {composite_score:.0f} > {SAR_THRESHOLD:.0f} — SAR narrative drafted for review")
        decision = "generate_sar"
    elif composite_score >= REVIEW_THRESHOLD or pep_hit:
        if pep_hit:
            reasons.append("PEP match — escalated for human decision (never auto-closed)")
        else:
            reasons.append(f"composite risk {composite_score:.0f} in [{REVIEW_THRESHOLD:.0f},{SAR_THRESHOLD:.0f}] — human decision required")
        decision = "human_review_gate"
    else:
        reasons.append(f"composite risk {composite_score:.0f} < {REVIEW_THRESHOLD:.0f} — close with documented rationale")
        decision = "close_case"

    # SAR and escalate paths require a BSA Officer; auto-close does not.
    human_review_required = decision in ("generate_sar", "human_review_gate")
    return {
        "composite_score": composite_score,
        "ofac_hit": ofac_hit,
        "pep_hit": pep_hit,
        "decision": decision,
        "human_review_required": human_review_required,
        "reasons": reasons,
        # The Step Functions Choice state branches on this.
        "next": {
            "generate_sar": "GenerateSAR",
            "human_review_gate": "HumanReviewGate",
            "close_case": "CloseCase",
        }[decision],
    }


def screen_parties(parties: List[Dict[str, Any]], sanctions: Dict[str, Any],
                   peps: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic watchlist screening over customer + counterparties.
    `sanctions`/`peps` are name->record maps (the connector returns these in prod).
    Returns hits + ofac_hit/pep_hit booleans used by routing.
    """
    hits: List[Dict[str, Any]] = []
    ofac_hit = pep_hit = False
    for p in parties:
        key = (p.get("name") or "").strip().lower()
        if key in sanctions:
            hits.append({"party": p.get("name"), "type": "OFAC_SDN", **sanctions[key]})
            ofac_hit = True
        if key in peps:
            hits.append({"party": p.get("name"), "type": "PEP", **peps[key]})
            pep_hit = True
    return {"hits": hits, "ofac_hit": ofac_hit, "pep_hit": pep_hit}


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Mask PII before persist/transmit. Prefers platform middleware; local fallback."""
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
                    found.append("SSN")
                    return ssn.sub("[SSN-MASKED]", o)
                return o
            if isinstance(o, dict):
                return {k: _walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_walk(v) for v in o]
            return o
        return _walk(record), sorted(set(found))
