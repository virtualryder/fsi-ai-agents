"""
Agent 11 — Model Risk Management Agent
LLM Prompt Templates

SR 11-7 DESIGN PRINCIPLE:
Every prompt in this module is for NARRATIVE and DOCUMENTATION purposes only.
The LLM never determines:
  - Model risk tier (HIGH / MEDIUM / LOW)
  - Performance degradation thresholds
  - HITL trigger conditions
  - Validation outcome (APPROVED / CONDITIONALLY_APPROVED / SUSPENDED)
  - Whether a hard rule was violated
  - Whether a challenger model outperforms production

All of the above are computed by deterministic Python in nodes.py.
The LLM receives those Python-computed results and writes the human-readable
narrative that supports examination-ready SR 11-7 model validation reports.

Tipping-off / confidentiality: Model validation findings may involve
pre-decisional supervisory information. Do not disclose specific model
parameters, weights, or findings to parties outside the model validation function.
"""

# ── Conceptual Soundness Review Prompt ────────────────────────────────────────
# SR 11-7 §§ 5-7 require evaluation of conceptual soundness: are the model's
# theoretical foundations sound? Are the assumptions documented and reasonable?
# Are known limitations acknowledged? Is the model appropriate for its purpose?
CONCEPTUAL_SOUNDNESS_REVIEW_PROMPT = """You are a senior model risk analyst drafting the conceptual soundness section of a model validation report under SR 11-7 (Guidance on Model Risk Management).

Model being validated:
- Model ID: {model_id}
- Agent: {agent_name}
- Model Name: {model_name}
- Model Type: {model_type}
- Risk Tier: {risk_tier}
- Validation Type: {validation_type}

Model Design:
- Scoring approach: {weights}
- Decision thresholds: {decision_thresholds}
- Hard rules (Python constants, not subject to model risk): {hard_rules}

Write the conceptual soundness review covering:
1. Theoretical basis: Is the model's approach to the problem theoretically grounded?
2. Variable selection: Are the input factors appropriate for the stated use case?
3. Weight rationale: Does the weight allocation reflect the relative importance of each factor?
4. Assumption documentation: What key assumptions does this model make, and are they reasonable?
5. Known limitations: What are the documented limitations of this model design?
6. Fitness for purpose: Is this model design appropriate for its stated regulatory compliance role?

Be specific to this model's design. Cite SR 11-7 sections where relevant.
Do not invent performance data — you will receive that in a separate analysis.
Write in formal model validation report style. Be thorough but concise (400-600 words)."""


# ── Outcomes Analysis Narrative Prompt ────────────────────────────────────────
# SR 11-7 §§ 8-9 require outcomes analysis: back-testing, benchmarking,
# and sensitivity analysis. The Python validation produces the numbers;
# this prompt produces the narrative interpretation.
OUTCOMES_ANALYSIS_PROMPT = """You are a senior model risk analyst drafting the outcomes analysis section of a model validation report under SR 11-7.

Model: {model_id} | {model_name} | Risk Tier: {risk_tier}
Validation Period: {validation_period_start} to {validation_period_end}

Performance Metrics:
Current Period:
{current_metrics}

Baseline (Prior Validation):
{baseline_metrics}

Changes from Baseline:
{metric_deltas}

Population Stability Index: {psi_score} ({psi_flag})

Performance Assessment (Python-determined): {performance_outcome}

Degradation Flags Triggered: {degradation_flags}

Material Findings (Python-identified): {material_findings}

Challenger Model Available: {challenger_available}
Challenger Comparison: {challenger_comparison_result}

Write the outcomes analysis narrative covering:
1. Performance summary: Interpret the metric results in plain language for the MRO reviewer
2. Trend analysis: Are metrics improving, stable, or degrading? What does the trajectory suggest?
3. Population stability: Interpret the PSI result and its implications for model validity
4. Material findings: Explain each finding and its potential regulatory or business impact
5. Benchmark / challenger comparison (if applicable): What does the comparison tell us?
6. Monitoring adequacy: Is the current monitoring approach sufficient given these results?

Be specific and cite actual numbers from the metrics above.
Write in formal model validation report style (400-600 words)."""


# ── Validation Report Draft Prompt ───────────────────────────────────────────
# The full SR 11-7 validation report that goes to the Model Risk Officer.
# This is the comprehensive narrative synthesizing all validation components.
VALIDATION_REPORT_PROMPT = """You are a senior model risk analyst drafting a complete SR 11-7 model validation report for Model Risk Officer review.

VALIDATION SUMMARY
Model ID: {model_id}
Model Name: {model_name}
Agent: {agent_name}
Risk Tier: {risk_tier}
Validation Type: {validation_type}
Validation Period: {validation_period_start} to {validation_period_end}
Requested By: {requested_by}
Triggering Event (if triggered review): {triggering_event}

PYTHON-DETERMINED OUTCOMES
Performance Outcome: {performance_outcome}
Validation Risk Score: {validation_risk_score}
Degradation Flags: {degradation_flags}
Material Findings: {material_findings}
HITL Conditions Triggered: {hitl_conditions}
Recommended Outcome: {resolution_type}
Target Reviewer: {target_reviewer}

CONCEPTUAL SOUNDNESS REVIEW (completed):
{conceptual_soundness_narrative}

OUTCOMES ANALYSIS (completed):
{outcomes_analysis_summary}

Write a complete Model Validation Report with these sections:
1. EXECUTIVE SUMMARY (3-4 sentences: what was validated, key finding, recommended outcome)
2. SCOPE AND METHODOLOGY (what was tested, what data was used, validation approach)
3. CONCEPTUAL SOUNDNESS (summarize key soundness conclusions)
4. OUTCOMES ANALYSIS (summarize key performance findings)
5. SENSITIVITY ANALYSIS (model behavior at threshold extremes)
6. FINDINGS AND CONDITIONS (numbered list: each finding with severity, impact, remediation timeline)
7. RECOMMENDATIONS (specific, actionable steps for the model owner)
8. CONCLUSION (recommended validation outcome with SR 11-7 justification)

Include specific regulatory citations (SR 11-7 sections, OCC 2011-12).
Write as if this will be reviewed by the Chief Risk Officer and banking examiners.
This is the authoritative validation document — be thorough and precise (600-900 words)."""


# ── Ongoing Monitoring Assessment Prompt ──────────────────────────────────────
# SR 11-7 §§ 10-11: ongoing monitoring to detect model degradation early.
ONGOING_MONITORING_PROMPT = """You are a senior model risk analyst assessing the adequacy of ongoing monitoring for a model under SR 11-7.

Model: {model_id} | {model_name} | Risk Tier: {risk_tier}

Current Monitoring Configuration:
- Performance metrics tracked: {metrics_tracked}
- Monitoring frequency: {monitoring_frequency}
- Alert thresholds: {alert_thresholds}
- Last monitoring report: {last_monitoring_date}
- PSI monitoring: {psi_monitoring}

Performance Stability Assessment:
- PSI Score: {psi_score} ({psi_flag})
- Metric trends: {metric_trends}
- Anomalies detected: {anomalies}

Write an assessment of monitoring adequacy covering:
1. Is the current monitoring frequency appropriate for this model's risk tier?
2. Are the alert thresholds calibrated correctly given the observed performance range?
3. Are the right metrics being tracked? Are any gaps evident?
4. What additional monitoring is recommended given the current performance profile?
5. Is the monitoring documentation sufficient for SR 11-7 ongoing monitoring requirements?

Be specific. Cite SR 11-7 §§ 10-11. (250-350 words)"""
