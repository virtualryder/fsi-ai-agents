# AWS Deployment Guide: Real-Time Fraud Detection Agent
## Enterprise Deployment Playbook — Sub-200ms Payment Fraud Prevention

> **Suite context:** This agent runs in parallel to the AML financial crime loop (Agents 01-03). Fraud patterns that suggest money laundering layering are flagged as SAR candidates and routed to Agent 01. See the [Suite Architecture](../../docs/SUITE-ARCHITECTURE.md) for the full platform picture.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             Real-Time Fraud Detection Agent — AWS Architecture               │
│                                                                             │
│  TRANSACTION STREAMS:                                                       │
│  ├── Core Banking (wire, ACH, internal transfers)                          │
│  ├── Card Networks (Visa/MC authorization stream)                           │
│  ├── Digital Banking (mobile, web, API-initiated payments)                 │
│  └── Fraud Management System (manual review queue integration)             │
│                   ↓                                                         │
│  API Gateway (low-latency) → SQS Transaction Queue                         │
│                   ↓                                                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    ECS Fargate Cluster                                 │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐  │ │
│  │  │  Streamlit UI   │  │  LangGraph Agent  │  │  MCP Auth Gateway   │  │ │
│  │  │  (Port 8504)    │  │  Worker           │  │  (Port 8443)        │  │ │
│  │  │  - Transaction  │  │  14-node DAG:     │  │  JWT validation     │  │ │
│  │  │    Input        │  │  REAL-TIME PATH:  │  │  Role-based authz   │  │ │
│  │  │  - Detection    │  │  intake→context   │  │  Audit logging      │  │ │
│  │  │    Pipeline     │  │  →features→rules  │  │                     │  │ │
│  │  │  - Fraud Score  │  │  ASYNC PATH:      │  │                     │  │ │
│  │  │  - Decision &   │  │  device→behavioral│  │                     │  │ │
│  │  │    Evidence     │  │  →LLM→composite   │  │                     │  │ │
│  │  │  - Analyst Rev. │  │  →routing         │  │                     │  │ │
│  │  │  - Audit Trail  │  │                   │  │                     │  │ │
│  │  └─────────────────┘  └──────────────────┘  └─────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                    ↓                          ↓                             │
│  ┌──────────────────────┐     ┌───────────────────────────────────────┐    │
│  │  AWS Bedrock         │     │  MCP Tool Servers                     │    │
│  │  Claude Haiku        │     │  ├── Core Banking Connector (8002)   │    │
│  │  (real-time path:    │     │  ├── Device Intelligence (8008)      │    │
│  │  rules + features)   │     │  ├── Behavioral Analytics (8009)     │    │
│  │  Claude Sonnet       │     │  └── Fraud Network Graph (8010)      │    │
│  │  (LLM synthesis,     │     └───────────────────────────────────────┘    │
│  │  Reg E drafting)     │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
│  DATA LAYER                                                                 │
│  RDS Aurora (fraud cases · Reg E records · analyst determinations)          │
│  DynamoDB (immutable audit trail · every scoring decision · every BLOCK)    │
│  ElastiCache Redis (account velocity state · session data · JWKS)           │
│  S3 (Reg E documentation · case evidence packages)                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Critical Architecture Note: Dual-Path Design

The fraud agent runs two execution paths:

**Real-Time Path (<200ms)**
Handles the immediate block/allow decision for payment authorization. Must complete within card network response time windows.
```
Transaction intake → Account context (Redis cache) → Feature extraction → Rule engine prescoring
→ Routing: BLOCK immediately if hard block trigger, else → Async path
```

**Async Enrichment Path**
Runs after the initial authorization response, enriches the fraud picture for analyst review:
```
Device intelligence → Behavioral analysis → LLM fraud synthesis → Composite scoring
→ Routing: Update case status · Analyst queue · SAR flag if needed
```

### ECS Task Configuration for Dual-Path

