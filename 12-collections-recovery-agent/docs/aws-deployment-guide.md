# Agent 12 — AWS Deployment Guide

## Collections & Recovery Agent: Production Deployment on AWS

**Document Purpose:** Step-by-step guide to deploying Agent 12 on AWS with production-grade
security, FDCPA compliance controls, and FCRA 7-year audit retention.

**Intended Audience:** DevOps Engineers, Cloud Architects, and Platform Teams deploying for
Collections Compliance Officers.

**Prerequisites:**
- AWS account with appropriate IAM permissions
- Python 3.11+, Docker, AWS CLI v2
- OpenAI API key (or AWS Bedrock access for data residency)
- SCRA database integration endpoint (DoD SCRA portal or third-party)
- Bankruptcy court monitoring feed (PACER or vendor)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AGENT 12 — AWS PRODUCTION ARCHITECTURE                    │
│                                                                              │
│  ┌─────────────┐    ┌─────────────────────────────────────────────────────┐  │
│  │  Collectors │    │  VPC — Private Subnet (us-east-1a / 1b)              │  │
│  │  Supervisors│───▶│  ┌──────────────┐  ┌───────────────────────────┐    │  │
│  │  Compliance │    │  │  ALB         │  │  ECS Fargate Cluster      │    │  │
│  │  Officers   │    │  │  Port 8512   │──▶│  2 tasks, 2 vCPU, 8 GB   │    │  │
│  └─────────────┘    │  │  WAF enabled │  │  UID 1000, readOnly FS    │    │  │
│                     │  └──────────────┘  └───────────┬───────────────┘    │  │
│                     │                                │                     │  │
│                     │  ┌─────────────────────────────▼──────────────────┐  │  │
│                     │  │  AWS Services (KMS-encrypted)                  │  │  │
│                     │  │                                                │  │  │
│                     │  │  Secrets Manager   DynamoDB          S3 Object │  │  │
│                     │  │  ├─OpenAI key      Case Registry     Lock      │  │  │
│                     │  │  ├─DB credentials  (PITR enabled)    7-year    │  │  │
│                     │  │  └─SMTP creds      GSI: status       GOVERNANCE│  │  │
│                     │  │                                                │  │  │
│                     │  │  CloudWatch Logs   EventBridge       SNS       │  │  │
│                     │  │  Audit log stream  (scheduled runs)  Alerts    │  │  │
│                     │  └────────────────────────────────────────────────┘  │  │
│                     └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Step 1: IAM Roles and Policies

Create a dedicated IAM role for the ECS task. Follow least-privilege — no wildcards on
sensitive services.

```bash
# Create ECS task execution role
aws iam create-role \
  --role-name agent12-collections-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach managed execution policy
aws iam attach-role-policy \
  --role-name agent12-collections-task-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

**Custom policy — minimum required permissions:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerRead",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:agent12/openai-key-*",
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:agent12/db-credentials-*",
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:agent12/smtp-credentials-*"
      ]
    },
    {
      "Sid": "DynamoDBCaseRegistry",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:GetItem",
        "dynamodb:Query"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/agent12-case-registry",
        "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/agent12-case-registry/index/*"
      ]
    },
    {
      "Sid": "S3AuditWrite",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::agent12-audit-trail-ACCOUNT_ID/*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:us-east-1:ACCOUNT_ID:log-group:/agent12/*"
    },
    {
      "Sid": "KMSDecrypt",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT_ID:key/AGENT12_KMS_KEY_ID"
    }
  ]
}
```

**Apply the custom policy:**

```bash
aws iam put-role-policy \
  --role-name agent12-collections-task-role \
  --policy-name agent12-minimum-access \
  --policy-document file://agent12-task-policy.json
```

---

## Step 2: AWS Secrets Manager

Store all credentials in Secrets Manager. Do not use environment variables for secrets.

