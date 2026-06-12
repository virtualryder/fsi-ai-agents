from lambdas import intake, assess, supervisor_notify, draft_letter, finalize


def _run(acct):
    ev = {"account": acct}
    ev = intake.handler(ev); ev = assess.handler(ev)
    if ev["assessment"]["next"] == "DraftLetter":
        ev = draft_letter.handler(ev)
    return finalize.handler(ev)


def test_scra_account_routes_to_review():
    ev = _run({"account_id": "A1", "scra_active_duty": True})
    assert ev["structured_output"]["human_review_required"] is True
    assert ev["structured_output"]["scra_rate_cap"] == 6.0
    assert ev["structured_output"]["letter_present"] is False


def test_clean_account_drafts_letter_with_disclosures():
    ev = _run({"account_id": "A2", "consumer_timezone": "America/New_York"})
    assert ev["structured_output"]["human_review_required"] is False
    assert ev["structured_output"]["letter_present"] is True
    assert "Mini-Miranda" in ev["letter"]["letter_text"]


def test_disclosures_are_python_injected_not_model():
    ev = _run({"account_id": "A3", "consumer_timezone": "America/New_York"})
    assert ev["letter"]["disclosures_injected"]
    assert "Mini-Miranda" not in ev["letter"]["body"]   # the model body excludes disclosures


def test_pii_masked_in_audit():
    ev = _run({"account_id": "A4", "consumer_timezone": "America/New_York", "ssn": "123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
