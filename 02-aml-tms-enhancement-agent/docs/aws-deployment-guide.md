# AWS Deployment Guide: AML/TMS Enhancement Agent
## Enterprise Deployment Playbook — Pre-Queue False Positive Reduction

> **Suite context:** This agent deploys upstream of the Financial Crime Investigation Agent (Agent 01). It is commonly deployed first — it delivers measurable ROI fastest and requires no changes to existing TMS configuration or analyst workflows. See the [Suite Architecture](../../docs/SUITE-ARCHITECTURE.md) for the full platform picture.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   AML/TMS Enhancement Agent — AWS Architecture               │
│                                                                             │
│  CUSTOMER TMS (Actimize / Verafin / NICE / Oracle Mantas)                  │
│  Alert webhook → API Gateway → Lambda (normalizer) → SQS Alert Queue       │
│                                                          ↓                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    ECS Fargate Cluster                                 │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐  │ │
│  │  │  Streamlit UI   │  │  LangGraph Agent  │  │  MCP Auth Gateway   │  │ │
│  │  │  (Port 8502)    │  │  Worker           │  │  (Port 8443)        │  │ │
│  │  │  - Live Queue   │  │  13-node scoring  │  │  JWT validation     │  │ │
│  │  │  - FP Metrics   │  │  pipeline         │  │  Role-based authz   │  │ │
│  │  │  - Suppression  │  │  Pulls from SQS   │  │  Audit logging      │  │ │
│  │  │    Audit        │  │                   │  │                     │  │ │
│  │  │  - Threshold    │  │                   │  │                     │  │ │
│  │  │    Config       │  │                   │  │                     │  │ │
│  │  └─────────────────┘  └──────────────────┘  └─────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                    ↓                          ↓                             │
│  ┌──────────────────────┐     ┌───────────────────────────────────────┐    │
│  │  AWS Bedrock         │     │  MCP Tool Servers                     │    │
│  │  Claude Haiku        │     │  ├── TMS Connector (Port 8001)        │    │
│  │  (scoring pipeline)  │     │  └── Core Banking Connector (8002)   │    │
│  │  Claude Sonnet       │     └───────────────────────────────────────┘    │
│  │  (LLM analysis node) │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
│  DATA LAYER                                                                 │
│  RDS Aurora (scoring results · suppression records · threshold config)      │
│  DynamoDB (immutable audit trail — every routing decision logged)           │
│  ElastiCache Redis (JWKS cache · rate limiting · session state)             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AWS Service Configuration

### ECS Fargate Task Definitions

**UI Task (Streamlit Dashboard)**
```yaml
Family: tms-enhancement-ui
CPU: 1024      # 1 vCPU — UI serving, not compute-intensive
Memory: 2048   # 2 GB
NetworkMode: awsvpc
RequiresCompatibilities: [FARGATE]

Environment:
  - Name: PORT
    Value: "8502"
  - Name: CUSTOMER_ID
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/tms-enhancement/CUSTOMER_ID/customer-id
  - Name: DATABASE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/tms-enhancement/CUSTOMER_ID/db-url
  - Name: REDIS_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/tms-enhancement/CUSTOMER_ID/redis-url

HealthCheck:
  Command: ["CMD-SHELL", "curl -f http://localhost:8502/_stcore/health || exit 1"]
  Interval: 30
  Timeout: 5
  Retries: 3
```

**Agent Worker Task (LangGraph Scoring Pipeline)**
```yaml
Family: tms-enhancement-worker
CPU: 2048      # 2 vCPU — LangGraph graph traversal is CPU-intensive
Memory: 4096   # 4 GB — 13-node pipeline with full customer context
NetworkMode: awsvpc
RequiresCompatibilities: [FARGATE]

Environment:
  - Name: OPENAI_API_KEY           # or use Bedrock (recommended for production)
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/tms-enhancement/CUSTOMER_ID/llm-key
  - Name: AWS_BEDROCK_MODEL_SCORING
    Value: "anthropic.claude-haiku-4-5-20251001"  # Fast, low-cost for scoring
  - Name: AWS_BEDROCK_MODEL_ANALYSIS
    Value: "anthropic.claude-3-5-sonnet-20241022-v2:0"  # Full analysis node
  - Name: SQS_QUEUE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/tms-enhancement/CUSTOMER_ID/sqs-url

# Auto-scaling: scale based on SQS queue depth
# Target: 1 worker task per 50 queued alerts
# Min: 1 task (always available), Max: 30 tasks (burst capacity for alert storms)
```