```bash
# OpenAI API key
aws secretsmanager create-secret \
  --name agent12/openai-key \
  --description "OpenAI API key for Agent 12 LLM narrative generation" \
  --secret-string '{"OPENAI_API_KEY":"sk-your-key-here"}' \
  --kms-key-id alias/agent12-cmk

# Database credentials (PostgreSQL checkpointer for LangGraph)
aws secretsmanager create-secret \
  --name agent12/db-credentials \
  --description "PostgreSQL connection string for LangGraph checkpointer" \
  --secret-string '{"POSTGRES_CONNECTION_STRING":"postgresql://..."}' \
  --kms-key-id alias/agent12-cmk

# SMTP credentials for compliance alert emails
aws secretsmanager create-secret \
  --name agent12/smtp-credentials \
  --description "SMTP credentials for FDCPA compliance alert emails" \
  --secret-string '{"SMTP_HOST":"smtp.example.com","SMTP_USER":"...","SMTP_PASS":"..."}' \
  --kms-key-id alias/agent12-cmk
```

**Create the KMS Customer Managed Key first:**

```bash
aws kms create-key \
  --description "Agent 12 — Collections Recovery CMK" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT

aws kms create-alias \
  --alias-name alias/agent12-cmk \
  --target-key-id KEY_ID_FROM_ABOVE
```

---

## Step 3: LLM Configuration

### Option A: OpenAI GPT-4o (standard)

```bash
# Retrieve API key at runtime from Secrets Manager
import boto3
import json

def get_llm():
    client = boto3.client("secretsmanager", region_name="us-east-1")
    secret = client.get_secret_value(SecretId="agent12/openai-key")
    key = json.loads(secret["SecretString"])["OPENAI_API_KEY"]
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o", temperature=0, api_key=key)
```

### Option B: AWS Bedrock Claude Sonnet 4.6 (recommended for data residency)

For institutions requiring data to remain within AWS (no third-party API calls):

```python
from langchain_aws import ChatBedrock

def get_llm():
    return ChatBedrock(
        model_id="anthropic.claude-sonnet-4-6-20260601-v1:0",
        region_name="us-east-1",
        model_kwargs={"temperature": 0, "max_tokens": 4096},
    )
```

**Bedrock IAM addition:**

```json
{
  "Sid": "BedrockInvoke",
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6-20260601-v1:0"
}
```

**Compliance note:** Bedrock ensures all LLM calls stay within AWS infrastructure.
Collection letter content (which may contain consumer account context) never leaves
your AWS account. This is the recommended option for institutions subject to data
residency requirements.

---

## Step 4: S3 Object Lock — 7-Year Audit Retention

FCRA requires 7-year retention of collections records. S3 Object Lock GOVERNANCE mode
provides immutable storage that survives collection activity disputes and litigation holds.

```bash
# Create bucket with Object Lock enabled (cannot be added later)
aws s3api create-bucket \
  --bucket agent12-audit-trail-ACCOUNT_ID \
  --region us-east-1 \
  --object-lock-enabled-for-bucket

# Enable versioning (required for Object Lock)
aws s3api put-bucket-versioning \
  --bucket agent12-audit-trail-ACCOUNT_ID \
  --versioning-configuration Status=Enabled

# Set default retention: 7 years = 2,556 days GOVERNANCE mode
aws s3api put-object-lock-configuration \
  --bucket agent12-audit-trail-ACCOUNT_ID \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "GOVERNANCE",
        "Days": 2556
      }
    }
  }'

# Enable server-side encryption with KMS CMK
aws s3api put-bucket-encryption \
  --bucket agent12-audit-trail-ACCOUNT_ID \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "alias/agent12-cmk"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Lifecycle policy: transition to Glacier Deep Archive after 2 years
aws s3api put-bucket-lifecycle-configuration \
  --bucket agent12-audit-trail-ACCOUNT_ID \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "TransitionToGlacier",
      "Status": "Enabled",
      "Filter": {"Prefix": "audit/"},
      "Transitions": [{
        "Days": 730,
        "StorageClass": "DEEP_ARCHIVE"
      }]
    }]
  }'
```

**Why GOVERNANCE mode (not COMPLIANCE):**
GOVERNANCE mode allows vault administrators to override retention with explicit `s3:BypassGovernanceRetention`
permission + MFA. This enables hold adjustment for legal settlement or regulatory direction
while still preventing casual deletion. COMPLIANCE mode provides stronger immutability
but cannot be overridden even by AWS Support — appropriate for certain regulated environments.

