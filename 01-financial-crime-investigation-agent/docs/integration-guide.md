# Integration Guide
## Financial Crime Investigation Agent — System Integration Playbook

---

## Overview

This guide provides step-by-step instructions for connecting the Financial Crime Investigation Agent to your bank's production systems. Each section covers authentication patterns, data schema mapping, latency expectations, and failover design.

All integration points in the codebase are marked with:
```
# ── INTEGRATION POINT ──────────────────────────────────────────────────────────
```

---

## 1. Transaction Monitoring Systems (TMS)

### Purpose
The TMS is the source of all investigation triggers. The agent receives TMS alerts and uses the TMS API to retrieve transaction history.

### Supported Vendors
| Vendor | Product | API Type | Auth Method |
|--------|---------|---------|-------------|
| NICE Actimize | SAM (Suspicious Activity Monitoring) | REST | API Key + OAuth 2.0 |
| Oracle Financial Services | FCCM / Mantas | SOAP/REST | mTLS + OAuth |
| SAS Institute | Anti-Money Laundering | REST | API Key |
| FIS | MISER AML | REST | OAuth 2.0 |
| Nasdaq | Verafin | REST | OAuth 2.0 + PKCE |
| Temenos | FCM | REST | OAuth 2.0 |

### Integration Steps: Actimize SAM

**Step 1: Obtain API Credentials**
- Contact your Actimize implementation team for API access
- Request: API base URL, API key, and OAuth client credentials
- Store in `.env`:
  ```
  ACTIMIZE_API_URL=https://your-instance.actimize.com/api/v1
  ACTIMIZE_API_KEY=your_api_key
  ```

**Step 2: Replace Mock Function in `tools/transaction_monitor.py`**
```python
# In get_transaction_history():
import requests

def get_transaction_history(account_id: str, days: int = 365) -> List[Dict]:
    headers = {
        "X-API-Key": os.getenv("ACTIMIZE_API_KEY"),
        "Content-Type": "application/json",
    }
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    response = requests.get(
        f"{os.getenv('ACTIMIZE_API_URL')}/accounts/{account_id}/transactions",
        headers=headers,
        params={"fromDate": start_date, "limit": 1000},
        timeout=30,
    )
    response.raise_for_status()
    return _normalize_actimize_transactions(response.json()["transactions"])
```

**Step 3: Schema Mapping**
Map Actimize transaction fields to the agent's schema:
```python
def _normalize_actimize_transactions(raw_txns: List[Dict]) -> List[Dict]:
    """Map Actimize SAM transaction fields to agent schema."""
    normalized = []
    for txn in raw_txns:
        normalized.append({
            "transaction_id": txn["transactionId"],
            "account_id": txn["accountNumber"],
            "date": txn["transactionDate"][:10],  # ISO date
            "amount": float(txn["transactionAmount"]),
            "transaction_type": _map_actimize_type(txn["transactionType"]),
            "direction": "CREDIT" if txn["creditDebit"] == "C" else "DEBIT",
            "channel": txn.get("channel", "UNKNOWN"),
            "counterparty_name": txn.get("counterpartyName"),
            "counterparty_country": txn.get("counterpartyCountry"),
            "currency": txn.get("currency", "USD"),
            "reference": txn.get("paymentReference"),
        })
    return normalized
```

**Latency Expectations:**
- Alert retrieval: <2 seconds
- Transaction history (12 months): 2-10 seconds depending on volume
- Pattern analysis API (if available): 5-15 seconds

**Failover Design:**
- Implement retry with exponential backoff (3 retries, 2^n seconds)
- Cache transaction data for 1 hour to reduce API load
- Log all API failures to audit trail
- Alert on consecutive failures via SMTP or PagerDuty

---

## 2. Core Banking / KYC Systems

### Purpose
Core banking provides the authoritative customer record — identity, account data, KYC status, and risk profile.

### Supported Vendors
| Vendor | Product | API Type | Auth Method |
|--------|---------|---------|-------------|
| Temenos | T24 / Transact | REST + TAFC | OAuth 2.0 + mTLS |
| FIS | Modern Banking Platform | REST | OAuth 2.0 |
| Jack Henry | Symitar | SOAP/REST | API Key + IP whitelist |
| Fiserv | DNA | REST | OAuth 2.0 |
| Oracle | FLEXCUBE | REST | OAuth 2.0 |
| Infosys | Finacle | REST | API Key |

