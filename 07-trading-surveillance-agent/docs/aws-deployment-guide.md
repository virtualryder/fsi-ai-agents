# AWS Deployment Guide
## Trading Surveillance Agent — Production Deployment

---

## Architecture Overview

```
Internet → ALB → ECS (Streamlit UI) → LangGraph Workflow Engine
                                     → RDS Aurora (case state)
                                     → DynamoDB (audit trail)
                                     → S3 Object Lock (records retention)

OMS/Trade Feed → SQS FIFO → Lambda (Alert Ingestor) → SQS (Processing Queue)
                                                      → ECS (Worker)
```

Estimated monthly cost: **~$485/month** (mid-size BD, 800 alerts/month)

---

## Step 1: VPC and Network

```hcl
# VPC: 10.7.0.0/16
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  name    = "trading-surveillance-vpc"
  cidr    = "10.7.0.0/16"

  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.7.1.0/24", "10.7.2.0/24"]
  public_subnets  = ["10.7.101.0/24", "10.7.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false   # Multi-AZ for HA
}
```

Security groups:
- `sg-surveillance-ui`: Allow 443 inbound from ALB; allow 8507 within VPC
- `sg-surveillance-worker`: No inbound; outbound HTTPS (443) for OpenAI API
- `sg-surveillance-db`: Allow 5432 from sg-surveillance-ui and sg-surveillance-worker only
- `sg-surveillance-alb`: Allow 443 from 0.0.0.0/0

---

## Step 2: Identity — Okta SAML + Cognito

Trading surveillance access is **strictly restricted to compliance and surveillance roles**. Front-office traders, research analysts, and sales staff must not have access to the surveillance dashboard.

```
Okta SAML Groups → Cognito Identity Pool → IAM Roles

Allowed groups (Okta):
  GRP-Trading-Surveillance-Officers
  GRP-Compliance-Officers
  GRP-BSA-Officers
  GRP-Legal-Counsel

Blocked (must not have access):
  GRP-Equities-Traders         ← would create conflict of interest
  GRP-Research-Analysts        ← Reg FD concerns
  GRP-Sales-Coverage           ← information barrier risk
```

Cognito User Pool configuration:
```json
{
  "MFAConfiguration": "ON",
  "MfaConfiguration": {
    "SoftwareTokenMfaConfiguration": {"Enabled": true}
  },
  "UserPoolTags": {
    "Compliance": "FINRA-3110",
    "DataClassification": "Confidential-Surveillance"
  }
}
```

**Critical:** Surveillance data is confidential. A trader who learns they are under surveillance could alter behavior or alert counterparties (information barrier breach). Access control must be enforced at the network and identity layer, not only at the application layer.

---

## Step 3: RDS Aurora PostgreSQL (Case State)

```sql
-- Multi-AZ Aurora cluster for LangGraph PostgresSaver
CREATE DATABASE trading_surveillance;

-- LangGraph checkpointer tables (created by PostgresSaver on first run)
-- Case state is durable across container restarts and HITL interrupts
```

PostgresSaver replaces MemorySaver in production:

```python
# production graph initialization
from langgraph.checkpoint.postgres import PostgresSaver
conn_str = os.getenv("AURORA_CONN_STR")
with PostgresSaver.from_conn_string(conn_str) as checkpointer:
    app = build_trading_surveillance_graph(checkpointer=checkpointer)
```

Aurora specs:
- Instance: `db.r6g.large` (mid-size BD); `db.r6g.xlarge` (large BD)
- Multi-AZ: Yes (primary + standby)
- Encryption: AWS KMS (aws/rds)
- Backup retention: 7 days (SEC Rule 17a-4 accessibility requirement)
- Parameter: `log_min_duration_statement = 5000` (log slow queries)

---

## Step 4: DynamoDB — Append-Only Audit Trail

```python
# DynamoDB table: trading-surveillance-audit
# Schema: alert_id (PK) + timestamp (SK)
# IAM policy enforces append-only
```

