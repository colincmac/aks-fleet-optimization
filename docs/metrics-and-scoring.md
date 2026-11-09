# Metrics and scoring

## Metric semantics

All time-series calculations use the report's declared observation window and step. The collector must record sample count and coverage per entity and metric. Production assessments should include peak, failover, batch, and business-cycle periods; the default minimum is 30 days, not a guarantee of representativeness. Any alternative minimum must be explicitly configured. Saved snapshots retain their actual declared window; analysis never silently extends missing history.

| Metric | Formula | Interpretation |
|---|---|---|
| Container CPU request efficiency | `usage_cpu_p95 / request_cpu` | How much of the requested CPU is used at P95 |
| Container memory request efficiency | `usage_memory_p95 / request_memory` | How much requested memory is used at P95 |
| Node-pool CPU utilization | `p95(sum(aligned node CPU usage)) / sum(allocatable CPU)` | Observed pool load relative to allocatable capacity; do not sum independently calculated node percentiles |
| Request saturation risk | `usage_p99 / request` plus throttling/latency | Whether requests might be too low |
| Fleet allocatable utilization | weighted usage / weighted allocatable | A directional rollup, not a target |
| Cost allocation coverage | accepted allocated, idle and system amounts / positive original amortized charges, per currency | Attribution completeness; not a savings estimate |
| Data coverage | present expected samples / expected samples | Confidence input |

## Why there is no universal utilization target

