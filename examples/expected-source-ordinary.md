# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `96da34aa7c0aa991e472e049dad443a84331f1ade855b11c19db74b7b70acf1f`
Profile digest: `bfda4f4ffbe4b704909615ecd90cfa31209b4be89c868a8181049b109ee96cfb`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/agentPools/userpool`: `unsupported-pool-evidence`

## Source Receipts

Eligibility requires a complete, fresh matching receipt; completed scope alone is insufficient.

- `azure-inventory` / `00000000-0000-0000-0000-000000000000`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `kubernetes-metadata` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `prometheus` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`

## Unresolved baseline measurements

Source-series coverage below is the fraction of expected evaluation points returned for each series. The report's metric coverage describes the assessment window, not these individual series. Names do not establish historical Pod or workload identity, so even full series coverage cannot justify a new request.

- `synthetic` / `synthetic-pod` / `api`: `cpu_usage` P95 100.0 mCPU; coverage 1.0; issues none observed.
- `synthetic` / `synthetic-pod` / `api`: `cpu_request` P95 1000.0 mCPU; coverage 1.0; issues none observed.

# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 0
- High or critical: 0
- Blocked findings: 1
- `AKS-RQ-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `e6d4fc65fe2c46653b8f52cf9cf01b0c50020b7d2569c8322f61bcc4d06400ad`
- Configuration digest: `b17ed9d9f17ce017746490ee5894c49b7cd2941ce9f3c78df960290fd45b556e`
- Pack: `AKS-RQ-002` v1.0.0; digest: `d7f0b7902c6400c9b2be49472a75ee4f949ac164dd6db69f80b2b86f0ff5bd56`; review ratio: 0.4

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
