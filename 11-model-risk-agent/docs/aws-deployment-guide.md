# Agent 11 — Model Risk Management Agent
# AWS Deployment Guide

## Overview

This guide covers the 12-step production deployment of Agent 11 on AWS. Agent 11 has unique infrastructure requirements compared to Agents 01-10 because it produces regulated compliance artifacts (SR 11-7 model validation reports) that must be retained in tamper-evident, write-once storage, and an audit trail that examiners can query independently of application code. Every infrastructure decision documented here was made to satisfy those regulatory constraints.

**Ports:** 8511 (Streamlit UI)
**Estimated deployment time:** 4–6 hours for a team familiar with AWS
**Prerequisites completed:** VPC, subnets, KMS key from shared infrastructure setup

---

## Architecture Overview

```
Internet ──► Route 53 ──► ACM Cert ──► ALB (HTTPS 443)
                                         │
                          ┌──────────────┘
                          │
                    ECS Fargate (private subnet)
                    Agent 11 Streamlit  :8511
                          │
           ┌──────────────┼──────────────┐──────────────┐
           │              │              │               │
      Secrets         Aurora PG      DynamoDB          S3
      Manager         (audit +       (model         (validation
      (API keys,      checkpoint)    registry)      reports —
      DB creds)                                     Object Lock
                                                    GOVERNANCE)
           │                              │
      AWS Bedrock /                   EventBridge
      OpenAI API                      (automated
      (LLM narrative)                 monitoring
                                      triggers)
           │
      CloudWatch
      (performance
      metric alarms
      → SNS → MRO
      email)
```

---

## Step 1: IAM Roles and Policies

**Why this step first:** IAM roles are referenced by every subsequent resource. Creating them first prevents circular dependency issues during deployment.

### ECS Task Role (Agent 11 runtime identity)

```bash
aws iam create-role \
  --role-name fsi-agent11-ecs-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'
```

Attach the following inline policy — least-privilege, no `*` on any sensitive service:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerReadOnly",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:fsi/agent11/*"
      ]
    },
    {
      "Sid": "DynamoDBModelRegistry",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:ACCOUNT:table/fsi-model-registry",
        "arn:aws:dynamodb:us-east-1:ACCOUNT:table/fsi-model-registry/index/*"
      ]
    },
    {
      "Sid": "S3ValidationReportWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::fsi-model-validation-reports",
        "arn:aws:s3:::fsi-model-validation-reports/*"
      ]
    },
    {
      "Sid": "KMSEncryptDecrypt",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT:key/FSI_KMS_KEY_ID"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {"cloudwatch:namespace": "FSI/ModelRisk"}
      }
    }
  ]
}
```

**Security note:** S3 write is intentionally included — Agent 11 must write validation reports. S3 delete is NOT included — Object Lock GOVERNANCE mode prevents deletion, but removing delete permission adds defense in depth.

---

## Step 2: Secrets Manager

Store all credentials before any ECS task runs. The application reads these at startup; they are never passed via environment variables.

```bash
# LLM API key (OpenAI or AWS Bedrock — see Step 3)
aws secretsmanager create-secret \
  --name fsi/agent11/openai-api-key \
  --secret-string '{"OPENAI_API_KEY":"sk-..."}' \
  --kms-key-id alias/fsi-agent11

# Aurora PostgreSQL connection string
aws secretsmanager create-secret \
  --name fsi/agent11/postgres-connection \
  --secret-string '{"POSTGRES_CONNECTION_STRING":"postgresql://..."}' \
  --kms-key-id alias/fsi-agent11

# Institution configuration
aws secretsmanager create-secret \
  --name fsi/agent11/institution-config \
  --secret-string '{
    "INSTITUTION_NAME": "First Regional Bank",
    "INSTITUTION_TYPE": "BANK",
    "MRO_EMAIL": "mro@institution.com",
    "CRO_EMAIL": "cro@institution.com"
  }' \
  --kms-key-id alias/fsi-agent11
