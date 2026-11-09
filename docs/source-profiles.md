# Source profiles and PromQL verification

This is the exact monitoring-format and maintainer-verification reference.
An operator preparing an assessment should first use
[the data-source task guide](how-to/validate-source-compatibility.md); an
unfamiliar reader can start with [the evidence lesson](learning/04-evidence-quality-and-historical-identity.md).
The pinned-tool section is for software verification, not a prerequisite for
understanding a fictional report.

Source profiles describe metric shape separately from transport support and
evidence sufficient for a guarded proposal. No source profile installs telemetry,
queries an endpoint during readiness, or attests an operator's permissions.

## Declared profiles

| Catalog profile | Intended input | Supported assessment boundary |
|---|---|---|
| [cadvisor-ksm](../src/aks_fleet_efficiency/catalog/sources/cadvisor-ksm.yaml) | CPU counters and kube-state-metrics requests with namespace, Pod name and container | Unresolved baseline measurements. No historical workload/Pod identity, ownership join or guarded target. |
| [identity-enriched](../src/aks_fleet_efficiency/catalog/sources/identity-enriched.yaml) | Existing historical UIDs or approved roster-bound recordings | Evidence-gated CPU, pool, memory/reliability and autoscaler history packs; missing history remains a gap. |

Both declare generic HTTPS and public-Azure managed Prometheus transports.
Transport availability is not live integration acceptance. The conservative
default `identity-enriched` selects an adapter format; it does not assert that
the required historical series exist. Select `cadvisor-ksm` explicitly for
name-only measurements.

Profiles record metric/query references, units through the shared query catalog,
label conventions, identity semantics, supported joins (`none`), limitations and
characterized component versions. The current matrix is **synthetic metric-shape
characterization**, not certification against live exporters or AKS versions.

The identity-enriched profile also exposes shared historical node CPU and
allocatable CPU/memory references for `AKS-NP-001`.
Pool exports require exact node resource IDs/UIDs, not today's pool
membership extrapolated across the window. Existing normalizer checks still
require aligned complete member evidence and constant capacity. The missing-
request inventory pack has no Prometheus capability or endpoint requirement.

The identity-enriched profile version 1.3.0 includes memory/reliability,
workload guard series and four packaged HPA replica gauges. HPA selectors retain
controller UID and historical target workload UID, not display names or current
target relabeling. The floor proposal's capability checks include all three
workload availability series even when only HPA series were supplied. Current
autoscaler investigations remain independently inventory-only.
This does not install or attest those
recordings, enrich names into history, or guarantee that a brownfield source has
the required inputs. Current Pod accounting/termination remain inventory-only.
PromQL expressions are tested with Prometheus `3.16.0-rc.2`; kube-state-metrics
`2.17.0` is a declared synthetic shape. Undeclared versions remain unknown;
explicit uncharacterized versions are unsupported, not silently mapped to a
nearby version. Neither version strings nor recording names attest a producer.

An exact approved Azure resource-ID label must already exist. Cluster display
names are not substitutes. Name-only scope needs explicit `cluster_resource_id`,
`namespace`, `pod` and `container` label mappings. The sample
[ordinary profile](../examples/ordinary-source-config.yaml) shows the fields.

## Inspect capabilities offline

```powershell
aks-fleet-advisor catalog capabilities AKS-RQ-002 --config examples\ordinary-source-config.yaml --as-of 2026-10-29T12:00:00Z
```

The command inspects declarations and leaves unobserved facts unknown.
For collected evidence, `--metrics` accepts a single **Prometheus metric
fragment** JSON file, not a combined assessment fragment. Combined samples are
assessed directly with the commands below, which also include the capability
matrix. Import/extraction never implies source approval.

Capabilities are reported per source, cluster, pack and mode:

- `available`: the required queried series have usable scoped evidence under
  the declared shape; this is not safe-change approval.
- `unavailable`: required queried series were observed missing; not zero.
- `unknown`: no collection, undeclared versions, partial/stale evidence or
  insufficient quality prevents a conclusion.
- `unsupported`: identity ambiguity, incompatible shape/binding or an explicit
  uncharacterized version prevents use.

Reports retain individual reason codes, profile definitions and UTC evaluation
time. Unsupported guarded source profiles block CPU targets independently of
the existing policy/reliability gates. Unknown version characterization is a
separate compatibility gap, not invented measurement coverage or certification.
Metric gaps never hide independently valid current configuration investigations.

