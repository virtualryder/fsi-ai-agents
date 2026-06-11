"""
LLM output evaluation harness — Rec 6.

Two eval families, both deterministic and CI-runnable WITHOUT API keys:

  STRUCTURAL  Does the artifact contain what the regulation requires?
              (SAR narratives: FinCEN's who/what/when/where/why sections;
               adverse-action output: ECOA-valid reason codes tied to real
               applicant factors.)
  GROUNDING   Is every number/entity in the artifact traceable to case
              state? (governance/grounding.py)

Golden datasets live in governance/evals/golden/*.json:
    {"cases": [{"id", "state": {...}, "artifact": "...", "expect": {...}}]}

Two run modes:
  pytest governance/evals            -> evaluates the RECORDED artifacts in
                                        the golden files (regression: did a
                                        prompt/code change degrade structure
                                        or grounding of known-good outputs?)
  python -m governance.evals.run_evals --live
                                     -> regenerates artifacts with the real
                                        model first (requires ANTHROPIC_API_KEY;
                                        run before any prompt-manifest bump).

Adding a case: capture a reviewed-and-approved production-quality output,
append it with its full input state, and let CI hold the line behind it.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from governance.grounding import verify_grounding  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# FinCEN SAR narrative guidance: the five interrogatives + disposition.
SAR_REQUIRED_ELEMENTS = {
    "who": re.compile(r"\b(customer|subject|account holder|individual|entity)\b", re.I),
    "what": re.compile(r"\b(wire|deposit|withdrawal|transfer|transaction|structur)\w*", re.I),
    "when": re.compile(r"\b(20\d{2}|january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I),
    "where": re.compile(r"\b(branch|account|jurisdiction|country|location|bank)\b", re.I),
    "why_suspicious": re.compile(r"\b(suspicious|unusual|inconsistent|no apparent|lacked|atypical|evasi)\w*", re.I),
}
PII_IN_NARRATIVE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b(?:\d[ -]?){15,19}\b")

# Regulation B / ECOA: principal reasons must be specific and factor-based.
VALID_ADVERSE_ACTION_REASONS = {
    "INSUFFICIENT_CREDIT_SCORE", "EXCESSIVE_DTI", "HIGH_LTV", "INSUFFICIENT_CASH_FLOW",
    "INSUFFICIENT_COLLATERAL", "RECENT_BANKRUPTCY", "DELINQUENT_CREDIT_OBLIGATIONS",
    "INSUFFICIENT_INCOME", "LIMITED_CREDIT_HISTORY",
}
PROHIBITED_REASON_LANGUAGE = re.compile(
    r"\b(neighborhood|area of residence|census tract|national origin|race|religion|"
    r"sex|gender|marital status|age of applicant|public assistance)\b", re.I)


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    failures: List[str] = field(default_factory=list)


def eval_sar_narrative(case: Dict[str, Any]) -> EvalResult:
    narrative: str = case["artifact"]
    failures: List[str] = []

    for element, pattern in SAR_REQUIRED_ELEMENTS.items():
        if not pattern.search(narrative):
            failures.append(f"missing FinCEN narrative element: {element}")

    if PII_IN_NARRATIVE.search(narrative):
        failures.append("raw PII (SSN/PAN) present in SAR narrative")

    grounding = verify_grounding(narrative, case["state"])
    for n in grounding.ungrounded_numbers:
        failures.append(f"ungrounded number in narrative: {n}")
    for e in grounding.ungrounded_entities:
        failures.append(f"ungrounded entity in narrative: {e}")

    min_words = case.get("expect", {}).get("min_words", 80)
    if len(narrative.split()) < min_words:
        failures.append(f"narrative too thin: {len(narrative.split())} words < {min_words}")

    return EvalResult(case["id"], not failures, failures)


def eval_adverse_action(case: Dict[str, Any]) -> EvalResult:
    artifact: Dict[str, Any] = case["artifact"]  # {"reasons": [...], "letter_text": "..."}
    state = case["state"]
    failures: List[str] = []

    reasons = artifact.get("reasons", [])
    if not 1 <= len(reasons) <= 4:
        failures.append(f"Reg B expects 1-4 principal reasons, got {len(reasons)}")

    for r in reasons:
        if r["code"] not in VALID_ADVERSE_ACTION_REASONS:
            failures.append(f"non-ECOA reason code: {r['code']}")

    # Each cited reason must be TRUE of this applicant (reason-accuracy):
    checks = {
        "INSUFFICIENT_CREDIT_SCORE": lambda s: s.get("credit_score", 850) < 680,
        "EXCESSIVE_DTI": lambda s: s.get("total_dti_ratio", 0) > 0.43,
        "HIGH_LTV": lambda s: s.get("ltv_ratio", 0) > 0.90,
        "INSUFFICIENT_CASH_FLOW": lambda s: not s.get("cash_flow_adequate", True),
        "RECENT_BANKRUPTCY": lambda s: s.get("bankruptcy_flag", False),
    }
    for r in reasons:
        check = checks.get(r["code"])
        if check and not check(state):
            failures.append(f"reason {r['code']} cited but not supported by applicant facts")

    letter = artifact.get("letter_text", "")
    if PROHIBITED_REASON_LANGUAGE.search(letter):
        failures.append("prohibited-basis language in adverse action letter")

    return EvalResult(case["id"], not failures, failures)


EVALUATORS = {
    "agent01_sar_narratives": eval_sar_narrative,
    "agent08_adverse_action": eval_adverse_action,
}


def run_all() -> List[EvalResult]:
    results: List[EvalResult] = []
    for golden_file in sorted(GOLDEN_DIR.glob("*.json")):
        suite = json.loads(golden_file.read_text())
        evaluator = EVALUATORS[golden_file.stem]
        for case in suite["cases"]:
            results.append(evaluator(case))
    return results


if __name__ == "__main__":
    results = run_all()
    failed = [r for r in results if not r.passed]
    for r in results:
        print(("PASS" if r.passed else "FAIL"), r.case_id)
        for f in r.failures:
            print("   -", f)
    print(f"\n{len(results) - len(failed)}/{len(results)} eval cases passed")
    raise SystemExit(1 if failed else 0)
