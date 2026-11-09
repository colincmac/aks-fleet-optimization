# Operations runbook

For customer adoption, start with the [documentation home](../README.md) and
[assessment guide](../accelerator-docs/assessment-guide.md). This runbook is the
technical reference for installation, approved collection and replay, not an
instruction to deploy a production service.

For an operator-run demo on your own AKS clusters, use the
[operator demo walkthrough](operator-demo.md). It includes isolated
test workloads, optional HPA/PDB cases, get/list-only reader manifests, local
profile/plan templates and an explicitly opted-in projected-inventory helper.
Real current inventory, synthetic historical examples and the local synthetic
Headlamp preview stay separate. No customer pilot or live acceptance is implied.

## Preflight

1. Confirm subscription and cluster allowlists.
2. Verify the identity has Reader and the minimal Kubernetes ClusterRole only.
3. Confirm the metric window contains representative periods.
4. Verify report storage classification, retention, and audience.
5. Run offline `readiness` and `preview`; perform a bounded collection only
   after independent approval. Neither offline command verifies live access.

## Installation and preflight

The supported package is `aks-fleet-efficiency-advisor` `0.1.0`
on Python 3.12+. Use an approved package feed or a wheel built from the reviewed
checkout; do not mix source code, installed package assets or older development
schemas. See [setup and verification](../../CONTRIBUTING.md) and the
[contract/version matrix](../recommendation-packs.md#supported-contracts).
Offline analysis needs the runtime dependencies; admitted Kubernetes quantity
parsing needs the `kubernetes` extra. Explicit approved collection also needs
`azure,metrics`. No install command grants roles or starts collection.

Review only the permissions needed by the selected packs: Azure Reader on the
approved inventory scope, the [minimal projected Kubernetes reader](../security-and-privacy.md#kubernetes-clusterrole-sketch),
and approved read/query access to the selected metric endpoint (including the
managed workspace's required metrics-reading role). Verify the actual identity
has no write grants; a read-only request path does not prove least privilege.
Inventory-only packs need no Prometheus access. Do not grant Secrets, logs,
Events, exec or mutation access to repair a missing-evidence result.

For private clusters, the CLI consumes approved sanitized metadata exports
with an independently verified cluster fingerprint; it does not open a tunnel,
execute kubeconfig plugins or fetch credentials. Run any separately approved
live readers from a location with approved DNS/routing/firewall connectivity.
Metric HTTP requests verify TLS, reject redirects and ignore ambient proxy
settings. Custom proxy/CA/cloud requirements remain pilot work: do not disable
TLS or broaden scope as a workaround. Keep customer artifacts only in approved
encrypted/ACL-protected locations with reviewed retention, never in fixtures.

### Installation troubleshooting

| Symptom | Safe next step |
|---|---|
| Missing packs or invalid installed assets | Reinstall/rebuild the complete reviewed wheel; all 21 manifests, queries and source profiles must be present. Do not substitute rule definitions from another version. |
| Invalid plan or unknown query key | Review the plan against `catalog show` and select supported dependencies; do not manufacture history or silently substitute another query. |
| Pack lock mismatch | Keep the original artifacts intact. Use their exact original reviewed package, or explicitly create a new assessment/configuration from approved evidence; do not edit the saved digest to claim identical replay. |
| Report fails schema validation | Check the supported schema and original package/configuration; do not edit the evidence or saved locks to conceal a mismatch. |
| Denied/unreachable source, missing/low-coverage/stale history | Inspect the scoped receipt, capability reason codes and query preview; have the operator validate approved identity/network/retention. Never coerce absence to zero or relax safety gates. |
| Unknown ordinary-telemetry workload identity | Use unresolved baseline measurements, or independently provide retained UID/roster evidence. Current Pod names cannot backfill history. |
| Partial assessment exit `3` or no recommendations | Inspect blocked findings and source gaps; this is not a healthy-fleet result. |
| Pinned `promtool` is missing or its checksum differs | Follow the approved setup in the source-profile guide. Do not execute a mismatched binary or change the lock to bypass the integrity check. |

## Onboarding readiness

Prepare the versioned profile described in the [onboarding guide](../onboarding-questionnaire.md), then run `aks-fleet-advisor readiness --config onboarding.yaml`. Optionally supply `--snapshot` and an aware `--as-of` time to evaluate exported evidence. JSON and Markdown are supported.

This is an offline check, not a permission or connectivity probe. Exit `3` means required facts remain unknown; exit `4` means a declared requirement or supplied snapshot is blocked. Neither permits treating the fleet as healthy or approving changes. Exit `2` rejects invalid input, and exit `1` reports a failed explicit output write. No roles, report directories, workload resources, or monitoring components are created. Live checks are deferred to the approved read-only adapters.

## Run

```bash
aks-fleet-advisor analyze \
  --snapshot snapshot.json \
  --config advisor-config.yaml \
  --format markdown \
  --output report.md
```

## Collection And Assessment

Use the [recommendation-pack guide](../recommendation-packs.md) to inspect
`catalog list/show/export`, select `--pack AKS-RQ-002`, or compare baseline and
guarded assessment. Baseline is now the default and cannot emit numeric resource
or replica proposals. Existing proposal fixtures explicitly select guarded mode
in their profiles; changing mode never bypasses owner/evidence gates.
Offline query export writes a new directory and contacts no endpoints.

For approved saved fragments, `assess` remains fully offline:

```bash
aks-fleet-advisor assess \
    --fragments examples/fixtures/pool-assessment.json \
    --config examples/pool-assessment-config.yaml \
    --as-of 2026-10-29T12:00:00Z \
    --format json
```

Inputs and outputs use schema 1.0. All 21 rules have packs: CPU request review
uses 2.1.0, eighteen packs use 2.0.0 and the two current scheduling/capacity
investigations use 1.0.0. JSON includes normalized snapshot/report, typed current/history/metadata evidence, digests and gaps; Markdown shows sources and eligible/blocked findings. `--output` exclusively creates a file. `--artifacts new-directory` creates the fixed replay set below an existing parent; the profile destination is never used implicitly. JSON reads are bounded at 32 MiB. Synthetic examples contact no endpoints.

`assess` returns `0` for complete supported-scope assessment, `3` partial/blocked, `2` invalid prerequisites and `1` output failure. `collect` returns `0` for complete requested collection and `3` for partial receipts, with the same error codes. Empty recommendations never mean a healthy fleet. The pool positive example is complete only for its observed scope, not full product/pilot acceptance.

Supported mappings are documented in [contracts](../data-contracts.md): Manual pools with exact historical membership/constant capacity; current homogeneous Deployment/StatefulSet replicas; direct single-Pod history; and approved conservative replica-envelope histories bound to an explicit complete historical roster digest. Changing request/replica histories, missing recordings, unknown overhead and unsupported constraints stay blocked. Never combine summary percentiles or infer historical membership from current Pods.

Present CPU quantities need `.[kubernetes]`; parser absence stays a gap without installation. Full development verification uses `.[dev,kubernetes]`. The history golden shows a synthetic owner-policy-bounded CPU proposal, not change approval or cash savings. Use scoped/Azure/replica examples for independently healthy findings alongside explicit denied sources.

Memory policy is separate: supply exact-container `safety_policy.memory` entries only from independently reviewed startup/failover/QoS/eviction evidence for the policy's UTC window. See the [contract](../data-contracts.md#memory-safety-readiness). `AKS-MEM-002` reports readiness or explicit blocked reasons; a passing informational review is not a numeric memory target, source attestation or change approval. Examples other than the memory case intentionally lack this policy and remain blocked for memory readiness. `AKS-MEM-001`/`AKS-REL-001` continue investigating eligible OOM/restart counts without requiring it. No limits are changed and savings remain null.

Numeric memory requests require a separate strict boolean `allow_request_reduction: true` on the exact container's memory policy; omission defaults off. `AKS-MEM-003` requires all readiness gates and full-grid request/limit/working-set/OOM/restart history from a supported direct single-Pod or approved complete-roster replica-envelope input. Envelopes additionally require the exact roster/digest, observed admission lists and complete eviction history specified in the [request contract](../data-contracts.md#memory-request-proposals); generic replica aggregation is not substituted. The [memory example](../../examples/expected-memory.md) is synthetic: run `aks-fleet-advisor assess --fragments examples/fixtures/memory-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown` for a 512-to-313 MiB request proposal with unchanged 1024 MiB limit. It exits `3` because unrelated pool evidence remains unsupported. Owner review, one-dimension-at-a-time canary validation and restoration of the original request on regression remain mandatory; enabling proposals is not change or live-access approval.

For separately approved collection, install `.[azure,kubernetes,metrics]` through the approved feed. Prepare explicit target allowlists, an independently verified cluster fingerprint and sanitized `KubernetesMetadataSnapshot` exports. Start from the synthetic [plan](../../examples/collection-plan.json) and [export](../../examples/fixtures/kubernetes-export.json), replacing scope/source/window/identities with approved evidence. These committed examples are not live targets.

```bash
aks-fleet-advisor collect --config approved-profile.yaml --plan approved-plan.json \
    --allow-live --output fragments.json
aks-fleet-advisor assess --config approved-profile.yaml --plan approved-plan.json \
    --allow-live --artifacts new-assessment
```

Only these explicitly invoked modes contact sources. The CLI uses sanitized exports, never kubeconfig/plugin execution or bearer environment-value reads. Generic anonymous HTTPS and tenant-bound public-Azure managed metrics are supported; inject approved credential/Kubernetes readers through `CollectionReaders` for other approved library integrations. Client/fingerprint provenance belongs to the operator. Private endpoints/custom proxy/CA requirements need pilot validation, not disabled TLS.

Select historical entities and approved query keys explicitly. Omitted selections do not invent metrics. Optional upstream recordings and membership references must come from an approved producer; the advisor never installs recordings or reconstructs missing history. Collection is sequential with total read/object/query/deadline budgets, no orchestration retries and bounded transport timeouts. Budget exhaustion preserves failures. The cooperative deadline cannot forcibly interrupt an injected call; its owner must bound transport execution.

Artifact layout: `fragments.json`, `snapshot.json`, `analysis-config.json`, `assessment.json`, `report.md`, then `manifest.json` containing SHA-256 hashes of the other files. Do not treat an interrupted directory without its final manifest as successful. Existing files/directories are untouched; choose a fresh destination. Secure the parent with approved ACLs, encryption, retention and audience: sanitized metadata still identifies workloads. No credential values belong in artifacts.

```bash
aks-fleet-advisor analyze --snapshot new-assessment/snapshot.json \
    --config new-assessment/analysis-config.json --as-of 2026-10-29T12:00:00Z --format json
```

Use the assessment's evaluation clock for exact replay. The full verifier checks source and installed-wheel report/artifact replay and no-consent refusal without network access. Validate actual source feasibility through the [source compatibility worksheet](../source-compatibility.md); no canary/change is applied by the advisor.

### Current autoscaler review

`AKS-AS-002` reviews observed HPA/VPA request-denominator overlap using complete fresh metadata, not metric history. The [synthetic example](../../examples/expected-autoscalers.md) is replayable:

```bash
aks-fleet-advisor assess --fragments examples/fixtures/autoscalers-assessment.json \
    --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z \
    --format markdown
```

Exit `3` preserves unrelated unsupported pool/history evidence. The review identifies a configured CPU utilization target of 75% and a matching Recreate VPA policy; it does not measure CPU load or prove oscillation. Exact-container/wildcard policy, explicit VPA mode/resources, matching current identities, successful versioned lists and source freshness are required. Exports that omit container `mode` remain unknown rather than assuming Auto. Keep owner review and existing CPU/memory reduction blocks; absolute/external signals are not a throughput-safety exemption. No controller change, resource target, role grant or live-access approval is produced.

### Memory completion examples

Use the standard offline `assess --fragments` workflow with `examples/fixtures/memory-envelope-assessment.json`, `memory-limit-assessment.json` or `memory-context-assessment.json`, the pool-assessment configuration and saved `--as-of 2026-10-29T12:00:00Z`. Each returns exit `3` because unrelated unsupported pool/vertical evidence remains visible.

The [envelope](../../examples/expected-memory-envelope.md) proposes 313 MiB per replica with a complete digest-bound roster, including deleted Pods; never sum its percentiles. Supply the exact approved memory min/max/envelope/restart recordings, stable controller history, observed admission lists and full workload eviction counts. The advisor installs/backfills nothing.

The [limit](../../examples/expected-memory-limit.md) proposes 1024 to 600 MiB while preserving request 512 MiB. Limits default off and require full-memory usage, complete zero OOM/restarts/evictions, allocator/cache and total-memory startup/failover review, observed Container LimitRange constraints and a reviewed `memory_limit_configuration_digest(workload)`. The digest is also in `AKS-MEM-004` current evidence; copying it is not evidence that the owner tested that configuration. Missing/changed/recreated/unreviewed evidence blocks. Canaries change only one dimension, with exact original-limit restoration on regression through customer tooling.

The [context](../../examples/expected-memory-context.md) reports ordered init/sidecar/overhead request accounting, a reported termination reason/exit code and workload evictions. These are not usage, root-cause diagnosis, node removability or approval. No Events/log bodies/messages are read. Headlamp displays the limit dimension but its resource-request approval workflow refuses limits and mixed proposals. Native snapshot/configuration replay preserves the same findings and versions. See [memory contracts](../data-contracts.md#memory-completion-contracts).

### Autoscaler completion examples

Use the same offline assessment command with `examples/fixtures/keda-assessment.json`, `vpa-bounds-assessment.json` or `replica-floor-assessment.json` and the pool-assessment configuration. All return exit `3` because unrelated unsupported pool/vertical evidence remains visible.

The [KEDA example](../../examples/expected-keda.md) verifies exact generated-HPA ownership without treating the ScaledObject as a competing HPA. The [VPA example](../../examples/expected-vpa-bounds.md) retains explicit CPU/memory bounds, not recommendation-generation freshness or a resource proposal. Trigger thresholds/authentication values are never imported.

The [replica example](../../examples/expected-replica-floor.md) proposes HPA minimum 2 to 1 only with strict explicit opt-in, complete seven-series history and configuration-bound owner evidence. Obtain `replica_configuration_digest` from `AKS-AS-003` evidence or the pure `replica_configuration_digest(workload)` helper, independently verify the owner-tested configuration, and place that reviewed digest in `safety_policy.replicas.configuration_digest`. Do not copy a digest into policy merely to bypass a blocked reason.

Owner-reviewed incident counts and references are declarations, not telemetry or approval. Unknown/positive reviews, observed OOM/restarts, changed requests/Pod identities/HPA config, unsupported controllers/constraints and incomplete availability block the floor. Review/approve separately and canary only the HPA minimum; restore the original floor on regression through customer delivery tooling. Existing Headlamp displays the proposal but its resource-request approval workflow refuses replica floors, including mixed records. No new roles, network calls, telemetry or delivery workflow are introduced. See [contract and supported scope](../data-contracts.md#opt-in-replica-floor-proposal).

### Historical HPA replica-bound review

The [HPA history example](../../examples/expected-hpa-history.md) is a saved synthetic floor investigation:

```bash
aks-fleet-advisor assess --fragments examples/fixtures/hpa-history-assessment.json \
    --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z \
    --format markdown
```

Exit `3` preserves unsupported pool/vertical-analysis evidence. `AKS-AS-003` observes count 1 across complete aligned evaluation points with bounds 1..5; it does not recommend lowering the minimum. Supply an explicit binding `hpa_uid` and approved UID-enriched HPA min/max/desired/current recordings for the actual window. These recordings are not assumed present or installed by the advisor. Missing history, current-only settings, changed/recreated controllers, incomplete samples or changed current bounds/status stay blocked. Bounds/status are not defaulted. Keep availability/failover review, UID/source verification and separate change approval; no replica target, autoscaler change or savings is produced. Exported snapshot/configuration replay uses the same engine and evaluation clock.

## Azure inventory API

This Python API is also used by the bounded collection CLI. Install optional Azure dependencies through the approved package feed:

```bash
python -m pip install -e '.[azure]'
```

Before running it against an environment, obtain approval for the profile's tenant and explicit subscription/cluster scope. Grant `Reader` only on the approved inventory scope; do not grant Contributor, cluster admin, or Kubernetes access for this adapter. Confirm the identity can see the full intended scope: Resource Graph can return a successful but limited authorized view. No role assignments are created by the collector.

The example below performs real read-only Azure queries when explicitly executed with an approved profile and authenticated identity. It writes only the selected local artifact:

```python
from pathlib import Path

from aks_fleet_efficiency.collectors.azure_resource_graph import (
    AzureResourceGraphCollector,
    AzureSdkInventoryReader,
)
from aks_fleet_efficiency.config import load_onboarding_config

profile = load_onboarding_config(Path("onboarding.yaml"))
with AzureSdkInventoryReader(profile) as reader:
    inventory = AzureResourceGraphCollector(profile, reader=reader).collect()
Path("azure-inventory.json").write_text(
    inventory.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
```

`DefaultAzureCredential` supports the operator's approved existing credentials or managed/workload identity; no interactive browser/broker prompt is started and no tenant configuration is changed. Each acquired token is checked for the configured tenant claim before it reaches Resource Graph. Azure still validates the token; the local claim check is a scope guard, not a replacement for server-side signature/audience validation. An opaque/unparseable token fails closed. Do not copy tokens or static credentials into the onboarding file.

The reader currently supports public Azure only and sends queries to `https://management.azure.com`. Approved identity token endpoints may also be used by Azure Identity. No Kubernetes endpoint, logs, Secrets, ConfigMap bodies, private endpoint addresses, or workload payloads are queried. Resource Graph uses a query POST, not a resource-write operation. Query projection retains approved inventory fields, not complete ARM response bodies.

Defaults are at most 1,000 records/page, 100 pages/subscription, three retries per page, a 30-second cap per retry delay, and 30-second request timeouts. Core constructor settings bound pages/retries; the SDK reader accepts request timeouts up to 120 seconds. Nested SDK retries are disabled. Long-running scans remain bounded by these per-subscription limits; no unbounded watcher is started.

Inspect `inventory.collection.status`, completed/requested scope, pagination completion, missing fields, and error codes before consuming output. Do not treat partial inventory or an empty authorized result as a healthy fleet. An explicitly targeted cluster missing from results fails scope completeness. Fleet links are discovered only in approved subscriptions and remain unknown when not observed. Required properties missing from ARG produce an incomplete receipt; no management-plane fallback is silently invoked. The output is an inventory fragment, not a metric-bearing snapshot for analysis.

Validation so far is offline with fake readers and mocked SDK calls; obtain operator-authorized integration evidence before relying on live behavior or enabling scheduled collection. The `readiness` command remains offline and does not invoke this adapter automatically.

References: [Resource Graph pagination and result semantics](https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data), [Python SDK client reference](https://learn.microsoft.com/en-us/python/api/azure-mgmt-resourcegraph/azure.mgmt.resourcegraph.resourcegraphclient?view=azure-python).

## Kubernetes metadata API

This is a Python API for operator-approved collection, not an automatic cluster-onboarding command. Install the optional client package through the approved feed:

```bash
python -m pip install -e '.[kubernetes]'
```

Supply an already configured read-only `kubernetes.client.ApiClient` for the approved endpoint. Configure verified HTTPS and the approved CA, `debug=False`, `retries=0`, no impersonation headers, and no credential-refresh hook before creating that client. The reader does not load kubeconfig, execute login plugins, read environment values, grant roles, or acquire Azure credentials. A caller-owned client must be closed by its caller. Expired credentials fail collection; replace them through the approved identity process rather than disabling checks.

Verify the target's `kube-system` namespace UID independently through the platform team's trusted inventory. Do not copy a UID from an unverified endpoint and call that identity reconciliation. The expected UID and declared Azure resource ID are both required. Optional node reconciliation also needs an approved `AzureClusterInventory` object and exact node resource-group name; leaving them absent intentionally produces unknown node bindings.

The function below performs real read-only cluster queries when explicitly called with an approved client. It returns a sanitized fragment; it does not save it, normalize metrics, or change workloads:

```python
from pathlib import Path
from typing import Any

from aks_fleet_efficiency.collectors.kubernetes_metadata import (
    KubernetesMetadataCollector,
    KubernetesSdkReader,
)
from aks_fleet_efficiency.config import load_onboarding_config


def collect_metadata(
    profile_path: Path,
    cluster_resource_id: str,
    expected_namespace_uid: str,
    api_client: Any,
):
    profile = load_onboarding_config(profile_path)
    reader = KubernetesSdkReader(
        profile, cluster_resource_id=cluster_resource_id, api_client=api_client
    )
    return KubernetesMetadataCollector(
        profile,
        cluster_resource_id=cluster_resource_id,
        expected_cluster_uid=expected_namespace_uid,
        reader=reader,
    ).collect()
```

Use only selected-resource `get/list` rights from the [security guidance](../security-and-privacy.md). This collector uses GET discovery/list requests, not watches, access-review POSTs, exec, logs, or mutation APIs. Where standard discovery is restricted, approve GET access only to the API discovery endpoints for the selected groups/versions. Optional VPA/KEDA/NAP groups require read access only if enabled and intended for collection; a denial is recorded, never treated as proven absence.

Defaults are at most 500 objects/page, 100 pages/resource type, three retries per page, 30 seconds/request, a 30-second retry-delay cap, and 16 MiB per response. Request timeouts are configurable up to 120 seconds and response bounds up to 64 MiB. SDK retries must stay disabled so the core retry budget is not multiplied. API discovery is bounded to approved groups and at most eight advertised versions per group. Expired continuation tokens, inconsistent list resource versions, oversized responses, duplicate identities, or required-resource failures leave collection incomplete. No daemon or unbounded watcher is started.

Review `collection`, `api_availability`, `resource_versions`, `workload_bindings`, and node reconciliation states before consuming the fragment. Complete metadata pagination is not evidence of healthy workloads, representative metrics, or permission to apply changes. Unknown labels, unavailable CRD versions, custom owners, missing Azure bindings, and API-index timing remain explicit limitations. The SDK reader receives full approved list responses transiently because Kubernetes lacks spec-field projection; it strips excluded values immediately and never logs them. Use a sanitized reader instead if the customer prohibits even transient access to full pod specifications.

Validation is offline with fake readers and a locally installed SDK 37.0.1 serialization test whose network function is stubbed. No live Kubernetes connection has been exercised. The offline `readiness` command does not invoke this adapter automatically. API references: [Kubernetes list/discovery semantics](https://kubernetes.io/docs/reference/using-api/api-concepts/), [official Python client](https://github.com/kubernetes-client/python).

## Prometheus metrics API

This is a read-only Python API; end-to-end normalization and collection commands remain separate work. Install the optional HTTP transport through the approved package feed; managed Prometheus also needs the Azure extra:

```bash
python -m pip install -e '.[metrics]'
python -m pip install -e '.[metrics,azure]'
```

Obtain approval for the metric source, endpoint egress, cluster allowlist, time range, and query budget. For Azure Monitor managed Prometheus, use the workspace query endpoint and an identity with `Monitoring Data Reader` scoped to the approved workspace. The reader grants no roles, installs no monitoring agent, and performs no deployment. Azure Identity may contact its approved token endpoints. The managed adapter currently accepts public-Azure `*.prometheus.monitor.azure.com` hosts, uses `https://prometheus.monitor.azure.com/.default`, and checks the acquired token's tenant claim before sending it. This guard does not replace Azure's server-side token validation.

Generic profiles can use anonymous access only where explicitly approved, or a bearer credential injected in process from the approved credential broker. A `bearer-environment` profile records a variable name, but the reader deliberately does not read its value; constructing that reader without an explicit credential fails. Never hardcode, print, or put credentials in the YAML. The default HTTP client verifies TLS, refuses redirects, and ignores environment proxy/CA overrides (`trust_env=False`). Private PKI/proxy requirements need an approved transport integration and live validation; do not bypass certificate checks. Custom transports are a trusted integration/test boundary, not untrusted profile input.

Prepare explicit `MetricEntity` objects from verified historical identity records, not only today's surviving pods/nodes. The function below queries a configured source only when explicitly called; it returns summaries rather than raw samples:

```python
from collections.abc import Sequence
from pathlib import Path

from aks_fleet_efficiency.collectors.prometheus import (
    PrometheusHttpReader,
    PrometheusMetricCollector,
)
from aks_fleet_efficiency.config import load_onboarding_config
from aks_fleet_efficiency.models import MetricEntity, PrometheusMetricsSnapshot


def collect_metric_history(
    profile_path: Path,
    source_name: str,
    entities: Sequence[MetricEntity],
) -> PrometheusMetricsSnapshot:
    profile = load_onboarding_config(profile_path)
    with PrometheusHttpReader(profile, source_name=source_name) as reader:
        return PrometheusMetricCollector(
            profile, source_name=source_name, reader=reader, entities=entities
        ).collect_observations()
```

With neither range argument, collection uses the last configured number of complete UTC days, normally 30. Supply both `start` and `end` for an explicit aware window; it is not silently extended. The default step is 300 seconds. Select a subset of catalog keys with `metrics` when appropriate; a selection with no applicable entity metric is rejected. Container identity requires the declared workload-kind mapping and canonical workload/pod UID labels. Workload history uses no fabricated pod UID. Approved node/workload `aks_advisor:*` recordings must already exist and expose the declared identities; no source-specific enrichment is installed automatically.

Defaults are 1,000 evaluation points/chunk, 10,000 planned queries, three retries per query, a 30-second delay cap, 30-second HTTP timeouts, 16 MiB decoded response limit, and 1,000 series/response. Constructor bounds constrain retries/chunks/query counts; HTTP timeouts are at most 120 seconds and decoded bodies at most 64 MiB. The endpoint is fixed to `/api/v1/query_range`; no admin, write, exemplar, target/configuration, or label-enumeration API is called. Raw samples are transient calculation inputs and are discarded from output; provider warnings are represented by a flag, not copied response text. Do not enable HTTP body/header tracing.

Inspect the collection receipt, each observation's quality/coverage/latest sample time/issues, and any null counter total. A complete request is not evidence that raw scrapes, historical identity, or a workload SLO are complete. Do not set `node_history_complete=True` unless the complete historical member set for the period is independently verified; current nodes alone are insufficient, and churn can still leave no common complete grid. Managed Prometheus case handling and source-specific metric conventions must be validated; ambiguous or mismatched identities remain missing instead of being joined by name.

This adapter was validated with synthetic range vectors, mocked identity/HTTP failures, and the installed HTTP client using a mock transport. No live customer endpoint, token acquisition, source permission, or retained data was exercised. The offline `readiness` command does not query endpoints automatically. References: [Prometheus query API](https://prometheus.io/docs/prometheus/latest/querying/api/), [Azure managed Prometheus API and access](https://learn.microsoft.com/en-us/azure/azure-monitor/metrics/prometheus-api-promql).

## Quality gates

- Use `--as-of 2026-10-29T12:00:00Z` for explicit offline replay. Omit it for current-time assessment; naive times are rejected. A replay clock is not authorization to apply historic findings.
- No partial inventory unless the report is explicitly marked partial.
- Metric coverage meets the rule threshold.
- Observation time and currency are present.
- Savings remain null, including after successful cost reconciliation.
- High-severity reliability guardrails are reviewed before efficiency findings.

The engine now lists ineligible checks separately under blocked findings, with stable IDs and reason codes. Do not interpret an empty recommendation list as a healthy fleet when blocked findings or partial collection are present. The original fixture uses the current schema but intentionally lacks collection provenance and remains a non-actionable missing-evidence example, not a legacy compatibility reader.

Default evidence settings are `minimum_observation_days: 30`, `minimum_coverage_ratio: 0.85`, `maximum_evidence_age_hours: 24`, and `maximum_metric_step_seconds: 300` under `thresholds`. Changes must reflect approved source retention and workload policy, not bypass a failing safety gate. Fresh collection time does not repair stale underlying observations. See [data contracts](../data-contracts.md) for required collector names, scopes, metric units, and owner policy fields.

## Incident response

Because the advisor is read-only, a runtime incident should not modify clusters. Stop the local runner and any customer-supplied job, revoke its identity as appropriate, preserve available audit records, quarantine reports, and validate that no credentials or forbidden fields were collected. The repository supplies no scheduler or hosted audit service.

## Rollback

Runtime rollback means restoring a compatible reviewed package and its rule/query assets; an operator-owned container deployment may instead restore its reviewed image. Preserve original saved locks rather than editing them. Customer change rollback is the separately approved restoration procedure; closing or superseding a finding is only a review decision. The advisor performs no cluster rollback.