```yaml
# Task 1: Real-Time Processor (latency-critical)
Family: fraud-detection-realtime
CPU: 4096      # 4 vCPU — latency-critical path must not be CPU-starved
Memory: 8192   # 8 GB — account velocity state in memory
NetworkMode: awsvpc

# Provisioned concurrency — no cold starts acceptable for real-time path
# Use Provisioned Fargate tasks (always warm)
CapacityProviderStrategy:
  CapacityProvider: FARGATE   # Always-running, not spot

# Real-time path models
Environment:
  - Name: BEDROCK_REALTIME_MODEL
    Value: "anthropic.claude-haiku-4-5-20251001"  # Sub-50ms inference
  - Name: SQS_REALTIME_QUEUE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/fraud/CUSTOMER_ID/realtime-sqs
  - Name: REDIS_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/fraud/CUSTOMER_ID/redis-url
  - Name: RESPONSE_DEADLINE_MS
    Value: "150"   # 150ms budget — 50ms buffer before network response window

# Task 2: Async Enrichment Processor
Family: fraud-detection-async
CPU: 2048
Memory: 4096
# Use FARGATE_SPOT for async tasks (non-latency-critical, 70% cheaper)
CapacityProviderStrategy:
  CapacityProvider: FARGATE_SPOT
  Weight: 80
  Base: 1       # 1 non-spot always-on

Environment:
  - Name: BEDROCK_ASYNC_MODEL
    Value: "anthropic.claude-3-5-sonnet-20241022-v2:0"  # Quality LLM synthesis
  - Name: SQS_ASYNC_QUEUE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:/fraud/CUSTOMER_ID/async-sqs
```

### SQS Configuration (Two Queues)
```yaml
# Queue 1: Real-time authorization decisions (FIFO, high-priority)
RealtimeQueue:
  QueueName: fraud-CUSTOMER_ID-realtime.fifo
  FifoQueue: true
  VisibilityTimeout: 10     # 10 seconds — must complete before payment times out
  MessageRetentionPeriod: 300  # 5 minutes — stale real-time decisions are invalid
  KmsMasterKeyId: alias/fraud-CUSTOMER_ID-sqs

# Queue 2: Async enrichment (standard, lower priority)
AsyncQueue:
  QueueName: fraud-CUSTOMER_ID-async
  VisibilityTimeout: 300    # 5 minutes — full enrichment pipeline
  MessageRetentionPeriod: 3600   # 1 hour
  RedrivePolicy:
    DeadLetterTargetArn: arn:aws:sqs:...:fraud-CUSTOMER_ID-async-dlq
    MaxReceiveCount: 3
```

### ElastiCache Redis (Account Velocity State)
```yaml
# Redis is critical for the real-time path — account velocity counters
# must be accessible in <5ms to meet the 150ms budget
CacheCluster:
  Engine: redis
  EngineVersion: "7.0"
  NodeType: cache.r6g.large    # Upgrade from t3 — real-time path needs low latency
  # Multi-AZ for high availability (payment blocking cannot go down)
  ReplicationGroupId: fraud-CUSTOMER_ID-velocity
  NumCacheClusters: 2    # 1 primary + 1 replica

# Velocity counters stored in Redis:
# fraud:velocity:{account_id}:txn_count_1h  → transaction count in last hour
# fraud:velocity:{account_id}:txn_amount_1h → transaction amount in last hour
# fraud:velocity:{account_id}:new_payees_24h → new payees in last 24 hours
# fraud:device:{device_fingerprint}:seen    → device first/last seen timestamps
# fraud:ip:{ip_hash}:reputation            → IP reputation (cached 15 min)
```

---

## Identity & Access Management

### Role Mapping for Agent 04

| AD Group | Cognito Claim | Permissions |
|----------|---------------|------------|
| `GRP-Fraud-Analysts` | `fraud_role: ANALYST` | Review flagged transactions, make fraud determinations |
| `GRP-Fraud-Managers` | `fraud_role: MANAGER` | All analyst permissions + rule configuration + threshold adjustment |
| `GRP-BSA-Officers` | `bsa_role: BSA_OFFICER` | SAR flag review + cross-AML access |
| `GRP-AML-Auditors` | `bsa_role: AUDITOR` | Full read-only access + audit trail |
| `GRP-Compliance-Officers` | `compliance_role: OFFICER` | Reg E documentation review |