```

**Why Secrets Manager over Parameter Store:** Secrets Manager supports automatic rotation, cross-account access, and fine-grained IAM resource policies. For financial institution credentials (especially DB strings), rotation capability is a compliance requirement under several security frameworks.

---

## Step 3: LLM Provider Configuration

Agent 11's LLM calls produce narratives only — conceptual soundness review text, outcomes interpretation, and validation report prose. All model risk determinations are Python-only.

### Option A: AWS Bedrock (recommended for regulated institutions)

Bedrock keeps LLM inference within the AWS account boundary — no data leaves your VPC perimeter. This satisfies data residency requirements and eliminates concerns about validation findings appearing in third-party model training data.

```bash
# Enable Bedrock model access (claude-3-sonnet-20241022 recommended)
aws bedrock put-foundation-model-entitlement \
  --model-id anthropic.claude-3-sonnet-20241022-v1:0

# Update the application environment to use Bedrock
# Set BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20241022-v1:0
# Set USE_BEDROCK=true in institution config secret
```

Add Bedrock invoke permission to the ECS task role:
```json
{
  "Sid": "BedrockInvokeModel",
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet-20241022-v1:0"
}
```

### Option B: OpenAI via Secrets Manager

Use the `fsi/agent11/openai-api-key` secret. All prompts are designed to include only model metadata and performance statistics — not customer PII — so outbound API calls do not transmit regulated data.

**Required review:** Confirm with your CISO that OpenAI API calls from within the institution's network are approved for model metadata transmission. Agent 11's prompts are safe by design (they contain model weights and statistical metrics, not transaction data), but institutional policy may require Bedrock.

---

## Step 4: S3 Object Lock Bucket (Validation Report Retention)

**Why Object Lock:** SR 11-7 and BSA record retention requirements mean validation reports must be retained for the model's operational life plus 5 years (10-year total for production models). Object Lock GOVERNANCE mode prevents deletion or modification — not even an AWS root user can delete an object before the retention period expires without a special GOVERNANCE bypass procedure that creates its own audit trail.

```bash
# Create bucket with Object Lock enabled at creation time
# (Object Lock cannot be enabled on an existing bucket)
aws s3api create-bucket \
  --bucket fsi-model-validation-reports \
  --region us-east-1 \
  --object-lock-enabled-for-bucket

# Enable default encryption (KMS)
aws s3api put-bucket-encryption \
  --bucket fsi-model-validation-reports \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/fsi-agent11"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Set default Object Lock configuration (GOVERNANCE, 10 years = 3652 days)
aws s3api put-object-lock-configuration \
  --bucket fsi-model-validation-reports \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "GOVERNANCE",
        "Days": 3652
      }
    }
  }'

# Block all public access
aws s3api put-public-access-block \
  --bucket fsi-model-validation-reports \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# S3 Intelligent-Tiering → Glacier Deep Archive after 365 days
# Reduces storage cost for older reports while maintaining 10-year retention
aws s3api put-bucket-lifecycle-configuration \
  --bucket fsi-model-validation-reports \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "archive-old-reports",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Transitions": [{
        "Days": 365,
        "StorageClass": "GLACIER_IR"
      }, {
        "Days": 730,
        "StorageClass": "DEEP_ARCHIVE"
      }]
    }]
  }'
```

**Examiner access:** When examiners request validation reports, provide them via pre-signed S3 URLs (time-limited). Do not grant examiners direct S3 console access. The pre-signed URL approach creates an access log entry for each document viewed — important for maintaining the chain of custody in the audit trail.

---

## Step 5: DynamoDB Model Registry

The model registry is the authoritative source of current model approval status. It is updated by Agent 11's `audit_finalize_node` after each validation event and read by Agent 11's `model_inventory_lookup_node` at the start of each validation.

```bash
aws dynamodb create-table \
  --table-name fsi-model-registry \
  --attribute-definitions \
    AttributeName=model_id,AttributeType=S \
    AttributeName=last_updated,AttributeType=S \
  --key-schema \
    AttributeName=model_id,KeyType=HASH \
    AttributeName=last_updated,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --sse-specification Enabled=true,SSEType=KMS,KMSMasterKeyId=alias/fsi-agent11 \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true

# Global secondary index for querying by approval status
aws dynamodb update-table \
  --table-name fsi-model-registry \
  --attribute-definitions \
    AttributeName=model_approval_status,AttributeType=S \
  --global-secondary-index-updates '[{
    "Create": {
      "IndexName": "approval-status-index",
      "KeySchema": [{"AttributeName": "model_approval_status", "KeyType": "HASH"}],
      "Projection": {"ProjectionType": "ALL"}
    }
  }]'