### SQS Configuration
```yaml
AlertQueue:
  QueueName: tms-enhancement-CUSTOMER_ID-alerts.fifo
  FifoQueue: true
  ContentBasedDeduplication: true
  VisibilityTimeout: 180    # 3 minutes — max scoring pipeline duration
  MessageRetentionPeriod: 1209600  # 14 days
  KmsMasterKeyId: alias/tms-enhancement-CUSTOMER_ID-sqs

  RedrivePolicy:
    DeadLetterTargetArn: arn:aws:sqs:REGION:ACCOUNT:tms-enhancement-CUSTOMER_ID-dlq.fifo
    MaxReceiveCount: 3
    # Failed alerts → DLQ → CloudWatch alarm → BSA Officer notification
    # Regulatory: no alert can be silently discarded
```

### AWS Bedrock Configuration
```python
# In agent/nodes.py — LLM configuration for scoring pipeline

from langchain_aws import ChatBedrock

# High-speed scoring nodes (rule pre-scoring, composite calculation)
# Use Haiku: 10x cheaper than Sonnet, adequate for structured tasks
scoring_llm = ChatBedrock(
    model_id="anthropic.claude-haiku-4-5-20251001",
    model_kwargs={
        "temperature": 0.0,    # Zero temperature for deterministic scoring
        "max_tokens": 512,     # Short output for structured scoring decisions
    }
)

# LLM contextual analysis node — full customer context review
# Use Sonnet: higher quality reasoning for the 50%-weight analysis component
analysis_llm = ChatBedrock(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    model_kwargs={
        "temperature": 0.1,
        "max_tokens": 2048,    # Full contextual analysis narrative
    }
)
```

### RDS Aurora Configuration
```yaml
# Stores scoring results, suppression records, threshold configuration
# Lighter workload than Agent 01 — no case management
Cluster:
  Engine: aurora-postgresql
  EngineVersion: "15.4"
  DatabaseName: tms_enhancement_CUSTOMER_ID

  AvailabilityZones: [us-east-1a, us-east-1b]  # 2-AZ for cost efficiency

  StorageEncrypted: true
  KmsKeyId: alias/tms-enhancement-CUSTOMER_ID-rds

  BackupRetentionPeriod: 35

Instances:
  Writer:
    InstanceClass: db.r6g.large   # Adequate for scoring workloads
  # No reader for this agent (write-heavy, scoring pipeline)
```

---

## Identity & Access Management

This agent uses the same Cognito + Okta SAML + Active Directory pattern as Agent 01. Refer to the [Agent 01 AWS Deployment Guide](../../01-financial-crime-investigation-agent/docs/aws-deployment-guide.md) for the full Cognito and Okta configuration.

### Role Mapping for Agent 02

| AD Group | Cognito Claim | Permissions |
|----------|---------------|------------|
| `GRP-BSA-Officers` | `bsa_role: BSA_OFFICER` | Full access + threshold configuration + suppression override |
| `GRP-AML-Investigators` | `bsa_role: INVESTIGATOR` | View queue + view decisions + human override |
| `GRP-AML-Auditors` | `bsa_role: AUDITOR` | View suppression audit + read-only |

