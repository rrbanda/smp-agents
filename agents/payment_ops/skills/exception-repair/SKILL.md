---
name: exception-repair
description: Diagnoses payment exceptions by correlating data across payment gateway, settlement, and compliance systems. Recommends repair actions with evidence chains and confidence levels. Supports human-in-the-loop approval workflow.
compatibility: Requires access to payment exception queue, SWIFT message store, counterparty database, sanctions screening, and fraud scoring APIs.
metadata:
  author: payments-team
  version: "1.0"
  tags: payments, exception-handling, repair, swift, compliance
---

# Payment Exception Repair Instructions

When asked to investigate or repair a payment exception, follow this methodology:

## Step 1: Review the Queue

Use `get_exception_queue` to see current pending exceptions. Note the priority ordering:
- **critical**: Amount mismatches, potential fraud -- must be reviewed immediately
- **high**: Missing data, sanctions holds -- SLA is 30 minutes
- **medium**: Duplicates, format issues -- SLA is 2 hours
- **low**: Informational, advisory -- SLA is end of business day

## Step 2: Pull Exception Details

Use `get_exception_detail` to retrieve the full exception record. Identify:
- The exception type (missing_bic, amount_mismatch, sanctions_hold, duplicate_payment)
- The original payment reference
- The error code and description
- Which systems are involved (originating system vs settlement system)

## Step 3: Retrieve the Payment Message

Use `get_payment_message` with the payment reference to see the original SWIFT MT103. Examine:
- Field :57A (Account With Institution) for BIC issues
- Field :32A (Value Date/Amount) for amount issues
- Field :59 (Beneficiary) for sanctions screening context
- Field :20 (Transaction Reference) for duplicate detection

## Step 4: Cross-Reference External Data

Depending on the exception type, pull additional context:
- **Missing BIC**: Use `get_counterparty_info` with likely BIC codes derived from the beneficiary IBAN country. For German IBANs (DE), try DEUTDEFF or COBADEFF.
- **Sanctions hold**: Use `check_sanctions_status` with the flagged entity name. Evaluate match score, match type, and differences.
- **All types**: Use `get_fraud_score` to check the transaction's ML risk assessment.

## Step 5: Check Historical Patterns

Use `get_repair_history` with the exception type to see:
- How often this type occurs (volume in last 90 days)
- What the auto-repair success rate is
- Which fix actions are most common and their success frequencies
- How long automated vs manual resolution typically takes

## Step 6: Formulate Diagnosis

Synthesize findings into a clear diagnosis:
- State the root cause in one sentence
- List the evidence (which tools returned what data)
- Note any compliance constraints (e.g. amount mismatches cannot be auto-repaired)

## Step 7: Recommend Action

Based on the diagnosis and repair history, recommend one of:
- **Auto-repair**: For high-confidence, policy-allowed fixes (e.g. add missing BIC)
- **Escalate to operator**: For ambiguous cases or policy-restricted actions
- **Return to originator**: When the exception cannot be resolved without the sender's correction

Include a confidence level: high (>90% historical success), medium (70-90%), low (<70%).

## Step 8: Present Structured Output

Return findings in this format:
```json
{
  "exception_id": "...",
  "diagnosis": "Root cause in one sentence",
  "evidence": [
    {"source": "tool_name", "finding": "what was found"}
  ],
  "fraud_risk": "low|medium|high",
  "recommended_action": "action_name",
  "confidence": "high|medium|low",
  "confidence_basis": "97% auto-repair success rate for this pattern over 147 cases",
  "requires_human_approval": true,
  "compliance_notes": "Any policy constraints"
}
```

Always present the recommendation clearly and wait for human approval before calling `submit_repair`.
