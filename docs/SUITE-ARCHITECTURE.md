# Financial Services AI Agent Suite — Architecture Overview
### Full Platform Reference Architecture

---

## Suite-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         FINANCIAL SERVICES AI AGENT SUITE                               │
│                              AWS Production Architecture                                │
│                                                                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                          INGRESS / IDENTITY LAYER                                 │  │
│  │                                                                                   │  │
│  │  Users (Investigators, BSA Officers, RMs, Fraud Analysts, Auditors)               │  │
│  │              ↓                                                                    │  │
│  │  Active Directory ──(AD Agent)──► Okta (Enterprise SSO + MFA)                    │  │
│  │                                          ↓ SAML 2.0                              │  │
│  │  CloudFront CDN + WAF  ──────────► ALB (Cognito OIDC)  ──► ECS Fargate UI        │  │
│  │  (HTTPS / TLS 1.3)                 (JWT Session)                                 │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                        AGENT ORCHESTRATION LAYER (ECS Fargate)                   │  │
│  │                                                                                   │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │  │
│  │  │ Agent 02       │  │ Agent 01       │  │ Agent 03       │  │ Agent 04       │  │  │
│  │  │ TMS            │  │ Financial      │  │ KYC/CDD        │  │ Fraud          │  │  │
│  │  │ Enhancement    │→ │ Crime Invest.  │← │ Perpetual      │  │ Detection      │  │  │
│  │  │ (Port 8502)    │  │ (Port 8501)    │  │ (Port 8503)    │  │ (Port 8504)    │  │  │
│  │  └────────────────┘  └────────────────┘  └────────────────┘  └────────────────┘  │  │
│  │                                                                                   │  │
│  │  ┌────────────────┐  ┌──────────────────────────────────────────────────────────┐ │  │
│  │  │ Agent 05       │  │  MCP Authentication Gateway (Port 8443)                  │ │  │
│  │  │ Wealth RM      │  │  JWT Validation · Role Authorization · Audit Logging     │ │  │
│  │  │ Copilot        │  │  Rate Limiting · Tool Proxy                              │ │  │
│  │  │ (Port 8505)    │  └──────────────────────────────────────────────────────────┘ │  │
│  │  └────────────────┘                        ↓                                    │  │
│  │                         ┌──────────────────────────────────┐                    │  │
│  │                         │  SQS Alert Queue (FIFO + DLQ)    │                    │  │
│  │                         └──────────────────────────────────┘                    │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                          ↕                                              │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                          AI INFERENCE LAYER                                      │  │
│  │                                                                                   │  │
│  │  AWS Bedrock (VPC Endpoint — no internet egress)                                  │  │
│  │  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐   │  │
│  │  │ Claude Sonnet        │  │ Claude Haiku          │  │ Bedrock Guardrails   │   │  │
│  │  │ SAR generation       │  │ Alert triage /        │  │ PII protection       │   │  │
│  │  │ EDD packages         │  │ fast scoring nodes    │  │ Output filtering     │   │  │
│  │  │ Proposal drafting    │  │                       │  │                      │   │  │
│  │  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                          ↕                                              │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                       MCP TOOL SERVER LAYER (ECS Fargate)                        │  │
│  │                                                                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │  │
│  │  │ TMS          │  │ Core Banking │  │ Watchlist    │  │ Adverse      │         │  │
│  │  │ Connector    │  │ Connector    │  │ Screener     │  │ Media        │         │  │
│  │  │ Port 8001    │  │ Port 8002    │  │ Port 8003    │  │ Port 8004    │         │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘         │  │
│  │                                                                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────────┐   │  │
│  │  │ Network      │  │ Case         │  │ Wealth / CRM Connector               │   │  │
│  │  │ Intelligence │  │ Management   │  │ Portfolio Data · IPS · Life Events   │   │  │
│  │  │ Port 8005    │  │ Port 8006    │  │ Port 8007                            │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                         ↕ PrivateLink / VPN / Direct Connect                           │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                         DATA LAYER                                                │  │
│  │                                                                                   │  │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐                │  │
│  │  │ RDS Aurora       │  │ DynamoDB         │  │ S3 Object Lock   │                │  │
│  │  │ PostgreSQL       │  │ Audit Trail      │  │ SAR Documents    │                │  │
│  │  │ Multi-AZ         │  │ (Append-only,    │  │ WORM / 5-year    │                │  │
│  │  │ Case / Review /  │  │  IAM-enforced)   │  │ BSA retention    │                │  │
│  │  │ Client data      │  │                  │  │                  │                │  │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘                │  │
│  │                                                                                   │  │
│  │  ┌──────────────────┐  ┌──────────────────┐                                      │  │
│  │  │ ElastiCache      │  │ S3 (Audit        │                                      │  │
│  │  │ Redis            │  │  Archive,         │                                      │  │
│  │  │ Sessions / JWKS  │  │  Glacier 5yr)    │                                      │  │
│  │  │ cache / Rate lmt │  │                  │                                      │  │
│  │  └──────────────────┘  └──────────────────┘                                      │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                    SECURITY & OPERATIONS LAYER (Cross-Cutting)                   │  │
│  │                                                                                   │  │
│  │  Secrets Manager · KMS (per-customer CMKs) · CloudTrail · CloudWatch             │  │
│  │  AWS Config (compliance rules) · Security Hub · GuardDuty                        │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────┘

