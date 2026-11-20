# Choose Checks For Your Assessment Question

[Documentation home](../README.md) | [Next: customer assessment](../accelerator-docs/assessment-guide.md)

## Goal And Prerequisites

A recommendation pack describes a rule's required inputs and review guidance. Select a small set that answers your question instead of treating every blocked check as a request for more access. This guide is for application/platform owners after [the first labs](../accelerator-docs/getting-started.md). Allow about 15 minutes for offline inspection; no cloud access is required.

## Three Ways To Start

Start with one cluster, one question and data already owned by your platform and application teams. These are independent entry points, not stages that everyone must complete. Keep your existing Prometheus/Grafana and delivery workflows; no billing import, VPA installation, new recording rules or monitoring platform is required for the first two.

| Entry point | Minimum input and example check | Access for preparing evidence | Useful result and stop condition |
| --- | --- | --- | --- |
| Current metadata | Fresh scoped AKS inventory and sanitized admitted-Pod/controller metadata; `AKS-SCHED-001`, `AKS-SCHED-002` or `AKS-RQ-001` | Existing export owner; if collecting, approved Azure Reader scope and get/list-only Kubernetes metadata access for the selected resources | Configuration facts and an owner investigation. Stop without historical metrics or a replacement resource value. |
| Ordinary Prometheus | Existing CPU usage/request series with exact cluster resource ID, namespace, Pod name and container; `AKS-RQ-002` in `baseline` with `cadvisor-ksm` | Existing metric query/read permission or approved saved fragments; Grafana query export is optional | Unresolved measurements, units, dates and explicit gaps. Stop without workload ownership/UID reconstruction or a numeric target. |
| Qualified history and upstream candidate | Existing historical UID/roster evidence, selected reliability series and owner policy, plus a supported saved VPA candidate; guarded CPU or memory-request pack | The same approved readers/exporters, limited to selected entities and queries; no added cloud role from enabling guarded mode | A validated upstream candidate or exact blockers. Defer a dimension if its history, freshness or owner evidence is missing. |

The following fictional examples use evaluation date October 29, 2026 so their freshness stays repeatable. For customer evidence, use the actual evaluation time. Run from the repository root after installation:

```text
aks-fleet-advisor analyze --snapshot examples/fixtures/scheduling-review-snapshot.json --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor assess --fragments examples/fixtures/ordinary-source-assessment.json --config examples/ordinary-source-config.yaml --pack AKS-RQ-002 --mode baseline --as-of 2026-10-29T12:00:00Z --format markdown
aks-fleet-advisor assess --fragments examples/fixtures/memory-assessment.json --config examples/pool-assessment-config.yaml --pack AKS-RQ-002 --pack AKS-MEM-003 --mode guarded --as-of 2026-10-29T12:00:00Z --format markdown
```

Expect exit `0` and one placement investigation for metadata; exit `3` with two unresolved CPU usage/request measurements and gaps for ordinary telemetry; and exit `3` with the fictional upstream 500 mCPU and 313 MiB request proposals for qualified history. The partial status preserves unsupported evidence elsewhere. No example calculates savings or approves a change. Ordinary measurements are not a workload-bound low-utilization finding; the advanced targets are supplied by VPA, not calculated from a percentage of the current request.

For each selected check, record the observed fact, missing evidence, next owner action and any optional integration. A valid handoff is: "The existing dashboard shows low CPU usage; the saved series lack historical workload UIDs. The monitoring owner will confirm the retained identity shape, while the application owner reviews whether startup reserve is intentional. We will not enable guarded proposals or request financial data for this question."

