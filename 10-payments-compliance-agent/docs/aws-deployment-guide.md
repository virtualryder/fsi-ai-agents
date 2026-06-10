# Agent 10 — AWS Production Deployment Guide

## Who This Guide Is For

This guide is written for:
- **DevOps / Platform engineers** deploying the agent to AWS
- **Security officers** reviewing the security architecture before approving production deployment
- **Compliance officers** verifying that the deployment satisfies data security requirements
  (GLBA, BSA, PCI-adjacent practices for payment data)

Every architectural decision is explained with its security rationale so that reviewers can
evaluate whether the controls are appropriate for their institution's risk appetite.

---

## Architecture Overview

```
Internet
    │
    ▼
[WAF] ─── Block OWASP Top 10, rate limit per IP
    │
    ▼
[ALB] ─── HTTPS only (TLS 1.2+), SSL termination
    │
    ▼
[ECS Fargate] ─── Agent 10 containers (non-root, read-only filesystem)
    │              Auto-scaling: 1-4 tasks, CPU/memory triggers
    │
    ├──► [Aurora PostgreSQL] ─── LangGraph checkpoint store (HITL state)
    │    Private subnet only. log_statement=none. KMS CMK encrypted.
    │
    ├──► [OpenAI API] ─── LLM calls (dispute analysis, compliance narrative, notices)
    │    Egress via NAT Gateway. No inbound from internet.
    │
    ├──► [S3 Bucket] ─── Audit trail export (Object Lock GOVERNANCE, 5-year)
    │    SSE-KMS. No public access. Macie scanning enabled.
    │
    └──► [Secrets Manager] ─── API keys, DB credentials (never in environment variables)
```

---

## Step 1 — VPC Configuration

### What to Deploy

Create a dedicated VPC for payments compliance workloads:
- 2 private subnets (ECS tasks, Aurora) — no internet-routable IP addresses
- 2 public subnets (ALB, NAT Gateway only)
- NAT Gateway for outbound-only internet access (OpenAI API calls)
- VPC Flow Logs enabled to CloudWatch Logs (required for incident investigation)

### Why This Architecture

**Why private subnets for ECS and Aurora?**
Payment data and compliance findings contain customer financial information protected
by GLBA. Placing these workloads in private subnets means they have no direct internet
exposure — an attacker cannot reach the database or application containers from the
internet, even if they discover the IP addresses.

**Why a dedicated VPC?**
Isolation prevents a compromise of another workload in a shared VPC from reaching
payments data. The payments compliance VPC should have minimal VPC peering — ideally
only to core banking systems that need to receive compliance findings.

**Why VPC Flow Logs?**
GLBA requires the ability to detect and respond to unauthorized access. VPC Flow Logs
provide a record of all network connections, enabling forensic analysis if a breach
is suspected.

```bash
# Example: Create VPC with Terraform (simplified)
resource "aws_vpc" "payments_compliance" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_hostnames = true
  tags = {
    Name        = "payments-compliance-vpc"
    Environment = "production"
    DataClass   = "PII-Financial"
  }
}
```

---

## Step 2 — WAF Configuration

### What to Deploy

AWS WAF v2 on the ALB with:
- AWS Managed Rules: CommonRuleSet (OWASP Top 10) + KnownBadInputsRuleSet
- Rate limiting: 1,000 requests per 5 minutes per IP
- Geo-blocking: restrict to institution's operating countries (if applicable)

### Why This Architecture

**Why WAF for a compliance tool?**
The Streamlit dashboard accepts payment event data as user input. Without a WAF,
an attacker could submit malformed inputs designed to exploit the application layer
(injection attacks, oversized payloads, malformed UTF-8). The agent processes this
input through LLM prompts — a WAF provides a defense-in-depth layer before the
application sanitizes inputs.

**Why rate limiting?**
Rate limiting prevents both accidental load (misconfigured scripts) and deliberate
denial-of-service attacks from consuming LLM API budget or database connections.

---

## Step 3 — KMS Customer-Managed Key (CMK)

### What to Deploy

Create a dedicated KMS CMK for the payments compliance workload:
- Key rotation: enabled (annual automatic rotation)
- Key policy: least-privilege (only ECS task role and Aurora service role)
- Separate CMKs for: Aurora database encryption, S3 bucket encryption, Secrets Manager

