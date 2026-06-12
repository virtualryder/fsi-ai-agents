from lambdas import intake, score, draft_reg_e, step_up, analyst_notify, allow, finalize


def _run(txn):
    ev = {"transaction": txn}
    ev = intake.handler(ev); ev = score.handler(ev)
    nxt = ev["decision"]["next"]
    ev = {"DraftRegE": draft_reg_e.handler, "StepUp": step_up.handler, "Allow": allow.handler}.get(
        nxt, lambda e: e)(ev)
    return finalize.handler(ev)


def test_fraud_ip_blocks_with_reg_e():
    ev = _run({"transaction_id": "T1", "ip": "203.0.113.66", "amount": 10})
    assert ev["structured_output"]["decision"] == "BLOCK"
    assert ev["structured_output"]["reg_e_disclosure_required"] is True
    assert ev["structured_output"]["notice_present"] is True


def test_clean_allows():
    ev = _run({"transaction_id": "T2", "amount": 20, "behavioral_score": 5})
    assert ev["structured_output"]["decision"] == "ALLOW"


def test_review_band_flags_human():
    ev = {"transaction": {"transaction_id": "T3", "behavioral_score": 40, "new_device": True, "cnp": True, "avs_match": False}}
    ev = intake.handler(ev); ev = score.handler(ev)
    assert ev["decision"]["human_review_required"] is True


def test_reg_e_draft_sets_no_decision():
    out = draft_reg_e.handler({"decision": {"decision": "BLOCK"}})
    assert set(out["notice"]) == {"notice_text", "drafted_by"}


def test_pan_masked_in_audit():
    ev = _run({"transaction_id": "T4", "amount": 20, "behavioral_score": 5, "pan": "4111 1111 1111 1111"})
    assert "4111 1111 1111 1111" not in str(ev["audit"])
