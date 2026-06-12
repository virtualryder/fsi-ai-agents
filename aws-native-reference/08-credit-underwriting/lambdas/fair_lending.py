"""Node 3 — deterministic fair-lending flags (illustrative)."""
from . import _shared  # noqa: F401


def handler(event, context=None):
    app = event.get("application", {})
    flags = []
    # Illustrative: a flagged census tract adds a REVIEW flag (never a score change).
    if app.get("census_tract_flagged"):
        flags.append("flagged_census_tract_review")
    if app.get("air_below_threshold"):
        flags.append("portfolio_AIR_below_0.80")
    return {**event, "fair_lending_flags": flags}