IAM policy to enforce append-only access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query"],
      "Resource": "arn:aws:dynamodb:*:*:table/trading-surveillance-audit"
    },
    {
      "Effect": "Deny",
      "Action": ["dynamodb:UpdateItem", "dynamodb:DeleteItem"],
      "Resource": "arn:aws:dynamodb:*:*:table/trading-surveillance-audit"
    }
  ]
}
```

Point-in-time recovery (PITR): Enabled. Satisfies SEC Rule 17a-4 requirement that records cannot be altered.

---

## Step 5: S3 Object Lock — Records Retention

```python
# Bucket: trading-surveillance-records-{account-id}
# Object Lock: COMPLIANCE mode, 3-year retention (SEC Rule 17a-4)
# SAR documentation: separate bucket, COMPLIANCE mode, 5-year retention
```

```bash
aws s3api create-bucket \
  --bucket trading-surveillance-records-${ACCOUNT_ID} \
  --region us-east-1

aws s3api put-object-lock-configuration \
  --bucket trading-surveillance-records-${ACCOUNT_ID} \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "COMPLIANCE",
        "Years": 3
      }
    }
  }'
```

Objects stored:
- Disposition memoranda (PDF)
- Audit trail exports (JSON)
- SAR narratives (encrypted, separate bucket with 5-year COMPLIANCE lock)
- Investigation narratives

**COMPLIANCE mode** means not even the AWS root account can delete objects within the retention period. This satisfies the SEC Rule 17a-4(f)(2)(ii)(A) non-erasure requirement.

---

## Step 6: SQS FIFO + Lambda — Trade Alert Ingestion

Trading surveillance systems (NASDAQ SMARTS, NICE Actimize, Bloomberg) push alerts via webhook or file drop. Lambda ingests and routes to the processing queue.

```python
# Lambda: alert-ingestor
import json
import boto3
import os

sqs = boto3.client("sqs")
QUEUE_URL = os.getenv("ALERT_QUEUE_URL")

def handler(event, context):
    for record in event.get("Records", []):
        # Parse alert from surveillance system webhook
        alert = json.loads(record["body"])

        # Validate required fields
        required = ["trader_id", "alert_type", "instrument_id", "notional_value"]
        if not all(k in alert for k in required):
            # Send to Dead Letter Queue for manual review
            send_to_dlq(alert, "MISSING_REQUIRED_FIELDS")
            continue

        # Route to processing queue
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(alert),
            MessageGroupId=alert["trader_id"],       # FIFO — same trader serialized
            MessageDeduplicationId=alert.get("alert_id", str(uuid.uuid4())),
        )
    return {"statusCode": 200}
