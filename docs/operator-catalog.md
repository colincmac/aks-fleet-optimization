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

Version: 2.0.0; family: autoscaler; evidence: inventory.

Investigate current fixed replicas with observed absence of HPA and KEDA.

Pack/query digest: `4c38704d699841a3b9cbfb4365989efdc6255353761e9a092f0a3b81ef4ebc20`.

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
    "AKS-AS-001": "4c38704d699841a3b9cbfb4365989efdc6255353761e9a092f0a3b81ef4ebc20"
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

Version: 2.0.0; family: autoscaler; evidence: inventory.

Review utilization request-denominator overlap on the exact current container and resource, with exact-container VPA policy taking precedence over wildcard policy.

Pack/query digest: `7870961887f0fd1b2ccc7ec3bf8c8153b3d4e1d965a05a8331d21cac904f48f8`.

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
    "AKS-AS-002": "7870961887f0fd1b2ccc7ec3bf8c8153b3d4e1d965a05a8331d21cac904f48f8"
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

Version: 2.0.0; family: autoscaler; evidence: metrics.

Investigate sampled floor, ceiling or fixed counts using four full-grid controller-UID-bound gauges, not today's bounds extrapolated into history.

Pack/query digest: `b1fde20fccf7620b29df2056348ac4d95c4a6131ae814b0b1cf00386165a5480`.

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
    "AKS-AS-003": "b1fde20fccf7620b29df2056348ac4d95c4a6131ae814b0b1cf00386165a5480"
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

Version: 2.0.0; family: autoscaler; evidence: inventory.

Investigate current KEDA ownership, generated HPA chains, activation and multiple controllers without interpreting trigger values or collecting authentication.

Pack/query digest: `d68e0d2a9aee2f6056cae5b11759a856819df8cbc354d9bf5c2b36114865cacd`.

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
    "AKS-AS-004": "d68e0d2a9aee2f6056cae5b11759a856819df8cbc354d9bf5c2b36114865cacd"
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

Version: 2.0.0; family: autoscaler; evidence: metrics.

A separately default-off positive-only HPA minimum proposal preserves maximum, signals and resources under configuration-bound owner and availability review.

Pack/query digest: `1919c70059e05df837cdd842d72fba8d8464e2b8f6d39c25dd9f3f6967619d26`.

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
    "AKS-AS-005": "1919c70059e05df837cdd842d72fba8d8464e2b8f6d39c25dd9f3f6967619d26"
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

Version: 2.0.0; family: autoscaler; evidence: metrics.

Investigate changing sampled controller bounds/count context independently of the stable-pinning and floor-proposal gates.

Pack/query digest: `d6af639b6f013410e0005f8d70e1650671d646500c9839fc0ccd42dba2d95d02`.

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
    "AKS-AS-006": "d6af639b6f013410e0005f8d70e1650671d646500c9839fc0ccd42dba2d95d02"
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

Version: 2.0.0; family: autoscaler; evidence: inventory.

Inspect current VPA resource targets, lower/upper/uncapped bounds and exact-container policy precedence without deriving advisor resource proposals.

Pack/query digest: `67390629e7dfd5919fecb831653b6b72117b9d8ed88c96f2cc12630a9552b1b2`.

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
    "AKS-AS-007": "67390629e7dfd5919fecb831653b6b72117b9d8ed88c96f2cc12630a9552b1b2"
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

Version: 2.0.0; family: memory; evidence: metrics.

OOM events were observed in the assessment window. Investigate memory limits, workload behavior and node pressure before any resource reduction; event counts alone do not identify the cause.

Pack/query digest: `5aa9bd2eab3c67ac864d9665236a55084974dfbf400767d28a6412b5c314aaff`.

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
    "AKS-MEM-001": "5aa9bd2eab3c67ac864d9665236a55084974dfbf400767d28a6412b5c314aaff"
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

Version: 2.0.0; family: memory; evidence: metrics.

Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.

Pack/query digest: `a8f370ee0397ffc2b5a70ef5a767dab1065c57a74c4f9c8d7a23a8b9444b0b96`.

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
    "AKS-MEM-002": "a8f370ee0397ffc2b5a70ef5a767dab1065c57a74c4f9c8d7a23a8b9444b0b96"
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

## AKS-MEM-003: Review lower memory request

Version: 2.0.0; family: memory; evidence: metrics.

A request-only memory proposal obeys the declared owner minimum, maximum reduction and peak/startup/failover headroom. It preserves the observed memory limit and Burstable QoS; it does not prove node removability, financial savings or change approval.

Pack/query digest: `4f9e63453b810bc0c85a40469d982fcedbc0861cf7b821a3b7d41e528b09d8d1`.

Baseline: A request-only memory proposal obeys the declared owner minimum, maximum reduction and peak/startup/failover headroom. It preserves the observed memory limit and Burstable QoS; it does not prove node removability, financial savings or change approval.

Guarded: A request-only memory proposal obeys the declared owner minimum, maximum reduction and peak/startup/failover headroom. It preserves the observed memory limit and Burstable QoS; it does not prove node removability, financial savings or change approval.

### Review parameters

No pack ratio controls. Proposal bounds belong to owner policy.

### Prerequisites

- Obtain separate owner approval for this specific request-only change; enabling proposals is not approval to apply them.
- Independently verify the reviewed scenario/eviction evidence, supported direct or approved-envelope history, absent overhead and current admitted settings.
- Keep CPU requests, all limits and other containers unchanged; do not combine independent CPU and memory proposals in one canary.

### Limitations

