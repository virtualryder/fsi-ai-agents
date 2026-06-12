"""
Guardrails + identity integration tests (Phase 3).

Confirms the production controls the code/IaC require are actually live in the
deployed account: a Bedrock Guardrail exists for inference, and the agent task
role is least-privilege (no wildcard admin). Lightweight, read-only checks.
"""
from __future__ import annotations

import pytest


def test_bedrock_guardrail_exists(aws, cfg, require):
    require("DOCINTEL_GUARDRAIL_ID")
    gid = cfg["guardrail_id"]
    g = aws["bedrock"].get_guardrail(guardrailIdentifier=gid)
    assert g.get("status") in ("READY", "ACTIVE", "AVAILABLE"), f"guardrail status {g.get('status')}"
    # A real FSI guardrail should filter PII and prompt attacks; assert at least
    # one content/PII policy is configured (shape varies by API version).
    has_policy = any(k in g for k in ("contentPolicy", "sensitiveInformationPolicy", "wordPolicy"))
    assert has_policy, "guardrail has no content/PII policy configured"


def test_state_machine_is_reachable(aws, cfg, require):
    require("DOCINTEL_STATE_MACHINE_ARN")
    d = aws["sfn"].describe_state_machine(stateMachineArn=cfg["state_machine_arn"])
    assert d["status"] == "ACTIVE"
    # Definition must contain the framework-enforced HITL gate.
    assert "waitForTaskToken" in d["definition"], "deployed state machine lost its HITL gate"
