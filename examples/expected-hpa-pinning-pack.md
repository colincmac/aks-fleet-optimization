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
- Snapshot digest: `1e71f8ca7598e41c50ddd248e9e2b154b43d9fb9cd430531606fd8e5646b07ca`
- Configuration digest: `8beab3c0727a5e0070a9514e19adc402923c667d1b60cecaeb3746790e3219f3`
- Pack: `AKS-AS-003` v2.0.0; digest: `b1fde20fccf7620b29df2056348ac4d95c4a6131ae814b0b1cf00386165a5480`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review HPA floor history for synthetic

- **ID:** `AKS-AS-003-d511905ba381`
- **Rule:** `AKS-AS-003` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-replica-bound

Requested and current HPA replica counts remained at a configured bound at every collected evaluation point in the assessment window. This does not prove continuous pinning between samples, low demand, unmet demand, saturation or SLO impact.

**Evidence**

- **Owner:** synthetic-owner
- `hpa_uid` = `synthetic-hpa-uid` (kubernetes-api)
- `bound_state` = `floor` (synthetic)
- `minimum_replicas` = `1` pods (synthetic)
- `maximum_replicas` = `5` pods (synthetic)
- `hpa_desired_replicas_min` = `1` pods (synthetic)
- `hpa_desired_replicas_max` = `1` pods (synthetic)
- `hpa_current_replicas_min` = `1` pods (synthetic)
- `hpa_current_replicas_max` = `1` pods (synthetic)
- `history_reference` = `synthetic-approved-hpa-history/reference` (approved-binding)
- `replica_configuration_digest` = `d32a4fbc345b32c204917935553dae2e4b0ea5c8cadeef3ecddbfc437a3d45dd` (current-configuration)

**Prerequisites**

- Have the owner verify historical HPA/workload UID enrichment and bound semantics; references are declarations, not source attestation.
- Review availability, failover, warm capacity, scaling signals and controller health before interpreting any minimum or maximum.

**Proposed actions**

- Investigate whether the observed replica bound remains appropriate with the owner; no replica target or controller change is proposed.

**Validation and safety**

- Correlate approved replica, demand, readiness and controller evidence with owner-declared SLOs before considering a separate change.
- Validate any separately approved change under startup, peak load and failover with explicit availability and rollback criteria.
- Risk: A floor can be intentional resilience capacity, not waste.
- Risk: A ceiling alone does not establish unsatisfied demand or saturation.
- Risk: Evaluation-point coverage can miss behavior between samples.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

