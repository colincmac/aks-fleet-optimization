# 6. Separate Resource Changes From Financial Value

[Previous: findings](05-recommendations-risk-and-confidence.md) | [Documentation home](../README.md)

## Why This Matters

Reducing requested CPU changes a scheduling setting. It does not necessarily change running nodes, committed spend or the bill. A financial conclusion needs its own evidence and accountable reviewer.

## Learning Objectives

- Separate an engineering opportunity, attributed cost, forecast and realized outcome.
- Explain amortized cost and why allocation is not avoidable spend.
- Record a financial hypothesis without inventing savings.

## Before You Begin

Complete [start with existing tools](00-start-with-existing-tools.md) and [the outcome module](01-why-fleet-efficiency.md). No billing access or live tools are needed for the synthetic lesson. FinOps practitioners connect technology decisions with financial accountability. A commitment, such as a reservation, can affect when capacity changes actually change cost.

## Concept

**Concept:** an engineering opportunity is a setting worth investigating. Attributed cost is an amount assigned to a resource/workload under reviewed allocation rules. A forecast is a separately owned estimate with assumptions. A realized outcome is a later result established from comparable actual evidence. None of these is interchangeable with the others.

Amortized cost spreads applicable commitment costs over their benefit period. Reconciliation checks an approved cost projection and allocation against the required scope, period, identities, currency and completeness rules.

## In AKS

Application requests share node infrastructure with other workloads and system components. Removing a request reservation may leave node count unchanged. Even an observed node reduction needs independent review of commitments, prices, demand, billing periods and effects elsewhere before claiming value.

## How The Advisor Uses This

The separate offline cost workflow consumes approved saved evidence from existing tools. It can normalize Cost Management or FOCUS ledgers and retain reviewed AKS Cost Analysis, OpenCost or Kubecost attribution at its actual granularity. Actual or aggregate evidence remains `attributed`; compatible amortized/effective row partitions can become `reconciled`. It does not query source systems or calculate savings, and unmatched charges remain visible.

## What It Cannot Conclude

**Solution boundary:** `estimated_monthly_savings` remains `null`, including after cost reconciliation. Matching cost to a workload does not establish avoidable billed resources, overlap-free opportunities or realized savings. The advisor makes no currency conversion or commitment-purchase recommendation.

## Synthetic Example

**Example: fictional USD 100 charge.** Reviewed shares assign USD 60 to an application, USD 25 to idle and USD 15 to system capacity. These partition the same USD 100; they are not extra charges. Full allocation coverage means the approved amounts were assigned, not that USD 25 or USD 60 can be saved.

A separate CPU request suggestion in that application cannot turn those amounts into a savings estimate. Capacity and financial effects must be observed and reviewed separately.

## Participant Exercise

### Optional Saved-Finance Exercise

Use the [runnable financial tutorial](../tutorials/reconcile-existing-cost-evidence.md) only for a financial question. Its fictional native FOCUS import lacks historical bindings and remains blocked; reviewed amortized shares reconcile the same USD 100 into USD 60 allocated, USD 25 idle and USD 15 system; actual/native aggregate evidence remains attributed. All three retain null savings. Identify each status, source basis, remaining identity limitation and the FinOps next action instead of calculating a benefit.

Expected decision: keep this review separate from a request-only test, whose success is established by independent SLO/scenario/rollback evidence. If billing periods, commitments or comparable demand are unavailable, record financial effect as unassessed or inconclusive and stop. A participant can complete metadata or ordinary-Prometheus work without doing this exercise or providing financial data.

**Participant exercise:** write a financial hypothesis with its unknowns, owner and comparison period. State what evidence would be needed if an approved engineering change later altered node behavior. Do not calculate savings.

## Expected Output

"A request-only change may release scheduling reservation. FinOps will check whether billable consumption changes under comparable demand and amortized billing periods, accounting for commitments and other changes. Until then, financial effect is unverified and advisor savings remain null."

## Discuss

- When can useful capacity release have no immediate bill reduction?
- Which changes in traffic or prices would invalidate a simple before/after comparison?
- How will teams avoid counting the same capacity effect twice?

## Common Misconceptions

- Idle allocation is not automatically recoverable money.
- Allocation coverage is not a percentage of available savings.
- A percentage reduction in requests is not the same percentage reduction in cost.

## Key Takeaways

Keep engineering validation and financial validation separate. Preserve unmatched/unallocated cost, period and currency. A justified inconclusive or no-financial-change outcome is better than an unsupported savings claim.

## Deeper Reference

- [Financial source profiles](../financial-source-profiles.md)
- [Cost projection, allocation and financial gates](../cost-reconciliation.md)
- [Always-null savings semantics](../metrics-and-scoring.md#savings-rules)
- [Separate engineering and financial outcomes](../accelerator-docs/implementation-guide.md#4-measure-engineering-and-financial-outcomes-separately)