### Integration Steps: Temenos T24

**Step 1: Obtain API Access**
```
CORE_BANKING_API_URL=https://your-t24-instance.bank.com/api/v1
CORE_BANKING_API_KEY=your_t24_api_key
```

**Step 2: Replace Mock Function in `tools/customer_profile.py`**
```python
def get_customer_profile(customer_id: str) -> Dict:
    import requests

    response = requests.get(
        f"{os.getenv('CORE_BANKING_API_URL')}/customers/{customer_id}",
        headers={
            "Authorization": f"Bearer {_get_t24_token()}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    response.raise_for_status()
    raw = response.json()
    return _normalize_t24_customer(raw)

def _get_t24_token() -> str:
    """Get OAuth 2.0 token from T24 token endpoint."""
    response = requests.post(
        f"{os.getenv('CORE_BANKING_API_URL')}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": os.getenv("T24_CLIENT_ID"),
            "client_secret": os.getenv("T24_CLIENT_SECRET"),
        },
    )
    return response.json()["access_token"]
```

**Step 3: KYC System Integration**
If KYC is separate from core banking (e.g., Refinitiv World-Check One as KYC platform):
```python
# Add to customer profile enrichment:
kyc_data = worldcheck_client.get_kyc_profile(customer_id=external_id)
customer_profile.update({
    "edd_status": kyc_data["eddStatus"],
    "pep_flag": kyc_data["isPep"],
    "kyc_date": kyc_data["lastReviewDate"],
})
```

**Latency Expectations:**
- Customer profile: <3 seconds
- Account details: <2 seconds
- Beneficial ownership: 3-10 seconds (may require multiple API calls for complex structures)

---

## 3. Watchlist Screening Systems

### Purpose
Mandatory OFAC and sanctions screening for all customers, beneficial owners, and transaction counterparties.

### Supported Vendors
| Vendor | Product | API Type | Auth Method |
|--------|---------|---------|-------------|
| LSEG (Refinitiv) | World-Check One | REST | HMAC Signature |
| Dow Jones | Risk & Compliance | REST | Bearer Token |
| LexisNexis | Bridger Insight XG | SOAP/REST | API Key |
| ComplyAdvantage | AML Platform | REST | Token |
| Accuity (Fircosoft) | Trusted Source | SWIFT-compatible | mTLS |
| NICE Actimize | WLF (Watch List Filtering) | REST | Integrated with TMS |

### Integration Steps: Refinitiv World-Check One

**Step 1: Authentication Setup**
World-Check uses HMAC-SHA256 signature authentication:
```python
import hmac
import hashlib
import base64
import time

def _get_worldcheck_headers(method: str, path: str, body: str = "") -> Dict:
    api_key = os.getenv("WORLD_CHECK_API_KEY")
    api_secret = os.getenv("WORLD_CHECK_API_SECRET")

    date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    string_to_sign = f"{method}\n{path}\n{date}\n{body}"
    signature = hmac.new(
        api_secret.encode(), string_to_sign.encode(), hashlib.sha256
    ).hexdigest()

    return {
        "Authorization": f"Credential={api_key},SignedHeaders=host;date,Signature={signature}",
        "Date": date,
        "Content-Type": "application/json",
    }
```

**Step 2: Replace OFAC Screening Function**
```python
def screen_against_ofac(name: str, dob: str = None, country: str = None) -> Dict:
    payload = {
        "entityType": "INDIVIDUAL",
        "names": [{"name": name, "type": "PRIMARY"}],
        "groupIds": ["RISK_INTELLIGENCE"],  # World-Check group
    }
    if dob:
        payload["dateOfBirth"] = dob
    if country:
        payload["nationality"] = country

    body = json.dumps(payload)
    headers = _get_worldcheck_headers("POST", "/v1/cases", body)

    response = requests.post(
        "https://rms-world-check-one-api.thomsonreuters.com/v1/cases",
        headers=headers,
        json=payload,
    )
    case_data = response.json()

    # Poll for results
    case_id = case_data["caseId"]
    results = _poll_worldcheck_results(case_id, headers)
    return _parse_worldcheck_ofac_result(results, name)
```

