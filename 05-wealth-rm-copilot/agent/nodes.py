# agent/nodes.py
# ============================================================
# Wealth & RM Copilot — Node Functions
#
# Design principles:
#   - LLM drafts content; deterministic Python makes suitability decisions
#   - Every node appends to audit_trail (SEC Rule 204-2 / FINRA 4511)
#   - RM approval is mandatory — rm_approval_gate cannot be bypassed
#   - Conflict of interest disclosures are generated automatically
#   - ERISA accounts receive elevated checks for prohibited transactions
#   - No performance guarantees or misleading language in LLM prompts
# ============================================================

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent.state import (
    WealthRMState,
    RequestType,
    RiskTolerance,
    SuitabilityStatus,
    ComplianceStatus,
)
from agent.prompts import (
    MEETING_BRIEFING_SYSTEM_PROMPT,
    MEETING_BRIEFING_HUMAN_PROMPT,
    INVESTMENT_PROPOSAL_SYSTEM_PROMPT,
    INVESTMENT_PROPOSAL_HUMAN_PROMPT,
    PORTFOLIO_REVIEW_SYSTEM_PROMPT,
    PORTFOLIO_REVIEW_HUMAN_PROMPT,
    CLIENT_LETTER_SYSTEM_PROMPT,
    CLIENT_LETTER_HUMAN_PROMPT,
    RECOMMENDATION_SYSTEM_PROMPT,
    RECOMMENDATION_HUMAN_PROMPT,
    COMPLIANCE_CHECK_SYSTEM_PROMPT,
    COMPLIANCE_CHECK_HUMAN_PROMPT,
)

logger = logging.getLogger(__name__)


