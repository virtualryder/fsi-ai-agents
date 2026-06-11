"""
Per-graph-node observability — Rec 4 (observability gap).

`traced_node` wraps a LangGraph node function in an OpenTelemetry span:

    span name        fsi.node.<function name>
    attributes       fsi.agent_id, fsi.node, fsi.case_id (best-effort from
                     state), fsi.errors_count on exit
    correlation      OTel context propagates across nodes in-process; the
                     case id attribute joins spans to the audit trail.

No hard dependency: when opentelemetry isn't installed (or OTEL_DISABLED is
set) the decorator is a zero-cost pass-through, so demo environments and CI
need nothing extra. Production: install opentelemetry-sdk + OTLP exporter
and point OTEL_EXPORTER_OTLP_ENDPOINT at the collector (ADOT sidecar on ECS
→ CloudWatch/X-Ray — see infra/terraform/modules/agent_service).

Adoption: decorate nodes directly, or wrap at graph build time:

    workflow.add_node("sanctions_screening", traced_node(sanctions_screening_node))
"""
from __future__ import annotations

import functools
import logging
import os
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

_CASE_ID_KEYS = (
    "case_id", "alert_id", "payment_event_id", "application_id", "document_id",
    "review_id", "change_id", "validation_id", "account_id", "transaction_id",
)


def _tracer():
    if os.getenv("OTEL_DISABLED", "").lower() == "true":
        return None
    try:
        from opentelemetry import trace  # lazy optional dep

        return trace.get_tracer("fsi-agent-platform")
    except ImportError:
        return None


def _case_id(state: Dict[str, Any]) -> str:
    for k in _CASE_ID_KEYS:
        v = state.get(k)
        if v:
            return str(v)
    return "unknown"


def traced_node(fn: Callable) -> Callable:
    """Wrap a node function in an OTel span; no-op when OTel is unavailable."""
    tracer = _tracer()
    if tracer is None:
        return fn

    @functools.wraps(fn)
    def wrapper(state: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        with tracer.start_as_current_span(f"fsi.node.{fn.__name__}") as span:
            span.set_attribute("fsi.agent_id", os.getenv("AGENT_ID", "unknown"))
            span.set_attribute("fsi.node", fn.__name__)
            span.set_attribute("fsi.case_id", _case_id(state))
            result = fn(state, *args, **kwargs)
            if isinstance(result, dict):
                span.set_attribute("fsi.errors_count", len(result.get("errors") or []))
                if result.get("human_review_required"):
                    span.set_attribute("fsi.hitl_triggered", True)
            return result

    return wrapper
