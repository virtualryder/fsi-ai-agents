"""
MCP authorization gateway tests (Phase 3) — run in CI without AWS or network.

These prove the security model the assessment specified (§7): deny-by-default,
least-privilege as agent∩user, short-lived scoped tokens with user context,
human approval for high-risk tools, append-only audit of every attempt
(including denials), and fail-closed behavior.
"""
from __future__ import annotations

import time

import pytest

from fsi_agent_platform.mcp_gateway import (
    ApprovalRequired,
    GatewayAuditLog,
    MCPGateway,
    PolicyDenied,
    TokenError,
    policy,
    tokens,
)

ANALYST = {"sub": "u-analyst", "custom:bsa_role": "BSA_ANALYST"}
OFFICER = {"sub": "u-officer", "custom:bsa_role": "BSA_OFFICER"}
KYC = {"sub": "u-kyc", "custom:bsa_role": "KYC_REVIEWER"}
APPROVAL = {"approved": True, "reviewer": {"sub": "supervisor-1", "email": "s@bank.example"}}
A01 = "01-financial-crime-investigation"


# ── policy: deny-by-default + least-privilege intersection ────────────────────
class TestPolicy:
    def test_unknown_tool_denied(self):
        assert policy.decide(A01, ["BSA_OFFICER"], "nope.tool").allowed is False

    def test_allowed_when_in_both_agent_and_user_sets(self):
        d = policy.decide(A01, ["BSA_ANALYST"], "watchlist.screen")
        assert d.allowed and d.effective_scope == ["watchlist.screen"]

    def test_denied_when_agent_lacks_grant_even_if_user_entitled(self):
        # Surveillance agent is not granted watchlist even for an entitled user.
        d = policy.decide("07-trading-surveillance", ["BSA_OFFICER"], "watchlist.screen")
        assert d.allowed is False and "not granted" in d.reason

    def test_denied_when_user_lacks_entitlement_even_if_agent_granted(self):
        # Agent 01 is granted tms.update_disposition, but a plain analyst is not.
        d = policy.decide(A01, ["BSA_ANALYST"], "tms.update_disposition")
        assert d.allowed is False and "not entitled" in d.reason

    def test_high_risk_tool_flags_approval(self):
        d = policy.decide(A01, ["BSA_OFFICER"], "tms.update_disposition")
        assert d.allowed and d.requires_approval is True

    def test_read_tool_does_not_require_approval(self):
        d = policy.decide(A01, ["BSA_OFFICER"], "watchlist.screen")
        assert d.allowed and d.requires_approval is False

    def test_unknown_role_contributes_no_entitlement(self):
        assert policy.decide(A01, ["WHO_DIS"], "watchlist.screen").allowed is False


# ── scoped tokens: short-lived, user-context, tamper/expiry fail-closed ───────
class TestTokens:
    def test_mint_and_verify_roundtrip(self):
        t = tokens.mint_scoped_token(subject="u1", agent_id=A01, tool="watchlist.screen",
                                     scope=["watchlist.screen"])
        c = tokens.verify_scoped_token(t, expected_tool="watchlist.screen")
        assert c["sub"] == "u1" and c["tool"] == "watchlist.screen" and "jti" in c

    def test_tamper_is_rejected(self):
        t = tokens.mint_scoped_token(subject="u1", agent_id=A01, tool="watchlist.screen", scope=[])
        with pytest.raises(TokenError):
            tokens.verify_scoped_token(t[:-2] + ("aa" if not t.endswith("aa") else "bb"))

    def test_expired_token_rejected(self):
        t = tokens.mint_scoped_token(subject="u1", agent_id=A01, tool="watchlist.screen",
                                     scope=[], ttl_seconds=-1)
        with pytest.raises(TokenError):
            tokens.verify_scoped_token(t)

    def test_wrong_tool_binding_rejected(self):
        t = tokens.mint_scoped_token(subject="u1", agent_id=A01, tool="watchlist.screen", scope=[])
        with pytest.raises(TokenError):
            tokens.verify_scoped_token(t, expected_tool="tms.get_alert")

    def test_malformed_token_rejected(self):
        with pytest.raises(TokenError):
            tokens.verify_scoped_token("not-a-token")


