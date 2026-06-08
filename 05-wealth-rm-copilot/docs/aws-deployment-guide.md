# AWS Deployment Guide: Wealth & RM Copilot
## Enterprise Deployment Playbook — RM Productivity + Reg BI Compliance

> **Suite context:** This agent is the client-facing intelligence layer of the suite. It uses KYC data maintained by Agent 03 and operates independently from the AML financial crime loop (Agents 01-02). It is the recommended entry point for wealth management firms without an AML program. See the [Suite Architecture](../../docs/SUITE-ARCHITECTURE.md) for the full platform picture.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                Wealth & RM Copilot — AWS Architecture                        │
│                                                                             │
│  RM REQUESTS:                                                               │
│  ├── Meeting prep (pre-client meeting briefing)                            │
│  ├── Rebalancing proposal (portfolio drift from IPS)                       │
│  ├── Investment proposal (new idea, Reg BI rationale)                      │
│  ├── Portfolio review (annual review document)                             │
│  ├── Client communication (life event, market event)                       │
│  └── Alert response (market alert, account anomaly)                        │
│                   ↓                                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    ECS Fargate Cluster                                 │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐  │ │
│  │  │  Streamlit UI   │  │  LangGraph Agent  │  │  MCP Auth Gateway   │  │ │
│  │  │  (Port 8505)    │  │  Worker           │  │  (Port 8443)        │  │ │
│  │  │  - RM Request   │  │  11-node workflow │  │  JWT validation     │  │ │
│  │  │  - Client       │  │  trigger_intake   │  │  Role-based authz   │  │ │
│  │  │    Profile      │  │  → client_profile │  │  Audit logging      │  │ │
│  │  │  - Portfolio    │  │  → portfolio_anal.│  │                     │  │ │
│  │  │    Analysis     │  │  → market_intel   │  │                     │  │ │
│  │  │  - Draft Output │  │  → suitability    │  │                     │  │ │
│  │  │  - RM Approval  │  │    (Python only)  │  │                     │  │ │
│  │  │  - Audit Trail  │  │  → rec_engine     │  │                     │  │ │
│  │  └─────────────────┘  └──────────────────┘  └─────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                    ↓                          ↓                             │
│  ┌──────────────────────┐     ┌───────────────────────────────────────┐    │
│  │  AWS Bedrock         │     │  MCP Tool Servers                     │    │
│  │  Claude Sonnet       │     │  ├── CRM Connector (Port 8011)        │    │
│  │  (content drafting,  │     │  ├── Portfolio Data (Port 8012)       │    │
│  │  Reg BI rationale,   │     │  ├── Market Intelligence (Port 8013)  │    │
│  │  client letters)     │     │  ├── KYC Profile (Agent 03) (8014)   │    │
│  └──────────────────────┘     │  └── Compliance Check (Port 8015)   │    │
│                                └───────────────────────────────────────┘    │
│                                                                             │
│  DATA LAYER                                                                 │
│  RDS Aurora (RM requests · approval records · client output history)        │
│  DynamoDB (immutable audit trail — every recommendation, every approval)    │
│  S3 (approved proposals · review documents · client letters — 6yr FINRA)   │
│  ElastiCache Redis (JWKS cache · portfolio data cache · session state)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Critical Design Note: Suitability Determination is Python-Only

The suitability check node (`suitability_check`) runs **exclusively in Python**. No LLM is involved in determining whether a recommendation is suitable for a client. This is a deliberate design decision with regulatory significance:

