# MCP Authorization Gateway (Phase 3)

The governed front door between agents and systems of record. Every agent tool
call passes through one enforcement point — there are **no standing service
accounts** and the model is **deny-by-default** and **fail-closed**.

This is the reference implementation of the security model in the assessment's
§7. It runs and is fully tested without AWS; the AWS-managed equivalent is the
documented deployment target (see the mapping below).

## The flow (one tool call)

```
agent ──▶ MCPGateway.invoke(user_claims, agent_id, tool, args, approval)
            │
            1. Authenticate     verified IdP claims; no subject ⇒ DENY (fail-closed)
            2. Authorize        deny-by-default; allowed ⇔ tool ∈ AGENT_GRANTS[agent] ∩ USER_ENTITLEMENTS[roles]
            3. Approve          high-risk (write/irreversible) tool ⇒ human approval w/ verified reviewer
            4. Mint token       short-lived token scoped to exactly this tool, carrying the user's sub
            5. Invoke           via the Phase 2 connector framework (fixture or live)
            6. Audit            append-only, PII-masked: ALLOW / DENY / PENDING_APPROVAL / ERROR + lineage
            7. Fail closed      any error ⇒ deny + audited, never silent success
```

## Least privilege is an intersection (the load-bearing idea)

An agent can **never exceed the human it acts for**. Permission is the
intersection of what the agent is granted and what the user is actually
entitled to:

```
permitted(tool) ⇔ tool ∈ AGENT_TOOL_GRANTS[agent] ∩ ⋃ ROLE_ENTITLEMENTS[user_roles]
```

So a financial-crime agent that *is* granted `tms.update_disposition` still
cannot perform it on behalf of a plain analyst who lacks that entitlement — and
a surveillance agent cannot call `watchlist.screen` at all, even for a fully
entitled officer. Both are denied and **both denials are audited**.

## High-risk tools require human approval

Write / irreversible tools (`tms.update_disposition`, `ach_operator.submit_return`)
return `PENDING_APPROVAL` and do not execute until a request carries a **verified
reviewer identity** (`approval={"approved": True, "reviewer": {"sub": ...}}`). The
approver is bound into the audit record. This is the tool-call approval gate from
§7, and it composes with each agent's own HITL gate.

## Scoped capability tokens

After authorization the gateway mints a token scoped to exactly one tool, with a
short TTL (default 5 min), carrying the acting user's `sub` (context propagation)
and a unique `jti`. The downstream tool trusts only this token. Tamper, expiry,
and tool-mismatch all raise `TokenError` (fail-closed).

> The reference token is a self-contained HMAC-signed token (stdlib only) so the
> model is testable with no dependency. **In production it is an AWS STS
> short-lived credential / Amazon Cognito token exchange / Bedrock AgentCore
> Identity workload token** — same claims, same TTL semantics, same fail-closed
> validation.

## Append-only audit (accountability, traceability, lineage)

Every attempt is recorded, PII-masked (via the Phase 1 boundary middleware),
with the acting user, the agent, the tool, the decision, the scoped-token `jti`,
the approver (if any), and a **lineage** pointer to the system of record reached.
Denials are recorded too — "the agent tried X and was refused" is exactly what an
investigation needs. Entries are immutable once appended.

## Mapping to AWS-native

| Reference (this package) | AWS-native deployment target |
|---|---|
| `MCPGateway` enforcement point | **Bedrock AgentCore Gateway** (or API Gateway + Lambda authorizer) |
| `policy.decide` (deny-by-default, intersection) | **OPA / Amazon Verified Permissions (Cedar)** fed by the IdP |
| User authentication (verified claims) | **Amazon Cognito / enterprise IdP (Okta) via SAML/OIDC** |
| `mint_scoped_token` (short-lived, scoped) | **AWS STS** session / **Cognito token exchange** / **AgentCore Identity** |
| Connector invocation | the Phase 2 connector layer → real vendor APIs |
| Append-only audit | **DynamoDB (PutItem-only IAM) + S3 Object Lock** (already in `infra/terraform`) |
| Human approval gate | **Step Functions `waitForTaskToken`** (see `aws-native-reference/`) |
| Agent identity | agent as a **registered workload/service principal** (AgentCore Identity / IAM role) |

## Usage

```python
from fsi_agent_platform.mcp_gateway import MCPGateway

gw = MCPGateway()  # fixture connectors by default; CONNECTOR_MODE=live for real systems
result = gw.invoke(
    user_claims={"sub": "u-analyst", "custom:bsa_role": "BSA_ANALYST"},
    agent_id="01-financial-crime-investigation",
    tool="watchlist.screen",
    args={"name": "Ivan Petrov"},
)
# result.decision == "ALLOW"; result.result is the connector output; result.audit_id logged
```

## Verified vs. needs-an-account

**Verified in CI (no AWS, no network):** deny-by-default, the least-privilege
intersection (both directions), scoped-token mint/verify/expiry/tamper, the
high-risk approval gate, append-only audit of allow + deny with PII masking and
lineage, and fail-closed behavior — 26 tests.

**Needs an AWS account (integration step):** swapping the HMAC token for STS/
Cognito/AgentCore Identity, the policy tables for Verified Permissions/OPA, and
the in-memory audit for DynamoDB+S3 Object Lock; wiring one agent's tool calls
through a deployed AgentCore Gateway. On the maturity ladder this gateway is
**Demonstrated** and **Deployable-by-design**.

## Wiring an agent through the gateway (adoption)

Replace a direct connector/fixture call inside an agent tool with a gateway
call that carries the acting user's claims:

```python
# BEFORE: agent calls a system of record directly
hits = get_connector("watchlist").screen(name)

# AFTER: the call is authorized, scoped, approved-if-needed, and audited
res = gateway.invoke(user_claims=ctx.user_claims,
                     agent_id="01-financial-crime-investigation",
                     tool="watchlist.screen", args={"name": name})
hits = res.result["hits"] if res.allowed else []
```

Recommended first adoption: Agent 09 (the front door), then the AML loop
(02 → 01), matching the pilot wedge.

### Reference adoption (implemented)

Agent 01 (Financial Crime Investigation) ships a gateway-backed tools module as
the concrete reference:

- `01-financial-crime-investigation-agent/tools/gateway_tools.py` — `screen_watchlist`,
  `get_customer`, `get_transactions`, `get_alert` (reads) and
  `update_alert_disposition` (high-risk write, needs approval), each routing
  through the gateway on behalf of the acting user. Fails closed
  (`GatewayUnavailable`) if the platform is not installed — never silent fixtures.
- `agent/state.py` carries `acting_user_claims` (verified IdP claims) so nodes
  can pass user context to the gateway.
- `platform_core/tests/test_agent01_gateway_adoption.py` exercises the full
  agent → gateway → connector path (ALLOW / DENY / approval / audit / PII-mask).

The existing fixture tools remain for the no-platform demo; the gateway-backed
module is the production path an engagement switches to.