---

## Step 5: DynamoDB Case Registry

```bash
# Create case registry with composite key
aws dynamodb create-table \
  --table-name agent12-case-registry \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=case_id,AttributeType=S \
    AttributeName=account_id,AttributeType=S \
    AttributeName=collections_outcome,AttributeType=S \
    AttributeName=created_date,AttributeType=S \
  --key-schema \
    AttributeName=case_id,KeyType=HASH \
    AttributeName=created_date,KeyType=RANGE \
  --global-secondary-indexes '[
    {
      "IndexName": "AccountIndex",
      "KeySchema": [
        {"AttributeName":"account_id","KeyType":"HASH"},
        {"AttributeName":"created_date","KeyType":"RANGE"}
      ],
      "Projection": {"ProjectionType":"ALL"}
    },
    {
      "IndexName": "OutcomeIndex",
      "KeySchema": [
        {"AttributeName":"collections_outcome","KeyType":"HASH"},
        {"AttributeName":"created_date","KeyType":"RANGE"}
      ],
      "Projection": {"ProjectionType":"ALL"}
    }
  ]' \
  --sse-specification '{
    "Enabled": true,
    "SSEType": "KMS",
    "KMSMasterKeyId": "alias/agent12-cmk"
  }'

# Enable Point-in-Time Recovery (PITR)
aws dynamodb update-continuous-backups \
  --table-name agent12-case-registry \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true

# Enable DynamoDB Streams (for cross-region replication)
aws dynamodb update-table \
  --table-name agent12-case-registry \
  --stream-specification StreamEnabled=true,StreamViewType=NEW_AND_OLD_IMAGES
```

**Case registry schema:**

```python
# Written by audit_finalize_node (Node 12)
case_record = {
    "case_id":              case_state["case_id"],        # Primary key
    "created_date":         date.today().isoformat(),     # Range key
    "account_id":           case_state["account_id"],     # ACCT-****{last4}
    "debt_type":            case_state["debt_type"],
    "consumer_state":       case_state["consumer_state"],
    "current_balance":      str(case_state["current_balance"]),
    "collections_outcome":  case_state["collections_outcome"],
    "hitl_required":        case_state["hitl_required"],
    "hitl_conditions":      json.dumps(case_state["hitl_conditions"]),
    "escalation_level":     case_state["escalation_level"],
    "reviewer_id":          case_state.get("reviewer_id", "AUTO"),
    "fdcpa_risk_tier":      case_state["regulatory_risk_tier"],
    "sol_expired":          case_state["sol_expired"],
    "scra_active_military": case_state["scra_active_military"],
    "bankruptcy_stay":      case_state["bankruptcy_stay_active"],
    "audit_s3_key":         f"audit/{case_state['case_id']}.json",
    "retention_policy":     "7-years-FCRA",
    "ttl":                  int((datetime.now() + timedelta(days=2556)).timestamp()),
}
```

---

## Step 6: PostgreSQL Checkpointer for LangGraph

LangGraph requires a checkpointer for `interrupt_before` to persist graph state during HITL
pause. In production, use PostgreSQL (Aurora Serverless v2 recommended).

```bash
# Create Aurora Serverless v2 cluster
aws rds create-db-cluster \
  --db-cluster-identifier agent12-langgraph-checkpoint \
  --engine aurora-postgresql \
  --engine-version 16.1 \
  --engine-mode provisioned \
  --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=4 \
  --master-username agent12admin \
  --master-user-password "GENERATE_STRONG_PASSWORD" \
  --vpc-security-group-ids sg-CHECKPOINTER_SG \
  --db-subnet-group-name agent12-db-subnet-group \
  --storage-encrypted \
  --kms-key-id alias/agent12-cmk \
  --deletion-protection \
  --backup-retention-period 35

# Add a serverless instance to the cluster
aws rds create-db-instance \
  --db-instance-identifier agent12-checkpoint-instance \
  --db-cluster-identifier agent12-langgraph-checkpoint \
  --db-instance-class db.serverless \
  --engine aurora-postgresql
```

**CRITICAL — Disable query logging to prevent PII in logs:**

