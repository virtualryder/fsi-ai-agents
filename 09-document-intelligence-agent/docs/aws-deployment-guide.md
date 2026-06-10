# AWS Deployment Guide — Document Intelligence Agent (Agent 09)

## Purpose of This Document

This guide explains how to deploy the Document Intelligence Agent to AWS in a production-ready, secure configuration. Every architectural and security decision in this guide is explained in terms that both engineering teams and compliance/security officers can evaluate.

**Who should read this:**
- Engineering teams deploying the agent to AWS
- Security officers evaluating the infrastructure security posture
- Compliance officers verifying that document processing meets regulatory requirements (GLBA, BSA/AML, SOC 2)
- Cloud architects reviewing the design before sign-off

---

## Architecture Overview

```
Internet
    │
    ▼
AWS WAF (Web Application Firewall)
    │  Blocks SQL injection, XSS, oversized requests, rate abuse
    │
    ▼
Application Load Balancer (HTTPS/TLS 1.3)
    │  Terminates TLS, enforces Okta SAML authentication
    │
    ▼
ECS Fargate (Private Subnet)
    │  Runs the Streamlit app and LangGraph agent
    │  Non-root container user (uid=1000)
    │
    ├──► Amazon S3 (Document Staging — optional)
    │    Object Lock (GOVERNANCE mode, 25 months)
    │    Amazon Macie PII detection on uploaded objects
    │
    ├──► Amazon Aurora PostgreSQL (Private Subnet)
    │    LangGraph checkpoint storage — encrypted with KMS CMK
    │    log_statement=none (prevents PII in slow query logs)
    │
    ├──► Amazon SQS (Output Queue)
    │    Downstream agents consume structured JSON payloads
    │    Messages encrypted with KMS CMK
    │
    └──► AWS Secrets Manager
         API keys, database credentials — never in environment at build time
```

**Estimated Monthly Cost:** ~$487–$622/month (see Step 11 for breakdown)

---

## Step 1: VPC and Network Isolation

### What We're Building
A Virtual Private Cloud with public subnets (for the load balancer) and private subnets (for the application and database). The application and database never have direct internet access.

### Why This Architecture
Financial document processing involves PII (SSNs, passport numbers, account numbers). Direct internet exposure of the application or database creates unnecessary attack surface. The load balancer is the only publicly addressable component — it validates all requests before forwarding to the private application tier.

The separation of public and private subnets is a defense-in-depth measure: even if an attacker compromises the load balancer, they are not on the same network segment as the database. They would need a second exploit to reach private resources.

```bash
# Create VPC with DNS enabled (required for VPC endpoints to function)
aws ec2 create-vpc \
  --cidr-block 10.09.0.0/16 \
  --enable-dns-hostnames \
  --enable-dns-support \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=agent09-vpc},{Key=Environment,Value=production},{Key=Agent,Value=09-document-intelligence}]'

VPC_ID=<vpc-id from output>

# Public subnets — for the ALB only (not the application)
# Spread across two AZs for high availability
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.09.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agent09-public-1a}]'

aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.09.2.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agent09-public-1b}]'

# Private subnets — for ECS tasks and Aurora
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.09.10.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agent09-private-1a}]'

aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.09.11.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=agent09-private-1b}]'

# NAT Gateway — allows private subnet to reach internet for package updates
# without being reachable from the internet (one-way outbound only)
aws ec2 create-nat-gateway \
  --subnet-id <public-subnet-1a-id> \
  --allocation-id <elastic-ip-allocation-id>
```

**For Security Officers:** The NAT Gateway enables outbound-only internet access from private subnets. ECS containers need to reach the OpenAI API and pull Docker images from ECR. The NAT Gateway has no inbound rules — it is stateful and only allows return traffic for connections initiated from inside the VPC.

---

## Step 2: Web Application Firewall (WAF)

### What We're Building
AWS WAF v2 with managed rule sets, attached to the Application Load Balancer.

