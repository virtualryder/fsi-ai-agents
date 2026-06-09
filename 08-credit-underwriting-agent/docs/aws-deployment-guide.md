# AWS Deployment Guide
## Credit Underwriting Agent — Production Deployment

---

## Architecture Overview

```
Internet → WAF → ALB → ECS (Streamlit UI) → LangGraph Workflow Engine
                                           → RDS Aurora (application state)
                                           → DynamoDB (audit trail)
                                           → S3 Object Lock (loan records)

LOS/Core Banking → SQS FIFO → Lambda (App Ingestor) → SQS (Processing Queue)
                                                      → ECS (Worker)

AWS Macie → S3 (PII detection in loan documents)
AWS KMS   → Envelope encryption for all PII fields at rest
```

**Security-first design:** Credit applications contain PII (name, address, income, credit score). The architecture enforces encryption at every layer — in transit (TLS 1.3), at rest (KMS), and in the application layer (field-level masking). No PII is logged in CloudWatch.

Estimated monthly cost: **~$380–$520/month** (community bank, 150 loans/month)

---

## Step 1: VPC and Network

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  name    = "credit-underwriting-vpc"
  cidr    = "10.8.0.0/16"

  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.8.1.0/24", "10.8.2.0/24"]
  public_subnets  = ["10.8.101.0/24", "10.8.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false  # Multi-AZ for HA
}
```

Security groups:
- `sg-underwriting-ui`: Allow 443 inbound from ALB; allow 8508 within VPC
- `sg-underwriting-worker`: No inbound; outbound HTTPS (443) for OpenAI API only
- `sg-underwriting-db`: Allow 5432 from `sg-underwriting-ui` and `sg-underwriting-worker` only
- `sg-underwriting-alb`: Allow 443 from 0.0.0.0/0

**Network isolation:** Worker service has no inbound access and restricted outbound — prevents lateral movement if compromised.

---

## Step 2: WAF — Web Application Firewall

Credit underwriting applications contain PII. A WAF is required to protect against injection attacks, data exfiltration, and bots submitting fraudulent applications.

```hcl
resource "aws_wafv2_web_acl" "underwriting_waf" {
  name  = "credit-underwriting-waf"
  scope = "REGIONAL"

  default_action { allow {} }

  # AWS Managed Rules — Core Rule Set (OWASP Top 10)
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # SQL injection protection
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 2
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLiRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # Rate limiting — prevent fraudulent bulk application submission
  rule {
    name     = "RateLimitApplicationSubmission"
    priority = 3
    action { count {} }  # Set to block after baseline established
    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitMetric"
      sampled_requests_enabled   = true
    }
  }
}
```

---

## Step 3: KMS — Envelope Encryption for PII

Credit applications contain PII (name, address, income, SSN reference). All persistent storage uses KMS-managed keys with automatic rotation.

```bash
# Create a customer-managed KMS key for underwriting PII
aws kms create-key \
  --description "Credit Underwriting PII Encryption" \
  --key-policy '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"AWS": "arn:aws:iam::ACCOUNT_ID:role/credit-underwriting-app"},
        "Action": ["kms:GenerateDataKey", "kms:Decrypt"],
        "Resource": "*"
      },
      {
        "Effect": "Deny",
        "Principal": "*",
        "Action": "kms:*",
        "Resource": "*",
        "Condition": {
          "StringNotEquals": {
            "aws:PrincipalAccount": "ACCOUNT_ID"
          }
        }
      }
    ]
  }'

# Enable automatic key rotation (annual)
aws kms enable-key-rotation --key-id KEY_ID
```

KMS applied to:
- RDS Aurora (database encryption)
- DynamoDB (audit trail encryption)
- S3 (loan records and documents)
- Secrets Manager (credentials)
- CloudWatch Logs (log encryption)
- SQS (message encryption)

---

## Step 4: Identity — Okta SAML + Cognito

Credit underwriting data is confidential. Access is restricted to underwriters and credit officers. **Loan applicant data must never be accessible to front-office staff or marketing teams.**

```
Okta SAML Groups → Cognito Identity Pool → IAM Roles

