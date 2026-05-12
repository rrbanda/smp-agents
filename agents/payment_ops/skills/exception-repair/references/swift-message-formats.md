# SWIFT MT103 Field Reference

The MT103 is a SWIFT message type used for single customer credit transfers.
It is the most common message type for cross-border payments.

## Key Fields for Exception Repair

| Field | Tag | Description | Repair Relevance |
|-------|-----|-------------|------------------|
| Transaction Reference | :20 | Unique reference assigned by the sender | Used for duplicate detection |
| Bank Operation Code | :23B | Type of operation (CRED, SPAY, etc.) | Rarely an issue |
| Value Date / Amount | :32A | Settlement date and amount | Amount mismatch detection |
| Instructed Amount | :33B | Original instructed amount (if different from :32A) | Compare with :32A for mismatches |
| Ordering Customer | :50K | Name and address of the payer | Sanctions screening input |
| Ordering Institution | :52A | BIC of the ordering bank | Routing validation |
| Sender's Correspondent | :53A | Intermediary bank BIC | Routing chain validation |
| Account With Institution | :57A | BIC of the beneficiary's bank | Most common missing-BIC field |
| Beneficiary | :59 | Name, address, and account of the payee | Sanctions screening input |
| Remittance Information | :70 | Invoice or contract reference | Duplicate detection support |
| Details of Charges | :71A | Who pays charges (SHA/OUR/BEN) | Rarely an issue |

## BIC Resolution from IBAN

When the :57A field (Account With Institution) is missing, the BIC can often
be derived from the beneficiary IBAN:

- **DE** (Germany): First 8 characters after "DE" + 2 check digits map to German bank codes
  - Common: DEUTDEFF (Deutsche Bank), COBADEFF (Commerzbank), DRESDEFF (Dresdner)
- **GB** (UK): Characters 5-8 of the IBAN are the bank sort code identifier
  - Common: NWBKGB2L (NatWest), BARCGB22 (Barclays), HBUKGB4B (HSBC)
- **JP** (Japan): No IBAN standard; BIC must be looked up from the bank code

## Error Codes

| Code | Category | Description |
|------|----------|-------------|
| E001 | Data | Beneficiary institution BIC is missing or invalid |
| E002 | Data | Ordering institution BIC is missing or invalid |
| E003 | Format | Message does not conform to MT103 format rules |
| E007 | Amount | Instructed amount does not match settlement amount |
| S003 | Compliance | Sanctions screening match detected |
| D002 | Duplicate | Duplicate payment reference detected |
| R001 | Routing | No valid routing path to beneficiary institution |
