# Offline Cost Reconciliation

[Documentation home](README.md) | [Start with existing tools](learning/00-start-with-existing-tools.md) | [Financial profiles](financial-source-profiles.md)

This workflow consumes approved saved evidence from existing financial and Kubernetes cost tools. It does not replace Microsoft Cost Management, FinOps hubs, AKS Cost Analysis, OpenCost, Kubecost or a FinOps review.

## Boundaries

The runtime has no billing SDK, Cost Management download client, managed AKS Cost Analysis endpoint client, OpenCost/Kubecost client, currency conversion, retail-price lookup, commitment-purchase logic, forecast or savings calculation. It never installs telemetry or mutates a cluster.

`estimated_monthly_savings` is structurally `null` for every profile and status. Attribution does not establish avoidable resources, commitment release, overlap-free opportunities or realized value.

## Inspect Saved Allocation Without A Ledger

If your question is only what an existing AKS Cost Analysis, OpenCost or Kubecost view attributed, use `project-allocation` instead of preparing billing rows and historical bindings. This normalizes an approved sanitized source-native aggregate projection through the same packaged profile; it does not perform financial reconciliation or join the amounts to engineering findings.

From the repository root after installation/activation, run this fictional saved AKS Cost Analysis example with a fresh output path:

```powershell
aks-fleet-advisor project-allocation --allocation-profile aks-cost-analysis --allocation examples/fixtures/aks-cost-analysis-allocation.json --output allocation-context.json
```

Expected exit: `0`. Output follows [the existing normalized allocation shape](../schemas/cost-allocation.schema.json) and retains the exact source/profile/producer versions, decimal amounts, currencies, period, completeness, granularity, identity basis, allocation policy and references. It creates no ledger, observation clock, historical UID, financial status or savings field. Command success means normalization succeeded, not that the source is fresh, complete, authenticated, financially reconciled or eligible to prioritize an engineering finding. Partial input stays explicitly partial; currencies are not combined or converted.

Only source-native aggregate amounts are accepted by this ledger-free command. Original-row shares require `project-costs` with an authoritative ledger so row IDs, approved subscription scope and over-allocation can be validated. Existing pricing/version/field checks still apply, including rejection of list-price evidence by the retained billing-oriented profiles. Invalid input exits `2` without echoing financial values or creating output; an existing destination is not overwritten and exits `1`. No endpoint, credential or live managed add-on API is accessed.

The allocation projection itself has no tenant or source-observation timestamp. Treat it as protected normalized source data, not an admitted assessment context. Use the separate observation workflow below only when genuine source-scope and observation-clock evidence are available. Keep using the customer's existing tool for financial investigation; add the ledger workflow below only for an explicit FinOps reconciliation question.

## Qualify Saved Allocation Context

`AllocationObservation` wraps an unchanged aggregate allocation with explicit tenant/subscription, exact cluster resource ID/fingerprint, source observation time and a source-binding reference. These fields must come from an independently established source-scope binding; do not copy today's fingerprint or use projection time to fill missing history. Declarations and hashes are not source authentication. Name-only namespace/workload attribution remains name-only even when cluster context qualifies.

From the repository root, this fictional example creates a fresh original assessment bundle and qualifies the supplied synthetic observation against it:

```text
aks-fleet-advisor assess --fragments examples/fixtures/pool-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z --artifacts .local/allocation-example
aks-fleet-advisor qualify-allocation --observation examples/fixtures/allocation-observation.json --assessment .local/allocation-example/assessment.json --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T12:00:00Z --output .local/qualified-allocation.json
```

Qualification validates original tenant/hash/configuration bindings and locked report replay, exact cluster/fingerprint, identical financial/report periods, supported financial profiles, pricing, completeness and source freshness. Source reads are bounded and reject links/junctions; invalid input exits `2` with redacted errors and no output. Existing output is never overwritten. Valid but stale, future, incomplete, negative-amount, incompatible-period or unsupported source/pricing evidence is retained as `blocked` context with exit `3`; qualified metadata exits `0`. Freshness uses the assessment's configured positive hours, and equality passes.

Output uses [allocation-context.schema.json](../schemas/allocation-context.schema.json), retaining the original [observation](../schemas/allocation-observation.schema.json) and requested period. Native AKS attribution may retain source-declared pricing; other supported allocation profiles retain billing-pricing requirements. No currencies are combined, and no amount, source observation or lower-level historical identity is invented. `qualified` is a context-consistency result, not ledger reconciliation, fresh engineering eligibility, source attestation, a changed finding priority or savings. The optional review-order workflow below requires its own stricter grain/comparability admission. Financial trends remain separate unfinished work; optional ledger/history workflows stay available.

## Order A Separate Cluster Cost Review

Use optional `order-cost-review` only when approved source observations provide one explicit cluster-grain allocated amount per exact cluster. It creates a separate review list; it never reorders or changes engineering findings, severity, confidence, eligibility, proposal values or savings. Existing allocation, ledger, reconciliation and history workflows remain available and optional. This is not financial trend analysis or an efficiency ranking.