`readiness` remains offline. For separately approved live capability evidence,
use `collect --plan ... --allow-live`, then inspect the saved metric fragment.
The configured scope, endpoint, identity and budgets require independent approval;
the flag alone is not consent. There is no automatic series-discovery, logging
probe, exporter installation or namespace-ownership enrichment.

## Ordinary telemetry without invented history

```powershell
aks-fleet-advisor assess --fragments examples\fixtures\ordinary-source-assessment.json --config examples\ordinary-source-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor assess --fragments examples\fixtures\ordinary-source-assessment.json --config examples\managed-source-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor catalog export AKS-RQ-002 --config examples\ordinary-source-config.yaml --source synthetic --entities examples\ordinary-source-entities.json --output ordinary-queries
```

Compare [generic](../examples/expected-source-ordinary.md) and
[managed](../examples/expected-source-managed.md) goldens. Both use synthetic
evidence and exit `3` because source/workload/pool gaps remain. Managed import
does not authenticate to Azure.

`baseline_measurements` retains qualified summaries and issues under
`MetricEntity(kind="unresolved_container")`. The entity cannot carry historical
workload/Pod UIDs, a membership digest or a fabricated ownership association.
Current metadata names never relabel its history. Baseline display retains
missing/stale/low-coverage evidence as gaps; no numeric resource/replica proposal
is derived from these measurements.

## Bounded query plans

Metric fragments retain `query_plan` with logical queries, unique expression/
interval bases, planned range requests, expected evaluations and the response
series limit. Identical range requests share a run-local, defensively copied
response; different scopes, intervals and delta offsets do not share evidence.
Terminal errors, warnings and partial coverage propagate to every dependent
observation. Cache reuse neither hides failures nor inflates retry receipts.

`maximum_metric_evaluations` is a total collection-plan budget;
`maximum_series_per_response` bounds every returned matrix, including foreign
series. Preflight budgets fail before reader calls; response excess fails with
`response-budget-exceeded`. Retries remain separately bounded and recorded.
The default maxima are five million evaluation points and ten thousand series
per response, with explicit stricter configuration available.

Query reuse does not change percentile semantics. P50/P95/P99 use
aligned returned samples; pool values still sum aligned member usage before
percentiles. Returned evaluation coverage is not raw scrape completeness.

## Optional approved-roster recordings

The [recording file](../src/aks_fleet_efficiency/catalog/recordings/approved-cpu-envelope.yaml)
is never installed by the advisor. An operator may separately review/install it
only when the specified upstream producer already supplies:

- Exact cluster/namespace/workload/container identity and reviewed membership digest.
- Per-member CPU/request/throttling values and disjoint integral OOM interval totals.
- A complete historical roster including deleted members and independently
  verified full-window membership/quality.
- A truthful `approved_roster_complete` signal for each evaluation point.

The recordings produce per-replica maxima, request min/max and interval totals;
they do not sum percentiles or manufacture digests. A missing/false completeness
signal produces absence, not zero. Producer assertions are not attestation; these
rules cannot detect a producer falsely claiming completeness or backfill missing
history. Existing request/replica/controller/reliability guards still apply.

## Required pinned tool

The supplied `eng\promtool.exe` is reused unchanged. The
[lock](../eng/promtool-lock.json) pins **Prometheus 3.16.0-rc.2**, its revision and
separately verified Windows/Linux amd64 archive and binary checksums. This is an
explicit **preview tool pin**, not a stable-release claim. Executables are
ignored by Git; no third-party binary is vendored.

```powershell
.\.venv\Scripts\python.exe scripts\setup_promtool.py
.\.venv\Scripts\python.exe scripts\validate_promql.py --output-dir new-promql-results
```

Setup reuses an existing checksum-matching binary. A missing binary requires
explicit `--download`; only that setup command and CI dependency setup access
the public GitHub release. The verifier itself performs no downloads or endpoint
queries. Missing/mismatched tools fail the gate before execution, never skip it.
Only Windows/Linux amd64 are supported.

`make verify` and the portable Python runner require actual `promtool check rules`
and `promtool test rules`. Tests cover syntax, units, counter resets, missing/
stale/foreign series, observed zero events and complete/partial roster recordings.
They use the actual catalog expressions, not separately maintained approximations.
