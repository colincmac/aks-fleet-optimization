# Source profiles and PromQL verification

This is the exact monitoring-format and maintainer-verification reference. An operator preparing an assessment should first use [the data-source task guide](how-to/validate-source-compatibility.md); an unfamiliar reader can start with [the evidence lesson](learning/04-evidence-quality-and-historical-identity.md). The pinned-tool section is for software verification, not a prerequisite for understanding a fictional report.

These source profiles describe metric shape separately from transport support and evidence sufficient for analysis. Financial inputs use the separate [financial source profiles](financial-source-profiles.md). No source profile installs telemetry, queries an endpoint during readiness, or attests an operator's permissions.

## Declared profiles

Choose a source shape for the selected question, not a new monitoring product. Current metadata checks need no metric profile or endpoint. Ordinary CPU measurements use `cadvisor-ksm` against existing enterprise Prometheus; qualified historical/candidate checks use `identity-enriched` only where its required history already exists. All three are useful stopping points; financial inputs are separate and optional. See the [entry-point examples](how-to/choose-recommendation-packs.md#three-ways-to-start).

| Catalog profile | Intended input | Supported assessment boundary |
| --- | --- | --- |
| [cadvisor-ksm](../src/aks_fleet_efficiency/catalog/sources/cadvisor-ksm.yaml) | CPU counters and kube-state-metrics requests with namespace, Pod name and container | Unresolved baseline measurements. No historical workload/Pod identity, ownership join or guarded target. |
| [identity-enriched](../src/aks_fleet_efficiency/catalog/sources/identity-enriched.yaml) | Existing historical UIDs or approved roster-bound recordings | Evidence-gated CPU, pool, memory/reliability and autoscaler history packs; missing history remains a gap. |

Both declare generic HTTPS and public-Azure managed Prometheus transports. Transport availability is not live integration acceptance. The conservative default `identity-enriched` selects an adapter format; it does not assert that the required historical series exist. Select `cadvisor-ksm` explicitly for name-only measurements.

Profiles record metric/query references, units through the shared query catalog, label conventions, identity semantics, supported joins (`none`), limitations and characterized component versions. The current matrix is **synthetic metric-shape characterization**, not certification against live exporters or AKS versions.

The identity-enriched profile also exposes shared historical node CPU and allocatable CPU/memory references for `AKS-NP-001`. Pool exports require exact node resource IDs/UIDs, not today's pool membership extrapolated across the window. Existing normalizer checks still require aligned complete member evidence and constant capacity. The missing- request inventory pack has no Prometheus capability or endpoint requirement.

The identity-enriched profile version 1.0.0 includes memory/reliability, workload guard series and four packaged HPA replica gauges. HPA selectors retain controller UID and historical target workload UID, not display names or current target relabeling. The floor proposal's capability checks include all three workload availability series even when only HPA series were supplied. Current autoscaler investigations remain independently inventory-only. This does not install or attest those recordings, enrich names into history, or guarantee that a brownfield source has the required inputs. Current Pod accounting/termination remain inventory-only. PromQL expressions are verified with the release selected by the [tool lock](../eng/promtool-lock.json); the source profiles separately declare Prometheus `3.16.0-rc.2` and kube-state-metrics `2.17.0` synthetic shapes. Undeclared versions remain unknown; explicit uncharacterized versions are unsupported, not silently mapped to a nearby version. Neither version strings nor recording names attest a producer.

An exact approved Azure resource-ID label must already exist. Cluster display names are not substitutes. Name-only scope needs explicit `cluster_resource_id`, `namespace`, `pod` and `container` label mappings. The sample [ordinary profile](../examples/ordinary-source-config.yaml) shows the fields.

`label_mapping` supplies the source-wide default label names. When an existing source uses a different label name for a specific installed catalog query, `query_label_mappings` may supply a partial override keyed by that query ID; unspecified logical labels continue to use the source default. For example, a source can map `cluster_resource_id` to `cluster_name` for `cpu_usage` while retaining `azure_resource_id` for `cpu_request`. Overrides contain label names only, must resolve to distinct valid Prometheus identifiers, and do not map label values, discover series, reconcile two cluster identities, or create historical UIDs. Unknown query IDs and collisions are rejected before source I/O. Offline readiness checks the effective mapping for every query selected by the configured pack and mode.

```yaml
label_mapping:
  cluster_resource_id: azure_resource_id
  namespace: namespace
  workload_kind: workload_kind
  workload: workload
  container: container
query_label_mappings:
  cpu_usage:
    cluster_resource_id: cluster_name
```

## Inspect capabilities offline

```powershell
aks-fleet-advisor catalog capabilities AKS-RQ-002 --config examples\ordinary-source-config.yaml --as-of 2026-10-29T12:00:00Z
```

The command inspects declarations and leaves unobserved facts unknown. For collected evidence, `--metrics` accepts a single **Prometheus metric fragment** JSON file, not a combined assessment fragment. Combined samples are assessed directly with the commands below, which also include the capability matrix. Import/extraction never implies source approval.

Capabilities are reported per source, cluster, pack and mode:

- `available`: the required queried series have usable scoped evidence under the declared shape; this is not safe-change approval.
- `unavailable`: required queried series were observed missing; not zero.
- `unknown`: no collection, undeclared versions, partial/stale evidence or insufficient quality prevents a conclusion.
- `unsupported`: identity ambiguity, incompatible shape/binding or an explicit uncharacterized version prevents use.

Reports retain individual reason codes, profile definitions and UTC evaluation time. Unsupported guarded source profiles block CPU targets independently of the existing policy/reliability gates. Unknown version characterization is a separate compatibility gap, not invented measurement coverage or certification. Metric gaps never hide independently valid current configuration investigations.

`readiness` remains offline. For separately approved live capability evidence, use `collect --plan ... --allow-live`, then inspect the saved metric fragment. The configured scope, endpoint, identity and budgets require independent approval; the flag alone is not consent. There is no automatic series-discovery, logging probe, exporter installation or namespace-ownership enrichment.

## Review a saved controller source

The [saved controller timeline](data-contracts.md#optional-saved-controller-timeline) is a separate SDK input, not a catalog Prometheus profile. Its CPU signal must come from the specified HPA's actual observed `Resource`/`Utilization` metric, with a producer-reviewed timestamp for that observation. Neither cAdvisor CPU, a configured target, stock desired/current/min/max gauges, nor the time an HPA object was read can supply a missing actual signal or timestamp. If a probe returns no samples, report the gap for that scope and window; it does not prove global metric absence.

Before any real input is used, the monitoring owner must review the producer and its version, the original signal/target match and clock and completeness semantics, and how historical target and Namespace/Deployment/HPA UIDs and both revisions are bound at each point. To include requests, verify they were observed for the same Pods measured by the HPA and share a single request basis; mixed rollout Pods or missing containers leave this field unknown. For optional Ready/Available, verify status corresponds to the admitted Deployment revision and original observation time. For a live Grafana overlay, separately complete host acceptance and verify this source on the approved demo scope. No producer, exporter, permissions, or live adapter is supplied by the offline contract.

## Ordinary telemetry without invented history

For this entry point, select only `AKS-RQ-002` in baseline mode. Its ordinary query set is CPU usage and admitted CPU request, not the advanced controller/throttling/OOM recordings. Returned series must already carry an exact cluster resource-ID label plus namespace, Pod name and container; no source-wide telemetry overhaul or historical UID enrichment is performed. Existing per-query label-name overrides can handle different label conventions, but do not translate cluster-name values into resource IDs. Ask the monitoring owner to verify the mapping or keep the unsupported identity explicit.

```powershell
aks-fleet-advisor assess --fragments examples\fixtures\ordinary-source-assessment.json --config examples\ordinary-source-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor assess --fragments examples\fixtures\ordinary-source-assessment.json --config examples\managed-source-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor catalog export AKS-RQ-002 --config examples\ordinary-source-config.yaml --source synthetic --entities examples\ordinary-source-entities.json --output ordinary-queries
```

Compare [generic](../examples/expected-source-ordinary.md) and [managed](../examples/expected-source-managed.md) goldens. Both use synthetic evidence and exit `3` because source/workload/pool gaps remain. Managed import does not authenticate to Azure.

`baseline_measurements` retains qualified summaries and issues under `MetricEntity(kind="unresolved_container")`. The entity cannot carry historical workload/Pod UIDs, a membership digest or a fabricated ownership association. Current metadata names never relabel its history. Baseline display retains missing/stale/low-coverage evidence as gaps; no numeric resource/replica proposal is derived from these measurements.

To review only these queries in an existing Grafana workflow, export optional query-only assets to a fresh directory:

```text
aks-fleet-advisor catalog export AKS-RQ-002 --config examples/ordinary-source-config.yaml --source synthetic --entities examples/ordinary-source-entities.json --mode baseline --grafana --output ordinary-grafana-queries
```

Expect exit `0`, two scoped PromQL files, a manifest and `dashboard.json`. This command performs no endpoint request or dashboard installation. The existing Grafana owner may review/import the journey-grouped query panels and select an already approved data source; the export creates no data source, alerts, recording rules, service or credentials. The dashboard identifies source/profile/version, units, step and its Grafana-controlled window, while its evidence-quality panel keeps coverage, freshness and missing-series status unknown until execution and assessment. Query panels do not supply historical identity or authorize proposals. Do not deploy another Grafana instance to use them.

## Bounded query plans

Qualified sources can export several selected metric packs into one deduplicated query/dashboard bundle using repeatable `--pack` options; see [combined investigation journeys](recommendation-packs.md#combine-query-investigation-journeys). The bundle retains every pack's provenance and the same effective per-query mappings. All selected packs need compatible explicit entities, and unmatched/foreign entities or stale locks fail before output. Ordinary name-only sources remain limited by their declared profile; combining packs never supplies missing historical identities or certifies guarded eligibility. Grafana targets declare the rendered minimum step, but actual evaluation may be coarser and coverage remains unknown until source execution and assessment.

Metric fragments retain `query_plan` with logical queries, unique expression/ interval bases, planned range requests, expected evaluations and the response series limit. Identical range requests share a run-local, defensively copied response; different scopes, intervals and delta offsets do not share evidence. Terminal errors, warnings and partial coverage propagate to every dependent observation. Cache reuse neither hides failures nor inflates retry receipts.

`maximum_metric_evaluations` is a total collection-plan budget; `maximum_series_per_response` bounds every returned matrix, including foreign series. Preflight budgets fail before reader calls; response excess fails with `response-budget-exceeded`. Retries remain separately bounded and recorded. The default maxima are five million evaluation points and ten thousand series per response, with explicit stricter configuration available.

Query reuse does not change percentile semantics. P50/P95/P99 use aligned returned samples; pool values still sum aligned member usage before percentiles. Returned evaluation coverage is not raw scrape completeness.

## Optional approved-roster recordings

The [recording file](../src/aks_fleet_efficiency/catalog/recordings/approved-cpu-envelope.yaml) is never installed by the advisor. An operator may separately review/install it only when the specified upstream producer already supplies:

- Exact cluster/namespace/workload/container identity and reviewed membership digest.
- Per-member CPU/request/throttling values and disjoint integral OOM interval totals.
- A complete historical roster including deleted members and independently verified full-window membership/quality.
- A truthful `approved_roster_complete` signal for each evaluation point.

The recordings produce per-replica maxima, request min/max and interval totals; they do not sum percentiles or manufacture digests. A missing/false completeness signal produces absence, not zero. Producer assertions are not attestation; these rules cannot detect a producer falsely claiming completeness or backfill missing history. Existing request/replica/controller/reliability guards still apply.

## Required pinned tool

An existing checksum-matching `eng\promtool.exe` is reused unchanged. The [lock](../eng/promtool-lock.json) is the source of truth for the selected Prometheus/promtool version, revision and Windows/Linux amd64 archive and binary checksums. A prerelease version is an explicit preview tool pin, not a stable-release claim. Executables are ignored by Git; no third-party binary is vendored.

```powershell
.\.venv\Scripts\python.exe scripts\setup_promtool.py
.\.venv\Scripts\python.exe scripts\validate_promql.py --output-dir new-promql-results
```

Setup reuses an existing checksum-matching binary. A missing binary requires explicit `--download`; only that setup command and CI dependency setup access the public GitHub release. The verifier itself performs no downloads or endpoint queries. Missing/mismatched tools fail the gate before execution, never skip it. Only Windows/Linux amd64 are supported.

### Change the Prometheus/promtool version

Choose an exact upstream release version (without the leading `v`). Promtool ships in the matching Prometheus release, so one version controls both the downloaded archive and its tool. For example, to select version `3.16.0`:

```powershell
.\.venv\Scripts\python.exe scripts\setup_promtool.py --update-lock 3.16.0 --download
.\.venv\Scripts\python.exe scripts\setup_promtool.py --download --replace
.\.venv\Scripts\python.exe scripts\verify.py
```

Replace `3.16.0` with the desired published version; stable and prerelease versions are supported. The first command resolves the release tag through the public GitHub API, reads its published `sha256sums.txt`, downloads both Windows/Linux amd64 archives, verifies their archive checksums, and computes the exact promtool binary checksums without executing either binary. It replaces the lock only after every check succeeds; it does not install a tool. This trusts the upstream GitHub release and checksum manifest, not an independent signature or attestation. Review the lock diff before committing it.

The second command explicitly replaces a previous local tool only after checksum/version/revision verification of the downloaded binary succeeds. Without `--replace`, a mismatched existing tool still fails before execution. Both operations require `--download`; normal verification remains offline and never rewrites the lock. A missing release, checksum, platform archive or exact binary member fails the update instead of retaining partial pins.

This changes the development verification tool, not a customer's running Prometheus server or the source profiles' characterized producer versions. Do not automatically rewrite those compatibility declarations: characterize new producer versions separately and update their fixtures/documentation only with supporting evidence.

`make verify` and the portable Python runner require actual `promtool check rules` and `promtool test rules`. Tests cover syntax, units, counter resets, missing/ stale/foreign series, observed zero events and complete/partial roster recordings. They use the actual catalog expressions, not separately maintained approximations.
