# Assessment onboarding questionnaire

This is the discovery/profile field reference, not the first learning exercise.
Start with [profile preparation](how-to/prepare-an-onboarding-profile.md) for
the task and sufficient-answer examples, or the
[first lab](accelerator-docs/getting-started.md) if you have not tried the tool.

Complete applicable questions with the application, platform, monitoring,
FinOps and security owners before requesting access. Use the
[participant workbook](facilitator/participant-workbook.md) to assign unanswered
questions and the [assessment sequence](accelerator-docs/assessment-guide.md)
for the handoff. Prefer protected references to existing architecture/policy
records over copied customer documents. A valid profile is not access approval.

## Scope and goals

- Which tenants, subscriptions, fleets, clusters, and environments are in scope?
- What business outcome matters: lower cost, higher density, capacity release, chargeback, or reliability?
- Which metric should improve, by when, and what must not regress?
- Are CPU, memory, GPU, storage, network, or observability costs in the first phase?

## Fleet and workload model

- Shared versus dedicated clusters and the reason for each?
- Namespace, node-pool, or cluster isolation boundaries?
- Fixed pools, cluster autoscaler, NAP/Karpenter, or mixed modes?
- Approved VM families, Spot usage, reservations, and capacity constraints?
- Custom scheduler profiles, admission mutation, placement policies, or fleet placement?
- Workload classes: interactive, batch, streaming, GPU, stateful, and legacy?

## Observability

- Prometheus-compatible endpoint and retention?
- Metric names or recording rules for CPU, memory, throttling, pending pods, and SLOs?
- Expected business peaks, load tests, batch windows, and failover exercises?
- Known collection gaps, sampling, aggregation, or label restrictions?

Complete the [source compatibility worksheet and proposed pilot plan](source-compatibility.md) with the source owner. Retention alone does not establish historical UID/request/membership evidence or approved recording semantics. Keep actual source records outside the repository; live validation requires separate, explicit operator consent.

## FinOps

- AKS Cost Analysis/OpenCost enabled?
- Amortized cost feed and currency?
- Allocation dimensions and rules for idle/system/unallocated cost?
- Existing showback/chargeback and approved discounts?

## Safety and governance

- SLOs, PDBs, topology, failover, and recovery requirements?
- Change, canary, and rollback processes?
- Required data residency and private networking?
- Approved read-only identities and report audience?

## Requested artifacts

- Sanitized cluster/node-pool configuration export.
- Workload policy and scheduling configuration summary.
- Metric catalog or dashboard definitions.
- Cost allocation schema/sample.
- Ownership mapping and environment classification.
- Representative load-test or peak-period dates.

## Versioned onboarding profile

Use the answers above to prepare a profile using the [synthetic example](../examples/onboarding-config.yaml). Its [schema](../schemas/onboarding-config.schema.json) and fleet snapshots use schema 1.0. `readiness`, `configure`, `preview`, `collect` and `assess` accept an onboarding profile containing `analysis`; `analyze` accepts that analysis-only configuration, including saved `analysis-config.json`. See the [version/contract matrix](recommendation-packs.md#supported-contracts).

- `scope` requires one tenant UUID and a nonempty, duplicate-free subscription allowlist.
- Optional `clusters` contain exact AKS resource IDs, named metric-source references, and environment classifications. IDs must belong to the subscription allowlist. An empty cluster list does not mean discovery has succeeded; review and approve an explicit collection plan before live reads.
- `metric_sources` declare HTTPS endpoints, authentication strategy, label mappings, retention, and resolution. Declarations are not verified endpoint facts. Credentials, URL user information, query parameters, and fragments are rejected.
- Generic sources support `anonymous` or `bearer-environment`. Bearer profiles contain only `token_environment_variable`, an environment-variable name, never its value. Offline readiness neither reads that variable nor authenticates. Anonymous authentication in the example is synthetic, not a production recommendation.
- Managed Prometheus profiles use `type: azure-managed-prometheus` and `authentication: default-azure-credential`. Offline readiness obtains no token and validates no live access. Only separately approved live collection constructs the tenant-bound public-Azure reader; workspace permissions, private connectivity and actual retained labels still need pilot validation.
- Label mappings must declare distinct cluster resource ID, namespace, workload kind, workload, and container labels. The source must also expose the canonical historical UID/digest labels required by the selected entity kind; those labels are not configurable aliases. Name-only series cannot be enriched from current metadata to reconstruct history. See the [mapping requirements](source-compatibility.md#identity-and-series-mapping).
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

Checks distinguish declared configuration from observed snapshot evidence and unknown live access. Supplied snapshots are checked for exact scope and tenant, required collector completeness/freshness, observation duration/coverage, and per-container CPU/throttling/OOM quality. Incompatible evidence is blocked; absent evidence remains unknown. Endpoints, credentials, actual retained series, Kubernetes permissions, destination access, and retention approval are never inferred from declarations.

Per-source `source.historical_identity`, `source.recording_semantics`, `source.provenance` and `source.network` checks expose unresolved pilot evidence explicitly. They stay unknown even with a valid supplied snapshot; offline readiness does not ingest operator approvals or attest source completeness. `source.labels` checks declarations, including `workload_kind`, not the actual retained label population.

| Exit | Meaning |
|---|---|
| `0` | Ready; the offline evaluator does not produce this status because live access and source facts remain unverified. |
| `1` | Report output could not be written. |
| `2` | Invalid arguments, configuration, snapshot, or evaluation timestamp. Sensitive input values are not echoed. |
| `3` | Unknown: no known blockers, but required evidence or live checks are unverified. Expected for the synthetic example. |
| `4` | Blocked: a configured requirement or supplied evidence fails a readiness check. |

The [readiness-report schema](../schemas/readiness-report.schema.json) uses version `1.0`. Reports include stable check codes, scope, status, messages, and configuration/optional snapshot digests. They intentionally omit endpoint URLs, owner values, credentials, and raw samples. Treat reports as environment data and apply the existing [security guidance](security-and-privacy.md).

No Azure or Kubernetes SDK call, endpoint request, role assignment, resource installation, or cluster mutation occurs in this mode. Live authentication, discovery, metric-series/label probes, and network checks remain work for the collection adapters. Offline status `unknown` is not production readiness or change approval; fix blockers and obtain live evidence through the approved collection path.
