# Approved Repair Procedures

This reference defines the approved repair actions by exception type,
escalation criteria, and compliance constraints.

## Repair Action Catalog

### add_bic
- **Applies to**: missing_bic exceptions (E001, E002)
- **Auto-repair eligible**: Yes, if confidence > 90%
- **Procedure**: Resolve BIC from counterparty database or IBAN derivation, patch the :57A field, resubmit to settlement
- **Escalation trigger**: If multiple candidate BICs found, or if the beneficiary bank is not a SWIFT member

### reject_duplicate
- **Applies to**: duplicate_payment exceptions (D002)
- **Auto-repair eligible**: Yes, for exact duplicates (same reference + amount + beneficiary)
- **Procedure**: Reject the newer submission, confirm the original payment is proceeding
- **Escalation trigger**: Near-duplicates where amounts differ slightly or the reference has a minor variation

### release_false_positive
- **Applies to**: sanctions_hold exceptions (S003)
- **Auto-repair eligible**: No -- always requires compliance officer sign-off
- **Procedure**: Agent prepares analysis (match score, differences, recommendation), compliance officer reviews and approves release
- **Escalation trigger**: Match score > 0.7, or exact name match regardless of score

### block_and_report
- **Applies to**: sanctions_hold exceptions where match is confirmed
- **Auto-repair eligible**: No
- **Procedure**: Block payment, file SAR (Suspicious Activity Report), notify compliance leadership
- **Escalation trigger**: Always escalated to senior compliance

### escalate_to_operator
- **Applies to**: Any exception type where automated resolution is not possible or not allowed
- **Auto-repair eligible**: No (by definition)
- **Procedure**: Flag exception for human review with agent's analysis attached
- **Common triggers**: Amount mismatches (policy CP-PAY-007), ambiguous sanctions matches, unusual fraud scores

### return_to_originator
- **Applies to**: Any exception where the issue originates from the sending institution
- **Auto-repair eligible**: Yes, for clear format errors
- **Procedure**: Generate reject message with error details, send back via the originating channel
- **Escalation trigger**: If the originator is a high-value client (auto-return may violate relationship SLA)

## Compliance Constraints

| Policy | Rule | Impact |
|--------|------|--------|
| CP-PAY-007 | Amount mismatches cannot be auto-repaired | Agent must escalate to operator |
| CP-BSA-012 | Sanctions decisions require human sign-off | Agent provides analysis only |
| CP-FRD-003 | Fraud scores > 0.8 trigger mandatory hold | Payment cannot proceed until cleared |
| CP-AUD-001 | All repair actions must include audit trail | submit_repair always generates audit record |

## Autonomy Levels

The agent operates at one of three autonomy levels, configured per exception type:

1. **Assist** (current default): Agent diagnoses and recommends; human approves all actions
2. **Supervised**: Agent executes low-risk repairs automatically; human reviews after the fact
3. **Autonomous**: Agent handles known patterns end-to-end; human monitors via dashboards

Progression from Assist to Autonomous requires:
- 30-day shadow mode with >= 95% recommendation accuracy
- Compliance review and sign-off
- Per-exception-type approval (not blanket)
