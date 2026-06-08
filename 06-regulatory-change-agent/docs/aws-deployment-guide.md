# AWS Deployment Guide
## Agent 06 — Regulatory Change Management Agent

---

## Architecture Overview

```
Internet Gateway
       │
  ALB (HTTPS/443) ── Cognito JWT Authorizer
       │
  ECS Fargate (Private Subnet)
  ┌─────────────────────────────────────────┐
  │  Task: streamlit-ui (port 8506)         │
  │  Task: workflow-worker (background)     │
  └─────────────────────────────────────────┘
       │              │              │
  Aurora Postgres  DynamoDB      S3 + Object Lock
  (workflow state) (audit trail) (regulatory docs)
       │
  EventBridge Scheduler
  (feed polling: every 24h)
       │
  Lambda: feed-ingestion
  (FinCEN, OCC, FDIC, CFPB feeds)
```

**Key difference from other suite agents:** Agent 06 adds an EventBridge + Lambda feed ingestion layer for automated regulatory monitoring. Changes detected by the feed ingestion Lambda are pushed to an SQS queue, which the workflow worker consumes.

---

## Prerequisites

- AWS account with ECS, RDS, DynamoDB, S3, Lambda, EventBridge, SQS, Cognito enabled
- Okta tenant with SAML 2.0 app configured (see Step 2)
- OpenAI API key (or AWS Bedrock access for claude-sonnet-4-6)
- Docker installed locally for image builds
- Terraform CLI ≥ 1.9 (optional — manual steps included)

---

## Step 1 — VPC and Networking

If deploying into an existing VPC, skip to Step 2. For a new VPC:

```bash
# Create VPC (10.6.0.0/16 — Agent 06 CIDR block)
aws ec2 create-vpc --cidr-block 10.6.0.0/16 --tag-specifications \
  'ResourceType=vpc,Tags=[{Key=Name,Value=reg-change-agent-vpc}]'

# Create subnets (2 public for ALB, 2 private for ECS + Lambda)
aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.6.1.0/24 \
  --availability-zone us-east-1a --tag-specifications \
  'ResourceType=subnet,Tags=[{Key=Name,Value=reg-change-public-1a}]'

aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.6.2.0/24 \
  --availability-zone us-east-1b --tag-specifications \
  'ResourceType=subnet,Tags=[{Key=Name,Value=reg-change-public-1b}]'

aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.6.10.0/24 \
  --availability-zone us-east-1a --tag-specifications \
  'ResourceType=subnet,Tags=[{Key=Name,Value=reg-change-private-1a}]'

aws ec2 create-subnet --vpc-id <VPC_ID> --cidr-block 10.6.11.0/24 \
  --availability-zone us-east-1b --tag-specifications \
  'ResourceType=subnet,Tags=[{Key=Name,Value=reg-change-private-1b}]'

# NAT Gateway for private subnet outbound (regulatory feed API calls)
aws ec2 allocate-address --domain vpc
aws ec2 create-nat-gateway --subnet-id <PUBLIC_SUBNET_1A> --allocation-id <EIP_ID>
```

---

## Step 2 — Identity Provider (Okta → Cognito)

### 2a. Create Okta SAML Application for Agent 06

1. Okta Admin → **Applications** → **Create App Integration**
2. Sign-on method: **SAML 2.0**
3. App name: `Reg Change Management Agent`
4. Single sign on URL: `https://<COGNITO_DOMAIN>.auth.us-east-1.amazoncognito.com/saml2/idpresponse`
5. Audience URI: `urn:amazon:cognito:sp:<USER_POOL_ID>`
6. Attribute statements:
   - `email` → `user.email`
   - `given_name` → `user.firstName`
   - `family_name` → `user.lastName`
7. Group attribute: `groups` → matches `.*`

### 2b. Assign Groups to Agent 06 App

Compliance role groups to assign to this app:

```
GRP-Chief-Compliance-Officers   → CHIEF_COMPLIANCE_OFFICER role
GRP-BSA-Officers                → BSA_OFFICER role
GRP-Consumer-Compliance         → CONSUMER_COMPLIANCE_OFFICER role
GRP-Risk-Officers               → CHIEF_RISK_OFFICER role
GRP-Investment-Compliance       → INVESTMENT_COMPLIANCE_OFFICER role
GRP-Privacy-Officers            → CHIEF_PRIVACY_OFFICER role
GRP-Compliance-Analysts         → COMPLIANCE_ANALYST role (read-only)
```