Allowed groups (Okta):
  GRP-Credit-Underwriters
  GRP-Senior-Underwriters
  GRP-Credit-Committee
  GRP-Chief-Credit-Officer
  GRP-BSA-Officers           ← OFAC review
  GRP-Compliance-Officers    ← Fair lending review
  GRP-Loan-Officers          ← Read-only (status only, no financial data)

Blocked:
  GRP-Marketing              ← No access to application data
  GRP-Retail-Tellers         ← No access to pending credit decisions
```

Cognito configuration:
```json
{
  "MFAConfiguration": "ON",
  "MfaConfiguration": {
    "SoftwareTokenMfaConfiguration": {"Enabled": true}
  },
  "PasswordPolicy": {
    "MinimumLength": 14,
    "RequireUppercase": true,
    "RequireNumbers": true,
    "RequireSymbols": true,
    "TemporaryPasswordValidityDays": 1
  },
  "UserPoolTags": {
    "Compliance": "ECOA-HMDA-CRA",
    "DataClassification": "Confidential-PII"
  }
}
```

Session timeout: 8-hour session cookie (ALB Cognito action). Underwriters re-authenticate each business day.

---

## Step 5: RDS Aurora PostgreSQL — Application State

```sql
-- Multi-AZ Aurora cluster for LangGraph PostgresSaver
CREATE DATABASE credit_underwriting;

-- Enable pgcrypto for field-level encryption (defense in depth)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- LangGraph checkpointer tables (auto-created by PostgresSaver on first run)
-- Application state is encrypted at the database level (KMS) and field level (pgcrypto)
```

Production configuration:
```python
from langgraph.checkpoint.postgres import PostgresSaver

# Never log connection string — loaded from Secrets Manager
conn_str = os.getenv("AURORA_CONN_STR")
with PostgresSaver.from_conn_string(conn_str) as checkpointer:
    app = build_underwriting_graph(checkpointer=checkpointer)
```

Aurora specs:
- Instance: `db.r6g.large` (community bank); `db.r6g.xlarge` (regional bank)
- Multi-AZ: Yes (primary + standby for HA)
- Encryption: AWS KMS (customer-managed key from Step 3)
- Backup retention: 7 days (ECOA / Reg B record-keeping)
- Enhanced monitoring: enabled (1-second granularity)
- Performance Insights: enabled (identify slow queries)
- Parameter: `log_min_duration_statement = 10000` (log queries >10s only — avoid logging PII in slow query log)

**Data security note:** `log_statement = 'none'` in Aurora parameter group — prevents SQL statements containing PII from appearing in database logs.

---

## Step 6: DynamoDB — Append-Only Audit Trail

The audit trail must be immutable per SR 11-7 (model output logging) and ECOA (adverse action decision documentation).

```python
# DynamoDB table: credit-underwriting-audit
# Schema: application_id (PK) + timestamp (SK)
# Encrypted with KMS customer-managed key
```

IAM policy enforcing append-only access:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/credit-underwriting-audit"
    },
    {
      "Effect": "Deny",
      "Action": [
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/credit-underwriting-audit"
    }
  ]
}
```

Point-in-time recovery (PITR): Enabled. Retention: 35 days.

**PII in audit trail:** The audit trail logs decision inputs and outputs but never raw SSN, full credit report data, or account numbers. The `_mask_pii()` function in `nodes.py` strips PII patterns from any text that enters the audit trail.

---

## Step 7: S3 Object Lock — Loan Record Retention

Loan files must be retained per federal record-keeping requirements:

| Document Type | Retention Period | Regulatory Basis |
|--------------|-----------------|-----------------|
| Credit application | 25 months | 12 CFR § 1002.12 (Reg B) |
| Adverse action notice | 25 months | 12 CFR § 1002.12 |
| Credit memo | 5 years after loan closure | OCC 12 CFR Part 12 |
| HMDA LAR data | 3 years | 12 CFR § 1003.5 |
| SBA loan documentation | 10 years | 13 CFR § 120.461 |

