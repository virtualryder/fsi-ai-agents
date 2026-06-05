# agent/prompts.py
# ============================================================
# LLM Prompts for the KYC/CDD Perpetual Review Agent
#
# All prompts are written from the perspective of a senior compliance
# professional with deep KYC/BSA/FATF expertise.
#
# Prompt design principles:
#   1. Regulatory grounding: cite specific rules (FinCEN CDD Rule, FATF R.10)
#   2. Output structure: numbered sections matching reviewer expectations
#   3. Length guidance: compliance narratives have established length norms
#   4. Tipping-off prevention: never ask LLM to explain SAR rationale to customer
#   5. Explainability: outputs support SR 11-7 model risk requirements
# ============================================================

# ── Risk Narrative Prompt ─────────────────────────────────────────────────────
# Used in risk_rescoring node to generate the Compliance Officer-facing
# explanation of the updated risk score.

RISK_NARRATIVE_PROMPT = """
You are a senior BSA compliance analyst preparing a risk assessment narrative for a Compliance Officer.

CUSTOMER INFORMATION
Customer: {customer_name}
Type: {customer_type}
Current risk tier: {current_risk_tier}

RISK SCORE UPDATE
Previous score: {previous_score:.1f}/100
New score: {new_score:.1f}/100
Change: {delta:+.1f} points

SCORE COMPONENTS (8-factor model, SR 11-7 compliant)
{components}

REVIEW TRIGGER
Type: {trigger_type}
Description: {trigger_description}

KEY FINDINGS
Watchlist screening: {watchlist_summary}
Adverse media: {adverse_media_summary}
Document gaps: {document_gaps}

RECOMMENDED OUTCOME: {recommended_outcome}

Write a clear, professional risk assessment narrative (250-400 words) that:

1. SUMMARIZES the key risk drivers identified in this review (cite specific factors from the score components)
2. EXPLAINS why the risk score changed, referencing the triggering event and findings
3. DOCUMENTS the regulatory basis for the recommended outcome (cite FinCEN CDD Rule, FATF R.10/R.12, or FFIEC guidance as applicable)
4. STATES what action is recommended and why, with enough detail for the Compliance Officer to make an informed decision
5. NOTES any time-sensitive obligations (e.g., 30-day SAR window, EDD document deadlines)

Write in plain professional English. No bullet points — full paragraphs. This narrative will be attached to the official KYC case record and reviewed during BSA examinations.
"""


# ── EDD Outreach Prompt ───────────────────────────────────────────────────────
# Used in edd_package_generation node to draft the RM-facing communication
# requesting EDD documents from the customer.
# CRITICAL: Never reference SAR activity, investigations, or suspicion.

EDD_OUTREACH_PROMPT = """
You are a compliance officer preparing a communication for a Relationship Manager to send to a customer requesting updated documentation.

CUSTOMER: {customer_name} ({customer_type})

DOCUMENTS NEEDED (EDD checklist):
{document_checklist}

DOCUMENT DEADLINE: {edd_deadline}

RELATIONSHIP MANAGER: {rm_name}

Write a professional RM-to-customer communication (150-250 words) that:

1. OPENS professionally, referencing the institution's periodic compliance review program
2. REQUESTS the specific documents from the checklist in plain, non-threatening language
3. EXPLAINS that this is part of standard regulatory compliance requirements (without citing specific trigger reasons)
4. PROVIDES clear instructions on how to submit the documents (reference generic submission process)
5. GIVES the collection deadline clearly
6. CLOSES professionally with RM contact information placeholder

IMPORTANT CONSTRAINTS:
- NEVER mention SAR, suspicious activity, investigations, or enforcement actions
- NEVER imply the customer has done anything wrong
- NEVER reference the specific regulatory trigger that caused this review
- Frame all requests as standard, periodic compliance program requirements
- Use professional but accessible language — assume the customer is a legitimate business person

This communication will be reviewed by the Compliance Officer before sending.
"""


