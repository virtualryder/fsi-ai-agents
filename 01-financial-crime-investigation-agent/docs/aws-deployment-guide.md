# AWS Deployment Guide: Financial Crime Investigation Agent
## Enterprise-Grade, Multi-Tenant, Repeatable Deployment Playbook

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [AWS Service Selection & Rationale](#2-aws-service-selection--rationale)
3. [Detailed Architecture Layers](#3-detailed-architecture-layers)
4. [Integration Points & MCP Server Authentication](#4-integration-points--mcp-server-authentication)
5. [Multi-Tenant Customer Deployment Pattern](#5-multi-tenant-customer-deployment-pattern)
6. [Infrastructure as Code (Terraform)](#6-infrastructure-as-code-terraform)
7. [CI/CD Pipeline](#7-cicd-pipeline)
8. [Security & Compliance Configuration](#8-security--compliance-configuration)
9. [Monitoring & Observability](#9-monitoring--observability)
10. [Step-by-Step Deployment Walkthrough](#10-step-by-step-deployment-walkthrough)
11. [Customer Onboarding Checklist](#11-customer-onboarding-checklist)
12. [Cost Estimation](#12-cost-estimation)

---

## 1. Architecture Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CUSTOMER'S NETWORK                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐                    │
│  │  TMS        │    │  Core Banking│    │  Case Mgmt      │                    │
│  │  (Actimize/ │    │  (Temenos/   │    │  (ServiceNow/   │                    │
│  │  Verafin)   │    │  FIS/Fiserv) │    │  Actimize CM)   │                    │
│  └──────┬──────┘    └──────┬───────┘    └────────┬────────┘                    │
│         │                  │                     │                             │
│  ┌──────▼──────────────────▼─────────────────────▼────────┐                    │
│  │                  AWS PrivateLink / VPN / Direct Connect  │                   │
│  └──────────────────────────────┬───────────────────────────┘                   │
└─────────────────────────────────┼───────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────────┐
│                         AWS CLOUD (Per-Customer VPC)                            │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                        PUBLIC SUBNET                                     │   │
│  │  ┌──────────────────┐    ┌───────────────────────────────────────────┐   │   │
│  │  │   CloudFront CDN │───▶│       Application Load Balancer           │   │   │
│  │  │   + WAF          │    │  (HTTPS, TLS 1.3, Cognito Auth)           │   │   │
│  │  └──────────────────┘    └────────────────────┬──────────────────────┘   │   │
│  └───────────────────────────────────────────────┼──────────────────────────┘   │
│                                                   │                             │
│  ┌────────────────────────────────────────────────▼──────────────────────────┐  │
│  │                       PRIVATE SUBNET (App Tier)                           │  │
│  │                                                                           │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    ECS Fargate Cluster                              │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │  │  │
│  │  │  │  Streamlit App  │  │  LangGraph Agent │  │  MCP Auth       │    │  │  │
│  │  │  │  Task (UI)      │  │  Task (Worker)   │  │  Gateway Task   │    │  │  │
│  │  │  │  Port: 8501     │  │  Port: 8080      │  │  Port: 8443     │    │  │  │
│  │  │  └────────┬────────┘  └────────┬─────────┘  └────────┬────────┘    │  │  │
│  │  │           │                    │                     │             │  │  │
│  │  └───────────┼────────────────────┼─────────────────────┼─────────────┘  │  │
│  │              │                    │                     │                │  │
│  │              ▼                    ▼                     ▼                │  │
│  │  ┌──────────────────┐  ┌─────────────────┐  ┌─────────────────────┐    │  │
│  │  │  Amazon SQS      │  │  Amazon Bedrock  │  │  MCP Tool Servers   │    │  │
│  │  │  (Alert Queue)   │  │  (Claude 3.5     │  │  (Containerized,    │    │  │
│  │  │                  │  │  Sonnet / Haiku) │  │  per integration)   │    │  │
│  │  └──────────────────┘  └─────────────────┘  └─────────────────────┘    │  │
│  │                                                                          │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                       PRIVATE SUBNET (Data Tier)                          │ │
│  │                                                                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │ │
│  │  │  RDS Aurora  │  │  DynamoDB    │  │  S3 (SAR     │  │  ElastiCache│  │ │
│  │  │  PostgreSQL  │  │  (Audit      │  │  Documents + │  │  Redis      │  │ │
│  │  │  (Cases)     │  │  Trail)      │  │  Case Files) │  │  (Sessions) │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │ │
│  │                                                                           │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                         SECURITY & OPERATIONS LAYER                       │ │
│  │                                                                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │ │
│  │  │  Secrets     │  │  KMS         │  │  CloudWatch  │  │  AWS Config │ │ │
│  │  │  Manager     │  │  (Encryption)│  │  (Logs+      │  │  + Security │ │ │
│  │  │              │  │              │  │  Metrics)    │  │  Hub        │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### External Service Integrations (Outside AWS)

```
AWS VPC
  │
  ├──[MCP Auth Gateway]──▶  OpenAI API / AWS Bedrock
  ├──[MCP Auth Gateway]──▶  Refinitiv World-Check (Watchlist)
  ├──[MCP Auth Gateway]──▶  ComplyAdvantage (Sanctions)
  ├──[MCP Auth Gateway]──▶  Dow Jones Risk & Compliance (Adverse Media)
  ├──[MCP Auth Gateway]──▶  Sayari / Quantexa (Network Analysis)
  └──[PrivateLink/VPN]────▶  Customer On-Premise Systems (TMS, Core Banking)
```

---

## 2. AWS Service Selection & Rationale

Each service was chosen for specific reasons related to financial-grade compliance, data residency, security controls, and operational reliability.

---

### 2.1 Amazon ECS Fargate

**What it does**: Runs the containerized application — Streamlit UI, LangGraph agent workers, and MCP Auth Gateway — without managing EC2 instances.

**Why chosen over alternatives**:
| Alternative | Why ECS Fargate wins |
|-------------|---------------------|
| EC2 directly | Fargate eliminates OS patching, capacity planning, and reduces attack surface |
| EKS (Kubernetes) | Fargate is operationally simpler; Kubernetes adds unnecessary complexity for this workload |
| Lambda | Investigations run 2-5 minutes end-to-end; Lambda's 15-min max and cold starts are problematic |
| App Runner | Less control over networking, VPC integration, and task-level IAM roles |

**How it's configured**:
```yaml
# ECS Task Definition - Agent Worker
Family: fcia-agent-worker
CPU: 2048         # 2 vCPU — LangGraph graph traversal is CPU-intensive
Memory: 4096      # 4 GB — NetworkX graph analysis + LLM context windows
NetworkMode: awsvpc
RequiresCompatibilities: [FARGATE]
ExecutionRoleArn: arn:aws:iam::ACCOUNT:role/fcia-execution-role
TaskRoleArn: arn:aws:iam::ACCOUNT:role/fcia-task-role  # Scoped Bedrock + S3 + DynamoDB perms

# Environment variables injected from Secrets Manager
Secrets:
  - Name: OPENAI_API_KEY
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:fcia/CUSTOMER_ID/openai-key
  - Name: DATABASE_URL
    ValueFrom: arn:aws:secretsmanager:REGION:ACCOUNT:secret:fcia/CUSTOMER_ID/db-url

# Health check
HealthCheck:
  Command: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
  Interval: 30
  Timeout: 5
  Retries: 3

# Auto-scaling: scale worker tasks based on SQS queue depth
# 0 tasks at idle → up to 20 tasks under load (alert bursts)
```

**How it fits the architecture**: Fargate tasks are the execution layer. The UI task serves investigators; worker tasks process investigations pulled from SQS; the MCP Auth Gateway task brokers all outbound API calls to third-party services.

---

### 2.2 Application Load Balancer (ALB)

**What it does**: Terminates HTTPS, routes traffic to the correct ECS tasks, enforces authentication via Cognito, and provides sticky sessions for the Streamlit UI.

**Why chosen**:
- Native Cognito integration for OIDC/SAML authentication (required for BSA Officer identity)
- Path-based routing: `/` → Streamlit UI, `/api` → Agent API, `/mcp` → MCP Gateway
- WAF integration for DDoS protection and OWASP rule sets
- Access logs to S3 for compliance audit trails

**How it's configured**:
```yaml
# ALB Listener Rules
HTTPS:443:
  - Condition: path-pattern /mcp/*
    Action: forward → mcp-gateway-target-group
    # MCP calls carry Cognito JWT in Authorization header
    # Validated by MCP Auth Gateway directly (not at ALB level)
    # ALB only enforces HTTPS; MCP Gateway does token validation
  - Condition: path-pattern /api/*
    Action: forward → agent-api-target-group
    AuthenticateCognito:
      UserPoolArn: arn:aws:cognito-idp:REGION:ACCOUNT:userpool/POOL_ID
      UserPoolClientId: CLIENT_ID
      UserPoolDomain: fcia-CUSTOMER_ID.auth.us-east-1.amazoncognito.com
      # Cognito redirects to Okta SAML if session not present
      OnUnauthenticatedRequest: authenticate
  - Condition: default
    Action: forward → streamlit-target-group
    AuthenticateCognito:
      UserPoolArn: arn:aws:cognito-idp:REGION:ACCOUNT:userpool/POOL_ID
      UserPoolClientId: CLIENT_ID
      UserPoolDomain: fcia-CUSTOMER_ID.auth.us-east-1.amazoncognito.com
      OnUnauthenticatedRequest: authenticate
      # SessionCookie scoped to domain; HTTPS-only; SameSite=Strict
      SessionCookieName: AWSELBAuthSessionCookie
      SessionTimeout: 28800  # 8 hours — one work shift

# Session stickiness (required for Streamlit WebSocket)
TargetGroup:
  StickinessEnabled: true
  StickinessDuration: 3600  # 1 hour session
  Protocol: HTTP
  HealthCheckPath: /_stcore/health
```

**Authentication flow for investigators**:
```
1. Investigator navigates to https://fcia.customer.com
2. ALB has no valid session cookie → redirects to Cognito Hosted UI
3. Cognito sees only Okta as IdP → immediately redirects to Okta
4. Okta checks AD group membership → prompts for Okta MFA (Push/FIDO2)
5. Okta issues SAML assertion with bsa_role and customer_id attributes
6. Cognito validates SAML assertion, maps attributes, issues JWT tokens
7. ALB receives Cognito JWT, sets encrypted session cookie, forwards to Streamlit
8. Investigator is logged in — their BSA role is available in every request header
```

---

### 2.3 Amazon Cognito

**What it does**: Manages user identity for BSA Officers and investigators. Integrates with the bank's existing Active Directory or SSO.

**Identity architecture**: The organization uses **Active Directory (AD) + Okta** as the enterprise SSO provider. Cognito acts as the AWS-side federation broker — it accepts SAML 2.0 assertions from Okta and issues AWS-scoped JWT tokens for the application and MCP authentication layer. No user credentials ever live in Cognito itself; Okta/AD is always the identity source of truth.

```
Active Directory (on-premise)
  │  AD Connect / Okta AD Agent (real-time sync)
  ▼
Okta (SSO provider)
  │  SAML 2.0 assertion (includes group memberships → BSA roles)
  ▼
Amazon Cognito User Pool (SAML Identity Provider)
  │  Issues Cognito JWT (id_token + access_token)
  ▼
ALB → ECS Streamlit UI  (application authentication)
  AND
MCP Auth Gateway        (service-to-service API authentication)
```

**Why this pattern**:
- Okta/AD is the authoritative identity source — BSA Officer provisioning and deprovisioning happen in AD, not a separate system
- Cognito does not store credentials; it only federates — eliminates a credentials store as an attack surface
- AD group memberships (e.g., `GRP-BSA-Officers`, `GRP-AML-Investigators`) map directly to BSA roles via Okta attribute statements in the SAML assertion
- MFA policy is enforced at Okta — the application inherits enterprise MFA without re-implementing it

**How it's configured**:

**Step A — Okta Application Configuration** (performed by customer's Okta admin):
```yaml
# Okta Admin Console → Applications → Add Application → SAML 2.0
Application:
  Name: "Financial Crime Investigation Agent - {CustomerName}"
  SignOnMethod: SAML 2.0

  SAML Settings:
    SingleSignOnURL: https://fcia-CUSTOMER_ID.auth.us-east-1.amazoncognito.com/saml2/idpresponse
    AudienceURI: urn:amazon:cognito:sp:COGNITO_USER_POOL_ID
    NameIDFormat: EmailAddress
    NameIDValue: user.email

  # Attribute statements — map AD group memberships to BSA roles
  AttributeStatements:
    - Name: bsa_role
      Format: Basic
      Value: |
        isMemberOf("GRP-BSA-Officers") ? "BSA_OFFICER" :
        isMemberOf("GRP-AML-Investigators") ? "INVESTIGATOR" :
        isMemberOf("GRP-AML-Auditors") ? "AUDITOR" :
        "READ_ONLY"
    - Name: customer_id
      Format: Basic
      Value: "first-national-bank"   # Hardcoded per Okta app instance
    - Name: display_name
      Format: Basic
      Value: user.displayName
    - Name: department
      Format: Basic
      Value: user.department

  # Group assignments — only assign to AML/BSA groups in Okta
  Assignments:
    Groups:
      - GRP-BSA-Officers
      - GRP-AML-Investigators
      - GRP-AML-Auditors
```

**Step B — Cognito User Pool SAML Federation**:
```yaml
UserPool:
  Name: fcia-CUSTOMER_ID-users
  # No built-in sign-up — all users come from Okta/AD
  AdminCreateUserConfig:
    AllowAdminCreateUserOnly: true

  # MFA: Okta enforces MFA; Cognito respects the authenticated SAML assertion
  # Do NOT re-require MFA in Cognito — it would create a double-MFA experience
  MFAConfiguration: OFF
  # Okta is configured with phishing-resistant MFA (FIDO2/WebAuthn or Okta Verify Push)

  # SAML Identity Provider — points to Okta
  IdentityProviders:
    - ProviderName: Okta
      ProviderType: SAML
      ProviderDetails:
        MetadataURL: https://CUSTOMER.okta.com/app/OKTA_APP_ID/sso/saml/metadata
        # OR upload metadata XML directly if Okta is not publicly accessible
        IDPSignout: true  # Single logout — logging out of app triggers Okta logout

  # Map Okta SAML attributes to Cognito user attributes
  AttributeMapping:
    email: http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
    custom:bsa_role: bsa_role             # From Okta attribute statement
    custom:customer_id: customer_id       # From Okta attribute statement
    name: display_name

  # Custom attributes for BSA authorization
  Schema:
    - Name: bsa_role
      AttributeDataType: String
      Mutable: true
      # Values: BSA_OFFICER | INVESTIGATOR | AUDITOR | READ_ONLY
    - Name: customer_id
      AttributeDataType: String
      Mutable: false

  # Token validity
  TokenValidityUnits:
    AccessToken: hours    # 8 hours (one work shift — aligns with Okta session duration)
    RefreshToken: days    # 30 days
    IdToken: hours

  # Hosted UI — Cognito redirects to Okta; investigator never sees a Cognito login page
  UserPoolClient:
    SupportedIdentityProviders: [Okta]  # Only Okta — no username/password fallback
    CallbackURLs:
      - https://fcia.CUSTOMER_DOMAIN.com/callback
    LogoutURLs:
      - https://fcia.CUSTOMER_DOMAIN.com/logout
    AllowedOAuthFlows: [code]           # Authorization code flow with PKCE
    AllowedOAuthScopes: [openid, email, profile]
```

**Step C — AD Group Setup** (performed by customer's AD/IT admin):
```
Active Directory Groups:
  GRP-BSA-Officers        → Members: Licensed BSA Officers only
  GRP-AML-Investigators   → Members: AML analyst team
  GRP-AML-Auditors        → Members: Internal audit, compliance oversight
  GRP-FCIA-ReadOnly       → Members: Management reporting access

Okta AD Agent syncs these groups to Okta in real-time.
When an investigator leaves the bank, removing them from AD
immediately revokes access to the application (next token refresh).
```

---

### 2.4 Amazon SQS (Simple Queue Service)

**What it does**: Decouples alert ingestion from investigation processing. TMS alerts arrive as messages; worker tasks pull and process them independently.

**Why chosen**:
- **Decoupling**: TMS alert bursts don't overwhelm the agent. Queue absorbs spikes.
- **Visibility timeout**: If a worker crashes mid-investigation (e.g., network failure), the message becomes visible again and another worker picks it up — no lost alerts.
- **Dead Letter Queue (DLQ)**: Alerts that fail 3x processing attempts go to DLQ for manual review — regulatory requirement that no alert is silently dropped.
- **FIFO variant**: Available if alert processing order matters (e.g., related alerts from same customer)

**How it's configured**:
```yaml
AlertQueue:
  QueueName: fcia-CUSTOMER_ID-alerts.fifo
  FifoQueue: true
  ContentBasedDeduplication: true
  VisibilityTimeout: 600    # 10 minutes — max investigation duration
  MessageRetentionPeriod: 1209600  # 14 days
  KmsMasterKeyId: alias/fcia-CUSTOMER_ID-sqs  # Encrypted at rest

  RedrivePolicy:
    DeadLetterTargetArn: arn:aws:sqs:REGION:ACCOUNT:fcia-CUSTOMER_ID-alerts-dlq
    MaxReceiveCount: 3    # 3 failed attempts → DLQ + CloudWatch alarm

DeadLetterQueue:
  QueueName: fcia-CUSTOMER_ID-alerts-dlq.fifo
  # CloudWatch alarm triggers PagerDuty when DLQ depth > 0
  # Compliance: no alert can be silently discarded
```

---

### 2.5 Amazon Bedrock

**What it does**: Provides LLM inference for the investigation agent — replaces direct OpenAI API calls with an AWS-native, data-residency-controlled model serving layer.

**Why chosen over direct OpenAI API**:
| Factor | OpenAI Direct | AWS Bedrock |
|--------|--------------|-------------|
| Data residency | Data leaves AWS | Data stays in AWS region |
| SOC 2 / HIPAA | OpenAI's controls | AWS's controls (audited) |
| Private connectivity | Internet | VPC endpoint, no internet egress |
| Model options | OpenAI only | Claude 3.5, Llama 3, Mistral, Titan |
| Cost management | Separate billing | Unified AWS billing + Savings Plans |
| Audit trail | Limited | CloudTrail logs every model invocation |

**How it's configured**:
```python
# In agent/nodes.py — replace ChatOpenAI with Bedrock
from langchain_aws import ChatBedrock
import boto3

# IAM role attached to ECS task grants Bedrock:InvokeModel permission
# No API key needed — uses IAM role credentials

llm = ChatBedrock(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    region_name="us-east-1",
    model_kwargs={
        "temperature": 0.1,      # Low temp for compliance precision
        "max_tokens": 8192,
    }
)

# For high-volume, latency-sensitive nodes (alert triage), use Haiku:
triage_llm = ChatBedrock(
    model_id="anthropic.claude-haiku-4-5-20251001",
    model_kwargs={"temperature": 0.1, "max_tokens": 1024}
)

# Bedrock Guardrails — prevent PII leakage in model outputs
# Configure via AWS Console: Bedrock → Guardrails
# Rules: Block credit card numbers, SSNs, account numbers in responses
```

**VPC Endpoint configuration**:
```yaml
# bedrock.REGION.amazonaws.com — private connectivity, no internet
VpcEndpoint:
  ServiceName: com.amazonaws.us-east-1.bedrock-runtime
  VpcEndpointType: Interface
  SubnetIds: [private-subnet-1, private-subnet-2]
  SecurityGroupIds: [bedrock-endpoint-sg]
  # SG rule: only allow inbound 443 from ECS task security group
```

---

### 2.6 Amazon RDS Aurora PostgreSQL

**What it does**: Stores investigation cases, SAR records, investigator assignments, and case status — the authoritative case management database.

**Why Aurora over standard RDS PostgreSQL**:
- **Multi-AZ by default**: Aurora automatically replicates across 3 AZs; no manual standby configuration
- **Storage auto-scaling**: Grows from 10 GB to 128 TB without downtime
- **Backtrack**: Can rewind the database to a point in time within 72 hours — useful for forensic investigation of data anomalies
- **5-year retention**: Aurora supports automated backups up to 35 days + manual snapshots for long-term; use S3 export for BSA 5-year retention

**How it's configured**:
```yaml
Cluster:
  Engine: aurora-postgresql
  EngineVersion: "15.4"
  DatabaseName: fcia_CUSTOMER_ID

  # Multi-AZ
  AvailabilityZones: [us-east-1a, us-east-1b, us-east-1c]

  # Encryption (required for PII/financial data)
  StorageEncrypted: true
  KmsKeyId: alias/fcia-CUSTOMER_ID-rds

  # Backup (BSA requires 5-year retention)
  BackupRetentionPeriod: 35    # Max Aurora automated backup
  # Supplement with weekly S3 exports via Lambda for years 2-5

  # Network isolation
  DBSubnetGroupName: fcia-private-subnet-group
  VpcSecurityGroupIds: [rds-sg]
  # SG: inbound 5432 only from ECS task security groups

  # Performance
  EnablePerformanceInsights: true
  PerformanceInsightsRetentionPeriod: 731  # 2 years

# Instances
Instances:
  Writer:
    InstanceClass: db.r6g.large   # 2 vCPU, 16 GB RAM
  Reader:
    InstanceClass: db.r6g.large
    # Read replicas for reporting/audit queries — don't impact writer
```

---

### 2.7 Amazon DynamoDB

**What it does**: Stores the immutable audit trail — every action taken during every investigation. Chosen for audit trail specifically (not general case storage) because of its properties.

**Why DynamoDB for audit trail (not RDS)**:
- **Immutability**: DynamoDB Streams can be configured as append-only; cannot UPDATE or DELETE with the right IAM policy
- **Throughput**: Audit events are high-volume writes (10+ events per investigation × many concurrent investigations)
- **TTL**: Can auto-expire records older than 5 years (BSA retention limit) — but export to S3 Glacier first
- **Point-in-time recovery**: Any state reconstructible within 35 days

**How it's configured**:
```yaml
Table:
  TableName: fcia-CUSTOMER_ID-audit-trail
  BillingMode: PAY_PER_REQUEST   # Unpredictable volume; avoid over-provisioning

  # Primary key: enables all required queries
  KeySchema:
    - AttributeName: case_id       # Partition key
      KeyType: HASH
    - AttributeName: timestamp     # Sort key (ISO 8601 — sorts lexicographically)
      KeyType: RANGE

  # Global Secondary Index: query all actions by a specific investigator
  GlobalSecondaryIndexes:
    - IndexName: investigator-index
      KeySchema:
        - AttributeName: investigator_id
          KeyType: HASH
        - AttributeName: timestamp
          KeyType: RANGE

  # Encryption
  SSESpecification:
    Enabled: true
    SSEType: KMS
    KMSMasterKeyId: alias/fcia-CUSTOMER_ID-dynamo

  # Immutability: IAM policy denies UpdateItem and DeleteItem for all roles
  # Only PutItem is permitted — all audit records are write-once

  # BSA 5-year retention
  TimeToLiveSpecification:
    AttributeName: ttl
    Enabled: true
  # TTL = current_epoch + (5 * 365 * 24 * 3600)
  # Before expiry: Lambda exports to S3 Glacier Deep Archive
```

---

### 2.8 Amazon S3

**What it does**: Stores generated SAR documents, case evidence files, exported reports, and long-term audit trail archives.

**Why S3**:
- **Durability**: 99.999999999% (11 nines) — exceeds BSA document retention requirements
- **Versioning**: Prevents accidental overwrite of SAR documents
- **Object Lock**: WORM (Write Once Read Many) compliance mode — SAR documents cannot be deleted or modified once filed
- **S3 Intelligent-Tiering**: Automatically moves old records to cheaper storage tiers

**How it's configured**:
```yaml
Buckets:
  SARDocuments:
    BucketName: fcia-CUSTOMER_ID-sar-documents
    VersioningConfiguration: Enabled

    # WORM compliance for filed SARs — cannot be deleted for 5 years
    ObjectLockConfiguration:
      ObjectLockEnabled: Enabled
      Rule:
        DefaultRetention:
          Mode: COMPLIANCE    # Even AWS Support cannot delete
          Years: 5

    # Encryption
    BucketEncryption:
      ServerSideEncryptionConfiguration:
        - ServerSideEncryptionByDefault:
            SSEAlgorithm: aws:kms
            KMSMasterKeyId: alias/fcia-CUSTOMER_ID-s3

    # Block all public access
    PublicAccessBlockConfiguration:
      BlockPublicAcls: true
      BlockPublicPolicy: true
      IgnorePublicAcls: true
      RestrictPublicBuckets: true

    # Lifecycle: SAR documents → Glacier after 90 days (still accessible)
    LifecycleConfiguration:
      Rules:
        - Status: Enabled
          Transitions:
            - Days: 90
              StorageClass: GLACIER
            - Days: 1825  # 5 years
              StorageClass: DEEP_ARCHIVE

  AuditArchive:
    BucketName: fcia-CUSTOMER_ID-audit-archive
    # DynamoDB exports land here; same Object Lock / KMS config
```

---

### 2.9 AWS Secrets Manager

**What it does**: Stores and rotates all credentials — database passwords, third-party API keys, TMS credentials, watchlist service API tokens.

**Why Secrets Manager over Parameter Store or environment variables**:
- **Automatic rotation**: Rotates RDS passwords on schedule; Lambda rotates third-party API keys
- **Fine-grained access**: Each ECS task role gets access only to its specific secrets
- **Audit trail**: Every secret read is logged in CloudTrail — required for SOC 2
- **Cross-account**: Secrets can be shared across accounts (useful for centralized key management)

**Secret structure** (namespaced by customer for multi-tenancy):
```
/fcia/{CUSTOMER_ID}/database/url              → postgresql://user:pass@host/db
/fcia/{CUSTOMER_ID}/llm/openai-api-key        → sk-...
/fcia/{CUSTOMER_ID}/tms/actimize-api-key      → ...
/fcia/{CUSTOMER_ID}/tms/actimize-url          → https://...
/fcia/{CUSTOMER_ID}/watchlist/worldcheck-key  → ...
/fcia/{CUSTOMER_ID}/watchlist/worldcheck-secret → ...
/fcia/{CUSTOMER_ID}/watchlist/complyadvantage → ...
/fcia/{CUSTOMER_ID}/adverse-media/dowjones    → ...
/fcia/{CUSTOMER_ID}/core-banking/api-key      → ...
/fcia/{CUSTOMER_ID}/core-banking/url          → ...
/fcia/{CUSTOMER_ID}/network-intel/sayari-key  → ...
/fcia/{CUSTOMER_ID}/notifications/smtp-pass   → ...
/fcia/{CUSTOMER_ID}/mcp/gateway-signing-key   → RS256 private key for JWT signing
```

---

### 2.10 AWS KMS (Key Management Service)

**What it does**: Provides encryption keys for every data store — RDS, DynamoDB, S3, SQS, and Secrets Manager.

**Why customer-managed KMS keys (CMKs) over AWS-managed keys**:
- **Key revocation**: In a data breach scenario, CMK can be disabled immediately, making all encrypted data inaccessible
- **Key rotation audit**: CloudTrail records every key usage — required for PCI DSS and SOC 2
- **Per-customer keys**: In multi-tenant deployments, each customer has their own CMK — one customer's key compromise cannot affect another's data

**Key hierarchy**:
```
fcia-{CUSTOMER_ID}-master    (root CMK — never used directly)
  ├── fcia-{CUSTOMER_ID}-rds
  ├── fcia-{CUSTOMER_ID}-dynamo
  ├── fcia-{CUSTOMER_ID}-s3
  ├── fcia-{CUSTOMER_ID}-sqs
  └── fcia-{CUSTOMER_ID}-secrets
```

---

### 2.11 Amazon CloudFront + WAF

**What it does**: CloudFront serves as the CDN and HTTPS termination point for the investigator dashboard. WAF protects against web attacks.

**WAF rules configured**:
```yaml
WebACL:
  Rules:
    - Name: AWSManagedRulesCommonRuleSet    # OWASP Top 10
    - Name: AWSManagedRulesSQLiRuleSet      # SQL injection (protects case data)
    - Name: AWSManagedRulesKnownBadInputs   # Log4j, Spring4Shell
    - Name: RateLimit                        # 1000 req/5min per IP (anti-DDoS)
    - Name: GeoRestriction                  # Optional: restrict to bank's countries
```

---

### 2.12 Amazon CloudWatch + X-Ray

**What it does**: Centralized logging, metrics, alerting, and distributed tracing for the entire investigation workflow.

**Why essential for compliance**: BSA Officers must be able to demonstrate that alerts were processed within regulatory timeframes and that the system operated correctly. CloudWatch is the audit evidence.

**Key dashboards configured**:
- Alert queue depth (SQS) — SLA monitoring
- Investigation completion time — average, P95, P99
- Bedrock token usage and latency per node
- SAR generation success rate
- Failed integration calls (TMS, watchlist, adverse media)
- Error rates by investigation node

---

### 2.13 AWS PrivateLink / Site-to-Site VPN / Direct Connect

**What it does**: Provides private, encrypted connectivity between the customer's on-premise banking systems and the AWS VPC — no traffic traverses the public internet.

**Decision matrix**:
| Method | When to use |
|--------|------------|
| **PrivateLink** | Vendor exposes their API as a VPC endpoint service (some modern fintechs support this) |
| **Site-to-Site VPN** | Quick setup for pilot deployments; lower cost; acceptable for smaller data volumes |
| **Direct Connect** | Production deployments; 1-10 Gbps dedicated circuit; lowest latency; required for real-time TMS alert streaming |

---

## 3. Detailed Architecture Layers

### Layer 1: Presentation Layer (Public)

```
Investigators → CloudFront (HTTPS) → WAF → ALB → Cognito Auth → ECS Fargate (Streamlit)
```

- CloudFront caches static Streamlit assets (JS, CSS)
- WAF validates every request before it reaches ALB
- ALB enforces Cognito JWT validation — unauthenticated requests get 401
- Streamlit task serves the investigation dashboard UI

### Layer 2: Application Layer (Private)

```
ALB → ECS Fargate (Agent Worker) ← SQS (Alert Queue)
                     ↓
              MCP Auth Gateway
                     ↓
         [External API integrations]
```

- Agent workers are stateless — they pull from SQS, process, write results to RDS/DynamoDB/S3
- MCP Auth Gateway is the single egress point for all third-party API calls
- Workers scale horizontally: 1 task per concurrent investigation

### Layer 3: Data Layer (Private, Isolated)

```
RDS Aurora  ← Case records, SAR metadata
DynamoDB    ← Immutable audit trail (append-only)
S3          ← SAR PDFs, evidence files, archives
ElastiCache ← Investigator sessions, investigation state cache
```

### Layer 4: Security Layer (Cross-cutting)

```
Secrets Manager  → Credentials injected at task startup
KMS              → All data encrypted at rest
CloudTrail       → All API calls logged
AWS Config       → Compliance rule enforcement
Security Hub     → Centralized findings aggregation
GuardDuty        → Threat detection (unauthorized API calls, credential misuse)
```

---

## 4. Integration Points & MCP Server Authentication

This is the most critical architectural layer — every external data source the agent queries must be accessed through a controlled, authenticated, audited gateway.

### 4.1 MCP (Model Context Protocol) Architecture

Rather than having the LangGraph agent call external APIs directly, all integrations are exposed as **MCP Tool Servers** running as dedicated ECS tasks. The agent calls tools via the MCP protocol; the MCP servers handle authentication, rate limiting, retries, and caching for each external system.

```
LangGraph Agent
      │
      │  MCP Protocol (JSON-RPC 2.0 over HTTPS)
      ▼
MCP Auth Gateway (Port 8443)
  │   ├── JWT validation (Cognito token)
  │   ├── Tool authorization (BSA role check)
  │   ├── Rate limiting (per tool, per customer)
  │   └── Audit logging (every tool call → CloudWatch)
  │
  ├──▶ MCP Server: TMS Connector (Port 8001)
  ├──▶ MCP Server: Core Banking Connector (Port 8002)
  ├──▶ MCP Server: Watchlist Screener (Port 8003)
  ├──▶ MCP Server: Adverse Media (Port 8004)
  ├──▶ MCP Server: Network Intelligence (Port 8005)
  └──▶ MCP Server: Case Management (Port 8006)
```

### 4.2 MCP Auth Gateway — Full Specification

**What it is**: A FastAPI service (ECS Fargate task) that acts as the authentication and authorization layer for all MCP tool calls. It validates Cognito JWTs — which were issued after successful Okta/AD SAML authentication — and enforces BSA role-based tool access.

**Token flow into MCP Gateway**:
```
Okta (SAML) → Cognito (JWT) → ALB session cookie (browser/UI)
                            → Bearer token in Authorization header (agent worker → MCP)

The LangGraph agent worker receives the investigator's Cognito access_token
via the investigation state context. It passes this token as a Bearer header
on every MCP tool call. The gateway validates the token against Cognito's
JWKS endpoint, which in turn was populated from the Okta SAML assertion.
```

```python
# mcp_gateway/main.py — Okta/AD → Cognito JWT authentication for all MCP tool calls

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, jwk
import httpx
import boto3
import json
from functools import lru_cache
from typing import Optional

app = FastAPI()
security = HTTPBearer()

# ─── COGNITO JWKS (backed by Okta SAML federation) ────────────────────────────

COGNITO_REGION = "us-east-1"
COGNITO_USER_POOL_ID = "us-east-1_XXXXXXXXX"
COGNITO_APP_CLIENT_ID = "XXXXXXXXXXXXXXXXXXXXXXXXXX"
COGNITO_JWKS_URL = (
    f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com"
    f"/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
)

@lru_cache(maxsize=1)
def get_jwks():
    """
    Fetch Cognito's JWKS public keys.
    Cognito issues these JWTs after validating the Okta SAML assertion.
    Cached in memory — keys rotate infrequently; Lambda warms the cache on schedule.
    ElastiCache Redis is used for cross-task caching (multiple ECS tasks share one cache).
    """
    # Try ElastiCache first
    cached = redis_client.get("cognito:jwks")
    if cached:
        return json.loads(cached)
    # Fall back to Cognito JWKS endpoint
    response = httpx.get(COGNITO_JWKS_URL, timeout=5.0)
    response.raise_for_status()
    keys = response.json()
    redis_client.setex("cognito:jwks", 3600, json.dumps(keys))  # Cache 1 hour
    return keys

def validate_cognito_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Validate a Cognito JWT that was issued after Okta/AD SAML authentication.

    Claims we expect (populated from Okta attribute statements):
      - sub: Cognito user subject (stable identifier)
      - email: investigator's email (from AD)
      - custom:bsa_role: BSA_OFFICER | INVESTIGATOR | AUDITOR | READ_ONLY
      - custom:customer_id: bank identifier (e.g., "first-national-bank")
      - token_use: "access" (we require access tokens, not ID tokens)
    """
    token = credentials.credentials
    try:
        # Decode header to get key ID (kid)
        unverified_headers = jwt.get_unverified_header(token)
        kid = unverified_headers.get("kid")

        # Find the matching public key from Cognito's JWKS
        jwks = get_jwks()
        public_key = None
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                public_key = jwk.construct(key_data)
                break

        if not public_key:
            raise HTTPException(401, "Unable to find matching public key")

        # Verify signature, expiry, and issuer
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=COGNITO_APP_CLIENT_ID,
            issuer=(
                f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com"
                f"/{COGNITO_USER_POOL_ID}"
            )
        )

        # Require access token type (not ID token)
        if payload.get("token_use") != "access":
            raise HTTPException(401, "Must use access token, not ID token")

        # Require BSA role claim — populated from Okta/AD group membership
        if "custom:bsa_role" not in payload:
            raise HTTPException(
                403,
                "Missing bsa_role claim. Ensure user is assigned to a BSA AD group in Okta."
            )

        # Require customer_id claim — set in Okta attribute statement per app instance
        if "custom:customer_id" not in payload:
            raise HTTPException(403, "Missing customer_id claim")

        return payload

    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {str(e)}")

# ─── BSA ROLE → TOOL AUTHORIZATION ───────────────────────────────────────────
# These roles map directly to AD groups (GRP-BSA-Officers, GRP-AML-Investigators, etc.)

TOOL_PERMISSIONS = {
    # Any authenticated investigator or BSA Officer
    "get_customer_profile":   ["BSA_OFFICER", "INVESTIGATOR"],
    "screen_watchlist":       ["BSA_OFFICER", "INVESTIGATOR"],
    "get_transactions":       ["BSA_OFFICER", "INVESTIGATOR"],
    "search_adverse_media":   ["BSA_OFFICER", "INVESTIGATOR"],
    "analyze_network":        ["BSA_OFFICER", "INVESTIGATOR"],
    "get_alert_details":      ["BSA_OFFICER", "INVESTIGATOR"],

    # BSA Officer only — regulated compliance actions
    "generate_sar_narrative": ["BSA_OFFICER"],
    "approve_sar":            ["BSA_OFFICER"],
    "file_sar_record":        ["BSA_OFFICER"],
    "close_case":             ["BSA_OFFICER"],

    # Auditors and BSA Officers — read-only oversight
    "view_audit_trail":       ["BSA_OFFICER", "AUDITOR", "INVESTIGATOR"],
    "export_case":            ["BSA_OFFICER", "AUDITOR"],
    "view_case_history":      ["BSA_OFFICER", "AUDITOR", "INVESTIGATOR", "READ_ONLY"],
}

def authorize_tool(tool_name: str, user_payload: dict):
    bsa_role = user_payload.get("custom:bsa_role", "READ_ONLY")
    allowed_roles = TOOL_PERMISSIONS.get(tool_name, [])
    if bsa_role not in allowed_roles:
        raise HTTPException(
            403,
            f"AD role '{bsa_role}' is not authorized for tool '{tool_name}'. "
            f"Required roles: {allowed_roles}"
        )

# ─── MCP TOOL PROXY ──────────────────────────────────────────────────────────

@app.post("/mcp/{server_name}/call")
async def proxy_tool_call(
    server_name: str,
    request: MCPToolCallRequest,
    user: dict = Depends(validate_cognito_jwt)
):
    """
    Gateway entry point for all MCP tool calls.

    Authentication chain:
      AD group membership → Okta SAML → Cognito JWT → This gateway → MCP tool server

    1. Validate Cognito JWT (signed after Okta/AD SAML auth)
    2. Authorize tool against BSA role (derived from AD group)
    3. Rate limit per customer + tool
    4. Forward to internal MCP server (VPC-private)
    5. Write immutable audit log entry
    """
    tool_name = request.tool_name
    customer_id = user["custom:customer_id"]
    bsa_role = user["custom:bsa_role"]

    # Step 2: Role authorization (AD group → BSA role → tool permission)
    authorize_tool(tool_name, user)

    # Step 3: Rate limiting (per customer_id + tool, 1-minute sliding window)
    rate_key = f"rate:{customer_id}:{tool_name}"
    call_count = redis_client.incr(rate_key)
    if call_count == 1:
        redis_client.expire(rate_key, 60)
    if call_count > RATE_LIMITS.get(tool_name, 100):
        raise HTTPException(429, f"Rate limit exceeded for {tool_name}")

    # Step 4: Forward to internal MCP server (private VPC DNS — never leaves AWS)
    mcp_server_url = MCP_SERVER_URLS[server_name]
    response = await forward_to_mcp_server(mcp_server_url, request)

    # Step 5: Immutable audit log → DynamoDB (append-only IAM policy)
    await log_tool_call(
        tool_name=tool_name,
        user_sub=user["sub"],           # Cognito subject (stable Okta user ID)
        user_email=user.get("email"),   # From AD via Okta SAML
        bsa_role=bsa_role,              # AD group membership
        customer_id=customer_id,
        case_id=request.context.get("case_id"),
        success=response.success,
        latency_ms=response.latency_ms,
        timestamp=datetime.utcnow().isoformat()
    )

    return response

# ─── HEALTH / READINESS ──────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """ECS health check endpoint — verifies Cognito JWKS reachable."""
    try:
        get_jwks()  # Will raise if Cognito unreachable
        return {"status": "healthy", "idp": "okta-cognito-federation"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}, 503
```

---

### 4.3 Integration Point: Transaction Monitoring System (TMS)

**Integration type**: Inbound (TMS → AWS) + Outbound (AWS → TMS)

**Inbound — Alert streaming**:
```
TMS (Actimize / Verafin / etc.)
  │
  │  Webhook POST or scheduled pull
  ▼
API Gateway (REST, public endpoint)
  │  JWT validation, schema validation
  ▼
Lambda (alert normalizer)
  │  Normalize to InvestigationState.AlertSchema
  ▼
SQS Alert Queue
  │
  ▼
ECS Agent Worker (picks up alert, starts investigation)
```

**Outbound — Transaction history queries**:
```
ECS Agent Worker
  │  MCP protocol
  ▼
MCP Auth Gateway
  │  JWT + role check
  ▼
MCP Server: TMS Connector (ECS task)
  │  Holds TMS API credentials (from Secrets Manager)
  │  Implements rate limiting, retry with backoff
  ▼
Customer TMS API (via PrivateLink or VPN)
```

**MCP TMS Connector — tools exposed**:
```python
# tools exposed by MCP Server: tms-connector
tools = [
    MCPTool(
        name="get_alert_details",
        description="Fetch full alert record from TMS by alert_id",
        input_schema={
            "alert_id": str,
            "include_transactions": bool  # Whether to include raw txn data
        }
    ),
    MCPTool(
        name="get_transaction_history",
        description="12-month transaction history for an account",
        input_schema={
            "account_id": str,
            "months": int,              # 1-24
            "transaction_types": list   # WIRE, ACH, CHECK, CASH, etc.
        }
    ),
    MCPTool(
        name="get_structured_alerts",
        description="Get structuring-flagged alerts for a customer",
        input_schema={"customer_id": str, "lookback_days": int}
    ),
    MCPTool(
        name="update_alert_status",
        description="Update alert disposition in TMS (SAR_FILED, CLOSED, etc.)",
        input_schema={
            "alert_id": str,
            "status": str,
            "disposition_reason": str,
            "case_id": str
        }
    )
]
```

**Authentication to TMS** (stored in Secrets Manager, retrieved by MCP server at startup):
```python
# Actimize SAM — OAuth 2.0 client credentials
client = ActimizeClient(
    base_url=secret("tms/actimize-url"),
    client_id=secret("tms/actimize-client-id"),
    client_secret=secret("tms/actimize-client-secret"),
    token_url=f"{base_url}/oauth/token"
)
# Token cached in ElastiCache; refreshed 60s before expiry
```

---

### 4.4 Integration Point: Core Banking / KYC System

**Integration type**: Read-only outbound queries for customer data

```
MCP Auth Gateway → MCP Server: Core Banking → Customer Core Banking API (VPN/PrivateLink)
```

**Tools exposed**:
```python
tools = [
    MCPTool(name="get_customer_profile",
            description="Full KYC record, risk tier, beneficial owners"),
    MCPTool(name="get_account_details",
            description="Account type, open date, status, balance"),
    MCPTool(name="get_edd_status",
            description="Enhanced Due Diligence status and documentation"),
    MCPTool(name="get_related_accounts",
            description="All accounts linked to a customer (joint, business)"),
    MCPTool(name="get_beneficial_owners",
            description="Beneficial ownership chain (CDD Rule compliance)")
]
```

**Authentication**: OAuth 2.0 or API Key (vendor-specific) from Secrets Manager
**Connection**: AWS PrivateLink (if vendor supports) or customer-managed VPN tunnel

---

### 4.5 Integration Point: Watchlist & Sanctions Screening

**Integration type**: Outbound query to third-party compliance data vendors

```
MCP Server: Watchlist Screener
  │
  ├──▶ Refinitiv World-Check One API (HTTPS, OAuth 2.0)
  ├──▶ ComplyAdvantage API (HTTPS, API Key)
  ├──▶ OFAC SDN API (HTTPS, public — no auth)
  └──▶ UN/EU Sanctions feeds (HTTPS, public — no auth)
```

**Critical compliance note**: Results from watchlist screening are **never cached** beyond the current investigation. Sanctions lists change daily; a cached "no hit" could be stale and expose the bank to OFAC violations.

```python
# MCP Watchlist Server — no caching of screening results
MCPTool(
    name="screen_entity",
    description="Screen name + DOB + nationality against all watchlists",
    input_schema={
        "name": str,
        "date_of_birth": Optional[str],
        "nationality": Optional[str],
        "entity_type": str,  # INDIVIDUAL | ORGANIZATION
        "screening_lists": list  # ["OFAC_SDN", "PEP", "EU_SANCTIONS", "UN_SANCTIONS"]
    },
    # Cache TTL: 0 — always fresh for compliance
    cache_ttl_seconds=0
)
```

**Authentication**: API keys from Secrets Manager; automatic rotation via Lambda every 90 days

---

### 4.6 Integration Point: Adverse Media Search

**Integration type**: Outbound query to news/OSINT vendors

```
MCP Server: Adverse Media → Dow Jones Risk & Compliance API
                          → LexisNexis Nexis+ API
                          → ComplyAdvantage (if adverse media add-on licensed)
```

**Tools exposed**:
```python
MCPTool(
    name="search_adverse_media",
    description="Search for news, court records, regulatory actions about an entity",
    input_schema={
        "entity_name": str,
        "entity_type": str,
        "lookback_years": int,  # 1-10 years
        "categories": list      # ["FINANCIAL_CRIME", "SANCTIONS", "FRAUD", "LEGAL"]
    },
    # Cache: 24 hours for adverse media (acceptable; news doesn't change hourly)
    cache_ttl_seconds=86400
)
```

---

### 4.7 Integration Point: Network Intelligence / Corporate Data

**Integration type**: Outbound query to corporate registry and network analysis vendors

```
MCP Server: Network Intelligence → Sayari Analytics API
                                 → OpenCorporates API
                                 → FinScan / IDEX (entity resolution)
```

**Tools exposed**:
```python
MCPTool(
    name="get_entity_network",
    description="Get corporate ownership and relationship network for an entity",
    input_schema={"entity_name": str, "depth": int}  # depth 1-3 hops
),
MCPTool(
    name="check_shell_company_indicators",
    description="Check for shell company risk indicators",
    input_schema={"entity_name": str, "jurisdiction": str}
),
MCPTool(
    name="get_beneficial_ownership",
    description="Trace beneficial ownership chain to UBO (Ultimate Beneficial Owner)",
    input_schema={"entity_name": str, "jurisdiction": str}
)
```

---

### 4.8 Integration Point: Case Management System

**Integration type**: Bidirectional — read open cases, write investigation results

```
MCP Server: Case Management → Customer Case Mgmt System (ServiceNow / Actimize CM)
                            → Internal (RDS Aurora + DynamoDB for cases managed in-platform)
```

**Tools exposed**:
```python
MCPTool(name="create_case",        description="Create new investigation case record"),
MCPTool(name="update_case_status", description="Update case status and notes"),
MCPTool(name="assign_case",        description="Assign case to investigator"),
MCPTool(name="get_related_cases",  description="Find prior cases for this customer"),
MCPTool(name="file_sar_record",    description="Record SAR filing in case management")
# Note: actual SAR submission to FinCEN is a separate manual step via BSA E-Filing
```

---

### 4.9 Integration Point: FinCEN SAR E-Filing (Compliance Boundary)

**This is intentionally NOT automated.** The agent generates the SAR narrative and populates the structured SAR fields, but actual submission to FinCEN's BSA E-Filing System must be performed by a licensed BSA Officer via the FinCEN portal.

The platform exports a structured SAR package:
```
S3: fcia-{CUSTOMER_ID}-sar-documents/
  └── {year}/{month}/
      └── SAR-{case_id}-{alert_id}.json    ← Structured SAR data (FinCEN Form 111 fields)
      └── SAR-{case_id}-{alert_id}.pdf     ← Human-readable narrative for BSA Officer review
      └── SAR-{case_id}-{alert_id}.xml     ← FinCEN BSA E-Filing XML format (import-ready)
```

The BSA Officer reviews the PDF, makes any edits in the Streamlit UI, and manually submits the XML to FinCEN BSA E-Filing. The platform records the FinCEN confirmation number upon submission.

---

## 5. Multi-Tenant Customer Deployment Pattern

Each customer (financial institution) gets a **fully isolated AWS deployment**. There is no shared infrastructure between customers — this is non-negotiable for financial data.

### Option A: Separate AWS Account per Customer (Recommended)

```
AWS Organizations
  ├── Management Account (billing, SSO)
  ├── Shared Services Account (ECR, CI/CD artifacts)
  ├── Customer A Account  (VPC, ECS, RDS, DynamoDB, S3, KMS — fully isolated)
  ├── Customer B Account  (VPC, ECS, RDS, DynamoDB, S3, KMS — fully isolated)
  └── Customer C Account  (...)
```

**Why separate accounts**:
- AWS account = hardest isolation boundary
- Blast radius containment: a misconfiguration in Customer A cannot affect Customer B
- Billing transparency: each customer's AWS costs are clear
- Regulatory: many banks require contractual isolation at account level

### Option B: Single Account, Separate VPCs (Cost-optimized, smaller customers)

```
Single AWS Account
  ├── VPC: customer-a  (all resources tagged customer_id=A)
  ├── VPC: customer-b  (all resources tagged customer_id=B)
  └── KMS keys, Secrets, S3 buckets are customer-namespaced
```

**Tradeoff**: Lower AWS account overhead, but weaker isolation — suitable for smaller institutions where contractual isolation at the VPC level is acceptable.

### Repeatable Deployment: Terraform Module

A single Terraform module provisions all infrastructure for one customer:

```hcl
# terraform/customer-deployment/main.tf
module "fcia_customer" {
  source  = "git::https://github.com/your-org/fcia-terraform//modules/customer"

  # ─── Required: Customer Identity ──────────────────────────────────────────
  customer_id        = "first-national-bank"    # Unique slug; used in all resource names
  customer_full_name = "First National Bank"
  aws_region         = "us-east-1"
  aws_account_id     = "123456789012"

  # ─── Networking ───────────────────────────────────────────────────────────
  vpc_cidr            = "10.10.0.0/16"
  availability_zones  = ["us-east-1a", "us-east-1b", "us-east-1c"]

  # ─── Application ──────────────────────────────────────────────────────────
  ecs_cpu_agent       = 2048     # Increase for high alert volumes
  ecs_memory_agent    = 4096
  ecs_agent_min_tasks = 1
  ecs_agent_max_tasks = 20       # Max concurrent investigations

  # ─── Database ─────────────────────────────────────────────────────────────
  rds_instance_class  = "db.r6g.large"
  rds_backup_days     = 35

  # ─── LLM Configuration ────────────────────────────────────────────────────
  llm_provider        = "bedrock"   # "bedrock" | "openai" | "azure_openai"
  bedrock_model_id    = "anthropic.claude-3-5-sonnet-20241022-v2:0"

  # ─── Authentication (Okta → AD federation) ────────────────────────────────
  # From: Okta Admin Console → Applications → FCIA App → Sign On → Identity Provider metadata
  cognito_okta_saml_metadata_url = "https://first-national-bank.okta.com/app/APP_ID/sso/saml/metadata"
  # AD groups that will map to BSA roles (must exist in customer's AD and be synced to Okta)
  ad_group_bsa_officers     = "GRP-BSA-Officers"
  ad_group_investigators    = "GRP-AML-Investigators"
  ad_group_auditors         = "GRP-AML-Auditors"

  # ─── Integration Toggles ───────────────────────────────────────────────────
  # Enable only the integrations the customer has licensed
  enable_tms_actimize      = true
  enable_tms_verafin       = false
  enable_watchlist_worldcheck    = true
  enable_watchlist_complyadvantage = false
  enable_adverse_media_dowjones  = true
  enable_network_intel_sayari    = false   # Add if customer licenses Sayari

  # ─── Bank Identity (for SAR filing) ────────────────────────────────────────
  bank_name            = "First National Bank"
  bank_ein             = "XX-XXXXXXX"
  bank_rssd_id         = "XXXXXXX"
  bsa_officer_email    = "bsa@first-national-bank.com"

  # ─── Notifications ─────────────────────────────────────────────────────────
  alert_email          = "aml-alerts@first-national-bank.com"
  pagerduty_service_key = var.pagerduty_key  # From secrets

  # ─── Compliance ────────────────────────────────────────────────────────────
  enable_s3_object_lock = true    # WORM for SAR documents
  audit_retention_years = 5       # BSA requirement
  enable_guardduty      = true
  enable_security_hub   = true
}
```

**Deploying a new customer** (after template is created):
```bash
# 1. Copy customer config
cp terraform/customers/template.tfvars terraform/customers/new-bank.tfvars

# 2. Edit customer-specific values
vim terraform/customers/new-bank.tfvars

# 3. Initialize and plan
cd terraform/customer-deployment
terraform init -backend-config="key=customers/new-bank/terraform.tfstate"
terraform plan -var-file="../customers/new-bank.tfvars"

# 4. Deploy (takes ~12 minutes for full stack)
terraform apply -var-file="../customers/new-bank.tfvars"

# 5. Load initial secrets
./scripts/load-customer-secrets.sh new-bank

# 6. Run deployment smoke test
./scripts/smoke-test.sh new-bank
```

---

## 6. Infrastructure as Code (Terraform)

### Module Structure
```
terraform/
├── modules/
│   ├── networking/          # VPC, subnets, NAT gateway, security groups
│   ├── ecs-cluster/         # ECS cluster, capacity providers
│   ├── ecs-services/        # Task definitions: UI, worker, MCP gateway
│   ├── database/            # Aurora PostgreSQL cluster
│   ├── dynamodb/            # Audit trail table
│   ├── s3/                  # SAR documents + audit archive buckets
│   ├── sqs/                 # Alert queue + DLQ
│   ├── cognito/             # User pool + SAML configuration
│   ├── kms/                 # CMK key hierarchy
│   ├── secrets/             # Secrets Manager secrets (empty shells — values loaded separately)
│   ├── bedrock/             # Bedrock model access, guardrails, VPC endpoint
│   ├── mcp-servers/         # MCP server task definitions per integration
│   ├── alb/                 # Load balancer, listener rules, target groups
│   ├── cloudfront/          # CDN distribution + WAF
│   ├── monitoring/          # CloudWatch dashboards, alarms, X-Ray
│   └── security/            # GuardDuty, Security Hub, Config rules
│
├── customer-deployment/     # Root module — composes all modules for one customer
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
│
├── customers/               # Per-customer .tfvars files
│   ├── template.tfvars      # Copy this for each new customer
│   ├── first-national-bank.tfvars
│   └── community-credit-union.tfvars
│
└── shared/                  # One-time shared infrastructure
    ├── ecr/                 # Shared ECR repository for Docker images
    ├── cicd/                # CodePipeline for builds
    └── organizations/       # AWS Organizations config
```

---

## 7. CI/CD Pipeline

```
GitHub / CodeCommit
  │  Push to main branch
  ▼
AWS CodePipeline
  │
  ├── Stage 1: Source
  │   └── Pull code from repo
  │
  ├── Stage 2: Build (CodeBuild)
  │   ├── Run pytest test suite
  │   ├── Run bandit (Python security scanning)
  │   ├── Run safety (dependency vulnerability check)
  │   └── Build Docker images:
  │       ├── fcia-app:latest     (Streamlit UI)
  │       ├── fcia-agent:latest   (LangGraph worker)
  │       ├── fcia-mcp-gateway:latest
  │       └── fcia-mcp-{tms,core-banking,...}:latest
  │
  ├── Stage 3: Push
  │   └── Push images to ECR (shared repository)
  │
  ├── Stage 4: Deploy to Staging
  │   └── Update ECS task definitions for staging customer
  │       Run integration tests against staging
  │
  └── Stage 5: Deploy to Production
      ├── Manual approval gate (required for financial software)
      └── Rolling ECS deployment:
          - New tasks start with new image
          - ALB health checks validate new tasks
          - Old tasks drain and terminate
          - Zero-downtime deployment
```

---

## 8. Security & Compliance Configuration

### Network Security Groups

```
# ALB Security Group
alb-sg:
  Inbound: 443 from 0.0.0.0/0 (internet HTTPS)
  Outbound: 8501 to ecs-ui-sg (Streamlit)
            8080 to ecs-agent-sg (Agent API)
            8443 to ecs-mcp-sg (MCP Gateway)

# ECS UI Security Group
ecs-ui-sg:
  Inbound: 8501 from alb-sg
  Outbound: 5432 to rds-sg (PostgreSQL)
            6379 to redis-sg (ElastiCache)
            443 to ecs-mcp-sg (MCP calls)

# ECS Agent Worker Security Group
ecs-agent-sg:
  Inbound: 8080 from alb-sg
           Also pulls from SQS (no inbound needed — SQS uses HTTPS polling)
  Outbound: 443 to bedrock-endpoint-sg (Bedrock)
            5432 to rds-sg
            6379 to redis-sg
            443 to ecs-mcp-sg

# MCP Gateway Security Group
ecs-mcp-sg:
  Inbound: 8443 from ecs-ui-sg, ecs-agent-sg
  Outbound: 8001-8006 to ecs-mcp-servers-sg (MCP tool servers)

# MCP Tool Servers Security Group
ecs-mcp-servers-sg:
  Inbound: 8001-8006 from ecs-mcp-sg
  Outbound: 443 to 0.0.0.0/0 via NAT Gateway (external vendor APIs)
            Also: 443 to customer VPN endpoint (for on-premise systems)
```

### IAM Roles (Principle of Least Privilege)

```yaml
# ECS Task Role — Agent Worker
# Only what the agent actually needs
fcia-agent-task-role:
  Allow:
    - bedrock:InvokeModel
      Resource: arn:aws:bedrock:*::foundation-model/anthropic.claude-*

    - sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes
      Resource: arn:aws:sqs:REGION:ACCOUNT:fcia-CUSTOMER_ID-alerts*

    - secretsmanager:GetSecretValue
      Resource: arn:aws:secretsmanager:*:*:secret:/fcia/CUSTOMER_ID/*

    - s3:PutObject
      Resource: arn:aws:s3:::fcia-CUSTOMER_ID-sar-documents/*

    - dynamodb:PutItem
      Resource: arn:aws:dynamodb:*:*:table/fcia-CUSTOMER_ID-audit-trail
      # Note: NO UpdateItem or DeleteItem — audit trail is append-only

    - kms:Decrypt, kms:GenerateDataKey
      Resource: arn:aws:kms:*:*:key/CUSTOMER_KMS_KEY_IDS
```

### Compliance Controls via AWS Config

```
AWS Config Rules (auto-remediated):
  ✓ rds-storage-encrypted              — RDS must be encrypted
  ✓ dynamodb-table-encrypted-at-rest   — DynamoDB must use KMS
  ✓ s3-bucket-server-side-encryption-enabled
  ✓ s3-bucket-public-read-prohibited
  ✓ ecs-task-definition-no-privileged-containers
  ✓ secretsmanager-rotation-enabled-check
  ✓ cloudtrail-enabled
  ✓ multi-region-cloudtrail-enabled
  ✓ guardduty-enabled-centralized
  ✓ cognito-user-pool-mfa-enabled      — MFA required for all users
```

---

## 9. Monitoring & Observability

### CloudWatch Dashboard: "FCIA Operations"

```
Row 1 — SLA Monitoring
  [Alert Queue Depth]  [Investigations In Progress]  [Avg Investigation Time]

Row 2 — AI Health
  [Bedrock Latency P50/P95]  [Bedrock Token Usage]  [LLM Error Rate]

Row 3 — Integration Health
  [TMS Connector Success Rate]  [Watchlist API Latency]  [Adverse Media API Latency]

Row 4 — Business Metrics
  [Alerts Processed Today]  [SARs Generated]  [Cases Closed]  [Escalation Rate]

Row 5 — Errors & Alerts
  [DLQ Depth (0 = healthy)]  [ECS Task Errors]  [Database Connection Errors]
```

### Critical Alarms

```yaml
Alarms:
  - Name: DLQ-Has-Messages
    Description: "Alert failed processing 3x — requires manual review"
    Metric: ApproximateNumberOfMessagesVisible (DLQ)
    Threshold: > 0
    Action: SNS → PagerDuty (immediate page to BSA Officer)

  - Name: Investigation-SLA-Breach
    Description: "Investigations taking > 10 minutes (SLA breach)"
    Metric: Custom metric fcia/InvestigationDurationSeconds
    Threshold: P95 > 600 seconds
    Action: SNS → Email to ops team

  - Name: Watchlist-API-Down
    Description: "Watchlist screening unavailable — OFAC risk"
    Metric: fcia/WatchlistAPISuccessRate
    Threshold: < 95% over 5 minutes
    Action: SNS → PagerDuty (critical — OFAC compliance impact)

  - Name: SAR-Deadline-Approaching
    Description: "SAR filing deadline within 5 days — BSA Officer action required"
    Metric: Custom metric from Lambda (scans RDS for approaching deadlines)
    Threshold: Any case with sar_deadline within 5 days AND status != SAR_FILED
    Action: SNS → Email to BSA Officer
```

---

## 10. Step-by-Step Deployment Walkthrough

### Prerequisites
- AWS CLI configured with admin credentials for target account
- Terraform >= 1.6.0 installed
- Docker Desktop running
- Access to customer's SSO metadata URL (for Cognito SAML)
- Customer's TMS API credentials
- Watchlist vendor API credentials

### Step 1: Bootstrap Shared Infrastructure (One-time, per your organization)

```bash
# Create shared ECR repository for Docker images
cd terraform/shared/ecr
terraform init && terraform apply

# Set up AWS Organizations structure (if using separate accounts per customer)
cd terraform/shared/organizations
terraform init && terraform apply

# Build and push initial Docker images
cd ..  # repo root
docker build -t fcia-app -f Dockerfile .
docker tag fcia-app:latest ${ECR_REGISTRY}/fcia-app:latest
docker push ${ECR_REGISTRY}/fcia-app:latest
# Repeat for fcia-agent, fcia-mcp-gateway, fcia-mcp-tms, etc.
```

### Step 2: Create Customer Configuration

```bash
# Copy and edit customer config
cp terraform/customers/template.tfvars terraform/customers/first-national-bank.tfvars

# Edit the file with customer-specific values:
# - customer_id, customer_full_name
# - VPC CIDR ranges
# - Cognito SAML metadata URL
# - Which integrations to enable
# - Bank identity fields for SAR filing
# - Alert email addresses
vim terraform/customers/first-national-bank.tfvars
```

### Step 3: Deploy Infrastructure

```bash
cd terraform/customer-deployment

# Initialize Terraform with customer-specific state file
terraform init \
  -backend-config="bucket=your-terraform-state-bucket" \
  -backend-config="key=customers/first-national-bank/terraform.tfstate" \
  -backend-config="region=us-east-1"

# Review what will be created
terraform plan -var-file="../customers/first-national-bank.tfvars" -out=plan.tfplan

# Apply (takes ~12 minutes)
terraform apply plan.tfplan
```

### Step 4: Load Secrets

```bash
# After infrastructure is created, load API keys into Secrets Manager
# (Never stored in Terraform — loaded separately for security)

./scripts/load-customer-secrets.sh first-national-bank \
  --openai-key "sk-..." \
  --actimize-url "https://actimize.first-national-bank.com/api" \
  --actimize-key "..." \
  --worldcheck-key "..." \
  --worldcheck-secret "..." \
  --dowjones-token "..." \
  --core-banking-url "https://core.first-national-bank.com/api/v1" \
  --core-banking-key "..."
```

### Step 5: Configure Network Connectivity

```bash
# Option A: Site-to-Site VPN to customer's data center (for on-premise TMS/core banking)
# Configure in AWS Console: VPC → Site-to-Site VPN Connections
# Provide customer with BGP ASN and tunnel configuration

# Option B: PrivateLink (for vendors that support it)
# Accept VPC endpoint service invitation from vendor
aws ec2 accept-vpc-endpoint-connections \
  --service-id vpce-svc-VENDOR_ID \
  --vpc-endpoint-ids vpce-YOUR_ENDPOINT_ID
```

### Step 6: Provision BSA Officer Access via Okta/AD

With the Okta + AD integration, **no accounts are created in Cognito directly**. Access is granted by adding users to the correct AD groups — Cognito and the application automatically pick up the role from Okta's SAML assertion.

```bash
# ─── PERFORMED BY CUSTOMER'S IT/AD ADMIN ─────────────────────────────────────

# Add BSA Officer to the correct AD group
# (PowerShell on AD Domain Controller, or via ADUC GUI)
Add-ADGroupMember -Identity "GRP-BSA-Officers" -Members "jsmith"
Add-ADGroupMember -Identity "GRP-BSA-Officers" -Members "mwilliams"

# Add AML Investigators
Add-ADGroupMember -Identity "GRP-AML-Investigators" -Members "analyst1"
Add-ADGroupMember -Identity "GRP-AML-Investigators" -Members "analyst2"

# Add Auditors (read + audit trail access)
Add-ADGroupMember -Identity "GRP-AML-Auditors" -Members "internal.auditor"

# ─── OKTA ADMIN STEPS ─────────────────────────────────────────────────────────
# 1. Okta AD Agent syncs group memberships automatically (near real-time)
# 2. In Okta Admin Console → Applications → FCIA App:
#    - Assign group "GRP-BSA-Officers" to the application
#    - Assign group "GRP-AML-Investigators" to the application
#    - Assign group "GRP-AML-Auditors" to the application
# 3. Users in these groups can now authenticate immediately

# ─── VERIFY ACCESS ────────────────────────────────────────────────────────────
# User navigates to: https://fcia.first-national-bank.com
# → Redirected to Okta
# → Okta checks AD group membership
# → MFA prompt (Okta Verify Push or FIDO2)
# → Redirected back to investigation dashboard
# → bsa_role claim visible in JWT = "BSA_OFFICER"

# ─── REVOCATION (OFFBOARDING) ─────────────────────────────────────────────────
# When an investigator leaves the bank:
# IT removes them from AD → Okta syncs → their Cognito JWT expires (8h max)
# No action needed in Cognito or the application directly
Remove-ADGroupMember -Identity "GRP-AML-Investigators" -Members "departing.analyst"
# Access revoked within 8 hours (next token refresh fails)
# For immediate revocation: IT disables the AD account entirely
Disable-ADAccount -Identity "departing.analyst"
# → All active sessions terminated at next ALB token validation check
```

### Step 7: Configure TMS Webhook (Alert Ingestion)

```bash
# Get the API Gateway endpoint URL from Terraform outputs
terraform output api_gateway_alert_endpoint
# → https://xyz.execute-api.us-east-1.amazonaws.com/prod/alerts

# Provide this URL to the customer's TMS team
# They configure their TMS to POST new alerts to this endpoint
# Provide the API key (from Secrets Manager) for webhook authentication
```

### Step 8: Smoke Test

```bash
# Run automated smoke test — verifies all components are working
./scripts/smoke-test.sh first-national-bank

# Tests:
# ✓ Streamlit UI accessible and loads
# ✓ Cognito authentication works
# ✓ SQS can receive test alert
# ✓ Agent worker picks up and processes alert
# ✓ Bedrock/OpenAI responds to LLM call
# ✓ MCP servers reachable via MCP Gateway
# ✓ RDS case record created
# ✓ DynamoDB audit trail written
# ✓ S3 SAR document generated
# ✓ CloudWatch metrics flowing
```

### Step 9: Load Sample Data and Train Investigators

```bash
# Load sample alerts for investigator training
python scripts/load-training-data.py \
  --customer-id first-national-bank \
  --data-file data/fixtures/sample_alerts.json

# Investigators can now log in and run through the workflow
# with realistic (but non-production) data
```

---

## 11. Customer Onboarding Checklist

### Before Deployment
- [ ] Signed MSA and data processing agreement
- [ ] Customer AWS account created (or VPC CIDR allocated)
- [ ] Customer provides TMS vendor and version
- [ ] Customer provides core banking vendor and API documentation
- [ ] Customer provides watchlist vendor API credentials
- [ ] Customer provides adverse media vendor API credentials
- [ ] Customer provides Okta SAML metadata URL (Okta Admin → FCIA App → Sign On → Identity Provider metadata)
- [ ] Customer's Okta admin creates SAML app with bsa_role and customer_id attribute statements
- [ ] AD groups created: GRP-BSA-Officers, GRP-AML-Investigators, GRP-AML-Auditors
- [ ] Okta AD Agent confirmed syncing AD groups to Okta in real-time
- [ ] Bank identity fields collected (Bank name, EIN, RSSD ID)
- [ ] BSA Officer contact information collected
- [ ] Network connectivity method agreed (VPN vs Direct Connect vs PrivateLink)
- [ ] Confirm AWS region for data residency compliance

### During Deployment
- [ ] Terraform applied successfully
- [ ] All secrets loaded
- [ ] Network connectivity tested
- [ ] Cognito SAML federation tested with Okta (AD groups → bsa_role JWT claim verified)
- [ ] MFA enforcement confirmed (Okta Verify Push or FIDO2 prompts correctly)
- [ ] Offboarding tested: AD account disabled → session revoked within token TTL
- [ ] TMS webhook endpoint configured
- [ ] MCP server connectivity to each vendor tested
- [ ] All CloudWatch alarms active
- [ ] Smoke test passed

### Before Go-Live
- [ ] BSA Officer accounts created and MFA enrolled
- [ ] Investigator accounts created
- [ ] Training session completed with BSA team
- [ ] Runbook provided to customer IT team
- [ ] Escalation contacts documented
- [ ] First live alert processed and reviewed with BSA Officer present
- [ ] SAR workflow tested end-to-end with BSA Officer

### Post Go-Live (Day 30)
- [ ] CloudWatch metrics reviewed with customer
- [ ] Alert processing SLAs confirmed meeting targets
- [ ] Any integration issues resolved
- [ ] Feedback collected for product roadmap

---

## 12. Cost Estimation

### Per-Customer Monthly AWS Cost (Typical Mid-Size Bank)

| Service | Configuration | Est. Monthly Cost |
|---------|--------------|-------------------|
| ECS Fargate (UI) | 1 task, 1vCPU/2GB, always-on | ~$30 |
| ECS Fargate (Agent workers) | Avg 2 tasks, 2vCPU/4GB | ~$120 |
| ECS Fargate (MCP Gateway + 6 servers) | 7 tasks, 0.5vCPU/1GB | ~$100 |
| ALB | 1 load balancer, ~50K requests/day | ~$20 |
| RDS Aurora PostgreSQL | db.r6g.large, Multi-AZ | ~$250 |
| DynamoDB | On-demand, ~1M audit events/month | ~$15 |
| S3 | 50 GB SAR documents + archives | ~$5 |
| SQS | ~10K alert messages/month | ~$1 |
| Bedrock (Claude 3.5 Sonnet) | ~500 investigations/month, ~50K tokens each | ~$1,250 |
| Secrets Manager | ~20 secrets | ~$8 |
| KMS | ~5 CMKs + API calls | ~$10 |
| CloudFront + WAF | ~100K requests/month | ~$20 |
| ElastiCache Redis | cache.t3.small | ~$25 |
| CloudWatch | Logs + metrics + dashboards | ~$30 |
| Data Transfer | ~50 GB/month | ~$5 |
| **Total** | | **~$1,889/month** |

**Notes**:
- Bedrock cost scales linearly with investigation volume — this is the dominant variable cost
- Use Bedrock model tiering: Claude Haiku for triage nodes (~10x cheaper), Claude Sonnet for SAR generation
- Reserved instances for RDS can reduce database cost by ~40%
- Consider Bedrock Provisioned Throughput for high-volume customers (>1000 investigations/month)

---

## Appendix: Environment Variables Reference

All environment variables are injected from Secrets Manager at ECS task startup. Never stored in Docker images or task definitions in plaintext.

| Variable | Purpose | Secret Path |
|----------|---------|-------------|
| `DATABASE_URL` | Aurora PostgreSQL connection | `/fcia/{id}/database/url` |
| `OPENAI_API_KEY` | OpenAI (if not using Bedrock) | `/fcia/{id}/llm/openai-key` |
| `AWS_BEDROCK_MODEL_ID` | Bedrock model identifier | Task definition environment |
| `ACTIMIZE_API_URL` | TMS API endpoint | `/fcia/{id}/tms/actimize-url` |
| `ACTIMIZE_API_KEY` | TMS authentication | `/fcia/{id}/tms/actimize-key` |
| `WORLD_CHECK_API_KEY` | Watchlist screening | `/fcia/{id}/watchlist/worldcheck-key` |
| `WORLD_CHECK_API_SECRET` | Watchlist screening | `/fcia/{id}/watchlist/worldcheck-secret` |
| `COMPLY_ADVANTAGE_API_KEY` | Alt watchlist screening | `/fcia/{id}/watchlist/complyadvantage` |
| `DOW_JONES_API_TOKEN` | Adverse media | `/fcia/{id}/adverse-media/dowjones` |
| `CORE_BANKING_API_URL` | Core banking endpoint | `/fcia/{id}/core-banking/url` |
| `CORE_BANKING_API_KEY` | Core banking auth | `/fcia/{id}/core-banking/key` |
| `SAYARI_API_KEY` | Network intelligence | `/fcia/{id}/network-intel/sayari` |
| `CASE_MGMT_API_URL` | Case management endpoint | `/fcia/{id}/case-mgmt/url` |
| `CASE_MGMT_API_KEY` | Case management auth | `/fcia/{id}/case-mgmt/key` |
| `MCP_GATEWAY_SIGNING_KEY` | JWT signing (MCP auth) | `/fcia/{id}/mcp/signing-key` |
| `BANK_NAME` | SAR filing identity | Task definition environment |
| `BANK_EIN` | SAR filing identity | `/fcia/{id}/bank/ein` |
| `BANK_RSSD` | SAR filing identity | `/fcia/{id}/bank/rssd` |
| `BSA_OFFICER_EMAIL` | SAR notifications | Task definition environment |
| `ALERT_EMAIL` | Ops alerts | Task definition environment |
| `SMTP_HOST` | Email notifications | Task definition environment |
| `SMTP_PASSWORD` | Email auth | `/fcia/{id}/notifications/smtp` |
| `CUSTOMER_ID` | Multi-tenant identifier | Task definition environment |
| `LOG_LEVEL` | Logging verbosity | Task definition environment |