```python
# agent/nodes.py — suitability_check node (abbreviated)

def suitability_check(state: WealthRMState) -> WealthRMState:
    """
    Python-only suitability determination.

    Reg BI (17 CFR 240.15l-1) Care Obligation requires that recommendations
    be in the client's best interest considering:
    - Risk profile
    - Investment objectives
    - Financial situation and needs
    - Other investments
    - Investment time horizon

    FINRA Rule 2111 Suitability requires:
    - Reasonable basis suitability
    - Customer-specific suitability
    - Quantitative suitability

    These are legal determinations — not suitable for LLM probabilistic reasoning.
    This function implements deterministic rule-based suitability screening.
    """
    recommendation = state["proposed_recommendation"]
    client = state["client_profile"]
    ips = state["investment_policy_statement"]

    # Hard blocks — unsuitable regardless of other factors
    if recommendation.risk_level > ips.max_risk_tolerance:
        return {**state, "suitability_result": "UNSUITABLE",
                "suitability_reason": f"Product risk level {recommendation.risk_level} exceeds IPS maximum {ips.max_risk_tolerance}"}

    if recommendation.security_type in ips.prohibited_securities:
        return {**state, "suitability_result": "UNSUITABLE",
                "suitability_reason": f"{recommendation.security_type} is prohibited by IPS"}

    if client.is_erisa_account and not recommendation.erisa_eligible:
        return {**state, "suitability_result": "UNSUITABLE",
                "suitability_reason": "ERISA account: prohibited transaction under 29 U.S.C. § 1106"}

    # SUITABLE_W_NOTE — suitable but requires disclosure
    notes = []
    if recommendation.has_conflicts_of_interest:
        notes.append("Conflict of interest disclosure required (Reg BI Conflict Obligation)")
    if client.ips_last_updated_days > 730:
        notes.append("IPS not updated in 24+ months — FINRA Rule 4512 refresh recommended")
    if recommendation.is_complex_product:
        notes.append("Complex product — enhanced disclosure required")

    if notes:
        return {**state, "suitability_result": "SUITABLE_W_NOTE", "suitability_notes": notes}

    return {**state, "suitability_result": "SUITABLE"}
```

**Why this matters for the sales conversation:** Examiners and legal teams are skeptical of AI-driven suitability determinations. This architecture makes clear that AI drafts the proposal content — the suitability determination is Python code that can be audited, read, and understood by compliance staff.

---

## AWS Service Configuration

### ECS Fargate Task Definition
```yaml
Family: wealth-rm-copilot-worker
CPU: 2048      # 2 vCPU — content drafting with large context windows
Memory: 4096   # 4 GB — full client portfolio in context for drafting
NetworkMode: awsvpc
RequiresCompatibilities: [FARGATE]

Environment:
  - Name: BEDROCK_MODEL_ID
    Value: "anthropic.claude-3-5-sonnet-20241022-v2:0"
    # Sonnet for all nodes — client-facing content quality is paramount
  - Name: DATABASE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/wealth-rm/CUSTOMER_ID/db-url
  - Name: CUSTOMER_ID
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/wealth-rm/CUSTOMER_ID/customer-id
  - Name: FIRM_NAME
    Value: "First National Bank Wealth Management"
  - Name: FORM_CRS_URL
    Value: "https://files.first-national-bank.com/form-crs.pdf"

# Scaling: on-demand — RMs submit requests throughout business hours
# Min: 1 task, Max: 20 tasks (1 per concurrent RM request)
```

### S3 Configuration (Client Document Archive)
```yaml
ClientDocuments:
  BucketName: wealth-rm-CUSTOMER_ID-client-documents
  VersioningConfiguration: Enabled

  # FINRA Rule 4511 / SEC Rule 204-2: 6-year retention for client communications
  ObjectLockConfiguration:
    ObjectLockEnabled: Enabled
    Rule:
      DefaultRetention:
        Mode: GOVERNANCE
        Years: 6    # FINRA 6-year record retention requirement

  BucketEncryption:
    ServerSideEncryptionConfiguration:
      - ServerSideEncryptionByDefault:
          SSEAlgorithm: aws:kms
          KMSMasterKeyId: alias/wealth-rm-CUSTOMER_ID-s3

  # Folder structure:
  # wealth-rm-CUSTOMER_ID-client-documents/
  #   {year}/{rm_id}/{client_id}/
  #     meeting-prep-{date}.pdf
  #     rebalancing-proposal-{date}.pdf
  #     investment-proposal-{date}.pdf
  #     portfolio-review-{date}.pdf
  #     client-communication-{date}.pdf
```

---

## Identity & Access Management

### Role Mapping for Agent 05

| AD Group | Cognito Claim | Permissions |
|----------|---------------|------------|
| `GRP-Wealth-RMs` | `rm_role: RM` | Submit requests, view own client outputs, approve own drafts |
| `GRP-Wealth-Managers` | `rm_role: MANAGER` | All RM permissions + view all RM outputs + override |
| `GRP-Compliance-Officers` | `compliance_role: OFFICER` | Review compliance flags, approve communications |
| `GRP-AML-Auditors` | `bsa_role: AUDITOR` | Full read-only access to all outputs and audit trails |