### Why WAF for a Document Processing Agent
Document upload endpoints are a high-value attack target:
- **Malicious file uploads**: Attackers upload ZIP bombs, polyglot files, or files containing code in the document payload to exploit parser vulnerabilities.
- **Prompt injection via document content**: If an attacker can control document content, they may attempt to inject instructions into the LLM via the document text. WAF can block documents with known injection patterns.
- **Oversized requests**: Large files can exhaust ECS memory and cause denial-of-service. WAF enforces size limits before the request reaches the application.
- **Rate abuse**: A compromised user account could flood the system with document submissions. WAF rate limiting prevents resource exhaustion.

```bash
# Create WAF Web ACL
aws wafv2 create-web-acl \
  --name "agent09-document-waf" \
  --scope "REGIONAL" \
  --default-action '{"Allow": {}}' \
  --rules '[
    {
      "Name": "AWSManagedRulesCommonRuleSet",
      "Priority": 1,
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
    },
    {
      "Name": "AWSManagedRulesSQLiRuleSet",
      "Priority": 2,
      "OverrideAction": {"None": {}},
      "Statement": {
        "ManagedRuleGroupStatement": {
          "VendorName": "AWS",
          "Name": "AWSManagedRulesSQLiRuleSet"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "SQLiRuleSet"
      }
    },
    {
      "Name": "AgentRateLimit",
      "Priority": 3,
      "Action": {"Block": {}},
      "Statement": {
        "RateBasedStatement": {
          "Limit": 100,
          "AggregateKeyType": "IP"
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "RateLimit"
      }
    },
    {
      "Name": "BlockOversizedRequests",
      "Priority": 4,
      "Action": {"Block": {}},
      "Statement": {
        "SizeConstraintStatement": {
          "FieldToMatch": {"Body": {}},
          "ComparisonOperator": "GT",
          "Size": 10485760,
          "TextTransformations": [{"Priority": 0, "Type": "NONE"}]
        }
      },
      "VisibilityConfig": {
        "SampledRequestsEnabled": true,
        "CloudWatchMetricsEnabled": true,
        "MetricName": "OversizedRequests"
      }
    }
  ]' \
  --visibility-config 'SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=agent09-waf'
```

**For Security Officers:** The 10MB request body limit in WAF matches the 10MB limit enforced by the `document_intake_node` in Python. This two-layer enforcement prevents oversized files from consuming ECS memory even if the application-level check is bypassed.

---

## Step 3: KMS Encryption Key Management

### What We're Building
A Customer-Managed Key (CMK) in AWS KMS with automatic annual rotation. This key encrypts all data at rest: the Aurora database, SQS queue, S3 bucket, and CloudWatch Logs.

### Why Customer-Managed Keys (Not AWS-Managed Keys)
Financial institutions processing PII are subject to GLBA data security requirements. Using CMKs provides:

1. **Control over key lifecycle**: You can revoke access to the key (and thus all encrypted data) immediately if a security incident occurs. With AWS-managed keys, you cannot revoke access.
2. **Key rotation audit trail**: KMS logs every use of the key to CloudTrail, providing a cryptographic record of what accessed encrypted data and when.
3. **Separation of duties**: The KMS key policy can be configured so that the ECS task role can *use* the key but cannot *administer* it. Administrators cannot access encrypted data without access to the key.
4. **Regulatory evidence**: Regulators (OCC, FDIC, CFPB examiners) expect financial institutions to demonstrate key management controls. CMKs with documented policies satisfy this requirement.

```bash
# Create the CMK for Agent 09
aws kms create-key \
  --description "Agent 09 Document Intelligence — Data Encryption Key" \
  --key-usage "ENCRYPT_DECRYPT" \
  --origin "AWS_KMS" \
  --tags TagKey=Agent,TagValue=09-document-intelligence \
         TagKey=Environment,TagValue=production \
         TagKey=DataClassification,TagValue=Confidential

KMS_KEY_ID=<key-id from output>

# Create a human-readable alias for the key
aws kms create-alias \
  --alias-name "alias/agent09-document-intelligence" \
  --target-key-id $KMS_KEY_ID

# Enable automatic annual key rotation
# WHY: Annual rotation limits the amount of data protected by any single key version.
# If a key version is ever compromised, rotation limits the historical exposure window.
aws kms enable-key-rotation --key-id $KMS_KEY_ID
```

