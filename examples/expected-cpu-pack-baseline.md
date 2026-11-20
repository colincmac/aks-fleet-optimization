# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `2e3c778296043923491c3ec25bac20c4801bec2effd2fc01730971135bf83f10`
Profile digest: `46d88885f6c5c49a4fdd46fc3b290037de583f1901eb1c17cb3298384616a974`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/agentPools/userpool`: `unsupported-pool-evidence`

## Source Receipts

Eligibility requires a complete, fresh matching receipt; completed scope alone is insufficient.

- `azure-inventory` / `00000000-0000-0000-0000-000000000000`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `kubernetes-metadata` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `prometheus` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`

# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-RQ-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `1166491b68c9866f238c9e476996e02c56d55c8eef323b70347a1f6692a74ef7`
- Configuration digest: `3366b0de7b64cefcee412547f3517b74a6891a819fa7cdb5be70f7510905cbb1`
- Pack: `AKS-RQ-002` v1.0.0; digest: `d7f0b7902c6400c9b2be49472a75ee4f949ac164dd6db69f80b2b86f0ff5bd56`; review ratio: 0.4

## Source capabilities

Metric availability is not source attestation or safe-change approval.
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared

## Recommendations

### 1. Review CPU request for synthetic/api

- **ID:** `AKS-RQ-002-3d127b89e9ee`
- **Rule:** `AKS-RQ-002` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** cpu-request-investigation

Observed P95 CPU usage is below the configured fraction of the current admitted request. This is an investigation, not a safe reduction target; owner policy, peaks and reliability must be reviewed independently.

**Evidence**

- **Owner:** synthetic-owner
- `cpu_p95_to_request_ratio` = `0.1` ratio (synthetic)
- `cpu_observation_basis` = `pod` (normalized-evidence)

**Prerequisites**

- Confirm the metric window contains peak and business-critical periods.
- Review P99 usage, throttling, startup and failover behavior.

**Proposed actions**

- Review observed usage, owner requirements and missing guarded evidence.

**Validation and safety**

- Run VPA in Off mode and compare recommendations.
- Canary an independently approved request change and verify SLOs under load.
- Risk: Historical usage might not represent future peaks.
- Risk: Lower requests can change placement and noisy-neighbor behavior.

**Rollback**

- No numeric change is proposed; do not apply a baseline investigation.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