### Okta Application Configuration (Agent 05 Specific)
```yaml
Application:
  Name: "Wealth RM Copilot - {CustomerName}"
  SignOnMethod: SAML 2.0

  SAML Settings:
    SingleSignOnURL: https://wealth-rm-CUSTOMER_ID.auth.us-east-1.amazoncognito.com/saml2/idpresponse
    AudienceURI: urn:amazon:cognito:sp:COGNITO_POOL_ID_AGENT05

  AttributeStatements:
    - Name: rm_role
      Value: |
        isMemberOf("GRP-Wealth-Managers") ? "MANAGER" :
        isMemberOf("GRP-Wealth-RMs") ? "RM" :
        "READ_ONLY"
    - Name: compliance_role
      Value: |
        isMemberOf("GRP-Compliance-Officers") ? "OFFICER" : ""
    - Name: rm_id
      Value: user.employeeNumber    # Maps RM to their client book of business

  Assignments:
    Groups:
      - GRP-Wealth-RMs
      - GRP-Wealth-Managers
      - GRP-Compliance-Officers
      - GRP-AML-Auditors
      # NOTE: Do NOT include GRP-BSA-Officers or GRP-AML-Investigators
      # per 18 U.S.C. § 1960 — no SAR/investigation references in client-facing app
```

### MCP Tool Authorization (Agent 05)
```python
TOOL_PERMISSIONS = {
    # Client data access
    "get_client_profile":          ["MANAGER", "RM", "OFFICER"],
    "get_portfolio_holdings":      ["MANAGER", "RM", "OFFICER"],
    "get_portfolio_performance":   ["MANAGER", "RM", "OFFICER"],
    "get_investment_policy":       ["MANAGER", "RM", "OFFICER"],
    "get_life_events":             ["MANAGER", "RM"],
    "get_client_crm_notes":        ["MANAGER", "RM"],

    # KYC data (from Agent 03 if deployed)
    "get_kyc_summary":             ["MANAGER", "RM", "OFFICER"],  # Non-sensitive KYC summary only
    # NOTE: Full KYC investigation data is NOT accessible via Agent 05
    # per the no-tipping-off principle (18 U.S.C. § 1960)

    # Market data
    "get_market_intelligence":     ["MANAGER", "RM"],
    "get_macro_conditions":        ["MANAGER", "RM"],
    "get_sector_alerts":           ["MANAGER", "RM"],

    # Content operations
    "generate_briefing":           ["MANAGER", "RM"],
    "generate_proposal":           ["MANAGER", "RM"],
    "generate_client_letter":      ["MANAGER", "RM"],

    # Compliance check
    "check_finra_2210_compliance": ["MANAGER", "RM", "OFFICER"],

    # Approval and archiving
    "approve_and_archive":         ["MANAGER", "RM"],   # RM approves own content
    "compliance_override":         ["OFFICER", "MANAGER"],  # Override compliance flag

    # Audit access
    "view_approval_audit_trail":   ["MANAGER", "OFFICER", "AUDITOR"],
    "export_client_output_history":["MANAGER", "OFFICER", "AUDITOR"],
}
```

---

## Step-by-Step Deployment

### Step 1: Deploy Infrastructure
```bash
cp terraform/customers/template.tfvars terraform/customers/first-national-bank-agent05.tfvars

# Key settings for Agent 05:
# - firm_name: "First National Bank Wealth Management"
# - form_crs_url: URL to firm's Form CRS PDF
# - crm_vendor: "salesforce" | "redtail" | "orion" | "tamarac" | "custom"
# - portfolio_system_vendor: "orion" | "advent" | "tamarac" | "fis_wealth" | "custom"
# - market_data_vendor: "morningstar" | "bloomberg" | "refinitiv" | "factset"
# - enable_agent03_kyc_integration: true  (if Agent 03 is deployed)
# - enable_erisa_checks: true
# - enable_reg_bi_documentation: true  (always true for broker-dealer)
# - document_retention_years: 6  (FINRA 4511 minimum)

cd terraform/customer-deployment
terraform init -backend-config="key=customers/first-national-bank/agent05/terraform.tfstate"
terraform apply -var-file="../customers/first-national-bank-agent05.tfvars"
# Takes ~9 minutes
```