```sql
-- Connect as admin after cluster creation
-- Disable query logging to prevent collection account data appearing in PostgreSQL logs
ALTER SYSTEM SET log_statement = 'none';
SELECT pg_reload_conf();

-- Verify setting
SHOW log_statement;
-- Expected: none

-- Apply DDL-only logging (captures schema changes but not data)
ALTER SYSTEM SET log_min_duration_statement = -1;
SELECT pg_reload_conf();
```

**Row-level security to prevent audit record modification:**

```sql
-- Create application user with restricted privileges
CREATE USER agent12_app WITH PASSWORD 'STRONG_PASSWORD';
GRANT CONNECT ON DATABASE langgraph TO agent12_app;
GRANT USAGE ON SCHEMA public TO agent12_app;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO agent12_app;
-- No UPDATE or DELETE granted — append-only enforcement

-- Rule to prevent deletion of audit records
CREATE RULE no_delete_checkpoint AS ON DELETE TO checkpoints DO INSTEAD NOTHING;
CREATE RULE no_update_checkpoint AS ON UPDATE TO checkpoints DO INSTEAD NOTHING;
```

---

## Step 7: CloudWatch Alarms — Collections Compliance Monitoring

Unlike Agent 11 (model performance metrics), Agent 12's CloudWatch alarms monitor
FDCPA contact compliance and HITL bypass attempts.

```bash
# CRITICAL: Alarm if contact_permitted=False bypassed (should be 0)
aws cloudwatch put-metric-alarm \
  --alarm-name agent12-contact-violation-attempt \
  --alarm-description "Contact attempted when contact_permitted_now=False — FDCPA § 805(a)(1) risk" \
  --metric-name ContactViolationAttempt \
  --namespace Agent12/FDCPACompliance \
  --statistic Sum \
  --period 3600 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:agent12-compliance-alerts \
  --treat-missing-data notBreaching

# Alarm: HITL bypass attempt (human_review_required is not False routing to auto)
aws cloudwatch put-metric-alarm \
  --alarm-name agent12-hitl-bypass-attempt \
  --alarm-description "Routing decision bypassed HITL without explicit False — fail-safe triggered" \
  --metric-name HITLBypassAttempt \
  --namespace Agent12/FDCPACompliance \
  --statistic Sum \
  --period 3600 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:agent12-compliance-alerts

# Alarm: SCRA case reviewed without supervisor approval
aws cloudwatch put-metric-alarm \
  --alarm-name agent12-scra-no-supervisor \
  --alarm-description "SCRA case processed without SUPERVISOR escalation decision" \
  --metric-name SCRAMissedEscalation \
  --namespace Agent12/FDCPACompliance \
  --statistic Sum \
  --period 86400 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:agent12-compliance-alerts

# Alarm: Reg F 7-in-7 violations (for monitoring, not blocking)
aws cloudwatch put-metric-alarm \
  --alarm-name agent12-reg-f-violations-high \
  --alarm-description "High volume of Reg F 7-in-7 violations — review dialer configuration" \
  --metric-name RegFViolationCount \
  --namespace Agent12/FDCPACompliance \
  --statistic Sum \
  --period 86400 \
  --threshold 10 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:agent12-ops-alerts
```

**Create SNS topics:**

```bash
# Compliance alerts (CRITICAL — email compliance officer)
aws sns create-topic --name agent12-compliance-alerts
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:agent12-compliance-alerts \
  --protocol email \
  --notification-endpoint compliance@yourinstitution.com

# Ops alerts (non-critical monitoring)
aws sns create-topic --name agent12-ops-alerts
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:agent12-ops-alerts \
  --protocol email \
  --notification-endpoint ops@yourinstitution.com
```

---

## Step 8: EventBridge — Scheduled Compliance Reports

```bash
# Weekly FDCPA compliance report (every Monday 8:00 AM ET)
aws events put-rule \
  --name agent12-weekly-compliance-report \
  --schedule-expression "cron(0 13 ? * MON *)" \
  --description "Agent 12 weekly FDCPA/Reg F compliance summary"

# Monthly regulatory metrics report (1st of each month)
aws events put-rule \
  --name agent12-monthly-regulatory-report \
  --schedule-expression "cron(0 9 1 * ? *)" \
  --description "Agent 12 monthly collections compliance metrics for CCO"
```