Use the [exact metric/label mapping](../source-compatibility.md#identity-and-series-mapping) only for the chosen question. Additional recordings are separately owned and optional; they cannot backfill absent history. Use the [saved-VPA workflow](../operations/runbook.md#saved-vpa-request-candidates) only for the third entry point. Retaining intentional capacity or deferring further analysis is a complete outcome.

## 1. Start With The Question

| Question | Starting check | Important boundary |
| --- | --- | --- |
| What restricts current Pod placement? | `AKS-SCHED-001` | Configuration investigation, not packing simulation or removable nodes |
| Which probe, topology-spread or PDB conditions may constrain optimization? | `AKS-SCHED-002` | Current owner investigation, not selector matching, generated configuration or a universal policy score |
| What current capacity classes need review? | `AKS-NP-002` | Current pool/provisioning context, not a NAP migration decision |
| Which observed NAP policy and workload facts may block consolidation review? | `AKS-NP-003` | Current blocker context, not packing/disruption feasibility or a removable-node claim |
| Does the same DaemonSet request occupy different fractions of different node shapes? | `AKS-NP-004` | Current effective requests and allocatable shares, not usage, node eligibility or a safe per-node sizing target |
| Are admitted CPU requests missing? | `AKS-RQ-001` | Current request investigation, not a replacement value |
| Is qualified CPU usage low relative to requests? | `AKS-RQ-002`, baseline first | Owner investigation; guarded values need independent additional requirements |
| Do resource-utilization HPA and mutating VPA policies overlap? | `AKS-AS-002` | Current interaction, not proof of oscillation or an SLO failure |
| Do memory or replica settings warrant review? | Inspect the relevant family in the pack reference | CPU-ready data do not establish memory/replica readiness |

HPA means Horizontal Pod Autoscaler; VPA means Vertical Pod Autoscaler; NAP means node auto-provisioning. Their roles are introduced in the [scaling lesson](../learning/03-horizontal-vertical-and-node-scaling.md).

### Follow An Investigation Journey

Choose a row after the entry-point decision above. Start by inspecting the named packs with `catalog show`; use the linked fictional report to understand the output before preparing customer evidence. A journey can end with an investigation, an explicit gap or intentional no change. It does not require enabling every listed pack or completing another journey.

| Journey and entry | Evidence and gap to preserve | Expected result and next owner decision |
| --- | --- | --- |
| Current requests and reliability: `AKS-RQ-001`, `AKS-RQ-003`, `AKS-MEM-001`, `AKS-REL-001`, `AKS-REL-002`, `AKS-REL-003`, `AKS-MEM-004`. Start with [missing requests](../../examples/expected-missing-request.md) or [Pod accounting](../../examples/expected-pod-memory-pack.md). | Current request/accounting/termination checks need fresh exact-scoped metadata; request-risk, OOM, restart and eviction checks need their own qualified histories. One valid metric does not fill another's gap; exit 137 alone is not OOM proof. | [Request-risk](../../examples/expected-request-risk.md), [OOM](../../examples/expected-oom-pack.md), [restart](../../examples/expected-restart-pack.md), [termination](../../examples/expected-termination-pack.md) and [eviction](../../examples/expected-eviction-pack.md) reports identify independent facts or blockers. The application owner chooses a cause investigation or retains intentional reserve, not a simultaneous resource change. |
| VPA/request candidate and memory-limit review: `AKS-RQ-002`, `AKS-AS-007`, `AKS-MEM-002`, `AKS-MEM-003`, `AKS-MEM-005`. Start with [baseline CPU](../../examples/expected-cpu-pack-baseline.md) and [current VPA bounds](../../examples/expected-vpa-bounds-pack.md). | Exact container/resource candidate, genuine candidate age, historical identities, representative peaks, reliability, controller, admission and owner-policy evidence are independent. Current VPA bounds do not prove target freshness; memory-limit evidence is separate from working set and request evidence. | Baseline investigates without targets; memory readiness is informational. Eligible guarded examples preserve [CPU](../../examples/expected-cpu-pack-guarded.md) and [memory-request](../../examples/expected-memory-request-pack.md) upstream candidates, or a separately opted-in [memory-limit](../../examples/expected-memory-limit-pack.md) proposal. The owner chooses at most one dimension for a separately approved test, or defers it. |
| HPA/VPA request-denominator interaction: `AKS-AS-002`. Start with the [interaction report](../../examples/expected-interaction-pack.md). | Fresh exact-target HPA signal and explicit VPA resource/container policy; no historical metrics required. Missing mode or signal details stay unknown. | A current overlapping utilization signal and mutating policy warrant controller-owner review. Absolute/external signals or VPA Off do not establish this finding; no finding does not prove a safe reduction. No oscillation or startup diagnosis is supplied. |
| KEDA/custom-metric ownership: `AKS-AS-004`. Start with the [KEDA report](../../examples/expected-keda-pack.md). | Observed APIs, exact KEDA-to-HPA ownership, trigger categories and explicit polling/cooldown/bounds; no trigger credentials/values or application throughput model. | The controller/application owner reviews responsibilities and missing activation evidence. A generated HPA is one ownership chain, not a second independent scaler. A zero minimum or external metric does not prove cold-start or scale-to-zero suitability. |
| Historical HPA behavior and replica review: `AKS-AS-003`, `AKS-AS-006`; separately inspect current `AKS-AS-001` or opted-in `AKS-AS-005`. Start with [pinning](../../examples/expected-hpa-pinning-pack.md) and [changes](../../examples/expected-hpa-change-pack.md). | Exact controller/workload identity and complete aligned gauge histories; today's replicas cannot backfill history. [Fixed-replica review](../../examples/expected-fixed-replica-pack.md) requires observed current controller absence; floor proposals add independent availability/scenario policy and full-grid histories. | Pinning/change findings describe sampled behavior, not oscillation or unmet demand. The owner may retain a warm floor or investigate a ceiling. Only a separate eligible guarded [floor example](../../examples/expected-hpa-floor-pack.md) proposes a lower positive minimum; it does not lower resources or approve a rollout. |
| Observed startup/readiness: explicitly select `AKS-START-001` for the [saved synthetic readiness example](../../examples/expected-startup.md). Current [probe/constraint context](../../examples/expected-optimization-constraints.md) remains separate under `AKS-SCHED-002`. | Exact saved sample grid, Pod/container-attempt identity and original clocks bracket an observed readiness transition. Separate exact-query post-readiness CPU/memory context is optional. Probe timing and whole-window percentiles cannot substitute; first-ever startup and application initialization remain unknown. | Review the sampled readiness bracket and independent usage gaps with the application owner. Define actual application-readiness and representative demand evidence separately; no reserve reduction, sizing, scale-to-zero or in-place resize claim follows. |
| DaemonSet overhead: `AKS-NP-004`. Start with the [heterogeneous-node example](../../examples/expected-daemonset-overhead.md). | Exact admitted DaemonSet Pod/Node/controller identities, effective app/init/sidecar/overhead requests and current allocatable CPU/memory on differing observed shapes. Missing desired coverage, usage or node eligibility stays unknown. | Identical effective requests can occupy different node shares. The DaemonSet/platform owner investigates intentional per-node needs; the report supplies no universal target, annotations or removable capacity. |
| Admission-aware validation: inspect `AKS-MEM-004`, then the applicable CPU/memory candidate pack. Start with [accounting](../../examples/expected-pod-memory-pack.md) and the [candidate contracts](../recommendation-packs.md#memory-and-reliability-packs). | Admitted values, observed LimitRange/ResourceQuota evidence, QoS and effective Pod accounting are separate from a controller template. Unknown admission evidence cannot be treated as an empty policy. | Retain the current effective request and candidate-specific blockers. The application/platform owner reviews actual admission constraints; guarded mode cannot override them or turn accounting into packing feasibility. |
| Placement and optimization constraints: `AKS-SCHED-001`, `AKS-SCHED-002`. Start with [placement](../../examples/expected-scheduling-review.md) and [constraints](../../examples/expected-optimization-constraints.md). | Fresh scoped Pod/controller/node metadata; probes, topology and PDB observations have independent gaps. Namespace PDB presence is not selector matching, and dropped labels are not known absence. | Owners review the specific placement or disruption fact. No scheduler-fit simulation, universal policy score, generated configuration or safe node-removal decision is supplied. |
| Fixed/CAS/NAP capacity review: `AKS-NP-001`, `AKS-NP-002`, `AKS-NP-003`. Start with [capacity classes](../../examples/expected-capacity-review.md) and the [NAP policy contract](../recommendation-packs.md#current-scheduling-and-capacity-packs); use [fixed-pool history](../../examples/expected-pool-review.md) only when available. | Capacity classes/NAP policy need fresh metadata and exact ownership; NAP workload context requires exact Pod/Node/NodeClaim/NodePool binding. Fixed-pool utilization additionally needs complete historical node membership and constant capacity. | The platform owner reviews source gaps, reservations and current blockers. Unknown attribution does not hide known policy facts. Neither low fixed-pool utilization nor NAP policy proves migration readiness, packing/disruption feasibility or removable nodes. |

For fleet inventory, repeated findings, optional financial context or optional AI handoff, use the [assessment contract](../scenario-coverage.md#assessment-contract) and linked operations guides rather than selecting an unrelated pack. Exported dashboards help investigate the chosen measurements; they do not supply missing source evidence or approval. Keep the report's per-pack subject units separate instead of summing them into a workload count.

## 2. Inspect Requirements Without Accessing A Cluster

From the repository root after installing the advisor, these commands work in Windows PowerShell and Linux/macOS and normally exit `0`:

```text
aks-fleet-advisor catalog list
aks-fleet-advisor catalog show AKS-SCHED-001
aks-fleet-advisor catalog show AKS-RQ-002
```

`list` shows the installed checks; `show` prints the selected manifest and provenance. Neither command contacts a service, creates output files or obtains credentials. Unknown pack IDs are errors, not permission to substitute a check.

Read evidence dependencies, supported modes, limitations, review actions and validation/rollback guidance. The [generated catalog](../operator-catalog.md) is exact reference, not a first-run lesson or source certification.

## 3. Record The Selection

For each question, record its pack ID, installed version, mode, needed input shape, unsupported cases and missing information owner. Keep exact versions and configuration with saved reports rather than copying counts/versions into a customer procedure that may drift.

Start in `baseline`: investigations without replacement values. `guarded` permits eligible numeric suggestions but is not approval, does not enable default-off owner policies and cannot bypass identity/reliability requirements. Changing a review ratio is not choosing a safe resource target.

Set `analysis.packs` and `analysis.mode` in the onboarding profile before using `readiness`, or select `--pack` and `--mode` on `assess`/`analyze`. Readiness gates the selected mode and excludes unused metric sources and metric prerequisites for metadata-only selection. Capability reports can still show both modes for comparison: an unsupported guarded shape does not make selected ordinary baseline measurements unusable. Offline access/source facts remain unknown, and the selected assessment remains authoritative for its finding-specific gates.

## Completion And Next Step

Finish when the owners can explain why each check was selected and what its output cannot conclude. An inventory-only scope is a useful outcome when history is unavailable. No files/cloud resources were created; no cleanup is needed for these inspection commands.

Continue with [data-source review](validate-source-compatibility.md) and [customer assessment](../accelerator-docs/assessment-guide.md). Exact pack contracts and supported parameters remain in [recommendation packs](../recommendation-packs.md) and [rule gates](../metrics-and-scoring.md#rule-gates).