### Step 2: Load Secrets
```bash
./scripts/load-customer-secrets.sh first-national-bank agent05 \
  --bedrock-region "us-east-1" \
  --crm-url "https://first-national-bank.salesforce.com" \
  --crm-key "..." \
  --portfolio-system-url "https://api.orion.com/v2" \
  --portfolio-system-key "..." \
  --market-data-url "https://api.morningstar.com/v2" \
  --market-data-key "..."
```

### Step 3: Configure AD Groups
```powershell
Add-ADGroupMember -Identity "GRP-Wealth-RMs" -Members "rm1", "rm2", "rm3", "rm4"
Add-ADGroupMember -Identity "GRP-Wealth-Managers" -Members "wealth.manager1"
Add-ADGroupMember -Identity "GRP-Compliance-Officers" -Members "compliance.officer1"
Add-ADGroupMember -Identity "GRP-AML-Auditors" -Members "internal.auditor"

# IMPORTANT: Verify these groups are NOT assigned to Agent 01, 02, 03 apps in Okta
# (by design — separation prevents co-mingling of AML and wealth data)
```

### Step 4: Configure Agent 03 Integration (If Deployed)
```bash
# If Agent 03 KYC/CDD is deployed, configure read-only KYC summary access
# Agent 05 gets a non-sensitive KYC summary — NOT full investigation data

aws secretsmanager put-secret-value \
  --secret-id /wealth-rm/first-national-bank/agent03-kyc-api-url \
  --secret-string "https://kyc-cdd-internal.first-national-bank.aws/kyc-summary"

# The KYC summary endpoint returns:
# - Customer risk tier (HIGH/MEDIUM/LOW) — available to RM
# - Document completeness status — "EDD required" flag for RM context
# - NOT: SAR history, watchlist hits, investigation details (tipping-off)
```

### Step 5: Load Firm Configuration
```bash
# Configure firm-specific Reg BI documentation templates
python scripts/configure-firm.py \
  --customer-id first-national-bank \
  --firm-name "First National Bank Wealth Management" \
  --form-crs-url "https://files.first-national-bank.com/form-crs.pdf" \
  --finra-crd "XXXXX" \
  --sec-registration "801-XXXXX" \
  --prohibited-securities "leveraged-etfs,inverse-etfs" \  # Firm-specific restrictions
  --conflict-disclosure-template "templates/conflict-disclosure.txt"
```

### Step 6: Smoke Test
```bash
./scripts/smoke-test.sh first-national-bank agent05

# Tests:
# ✓ Streamlit UI loads at port 8505
# ✓ RM auth works (Okta → Cognito → rm_role: RM in JWT)
# ✓ Manager auth works (rm_role: MANAGER)
# ✓ Client profile lookup succeeds (CRM MCP connector)
# ✓ Portfolio holdings retrieved (portfolio system MCP connector)
# ✓ Suitability check runs (Python-only — no Bedrock call in this node)
# ✓ UNSUITABLE recommendation blocked before draft creation
# ✓ SUITABLE recommendation proceeds to content drafting
# ✓ Claude Sonnet generates briefing/proposal draft
# ✓ FINRA 2210 compliance check catches test prohibited phrase
# ✓ RM approval gate works — approval archived to S3
# ✓ Audit trail written to DynamoDB with RM identity from JWT
# ✓ 18 U.S.C. § 1960 check: no SAR or investigation references in output
```

---

