# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `dfab8f2279b789772af5c1f22c575a34f5b5b71d942fa4e7ce9d6a23dd159148`
Profile digest: `a074982123dca9b797a4b601e07379ed00c84b5fce9c6ad12beee52eeffd3c7b`

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
- Node pools analyzed: 0
- Workloads analyzed: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- Snapshot digest: `7bd2e21b8c664ae7f4a9519f8770e9b458d4378bf337df38af2b088115832124`
- Configuration digest: `42376cfa1438e23c8c160d5eea427de7612bb0e96b220e25931c0b87939e6d67`
- Pack: `AKS-RQ-002` v2.1.0; digest: `b347d11ef3b28bf5b7e851d3d01cff46b461a8d9ae120e4fdab983513ab66344`; review ratio: 0.4

## Source capabilities

Metric availability is not source attestation or safe-change approval.
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared

## Recommendations

### 1. Review CPU request for synthetic/api

- **ID:** `AKS-RQ-002-3d127b89e9ee`
- **Rule:** `AKS-RQ-002` v2.1.0
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