### Okta Application Configuration (Agent 04 Specific)
```yaml
Application:
  Name: "Real-Time Fraud Detection - {CustomerName}"
  SignOnMethod: SAML 2.0

  SAML Settings:
    SingleSignOnURL: https://fraud-detection-CUSTOMER_ID.auth.us-east-1.amazoncognito.com/saml2/idpresponse
    AudienceURI: urn:amazon:cognito:sp:COGNITO_POOL_ID_AGENT04

  AttributeStatements:
    - Name: fraud_role
      Value: |
        isMemberOf("GRP-Fraud-Managers") ? "MANAGER" :
        isMemberOf("GRP-Fraud-Analysts") ? "ANALYST" :
        "READ_ONLY"
    - Name: bsa_role
      Value: |
        isMemberOf("GRP-BSA-Officers") ? "BSA_OFFICER" :
        isMemberOf("GRP-AML-Auditors") ? "AUDITOR" :
        ""
    - Name: compliance_role
      Value: |
        isMemberOf("GRP-Compliance-Officers") ? "OFFICER" : ""

  Assignments:
    Groups:
      - GRP-Fraud-Analysts
      - GRP-Fraud-Managers
      - GRP-BSA-Officers      # For SAR cross-referencing
      - GRP-Compliance-Officers  # For Reg E review
      - GRP-AML-Auditors
```

### MCP Tool Authorization (Agent 04)
```python
TOOL_PERMISSIONS = {
    # Transaction and account data
    "get_account_context":        ["MANAGER", "ANALYST", "BSA_OFFICER"],
    "get_transaction_history":    ["MANAGER", "ANALYST", "BSA_OFFICER"],
    "get_velocity_counters":      ["MANAGER", "ANALYST"],

    # Device and behavioral intelligence
    "get_device_intelligence":    ["MANAGER", "ANALYST"],
    "get_behavioral_profile":     ["MANAGER", "ANALYST"],
    "get_ip_reputation":          ["MANAGER", "ANALYST"],

    # Decision actions
    "block_transaction":          ["MANAGER"],   # Manager-only block confirmation
    "step_up_authentication":     ["MANAGER", "ANALYST"],
    "generate_reg_e_disclosure":  ["MANAGER", "ANALYST"],

    # SAR flagging (requires BSA role)
    "flag_for_sar_review":        ["BSA_OFFICER", "MANAGER"],
    "route_to_agent01":           ["BSA_OFFICER", "MANAGER"],  # AML escalation

    # Analyst review
    "confirm_fraud":              ["MANAGER", "ANALYST"],
    "clear_false_positive":       ["MANAGER", "ANALYST"],
    "close_case":                 ["MANAGER"],

    # Audit and reporting
    "view_fraud_audit_trail":     ["MANAGER", "ANALYST", "BSA_OFFICER", "AUDITOR"],
    "export_case_evidence":       ["MANAGER", "BSA_OFFICER", "AUDITOR"],
    "view_reg_e_documentation":   ["MANAGER", "OFFICER", "AUDITOR"],
}
```

---

## Step-by-Step Deployment

### Step 1: Deploy Infrastructure
```bash
cp terraform/customers/template.tfvars terraform/customers/first-national-bank-agent04.tfvars

# Key settings for Agent 04:
# - transaction_volume_daily: 500000  (drives SQS sizing and auto-scaling)
# - realtime_latency_budget_ms: 150   (SLA for real-time path)
# - card_network: "visa" | "mastercard" | "both" | "none"
# - enable_ach_fraud: true
# - enable_wire_fraud: true
# - enable_card_not_present: true
# - enable_account_takeover: true
# - enable_elder_financial_exploitation: true

cd terraform/customer-deployment
terraform init -backend-config="key=customers/first-national-bank/agent04/terraform.tfstate"
terraform apply -var-file="../customers/first-national-bank-agent04.tfvars"
# Takes ~12 minutes (Redis cluster creation is the slowest component)
```

### Step 2: Load Secrets
```bash
./scripts/load-customer-secrets.sh first-national-bank agent04 \
  --bedrock-region "us-east-1" \
  --core-banking-url "https://core.first-national-bank.com/api" \
  --core-banking-key "..." \
  --device-intelligence-key "..." \     # ThreatMetrix, Sardine, or similar
  --behavioral-analytics-key "..." \    # Biocatch, Neuro-ID, or similar
  --visa-api-key "..." \                # If using Visa DPS/decision manager
  --mastercard-api-key "..."            # If using Mastercard Decision Intelligence
```

