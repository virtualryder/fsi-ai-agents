# tools/case_management.py
# ============================================================
# Case Management System Integration
#
# WHY AN INVESTIGATOR NEEDS THIS:
#   Every investigation must be formally tracked in a case management system.
#   The case record is the official regulatory record of the investigation —
#   it links the alert, the investigation findings, the disposition, and all
#   human actions in one auditable record. Without case management, there is
#   no way to ensure investigations are completed within regulatory timeframes,
#   no way to track analyst workloads, and no way to demonstrate to examiners
#   that every alert was investigated and resolved.
#
# REGULATORY REQUIREMENTS SERVED:
#   - BSA: All investigations must be documented and retained 5 years
#   - OCC BSA/AML Examination Handbook: "Banks should have adequate controls
#     to ensure that all alerts are reviewed in a timely manner"
#   - FinCEN SAR: Filing within 30 days requires tracking the detection date
#   - FATF: Adequate resources and systems for AML program effectiveness
#   - SR 11-7: For AI-assisted decisions, human review must be documented
#
# REAL VENDOR SYSTEMS THAT PROVIDE THIS:
#   Enterprise Case Management:
#   - NICE Actimize Case Manager: Industry standard, tight TMS integration
#   - Hyland OnBase: Document management + case management, used by large banks
#   - Verint Financial Compliance: Strong for surveillance + AML
#   - Fiserv AML Manager: Community/regional bank focused
#
#   IT Service Management Adapted for AML:
#   - ServiceNow (GRC module): Enterprise workflow platform
#   - Archer GRC (RSA): Risk management platform with case management
#   - LogicGate: Risk workflow automation
#
#   Custom/In-House Systems:
#   - Many Tier 1 banks build proprietary case management
#   - Often built on Oracle, Salesforce, or custom databases
#   - Typical tech: PostgreSQL/Oracle backend, React/Angular frontend
# ============================================================

import logging
import json
import random
import string
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Simulated in-memory case database for demonstration
# In production: replace with PostgreSQL or case management API
_CASE_DATABASE: Dict[str, Dict[str, Any]] = {}

# ── INTEGRATION POINT ────────────────────────────────────────────────────────
# PRODUCTION: Replace in-memory dict with real case management API.
#
# Actimize Case Manager API example:
#   import requests
#   headers = {
#       "X-API-Key": os.getenv("ACTIMIZE_API_KEY"),
#       "Content-Type": "application/json",
#   }
#   base_url = os.getenv("ACTIMIZE_API_URL")
#
#   # Create case:
#   response = requests.post(
#       f"{base_url}/cases",
#       headers=headers,
#       json={
#           "alertId": alert_id,
#           "customerId": customer_id,
#           "priority": "HIGH",
#           "assignedTo": investigator_id,
#           "sourceSystem": "AI_INVESTIGATION_AGENT",
#       }
#   )
#   return response.json()["caseId"]
#
# ServiceNow (GRC) example:
#   from pysnow import Client
#   client = Client(instance=os.getenv("SNOW_INSTANCE"), user=user, password=password)
#   record = client.resource(api_path="/table/u_aml_cases")
#   response = record.create(payload={
#       "u_alert_id": alert_id,
#       "u_customer_id": customer_id,
#       "u_investigator": investigator_id,
#       "u_status": "open",
#   })
#   return response["sys_id"]  # ServiceNow case ID
# ─────────────────────────────────────────────────────────────────────────────


def _generate_case_id() -> str:
    """Generate a realistic case ID in the format CASE-YYYY-NNNNN."""
    year = datetime.utcnow().year
    sequence = random.randint(10000, 99999)
    return f"CASE-{year}-{sequence}"