### Why This Architecture

**Why a dedicated CMK (not AWS-managed key)?**
AWS-managed keys are controlled by AWS. A dedicated CMK gives the institution:
1. The ability to revoke the key immediately if a breach is detected (effectively
   destroying access to all encrypted data)
2. Full audit log of every key usage in CloudTrail (who decrypted what, when)
3. The ability to share the key with specific roles only (not all AWS services)

**Why annual rotation?**
Key rotation limits the exposure window if a key is compromised. Even if an attacker
obtains an old key version, they can only decrypt data encrypted during that key version's
period.

```bash
aws kms create-key \
  --description "payments-compliance-cmk" \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS

aws kms enable-key-rotation --key-id <key-id>
```

---

## Step 4 — IAM Least-Privilege Roles

### What to Deploy

Three IAM roles:

**ECS Task Role** (assumed by running containers):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:payments-compliance/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::payments-compliance-audit-trail/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT:key/CMK-ID"
    }
  ]
}
```

**ECS Execution Role** (assumed by ECS to pull images and write logs):
- AmazonECSTaskExecutionRolePolicy (managed)
- Plus: `logs:CreateLogGroup` and `secretsmanager:GetSecretValue` for startup secrets

### Why This Architecture

**Why separate task role and execution role?**
The execution role is used by the ECS agent (infrastructure), not the application code.
The task role is used by the application. Separating them means application code cannot
access ECR or CloudWatch Logs (no need), and the ECS agent cannot access Secrets Manager
(no need).

**Why no `s3:GetObject` on the audit bucket for ECS?**
The application writes audit trail entries to S3 but never reads them from within the
application. Read access to the audit trail is limited to the security/compliance team's
role. This prevents a compromised application from reading audit data and covering tracks.

---

## Step 5 — AWS Secrets Manager

### What to Store in Secrets Manager

| Secret Name | Content | Rotation |
|-------------|---------|----------|
| `payments-compliance/openai-api-key` | OpenAI API key | Manual (when rotated) |
| `payments-compliance/postgres-dsn` | PostgreSQL connection string with credentials | 30-day auto-rotation |
| `payments-compliance/institution-name` | Institution name for customer notices | Manual |

### Why Secrets Manager (Not Environment Variables)

Environment variables are visible in:
- ECS task definition (stored in AWS console)
- `docker inspect` output (accessible to any process with Docker socket access)
- Process environment (`/proc/self/environ` on Linux)
- CloudTrail logs of task definition events

Secrets Manager secrets are:
- Encrypted at rest with KMS
- Accessed via API call (requires IAM permission + KMS decrypt)
- Audited in CloudTrail with principal, time, and action
- Rotatable without rebuilding the container image

**Application code retrieves secrets at startup:**
```python
import boto3
import json

def get_secret(secret_name: str) -> str:
    client = boto3.client("secretsmanager", region_name="us-east-1")
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])["value"]

OPENAI_API_KEY = get_secret("payments-compliance/openai-api-key")
```

---

## Step 6 — Aurora PostgreSQL (LangGraph Checkpoint Store)

### What to Deploy

Aurora PostgreSQL Serverless v2:
- Engine: PostgreSQL 15
- Minimum ACU: 0.5 (scales to 0 when idle)
- Maximum ACU: 4 (sufficient for 100 concurrent HITL reviews)
- Encryption: KMS CMK (the key created in Step 3)
- Parameter group: `log_statement = none`
- Deletion protection: enabled
- Automated backups: 7-day retention
- Multi-AZ: enabled (for production)

### Why This Architecture

**Why `log_statement = none`?**

This is the most critical Aurora configuration for compliance workloads. Aurora's
query logs record the full SQL statement — including all parameter values — when
`log_statement` is set to `all` or `ddl`. Since LangGraph checkpoints store payment
event state (including originator names, amounts, return codes, customer claim text),
enabling query logging would write payment data to CloudWatch Logs.

CloudWatch Logs:
- Are retained indefinitely by default
- Are accessible to all IAM principals with CloudWatch read access
- May be exported to S3 or third-party logging platforms
- Are not subject to the same access controls as the Aurora database itself

Setting `log_statement = none` ensures that payment data in checkpoint records
is never written to application logs.

**Why PostgresSaver instead of MemorySaver for production?**

A Reg E investigation takes up to 45 calendar days. The HITL review queue must persist
across:
- ECS task restarts (container crashes, deployments)
- Aurora failover events (Multi-AZ switchover)
- Scaling events (new ECS tasks don't inherit memory from old tasks)
- Weekend / holiday gaps in reviewer availability

MemorySaver (development) stores state in Python dict — destroyed on process exit.
PostgresSaver stores state in Aurora — survives all the above events.

**Setup:**
```python
from langgraph.checkpoint.postgres import PostgresSaver