```

**Seed the registry with current model state:**

```bash
# Example for AGT02-FP-SCORE-v1 (repeat for all 5 models)
aws dynamodb put-item \
  --table-name fsi-model-registry \
  --item '{
    "model_id": {"S": "AGT02-FP-SCORE-v1"},
    "last_updated": {"S": "2025-01-01T00:00:00Z"},
    "model_approval_status": {"S": "APPROVED"},
    "risk_tier": {"S": "HIGH"},
    "last_validation_date": {"S": "2025-01-01"},
    "next_revalidation_date": {"S": "2026-01-01"},
    "validation_id_last": {"S": "INITIAL_SEED"},
    "responsible_mro": {"S": "mro@institution.com"}
  }'
```

---

## Step 6: Aurora PostgreSQL (LangGraph Checkpoint Store + Audit Trail)

Agent 11 uses Aurora PostgreSQL for two purposes: LangGraph checkpoint storage (conversation state between graph runs) and the append-only audit trail that constitutes the SR 11-7 examination record.

```bash
# Create Aurora Serverless v2 cluster
aws rds create-db-cluster \
  --db-cluster-identifier fsi-agent11-aurora \
  --engine aurora-postgresql \
  --engine-version 15.4 \
  --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=8 \
  --master-username agent11admin \
  --manage-master-user-password \
  --master-user-secret-kms-key-id alias/fsi-agent11 \
  --vpc-security-group-ids sg-AGENT11_SG_ID \
  --db-subnet-group-name fsi-db-subnet-group \
  --storage-encrypted \
  --kms-key-id alias/fsi-agent11 \
  --deletion-protection \
  --backup-retention-period 35 \
  --enable-cloudwatch-logs-exports '["postgresql"]'

aws rds create-db-instance \
  --db-instance-identifier fsi-agent11-aurora-instance-1 \
  --db-cluster-identifier fsi-agent11-aurora \
  --db-instance-class db.serverless \
  --engine aurora-postgresql
```

**CRITICAL: Disable query logging for model parameters and validation findings.** Model validation findings, model weights, and PSI scores in database query logs would expose model internals to anyone with CloudWatch Logs access. This is a required pre-go-live item.

```sql
-- Connect to Aurora and run:
ALTER SYSTEM SET log_statement = 'none';
ALTER SYSTEM SET log_min_duration_statement = -1;
SELECT pg_reload_conf();

-- Verify setting took effect:
SHOW log_statement;  -- Should return 'none'
```

Create the LangGraph schema and the audit trail table:

```sql
-- LangGraph checkpoint tables (installed by langgraph-checkpoint-postgres)
-- Run: python -c "from langgraph.checkpoint.postgres import PostgresSaver; PostgresSaver.create_tables(conn)"

-- Audit trail table (Agent 11 specific)
CREATE TABLE model_validation_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_id VARCHAR(64) NOT NULL,
    model_id VARCHAR(64) NOT NULL,
    validation_type VARCHAR(64) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    node_name VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    reviewer_id VARCHAR(256),
    reviewer_decision VARCHAR(64),
    hitl_required BOOLEAN,
    validation_outcome VARCHAR(64),
    model_approval_status VARCHAR(64),
    conditions_imposed TEXT,
    retention_policy VARCHAR(64) DEFAULT '10_YEARS_S3_OBJECT_LOCK_GOVERNANCE',
    audit_payload JSONB NOT NULL
);

-- Indexes for examiner queries
CREATE INDEX idx_audit_model_id ON model_validation_audit(model_id);
CREATE INDEX idx_audit_validation_id ON model_validation_audit(validation_id);
CREATE INDEX idx_audit_timestamp ON model_validation_audit(event_timestamp);
CREATE INDEX idx_audit_outcome ON model_validation_audit(validation_outcome);

