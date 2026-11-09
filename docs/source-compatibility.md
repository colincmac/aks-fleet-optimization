# Brownfield Source Compatibility

This reference specifies exact input shapes and source-review evidence. Here
source means an inventory, configuration or monitoring system/file, not code.
For a step-by-step owner task and a fictional sufficient-answer example, use
[check whether your data can answer the question](how-to/validate-source-compatibility.md).
For the underlying concept, read [data quality and identity](learning/04-evidence-quality-and-historical-identity.md).

Use this worksheet to verify whether your existing inventory and telemetry can
support the selected assessment. The shapes below are adapter contracts
characterized with synthetic data, not verified product defaults or a
requirement to replace existing telemetry. Actual source compatibility requires
approved environment-specific evidence.

Use the [onboarding profile](../examples/onboarding-config.yaml), [contracts](data-contracts.md), [query catalog](../src/aks_fleet_efficiency/collectors/prometheus.py) and [collector runbook](operations/runbook.md#prometheus-metrics-api) together. Offline `readiness` does not query endpoints, ingest this worksheet, or validate its approvals.

## Supported Shapes

Transport and historical semantics are separate compatibility decisions. A successful HTTPS request does not establish identity, complete history, safe recommendations or read-only identity permissions.

| Source shape | Currently usable boundary | Evidence required before pilot acceptance |
|---|---|---|
| Sanitized metadata export | CLI import and offline current inventory; no metric history inferred. | Approved exporter/version, exact tenant/cluster and independent `kube-system` UID, versioned resource lists and field exclusions. |
| Current HPA/VPA configuration | `AKS-AS-002` current request-denominator review; no historical metric or controller-behavior claim. | Approved current target references and unique Namespace/workload identities, successful HPA/VPA lists, explicit HPA target type and VPA update/container modes/resources. Exports missing container `mode` stay unknown; do not infer defaults or treat this review as permission to rightsize active controllers. |
| UID-bound HPA replica history | `AKS-AS-003` sampled floor/ceiling/fixed-bound investigation; no replica target or demand diagnosis. | Explicit binding `hpa_uid`, historical target workload UID, approved full-window min/max/desired/current gauges, fresh matching current bounds/status and source provenance. Today's associations cannot relabel history; missing, recreated or changing-controller histories stay blocked. |
| Current KEDA/VPA supplemental evidence | `AKS-AS-004` generated-controller/activation and `AKS-AS-007` VPA bounds investigations. | Explicit ScaledObject target/trigger/bounds/polling/cooldown, versioned API lists, current `status.hpaName` and exact HPA controller owner; explicit VPA container status/policy quantities. No trigger metadata/authentication values are retained. Missing fields/defaults stay unknown. |
| Opted-in HPA minimum proposal | `AKS-AS-005`, only for an unconstrained homogeneous Deployment with one unmanaged HPA; no zero target or vertical change. | Seven complete aligned HPA/workload replica series, current Deployment availability, exact configuration digest, explicit owner-reviewed tested count, peak/startup/throughput/zone/failover/disruption/reliability evidence and zero reviewed incident counts. References are not attestation. Unsupported PDB/state/scheduling/KEDA/controller shapes stay blocked. |
| Generic Prometheus-compatible HTTPS | Fixed `/api/v1/query_range`, approved anonymous access or explicitly injected bearer credential in the library. CLI supports anonymous generic sources, not implicit bearer environment reads. | Endpoint ownership, authentication/client provenance, permission review, retained catalog series and runner network validation. |
| Public-Azure managed Prometheus | Tenant-bound noninteractive credential and approved `*.prometheus.monitor.azure.com` query endpoint. | Workspace binding, approved credential chain/principal, workspace-scoped `Monitoring Data Reader` review, retained series and network validation. Sovereign-cloud compatibility is not implemented. |
| Identity-enriched direct container history | Exact historical Pod/workload UIDs; bounded request proposals and separately default-off single-Pod memory limits. | Existing full-window UID enrichment and constant admitted request/limit history. Limits additionally need full-memory usage, zero full workload eviction/OOM/restart history, current admission lists and configuration-bound allocator/scenario review. Working set alone is insufficient. |
| Approved replica envelope | Conservative per-replica upper envelope for homogeneous replicas or an approved churned roster; not a workload-total percentile. | Reviewed upstream producer/definition, complete historical roster including deleted Pods, exact digest, stable requests/counts, complete guardrail history and current metadata. |
| Historical node/pool recordings | Aligned sum-before-percentile CPU review with independently verified full-window membership and constant capacity. | Exact node resource IDs/UIDs and pool binding, deleted-node history, aligned usage and constant allocatable capacity. Current nodes cannot establish historical membership. |
| Memory/restart replica envelopes | Memory request proposals and restart investigations over a complete digest-bound historical roster; not workload-total percentiles or replica-limit proposals. | Aligned max working set, constant request/limit min/max, full integral restart/OOM interval totals, stable desired/observed/available/controller history, current absence/overhead/QoS/admission and reviewed policy. Deleted members must be included; no survivor extrapolation. |
| Workload evictions and current termination | Full-window workload counter plus separate UID-bound last-state metadata; no inferred root causes. | Approved historical `evictions` producer with exact workload UID and disjoint intervals. Current status may expose only reason/exitCode/finishedAt; never messages/log bodies. Missing counts/context stay unknown. |
| Name-only series, unknown recordings or unsupported network/auth | Inventory-only findings may remain useful; affected metric findings stay partial/blocked. | Record the gap and supported subset. Do not synthesize UIDs, assume zero/absence, install telemetry or weaken TLS/identity checks. |

Raw cAdvisor/kube-state-metrics availability alone is insufficient for guarded
history assessment: the advisor currently selects historical identity labels directly and does not execute arbitrary source-specific enrichment joins. Approve an existing history-aware upstream mapping or record the profile as unsupported for that analysis. New recordings cannot backfill missing historical labels or observations.

## Identity And Series Mapping

Select the explicit [name-only source profile](source-profiles.md) when your
telemetry lacks historical identities.
Ordinary CPU/request series can be retained as unresolved baseline measurements
with per-pack capability gaps. This performs no ownership/history enrichment,
does not infer absent series as zero and does not authorize numeric targets.
Generic/managed source shapes are synthetically characterized, not live accepted.

The profile maps five logical labels: `cluster_resource_id`, `namespace`, `workload_kind`, `workload`, `container`. Values are source label names, not aliases for arbitrary resource names. Exact Azure resource-ID values must already exist in returned series. Labels must be distinct and must not overwrite the canonical identity labels used by the selected entity kind.

Canonical labels are not configurable through `label_mapping`: direct container history uses `workload_uid` and `pod_uid`; workload history uses `workload_uid`; HPA history uses `workload_uid` and `hpa_uid`; replica envelopes use `workload_uid` and `membership_digest`; nodes use `node_resource_id` and `node_uid`. Namespace UID and cluster fingerprint bindings come from approved metadata/assessment contracts, not invented Prometheus labels. Names/kinds/container labels scope selectors but do not replace UIDs.

Record an approved definition and retained-window evidence for every selected catalog key. This table describes supported metric mappings; inventory-only scheduling reviews do not require these series.

| Catalog keys | Required source expression or recording semantics |
|---|---|
| `cpu_usage` | `rate(container_cpu_usage_seconds_total[5m]) * 1000`, selected by complete identity; mCPU. The rate needs source samples before the first evaluation point. |
| `cpu_request` | `kube_pod_container_resource_requests` with `resource="cpu",unit="core"`, converted to mCPU; historical admitted request, not today's template. |
| `memory_request`, `memory_limit` | `kube_pod_container_resource_requests` / `kube_pod_container_resource_limits` with `resource="memory",unit="byte"`, converted to MiB. Direct single-Pod history must be complete, constant and independently match the current admitted value. Missing series does not prove absence; current metadata does not backfill history. Generic replica/churn aggregation is unsupported; approved complete-roster memory envelopes use the separate `replica_memory_*` contract below. |
| `cpu_throttling` | Rates of `container_cpu_cfs_throttled_periods_total` divided by `container_cpu_cfs_periods_total`; ratio. Missing/undefined ratios remain unknown. |
| `oom_events` | Complete disjoint `increase(container_oom_events_total[step])` intervals; events. Absent series is not zero OOMs. |
| `restarts` | Complete disjoint `increase(kube_pod_container_status_restarts_total[step])` intervals; events, bound to the exact historical workload/Pod/container. Direct single-Pod restart investigations require a complete integral total; current lifetime counters, fractional estimates and replica/churn aggregates are not substituted. |
| `desired_replicas`, `available_replicas`, `observed_replicas` | `aks_advisor:workload_desired_replicas`, `aks_advisor:workload_available_replicas`, `aks_advisor:workload_observed_pods`; explicit aligned counts bound to workload UID. |
| `hpa_present`, `keda_present`, `vpa_present` | `aks_advisor:workload_hpa_present`, `aks_advisor:workload_keda_present`, `aks_advisor:workload_vpa_present`; explicit zero/one history. Missing recording or denied API is not absence. Independent current discovery/list evidence is also required. |
| `hpa_min_replicas`, `hpa_max_replicas`, `hpa_desired_replicas`, `hpa_current_replicas` | Corresponding `aks_advisor:hpa_*_replicas` gauges in pods, carrying canonical HPA and historical target workload UIDs. Full aligned min/max/current/desired history must exist for that exact controller and period; min/max must be constant and match fresh current bounds for the supported pinning check. These optional recordings are not assumed installed, reconstructed from current settings, or backfilled. |
| `replica_cpu_envelope` | `aks_advisor:workload_container_cpu_max_mcores`; aligned maximum across the complete approved historical roster, with its `membership_digest`. No summing or averaging percentiles. |
| `replica_cpu_request_min`, `replica_cpu_request_max` | Corresponding `aks_advisor:workload_container_cpu_request_min_mcores` and `aks_advisor:workload_container_cpu_request_max_mcores`; both constant at the current admitted request. |
| `replica_cpu_throttling`, `replica_oom_events` | `aks_advisor:workload_container_cpu_throttling_max` and `aks_advisor:workload_container_oom_increase`; maximum per-replica throttling and complete OOM increases. OOM recording also binds `step_seconds`. |
| `replica_memory_envelope`, `replica_memory_request_min/max`, `replica_memory_limit_min/max` | `aks_advisor:workload_container_memory_max_mib` and corresponding request/limit min/max MiB recordings; aligned max across the complete digest-bound roster. Requests and limits must be constant and match current admitted values. |
| `replica_restarts`, `evictions` | `aks_advisor:workload_container_restart_increase` (roster-bound container aggregate) and `aks_advisor:workload_eviction_increase` (workload UID total); disjoint complete intervals with explicit `step_seconds`, integral totals and no missing-to-zero conversion. |
| `memory_total_usage` | `container_memory_usage_bytes / 1048576` at the exact historical Pod/container identity. Full-memory percentiles/extrema and independent owner allocator/cache/startup/failover review are mandatory for limits; working set is not a substitute. |
| `node_cpu_usage`, `node_allocatable_cpu`, `node_allocatable_memory` | `aks_advisor:node_cpu_usage_mcores`, `aks_advisor:node_allocatable_cpu_mcores`, `aks_advisor:node_allocatable_memory_mib`; exact historical node identities, mCPU/MiB and approved pool membership. |

These `aks_advisor:*` names are adapter requirements, not built-in AKS recordings. Do not install them as part of assessment or equate matching names with reviewed semantics. OOM/restart investigations do not establish safe memory targets or source compatibility. Select queries from the pack's catalog dependencies; collecting additional series does not enable an unsupported analysis.

## Pilot Evidence Worksheet

Complete one record per source and approved scope in the operator's access-controlled evidence store. Reference it by opaque identifier, revision, reviewer and UTC review time. Do not commit customer telemetry, endpoints, identities, label dumps, recording bodies or credentials here. Summaries, receipts and reports still need classification, retention and audience controls. A reference/hash is an integrity identifier, not source attestation or approval.

Complete every applicable row with independently reviewed source evidence. No
row is satisfied by the synthetic examples.

| Record | Evidence to obtain and decision to record |
|---|---|
| Scope and ownership | Explicit tenant/subscription/cluster/workspace allowlists, environment, source owner, platform/security reviewers, intended assessment families and excluded scopes. |
| Series inventory | Approved catalog inventory/definition references; required metric presence and units for each entity kind. Prefer existing owner-produced sanitized evidence; no unbounded series/label/configuration dump. |
| Historical identities | Label mapping and uniqueness, historical workload/Pod/node UIDs and Namespace binding, handling of recreated names/deleted members, enrichment producer and approved historical roster. |
| Recordings | Versioned producer/definition and review, first available date, membership digest calculation, max-envelope and counter semantics, gaps and evidence of unavailable history. |
| Retention and resolution | Actual earliest/latest usable observations for selected series, UTC interval, retained step/downsampling across the whole interval, raw scrape/rate lookback support and known gaps. Thirty retained days alone does not establish compatibility. |
| Requests and replicas | Full-window admitted request min/max, observed/desired/available replicas and controller histories. Changing requests/replicas stay unsupported, not extrapolated. |
| Node/pool history | Full historical membership, pool/resource bindings, constant allocatable CPU/memory, alignment and node churn; otherwise block pool assessment. |
| Credentials and permissions | Approved credential-chain/client/exporter origin and version, tenant/audience/workspace binding, administrator-reviewed effective read-only roles including inherited permissions. No token, kubeconfig or secret values; no access-review POSTs. |
| Endpoint and fingerprint | Trusted endpoint owner/configuration reference and independently established cluster fingerprint provenance. A UID copied only from the endpoint under test is not independent verification. |
| Network and TLS | Intended in-network runner, private DNS/routes, approved outbound destinations, proxy and CA requirements. Built-in metrics transport verifies TLS, refuses redirects and ignores environment proxy/CA overrides. Unsupported integration needs a separately reviewed path, never a TLS bypass. |
| Safety and data handling | Owner policy/SLO and reviewed representative window, sanitized export approval, storage ACLs, encryption, retention/deletion, report audience and incident contact. No raw samples in advisor artifacts. |
| Outcome | For each intended family: supported shape with evidence, blocked known gap, or unknown pending evidence; accountable owner and next action. No fleet-wide pass from one healthy target. |

## Bounded Validation Plan

This is a validation template, not consent or executable configuration. Offline
`readiness` is not a live probe. Do not execute live commands, acquire tokens or
contact source endpoints until the applicable approval is recorded.

1. **Offline preparation:** run synthetic characterization and `readiness` with approved saved inputs. Select the smallest useful shape and record missing evidence without changing the source. Inventory-only assessment is valid when historical metrics are unsupported.
2. **Evidence review:** the source/platform owners supply the worksheet evidence through an approved path. Review fingerprint/exporter provenance, effective read-only permissions, query semantics and privacy/network requirements. Treat any additional source-inventory queries as live access requiring their own prior approval; the advisor has no series-enumeration probe.
3. **Consent gate:** approve exact nonproduction scope, source/endpoints, principal/client/runner, query catalog subset, entity/roster bindings, UTC window/step, output destination/retention, budgets and test cases. Record approvers, UTC validity/expiry, stop contact and approval reference in the external pilot record. A configured endpoint, issue, digest or `--allow-live` flag alone is not operator approval.
4. **Small live slice, only after consent:** start with one nonproduction cluster, one workload/container or approved pool and selected required metrics. Use approved sanitized Kubernetes exports for the CLI. Initially test a short explicit interval to establish transport/shape only; it cannot satisfy the 30-day recommendation gate. Then query the full approved representative window without silently reducing minimums.
5. **Bounded failure cases:** use synthetic/injected denied scope, missing series/UID, stale/sparse history, absent recording, mismatched digest and expired approval. Real denied-scope or alternate-network tests require explicit listed authorization; never probe an unapproved target. Stop on identity/TLS mismatch, unsafe fields, unexpected privileges, budget exhaustion or withdrawn/expired consent. Do not broaden scope or retry with stronger permissions.
6. **Offline acceptance and replay:** review source-specific partial/blocked receipts and each entity's coverage/freshness/units, exact historical bindings and unsupported cases. Export exclusive artifacts, replay with the same configuration/clock, and obtain platform/security/source-owner signoff outside the repository. Healthy inventory findings may coexist with blocked historical findings; savings stay null. Authorize broader/production scope separately.

Proposed initial run ceilings, subject to explicit lower/equal operator approval: one cluster, at most ten explicit historical entities, 500 reads, 5,000 objects, 500 range-query chunks, 300 elapsed seconds, zero collector retries and sequential execution. Keep HTTP limits at most 30 seconds/request, 16 MiB/response and 1,000 series/response. Preflight the planned query count; if the full selected window does not fit, narrow the approved subset or obtain revised approval, not a shorter undeclared window. The elapsed deadline is cooperative and cannot interrupt an already running injected reader.

Use the existing [collection plan](../examples/collection-plan.json) only as a synthetic format example. Do not commit the populated pilot plan or silently treat it as approved. Operators must retain independent transport timeouts and a way to stop the runner.

## Offline Characterization

The [metrics tests](../tests/test_prometheus.py) reuse synthetic `matrix`, `labels`, `profile` and `FakeMetricReader` fixtures. They characterize mapped cluster/Namespace/controller/container names with canonical UIDs for CPU/request/throttling/OOM, missing historical UIDs, absent replica/controller recordings and missing/mismatched roster digests. Existing tests also cover aligned percentiles, sum-before-percentile pools, unverified node membership, partial/stale history and bounded mocked HTTPS/authentication. The [assessment tests](../tests/test_assessment.py) exercise the separate normalization/policy guards.

The [readiness tests](../tests/test_readiness.py) demonstrate that declarations and a supplied normalized snapshot cannot clear `source.historical_identity`, `source.recording_semantics`, `source.provenance` or `source.network`. These checks remain `unknown` even when declared labels/retention and snapshot history pass. Missing `workload_kind` mapping blocks `source.labels`, matching the container/workload collector requirement. Offline readiness never becomes proof of pilot acceptance.

Run the focused checks without network access:

```bash
python -m pytest tests/test_readiness.py tests/test_prometheus.py -q
```

Accept a source only after its mapping, approved evidence, nonproduction
validation and outcome have been reviewed by the source, platform and security
owners. Neither this worksheet nor synthetic tests certifies your environment.