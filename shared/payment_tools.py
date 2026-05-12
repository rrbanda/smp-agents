"""Mock payment operations tools for the Payment Exception Repair demo.

Returns realistic hardcoded data that simulates SWIFT/ISO 20022 payment
processing systems.  Every function follows the same plain-function
convention used by the real tools in catalog_tools.py and neo4j_tools.py
so that ADK auto-discovers signatures and docstrings for the LLM.

Design principle: all mock data lives in _MOCK_DATA at module level.
To swap in a real backend, replace the function body while keeping the
signature and docstring unchanged.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock data store -- internally consistent across all tools
# ---------------------------------------------------------------------------

_MOCK_EXCEPTIONS: dict[str, dict[str, Any]] = {
    "EXC-2024-0847": {
        "exception_id": "EXC-2024-0847",
        "type": "missing_bic",
        "title": "Missing Beneficiary BIC",
        "priority": "high",
        "status": "pending",
        "created_at": "2025-05-13T08:12:34Z",
        "payment_reference": "MT103-REF-20250513-A",
        "amount": "125,000.00",
        "currency": "USD",
        "originator": "ACME Corp (ACMEUS33)",
        "beneficiary_name": "Schmidt Manufacturing GmbH",
        "beneficiary_account": "DE89370400440532013000",
        "beneficiary_bic": "",
        "error_code": "E001",
        "error_description": "Beneficiary institution BIC is missing or invalid",
        "originating_system": "Payment Gateway",
        "settlement_system": "SWIFT Alliance Lite2",
    },
    "EXC-2024-0851": {
        "exception_id": "EXC-2024-0851",
        "type": "amount_mismatch",
        "title": "Amount Mismatch",
        "priority": "critical",
        "status": "pending",
        "created_at": "2025-05-13T09:04:17Z",
        "payment_reference": "MT103-REF-20250513-B",
        "amount": "50,000.00",
        "currency": "USD",
        "settlement_amount": "5,000.00",
        "originator": "GlobalTrade Inc (GLOAUS66)",
        "beneficiary_name": "Tanaka Industries Ltd",
        "beneficiary_account": "JP12345678901234",
        "beneficiary_bic": "BOTKJPJT",
        "error_code": "E007",
        "error_description": "Instructed amount does not match settlement amount (USD 50,000.00 vs USD 5,000.00)",
        "originating_system": "Treasury Workstation",
        "settlement_system": "SWIFT Alliance Lite2",
    },
    "EXC-2024-0853": {
        "exception_id": "EXC-2024-0853",
        "type": "sanctions_hold",
        "title": "Sanctions Screening Hold",
        "priority": "high",
        "status": "pending",
        "created_at": "2025-05-13T09:22:51Z",
        "payment_reference": "MT103-REF-20250513-C",
        "amount": "87,500.00",
        "currency": "EUR",
        "originator": "Meridian Partners SA (MERIEU2D)",
        "beneficiary_name": "Ahmed Holdings LLC",
        "beneficiary_account": "AE070331234567890123456",
        "beneficiary_bic": "ABORAEADXXX",
        "error_code": "S003",
        "error_description": "Beneficiary name triggered OFAC SDN partial match (score 0.31)",
        "originating_system": "Payment Gateway",
        "settlement_system": "Sanctions Screening Engine",
    },
    "EXC-2024-0856": {
        "exception_id": "EXC-2024-0856",
        "type": "duplicate_payment",
        "title": "Duplicate Payment Detected",
        "priority": "medium",
        "status": "pending",
        "created_at": "2025-05-13T10:45:03Z",
        "payment_reference": "MT103-REF-20250513-D",
        "amount": "23,750.00",
        "currency": "GBP",
        "originator": "Northfield Capital (NORCGB2L)",
        "beneficiary_name": "BlueSky Consulting Ltd",
        "beneficiary_account": "GB29NWBK60161331926819",
        "beneficiary_bic": "NWBKGB2L",
        "error_code": "D002",
        "error_description": (
            "Duplicate reference: same amount, beneficiary, and reference submitted at 06:31 and 10:44 today"
        ),
        "original_payment_id": "PAY-20250513-0631-NORCGB2L",
        "originating_system": "Payment Gateway",
        "settlement_system": "Dedup Engine",
    },
}

_MOCK_MESSAGES: dict[str, str] = {
    "MT103-REF-20250513-A": (
        "=== SWIFT MT103 Single Customer Credit Transfer ===\n"
        "Message Reference : MT103-REF-20250513-A\n"
        "Date              : 2025-05-13\n"
        ":20: Transaction Ref  : TXN-20250513-ACME-001\n"
        ":23B: Bank Operation   : CRED\n"
        ":32A: Value Date/Amt   : 250513USD125000,00\n"
        ":50K: Ordering Customer:\n"
        "      /US33100100000123456789\n"
        "      ACME Corp\n"
        "      100 Industrial Parkway\n"
        "      Chicago, IL 60601 US\n"
        ":52A: Ordering Inst    : ACMEUS33\n"
        ":53A: Sender Corresp   : CHASUS33\n"
        ":57A: Account With Inst: (EMPTY - MISSING BIC)\n"
        ":59:  Beneficiary      :\n"
        "      /DE89370400440532013000\n"
        "      Schmidt Manufacturing GmbH\n"
        "      Industriestrasse 42\n"
        "      Frankfurt 60325 DE\n"
        ":70:  Remittance Info  : /INV/2025-04-3892\n"
        ":71A: Charges          : SHA\n"
        "=== END MT103 ==="
    ),
    "MT103-REF-20250513-B": (
        "=== SWIFT MT103 Single Customer Credit Transfer ===\n"
        "Message Reference : MT103-REF-20250513-B\n"
        "Date              : 2025-05-13\n"
        ":20: Transaction Ref  : TXN-20250513-GLOB-002\n"
        ":23B: Bank Operation   : CRED\n"
        ":32A: Value Date/Amt   : 250513USD50000,00\n"
        ":33B: Instructed Amt   : USD50000,00\n"
        ":50K: Ordering Customer:\n"
        "      /US44200200000987654321\n"
        "      GlobalTrade Inc\n"
        "      200 Commerce Drive\n"
        "      New York, NY 10005 US\n"
        ":52A: Ordering Inst    : GLOAUS66\n"
        ":53A: Sender Corresp   : CITIUS33\n"
        ":57A: Account With Inst: BOTKJPJT\n"
        ":59:  Beneficiary      :\n"
        "      /JP12345678901234\n"
        "      Tanaka Industries Ltd\n"
        "      1-2-3 Marunouchi, Chiyoda-ku\n"
        "      Tokyo 100-0005 JP\n"
        ":70:  Remittance Info  : /PO/2025-Q2-8831\n"
        ":71A: Charges          : OUR\n"
        "NOTE: Settlement amount received as USD 5,000.00 (mismatch)\n"
        "=== END MT103 ==="
    ),
    "MT103-REF-20250513-C": (
        "=== SWIFT MT103 Single Customer Credit Transfer ===\n"
        "Message Reference : MT103-REF-20250513-C\n"
        "Date              : 2025-05-13\n"
        ":20: Transaction Ref  : TXN-20250513-MERI-003\n"
        ":23B: Bank Operation   : CRED\n"
        ":32A: Value Date/Amt   : 250513EUR87500,00\n"
        ":50K: Ordering Customer:\n"
        "      /LU28001900006449750001\n"
        "      Meridian Partners SA\n"
        "      12 Boulevard Royal\n"
        "      Luxembourg L-2449 LU\n"
        ":52A: Ordering Inst    : MERIEU2D\n"
        ":53A: Sender Corresp   : DEUTLULL\n"
        ":57A: Account With Inst:ABORAEADXXX\n"
        ":59:  Beneficiary      :\n"
        "      /AE070331234567890123456\n"
        "      Ahmed Holdings LLC\n"
        "      Suite 401, Al Reem Tower\n"
        "      Abu Dhabi AE\n"
        ":70:  Remittance Info  : /CONTRACT/ME-2025-1120\n"
        ":71A: Charges          : SHA\n"
        "=== END MT103 ==="
    ),
    "MT103-REF-20250513-D": (
        "=== SWIFT MT103 Single Customer Credit Transfer ===\n"
        "Message Reference : MT103-REF-20250513-D\n"
        "Date              : 2025-05-13\n"
        ":20: Transaction Ref  : TXN-20250513-NORC-004\n"
        ":23B: Bank Operation   : CRED\n"
        ":32A: Value Date/Amt   : 250513GBP23750,00\n"
        ":50K: Ordering Customer:\n"
        "      /GB82WEST12345698765432\n"
        "      Northfield Capital\n"
        "      55 Threadneedle Street\n"
        "      London EC2R 8AH GB\n"
        ":52A: Ordering Inst    : NORCGB2L\n"
        ":53A: Sender Corresp   : WESTGB2L\n"
        ":57A: Account With Inst: NWBKGB2L\n"
        ":59:  Beneficiary      :\n"
        "      /GB29NWBK60161331926819\n"
        "      BlueSky Consulting Ltd\n"
        "      14 King Street\n"
        "      Manchester M2 4WU GB\n"
        ":70:  Remittance Info  : /INV/BS-2025-0447\n"
        ":71A: Charges          : SHA\n"
        "NOTE: Duplicate of PAY-20250513-0631-NORCGB2L submitted at 06:31 today\n"
        "=== END MT103 ==="
    ),
}

_MOCK_COUNTERPARTIES: dict[str, dict[str, Any]] = {
    "DEUTDEFF": {
        "bic": "DEUTDEFF",
        "bank_name": "Deutsche Bank AG",
        "city": "Frankfurt am Main",
        "country": "Germany",
        "country_code": "DE",
        "swift_member": True,
        "status": "active",
    },
    "COBADEFF": {
        "bic": "COBADEFF",
        "bank_name": "Commerzbank AG",
        "city": "Frankfurt am Main",
        "country": "Germany",
        "country_code": "DE",
        "swift_member": True,
        "status": "active",
    },
    "BOTKJPJT": {
        "bic": "BOTKJPJT",
        "bank_name": "MUFG Bank, Ltd.",
        "city": "Tokyo",
        "country": "Japan",
        "country_code": "JP",
        "swift_member": True,
        "status": "active",
    },
    "NWBKGB2L": {
        "bic": "NWBKGB2L",
        "bank_name": "NatWest (National Westminster Bank Plc)",
        "city": "London",
        "country": "United Kingdom",
        "country_code": "GB",
        "swift_member": True,
        "status": "active",
    },
    "ACMEUS33": {
        "bic": "ACMEUS33",
        "bank_name": "ACME Corporate Banking",
        "city": "Chicago",
        "country": "United States",
        "country_code": "US",
        "swift_member": True,
        "status": "active",
    },
    "ABSORAEADXXX": {
        "bic": "ABSORAEADXXX",
        "bank_name": "Arab Bank for Investment and Foreign Trade",
        "city": "Abu Dhabi",
        "country": "United Arab Emirates",
        "country_code": "AE",
        "swift_member": True,
        "status": "active",
    },
}

_MOCK_SANCTIONS: dict[str, dict[str, Any]] = {
    "ahmed holdings llc": {
        "entity_searched": "Ahmed Holdings LLC",
        "screening_result": "potential_match",
        "match_score": 0.31,
        "match_type": "fuzzy_name",
        "matched_list": "OFAC SDN",
        "matched_entry": "AHMAD HOLDINGS (Dubai, UAE)",
        "matched_entry_id": "SDN-29471",
        "differences": [
            "Searched 'Ahmed' vs listed 'Ahmad' (transliteration variant)",
            "Searched 'LLC' (Abu Dhabi) vs listed entity in Dubai",
            "No matching aliases or addresses",
        ],
        "recommendation": (
            "Likely false positive -- name is a common transliteration variant; "
            "jurisdictions differ; no address or alias overlap."
        ),
    },
    "schmidt manufacturing gmbh": {
        "entity_searched": "Schmidt Manufacturing GmbH",
        "screening_result": "clear",
        "match_score": 0.0,
        "match_type": "none",
        "matched_list": "N/A",
        "matched_entry": "N/A",
        "matched_entry_id": "N/A",
        "differences": [],
        "recommendation": "No sanctions match found.",
    },
}

_MOCK_REPAIR_HISTORY: dict[str, dict[str, Any]] = {
    "missing_bic": {
        "exception_type": "missing_bic",
        "total_occurrences_90d": 147,
        "auto_repair_rate": 0.97,
        "common_fixes": [
            {
                "action": "add_bic_from_counterparty_lookup",
                "frequency": 0.82,
                "description": "BIC resolved from beneficiary IBAN country + historical payment records",
            },
            {
                "action": "add_bic_from_beneficiary_iban",
                "frequency": 0.12,
                "description": "BIC derived from IBAN bank code (first 4-8 chars after country code)",
            },
            {
                "action": "return_to_originator",
                "frequency": 0.06,
                "description": "Unable to resolve BIC; payment returned for correction",
            },
        ],
        "avg_resolution_time_minutes": 4.2,
        "avg_manual_resolution_time_minutes": 38.0,
    },
    "amount_mismatch": {
        "exception_type": "amount_mismatch",
        "total_occurrences_90d": 23,
        "auto_repair_rate": 0.0,
        "common_fixes": [
            {
                "action": "escalate_to_operator",
                "frequency": 0.87,
                "description": "Amount discrepancies always require human review per compliance policy",
            },
            {
                "action": "return_to_originator",
                "frequency": 0.13,
                "description": "Payment returned when originator confirms the instructed amount was wrong",
            },
        ],
        "avg_resolution_time_minutes": 120.0,
        "avg_manual_resolution_time_minutes": 120.0,
        "policy_note": "Amount mismatches cannot be auto-repaired per compliance policy CP-PAY-007.",
    },
    "sanctions_hold": {
        "exception_type": "sanctions_hold",
        "total_occurrences_90d": 312,
        "auto_repair_rate": 0.0,
        "common_fixes": [
            {
                "action": "release_false_positive",
                "frequency": 0.91,
                "description": "Compliance officer confirms false positive after review",
            },
            {
                "action": "block_and_report",
                "frequency": 0.07,
                "description": "True positive; payment blocked and SAR filed",
            },
            {
                "action": "escalate_to_compliance",
                "frequency": 0.02,
                "description": "Ambiguous match requiring senior compliance review",
            },
        ],
        "avg_resolution_time_minutes": 45.0,
        "avg_manual_resolution_time_minutes": 45.0,
        "policy_note": "Sanctions decisions require human sign-off per BSA/AML policy. Agent provides analysis only.",
    },
    "duplicate_payment": {
        "exception_type": "duplicate_payment",
        "total_occurrences_90d": 68,
        "auto_repair_rate": 0.85,
        "common_fixes": [
            {
                "action": "reject_duplicate",
                "frequency": 0.79,
                "description": "Exact duplicate rejected; original payment proceeds",
            },
            {
                "action": "release_intentional_duplicate",
                "frequency": 0.15,
                "description": "Originator confirms this is an intentional repeat payment",
            },
            {
                "action": "escalate_to_operator",
                "frequency": 0.06,
                "description": "Near-duplicate (different minor fields) requires manual review",
            },
        ],
        "avg_resolution_time_minutes": 2.1,
        "avg_manual_resolution_time_minutes": 15.0,
    },
}

_MOCK_FRAUD_SCORES: dict[str, dict[str, Any]] = {
    "MT103-REF-20250513-A": {
        "payment_reference": "MT103-REF-20250513-A",
        "fraud_score": 0.03,
        "risk_level": "low",
        "model_version": "fraud-detect-v3.2.1",
        "contributing_factors": [
            {
                "factor": "originator_history",
                "score": 0.01,
                "detail": "ACME Corp has 847 clean transactions in 12 months",
            },
            {
                "factor": "beneficiary_country",
                "score": 0.02,
                "detail": "Germany (DE) is low-risk jurisdiction",
            },
            {
                "factor": "amount_pattern",
                "score": 0.04,
                "detail": "Amount is within normal range for this originator",
            },
            {
                "factor": "time_of_day",
                "score": 0.05,
                "detail": "Submitted during normal business hours (08:12 ET)",
            },
        ],
    },
    "MT103-REF-20250513-B": {
        "payment_reference": "MT103-REF-20250513-B",
        "fraud_score": 0.42,
        "risk_level": "medium",
        "model_version": "fraud-detect-v3.2.1",
        "contributing_factors": [
            {
                "factor": "amount_anomaly",
                "score": 0.65,
                "detail": "10x discrepancy between instructed and settlement amount",
            },
            {
                "factor": "originator_history",
                "score": 0.08,
                "detail": "GlobalTrade has 234 clean transactions in 12 months",
            },
            {
                "factor": "beneficiary_country",
                "score": 0.12,
                "detail": "Japan (JP) is low-risk jurisdiction",
            },
            {
                "factor": "settlement_timing",
                "score": 0.38,
                "detail": "Settlement amount received 47 minutes after instruction",
            },
        ],
    },
    "MT103-REF-20250513-C": {
        "payment_reference": "MT103-REF-20250513-C",
        "fraud_score": 0.18,
        "risk_level": "low",
        "model_version": "fraud-detect-v3.2.1",
        "contributing_factors": [
            {
                "factor": "originator_history",
                "score": 0.05,
                "detail": "Meridian Partners has 156 clean transactions in 12 months",
            },
            {
                "factor": "beneficiary_country",
                "score": 0.22,
                "detail": "UAE is moderate-risk jurisdiction",
            },
            {
                "factor": "amount_pattern",
                "score": 0.08,
                "detail": "Amount is within normal range for this corridor",
            },
            {
                "factor": "sanctions_flag",
                "score": 0.35,
                "detail": "Sanctions screening triggered (handled separately)",
            },
        ],
    },
    "MT103-REF-20250513-D": {
        "payment_reference": "MT103-REF-20250513-D",
        "fraud_score": 0.07,
        "risk_level": "low",
        "model_version": "fraud-detect-v3.2.1",
        "contributing_factors": [
            {
                "factor": "originator_history",
                "score": 0.02,
                "detail": "Northfield Capital has 412 clean transactions in 12 months",
            },
            {
                "factor": "duplicate_flag",
                "score": 0.15,
                "detail": "Duplicate detection triggered (handled separately)",
            },
            {
                "factor": "beneficiary_country",
                "score": 0.01,
                "detail": "United Kingdom (GB) is low-risk jurisdiction",
            },
            {
                "factor": "amount_pattern",
                "score": 0.03,
                "detail": "Amount is within normal range for this originator",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Public tool functions (ADK-compatible: plain functions with docstrings)
# ---------------------------------------------------------------------------


def get_exception_queue(status: str = "pending", priority: str = "") -> str:
    """Get the current payment exception queue with optional filters.

    Args:
        status: Filter by exception status (pending, in_review, resolved, escalated). Default: pending.
        priority: Filter by priority level (critical, high, medium, low). Leave empty for all priorities.

    Returns:
        JSON string with a list of payment exceptions including ID, type, priority,
        amount, currency, and creation timestamp.
    """
    results = []
    for exc in _MOCK_EXCEPTIONS.values():
        if status and exc["status"] != status:
            continue
        if priority and exc["priority"] != priority:
            continue
        results.append({
            "exception_id": exc["exception_id"],
            "type": exc["type"],
            "title": exc["title"],
            "priority": exc["priority"],
            "status": exc["status"],
            "amount": exc["amount"],
            "currency": exc["currency"],
            "beneficiary_name": exc["beneficiary_name"],
            "created_at": exc["created_at"],
            "error_code": exc["error_code"],
        })
    return json.dumps({"total": len(results), "exceptions": results}, indent=2)


def get_exception_detail(exception_id: str) -> str:
    """Get full details for a specific payment exception.

    Args:
        exception_id: The exception identifier (e.g. 'EXC-2024-0847').

    Returns:
        JSON string with complete exception record including payment reference,
        error codes, amounts, originator/beneficiary details, and timestamps.
        Returns an error if the exception ID is not found.
    """
    exc = _MOCK_EXCEPTIONS.get(exception_id)
    if exc is None:
        return json.dumps({"error": f"Exception '{exception_id}' not found"})
    return json.dumps(exc, indent=2)


def get_payment_message(payment_reference: str) -> str:
    """Retrieve the original SWIFT MT103 payment message content.

    Args:
        payment_reference: The payment message reference (e.g. 'MT103-REF-20250513-A').

    Returns:
        The raw SWIFT MT103 message text showing all fields including
        ordering customer, beneficiary, amounts, and correspondent banks.
        Returns an error if the reference is not found.
    """
    msg = _MOCK_MESSAGES.get(payment_reference)
    if msg is None:
        return json.dumps({"error": f"Payment message '{payment_reference}' not found"})
    return msg


def get_counterparty_info(bic_code: str) -> str:
    """Look up counterparty bank information by BIC/SWIFT code.

    Args:
        bic_code: The SWIFT BIC code (e.g. 'DEUTDEFF' for Deutsche Bank Frankfurt).

    Returns:
        JSON string with bank name, city, country, SWIFT membership status.
        Returns an error if the BIC code is not found.
    """
    info = _MOCK_COUNTERPARTIES.get(bic_code)
    if info is None:
        return json.dumps({
            "error": f"BIC '{bic_code}' not found in counterparty database",
            "suggestion": "Try looking up the beneficiary IBAN country to determine the likely correspondent bank",
            "known_german_bics": ["DEUTDEFF (Deutsche Bank AG)", "COBADEFF (Commerzbank AG)"],
        })
    return json.dumps(info, indent=2)


def check_sanctions_status(entity_name: str) -> str:
    """Screen an entity name against sanctions watchlists (OFAC SDN, EU, UN).

    Args:
        entity_name: The entity name to screen (person or organization).

    Returns:
        JSON string with screening result: match score (0.0-1.0),
        match type (exact/fuzzy/alias/none), matched list, and differences
        found between the searched entity and the matched entry.
    """
    key = entity_name.strip().lower()
    result = _MOCK_SANCTIONS.get(key)
    if result is None:
        return json.dumps({
            "entity_searched": entity_name,
            "screening_result": "clear",
            "match_score": 0.0,
            "match_type": "none",
            "matched_list": "N/A",
            "recommendation": "No sanctions match found.",
        })
    return json.dumps(result, indent=2)


def get_repair_history(exception_type: str) -> str:
    """Get historical repair patterns and success rates for an exception type.

    This provides data from the ML-powered repair recommendation engine
    based on the last 90 days of resolved exceptions.

    Args:
        exception_type: The exception type code (e.g. 'missing_bic', 'amount_mismatch',
            'sanctions_hold', 'duplicate_payment').

    Returns:
        JSON string with historical patterns including auto-repair success rate,
        common fix actions with frequencies, and average resolution times
        for both automated and manual handling.
    """
    history = _MOCK_REPAIR_HISTORY.get(exception_type)
    if history is None:
        return json.dumps({"error": f"No repair history for exception type '{exception_type}'"})
    return json.dumps(history, indent=2)


def get_fraud_score(payment_reference: str) -> str:
    """Get the ML fraud risk score for a payment transaction.

    Uses the fraud-detect model to evaluate transaction risk based on
    originator history, beneficiary jurisdiction, amount patterns,
    and timing signals.

    Args:
        payment_reference: The payment message reference (e.g. 'MT103-REF-20250513-A').

    Returns:
        JSON string with fraud score (0.0 = no risk, 1.0 = certain fraud),
        risk level (low/medium/high/critical), model version, and
        individual contributing factor scores with explanations.
    """
    score = _MOCK_FRAUD_SCORES.get(payment_reference)
    if score is None:
        return json.dumps({"error": f"No fraud score available for '{payment_reference}'"})
    return json.dumps(score, indent=2)


def submit_repair(exception_id: str, action: str, details: str = "") -> str:
    """Submit a repair recommendation for a payment exception.

    In production this would update the exception management system and
    trigger the downstream repair workflow. In the current configuration
    it logs the action and returns a confirmation with audit trail.

    Args:
        exception_id: The exception to repair (e.g. 'EXC-2024-0847').
        action: The repair action to take (e.g. 'add_bic', 'reject_duplicate',
            'release_false_positive', 'escalate_to_operator', 'return_to_originator').
        details: Free-text explanation of the repair rationale and evidence.

    Returns:
        JSON string with repair confirmation including audit trail
        (timestamp, operator, action, status).
    """
    exc = _MOCK_EXCEPTIONS.get(exception_id)
    if exc is None:
        return json.dumps({"error": f"Exception '{exception_id}' not found"})

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "status": "repair_submitted",
        "exception_id": exception_id,
        "action": action,
        "details": details,
        "audit": {
            "submitted_at": now,
            "submitted_by": "payment_ops_agent",
            "approval_status": "pending_human_review",
            "audit_id": f"AUD-{exception_id}-{now[:10].replace('-', '')}",
        },
        "next_steps": (
            "Repair recommendation queued for operator review. "
            "Operator will approve or reject within SLA (15 minutes for high priority)."
        ),
    }
    logger.info("Repair submitted: %s -> %s (%s)", exception_id, action, details[:80])
    return json.dumps(result, indent=2)
