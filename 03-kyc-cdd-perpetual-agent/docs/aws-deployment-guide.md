# AWS Deployment Guide: KYC/CDD Perpetual Monitoring Agent
## Enterprise Deployment Playbook — Perpetual KYC at Scale

> **Suite context:** This agent runs the customer due diligence lifecycle. It is triggered by risk events — including findings from the Financial Crime Investigation Agent (Agent 01) — and feeds updated risk ratings back to the AML agents. See the [Suite Architecture](../../docs/SUITE-ARCHITECTURE.md) for the full platform picture.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                KYC/CDD Perpetual Monitoring Agent — AWS Architecture         │
│                                                                             │
│  TRIGGER SOURCES:                                                           │
│  ├── Agent 01 (SAR filed, high risk confirmed)                             │
│  ├── Agent 04 (Fraud pattern detected)                                      │
│  ├── Watchlist Service (OFAC/PEP hit)                                      │
│  ├── TMS (Transaction anomaly)                                              │
│  ├── Scheduled Review (Annual/Biennial/Triennial per risk tier)            │
│  └── Manual trigger (BSA Officer, RM, Compliance Officer)                  │
│                   ↓                                                         │
│  API Gateway → Lambda (trigger normalizer) → SQS Review Queue              │
│                   ↓                                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    ECS Fargate Cluster                                 │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐  │ │
│  │  │  Streamlit UI   │  │  LangGraph Agent  │  │  MCP Auth Gateway   │  │ │
│  │  │  (Port 8503)    │  │  Worker           │  │  (Port 8443)        │  │ │
│  │  │  - Review Queue │  │  9-12 node CDD    │  │  JWT validation     │  │ │
│  │  │  - Risk Assess. │  │  refresh workflow │  │  Role-based authz   │  │ │
│  │  │  - EDD Package  │  │  Pulls from SQS   │  │  Audit logging      │  │ │
│  │  │  - Compliance   │  │                   │  │                     │  │ │
│  │  │    Review       │  │                   │  │                     │  │ │
│  │  │  - Audit Trail  │  │                   │  │                     │  │ │
│  │  └─────────────────┘  └──────────────────┘  └─────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                    ↓                          ↓                             │
│  ┌──────────────────────┐     ┌───────────────────────────────────────┐    │
│  │  AWS Bedrock         │     │  MCP Tool Servers                     │    │
│  │  Claude Sonnet       │     │  ├── Core Banking / KYC (Port 8002)  │    │
│  │  (EDD packages,      │     │  ├── Watchlist Screener (Port 8003)  │    │
│  │  risk narratives,    │     │  ├── Adverse Media (Port 8004)       │    │
│  │  RM communications)  │     │  └── Network Intelligence (Port 8005)│    │
│  └──────────────────────┘     └───────────────────────────────────────┘    │
│                                                                             │
│  DATA LAYER                                                                 │
│  RDS Aurora (KYC reviews · risk ratings · EDD records · trigger history)   │
│  DynamoDB (immutable audit trail — every review decision, every override)   │
│  S3 Object Lock (EDD packages · review documentation — WORM)               │
│  ElastiCache Redis (JWKS cache · rate limiting · review state)              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AWS Service Configuration

### ECS Fargate Task Definitions

**Agent Worker Task (KYC/CDD Refresh Pipeline)**
```yaml
Family: kyc-cdd-worker
CPU: 2048      # 2 vCPU — multi-step review with external API calls
Memory: 4096   # 4 GB — full customer profile + document analysis in context
NetworkMode: awsvpc
RequiresCompatibilities: [FARGATE]

Environment:
  - Name: BEDROCK_MODEL_ID
    Value: "anthropic.claude-3-5-sonnet-20241022-v2:0"
    # Sonnet for all nodes — EDD packages need high-quality, citation-accurate output
  - Name: SQS_QUEUE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/kyc-cdd/CUSTOMER_ID/sqs-url
  - Name: DATABASE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/kyc-cdd/CUSTOMER_ID/db-url
  - Name: CUSTOMER_ID
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/kyc-cdd/CUSTOMER_ID/customer-id

HealthCheck:
  Command: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
  Interval: 30
  Timeout: 5
  Retries: 3

# Scaling: KYC reviews are not real-time — 1-5 minute completion acceptable
# Scale: 1 task minimum, up to 10 tasks during bulk review processing
```

