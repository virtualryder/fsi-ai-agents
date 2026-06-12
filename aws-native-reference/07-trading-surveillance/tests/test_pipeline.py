from lambdas import intake, detect, score, draft_memo, compliance_notify, disposition, finalize


def _run(alert):
    ev = {"alert": alert}
    for fn in (intake.handler, detect.handler, score.handler):
        ev = fn(ev)
    if ev["scoring"]["next"] == "ComplianceReviewGate":
        ev = draft_memo.handler(ev)
    else:
        ev = disposition.handler(ev)
    return finalize.handler(ev)


def test_insider_reviews_with_sar_and_memo():
    ev = _run({"alert_id": "S1", "alert_type": "INSIDER_TRADING", "amount": 20000})
    assert ev["structured_output"]["tier"] == "CRITICAL"
    assert ev["structured_output"]["sar_required"] is True
    assert ev["structured_output"]["human_review_required"] is True
    assert ev["structured_output"]["memo_present"] is True


def test_low_alert_dispositions():
    ev = _run({"alert_id": "S2", "alert_type": "UNUSUAL_ACTIVITY", "amount": 100})
    assert ev["structured_output"]["human_review_required"] is False
    assert ev["structured_output"]["memo_present"] is False


def test_memo_sets_no_determination():
    out = draft_memo.handler({"scoring": {"alert_type": "INSIDER_TRADING", "tier": "CRITICAL", "sar_required": True}})
    assert set(out["memo"]) == {"memo_text", "drafted_by"}


def test_pii_masked_in_audit():
    ev = _run({"alert_id": "S3", "alert_type": "INSIDER_TRADING", "amount": 20000, "note": "SSN 123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