```bash
# Primary loan records bucket (25-month retention)
aws s3api create-bucket \
  --bucket credit-underwriting-records-${ACCOUNT_ID} \
  --region us-east-1

aws s3api put-object-lock-configuration \
  --bucket credit-underwriting-records-${ACCOUNT_ID} \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "GOVERNANCE",
        "Months": 25
      }
    }
  }'

# Long-term credit memo retention (5 years)
aws s3api create-bucket \
  --bucket credit-memos-${ACCOUNT_ID} \
  --region us-east-1

aws s3api put-object-lock-configuration \
  --bucket credit-memos-${ACCOUNT_ID} \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "COMPLIANCE",
        "Years": 5
      }
    }
  }'
```

**GOVERNANCE vs COMPLIANCE mode:** Adverse action notices and HMDA LAR use GOVERNANCE (CCO can override for corrections). Credit memos and SBA documentation use COMPLIANCE (no override — satisfies examination requirements).

### Macie for PII Detection

```bash
# Enable Macie to detect unintentional PII in S3 buckets
aws macie2 enable-macie

aws macie2 create-classification-job \
  --job-type ONE_TIME \
  --name "credit-underwriting-pii-scan" \
  --s3-job-definition '{
    "bucketDefinitions": [{
      "accountId": "ACCOUNT_ID",
      "buckets": [
        "credit-underwriting-records-ACCOUNT_ID",
        "credit-memos-ACCOUNT_ID"
      ]
    }]
  }'
```

---

## Step 8: SQS FIFO + Lambda — LOS Integration

In production, the Loan Origination System (Encompass, Byte, OpenClose) pushes applications via webhook or file drop.

```python
# Lambda: credit-application-ingestor
import json
import boto3
import re
import os

sqs = boto3.client("sqs")
QUEUE_URL = os.getenv("APPLICATION_QUEUE_URL")

# PII fields that must NEVER appear in SQS message metadata
PII_FIELDS = {"ssn", "tax_id", "full_account_number", "drivers_license"}

def sanitize_for_queue(application: dict) -> dict:
    """Remove PII that should stay in LOS — only pass derived fields."""
    sanitized = {k: v for k, v in application.items() if k not in PII_FIELDS}
    return sanitized

def handler(event, context):
    for record in event.get("Records", []):
        application = json.loads(record["body"])

        # Validate required fields
        required = ["applicant_id", "loan_type", "requested_amount", "annual_income"]
        if not all(k in application for k in required):
            send_to_dlq(application, "MISSING_REQUIRED_FIELDS")
            continue

        # Sanitize before queuing
        sanitized = sanitize_for_queue(application)

        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(sanitized),
            MessageGroupId=application["applicant_id"],  # FIFO per applicant
            MessageDeduplicationId=application.get("application_id", str(uuid.uuid4())),
        )
    return {"statusCode": 200}
```

SQS configuration:
- Queue type: FIFO (same applicant serialized — prevents duplicate processing)
- Visibility timeout: 300 seconds
- Dead Letter Queue: `credit-underwriting-dlq` — 3 receive attempts
- Encryption: SQS SSE with KMS customer-managed key (never plaintext PII in queue)
- CloudWatch alarm: DLQ depth > 0 → PagerDuty

---

## Step 9: ECS Task Definitions

```json
{
  "family": "credit-underwriting-ui",
  "cpu": "1024",
  "memory": "2048",
  "networkMode": "awsvpc",
  "containerDefinitions": [{
    "name": "underwriting-ui",
    "image": "${ECR_REPO}:latest",
    "portMappings": [{"containerPort": 8508}],
    "secrets": [
      {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:.../openai-api-key"},
      {"name": "AURORA_CONN_STR", "valueFrom": "arn:aws:secretsmanager:.../aurora-conn-str"},
      {"name": "KMS_KEY_ARN", "valueFrom": "arn:aws:secretsmanager:.../kms-key-arn"}
    ],
    "environment": [
      {"name": "FAIR_LENDING_REVIEW_ENABLED", "value": "true"},
      {"name": "LOG_LEVEL", "value": "WARNING"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/credit-underwriting",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ui"
      }
    }
  }]
}
```

**Log security:** `LOG_LEVEL=WARNING` prevents INFO-level logs from capturing application data. CloudWatch log group is encrypted with KMS. Log retention: 90 days.

---

## Step 10: CloudWatch Alarms

