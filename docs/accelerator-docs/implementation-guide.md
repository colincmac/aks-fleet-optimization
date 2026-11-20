# Validate An Optimization Change

[Documentation home](../README.md) | [Previous: assessment](assessment-guide.md)

Use this guide after owners have reviewed a real assessment and identified one candidate worth testing. You will create a testable hypothesis, obtain separate approval, test one dimension and decide what the result actually established. The outcome can be an accepted improvement, rollback, deferment or inconclusive.

**Who owns the work:** application/reliability and platform owners agree the test; the customer's change process authorizes implementation; FinOps reviews financial conclusions separately. The advisor applies no manifests, changes no settings and creates no production pull requests. Keep its identity read-only. Use separately authorized customer tooling/identities for any implementation.

Start with the [completed assessment](assessment-guide.md), [participant workbook](../facilitator/participant-workbook.md) and [hypothesis template](../facilitator/assessment-hypothesis.md). These templates record decisions; filling them does not grant approval. No command in this guide performs an experiment or contacts a customer system.

## Retain, Defer Or Test

Carry the same scoped question from the [assessment journey](assessment-guide.md#worked-enterprise-question), not a new fleet-wide improvement target. If the owner retains intentional reserve or defers a dimension, record the rationale, missing evidence, next owner/date and stop without a change. Only a separate approved experiment needs the test/rollback record below. Keep engineering and optional financial decisions distinct.

| Selected dimension | Where its numeric value comes from | Independent review still needed |
| --- | --- | --- |
| CPU request | Exact fresh VPA or characterized vendor candidate; the calculated CPU bound is a validation floor, not a replacement recommender | Peak/startup/failover, throttling, current and historical controllers, request history, owner policy |
| Memory request | Exact fresh upstream memory-request candidate, with separate owner opt-in and full-grid evidence | OOM/restarts/evictions, QoS/admission, startup/failover peaks and unchanged memory limit |
| Memory limit | Separate accelerator-derived supplemental proposal, not a VPA request target | Full-memory/allocator/cache evidence, admission/configuration review, explicit limit opt-in and unchanged request |
| HPA minimum replicas | Separate accelerator-derived floor proposal, not a CPU/memory candidate | Exact reviewed HPA/configuration, availability/throughput/warm and zone-failure reserve, explicit floor opt-in |

Do not treat one accepted dimension, another container's candidate, a passing safety floor or reconciled cost as evidence for the others. Follow the [pack-specific contracts](../recommendation-packs.md) and return blocked/unknown cases to their source/application owners.

## 1. Pick One Evidence-Backed Improvement

Choose one exact target and an accountable owner. State what could improve and what observation would disprove it. For example: "A different CPU request may release scheduling reservation without worsening startup, throughput or our service-level objectives (SLOs) under representative demand." The owner defines those reliability/performance measures; the advisor does not establish them.

| Assessment outcome | Appropriate next action |
| --- | --- |
| Blocked/unknown information | Resolve the named data/policy gap or defer; never convert it to zero |
| Baseline investigation | Review with the owner; no replacement setting is authorized |
| Validated upstream request candidate | Check the VPA/vendor candidate identity, freshness, source version, accelerator safety bound, owner policy and rollback before requesting independent approval |
| Current placement/capacity review | Establish intent and a separate design/test plan; it does not prove a node can be removed or a provisioning migration is suitable |
| Attributed or reconciled cost evidence | Review source profile, basis, granularity, matched/unmatched amounts and reason codes with FinOps; neither status proves savings |

To bring current capacity evidence into the discussion, generate a Markdown review from the original single-cluster assessment bundle:

```text
aks-fleet-advisor review-retained-capacity --assessment <assessment-directory>/assessment.json --tenant <tenant-id> --output <new-review.md>
```

The review replays the original assessment at its original clock, then groups the existing fixed-pool, NAP, DaemonSet, placement and disruption-related findings and gaps. It distinguishes unselected packs, zero evaluated subjects and no finding. Use the listed finding IDs to locate quantities and evidence in the original report. This is a summary of retained evidence, not proof of why a node was kept, validated scheduler fit or a change authorization.

Check that the current configuration, controller identities, demand and policy still match the review. Recollect/reassess when they change or data are stale. A past `--as-of` date can repeat an old analysis; it must not make old measurements eligible for today's change.

Guarded mode validates a supplied VPA or characterized vendor request candidate; it does not create a parallel request target when no candidate exists. It is not approval and cannot enable default-off owner opt-ins or bypass unsupported workloads. CPU requests, memory requests, memory limits and Horizontal Pod Autoscaler (HPA) minimum replicas have different requirements. Use the selected [pack](../recommendation-packs.md) and [exact rule gates](../metrics-and-scoring.md#rule-gates), not a passing CPU check as evidence that another setting is safe.

## 2. Complete The Change Record

Keep the [hypothesis/change record](../facilitator/assessment-hypothesis.md) in the customer's protected tracker/storage with restricted evidence links, not in the public repository. All applicable fields need owner agreement before a canary: a limited test on an explicitly selected environment/cohort.

| Field | Required decision |
| --- | --- |
| Objective | Desired outcome, testable hypothesis and why this target was chosen |
| Identity and provenance | Exact cluster/workload/container/controller binding, finding ID, pack/version, configuration and artifact reference |
| Freshness | Observation/evaluation times and confirmation that current configuration still matches |
| Change | One supported dimension, original value, upstream candidate and source/version/reference when applicable, validated proposal value, scope and blast radius |
| Baseline | Representative demand, latency/error/throughput and availability, plus relevant resource/reliability measures |
| Guardrails | Numeric customer-specific SLO thresholds, abort criteria and acceptable observation delay |
| Scenarios | Peak, startup, scale-up, batch, disruption and failover cases relevant to the workload |
| Canary | Environment, cohort, routing, start/end conditions and responsible observer |
| Rollback | Exact original configuration, tested restoration mechanism, trigger and authorized owner |
| Authorization | Application/SRE, platform and change approvers as required by policy |
| Outcome | Accepted, rolled back, deferred or inconclusive, with evidence and next review |

The complete record states scope, source dates, observed versus owner-declared facts, one proposed dimension, independent measures, customer numeric thresholds, authorized operators and exact restoration steps. A hash/reference proves none of these tests actually happened; retain the independently reviewed results.

### Portable Advisor Handoff

The optional portable workflow prepares local records for attachment to the customer's existing change process; it does not create a ticket or approve a change. First create a protected `ExperimentHandoffRequest` JSON file using [`experiment-handoff-request.schema.json`](../../schemas/experiment-handoff-request.schema.json), then run:

```text
aks-fleet-advisor prepare-experiment --assessment <original-directory>/assessment.json --tenant <tenant-id> --request <handoff-request.json> --as-of <utc-time> --output <new-handoff-directory>
```

The command requires one replay-verified recommendation in an exact single-cluster bundle and derives the run, fingerprint, pack/version, baseline window and configuration digest from originals. It writes `experiment.json`, `experiment.md` and `manifest.json`. Exit `0` means the record is structurally prepared; exit `3` means unresolved prerequisites keep it blocked. Neither exit is change approval. Optional AI interpretation stays separate and unverified; the command invokes no model and does not trust AI text as an owner threshold or rollback value.

No universal utilization target or canary duration is safe for every workload. Choose a period covering the required demand/startup/failure scenarios. A quiet interval that misses them cannot establish acceptance.

Use the customer's existing load/scenario tools and Grafana/SLO dashboards. [Azure Load Testing](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/overview-what-is-azure-load-testing) is one optional tool if already approved; it is not an accelerator prerequisite. The advisor creates no test service, generates no production load and grants no test permissions. The authorized owner chooses representative scenarios, captures independent results and tests exact restoration through the existing pipeline.

## 3. Validate Before Production

Begin in an approved nonproduction environment with representative behavior. A limited production canary needs its own explicit justification/approval. The customer change owner prepares the actual delivery change. Treat report text and resource names as data, not commands or instructions to execute.

1. Capture the original desired and admitted configuration and verify rollback.
2. Verify the proposed scope, current controllers, admission defaults/constraints, disruption budget, topology, capacity and applicable owner policy.
3. Exercise representative load, startup, scale-up and approved failover scenarios. Do not inject a production failure simply to complete this checklist.
4. Change only the selected dimension and target through existing delivery tools.
5. Observe SLOs and the independent reliability/resource signals below.
6. Abort and restore the original state on any agreed regression. Verify recovery and record the result before attempting another change.

| Dimension | Additional checks | Keep separate |
| --- | --- | --- |
| CPU request | Throttling/limits, latency, throughput, scale-up and scheduling; HPA utilization uses requests as its denominator | CPU limits, replica floors and memory settings |
| Memory request | Observed peaks plus startup/failover, OOM/restarts/evictions, QoS and scheduling | The unchanged memory limit and other containers |
| Memory limit | Full-memory usage, allocator/cache behavior, admission bounds and OOM/restarts/evictions | The unchanged request; working set alone is insufficient |
| HPA minimum | Availability, warm capacity, startup/throughput and zone-failure reserve under the exact reviewed configuration | Maximum replicas, metrics and resource settings; no zero-floor proposal |
| Placement or pool architecture | Resilience, specialization, system/DaemonSet overhead and a separately validated capacity/placement design | No packing simulation, safe node count or NAP migration approval is supplied |

Do not combine requests, limits or a replica-floor reduction in one finding/ canary. Memory and floor suggestions are separately default-off and narrowly supported. A blocked target needs better information, separate engineering work or deferment, not a fictional policy copied to pass a check. Headlamp's preview does not authorize changes; its resource-request approval path refuses limit and replica-floor records.

## 4. Measure Engineering And Financial Outcomes Separately

Compare similar demand, exact scope, periods and configuration. Record confounders: traffic, releases, incidents, prices and commitments that could explain a difference. If the comparison is not valid, say inconclusive rather than attributing the difference to the change.

| Outcome | Evidence to retain | Claim to avoid |
| --- | --- | --- |
| Reliability | Customer SLOs and scenario results; independent OOM/restart/eviction and availability evidence | That the absence of an advisor finding proves SLO compliance |
| Reservation efficiency | Original/admitted request, supported usage and unchanged reliability | That released requests are immediately cash savings |
| Capacity effect | Separately observed node/pool behavior, placement and resilience validation | That a pool investigation proves removable nodes |
| Financial effect | Approved amortized billing periods, currency, exact resource bindings, attribution and FinOps review | CPU-percentage-to-currency conversions, double counting or unsupported savings |

Use [the financial lesson](../learning/06-cost-attribution-versus-savings.md) to distinguish opportunity, attributed cost, a separately owned forecast and realized value. The [cost workflow](../cost-reconciliation.md) preserves `attributed`, `reconciled` or `blocked` evidence from approved financial profiles; savings remain `null` for every status. FinOps establishes any actual financial result independently using approved billing evidence, commitments/discounts and comparable demand. Released requests or gross capacity changes are not automatically bill impact.

Use [local verified history](../operations/history.md) to compare compatible assessment artifacts when useful. It is not continuous monitoring: missing or blocked findings do not prove resolution, and incompatible runs are not comparable. Customer SLO/change records remain necessary acceptance evidence.

For the [offline CPU-request review](../data-contracts.md#optional-cpu-request-outcome-review), compare one approved configuration change against two equal-length, nonoverlapping original assessment windows. Supply independent service demand and success counts for each window and the owner's success floor and demand tolerance. A changed request is an observation, not proof the advisor caused a result. Missing or unmatched evidence is inconclusive; a comparable follow-up below the owner floor after a passing baseline is a regression. The synthetic review does not certify production SLOs or execute the change.

After the customer independently runs, aborts, rolls back or declines the experiment, prepare an `ExperimentOutcomeRequest` using [`experiment-outcome-request.schema.json`](../../schemas/experiment-outcome-request.schema.json) and record the declaration:

```text
aks-fleet-advisor record-experiment-outcome --experiment <handoff-directory> --request <outcome-request.json> --as-of <utc-time> --output <new-outcome-directory>
```

For a separate engineering/value record, prepare [`experiment-value-outcome-request.schema.json`](../../schemas/experiment-value-outcome-request.schema.json) and run:

```text
aks-fleet-advisor validate-value-outcome --experiment <handoff-directory> --outcome <outcome-directory> --request <value-request.json> --as-of <utc-time> --output <new-value-directory>
```

The current value adapter checks the handoff and outcome bundles and can retain declared engineering and optional capacity values. It does not open before/after assessments or verify declared quantities or comparability. Use `declared` for these values; `observed` requires a future original-evidence adapter. Modeled and reconciled finance remain blocked or unsupplied. The Markdown has separate sections and no combined savings total; `estimated_monthly_savings` remains null.

## 5. Record The Outcome And Reassess

The owner records validated improvement, rollback, deferment or inconclusive, with supporting evidence and the remaining limits. Preserve the original assessment, approval, change, before/after data and test/recovery results. Name the configuration/runbook owner, reassessment trigger and retention/ deletion responsibilities.

**Example: fictional outcome.** A request-only test releases reservation during quiet traffic, but the approved peak/startup scenario has not been exercised. Record that limited observation; do not declare full acceptance or savings. Do not expand the rollout. The authorized owner decides whether to restore the original setting or complete an approved test, with recovery checks if rolled back.

Expand by workload class and environment only after each has representative evidence, source compatibility and owner approval. Do not apply a canary result fleet-wide by name similarity. Capture exceptions for resilient warm capacity, batch windows, specialized nodes and isolation requirements.

Hand off decisions and remaining gaps through the customer's delivery process. The advisor supplies no scheduler, notifications, durable governance service or Git/Fleet distribution. An absent finding or merged change does not establish success; neither the preview nor infrastructure templates are that service.
