"""CI entry point: golden-case evals as pytest. See run_evals.py for the harness."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from governance.evals.run_evals import run_all  # noqa: E402


@pytest.mark.parametrize("result", run_all(), ids=lambda r: r.case_id)
def test_golden_case(result):
    assert result.passed, f"{result.case_id}: " + "; ".join(result.failures)
