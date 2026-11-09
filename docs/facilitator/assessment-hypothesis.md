# Assessment Hypothesis

[Workbook](participant-workbook.md) | [Change validation](../accelerator-docs/implementation-guide.md)

Use one copy of this blank customer template for one bounded candidate. Store
the populated record with the customer's protected assessment/change records,
not Git. This is not advisor input, source attestation, change approval or a
savings calculation. Do not copy fictional identities, values or policies into
a production record.

## Business Outcome And Scope

| Field | Customer-owned record |
|---|---|
| Hypothesis reference, revision and review date | |
| Desired application/business outcome | |
| Exact protected cluster/workload/container/controller reference | |
| Environment/workload class and exclusions | |
| Accountable application/platform owner | |

## Observed And Missing Evidence

| Field | Customer-owned record |
|---|---|
| Original assessment/finding ID, pack/version and protected artifact reference | |
| Observation period, evaluation time, units and current-configuration check | |
| Collected facts | |
| Separate owner declarations and independent review references | |
| Missing/unsupported facts, owners and next actions | |
| Why this is an investigation or eligible proposal, not an approval | |

## Candidate Intervention And Reliability Constraints

| Field | Customer-owned record |
|---|---|
| Falsifiable hypothesis and evidence that would disprove it | |
| One proposed dimension; original and proposed values if independently justified | |
| Supported shape and unresolved controller/admission/placement constraints | |
| SLOs, peak/startup/failover/disruption requirements | |
| Blast radius and reasons not to proceed | |

## Validation And Rollback

| Field | Customer-owned record |
|---|---|
| Representative test/scenario plan and canary scope | |
| Independent measures and numeric customer acceptance/abort criteria | |
| Observation period and accountable observer | |
| Exact original-state restoration procedure and test evidence | |
| Authorized implementation/rollback owner | |
| Separate change approval reference and validity | Not granted by this template |

Requests, limits and replica floors need separate tests. The advisor applies
none of them. A report, hash or policy reference does not prove the planned
scenario was tested or authorize implementation.

## Cost Hypothesis

| Field | Customer-owned record |
|---|---|
| Engineering effect expected, without a savings claim | |
| FinOps owner and financial baseline period/currency/cost basis | |
| Attribution, unmatched charges, commitments and demand/price assumptions | |
| Separately owned forecast, if approved outside the advisor | |
| Actual billing/capacity comparison needed to establish an outcome | |
| Confounders and overlap/double-counting controls | |

Advisor estimated savings remain null even when attribution reconciles.

## Decision, Outcome And Next Action

| Field | Customer-owned record |
|---|---|
| Current decision and rationale | |
| Outcome: retain/defer/reject/test/rollback/inconclusive/validated, as applicable | |
| Acceptance evidence and remaining limits | |
| Named next-action owner and date | |
| Reassessment trigger and artifact retention/deletion owner | |

A disappearing finding or merged change does not establish resolution or a
financial outcome. Distinguish observed engineering effects, independent
financial validation and realized outcomes. Exact meanings remain in
[finding contracts](../data-contracts.md#recommendation-and-replay),
[cost gates](../cost-reconciliation.md#financial-gates) and
[change validation](../accelerator-docs/implementation-guide.md).