### Okta Application Configuration (Agent 02 Specific)
```yaml
Application:
  Name: "TMS Enhancement Agent - {CustomerName}"
  SignOnMethod: SAML 2.0

  SAML Settings:
    SingleSignOnURL: https://tms-enhancement-CUSTOMER_ID.auth.us-east-1.amazoncognito.com/saml2/idpresponse
    AudienceURI: urn:amazon:cognito:sp:COGNITO_POOL_ID_AGENT02

  AttributeStatements:
    - Name: bsa_role
      Value: |
        isMemberOf("GRP-BSA-Officers") ? "BSA_OFFICER" :
        isMemberOf("GRP-AML-Investigators") ? "INVESTIGATOR" :
        isMemberOf("GRP-AML-Auditors") ? "AUDITOR" :
        "READ_ONLY"

  # IMPORTANT: Only assign BSA/AML groups to this app
  # Do NOT assign GRP-Wealth-RMs or GRP-Fraud-Analysts — wrong application
  Assignments:
    Groups:
      - GRP-BSA-Officers
      - GRP-AML-Investigators
      - GRP-AML-Auditors
```

### MCP Tool Authorization (Agent 02)
```python
# Agents 02 only needs read access to TMS and core banking
# It does NOT have SAR generation or case filing permissions
TOOL_PERMISSIONS = {
    "get_alert_details":       ["BSA_OFFICER", "INVESTIGATOR"],
    "get_customer_profile":    ["BSA_OFFICER", "INVESTIGATOR"],
    "get_transaction_summary": ["BSA_OFFICER", "INVESTIGATOR"],
    "get_historical_fp_rates": ["BSA_OFFICER", "INVESTIGATOR"],

    # Threshold configuration — BSA Officer only
    "update_fp_threshold":     ["BSA_OFFICER"],
    "override_suppression":    ["BSA_OFFICER"],
    "approve_suppression_batch": ["BSA_OFFICER"],

    # Audit access
    "view_suppression_audit":  ["BSA_OFFICER", "AUDITOR", "INVESTIGATOR"],
    "export_suppression_report": ["BSA_OFFICER", "AUDITOR"],
}
```

---

## Step-by-Step Deployment

### Prerequisites
- Terraform ≥ 1.6.0
- AWS CLI configured for target account
- Docker Desktop (for local image builds)
- Customer's Okta SAML metadata URL
- TMS API credentials (Actimize, Verafin, etc.)

### Step 1: Deploy Shared Infrastructure (if Agent 01 not already deployed)
If deploying Agent 02 standalone (common for first-engagement deployments):
```bash
cd terraform/shared/ecr
terraform init && terraform apply
# Creates shared ECR repository for all agent Docker images
```

### Step 2: Configure Customer Variables
```bash
cp terraform/customers/template.tfvars terraform/customers/first-national-bank-agent02.tfvars

# Edit with customer-specific values:
# - customer_id: "first-national-bank"
# - cognito_okta_saml_metadata_url: from Okta app
# - tms_platform: "actimize" | "verafin" | "nice" | "mantas"
# - enable_core_banking_lookup: true (needed for customer context enrichment)
# - alert_volume_daily: 500 (used to size SQS and ECS auto-scaling)
# - suppress_threshold: 85 (BSA Officer can adjust in dashboard post-deploy)
# - escalate_threshold: 15 (below this → auto-escalate to Agent 01)
```

### Step 3: Deploy Infrastructure
```bash
cd terraform/customer-deployment
terraform init \
  -backend-config="key=customers/first-national-bank/agent02/terraform.tfstate"

terraform plan -var-file="../customers/first-national-bank-agent02.tfvars"
terraform apply
# Takes ~8 minutes (lighter stack than Agent 01 — no network graph DB)
```

### Step 4: Load Secrets
```bash
./scripts/load-customer-secrets.sh first-national-bank agent02 \
  --llm-key "sk-..." \
  --actimize-url "https://actimize.first-national-bank.com/api" \
  --actimize-key "..." \
  --core-banking-url "https://core.first-national-bank.com/api" \
  --core-banking-key "..."
```

