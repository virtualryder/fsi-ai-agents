"""End-to-end Lambda chain (demo) — proves the deterministic suppression gate."""
from lambdas import ingest, justify, route, record_disposition, escalate, finalize


def _run(alert):
    ev = {"alert": alert}
    for fn in (ingest.handler, justify.handler, route.handler):
        ev = fn(ev)
    nxt = ev["routing"]["next"]
    if nxt == "RecordDisposition":
        ev = record_disposition.handler(ev)
    elif nxt == "Escalate":
        ev = escalate.handler(ev)
    return finalize.handler(ev)


def test_high_deterministic_suppresses():
    ev = _run({"alert_id": "A1", "alert_type": "VELOCITY", "rule_score": 90, "historical_score": 88, "features": {}})
    assert ev["structured_output"]["decision"] == "SUPPRESS"
    assert ev["structured_output"]["human_review_required"] is True


def test_llm_cannot_suppress_alone():
    # advisory LLM fp is high (demo=70) but deterministic is low -> not suppressed
    ev = _run({"alert_id": "A2", "alert_type": "WIRE", "rule_score": 45, "historical_score": 45, "features": {}})
    assert ev["structured_output"]["decision"] != "SUPPRESS"


def test_pep_escalates():
    ev = _run({"alert_id": "A3", "rule_score": 95, "historical_score": 95, "features": {"pep_flag": True}})
    assert ev["structured_output"]["decision"] == "ESCALATE"
    assert ev["escalated_to"] == "01-financial-crime-investigation"


def test_justify_sets_no_routing():
    from lambdas import justify as j
    out = j.handler({"alert": {"alert_type": "X"}})
    assert set(out["justification"]) == {"advisory_fp_probability", "narrative", "drafted_by"}


def test_pii_masked_in_audit():
    ev = _run({"alert_id": "A4", "rule_score": 90, "historical_score": 90, "features": {}, "note": "SSN 123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