**Match Threshold Configuration:**
```python
# In watchlist_screening.py — configure thresholds per risk appetite
MATCH_THRESHOLDS = {
    "OFAC_SDN": 85,      # 85% fuzzy match triggers OFAC hit
    "PEP": 80,            # 80% for PEP detection
    "EU_SANCTIONS": 85,   # Same as OFAC for EU list
    "UN_CONSOLIDATED": 85,# UN list threshold
    "INTERNAL": 95,       # Internal list — higher threshold (exact-ish)
}
```

**Latency Expectations:**
- Single name screening: 1-5 seconds
- Batch screening (20+ names): 5-30 seconds
- Full counterparty screening: 10-60 seconds

**Failover Design:**
- If primary vendor (World-Check) is unavailable, fall back to OFAC's free SDN API
- Cache negative results for 24 hours (no-hit caching)
- Never cache positive hits — always re-screen
- Alert compliance team if screening system is unavailable for >15 minutes

---

## 4. Case Management Systems

### Purpose
Formal case tracking, workflow management, SLA enforcement, and BSA record retention.

### Supported Vendors
| Vendor | Product | API Type | Auth Method |
|--------|---------|---------|-------------|
| NICE Actimize | Case Manager | REST | API Key + OAuth |
| Hyland | OnBase | REST | OAuth 2.0 |
| ServiceNow | GRC/IRM Module | REST | OAuth 2.0 |
| RSA Archer | GRC Platform | REST | API Key |
| LogicGate | Risk Cloud | REST | Bearer Token |
| Custom | PostgreSQL + FastAPI | REST | JWT |

### Integration Steps: ServiceNow GRC

**Step 1: Configure ServiceNow Connection**
```
SERVICENOW_INSTANCE=your-instance.service-now.com
SERVICENOW_CLIENT_ID=your_oauth_client_id
SERVICENOW_CLIENT_SECRET=your_oauth_client_secret
```

**Step 2: Replace Case Creation Function**
```python
from pysnow import Client

def create_case(alert_id: str, customer_id: str, investigator_id: str) -> str:
    client = Client(
        instance=os.getenv("SERVICENOW_INSTANCE"),
        client_id=os.getenv("SERVICENOW_CLIENT_ID"),
        client_secret=os.getenv("SERVICENOW_CLIENT_SECRET"),
        default_payload={"sysparm_display_value": "true"},
    )

    record = client.resource(api_path="/table/u_aml_investigation_cases")
    result = record.create(payload={
        "u_alert_id": alert_id,
        "u_customer_id": customer_id,
        "u_assigned_investigator": investigator_id,
        "u_status": "open",
        "u_sar_deadline": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "u_source_system": "AI_INVESTIGATION_AGENT",
        "u_priority": "high",
    })
    return result["sys_id"]
```

---

## 5. Adverse Media Systems

### Purpose
Open-source intelligence (OSINT) and adverse media screening for enhanced due diligence.

### Integration Steps: Dow Jones Risk & Compliance

```python
def search_adverse_media(name: str, aliases: List[str] = None) -> List[Dict]:
    headers = {
        "Authorization": f"Bearer {os.getenv('DOW_JONES_API_TOKEN')}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": name,
        "entityType": "individual",
        "categories": ["adverse-media", "financial-crime", "regulatory"],
        "dateRange": {
            "from": (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d"),
            "to": datetime.now().strftime("%Y-%m-%d"),
        },
        "languages": ["en"],
        "maxResults": 50,
    }

    response = requests.post(
        "https://api.dowjones.com/riskandcompliance/v1/search",
        headers=headers,
        json=payload,
    )
    return _parse_dj_results(response.json())
```

---

## 6. LLM / AI Model Integration

### Current: OpenAI GPT-4o (Default)
- Used for: Alert analysis, transaction pattern detection, SAR narrative generation
- Config: `OPENAI_API_KEY` in `.env`
- Compliance note: Customer data is sent to OpenAI API — review data privacy agreements

