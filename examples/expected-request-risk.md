# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 0
- Workloads analyzed: 1
- Recommendations: 1
- High or critical: 1
- Blocked findings: 0
- Snapshot digest: `ae4f12c7950216742d24a2210c31c6134751192f5bfbdda89f77eed764e417a2`
- Configuration digest: `730dadcc0683aaa525d11822d9009844a365dbca4c160368533a852a33a8d0b3`
- Pack: `AKS-RQ-003` v2.0.0; digest: `3686fb298e7a8ccb1e776d818e87608eae7630b790e07f2b980cd30d139724be`; review ratio: 0.9

## Recommendations

### 1. Review CPU request risk for synthetic/api

- **ID:** `AKS-RQ-003-add67f939342`
- **Rule:** `AKS-RQ-003` v2.0.0
- **Severity / confidence:** high / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** reliability-guardrail

P95 CPU usage is close to or above the request. Requests are not CPU limits; this ratio alone does not establish saturation. Review throttling, limits and SLOs before denser placement.

**Evidence**

- `cpu_p95_to_request_ratio` = `1.1` ratio (synthetic)
- `cpu_throttled_ratio` = `0.001` ratio (synthetic)

**Prerequisites**

- Correlate saturation with latency and error SLOs.

**Proposed actions**

- Review CPU request/limit policy and horizontal scaling signal.

**Validation and safety**

- Load test at peak concurrency and failover conditions.
- Risk: Densification can amplify contention.

**Rollback**

- No target is proposed; revert a separately approved change through its owning delivery pipeline if guardrails regress.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