def create_case(
    alert_id: str,
    customer_id: str,
    investigator_id: str,
    priority: str = "HIGH",
) -> str:
    """
    Create a new investigation case in the case management system.

    This is called at the end of every investigation — whether the outcome
    is SAR filing, escalation, or case closure. The case record is the
    formal record of the investigation and is retained for 5 years per BSA.

    The case record links:
    - The originating TMS alert (starting point)
    - The customer record (from core banking/KYC)
    - The investigation findings (transaction analysis, watchlist results, etc.)
    - The human investigator who reviewed and made the final decision
    - The disposition (SAR filed, escalated, or closed with rationale)

    Args:
        alert_id: The TMS alert ID that triggered the investigation
        customer_id: The customer under investigation
        investigator_id: The licensed BSA officer/analyst assigned
        priority: Case priority (HIGH/MEDIUM/LOW) — drives SLA timelines

    Returns:
        Case ID string for the newly created case

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace this function with your case management API call.
    # Typical data to capture at case creation:
    # - alert_id, customer_id, investigator_id (as above)
    # - creation_timestamp (auto-set)
    # - sar_deadline (30 or 60 days from now)
    # - priority (HIGH/MEDIUM/LOW)
    # - source_system ("AI_INVESTIGATION_AGENT" for traceability)
    # - initial_findings_json (link to state data)
    # ──────────────────────────────────────────────────────────────────────────
    """
    case_id = _generate_case_id()
    detection_date = datetime.utcnow()

    case_record = {
        "case_id": case_id,
        "alert_id": alert_id,
        "customer_id": customer_id,
        "investigator_id": investigator_id,
        "priority": priority,
        "status": "OPEN",
        "created_at": detection_date.isoformat() + "Z",
        "updated_at": detection_date.isoformat() + "Z",
        "sar_filing_deadline": (detection_date + timedelta(days=30)).strftime("%Y-%m-%d"),
        "bsa_retention_expiry": (detection_date + timedelta(days=1825)).strftime("%Y-%m-%d"),
        "source_system": "AI_INVESTIGATION_AGENT",
        "ai_model_version": "gpt-4o",
        "human_review_required": True,
        "disposition": None,
        "sar_filed": False,
        "sar_id": None,
        "notes": [],
        "timeline": [
            {
                "timestamp": detection_date.isoformat() + "Z",
                "actor": "AI_AGENT",
                "action": f"Case created from alert {alert_id} by AI Investigation Agent",
                "system": "AI_INVESTIGATION_AGENT",
            }
        ],
    }

    # Store in mock database
    _CASE_DATABASE[case_id] = case_record

    logger.info(f"[case_management] Case {case_id} created for alert {alert_id}, customer {customer_id}")
    return case_id


def update_case_status(
    case_id: str,
    status: str,
    notes: str = "",
    actor: str = "AI_AGENT",
) -> Dict[str, Any]:
    """
    Update the status of an existing case with new findings or disposition.

    Status values and their regulatory significance:
    - OPEN: Investigation in progress — SLA clock is running
    - IN_REVIEW: Assigned to an investigator, actively being worked
    - PENDING_HUMAN_REVIEW: AI investigation complete, awaiting BSA Officer review
    - ESCALATED: Sent to senior analyst, compliance officer, or EDD team
    - SAR_APPROVED: BSA Officer has approved SAR draft for filing
    - SAR_FILED: SAR has been submitted to FinCEN — retain confirmation number
    - CLOSED: No SAR, investigation complete, rationale documented
    - 314B_REQUESTED: Information sharing request sent to another FI
    - LE_REFERRAL: Referred to law enforcement (voluntary disclosure)

    Args:
        case_id: The case to update
        status: New status (see values above)
        notes: Description of what changed and why
        actor: Who made this change (investigator_id or system name)

    Returns:
        Updated case record

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with case management API PATCH/PUT call:
    #   response = requests.patch(
    #       f"{ACTIMIZE_BASE_URL}/cases/{case_id}",
    #       headers=headers,
    #       json={"status": status, "notes": notes, "updatedBy": actor}
    #   )
    # ──────────────────────────────────────────────────────────────────────────
    """
    if case_id not in _CASE_DATABASE:
        # Case not in mock DB — create a placeholder
        logger.warning(f"[case_management] Case {case_id} not found — creating placeholder")
        _CASE_DATABASE[case_id] = {
            "case_id": case_id,
            "status": "UNKNOWN",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "timeline": [],
            "notes": [],
        }

    case = _CASE_DATABASE[case_id]
    case["status"] = status
    case["updated_at"] = datetime.utcnow().isoformat() + "Z"

    if notes:
        case["notes"].append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "actor": actor,
            "note": notes,
        })

    case["timeline"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": actor,
        "action": f"Status updated to {status}",
        "note": notes[:200] if notes else "",
        "system": "AI_INVESTIGATION_AGENT",
    })

    logger.info(f"[case_management] Case {case_id} updated to status '{status}'")
    return case