**For Compliance Officers:** NIST SP 800-57 recommends key rotation periods based on data sensitivity. Annual rotation for a data encryption key protecting financial PII is consistent with industry best practice. The KMS key policy should follow least-privilege: the ECS task IAM role receives `kms:Decrypt` and `kms:GenerateDataKey` only — not `kms:DeleteKey` or `kms:ScheduleKeyDeletion`.

---

## Step 4: Identity and Access Management (IAM)

### What We're Building
Least-privilege IAM roles for the ECS task (what the application can do) and for human operators (what engineers and compliance reviewers can do).

### Why Least-Privilege Matters for a Document Processing Agent
The ECS task processes documents containing SSNs, passport numbers, and wire transfer details. If the task role were over-privileged (e.g., had `s3:*` or `sqs:*`), a compromised container could exfiltrate documents to any S3 bucket or read messages from any SQS queue. Least-privilege limits what an attacker can do if they compromise the running container.

```bash
# ECS Task Execution Role — used by ECS to pull the container image and
# retrieve secrets from Secrets Manager before the container starts
aws iam create-role \
  --role-name agent09-task-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the standard ECS execution policy (ECR pull, CloudWatch Logs)
aws iam attach-role-policy \
  --role-name agent09-task-execution-role \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"

# ECS Task Role — used by the running container to access AWS services.
# Strictly limited to what the application actually needs.
aws iam create-role \
  --role-name agent09-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Task Role Policy: granular permissions for each service the application uses
aws iam put-role-policy \
  --role-name agent09-task-role \
  --policy-name agent09-task-policy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "ReadSecretsForAPIKeys",
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:prod/agent09/*"
      },
      {
        "Sid": "UseKMSKeyForEncryption",
        "Effect": "Allow",
        "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
        "Resource": "arn:aws:kms:us-east-1:*:key/*",
        "Condition": {
          "StringEquals": {"kms:ViaService": ["rds.us-east-1.amazonaws.com", "sqs.us-east-1.amazonaws.com", "s3.us-east-1.amazonaws.com"]}
        }
      },
      {
        "Sid": "SQSSendToDownstreamAgents",
        "Effect": "Allow",
        "Action": ["sqs:SendMessage"],
        "Resource": [
          "arn:aws:sqs:us-east-1:*:agent01-financial-crime-inbox",
          "arn:aws:sqs:us-east-1:*:agent03-kyc-cdd-inbox",
          "arn:aws:sqs:us-east-1:*:agent04-fraud-detection-inbox",
          "arn:aws:sqs:us-east-1:*:agent06-regulatory-change-inbox",
          "arn:aws:sqs:us-east-1:*:agent07-trading-surveillance-inbox",
          "arn:aws:sqs:us-east-1:*:agent08-credit-underwriting-inbox"
        ]
      },
      {
        "Sid": "CloudWatchLogsWrite",
        "Effect": "Allow",
        "Action": [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        "Resource": "arn:aws:logs:us-east-1:*:log-group:/ecs/agent09-document-intelligence:*"
      },
      {
        "Sid": "DenyDeleteAuditTrail",
        "Effect": "Deny",
        "Action": [
          "dynamodb:DeleteItem",
          "dynamodb:UpdateItem",
          "rds-data:ExecuteStatement"
        ],
        "Resource": "*",
        "Condition": {
          "StringEquals": {
            "aws:ResourceTag/AuditTrail": "true"
          }
        }
      }
    ]
  }'
```

**For Security Officers:** Note the explicit `Deny` statement for DeleteItem/UpdateItem on resources tagged as audit trail storage. This provides an IAM-level guarantee that application code cannot modify or delete audit trail records, even if there is a bug in the application.

---

## Step 5: Secrets Manager — API Key Storage

### What We're Building
AWS Secrets Manager storage for the OpenAI API key, database credentials, and any other sensitive configuration.

