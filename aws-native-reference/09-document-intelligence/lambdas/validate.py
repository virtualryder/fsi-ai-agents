"""Node 3 — deterministic field validation + business-rule checks."""
from __future__ import annotations
from . import _shared  # noqa: F401

# Minimal required-field rules per type (illustrative).
_REQUIRED = {
    "loan_application_1003": ["borrower", "loan_amount"],
    "wire_instruction": ["beneficiary", "amount"],
}


def handler(event, context=None):
    ex = event.get("extraction", {})
    dt = ex.get("document_type", "unknown")
    fields = ex.get("fields", {})
    validation_errors = [f"missing required field: {f}" for f in _REQUIRED.get(dt, []) if f not in fields]
    # Example AML business-rule signal: a wire with no beneficiary name is a red flag.
    business_rule_violations = []
    if dt == "wire_instruction" and not fields.get("beneficiary"):
        business_rule_violations.append("wire instruction missing beneficiary")
    return {**event, "validation_errors": validation_errors,
            "business_rule_violations": business_rule_violations}
