# Aggregate Fleet Insights

[Documentation home](README.md) | [Recommendation packs](recommendation-packs.md) | [Data contracts](data-contracts.md)

Use `fleet summarize` to combine two or more completed `assessment.json` artifacts into one read-only view. The command performs no Azure, Kubernetes or Prometheus requests. Azure Kubernetes Fleet Manager is not required.

Fleet aggregation answers questions such as:

- Which clusters or declared peer groups contain the most findings or blocked evidence?
- Which rule IDs recur across explicitly assessed clusters?
- Which missing source, identity or reliability reasons recur?
- Which clusters have available, unavailable, unknown or unsupported source capabilities?
- Which fixed/CAS and verified static/dynamic NAP pool objects were observed, with unknown classes retained?
- Which ARM pool objects explicitly declare Spot or regular priority, with omitted priority kept unknown?
- Which distinct UID-bound workload owners have listed Pods, including DaemonSets and Jobs outside vertical rightsizing eligibility?
- Which exact Namespace UIDs contain those workload kinds, and where is an admitted window-matched review-owner declaration missing?
- Which finding categories, rules and blockers recur within each declared peer group?
- Are the assessment windows, modes, configurations and pack definitions comparable?

It does not calculate a fleet efficiency score, choose a target cluster, pool spare capacity across clusters, recommend placement or estimate savings.

## Try It With Two Fictional Clusters

Follow the [fictional fleet lab](../examples/fleet-lab.md) to create and compare two assessment bundles and see why a different check makes a second comparison unsuitable for ranking. The same guide is included in the standalone fleet-lab ZIP. No optional dependencies or credentials are needed.

## Prepare Comparable Assessments

Generate each assessment through the ordinary saved-fragment or explicitly approved collection workflow. Preserve each complete artifact directory. Pass the `assessment.json` file from each directory; do not extract and edit its embedded report.

Each input must contain:

- One tenant shared by every input.
- Distinct exact Azure cluster resource IDs and Kubernetes cluster fingerprints.
- Collection provenance and the original source-capability records.
- The normalized snapshot and deterministic analysis report.
- The original sibling `manifest.json`, `fragments.json`, `snapshot.json`, `analysis-config.json` and `report.md` files, with intact hashes and matching locked configuration.
- An aware evaluation time supplied to the fleet command.

The command validates the complete bounded artifact bundle and replays its report with the saved locked configuration at the original report time. Edited findings, severity, evidence, capability records or configuration are rejected, including consistently rehashed report edits. Hashes and deterministic replay establish consistency, not source authentication or approval. Keep the compatible package for replay; do not reseal old artifacts with new pack definitions.

Provide one `--peer-group` for each `--assessment`, in the same order. A peer group is operator-supplied comparison context such as `production`, `nonproduction`, `regional-api` or `platform-generation-2`. It is not source attestation, workload portability or an authorization boundary.

```powershell
aks-fleet-advisor fleet summarize `
  --assessment .local/cluster-a/assessment.json `
  --peer-group production `
  --assessment .local/cluster-b/assessment.json `
  --peer-group production `
  --as-of 2026-10-29T12:00:00Z `
  --format markdown `
  --output .local/fleet-insights.md