def close_case(
    case_id: str,
    disposition: str,
    reason: str,
    closed_by: str = "AI_AGENT",
) -> Dict[str, Any]:
    """
    Close an investigation case with documented disposition and rationale.

    BSA requires that closed cases have documented rationale explaining
    why no SAR was filed. "No suspicious activity found" is not sufficient —
    the rationale must explain what was investigated and what information
    was considered in making the determination.

    Disposition values:
    - NO_SUSPICIOUS_ACTIVITY: Investigation found no credible suspicious activity
    - CUSTOMER_EXPLANATION_ACCEPTED: Customer provided credible explanation
    - PRIOR_DISCLOSURE: Activity was already disclosed/reported
    - PATTERN_EXPLAINED_BY_BUSINESS: Activity consistent with verified business
    - SAR_FILED: SAR was filed — case closed after filing
    - ESCALATED_TO_SENIOR_ANALYST: Passed to senior review

    Args:
        case_id: Case to close
        disposition: Disposition category (see values above)
        reason: Documented rationale (will be retained for 5 years)
        closed_by: Actor who closed the case (usually investigator_id)

    Returns:
        Final case record

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Case closure in production should also:
    # 1. Archive all investigation documents to BSA records system
    # 2. Trigger 5-year retention timer in document management system
    # 3. Update customer risk profile if warranted
    # 4. Close the originating TMS alert
    # 5. Generate closure statistics for management reporting
    # ──────────────────────────────────────────────────────────────────────────
    """
    if case_id not in _CASE_DATABASE:
        _CASE_DATABASE[case_id] = {"case_id": case_id, "timeline": [], "notes": []}

    case = _CASE_DATABASE[case_id]
    case["status"] = "CLOSED"
    case["disposition"] = disposition
    case["closed_at"] = datetime.utcnow().isoformat() + "Z"
    case["closed_by"] = closed_by
    case["closure_reason"] = reason
    case["retention_expiry"] = (datetime.utcnow() + timedelta(days=1825)).strftime("%Y-%m-%d")

    case["notes"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": closed_by,
        "note": f"CASE CLOSED — Disposition: {disposition}. Reason: {reason}",
    })

    case["timeline"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": closed_by,
        "action": f"Case CLOSED with disposition: {disposition}",
        "system": "AI_INVESTIGATION_AGENT",
    })

    # BSA record retention note — always added to closed cases
    case["bsa_retention_note"] = (
        f"Per 31 CFR § 1010.430, this case record must be retained until {case['retention_expiry']}. "
        f"Closed by {closed_by} on {case['closed_at']}."
    )

    logger.info(f"[case_management] Case {case_id} CLOSED — disposition: {disposition}")
    return case


def assign_case(case_id: str, investigator_id: str) -> Dict[str, Any]:
    """
    Assign or reassign a case to a specific investigator.

    Case assignment is important for:
    - Accountability: Each case has a named responsible analyst
    - Workload management: Prevents cases from being unassigned
    - Expertise routing: Complex cases go to senior analysts
    - SLA tracking: Assignment starts the investigation SLA clock

    Investigators must be licensed/certified — most banks require:
    - CAMS (Certified Anti-Money Laundering Specialist) — ACAMS
    - CFE (Certified Fraud Examiner) — ACFE
    - BSA/AML certification from bank training program

    Args:
        case_id: Case to assign
        investigator_id: The investigator's employee ID

    Returns:
        Updated case record

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # In production, also:
    # - Validate that investigator_id exists in HR/identity system
    # - Check investigator's current workload (SLA management)
    # - Send notification to investigator (email/Teams/Slack)
    # - Update supervisor dashboard
    # ──────────────────────────────────────────────────────────────────────────
    """
    if case_id not in _CASE_DATABASE:
        _CASE_DATABASE[case_id] = {"case_id": case_id, "timeline": [], "notes": []}

    case = _CASE_DATABASE[case_id]
    previous_investigator = case.get("investigator_id")
    case["investigator_id"] = investigator_id
    case["assigned_at"] = datetime.utcnow().isoformat() + "Z"
    case["updated_at"] = datetime.utcnow().isoformat() + "Z"

    case["timeline"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": "CASE_MANAGER",
        "action": f"Case assigned to {investigator_id}" +
                  (f" (reassigned from {previous_investigator})" if previous_investigator else ""),
        "system": "AI_INVESTIGATION_AGENT",
    })

    logger.info(f"[case_management] Case {case_id} assigned to {investigator_id}")
    return case


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a case record by case ID.

    Used by the Streamlit dashboard to display case history and
    by the investigation agent to check if a case already exists.

    Args:
        case_id: Case ID to retrieve

    Returns:
        Case record dictionary or None if not found

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with:
    #   response = requests.get(f"{ACTIMIZE_BASE_URL}/cases/{case_id}", headers=headers)
    #   return response.json()
    # ──────────────────────────────────────────────────────────────────────────
    """
    return _CASE_DATABASE.get(case_id)


def get_all_cases() -> List[Dict[str, Any]]:
    """
    Retrieve all cases for the dashboard alert queue display.

    Returns:
        List of all case records (for demo purposes — production would paginate)

    # ── INTEGRATION POINT ──────────────────────────────────────────────────────
    # Replace with:
    #   response = requests.get(
    #       f"{ACTIMIZE_BASE_URL}/cases",
    #       headers=headers,
    #       params={"status": "OPEN,PENDING_HUMAN_REVIEW", "limit": 100}
    #   )
    #   return response.json()["cases"]
    # ──────────────────────────────────────────────────────────────────────────
    """
    return list(_CASE_DATABASE.values())