### Step 5: Configure TMS Webhook (Alert Ingestion)
```bash
# Get API Gateway endpoint from Terraform output
terraform output alert_ingestion_endpoint
# → https://abc123.execute-api.us-east-1.amazonaws.com/prod/tms-alerts

# Provide this URL to the customer's TMS team
# They configure TMS to POST new alerts here
# Provide the webhook API key from Secrets Manager for authentication

# Alert payload schema the TMS must send:
# {
#   "alert_id": "TMS-2024-001234",
#   "customer_id": "CUST-789012",
#   "account_id": "ACC-456789",
#   "rule_id": "STR-001",
#   "rule_name": "Structuring Velocity",
#   "alert_amount": 9800.00,
#   "alert_date": "2024-01-15T10:30:00Z",
#   "transaction_ids": ["TXN-001", "TXN-002"],
#   "typology": "STRUCTURING"
# }
```

### Step 6: Configure BSA Officer Access via Okta/AD
```powershell
# Run on customer's AD Domain Controller
# Add BSA Officers (can configure thresholds, approve/override suppressions)
Add-ADGroupMember -Identity "GRP-BSA-Officers" -Members "bsa.officer1"

# Add AML Investigators (can view queue and decisions)
Add-ADGroupMember -Identity "GRP-AML-Investigators" -Members "analyst1", "analyst2"

# Add Auditors (read-only, suppression audit access)
Add-ADGroupMember -Identity "GRP-AML-Auditors" -Members "internal.auditor"
```

### Step 7: Calibrate Thresholds (BSA Officer Task)
After deployment, the BSA Officer should calibrate the FP thresholds before go-live:
```
1. Log in to the dashboard at https://tms-enhancement.customer.com
2. Navigate to "Threshold Configuration" tab
3. Review the default thresholds:
   - SUPPRESS: FP confidence ≥ 85%
   - DOWNGRADE: FP confidence ≥ 60%
   - PASS-THROUGH: FP confidence 15-60%
   - ESCALATE: FP confidence ≤ 15%
4. Run the scoring pipeline against a sample of known alerts
   (use historical data where disposition is known)
5. Adjust thresholds based on institution's risk appetite
6. Document threshold rationale in the system (required for SR 11-7)
```

### Step 8: Integration Validation
If deploying alongside Agent 01 (Financial Crime Investigation Agent):
```bash
# Verify escalation routing works end-to-end
# 1. Submit a test alert with FP score ≤ 15% (high-risk pattern)
# 2. Confirm it appears in Agent 01's queue marked as HIGH priority
# 3. Confirm the escalation includes the FP score and scoring rationale

# Test the routing in Agent 02's dashboard:
# - Load demo alert with structuring pattern → should ESCALATE (≤15% FP)
# - Load demo alert with known-good customer → should SUPPRESS (≥85% FP)
```

### Step 9: Smoke Test
```bash
./scripts/smoke-test.sh first-national-bank agent02

# Tests:
# ✓ Streamlit UI loads at port 8502
# ✓ Cognito authentication (Okta login flow)
# ✓ SQS can receive test alert via API Gateway
# ✓ Worker picks up alert and runs 13-node scoring pipeline
# ✓ Bedrock responds to both Haiku and Sonnet calls
# ✓ TMS Connector MCP server reaches TMS API
# ✓ Core Banking MCP server reaches customer profile API
# ✓ Routing decision logged to DynamoDB audit trail
# ✓ Scoring result written to Aurora PostgreSQL
# ✓ CloudWatch metrics flowing (queue depth, processing time, routing breakdown)
```

---

## Terraform Module Reference
```hcl
module "tms_enhancement_customer" {
  source = "git::https://github.com/your-org/fsi-agents-terraform//modules/agent02"

  customer_id        = "first-national-bank"
  customer_full_name = "First National Bank"
  aws_region         = "us-east-1"

  # Sizing
  ecs_worker_min_tasks = 1
  ecs_worker_max_tasks = 30      # 1 task per 50 queued alerts
  alert_volume_daily   = 500    # Used to size auto-scaling targets

  # LLM
  llm_provider              = "bedrock"
  bedrock_scoring_model_id  = "anthropic.claude-haiku-4-5-20251001"
  bedrock_analysis_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

  # Authentication
  cognito_okta_saml_metadata_url = "https://customer.okta.com/app/APP_ID/sso/saml/metadata"
  ad_group_bsa_officers   = "GRP-BSA-Officers"
  ad_group_investigators  = "GRP-AML-Investigators"
  ad_group_auditors       = "GRP-AML-Auditors"

  # TMS Integration
  tms_platform            = "actimize"    # actimize | verafin | nice | mantas
  enable_core_banking     = true

  # Routing Thresholds (adjustable post-deploy by BSA Officer in dashboard)
  default_suppress_threshold  = 85
  default_downgrade_threshold = 60
  default_escalate_threshold  = 15

  # If Agent 01 is deployed — enable escalation routing
  enable_agent01_escalation    = true
  agent01_sqs_queue_url        = "arn:aws:sqs:us-east-1:ACCOUNT:fcia-first-national-bank-alerts.fifo"
  agent01_escalation_priority  = "HIGH"

  # Compliance
  audit_retention_years = 5
  enable_guardduty      = true
  enable_security_hub   = true
}
```