-- Prevent any UPDATE or DELETE on audit records (append-only enforcement)
CREATE RULE no_update_audit AS ON UPDATE TO model_validation_audit DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO model_validation_audit DO INSTEAD NOTHING;
```

---

## Step 7: CloudWatch Alarms and SNS (Performance Degradation Alerts)

Agent 11 publishes custom metrics to CloudWatch after each monitoring event. These alarms serve two purposes: automated detection of degradation between Agent 11 validation cycles, and the notification backbone for the MRO/CRO escalation system.

```bash
# Create SNS topics for each escalation path
aws sns create-topic --name fsi-agent11-mro-alerts \
  --attributes DisplayName="Agent 11 MRO Alerts"
aws sns create-topic --name fsi-agent11-cro-alerts \
  --attributes DisplayName="Agent 11 CRO Alerts - CRITICAL"

# Subscribe MRO and CRO email addresses
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:fsi-agent11-mro-alerts \
  --protocol email \
  --notification-endpoint mro@institution.com

aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:fsi-agent11-cro-alerts \
  --protocol email \
  --notification-endpoint cro@institution.com
```

Create CloudWatch alarms for each metric and model combination (example for AGT04 Gini):

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "Agent11-AGT04-GiniDegradation" \
  --alarm-description "AGT04-FRAUD-SCORE-v1 Gini coefficient declined >10 points from baseline" \
  --metric-name GiniCoefficient \
  --namespace FSI/ModelRisk \
  --dimensions Name=ModelId,Value=AGT04-FRAUD-SCORE-v1 \
  --statistic Minimum \
  --period 86400 \
  --evaluation-periods 1 \
  --threshold 58.4 \
  --comparison-operator LessThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:fsi-agent11-mro-alerts \
  --ok-actions arn:aws:sns:us-east-1:ACCOUNT:fsi-agent11-mro-alerts \
  --treat-missing-data notBreaching

# Hard rule violation alarm → CRO (immediate, no suppression)
aws cloudwatch put-metric-alarm \
  --alarm-name "Agent11-HardRuleViolation-CRITICAL" \
  --alarm-description "CRITICAL: Hard rule violation detected in production logs — CRO escalation required" \
  --metric-name HardRuleViolationCount \
  --namespace FSI/ModelRisk \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:fsi-agent11-cro-alerts \
  --treat-missing-data notBreaching
```

---

## Step 8: EventBridge (Automated Monitoring Schedule)

EventBridge triggers automated ongoing monitoring events on the schedule required by SR 11-7. HIGH-tier models are triggered monthly; the EventBridge rule invokes a Lambda that initiates the Agent 11 validation pipeline.

```bash
# Monthly automated monitoring trigger for HIGH-tier models
aws events put-rule \
  --name "fsi-agent11-monthly-monitoring" \
  --description "SR 11-7 monthly automated monitoring for HIGH-tier models" \
  --schedule-expression "cron(0 9 1 * ? *)" \
  --state ENABLED

# Lambda function that initiates the monitoring run
# (Lambda code: calls Agent 11 API endpoint with ONGOING_MONITORING validation type)
aws events put-targets \
  --rule fsi-agent11-monthly-monitoring \
  --targets '[{
    "Id": "agent11-monitoring-trigger",
    "Arn": "arn:aws:lambda:us-east-1:ACCOUNT:function:fsi-agent11-monitoring-trigger",
    "Input": "{\"validation_type\": \"ONGOING_MONITORING\", \"models\": [\"AGT02-FP-SCORE-v1\", \"AGT03-KYC-RISK-v1\", \"AGT04-FRAUD-SCORE-v1\", \"AGT07-SURV-RISK-v1\", \"AGT08-CREDIT-SCORE-v1\"]}"
  }]'
```

---

## Step 9: ECS Fargate Service