### Step 3: Configure Transaction Stream Integration
```bash
# Get the API Gateway endpoint for transaction ingestion
terraform output fraud_ingestion_endpoint
# → https://fraud.execute-api.us-east-1.amazonaws.com/prod/transactions

# Configure core banking / card processing system to POST transactions:
# {
#   "transaction_id": "TXN-2024-001234",
#   "account_id": "ACC-789012",
#   "customer_id": "CUST-456789",
#   "amount": 2500.00,
#   "currency": "USD",
#   "transaction_type": "WIRE",
#   "channel": "MOBILE",
#   "merchant_mcc": null,
#   "payee_account": "EXT-PAYEE-001",
#   "device_fingerprint": "d3f4...",   # Hashed before transmission
#   "ip_address_hash": "a1b2...",      # Hashed before transmission (GLBA)
#   "timestamp": "2024-01-15T10:30:00Z",
#   "is_new_payee": true
# }
```

### Step 4: Configure AD Groups
```powershell
Add-ADGroupMember -Identity "GRP-Fraud-Analysts" -Members "fraud.analyst1", "fraud.analyst2"
Add-ADGroupMember -Identity "GRP-Fraud-Managers" -Members "fraud.manager1"
Add-ADGroupMember -Identity "GRP-BSA-Officers" -Members "bsa.officer1"   # If not already added
Add-ADGroupMember -Identity "GRP-Compliance-Officers" -Members "compliance.officer1"
Add-ADGroupMember -Identity "GRP-AML-Auditors" -Members "internal.auditor"
```

### Step 5: Configure Agent 01 Cross-Referencing (If Deployed)
```bash
# Fraud patterns that suggest AML layering should route to Agent 01
# Configure the SAR flag → Agent 01 routing

aws secretsmanager put-secret-value \
  --secret-id /fraud/first-national-bank/agent01-queue-url \
  --secret-string "https://sqs.us-east-1.amazonaws.com/ACCOUNT/fcia-first-national-bank-alerts.fifo"

# Trigger patterns that cross-route to AML:
# - Structuring patterns (multiple transactions just below $10K)
# - Known fraud network payees
# - Wire + immediate fund withdrawal pattern
# - Card testing (velocity) + subsequent large transaction
```

### Step 6: Calibrate Fraud Score Thresholds
```bash
# Run backtesting against historical fraud data before go-live
python scripts/calibrate-thresholds.py \
  --customer-id first-national-bank \
  --historical-fraud-data fraud_labels_12mo.csv \
  --target-false-positive-rate 0.02   # 2% false positive target
  # Script produces recommended thresholds based on score distribution
  # Output: recommend BLOCK ≥ 87, STEP-UP ≥ 64, REVIEW ≥ 38
```

### Step 7: Smoke Test
```bash
./scripts/smoke-test.sh first-national-bank agent04

# Tests:
# ✓ Streamlit UI loads at port 8504
# ✓ Cognito / Okta auth works for Fraud Analyst, Manager, BSA Officer
# ✓ Real-time path completes within 200ms (load test with 50 concurrent txns)
# ✓ Async enrichment path completes within 5 minutes
# ✓ BLOCK decision generates Reg E disclosure draft
# ✓ Structuring pattern triggers AML SAR flag
# ✓ PII (IP address, device fingerprint) is hashed in audit log
# ✓ Analyst review gate works correctly
# ✓ Audit trail written to DynamoDB with GLBA-compliant hashed identifiers
# ✓ CloudWatch real-time latency metric flowing
```

---

## Terraform Module Reference
```hcl
module "fraud_detection_customer" {
  source = "git::https://github.com/your-org/fsi-agents-terraform//modules/agent04"

  customer_id        = "first-national-bank"
  customer_full_name = "First National Bank"
  aws_region         = "us-east-1"

  # LLM
  llm_provider             = "bedrock"
  bedrock_realtime_model   = "anthropic.claude-haiku-4-5-20251001"
  bedrock_async_model      = "anthropic.claude-3-5-sonnet-20241022-v2:0"

  # Authentication
  cognito_okta_saml_metadata_url = "https://customer.okta.com/app/APP_ID/sso/saml/metadata"
  ad_groups = {
    fraud_analysts       = "GRP-Fraud-Analysts"
    fraud_managers       = "GRP-Fraud-Managers"
    bsa_officers         = "GRP-BSA-Officers"
    compliance_officers  = "GRP-Compliance-Officers"
    auditors             = "GRP-AML-Auditors"
  }

  # Transaction volume (drives infrastructure sizing)
  transaction_volume_daily       = 500000
  peak_transactions_per_second   = 50
  realtime_latency_budget_ms     = 150

  # Fraud types to enable
  enable_card_fraud              = true
  enable_ach_fraud               = true
  enable_wire_fraud              = true
  enable_account_takeover        = true
  enable_elder_exploitation      = true
  enable_authorized_push_payment = true

  # Routing thresholds (calibrate post-deploy)
  block_threshold      = 85
  step_up_threshold    = 65
  review_threshold     = 40

  # Cross-agent routing
  enable_agent01_sar_routing = true
  agent01_sqs_queue_url     = "arn:aws:sqs:us-east-1:ACCOUNT:fcia-first-national-bank-alerts.fifo"

  # Compliance
  enable_reg_e_automation    = true
  reg_e_provisional_credit_days = 10   # Business days
  audit_retention_years      = 5
  enable_guardduty           = true
}
```

