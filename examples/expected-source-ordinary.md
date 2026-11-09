# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `805ce983d4a91be2de470892eec1f05c890dc7f6cc5505520447b046cbf50987`
Profile digest: `c3ca0a0f07f43c3a9350db0335a9653d6fdc035df7d2b9dd86f65aa808e72d18`

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
- Recommendations: 0
- High or critical: 0
- Blocked findings: 1
- Snapshot digest: `b001561c51a7cb7fc6d7145dc936043d0a691daf7c7736cdc5a2a36cdc5628ff`
- Configuration digest: `8a522bc0ecf896daf78f29361b0aef9ac8e75d8cec17adb0b8fcfd1b5c4faf57`
- Pack: `AKS-RQ-002` v2.1.0; digest: `b347d11ef3b28bf5b7e851d3d01cff46b461a8d9ae120e4fdab983513ab66344`; review ratio: 0.4

## Source capabilities

Metric availability is not source attestation or safe-change approval.
- `synthetic` / `AKS-RQ-002` / `baseline`: `available` (`cadvisor-ksm`).
- `synthetic` / `AKS-RQ-002` / `guarded`: `unsupported` (`cadvisor-ksm`).
  - `history.identity`: historical\_identity\_unavailable
  - `history.identity`: identity\_shape\_mismatch

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

No recommendations were generated.
## Blocked findings

These checks are not actionable recommendations.

- `AKS-RQ-002` / `AKS-RQ-002-3d127b89e9ee` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_metric`, `missing_metric_quality`, `unknown_metric_aggregation`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.


## Unresolved baseline measurements

Names identify source series only, not historical workload or Pod identities.
- `synthetic` / `synthetic-pod` / `api`: `cpu_usage` P95 100.0 mCPU; coverage 1.0; issues none observed.
- `synthetic` / `synthetic-pod` / `api`: `cpu_request` P95 1000.0 mCPU; coverage 1.0; issues none observed.