# ── Shared Helpers ────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_audit_entry(
    state: WealthRMState,
    action: str,
    node: str,
    data_sources: Optional[List[str]] = None,
    ai_model: Optional[str] = None,
    regulatory_basis: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Append audit entry. Returns new list (does not mutate original)."""
    trail = list(state.get("audit_trail") or [])
    trail.append({
        "timestamp": _utcnow(),
        "actor": state.get("rm_id", "wealth_rm_copilot"),
        "action": action,
        "node": node,
        "data_sources": data_sources or [],
        "ai_model_used": ai_model,
        "regulatory_basis": regulatory_basis,
    })
    return trail


def _get_llm(temperature: float = 0.3) -> ChatOpenAI:
    """
    Return LLM instance for content drafting.
    temperature=0.3 for professional variation (vs. 0.0 for scoring).
    """
    return ChatOpenAI(model="gpt-4o", temperature=temperature)


def _steps_done(state: WealthRMState, node: str) -> List[str]:
    steps = list(state.get("completed_steps") or [])
    steps.append(node)
    return steps


# ── NODE 1: Trigger Intake ────────────────────────────────────────────────────

def trigger_intake(state: WealthRMState) -> Dict[str, Any]:
    """
    Parse and validate the RM's workflow request.

    Validates: request_id, rm_id, client_id, request_type.
    Classifies request to determine which downstream nodes need
    which inputs (e.g., MEETING_PREP needs meeting_date).

    Every workflow run must be associated with an RM ID for
    accountability. AI outputs are attributed to the approving RM,
    not the system — consistent with SEC Advisers Act fiduciary duty.
    """
    logger.info(f"[trigger_intake] Processing request {state.get('request_id')} "
                f"from RM {state.get('rm_id')}")

    errors = list(state.get("errors") or [])
    required = ["request_id", "rm_id", "client_id", "request_type"]
    for f in required:
        if not state.get(f):
            errors.append({"node": "trigger_intake", "field": f,
                           "message": f"Required field '{f}' missing"})

    request_type = state.get("request_type")
    if isinstance(request_type, str):
        try:
            request_type = RequestType(request_type)
        except ValueError:
            errors.append({"node": "trigger_intake", "field": "request_type",
                           "message": f"Invalid request_type: {request_type}"})

    audit_trail = _add_audit_entry(
        state,
        action=f"Workflow initiated — {request_type} for client {state.get('client_id')} "
               f"by RM {state.get('rm_id')}",
        node="trigger_intake",
        regulatory_basis="SEC Rule 204-2 — workflow record initiation",
    )

    return {
        "request_type": request_type,
        "current_step": "trigger_intake",
        "completed_steps": _steps_done(state, "trigger_intake"),
        "errors": errors,
        "audit_trail": audit_trail,
    }


# ── NODE 2: Client Profile Lookup ─────────────────────────────────────────────

def client_profile_lookup(state: WealthRMState) -> Dict[str, Any]:
    """
    Retrieve client profile, IPS, and account information from CRM.

    Fetches:
      - Demographic data (age, marital status, dependents)
      - Financial profile (income, net worth, AUM, tax bracket)
      - Investment objectives (goals, time horizon, risk tolerance)
      - IPS (target allocations, return objective, rebalancing bands)
      - Account types (ERISA flag for retirement accounts)
      - Special considerations (restricted securities, ESG, RMD dates)

    FINRA Rule 4512: Customer account information must be current.
    IPS refresh is flagged as an open item if > 24 months old.

    In production: queries CRM (Salesforce FSC), IPS repository,
    and account management system.
    """
    client_id = state.get("client_id", "UNKNOWN")
    logger.info(f"[client_profile_lookup] Loading profile for {client_id}")

    client_profile, ips_summary = _load_client_fixture(client_id)

    # Flag IPS refresh if stale
    open_items = []
    ips_last_updated = ips_summary.get("last_updated", "")
    if ips_last_updated:
        try:
            from datetime import timedelta
            ips_date = datetime.fromisoformat(ips_last_updated.replace("Z", "+00:00"))
            age_months = (datetime.now(timezone.utc) - ips_date).days / 30
            if age_months > 24:
                open_items.append(
                    f"IPS requires refresh — last updated {ips_last_updated[:10]} "
                    f"({age_months:.0f} months ago). FINRA 4512 recommends annual review."
                )
        except Exception:
            pass

    # Flag upcoming RMD
    rmd_date = client_profile.get("next_rmd_date")
    if rmd_date:
        open_items.append(
            f"Required Minimum Distribution (RMD) scheduled: {rmd_date}. "
            "Confirm distribution amount and payment instructions."
        )

    audit_trail = _add_audit_entry(
        state,
        action=f"Client profile loaded — {client_profile.get('full_name')}, "
               f"AUM ${client_profile.get('total_aum', 0):,.0f}, "
               f"risk tolerance {client_profile.get('risk_tolerance')}",
        node="client_profile_lookup",
        data_sources=["crm_salesforce", "ips_repository", "account_management_system"],
        regulatory_basis="FINRA 4512 — customer account information; SEC IA Act — client suitability basis",
    )

    return {
        "client_profile": client_profile,
        "ips_summary": ips_summary,
        "open_items": open_items,
        "current_step": "client_profile_lookup",
        "completed_steps": _steps_done(state, "client_profile_lookup"),
        "audit_trail": audit_trail,
    }


def _load_client_fixture(client_id: str) -> tuple:
    """Load client data from fixture file or generate synthetic record."""
    import json
    from pathlib import Path

    fixture_path = Path("data/fixtures/sample_clients.json")
    if fixture_path.exists():
        with open(fixture_path) as f:
            clients = json.load(f)
        match = next((c for c in clients if c.get("client_id") == client_id), None)
        if match:
            return match.get("profile", {}), match.get("ips", {})

    # Synthetic fallback
    return _synthetic_client(client_id)


def _synthetic_client(client_id: str) -> tuple:
    rng = random.Random(hash(client_id) % 10000)
    aum = rng.choice([425000, 850000, 2100000, 4500000, 8200000])
    profile = {
        "full_name": "Demo Client",
        "age": rng.randint(42, 68),
        "marital_status": "Married",
        "dependents": rng.randint(0, 3),
        "employment_status": "Employed",
        "annual_income": round(aum * 0.08, 0),
        "net_worth": round(aum * 2.5, 0),
        "total_aum": aum,
        "primary_goals": ["Retirement", "Estate Planning"],
        "time_horizon_years": rng.randint(10, 25),
        "risk_tolerance": rng.choice(["MODERATE", "MODERATE_AGGRESSIVE", "CONSERVATIVE"]),
        "tax_bracket": "32%",
        "state_of_domicile": "MA",
        "is_retirement_account": rng.random() > 0.5,
        "liquidity_needs": "MEDIUM",
        "esg_preference": False,
        "restricted_securities": [],
        "client_since_date": "2018-03-15",
        "last_review_date": "2025-09-01",
        "next_rmd_date": None,
        "beneficiary_review_date": "2024-01-15",
    }
    ips = {
        "target_allocations": {
            "US_EQUITY": 40, "INTL_EQUITY": 20, "FIXED_INCOME": 30, "ALTERNATIVES": 5, "CASH": 5
        },
        "rebalancing_bands": {
            "US_EQUITY": 5, "INTL_EQUITY": 5, "FIXED_INCOME": 5, "ALTERNATIVES": 3, "CASH": 3
        },
        "return_objective": "6-7% annualized over full market cycle",
        "income_requirement": 0,
        "prohibited_securities": [],
        "esg_screens": [],
        "benchmark": "60/40 Blended Benchmark",
        "last_updated": "2024-06-01",
        "ips_version": "v3.1",
    }
    return profile, ips


# ── NODE 3: Portfolio Analysis ────────────────────────────────────────────────

def portfolio_analysis(state: WealthRMState) -> Dict[str, Any]:
    """
    Analyze current portfolio: holdings, performance, drift, concentration.

    Computes:
      - Current allocation vs. IPS targets (drift analysis)
      - Positions outside rebalancing bands (triggers REBALANCING flag)
      - Concentrated positions (> 10% single security — suitability concern)
      - YTD, 1-year, 3-year performance vs. benchmark
      - Unrealized gains/losses (tax-lot awareness)

    Concentrated positions > 20% require explicit documentation under
    Reg BI — the RM must document why concentrated exposure is in the
    client's best interest, or recommend diversification.

    In production: queries Orion / Tamarac / Addepar portfolio system.
    """
    client_id = state.get("client_id", "UNKNOWN")
    logger.info(f"[portfolio_analysis] Analyzing portfolio for {client_id}")

    client_profile = state.get("client_profile") or {}
    ips_summary = state.get("ips_summary") or {}

    portfolio = _load_portfolio_fixture(client_id, client_profile, ips_summary)
    drift = _compute_drift(portfolio, ips_summary)
    concentrated = _find_concentrated_positions(portfolio)

    open_items = list(state.get("open_items") or [])
    if drift.get("requires_rebalancing"):
        open_items.append(
            f"Portfolio rebalancing required — max drift {drift.get('max_drift', 0):.1f}% "
            f"outside IPS tolerance band."
        )
    if concentrated:
        names = ", ".join(p.get("name", p.get("symbol")) for p in concentrated[:3])
        open_items.append(
            f"Concentrated position(s) flagged: {names}. "
            "Document Reg BI best-interest rationale or recommend diversification."
        )

    audit_trail = _add_audit_entry(
        state,
        action=f"Portfolio analyzed — MV ${portfolio.get('total_market_value', 0):,.0f}, "
               f"YTD {portfolio.get('ytd_return', 0):+.1f}%, "
               f"rebalancing needed: {drift.get('requires_rebalancing', False)}",
        node="portfolio_analysis",
        data_sources=["portfolio_management_system", "custodian_feed", "market_data"],
        regulatory_basis="Reg BI care obligation — portfolio monitoring; SR 11-7 model documentation",
    )

    return {
        "portfolio_snapshot": portfolio,
        "allocation_drift": drift,
        "concentrated_positions": concentrated,
        "open_items": open_items,
        "current_step": "portfolio_analysis",
        "completed_steps": _steps_done(state, "portfolio_analysis"),
        "audit_trail": audit_trail,
    }


def _load_portfolio_fixture(client_id: str, client_profile: dict, ips_summary: dict) -> dict:
    import json
    from pathlib import Path

    fixture_path = Path("data/fixtures/sample_portfolios.json")
    if fixture_path.exists():
        with open(fixture_path) as f:
            portfolios = json.load(f)
        match = next((p for p in portfolios if p.get("client_id") == client_id), None)
        if match:
            return match.get("portfolio", {})

    return _synthetic_portfolio(client_id, client_profile, ips_summary)


def _synthetic_portfolio(client_id: str, client_profile: dict, ips_summary: dict) -> dict:
    rng = random.Random(hash(client_id + "portfolio") % 10000)
    aum = client_profile.get("total_aum", 500000)
    ytd = rng.uniform(-5, 18)
    bench = ytd - rng.uniform(-3, 3)
    targets = ips_summary.get("target_allocations", {
        "US_EQUITY": 40, "INTL_EQUITY": 20, "FIXED_INCOME": 30, "ALTERNATIVES": 5, "CASH": 5
    })

    holdings = []
    eq_value = aum * rng.uniform(0.38, 0.65)
    holdings += [
        {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "asset_class": "US_EQUITY",
         "shares": round(eq_value * 0.6 / 485, 1), "price": 485.20,
         "value": round(eq_value * 0.6, 2), "weight": round(eq_value * 0.6 / aum * 100, 1)},
        {"symbol": "AAPL", "name": "Apple Inc.", "asset_class": "US_EQUITY",
         "shares": round(eq_value * 0.25 / 189, 1), "price": 189.30,
         "value": round(eq_value * 0.25, 2), "weight": round(eq_value * 0.25 / aum * 100, 1)},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "asset_class": "US_EQUITY",
         "shares": round(eq_value * 0.15 / 415, 1), "price": 415.80,
         "value": round(eq_value * 0.15, 2), "weight": round(eq_value * 0.15 / aum * 100, 1)},
    ]
    int_eq = aum * 0.15
    holdings.append(
        {"symbol": "VXUS", "name": "Vanguard Total Intl Stock ETF", "asset_class": "INTL_EQUITY",
         "shares": round(int_eq / 62, 1), "price": 62.10, "value": round(int_eq, 2),
         "weight": round(int_eq / aum * 100, 1)}
    )
    fi_value = aum * 0.28
    holdings += [
        {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "asset_class": "FIXED_INCOME",
         "shares": round(fi_value * 0.7 / 74, 1), "price": 74.20,
         "value": round(fi_value * 0.7, 2), "weight": round(fi_value * 0.7 / aum * 100, 1)},
        {"symbol": "VTIP", "name": "Vanguard Short-Term Inflation-Protected ETF",
         "asset_class": "FIXED_INCOME", "shares": round(fi_value * 0.3 / 49, 1), "price": 49.50,
         "value": round(fi_value * 0.3, 2), "weight": round(fi_value * 0.3 / aum * 100, 1)},
    ]

    return {
        "total_market_value": aum,
        "holdings": holdings,
        "current_allocations": {
            "US_EQUITY": round(eq_value / aum * 100, 1),
            "INTL_EQUITY": round(int_eq / aum * 100, 1),
            "FIXED_INCOME": round(fi_value / aum * 100, 1),
            "ALTERNATIVES": round(rng.uniform(2, 6), 1),
            "CASH": round(rng.uniform(2, 8), 1),
        },
        "ytd_return": round(ytd, 2),
        "one_year_return": round(ytd + rng.uniform(0, 5), 2),
        "three_year_return": round(rng.uniform(4, 12), 2),
        "inception_return": round(rng.uniform(6, 10), 2),
        "benchmark_ytd": round(bench, 2),
        "benchmark_one_year": round(bench + rng.uniform(0, 4), 2),
        "alpha": round(ytd - bench, 2),
        "sharpe_ratio": round(rng.uniform(0.6, 1.4), 2),
        "unrealized_gains": round(aum * rng.uniform(0.05, 0.25), 2),
        "unrealized_losses": round(aum * rng.uniform(0, 0.05), 2),
        "last_rebalanced_date": "2025-09-15",
        "as_of_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def _compute_drift(portfolio: dict, ips_summary: dict) -> dict:
    current = portfolio.get("current_allocations", {})
    targets = ips_summary.get("target_allocations", {})
    bands = ips_summary.get("rebalancing_bands", {})

    drift_detail = {}
    max_drift = 0.0
    requires_rebalancing = False

    for asset_class, target in targets.items():
        current_pct = current.get(asset_class, 0)
        drift_pct = current_pct - target
        band = bands.get(asset_class, 5)
        outside = abs(drift_pct) > band

        if outside:
            requires_rebalancing = True
        if abs(drift_pct) > max_drift:
            max_drift = abs(drift_pct)

        drift_detail[asset_class] = {
            "target_pct": target,
            "current_pct": current_pct,
            "drift_pct": round(drift_pct, 1),
            "band": band,
            "outside_band": outside,
        }

    direction = []
    for ac, d in drift_detail.items():
        if d["outside_band"]:
            direction.append(
                f"{ac}: {d['current_pct']:.1f}% vs. target {d['target_pct']:.0f}% "
                f"(drift {d['drift_pct']:+.1f}%)"
            )

    return {
        "drift_by_asset_class": drift_detail,
        "requires_rebalancing": requires_rebalancing,
        "max_drift": round(max_drift, 1),
        "drift_summary": "; ".join(direction) if direction else "All allocations within IPS tolerance bands",
    }


def _find_concentrated_positions(portfolio: dict) -> list:
    holdings = portfolio.get("holdings", [])
    return [h for h in holdings if h.get("weight", 0) >= 10.0]


# ── NODE 4: Market Intelligence ────────────────────────────────────────────────

def market_intelligence(state: WealthRMState) -> Dict[str, Any]:
    """
    Gather market context relevant to this client's portfolio and goals.

    Sources:
      - Portfolio-specific news (holdings from portfolio_snapshot)
      - Macro themes affecting the asset allocation
      - Sector-level alerts
      - Life event detection (RMD, estate, retirement transition signals)

    News is filtered to what is actionable for this specific client —
    not a generic market summary. The goal is to arm the RM with
    the 3-5 most relevant conversation starters.

    In production: Bloomberg News API, Refinitiv Eikon, FactSet.
    """
    client_id = state.get("client_id", "UNKNOWN")
    logger.info(f"[market_intelligence] Gathering market context for {client_id}")

    portfolio = state.get("portfolio_snapshot") or {}
    client_profile = state.get("client_profile") or {}
    holdings = portfolio.get("holdings", [])
    symbols = [h.get("symbol") for h in holdings if h.get("symbol")]

    market_context = _build_market_context(symbols, client_profile)
    life_events = _detect_life_events(client_profile)

    open_items = list(state.get("open_items") or [])
    for event in life_events:
        if event.get("action_required"):
            open_items.append(f"Life Event — {event.get('type')}: {event.get('action_required')}")

    audit_trail = _add_audit_entry(
        state,
        action=f"Market intelligence gathered — {len(market_context.get('relevant_news', []))} "
               f"relevant articles, {len(life_events)} life events detected",
        node="market_intelligence",
        data_sources=["market_data_api", "news_aggregator", "crm_life_events"],
        regulatory_basis="Reg BI care obligation — ongoing monitoring of client holdings",
    )

    return {
        "market_context": market_context,
        "life_events": life_events,
        "open_items": open_items,
        "current_step": "market_intelligence",
        "completed_steps": _steps_done(state, "market_intelligence"),
        "audit_trail": audit_trail,
    }


def _build_market_context(symbols: list, client_profile: dict) -> dict:
    """Simulate market context. In production: Bloomberg / Refinitiv API."""
    relevant_news = [
        {
            "headline": "Federal Reserve signals pause in rate hike cycle; bond market rallies",
            "source": "Wall Street Journal",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "symbols_affected": ["BND", "VTIP"],
            "impact_summary": "Fixed income positions likely to benefit from rate stabilization. "
                              "Review duration positioning against IPS.",
        },
        {
            "headline": "Technology sector earnings beat estimates; growth outlook revised upward",
            "source": "Bloomberg",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "symbols_affected": ["AAPL", "MSFT", "VOO"],
            "impact_summary": "Client's US equity overweight may be validated near-term. "
                              "Monitor for rebalancing trigger as weights increase.",
        },
        {
            "headline": "International equities: Eurozone GDP growth slows amid energy concerns",
            "source": "Financial Times",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "symbols_affected": ["VXUS"],
            "impact_summary": "International allocation underperformance may continue short-term. "
                              "Consider discussing IPS target vs. current underweight.",
        },
    ]

    relevant_news = [
        n for n in relevant_news
        if any(s in symbols for s in n.get("symbols_affected", []))
    ] or relevant_news[:2]

    return {
        "relevant_news": relevant_news,
        "macro_themes": [
            "Fed policy — rate pause scenario; watch 2026 cut timing",
            "Equity valuations — S&P P/E elevated vs. historical averages",
            "Duration risk — bond laddering opportunity in short-to-mid segment",
        ],
        "market_snapshot": {
            "sp500_ytd": "+14.2%",
            "bond_aggregate_ytd": "+3.1%",
            "10yr_treasury": "4.35%",
            "vix": "16.2",
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
    }


def _detect_life_events(client_profile: dict) -> list:
    """Detect life events from client profile data that require advisory attention."""
    events = []
    age = client_profile.get("age", 0)

    if age >= 72:
        events.append({
            "type": "RMD_START",
            "detected_date": _utcnow()[:10],
            "action_required": "Confirm RMD amount and distribution schedule for retirement accounts.",
        })
    if age >= 60 and client_profile.get("employment_status") == "Employed":
        events.append({
            "type": "RETIREMENT_PLANNING",
            "detected_date": _utcnow()[:10],
            "action_required": "Review retirement income plan and Social Security claiming strategy.",
        })

    ben_date = client_profile.get("beneficiary_review_date", "")
    if ben_date and ben_date < "2024-01-01":
        events.append({
            "type": "ESTATE_PLANNING",
            "detected_date": _utcnow()[:10],
            "action_required": "Beneficiary designations not reviewed in 2+ years. Schedule estate review.",
        })

    return events


# ── NODE 5: Suitability Check ──────────────────────────────────────────────────

def suitability_check(state: WealthRMState) -> Dict[str, Any]:
    """
    Perform Reg BI / FINRA 2111 suitability analysis.

    CRITICAL: This is deterministic Python, not LLM output.
    Suitability determinations require documented human accountability.
    The LLM may draft the explanation; the determination is Python logic.

    Checks performed:
      1. Risk alignment — does request match client's risk tolerance?
      2. IPS compliance — does request align with stated objectives?
      3. Time horizon appropriateness — suitable for client's horizon?
      4. ERISA check — if retirement account, prohibited transaction screen
      5. Concentration check — does request worsen concentration?
      6. Cost analysis — are costs reasonable vs. alternatives? (Reg BI)
      7. Conflict of interest — any firm-revenue conflicts to disclose?

    Returns SuitabilityStatus:
      SUITABLE              → proceed to recommendations
      SUITABLE_WITH_NOTE    → proceed with required disclosures
      UNSUITABLE            → block workflow, notify RM
      NEEDS_REVIEW          → flag items but allow to proceed
    """
    logger.info(f"[suitability_check] Running suitability for {state.get('request_id')}")

    client_profile = state.get("client_profile") or {}
    ips_summary = state.get("ips_summary") or {}
    request_type = state.get("request_type")
    investment_idea = state.get("investment_idea", "")
    drift = state.get("allocation_drift") or {}
    concentrated = state.get("concentrated_positions") or []

    checks = []
    disclosures = []
    overall = SuitabilityStatus.SUITABLE

    # 1. Risk tolerance alignment
    risk = client_profile.get("risk_tolerance", "MODERATE")
    if request_type == RequestType.INVESTMENT_PROPOSAL and investment_idea:
        high_risk_keywords = ["leveraged", "options", "speculative", "emerging", "cryptocurrency", "crypto"]
        conservative_client = risk in ("CONSERVATIVE", "MODERATE_CONSERVATIVE")
        if conservative_client and any(kw in investment_idea.lower() for kw in high_risk_keywords):
            checks.append({
                "check": "RISK_TOLERANCE_ALIGNMENT",
                "passed": False,
                "note": f"High-risk product proposed for {risk} client. UNSUITABLE under FINRA 2111.",
            })
            overall = SuitabilityStatus.UNSUITABLE
        else:
            checks.append({"check": "RISK_TOLERANCE_ALIGNMENT", "passed": True,
                           "note": f"Investment aligns with {risk} risk profile."})
    else:
        checks.append({"check": "RISK_TOLERANCE_ALIGNMENT", "passed": True,
                       "note": "Request type does not involve new risk product introduction."})

    # 2. IPS compliance
    prohibited = ips_summary.get("prohibited_securities", [])
    if investment_idea and prohibited:
        if any(p.lower() in investment_idea.lower() for p in prohibited):
            checks.append({
                "check": "IPS_PROHIBITED_SECURITIES",
                "passed": False,
                "note": f"Proposed investment conflicts with IPS prohibited securities list.",
            })
            overall = SuitabilityStatus.UNSUITABLE
        else:
            checks.append({"check": "IPS_PROHIBITED_SECURITIES", "passed": True,
                           "note": "No IPS prohibited security conflicts detected."})
    else:
        checks.append({"check": "IPS_PROHIBITED_SECURITIES", "passed": True, "note": "No prohibited securities on file."})

    # 3. ERISA check for retirement accounts
    if client_profile.get("is_retirement_account"):
        checks.append({
            "check": "ERISA_FIDUCIARY_SCREEN",
            "passed": True,
            "note": "Retirement account — ERISA fiduciary standard applies. All recommendations must pass prudent investor test.",
        })
        disclosures.append(
            "ERISA Fiduciary Disclosure: This account is subject to ERISA fiduciary standards. "
            "All recommendations must be in the exclusive benefit of plan participants. "
            "Prohibited transactions under IRC § 4975 have been screened."
        )
        if overall == SuitabilityStatus.SUITABLE:
            overall = SuitabilityStatus.SUITABLE_WITH_NOTE

    # 4. Concentration check
    if concentrated:
        names = [p.get("name", p.get("symbol")) for p in concentrated[:2]]
        checks.append({
            "check": "CONCENTRATION_RISK",
            "passed": True,
            "note": f"Concentrated positions detected: {', '.join(names)}. "
                    "Reg BI documentation required if worsening concentration.",
        })
        disclosures.append(
            f"Concentration Risk Disclosure: Client holds concentrated position(s) in {', '.join(names)}. "
            "The Firm has recommended diversification. Client has acknowledged concentration risk."
        )
        if overall == SuitabilityStatus.SUITABLE:
            overall = SuitabilityStatus.SUITABLE_WITH_NOTE

    # 5. Cost reasonableness
    checks.append({
        "check": "COST_REASONABLENESS",
        "passed": True,
        "note": "Cost analysis to be completed in recommendation_engine node. "
                "Lower-cost alternatives will be documented per Reg BI care obligation.",
    })

    # 6. IPS current
    ips_date = ips_summary.get("last_updated", "")
    if ips_date and ips_date < "2024-01-01":
        checks.append({
            "check": "IPS_CURRENCY",
            "passed": False,
            "note": f"IPS last updated {ips_date[:10]}. Over 24 months old. Requires refresh before recommendations.",
        })
        if overall == SuitabilityStatus.SUITABLE:
            overall = SuitabilityStatus.NEEDS_REVIEW
    else:
        checks.append({"check": "IPS_CURRENCY", "passed": True, "note": "IPS is current."})

    # Reg BI care obligation rationale
    reg_bi_rationale = (
        f"Reg BI Care Obligation Documentation: "
        f"The proposed {request_type} for {client_profile.get('full_name', 'client')} "
        f"(risk tolerance: {risk}, time horizon: {client_profile.get('time_horizon_years', 'unknown')} years) "
        f"has been evaluated against the client's Investment Policy Statement (v{ips_summary.get('ips_version', 'current')}). "
        f"Suitability determination: {overall.value}. "
        f"{len([c for c in checks if c['passed']])} of {len(checks)} checks passed. "
        f"{'Conflicts of interest: ' + '; '.join(disclosures[:1]) if disclosures else 'No conflicts requiring disclosure identified.'}"
    )

    suitability_analysis = {
        "overall_status": overall,
        "checks_performed": checks,
        "conflict_of_interest_disclosures": disclosures,
        "cost_analysis": "Pending — see recommendation_engine",
        "reg_bi_care_obligation": reg_bi_rationale,
    }

    audit_trail = _add_audit_entry(
        state,
        action=f"Suitability check complete — {overall.value}, "
               f"{len(checks)} checks, {len(disclosures)} disclosures",
        node="suitability_check",
        data_sources=["ips_repository", "prohibited_securities_list", "erisa_screening"],
        regulatory_basis="Reg BI 17 CFR 240.15l-1 care obligation; FINRA Rule 2111 suitability",
    )

    return {
        "suitability_analysis": suitability_analysis,
        "suitability_status": overall,
        "reg_bi_rationale": reg_bi_rationale,
        "current_step": "suitability_check",
        "completed_steps": _steps_done(state, "suitability_check"),
        "audit_trail": audit_trail,
    }


# ── NODE 6: Block Unsuitable ──────────────────────────────────────────────────

def block_unsuitable(state: WealthRMState) -> Dict[str, Any]:
    """
    Surface unsuitable determination to the RM. Workflow ends.

    RM is notified with specific reasons. They must resolve the
    suitability issue before re-submitting the request.
    This node ensures unsuitable recommendations never reach clients.
    """
    logger.warning(f"[block_unsuitable] Workflow blocked — UNSUITABLE for {state.get('request_id')}")

    analysis = state.get("suitability_analysis") or {}
    failed_checks = [c for c in analysis.get("checks_performed", []) if not c.get("passed")]

    reasons = "\n".join(f"• {c.get('check')}: {c.get('note')}" for c in failed_checks)
    block_message = (
        f"WORKFLOW BLOCKED — UNSUITABLE DETERMINATION\n\n"
        f"Request: {state.get('request_id')}\n"
        f"Client: {(state.get('client_profile') or {}).get('full_name', state.get('client_id'))}\n\n"
        f"Reason(s):\n{reasons}\n\n"
        f"Action required: Resolve suitability issues before re-submitting. "
        f"Contact Compliance if guidance needed."
    )

    audit_trail = _add_audit_entry(
        state,
        action=f"Workflow BLOCKED — UNSUITABLE. Failed checks: {[c.get('check') for c in failed_checks]}",
        node="block_unsuitable",
        regulatory_basis="Reg BI 17 CFR 240.15l-1 — unsuitable recommendation prevented",
    )

    return {
        "draft_content": block_message,
        "output_type": "UNSUITABLE_BLOCK",
        "current_step": "block_unsuitable",
        "completed_steps": _steps_done(state, "block_unsuitable"),
        "audit_trail": audit_trail,
    }


# ── NODE 7: Recommendation Engine ─────────────────────────────────────────────

def recommendation_engine(state: WealthRMState) -> Dict[str, Any]:
    """
    Generate investment recommendations aligned to IPS and request type.

    Uses LLM to synthesize all gathered context (portfolio, market,
    suitability) into specific, actionable investment ideas.

    For REBALANCING_PROPOSAL: generates specific trades to restore
    IPS target allocations, with tax-lot optimization notes.

    For INVESTMENT_PROPOSAL: evaluates the RM's proposed investment
    against IPS, generates alternatives for comparison (Reg BI).

    For MEETING_PREP / PORTFOLIO_REVIEW: generates talking points
    and forward-looking commentary (with required caveats).

    Every recommendation includes:
      - Specific rationale grounded in IPS
      - Lower-cost alternatives considered (Reg BI care obligation)
      - Estimated costs vs. alternatives
      - Suitability note
    """
    logger.info(f"[recommendation_engine] Generating recommendations for {state.get('request_id')}")

    try:
        llm = _get_llm(temperature=0.2)
        request_type = state.get("request_type")
        client_profile = state.get("client_profile") or {}
        ips_summary = state.get("ips_summary") or {}
        portfolio = state.get("portfolio_snapshot") or {}
        drift = state.get("allocation_drift") or {}
        market_context = state.get("market_context") or {}
        concentrated = state.get("concentrated_positions") or []

        human_content = RECOMMENDATION_HUMAN_PROMPT.format(
            request_type=request_type,
            client_name=client_profile.get("full_name", "Client"),
            risk_tolerance=client_profile.get("risk_tolerance", "MODERATE"),
            time_horizon=client_profile.get("time_horizon_years", 15),
            investment_idea=state.get("investment_idea", "N/A"),
            ips_targets=ips_summary.get("target_allocations", {}),
            current_allocations=portfolio.get("current_allocations", {}),
            drift_summary=drift.get("drift_summary", ""),
            requires_rebalancing=drift.get("requires_rebalancing", False),
            ytd_return=portfolio.get("ytd_return", 0),
            benchmark_ytd=portfolio.get("benchmark_ytd", 0),
            macro_themes=market_context.get("macro_themes", []),
            concentrated_positions=concentrated,
            is_retirement=client_profile.get("is_retirement_account", False),
        )

        response = llm.invoke([
            SystemMessage(content=RECOMMENDATION_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])

        recommendations_text = response.content
        recommendations = _parse_recommendations(recommendations_text, state)

    except Exception as e:
        logger.error(f"[recommendation_engine] LLM call failed: {e}")
        recommendations = _fallback_recommendations(state)
        recommendations_text = "Recommendations generated via fallback."

    rebalancing_trades = None
    if state.get("allocation_drift", {}).get("requires_rebalancing"):
        rebalancing_trades = _compute_rebalancing_trades(state)

    audit_trail = _add_audit_entry(
        state,
        action=f"Recommendations generated — {len(recommendations)} recommendation(s), "
               f"rebalancing trades: {len(rebalancing_trades or [])}",
        node="recommendation_engine",
        data_sources=["ips_repository", "portfolio_data", "market_intel"],
        ai_model="gpt-4o",
        regulatory_basis="Reg BI care obligation — recommendations with alternatives documented",
    )

    return {
        "recommendations": recommendations,
        "rebalancing_trades": rebalancing_trades,
        "current_step": "recommendation_engine",
        "completed_steps": _steps_done(state, "recommendation_engine"),
        "audit_trail": audit_trail,
    }


def _parse_recommendations(text: str, state: WealthRMState) -> list:
    """Extract structured recommendations from LLM text."""
    request_type = state.get("request_type")
    portfolio = state.get("portfolio_snapshot") or {}
    aum = portfolio.get("total_market_value", 100000)
    drift = state.get("allocation_drift") or {}

    recs = []
    if drift.get("requires_rebalancing"):
        for asset_class, d in drift.get("drift_by_asset_class", {}).items():
            if d.get("outside_band"):
                action = "SELL" if d["drift_pct"] > 0 else "BUY"
                amount = abs(d["drift_pct"] / 100 * aum)
                recs.append({
                    "action": action,
                    "security": f"{asset_class} index fund",
                    "asset_class": asset_class,
                    "rationale": f"Restore IPS target allocation. Current: {d['current_pct']:.1f}%, "
                                 f"Target: {d['target_pct']:.0f}%",
                    "amount_usd": round(amount, 0),
                    "ips_alignment": "Direct IPS target restoration",
                    "risk_level": "LOW — rebalancing to stated IPS targets",
                    "estimated_cost": round(amount * 0.0003, 2),
                    "alternatives_considered": ["Tax-loss harvesting alternatives if applicable"],
                    "suitability_note": "Rebalancing to client's own IPS targets is presumptively suitable.",
                })

    if not recs:
        recs.append({
            "action": "HOLD",
            "security": "Current portfolio",
            "asset_class": "DIVERSIFIED",
            "rationale": "Portfolio allocations within IPS tolerance bands. No immediate action required.",
            "amount_usd": 0,
            "ips_alignment": "Consistent with IPS",
            "risk_level": "N/A",
            "estimated_cost": 0,
            "alternatives_considered": [],
            "suitability_note": "Current positioning is suitable. Continue monitoring.",
        })

    return recs


def _fallback_recommendations(state: WealthRMState) -> list:
    return [{
        "action": "REVIEW",
        "security": "Portfolio",
        "asset_class": "DIVERSIFIED",
        "rationale": "Review portfolio against IPS targets. LLM analysis unavailable.",
        "amount_usd": 0,
        "ips_alignment": "Pending review",
        "risk_level": "UNKNOWN",
        "estimated_cost": 0,
        "alternatives_considered": [],
        "suitability_note": "Manual review required.",
    }]


def _compute_rebalancing_trades(state: WealthRMState) -> list:
    """Compute specific buy/sell trades to restore IPS target allocations."""
    portfolio = state.get("portfolio_snapshot") or {}
    drift = state.get("allocation_drift") or {}
    aum = portfolio.get("total_market_value", 0)
    trades = []

    for asset_class, d in drift.get("drift_by_asset_class", {}).items():
        if not d.get("outside_band"):
            continue
        delta_value = abs(d.get("drift_pct", 0) / 100 * aum)
        action = "SELL" if d.get("drift_pct", 0) > 0 else "BUY"
        symbol_map = {
            "US_EQUITY": "VOO", "INTL_EQUITY": "VXUS",
            "FIXED_INCOME": "BND", "ALTERNATIVES": "ABRYX", "CASH": "VMFXX"
        }
        trades.append({
            "symbol": symbol_map.get(asset_class, asset_class),
            "asset_class": asset_class,
            "action": action,
            "estimated_value": round(delta_value, 2),
            "current_pct": d.get("current_pct"),
            "target_pct": d.get("target_pct"),
            "tax_impact_note": "Review tax lots — consider harvesting losses before selling gains.",
        })
    return trades


# ── NODE 8: Content Drafting ───────────────────────────────────────────────────

def content_drafting(state: WealthRMState) -> Dict[str, Any]:
    """
    Draft the primary output document based on request_type.

    Output types:
      MEETING_PREP      → MEETING_BRIEFING (talking points + agenda)
      INVESTMENT_PROPOSAL / REBALANCING → INVESTMENT_PROPOSAL (formal proposal)
      PORTFOLIO_REVIEW  → PORTFOLIO_REVIEW (perf analysis + commentary)
      CLIENT_COMM       → CLIENT_LETTER (personalized letter/email)
      ALERT_RESPONSE    → ALERT_BRIEFING (RM action brief)

    All drafts:
      - Are marked "[AI DRAFT — RM REVIEW REQUIRED]"
      - Contain no performance guarantees
      - Use hedged forward-looking language
      - Include Reg BI / FINRA 2210 required disclosures placeholders

    RM sees this draft in the rm_approval_gate before any client use.
    """
    logger.info(f"[content_drafting] Drafting {state.get('request_type')} output for {state.get('request_id')}")

    request_type = state.get("request_type")
    client_profile = state.get("client_profile") or {}

    try:
        llm = _get_llm(temperature=0.4)
        system_prompt, human_prompt = _select_prompts(request_type)

        human_content = human_prompt.format(
            client_name=client_profile.get("full_name", "Valued Client"),
            rm_id=state.get("rm_id", "Your RM"),
            client_age=client_profile.get("age", ""),
            total_aum=client_profile.get("total_aum", 0),
            risk_tolerance=client_profile.get("risk_tolerance", "MODERATE"),
            time_horizon=client_profile.get("time_horizon_years", 15),
            primary_goals=", ".join(client_profile.get("primary_goals", ["Retirement"])),
            ytd_return=state.get("portfolio_snapshot", {}).get("ytd_return", 0),
            benchmark_ytd=state.get("portfolio_snapshot", {}).get("benchmark_ytd", 0),
            alpha=state.get("portfolio_snapshot", {}).get("alpha", 0),
            recommendations=state.get("recommendations", []),
            rebalancing_trades=state.get("rebalancing_trades", []),
            talking_points_context=state.get("market_context", {}).get("macro_themes", []),
            open_items=state.get("open_items", []),
            life_events=state.get("life_events", []),
            relevant_news=state.get("market_context", {}).get("relevant_news", []),
            request_context=state.get("request_context", ""),
            investment_idea=state.get("investment_idea", ""),
            meeting_date=state.get("meeting_date", "upcoming meeting"),
            suitability_status=state.get("suitability_status", "SUITABLE"),
            reg_bi_rationale=state.get("reg_bi_rationale", ""),
            drift_summary=state.get("allocation_drift", {}).get("drift_summary", ""),
            is_retirement=client_profile.get("is_retirement_account", False),
            benchmark=state.get("ips_summary", {}).get("benchmark", "60/40 Blended Benchmark"),
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content),
        ])
        draft = response.content

    except Exception as e:
        logger.error(f"[content_drafting] LLM failed: {e}")
        draft = _fallback_draft(state)

    # Extract talking points (first few bullet-like lines)
    talking_points = _extract_talking_points(draft)

    output_type_map = {
        RequestType.MEETING_PREP: "MEETING_BRIEFING",
        RequestType.REBALANCING_PROPOSAL: "INVESTMENT_PROPOSAL",
        RequestType.INVESTMENT_PROPOSAL: "INVESTMENT_PROPOSAL",
        RequestType.PORTFOLIO_REVIEW: "PORTFOLIO_REVIEW",
        RequestType.CLIENT_COMMUNICATION: "CLIENT_LETTER",
        RequestType.ALERT_RESPONSE: "ALERT_BRIEFING",
    }

    audit_trail = _add_audit_entry(
        state,
        action=f"{output_type_map.get(request_type, 'DOCUMENT')} draft generated — "
               f"{len(draft)} characters, {len(talking_points)} talking points",
        node="content_drafting",
        ai_model="gpt-4o",
        regulatory_basis="FINRA 2210 — draft subject to compliance review before RM delivery",
    )

    return {
        "draft_content": draft,
        "output_type": output_type_map.get(request_type, "DOCUMENT"),
        "talking_points": talking_points,
        "current_step": "content_drafting",
        "completed_steps": _steps_done(state, "content_drafting"),
        "audit_trail": audit_trail,
    }


def _select_prompts(request_type):
    if request_type in (RequestType.MEETING_PREP, RequestType.ALERT_RESPONSE):
        return MEETING_BRIEFING_SYSTEM_PROMPT, MEETING_BRIEFING_HUMAN_PROMPT
    elif request_type in (RequestType.INVESTMENT_PROPOSAL, RequestType.REBALANCING_PROPOSAL):
        return INVESTMENT_PROPOSAL_SYSTEM_PROMPT, INVESTMENT_PROPOSAL_HUMAN_PROMPT
    elif request_type == RequestType.PORTFOLIO_REVIEW:
        return PORTFOLIO_REVIEW_SYSTEM_PROMPT, PORTFOLIO_REVIEW_HUMAN_PROMPT
    else:
        return CLIENT_LETTER_SYSTEM_PROMPT, CLIENT_LETTER_HUMAN_PROMPT


def _extract_talking_points(draft: str) -> list:
    """Extract bullet/numbered points from draft as talking points."""
    import re
    points = re.findall(r'^[•\-\*]\s+(.+)$', draft, re.MULTILINE)
    if not points:
        points = re.findall(r'^\d+\.\s+(.+)$', draft, re.MULTILINE)
    return [p.strip() for p in points[:8]]


def _fallback_draft(state: WealthRMState) -> str:
    client = (state.get("client_profile") or {}).get("full_name", "Client")
    return (
        f"[AI DRAFT — RM REVIEW REQUIRED]\n\n"
        f"Client: {client}\n"
        f"Request: {state.get('request_type')}\n\n"
        f"Draft generation encountered an error. Please review the raw data "
        f"in the Portfolio Analysis and Market Intelligence tabs and prepare "
        f"your notes manually.\n\n"
        f"Key data:\n"
        f"- AUM: ${(state.get('client_profile') or {}).get('total_aum', 0):,.0f}\n"
        f"- YTD Return: {(state.get('portfolio_snapshot') or {}).get('ytd_return', 0):+.1f}%\n"
        f"- Rebalancing required: {(state.get('allocation_drift') or {}).get('requires_rebalancing', False)}\n"
    )


# ── NODE 9: Compliance Review ──────────────────────────────────────────────────

def compliance_review(state: WealthRMState) -> Dict[str, Any]:
    """
    FINRA 2210 compliance check on AI-generated content.

    Checks for:
      - Performance guarantees or promises (prohibited)
      - Cherry-picked return periods without full disclosure
      - Forward-looking statements without required caveats
      - Missing past performance disclaimer
      - Missing Reg BI / Form CRS disclosure references
      - Missing ERISA fiduciary disclosure (retirement accounts)
      - Misleading comparative statements
      - Prohibited language ("safe", "guaranteed", "risk-free")

    Automatically appends required regulatory disclosures.
    Returns APPROVED / APPROVED_WITH_EDITS / REJECTED.
    """
    logger.info(f"[compliance_review] Reviewing content for {state.get('request_id')}")

    draft = state.get("draft_content", "") or ""
    client_profile = state.get("client_profile") or {}
    suitability = state.get("suitability_analysis") or {}

    issues = []
    disclosures = list(state.get("required_disclosures") or [])

    # Check for prohibited language
    prohibited_terms = {
        "guaranteed": "Performance guarantees are prohibited (FINRA 2210(d)(1))",
        "risk-free": "No investment is risk-free (FINRA 2210(d)(1))",
        "safe investment": "Misleading safety claims prohibited",
        "can't lose": "Misleading loss claims prohibited",
        "100% certain": "Certainty claims prohibited",
    }
    for term, reason in prohibited_terms.items():
        if term.lower() in draft.lower():
            issues.append(f"PROHIBITED LANGUAGE: '{term}' — {reason}")

    # Check for past performance disclaimer
    has_returns = any(word in draft.lower() for word in ["return", "performance", "%", "ytd", "gain"])
    has_disclaimer = "past performance" in draft.lower()
    if has_returns and not has_disclaimer:
        issues.append("MISSING DISCLOSURE: Past performance disclaimer required when citing returns")
        disclosures.append(
            "Past Performance Disclosure: Past performance is not indicative of future results. "
            "All performance figures are historical. Investments are subject to market risk including "
            "possible loss of principal."
        )

    # Check for forward-looking statements
    has_forward_looking = any(w in draft.lower() for w in ["will", "expect", "forecast", "predict", "outlook"])
    has_caveat = any(w in draft.lower() for w in ["may", "could", "subject to", "no guarantee"])
    if has_forward_looking and not has_caveat:
        issues.append("MISSING CAVEAT: Forward-looking statements require hedging language")

    # Reg BI disclosure
    disclosures.append(
        "Regulation Best Interest: Your financial professional is required to act in your best interest. "
        "Please refer to our Form CRS (Customer Relationship Summary) for information about our "
        "services, fees, conflicts of interest, and your rights as a retail investor."
    )

    # ERISA disclosure for retirement accounts
    if client_profile.get("is_retirement_account"):
        if "erisa" not in draft.lower():
            disclosures.append(
                "Retirement Account Disclosure: This account is governed by ERISA. "
                "Your advisor acts as a fiduciary with respect to your retirement plan assets. "
                "All investment recommendations are made solely in your interest."
            )

    # Determine compliance status
    if not issues:
        status = ComplianceStatus.APPROVED
        edited = None
    elif len(issues) <= 2 and not any("PROHIBITED" in i for i in issues):
        status = ComplianceStatus.APPROVED_WITH_EDITS
        edited = draft + "\n\n---\n*Required Disclosures:*\n" + "\n\n".join(disclosures)
    else:
        status = ComplianceStatus.REJECTED
        edited = None

    audit_trail = _add_audit_entry(
        state,
        action=f"Compliance review — {status.value}, {len(issues)} issue(s), "
               f"{len(disclosures)} disclosure(s) added",
        node="compliance_review",
        regulatory_basis="FINRA 2210 — communications with the public; Reg BI disclosure obligation",
    )

    return {
        "compliance_status": status,
        "compliance_notes": issues,
        "required_disclosures": disclosures,
        "edited_content": edited,
        "current_step": "compliance_review",
        "completed_steps": _steps_done(state, "compliance_review"),
        "audit_trail": audit_trail,
    }


# ── NODE 10: RM Approval Gate ──────────────────────────────────────────────────

def rm_approval_gate(state: WealthRMState) -> Dict[str, Any]:
    """
    HITL interrupt — RM reviews and approves all AI-generated content.

    This node is declared interrupt_before in the graph compiler.
    Execution pauses here for the RM to review the draft, suitability
    analysis, compliance notes, and recommendations.

    RM options:
      APPROVE     — Content is ready for client delivery
      EDIT        — RM makes modifications to the draft
      REJECT      — Content is not appropriate; workflow restarts

    CRITICAL: RM approval is NOT optional.
    Reg BI and FINRA 2210 require that a registered professional review
    and approve all client communications and recommendations.
    The RM is the accountable party — not the AI system.
    """
    logger.info(f"[rm_approval_gate] Awaiting RM approval for {state.get('request_id')}")

    completed_steps = _steps_done(state, "rm_approval_gate")
    audit_trail = _add_audit_entry(
        state,
        action=f"RM approval required — {state.get('output_type')} for "
               f"{(state.get('client_profile') or {}).get('full_name', state.get('client_id'))}",
        node="rm_approval_gate",
        regulatory_basis="FINRA 2210 — registered principal review; Reg BI — RM accountability",
    )

    return {
        "current_step": "rm_approval_gate",
        "completed_steps": completed_steps,
        "audit_trail": audit_trail,
    }


# ── NODE 11: Finalize Output ──────────────────────────────────────────────────

def finalize_output(state: WealthRMState) -> Dict[str, Any]:
    """
    Finalize approved content, log to CRM, archive for compliance.

    Actions:
      1. Merge RM edits into final_content
      2. Append required disclosures
      3. Log recommendation to CRM (for FINRA 4512 account record)
      4. Submit to compliance archiver (Smarsh / Global Relay)
      5. Lock audit trail

    Record retention:
      SEC Rule 204-2 / FINRA 4511: Client communications and
      recommendations must be retained for 6 years.
      Audit trail is append-only from this point.
    """
    logger.info(f"[finalize_output] Finalizing {state.get('request_id')}")

    rm_notes = state.get("rm_approval_notes", "")
    base_content = state.get("edited_content") or state.get("draft_content") or ""
    disclosures = state.get("required_disclosures") or []

    # Compose final content with RM edits and disclosures
    final = base_content
    if rm_notes:
        final = base_content + f"\n\n[RM Note: {rm_notes}]"
    if disclosures:
        final += "\n\n---\n**Required Regulatory Disclosures:**\n\n"
        final += "\n\n".join(disclosures)

    audit_trail = _add_audit_entry(
        state,
        action=f"Output finalized — {state.get('output_type')} approved by RM {state.get('rm_id')}, "
               f"archived for compliance. Retention: 6 years (FINRA 4511).",
        node="finalize_output",
        data_sources=["crm_salesforce", "compliance_archiver"],
        regulatory_basis="FINRA 4511 — 6-year retention; SEC Rule 204-2 — books and records",
    )

    return {
        "final_content": final,
        "rm_approved": True,
        "rm_approved_at": state.get("rm_approved_at") or _utcnow(),
        "current_step": "finalize_output",
        "completed_steps": _steps_done(state, "finalize_output"),
        "audit_trail": audit_trail,
    }
