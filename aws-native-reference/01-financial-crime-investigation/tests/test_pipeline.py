"""End-to-end Lambda chain (demo) — proves the deterministic SAR gate."""
from lambdas import screen, score, route, generate_sar, close_case, finalize


def _run(case):
    ev = {"case": case}
    ev = screen.handler(ev); ev = score.handler(ev); ev = route.handler(ev)
    if ev["routing"]["next"] == "GenerateSAR":
        ev = generate_sar.handler(ev)
    elif ev["routing"]["next"] == "CloseCase":
        ev = close_case.handler(ev)
    return finalize.handler(ev)


def test_ofac_case_routes_to_sar():
    ev = _run({"case_id": "FC-1", "customer_name": "Ivan Petrov", "account_last4": "4471",
               "alert_type": "STRUCTURING", "parties": [{"name": "Ivan Petrov"}],
               "factors": {"network": 0.3, "transactions": 0.4, "adverse_media": 0.2, "customer_profile": 0.3}})
    assert ev["structured_output"]["decision"] == "generate_sar"
    assert ev["structured_output"]["sar_present"] is True
    assert ev["structured_output"]["human_review_required"] is True


def test_clean_case_closes():
    ev = _run({"case_id": "FC-2", "customer_name": "Jane Public", "account_last4": "0001",
               "alert_type": "CASH", "parties": [{"name": "Jane Public"}],
               "factors": {"network": 0.05, "transactions": 0.1, "adverse_media": 0.0, "customer_profile": 0.1}})
    assert ev["structured_output"]["decision"] == "close_case"
    assert ev["structured_output"]["sar_present"] is False


def test_no_raw_pii_in_finalized_audit():
    ev = _run({"case_id": "FC-3", "customer_name": "Ivan Petrov", "account_last4": "9", "alert_type": "X",
               "parties": [{"name": "Ivan Petrov"}], "factors": {}, "ssn_note": "SSN 987-65-4321"})
    assert "987-65-4321" not in str(ev["audit"])


def test_sar_drafting_sets_no_routing():
    from lambdas import generate_sar as gs
    out = gs.handler({"case": {"customer_name": "X"}, "composite_score": 80, "screening": {}})
    assert set(out["sar"]) == {"narrative", "drafted_by"}