**Important separation of duties:** Fraud and financial crime investigation staff (GRP-Fraud-Analysts, GRP-AML-Analysts) do NOT need access to Agent 06. The regulatory change management function is a compliance program function, not an investigation function.

### 2c. Create Cognito User Pool

```bash
aws cognito-idp create-user-pool \
  --pool-name "reg-change-agent-users" \
  --schema '[{"Name":"email","Required":true},{"Name":"custom:role","Mutable":true}]' \
  --auto-verified-attributes email

# Create app client
aws cognito-idp create-user-pool-client \
  --user-pool-id <USER_POOL_ID> \
  --client-name "reg-change-streamlit" \
  --generate-secret \
  --supported-identity-providers <OKTA_IDP_NAME> \
  --callback-urls '["https://<ALB_DNS>/oauth2/idpresponse"]' \
  --allowed-o-auth-flows code \
  --allowed-o-auth-scopes openid email profile
```

### 2d. Role Mapping Lambda

```python
# Lambda: cognito-pre-token-generation
# Maps Okta group membership to application role claim

ROLE_MAP = {
    "GRP-Chief-Compliance-Officers": "CHIEF_COMPLIANCE_OFFICER",
    "GRP-BSA-Officers": "BSA_OFFICER",
    "GRP-Consumer-Compliance": "CONSUMER_COMPLIANCE_OFFICER",
    "GRP-Risk-Officers": "CHIEF_RISK_OFFICER",
    "GRP-Investment-Compliance": "INVESTMENT_COMPLIANCE_OFFICER",
    "GRP-Privacy-Officers": "CHIEF_PRIVACY_OFFICER",
    "GRP-Compliance-Analysts": "COMPLIANCE_ANALYST",
}

def handler(event, context):
    groups = event.get("request", {}).get("groupConfiguration", {}).get("groupsToOverride", [])
    role = next((ROLE_MAP[g] for g in groups if g in ROLE_MAP), "READ_ONLY")
    event["response"]["claimsOverrideDetails"] = {
        "claimsToAddOrOverride": {"custom:role": role}
    }
    return event
```

---

## Step 3 — Data Stores

### 3a. Aurora PostgreSQL (Workflow State)

```bash
aws rds create-db-cluster \
  --db-cluster-identifier reg-change-agent-cluster \
  --engine aurora-postgresql \
  --engine-version 16.1 \
  --master-username rcm_admin \
  --master-user-password <SECURE_PASSWORD> \
  --vpc-security-group-ids <SG_ID> \
  --db-subnet-group-name <SUBNET_GROUP> \
  --backup-retention-period 7 \
  --deletion-protection

# Writer + reader instances
aws rds create-db-instance --db-instance-identifier reg-change-writer \
  --db-cluster-identifier reg-change-agent-cluster \
  --db-instance-class db.r6g.large --engine aurora-postgresql

aws rds create-db-instance --db-instance-identifier reg-change-reader \
  --db-cluster-identifier reg-change-agent-cluster \
  --db-instance-class db.r6g.large --engine aurora-postgresql \
  --promotion-tier 1
```

For production LangGraph state persistence:
```python
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
checkpointer = PostgresSaver(conn)
graph = build_regulatory_change_graph(checkpointer=checkpointer)
```

### 3b. DynamoDB — Audit Trail (Append-Only)

```bash
aws dynamodb create-table \
  --table-name RegChangeAuditTrail \
  --attribute-definitions \
    AttributeName=change_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=S \
  --key-schema \
    AttributeName=change_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true

# IAM policy — append only (no UpdateItem, DeleteItem)
aws iam create-policy \
  --policy-name RegChangeAuditAppendOnly \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/RegChangeAuditTrail"
    }]
  }'
```

### 3c. S3 — Regulatory Documents (Object Lock)

Regulatory publications and EDD documents must be retained per BSA record-keeping (31 CFR § 1010.430 — 5 years):

```bash
aws s3api create-bucket \
  --bucket reg-change-docs-<ACCOUNT_ID> \
  --object-lock-enabled-for-bucket \
  --region us-east-1

# Set GOVERNANCE mode Object Lock — 5-year retention for regulatory docs
aws s3api put-object-lock-configuration \
  --bucket reg-change-docs-<ACCOUNT_ID> \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "GOVERNANCE",
        "Years": 5
      }
    }
  }'
```

---