Prepare two or more original assessment directories and their independently established `AllocationObservation` files. Repeat `--assessment` and `--observation` in corresponding order, with fresh output:

```text
aks-fleet-advisor order-cost-review --assessment cluster-a/assessment.json --observation approved-cluster-a.json --assessment cluster-b/assessment.json --observation approved-cluster-b.json --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T12:00:00Z --output .local/cluster-cost-review.json
```

These are input-path placeholders, not supplied customer data. Use the actual evaluation clock for new evidence. The existing fictional allocation observation is namespace-grain and is intentionally not an ordering input; successful general qualification does not make its grain comparable for this command.

The command performs bounded original-file/hash/configuration/tenant admission and locked report replay, checks the original Kubernetes fingerprint and requalifies each observation against that exact cluster and report period. It then requires a common source reference, profile/producer, period, currency across every bucket, cost/pricing basis and evaluation clock. The strictest original configured age limit applies to the complete comparison. Blocked/incomplete/negative/stale/future input, duplicate or recreated cluster contexts, multiple allocated rows, mixed grain, name-only cluster attribution, lower-level fields masquerading as cluster grain and mismatched validity periods refuse the whole comparison, never silently drop a cluster.

Output follows [cluster-cost-review-order.schema.json](../schemas/cluster-cost-review-order.schema.json). Rows are ordered by descending exact decimal source-native allocated amount, then exact cluster resource ID/fingerprint; ambient decimal precision does not round the sort key. Original qualified context, currency, idle/shared/system/unallocated amounts and original assessment run IDs remain visible. Nonallocated amounts are not blended into the ordering amount. Source-native amounts remain attribution, not an authoritative ledger partition or avoidable/released cost. `engineering_order_changed` is fixed false and savings remain null.

SDK `order_saved_cost_reviews` supplies original-artifact admission; pure `order_cluster_cost_reviews` only requalifies its caller-supplied contexts and checks their comparability, not source authentication or original-file provenance. Invalid CLI inputs exit `2` with redacted errors and no output; existing output is refused without replacement. Budgets are 2..1000 pairs, 32 MiB per observation/original bundle and 128 MiB combined canonical observation/bundle payload. CLI raw observation reads are separately capped at 128 MiB and output at 128 MiB; formatting bytes do not become financial facts. No endpoint, credential, currency conversion or automatic financial action is used.

## Schema 1.0 Inputs

A normalized `CostImport` separates one authoritative ledger from optional allocation evidence:

- `ledger_profile`: exact packaged profile, profile version and characterized producer version.
- `cost_basis`: `actual`, `amortized` or reviewed FOCUS `effective` cost.
- `period`, tenant, subscriptions, source observation, completeness and exact original rows.
- `bindings`: exact historical billed-resource to AKS cluster/pool mappings with a validity period covering the ledger period.
- `allocation`: either original-row fractions or source-native aggregate amounts, never both.

