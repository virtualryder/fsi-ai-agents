# agent/state.py
# ============================================================
# WealthRMState — Complete state for an RM Copilot workflow
#
# Regulatory context:
#   - Reg BI (17 CFR 240.15l-1 / Exchange Act Rule 15l-1):
#       Broker-dealer best interest obligation — recommendations must be
#       in the retail customer's best interest, considering cost, risk,
#       and client objectives. Care, Conflict of Interest, Disclosure,
#       and Compliance obligations.
#   - SEC Investment Advisers Act (15 U.S.C. § 80b-1):
#       RIA fiduciary duty — must act in client's best interest and
#       disclose all material conflicts of interest.
#   - FINRA Rule 2111 (Suitability):
#       Reasonable basis, customer-specific, and quantitative suitability.
#       Each recommendation must be suitable based on customer profile.
#   - FINRA Rule 4512: Customer account information maintenance.
#   - ERISA (29 U.S.C. § 1001): Fiduciary standard for retirement accounts.
#       Prohibited transactions, exclusive benefit rule, prudent investor.
#   - SEC Reg S-P (17 CFR Part 248): Client financial data privacy.
#   - FINRA Rule 2210: Communications standards — fair and balanced,
#       no misleading statements, clear and prominent disclosures.
#
# Human-in-the-loop:
#   rm_approval_gate pauses for RM review of all AI-generated content
#   before any client-facing communication is finalized.
#   RM always has final accountability — AI is copilot, not pilot.
# ============================================================

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class RequestType(str, Enum):
    """
    The type of RM workflow request being processed.

    MEETING_PREP:         Prepare briefing for upcoming client meeting.
                          Output: client briefing with portfolio snapshot,
                          talking points, and open items.
    REBALANCING_PROPOSAL: Portfolio has drifted from IPS targets.
                          Output: rebalancing recommendation with
                          Reg BI suitability analysis.
    INVESTMENT_PROPOSAL:  RM wants to present a new investment idea.
                          Output: investment proposal with IPS alignment
                          and suitability rationale.
    PORTFOLIO_REVIEW:     Annual/quarterly review preparation.
                          Output: performance attribution, benchmark
                          comparison, forward-looking commentary.
    CLIENT_COMMUNICATION: Draft a letter or email to the client.
                          Output: compliant communication draft ready
                          for RM review and send.
    ALERT_RESPONSE:       Market event or life event trigger.
                          Output: briefing on the alert and suggested
                          RM talking points / action.
    """
    MEETING_PREP = "MEETING_PREP"
    REBALANCING_PROPOSAL = "REBALANCING_PROPOSAL"
    INVESTMENT_PROPOSAL = "INVESTMENT_PROPOSAL"
    PORTFOLIO_REVIEW = "PORTFOLIO_REVIEW"
    CLIENT_COMMUNICATION = "CLIENT_COMMUNICATION"
    ALERT_RESPONSE = "ALERT_RESPONSE"


class RiskTolerance(str, Enum):
    """
    Client's stated and assessed risk tolerance.
    Must match Investment Policy Statement (IPS).
    Changes require written update and supervisory approval.
    """
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE_CONSERVATIVE = "MODERATE_CONSERVATIVE"
    MODERATE = "MODERATE"
    MODERATE_AGGRESSIVE = "MODERATE_AGGRESSIVE"
    AGGRESSIVE = "AGGRESSIVE"


class AccountType(str, Enum):
    """
    Account type drives regulatory treatment.
    ERISA accounts: fiduciary standard, prohibited transactions.
    Taxable accounts: tax-lot optimization, wash sale rules.
    """
    TAXABLE = "TAXABLE"
    TRADITIONAL_IRA = "TRADITIONAL_IRA"
    ROTH_IRA = "ROTH_IRA"
    SEP_IRA = "SEP_IRA"
    SOLO_401K = "SOLO_401K"
    EMPLOYER_401K = "EMPLOYER_401K"
    TRUST = "TRUST"
    CUSTODIAL = "CUSTODIAL"
    JOINT = "JOINT"


class SuitabilityStatus(str, Enum):
    """
    Reg BI / FINRA 2111 suitability determination.

    SUITABLE:          Recommendation passes all suitability checks.
    SUITABLE_WITH_NOTE: Suitable but requires additional disclosure
                        (e.g., higher-cost share class, conflict exists).
    UNSUITABLE:        Recommendation fails suitability — must not proceed.
    NEEDS_REVIEW:      Insufficient information to determine suitability.
                        RM must gather additional client information.
    """
    SUITABLE = "SUITABLE"
    SUITABLE_WITH_NOTE = "SUITABLE_WITH_NOTE"
    UNSUITABLE = "UNSUITABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ComplianceStatus(str, Enum):
    """
    FINRA 2210 communication compliance status.
    AI-generated content must pass compliance check before RM review.
    """
    APPROVED = "APPROVED"
    APPROVED_WITH_EDITS = "APPROVED_WITH_EDITS"
    REJECTED = "REJECTED"
    PENDING_REVIEW = "PENDING_REVIEW"