---

## Step 9: ECS Fargate Deployment

### 9.1 Build and Push Docker Image

```bash
# Build production image
docker build -t agent12-collections .

# Tag and push to ECR
aws ecr create-repository --repository-name agent12-collections
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker tag agent12-collections:latest \
  ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/agent12-collections:latest
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/agent12-collections:latest
```

### 9.2 ECS Task Definition

```json
{
  "family": "agent12-collections",
  "taskRoleArn": "arn:aws:iam::ACCOUNT_ID:role/agent12-collections-task-role",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/agent12-collections-task-role",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "8192",
  "containerDefinitions": [{
    "name": "agent12",
    "image": "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/agent12-collections:latest",
    "portMappings": [{"containerPort": 8512, "protocol": "tcp"}],
    "environment": [
      {"name": "PORT", "value": "8512"},
      {"name": "INSTITUTION_NAME", "value": "Your Institution"},
      {"name": "INSTITUTION_TYPE", "value": "BANK"}
    ],
    "secrets": [
      {
        "name": "OPENAI_API_KEY",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:agent12/openai-key:OPENAI_API_KEY::"
      },
      {
        "name": "POSTGRES_CONNECTION_STRING",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:agent12/db-credentials:POSTGRES_CONNECTION_STRING::"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/agent12/collections",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "linuxParameters": {
      "readonlyRootFilesystem": true,
      "tmpfs": [{"containerPath": "/tmp", "size": 512}]
    },
    "user": "1000",
    "essential": true,
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8512/_stcore/health || exit 1"],
      "interval": 30,
      "timeout": 5,
      "retries": 3,
      "startPeriod": 60
    }
  }]
}
```

### 9.3 ECS Service

```bash
# Register task definition
aws ecs register-task-definition --cli-input-json file://agent12-task-definition.json

# Create ECS cluster
aws ecs create-cluster --cluster-name agent12-cluster

# Create service with 2 tasks for high availability
aws ecs create-service \
  --cluster agent12-cluster \
  --service-name agent12-collections-service \
  --task-definition agent12-collections \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-PRIVATE_1,subnet-PRIVATE_2],
    securityGroups=[sg-AGENT12_ECS],
    assignPublicIp=DISABLED
  }" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:ACCOUNT_ID:targetgroup/agent12/...,containerName=agent12,containerPort=8512"
```

---

## Step 10: WAF — Protecting the HITL Gate

The HITL gate (human_review_gate node) is a critical control point. WAF rules prevent
automated bypass attempts.

```bash
# Create WAF Web ACL
aws wafv2 create-web-acl \
  --name agent12-waf \
  --scope REGIONAL \
  --default-action Allow={} \
  --rules '[
    {
      "Name": "HITLRateLimit",
      "Priority": 1,
      "Statement": {
        "RateBasedStatement": {
          "Limit": 30,
          "AggregateKeyType": "IP",
          "EvaluationWindowSec": 300
        }
      },
      "Action": {"Block": {}},
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "HITLRateLimit"
      }
    },
    {
      "Name": "AWSManagedRulesCommonRuleSet",
      "Priority": 2,
      "OverrideAction": {"None": {}},
      "Statement": {
        "ManagedRuleGroupStatement": {
          "VendorName": "AWS",
          "Name": "AWSManagedRulesCommonRuleSet"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "CommonRuleSet"
      }
    }
  ]' \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=agent12WAF

# Associate WAF with ALB
aws wafv2 associate-web-acl \
  --web-acl-arn arn:aws:wafv2:us-east-1:ACCOUNT_ID:regional/webacl/agent12-waf/... \
  --resource-arn arn:aws:elasticloadbalancing:us-east-1:ACCOUNT_ID:loadbalancer/app/agent12-alb/...
```

**Why 30 submissions per 5 minutes:** The HITL gate requires a human supervisor to review
case findings, conditions, and make a reasoned decision. Legitimate supervisors cannot
review and decide more than 6 cases per minute. The 30/5-min limit provides buffer while
blocking automated scripts that might attempt to submit bulk decisions.

---

## Step 11: Security Groups

