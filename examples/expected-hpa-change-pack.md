# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 0
- Workloads analyzed: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- Snapshot digest: `403e6974dc0138a964a0a9e859c12d1799d372b567045a01cc4db1fb6d326f32`
- Configuration digest: `9a76edb2d826f08a845adb880c0b7885600a80a0d049b244d241526de3aae33f`
- Pack: `AKS-AS-006` v2.0.0; digest: `d6af639b6f013410e0005f8d70e1650671d646500c9839fc0ccd42dba2d95d02`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review changed HPA bounds and replica context for synthetic

- **ID:** `AKS-AS-006-59f970c25453`
- **Rule:** `AKS-AS-006` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-investigation

Historical or current HPA bounds/count context changed. These sampled extrema do not establish oscillation, scaling lag, unmet demand or SLO impact. Reassess controller identity and availability before proposing a change.

**Evidence**

- **Owner:** synthetic-owner
- `hpa_current_replicas_min` = `1` pods (synthetic)
- `hpa_current_replicas_max` = `1` pods (synthetic)
- `hpa_desired_replicas_min` = `1` pods (synthetic)
- `hpa_desired_replicas_max` = `1` pods (synthetic)
- `hpa_max_replicas_min` = `2` pods (synthetic)
- `hpa_max_replicas_max` = `5` pods (synthetic)
- `hpa_min_replicas_min` = `1` pods (synthetic)
- `hpa_min_replicas_max` = `1` pods (synthetic)
- `hpa_uid` = `synthetic-hpa-uid` (synthetic)
- `observed_controller_change` = `changing_hpa_bounds` (aligned-history)

**Prerequisites**

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.

**Proposed actions**

- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

**Validation and safety**

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.
- Risk: Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