class WealthRMState(TypedDict, total=False):
    """
    Complete state for a single Wealth & RM Copilot workflow run.

    Populated incrementally as the graph progresses.
    total=False: all fields optional at initialization.
    """

    # ── Request / Trigger ─────────────────────────────────────────────────────

    request_id: str
    # Unique workflow run ID. Format: "RM-YYYYMMDD-XXXXXXXXXX"

    rm_id: str
    # Relationship Manager user ID — for audit and accountability

    client_id: str
    # Client identifier — links to CRM and account records

    request_type: RequestType
    # The type of RM workflow being executed

    request_context: Optional[str]
    # Free-form context from the RM: "Q3 review", "Tech concentration concern",
    # "Client called about inflation", "Upcoming estate meeting"

    meeting_date: Optional[str]
    # For MEETING_PREP: ISO 8601 date of scheduled meeting

    investment_idea: Optional[str]
    # For INVESTMENT_PROPOSAL: the specific investment being proposed
    # (fund name/ticker, asset class, strategy description)

    alert_description: Optional[str]
    # For ALERT_RESPONSE: description of the triggering event

    # ── Client Profile ────────────────────────────────────────────────────────
    # Sourced from CRM / account opening documents (FINRA 4512).
    # Changes require written client authorization and supervisory approval.

    client_profile: Optional[Dict[str, Any]]
    # Full client profile:
    #   - full_name: str
    #   - age: int
    #   - marital_status: str
    #   - dependents: int
    #   - employment_status: str
    #   - annual_income: float
    #   - net_worth: float
    #   - total_aum: float (assets under management with this firm)
    #   - primary_goals: list[str] (retirement, education, estate, income)
    #   - time_horizon_years: int
    #   - risk_tolerance: RiskTolerance
    #   - tax_bracket: str (federal marginal rate)
    #   - state_of_domicile: str
    #   - is_retirement_account: bool (ERISA flag)
    #   - liquidity_needs: str (LOW/MEDIUM/HIGH)
    #   - esg_preference: bool
    #   - restricted_securities: list[str] (employer stock, legacy positions)
    #   - client_since_date: str
    #   - last_review_date: str
    #   - next_rmd_date: Optional[str] (Required Minimum Distribution)
    #   - beneficiary_review_date: Optional[str]

    ips_summary: Optional[Dict[str, Any]]
    # Investment Policy Statement summary:
    #   - target_allocations: dict (asset class → target %)
    #   - rebalancing_bands: dict (asset class → tolerance band %)
    #   - return_objective: str
    #   - income_requirement: float (annual distribution target)
    #   - prohibited_securities: list[str]
    #   - esg_screens: list[str]
    #   - benchmark: str (e.g., "60/40 Blended Benchmark")
    #   - last_updated: str
    #   - ips_version: str

    # ── Portfolio Data ────────────────────────────────────────────────────────
    # Sourced from portfolio management system / custodian.
    # All values as of last business day close.

    portfolio_snapshot: Optional[Dict[str, Any]]
    # Current portfolio:
    #   - total_market_value: float
    #   - holdings: list[dict] (symbol, name, asset_class, shares, price, value, weight)
    #   - current_allocations: dict (asset class → current %)
    #   - ytd_return: float
    #   - one_year_return: float
    #   - three_year_return: float
    #   - inception_return: float
    #   - benchmark_ytd: float
    #   - benchmark_one_year: float
    #   - alpha: float (risk-adjusted excess return)
    #   - sharpe_ratio: float
    #   - unrealized_gains: float
    #   - unrealized_losses: float
    #   - last_rebalanced_date: str
    #   - as_of_date: str

    allocation_drift: Optional[Dict[str, Any]]
    # Current vs. IPS target allocation analysis:
    #   Per asset class: {target_pct, current_pct, drift_pct, outside_band: bool}
    #   - max_drift: float (largest single-asset-class deviation)
    #   - requires_rebalancing: bool
    #   - drift_summary: str (plain language summary)

    concentrated_positions: Optional[List[Dict[str, Any]]]
    # Positions > 10% of portfolio — concentration risk flag
    #   Each: {symbol, name, weight_pct, unrealized_gain, tax_impact}
    #   Concentration risk is both suitability and Reg BI concern

    # ── Market Intelligence ────────────────────────────────────────────────────
    # Recent news and macro context relevant to this client's portfolio.

    market_context: Optional[Dict[str, Any]]
    # Market intelligence summary:
    #   - relevant_news: list[dict] (headline, source, date, impact_summary)
    #   - macro_themes: list[str] (e.g., "Fed policy pivot", "Yield curve inversion")
    #   - sector_alerts: list[dict] (sector, alert_type, description)
    #   - portfolio_specific_news: list[dict] (for client's actual holdings)
    #   - market_snapshot: dict (SPX/BND returns, rates, VIX)

    life_events: Optional[List[Dict[str, Any]]]
    # Detected or RM-noted life events that require advisory action:
    #   - type: str (RETIREMENT, INHERITANCE, DIVORCE, JOB_CHANGE, DEATH_OF_SPOUSE,
    #                COLLEGE_FUNDING, RMD_START, ESTATE_PLANNING)
    #   - detected_date: str
    #   - action_required: str

    # ── Suitability & Reg BI ──────────────────────────────────────────────────
    # FINRA 2111 and Reg BI suitability analysis for any recommendations.
    # Must be documented before any recommendation is made to client.

    suitability_analysis: Optional[Dict[str, Any]]
    # Suitability check results:
    #   - overall_status: SuitabilityStatus
    #   - checks_performed: list[dict] (check_name, passed, note)
    #   - conflict_of_interest_disclosures: list[str]
    #   - cost_analysis: dict (product costs vs. alternatives considered)
    #   - reg_bi_care_obligation: str (documentation for Reg BI care)
    #   - reg_bi_conflict_obligation: str (conflict disclosure documentation)

    suitability_status: Optional[SuitabilityStatus]
    # Summary suitability determination

    reg_bi_rationale: Optional[str]
    # Plain-language Reg BI "best interest" rationale for the recommendation.
    # Required documentation for each recommendation under Reg BI.

    # ── Recommendations ───────────────────────────────────────────────────────

    recommendations: Optional[List[Dict[str, Any]]]
    # Investment recommendations generated by the agent:
    #   Each: {
    #     "action": BUY/SELL/HOLD/REBALANCE,
    #     "security": str,
    #     "asset_class": str,
    #     "rationale": str,
    #     "amount_usd": float,
    #     "ips_alignment": str,
    #     "risk_level": str,
    #     "estimated_cost": float,
    #     "alternatives_considered": list[str],
    #     "suitability_note": str,
    #   }

    rebalancing_trades: Optional[List[Dict[str, Any]]]
    # Specific rebalancing trades:
    #   Each: {symbol, action, shares, estimated_value, tax_impact_note}

    # ── Generated Content ──────────────────────────────────────────────────────

    output_type: Optional[str]
    # MEETING_BRIEFING | INVESTMENT_PROPOSAL | PORTFOLIO_REVIEW |
    # CLIENT_LETTER | ALERT_BRIEFING

    draft_content: Optional[str]
    # AI-generated draft of the primary output document.
    # Subject to compliance review and RM approval before any client use.

    talking_points: Optional[List[str]]
    # Key talking points for the RM's client conversation.
    # Actionable, specific, and IPS-grounded.

    open_items: Optional[List[str]]
    # Outstanding action items requiring RM or client follow-up:
    # IPS refresh, missing documents, pending elections, beneficiary updates

    # ── Compliance Review ─────────────────────────────────────────────────────
    # FINRA 2210: All client communications must be fair, balanced, and
    # not misleading. AI-generated content requires compliance check.

    compliance_status: Optional[ComplianceStatus]

    compliance_notes: Optional[List[str]]
    # Issues flagged by compliance check:
    #   - Missing disclosures
    #   - Performance claims without required disclaimer
    #   - Forward-looking statements without caveats
    #   - Missing Reg BI best interest language
    #   - Prohibited language (guarantees, cherry-picked returns)

    edited_content: Optional[str]
    # Compliance-edited version of draft_content (if edits were required)

    required_disclosures: Optional[List[str]]
    # Mandatory regulatory disclosures that must accompany the output:
    #   - Reg BI disclosure (Form CRS reference)
    #   - Past performance disclaimer
    #   - Risk disclosure
    #   - Conflict of interest disclosure (if applicable)
    #   - ERISA fiduciary disclosure (for retirement accounts)

    # ── RM Approval ───────────────────────────────────────────────────────────

    rm_approved: Optional[bool]
    # True when RM has reviewed and approved the final output

    rm_approval_notes: Optional[str]
    # RM's notes or modifications during approval review

    rm_approved_at: Optional[str]
    # ISO 8601 timestamp of RM approval

    final_content: Optional[str]
    # Final approved content — ready for client delivery

    # ── Workflow Infrastructure ────────────────────────────────────────────────

    current_step: Optional[str]

    completed_steps: Optional[List[str]]

    errors: Optional[List[Dict[str, Any]]]

    # ── Audit Trail ────────────────────────────────────────────────────────────
    # SEC Advisers Act Rule 204-2: Books and records.
    # All client communications and recommendations must be retained 5 years.
    # FINRA 4511: 6-year retention for most records.

    audit_trail: Optional[List[Dict[str, Any]]]
    # Each entry: {
    #   "timestamp": ISO 8601,
    #   "actor": "wealth_rm_copilot" | rm_id,
    #   "action": description,
    #   "node": graph node name,
    #   "data_sources": list,
    #   "ai_model_used": str or None,
    #   "regulatory_basis": str,
    # }
