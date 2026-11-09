# Offline cost reconciliation

This is the exact cost-import/allocation reference. Start with
[cost attribution versus savings](learning/06-cost-attribution-versus-savings.md)
for a worked explanation of what assigned cost does and does not establish.
Reconciliation here checks approved attribution; it is not a forecast or
realized-savings result.

Import **one sanitized amortized-cost projection**
and optional reviewed allocation shares. It does not query billing systems,
install OpenCost, deploy a service, or enable financial recommendations.

## Supported profiles

`azure-cost-details-projection-v1` is an advisor-owned, versioned JSON projection
of an existing **AmortizedCost** Cost Management cost-details export. It is not a
raw CSV reader or a claim that every EA/MCA/FOCUS dataset is interchangeable.
The [cost-import schema](../schemas/cost-import.schema.json) is authoritative;
unknown fields, nonfinite amounts and float financial inputs are rejected.
Use decimal strings, not binary floating-point conversions.

An operator prepares the allowlisted projection outside the advisor boundary:

| Projection field | Required mapping / treatment |
|---|---|
| `cost_basis` | Explicitly `amortized` from the export request/manifest, never inferred from price or amount. Actual/list-price input is unsupported. |
| `source_reference` / `source_observed_at` | Approved export identifier and aware UTC observation time, after the exported period. No download URL or credential. |
| `export_complete` | Explicit completeness declaration covering all requested pages/files/partitions, including unmatched charges. Omission is incomplete. |
| `tenant_id` / `subscription_ids` | Separately approved tenant/subscription scope; not display names. |
| Row `id` | Stable, unique export/partition/row identity assigned during projection. Do not merge overlapping exports or give duplicate source rows new identities. |
| `resource_id` / `subscription_id` | Original `ResourceId` and `SubscriptionId`; a missing resource remains `null`. Preserve exact case and spelling; no name or resource-group inference. |
| Row `period` | Actual usage interval, e.g. `Date` mapped to a complete UTC day, within the exported interval. Do not substitute invoice dates. All intervals are half-open `[start,end)`. |
| `amount` / `currency` | `CostInBillingCurrency` and `BillingCurrency`. No retail price, pricing-currency conversion, monthly extrapolation, or new amortization. |
| `pricing_model` / `charge_type` | Preserve `PricingModel` and `ChargeType`. Usage, unused benefits, purchases, refunds and adjustments are not equivalent. |
| `benefit_id` / `reservation_id` | Preserve applicable `BenefitId` and `ReservationId`. Reservation/SavingsPlan usage without its benefit identity blocks reconciliation. |
| `charge_category` | Reviewed, exclusive meter-to-`compute`/`storage`/`network`/`other` classification. Do not use idle/system as charge types or guess from a resource name. |

This profile is synthetically characterized, **not operator/source certified**.
Export completeness, source references and resource bindings are declarations,
not independent attestation. Do not commit customer cost evidence.

### Exact resource and workload reconciliation

Every matched billed resource requires one explicit historical `bindings` entry:
the original billed Azure ID, exact AKS cluster ID/fingerprint, optional exact
agent-pool ID, and an approved historical mapping reference. VMSS, storage and
network bills do not automatically use AKS pool IDs. The advisor never derives
that mapping from display names, today's node roster, or a resource-group prefix.
The binding applies to this export period; operators must verify its full-window
validity before supplying it.

The supplied snapshot must contain exactly one matching cluster/fingerprint and,
when specified, pool. Allocated workload shares additionally require exact
namespace, workload UID and one named container in that cluster. A recreated
workload or cluster does not inherit the previous identity's cost. Snapshot
membership verifies the target only; the upstream historical binding/share
evidence must establish period membership. Deleted/unmapped workloads remain
unmatched; no present-day name join or unsupported history is synthesized.

Rows outside the approved subscriptions are invalid. The snapshot tenant must
match, and its subscriptions must be inside the declared cost scope. Missing,
partial, ambiguous, stale or future Azure/Kubernetes inventory receipts block
reconciliation. Costs do not depend on Prometheus coverage, and a cost failure
does not modify the snapshot, suppress capacity findings or change the engine.

### Allocation is a partition, not additional billing