### SQS Configuration
```yaml
ReviewQueue:
  QueueName: kyc-cdd-CUSTOMER_ID-reviews.fifo
  FifoQueue: true
  VisibilityTimeout: 600    # 10 minutes — EDD review workflows take longer
  MessageRetentionPeriod: 1209600  # 14 days
  KmsMasterKeyId: alias/kyc-cdd-CUSTOMER_ID-sqs

  # Message attributes for priority routing
  # WATCHLIST_HIT → 3-day deadline (highest urgency)
  # SAR_FILED → 7-day deadline
  # SCHEDULED → 60-day window

  RedrivePolicy:
    DeadLetterTargetArn: arn:aws:sqs:REGION:ACCOUNT:kyc-cdd-CUSTOMER_ID-dlq.fifo
    MaxReceiveCount: 3

# EventBridge Scheduler — triggers scheduled reviews based on risk tier
# HIGH risk: annual review (trigger 30 days before anniversary)
# MEDIUM risk: biennial review
# LOW risk: triennial review
EventBridgeScheduler:
  HighRiskReviewSchedule:
    ScheduleExpression: "rate(1 day)"
    Target: Lambda (scans RDS for customers with upcoming review dates → enqueues)
```

### S3 Configuration (EDD Document Storage)
```yaml
EDDDocuments:
  BucketName: kyc-cdd-CUSTOMER_ID-edd-documents
  VersioningConfiguration: Enabled

  # WORM for completed EDD packages (immutable once compliance officer approves)
  ObjectLockConfiguration:
    ObjectLockEnabled: Enabled
    Rule:
      DefaultRetention:
        Mode: GOVERNANCE    # 5-year BSA retention; COMPLIANCE if required by contract
        Years: 5

  BucketEncryption:
    ServerSideEncryptionConfiguration:
      - ServerSideEncryptionByDefault:
          SSEAlgorithm: aws:kms
          KMSMasterKeyId: alias/kyc-cdd-CUSTOMER_ID-s3

  # Lifecycle: archive older EDD packages to Glacier
  LifecycleConfiguration:
    Rules:
      - Status: Enabled
        Transitions:
          - Days: 365
            StorageClass: GLACIER
          - Days: 1825   # 5 years
            StorageClass: DEEP_ARCHIVE
```

---

## Identity & Access Management

### Role Mapping for Agent 03

| AD Group | Cognito Claim | Permissions |
|----------|---------------|------------|
| `GRP-BSA-Officers` | `bsa_role: BSA_OFFICER` | Full access + risk rating changes + EDD approval |
| `GRP-Compliance-Officers` | `compliance_role: OFFICER` | Review and approve CDD refreshes, override risk ratings |
| `GRP-AML-Investigators` | `bsa_role: INVESTIGATOR` | Trigger manual reviews, view risk profiles |
| `GRP-Wealth-RMs` | `rm_role: RM` | View RM notification queue, acknowledge EDD requests |
| `GRP-AML-Auditors` | `bsa_role: AUDITOR` | Full read-only access to all reviews and audit trails |

### Okta Application Configuration (Agent 03 Specific)
```yaml
Application:
  Name: "KYC/CDD Perpetual Monitoring - {CustomerName}"
  SignOnMethod: SAML 2.0

  SAML Settings:
    SingleSignOnURL: https://kyc-cdd-CUSTOMER_ID.auth.us-east-1.amazoncognito.com/saml2/idpresponse
    AudienceURI: urn:amazon:cognito:sp:COGNITO_POOL_ID_AGENT03

  AttributeStatements:
    - Name: bsa_role
      Value: |
        isMemberOf("GRP-BSA-Officers") ? "BSA_OFFICER" :
        isMemberOf("GRP-AML-Investigators") ? "INVESTIGATOR" :
        isMemberOf("GRP-AML-Auditors") ? "AUDITOR" :
        "READ_ONLY"
    - Name: compliance_role
      Value: |
        isMemberOf("GRP-Compliance-Officers") ? "OFFICER" : ""
    - Name: rm_role
      Value: |
        isMemberOf("GRP-Wealth-RMs") ? "RM" : ""

  Assignments:
    Groups:
      - GRP-BSA-Officers
      - GRP-Compliance-Officers
      - GRP-AML-Investigators
      - GRP-Wealth-RMs       # For RM notification acknowledgment
      - GRP-AML-Auditors
```

