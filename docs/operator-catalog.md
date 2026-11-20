# Generated operator catalog

Generated from packaged manifests. Do not edit; run `scripts/generate_operator_catalog.py`.

Guarded mode is not approval. Numeric proposals require independent owner policy, complete identity-bound evidence, reliability gates and a one-dimensional canary/rollback. Configuration never enables owner opt-ins or changes a cluster.

## Glossary

- **baseline**: Qualified investigations only; no numeric resource or replica proposals.
- **guarded**: Guarded mode is not approval. Numeric proposals require independent owner policy, complete identity-bound evidence, reliability gates and a one-dimensional canary/rollback. Configuration never enables owner opt-ins or changes a cluster.
- **coverage**: Returned evaluation points, not proof of raw scrape completeness.
- **identity**: Historical UIDs and exact Azure IDs; current names cannot backfill history.
- **unknown**: Missing or unsupported evidence is not zero or proof of health.
- **query-only**: Executable exports measure signals; they do not pass assessment gates.
- **provenance**: Pack/query versions and digests bind replay, not source attestation.
- **mCPU**: One thousandth of a CPU core.
- **MiB**: 1,048,576 bytes; working set and full usage are distinct measurements.
- **ratio**: Dimensionless fraction; not a universal utilization target.
- **events**: Complete interval counts; missing intervals are not zero.
- **pods**: Sampled replica counts, not availability or safe capacity by themselves.
- **boolean**: Explicit observed state; missing observations remain unknown.

## AKS-AS-001: Review autoscaling

Version: 1.0.0; family: autoscaler; evidence: inventory.

Investigate current fixed replicas with observed absence of HPA and KEDA.

Pack/query digest: `fac572d7cd4dd5802b9576c8dd503fa1542af662b53b565a34102f8242ea0ab0`.

Baseline: The workload has multiple replicas but no HPA or KEDA signal in the current snapshot. Confirm whether fixed capacity is an explicit requirement; current configuration does not establish historical absence.

Guarded: The workload has multiple replicas but no HPA or KEDA signal in the current snapshot. Confirm whether fixed capacity is an explicit requirement; no numeric replica proposal is made.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Identify a scaling signal tied to user demand or queue depth.

### Limitations

- Current absence is not historical controller absence, proof of low demand or safe rightsizing.

### Risks

- A poorly selected signal can cause oscillation or SLO regressions.

### Validation

- Validate scaling behavior with representative load.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped inventory and workload identity
- Explicit observed HPA/KEDA absence without contradictory current controllers
- Current replicas at or above the configured minimum\_replicas\_for\_autoscaling\_review
- Document why fixed replicas are required, or prototype HPA/KEDA.

### Guarded evidence and actions