Optional `reviewed-allocation-shares-v1` supports operator-prepared AKS Cost
Analysis, OpenCost or Kubecost shares. This is **not a native allocation API
adapter**. Source shares require explicit original billing-row identity, exact
window and historical workload binding. Ordinary name-only allocation API
responses cannot supply missing UIDs; report those as unmatched.

Supply reviewed dimensionless shares of each original billing row, not vendor
list-price dollar totals. `basis` must be `reviewed-shares` and `shared_idle` must
be false. Idle already redistributed into workload shares cannot also appear as
an idle row. Do not assume the managed AKS add-on exposes an OpenCost API.

Each share has exactly one attribution category:
`allocated`, `idle`, `system`, or `unallocated`. Only `allocated` targets a
workload/container. Duplicate targets or shares summing above one are invalid.
The remaining fraction and rejected/unmatched shares stay unallocated.
Every original amount, currency, benefit and unmatched row remains in the output.

For each billing row:

```text
attributed amount = original amortized amount * approved fraction
residual unallocated = original amount - sum(accepted attributed amounts)
```

Decimal arithmetic preserves sub-cent residue without rounding money up.
Charge-category and attribution totals are **two views of the same ledger**,
never additive. Cost rows are sorted by ID and currencies by code. The output
retains original evidence, accepted bindings/shares, explicit row issues,
canonical input/snapshot SHA-256 digests and evaluation parameters for replay.

## Financial gates

Per currency:

```text
denominator = sum(positive original amortized charges, including unmatched rows)
allocation coverage = accepted allocated + idle + system amounts / denominator
```

Coverage must meet the configured threshold (default `0.95`; equality passes).
Explicit and residual unallocated amounts do not count as allocated. The output
also records exact matched/unmatched resource amounts and signed original totals.
Zero/empty denominators have unknown coverage, never 100%.
Refunds, negative charges, purchases, unused commitments and adjustments are
retained but block this profile; they are not silently netted away to
inflate coverage. Missing benefit identities, incomplete exports, mismatched
cost/assessment or allocation windows, invalid bindings and stale/future evidence
also block reconciliation.

Mixed currencies retain independent ledgers and always block; there is no
combined total or exchange-rate fallback. A passing allocation threshold is
necessary, not sufficient, for a `reconciled` result.

`estimated_monthly_savings` is **always null**, including for reconciled input.
Attribution does not establish avoidable billable resources, commitment release,
overlap-free proposals, or realized outcomes.

## Replay and exit codes

From the repository root, using only synthetic inputs:

```powershell
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli reconcile-costs `
  --costs examples\fixtures\cost-import.json `
  --snapshot examples\fixtures\cost-snapshot.json `
  --as-of 2026-10-29T12:00:00Z `
  --output costs.json
```

The example partitions USD 100 into 60 allocated, 25 idle and 15 system, with
100% allocation coverage and null savings. Output must be new; no file is
overwritten. Omit `--output` for JSON on stdout.

`--minimum-allocation-coverage` is a decimal string between zero and one.
`--maximum-evidence-age-hours` defaults to 24 and is bounded to 1..8760;
it applies independently to the export, snapshot and inventory source receipts.
Use an explicit aware `--as-of` for reproducible replay; historical replay is
not current source validation or change approval.

Exit codes: `0` reconciled, `3` blocked with retained evidence, `2` invalid input
or prerequisites, `1` output failure. Input size is bounded by the existing
32 MiB reader; rows, bindings and shares each have a 100,000-entry limit.
There are no network clients, retries, downloads or permissions in this path.
Financial artifacts require customer-owned access control, encryption and
retention; do not share the full ledger as a public report.

## Limitations

Only the projection and allocation-share profiles described above are supported.
Validate the actual export, historical bindings and completeness independently.
There is no native billing/allocation API client, raw CSV import, currency
conversion, commitment purchase recommendation or savings calculation.
Cost reconciliation does not create a monitoring or governance service.

References:

- [Microsoft cost-details fields](https://learn.microsoft.com/en-us/azure/cost-management-billing/automate/understand-usage-details-fields)
- [OpenCost allocation API and pricing basis](https://opencost.io/docs/integrations/api/)
- [Assessment evidence and replay](data-contracts.md#recommendation-and-replay)