## Terraform Module Reference
```hcl
module "wealth_rm_copilot_customer" {
  source = "git::https://github.com/your-org/fsi-agents-terraform//modules/agent05"

  customer_id        = "first-national-bank"
  customer_full_name = "First National Bank"
  aws_region         = "us-east-1"
  firm_name          = "First National Bank Wealth Management"

  # LLM (Sonnet — client-facing content quality is paramount)
  llm_provider    = "bedrock"
  bedrock_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

  # Authentication
  cognito_okta_saml_metadata_url = "https://customer.okta.com/app/APP_ID/sso/saml/metadata"
  ad_groups = {
    wealth_rms           = "GRP-Wealth-RMs"
    wealth_managers      = "GRP-Wealth-Managers"
    compliance_officers  = "GRP-Compliance-Officers"
    auditors             = "GRP-AML-Auditors"
  }

  # Integrations
  crm_vendor              = "salesforce"
  portfolio_system_vendor = "orion"
  market_data_vendor      = "morningstar"

  # Agent 03 integration (optional)
  enable_agent03_kyc_integration = true
  agent03_kyc_summary_url       = "https://kyc-internal.aws/kyc-summary"  # Internal VPC URL

  # Compliance configuration
  enable_reg_bi_documentation = true
  enable_erisa_checks         = true
  enable_finra_2210_check     = true
  finra_crd_number            = "XXXXX"
  sec_registration_number     = "801-XXXXX"
  form_crs_url                = "https://files.first-national-bank.com/form-crs.pdf"

  # Firm-specific restrictions (Reg BI Conflict Obligation)
  prohibited_securities = ["leveraged-etfs", "inverse-etfs", "naked-options"]

  # Document retention (FINRA Rule 4511 / SEC Rule 204-2)
  document_retention_years = 6
  enable_guardduty         = true
}
```

---

## CloudWatch Monitoring

### Key Metrics Dashboard: "Wealth RM Copilot — Operations"
```
Row 1 — Usage
  [Requests Today by Type]  [Avg Pipeline Duration]  [RM Active Users]

Row 2 — Quality
  [Suitability Block Rate]  [FINRA 2210 Flag Rate]  [RM Modification Rate (vs. accept as-is)]

Row 3 — Compliance
  [Requests Approved Today]  [Pending RM Approval > 24hrs]  [Compliance Override Count]

Row 4 — AI Health
  [Bedrock Sonnet Latency P50/P95]  [Bedrock Error Rate]  [CRM Connector Success Rate]

Row 5 — Operational
  [S3 Archive Success Rate]  [DynamoDB Audit Write Success]  [Active Sessions]
```

### Key Alarms
```yaml
- Name: Suitability-Check-Error
  Threshold: Python suitability check error rate > 1%
  Action: Email → Compliance Officer + Engineering
  Reason: Suitability is Python-only — errors here are code bugs, not model errors

- Name: Pending-Approvals-Aging
  Threshold: Any RM request pending approval > 24 hours
  Action: Email → RM Manager
  Reason: RMs may have missed approval notification

- Name: Bedrock-Sonnet-Error-Rate-High
  Threshold: Error rate > 5% over 10 minutes
  Action: Email → ops team
  Reason: Content drafting unavailable — RMs cannot complete requests

- Name: S3-Archive-Failure
  Threshold: Any approved output not archived within 5 minutes
  Action: PagerDuty → ops team
  Reason: FINRA record-keeping requirement — approved content must be archived
```

---

## Cost Estimation

| Service | Configuration | Monthly Cost |
|---------|--------------|-------------|
| ECS Fargate (UI) | 1 task, 1vCPU/2GB | ~$30 |
| ECS Fargate (Workers) | Avg 2 tasks, 2vCPU/4GB | ~$120 |
| ECS Fargate (MCP Gateway + 5 servers) | 6 tasks, 0.5vCPU/1GB | ~$90 |
| ALB | 1 LB | ~$20 |
| RDS Aurora PostgreSQL | db.r6g.large, Multi-AZ | ~$250 |
| DynamoDB | On-demand, ~100K events/month | ~$3 |
| S3 (client documents, WORM) | 50 GB/month | ~$5 |
| Bedrock (Claude Sonnet) | 50 RMs × 10 requests/week × 8K tokens avg | ~$480 |
| Secrets Manager + KMS | ~10 secrets, ~5 CMKs | ~$15 |
| CloudWatch | Logs + metrics | ~$20 |
| ElastiCache Redis | cache.t3.small | ~$25 |
| **Total** | | **~$1,058/month** |

*Bedrock cost assumes 50 RMs × 10 requests/week × ~8,000 tokens per request (profile context + draft output). Scales linearly with RM count and usage frequency.*

*External data costs (CRM API calls, portfolio data feed, market data API) are billed separately by the data vendors — typically included in existing enterprise contracts.*