```bash
# Create ECR repository
aws ecr create-repository \
  --repository-name fsi-agent11 \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=KMS,kmsKey=alias/fsi-agent11

# Build and push image
docker build -t fsi-agent11 .
docker tag fsi-agent11:latest ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/fsi-agent11:latest
aws ecr get-login-password | docker login --username AWS \
  --password-stdin ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
docker push ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/fsi-agent11:latest

# ECS task definition
aws ecs register-task-definition \
  --family fsi-agent11 \
  --network-mode awsvpc \
  --requires-compatibilities FARGATE \
  --cpu 2048 \
  --memory 8192 \
  --execution-role-arn arn:aws:iam::ACCOUNT:role/fsi-ecs-execution-role \
  --task-role-arn arn:aws:iam::ACCOUNT:role/fsi-agent11-ecs-task-role \
  --container-definitions '[{
    "name": "agent11",
    "image": "ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/fsi-agent11:latest",
    "portMappings": [{"containerPort": 8511, "protocol": "tcp"}],
    "environment": [
      {"name": "AWS_DEFAULT_REGION", "value": "us-east-1"},
      {"name": "PORT", "value": "8511"}
    ],
    "secrets": [
      {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:fsi/agent11/openai-api-key:OPENAI_API_KEY::"},
      {"name": "POSTGRES_CONNECTION_STRING", "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:fsi/agent11/postgres-connection:POSTGRES_CONNECTION_STRING::"},
      {"name": "INSTITUTION_NAME", "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:fsi/agent11/institution-config:INSTITUTION_NAME::"},
      {"name": "MRO_EMAIL", "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:fsi/agent11/institution-config:MRO_EMAIL::"},
      {"name": "CRO_EMAIL", "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:fsi/agent11/institution-config:CRO_EMAIL::"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/fsi-agent11",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "agent11"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('"'"'http://localhost:8511/_stcore/health'"'"')\" || exit 1"],
      "interval": 30,
      "timeout": 10,
      "retries": 3,
      "startPeriod": 60
    },
    "readonlyRootFilesystem": true,
    "user": "1000:1000"
  }]'

# Create ECS service (2 tasks for HA)
aws ecs create-service \
  --cluster fsi-ai-agents \
  --service-name agent11 \
  --task-definition fsi-agent11 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[PRIVATE_SUBNET_1,PRIVATE_SUBNET_2],
    securityGroups=[sg-AGENT11_SG_ID],
    assignPublicIp=DISABLED
  }" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:targetgroup/agent11-tg/...,containerName=agent11,containerPort=8511"
```

---

## Step 10: WAF Rules

Agent 11 is accessed by MROs and CROs — a small, known user population. WAF rate limiting protects the HITL gate from automation attempts. Model validation decisions must come from authenticated humans, not automated scripts.

```bash
# Rate limiting: 100 requests per 5-minute window per IP
aws wafv2 create-rule-group \
  --name fsi-agent11-rate-limit \
  --scope REGIONAL \
  --capacity 10 \
  --rules '[{
    "Name": "rate-limit-hitl",
    "Priority": 1,
    "Statement": {
      "RateBasedStatement": {
        "Limit": 100,
        "AggregateKeyType": "IP"
      }
    },
    "Action": {"Block": {}},
    "VisibilityConfig": {
      "SampledRequestsEnabled": true,
      "CloudWatchMetricsEnabled": true,
      "MetricName": "agent11-rate-limit"
    }
  }]' \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=agent11-waf

# Associate WAF with ALB
aws wafv2 associate-web-acl \
  --web-acl-arn arn:aws:wafv2:us-east-1:ACCOUNT:regional/webacl/fsi-agent11-waf/... \
  --resource-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT:loadbalancer/app/fsi-agents-alb/...
```

---

## Step 11: Security Group Configuration

Agent 11's security group follows the same deny-by-default pattern as all FSI Suite agents:

```bash
aws ec2 create-security-group \
  --group-name sg-fsi-agent11 \
  --description "Agent 11 Model Risk Management — MRO/CRO access only" \
  --vpc-id vpc-FSI_VPC_ID

# HTTPS from ALB only
aws ec2 authorize-security-group-ingress \
  --group-id sg-AGENT11_SG_ID \
  --protocol tcp --port 8511 \
  --source-group sg-FSI_ALB_SG_ID

# Outbound: Aurora (5432)
aws ec2 authorize-security-group-egress \
  --group-id sg-AGENT11_SG_ID \
  --protocol tcp --port 5432 \
  --destination-group sg-FSI_AURORA_SG_ID

# Outbound: Secrets Manager, DynamoDB, S3, CloudWatch, EventBridge (via VPC endpoints)
aws ec2 authorize-security-group-egress \
  --group-id sg-AGENT11_SG_ID \
  --protocol tcp --port 443 \
  --cidr 0.0.0.0/0  # Scoped to VPC endpoints in production
```