- A request-only memory proposal obeys the declared owner minimum, maximum reduction and peak/startup/failover headroom. It preserves the observed memory limit and Burstable QoS; it does not prove node removability, financial savings or change approval.
- References/digests are integrity declarations, not source attestation or approval.

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
- Existing QoS, admission, controller, full-grid and reliability guards
- Propose \_\_proposed\_request\_mib\_\_ MiB memory request per replica for this container only; keep limits unchanged and obtain owner approval.

### Guarded evidence and actions

- Complete fresh exact-scoped sources and aligned metric quality
- Exact historical identities and complete required history; missing is not zero
- Independent owner-reviewed window/SLO/disruption/scenario bounds
- Existing QoS, admission, controller, full-grid and reliability guards
- Propose \_\_proposed\_request\_mib\_\_ MiB memory request per replica for this container only; keep limits unchanged and obtain owner approval.

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
    "AKS-MEM-003": "4f9e63453b810bc0c85a40469d982fcedbc0861cf7b821a3b7d41e528b09d8d1"
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

Version: 2.0.0; family: memory; evidence: inventory.

Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.

Pack/query digest: `06a6565d5c06f7b7d7a38848f37f9931236d18375752fbfdd03567718e899155`.

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
    "AKS-MEM-004": "06a6565d5c06f7b7d7a38848f37f9931236d18375752fbfdd03567718e899155"
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

Version: 2.0.0; family: memory; evidence: metrics.

An explicitly opted-in, configuration-bound memory limit proposal uses complete total-memory usage, not working set alone, plus reviewed allocator/cache, startup and failover peaks. Requests, CPU and other containers remain unchanged; owner declarations are not source attestation or approval.

Pack/query digest: `8a8ea234def4ae4454b4d970ecb34d8a5c6f03e083f5cb81da7dbb588386d040`.

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
    "AKS-MEM-005": "8a8ea234def4ae4454b4d970ecb34d8a5c6f03e083f5cb81da7dbb588386d040"
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

Version: 2.0.0; family: node-pool; evidence: metrics.

Investigate qualified historical pool usage while preserving complete membership, aligned sums and constant capacity.

Pack/query digest: `bb6d38a357d12431b92179a4fcf382f9ade0f3a262c776c402cb2533c15ee747`.

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
    "AKS-NP-001": "bb6d38a357d12431b92179a4fcf382f9ade0f3a262c776c402cb2533c15ee747"
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

## AKS-REL-001: Investigate restarts

Version: 2.0.0; family: reliability; evidence: metrics.

Container restarts were observed in the assessment window. Correlate them with owner-declared SLOs and approved operational evidence; the count alone does not establish memory pressure, an OOM cause or an application failure.

Pack/query digest: `d15a8c1b06e1f3a28c28023b5db85ea5872174b0a399f6ec73e76c8509909d5e`.

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
    "AKS-REL-001": "d15a8c1b06e1f3a28c28023b5db85ea5872174b0a399f6ec73e76c8509909d5e"
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

Version: 2.0.0; family: reliability; evidence: inventory.

Current UID-bound last-termination status reports a reason and exit code. It does not establish the cause of all restarts, historical frequency, node pressure or SLO impact; exit code 137 alone is not proof of OOM.

Pack/query digest: `929ec47b9f67b3bf82e3d40bc375e220a7e9a9e66010e9fbe278899cb4ea589f`.

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
    "AKS-REL-002": "929ec47b9f67b3bf82e3d40bc375e220a7e9a9e66010e9fbe278899cb4ea589f"
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

Version: 2.0.0; family: reliability; evidence: metrics.

Identity-bound workload eviction counts were observed over the declared window. They are reported once per workload, not multiplied by containers; counts do not establish node-pressure causes or SLO impact.

Pack/query digest: `26ae8db918931762d9b10ef12206ef979401239ca10bdb59f915682b35c347ce`.

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
    "AKS-REL-003": "26ae8db918931762d9b10ef12206ef979401239ca10bdb59f915682b35c347ce"
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

Version: 2.0.0; family: cpu; evidence: inventory.

Investigate an explicitly observed absent or zero admitted CPU request without choosing a target.

Pack/query digest: `5ad78cbaccf1bb5a22dcce6a4cf28baaf58e89134f76369715b27b64f8944823`.

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
    "AKS-RQ-001": "5ad78cbaccf1bb5a22dcce6a4cf28baaf58e89134f76369715b27b64f8944823"
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

Version: 2.1.0; family: cpu; evidence: metrics.

Compare observed CPU usage with the admitted request, then independently evaluate a policy-bounded reduction.

Pack/query digest: `b347d11ef3b28bf5b7e851d3d01cff46b461a8d9ae120e4fdab983513ab66344`.

Baseline: Observed P95 CPU usage is below the configured fraction of the current admitted request. This is an investigation, not a safe reduction target; owner policy, peaks and reliability must be reviewed independently.

Guarded: Historical CPU usage is below the request. The proposal respects observed peaks, declared headroom and owner policy; validate it through a separately approved canary.

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

- All baseline evidence, qualified P99/observed peaks, throttling and OOM history
- Known compatible autoscalers and no observed OOM or workload eviction veto
- Owner-reviewed window, disruption policy, environment, minimum, headroom and reduction bounds
- Open a review PR with the proposed request and rollback criteria.

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
    "AKS-RQ-002": "b347d11ef3b28bf5b7e851d3d01cff46b461a8d9ae120e4fdab983513ab66344"
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

Version: 2.0.0; family: cpu; evidence: metrics.

Correlate high observed usage relative to an admitted request with throttling, limits and SLOs; do not infer saturation.

Pack/query digest: `3686fb298e7a8ccb1e776d818e87608eae7630b790e07f2b980cd30d139724be`.

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
    "AKS-RQ-003": "3686fb298e7a8ccb1e776d818e87608eae7630b790e07f2b980cd30d139724be"
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
