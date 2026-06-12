"""Node 2 — deterministic rule engine + composite + decision (no model in routing)."""
from . import _shared  # noqa: F401
import core


def handler(event, context=None):
    txn = event.get("transaction", {})
    rule = core.rule_engine(txn)
    decision = core.decide(rule, behavioral_score=float(txn.get("behavioral_score", 0.0)))
    return {**event, "rule": rule, "decision": decision}