### Why Not Environment Variables in the Task Definition
ECS task definition environment variables are stored in the AWS control plane and visible to anyone with `ecs:DescribeTaskDefinitions` permission. Secrets Manager provides:
- Encrypted storage with KMS
- Fine-grained IAM access control
- Automatic credential rotation for database passwords
- Audit trail of secret access in CloudTrail

```bash
# Store the OpenAI API key in Secrets Manager
aws secretsmanager create-secret \
  --name "prod/agent09/openai-api-key" \
  --description "OpenAI API key for Agent 09 Document Intelligence" \
  --secret-string '{"api_key": "sk-your-key-here"}' \
  --kms-key-id $KMS_KEY_ID

# Store Aurora database credentials
aws secretsmanager create-secret \
  --name "prod/agent09/aurora" \
  --description "Aurora PostgreSQL credentials for LangGraph checkpointer" \
  --secret-string '{
    "username": "agent09",
    "password": "generate-a-strong-password",
    "host": "agent09-cluster.cluster-xxx.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "database": "agent09_db",
    "connection_string": "postgresql://agent09:password@host:5432/agent09_db"
  }' \
  --kms-key-id $KMS_KEY_ID

# Enable automatic rotation for database credentials (90-day rotation)
aws secretsmanager rotate-secret \
  --secret-id "prod/agent09/aurora" \
  --rotation-lambda-arn <rotation-lambda-arn> \
  --rotation-rules AutomaticallyAfterDays=90
```

---

## Step 6: Aurora PostgreSQL — LangGraph Checkpoint Storage

### What We're Building
An encrypted Aurora PostgreSQL Serverless v2 cluster for LangGraph state persistence (HITL checkpoint storage and audit trail durability).

### Why Aurora (Not RDS Single Instance)
Aurora Serverless v2 provides:
- **Automatic failover**: In a production HITL system, a database failure during a reviewer's session would lose all pending review queue state. Aurora Multi-AZ with automatic failover recovers in ~30 seconds.
- **Scale-to-zero**: For development/staging environments, Aurora Serverless v2 can scale to 0 ACUs when idle, reducing cost.
- **Compatible with PostgreSQL tools**: Standard psql, pg_dump, and LangGraph's PostgresSaver work without modification.

### Why log_statement=none — A Critical Security Setting
PostgreSQL's default logging configuration can log slow queries, which includes the query parameters. For a LangGraph checkpoint database, slow queries may include serialized state containing extracted document text with PII. Setting `log_statement=none` ensures that no document content or PII is written to PostgreSQL logs, which flow to CloudWatch Logs.

```bash
# Create the Aurora Serverless v2 cluster
aws rds create-db-cluster \
  --db-cluster-identifier "agent09-document-intel" \
  --engine "aurora-postgresql" \
  --engine-version "15.4" \
  --engine-mode "provisioned" \
  --serverlessv2-scaling-configuration MinCapacity=0.5,MaxCapacity=8 \
  --master-username "agent09admin" \
  --master-user-password "$(aws secretsmanager get-secret-value --secret-id prod/agent09/aurora --query SecretString --output text | jq -r .password)" \
  --database-name "agent09_db" \
  --storage-encrypted \
  --kms-key-id $KMS_KEY_ID \
  --vpc-security-group-ids <private-sg-id> \
  --db-subnet-group-name "agent09-private-subnet-group" \
  --backup-retention-period 35 \
  --preferred-backup-window "02:00-03:00" \
  --deletion-protection \
  --tags Key=Agent,Value=09-document-intelligence Key=DataClassification,Value=Confidential

# Create a DB cluster parameter group with security-hardened PostgreSQL settings
aws rds create-db-cluster-parameter-group \
  --db-cluster-parameter-group-name "agent09-postgres-params" \
  --db-parameter-group-family "aurora-postgresql15" \
  --description "Agent 09 security-hardened PostgreSQL parameters"

# Apply critical security parameters
aws rds modify-db-cluster-parameter-group \
  --db-cluster-parameter-group-name "agent09-postgres-params" \
  --parameters \
    "ParameterName=log_statement,ParameterValue=none,ApplyMethod=immediate" \
    "ParameterName=log_min_duration_statement,ParameterValue=-1,ApplyMethod=immediate" \
    "ParameterName=log_connections,ParameterValue=1,ApplyMethod=immediate" \
    "ParameterName=log_disconnections,ParameterValue=1,ApplyMethod=immediate" \
    "ParameterName=ssl,ParameterValue=1,ApplyMethod=immediate" \
    "ParameterName=rds.force_ssl,ParameterValue=1,ApplyMethod=immediate"
```