- Complete fresh exact-scoped inventory and workload identity
- Explicit observed HPA/KEDA absence without contradictory current controllers
- Current replicas at or above the configured minimum\_replicas\_for\_autoscaling\_review
- Document why fixed replicas are required, or prototype HPA/KEDA.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-001"
  ],
  "pack_parameters": {
    "AKS-AS-001": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-001": "fac572d7cd4dd5802b9576c8dd503fa1542af662b53b565a34102f8242ea0ab0"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-001`.

## AKS-AS-002: Review HPA/VPA resource interaction

Version: 1.0.0; family: autoscaler; evidence: inventory.

Review utilization request-denominator overlap on the exact current container and resource, with exact-container VPA policy taking precedence over wildcard policy.

Pack/query digest: `bc2fc328dc8244e004bdcf6b452344a87948fb232c5021c63c1245f6ae03f376`.

Baseline: A current HPA utilization target uses a resource request that a matching VPA may change. Review the shared request denominator; configuration alone does not establish oscillation or SLO impact. Initial mode affects new Pods rather than continuously updating them.

Guarded: A current HPA utilization target uses a resource request that a matching VPA may change. Review the shared request denominator; configuration alone does not establish oscillation or SLO impact. Initial mode affects new Pods rather than continuously updating them.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Have the owner verify the exact current HPA/VPA UIDs, target workload and container resource policy before interpreting the interaction.
- Distinguish utilization percentages from absolute/external signals; KEDA ownership does not remove a generated HPA's request denominator.

### Limitations

- Current-only evidence cannot prove request changes, oscillation, controller history or SLO impact.
- Absolute and external signals do not establish utilization-denominator overlap.

### Risks

- Changing requests can change utilization feedback and replica decisions.
- External or absolute signals do not eliminate per-Pod throughput risk; no conflict finding is not proof of safe rightsizing.

### Validation

- Use approved operational tools to correlate replica/request history with demand, controller behavior and owner-declared SLOs.
- Validate any separately approved controller change in an isolated canary with explicit availability and rollback criteria.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped metadata and current workload/controller identities
- Observed HPA utilization signals and explicit mutating VPA container resource policies
- Review controller responsibilities and resource signals with the owner; no controller change or numeric resource reduction is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped metadata and current workload/controller identities
- Observed HPA utilization signals and explicit mutating VPA container resource policies
- Review controller responsibilities and resource signals with the owner; no controller change or numeric resource reduction is proposed.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-002"
  ],
  "pack_parameters": {
    "AKS-AS-002": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-002": "bc2fc328dc8244e004bdcf6b452344a87948fb232c5021c63c1245f6ae03f376"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-002`.

## AKS-AS-003: Review HPA \_\_bound\_state\_\_ history

Version: 1.0.0; family: autoscaler; evidence: metrics.

Investigate sampled floor, ceiling or fixed counts using four full-grid controller-UID-bound gauges, not today's bounds extrapolated into history.

Pack/query digest: `129fc1650bd91b20c8a2415cd824b56913c06881d2e5db041f5e9298be088592`.

Baseline: Requested and current HPA replica counts remained at a configured bound at every collected evaluation point in the assessment window. This does not prove continuous pinning between samples, low demand, unmet demand, saturation or SLO impact.

Guarded: Requested and current HPA replica counts remained at a configured bound at every collected evaluation point in the assessment window. This does not prove continuous pinning between samples, low demand, unmet demand, saturation or SLO impact.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Have the owner verify historical HPA/workload UID enrichment and bound semantics; references are declarations, not source attestation.
- Review availability, failover, warm capacity, scaling signals and controller health before interpreting any minimum or maximum.

### Limitations

- Current-only configuration cannot establish controller history.
- Evaluation-point coverage is not continuous pinning, raw scrape completeness or proof of demand.

### Risks

- A floor can be intentional resilience capacity, not waste.
- A ceiling alone does not establish unsatisfied demand or saturation.
- Evaluation-point coverage can miss behavior between samples.

### Validation

- Correlate approved replica, demand, readiness and controller evidence with owner-declared SLOs before considering a separate change.
- Validate any separately approved change under startup, peak load and failover with explicit availability and rollback criteria.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and four 100-percent aligned HPA history series
- One current HPA with matching historical controller and target workload UIDs
- Stable historical bounds and matching fresh current spec/status
- Investigate whether the observed replica bound remains appropriate with the owner; no replica target or controller change is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and four 100-percent aligned HPA history series
- One current HPA with matching historical controller and target workload UIDs
- Stable historical bounds and matching fresh current spec/status
- Investigate whether the observed replica bound remains appropriate with the owner; no replica target or controller change is proposed.

### Query templates (not executable exports)

- hpa_current_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_current\_replicas\{\_\_scope\_\_\}
- hpa_desired_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_desired\_replicas\{\_\_scope\_\_\}
- hpa_max_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_max\_replicas\{\_\_scope\_\_\}
- hpa_min_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_min\_replicas\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-003"
  ],
  "pack_parameters": {
    "AKS-AS-003": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-003": "129fc1650bd91b20c8a2415cd824b56913c06881d2e5db041f5e9298be088592"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-003`.

## AKS-AS-004: Review controller ownership and activation

Version: 1.0.0; family: autoscaler; evidence: inventory.

Investigate current KEDA ownership, generated HPA chains, activation and multiple controllers without interpreting trigger values or collecting authentication.

Pack/query digest: `de32fe82374db00e8ee980be1abc2246ba947c9fcefd27e137a6dfb96518e14d`.

Baseline: Review current controller responsibilities; configuration does not prove oscillation, demand or SLO impact.

Guarded: Review current controller responsibilities; configuration does not prove oscillation, demand or SLO impact.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Evidence-selected summaries

- multiple-controllers: Multiple controllers target the same current workload. Review their responsibilities; this does not prove oscillation or SLO impact.
- keda-chain: KEDA owns the observed generated HPA; these are one scaling chain, not two competing HPAs. Trigger types and metric types are current configuration, not proof of demand or activation.
- cpu-memory-only: CPU/memory-only triggers cannot activate a workload from zero; review an independent activation signal and availability policy.
- zero-minimum: A declared zero minimum is only a scale-to-zero review candidate; verify activation, cold-start, state and availability requirements.

### Prerequisites

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.
- For KEDA, verify activation, trigger authentication and generated HPA behavior in operator tools; trigger values and credentials are never collected by the advisor.

### Limitations

- A generated HPA and its KEDA owner are one chain, not two competing HPAs.
- A zero minimum is an investigation only, not safe zero capacity or observed activation.

### Risks

- Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.
- Scale-to-zero can violate cold-start, state, quorum, throughput or availability requirements.

### Validation

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped metadata with observed HPA/VPA/KEDA APIs
- Exact workload/controller UIDs and resolved KEDA generated-HPA ownership
- Explicit trigger types, metric types, minima/maxima, polling and cooldown
- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

### Guarded evidence and actions

- Complete fresh exact-scoped metadata with observed HPA/VPA/KEDA APIs
- Exact workload/controller UIDs and resolved KEDA generated-HPA ownership
- Explicit trigger types, metric types, minima/maxima, polling and cooldown
- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-004"
  ],
  "pack_parameters": {
    "AKS-AS-004": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-004": "de32fe82374db00e8ee980be1abc2246ba947c9fcefd27e137a6dfb96518e14d"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-004`.

## AKS-AS-005: Review bounded HPA minimum replicas

Version: 1.0.0; family: autoscaler; evidence: metrics.

A separately default-off positive-only HPA minimum proposal preserves maximum, signals and resources under configuration-bound owner and availability review.

Pack/query digest: `aa841b1ac664b2ad990ecb3c069a531d57cda5b04e2421341650ef5eb5a388f0`.

Baseline: Baseline exposes evidence gaps only; a numeric HPA floor proposal requires guarded mode and independent owner opt-in with complete configuration-bound history.

Guarded: An explicitly opted-in owner policy and complete stable HPA/workload availability history permit a bounded minimum-replica proposal. Owner review declarations are not source attestation or change approval. The HPA maximum, metric targets and resource requests remain unchanged; no savings or automatic remediation is implied.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Obtain separate owner approval bound to this exact workload/HPA UID, proposal, configuration and observation window.
- Reconfirm the reviewed load test, throughput, startup, zonal failure, failover reserve and disruption allowance for the proposed floor.

### Limitations

- KEDA-managed floors, StatefulSet/quorum, PDB matching, changed controllers, Pod budgets and unsupported scheduling/overhead are blocked.
- No current-only values, references or digests establish historical evidence, source attestation or change approval.
- Proposed floor is at least one and below the current floor; resources, maximum and signals remain unchanged.

### Risks

- Lower warm capacity can delay scale-up or increase per-Pod load.
- PDB matching, stateful quorum, KEDA-managed floors, changing histories and unsupported scheduling constraints are not supported proposals.

### Validation

- Canary only the HPA minimum; leave maximum, signals and CPU/memory requests unchanged. Verify availability and SLOs under peak load, startup and declared zone/failover scenarios.
- Stop promotion on pending/unavailable Pods, elevated throttling, OOM/restarts, scale-up latency or throughput/SLO regression.

### Rollback

- Restore the original HPA minimum of \_\_current\_floor\_\_ replicas through customer-owned delivery tooling on any guardrail regression; the advisor never changes controllers or performs rollback.

### Baseline rollback


### Baseline evidence and actions

- Current configuration and all seven full-grid UID-bound series may expose explicit proposal gaps, never a numeric baseline proposal
- Review the structured HPA minimum proposal with the owner; this report does not approve or apply a change.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and all seven 100-percent aligned stable HPA/workload series
- One unmanaged HPA and unconstrained Deployment with explicit current availability
- Default-off allow\_floor\_reduction and exact HPA/configuration/window-bound owner review
- Reviewed positive tested/minimum replicas, maximum reduction, failover reserve and disruption allowance
- Independently reviewed peak, throughput, startup, zone failure and zero reliability incidents
- Review the structured HPA minimum proposal with the owner; this report does not approve or apply a change.

### Query templates (not executable exports)

- available_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_available\_replicas\{\_\_scope\_\_\}
- desired_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_desired\_replicas\{\_\_scope\_\_\}
- hpa_current_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_current\_replicas\{\_\_scope\_\_\}
- hpa_desired_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_desired\_replicas\{\_\_scope\_\_\}
- hpa_max_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_max\_replicas\{\_\_scope\_\_\}
- hpa_min_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_min\_replicas\{\_\_scope\_\_\}
- observed_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_observed\_pods\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-005"
  ],
  "pack_parameters": {
    "AKS-AS-005": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-005": "aa841b1ac664b2ad990ecb3c069a531d57cda5b04e2421341650ef5eb5a388f0"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-005`.

## AKS-AS-006: Review changed HPA bounds and replica context

Version: 1.0.0; family: autoscaler; evidence: metrics.

Investigate changing sampled controller bounds/count context independently of the stable-pinning and floor-proposal gates.

Pack/query digest: `abf0c1f18ad7f1856d2a0dce4c76be3d0b07bc87dc620c1bc799658a00f874c0`.

Baseline: Historical or current HPA bounds/count context changed. These sampled extrema do not establish oscillation, scaling lag, unmet demand or SLO impact. Reassess controller identity and availability before proposing a change.

Guarded: Historical or current HPA bounds/count context changed. These sampled extrema do not establish oscillation, scaling lag, unmet demand or SLO impact. Reassess controller identity and availability before proposing a change.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.

### Limitations

- Current-only evidence cannot establish historical changes.
- Changing sampled extrema do not diagnose oscillation, scaling lag or unmet demand.

### Risks

- Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.

### Validation

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and four full-grid controller/workload UID-bound history series
- Matching current HPA identity and structurally consistent integer count extrema
- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and four full-grid controller/workload UID-bound history series
- Matching current HPA identity and structurally consistent integer count extrema
- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

### Query templates (not executable exports)

- hpa_current_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_current\_replicas\{\_\_scope\_\_\}
- hpa_desired_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_desired\_replicas\{\_\_scope\_\_\}
- hpa_max_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_max\_replicas\{\_\_scope\_\_\}
- hpa_min_replicas v1.0.0, hpa, pods.
  Template: aks\_advisor:hpa\_min\_replicas\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-006"
  ],
  "pack_parameters": {
    "AKS-AS-006": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-006": "abf0c1f18ad7f1856d2a0dce4c76be3d0b07bc87dc620c1bc799658a00f874c0"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-006`.

## AKS-AS-007: Review VPA recommendation and policy bounds

Version: 1.0.0; family: autoscaler; evidence: inventory.

Inspect current VPA resource targets, lower/upper/uncapped bounds and exact-container policy precedence without deriving advisor resource proposals.

Pack/query digest: `94b5bc8f0b4e303252079dca55dd6ae7b6adc9e4ae8f7aa600e743d16ff409f1`.

Baseline: Current VPA status retains resource targets and bounds, not an advisor rightsizing authorization. Metadata freshness does not establish the VPA recommendation's generation time or representative history.

Guarded: Current VPA status retains resource targets and bounds, not an advisor rightsizing authorization. Metadata freshness does not establish the VPA recommendation's generation time or representative history.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.

### Limitations

- Metadata freshness does not prove VPA recommendation generation time or representative history.
- A VPA target is context, not an advisor request/limit authorization.

### Risks

- Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.

### Validation

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped metadata with current workload/controller UIDs
- One VPA with matching admitted containers and explicit coherent resource/policy bounds in mCPU or MiB
- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

### Guarded evidence and actions

- Complete fresh exact-scoped metadata with current workload/controller UIDs
- One VPA with matching admitted containers and explicit coherent resource/policy bounds in mCPU or MiB
- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-AS-007"
  ],
  "pack_parameters": {
    "AKS-AS-007": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-AS-007": "94b5bc8f0b4e303252079dca55dd6ae7b6adc9e4ae8f7aa600e743d16ff409f1"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-AS-007`.

## AKS-MEM-001: Investigate OOM events

Version: 1.0.0; family: memory; evidence: metrics.

OOM events were observed in the assessment window. Investigate memory limits, workload behavior and node pressure before any resource reduction; event counts alone do not identify the cause.

Pack/query digest: `f69012630c4d2a464a20053c932d05b8669666311d1237b3bc198c398c3c4c42`.

Baseline: OOM events were observed in the assessment window. Investigate memory limits, workload behavior and node pressure before any resource reduction; event counts alone do not identify the cause.

Guarded: OOM events were observed in the assessment window. Investigate memory limits, workload behavior and node pressure before any resource reduction; event counts alone do not identify the cause.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Have the workload owner correlate OOM timing with memory limits, node pressure, restarts and application SLOs through approved tools.

### Limitations

- OOM events were observed in the assessment window. Investigate memory limits, workload behavior and node pressure before any resource reduction; event counts alone do not identify the cause.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Lowering memory requests or limits can worsen eviction or OOM risk.
- Working-set samples can miss short peaks and do not prove a safe memory limit or request.

### Validation

- Review startup, peak load and failover memory behavior.
- Validate any separately approved change against OOM, restarts, evictions and owner-declared SLOs.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Investigate memory reliability before considering rightsizing; no numeric memory reduction is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Investigate memory reliability before considering rightsizing; no numeric memory reduction is proposed.

### Query templates (not executable exports)

- oom_events v1.0.0, container, events.
  Template: increase\(container\_oom\_events\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- replica_oom_events v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_oom\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-MEM-001"
  ],
  "pack_parameters": {
    "AKS-MEM-001": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-MEM-001": "f69012630c4d2a464a20053c932d05b8669666311d1237b3bc198c398c3c4c42"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-MEM-001`.

## AKS-MEM-002: Review memory safety

Version: 1.0.0; family: memory; evidence: metrics.

Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.

Pack/query digest: `a1c26aa2a90c056b93c48279c9df977c97d9e9d9f26d6a275a8cadd414a1f52a`.

Baseline: Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.

Guarded: Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Independently verify owner-reviewed startup, failover and eviction evidence; references and declarations are not source attestation.
- Keep limits and QoS unchanged; any future target needs separate owner approval and effective-Pod validation.

### Limitations

- Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Working set and sampled peaks can omit relevant memory and bursts.
- Lower requests can increase node-pressure eviction risk even when the QoS class is unchanged.

### Validation

- Validate startup, peak load and failover against owner-declared SLOs, OOM, restarts and evictions before approving any change.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- Existing QoS, admission, controller, full-grid and reliability guards
- Review memory safety evidence only; no numeric memory request or limit change is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- Existing QoS, admission, controller, full-grid and reliability guards
- Review memory safety evidence only; no numeric memory request or limit change is proposed.

### Query templates (not executable exports)

- available_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_available\_replicas\{\_\_scope\_\_\}
- desired_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_desired\_replicas\{\_\_scope\_\_\}
- evictions v1.0.0, workload, events.
  Template: aks\_advisor:workload\_eviction\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- hpa_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_hpa\_present\{\_\_scope\_\_\}
- keda_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_keda\_present\{\_\_scope\_\_\}
- memory_limit v1.0.0, container, MiB.
  Template: kube\_pod\_container\_resource\_limits\{\_\_scope\_\_,resource="memory",unit="byte"\} / 1048576
- memory_request v1.0.0, container, MiB.
  Template: kube\_pod\_container\_resource\_requests\{\_\_scope\_\_,resource="memory",unit="byte"\} / 1048576
- memory_usage v1.0.0, container, MiB.
  Template: container\_memory\_working\_set\_bytes\{\_\_scope\_\_\} / 1048576
- observed_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_observed\_pods\{\_\_scope\_\_\}
- oom_events v1.0.0, container, events.
  Template: increase\(container\_oom\_events\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- replica_memory_envelope v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_max\_mib\{\_\_scope\_\_\}
- replica_memory_limit_max v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_limit\_max\_mib\{\_\_scope\_\_\}
- replica_memory_limit_min v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_limit\_min\_mib\{\_\_scope\_\_\}
- replica_memory_request_max v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_request\_max\_mib\{\_\_scope\_\_\}
- replica_memory_request_min v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_request\_min\_mib\{\_\_scope\_\_\}
- replica_oom_events v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_oom\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- replica_restarts v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_restart\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- restarts v1.0.0, container, events.
  Template: increase\(kube\_pod\_container\_status\_restarts\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- unschedulable_pods v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_unschedulable\_pods\{\_\_scope\_\_\}
- vpa_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_vpa\_present\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-MEM-002"
  ],
  "pack_parameters": {
    "AKS-MEM-002": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-MEM-002": "a1c26aa2a90c056b93c48279c9df977c97d9e9d9f26d6a275a8cadd414a1f52a"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-MEM-002`.

## AKS-MEM-003: Validate memory request candidate

Version: 1.0.0; family: memory; evidence: metrics.

Validate one exact upstream memory request candidate against the declared owner minimum, maximum reduction, peak/startup/failover headroom, admission, QoS and reliability evidence.

Pack/query digest: `24ac10817abfeb3f6ad2641646310ada00dd1c61113f60dd14a3985f9560d369`.

Baseline: The upstream memory request candidate requires guarded evidence validation; no candidate is approved or applied by this baseline review.

Guarded: The upstream memory request candidate is not below the accelerator safety floor and passed the required admission, QoS, reliability and owner-policy gates.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Obtain separate owner approval for this specific request-only change; enabling proposals is not approval to apply them.
- Independently verify the reviewed scenario/eviction evidence, supported direct or approved-envelope history, absent overhead and current admitted settings.
- Keep CPU requests, all limits and other containers unchanged; do not combine independent CPU and memory proposals in one canary.

### Limitations

- The accelerator calculates a safety floor and rejects candidates below it; the accepted value remains the upstream candidate, not an independently derived target.
- A validated candidate does not prove node removability, financial savings or change approval.
- References/digests are integrity declarations, not source attestation or approval.
- Candidate conflicts are evaluated per exact container and resource dimension; unknown source versions remain blocked.
- Current Off-mode VPA preserves qualified history but does not prove its historical mode or authorize a change.

### Risks

- Working-set samples can omit relevant memory and short peaks.
- Lower requests reduce eviction protection and can increase node pressure or change placement despite unchanged Burstable QoS.

### Validation

- Canary only the approved memory request under startup, peak load and failover; confirm the limit and QoS remain unchanged.
- Compare OOM, restarts, evictions, placement and owner-declared SLOs with the pre-change baseline before promotion.

### Rollback

- If OOM, restarts, evictions or owner-declared SLOs regress, stop promotion and restore the original \_\_current\_request\_mib\_\_ MiB memory request through the owning delivery pipeline; keep all other settings unchanged.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- One exact fresh per-container VPA or Kubecost candidate from a characterized source version matching current workload, request and unit
- Existing QoS, admission, controller, full-grid and reliability guards
- Review the validated upstream \_\_proposed\_request\_mib\_\_ MiB candidate for this container only; keep limits unchanged and obtain owner approval.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- One exact fresh per-container VPA or Kubecost candidate from a characterized source version matching current workload, request and unit
- Existing QoS, admission, controller, full-grid and reliability guards
- Review the validated upstream \_\_proposed\_request\_mib\_\_ MiB candidate for this container only; keep limits unchanged and obtain owner approval.

### Query templates (not executable exports)

- available_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_available\_replicas\{\_\_scope\_\_\}
- desired_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_desired\_replicas\{\_\_scope\_\_\}
- evictions v1.0.0, workload, events.
  Template: aks\_advisor:workload\_eviction\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- hpa_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_hpa\_present\{\_\_scope\_\_\}
- keda_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_keda\_present\{\_\_scope\_\_\}
- memory_limit v1.0.0, container, MiB.
  Template: kube\_pod\_container\_resource\_limits\{\_\_scope\_\_,resource="memory",unit="byte"\} / 1048576
- memory_request v1.0.0, container, MiB.
  Template: kube\_pod\_container\_resource\_requests\{\_\_scope\_\_,resource="memory",unit="byte"\} / 1048576
- memory_usage v1.0.0, container, MiB.
  Template: container\_memory\_working\_set\_bytes\{\_\_scope\_\_\} / 1048576
- observed_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_observed\_pods\{\_\_scope\_\_\}
- oom_events v1.0.0, container, events.
  Template: increase\(container\_oom\_events\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- replica_memory_envelope v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_max\_mib\{\_\_scope\_\_\}
- replica_memory_limit_max v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_limit\_max\_mib\{\_\_scope\_\_\}
- replica_memory_limit_min v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_limit\_min\_mib\{\_\_scope\_\_\}
- replica_memory_request_max v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_request\_max\_mib\{\_\_scope\_\_\}
- replica_memory_request_min v1.0.0, workload_container, MiB.
  Template: aks\_advisor:workload\_container\_memory\_request\_min\_mib\{\_\_scope\_\_\}
- replica_oom_events v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_oom\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- replica_restarts v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_restart\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- restarts v1.0.0, container, events.
  Template: increase\(kube\_pod\_container\_status\_restarts\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- unschedulable_pods v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_unschedulable\_pods\{\_\_scope\_\_\}
- vpa_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_vpa\_present\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-MEM-003"
  ],
  "pack_parameters": {
    "AKS-MEM-003": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-MEM-003": "24ac10817abfeb3f6ad2641646310ada00dd1c61113f60dd14a3985f9560d369"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-MEM-003`.

## AKS-MEM-004: Review effective Pod memory

Version: 1.0.0; family: memory; evidence: inventory.

Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.

Pack/query digest: `c6cdb8cf9cc9bb99fbea9fc5fcf5a5f68c5d907dbde5e71b53d3f009fa281480`.

Baseline: Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.

Guarded: Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Verify admitted quantities, native sidecar ordering and overhead.

### Limitations

- Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Current accounting does not establish historical usage or packing feasibility.

### Validation

- Compare the current effective request with the admitted Pod configuration.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped Azure/Kubernetes receipts
- Approved current UID-bound metadata; no history extrapolation
- Review accounting only; no request or limit change is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped Azure/Kubernetes receipts
- Approved current UID-bound metadata; no history extrapolation
- Review accounting only; no request or limit change is proposed.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-MEM-004"
  ],
  "pack_parameters": {
    "AKS-MEM-004": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-MEM-004": "c6cdb8cf9cc9bb99fbea9fc5fcf5a5f68c5d907dbde5e71b53d3f009fa281480"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-MEM-004`.

## AKS-MEM-005: Review bounded memory limit

Version: 1.0.0; family: memory; evidence: metrics.

An explicitly opted-in, configuration-bound memory limit proposal uses complete total-memory usage, not working set alone, plus reviewed allocator/cache, startup and failover peaks. Requests, CPU and other containers remain unchanged; owner declarations are not source attestation or approval.

Pack/query digest: `bb86c88b2d765e4de7e7596fe02ac0cc2f37fa808334b802534a667b0bd5312b`.

Baseline: An explicitly opted-in, configuration-bound memory limit proposal uses complete total-memory usage, not working set alone, plus reviewed allocator/cache, startup and failover peaks. Requests, CPU and other containers remain unchanged; owner declarations are not source attestation or approval.

Guarded: An explicitly opted-in, configuration-bound memory limit proposal uses complete total-memory usage, not working set alone, plus reviewed allocator/cache, startup and failover peaks. Requests, CPU and other containers remain unchanged; owner declarations are not source attestation or approval.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Obtain separate approval for the exact container/configuration, limit and evidence window.
- Independently verify allocator/cache and full-memory scenario evidence; preserve requests and QoS.

### Limitations

- An explicitly opted-in, configuration-bound memory limit proposal uses complete total-memory usage, not working set alone, plus reviewed allocator/cache, startup and failover peaks. Requests, CPU and other containers remain unchanged; owner declarations are not source attestation or approval.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Lower hard limits can cause OOM despite unchanged requests and Burstable QoS.
- Sampled total-memory peaks are not proof that all future peaks were observed.

### Validation

- Canary the memory limit only under startup, peak and failover load; leave all requests unchanged.
- Stop promotion on OOM, restarts, evictions or owner SLO regression.

### Rollback

- Restore the original \_\_current\_limit\_mib\_\_ MiB limit through customer delivery tooling on regression; the advisor never rolls back.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- Existing QoS, admission, controller, full-grid and reliability guards
- Review this limit-only proposal with the owner; no change is authorized or applied.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- Existing QoS, admission, controller, full-grid and reliability guards
- Review this limit-only proposal with the owner; no change is authorized or applied.

### Query templates (not executable exports)

- available_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_available\_replicas\{\_\_scope\_\_\}
- desired_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_desired\_replicas\{\_\_scope\_\_\}
- evictions v1.0.0, workload, events.
  Template: aks\_advisor:workload\_eviction\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- hpa_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_hpa\_present\{\_\_scope\_\_\}
- keda_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_keda\_present\{\_\_scope\_\_\}
- memory_limit v1.0.0, container, MiB.
  Template: kube\_pod\_container\_resource\_limits\{\_\_scope\_\_,resource="memory",unit="byte"\} / 1048576
- memory_request v1.0.0, container, MiB.
  Template: kube\_pod\_container\_resource\_requests\{\_\_scope\_\_,resource="memory",unit="byte"\} / 1048576
- memory_total_usage v1.0.0, container, MiB.
  Template: container\_memory\_usage\_bytes\{\_\_scope\_\_\} / 1048576
- observed_replicas v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_observed\_pods\{\_\_scope\_\_\}
- oom_events v1.0.0, container, events.
  Template: increase\(container\_oom\_events\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- restarts v1.0.0, container, events.
  Template: increase\(kube\_pod\_container\_status\_restarts\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- unschedulable_pods v1.0.0, workload, pods.
  Template: aks\_advisor:workload\_unschedulable\_pods\{\_\_scope\_\_\}
- vpa_present v1.0.0, workload, boolean.
  Template: aks\_advisor:workload\_vpa\_present\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-MEM-005"
  ],
  "pack_parameters": {
    "AKS-MEM-005": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-MEM-005": "bb86c88b2d765e4de7e7596fe02ac0cc2f37fa808334b802534a667b0bd5312b"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-MEM-005`.

## AKS-NP-001: Review low-utilization node pool

Version: 1.0.0; family: node-pool; evidence: metrics.

Investigate qualified historical pool usage while preserving complete membership, aligned sums and constant capacity.

Pack/query digest: `f9209222647295f9d7c0db4518fdd6170f77f2f39567ff4ab402d345e1abebe8`.

Baseline: P95 CPU utilization is below the configured review threshold. This is not proof a node can be removed; validate resilience and scheduling constraints before a separately approved change.

Guarded: P95 CPU utilization is below the configured review threshold. This is not proof a node can be removed; validate resilience and scheduling constraints before a separately approved change.

### Review parameters

- review_ratio: default 0.2 ratio; 0 &lt;= review\_ratio &lt; 1. Investigation threshold only, not a utilization target or proposal bound. Equality produces no signal; safety/owner gates cannot be overridden.

### Prerequisites

- Confirm pod disruption budgets and zonal resilience.
- Check pending pods, daemonset overhead and scale-up latency.

### Limitations

- Low CPU usage is not proof a node can be removed.
- Current node membership cannot reconstruct deleted-node history.
- This pack does not implement NAP eligibility, packing simulation or a node-count target.

### Risks

- Reducing warm capacity can increase scale-up latency.
- Average or P95 utilization alone can hide short bursts.

### Validation

- Load test any separately proposed minimum capacity.
- Compare P95/P99 saturation, pending pods and SLOs before and after.

### Rollback

- No node target is proposed; revert a separately approved capacity change through the owning delivery pipeline on regression.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh scoped sources
- Exact pool and historical node identities
- Complete historical membership
- Aligned usage summed before percentiles
- Full-window constant allocatable capacity
- Review minimum node count and autoscaler profile.
- Investigate existing placement and resilience requirements.

### Guarded evidence and actions

- Complete fresh scoped sources
- Exact pool and historical node identities
- Complete historical membership
- Aligned usage summed before percentiles
- Full-window constant allocatable capacity
- Review minimum node count and autoscaler profile.
- Investigate existing placement and resilience requirements.

### Query templates (not executable exports)

- node_allocatable_cpu v1.0.0, node, mCPU.
  Template: aks\_advisor:node\_allocatable\_cpu\_mcores\{\_\_scope\_\_\}
- node_allocatable_memory v1.0.0, node, MiB.
  Template: aks\_advisor:node\_allocatable\_memory\_mib\{\_\_scope\_\_\}
- node_cpu_usage v1.0.0, node, mCPU.
  Template: aks\_advisor:node\_cpu\_usage\_mcores\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-NP-001"
  ],
  "pack_parameters": {
    "AKS-NP-001": {
      "review_ratio": 0.2
    }
  },
  "pack_locks": {
    "AKS-NP-001": "f9209222647295f9d7c0db4518fdd6170f77f2f39567ff4ab402d345e1abebe8"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-NP-001`.

## AKS-NP-002: Review capacity management and NAP prerequisites

Version: 1.0.0; family: node-pool; evidence: inventory.

Classify current fixed/CAS pools and UID-bound NAP supply independently of historical pool utilization.

Pack/query digest: `96fd7b91e3b77b99e6e7c67ab1e10130f0e31664774746999231cc1467808d7b`.

Baseline: Current capacity configuration and declared intent support investigation only, not NAP eligibility, migration approval, lower minima, removable nodes or financial savings.

Guarded: Current capacity configuration and declared intent support investigation only, not NAP eligibility, migration approval, lower minima, removable nodes or financial savings.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Review current Microsoft AKS NAP support for the exact version, region, networking and identity.
- Preserve system capacity, Spot interruption tolerance, hardware, zoning and owner-reserved capacity.
- Compare CAS tuning with a separately approved transition; do not enable NAP or disable CAS from this report.

### Limitations

- Auto cluster mode does not make existing ARM pools NAP-managed. Dynamic supply requires exact NodeClaim/NodePool ownership and provider-bound Node identity.
- Equal CAS bounds are configuration, not intentional reservation or a safe lower minimum.
- Specialization and reserved capacity require exact-pool owner declarations; SKU strings alone do not prove hardware requirements.
- Networking, identity, quota, regional SKU availability, workload/disruption fit and operational acceptance are unverified prerequisites.
- Current policies and supply do not establish consolidation behavior, packing feasibility, removable nodes or cash savings.

### Risks

- Removing minima or migrating capacity can violate disruption, storage, specialized hardware and failover requirements.
- NAP has unsupported configurations and stop/start and egress constraints; configuration eligibility alone is insufficient.

### Validation

- Confirm complete NAP API lists, exact owner/provider identities, node-class requirements, limits and disruption budgets.
- Validate all unknown prerequisites using separately approved sanitized evidence and current AKS documentation.
- Require workload-fit, pending-Pod, availability and packing evidence before a separate migration proposal.

### Rollback

- No change is proposed. A later approved experiment must retain original capacity and define an owner-controlled rollback.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped Azure and Kubernetes inventory with a verified cluster fingerprint
- Investigate capacity classes and missing prerequisites; no migration or node-count change is recommended.

### Guarded evidence and actions

- Complete fresh exact-scoped Azure and Kubernetes inventory with a verified cluster fingerprint
- Investigate capacity classes and missing prerequisites; guarded mode does not authorize migration.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-NP-002"
  ],
  "pack_parameters": {
    "AKS-NP-002": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-NP-002": "96fd7b91e3b77b99e6e7c67ab1e10130f0e31664774746999231cc1467808d7b"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-NP-002`.

## AKS-NP-003: Review current NAP consolidation blockers

Version: 1.0.0; family: node-pool; evidence: inventory.

Correlate exact current NAP NodePool disruption policy with observed placement, ownership, local-storage and namespace PDB context before a separate consolidation investigation.

Pack/query digest: `341da7cf1a7589dcb068f3a4090306fe0e3a9591ea31634fedabeeb6c0f51124`.

Baseline: Observed current NodePool and scheduling facts may block consolidation. This is not packing or disruption feasibility, a removable-node claim, a replacement plan or savings.

Guarded: Observed current NodePool and scheduling facts may block consolidation. Guarded mode does not authorize disruption, removal, replacement or a NodePool change.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Review each blocker with workload, storage and platform owners using approved current Kubernetes and AKS tooling.
- Obtain separate pending-shape, DaemonSet overhead, PDB selector, replacement-capacity and failure-domain evidence before any consolidation feasibility claim.

### Limitations

- Pod constraints are scoped only through exact current Pod-to-Node-to-provider/UID-bound NodeClaim-to-NodePool membership; they do not prove eligibility for another pool.
- Namespace PDB context is limited to namespaces of attributed Pods and remains unmatched; unknown attribution is a separate gap beside independently observed policy facts.
- Static-pool effectiveness and disruption-budget reason/schedule semantics are not calculated; literal settings are configuration facts, not an active-disruption simulation.
- Literal zone requirements, retained minValues and zone labels on exact current NodeClaim-bound Nodes are descriptive only; they do not establish eligible domains, minimum diversity effectiveness, zone availability or replacement feasibility.
- Missing PDB status remains unknown; an unavailable PDB list produces an independent gap and unknown counts without erasing observed NodePool policy blockers.
- Invalid static replica evidence blocks only the affected NodePool; shared inventory and identity failures remain cluster-scoped.
- Unknown NAP APIs are not applicable by default; unavailable NodePool inventory blocks only when Auto mode, a NAP pool or UID/provider-bound NAP supply is observed.
- NodePool policy and current Pod/PDB facts do not establish packing feasibility, disruption feasibility or a removable node.
- Namespace PDBs are not matched to Pods because arbitrary labels are excluded; zero disruptions is point-in-time context only.
- DaemonSet presence is retained but its per-node resource overhead is not calculated by this pack.
- Do-not-disrupt annotations, volume/CSI binding, application quorum, pending shapes and eligible replacement capacity are not collected here.

### Risks

- Treating current policy or aggregate free capacity as removal feasibility can violate availability, storage, topology or specialized-compute requirements.
- Voluntary disruption settings do not cover every expiry, interruption or involuntary failure path.

### Validation

- Confirm exact NodePool/node-class identities, current disruption policy and all excluded or unknown blocker classes.
- Review declared zone requirements separately from current bound-Node zone labels; missing labels, partial requirements and unresolved membership are unknown, not zero available zones.
- Match actual PDB selectors and storage/topology constraints outside this report before any separately approved disruption test.
- Validate DaemonSet overhead, pending Pod shapes, replacement capacity and owner availability requirements independently.

### Rollback

- No change is proposed. Any later owner-approved experiment must preserve the original NodePool and workload policies for immediate restoration.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped Azure and Kubernetes inventory with a verified cluster fingerprint
- Exact NodePool/node-class identity, disruption policy and sanitized current scheduling/PDB context
- Investigate current consolidation blockers; do not drain, replace or remove nodes from this report.

### Guarded evidence and actions

- Complete fresh exact-scoped Azure and Kubernetes inventory with a verified cluster fingerprint
- Exact NodePool/node-class identity, disruption policy and sanitized current scheduling/PDB context
- Investigate current consolidation blockers; guarded mode does not authorize disruption or a NodePool change.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-NP-003"
  ],
  "pack_parameters": {
    "AKS-NP-003": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-NP-003": "341da7cf1a7589dcb068f3a4090306fe0e3a9591ea31634fedabeeb6c0f51124"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-NP-003`.

## AKS-NP-004: Review DaemonSet overhead across current node shapes

Version: 1.0.0; family: node-pool; evidence: inventory.

Compare the same DaemonSet's identical effective admitted CPU and memory requests against current allocatable capacity on different observed nodes.

Pack/query digest: `99962096cbf4483b8ab0a938f7b41ed7ad00818346286e990d3bb894f733d949`.

Baseline: Identical admitted DaemonSet requests occupy different fractions of current node allocatable capacity. This is owner-review context, not a universal target, usage measurement, placement claim or savings.

Guarded: Identical admitted DaemonSet requests occupy different fractions of current node allocatable capacity. Guarded mode does not authorize sizing, admission annotations, placement or node removal.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Confirm the DaemonSet owner and whether heterogeneous nodes need distinct resource policies using approved tooling.

### Limitations

- Values describe current effective requests including init and restartable-sidecar ordering, not usage, readiness, free capacity or historical membership.
- Only observed assigned nonterminal DaemonSet Pods are compared; unassigned or unresolved Pods remain evidence gaps and no missing Pod is synthesized.
- Mixed admitted requests, duplicate Pods on a node, unknown lifecycle/resource accounting and missing node capacity block that DaemonSet's comparison.
- Different percentages are owner-review context without a universal materiality threshold or safe per-node request target.
- Desired and ready controller counts are independently retained review context with unverified generation binding; count agreement or differences do not establish desired Node membership, missing Pod placement or disruption feasibility.
- No NodePool eligibility, GPU/extended-resource fit, storage, packing, replacement, removable-node or savings claim is made.

### Risks

- Current requests may protect initialization, restartable sidecars or failure scenarios; lower percentages do not authorize a reduction.

### Validation

- Recheck exact Pod/controller/node identities and admitted requests, init ordering, Pod overhead and allocatable capacity.
- Review controller desired/ready status separately from complete current owned-Pod and Node counts; unknown status does not invalidate independent observed request shares.
- Review node-specific demand, startup and reliability evidence independently before any separately approved sizing experiment.

### Rollback

- No change is proposed. Preserve exact original DaemonSet settings for rollback of any separately approved experiment.

### Baseline rollback


### Baseline evidence and actions

- Fresh complete scoped inventory with exact cluster fingerprint, Namespace, DaemonSet, Pod and current Node identities
- Versioned Pod, Node, Namespace and DaemonSet lists with explicit admitted requests, init containers, Pod overhead and positive node allocatable CPU/memory
- Review observed request-share differences with the DaemonSet and platform owners; do not generate or apply node-specific sizing.

### Guarded evidence and actions

- Fresh complete scoped inventory with exact cluster fingerprint, Namespace, DaemonSet, Pod and current Node identities
- Versioned Pod, Node, Namespace and DaemonSet lists with explicit admitted requests, init containers, Pod overhead and positive node allocatable CPU/memory
- Review observed request-share differences; guarded mode does not authorize sizing, admission annotations or node changes.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-NP-004"
  ],
  "pack_parameters": {
    "AKS-NP-004": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-NP-004": "99962096cbf4483b8ab0a938f7b41ed7ad00818346286e990d3bb894f733d949"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-NP-004`.

## AKS-REL-001: Investigate restarts

Version: 1.0.0; family: reliability; evidence: metrics.

Container restarts were observed in the assessment window. Correlate them with owner-declared SLOs and approved operational evidence; the count alone does not establish memory pressure, an OOM cause or an application failure.

Pack/query digest: `94e2af087bbcfbab390f68d3b7c631f83f61cebca51bb83e7d55c0fe3ab2c503`.

Baseline: Container restarts were observed in the assessment window. Correlate them with owner-declared SLOs and approved operational evidence; the count alone does not establish memory pressure, an OOM cause or an application failure.

Guarded: Container restarts were observed in the assessment window. Correlate them with owner-declared SLOs and approved operational evidence; the count alone does not establish memory pressure, an OOM cause or an application failure.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Have the workload owner distinguish expected restarts from probe, application, OOM or node-related failures using approved tools.

### Limitations

- Container restarts were observed in the assessment window. Correlate them with owner-declared SLOs and approved operational evidence; the count alone does not establish memory pressure, an OOM cause or an application failure.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Restart counts do not identify their cause or prove SLO impact.
- Resource changes without cause analysis can worsen reliability.

### Validation

- Correlate restart timing with changes and owner-declared SLOs.
- Validate any separately approved change under startup, peak load and failover conditions, checking OOM and restart behavior.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Investigate restart causes before considering memory rightsizing; no resource change is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Investigate restart causes before considering memory rightsizing; no resource change is proposed.

### Query templates (not executable exports)

- replica_restarts v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_restart\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}
- restarts v1.0.0, container, events.
  Template: increase\(kube\_pod\_container\_status\_restarts\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-REL-001"
  ],
  "pack_parameters": {
    "AKS-REL-001": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-REL-001": "94e2af087bbcfbab390f68d3b7c631f83f61cebca51bb83e7d55c0fe3ab2c503"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-REL-001`.

## AKS-REL-002: Review reported termination context

Version: 1.0.0; family: reliability; evidence: inventory.

Current UID-bound last-termination status reports a reason and exit code. It does not establish the cause of all restarts, historical frequency, node pressure or SLO impact; exit code 137 alone is not proof of OOM.

Pack/query digest: `d9e19bb911e79d39e3dcf7a4bddee292b51e092cd78ed42c244516325ddd5349`.

Baseline: Current UID-bound last-termination status reports a reason and exit code. It does not establish the cause of all restarts, historical frequency, node pressure or SLO impact; exit code 137 alone is not proof of OOM.

Guarded: Current UID-bound last-termination status reports a reason and exit code. It does not establish the cause of all restarts, historical frequency, node pressure or SLO impact; exit code 137 alone is not proof of OOM.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Confirm the exact current Pod/container and reported termination time.

### Limitations

- Current UID-bound last-termination status reports a reason and exit code. It does not establish the cause of all restarts, historical frequency, node pressure or SLO impact; exit code 137 alone is not proof of OOM.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Retained last-state metadata is not a complete incident history.

### Validation

- Correlate approved incident/change evidence with owner-declared SLOs.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped Azure/Kubernetes receipts
- Approved current UID-bound metadata; no history extrapolation
- Investigate reported context; no resource change is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped Azure/Kubernetes receipts
- Approved current UID-bound metadata; no history extrapolation
- Investigate reported context; no resource change is proposed.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-REL-002"
  ],
  "pack_parameters": {
    "AKS-REL-002": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-REL-002": "d9e19bb911e79d39e3dcf7a4bddee292b51e092cd78ed42c244516325ddd5349"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-REL-002`.

## AKS-REL-003: Investigate workload evictions

Version: 1.0.0; family: reliability; evidence: metrics.

Identity-bound workload eviction counts were observed over the declared window. They are reported once per workload, not multiplied by containers; counts do not establish node-pressure causes or SLO impact.

Pack/query digest: `a210621d7cddb3b84709712cd7daf7b34a221cc97f8d270e4f120bb7998ab569`.

Baseline: Identity-bound workload eviction counts were observed over the declared window. They are reported once per workload, not multiplied by containers; counts do not establish node-pressure causes or SLO impact.

Guarded: Identity-bound workload eviction counts were observed over the declared window. They are reported once per workload, not multiplied by containers; counts do not establish node-pressure causes or SLO impact.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Verify the approved historical eviction producer and workload identity.

### Limitations

- Identity-bound workload eviction counts were observed over the declared window. They are reported once per workload, not multiplied by containers; counts do not establish node-pressure causes or SLO impact.
- References/digests are integrity declarations, not source attestation or approval.

### Risks

- Evictions may have multiple causes; missing history is not zero.

### Validation

- Review approved incident metadata and availability evidence before reductions.

### Rollback

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Investigate workload eviction risk; no numeric change is proposed.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Investigate workload eviction risk; no numeric change is proposed.

### Query templates (not executable exports)

- evictions v1.0.0, workload, events.
  Template: aks\_advisor:workload\_eviction\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-REL-003"
  ],
  "pack_parameters": {
    "AKS-REL-003": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-REL-003": "a210621d7cddb3b84709712cd7daf7b34a221cc97f8d270e4f120bb7998ab569"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-REL-003`.

## AKS-RQ-001: Review missing CPU request

Version: 1.0.0; family: cpu; evidence: inventory.

Investigate an explicitly observed absent or zero admitted CPU request without choosing a target.

Pack/query digest: `64dbc1e4751804bd9f762d1bb37c2dd90d7a1b9884d138034c326136cfaa2e16`.

Baseline: No positive CPU request was explicitly observed. Requests support reliable scheduling, rightsizing and cost attribution. This is an investigation, not a numeric target.

Guarded: No positive CPU request was explicitly observed. Requests support reliable scheduling, rightsizing and cost attribution. This is an investigation, not a numeric target.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Collect representative CPU usage before selecting a value.

### Limitations

- Omitted or unobserved request state is unknown, not absent.
- This review does not select a request or establish savings.

### Risks

- An arbitrarily low request can cause contention or poor placement.

### Validation

- Load test and monitor throttling and latency.

### Rollback

- No numeric change is proposed; restore any separately approved change through the owning delivery pipeline.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh scoped Azure and Kubernetes receipts
- Explicit current admitted request observation
- Use VPA recommendation mode or historical percentiles to propose a request.

### Guarded evidence and actions

- Complete fresh scoped Azure and Kubernetes receipts
- Explicit current admitted request observation
- Use VPA recommendation mode or historical percentiles to propose a request.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-RQ-001"
  ],
  "pack_parameters": {
    "AKS-RQ-001": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-RQ-001": "64dbc1e4751804bd9f762d1bb37c2dd90d7a1b9884d138034c326136cfaa2e16"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-RQ-001`.

## AKS-RQ-002: Review CPU request

Version: 1.0.0; family: cpu; evidence: metrics.

Compare observed CPU usage with the admitted request, then validate one exact upstream request candidate against policy and reliability bounds.

Pack/query digest: `d7f0b7902c6400c9b2be49472a75ee4f949ac164dd6db69f80b2b86f0ff5bd56`.

Baseline: Observed P95 CPU usage is below the configured fraction of the current admitted request. This is an investigation, not a safe reduction target; owner policy, peaks and reliability must be reviewed independently.

Guarded: The upstream CPU request candidate is not below the accelerator safety floor and passed the required evidence gates; validate it through a separately approved canary.

### Review parameters

- review_ratio: default 0.4 ratio; 0 &lt; review\_ratio &lt; 1. Investigation threshold only, not a utilization target or proposal bound. Equality produces no signal; safety/owner gates cannot be overridden.

### Prerequisites

- Confirm the metric window contains peak and business-critical periods.
- Review P99 usage, throttling, startup and failover behavior.

### Limitations

- Low CPU usage is not a safe reduction target or proof a node can be removed.
- Requests are not CPU limits; a request ratio is not saturation.
- Current identities cannot reconstruct missing history or deleted membership.
- Replica-envelope statistics are conservative per-replica values, not workload-total percentiles.
- Returned evaluation-point coverage is not raw scrape completeness.
- Candidate conflicts are evaluated per exact container and resource dimension; unknown source versions remain blocked.
- A current Off-mode VPA does not establish historical nonmutation; independent controller and request history remains required.

### Risks

- Historical usage might not represent future peaks.
- Lower requests can change placement and noisy-neighbor behavior.

### Validation

- Run VPA in Off mode and compare recommendations.
- Canary an independently approved request change and verify SLOs under load.

### Rollback

- Restore the previous CPU request of \_\_current\_cpu\_request\_\_ mCPU in source configuration through the owning delivery pipeline.
- Stop promotion if SLOs, throttling, OOM or restarts regress; remeasure before proposing another change.

### Baseline rollback

- No numeric change is proposed; do not apply a baseline investigation.

### Baseline evidence and actions

- Complete fresh scoped Azure, Kubernetes and Prometheus receipts
- Exact cluster/workload identity and declared direct or approved replica-envelope usage
- Observed positive admitted CPU request and qualified P95 usage
- Configured observation duration, coverage, freshness and resolution
- Review observed usage, owner requirements and missing guarded evidence.

### Guarded evidence and actions

- One exact fresh per-container VPA or Kubecost candidate from a characterized source version matching current workload, request and unit
- All baseline evidence, qualified P99/observed peaks, throttling and OOM history
- Known compatible autoscalers and no observed OOM or workload eviction veto
- Owner-reviewed window, disruption policy, environment, minimum, headroom and reduction bounds
- Review the validated upstream request candidate and rollback criteria before any customer-owned PR.

### Query templates (not executable exports)

- cpu_request v1.0.0, container, mCPU.
  Template: kube\_pod\_container\_resource\_requests\{\_\_scope\_\_,resource="cpu",unit="core"\} \* 1000
- cpu_throttling v1.0.0, container, ratio.
  Template: rate\(container\_cpu\_cfs\_throttled\_periods\_total\{\_\_scope\_\_\}\[5m\]\) / rate\(container\_cpu\_cfs\_periods\_total\{\_\_scope\_\_\}\[5m\]\)
- cpu_usage v1.0.0, container, mCPU.
  Template: rate\(container\_cpu\_usage\_seconds\_total\{\_\_scope\_\_\}\[5m\]\) \* 1000
- oom_events v1.0.0, container, events.
  Template: increase\(container\_oom\_events\_total\{\_\_scope\_\_\}\[\_\_step\_\_s\]\)
- replica_cpu_envelope v1.0.0, workload_container, mCPU.
  Template: aks\_advisor:workload\_container\_cpu\_max\_mcores\{\_\_scope\_\_\}
- replica_cpu_request_max v1.0.0, workload_container, mCPU.
  Template: aks\_advisor:workload\_container\_cpu\_request\_max\_mcores\{\_\_scope\_\_\}
- replica_cpu_request_min v1.0.0, workload_container, mCPU.
  Template: aks\_advisor:workload\_container\_cpu\_request\_min\_mcores\{\_\_scope\_\_\}
- replica_cpu_throttling v1.0.0, workload_container, ratio.
  Template: aks\_advisor:workload\_container\_cpu\_throttling\_max\{\_\_scope\_\_\}
- replica_oom_events v1.0.0, workload_container, events.
  Template: aks\_advisor:workload\_container\_oom\_increase\{\_\_scope\_\_,step\_seconds="\_\_step\_\_"\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-RQ-002"
  ],
  "pack_parameters": {
    "AKS-RQ-002": {
      "review_ratio": 0.4
    }
  },
  "pack_locks": {
    "AKS-RQ-002": "d7f0b7902c6400c9b2be49472a75ee4f949ac164dd6db69f80b2b86f0ff5bd56"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-RQ-002`.

## AKS-RQ-003: Review CPU request risk

Version: 1.0.0; family: cpu; evidence: metrics.

Correlate high observed usage relative to an admitted request with throttling, limits and SLOs; do not infer saturation.

Pack/query digest: `f4f9e64dabd50569063c8b3264932bc5c0c9f0855032f91347377ef55be1cc3a`.

Baseline: P95 CPU usage is close to or above the request. Requests are not CPU limits; this ratio alone does not establish saturation. Review throttling, limits and SLOs before denser placement.

Guarded: P95 CPU usage is close to or above the request. Requests are not CPU limits; this ratio alone does not establish saturation. Review throttling, limits and SLOs before denser placement.

### Review parameters

- review_ratio: default 0.9 ratio; review\_ratio &gt; 0. Investigation threshold only, not a utilization target or proposal bound. Equality produces no signal; safety/owner gates cannot be overridden.

### Prerequisites

- Correlate saturation with latency and error SLOs.

### Limitations

- Requests are not CPU limits; a request ratio does not establish saturation.
- This independent review never proposes resources, replicas or financial savings.

### Risks

- Densification can amplify contention.

### Validation

- Load test at peak concurrency and failover conditions.

### Rollback

- No target is proposed; revert a separately approved change through its owning delivery pipeline if guardrails regress.

### Baseline rollback


### Baseline evidence and actions

- Complete fresh scoped sources
- Observed positive admitted request
- Qualified P95 CPU and throttling evidence
- Review CPU request/limit policy and horizontal scaling signal.

### Guarded evidence and actions

- Complete fresh scoped sources
- Observed positive admitted request
- Qualified P95 CPU and throttling evidence
- Review CPU request/limit policy and horizontal scaling signal.

### Query templates (not executable exports)

- cpu_request v1.0.0, container, mCPU.
  Template: kube\_pod\_container\_resource\_requests\{\_\_scope\_\_,resource="cpu",unit="core"\} \* 1000
- cpu_throttling v1.0.0, container, ratio.
  Template: rate\(container\_cpu\_cfs\_throttled\_periods\_total\{\_\_scope\_\_\}\[5m\]\) / rate\(container\_cpu\_cfs\_periods\_total\{\_\_scope\_\_\}\[5m\]\)
- cpu_usage v1.0.0, container, mCPU.
  Template: rate\(container\_cpu\_usage\_seconds\_total\{\_\_scope\_\_\}\[5m\]\) \* 1000
- replica_cpu_envelope v1.0.0, workload_container, mCPU.
  Template: aks\_advisor:workload\_container\_cpu\_max\_mcores\{\_\_scope\_\_\}
- replica_cpu_request_max v1.0.0, workload_container, mCPU.
  Template: aks\_advisor:workload\_container\_cpu\_request\_max\_mcores\{\_\_scope\_\_\}
- replica_cpu_request_min v1.0.0, workload_container, mCPU.
  Template: aks\_advisor:workload\_container\_cpu\_request\_min\_mcores\{\_\_scope\_\_\}
- replica_cpu_throttling v1.0.0, workload_container, ratio.
  Template: aks\_advisor:workload\_container\_cpu\_throttling\_max\{\_\_scope\_\_\}

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-RQ-003"
  ],
  "pack_parameters": {
    "AKS-RQ-003": {
      "review_ratio": 0.9
    }
  },
  "pack_locks": {
    "AKS-RQ-003": "f4f9e64dabd50569063c8b3264932bc5c0c9f0855032f91347377ef55be1cc3a"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-RQ-003`.

## AKS-SCHED-001: Investigate current placement constraints

Version: 1.0.0; family: scheduling; evidence: inventory.

Explain observed placement restrictions separately from resource usage and vertical eligibility.

Pack/query digest: `420359fdf0a9ef15bef7836a1544ceaa729e2bac461bb97f6a81830c10c5f71b`.

Baseline: Observed current constraints may restrict placement. These are review candidates, not proof of stranded capacity, scheduler failure, PDB matching or removable nodes.

Guarded: Observed current constraints may restrict placement. These are review candidates, not proof of stranded capacity, scheduler failure, PDB matching or removable nodes.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Review the admitted Pod, matching node labels/taints, volume topology and actual PDB selectors with its owner.

### Limitations

- Current metadata is not historical scheduling behavior, a packing simulation or proof of stranded capacity.
- Projected labels cannot prove selector matches or absence. Namespace PDB candidates are not matched budgets.
- Tolerations permit placement but do not require it. Soft preferences are distinct from hard constraints.
- Volume bindings, CSI topology, Pod/IP slots, priority/preemption, daemon requests and availability need independent review.

### Risks

- Relaxing affinity, topology, taints or disruption policy can violate isolation, availability or storage requirements.

### Validation

- Correlate each observed restriction with approved pending-Pod history and scheduler capacity evidence.
- Check daemon and init/sidecar overhead, Pod/IP slots, priorities, volumes and zonal failover before any packing claim.
- Keep hard requirements and soft preferences separate; verify unknown fields rather than assuming absence.

### Rollback

- No change is proposed. Any later owner-approved experiment requires a separate canary and exact configuration rollback.

### Baseline rollback


### Baseline evidence and actions

- Fresh complete scoped inventory with exact cluster, Namespace, Pod and controller UIDs
- Investigate current placement restrictions; do not remove nodes or relax policy from this report.

### Guarded evidence and actions

- Fresh complete scoped inventory with exact cluster, Namespace, Pod and controller UIDs
- Investigate current placement restrictions; guarded mode does not authorize a scheduling change.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-SCHED-001"
  ],
  "pack_parameters": {
    "AKS-SCHED-001": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-SCHED-001": "420359fdf0a9ef15bef7836a1544ceaa729e2bac461bb97f6a81830c10c5f71b"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-SCHED-001`.

## AKS-SCHED-002: Review current optimization constraints

Version: 1.0.0; family: scheduling; evidence: inventory.

Identify current probe, topology-spread and voluntary-disruption evidence that needs owner review before scaling, disruption or consolidation decisions.

Pack/query digest: `254907cebd33f0d8f68d0693dc70856de408a17924a17eace4c08e8a15d3b9cb`.

Baseline: Current probe, topology or voluntary-disruption evidence may constrain scaling, disruption, consolidation or portability. The finding is an owner investigation, not a selector match, universal policy judgment or generated configuration.

Guarded: Current probe, topology or voluntary-disruption evidence may constrain scaling, disruption, consolidation or portability. Guarded mode does not authorize a change or generate configuration.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Ask the workload owner which startup, health, availability, failure-domain and disruption behavior the application requires.
- Verify actual PDB selectors and eligible Pods with approved Kubernetes tooling before relating a budget to a workload.

### Limitations

- Unavailable PDB inventory for observed Pods produces an independent evidence gap without hiding qualified probe or topology findings.
- Probe presence does not establish application health, correct timing or safe probe behavior; probe handlers and payloads are not collected.
- Missing topology spread is an owner review candidate, not proof that spreading is required or that a workload is portable.
- Omitted/defaulted replica counts remain unknown; topology findings are limited to explicitly replicated Deployment and StatefulSet workloads.
- PDB selector matching is unknown. Zero allowed disruptions is a point-in-time voluntary-disruption constraint, not proof that a PDB is universally too strict.
- Current metadata is not historical behavior, disruption feasibility, a node-removal plan or evidence of savings.

### Risks

- Adding probes without application semantics can cause restart loops or remove healthy endpoints from service.
- Changing topology or disruption policy can reduce availability, violate storage constraints or increase correlated failure risk.

### Validation

- Validate probe behavior during startup, steady state, dependency failure and graceful termination using owner-approved tests.
- Validate replica placement and failure-domain behavior before any topology-policy experiment.
- Recheck actual PDB selectors, desired healthy counts and disruptions allowed immediately before any separately approved voluntary disruption.

### Rollback

- No configuration is generated or applied. Restore any separately approved probe, topology or PDB experiment through the owner's delivery system if validation regresses.

### Baseline rollback


### Baseline evidence and actions

- Fresh complete scoped inventory with exact cluster, Namespace, Pod, controller and PDB identities
- Sanitized per-container probe presence, typed topology-spread details and namespace PDB availability/status evidence
- Explicit current controller replica count of at least two for topology-spread findings
- Review the observed constraints with the workload and platform owners; do not generate or apply configuration from this finding.

### Guarded evidence and actions

- Fresh complete scoped inventory with exact cluster, Namespace, Pod, controller and PDB identities
- Sanitized per-container probe presence, typed topology-spread details and namespace PDB availability/status evidence
- Explicit current controller replica count of at least two for topology-spread findings
- Review the observed constraints with the workload and platform owners; guarded mode does not authorize or generate a change.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-SCHED-002"
  ],
  "pack_parameters": {
    "AKS-SCHED-002": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-SCHED-002": "254907cebd33f0d8f68d0693dc70856de408a17924a17eace4c08e8a15d3b9cb"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-SCHED-002`.

## AKS-START-001: Investigate observed readiness and subsequent demand

Version: 1.0.0; family: reliability; evidence: inventory.

Review a bounded sampled Pod readiness transition within one exact observed container attempt and independently qualified post-readiness measurements.

Pack/query digest: `8450c0d16acdcf131818821a967882bd5656213773902a1349af13724819933d`.

Baseline: Saved samples bracket an observed Pod readiness transition. This is not application startup duration, proof of a first attempt or a safe resource setting.

Guarded: Saved samples bracket an observed Pod readiness transition. Guarded mode does not authorize resource, replica or startup-policy changes.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Obtain approved existing saved lifecycle evidence; do not install an observer, collect Events/logs or infer history from current status.

### Limitations

- Explicitly selected saved-history pack; default analysis retains its original pack selection.
- Bounds describe a sampled Pod readiness proxy, not first-ever startup, continuous history or application initialization latency.
- A zero restart counter and stable sampled runtime digest do not prove historical absence of restarts between samples.
- Usage requires its own exact catalog query, full aligned coverage and a separate post-readiness window inside the sampled attempt; CPU rate lookback must also follow readiness.
- Missing usage does not erase independently valid readiness observations; working set is not full-memory usage and no representative-demand claim is supplied.
- Saved source consistency is not authentication or actual-source compatibility certification. No target, autoscaling suitability or savings is supplied.

### Risks

- Pod readiness may reflect probes or readiness gates rather than application initialization, and sampling can miss transitions or peaks.

### Validation

- Review exact Pod/container identity, original receipts, sample cadence and readiness criterion before interpreting the observed bracket.
- Review independent application startup, SLO, peak, failover and representative usage evidence before considering any change.

### Rollback

- No change is proposed; preserve original settings for rollback of any separately approved experiment.

### Baseline rollback


### Baseline evidence and actions

- Complete aligned saved native lifecycle observations with exact cluster, Namespace, workload, Pod and container-attempt identity and original source clocks
- Fresh scoped current inventory and an observed not-ready to ready transition without changed or missing attempt evidence
- Review the observed readiness bracket and independent measurement gaps with the workload owner; do not choose a resource or replica target.

### Guarded evidence and actions

- Complete aligned saved native lifecycle observations with exact cluster, Namespace, workload, Pod and container-attempt identity and original source clocks
- Fresh scoped current inventory and an observed not-ready to ready transition without changed or missing attempt evidence
- Review the observed readiness bracket; guarded mode does not authorize sizing, scale-to-zero or remediation.

### Query templates (not executable exports)

Inventory-only; no metric endpoint or PromQL required.

### Synthetic baseline configuration example

This selects a pack, not a healthy result or owner approval.

```json
{
  "mode": "baseline",
  "packs": [
    "AKS-START-001"
  ],
  "pack_parameters": {
    "AKS-START-001": {
      "review_ratio": null
    }
  },
  "pack_locks": {
    "AKS-START-001": "8450c0d16acdcf131818821a967882bd5656213773902a1349af13724819933d"
  },
  "thresholds": {
    "minimum_coverage_ratio": 0.85,
    "minimum_observation_days": 30,
    "maximum_evidence_age_hours": 24.0,
    "maximum_metric_step_seconds": 300,
    "minimum_replicas_for_autoscaling_review": 2
  },
  "excluded_namespaces": [
    "kube-system",
    "gatekeeper-system"
  ],
  "environment_risk": {
    "production": "high",
    "nonproduction": "medium"
  },
  "enable_estimated_savings": false
}
```

Inspect: `aks-fleet-advisor catalog show AKS-START-001`.