```bash
# ALB Security Group — accepts HTTPS from internal network only
aws ec2 create-security-group \
  --group-name agent12-alb-sg \
  --description "Agent 12 ALB — inbound HTTPS from corporate network"

aws ec2 authorize-security-group-ingress \
  --group-id sg-ALB_SG \
  --protocol tcp \
  --port 8512 \
  --cidr YOUR_CORPORATE_CIDR_RANGE

# ECS Security Group — accepts traffic only from ALB
aws ec2 create-security-group \
  --group-name agent12-ecs-sg \
  --description "Agent 12 ECS tasks — inbound from ALB only"

aws ec2 authorize-security-group-ingress \
  --group-id sg-ECS_SG \
  --protocol tcp \
  --port 8512 \
  --source-group sg-ALB_SG

# ECS egress — HTTPS to AWS services and OpenAI (if not using Bedrock)
aws ec2 authorize-security-group-egress \
  --group-id sg-ECS_SG \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# PostgreSQL checkpointer Security Group
aws ec2 create-security-group \
  --group-name agent12-db-sg \
  --description "Agent 12 PostgreSQL — inbound from ECS only"

aws ec2 authorize-security-group-ingress \
  --group-id sg-DB_SG \
  --protocol tcp \
  --port 5432 \
  --source-group sg-ECS_SG
```

---

## Step 12: Pre-Go-Live Checklist

Before processing live collection accounts, verify all of the following.

### Regulatory Compliance Verification

- [ ] **FDCPA time enforcement:** Submit a test case with `consumer_timezone=America/Chicago`
  after 9pm Chicago time; verify `contact_permitted_now=False` in audit trail
- [ ] **Fail-safe timezone:** Submit a test case with `consumer_timezone=INVALID`; verify
  `contact_permitted_now=False` (fail-safe activated)
- [ ] **Reg F 7-in-7:** Submit a test case with `prior_contacts_7_days=7`; verify
  `regulation_f_violations` is non-empty
- [ ] **SCRA HITL:** Submit DEMO-002 (SCRA scenario); verify `hitl_conditions` contains
  `SCRA_DETECTED` and `escalation_level=SUPERVISOR`
- [ ] **Bankruptcy HITL:** Submit DEMO-003 (bankruptcy scenario); verify `hitl_conditions`
  contains `BANKRUPTCY_STAY_DETECTED` and `escalation_level=COMPLIANCE`
- [ ] **SOL expired:** Submit a case with `debt_date_of_last_payment` 10 years ago;
  verify `sol_expired=True` and collectability score reduction
- [ ] **HITL fail-safe routing:** Verify that `human_review_required=None` routes to
  HITL gate (not auto-route): `pytest tests/test_graph.py::TestRoutingFunctions -v`
- [ ] **frozenset immutability:** Run `pytest tests/test_nodes.py::TestSecurityProperties -v`;
  verify all 4 security property tests pass
- [ ] **PII masking:** Submit a case; verify account number in audit trail is `ACCT-****{last4}`;
  verify no raw account number appears in CloudWatch Logs or DynamoDB
- [ ] **Mini-Miranda injection:** Submit a case through communication drafting; verify
  mini-Miranda text appears verbatim in the letter output (Python-injected, not LLM-generated)

### Security Verification

- [ ] **KMS encryption:** Verify S3 objects have `x-amz-server-side-encryption: aws:kms`
- [ ] **S3 Object Lock:** Attempt to delete a test audit object; verify deletion is blocked
- [ ] **PostgreSQL `log_statement`:** Connect to Aurora and run `SHOW log_statement;`;
  verify value is `none` (not `all` or `ddl`)
- [ ] **WAF rate limit:** Submit 35 HITL decisions in 5 minutes from the same IP;
  verify 31st+ is blocked (HTTP 403)
- [ ] **ECS non-root:** Verify ECS task runs as UID 1000:
  ```bash
  aws ecs execute-command --cluster agent12-cluster \
    --task TASK_ID --container agent12 \
    --command "id" --interactive
  # Expected: uid=1000(agent12) gid=1000(agent12)
  ```
