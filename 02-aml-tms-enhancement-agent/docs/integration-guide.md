# Integration Guide — AML/TMS Enhancement Agent

## Architecture Position

This agent sits **between** the TMS rule engine and the analyst alert queue:

```
TMS Rule Engine
      ↓
[AML/TMS Enhancement Agent]   ← YOU ARE HERE
  ├── SUPPRESS  → Suppression audit log (BSA Officer review)
  ├── DOWNGRADE → Analyst queue (lower priority)
  ├── PASS_THROUGH → Analyst queue (normal priority)
  └── ESCALATE  → Financial Crime Investigation Agent (high priority)
```

## TMS Vendor Integration

### Actimize (NICE)
```python
# tools/tms_connector.py — replace _load_fixture_alerts() with:
import httpx

def get_pending_alerts(limit=50):
    url = f"{os.getenv('TMS_API_URL')}/alerts"
    headers = {"X-API-Key": os.getenv("TMS_API_KEY")}
    params = {"status": "PENDING_AI_REVIEW", "limit": limit}
    resp = httpx.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["alerts"]
```

### Verafin
```python
def get_pending_alerts(limit=50):
    url = f"{os.getenv('TMS_API_URL')}/alerts/queue/prestage"
    headers = {"Authorization": f"Bearer {os.getenv('TMS_API_KEY')}"}
    resp = httpx.get(url, headers=headers, params={"max": limit}, timeout=30)
    resp.raise_for_status()
    return resp.json()
```

### Oracle Mantas
```python
def get_pending_alerts(limit=50):
    url = f"{os.getenv('TMS_API_URL')}/mantas/api/alerts"
    params = {"alertStatus": "NEW", "assignedTo": "AI_LAYER", "limit": limit}
    resp = httpx.get(url, auth=(os.getenv("TMS_USER"), os.getenv("TMS_PASS")), params=params)
    resp.raise_for_status()
    return resp.json()["data"]
```

## Core Banking Integration

Replace `tools/customer_context.py` → `get_customer_summary()`:

```python
def get_customer_summary(customer_id):
    # Temenos T24
    url = f"{os.getenv('CORE_BANKING_API_URL')}/party/{customer_id}/riskProfile"
    headers = {"Authorization": f"Bearer {os.getenv('CORE_BANKING_API_KEY')}"}
    resp = httpx.get(url, headers=headers, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    raw = resp.json()
    return CustomerSummary(
        customer_id=raw["partyId"],
        full_name=raw["legalName"],
        risk_tier=raw["amlRiskRating"],
        # ... map remaining fields
    )
```

## Downstream: Investigation Agent

When an alert is queued or escalated, the suppression engine notifies the
downstream investigation agent via SQS:

```python
import boto3

sqs = boto3.client("sqs", region_name="us-east-1")

def enqueue_for_investigation(alert_id, priority, fp_probability):
    sqs.send_message(
        QueueUrl=os.getenv("INVESTIGATION_QUEUE_URL"),
        MessageBody=json.dumps({
            "alert_id": alert_id,
            "priority": priority,
            "fp_probability_pct": fp_probability,
            "source": "aml-tms-enhancement-agent",
        }),
        MessageAttributes={
            "Priority": {"DataType": "String", "StringValue": priority}
        },
    )
```

## Historical Data Pipeline

The `historical_fp_rates` in `data/fixtures/historical_outcomes.json` should be
replaced with a nightly ETL job querying your case management system:

```sql
-- Compute rule-level FP rates (run nightly, cache in Redis/DynamoDB)
SELECT
    triggered_rule,
    COUNT(*) AS total_alerts,
    SUM(CASE WHEN outcome = 'FALSE_POSITIVE' THEN 1 ELSE 0 END) AS fp_count,
    ROUND(
        SUM(CASE WHEN outcome = 'FALSE_POSITIVE' THEN 1.0 ELSE 0 END) / COUNT(*), 4
    ) AS fp_rate
FROM alert_outcomes
WHERE alert_date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY triggered_rule
HAVING COUNT(*) >= 50   -- Only include rules with sufficient history
ORDER BY fp_rate DESC;
```

## AWS Production Architecture

```
Internet → ALB → ECS Fargate (Streamlit app)
                      ↓
              SQS pre-scoring queue
                      ↓
              ECS Fargate (scoring workers)
               ├── Aurora PostgreSQL (case records)
               ├── DynamoDB (suppression audit log — WORM)
               ├── ElastiCache Redis (FP rate cache)
               └── AWS Bedrock (LLM — data stays in VPC)
```