### Alternative: AWS Bedrock (Recommended for Production)
Keep data within your AWS VPC:
```python
import boto3
from langchain_aws import ChatBedrock

def _get_llm():
    """Use AWS Bedrock for on-premises data privacy."""
    bedrock_client = boto3.client(
        service_name="bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
    return ChatBedrock(
        client=bedrock_client,
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        model_kwargs={"temperature": 0.1},
    )
```

### Alternative: Azure OpenAI (Data stays in Azure tenant)
```python
from langchain_openai import AzureChatOpenAI

def _get_llm():
    return AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-01",
        temperature=0.1,
    )
```

### Alternative: On-Premises (Air-Gapped)
For highly sensitive environments:
```python
from langchain_community.llms import Ollama

def _get_llm():
    """Use local Ollama instance — no data leaves the bank."""
    return Ollama(
        model="llama3.1:70b",  # Requires significant GPU infrastructure
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
```

---

## 7. Database / State Persistence

### Current: In-Memory (Demo Only)
- Case data stored in Python dict (`_CASE_DATABASE` in `case_management.py`)
- LangGraph state in `MemorySaver` (in-process memory)
- Not suitable for production (data lost on restart)

### Production: PostgreSQL

**Step 1: Configure Database**
```
DATABASE_URL=postgresql://user:password@host:5432/aml_db
```

**Step 2: LangGraph with PostgreSQL Checkpointing**
```python
# In agent/graph.py
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg2

def build_investigation_graph(use_memory: bool = False):
    if use_memory:
        checkpointer = MemorySaver()
    else:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()  # Create required tables

    workflow = StateGraph(InvestigationState)
    # ... rest of graph setup
    return workflow.compile(checkpointer=checkpointer)
```

**Step 3: Case Management Database Schema**
```sql
CREATE TABLE aml_cases (
    case_id VARCHAR(50) PRIMARY KEY,
    alert_id VARCHAR(50) NOT NULL,
    customer_id VARCHAR(50) NOT NULL,
    investigator_id VARCHAR(50),
    status VARCHAR(50) DEFAULT 'OPEN',
    risk_score FLOAT,
    recommended_action VARCHAR(20),
    sar_filing_deadline DATE,
    retention_expiry DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    investigation_state JSONB,  -- Full LangGraph state
    audit_trail JSONB DEFAULT '[]'::jsonb,
    investigation_notes JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX idx_cases_customer ON aml_cases(customer_id);
CREATE INDEX idx_cases_status ON aml_cases(status);
CREATE INDEX idx_cases_deadline ON aml_cases(sar_filing_deadline);
```

---

## 8. Production Architecture Checklist

### Security
- [ ] All API keys stored in AWS Secrets Manager or Azure Key Vault
- [ ] mTLS for all inter-service communication
- [ ] VPC with private subnets for all services
- [ ] WAF in front of Streamlit application
- [ ] All data encrypted at rest (AES-256) and in transit (TLS 1.3)
- [ ] PII masked in logs (no SSN, account numbers in log files)
- [ ] Non-root container user (already configured in Dockerfile)

### Compliance
- [ ] Model validation completed per SR 11-7 before production use
- [ ] Data processing agreements with all vendor APIs reviewed by legal
- [ ] Data residency confirmed (customer data must stay in US for BSA purposes)
- [ ] Penetration testing completed
- [ ] BSA Officer approved AI-in-the-loop process documentation
- [ ] Examiner walk-through dry run completed

### Reliability
- [ ] Circuit breakers on all external API calls
- [ ] Retry logic with exponential backoff
- [ ] Dead letter queue for failed investigations
- [ ] Health checks on all dependencies
- [ ] Alerting for API failures, latency spikes, and queue backlog
- [ ] Multi-region deployment for disaster recovery

### Observability
- [ ] Structured logging (JSON) to CloudWatch / Azure Monitor
- [ ] Distributed tracing (AWS X-Ray / Datadog)
- [ ] Dashboard for: alert queue depth, SAR deadline countdown, model performance
- [ ] Audit trail verification job (ensure no gaps in audit log)
