# Recommendation packs

For a customer task, start with [choose checks for your question](how-to/choose-recommendation-packs.md).
This page is the detailed version/parameter/workflow reference. A pack describes
one rule's required inputs and review guidance; selecting it does not establish
that the customer's inputs exist or approve a change.

Recommendation packs define the evidence, parameters, limitations and operator
guidance for each assessment. All [21 rules](../src/aks_fleet_efficiency/catalog/inventory.yaml)
have packs. Use the [operator catalog](operator-catalog.md) to choose packs for
your question, and validate source compatibility before using customer evidence.

For tool selection, combined-controller scenarios and environment investigation,
use the [orchestration and scheduling guide](orchestration-and-scheduling.md).

## Supported contracts

Use `aks-fleet-efficiency-advisor` version `0.1.0` for preparation, collection
and offline assessment. Install
from the approved feed or build the wheel from the reviewed checkout; install
instructions and extras are in [Contributing](../CONTRIBUTING.md).
An exported query/dashboard can run in existing approved tooling without the
advisor runtime. There is no required service, MCP adapter or AI dependency.

| Asset | Supported version and boundary |
|---|---|
| Configuration, fragments, snapshot, report, pack and export contracts | Schema `1.0`; generated [schemas](../schemas) are authoritative alongside Python cross-field validation |
| CPU review/proposal pack `AKS-RQ-002` | `2.1.0` |
| Other eighteen packs | `2.0.0` |
| Current scheduling/capacity investigations `AKS-SCHED-001` / `AKS-NP-002` | `1.0.0`; inventory-only, no numeric or migration proposal |
| All 35 shared query assets | `1.0.0`; templates are packaged `.promql`, rendered through the same helper for export, planning and execution |
| Source profiles | `identity-enriched` `1.3.0`, `cadvisor-ksm` `1.0.0`; synthetic characterization, not live certification |
| Artifact directory | `fragments.json`, `snapshot.json`, `analysis-config.json`, `assessment.json`, `report.md`, then last-written `manifest.json` with hashes |

All 21 pack IDs must resolve to matching manifests in the installed package.
Use the [generated catalog](operator-catalog.md) to inspect each pack's evidence,
parameters, queries, limitations and validation/rollback guidance. Reports retain
the selected manifest's version and provenance.

Saved configuration locks must match the installed manifest and query definitions.
Retain a compatible package for replay or create a new assessment from reviewed
evidence. Do not edit saved locks to conceal a mismatch. Only query keys listed
in the catalog are supported; CPU limits are current inventory context, not an
independently collected historical metric.

