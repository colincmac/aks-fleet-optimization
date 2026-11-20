# Financial Source Profiles

[Documentation home](README.md) | [Cost reconciliation](cost-reconciliation.md)

Financial profiles characterize approved saved projections. They do not authenticate a product, attest source completeness, certify a producer version, or create a live integration.

Financial evidence is optional. Start with the customer's existing Prometheus/Grafana and selected workload checks when the question is engineering efficiency; add this workflow only when FinOps needs to examine a specific existing allocation or financial ledger. No billing permissions, new telemetry or product installation are required by the offline import.

For source-native aggregate context alone, [project a saved allocation without a ledger](cost-reconciliation.md#inspect-saved-allocation-without-a-ledger). This reuses the same characterized profiles, decimal amounts, period, identity and pricing limitations. It is normalization, not an assessment, freshness check, reconciliation or savings claim; row-share validation remains ledger-backed.

## Profile Matrix

| Profile | Upstream foundation | Accepted evidence | Reconciliation capability | Important limits |
| --- | --- | --- | --- | --- |
| `azure-cost-details-amortized` | Microsoft Cost Management cost-details export | Sanitized allowlisted amortized ledger rows with exact Azure resource IDs | Original-row partition can become `reconciled` when every financial gate passes | No raw export parser, billing API client, or Kubernetes allocation inference |
| `azure-cost-details-actual` | Microsoft Cost Management cost-details export | Sanitized actual-cost ledger rows | Attribution only; actual cost cannot become financially `reconciled` | Preserve for visibility and comparison context, not amortized commitment conclusions |
| `finops-focus` | Cost Management FOCUS export or approved FinOps hubs projection | Sanitized Azure FOCUS `1.2-preview` projection, or bounded native CSV/manifest conversion into it | Original-row partition can become `reconciled` after reviewed effective-cost mapping and all financial gates | Corrections, nonusage charges and unused/unknown commitment consumption remain blocked; no ADX, Fabric, storage or FinOps hubs client |
| `aks-cost-analysis` | Managed AKS Cost Analysis views | Reviewed saved cluster, namespace, asset, idle, system and service attribution | `attributed` aggregate evidence | No public managed add-on OpenCost endpoint is assumed; native views do not provide original billing-row or workload-UID identity |
| `opencost-allocation` | Existing OpenCost installation | Reviewed saved source-native allocation with explicit billing-pricing provenance | `attributed` aggregate evidence | Default list-price estimates are not billing actuals; pricing provider, idle/shared policy and identity limits must be retained |
| `kubecost-allocation` | Existing Kubecost installation | Reviewed saved projection with explicit billing-pricing provenance | `attributed` aggregate evidence | List-price estimates and uncharacterized versions are not accepted by this billing workflow; shared-cost settings remain source facts |
| `reviewed-allocation-shares` | Operator-reviewed partition derived from an approved source | Dimensionless fractions tied to original ledger row IDs and historical bindings | Can partition a compatible amortized/effective ledger | Review does not establish avoidable cost, savings, source authenticity or workload safety |

## Support And Product Boundaries

AKS Cost Analysis is a managed AKS capability built on OpenCost-derived usage and reconciled Azure billing data, but its product contract is not interchangeable with a standalone OpenCost API. Use the supported Azure portal and Cost Management views described in [AKS Cost Analysis](https://learn.microsoft.com/azure/aks/cost-analysis) and [View Kubernetes costs](https://learn.microsoft.com/azure/cost-management-billing/costs/view-kubernetes-costs).

FinOps hubs extend Cost Management for enterprise analytics and are an appropriate upstream financial platform. FinOps Toolkit solutions are provided as-is, while underlying managed products have their own support contracts; see [FinOps hubs](https://learn.microsoft.com/cloud-computing/finops/toolkit/hubs/finops-hubs-overview) and [FinOps Toolkit support](https://learn.microsoft.com/cloud-computing/finops/toolkit/help/support).

OpenCost and Kubecost profiles describe only the committed sanitized projection. A similar product name, successful HTTP response, or matching field name does not satisfy the profile.

## AKS Cost Analysis Applicability

Use this optional source only when the existing service and offer are eligible. The [AKS Cost Analysis prerequisites and limits](https://learn.microsoft.com/en-us/azure/aks/cost-analysis#prerequisites) currently specify Standard/Premium tier, cluster managed identity, Azure Disk CSI driver and required Azure API egress. Kubernetes cost views support Enterprise Agreement and Microsoft Customer Agreement offers, not every billing offer; virtual nodes and the listed `usnateast`, `usnatwest`, `usseceast` and `ussecwest` regions are unsupported. These are source-applicability facts, not a recommendation to change tier, billing offer or provisioning mode. Use other existing approved evidence or defer the financial question when they do not fit.

The documented add-on estimate is about 200 MB plus 0.5 MB per container, with a current 4 GB memory limit supporting approximately 7,000 containers per cluster; these are estimates subject to change, not an accelerator scalability guarantee. Allow up to 24 hours after enablement for initial data; normal cost/usage availability is typically 8-24 hours, not real-time incident or request-freshness evidence. Recheck the [current limitations](https://learn.microsoft.com/en-us/azure/aks/cost-analysis#limitations) for the actual cluster size and [view semantics](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/view-kubernetes-costs) before interpreting a missing or delayed view.

The add-on uses its own `cost-analysis-identity` with read access to the node resource group and association to node pools to collect asset identifiers. Its installation/identity/egress are owned by the platform operator; the local advisor neither enables it nor acquires that identity. Viewing cost data needs one of the documented subscription roles; prefer existing authorized readers rather than granting Owner/Contributor for this workflow. The advisor's saved-file import needs no billing or Kubernetes permission. Preserve exact Azure asset IDs and the source's cluster/namespace/asset granularity; those views do not establish original billing-row partitions, workload UIDs, or historical container ownership.

Review idle, system, service, shared and unallocated treatment explicitly. [Idle costs](https://learn.microsoft.com/en-us/azure/aks/cost-analysis-idle-costs) can reflect overprovisioning or intentional demand/failover buffer; idle attribution is not proof of waste or removable nodes. Retain the source period, currency, cost/pricing basis and current producer/profile version, and do not redistribute idle/shared amounts without an independently reviewed policy. For existing OpenCost/Kubecost, keep list-price estimates in their upstream context unless separately reviewed billing-ledger provenance satisfies this import. None of these financial checks is required for selected engineering analysis.

## Version Characterization

The packaged YAML profiles under `src/aks_fleet_efficiency/catalog/cost_sources/` declare synthetically characterized source contracts. A profile version identifies the advisor's interpretation; `projection_format` identifies its sanitized JSON shape; `producer_version_kind` explains what the input's `producer_version` actually names. These are separate from an upstream specification or API version. A version match alone does not establish field correctness, pricing provenance or source authenticity.

| Profiles | Profile version | Projection format | Producer-version role and characterized label |
| --- | --- | --- | --- |
| Azure Cost Details actual/amortized | `1.0.0` | `azure-cost-details-projection-v1` | `projection`: `2025.05.01`, a synthetic projection-producer label, not a native Cost Details dataset version |
| FOCUS | `1.0.0` | `finops-focus-projection-v1` | `dataset`: Azure `1.2-preview`; `specification_version` is separately recorded as `1.2` |
| Managed AKS Cost Analysis | `1.0.0` | `reviewed-aks-cost-analysis-v1` | `projection`: `1.0.0`, not a discovered managed add-on version |
| OpenCost | `1.0.0` | `reviewed-opencost-allocation-v1` | `product`: `1.117.6` |
| Kubecost | `1.0.0` | `reviewed-kubecost-allocation-v1` | `product`: `2.4.0` |
| Reviewed shares | `1.0.0` | `reviewed-allocation-shares-v1` | `projection`: `1.0.0` |

Native labels such as `1.0r2` or `1.2-preview` are not rewritten as semantic versions. A label can be syntactically valid without being characterized by a selected profile. Projection rejects unsupported labels or formats before creating normalized evidence; normalized imports with unsupported profile versions remain blocked. Retain the compatible package for replay of older projections rather than changing a version string to force acceptance.

## FOCUS Financial Semantics

The optional [native CSV handoff](tutorials/reconcile-existing-cost-evidence.md#convert-a-native-focus-export) reads local Cost Management export parts directly, without customer-written preprocessing. It supports only the documented `1.2-preview` dataset, CSV without compression and manifest version `2024-04-01`, within bounded selected scope. Other Cost Details formats, Parquet/Gzip and native OpenCost/Kubecost responses are not converted. Matching these labels does not certify a customer export: validate its actual content and controls in a separately approved pilot.

Prepare the allowlisted projection using the source fields documented in [Microsoft's FOCUS dataset schema](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus). `charge_category` uses `Usage`, `Purchase`, `Tax`, `Credit` or `Adjustment`; `pricing_category` uses `Standard`, `Dynamic`, `Committed` or `Other`, or null where the specification permits it. The earlier labels `Usage-Based` and `On-Demand` are not accepted as FOCUS 1.2 values. The [FOCUS specification](https://focus.finops.org/#specification) defines these semantics independently of the advisor.

The normalized row retains its original charge category, pricing category, correction class and supplied commitment fields in `focus`, alongside its unchanged decimal amount. `Standard` maps to the normalized `OnDemand` pricing model; `Dynamic` remains `Dynamic`, not an inferred Spot purchase. `Committed` remains `Committed`, with the supplied commitment discount ID also retained as `benefit_id`; no reservation or Savings Plan product is guessed from a price.

A positive purchase, tax, credit, adjustment, correction or unused commitment does not become ordinary usage. Those rows remain visible but block the supported row-partition reconciliation. Committed usage additionally needs its benefit ID, category/type and an explicit `Used` consumption status. Missing consumption status is unknown, not evidence that the commitment was used; Microsoft's current dataset documentation lists this status as null/empty, so such rows remain blocked unless independently supported source evidence actually supplies it. Do not invent a status to obtain a reconciled result. Nonfinancial workload checks are unaffected.

## Vendor Pricing Provenance

The [OpenCost allocation API](https://www.opencost.io/docs/integrations/api/#allocation-api) describes standard allocations based on on-demand list pricing. Those estimates can be useful in the customer's existing OpenCost/Grafana workflow, but they are not Azure invoice actuals. This advisor's billing workflow explicitly rejects `pricing_basis: list-price`; it does not convert an estimate to actual, amortized or effective cost.

For OpenCost/Kubecost imports, use `pricing_basis: billing-ledger` only after the FinOps owner has independently reviewed the supplying billing integration, price adjustments, period/currency and allocation settings. Retain that review through the protected `source_reference`; the field is an operator declaration, not authentication or automatic verification. A missing or `source-declared` pricing basis is insufficient for these profiles: projection rejects it, while a normalized import is blocked with `allocation-pricing-unverified`. Even with billing provenance, native aggregate amounts remain `attributed`, not reconciled billing-row partitions or savings.

## Data Handling

Financial projections contain amounts and infrastructure identities. Store them under customer-approved access, encryption, residency, retention and audience controls. Do not commit customer exports, endpoint details, billing identifiers, credentials, arbitrary tags or allocation labels.