---

## CloudWatch Monitoring

### Key Metrics Dashboard: "TMS Enhancement — Operations"
```
Row 1 — Queue & Throughput
  [SQS Alert Queue Depth]  [Alerts Processed/Hour]  [Avg Scoring Duration (ms)]

Row 2 — Routing Outcomes
  [SUPPRESS Rate %]  [DOWNGRADE Rate %]  [PASS-THROUGH Rate %]  [ESCALATE Rate %]

Row 3 — AI Health
  [Bedrock Haiku Latency P50/P95]  [Bedrock Sonnet Latency P50/P95]  [LLM Error Rate]

Row 4 — Integration Health
  [TMS Connector Success Rate]  [Core Banking Connector Success Rate]  [DLQ Depth]

Row 5 — ROI Tracking
  [Analyst Hours Saved (Est.)]  [FP Suppression Count]  [Escalation Count (to Agent 01)]
```

### Critical Alarms
```yaml
- Name: DLQ-Has-Messages
  Threshold: > 0
  Action: PagerDuty → BSA Officer
  Reason: Alert failed scoring 3x — requires investigation

- Name: FP-Suppress-Rate-Anomaly
  Threshold: Suppress rate > 95% or < 20% over 1-hour window
  Action: Email → BSA Officer
  Reason: Unexpected change in FP rate may indicate model drift or TMS tuning change

- Name: LLM-Error-Rate-High
  Threshold: Bedrock error rate > 5% over 5 minutes
  Action: Email → ops team
  Reason: Degraded scoring quality — alerts still processed via rule-only fallback

- Name: Escalation-Spike
  Threshold: Escalation rate > 20% over 1 hour (vs. baseline ≤5%)
  Action: Email → BSA Officer + AML team lead
  Reason: Unusual pattern of high-risk alerts — may indicate coordinated activity
```

---

## Cost Estimation

| Service | Configuration | Monthly Cost |
|---------|--------------|-------------|
| ECS Fargate (UI) | 1 task, 0.5vCPU/1GB | ~$15 |
| ECS Fargate (Workers) | Avg 2 tasks, 2vCPU/4GB | ~$120 |
| ECS Fargate (MCP Gateway + 2 servers) | 3 tasks, 0.5vCPU/1GB | ~$45 |
| ALB | 1 LB, ~50K req/day | ~$20 |
| RDS Aurora PostgreSQL | db.r6g.large, 2-AZ | ~$200 |
| DynamoDB | On-demand, ~500K events/month | ~$8 |
| SQS | ~15K messages/month | ~$1 |
| Bedrock (Claude Haiku) | 500 alerts/day × 1K tokens avg | ~$150 |
| Bedrock (Claude Sonnet) | 500 alerts/day × 3K tokens avg | ~$450 |
| Secrets Manager + KMS | ~10 secrets, ~5 CMKs | ~$15 |
| CloudWatch | Logs + metrics + dashboards | ~$25 |
| ElastiCache Redis | cache.t3.micro | ~$15 |
| **Total** | | **~$1,064/month** |

*Bedrock cost is the primary variable. At 500 alerts/day, ~60% processed by Haiku (scoring nodes), ~40% by Sonnet (LLM analysis). Adjust based on actual alert volume.*
