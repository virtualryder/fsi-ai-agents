"""End-to-end Lambda chain (demo mode) — proves the deterministic gate holds."""
from lambdas import pii_mask, extract, validate, route, finalize


def _run(text, doc_id="D-1"):
    ev = {"document": {"doc_id": doc_id, "text": text}}
    for fn in (pii_mask.handler, extract.handler, validate.handler, route.handler, finalize.handler):
        ev = fn(ev)
    return ev


def test_clean_loan_app_without_pii_auto_routes():
    ev = _run("FORM 1003 Uniform Residential Loan Application borrower loan_amount 250000")
    assert ev["extraction"]["document_type"] == "loan_application_1003"
    assert ev["routing"]["human_review_required"] is False
    assert ev["status"] == "COMPLETE"


def test_pii_forces_human_review():
    ev = _run("FORM 1003 Uniform Residential Loan Application. SSN 123-45-6789")
    assert ev["pii_types"] == ["SSN"]
    assert ev["routing"]["human_review_required"] is True


def test_sar_form_always_human_review():
    ev = _run("FinCEN SAR suspicious activity report")
    assert ev["extraction"]["document_type"] == "sar_form"
    assert ev["routing"]["human_review_required"] is True


def test_no_raw_pii_in_finalized_audit():
    ev = _run("driver license. SSN 987-65-4321")
    assert "987-65-4321" not in str(ev["audit"])


def test_llm_layer_sets_no_routing_fields():
    """The extraction (LLM) output must not contain routing/HITL decisions."""
    from lambdas import extract as ex
    out = ex.handler({"masked_text": "FinCEN SAR suspicious activity report"})
    assert set(out["extraction"]) <= {"document_type", "fields", "confidence", "field_confidences"}
    assert "human_review_required" not in out["extraction"]
    assert "target_agents" not in out["extraction"]
