"""
Deterministic core for the AWS-native Real-Time Fraud Detection agent.

Faithful to 04-fraud-detection-agent: the authorization decision is deterministic
Python. Hard-block rules (RULE-009 known-fraud IP, RULE-010 OFAC-adjacent
merchant) force BLOCK regardless of score; otherwise a deterministic composite
(rule + behavioral, LLM EXCLUDED from routing) maps to BLOCK / STEP_UP /
ANALYST_REVIEW / ALLOW. The LLM only adds advisory analyst context off the hot
path. Reg E disclosure is auto-flagged for BLOCK.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

KNOWN_FRAUD_IPS = frozenset({"203.0.113.66", "tor-exit"})
OFAC_MERCHANTS = frozenset({"MERCH-SDN-001"})
RESTRICTED_MCC = frozenset({"7995", "6051"})  # gambling, crypto

BLOCK_THRESHOLD = 85.0
STEP_UP_THRESHOLD = 65.0
REVIEW_THRESHOLD = 40.0


def rule_engine(txn: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic rule pre-scoring + hard-block detection."""
    score = 0.0
    rules: List[str] = []
    hard_block = False

    ip = str(txn.get("ip", "")).lower()
    if ip in KNOWN_FRAUD_IPS:
        hard_block = True
        rules.append("RULE-009 known-fraud IP / Tor exit (hard block)")
    if str(txn.get("merchant_id", "")) in OFAC_MERCHANTS:
        hard_block = True
        rules.append("RULE-010 OFAC-adjacent merchant (hard block)")

    if txn.get("card_testing"):  # many small auths in a window
        score += 40; rules.append("card-testing velocity")
    if float(txn.get("amount", 0)) > float(txn.get("hourly_limit", 1e9)):
        score += 30; rules.append("hourly amount limit exceeded")
    if str(txn.get("mcc", "")) in RESTRICTED_MCC:
        score += 20; rules.append("restricted MCC")
    if txn.get("cnp") and not txn.get("avs_match", True):
        score += 25; rules.append("CNP + AVS mismatch")
    if txn.get("new_device"):
        score += 15; rules.append("new/unrecognized device")
    return {"rule_score": min(100.0, score), "rules": rules, "hard_block": hard_block}


def composite_score(rule_score: float, behavioral_score: float) -> float:
    """Deterministic composite (rule 60% + behavioral 40%). LLM excluded."""
    return round(rule_score * 0.6 + behavioral_score * 0.4, 1)


def decide(rule: Dict[str, Any], behavioral_score: float = 0.0) -> Dict[str, Any]:
    """Deterministic fraud decision. Hard block overrides score."""
    comp = composite_score(rule.get("rule_score", 0.0), behavioral_score)
    if rule.get("hard_block"):
        decision, reason = "BLOCK", "hard-block rule fired"
    elif comp >= BLOCK_THRESHOLD:
        decision, reason = "BLOCK", f"composite {comp:.0f} >= {BLOCK_THRESHOLD:.0f}"
    elif comp >= STEP_UP_THRESHOLD:
        decision, reason = "STEP_UP", f"composite {comp:.0f} in step-up band"
    elif comp >= REVIEW_THRESHOLD:
        decision, reason = "ANALYST_REVIEW", f"composite {comp:.0f} in review band"
    else:
        decision, reason = "ALLOW", f"composite {comp:.0f} below review band"

    reg_e_disclosure = decision == "BLOCK"          # provisional-credit / dispute rights
    human_review_required = decision == "ANALYST_REVIEW"
    nxt = {"BLOCK": "DraftRegE", "STEP_UP": "StepUp",
           "ANALYST_REVIEW": "AnalystReviewGate", "ALLOW": "Allow"}[decision]
    return {
        "decision": decision, "composite_score": comp, "reason": reason,
        "hard_block": rule.get("hard_block", False),
        "reg_e_disclosure_required": reg_e_disclosure,
        "human_review_required": human_review_required, "next": nxt,
    }


def mask_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    try:
        from fsi_agent_platform.pii import mask_obj
        return mask_obj(record)
    except Exception:
        import re
        card = re.compile(r"\b(?:\d[ -]?){13,19}\b")
        found: List[str] = []

        def luhn(s):
            ds = [int(c) for c in s if c.isdigit()]
            if len(ds) < 13:
                return False
            chk = 0; par = len(ds) % 2
            for i, d in enumerate(ds):
                if i % 2 == par:
                    d *= 2
                    if d > 9:
                        d -= 9
                chk += d
            return chk % 10 == 0

        def _walk(o):
            if isinstance(o, str):
                def rep(m):
                    if luhn(m.group(0)):
                        found.append("CREDIT_CARD"); return "[CARD-MASKED]"
                    return m.group(0)
                return card.sub(rep, o)
            if isinstance(o, dict):
                return {k: _walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_walk(v) for v in o]
            return o
        return _walk(record), sorted(set(found))