```

SQS configuration:
- Queue type: FIFO
- Visibility timeout: 300s (allow workflow to complete)
- Dead Letter Queue: `trading-surveillance-alerts-dlq` — threshold 3 receive attempts
- CloudWatch alarm: DLQ depth > 0 → PagerDuty alert

---

## Step 7: ECS Task Definitions

Two ECS services:

**UI Service** (Streamlit Dashboard):
```json
{
  "family": "trading-surveillance-ui",
  "cpu": "1024",
  "memory": "2048",
  "networkMode": "awsvpc",
  "containerDefinitions": [{
    "name": "surveillance-ui",
    "image": "${ECR_REPO}:latest",
    "portMappings": [{"containerPort": 8507}],
    "environment": [
      {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."},
      {"name": "AURORA_CONN_STR", "valueFrom": "arn:aws:secretsmanager:..."}
    ]
  }]
}
```

**Worker Service** (Alert processing from SQS):
```json
{
  "family": "trading-surveillance-worker",
  "cpu": "2048",
  "memory": "4096",
  "containerDefinitions": [{
    "name": "surveillance-worker",
    "image": "${ECR_REPO}:worker",
    "environment": [
      {"name": "SQS_QUEUE_URL", "valueFrom": "arn:aws:secretsmanager:..."},
      {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."}
    ]
  }]
}
```

Auto-scaling:
- UI: min 1, max 4 — scale on ALB request count
- Worker: min 1, max 10 — scale on SQS queue depth (target: <100 messages)

---

## Step 8: ALB + Cognito Authentication

```hcl
resource "aws_alb_listener_rule" "cognito_auth" {
  listener_arn = aws_alb_listener.https.arn

  action {
    type = "authenticate-cognito"
    authenticate_cognito {
      user_pool_arn       = aws_cognito_user_pool.surveillance.arn
      user_pool_client_id = aws_cognito_user_pool_client.surveillance.id
      user_pool_domain    = aws_cognito_user_pool_domain.surveillance.domain
      # Session cookie: 8-hour expiry (enforce re-auth each trading day)
      session_cookie_name = "surveillance-session"
      session_timeout     = 28800
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.surveillance_ui.arn
  }
}
```

---

## Step 9: Secrets Manager

```bash
# Store all secrets in AWS Secrets Manager — never in environment files or code
aws secretsmanager create-secret \
  --name "trading-surveillance/openai-api-key" \
  --secret-string '{"OPENAI_API_KEY":"sk-..."}'

aws secretsmanager create-secret \
  --name "trading-surveillance/aurora-conn-str" \
  --secret-string '{"CONN_STR":"postgresql://user:pass@host:5432/trading_surveillance"}'
```

Rotation: OpenAI API key rotation via Lambda trigger on 90-day schedule.

---

## Step 10: CloudWatch Alarms

```python
alarms = [
    # Operational
    {
        "AlarmName": "surveillance-dlq-depth",
        "Namespace": "AWS/SQS",
        "MetricName": "ApproximateNumberOfMessagesVisible",
        "Threshold": 1,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "AlarmDescription": "Alerts in Dead Letter Queue — manual review required",
    },
    {
        "AlarmName": "surveillance-hitl-overdue",
        "Namespace": "TradingSurveillance",
        "MetricName": "HITLReviewOverdue24h",
        "Threshold": 1,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "AlarmDescription": "HIGH/CRITICAL case awaiting compliance review >24h — SLA breach",
    },
    # Regulatory
    {
        "AlarmName": "surveillance-sar-filing-window",
        "Namespace": "TradingSurveillance",
        "MetricName": "SARFilingWindowRemaining",
        "Threshold": 5,
        "ComparisonOperator": "LessThanOrEqualToThreshold",
        "AlarmDescription": "SAR filing deadline within 5 days — BSA filing required",
    },
    {
        "AlarmName": "surveillance-critical-alert-unreviewed",
        "Namespace": "TradingSurveillance",
        "MetricName": "CriticalAlertsUnreviewed4h",
        "Threshold": 1,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "AlarmDescription": "CRITICAL alert not reviewed within 4 hours — escalate to CCO",
    },
    # Model integrity
    {
        "AlarmName": "surveillance-scoring-tier-drift",
        "Namespace": "TradingSurveillance",
        "MetricName": "CriticalAlertPct30d",
        "Threshold": 0.20,
        "ComparisonOperator": "GreaterThanThreshold",
        "AlarmDescription": ">20% of alerts scoring CRITICAL — possible scoring model calibration issue",
    },
]
```

---

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| ECS (UI + Worker, ~2 vCPU avg) | $85 |
| Aurora PostgreSQL (r6g.large Multi-AZ) | $180 |
| DynamoDB (on-demand, ~50K audit writes/month) | $25 |
| S3 (records + SAR bucket, ~5 GB/month) | $15 |
| SQS FIFO (800 alerts × 10 messages each) | $5 |
| ALB + NAT Gateway | $65 |
| Secrets Manager (3 secrets, rotation) | $5 |
| CloudWatch (logs + alarms + dashboards) | $30 |
| Lambda (alert ingestor, ~10K invocations) | $5 |
| OpenAI API (gpt-4o, ~$65/1K alerts) | $52 |
| **Total** | **~$467/month** |

Scales to ~$890/month for large BD processing 3,000 alerts/month.