## Step 4 — SQS Queue (Regulatory Feed → Workflow)

```bash
# Main queue for incoming regulatory changes
aws sqs create-queue \
  --queue-name reg-change-intake.fifo \
  --attributes '{
    "FifoQueue": "true",
    "ContentBasedDeduplication": "true",
    "VisibilityTimeout": "300",
    "MessageRetentionPeriod": "86400",
    "ReceiveMessageWaitTimeSeconds": "20"
  }'

# Dead Letter Queue — no change silently lost
aws sqs create-queue \
  --queue-name reg-change-intake-dlq.fifo \
  --attributes '{"FifoQueue": "true", "MessageRetentionPeriod": "604800"}'

# Redrive policy
aws sqs set-queue-attributes \
  --queue-url <QUEUE_URL> \
  --attributes '{
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"<DLQ_ARN>\",\"maxReceiveCount\":\"3\"}"
  }'
```

---

## Step 5 — EventBridge + Lambda Feed Ingestion

### 5a. Feed Ingestion Lambda

```python
# lambda/feed_ingestion/handler.py
import json
import boto3
import feedparser
import requests

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["INTAKE_QUEUE_URL"]

REGULATORY_FEEDS = [
    {"authority": "FinCEN", "url": "https://www.fincen.gov/rss.xml", "domain": "BSA_AML"},
    {"authority": "OCC", "url": "https://www.occ.gov/news-issuances/bulletins/rss.xml", "domain": "BSA_AML"},
    {"authority": "CFPB", "url": "https://www.consumerfinance.gov/feed/", "domain": "CONSUMER_COMPLIANCE"},
    {"authority": "FDIC", "url": "https://www.fdic.gov/news/financial-institution-letters/rss.xml", "domain": "BSA_AML"},
]

def handler(event, context):
    for feed_config in REGULATORY_FEEDS:
        feed = feedparser.parse(feed_config["url"])
        for entry in feed.entries[:5]:  # Latest 5 entries per feed
            change = {
                "change_title": entry.get("title", ""),
                "regulatory_authority": feed_config["authority"],
                "regulatory_domain": feed_config["domain"],
                "summary_text": entry.get("summary", ""),
                "source_url": entry.get("link", ""),
                "publication_date": entry.get("published", ""),
                "change_type": "BULLETIN",  # Default; enriched by downstream
                "full_text": "",
                "audit_trail": [],
                "completed_steps": [],
                "errors": [],
            }
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(change),
                MessageGroupId=feed_config["authority"],
                MessageDeduplicationId=entry.get("id", entry.get("link", ""))[:100],
            )
    return {"statusCode": 200}
```

### 5b. EventBridge Schedule

```bash
# Daily regulatory feed polling at 6 AM UTC
aws events put-rule \
  --name "reg-change-feed-polling" \
  --schedule-expression "cron(0 6 * * ? *)" \
  --state ENABLED

aws events put-targets \
  --rule "reg-change-feed-polling" \
  --targets '[{
    "Id": "feed-ingestion-lambda",
    "Arn": "<LAMBDA_ARN>"
  }]'
```

---

## Step 6 — ECS Task Definitions

### Streamlit UI Task (reg-change-streamlit)

```json
{
  "family": "reg-change-streamlit",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT>:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::<ACCOUNT>:role/reg-change-task-role",
  "containerDefinitions": [{
    "name": "streamlit",
    "image": "<ECR_URI>/reg-change-agent:latest",
    "portMappings": [{"containerPort": 8506, "protocol": "tcp"}],
    "environment": [
      {"name": "INSTITUTION_TYPE", "value": "Commercial Bank"},
      {"name": "PRIMARY_REGULATOR", "value": "Federal Reserve"}
    ],
    "secrets": [
      {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:<ACCOUNT>:secret:reg-change/openai-api-key"},
      {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:<ACCOUNT>:secret:reg-change/database-url"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/reg-change-agent",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "streamlit"
      }
    }
  }]
}
```

### Workflow Worker Task (reg-change-worker)

```json
{
  "family": "reg-change-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "containerDefinitions": [{
    "name": "worker",
    "image": "<ECR_URI>/reg-change-agent:latest",
    "command": ["python", "-m", "worker.main"],
    "environment": [
      {"name": "WORKER_MODE", "value": "true"},
      {"name": "SQS_QUEUE_URL", "valueFrom": "<QUEUE_URL>"}
    ],
    "secrets": [
      {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:<ACCOUNT>:secret:reg-change/openai-api-key"},
      {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-1:<ACCOUNT>:secret:reg-change/database-url"}
    ]
  }]
}
```