- [ ] **Read-only filesystem:** Attempt to write outside `/tmp` in ECS container; verify failure
- [ ] **No public IP:** Verify ECS tasks have `assignPublicIp=DISABLED`; verify no direct
  internet access to ECS
- [ ] **Secrets Manager (no env vars):** Verify `OPENAI_API_KEY` does not appear in ECS
  task environment variables; verify it is loaded from Secrets Manager at runtime

### Functional Verification

- [ ] All 4 demo scenarios run successfully: DEMO-001, DEMO-002, DEMO-003, DEMO-004
- [ ] Full test suite passes: `pytest tests/ -v` (target: 12 test classes, 60+ assertions)
- [ ] HITL gate pauses graph correctly; restarting with supervisor decision continues to
  communication drafting
- [ ] Audit trail contains one entry per node (12 entries for a complete run)
- [ ] DynamoDB case record is written by `audit_finalize_node`
- [ ] S3 audit JSON is uploaded with Object Lock tag

### Operational Verification

- [ ] CloudWatch alarms are in `OK` state (not `ALARM` or `INSUFFICIENT_DATA`)
- [ ] SNS email subscription confirmed for compliance@yourinstitution.com
- [ ] Aurora PostgreSQL PITR is enabled (verify in RDS console)
- [ ] ECS service shows 2 running tasks (desired count = actual count)
- [ ] ALB health checks passing for both target groups
- [ ] DR test: Terminate one ECS task; verify second task handles load; verify new task
  is launched within 5 minutes

### Compliance Officer Sign-Off

Before go-live, the Chief Compliance Officer should review and sign off on:
- [ ] FDCPA contact time enforcement configuration (timezone handling, fail-safe verification)
- [ ] SCRA HITL condition enforcement (immutability test results)
- [ ] Bankruptcy stay HITL enforcement (compliance escalation path)
- [ ] PII masking verification (no raw PII in logs, LLM prompts, or DynamoDB)
- [ ] 7-year audit retention configuration (S3 Object Lock verification)
- [ ] Mini-Miranda and validation notice verbatim injection verification
- [ ] Reg F 7-in-7 enforcement (integer comparison, CRM data feed confirmation)

---

## Appendix A: Environment Variables Reference

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| `OPENAI_API_KEY` | Yes (live mode) | Secrets Manager | GPT-4o API key |
| `POSTGRES_CONNECTION_STRING` | Yes (production) | Secrets Manager | LangGraph PostgreSQL checkpointer |
| `INSTITUTION_NAME` | Yes | env | Institution name for letter headers |
| `INSTITUTION_TYPE` | Yes | env | BANK, CU, FDCPA_THIRD_PARTY, etc. |
| `COLLECTIONS_COMPLIANCE_EMAIL` | Yes | env | Alert recipient |
| `LEGAL_COUNSEL_EMAIL` | Yes | env | LEGAL_REFERRAL outcome notification |
| `SETTLEMENT_HIGH_VALUE_THRESHOLD` | Optional | env | Default: 10000 |
| `SETTLEMENT_MAX_DISCOUNT_PCT` | Optional | env | Default: 40 |
| `PORT` | Yes | env | Default: 8512 |

---

## Appendix B: Monitoring Metrics

| Metric | Namespace | Alarm Threshold | Severity |
|--------|-----------|----------------|----------|
| `ContactViolationAttempt` | Agent12/FDCPACompliance | ≥1 per hour | CRITICAL |
| `HITLBypassAttempt` | Agent12/FDCPACompliance | ≥1 per hour | CRITICAL |
| `SCRAMissedEscalation` | Agent12/FDCPACompliance | ≥1 per day | CRITICAL |
| `RegFViolationCount` | Agent12/FDCPACompliance | ≥10 per day | WARNING |
| `BankruptcyStayContactAttempt` | Agent12/FDCPACompliance | ≥1 per hour | CRITICAL |
| `CaseProcessingLatency` | Agent12/Operations | >120 seconds | WARNING |
| `HITLQueueDepth` | Agent12/Operations | >50 pending | WARNING |
| `AuditS3WriteFailure` | Agent12/Operations | ≥1 per hour | CRITICAL |

---

*Document version: 1.0 | Agent 12 — Collections & Recovery Agent | FSI AI Suite*