**For Compliance Officers:** The 35-day backup retention period with `--deletion-protection` ensures that database backups covering the 30-day BSA record-keeping lookback period are always available. The `deletion-protection` flag prevents the database cluster from being deleted without first explicitly disabling deletion protection — a safeguard against accidental or malicious data destruction.

---

## Step 7: S3 for Document Staging (Optional)

### What We're Building
An S3 bucket for optional document staging (when documents arrive via async channels like email or SFTP rather than direct upload). Amazon Macie provides automated PII detection on uploaded objects.

### Why Object Lock and Macie
Object Lock in GOVERNANCE mode ensures that once a document is staged, it cannot be overwritten or deleted during the retention period. This satisfies BSA record-keeping requirements that original documents be preserved.

Macie provides a second layer of PII detection. If a document bypasses the application's PII masking (due to a rare OCR failure or an unsupported document format), Macie will detect the PII in the staged file and generate a CloudWatch alert, allowing the operations team to investigate before the document is processed.

```bash
# Create the document staging bucket
aws s3api create-bucket \
  --bucket "agent09-document-staging-$(aws sts get-caller-identity --query Account --output text)" \
  --region us-east-1

# Enable server-side encryption with the KMS CMK
aws s3api put-bucket-encryption \
  --bucket "agent09-document-staging-..." \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "'$KMS_KEY_ID'"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Block all public access — documents must never be publicly readable
aws s3api put-public-access-block \
  --bucket "agent09-document-staging-..." \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Enable Object Lock in GOVERNANCE mode (25 months = covers BSA 5-year retention with rolling window)
# GOVERNANCE mode: can be overridden by users with s3:BypassGovernanceRetention permission
# COMPLIANCE mode: cannot be overridden by anyone including root — use for 5-year BSA retention
aws s3api put-object-lock-configuration \
  --bucket "agent09-document-staging-..." \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "GOVERNANCE",
        "Days": 760
      }
    }
  }'

# Enable Amazon Macie for automated PII detection
aws macie2 enable-macie

aws macie2 create-classification-job \
  --name "agent09-document-pii-scan" \
  --job-type "SCHEDULED" \
  --schedule-frequency "DAILY" \
  --s3-job-definition '{
    "BucketDefinitions": [{
      "AccountId": "'$(aws sts get-caller-identity --query Account --output text)'",
      "Buckets": ["agent09-document-staging-..."]
    }]
  }'
```

---

## Step 8: Amazon SQS — Downstream Agent Routing

### What We're Building
SQS queues that receive structured JSON payloads from Agent 09 for consumption by downstream specialist agents.

### Why SQS Instead of Direct API Calls
When Agent 09 processes a document and determines it should go to the Credit Underwriting agent, it could call Agent 08's API directly. But SQS provides:

1. **Durability**: If Agent 08 is momentarily unavailable (ECS task restart, deployment), the message waits in the queue without loss. Direct API calls would fail.
2. **Decoupling**: Agent 09 does not need to know Agent 08's current IP address or port. It writes to a queue name, and Agent 08 reads from it.
3. **Backpressure**: Agent 08 can process at its own rate without Agent 09 overwhelming it with requests.
4. **Retry logic**: SQS provides automatic message redelivery if Agent 08 fails to acknowledge a message (e.g., crashes mid-processing).

