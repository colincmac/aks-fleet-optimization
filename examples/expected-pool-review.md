# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 1
- Snapshot vertical-workload records: 0
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-NP-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `eddc8615c49aa17b0579e0248a817cf9f39a8c3ffab8a00c595cd295e43dcac3`
- Configuration digest: `d07325ad83ad8944b53d70839d8a3c9b8b06d3133105837049742cccd89d4b91`
- Pack: `AKS-NP-001` v1.0.0; digest: `f9209222647295f9d7c0db4518fdd6170f77f2f39567ff4ab402d345e1abebe8`; review ratio: 0.2

## Source capabilities

Metric availability is not source attestation or safe-change approval.
- `synthetic` / `AKS-NP-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-NP-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared

## Recommendations

### 1. Review low-utilization node pool userpool

- **ID:** `AKS-NP-001-ec1a7b48d9eb`
- **Rule:** `AKS-NP-001` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `-` / `-`
- **Category:** node-pool-efficiency

P95 CPU utilization is below the configured review threshold. This is not proof a node can be removed; validate resilience and scheduling constraints before a separately approved change.

**Evidence**

- `node_pool_cpu_p95_utilization` = `0.0571` ratio (synthetic)
- `node_count` = `1` nodes (inventory)

**Prerequisites**

- Confirm pod disruption budgets and zonal resilience.
- Check pending pods, daemonset overhead and scale-up latency.

**Proposed actions**

- Review minimum node count and autoscaler profile.
- Investigate existing placement and resilience requirements.

**Validation and safety**

- Load test any separately proposed minimum capacity.
- Compare P95/P99 saturation, pending pods and SLOs before and after.
- Risk: Reducing warm capacity can increase scale-up latency.
- Risk: Average or P95 utilization alone can hide short bursts.

**Rollback**

- No node target is proposed; revert a separately approved capacity change through the owning delivery pipeline on regression.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