---

## Step 12: Pre-Go-Live Checklist

Complete all items before Agent 11 serves production validation events. Each item maps to a regulatory requirement.

**Regulatory / Compliance**

- [ ] Aurora `log_statement=none` verified (prevents validation findings in query logs)
- [ ] S3 Object Lock GOVERNANCE mode confirmed on `fsi-model-validation-reports` bucket
- [ ] DynamoDB point-in-time recovery enabled on `fsi-model-registry` table
- [ ] Model registry seeded with current approval status for all 5 models
- [ ] MRO and CRO email subscriptions confirmed via SNS opt-in (check email)
- [ ] EventBridge monthly monitoring rule verified with test invocation

**Security**

- [ ] ECS task runs as UID 1000 (non-root) — verify with `docker run --user 1000 ...`
- [ ] Container filesystem is read-only (`readonlyRootFilesystem: true`)
- [ ] ECR image scan results reviewed — no CRITICAL vulnerabilities
- [ ] WAF rate limiting rule active and logging to CloudWatch
- [ ] Secrets Manager secrets confirmed accessible from ECS task role
- [ ] KMS key policy restricts decrypt to ECS task role only

**Functional**

- [ ] Demo Scenario DEMO-001 (Annual Revalidation — PASS) completes end-to-end
- [ ] Demo Scenario DEMO-002 (Triggered Review — CRITICAL) triggers HITL correctly
- [ ] Demo Scenario DEMO-003 (Fair Lending Flag) triggers HITL + Fair Lending Officer
- [ ] MRO decision submission persists to DynamoDB and S3
- [ ] Audit trail entry appears in Aurora after each validation event
- [ ] CloudWatch metric `GiniCoefficient` published after DEMO-002 run

**Operations**

- [ ] ECS service health check green on both tasks
- [ ] Aurora connection test from ECS task (not from local workstation)
- [ ] ALB target group shows both tasks as healthy
- [ ] CloudWatch log group `/ecs/fsi-agent11` receiving logs
- [ ] Backup and DR test: restore Aurora to a point-in-time 24 hours prior

---

## Monitoring and Operations

### Key Metrics to Watch (CloudWatch Dashboard)

| Metric | Namespace | Purpose | Alert Threshold |
|---|---|---|---|
| `GiniCoefficient` | `FSI/ModelRisk` | Model discriminatory power | Decline >10 points from baseline |
| `KSStatistic` | `FSI/ModelRisk` | KS separation score | Decline >8pp from baseline |
| `PSIScore` | `FSI/ModelRisk` | Population stability | >0.10 warning, >0.25 critical |
| `FalseNegativeRate` | `FSI/ModelRisk` | SAR/compliance miss rate | Increase >3pp from baseline |
| `HardRuleViolationCount` | `FSI/ModelRisk` | OFAC/PEP bypass events | Any nonzero value → CRO |
| `ValidationEventDuration` | `FSI/ModelRisk` | Pipeline latency | >300 seconds per event |
| `HITLPendingCount` | `FSI/ModelRisk` | Unreviewed MRO items | >5 pending → MRO reminder |

### Operational Notes

**Model suspension handling:** When the MRO selects `REQUIRE_REMEDIATION` at the HITL gate, Agent 11 sets `model_approval_status=SUSPENDED` in DynamoDB and S3. The relevant business agent (02, 03, 04, 07, or 08) must check the model registry before each scoring run in production. The model registry is the authoritative source — a SUSPENDED status means the scoring model must not be used for production decisions until remediation is complete.

**Rotation and key management:** KMS key rotation is set to annual by default. Rotate Secrets Manager secrets on the schedule in your institution's key management policy. The ECS task role's access to the KMS key is the only authorization path — direct access via the console is not permitted by the key policy.

**Disaster recovery:** Aurora point-in-time recovery is enabled for 35 days. S3 Object Lock prevents deletion of validation reports regardless of Aurora failure. The model registry (DynamoDB) has point-in-time recovery and cross-region replication configured at Step 5. Recovery time objective for Agent 11: 4 hours (Aurora restore from PITR). Recovery point objective: 5 minutes (Aurora continuous backup).
