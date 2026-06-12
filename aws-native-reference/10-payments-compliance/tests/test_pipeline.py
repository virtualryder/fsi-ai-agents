"""End-to-end Lambda chain (demo)."""
from lambdas import intake, screen, route, hitl_notify, auto_resolve, draft_notice, finalize


def _run(pe):
    ev = {"payment_event": pe}
    for fn in (intake.handler, screen.handler, route.handler):
        ev = fn(ev)
    nxt = ev["routing"]["next"]
    if nxt == "AutoResolve":
        ev = auto_resolve.handler(ev)
    elif nxt == "DraftNotice":
        ev = draft_notice.handler(ev)
    return finalize.handler(ev)


def test_unauthorized_return_routes_to_review():
    ev = _run({"payment_id": "P1", "event_type": "ACH_RETURN", "return_code": "R10", "consumer": True, "amount": 1200})
    assert ev["structured_output"]["human_review_required"] is True


def test_noc_auto_resolves():
    ev = _run({"payment_id": "P2", "event_type": "NOC", "amount": 0})
    assert ev["structured_output"]["disposition"] == "AUTO_RESOLVED"


def test_normal_dispute_drafts_reg_e_notice():
    ev = _run({"payment_id": "P3", "event_type": "ACH_DISPUTE", "return_code": "R01", "amount": 200, "consumer": True})
    assert ev["structured_output"]["notice_present"] is True


def test_draft_sets_no_determination():
    from lambdas import draft_notice as d
    out = d.handler({"routing": {"reg_e_eligible": True}, "screening": {"return_code": "R10"}})
    assert set(out["notice"]) == {"notice_text", "drafted_by"}


def test_pii_masked_in_audit():
    ev = _run({"payment_id": "P4", "event_type": "ACH_DISPUTE", "return_code": "R01", "amount": 10,
               "memo": "SSN 123-45-6789"})
    assert "123-45-6789" not in str(ev["audit"])
