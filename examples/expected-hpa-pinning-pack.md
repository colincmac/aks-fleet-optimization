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
- `AKS-AS-003` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `115923b75fc30c95553cd7a9133cf1587b69aa25af3bda68d6d518e64ddc658d`
- Configuration digest: `4e499c09ff9b030ebfbe7abc456dec9ea73d39d24a487fe9a0d15c6f9476662e`
- Pack: `AKS-AS-003` v1.0.0; digest: `129fc1650bd91b20c8a2415cd824b56913c06881d2e5db041f5e9298be088592`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review HPA floor history for synthetic

- **ID:** `AKS-AS-003-d511905ba381`
- **Rule:** `AKS-AS-003` v1.0.0
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