For install, permission, private-network and failure guidance, use the
[runbook](operations/runbook.md#installation-and-preflight).

### Validation boundaries

| Plan scenario | Offline evidence | External acceptance |
|---|---|---|
| No deployment | Source/wheel catalog inspection and scoped query/Grafana export | Execution in operator-approved tooling not observed |
| Ordinary telemetry | Generic/managed name-only baseline goldens retain explicit gaps | Actual retained source/labels not validated |
| Configuration-only | Current autoscaler/accounting tests run independently of history | Actual scoped metadata permissions not validated |
| Guarded evidence | CPU, memory request, memory limit and HPA-floor fixtures retain independent owner/safety vetoes | Owner approval and real canary/rollback not performed |
| Failure | Mock denied/unreachable readers, missing/stale/partial evidence and browser failure states | Live network/identity failure validation not performed |
| Replay | Fixed-clock source/installed-wheel reports, exports and locked artifact replay | No customer artifact is committed |
| Comprehension | Synthetic catalog/configure/preview and desktop/mobile browser scenarios | An unfamiliar platform operator must still complete the walkthrough |

Validate your actual source, effective permissions, network path and operator
workflow in a separately approved pilot. Automated synthetic tests do not
certify customer compatibility, deployment readiness or change approval.
Scheduling and capacity packs support current investigations only; broader
packing and NAP eligibility/migration analysis are unsupported.

## Current scheduling and capacity packs

`AKS-SCHED-001` reviews hard/soft placement constraints, volume references,
priority, runtime/init/overhead and current node/DaemonSet/PDB context.
`AKS-NP-002` classifies fixed/CAS pools and owner-declared reserved/specialized
capacity, inspects current NAP APIs/configuration and binds observed dynamic
supply by exact owner/provider identity. Unknown prerequisites are explicit;
neither pack proves stranded capacity, safe minima, removable nodes or migration.
Both are inventory-only with identical investigation boundaries in either mode.
Neither exposes threshold parameters or needs metric credentials.

Inspect with `catalog show AKS-SCHED-001` or `catalog show AKS-NP-002`.
For reproducible synthetic CLI examples:

```powershell
aks-fleet-advisor analyze --snapshot examples/fixtures/scheduling-review-snapshot.json --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor analyze --snapshot examples/fixtures/capacity-review-snapshot.json --pack AKS-NP-002 --as-of 2026-10-29T12:00:00Z --format markdown
```

The [source fragments](../examples/fixtures/placement-assessment.json) include
current constraints and an exact-pool owner reservation declaration. This
declaration is not attestation or approval; do not infer reservation from CAS
minima. The [contracts](data-contracts.md#current-placement-and-capacity-investigations)
describe unsupported matching, packing and NAP prerequisites.
Consult [current Microsoft NAP limitations](https://learn.microsoft.com/azure/aks/node-auto-provisioning#limitations-and-unsupported-features)
for each independently approved assessment; no static prerequisite list or
observed CRD is a certification of a cluster's eligibility.

## Operator workflow

The [generated catalog](operator-catalog.md) contains all 21 cards, shared
query templates, glossary, defaults/units/bounds, prerequisites, limitations,
validation/rollback and synthetic baseline configurations. It is generated from
the packaged manifests, not a second hand-maintained catalog or evidence of
source compatibility. Templates are clearly labelled **not executable**.

```powershell
aks-fleet-advisor catalog guide --output operator-guide.md
aks-fleet-advisor configure --output local-profile.yaml
```

`configure` guides tenant/subscription/exact-cluster scope, local source names,
HTTPS endpoints, declared source semantics and label mappings, pack selection,
mode and supported review ratios. Start with `--config` to retain an existing
approved profile. Defaults, units, bounds and implications are shown; no
credential values are requested, no source is probed, and owner opt-ins are
never added. Guarded mode is not owner approval. Unknown source versions remain
unknown; existing telemetry must supply the declared historical identities.

For reproducible non-interactive local changes:

```powershell
aks-fleet-advisor configure --config examples\cpu-pack-config.yaml --no-interactive --pack AKS-RQ-002 --review-ratio AKS-RQ-002=0.3 --output local-profile.yaml
aks-fleet-advisor preview --config local-profile.yaml --plan examples\operator-plan.json --as-of 2026-10-29T12:00:00Z --output execution-preview.json
aks-fleet-advisor catalog export AKS-RQ-002 --config local-profile.yaml --source synthetic --entities examples\cpu-pack-entities.json --grafana --output query-assets
aks-fleet-advisor assess --config local-profile.yaml --fragments examples\fixtures\history-assessment.json --as-of 2026-10-29T12:00:00Z --format markdown --output local-report.md
```

All commands above are offline, synthetic and refuse to overwrite existing
outputs. The example assessment intentionally exits `3` for incomplete evidence;
a report is not a claim of full source/pilot acceptance.

`preview` constructs no live readers and reads no metadata exports or credential
values. It shows the exact scoped ARG query and planned metric expressions,
HTTPS operations, UTC range, step/chunk/counter-offset semantics, query/evaluation
counts, read/object/duration/response budgets, excluded fields, configured artifact
destination, original pack/parameter locks and unresolved prerequisites. Counts
come from the collector's planner; selected-query dependencies share execution's
selection helper. Pagination, permissions, source evidence, SDK-selected ARG API
version and private connectivity remain unverified. It previews the **CLI's
sanitized metadata import**, not an injected SDK Kubernetes reader. The example
plan deliberately has no metadata export, leaving that prerequisite unresolved.
Before separately approved execution, supply the validated export and fingerprint
and review the preview again. Pass the reviewed artifact destination explicitly
to execution's `--artifacts`/`--output`; preview does not create it or authorize
`--allow-live`.

The export directory contains fully rendered `.promql`, a versioned manifest
and, with `--grafana`, an optional query-only Grafana dashboard. Import the JSON
through Grafana's existing import workflow and select the approved Prometheus
datasource. The datasource placeholder is Grafana configuration, not part of
the executable PromQL. These files can be distributed to operators who have
**no Python runtime and no advisor/custom dashboard backend**. Python is needed
to prepare/export or assess, not to run exported queries in approved tooling.
Queries/dashboard panels do not calculate safe proposals, approval or savings.

The existing Headlamp preview adds a **Recommendation catalog** route that
remains inspectable without loaded recommendations. Imported optional
`OperatorInspection` preserves the original card, effective parameters, mode,
pack/query digest and versions, resolved queries when supplied, source profiles
and capability reason codes. Missing inspection stays unknown; it is not
silently replaced with today's catalog. Measurement evidence, investigation,
numeric proposal, owner-policy checks and validation/rollback remain separate.
No authoritative facts are recalculated in the browser. Text and expressions
render inertly, without generated external links or HTML interpretation.

Inspection records reject mismatched pack/version/mode/scope and baseline
numeric proposals. Unknown/unsupported capability blocks resource approval;
limit and HPA-floor proposals remain refused by the resource-request workflow.
Production actions remain disabled without an independent authenticated backend.
The standalone preview alone supports synthetic `?scenario=empty`, `denied`,
`baseline`, `guarded`, `unsupported`, `limit` and `floor` test states.

Use the reviewed package's generated assets together; do not combine catalog,
schema or Headlamp assets from different versions. Independent operator review,
source validation and production deployment approval cannot be inferred from
automated offline tests.

## Autoscaler packs

Seven separately selectable version 2.0.0 packs cover autoscaler assessments:

| Pack | Purpose and evidence boundary |
|---|---|
| [AKS-AS-001](../src/aks_fleet_efficiency/catalog/packs/fixed-replica-review.yaml) | Current fixed-replica investigation with observed HPA/KEDA absence. Uses `thresholds.minimum_replicas_for_autoscaling_review` (default 2, minimum 1); no historical absence or replica target. |
| [AKS-AS-002](../src/aks_fleet_efficiency/catalog/packs/autoscaler-interaction.yaml) | Current utilization/request-denominator overlap with matching mutating VPA resource policy. Exact-container policy overrides wildcard policy; absolute/external targets do not establish this interaction. |
| [AKS-AS-003](../src/aks_fleet_efficiency/catalog/packs/hpa-pinning.yaml) | Four full-grid HPA UID/workload UID histories support a sampled floor/ceiling/fixed investigation. Current counts never backfill history; independent of VPA policy and CPU usage. |
| [AKS-AS-004](../src/aks_fleet_efficiency/catalog/packs/controller-responsibility.yaml) | Current KEDA ownership/activation and multiple-controller investigation. KEDA and its generated HPA are one chain; no trigger values, authentication or safe zero target. |
| [AKS-AS-005](../src/aks_fleet_efficiency/catalog/packs/hpa-floor-proposal.yaml) | Separately default-off guarded positive HPA minimum proposal with all seven full-grid histories and exact configuration-bound owner availability/scenario/reliability reviews. |
| [AKS-AS-006](../src/aks_fleet_efficiency/catalog/packs/hpa-change-review.yaml) | Independent changing HPA bounds/count-context investigation, not an oscillation, scaling-lag or unmet-demand diagnosis. |
| [AKS-AS-007](../src/aks_fleet_efficiency/catalog/packs/vpa-bounds-review.yaml) | Current VPA status/policy targets and bounds in mCPU/MiB are context, not advisor request/limit authorization or proof of recommendation freshness. |

AS-001/002/004/007 are inventory-only: no Prometheus client, source or history is
required. Eligible current investigations survive unrelated missing history.
AS-003/006 share four packaged HPA gauge expressions; AS-005 additionally uses
desired/observed/available workload replica queries. Selectors retain both exact
historical workload UID and HPA UID; shared dependencies never merge controllers.
The identity-enriched profile is version 1.3.0. Existing `aks_advisor:*` recordings
must already preserve historical identity; none are installed or backfilled.

Pack parameters cannot enable floor proposals or override owner bounds.
`ReplicaSafetyPolicy.allow_floor_reduction` remains strictly default-off; guarded
mode alone is not approval. Baseline blocks numeric proposals. The
[qualified floor golden](../examples/expected-hpa-floor-pack.md) retains 2 to 1,
leaving HPA maximum, signals, requests and limits unchanged. Missing, stale,
partial, low-coverage, changed-controller or contradictory history stays blocked.
KEDA/StatefulSet/PDB/unsupported scheduling, state, overhead and zero-floor shapes
remain unsupported. Savings stay null; approval, one-dimensional canary and
restoration of the original floor belong to customer tooling. Headlamp still
refuses floor proposals through its resource-request approval path.

```powershell
aks-fleet-advisor catalog show AKS-AS-002
aks-fleet-advisor analyze --snapshot examples\fixtures\interaction-pack-snapshot.json --pack AKS-AS-002 --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor analyze --snapshot examples\fixtures\hpa-floor-pack-snapshot.json --pack AKS-AS-005 --mode guarded --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor catalog export AKS-AS-005 --config examples\cpu-pack-config.yaml --source synthetic --entities examples\autoscaler-pack-entities.json --mode guarded --output autoscaler-queries
```

These offline examples are synthetic evidence, not live certification or approval.
Query-only export does not establish that assessment safety gates passed.

## Memory and reliability packs

Eight separately selectable version 2.0.0 packs cover memory and reliability:

| Pack | Purpose and evidence boundary |
|---|---|
| [AKS-MEM-001](../src/aks_fleet_efficiency/catalog/packs/oom-investigation.yaml) | Investigate complete identity-bound OOM counts. Independently valid working-set/request/limit history is context only; neither CPU absence nor active controllers hide the investigation. |
| [AKS-MEM-002](../src/aks_fleet_efficiency/catalog/packs/memory-safety-review.yaml) | Informational readiness using independent memory, owner scenario, QoS, controller and reliability gates. No numeric target. |
| [AKS-MEM-003](../src/aks_fleet_efficiency/catalog/packs/memory-request-proposal.yaml) | Default-off guarded request-only proposal from supported direct or approved complete-roster envelopes. Limits, CPU and QoS remain unchanged. |
| [AKS-MEM-004](../src/aks_fleet_efficiency/catalog/packs/pod-memory-accounting.yaml) | Current effective-Pod request accounting, including native sidecar/init ordering and overhead. Not historical usage or packing feasibility. |
| [AKS-MEM-005](../src/aks_fleet_efficiency/catalog/packs/memory-limit-proposal.yaml) | Separate default-off guarded single-Pod limit proposal. Requires full-memory usage, admission/configuration binding, reviewed allocator/scenarios and complete zero reliability history; working set alone is insufficient. |
| [AKS-REL-001](../src/aks_fleet_efficiency/catalog/packs/restart-investigation.yaml) | Complete direct or approved roster-bound restart investigation. No inferred OOM cause or resource target. |
| [AKS-REL-002](../src/aks_fleet_efficiency/catalog/packs/termination-context.yaml) | Current UID-bound last-termination context. Exit code 137 alone is not OOM proof or a diagnosis of all restarts. |
| [AKS-REL-003](../src/aks_fleet_efficiency/catalog/packs/eviction-investigation.yaml) | Independently qualified workload eviction history, emitted once per workload. Counts do not establish node-pressure causes or SLO impact. |

MEM-004 and REL-002 are inventory-only: they have no PromQL requirement.
The other packs own their required direct/envelope/workload query references;
shared expressions are used by export and collection. OOM/restart investigations
do not require optional CPU or memory context to be present. Optional context is
included only when its independent evidence is eligible.

Memory bounds remain exact-container owner policy, not `review_ratio` parameters.
Pack parameters cannot enable a proposal. Baseline blocks numeric request/limit
proposals, and guarded mode still requires separate strict policy opt-ins.
Unknown, stale, partial, low-coverage or contradictory evidence remains blocked.
Admission, QoS, controller, peak, full-grid and historical membership evidence
are mandatory. Explicitly unsupported source profiles veto numeric proposals.

```powershell
aks-fleet-advisor catalog show AKS-MEM-003
aks-fleet-advisor analyze --snapshot examples\fixtures\memory-request-pack-snapshot.json --pack AKS-MEM-003 --mode guarded --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor analyze --snapshot examples\fixtures\memory-limit-pack-snapshot.json --pack AKS-MEM-005 --mode guarded --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor analyze --snapshot examples\fixtures\pod-memory-pack-snapshot.json --pack AKS-MEM-004 --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor catalog export AKS-MEM-005 --config examples\cpu-pack-config.yaml --source synthetic --entities examples\cpu-pack-entities.json --mode guarded --output memory-limit-queries
```

The [request](../examples/expected-memory-request-pack.md),
[limit](../examples/expected-memory-limit-pack.md) and
[accounting](../examples/expected-pod-memory-pack.md) synthetic goldens preserve
313 MiB per replica, a separate 1024-to-600 MiB limit with the 512 MiB request
unchanged, and 1184 MiB current Pod accounting. These are fixtures, not customer
measurements or approval. Request and limit changes never coexist in one finding
or canary. Limits remain unsupported for replica/churn histories, Pod budgets,
unknown/active controllers and unsupported admission/overhead/QoS shapes.

Titles, summaries, limitations and operator guidance live in the manifests;
literal memory-only placeholders fill already-derived current/proposed values
without evaluating collected text. Guidance/digests cannot establish source
attestation. Algorithm changes still require typed code, versioning and tests.

## CPU request and pool review packs

Three version 2.0.0 packs provide investigations without numeric proposals:

| Pack | Evidence | Output and limitations |
|---|---|---|
| [AKS-RQ-001](../src/aks_fleet_efficiency/catalog/packs/missing-cpu-request.yaml) | Complete fresh scoped inventory/metadata and explicitly observed admitted request state | Current missing/zero request review. Unobserved/omitted state stays blocked. No metric history, request target or PromQL queries required. |
| [AKS-RQ-003](../src/aks_fleet_efficiency/catalog/packs/cpu-request-risk.yaml) | Observed positive request, exact identity and qualified P95/throttling history | Investigate a high request ratio, not proof of saturation or a CPU limit. No resources, replicas or savings proposed. |
| [AKS-NP-001](../src/aks_fleet_efficiency/catalog/packs/node-pool-review.yaml) | Exact pool/historical node identity, complete membership, aligned usage and constant capacity | Low-utilization investigation only. No removable-node claim, NAP eligibility or packing simulation. NAP-managed/empty pools are excluded. |

Both assessment modes retain the same review-only boundaries for these packs.
Metric dependencies and operator guidance live in the manifests; shared gates
still validate source scope, freshness, quality, units and observation windows.
Inventory-only selection does not construct metric/credential clients and does
not require a metric source for readiness. Permission/endpoint approval remains
unknown until separately established.

```powershell
aks-fleet-advisor catalog show AKS-RQ-001
aks-fleet-advisor analyze --snapshot examples\fixtures\missing-request-snapshot.json --pack AKS-RQ-001 --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor analyze --snapshot examples\fixtures\request-risk-snapshot.json --pack AKS-RQ-003 --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor analyze --snapshot examples\fixtures\pool-review-snapshot.json --pack AKS-NP-001 --as-of 2026-10-29T12:00:00Z
aks-fleet-advisor catalog export AKS-NP-001 --config examples\cpu-pack-config.yaml --source synthetic --entities examples\pool-pack-entities.json --output pool-queries
```

Compare [missing request](../examples/expected-missing-request.md),
[request risk](../examples/expected-request-risk.md) and
[pool review](../examples/expected-pool-review.md) synthetic goldens.
The pool export contains three queries per historical node, not a fabricated
pool-total percentile. Current membership alone, missing node series or changed
capacity leaves normalization unsupported. `catalog export/capabilities` clearly
reject Prometheus operations for the inventory-only pack.

Parameters are validated by the closed evaluator, not by an executable rule DSL:

```yaml
packs: [AKS-RQ-001, AKS-RQ-003, AKS-NP-001]
pack_parameters:
  AKS-RQ-003:
    review_ratio: 0.9
  AKS-NP-001:
    review_ratio: 0.2
```

The request-risk ratio must be positive and finite; a threshold above one is
valid. The pool ratio must satisfy `0 <= ratio < 1`; zero disables its low-usage
signal, not evidence-gap reporting. Inventory accepts no ratio.
Unknown parameters fail visibly.

Request-risk thresholds are independent of reduction thresholds, including
when only the risk pack is selected. Unknown request observations or identities
block that review. Validate actual source mappings in an approved pilot before
relying on a customer assessment.

## What the CPU pack does

The [manifest](../src/aks_fleet_efficiency/catalog/packs/cpu-request.yaml) describes
queries, evidence, parameters, limitations and operator guidance.
[Shared PromQL assets](../src/aks_fleet_efficiency/catalog/queries.yaml) are used by
both export and collection; the evaluator is typed Python, not executable YAML.

| Mode | CPU output | Required boundary |
|---|---|---|
| `baseline` (default) | Investigate low P95 usage relative to the current admitted request | Complete fresh scoped sources, exact identity, qualified usage and an observed positive request. No safe target or node-removal claim. |
| `guarded` | Independently policy-bounded CPU request proposal | All existing peak/P99, throttling, OOM, eviction, controller, owner, window and environment gates. Separate approval/canary required. |

Baseline reports cannot contain numeric CPU/memory request, memory limit or
replica-floor proposals. Memory and autoscaler proposals retain their gates and
appear blocked with `guarded_mode_required` when applicable. Guarded mode does
not enable default-off memory/limit/floor policies or authorize changes.

The CPU rule uses version **2.1.0** for mode/pack semantics and the explicit
unsupported-source-profile guard. [Source profiles](source-profiles.md) also
provide unresolved baseline measurements without historical UID claims.
Use schema 1.0 and the parameters below. Unsupported configuration is rejected,
not silently translated.

## Inspect and export without contacting endpoints

```powershell
aks-fleet-advisor catalog list
aks-fleet-advisor catalog show AKS-RQ-002
aks-fleet-advisor catalog export AKS-RQ-002 --config examples\cpu-pack-config.yaml --source synthetic --entities examples\cpu-pack-entities.json --output cpu-queries
```

The [profile](../examples/cpu-pack-config.yaml) and
[entity list](../examples/cpu-pack-entities.json) are synthetic. The output
directory must be new and its parent must exist. Export performs no
authentication, endpoint requests, exporter installation or recording-rule writes.

`show` returns one JSON object containing the manifest and provenance.
`export` writes valid, fully scope-resolved `.promql` files and a final typed
manifest containing source, step, entity/expression digests and pack provenance.
Packaged templates use `__scope__`/`__step__` insertion points and are not advertised
as directly executable queries. Only rendered exports are executable PromQL.

Every export must match a declared source's exact cluster allowlist and the
required labels. Names cannot substitute for historical workload/Pod UIDs.
Approved replica envelopes require `membership_digest`, not a fake Pod UID.
Selectors escape collected values as data. Unknown sources, packs, missing/colliding
mappings and unsupported/duplicate/foreign entities are rejected.

Generic and public-Azure managed Prometheus transports are declared, not
live-certified source profiles. Custom `aks_advisor:*` recordings are not built-in
AKS series, and exporting their queries does not create or backfill them.

## Assess CPU requests

```powershell
aks-fleet-advisor assess --fragments examples\fixtures\history-assessment.json --config examples\cpu-pack-config.yaml --mode baseline --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor assess --fragments examples\fixtures\history-assessment.json --config examples\cpu-pack-config.yaml --mode guarded --as-of 2026-10-29T12:00:00Z --format markdown --artifacts cpu-assessment
```

Compare [baseline](../examples/expected-cpu-pack-baseline.md) and
[guarded](../examples/expected-cpu-pack-guarded.md) output. The guarded synthetic
case preserves the 1000-to-500 mCPU proposal. Both commands exit `3` because the
supplied fragment has an unrelated unsupported pool-evidence gap; CPU pack
selection never turns a partial source assessment into a full-fleet success.

`analyze` and `assess` also accept repeatable `--pack AKS-RQ-002`. Unknown or
unimplemented pack IDs fail, rather than selecting an unrelated rule.
Without `packs`, all existing rules are evaluated in the selected mode; reports
retain the selected manifest/query provenance for all 21 packs.

For approved combined live assessment, explicit pack selection narrows the
collection plan to the intersection of approved metrics and mode-specific pack
dependencies. It never adds unapproved queries or modifies the caller's plan.
Missing required inputs remain visible gaps. Endpoint access still requires the
separately approved plan, identity and `--allow-live`.

## Customize a review parameter, not a safety target

```yaml
mode: baseline
packs: [AKS-RQ-002]
pack_parameters:
  AKS-RQ-002:
    review_ratio: 0.4
```

`review_ratio` is a strict finite number between zero and one. Equality does not
trigger a low-usage finding. It is a review threshold, not desired utilization
or a CPU target.

The guarded target still rounds upward within independently declared owner
minimum/reduction/headroom bounds and observed peaks. Lowering a review threshold
cannot bypass eligibility or reliability gates.

## Replay and provenance

Reports retain mode, selected pack versions/digests, typed parameters and shared
query definitions. Actual metric collection additionally retains the exact query
expression in `MetricQuality.query_expression`; CPU findings expose these source
queries in metadata. Imported summaries lacking that field remain explicitly
unknown (`null`), not falsely attributed to today's query definitions.

Assessment artifacts save the effective configuration, including `pack_locks`.
The lock binds the manifest and query definitions; changing either causes an
explicit replay/preflight failure, not substitution of the newest pack.
Algorithm changes require a rule version change. Pack locks are integrity
identifiers, not source attestation or change approval.

```powershell
aks-fleet-advisor analyze --snapshot cpu-assessment\snapshot.json --config cpu-assessment\analysis-config.json --as-of 2026-10-29T12:00:00Z --format json
```

Do not change mode, parameters, clock or evidence and call the result identical
replay. A fresh deliberate assessment can use a new configuration without a lock.
Saved artifacts and query exports contain scoped identifiers and follow the
same classification/access/retention policy as reports.

## Verify the installation

For source-checkout verification, run `make verify` or
`.\.venv\Scripts\python.exe scripts\verify.py` with the
[development dependencies and pinned tool](../CONTRIBUTING.md) installed.
The verifier checks catalog/schema consistency, synthetic evidence, query
expressions and source/installed-wheel replay without contacting live sources.
It does not establish permissions, retained history, source authenticity or
customer deployment acceptance. Use the [source compatibility worksheet](source-compatibility.md)
for those environment-specific checks.