# ── gateway: end-to-end enforcement ───────────────────────────────────────────
class TestGateway:
    def test_allowed_read_invokes_connector(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims=ANALYST, agent_id=A01, tool="watchlist.screen",
                      args={"name": "Ivan Petrov"})
        assert r.decision == "ALLOW" and r.allowed and r.result["hit"] is True
        assert r.token_jti and r.scope == ["watchlist.screen"]

    def test_unauthenticated_is_denied(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims={}, agent_id=A01, tool="watchlist.screen", args={"name": "x"})
        assert r.decision == "DENY" and "authenticated" in r.reason

    def test_least_privilege_blocks_user_overreach(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims=ANALYST, agent_id=A01, tool="tms.update_disposition",
                      args={"alert_id": "A1", "disposition": "CLOSE", "reason": "x"})
        assert r.decision == "DENY" and "not entitled" in r.reason

    def test_agent_overreach_blocked(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims=OFFICER, agent_id="07-trading-surveillance",
                      tool="watchlist.screen", args={"name": "x"})
        assert r.decision == "DENY" and "not granted" in r.reason

    def test_high_risk_pends_without_approval(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims=OFFICER, agent_id=A01, tool="tms.update_disposition",
                      args={"alert_id": "A1", "disposition": "ESCALATE", "reason": "x"})
        assert r.decision == "PENDING_APPROVAL" and r.requires_approval and r.result is None

    def test_high_risk_executes_with_verified_approval(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims=OFFICER, agent_id=A01, tool="tms.update_disposition",
                      args={"alert_id": "A1", "disposition": "ESCALATE", "reason": "x"},
                      approval=APPROVAL)
        assert r.decision == "ALLOW" and r.result["accepted"] is True

    def test_approval_without_verified_reviewer_still_pends(self):
        gw = MCPGateway()
        r = gw.invoke(user_claims=OFFICER, agent_id=A01, tool="tms.update_disposition",
                      args={"alert_id": "A1", "disposition": "ESCALATE", "reason": "x"},
                      approval={"approved": True, "reviewer": {}})  # no reviewer sub
        assert r.decision == "PENDING_APPROVAL"

    def test_raise_on_deny_modes(self):
        gw = MCPGateway()
        with pytest.raises(PolicyDenied):
            gw.invoke(user_claims=ANALYST, agent_id=A01, tool="tms.update_disposition",
                      args={"alert_id": "A1", "disposition": "x", "reason": "y"}, raise_on_deny=True)
        with pytest.raises(ApprovalRequired):
            gw.invoke(user_claims=OFFICER, agent_id=A01, tool="tms.update_disposition",
                      args={"alert_id": "A1", "disposition": "x", "reason": "y"}, raise_on_deny=True)


# ── audit: append-only, captures allow + deny, masks PII, carries lineage ─────
class TestAudit:
    def test_every_attempt_is_audited(self):
        gw = MCPGateway()
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="watchlist.screen", args={"name": "Ivan Petrov"})
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="tms.update_disposition",
                  args={"alert_id": "A1", "disposition": "x", "reason": "y"})
        entries = gw.audit.entries()
        assert len(entries) == 2
        assert {e["decision"] for e in entries} == {"ALLOW", "DENY"}

    def test_denials_are_queryable(self):
        gw = MCPGateway()
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="tms.update_disposition",
                  args={"alert_id": "A1", "disposition": "x", "reason": "y"})
        assert len(gw.audit.denials()) == 1

    def test_allow_entry_has_lineage_and_token(self):
        gw = MCPGateway()
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="core_banking.get_customer",
                  args={"customer_id": "CUST-001"})
        e = [e for e in gw.audit.entries() if e["decision"] == "ALLOW"][0]
        assert e["lineage"]["connector"] == "core_banking" and e["token_jti"]

    def test_audit_masks_pii_in_args(self):
        gw = MCPGateway()
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="watchlist.screen",
                  args={"name": "SSN 123-45-6789"})
        blob = repr(gw.audit.entries())
        assert "123-45-6789" not in blob

    def test_audit_is_append_only_copy(self):
        gw = MCPGateway()
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="watchlist.screen", args={"name": "x"})
        snapshot = gw.audit.entries()
        snapshot.clear()  # mutating the returned list must not affect the log
        assert len(gw.audit.entries()) == 1

    def test_external_sink_receives_records(self):
        seen = []
        gw = MCPGateway(audit=GatewayAuditLog(sink=seen.append))
        gw.invoke(user_claims=ANALYST, agent_id=A01, tool="watchlist.screen", args={"name": "x"})
        assert len(seen) == 1 and seen[0]["decision"] == "ALLOW"
