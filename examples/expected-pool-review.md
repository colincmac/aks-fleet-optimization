# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 1
- Workloads analyzed: 0
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- Snapshot digest: `c5202dbbdeb30a5feb6873b82c0bc3c5edb507bcc4591791d7eabaea70208d10`
- Configuration digest: `abda5b277051f655ee50b28f2f81c9944716e9c91630076c9d4b317a985507a4`
- Pack: `AKS-NP-001` v2.0.0; digest: `bb6d38a357d12431b92179a4fcf382f9ade0f3a262c776c402cb2533c15ee747`; review ratio: 0.2

## Source capabilities

Metric availability is not source attestation or safe-change approval.
- `synthetic` / `AKS-NP-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-NP-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared

## Recommendations

### 1. Review low-utilization node pool userpool

- **ID:** `AKS-NP-001-ec1a7b48d9eb`
- **Rule:** `AKS-NP-001` v2.0.0
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