### MCP Tool Authorization (Agent 03)
```python
TOOL_PERMISSIONS = {
    # Read operations — available to all authenticated users
    "get_customer_kyc_profile":   ["BSA_OFFICER", "INVESTIGATOR", "OFFICER", "RM", "AUDITOR"],
    "get_beneficial_owners":      ["BSA_OFFICER", "INVESTIGATOR", "OFFICER", "AUDITOR"],
    "screen_entity_watchlist":    ["BSA_OFFICER", "INVESTIGATOR", "OFFICER"],
    "search_adverse_media":       ["BSA_OFFICER", "INVESTIGATOR", "OFFICER"],
    "get_entity_network":         ["BSA_OFFICER", "INVESTIGATOR", "OFFICER"],

    # Write operations — compliance-sensitive
    "update_customer_risk_rating": ["BSA_OFFICER", "OFFICER"],      # Only officers
    "generate_edd_package":        ["BSA_OFFICER", "INVESTIGATOR", "OFFICER"],
    "send_rm_notification":        ["BSA_OFFICER", "OFFICER"],
    "close_review_case":           ["BSA_OFFICER", "OFFICER"],

    # RM-specific
    "acknowledge_edd_request":     ["RM", "BSA_OFFICER"],
    "view_rm_queue":               ["RM", "BSA_OFFICER", "OFFICER"],

    # Audit
    "view_review_audit_trail":     ["BSA_OFFICER", "OFFICER", "AUDITOR"],
    "export_review_history":       ["BSA_OFFICER", "OFFICER", "AUDITOR"],
}
```

---

## Step-by-Step Deployment

### Step 1: Deploy Infrastructure
```bash
cp terraform/customers/template.tfvars terraform/customers/first-national-bank-agent03.tfvars

# Key settings to configure:
# - customer_id
# - cognito_okta_saml_metadata_url
# - kyc_system_vendor: "fis" | "fiserv" | "jack_henry" | "temenos" | "custom"
# - watchlist_vendor: "worldcheck" | "complyadvantage" | "lexisnexis_bridger"
# - adverse_media_vendor: "dowjones" | "lexisnexis_nexis"
# - enable_network_intelligence: true/false (Sayari or OpenCorporates)
# - enable_rm_notifications: true (if Agent 05 Wealth Copilot is deployed)
# - scheduled_review_lambda: true (enables EventBridge for automated periodic triggers)

cd terraform/customer-deployment
terraform init -backend-config="key=customers/first-national-bank/agent03/terraform.tfstate"
terraform apply -var-file="../customers/first-national-bank-agent03.tfvars"
# Takes ~10 minutes
```

### Step 2: Load Secrets
```bash
./scripts/load-customer-secrets.sh first-national-bank agent03 \
  --llm-key "bedrock"  \          # or "sk-..." for OpenAI
  --kyc-system-url "https://kyc.first-national-bank.com/api" \
  --kyc-system-key "..." \
  --worldcheck-key "..." \
  --worldcheck-secret "..." \
  --dowjones-token "..." \
  --sayari-key "..."  # optional — network intelligence
```

### Step 3: Configure AD Groups
```powershell
# Run on AD Domain Controller
Add-ADGroupMember -Identity "GRP-BSA-Officers" -Members "bsa.officer1"
Add-ADGroupMember -Identity "GRP-Compliance-Officers" -Members "compliance.officer1"
Add-ADGroupMember -Identity "GRP-AML-Investigators" -Members "kyc.analyst1"
Add-ADGroupMember -Identity "GRP-Wealth-RMs" -Members "rm1", "rm2", "rm3"
Add-ADGroupMember -Identity "GRP-AML-Auditors" -Members "internal.auditor"
```

### Step 4: Configure Agent 01 Integration (Cross-Agent Event Routing)
If Agent 01 (Financial Crime Investigation) is already deployed, configure event routing so that SAR filings and high-risk confirmations automatically trigger KYC reviews:
```bash
# In Agent 01's environment — add Agent 03's SQS queue URL
aws secretsmanager update-secret \
  --secret-id /fcia/first-national-bank/kyc-trigger-queue \
  --secret-string "https://sqs.us-east-1.amazonaws.com/ACCOUNT/kyc-cdd-first-national-bank-reviews.fifo"

# Agent 01's finalize_case node will automatically enqueue a KYC trigger
# when a SAR is filed or a customer is confirmed high-risk
```