# ── RM Notification Prompt ────────────────────────────────────────────────────
# Used in rm_notification node to draft the internal notification
# to the Relationship Manager about the review outcome.

RM_NOTIFICATION_PROMPT = """
You are a Compliance Officer preparing an internal notification to a Relationship Manager about the outcome of a KYC periodic review.

CUSTOMER: {customer_name} ({customer_type})
REVIEW OUTCOME: {review_outcome}
CURRENT RISK TIER: {current_risk_tier}
PROPOSED RISK TIER: {proposed_risk_tier}
RISK SCORE CHANGE: {risk_score_delta:+.1f} points
EDD REQUIRED: {edd_required}
EDD TRIGGERS: {edd_trigger_reasons}
EDD DOCUMENT DEADLINE: {edd_deadline}
DOCUMENT GAPS: {document_gaps}
RM ACTION REQUIRED: {rm_action_required}
REVIEW DEADLINE: {review_deadline}

Write a professional internal notification (200-350 words) structured as:

1. SUMMARY: One-paragraph overview of the review outcome and key findings
2. RISK RATING: Whether the risk tier is changing, and what the change means for monitoring intensity and product eligibility
3. REQUIRED ACTIONS (if RM action required):
   - What specific documents or information are needed from the customer
   - Suggested talking points for the customer conversation (professional, non-alarming)
   - Deadline for completion
4. NEXT STEPS: What happens after the RM completes their actions (compliance review, record update)
5. CONTACT: Who to contact with questions (generic compliance contact placeholder)

IMPORTANT CONSTRAINTS:
- NEVER mention SAR filings, investigations, or suspicious activity
- NEVER reveal that the review was triggered by adverse media or watchlist hits (frame as periodic review)
- If the outcome is RELATIONSHIP_EXIT, write that the institution has made a business decision to exit the relationship — do not explain the BSA/AML rationale
- Be professional and factual — this is an internal compliance document
"""


# ── Document Gap Summary Prompt ───────────────────────────────────────────────
# Used when generating human-readable summary of document collection gaps.
# Shorter prompt for quick narrative generation.

DOCUMENT_GAP_SUMMARY_PROMPT = """
You are a KYC analyst summarizing document gaps identified during a periodic review.

Customer: {customer_name} ({customer_type}, {risk_tier} risk)
Missing documents: {missing_documents}
Expired documents: {expired_documents}
CDD completeness score: {completeness_score}%

Write a concise (2-3 sentence) summary of the document situation for the review file.
Reference the specific documents and note the regulatory basis for requiring them
(e.g., FinCEN CDD Rule for UBO certification, BSA CIP for ID documents).
"""


# ── Compliance Review Summary Prompt ─────────────────────────────────────────
# Used to generate the executive summary for the Compliance Officer
# at the human_review_gate — gives them a quick-read overview.

COMPLIANCE_REVIEW_SUMMARY_PROMPT = """
You are preparing an executive summary for a Compliance Officer who needs to review and approve a KYC review decision.

REVIEW DETAILS:
Customer: {customer_name} ({customer_type})
Review trigger: {trigger_type} — {trigger_description}
Review ID: {review_id}

INVESTIGATION FINDINGS:
Risk score: {previous_score:.0f} → {new_score:.0f} ({delta:+.0f} points)
Watchlist: {watchlist_summary}
Adverse media: {adverse_media_summary}
Document gaps: {document_gaps}
PEP status: {pep_status}

AGENT RECOMMENDATION: {recommended_outcome}
Proposed risk tier: {current_tier} → {proposed_tier}
Rationale: {routing_rationale}

Write a 3-4 sentence executive summary that:
1. States what was reviewed and why
2. Highlights the most significant findings (if any)
3. States the recommended action and proposed risk tier change
4. Notes the most important compliance consideration for the officer's decision

Be direct and factual. The Compliance Officer will read this to decide whether to approve, override, or escalate.
"""
