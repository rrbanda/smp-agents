# ISO 20022 Error and Status Codes

Reference for common status and reason codes encountered in payment
exception handling across SWIFT, SEPA, and Fedwire corridors.

## Payment Status Codes (pacs.002)

| Code | Name | Description |
|------|------|-------------|
| ACTC | AcceptedTechnicalValidation | Authentication and syntactic validation passed |
| ACCP | AcceptedCustomerProfile | Customer profile check passed |
| ACSP | AcceptedSettlementInProcess | Settlement is in progress |
| ACSC | AcceptedSettlementCompleted | Settlement completed successfully |
| RJCT | Rejected | Payment has been rejected |
| PDNG | Pending | Payment is pending (sanctions, fraud, or data check) |

## Rejection Reason Codes

| Code | Name | Description | Common Resolution |
|------|------|-------------|-------------------|
| AC01 | IncorrectAccountNumber | Account number is invalid | Return to originator for correction |
| AC04 | ClosedAccountNumber | Account has been closed | Return to originator |
| AC06 | BlockedAccount | Account is blocked (sanctions, court order) | Escalate to compliance |
| AG01 | TransactionForbidden | Transaction type not allowed for this account | Return to originator |
| AM02 | NotAllowedAmount | Amount exceeds limit for this transaction type | Escalate to operator |
| AM04 | InsufficientFunds | Insufficient funds in debtor account | Notify originator |
| AM05 | Duplication | Duplicate transaction detected | Reject duplicate |
| BE01 | InconsistentWithEndCustomer | Beneficiary details inconsistent | Verify and repair or return |
| MS02 | NotSpecifiedReasonCustomer | Reason not specified by customer | Escalate to operator |
| RC01 | BankIdentifierIncorrect | BIC is incorrect or missing | Look up correct BIC and repair |
| RR01 | MissingDebtorAccountOrID | Debtor account missing | Return to originator |
| RR04 | RegulatoryReason | Regulatory hold (sanctions, AML) | Escalate to compliance |

## Status-to-Action Mapping

When processing exceptions, map the ISO 20022 status to the appropriate
repair action:

```
RC01 (BankIdentifierIncorrect) -> add_bic
AM05 (Duplication)             -> reject_duplicate
RR04 (RegulatoryReason)        -> check_sanctions_status -> release or block
AM02 (NotAllowedAmount)        -> escalate_to_operator
AC01 (IncorrectAccountNumber)  -> return_to_originator
```

## Field Validation Rules

| Field | Rule | Error if Violated |
|-------|------|-------------------|
| BIC | 8 or 11 alphanumeric characters | RC01 |
| IBAN | Country code (2) + check digits (2) + BBAN (up to 30) | AC01 |
| Amount | Positive decimal, max 2 decimal places for most currencies | AM02 |
| Currency | ISO 4217 3-letter code | Invalid currency |
| Date | ISO 8601 or SWIFT date format (YYMMDD) | Format error |
