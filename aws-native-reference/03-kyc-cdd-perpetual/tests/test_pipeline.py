from lambdas import screen, rescore, draft_edd, compliance_notify, finalize


def _run(cust):
    ev = {"customer": cust}
    ev = screen.handler(ev); ev = rescore.handler(ev)
    if ev["rescore"]["next"] == "ComplianceReviewGate":
        ev = draft_edd.handler(ev)
    return finalize.handler(ev)


def test_ofac_customer_routes_to_review_with_edd():
    ev = _run({"customer_id": "C1", "full_name": "Ivan Petrov", "risk_tier": "MEDIUM", "risk_score": 20,
               "parties": [{"name": "Ivan Petrov"}]})
    assert ev["structured_output"]["outcome"] == "ESCALATE"
    assert ev["structured_output"]["human_review_required"] is True
    assert ev["structured_output"]["edd_present"] is True


def test_clean_customer_passes():
    ev = _run({"customer_id": "C2", "full_name": "Jane Public", "risk_tier": "MEDIUM", "risk_score": 50,
               "parties": [{"name": "Jane Public"}]})
    assert ev["structured_output"]["outcome"] == "PASS"
    assert ev["structured_output"]["human_review_required"] is False


def test_edd_draft_sets_no_rating():
    out = draft_edd.handler({"rescore": {"outcome": "EDD_REQUIRED"}})
    assert set(out["edd"]) == {"edd_text", "drafted_by"}


def test_pii_masked_in_audit():
    ev = _run({"customer_id": "C3", "full_name": "Ivan Petrov", "risk_tier": "MEDIUM", "risk_score": 20,
               "parties": [{"name": "Ivan Petrov"}], "ssn": "123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
