from lambdas import intake, impact, gap_analysis, cco_notify, finalize


def _run(change):
    ev = {"change": change}
    ev = intake.handler(ev); ev = impact.handler(ev)
    if ev["impact"]["next"] == "GapAnalysis":
        ev = gap_analysis.handler(ev)
    return finalize.handler(ev)


def test_critical_change_drafts_gap_and_reviews():
    ev = _run({"change_id": "REG-1", "source_tier": "TIER_1", "days_to_effective": 20,
               "business_lines_count": 6, "products_count": 8, "mapped_policies_count": 4, "change_type": "FINAL_RULE"})
    assert ev["structured_output"]["tier"] == "CRITICAL"
    assert ev["structured_output"]["human_review_required"] is True
    assert ev["structured_output"]["gap_analysis_present"] is True


def test_low_change_finalizes():
    ev = _run({"change_id": "REG-2", "source_tier": "UNRECOGNIZED", "days_to_effective": 365, "change_type": "SPEECH"})
    assert ev["structured_output"]["tier"] == "LOW"
    assert ev["structured_output"]["human_review_required"] is False


def test_enforcement_action_reviews():
    ev = _run({"change_id": "REG-3", "source_tier": "TIER_3", "days_to_effective": 300, "change_type": "ENFORCEMENT_ACTION"})
    assert ev["structured_output"]["human_review_required"] is True


def test_gap_draft_sets_no_tier():
    out = gap_analysis.handler({"impact": {"tier": "HIGH"}})
    assert set(out["gap_analysis"]) == {"gap_text", "drafted_by"}
