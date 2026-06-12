from lambdas import intake, suitability, block_unsuitable, recommend, rm_notify, finalize


def _run(req):
    ev = {"request": req}
    ev = intake.handler(ev); ev = suitability.handler(ev)
    if ev["suitability"]["next"] == "BlockUnsuitable":
        ev = block_unsuitable.handler(ev)
    else:
        ev = recommend.handler(ev)
    return finalize.handler(ev)


def test_unsuitable_is_blocked():
    ev = _run({"request_id": "R1", "request_type": "INVESTMENT_PROPOSAL", "investment_idea": "3x leveraged ETF",
               "client_profile": {"risk_tolerance": "CONSERVATIVE"}, "ips_summary": {}})
    assert ev["structured_output"]["suitability_status"] == "UNSUITABLE"
    assert ev["structured_output"]["blocked"] is True
    assert ev["structured_output"]["recommendation_present"] is False


def test_suitable_drafts_recommendation():
    ev = _run({"request_id": "R2", "request_type": "INVESTMENT_PROPOSAL", "investment_idea": "index fund",
               "client_profile": {"risk_tolerance": "MODERATE"}, "ips_summary": {"last_updated": "2025-01-01"}})
    assert ev["structured_output"]["suitability_status"] == "SUITABLE"
    assert ev["structured_output"]["recommendation_present"] is True


def test_recommend_draft_sets_no_status():
    out = recommend.handler({"suitability": {"status": "SUITABLE", "disclosures": []}})
    assert set(out["recommendation"]) == {"draft_text", "drafted_by"}


def test_pii_masked_in_audit():
    ev = _run({"request_id": "R3", "request_type": "MEETING_PREP", "client_profile": {"risk_tolerance": "MODERATE"},
               "ips_summary": {"last_updated": "2025-01-01"}, "ssn": "123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