---

## Step 7 — MCP Tool Authorization

The MCP Auth Gateway enforces role-based access to Agent 06 tools:

| Tool | BSA_OFFICER | CCO | COMPLIANCE_ANALYST | Business Unit Head |
|------|------------|-----|--------------------|-------------------|
| `submit_regulatory_change` | ✅ | ✅ | ✅ | ❌ |
| `view_gap_analysis` | ✅ | ✅ | ✅ | ❌ |
| `submit_officer_review` | ✅ | ✅ | ❌ | ❌ |
| `update_task_status` | ✅ | ✅ | ✅ | ✅ |
| `view_remediation_tasks` | ✅ | ✅ | ✅ | ✅ |
| `view_audit_trail` | ✅ | ✅ | ✅ | ❌ |
| `configure_thresholds` | ❌ | ✅ | ❌ | ❌ |
| `configure_sources` | ❌ | ✅ | ❌ | ❌ |

---

## Step 8 — ALB and Cognito Integration

```bash
# Create target group pointing to ECS tasks
aws elbv2 create-target-group \
  --name reg-change-tg \
  --protocol HTTP \
  --port 8506 \
  --vpc-id <VPC_ID> \
  --target-type ip \
  --health-check-path "/_stcore/health"

# Attach Cognito authorizer to ALB listener rule
aws elbv2 create-listener \
  --load-balancer-arn <ALB_ARN> \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=<CERT_ARN> \
  --default-actions '[{
    "Type": "authenticate-cognito",
    "AuthenticateCognitoConfig": {
      "UserPoolArn": "<USER_POOL_ARN>",
      "UserPoolClientId": "<CLIENT_ID>",
      "UserPoolDomain": "<COGNITO_DOMAIN>",
      "SessionCookieName": "AWSELBAuthSessionCookie",
      "OnUnauthenticatedRequest": "authenticate"
    },
    "Order": 1
  },{
    "Type": "forward",
    "TargetGroupArn": "<TARGET_GROUP_ARN>",
    "Order": 2
  }]'
```

---

## Step 9 — CloudWatch Monitoring

### Critical Alarms

```bash
# DLQ depth — no change should be silently lost
aws cloudwatch put-metric-alarm \
  --alarm-name "RegChange-DLQ-Depth" \
  --metric-name ApproximateNumberOfMessagesVisible \
  --namespace AWS/SQS \
  --dimensions Name=QueueName,Value=reg-change-intake-dlq.fifo \
  --statistic Maximum --period 300 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions <SNS_ARN>

# Overdue HITL reviews (CRITICAL/HIGH changes awaiting officer review > 24h)
aws cloudwatch put-metric-alarm \
  --alarm-name "RegChange-HITL-Overdue" \
  --metric-name HumanReviewAwaitingHours \
  --namespace RegChangeAgent/Metrics \
  --statistic Maximum --period 3600 \
  --threshold 24 --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_ARN>

# Remediation deadline approaching (< 30 days without task completion)
aws cloudwatch put-metric-alarm \
  --alarm-name "RegChange-Deadline-30Day" \
  --metric-name OpenChangesDeadlineWithin30Days \
  --namespace RegChangeAgent/Metrics \
  --statistic Sum --period 86400 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions <SNS_COMPLIANCE_ARN>
```

---

## Step 10 — Cost Estimate

| Resource | Spec | Monthly Cost |
|----------|------|-------------|
| ECS Fargate (UI) | 1 vCPU / 2 GB — 160 hrs/month | $38 |
| ECS Fargate (Worker) | 2 vCPU / 4 GB — scheduled | $85 |
| Aurora PostgreSQL | db.r6g.large Multi-AZ | $220 |
| DynamoDB (audit) | Pay per request | $12 |
| S3 + Object Lock | 50 GB regulatory docs | $8 |
| SQS | < 1M messages | $2 |
| Lambda (feed ingestion) | Daily runs | $3 |
| EventBridge | Scheduled rules | $1 |
| ALB | Standard | $18 |
| CloudWatch + Secrets Manager | Standard | $25 |
| **Total** | | **~$412/month** |

Lowest infrastructure cost in the suite — the batch/asynchronous nature of regulatory change processing means there is no real-time latency requirement and no need for provisioned Fargate or large Redis clusters.
