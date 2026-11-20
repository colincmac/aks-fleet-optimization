# Assessment onboarding questionnaire

This is the discovery/profile field reference, not the first learning exercise. Start with [profile preparation](how-to/prepare-an-onboarding-profile.md) for the task and sufficient-answer examples, or the [first lab](accelerator-docs/getting-started.md) if you have not tried the tool.

Complete applicable questions with the application, platform, monitoring, FinOps and security owners before requesting access. Use the [participant workbook](facilitator/participant-workbook.md) to assign unanswered questions and the [assessment sequence](accelerator-docs/assessment-guide.md) for the handoff. Prefer protected references to existing architecture/policy records over copied customer documents. A valid profile is not access approval.

## Choose The Smallest Scope

Choose one cluster and one [entry point](how-to/choose-recommendation-packs.md#three-ways-to-start): current metadata, ordinary CPU measurements in existing Prometheus/Grafana, or optional qualified history and upstream candidate validation. Skip questions and artifacts that do not support the selected check. A metadata question needs no metric endpoint; ordinary CPU measurements need no VPA, historical UID recordings or financial files. Missing advanced evidence affects dependent checks only. Record an owner and a next action, or stop with an intentional no-change/defer decision.

For each selected pack, ask: what has the existing tool already established; what fact is observed; what remains unknown; who owns the next review; and is any extra integration genuinely needed? Do not request a new stack or broader read permissions merely to eliminate all unknowns. Keep application changes and canary/rollback approval in existing delivery processes.

Use the [assessment contract](scenario-coverage.md#assessment-contract) to separate delivered checks from unfinished capabilities. A request to investigate startup, scheduler fit or historical fleet capacity is not proof that those source contracts exist. Record the unsupported claim and next evidence decision rather than substituting probe delays, aggregate free capacity or today's membership. The same person may answer several ownership questions; these responsibilities do not require separate teams.

## Scope and goals

- Which tenants, subscriptions, fleets, clusters, and environments are in scope?
- What business outcome matters: lower cost, higher density, capacity release, chargeback, or reliability?
- Which metric should improve, by when, and what must not regress?
- Which single CPU, memory, capacity or configuration question is selected, and which dimensions are deliberately deferred?

## Optional Saved Fleet Review

Skip this section for a single-cluster engineering question. Fleet Manager is not a prerequisite for composing saved assessments.

- Which original one-cluster assessment bundles, exact cluster resource IDs/fingerprints and declared tenant are permitted inputs? Can each bundle replay with its original configuration and compatible package?
- Which operator-declared peer groups make comparisons meaningful, and which windows, source profiles or settings are not comparable? A group label is not evidence of portability or placement feasibility.
- Is the question about current inventory/resource envelopes, differences between two assessments, or recurrence across selected reports? None supplies continuous history, historical cluster usage or proof that a missing finding was resolved.
- Who will review known and unknown supply/workload dimensions and retain the original evidence dates? Composition time must not refresh old evidence.

## Fleet and workload model

- Shared versus dedicated clusters and the reason for each?
- Namespace, node-pool, or cluster isolation boundaries?
- Fixed pools, cluster autoscaler, NAP/Karpenter, or mixed modes?
- Approved VM families, Spot usage, reservations, and capacity constraints?
- Custom scheduler profiles, admission mutation, placement policies, or fleet placement?
- Workload classes: interactive, batch, streaming, GPU, stateful, and legacy?

## Observability

- Which existing Prometheus/Grafana source and approved query/read access can answer the selected question, or can its owner supply saved fragments?
- What are the selected catalog metric names, units, effective label mappings, retained window and resolution? Ordinary CPU needs usage/request series and exact cluster resource-ID/namespace/Pod/container labels; qualified history additionally needs the explicit UID/roster contract, not today's name association.
- Are optional advanced recordings already present and independently owned? If not, can this check be deferred without changing the source?
- Expected business peaks, load tests, batch windows, and failover exercises?
- Known collection gaps, sampling, aggregation, or label restrictions?

Complete the [source compatibility worksheet and proposed pilot plan](source-compatibility.md) with the source owner. Retention alone does not establish historical UID/request/membership evidence or approved recording semantics. Keep actual source records outside the repository; live validation requires separate, explicit operator consent.

## FinOps

This section is optional for engineering-only questions. Do not request billing files or a new cost-tool deployment for current metadata or ordinary CPU observations.

- Which existing tools are in use: Cost Management/FinOps hubs, AKS Cost Analysis, Azure Advisor, the [Cost Optimization workbook](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/workbooks/optimization), [Azure Optimization Engine](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/optimization-engine/overview), VPA, OpenCost or Kubecost? Record relevant product/profile/version and protected evidence references; do not deploy every option.
- Which existing findings or candidates have owners already reviewed, and what advanced question remains unresolved?
- Is the financial evidence actual, amortized or reviewed FOCUS effective cost, for which period and currency?
- What are the allocation dimensions and explicit rules for idle/shared/system/service/unallocated cost?
- For optional allocation qualification, are the declared tenant/subscription, exact cluster/fingerprint, genuine source-observation time and financial period available? Qualification must match the original replay-verified assessment period; it is not reconciliation, source authentication or cost-based finding ordering.
- Does the saved projection match a characterized [financial source profile](financial-source-profiles.md), including producer version and identity limits?
- Existing showback/chargeback and approved discounts?
- If using AKS Cost Analysis, has the platform/FinOps owner checked its [offer, tier, scale, latency and identity limits](financial-source-profiles.md#aks-cost-analysis-applicability)? Unsupported or delayed views are an optional-source gap, not an instruction to change the platform or block workload analysis.
- Who receives the result in the current workbook/AOE/cost-tool or engineering triage workflow? A protected report link in an existing record is sufficient; no native outbound connector is supplied. Distinguish managed-product support from [as-is toolkit support](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/help/support).

## Optional Offline AI Review

Skip this section for ordinary analysis. No AI deployment, model or external disclosure is needed for assessment or the offline handoff.

- Is a local pseudonymous finding-summary export separately permitted, for which original bundles, audience, destination and retention? Pseudonyms and hashes are not anonymization or permission to upload.
- Is the task an explanation or a closed review checklist bound to one exact package/scope/objective? Accepted output remains an unverified draft, not validated advice, readiness or approval.
- Can validation regenerate the package from the original bundles and check exact copied facts, citations and clocks? Raw measurements, metadata/owner prose, financial context and executable fields are not part of the summary release.
- Would the question need richer records or model invocation? Those are separate, unfinished capabilities requiring explicit data/provider/network/spend decisions, not an extension of existing summary consent. See the [offline handoff](operations/ai-evidence.md).

## Safety and governance

- SLOs, PDBs, topology, failover, and recovery requirements?
- Change, canary, and rollback processes?
- Required data residency and private networking?
- Approved read-only identities and report audience?

## Requested artifacts

Request only applicable artifacts through existing owners and protected storage:

| Selected question | Minimum artifact handoff |
| --- | --- |
| Current configuration | Sanitized current cluster/workload/Pod metadata and relevant scheduling/controller fields, exact scope/fingerprint, complete receipts and declared owner/environment |
| Ordinary CPU observations | Approved saved metric fragments or selected query/label definitions from existing monitoring; no credentials, arbitrary label dumps or historical-UID invention |
| Qualified candidate validation | Exact historical identity/roster and selected metric history, admitted requests, independent owner peak/reliability policy, and supported saved VPA status with honest generation-age evidence; see the [handoff](operations/runbook.md#saved-vpa-request-candidates) |
| Optional fleet/comparison question | Explicit original one-cluster assessment bundles, declared tenant, exact identities, compatible configuration/package and peer groups; no fleet service or financial input required |
| Optional financial question | Supported sanitized ledger/allocation projections, or approved protected local FOCUS CSV/manifest inputs plus review controls for the [offline converter](tutorials/reconcile-existing-cost-evidence.md#convert-a-native-focus-export); no raw exports in reports, workshop records, Git or error logs |
| Optional offline AI review | Separately consented local summary package regenerated from original bundles, and a closed explanation/checklist draft with exact citations; no provider credentials or richer telemetry release |

Representative load-test dates and independent canary/rollback evidence are needed only for a separately approved change question, not for starting a current-metadata investigation. All saved evidence still requires existing classification, ACLs, encryption and retention.

## Versioned onboarding profile

Use the answers above to prepare a profile using the [synthetic example](../examples/onboarding-config.yaml). Its [schema](../schemas/onboarding-config.schema.json) and fleet snapshots use schema 1.0. `readiness`, `configure`, `preview`, `collect` and `assess` accept an onboarding profile containing `analysis`; `analyze` accepts that analysis-only configuration, including saved `analysis-config.json`. See the [version/contract matrix](recommendation-packs.md#supported-contracts).

- `scope` requires one tenant UUID and a nonempty, duplicate-free subscription allowlist.
- Optional `clusters` contain exact AKS resource IDs, named metric-source references, and environment classifications. IDs must belong to the subscription allowlist. An empty cluster list does not mean discovery has succeeded; review and approve an explicit collection plan before live reads.
- `metric_sources` declare HTTPS endpoints, authentication strategy, label mappings, retention, and resolution. Declarations are not verified endpoint facts. Credentials, URL user information, query parameters, and fragments are rejected.
- Generic sources support `anonymous` or `bearer-environment`. Bearer profiles contain only `token_environment_variable`, an environment-variable name, never its value. Offline readiness neither reads that variable nor authenticates. Anonymous authentication in the example is synthetic, not a production recommendation.
- Managed Prometheus profiles use `type: azure-managed-prometheus` and `authentication: default-azure-credential`. Offline readiness obtains no token and validates no live access. Only separately approved live collection constructs the tenant-bound public-Azure reader; workspace permissions, private connectivity and actual retained labels still need pilot validation.
- `label_mapping` supplies source-wide defaults. Optional `query_label_mappings` are partial overrides keyed by installed catalog query ID for sources whose metric families use different label names. Every effective mapping selected by the configured pack/mode must contain distinct required cluster resource ID, namespace, workload kind, workload and container labels as applicable. Overrides do not translate returned values or attest that differently named labels identify the same cluster. The source must also expose the canonical historical UID/digest labels required by the selected entity kind; those labels are not configurable aliases. Name-only series cannot be enriched from current metadata to reconstruct history. See the [mapping requirements](source-compatibility.md#identity-and-series-mapping).
- `ownership` maps exact cluster/namespace pairs to declared owners and optional policy references. These mappings do not grant permissions, create workload safety policies, or approve changes.
- `report_directory` is a filesystem destination, resolved relative to the profile file when loaded. Loading and readiness evaluation do not create it or test write access. `analysis` optionally embeds the existing thresholds and risk configuration.

The example uses zero UUIDs, synthetic owners, and an intentionally invalid example endpoint. It is not a customer inventory and must not be used to claim live readiness.

## Offline readiness

```bash
aks-fleet-advisor readiness \
	--config examples/onboarding-config.yaml \
	--as-of 2026-10-29T12:00:00Z \
	--format markdown
```

Add `--snapshot path/to/snapshot.json` to check normalized evidence against the profile, or `--output readiness.json --format json` to write the report explicitly. The configured destination is not written automatically, and missing output-parent directories are not created. Omit `--as-of` for current-time evaluation.

Checks distinguish declared configuration from observed snapshot evidence and unknown live access. Set `analysis.packs` and `analysis.mode` to the chosen question first. Readiness gates only that mode and the metric sources referenced by the selected clusters; inventory-only selection omits metric-source/history/quality prerequisites and requires only its inventory collectors. Supplied snapshots retain exact scope, tenant and freshness checks. For metric selection, duration/coverage and selected normalized CPU/throttling/OOM query quality are checked; other dimensions and unresolved measurements require their selected assessment's own gates. Unselected guarded requirements do not block baseline readiness. Incompatible selected evidence is blocked; absent evidence remains unknown. Endpoints, credentials, actual retained series, Kubernetes permissions, destination access, and retention approval are never inferred from declarations.

Per-source `source.historical_identity`, `source.recording_semantics`, `source.provenance` and `source.network` checks expose unresolved pilot evidence explicitly. They stay unknown even with a valid supplied snapshot; offline readiness does not ingest operator approvals or attest source completeness. `source.labels` checks declarations, including `workload_kind`, not the actual retained label population.

| Exit | Meaning |
| --- | --- |
| `0` | Ready; the offline evaluator does not produce this status because live access and source facts remain unverified. |
| `1` | Report output could not be written. |
| `2` | Invalid arguments, configuration, snapshot, or evaluation timestamp. Sensitive input values are not echoed. |
| `3` | Unknown: no known blockers, but required evidence or live checks are unverified. Expected for the synthetic example. |
| `4` | Blocked: a configured requirement or supplied evidence fails a readiness check. |

The [readiness-report schema](../schemas/readiness-report.schema.json) uses version `1.0`. Reports include stable check codes, scope, status, messages, and configuration/optional snapshot digests. They intentionally omit endpoint URLs, owner values, credentials, and raw samples. Treat reports as environment data and apply the existing [security guidance](security-and-privacy.md).

No Azure or Kubernetes SDK call, endpoint request, role assignment, resource installation, or cluster mutation occurs in this mode. Live authentication, discovery, metric-series/label probes, and network checks remain work for the collection adapters. Offline status `unknown` is not production readiness or change approval; fix blockers and obtain live evidence through the approved collection path.