### Step 5: Load Initial Customer Risk Tier Data
```bash
# Import existing risk ratings from core banking/KYC system
# This bootstraps the periodic review scheduler
python scripts/import-risk-tiers.py \
  --customer-id first-national-bank \
  --source-system fis \
  --api-url "https://core.first-national-bank.com/api" \
  --api-key "..."
# Creates baseline review schedules for all HIGH/MEDIUM/LOW customers
```

### Step 6: Smoke Test
```bash
./scripts/smoke-test.sh first-national-bank agent03

# Tests:
# ✓ Streamlit UI loads at port 8503
# ✓ Cognito / Okta authentication works for BSA Officer, Compliance Officer, RM roles
# ✓ Manual trigger creates review record in queue
# ✓ Worker picks up review and runs CDD refresh pipeline
# ✓ Watchlist screening returns result (no cached hits)
# ✓ Adverse media search completes
# ✓ Risk rescoring produces weighted 8-factor output
# ✓ EDD package generated and uploaded to S3
# ✓ RM notification drafted
# ✓ Compliance Officer review gate works
# ✓ Audit trail written to DynamoDB
# ✓ EventBridge scheduled review trigger fires correctly
```

---

## Terraform Module Reference
```hcl
module "kyc_cdd_customer" {
  source = "git::https://github.com/your-org/fsi-agents-terraform//modules/agent03"

  customer_id        = "first-national-bank"
  customer_full_name = "First National Bank"
  aws_region         = "us-east-1"

  # LLM (Sonnet for all nodes — EDD quality is critical)
  llm_provider    = "bedrock"
  bedrock_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

  # Authentication
  cognito_okta_saml_metadata_url = "https://customer.okta.com/app/APP_ID/sso/saml/metadata"
  ad_groups = {
    bsa_officers         = "GRP-BSA-Officers"
    compliance_officers  = "GRP-Compliance-Officers"
    investigators        = "GRP-AML-Investigators"
    wealth_rms           = "GRP-Wealth-RMs"
    auditors             = "GRP-AML-Auditors"
  }

  # Integrations
  kyc_system_vendor          = "fis"
  watchlist_vendor           = "worldcheck"
  adverse_media_vendor       = "dowjones"
  enable_network_intelligence = true
  enable_rm_notifications    = true    # Requires Agent 05 or email fallback

  # Cross-agent integration
  agent01_sar_event_source   = "arn:aws:sqs:us-east-1:ACCOUNT:fcia-first-national-bank-alerts.fifo"
  # Agent 01 enqueues KYC trigger events here when SAR is filed

  # Review scheduling
  enable_scheduled_reviews   = true
  high_risk_review_days      = 365     # Annual
  medium_risk_review_days    = 730     # Biennial
  low_risk_review_days       = 1095    # Triennial

  # Compliance
  edd_document_retention_years = 5
  audit_retention_years        = 5
  enable_guardduty             = true
}
```

---

## Cost Estimation

| Service | Configuration | Monthly Cost |
|---------|--------------|-------------|
| ECS Fargate (UI) | 1 task, 1vCPU/2GB | ~$30 |
| ECS Fargate (Workers) | Avg 2 tasks, 2vCPU/4GB | ~$120 |
| ECS Fargate (MCP Gateway + 4 servers) | 5 tasks, 0.5vCPU/1GB | ~$75 |
| ALB | 1 LB | ~$20 |
| Lambda (review scheduler) | EventBridge-triggered | ~$2 |
| RDS Aurora PostgreSQL | db.r6g.large, Multi-AZ | ~$250 |
| DynamoDB | ~200K audit events/month | ~$3 |
| S3 (EDD documents + archive) | 20 GB/month | ~$5 |
| SQS | ~2K reviews/month | ~$1 |
| Bedrock (Claude Sonnet) | 2K reviews × 10K tokens avg | ~$300 |
| Secrets Manager + KMS | ~12 secrets, ~5 CMKs | ~$15 |
| CloudWatch | Logs + metrics | ~$20 |
| ElastiCache Redis | cache.t3.micro | ~$15 |
| **Total** | | **~$856/month** |

*Lower Bedrock cost than Agents 01/02 because KYC reviews are lower volume (2K/month vs. daily alert scoring). Watchlist and adverse media vendor API costs are external to AWS billing.*
