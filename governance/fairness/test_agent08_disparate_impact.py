"""
Fair-lending / disparate-impact testing — Rec 6 (ECOA / Regulation B).

The CFPB enforcement asymmetry the field guide sells against ($50K model
finding vs $5M-$50M enforcement action) cuts both ways: shipping a credit
model WITHOUT disparate-impact testing is itself the finding. This module
provides the two tests a fair-lending reviewer asks for first, runnable in
CI because Agent 08's scoring is deterministic Python:

1. MATCHED-PAIR BLINDNESS. Two applications identical in every underwriting
   factor but differing in protected-class-correlated attributes (applicant
   name, census tract, ZIP) must receive IDENTICAL risk scores and tiers.
   The flagged-census-tract mechanism may add fair-lending REVIEW (that is
   its purpose) — it must never move the score or the credit decision.

2. ADVERSE IMPACT RATIO (four-fifths rule). `compute_adverse_impact_ratio`
   runs a synthetic portfolio through the scorer grouped by a protected-
   class proxy and computes selection-rate ratios. The synthetic fixture in
   this file is constructed identical-by-design, so the suite asserts the
   harness reports AIR == 1.0 — proving the pipeline contains no group-
   sensitive pathway. At a customer engagement the same harness runs on the
   institution's historical applications with real demographic codings
   (HMDA GMI), where AIR < 0.80 is the regulatory presumption threshold.

Limitation (stated honestly): these tests prove the DETERMINISTIC scorer is
blind. The LLM narrative layer is exercised separately (governance/evals
adverse-action checks) because reason-statement quality on protected-class
correlates is a model-behavior property, not a code property.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT08 = REPO_ROOT / "08-credit-underwriting-agent"


@pytest.fixture(scope="module")
def a08():
    sys.path.insert(0, str(AGENT08))
    for mod in [m for m in list(sys.modules) if m.startswith("agent")]:
        del sys.modules[mod]
    import agent.nodes as nodes_mod
    yield nodes_mod
    sys.path.remove(str(AGENT08))
    for mod in [m for m in list(sys.modules) if m.startswith("agent")]:
        del sys.modules[mod]


BASE_APPLICATION = {
    "application_id": "FAIR-TEST-001",
    "loan_type": "MORTGAGE_CONVENTIONAL",
    "credit_score": 705,
    "total_dti_ratio": 0.38,
    "ltv_ratio": 0.82,
    "cash_flow_adequate": True,
    "dscr": None,
    "collateral_type": "RESIDENTIAL_PROPERTY",
    "bankruptcy_flag": False,
    "bankruptcy_chapter": "",
    "bankruptcy_discharge_years": 10.0,
    "ofac_hit": False,
    "audit_trail": [],
    "completed_steps": [],
    "errors": [],
}

# Pairs differ ONLY in protected-class-correlated attributes.
MATCHED_PAIRS: List[Tuple[Dict, Dict]] = [
    (
        {"applicant_name": "Emily Carlson", "property_census_tract": "26125198000", "property_zip": "48304"},
        {"applicant_name": "Lakisha Washington", "property_census_tract": "26163516900", "property_zip": "48205"},
    ),
    (
        {"applicant_name": "Gregory Olson", "property_census_tract": "55079004700", "property_zip": "53217"},
        {"applicant_name": "Jose Hernandez", "property_census_tract": "06037207400", "property_zip": "90011"},
    ),
    (
        {"applicant_name": "Susan Miller", "property_census_tract": "36059303400", "property_zip": "11030"},
        {"applicant_name": "Mei-Ling Chen", "property_census_tract": "36061010000", "property_zip": "10002"},
    ),
]


def _score(nodes, overrides: Dict) -> Dict:
    state = {**BASE_APPLICATION, **overrides}
    return nodes.risk_scoring_node(state)


class TestMatchedPairBlindness:
    def test_scores_identical_across_matched_pairs(self, a08):
        for variant_a, variant_b in MATCHED_PAIRS:
            ra = _score(a08, variant_a)
            rb = _score(a08, variant_b)
            assert ra.get("composite_score") == rb.get("composite_score"), (
                f"Score differs for matched pair {variant_a['applicant_name']} vs "
                f"{variant_b['applicant_name']} — protected-class-correlated attribute "
                "is influencing the credit score (ECOA violation pattern)."
            )

    def test_decision_tier_identical_across_matched_pairs(self, a08):
        for variant_a, variant_b in MATCHED_PAIRS:
            ra = _score(a08, variant_a)
            rb = _score(a08, variant_b)
            tier_keys = [k for k in ra if "tier" in k or "decision" in k or "recommendation" in k]
            for k in tier_keys:
                assert ra.get(k) == rb.get(k), f"{k} differs across matched pair"

    def test_flagged_tract_adds_review_not_score_change(self, a08):
        """The geographic flag exists to ADD fair-lending review — confirm it
        cannot move the score (review is a control; a score change is redlining)."""
        neutral = _score(a08, {"applicant_name": "T", "property_census_tract": "26125198000"})
        flagged = _score(a08, {"applicant_name": "T", "property_census_tract": "17031838400"})
        assert neutral.get("composite_score") == flagged.get("composite_score")


# ── Four-fifths (adverse impact ratio) harness ───────────────────────────────
def compute_adverse_impact_ratio(decisions: List[Dict]) -> Dict[str, float]:
    """
    decisions: [{"group": str, "approved": bool}, ...]
    Returns {group: selection_rate / max_selection_rate}. The group with the
    highest selection rate gets 1.0; any group below 0.80 fails the
    four-fifths rule (EEOC/CFPB presumption of disparate impact).
    """
    rates: Dict[str, Tuple[int, int]] = {}
    for d in decisions:
        approved, total = rates.get(d["group"], (0, 0))
        rates[d["group"]] = (approved + (1 if d["approved"] else 0), total + 1)
    selection = {g: (a / t if t else 0.0) for g, (a, t) in rates.items()}
    top = max(selection.values()) if selection else 0.0
    return {g: (r / top if top else 0.0) for g, r in selection.items()}


class TestAdverseImpactHarness:
    def test_identical_portfolios_yield_air_of_one(self, a08):
        """Synthetic identical-by-design portfolio through the real scorer:
        any AIR deviation from 1.0 means a group-sensitive pathway exists."""
        profiles = [
            {"credit_score": 760, "total_dti_ratio": 0.30, "ltv_ratio": 0.75},
            {"credit_score": 705, "total_dti_ratio": 0.38, "ltv_ratio": 0.82},
            {"credit_score": 650, "total_dti_ratio": 0.45, "ltv_ratio": 0.90},
            {"credit_score": 590, "total_dti_ratio": 0.49, "ltv_ratio": 0.95},
        ]
        decisions = []
        for group, name, tract in (
            ("A", "Emily Carlson", "26125198000"),
            ("B", "Lakisha Washington", "17031838400"),
        ):
            for p in profiles:
                r = _score(a08, {**p, "applicant_name": name, "property_census_tract": tract})
                score = r.get("composite_score") or 0.0
                decisions.append({"group": group, "approved": score >= 0.55})
        air = compute_adverse_impact_ratio(decisions)
        assert air["A"] == air["B"] == 1.0, f"Group-sensitive pathway detected: AIR={air}"

    def test_harness_flags_a_known_disparity(self):
        """Sanity: the AIR math itself detects an engineered 50% disparity."""
        decisions = (
            [{"group": "A", "approved": True}] * 8 + [{"group": "A", "approved": False}] * 2
            + [{"group": "B", "approved": True}] * 4 + [{"group": "B", "approved": False}] * 6
        )
        air = compute_adverse_impact_ratio(decisions)
        assert air["B"] == pytest.approx(0.5)
        assert air["B"] < 0.80  # four-fifths failure correctly surfaced