EXTERNAL INTEGRATIONS (via MCP Tool Servers + NAT Gateway)
├── TMS Platforms:    Actimize · Verafin · NICE · Oracle Mantas
├── Core Banking:     FIS · Fiserv · Jack Henry · Temenos T24
├── Watchlists:       Refinitiv World-Check · LexisNexis Bridger · ComplyAdvantage · OFAC SDN
├── Adverse Media:    Dow Jones Risk & Compliance · LexisNexis Nexis+
├── Network Intel:    Sayari Analytics · OpenCorporates · Quantexa
├── Case Management:  ServiceNow GRC · Actimize Case Manager
└── Wealth/CRM:       Salesforce · Redtail · Orion · Tamarac
```

---

## Agent Data Flow Diagram

```
EXTERNAL EVENTS
│
├── TMS Alert Fired ──────────────────────────────────────────────────────────┐
│                                                                              ▼
│                                                              ┌──────────────────────┐
│                                                              │  Agent 02            │
│                                                              │  TMS Enhancement     │
│                                                              │                      │
│                                                              │  FP Score < 15%? ───►│──► Agent 01 (ESCALATE HIGH)
│                                                              │  FP Score 15-60%? ──►│──► Analyst Queue (PASS-THROUGH)
│                                                              │  FP Score 60-85%? ──►│──► Analyst Queue (DOWNGRADE)
│                                                              │  FP Score ≥ 85%?  ──►│──► Suppression Audit Log
│                                                              └──────────────────────┘
│
├── Risk Event Detected ────────────────────────────────────────────────────────┐
│   (Adverse media · Watchlist hit · SAR filed · Transaction spike)             ▼
│                                                              ┌──────────────────────┐
│                                                              │  Agent 03            │
│                                                              │  KYC/CDD Perpetual   │
│                                                              │                      │
│                                                              │  Trigger Evaluation  │
│                                                              │  → CDD Refresh       │
│                                                              │  → Watchlist Screen  │
│                                                              │  → Rescore (8 factors│
│                                                              │  → EDD Package gen.  │
│                                                              │  → RM Notification   │
│                                                              │  → Compliance review │
│                                                              └──────────────────────┘
│                                                                         │
│              Agent 01 findings (SAR filed, high risk confirmed) ────────┘
│              Feed Agent 03 as risk event trigger
│
├── Transaction Processed ─────────────────────────────────────────────────────┐
│                                                                              ▼
│                                                              ┌──────────────────────┐
│                                                              │  Agent 04            │
│                                                              │  Real-Time Fraud     │
│                                                              │                      │
│                                                              │  <200ms path:        │
│                                                              │  Rules + Feature ext.│
│                                                              │                      │
│                                                              │  Async path:         │
│                                                              │  Device · Behavioral │
│                                                              │  · LLM synthesis     │
│                                                              │                      │
│                                                              │  Score ≥ 85: BLOCK   │
│                                                              │  Score 65-84: STEP-UP│
│                                                              │  Score 40-64: REVIEW │
│                                                              │  Score < 40: ALLOW   │
│                                                              │                      │
│                                                              │  SAR Flag → Agent 01 │
│                                                              └──────────────────────┘
│
└── RM Request ─────────────────────────────────────────────────────────────────┐
    (Meeting prep · Proposal · Review · Client communication)                  ▼
                                                              ┌──────────────────────┐
                                                              │  Agent 05            │
                                                              │  Wealth RM Copilot   │
                                                              │                      │
                                                              │  Client profile      │
                                                              │  → Portfolio analysis│
                                                              │  → Market intel      │
                                                              │  → Suitability check │
                                                              │    (Python, not LLM) │
                                                              │  → Content drafting  │
                                                              │  → FINRA 2210 check  │
                                                              │  → RM approval gate  │
                                                              └──────────────────────┘
                                                                         │
                                                    Agent 03 KYC data ───┘
                                                    (Customer risk profile,
                                                     watchlist status,
                                                     document completeness)
```

---

## Authentication Architecture (All Agents)

All five agents share the same identity federation pattern. One Okta application per agent is the recommended configuration — this allows separate group assignments per agent (an RM should access Agent 05, not Agent 01).

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      SHARED IDENTITY ARCHITECTURE                               │
│                                                                                 │
│  Customer Active Directory                                                      │
│  ┌──────────────────────────────────────────────────────┐                      │
│  │  GRP-BSA-Officers          → bsa_role: BSA_OFFICER   │                      │
│  │  GRP-AML-Investigators     → bsa_role: INVESTIGATOR  │                      │
│  │  GRP-AML-Auditors          → bsa_role: AUDITOR       │                      │
│  │  GRP-Fraud-Analysts        → fraud_role: ANALYST     │                      │
│  │  GRP-Wealth-RMs            → rm_role: RM             │                      │
│  │  GRP-Compliance-Officers   → compliance_role: OFFICER│                      │
│  └──────────────────────────────────────────────────────┘                      │
│                          │ Okta AD Agent (real-time sync)                      │
│                          ▼                                                      │
│  Okta SSO                                                                       │
│  ┌──────────────────────────────────────────────────────┐                      │
│  │  SAML App: Agent 01 (Financial Crime Investigation)  │                      │
│  │  SAML App: Agent 02 (TMS Enhancement)               │                      │
│  │  SAML App: Agent 03 (KYC/CDD Perpetual)             │                      │
│  │  SAML App: Agent 04 (Real-Time Fraud Detection)     │                      │
│  │  SAML App: Agent 05 (Wealth RM Copilot)             │                      │
│  │                                                      │                      │
│  │  Attribute mapping: AD group → role claim in SAML   │                      │
│  │  MFA policy: Okta Verify Push or FIDO2 (enforced)   │                      │
│  └──────────────────────────────────────────────────────┘                      │
│                          │ SAML 2.0 assertion                                  │
│                          ▼                                                      │
│  Amazon Cognito (one User Pool per agent)                                       │
│  ┌──────────────────────────────────────────────────────┐                      │
│  │  Federation only — no credentials stored in Cognito  │                      │
│  │  Issues JWT (access_token + id_token)                │                      │
│  │  JWT carries custom claims from Okta SAML:           │                      │
│  │    custom:bsa_role / custom:fraud_role / custom:rm_role                      │
│  │    custom:customer_id                                │                      │
│  └──────────────────────────────────────────────────────┘                      │
│                          │ JWT                                                  │
│                          ▼                                                      │
│  ALB (per agent) → validates JWT → routes to ECS Fargate                        │
│  MCP Auth Gateway → validates JWT → authorizes tool calls by role               │
│                                                                                 │
│  OFFBOARDING: Remove user from AD group → Okta syncs immediately               │
│  Access revoked at next JWT refresh (max 8 hours) or sooner if AD              │
│  account is disabled (all active sessions fail immediately)                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AWS VPC (Per-Customer Isolated)                       │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        PUBLIC SUBNETS (2 AZs)                        │   │
│  │  CloudFront Origin · ALB (per agent) · NAT Gateway                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                              ↕                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      PRIVATE SUBNETS — APP TIER                      │   │
│  │  ECS Fargate: Agent UI tasks (01-05) · Agent Worker tasks           │   │
│  │  ECS Fargate: MCP Auth Gateway · MCP Tool Servers (01-07)           │   │
│  │  SQS Polling (no inbound needed) · VPC Endpoints (Bedrock, S3, etc.)│   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                              ↕                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      PRIVATE SUBNETS — DATA TIER                     │   │
│  │  RDS Aurora PostgreSQL (Multi-AZ)                                    │   │
│  │  DynamoDB (VPC Endpoint — no internet routing)                       │   │
│  │  ElastiCache Redis (session + JWKS cache)                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  VPC Endpoints (private connectivity, no internet):                         │
│  ├── com.amazonaws.*.bedrock-runtime  (LLM inference)                       │
│  ├── com.amazonaws.*.secretsmanager   (credential retrieval)                │
│  ├── com.amazonaws.*.s3               (document storage)                    │
│  ├── com.amazonaws.*.dynamodb         (audit trail)                         │
│  └── com.amazonaws.*.sqs              (alert queue)                         │
└─────────────────────────────────────────────────────────────────────────────┘
         ↕                                                    ↕
┌─────────────────┐                              ┌─────────────────────────┐
│  Internet       │                              │  Customer On-Premise    │
│  (Watchlist,    │                              │  (TMS · Core Banking ·  │
│  Adverse Media, │                              │  Case Management)       │
│  OSINT vendors) │                              │                         │
│  via NAT GW     │                              │  VPN / Direct Connect   │
└─────────────────┘                              └─────────────────────────┘
```

---

## Security Controls Summary

| Control | Implementation | Regulatory Basis |
|---------|---------------|-----------------|
| **Encryption at rest** | KMS CMK per customer, per data store | PCI DSS, GLBA, SOC 2 |
| **Encryption in transit** | TLS 1.3 on all connections | PCI DSS, GLBA |
| **Identity federation** | Cognito + Okta SAML + AD | FFIEC authentication guidance |
| **MFA enforcement** | Okta Verify Push or FIDO2 | FFIEC CAT, NIST 800-63B |
| **Immutable audit trail** | DynamoDB append-only (IAM blocks UpdateItem/DeleteItem) | BSA 5-year retention |
| **WORM document storage** | S3 Object Lock COMPLIANCE mode | BSA 31 U.S.C. § 5318 |
| **Data residency** | Bedrock VPC endpoint — inference stays in AWS account | Bank data privacy requirements |
| **Network isolation** | Per-customer VPC; no shared infrastructure | Multi-tenant data isolation |
| **Secrets management** | Secrets Manager with auto-rotation | SOC 2, GLBA |
| **Threat detection** | GuardDuty + Security Hub | SOC 2, OCC expectations |
| **Configuration compliance** | AWS Config rules with auto-remediation | SOC 2, OCC |
| **PII protection** | Bedrock Guardrails; log sanitization | GLBA, CCPA |

---

## Regulatory Coverage Matrix (Full Suite)

| Regulation | Agent 01 | Agent 02 | Agent 03 | Agent 04 | Agent 05 |
|------------|:---:|:---:|:---:|:---:|:---:|
| BSA 31 U.S.C. § 5318 (SAR filing) | ✅ | ✅ | ✅ | ✅ | — |
| FinCEN CDD Rule (31 CFR 1020.210) | ✅ | ✅ | ✅ | — | — |
| OFAC IEEPA (SDN screening) | ✅ | ✅ | ✅ | ✅ | — |
| FATF R.10 (Customer due diligence) | ✅ | — | ✅ | — | — |
| FATF R.12 (PEP enhanced due diligence) | ✅ | ✅ | ✅ | — | — |
| FATF R.20 (Suspicious transaction reporting) | ✅ | ✅ | — | ✅ | — |
| USA PATRIOT Act § 326 (CIP) | ✅ | — | ✅ | — | — |
| FIN-2014-G001 (SAR narrative format) | ✅ | — | — | — | — |
| SR 11-7 (Model risk management) | ✅ | ✅ | ✅ | ✅ | ✅ |
| FFIEC BSA/AML Examination Manual | ✅ | ✅ | ✅ | — | — |
| 18 U.S.C. § 1960 (No tipping off) | ✅ | — | — | — | ✅ |
| 5-year BSA record retention | ✅ | ✅ | ✅ | ✅ | — |
| Reg E (EFTA) — provisional credit | — | — | — | ✅ | — |
| Nacha Rules (ACH fraud) | — | — | — | ✅ | — |
| Reg BI (17 CFR 240.15l-1) | — | — | — | — | ✅ |
| FINRA Rule 2111 (Suitability) | — | — | — | — | ✅ |
| FINRA Rule 2210 (Communications) | — | — | — | — | ✅ |
| ERISA (retirement account fiduciary) | — | — | — | — | ✅ |
| GLBA (data privacy) | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Technology Stack Reference

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Agent orchestration | LangGraph | ≥ 0.2.28 | StateGraph DAG; deterministic routing |
| LLM (primary) | Claude Sonnet via AWS Bedrock | Latest | High-quality drafting, compliance reasoning |
| LLM (triage) | Claude Haiku via AWS Bedrock | Latest | Fast, low-cost; triage and scoring nodes |
| LLM (alternative) | OpenAI GPT-4o | Latest | Default for local/POC deployments |
| UI | Streamlit | ≥ 1.43 | POC/demo; FastAPI + Next.js for production |
| API layer | FastAPI | ≥ 0.115 | MCP Gateway, agent APIs |
| Databases | Aurora PostgreSQL + DynamoDB | PG 15+ | Cases + immutable audit |
| Vector store | pgvector (Aurora) | — | Production; ChromaDB for local dev |
| Cache | ElastiCache Redis | — | Session, JWKS, rate limiting |
| Container runtime | ECS Fargate | — | Serverless containers; no EC2 management |
| IaC | Terraform | ≥ 1.6 | Per-customer module; ~12 min deploy |
| CI/CD | AWS CodePipeline + CodeBuild | — | Security scanning + rolling deploy |
| Auth | Cognito + Okta + Active Directory | — | SAML 2.0 federation; no credentials in app |
| Secrets | AWS Secrets Manager | — | Auto-rotation; per-customer namespacing |
| Encryption | AWS KMS (CMK per customer) | — | Per-datastore keys; key revocation |
| Monitoring | CloudWatch + X-Ray | — | SLA dashboards, distributed tracing |
| Compliance | AWS Config + GuardDuty + Security Hub | — | Automated compliance rules |

---

## Deployment Topology Options

### Option 1: Separate AWS Accounts (Recommended for Large Institutions)
```
AWS Organizations
├── Management Account (billing consolidation, AWS SSO)
├── Shared Services Account (ECR, CodePipeline, Terraform state)
├── Institution A Account
│   └── VPC → All 5 agent stacks, fully isolated
├── Institution B Account
│   └── VPC → All 5 agent stacks, fully isolated
└── Institution C Account
    └── VPC → Selected agents (e.g., 02 + 01 only)
```
**Best for:** Institutions with contractual requirements for account-level isolation; large banks with strict data governance.

### Option 2: Single Account, Multiple VPCs (Cost-Optimized)
```
Single AWS Account
├── VPC: Institution A (10.10.0.0/16)
│   ├── ECS Cluster: institution-a
│   ├── RDS Aurora: institution-a-db
│   └── KMS, Secrets, S3: customer-a-namespaced
└── VPC: Institution B (10.20.0.0/16)
    ├── ECS Cluster: institution-b
    ├── RDS Aurora: institution-b-db
    └── KMS, Secrets, S3: customer-b-namespaced
```
**Best for:** Smaller institutions; POC environments; customers comfortable with VPC-level isolation.

### Option 3: Single Institution, Self-Managed (Direct Deployment)
```
Institution's Own AWS Account
└── VPC → All 5 agents deployed by institution's IT/cloud team
    Terraform modules provided; institution owns and operates
```
**Best for:** Institutions with mature AWS practices who want full ownership; avoids any managed service arrangement.