```bash
# Create SQS queues for each downstream agent
# Agent 09 writes to these queues; downstream agents read from them
for AGENT in agent01-financial-crime agent03-kyc-cdd agent04-fraud-detection \
             agent06-regulatory-change agent07-trading-surveillance agent08-credit-underwriting; do
  aws sqs create-queue \
    --queue-name "${AGENT}-inbox" \
    --attributes '{
      "KmsMasterKeyId": "'$KMS_KEY_ID'",
      "MessageRetentionPeriod": "1209600",
      "VisibilityTimeout": "300",
      "ReceiveMessageWaitTimeSeconds": "20"
    }' \
    --tags Agent=09-document-intelligence,Environment=production
done
```

**Note:** `MessageRetentionPeriod=1209600` = 14 days. Messages not consumed within 14 days are discarded. In practice, downstream agents should consume messages within minutes to hours; 14 days provides a large safety margin for maintenance windows.

---

## Step 9: ECS Fargate Service

### What We're Building
An ECS Fargate service that runs the Document Intelligence Agent as a containerized application without managing EC2 instances.

### Security Configuration Highlights
- `readonlyRootFilesystem: true` — the container's filesystem is read-only. Malware that gains code execution in the container cannot write to disk.
- `privileged: false` — the container does not have Linux capabilities beyond what a normal process needs. No ability to load kernel modules, access raw network sockets, or manipulate other containers.
- `logConfiguration` with `awslogs-stream-prefix` — all container logs go to CloudWatch with a consistent prefix, making audit queries reliable.

```bash
# Register the ECS task definition
aws ecs register-task-definition \
  --family "agent09-document-intelligence" \
  --cpu "1024" \
  --memory "2048" \
  --network-mode "awsvpc" \
  --requires-compatibilities "FARGATE" \
  --execution-role-arn "arn:aws:iam::*:role/agent09-task-execution-role" \
  --task-role-arn "arn:aws:iam::*:role/agent09-task-role" \
  --container-definitions '[{
    "name": "agent09",
    "image": "<account>.dkr.ecr.us-east-1.amazonaws.com/agent09-document-intelligence:latest",
    "portMappings": [{"containerPort": 8509, "protocol": "tcp"}],
    "environment": [
      {"name": "LOG_LEVEL", "value": "WARNING"},
      {"name": "PYTHONUNBUFFERED", "value": "1"},
      {"name": "STREAMLIT_SERVER_HEADLESS", "value": "true"},
      {"name": "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION", "value": "true"}
    ],
    "secrets": [
      {
        "name": "OPENAI_API_KEY",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:*:secret:prod/agent09/openai-api-key:api_key::"
      },
      {
        "name": "DATABASE_URL",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:*:secret:prod/agent09/aurora:connection_string::"
      }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/agent09-document-intelligence",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "agent09"
      }
    },
    "linuxParameters": {
      "readonlyRootFilesystem": true,
      "tmpfs": [{"containerPath": "/tmp", "size": 512}]
    },
    "privileged": false,
    "user": "1000:1000",
    "healthCheck": {
      "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('"'"'http://localhost:8509/_stcore/health'"'"')\" || exit 1"],
      "interval": 30,
      "timeout": 10,
      "retries": 3,
      "startPeriod": 60
    }
  }]'
```

---

## Step 10: CloudWatch Alarms and Monitoring

### What We're Building
CloudWatch alarms that notify the operations team when the agent encounters security events or operational problems.

### Why These Specific Alarms
Each alarm is designed to catch a specific security or operational concern unique to document processing:

| Alarm | Threshold | Why It Matters |
|---|---|---|
| `HighHITLQueueDepth` | > 20 pending reviews | A large HITL backlog means SAR/CTR/Government ID documents are not being reviewed promptly. BSA regulations impose time limits on SAR filing (30 days). |
| `PIIDetectedInPayload` | Any occurrence | If PII appears in an output payload, the masking pipeline has failed. This is a regulatory violation (GLBA) and must be investigated immediately. |
| `DocumentRejectionRate` | > 10% of submissions | A high rejection rate may indicate a broken source system feeding malformed documents, or an attempted upload of unsupported file types. |
| `LLMApiErrors` | > 5 errors/5min | LLM API failures cause field extraction to fail or fall back to empty fields. A high error rate means documents are being processed with incomplete extraction. |
| `DatabaseConnectionErrors` | Any occurrence | Database connection failures mean LangGraph cannot persist state. HITL review decisions may be lost. |
| `WAFBlockedRequests` | > 50 blocks/15min | May indicate an active attack against the document upload endpoint. Investigate source IPs. |

