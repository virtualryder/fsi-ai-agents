"""Governance core tests — prompt manifest regression gate + grounding checks."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from governance.grounding import verify_grounding
from governance.prompt_registry import diff_against_manifest, discover_prompt_files


class TestPromptManifestGate:
    def test_all_12_agents_have_prompt_files(self):
        assert len(discover_prompt_files()) == 12

    def test_no_prompt_drift(self):
        """
        FAILS when any agent's prompts.py changed without a manifest update.
        Prompts are model configuration (SR 11-7): changes must be explicit.
        Fix: python -m governance.prompt_registry --update  (same PR).
        """
        problems = diff_against_manifest()
        assert not problems, f"Prompt drift without version bump: {problems}"


class TestGrounding:
    STATE = {
        "alert_id": "TMS-9912",
        "amount": 45000,
        "transactions": [{"amount": 18000.50, "counterparty": "Acme Trading LLC"}],
        "narrative_inputs": "Customer Maria Gonzalez wired funds to Acme Trading LLC",
        "customer_name": "Maria Gonzalez",
    }

    def test_grounded_narrative_passes(self):
        n = "Maria Gonzalez initiated a wire of $45,000, including $18,000.50 to Acme Trading LLC."
        r = verify_grounding(n, self.STATE)
        assert r.grounded, (r.ungrounded_numbers, r.ungrounded_entities)

    def test_hallucinated_amount_flagged(self):
        n = "The customer wired $99,999 in structured transactions."
        r = verify_grounding(n, self.STATE)
        assert "$99,999" in r.ungrounded_numbers

    def test_hallucinated_entity_flagged(self):
        n = "Funds were routed through Pacific Shell Holdings before withdrawal."
        r = verify_grounding(n, self.STATE)
        assert "Pacific Shell Holdings" in r.ungrounded_entities

    def test_regulatory_boilerplate_allowed(self):
        n = "This Suspicious Activity Report is filed with FinCEN per the Bank Secrecy Act."
        r = verify_grounding(n, self.STATE)
        assert r.grounded

    def test_small_counts_not_flagged(self):
        n = "The customer made 3 deposits over 2 days."
        r = verify_grounding(n, self.STATE)
        assert r.grounded

    def test_number_format_aliases(self):
        # 45000 in state should ground "$45,000.00" in narrative
        r = verify_grounding("A total of $45,000.00 moved.", self.STATE)
        assert r.grounded

    def test_empty_narrative(self):
        assert verify_grounding("", self.STATE).grounded
