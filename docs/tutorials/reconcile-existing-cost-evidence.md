# Reconcile Existing Cost Evidence

[Documentation home](../README.md) | [Financial profiles](../financial-source-profiles.md)

This tutorial uses only synthetic saved inputs. It does not contact Azure, AKS Cost Analysis, OpenCost, Kubecost, FinOps hubs, or a billing endpoint.

Financial imports are optional and separate from workload engineering checks. Use existing Cost Management/FinOps tools for ordinary financial questions. This handoff is for reviewing a specific unresolved attribution or reconciliation question, not another billing platform.

## Convert A Native FOCUS Export

For approved customer evidence, select **Cost and usage details (FOCUS)**, dataset **1.2-preview**, **CSV**, compression **None** in the existing Cost Management export. Use a scope that supports FOCUS; management-group and MOSP exports are not supported. Have the existing export owner download the native manifest and every CSV part from one completed run into protected local storage. Do not mix runs or alter the files. See [Microsoft's export settings and partition manifest](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) and [FOCUS dataset schema](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview). The advisor obtains no billing identity or storage permission and does not create exports or download files.

Try the generated fictional export from the repository root, using fresh output paths:

```powershell
aks-fleet-advisor convert-focus `
  --manifest examples/fixtures/focus-manifest.json `
  --part examples/fixtures/focus-part0.csv `
  --review examples/fixtures/focus-review.json `
  --output normalized-focus.json
aks-fleet-advisor reconcile-costs `
  --costs normalized-focus.json `
  --as-of 2026-10-29T12:00:00Z `
  --output reconciled-focus.json
```

Conversion exits `0`; reconciliation exits `3` with `blocked`, USD 100 retained and `estimated_monthly_savings: null`. This example deliberately has no historical resource bindings or allocation evidence. Missing identity is a useful outcome, not a reason to fabricate a workload match. No snapshot is required. Reconciliation can be replayed against the same normalized file and evaluation clock without access to the original export.

The FinOps owner supplies the small review file, not a transformed ledger or custom preprocessing script. Use the [synthetic review shape](../../examples/fixtures/focus-review.json), replacing every fictional value with independently reviewed evidence:

| Review field | Required evidence |
| --- | --- |
| `tenant_id`, `subscription_ids` | Explicit approved scope; source subscription IDs are checked, not inferred |
| `period.start`, `period.end` | Reviewed nonempty half-open UTC period containing every source charge |
| `source_reference` | Inert protected review reference, never a credential, SAS URL or raw manifest |
| `source_observed_at` | Independently verified export observation/completion time, not the file modification clock |
| `expected_totals` | Exact decimal-string `EffectiveCost` control totals per `BillingCurrency` from the independent source review, not list prices or a USD conversion |
| Optional `bindings` | Existing exact historical resource-to-cluster bindings with validity period/reference; absent bindings remain gaps |

Repeat `--part` for each explicitly selected local partition. The converter matches unique basenames to the native manifest but never opens manifest-supplied paths or URLs. It requires manifest version `2024-04-01`, export type `FocusCost` and the selected dataset/format; unsupported versions are rejected, not relabeled. Limits are 100 parts, 100,000 records and 32 MiB total CSV bytes, plus 32 MiB each for manifest/review JSON. UTF-8 with optional BOM, CRLF and correctly quoted multiline fields are supported. Duplicate/missing required headers, malformed CSV, missing parts, mismatched byte/record counts, out-of-scope rows and unequal totals fail without producing an output. Parquet and compressed exports are outside this bounded adapter; choose an appropriate smaller export scope rather than silently dropping files or rows.

Only allowlisted financial fields survive conversion. Billing/account names, contact details, tags, descriptions, arbitrary extension fields, raw manifest content and local paths are excluded from output and error text. Parsing raw exports necessarily reads those fields transiently: use this path only under approved local data-handling policy. Protect inputs and normalized financial artifacts with existing ACLs, encryption and retention; never put customer files in Git, workshop records or logs. Digests do not authenticate the producer.

`export_provenance` retains manifest/run hashes and partition/file hashes, byte/record counts and effective-cost totals. Each normalized row ID combines its manifest partition-path hash, file SHA-256 and one-based CSV record ordinal; a multiline record counts once. Identical-content partitions remain separate without retaining raw paths. These IDs identify the saved export, not stable billing charge identities across reruns. Preserve the exact source files for audit under approved retention.

When independently reviewed allocation already exists, optionally supply `--allocation-profile` and `--allocation` together to `convert-focus`, using the same supported projections as `project-costs`. Row shares must reference the converted row IDs, use effective cost and match the original period/historical binding; native aggregates remain at their supplied granularity. Purchases, taxes, corrections, unused/unknown commitment consumption and missing historical bindings retain existing blockers and amounts. In particular, the documented Azure dataset leaves commitment status empty: never replace that with `Used`. A matching schema or successful synthetic replay does not certify live customer compatibility; validate that separately in an approved pilot. Managed AKS Cost Analysis is not assumed to expose a public OpenCost endpoint.

## 1. Project Approved Saved Evidence

From the repository root, create a new normalized schema-1 file:

```powershell
aks-fleet-advisor project-costs `
  --ledger-profile azure-cost-details-amortized `
  --ledger examples/fixtures/azure-cost-details-projection.json `
  --allocation-profile reviewed-allocation-shares `
  --allocation examples/fixtures/reviewed-allocation-shares.json `
  --output normalized-costs.json
```

The command reads bounded allowlisted JSON and refuses overwrite. It does not download exports, follow references, convert currencies, price resources, or infer historical Kubernetes identities.

## 2. Reconcile The Normalized Evidence

```powershell
aks-fleet-advisor reconcile-costs `
  --costs normalized-costs.json `
  --snapshot examples/fixtures/cost-snapshot.json `
  --as-of 2026-10-29T12:00:00Z `
  --output reconciled-costs.json
```

The synthetic amortized ledger partitions USD 100 into USD 60 allocated, USD 25 idle and USD 15 system. The expected status is `reconciled`, while `estimated_monthly_savings` remains `null`.

## 3. Preserve Actual AKS Cost Analysis Attribution

Project the synthetic actual-cost ledger with reviewed native AKS Cost Analysis allocation:

```powershell
aks-fleet-advisor project-costs `
  --ledger-profile azure-cost-details-actual `
  --ledger examples/fixtures/azure-cost-details-actual-projection.json `
  --allocation-profile aks-cost-analysis `
  --allocation examples/fixtures/aks-cost-analysis-allocation.json `
  --output normalized-actual-costs.json
aks-fleet-advisor reconcile-costs `
  --costs normalized-actual-costs.json `
  --as-of 2026-10-29T12:00:00Z `
  --output attributed-actual-costs.json
```

Projection exits `0`; reconciliation exits `3` without a snapshot. The expected status is `attributed` with `actual-cost-not-financially-reconciled` and `aggregate-allocation-not-ledger-partition`; the source amounts and granularity remain visible and savings remain null. The fixed date belongs to the fictional source, not a current customer run.

## 4. Interpret Other Outcomes

- `attributed`: valid source-native or actual-cost allocation is retained but cannot satisfy amortized row-reconciliation gates.
- `blocked`: unsupported profile/version, stale or incomplete evidence, mixed currency, incompatible basis/period, unmatched rows, unsupported charges or insufficient allocation coverage prevents reconciliation.
- A deleted current workload does not erase an independently reviewed exact historical allocation. Current absence is reported as context and prevents using that evidence as a current resource proposal.
- Namespace or asset aggregates remain at their source granularity. They are never upgraded into workload/container UID history.

## 5. Clean Up

Delete the synthetic outputs when finished. No cloud resource or source system was changed.

## 6. Next Step

Use the [assessment guide](../accelerator-docs/assessment-guide.md) only when an existing-tool result leaves a specific enterprise question that the accelerator can answer with approved evidence.
