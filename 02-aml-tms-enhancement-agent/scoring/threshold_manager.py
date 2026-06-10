"""
Threshold Manager — governs when alerts are suppressed, downgraded, or escalated.

Thresholds are configurable via environment variables (SUPPRESS_THRESHOLD,
DOWNGRADE_THRESHOLD, ESCALATE_THRESHOLD) and adjustable per alert type
and customer risk tier.

Regulatory basis: SR 11-7 requires documented, governed thresholds with
periodic back-testing. Any threshold change must be logged and reviewed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Thresholds:
    suppress: float   # FP probability >= this → SUPPRESS
    downgrade: float  # FP probability >= this (but < suppress) → DOWNGRADE
    escalate: float   # FP probability <= this → ESCALATE
    # Everything between escalate and downgrade → PASS_THROUGH


# ── Default thresholds (environment-configurable) ────────────────────────────
_DEFAULT_SUPPRESS = float(os.getenv("SUPPRESS_THRESHOLD", "85"))
_DEFAULT_DOWNGRADE = float(os.getenv("DOWNGRADE_THRESHOLD", "60"))
_DEFAULT_ESCALATE = float(os.getenv("ESCALATE_THRESHOLD", "15"))

DEFAULT_THRESHOLDS = Thresholds(
    suppress=_DEFAULT_SUPPRESS,
    downgrade=_DEFAULT_DOWNGRADE,
    escalate=_DEFAULT_ESCALATE,
)

# ── Alert-type overrides ─────────────────────────────────────────────────────
# Certain typologies are high-risk by nature and require tighter thresholds.
# These override defaults when the alert_type matches.
ALERT_TYPE_OVERRIDES: dict[str, Thresholds] = {
    # Layering / rapid movement: genuinely suspicious when it occurs
    "RAPID_MOVEMENT": Thresholds(suppress=92, downgrade=72, escalate=10),
    "LAYERING": Thresholds(suppress=92, downgrade=72, escalate=10),
    # PEP-related: never suppress, always at least pass-through
    "PEP_RELATED": Thresholds(suppress=999, downgrade=999, escalate=25),
    # OFAC / sanctions proximity: never suppress
    "OFAC_PROXIMITY": Thresholds(suppress=999, downgrade=999, escalate=5),
    # Round-dollar: very high FP rate, can suppress aggressively
    "ROUND_DOLLAR": Thresholds(suppress=80, downgrade=55, escalate=15),
    # Card velocity: extremely high FP rate (travel, legitimate merchants)
    "VELOCITY": Thresholds(suppress=80, downgrade=55, escalate=20),
}

# ── Risk-tier adjustments (applied on top of type-level thresholds) ──────────
# Higher risk customers → harder to suppress (need more confidence).
# CONTROL: adjustments are POSITIVE points added to the FP-probability
# required before an alert may be suppressed or downgraded. A negative sign
# here would invert the control and make high-risk customers' alerts the
# EASIEST to auto-suppress — guarded by
# tests/test_scoring.py::TestThresholdManager::test_very_high_risk_harder_to_suppress.
RISK_TIER_ADJUSTMENTS: dict[str, float] = {
    "LOW": 0.0,         # No adjustment
    "MEDIUM": 2.0,      # Suppress threshold 2 pts harder
    "HIGH": 5.0,        # 5 pts harder
    "VERY_HIGH": 12.0,  # 12 pts harder — nearly impossible to auto-suppress
}


class ThresholdManager:
    """
    Resolves effective thresholds for a given alert context.

    Usage:
        mgr = ThresholdManager()
        thresholds = mgr.get_thresholds("VELOCITY", "MEDIUM")
        decision = mgr.route(fp_probability=88, alert_type="VELOCITY", risk_tier="MEDIUM")
    """

    def get_thresholds(self, alert_type: str, risk_tier: str) -> Thresholds:
        """
        Return effective thresholds for this alert type + risk tier combination.

        Priority: alert_type override → risk_tier adjustment → defaults.
        """
        base = ALERT_TYPE_OVERRIDES.get(alert_type, DEFAULT_THRESHOLDS)
        adjustment = RISK_TIER_ADJUSTMENTS.get(risk_tier, 0.0)
        return Thresholds(
            suppress=base.suppress + adjustment,
            downgrade=base.downgrade + adjustment,
            escalate=base.escalate,          # escalate threshold is not risk-adjusted
        )

    def route(
        self,
        fp_probability: float,
        alert_type: str,
        risk_tier: str,
        regulatory_override: bool = False,
        regulatory_override_reason: str = "",
    ) -> tuple[Literal["SUPPRESS", "DOWNGRADE", "PASS_THROUGH", "ESCALATE"], Thresholds]:
        """
        Map a composite FP probability to a routing decision.

        Returns (decision, effective_thresholds) so the caller can log
        the thresholds used (SR 11-7 audit requirement).

        Regulatory overrides always win — even a 99% FP probability alert
        will be escalated if the override flag is set.
        """
        thresholds = self.get_thresholds(alert_type, risk_tier)

        if regulatory_override:
            return "ESCALATE", thresholds

        if fp_probability >= thresholds.suppress:
            return "SUPPRESS", thresholds
        elif fp_probability >= thresholds.downgrade:
            return "DOWNGRADE", thresholds
        elif fp_probability <= thresholds.escalate:
            return "ESCALATE", thresholds
        else:
            return "PASS_THROUGH", thresholds

    def explain_thresholds(self, alert_type: str, risk_tier: str) -> dict:
        """Return a human-readable explanation of the effective thresholds."""
        t = self.get_thresholds(alert_type, risk_tier)
        return {
            "alert_type": alert_type,
            "risk_tier": risk_tier,
            "effective_suppress_threshold": t.suppress,
            "effective_downgrade_threshold": t.downgrade,
            "effective_escalate_threshold": t.escalate,
            "base_override_applied": alert_type in ALERT_TYPE_OVERRIDES,
            "risk_tier_adjustment": RISK_TIER_ADJUSTMENTS.get(risk_tier, 0.0),
        }