```python
alarms = [
    # Compliance — adverse action deadlines
    {
        "AlarmName": "underwriting-adverse-action-overdue",
        "Namespace": "CreditUnderwriting",
        "MetricName": "AdverseActionDeadlineBreached",
        "Threshold": 1,
        "AlarmDescription": "Adverse action notice deadline breached — Reg B violation risk",
    },
    # Compliance — HITL SLA
    {
        "AlarmName": "underwriting-hitl-overdue",
        "Namespace": "CreditUnderwriting",
        "MetricName": "HITLReviewOverdue48h",
        "Threshold": 1,
        "AlarmDescription": "Application awaiting underwriter review > 48 hours — SLA breach",
    },
    # Security — OFAC match volume
    {
        "AlarmName": "underwriting-ofac-spike",
        "Namespace": "CreditUnderwriting",
        "MetricName": "OFACMatchCount",
        "Threshold": 3,
        "AlarmDescription": ">3 OFAC matches in 24 hours — potential synthetic identity fraud ring",
    },
    # Security — WAF block rate
    {
        "AlarmName": "underwriting-waf-blocks",
        "Namespace": "AWS/WAFV2",
        "MetricName": "BlockedRequests",
        "Threshold": 100,
        "AlarmDescription": ">100 WAF blocks in 5 minutes — potential attack on application portal",
    },
    # Model integrity — SR 11-7 monitoring
    {
        "AlarmName": "underwriting-approval-rate-drift",
        "Namespace": "CreditUnderwriting",
        "MetricName": "ApprovalRate30d",
        "Threshold": 0.85,
        "ComparisonOperator": "GreaterThanThreshold",
        "AlarmDescription": ">85% approval rate over 30 days — possible model calibration issue",
    },
    {
        "AlarmName": "underwriting-fair-lending-flag-rate",
        "Namespace": "CreditUnderwriting",
        "MetricName": "FairLendingFlagRate",
        "Threshold": 0.15,
        "ComparisonOperator": "GreaterThanThreshold",
        "AlarmDescription": ">15% of applications flagged for fair lending review — review flagging logic",
    },
]
```

---

## Step 11: Secrets Manager

```bash
# All secrets in Secrets Manager — never in environment files or container images
aws secretsmanager create-secret \
  --name "credit-underwriting/openai-api-key" \
  --kms-key-id KEY_ID \
  --secret-string '{"OPENAI_API_KEY":"sk-..."}'

aws secretsmanager create-secret \
  --name "credit-underwriting/aurora-conn-str" \
  --kms-key-id KEY_ID \
  --secret-string '{"CONN_STR":"postgresql://user:pass@host:5432/credit_underwriting"}'

aws secretsmanager create-secret \
  --name "credit-underwriting/ofac-api-key" \
  --kms-key-id KEY_ID \
  --secret-string '{"API_KEY":"..."}'
```

Rotation:
- OpenAI API key: Lambda rotation on 90-day schedule
- Aurora credentials: Secrets Manager + RDS integration (automatic rotation)
- OFAC API key: Manual rotation on vendor schedule

---

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| ECS Fargate (UI + Worker) | $75 |
| Aurora PostgreSQL (r6g.large Multi-AZ) | $180 |
| DynamoDB (on-demand, ~30K audit writes/month) | $18 |
| S3 (loan records, credit memos, HMDA LAR) | $12 |
| SQS FIFO (150 apps × 8 messages) | $3 |
| ALB + NAT Gateway | $65 |
| WAF (web ACL + rule groups) | $20 |
| Secrets Manager (4 secrets, rotation) | $6 |
| CloudWatch (logs encrypted, alarms, dashboards) | $28 |
| KMS (customer-managed key, API calls) | $8 |
| Lambda (app ingestor, ~5K invocations) | $2 |
| AWS Macie (quarterly PII scan) | $15 |
| OpenAI API (gpt-4o, credit memos + adverse action) | $45–$180 |
| **Total** | **~$477–$612/month** |

Scales to ~$890/month for regional bank processing 400 loans/month.

**Security premium vs. baseline:** WAF + KMS + Macie add ~$43/month. For an application handling credit application PII, this is non-negotiable — a single ECOA or GLBA enforcement action costs orders of magnitude more.