FOCUS rows also retain typed source financial metadata in `focus`. Normalized charge/pricing/benefit fields must agree with that metadata. OpenCost/Kubecost allocation evidence requires independently reviewed `pricing_basis: billing-ledger`; list-price estimates are not accepted as actual billing data. See the [version and pricing guide](financial-source-profiles.md#version-characterization) before preparing an import. Financial inputs are not prerequisites for workload or Prometheus analysis.

Money and fractions use decimal strings. Unknown fields, floats, nonfinite values, ambiguous IDs, duplicate rows/targets, over-allocation and out-of-scope resources are rejected.

## Projection

An optional [native FOCUS handoff](tutorials/reconcile-existing-cost-evidence.md#convert-a-native-focus-export) converts bounded local Azure `1.2-preview` CSV exports with their native manifest and independently reviewed controls. `convert-focus` checks every selected partition and exact currency totals, excludes sensitive columns, and adds digest/count provenance without downloading data or inventing historical bindings. Workload analysis does not depend on this financial workflow.

Use `project-costs` to normalize a supported sanitized source projection. The packaged projectors currently accept Azure Cost Details, FOCUS and reviewed allocation projections. Managed AKS Cost Analysis, OpenCost and Kubecost are accepted only through reviewed saved allocation projections matching their financial profile; there is no assumed live managed add-on API.

```text
aks-fleet-advisor project-costs --ledger-profile PROFILE --ledger LEDGER.json --allocation-profile PROFILE --allocation ALLOCATION.json --output normalized-costs.json
```

Output must be new. Projection is deterministic and offline; it preserves explicit source references and fails closed on profile, producer version, format or field mismatch.

## Attribution Shapes

### Original-Row Shares

`reviewed-allocation-shares` accepts dimensionless fractions tied to original ledger-row IDs. An allocated target additionally needs exact cluster identity, granularity, protected evidence reference and identity basis. Exact historical workload/container targets require workload UID and a validity period covering the billed row.

Every allocated target must belong to the import's approved `subscription_ids`. For an original-row share, its cluster resource ID must also exactly match the billed resource's historical cluster binding. Adding another subscription to the approved scope does not establish that its cluster consumed this row's resources.

For example, if a billed VM scale set is historically bound to cluster A, a workload share naming cluster B is blocked with `allocation-cluster-mismatch`. No share of that row is accepted, and its original amount remains unallocated. A target outside the approved subscriptions is rejected as invalid input before reconciliation. Correct the source mapping with the financial/platform owner; do not broaden scope or substitute a current name to clear the check.

For each row:

```text
attributed amount = original ledger amount * accepted fraction
residual unallocated = original ledger amount - sum(accepted attributed amounts)
```

### Source-Native Aggregate Amounts

AKS Cost Analysis, OpenCost and Kubecost evidence can retain cluster, namespace, workload, container or asset amounts at the granularity their reviewed projection actually supplies. Aggregate amounts receive `attributed` status and do not claim original billing-row partition or historical UID identity.

Aggregate target clusters must also belong to the approved subscriptions, but the advisor does not invent a billing-row binding for them. An approved aggregate for another cluster can remain attributed without becoming a reconciled row partition. Keep shared-cost decisions in the existing financial process, such as [Microsoft Cost Management allocation rules](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/allocate-costs); those rules are distinct from this advisor's historical row checks.

## Statuses

| Status | Meaning | Exit |
| --- | --- | --: |
| `reconciled` | Complete compatible amortized/effective ledger and exact row partition pass every financial gate | 0 |
| `attributed` | Valid source-native aggregate or actual-cost evidence is retained but cannot establish financial reconciliation | 3 |
| `blocked` | Invalid compatibility, completeness, freshness, identity, charge, currency or allocation gate | 3 |

Invalid input exits `2`; output failure exits `1`.

Actual cost is preserved but always includes `actual-cost-not-financially-reconciled`. Native source aggregates include `aggregate-allocation-not-ledger-partition`. These are explicit limits, not errors to suppress.

## Financial Gates

A `reconciled` result requires one supported ledger profile/version, one supported allocation profile/version, matching period and cost basis, complete evidence, supported usage charges, required reservation/Savings Plan identities, one currency, positive original cost, historical resource bindings and allocation coverage at or above the configured threshold.

Per currency:

```text
denominator = sum(positive original ledger charges, including unmatched rows)
allocation coverage = accepted allocated + idle + shared + system row-partition amounts / denominator
```

Mixed currencies retain independent ledgers and block reconciliation. Refunds, purchases, taxes, credits, corrections, unused commitments and adjustments are retained but block the current row-partition profile; they are not silently netted away. FOCUS committed usage requires the supplied benefit identity and consumption evidence; unknown consumption status produces `commitment-status-unknown`, not assumed usage. Unsupported `Other` pricing produces `unsupported-pricing-model`. The [Microsoft FOCUS schema](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus) explains the upstream fields and current dataset limitations.

## Current Snapshot Context

The cost period is independent of the metric window. A current snapshot is optional and is never used to manufacture historical cost identity. When supplied, it adds current context such as `current-workload-not-observed`; deletion or recreation does not erase valid historical attribution, but it prevents treating that historical target as current proposal evidence.

## Replay

```powershell
aks-fleet-advisor reconcile-costs `
  --costs examples/fixtures/cost-import.json `
  --snapshot examples/fixtures/cost-snapshot.json `
  --as-of 2026-10-29T12:00:00Z `
  --output costs.json
```

Run from the repository root after installation/activation, using a fresh output path. This fictional replay exits `0`, retains the USD 100 partition and leaves savings `null`; its fixed evaluation date is not a way to qualify stale customer evidence. The shared verifier checks every financial PowerShell command block for path/control-character corruption and missing fences; see the [worked tutorial](tutorials/reconcile-existing-cost-evidence.md) for optional blocked and attributed outcomes.

Inputs are bounded to 32 MiB and rows, bindings, shares and aggregate amounts are bounded to 100,000 entries. Output retains canonical input/snapshot digests, installed source definitions, exact evidence, issues and evaluation parameters for replay.

## Limitations

Validate the actual export, producer version, historical mappings, cost basis, allocation configuration and completeness independently. Cost reconciliation does not create an official framework score, source certification, billing audit, savings forecast, monitoring service or governance approval.

References:

- [AKS cost optimization practices](https://learn.microsoft.com/azure/aks/best-practices-cost)
- [AKS Cost Analysis](https://learn.microsoft.com/azure/aks/cost-analysis)
- [Understand AKS idle costs](https://learn.microsoft.com/azure/aks/cost-analysis-idle-costs)
- [View Kubernetes costs](https://learn.microsoft.com/azure/cost-management-billing/costs/view-kubernetes-costs)
- [FinOps hubs](https://learn.microsoft.com/cloud-computing/finops/toolkit/hubs/finops-hubs-overview)
