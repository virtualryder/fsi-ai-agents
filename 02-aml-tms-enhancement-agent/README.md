# AML/TMS Enhancement Agent
### Pre-Queue False Positive Reduction for Financial Crime Compliance

> **Part of the Financial Crime AI Suite** — builds on the [Financial Crime Investigation Agent](../01-financial-crime-investigation-agent/) by solving the upstream problem: reducing the 85-95% false positive rate before alerts ever reach analysts.

---

## The Problem

A mid-sized bank with 10 analysts reviewing 500 alerts/day at a 90% false positive rate:
- 450 wasted analyst-hours/day on noise
- ~$4M/year in wasted labor
- Genuine suspicious activity buried under false positive volume

**This agent cuts that volume by ~50% before the first analyst ever opens a case.**

---

## Architecture

```
TMS Rule Engine (Actimize / Verafin / NICE / Oracle Mantas)
        ↓
┌─────────────────────────────────────────────────────────┐
│           AML/TMS Enhancement Agent                     │
│                                                         │
│  ingest → customer_context → historical_patterns        │
│       → feature_extraction → rule_based_prescoring      │
│       → llm_analysis → composite_score → routing        │
│                                                         │
│  SUPPRESS (FP≥85%) → Suppression Audit Log             │
│  DOWNGRADE (FP≥60%) → Analyst Queue (low priority)     │
│  PASS_THROUGH (FP 15-60%) → Analyst Queue (normal)     │
│  ESCALATE (FP≤15%) → Investigation Agent (HIGH)        │
└─────────────────────────────────────────────────────────┘
        ↓
Financial Crime Investigation Agent
```

### Scoring Pipeline (LangGraph)

| Node | Purpose |
|------|---------|
| `ingest_raw_alert` | Parse and validate incoming TMS alert |
| `customer_context_lookup` | Fetch risk tier, expected volumes, FP history |
| `historical_pattern_check` | Rule-level and typology-level FP rates |
| `extract_features_node` | Build structured feature set for scoring |
| `rule_based_prescoring` | Fast deterministic pre-filter (30% weight) |
| `llm_false_positive_analysis` | GPT-4o contextual reasoning (50% weight) |
| `compute_composite_score_node` | Weighted composite FP probability |
| `determine_routing` | Map score to routing decision via ThresholdManager |
| `execute_suppression/downgrade/enqueue/escalation` | Take action + audit |
| `finalize_scoring` | Timing, final audit entry |

### Composite Scoring Weights
| Component | Weight | Rationale |
|-----------|--------|-----------|
| Rule-based pre-filter | 30% | Fast, deterministic, interpretable |
| LLM analysis | 50% | Contextual reasoning across all signals |
| Historical patterns | 20% | Statistical base rates |

---

## Regulatory Compliance

| Requirement | Implementation |
|-------------|----------------|
| **SR 11-7** | Explainable scores, factor-by-factor breakdown, audit trail for every decision |
| **BSA** | No suppression without full justification narrative |
| **FATF R.12** | PEP flag → mandatory ESCALATE, never suppress |
| **OFAC** | High-risk geography + large wire + new account → mandatory ESCALATE |
| **90-Day Review** | All suppressions flagged for BSA Officer review within 90 days |
| **Human-in-the-Loop** | BSA Officer can approve/reverse any suppression in the dashboard |

---

## Quick Start

### Local Development
```bash
# 1. Clone and configure
cp .env.example .env
# Add OPENAI_API_KEY to .env

# 2. Run with Docker Compose
docker compose up

# Open: http://localhost:8502
```

### Without Docker
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Run Tests
```bash
pytest tests/ -v
```

---

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| ⚡ Live Scoring Queue | Load TMS alerts and run AI scoring pipeline |
| 📊 FP Reduction Metrics | Suppression rates, analyst hours saved, ROI estimate |
| 📋 Suppression Audit | BSA Officer review panel for all suppression decisions |
| 🔍 Alert Detail | Full score breakdown: gauge, component chart, LLM narrative |
| ⚙️ Threshold Config | Operational controls for scoring thresholds (BSA Officer only) |

---

## Deploy to Railway

1. Fork this repo
2. Create new Railway project → Connect GitHub repo
3. Set environment variable: `OPENAI_API_KEY=sk-...`
4. Railway auto-deploys via `railway.toml`

> **Health check fix**: `railway.toml` uses `sh -c 'streamlit run app.py --server.port "$PORT"'` to ensure Railway's `$PORT` variable expands correctly at runtime.

---

## Project Structure

```
02-aml-tms-enhancement-agent/
├── app.py                          # Streamlit dashboard (5 tabs)
├── agent/
│   ├── graph.py                    # LangGraph StateGraph (13 nodes)
│   ├── nodes.py                    # Node functions (scoring pipeline)
│   ├── state.py                    # AlertScoringState TypedDict
│   └── prompts.py                  # LLM prompts (FP analysis, justification)
├── scoring/
│   ├── false_positive_classifier.py # Rule-based scoring + composite formula
│   ├── feature_extractor.py         # Feature extraction from raw alert data
│   └── threshold_manager.py         # Configurable routing thresholds
├── tools/
│   ├── tms_connector.py             # TMS integration (Actimize/Verafin/NICE)
│   ├── customer_context.py          # Core banking customer lookup
│   ├── historical_patterns.py       # FP rate data retrieval
│   └── suppression_engine.py        # Suppression audit records
├── data/fixtures/                   # Sample alerts, customers, historical rates
├── tests/                           # Pytest test suite (graph, scoring, tools)
├── docs/                            # Integration guide, ROI analysis
├── Dockerfile
├── docker-compose.yml
└── railway.toml
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Orchestration | LangGraph 0.2.28+ |
| LLM | OpenAI GPT-4o (configurable: AWS Bedrock, Azure OpenAI) |
| UI | Streamlit 1.43+ |
| Visualization | Plotly 5.24+ |
| Testing | Pytest 8.3+ |
| Database | PostgreSQL (production), in-memory (development) |

---

## Build Order

This is the second agent in a three-part suite:

1. **Financial Crime Investigation Agent** — investigate alerts faster
2. **AML/TMS Enhancement Agent** (this) — stop generating 9/10 bad alerts
3. **Cross-Domain Regulatory Compliance Agent** — elevate from AML tool to compliance intelligence platform

Each agent reuses the same infrastructure, integrations, and LLM stack.
Each one extends the last — and grows the contract with the same buyer.