dsn = get_secret("payments-compliance/postgres-dsn")
checkpointer = PostgresSaver.from_conn_string(dsn)
checkpointer.setup()  # Creates langgraph_checkpoints table if not present
```

---

## Step 7 — S3 Audit Trail Bucket

### What to Deploy

S3 bucket with:
- Object Lock: GOVERNANCE mode, 5-year retention period
- SSE-KMS: CMK from Step 3
- Versioning: enabled (required for Object Lock)
- Public access: blocked (all four block public access settings)
- Bucket policy: deny `s3:DeleteObject` and `s3:PutObjectAcl` from all principals
- Amazon Macie: enabled for PII detection scanning

### Why This Architecture

**Why Object Lock GOVERNANCE mode?**

BSA requires 5-year record retention for records relating to SARs, CTRs, and suspicious
activity (31 CFR 1010.430). Object Lock GOVERNANCE mode prevents:
- Application code from deleting audit records
- Compromised IAM credentials from deleting audit records
- Any principal without `s3:BypassGovernanceRetention` permission from modifying records

In GOVERNANCE mode (vs. COMPLIANCE mode), the institution's administrator CAN override
the retention lock in extreme cases (e.g., to delete records in response to a legal
hold or regulatory instruction). This flexibility is intentional — COMPLIANCE mode locks
are truly irrevocable.

**Why Macie?**

If a bug in the application causes full account numbers or SSNs to leak into the audit
trail despite masking, Amazon Macie will detect the PII and alert the security team
before the data accumulates for 5 years in Object Lock storage.

---

## Step 8 — ECS Fargate Task Definition

### Key Security Settings

```json
{
  "containerDefinitions": [{
    "name": "payments-compliance",
    "image": "ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/payments-compliance:latest",
    "readonlyRootFilesystem": true,
    "user": "1000:1000",
    "mountPoints": [
      {
        "containerPath": "/tmp",
        "sourceVolume": "tmp-volume",
        "readOnly": false
      }
    ],
    "secrets": [
      {
        "name": "OPENAI_API_KEY",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:payments-compliance/openai-api-key"
      },
      {
        "name": "POSTGRES_CONNECTION_STRING",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:payments-compliance/postgres-dsn"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/payments-compliance",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "agent10"
      }
    }
  }]
}
```

### Why These Settings

**`readonlyRootFilesystem: true`:**
If an attacker achieves code execution in the container, a read-only filesystem prevents
them from writing malware, modifying application code, or installing persistence mechanisms.
The `/tmp` tmpfs mount provides scratch space for Streamlit session files.

**`user: "1000:1000"`:**
Running as non-root means a container escape gives the attacker a non-privileged user
on the underlying EC2 host (Fargate hypervisor), not root. This significantly limits
lateral movement capability.

**`secrets` from Secrets Manager:**
Secrets are injected into the container environment from Secrets Manager at task startup.
They are not stored in the task definition — a `describe-task-definition` API call
does not reveal secret values.

---

## Step 9 — CloudWatch Alarms and Monitoring

### Alarms to Create

| Alarm | Metric | Threshold | Action |
|-------|--------|-----------|--------|
| SLA breach detected | Custom metric: `payments_sla_breached` | > 0 | PagerDuty / SNS |
| OFAC hit rate spike | Custom metric: `payments_ofac_hit` | > 2 in 1 hour | BSA Officer alert |
| SAR candidate queue depth | Custom metric: `payments_sar_candidate` | > 5 | BSA Officer alert |
| Review queue age | Custom metric: `payments_hitl_queue_age_hours` | > 4 hours | DISPUTES Manager alert |
| LLM API error rate | `HTTPSErrors` from NAT Gateway | > 5% | PagerDuty |
| Container CPU (scaling) | `CPUUtilization` | > 70% | Scale out ECS tasks |

### Why Proactive SLA Monitoring

The regulatory consequence of a missed Reg E SLA (provisional credit not issued within
10 business days) is a per-violation fine and potential CFPB enforcement action.
CloudWatch alarms on the `sla_breached` custom metric alert the compliance team before
the SLA window closes, not after.

---

## Step 10 — Security Group Rules

### Application Tier (ECS Tasks)

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| Inbound | TCP | 8510 | ALB Security Group | Streamlit traffic from ALB only |
| Outbound | TCP | 443 | 0.0.0.0/0 | OpenAI API via NAT Gateway |
| Outbound | TCP | 5432 | Aurora Security Group | PostgreSQL checkpoint store |

### Database Tier (Aurora)

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| Inbound | TCP | 5432 | ECS Security Group | LangGraph checkpoint reads/writes |
| (All other) | — | — | DENY | No other access |

### Why These Rules

No direct database access from the internet. No SSH or administrative ports open.
The database is accessible only from ECS task containers — not from developer laptops,
NAT Gateway, or other services. Database credentials are in Secrets Manager, not
in code or environment variables.

---

## Step 11 — Cost Estimate

| Service | Config | Monthly Cost |
|---------|--------|-------------|
| ECS Fargate | 1 task (0.5 vCPU, 1 GB), 720 hours | ~$18 |
| Aurora PostgreSQL Serverless v2 | 0.5-4 ACU, ~100 hrs/month active | ~$50 |
| ALB | 1 ALB, ~100 GB processed/month | ~$22 |
| WAF | 1 Web ACL, ~1M requests/month | ~$16 |
| Secrets Manager | 3 secrets | ~$1 |
| S3 (audit trail) | 10 GB/year | ~$1 |
| KMS | 1 CMK + API calls | ~$5 |
| NAT Gateway | ~1 GB/month egress to OpenAI | ~$5 |
| OpenAI API | ~40,000 LLM calls/year at $0.015 | ~$50/month |
| **Total** | | **~$168 / month** |

*Estimate for moderate production load. Actual cost varies with dispute volume.*

---

## Step 12 — Pre-Go-Live Security Checklist

Before deploying to production, verify each of the following:

- [ ] KMS CMK created with annual rotation enabled
- [ ] Aurora `log_statement = none` confirmed in parameter group
- [ ] S3 Object Lock enabled in GOVERNANCE mode with 5-year retention
- [ ] S3 public access blocked (all 4 settings)
- [ ] WAF rule groups attached to ALB
- [ ] Secrets Manager secrets created (no API keys in environment or task definition)
- [ ] ECS task runs as non-root (uid=1000) with read-only root filesystem
- [ ] PostgresSaver configured (not MemorySaver) — HITL reviews survive restarts
- [ ] VPC Flow Logs enabled to CloudWatch
- [ ] CloudWatch alarms created for SLA breach, OFAC hit, SAR queue depth
- [ ] Amazon Macie enabled on audit trail S3 bucket
- [ ] IAM task role uses least-privilege (no wildcard `*` actions)
- [ ] No IAM credentials in application code or container images
- [ ] Test HITL workflow end-to-end: submit event → pause at review gate → approve → resolution drafted
- [ ] Run `pytest tests/` — all tests must pass before production deployment
- [ ] Compliance officer review of `docs/regulatory-compliance.md`

---

## Appendix: Container Image Scanning

Before deploying any image, scan for vulnerabilities:

```bash
# Using Amazon ECR built-in scanning (recommended)
aws ecr start-image-scan \
  --repository-name payments-compliance \
  --image-id imageTag=latest

aws ecr describe-image-scan-findings \
  --repository-name payments-compliance \
  --image-id imageTag=latest

# Block deployment if CRITICAL vulnerabilities exist
```

Configure ECR to scan on push (automated, no manual step needed for subsequent deploys):
```bash
aws ecr put-image-scanning-configuration \
  --repository-name payments-compliance \
  --image-scanning-configuration scanOnPush=true
```