```bash
# Example: HITL Queue Depth Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "agent09-HITLQueueDepth" \
  --alarm-description "More than 20 documents pending human review — possible bottleneck or SAR/CTR filing deadline risk" \
  --metric-name "HITLQueueDepth" \
  --namespace "Agent09/DocumentIntelligence" \
  --statistic "Maximum" \
  --period 300 \
  --threshold 20 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions "arn:aws:sns:us-east-1:*:agent09-ops-alerts"

# Example: PII in Payload Alarm (should never fire in a correctly operating system)
aws cloudwatch put-metric-alarm \
  --alarm-name "agent09-PIIInOutputPayload" \
  --alarm-description "CRITICAL: PII detected in an output payload — masking pipeline failure. Requires immediate investigation." \
  --metric-name "PIIInPayloadCount" \
  --namespace "Agent09/DocumentIntelligence" \
  --statistic "Sum" \
  --period 60 \
  --threshold 0 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions "arn:aws:sns:us-east-1:*:agent09-security-incidents" \
  --treat-missing-data "notBreaching"
```

---

## Step 11: Cost Estimate

| Component | Configuration | Monthly Cost |
|---|---|---|
| ECS Fargate | 1 vCPU, 2GB RAM, ~730 hours/month | ~$65–$85 |
| Aurora Serverless v2 | 0.5–4 ACUs (scales with load) | ~$130–$180 |
| Application Load Balancer | ~$25 fixed + data processing | ~$30–$45 |
| WAF | ~$5 base + $0.60/1M requests | ~$10–$20 |
| KMS | $1/key/month + $0.03/10K API calls | ~$5–$10 |
| Secrets Manager | $0.40/secret/month (3 secrets) | ~$2 |
| S3 (document staging) | Variable — depends on document volume | ~$5–$30 |
| SQS (6 queues) | ~$0.40/million messages | ~$5–$15 |
| CloudWatch Logs + Alarms | Log ingestion + 10 alarms | ~$20–$35 |
| NAT Gateway | $0.045/hour + $0.045/GB | ~$35–$50 |
| Amazon Macie | ~$1/GB of S3 data scanned | ~$10–$30 |
| ECR (Docker images) | $0.10/GB storage + data transfer | ~$5–$10 |
| **Total** | | **~$322–$512/month** |

**OpenAI API Costs (not AWS):** Estimated separately. GPT-4o classification + extraction: ~$0.002–$0.008 per document depending on length. At 10,000 documents/month: ~$20–$80/month in LLM costs.

---

## Step 12: Security Checklist for Go-Live

Before processing real documents in production, verify:

- [ ] WAF is attached to the ALB and all rule sets are enabled
- [ ] ALB listener enforces HTTPS (HTTP redirects to HTTPS)
- [ ] TLS certificate is issued by AWS Certificate Manager (not self-signed)
- [ ] Okta SAML authentication is configured on the ALB listener (no unauthenticated access)
- [ ] ECS container runs as uid=1000 (non-root)
- [ ] `readonlyRootFilesystem: true` is set in the task definition
- [ ] No secrets in the task definition environment — all from Secrets Manager
- [ ] Aurora parameter group has `log_statement=none` applied
- [ ] S3 bucket has all public access blocked and Object Lock enabled
- [ ] Macie classification job is running and alerts are routing to SNS
- [ ] CloudWatch alarms are configured and SNS subscription is confirmed
- [ ] KMS key rotation is enabled
- [ ] IAM task role follows least-privilege (no wildcard `*` in actions)
- [ ] VPC Flow Logs are enabled for forensic investigation capability
- [ ] CloudTrail is enabled in the account (logs KMS key usage and Secrets Manager access)
- [ ] ECR image scanning is enabled (scan on push)
- [ ] A pen test or security review has been conducted on the document upload endpoint