The metric adapter emits a separate [historical fragment](data-contracts.md#historical-metrics). Its default window is the last 30 complete UTC days. Range queries are aligned and chunked; coverage counts returned evaluation points, not raw scrape completeness. Recent-tail freshness is checked independently of total coverage. Collection does not extend missing history, infer absent series as zero, or create recording rules.

CPU and memory percentiles summarize observed samples with inclusive interpolation. OOM/restart `increase()` values are queried on disjoint step intervals and summed only for complete, issue-free coverage; partial totals remain null. Source resets are handled by PromQL, not by subtracting raw counters in the advisor. Workload history uses a workload UID; per-pod history requires its actual historical pod UID. A short-lived pod's partial window is not extrapolated to 30 days.

Node-pool observations are conservative: only explicit historically complete membership permits numeric aggregation, and only common aligned timestamps are summed before percentiles. Current-node membership alone is insufficient. Neither the source contract nor a high coverage ratio proves a billable node can be removed or an SLO is met.

A high average can be unsafe for bursty or zonally resilient workloads, while a low average can be correct for latency, failover, batch windows, GPU availability, or scale-up protection. Compare workloads within peer groups and treat CPU, memory, throttling, pending pods, latency, and cost together.

## Rule gates

`AKS-SCHED-001` and `AKS-NP-002` version 1.0.0 are current-inventory
investigations, independent of metric-window duration and coverage. They require
exact identities, coherent fresh observation times and complete scoped inventory
receipts. Constraint counts and capacity classes are not utilization targets,
historical scheduler diagnoses, packing scores or removable-node estimates.
Missing prerequisite evidence stays unknown; savings and numeric proposals
remain null. See the [placement contracts](data-contracts.md#current-placement-and-capacity-investigations).

The eight [memory/reliability packs](recommendation-packs.md#memory-and-reliability-packs)
use version 2.0.0. Investigations are independent, readiness is informational,
request/limit proposals are separately default-off and guarded, and historical
envelopes retain complete-roster/per-replica meaning.

The [review packs](recommendation-packs.md#cpu-request-and-pool-review-packs)
define missing-request, request-risk and pool investigation in version 2.0.0
manifests. The request-risk ratio defaults to 0.9 and must be positive; the
pool ratio defaults to 0.2 and must be at least zero and below one. Equality
produces no respective review signal. Request-risk selection is independent of
the reduction threshold, and unknown admitted-request observation or identity
blocks it. These reviews never choose targets or financial savings.

The [CPU pack](recommendation-packs.md) supports baseline/guarded assessment.
`AKS-RQ-002` version 2.1.0 defaults to a qualified P95/current-request
investigation without a numeric target. Guarded mode retains all CPU reduction
gates below. Its finite `review_ratio` pack parameter defaults to 0.4, strictly
between zero and one; equality produces no low-usage signal. This threshold
cannot override coverage, owner policy, peaks or reliability.

An explicitly unsupported [source profile](source-profiles.md) vetoes numeric
proposals, including guarded CPU and memory targets. Name-only ordinary telemetry
is retained as unresolved baseline
measurements, never UID-bound workload history or safe targets. Query
deduplication changes execution volume only; it preserves sampling, warnings,
errors, coverage, counter intervals and sum-before-percentile semantics.

A recommendation should be emitted only when:

1. Required fields are present.
2. Required per-entity metric coverage meets the configured minimum; lower confidence cannot bypass a reduction gate.
3. The observation window is long enough for the rule.
4. Reliability guardrails do not contradict the efficiency signal.
5. The rule explains what additional validation is required.

Required collection results must also be complete and cover the exact scope. The defaults are 30 observation days, 85% coverage, at most 24 hours of evidence age, and at most a 300-second metric step; they are configurable evidence gates, not utilization targets. Boundary equality passes. Unknown, stale, short, misaligned, incomplete, or contradictory evidence produces blocked findings with reason codes instead of actionable reductions. Inventory-only reviews can still appear when fresh inventory is complete but metric history is insufficient.

The [schema 1.0 contract](data-contracts.md#scoped-collection-eligibility) uses CPU request review pack version 2.1.0, version 2.0.0 for eighteen packs and version 1.0.0 for the two current scheduling/capacity investigations. Every finding needs an unambiguous complete/fresh source receipt for its own cluster and valid quality for each required metric. A denied source elsewhere does not invalidate independently complete evidence. Partial multi-scope receipts are not split into successes. Global coverage/count floors are diagnostic, not cross-cluster gates; per-entity coverage, shared window/freshness, resolution and all reduction guards are mandatory.

CPU reductions require explicit request observation, known autoscaler states, cluster/workload identity, declared owner policy, representative peaks/P99, throttling, and OOM evidence. The policy sets minimum CPU, maximum reduction, headroom, and throttling bounds. The engine rounds upward and uses observed maxima/P99 rather than treating P95 alone as a safe target. Active/unknown controller interactions remain blocked for numeric reductions; the current-only review below does not authorize them. Review findings do not establish that an SLO is met or that a node can be removed.

CPU usage near a request is not itself saturation: a request is not a CPU limit. The request-risk rule asks for correlation with limits, throttling, and SLOs rather than asserting saturation from the ratio alone. Confidence is driven by required evidence coverage, not the mere presence of cost data. Reports remain proposals requiring owner review and canary validation.

### Current Autoscaler Interaction

`AKS-AS-002` version `2.0.0` emits a medium-severity current configuration investigation when an observed HPA Resource/ContainerResource **Utilization** signal and a mutating VPA policy overlap on the same exact current workload, container and CPU/memory resource. Utilization is relative to requests, so changing the request can change the HPA feedback denominator. This is a potential interaction, not proof that requests changed, replicas oscillated or SLOs failed. [AKS VPA guidance](https://learn.microsoft.com/azure/aks/vertical-pod-autoscaler#limitations-and-considerations) cautions against HPA/VPA use on the same CPU/memory metrics.

Require complete fresh Azure/Kubernetes source receipts, matching cluster/workload/Namespace bindings, observed HPA/VPA APIs/lists and valid explicit current signal/policy evidence. Configuration age uses the configured maximum evidence age; equality passes. Unknown, stale, future, malformed or mismatched evidence stays blocked. This inventory-only rule does not require a 30-day window, metrics samples or Prometheus availability. High confidence describes the explicitly observed configuration overlap, not historical coverage, source attestation or runtime impact.

VPA Off and container Off are nonmutating for this check. Initial affects newly created Pods; Recreate/Auto/InPlaceOrRecreate may alter requests through their declared strategy. Exact-container policy overrides wildcard policy; controlled resources must match the HPA signal. ContainerResource HPA affects only its named admitted container; Resource HPA covers the admitted containers. Missing policy/default evidence is unknown, never presumed Auto or CPU+memory.

AverageValue/Value, external/custom signals, disjoint resources and recommendation-only VPA do not produce this denominator finding. That is not proof of safe rightsizing or throughput. KEDA ownership does not change an observed HPA's signal type; the separate ownership/activation investigation below does not relax vertical reductions. Active/unknown controllers block reductions, including when current evidence contradicts a declared absence. The fixed-replica review suppresses false absence claims for observed HPAs/ScaledObjects and blocks unknown current configuration.

Findings retain controller UIDs/names, resource, container, target percentage and VPA mode. They require owner investigation and validation/rollback for any separately approved change, but propose no controller mutation, replica count, resource target or savings. Other autoscaler investigations and the separately guarded HPA minimum proposal are described below.

### Historical HPA Bound Review

`AKS-AS-003` version `2.0.0` is a medium-severity investigation of an explicitly UID-bound HPA whose desired and current counts are at a configured bound at every collected evaluation point. It is separate from the current-only `AKS-AS-002` check. The four approved HPA gauge histories, explicit controller binding and current bounds/status are required; current replica count or workload percentile summaries cannot substitute.

Require complete/fresh scoped inventory, metadata and Prometheus receipts, exact current/historical identities, the configured minimum observation duration (default 30 days), aligned source/query/unit/step/window evidence and **100% expected evaluation points** for all four gauges. Lowering the general coverage threshold does not bypass completeness. Current count extrema are nonnegative integers; fractional/duplicate/missing/foreign summaries are rejected or blocked, not rounded or filled. Boundary equality at the duration/freshness limits passes.

Historical minimum/maximum bounds must each be constant and match their explicitly observed current values. Both historical desired and current replica extrema must equal the same count throughout the sampled window:

- Count equals minimum only: `floor`.
- Count equals maximum only: `ceiling`.
- Count equals equal minimum/maximum: one `fixed` finding.
- Valid changing/interior replica counts: no pinned finding.

The fresh current HPA desired/current counts and workload replicas must still match that count. Missing or changed bounds/status, incomplete/short/stale history, multiple/recreated controllers, unknown identity or source mismatch stay blocked. Missing/invalid VPA policy and missing CPU usage do not hide an independently eligible HPA bound review. Confidence derives from the required full-grid evidence, not from ownership declarations or cost.

A floor can be intentional warm/resilience capacity; a ceiling does not prove unmet demand, saturation, ScalingLimited state or SLO impact. Evaluation-point completeness is not continuous observation between samples or raw scrape completeness. Review owner availability/failover policies, scaling signals, controller health and approved demand evidence before any separate change. No replica target, minimum reduction, scale-to-zero suitability, resource proposal or savings is emitted; historical HPA presence cannot be used to authorize vertical reductions.

The [synthetic example](../examples/expected-hpa-history.md) observes desired/current count 1 at each evaluation point with stable bounds 1..5 and matching current status. It is a `floor` review, not a recommendation to reduce the minimum. Required upstream producer semantics and non-attestation limits are in [the contract](data-contracts.md#historical-hpa-replica-bounds).

### Autoscaler Ownership, Changes and VPA Bounds

All autoscaler packs are version `2.0.0`. `AKS-AS-004` is a medium-severity current-only investigation with complete fresh inventory/metadata, exact target/controller ownership and explicitly observed APIs. It reports multiple controller responsibilities or a verified KEDA-generated HPA chain. CPU/memory-only KEDA triggers cannot activate from zero; event/custom-trigger zero minima are review candidates only. Missing trigger types/metric types, bounds, polling/cooldown or ownership stay blocked. No activation thresholds/authentication values are collected, and no cold-start suitability or safe zero target is inferred.

`AKS-AS-006` is a medium-severity sampled-history investigation requiring the same complete aligned HPA metric/source gates as pinning. Valid changed min/max bounds, varying desired/current extrema or changed fresh current context are reviewable. Extrema alone cannot diagnose oscillation, correlation, scaling lag, unmet demand or SLO impact. Unknown/recreated identity and incomplete history remain blocked.

`AKS-AS-007` is a medium-severity current-only VPA status/policy review. Each matching container/resource requires positive lower/target/upper values with `lower <= target <= upper`, plus explicit `0 <= minAllowed <= target <= maxAllowed`. CPU units are mCPU and memory units are MiB; uncapped targets are context. Missing, contradictory, duplicate, malformed, stale or foreign evidence stays blocked. High confidence concerns the observed configuration/status, not recommendation freshness or safe rightsizing. Invalid supplemental VPA evidence does not hide an independently valid denominator finding.

These investigations retain exact identities, evidence, prerequisites, risk, validation and rollback guidance. They do not propose resource/replica targets or financial savings.

### Bounded HPA Minimum Proposal

`AKS-AS-005` version `2.0.0` is separately default-off, owner-policy-gated and medium severity. The [contract](data-contracts.md#opt-in-replica-floor-proposal) defines the exact supported Deployment shape, digest binding, independent owner reviews, zero reviewed incident counts, complete seven-series history and current availability. Required evaluation-point coverage is 100%; lowering general coverage cannot bypass it. Confidence is based on the minimum required metric coverage, not reference/hash presence.

For current floor `C`, maximum reduction ratio `r`, tested replica count `T`, minimum available `A`, failover reserve `F` and maximum-unavailable allowance `U`, calculate:

```text
proposed_floor = max(ceil(C * (1 - r)), T, A + F + U)
```

Require `1 <= proposed_floor < C`. Upward rounding must not exceed the permitted reduction or produce an increase. The proposal never changes the HPA maximum, metrics, controller ownership or resources. A pinned floor alone is insufficient: explicit configuration-bound owner peak-load/throughput/startup/zone-failure/reliability evidence, exact reviewed window and disruption policy are mandatory. Owner-reviewed counts remain declarations; known positive source OOM/restart evidence vetoes zero declarations.

The [synthetic floor example](../examples/expected-replica-floor.md) proposes 2 to 1 only within those declared guards. This is not change approval, proof of SLO compliance, node removal or savings. Validate the exact proposal in a separate owner-approved canary, one dimension at a time; restore the original HPA minimum through customer delivery tooling on any regression. KEDA-managed, StatefulSet, constrained, changed/recreated/multiple-controller and zero-floor proposals stay blocked. Existing CPU/memory reduction gates are unchanged.

### OOM Investigation

`AKS-MEM-001` emits a high-severity reliability investigation only for a validated positive full-window OOM count. Valid zero means no OOM finding; unknown, stale, short, incomplete or low-coverage evidence stays blocked. The rule runs independently of CPU requests/usage and does not require autoscalers to be absent. Confidence is based on the minimum coverage of included evidence.

When independently valid, direct single-Pod or approved complete-roster per-replica working-set P95/P99 and observed maxima provide context. Working set can omit relevant memory and sampling can miss brief peaks; these values alone are not a safe memory request/limit. Event counts alone do not distinguish container-limit OOM from node pressure or establish restart/eviction causes. Owner investigation uses approved tools and SLOs; the advisor collects no logs or event bodies. This investigation proposes no numeric changes or financial savings.

OOM findings can also include admitted memory requests/limits as context only when independent complete constant direct or approved-envelope history matches the current value and passes per-metric eligibility. Observation flags distinguish unknown, explicitly absent and zero current values. Missing history is never supplied by current values or CPU coverage; changed values and unbound replica/churn aggregates remain unsupported. Neither a low working-set/request ratio nor these observations alone authorizes a memory reduction.

### Restart Investigation

`AKS-REL-001` independently investigates validated positive full-window container restart counts with medium severity. It uses the same source, scope, identity and metric-quality gates as OOM investigations; confidence comes from restart coverage. Valid zero produces no restart finding, while unknown or ineligible evidence stays blocked. Missing CPU usage or active autoscalers do not hide restart risk.

Direct history consumes complete disjoint `increase(kube_pod_container_status_restarts_total[step])` intervals. The version 2.0.0 pack also supports approved digest-bound `replica_restarts` interval totals across the complete historical roster, including deleted Pods. Full-window totals must be integral and consistent with interval extrema/counts; fractional estimates, partial lifetimes and generic per-Pod counters under an aggregate identity are not substituted. Current termination context is separate, not a cause diagnosis for all restarts. No numeric change or SLO impact is inferred.

### Memory Safety Review

`AKS-MEM-002` version `2.0.0` is informational readiness, not numeric rightsizing. It independently supports stable direct and approved replica-envelope memory evidence; CPU usage is not required. Missing policy/evidence retains stable blocked IDs and reasons. An empty recommendation list does not mean safe memory settings.

Require complete scoped/fresh sources, exact identity, owner/SLO/disruption/window review, known absent/inactive autoscalers and independent stable request/limit, working-set P95/P99/peak and zero OOM/restart quality. Envelopes additionally require constant min/max bounds, full roster digest, observed admission lists and complete workload eviction history. Existing duration/resolution/coverage/freshness gates remain. Percentiles describe aligned per-replica maxima, never combined workload totals. Positive collected evictions or abnormal termination context cannot be hidden by owner zero declarations.

The [memory policy](data-contracts.md#memory-safety-readiness) additionally supplies owner-reviewed startup/failover peaks, a zero eviction count and reviewed QoS. Unknown scenarios, positive OOM/restarts/evictions, unknown/mismatched QoS or unreviewed windows block readiness. Owner declarations are not collector measurements or source attestation. Only observed/reviewed Burstable QoS with request strictly below the unchanged limit is supported. Guaranteed/BestEffort or equal request/limit require separate QoS/limit semantics, not an implicit transition.

The request must exceed the declared minimum. Each of the observed working-set maximum and reviewed startup/failover peaks, multiplied by the declared headroom factor, must be **strictly below** the current request; equality blocks because it leaves no headroom for reduction. A low P95 alone cannot pass. These are owner-specific guards, not universal utilization targets. Maximum reduction ratio is validated and included with the other owner bounds as evidence, but no target is calculated or proposed.

Confidence uses the minimum required metric coverage; owner declarations have no fabricated coverage. Readiness preserves limits, emits no target/savings and requires separate owner validation. Replica/churn request support is bounded below; automation remains unsupported.

### Memory Request Proposal

`AKS-MEM-003` version `2.0.0` is separate from readiness. Proposals require guarded mode and an exact-container memory policy with strict boolean `allow_request_reduction: true`. Default-off candidates retain `memory_request_reduction_not_enabled`. Opt-in permits analysis, never application.

Require every readiness gate, nonblank owner/SLO and full-grid 100% request/limit/working-set/OOM/restart history. Direct single-Pod and approved stable replica/churn envelopes are supported; the latter require roster binding, constant request/limit min/max, current/historical controller guards, observed admission lists and complete eviction history. Known admission minima/maxima/limit-request ratios gate the proposed request. General coverage cannot override full-grid guards; CPU usage is not required.

```text
peak = max(working_set_P99, observed_working_set_max, startup_peak, failover_peak)
target_MiB = ceil(max(
    owner_minimum_request_MiB,
    current_request_MiB * (1 - owner_maximum_reduction_ratio),
    peak * owner_headroom_factor
))
```

The target must be positive and strictly lower than the current request. Rounding that eliminates the reduction blocks with `no_safe_memory_reduction`; it never becomes a request increase or a zero-valued proposal. Observed peaks, not P95 alone, can dominate the result. For the [synthetic example](../examples/expected-memory.md), request 512 MiB, minimum 128, maximum reduction 0.5, maximum observed/scenario peak 250 and headroom 1.25 yield `ceil(max(128, 256, 312.5)) = 313 MiB`, with the 1024 MiB limit unchanged.

This medium-severity finding contains a memory-only request proposal, null CPU proposal fields, explicit policy/metric evidence and restoration of the original request on regression. It preserves Burstable QoS by requiring the current request below its unchanged positive limit; Guaranteed/BestEffort and limit adjustments remain unsupported. Confidence follows the minimum required metric coverage, which is high only after the full-grid gate passes, not because owner declarations have invented coverage.

Separate owner approval and a request-only canary are mandatory. Validate startup/failover/reliability/placement/SLOs, keeping CPU, limits and other containers unchanged. Working set and owner references are not full-memory accounting or attestation. The [envelope example](../examples/expected-memory-envelope.md) proposes 313 MiB per replica, not a summed workload percentile or savings. Limit proposals are independently gated below.

### Effective Pod, Termination and Eviction Reviews

`AKS-MEM-004`, `AKS-REL-002` and `AKS-REL-003` are version 2.0.0 packs. Current Pod accounting/termination require complete fresh inventory/metadata; they do not require Prometheus. Accounting is informational; unknown quantities/init/overhead or unsupported Pod budgets are blocked. Restartable init requests remain concurrent with later initializers/application containers. The [context example](../examples/expected-memory-context.md) reports `max(704, 1152) + 32 = 1184 MiB`, not usage or removable capacity.

Last-termination reason, exit code and UTC time are current UID-bound status, not the cause of all restarts; 137 alone is not OOM proof. Invalid/duplicate/foreign/future context remains blocked. Evictions require independent full-window integral workload-counter quality, source/identity/duration/freshness and coverage. Positive counts produce a medium investigation once per workload; zero produces none and missing stays blocked. Counters do not establish node pressure or SLO impact. Positive collected evictions block CPU/memory reductions; owner zero declarations cannot veto collected evidence.

### Separate Memory Limit Proposal

`AKS-MEM-005` version 2.0.0 defaults off through exact-container `memory_limits` policy and requires guarded mode. It requires one stable direct Pod, observed Burstable QoS, complete constant request/limit history, complete total-memory usage (not working set alone), zero full-grid OOM/restarts/evictions, current controller absence, exact reviewed window/environment/owner/SLO/disruption, allocator/cache and total-memory startup/failover review, and a matching current configuration/admission digest. Source/query/units/window/step and 100% grids must align. Missing admission lists or unsupported Pod-level admission bounds block; known Container min/max/limit-request ratios are enforced.

```text
peak = max(total_memory_max, reviewed_startup_total_peak, reviewed_failover_total_peak)
target_MiB = ceil(max(
    owner_minimum_limit, observed_admission_minimum,
    current_limit * (1 - owner_maximum_reduction_ratio),
    unchanged_request + 1 MiB, peak + 1 MiB,
    peak * owner_headroom_factor
))
```

Require a target strictly above request/peak and strictly below current limit, within admission maximum and limit/request ratio. Nonfinite/rounding violations stay blocked. Owner references/digests are declarations/integrity only; no approval or universal memory target is implied. The [limit example](../examples/expected-memory-limit.md) yields 600 MiB from 1024, retaining request 512 MiB and QoS. Reports use separate paired limit fields with exact restoration of the original limit on OOM/restart/eviction/SLO regression. Request and limit changes cannot coexist in one finding or canary. Replica/churn limits, init/runtime/Pod budgets, Guaranteed/BestEffort, controller interactions and savings/remediation remain unsupported. Existing Headlamp displays limits but refuses them through the resource-request approval workflow.

## Review and prioritization

Reports provide severity, confidence, evidence and risk, not a monetary
prioritization score. Prioritize findings with the accountable owners using
reliability urgency, business relevance, prerequisites and blast radius.
Never turn a low-confidence capacity estimate into a dollar amount.

## Savings rules

`estimated_monthly_savings` is always `null`, including after successful cost
reconciliation. Engineering opportunity does not establish a billable-resource
reduction or realized financial outcome; FinOps must validate those separately
using approved, period-aligned billing evidence and commitment/allocation rules.

The [offline cost profile](cost-reconciliation.md)
supports attribution reconciliation, not savings. Coverage uses accepted
allocated/idle/system amounts divided by all positive original amortized
charges in each currency, including unmatched charges in the denominator.
Unallocated amounts do not count as allocated; the default minimum is 0.95,
with equality passing. Credits/unsupported charge types, incomplete or stale
evidence, identity/period failures and mixed currencies block reconciliation.
Charge-category and attribution totals partition the same costs and must not
be added together. Reconciled input still produces no monthly savings.
