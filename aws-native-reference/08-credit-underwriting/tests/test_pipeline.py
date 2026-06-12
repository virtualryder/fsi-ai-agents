"""End-to-end Lambda chain (demo)."""
from lambdas import (verify, evaluate, fair_lending, route, generate_adverse_action,
                     auto_approve, finalize)


def _run(app):
    ev = {"application": app}
    for fn in (verify.handler, evaluate.handler, fair_lending.handler, route.handler):
        ev = fn(ev)
    nxt = ev["routing"]["next"]
    if nxt == "GenerateAdverseAction":
        ev = generate_adverse_action.handler(ev)
    elif nxt == "AutoApprove":
        ev = auto_approve.handler(ev)
    return finalize.handler(ev)


def test_strong_approves():
    ev = _run({"application_id": "A1", "credit_score": 780, "total_dti_ratio": 0.30, "ltv_ratio": 0.70,
               "income_verified": True, "reserves_months": 6})
    assert ev["structured_output"]["decision"] == "APPROVE"


def test_decline_has_codes_and_notice():
    ev = _run({"application_id": "A2", "credit_score": 600, "total_dti_ratio": 0.30, "ltv_ratio": 0.80})
    assert ev["structured_output"]["decision"] == "DECLINE"
    assert ev["structured_output"]["adverse_action_reasons"]
    assert ev["structured_output"]["notice_present"] is True


def test_adverse_action_letter_has_no_prohibited_language():
    ev = _run({"application_id": "A3", "credit_score": 600, "total_dti_ratio": 0.30, "ltv_ratio": 0.80})
    assert ev["notice"]["prohibited_language_clean"] is True


def test_draft_sets_no_decision():
    from lambdas import generate_adverse_action as g
    out = g.handler({"evaluation": {"decision": "DECLINE", "adverse_action_reasons": ["DTI_TOO_HIGH"]}})
    assert set(out["notice"]) == {"letter_text", "drafted_by", "prohibited_language_clean"}


def test_pii_masked_in_audit():
    ev = _run({"application_id": "A4", "credit_score": 600, "total_dti_ratio": 0.3, "ltv_ratio": 0.8,
               "ssn": "123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
