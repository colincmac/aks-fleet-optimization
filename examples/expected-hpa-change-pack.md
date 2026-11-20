# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-AS-006` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `f1bace45c23ca1beec5e654398b6a1daf786fefaf2fd7b79b2c03a14a75e113f`
- Configuration digest: `794f1be7a1d4edbfe956c8e0c4b019a19cc78e5e94ee49950e9d666ef7de673d`
- Pack: `AKS-AS-006` v1.0.0; digest: `abf0c1f18ad7f1856d2a0dce4c76be3d0b07bc87dc620c1bc799658a00f874c0`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review changed HPA bounds and replica context for synthetic

- **ID:** `AKS-AS-006-59f970c25453`
- **Rule:** `AKS-AS-006` v1.0.0
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