```

Use a fresh output path. JSON output follows [`fleet-insight.schema.json`](../schemas/fleet-insight.schema.json).

## Understand Comparability

The command always preserves each cluster's findings and source status. It sets `comparable: false` when inputs differ in observation window, analysis mode, pack definitions or analysis configuration. Those differences are reported as explicit reason codes; the command does not silently normalize them.

Window comparability uses the exact start and end times. Different sample counts or coverage ratios remain visible in each cluster record; they do not become an `observation_windows_differ` result or imply equal evidence quality.

Each peer-group record has its own `comparable` flag and reasons. A compatible production group can remain comparable internally even when another group's window makes the whole fleet non-comparable. A single-cluster group is consistent with its own basis; it establishes no comparison with another group. Counts for non-comparable inputs are retained as descriptive observations, not rankings or normalized demand.

Non-comparable inputs can still show which findings and gaps exist in each cluster. They must not be used for relative ranking or to claim one cluster is more efficient than another.

## Interpret The Output

The summary contains cluster, peer-group, recommendation, blocked-finding and high/critical counts. `rule_counts` counts eligible findings by deterministic rule ID. `blocked_reason_counts` counts every reported blocker, so one blocked finding can contribute more than one reason.

Each cluster record retains exact identity, location, environment, peer group, assessment status, mode, window, source capabilities and capability-status counts. Names and peer groups are display/grouping data; exact IDs and fingerprints remain the identity anchors.

## Inventory Breakdowns

Each cluster retains `supply_inventory` and `workload_inventory`, their observation times and reason codes. These dimensions use complete exact-scoped Azure/Kubernetes receipts, identity bindings and configured freshness limits at the **original assessment time**. The fleet command's generation time does not recollect evidence or make it current. Missing metrics do not erase qualified current inventory, and inventory availability never supplies historical usage, a numeric target or source authentication.

`available` means the bounded count is supported, not that the cluster is healthy or all V1 evidence exists. `partial` retains admitted counts while an ownership/classification/API gap remains. `unknown` leaves the affected counts `null` because missing, stale, future, foreign or incomplete prerequisites prevent the count. An empty dictionary with available inventory is an observed zero, not unknown data.

Supply `pool_counts` counts **objects**, not nodes, replicas, workload placement or removable capacity. Fixed/CAS classes use explicit ARM pool autoscaling state; missing state is an observed `unknown` object. `nap_static` and `nap_dynamic` require observed Auto mode, a successful versioned NodePool inventory and an exact resolved AKS node-class binding with observed node-class inventory. Unverified NodePool objects stay unknown. A missing NAP list leaves the supply dimension partial rather than silently proving no NAP objects. ARM pools and Karpenter NodePools remain distinct objects; static replica counts are not added as nodes. Pool objects remain cluster-scoped; namespace exclusions affect workload counts, not these pool definitions.

Workload `workload_counts` counts distinct current owner UIDs with listed Pods for the supported Deployment, StatefulSet, DaemonSet and Job owner chains. Multiple Pods of one DaemonSet count as one owner. It does not enumerate controllers with no Pods, ready replicas, historical membership or every Kubernetes kind. Unresolved or contradictory owner identities remain explicit through `unresolved_pods` and reason codes. `observed_pods` counts listed objects, not healthy/running replicas. The assessment's exact `excluded_namespaces` is retained and applied to these counts.

Cluster records retain their own `rule_counts`, `category_counts` and `blocked_reason_counts`. Peer-group records preserve sorted member resource IDs, finding/source-status counts, summed observed pool/workload counts and `inventory_status_counts` by cluster for both dimensions. Wholly unknown group dimensions remain `null`; partially observed group totals include only admitted counts and must be read with their status counts. Capability-status counts count original per-pack/source/mode records, not distinct sources or healthy clusters.

`supply_inventory.arm_pool_market` independently counts current ARM pool objects as `spot`, `regular` or `unknown` using only the admitted nullable ARM priority field. Explicit false establishes regular priority; omission is not false. Original source clocks and exact inventory gates apply. Unresolved NAP classification does not erase otherwise qualified ARM priority counts. These are not Node counts, actual workload market, NAP capacity-type policy or historical Spot/fallback persistence. Peer groups expose `arm_pool_market_counts` and per-cluster `arm_pool_market` status counts; wholly unknown counts stay null, and partial totals must be read with their status counts.

`workload_inventory.namespace_distribution` retains separate rows for exact current Namespace name/UID bindings, deduplicated workload-kind counts, listed Pods and unresolved Pods. Missing Namespace UID is explicit, never joined to another same-named Namespace. Namespace exclusions match the ordinary workload inventory; they do not alter the separate all-namespace scheduling reservation audit. Rows are per cluster, not name-joined across clusters or recreated UIDs.

`workload_investigations` lists resolved current workload UIDs with Namespace UID/kind/name and `review_owner_status` of `declared` or `unknown`, plus machine gaps. Declared means exactly one admitted normalized workload with matching UID/Namespace/kind/name carries a nonblank review owner for the exact assessment window. Missing, ambiguous, mismatched or wrong-window policy context remains unknown. Owner names, SLO references and policy prose are not copied. This is review-context coverage, not business ownership, authorization or approval. `review_owner_status_counts` counts resolved included workload identities only; unresolved Pods remain a separate gap, not invented named workloads. Peer-group coverage totals follow the same admitted-count/unknown conventions.

Each resolved workload investigation also retains `observed_supply`: listed current Pod counts by independently qualified existing ARM provider/pool or NAP Node/NodeClaim/NodePool UID bindings. Capacity scope, fingerprint and original clocks must agree with scheduling evidence. Missing or conflicting joins stay an explicit `unknown` bucket; stale/foreign capacity leaves this dimension null without erasing independently valid workload counts. These are current observed associations, not eligible placement, actual Node market or historical market persistence. A Node with contradictory ARM and NAP bindings is not assigned by preference.

The new rows use existing admitted evidence without additional collection. Scheduling feasibility, actual Node market, historical Spot/fallback attribution and business-owner routing remain unestablished. No spare capacity or workload portability is inferred. Repeated-snapshot observations remain the separate workflow below.

## Current Resource Envelopes

Each cluster's `resource_envelope` separately reports current Kubernetes Node `capacity`, `allocatable` and effective admitted nonterminal Pod `requested` CPU/memory, in mCPU/MiB. These values come from normalized snapshot-bound approved fields and retain original observation times, dimension status and reason codes. Node totals cover all listed Nodes; Pod totals honor the assessment's namespace exclusions and include Pending as well as Running requests. They are not usage, ready capacity, unreserved capacity or placement eligibility. Kubernetes Node capacity is not Azure billed/provisioned capacity.

Requests use admitted containers, ordered init/restartable-sidecar accounting and explicit Pod overhead, never controller templates. Unknown phase, missing components, unsupported Pod budgets or a missing quantity make the affected total unknown rather than supplying zero or summing only survivors. CPU and memory remain independent: valid memory can survive missing CPU. Explicit terminal Pods are excluded, complete empty lists can produce zero, and overflow becomes unknown. Missing or partial required inventory blocks the affected envelope.

For one replay-qualified cluster, `current_gaps` reports `capacity_minus_allocatable` and signed `allocatable_minus_requests`, independently in mCPU and MiB. The envelope retains the original inventory observation time; each gap reports covered and expected Nodes, and covered and expected nonterminal Pods for the request comparison. A Node with known allocatable above capacity blocks that dimension even if totals balance. The request comparison is withheld if namespace exclusions remove any nonterminal or unknown-phase Pod, rather than subtracting a scoped request total from cluster-wide allocatable. Pending requests count toward the comparison; the result is not live free capacity, schedulable headroom, safe reduction, or savings. A complete observed zero is a value; an unsupported difference is null with a reason.

Peer-group current totals are calculated only for comparable groups and only when every member supplies the particular resource dimension. Missing member CPU does not become a partial CPU total; incompatible groups retain null totals and `peer_group_not_comparable`. Original observation times remain visible because separate collection calls are not a transactional fleet snapshot. No free-capacity subtraction or cross-cluster portability claim is made.

`observed_usage` stays null, and `requests_minus_usage` reports `aligned_cluster_usage_unavailable`. The retained per-entity/pool percentiles do not provide aligned cluster-level samples; summing their P95/P99 values would invent a different statistic. The optional saved-history path below is separate: Node usage does not establish usage of the admitted Pod roster, even on the same cluster. Azure provisioned/billed capacity and actual producer completeness are not supplied by that path.

## Review Saved Historical Contributions

Use `fleet review-node-history` for an explicitly prepared [historical Node evidence file](../schemas/historical-node-evidence.schema.json). It contains exact tenant/cluster/fingerprint and Node UID/resource bindings, declared source/profile/version/mapping, UTC range/step, independent CPU and memory receipts, and a complete explicit Node roster at each evaluation point. CPU is a separately characterized rate of `node_cpu_usage_seconds_total` in mCPU with an explicit rate window; memory is `node_memory_working_set_bytes` converted to MiB. Container working set, total-minus-available and current Node membership are not substitutes. This contract does not install or characterize a producer.

```text
aks-fleet-advisor fleet review-node-history --history approved-node-history.json --tenant <tenant-id> --cluster <exact-cluster-resource-id> --as-of <utc-time> --output node-history-review.json
```

For a runnable offline example, the canonical [synthetic history](../examples/fixtures/node-history-evidence.json) contains two fictional Nodes over a ten-minute grid ending October 29, 2026 at 12:00 UTC. From the repository root, use a fresh output path:

```text
aks-fleet-advisor fleet review-node-history --history examples/fixtures/node-history-evidence.json --tenant 00000000-0000-0000-0000-000000000000 --cluster /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic --as-of 2026-10-29T12:00:00Z --output .local/node-history-example.json
```

Expect CPU P95 1000 mCPU and Node-working-set P99 200 MiB, with source admission still unverified. This demonstrates aligned arithmetic, not representative demand or an installed historical producer. Do not use the example evaluation clock to make real stale evidence current.

The reviewer sums aligned complete Node contributions first, then calculates inclusive CPU P95 and Node-working-set P99. Missing membership or an evaluation point withholds that dimension's percentile, never sums only surviving Nodes, and never fills missing values with zero. CPU and memory remain independent. A complete explicitly empty supplied roster can yield observed zero, but still does not authenticate the roster. Duplicate/foreign contributors, changed UID bindings, malformed/nonfinite quantities, off-grid timestamps and exceeded budgets are refused. Original source/sample clocks and independent recent-tail checks remain explicit; retrieval completion cannot refresh a historical membership timestamp. Expected grids, total memberships/contributions and output are bounded to 100,000 points, 100,000 rows and 32 MiB respectively.

Repeat `--node-history approved-node-history.json` on `fleet summarize` to attach histories to exact original assessments. Each history must match tenant/resource ID/fingerprint and lie inside its original report window; it is re-evaluated at the original report clock and configured age policy. Unknown or duplicate selected cluster bindings are rejected. Historical peer totals require every selected cluster's full grid and compatible profile/version/mapping, measure, rate window and resolution. Aligned cluster contributions are summed before peer percentiles; unlike percentiles are never added. Missing CPU does not erase independently complete memory. The JSON/Markdown output keeps the historical window and gaps separate from current capacity. The only source state is `unverified_saved_contributions`; neither a complete grid nor matching hashes certifies the real producer, continuous observation, safe sizing, free/movable capacity or financial value. Actual query/dashboard source support requires independently characterized existing recordings and UID/membership mappings.

## Supply Declared Routing And Market Context

Repeat `--context approved-fleet-context.json` on `fleet summarize` for the separate [fleet context](../schemas/fleet-context.schema.json). It binds one exact tenant/cluster/fingerprint and declared source/profile/version to opaque business-owner references and optional sampled market history. All supplemental history/context files share a 32 MiB input budget. Old assessments and ordinary output are unchanged when these options are absent.

Business-owner declarations bind exact Namespace/workload UIDs, a SHA-256-shaped opaque owner reference and an explicit validity interval covering the original report window. These are routing declarations, not authenticated ownership or change authority. Missing/stale/future/wrong-window declarations remain unknown; conflicting owners yield no selected reference. Unmatched declarations are counted separately rather than assigned to a same-named workload. Review-owner policy coverage remains a separate existing dimension. No contact names, email addresses, scraped owner labels or owner/SLO prose are added.

Optional market history carries an explicit UTC grid, complete per-point Node UID/resource roster, `spot`/`regular`/`unknown` labels and original receipts. Missing points/receipts, stale tails and contradictory same-UID market labels withhold affected counts; unknown market stays a separate bucket. These are supplied source observations, not NAP capacity-type policy or inferred actual-market certification. Fallback records require a separate complete scoped receipt, distinct exact historical Node bindings, original timestamps and opaque upstream references. An empty or missing fallback export never follows from market transitions; without the separate receipt, fallback remains null. All context retains `unverified_saved_context`; no placement, portability, replacement, availability or savings conclusion follows.

Estimated monthly savings is always `null`. A recurring recommendation is an investigation priority, not proof of safe remediation, workload portability, node removal or financial value.

## Compare Repeated Assessments

Use `fleet trends` for two or more explicit saved assessments across one or more clusters. It needs no history-store import, new collection or Azure Kubernetes Fleet Manager. First create the two fictional directories in the [artifact comparison walkthrough](operations/history.md#compare-artifact-directories), then run:

```powershell
aks-fleet-advisor fleet trends --assessment comparison-previous/assessment.json --peer-group production --assessment comparison-current/assessment.json --peer-group production --tenant 00000000-0000-0000-0000-000000000000
```

This example evaluates the same retained evidence at two report times; it demonstrates comparison, not independently recollected measurements. For your own fleet, repeat `--assessment` and supply one `--peer-group` per input. Every assessment must retain its complete original artifact bundle, describe exactly one cluster and pass original-file integrity, tenant/configuration bindings and locked report replay. Provide the approved tenant explicitly. Input order does not select chronology: each series is sorted by original evaluation time, window end and content ID, and comparison requires strictly increasing report times and nondecreasing window ends.

JSON follows [fleet-history-trend.schema.json](../schemas/fleet-history-trend.schema.json). A series is keyed by the exact cluster resource ID, fingerprint and declared peer group. Recreated fingerprints and changed peer groups form separate series rather than stitching identities or cohorts. Each record retains its run summaries and consecutive pairwise comparisons with the same six states as direct artifact comparison. Incompatible scope/configuration/pack/window-duration bases produce `not_comparable`; independent compatible series remain useful. A single-sample series has `insufficient_samples`, no comparisons and unknown recurrence.

`recurring_findings` lists exact recreation-aware finding IDs eligible in at least two selected runs only when the whole series has a compatible basis. `observed_runs` counts eligible report records, not independent measurement windows, continuous persistence or a lifetime history. First/last times refer to those selected report records and do not refresh source evidence. Missing or stale data remains `not_observed` or `blocked` according to the retained pairwise rules; an absent finding never proves resolution. Incompatible or single-sample recurrence is `null`, not an empty successful result.

Bounds are 2..100 selected bundles, 32 MiB original payload per bundle and 128 MiB total payload across the selection. Duplicate content IDs, invalid peer labels, foreign tenants, links/junctions, missing files, altered reports and invalid clocks fail closed. The command writes no store or output directories and prints JSON; valid partial or non-comparable evidence exits `0`, invalid inputs exit `2` with values omitted from errors. Peer labels remain untrusted display/grouping data. No cross-cluster resource transfer, historical usage aggregation, financial trend, automatic resolution, ranking or approval is calculated, and estimated monthly savings stays `null`.

### Project a fleet drift matrix

Add `--format matrix --as-of 2026-10-29T13:00:00Z` to the same command (choose an explicit UTC clock at or after the latest selected report). The [matrix schema](../schemas/fleet-drift-matrix.schema.json) adds one row per exact cluster/fingerprint/declared peer group. Each row gives the latest report age, original window and metric sample count/coverage, current resource envelope, latest pairwise findings and compatible recurrence. The previous resource envelope is included only when the latest pair is comparable; its values remain separate, not normalized deltas or evidence of equivalent demand. Missing quantities remain unknown. Report age is not metric freshness; the resource envelope retains its original inventory observation time.

The matrix additionally refuses comparisons across known source identity/profile/step, observed controller UID, or workload safety-policy changes. Unknown observations are not filled from a different run. It retains only the latest pair per series and suppresses recurrence if any selected pair has an incompatible basis. Output is capped at 4 MiB. Run IDs identify protected originals but do not grant access; display or resolve them only for the already authorized audience. The offline output contains no paths or links and is not published to Headlamp or Grafana by this command.

`check_evidence` keeps counts for each selected pack alongside its replayed version and digest. Examined subjects, qualified findings, blocked records, and high or critical findings are separate counts, not a coverage fraction. One pack can record a blocker for missing inventory without examining any subjects. The report does not retain an independently established expected subject roster, so check coverage remains unknown even if recorded blocker counts fall. Do not sum examined subjects across packs or treat zero findings as a pass. Older matrices without this field have no per-pack evidence.

### Export a protected Grafana evidence snapshot

Use this view when live telemetry cannot tell you what a prior advisor run actually assessed. Generate importable Grafana JSON from the **same original assessment bundles**. No datasource, Headlamp installation, export agent, or Grafana credentials are needed to generate it.

```powershell
aks-fleet-advisor fleet trends --assessment comparison-previous/assessment.json --peer-group production --assessment comparison-current/assessment.json --peer-group production --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T13:00:00Z --format grafana > fleet-evidence.json
```

In the authorized Grafana instance, use **Dashboards → Import** and select `fleet-evidence.json`. For each cluster/fingerprint/peer group, the text panels show original run/window and inventory clocks, age **at export**, recurrence by rule, metric coverage, signed inventory gaps where qualified, and a separate table of the latest selected packs, versions, examined subjects, qualified findings, blockers, and high or critical findings. The prior resources are shown beside the latest only for the latest comparable pair. CPU and memory remain separate; request-minus-usage stays unknown without qualified evidence. Grafana's time picker does not refresh or reinterpret this snapshot. Regenerate from approved bundles for the next review.

**The JSON itself contains protected assessment data.** Generate it in approved private storage. Import only into an instance and folder whose permissions have been verified for the entire snapshot audience; test direct dashboard access with an unauthorized identity. Do not use public dashboards, shared snapshots, public exports, or dashboard URLs that expose the archive. Run IDs are opaque references for authorized operators, not URLs or authorization tokens. Delete obsolete imported copies per the retention policy. The command keeps originals local and does not publish to Grafana or contact any source.