---

## CloudWatch Monitoring

### Key Metrics Dashboard: "Fraud Detection — Operations"
```
Row 1 — Real-Time Performance (SLA Monitoring)
  [P50 Real-Time Path Latency]  [P95 Latency]  [P99 Latency]  [Timeout Rate]

Row 2 — Decision Outcomes
  [Block Rate %]  [Step-Up Rate %]  [Review Queue Rate %]  [Allow Rate %]

Row 3 — Fraud Impact
  [Fraud $ Blocked]  [FP Rate]  [Analyst Review Queue Depth]  [Reg E Disclosures Sent]

Row 4 — AI Health
  [Haiku Latency P50/P95]  [Sonnet Latency]  [Bedrock Error Rate]

Row 5 — Integration Health
  [Core Banking API Success Rate]  [Device Intelligence Latency]  [DLQ Depth]
```

### Critical Alarms
```yaml
- Name: Realtime-Latency-SLA-Breach
  Threshold: P95 > 200ms
  Action: PagerDuty (immediate) → Ops team + Fraud Manager
  Reason: Payment authorization window exceeded — customers experiencing declined payments

- Name: Realtime-Worker-Insufficient-Capacity
  Threshold: SQS realtime queue depth > 100 for > 30 seconds
  Action: Auto-scale ECS tasks + PagerDuty
  Reason: Transaction burst exceeding worker capacity

- Name: Block-Rate-Anomaly
  Threshold: Block rate > 20% or < 0.5% over 15-minute window
  Action: Email → Fraud Manager
  Reason: May indicate rule misconfiguration or coordinated fraud attack

- Name: Reg-E-Deadline-Approaching
  Threshold: Any blocked transaction with dispute_filed = true AND provisional_credit_date within 2 business days
  Action: Email → Compliance Officer
  Reason: Reg E provisional credit deadline approaching
```

---

## Cost Estimation

| Service | Configuration | Monthly Cost |
|---------|--------------|-------------|
| ECS Fargate (UI) | 1 task, 1vCPU/2GB | ~$30 |
| ECS Fargate (Real-time workers, provisioned) | 3 tasks, 4vCPU/8GB, always-on | ~$720 |
| ECS Fargate (Async workers, spot) | Avg 2 tasks, 2vCPU/4GB, Fargate Spot | ~$75 |
| ECS Fargate (MCP Gateway + 4 servers) | 5 tasks, 0.5vCPU/1GB | ~$75 |
| ALB | 1 LB | ~$20 |
| ElastiCache Redis | cache.r6g.large, Multi-AZ | ~$150 |
| RDS Aurora PostgreSQL | db.r6g.large, Multi-AZ | ~$250 |
| DynamoDB | On-demand, ~5M events/month | ~$25 |
| SQS (real-time + async) | ~15M messages/month | ~$6 |
| Bedrock (Claude Haiku — real-time) | 500K txn/day × ~200 tokens | ~$400 |
| Bedrock (Claude Sonnet — async enrichment) | ~50K async × 5K tokens | ~$375 |
| S3 (Reg E docs + evidence) | 10 GB/month | ~$3 |
| Secrets Manager + KMS | ~12 secrets, ~5 CMKs | ~$15 |
| CloudWatch | Logs + metrics + dashboards | ~$35 |
| **Total** | | **~$2,179/month** |

*Higher cost than Agents 02-03 due to:*
- *Provisioned (non-spot) ECS for real-time latency path*
- *Larger Redis cluster for velocity state (cache.r6g.large vs. t3.micro)*
- *Higher transaction volume → more Bedrock tokens*
- *Use Fargate Spot for async workers to reduce cost 70%*
