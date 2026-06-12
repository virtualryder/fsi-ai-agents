from lambdas import inventory, assess, narrative, mro_notify, finalize


def _run(model):
    ev = {"model": model}
    ev = inventory.handler(ev); ev = assess.handler(ev)
    if ev["validation"]["next"] == "ModelRiskReviewGate":
        ev = narrative.handler(ev)
    return finalize.handler(ev)


def test_psi_critical_reviews_with_narrative():
    ev = _run({"model_id": "M1", "risk_tier": "HIGH", "validation_type": "ANNUAL",
               "current_dist": {"a": 85, "b": 15}, "baseline_dist": {"a": 50, "b": 50}})
    assert ev["structured_output"]["psi_class"] == "CRITICAL"
    assert ev["structured_output"]["human_review_required"] is True
    assert ev["structured_output"]["narrative_present"] is True


def test_stable_model_finalizes():
    ev = _run({"model_id": "M2", "risk_tier": "LOW", "validation_type": "ANNUAL",
               "current_dist": {"a": 50}, "baseline_dist": {"a": 50}})
    assert ev["structured_output"]["human_review_required"] is False


def test_narrative_sets_no_outcome():
    out = narrative.handler({"validation": {"model_id": "M", "psi": 0.3, "psi_class": "CRITICAL",
                                            "risk_tier": "HIGH", "degradation_flags": [], "reviewer": "MODEL_RISK_OFFICER"}})
    assert set(out["narrative"]) == {"narrative_text", "drafted_by"}
