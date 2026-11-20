# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 1
- Blocked findings: 0
- `AKS-RQ-003` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `acb8ffc83e3c4163fc206957e8ae174c266e09684a8469d30a87869f257708eb`
- Configuration digest: `85f4fdf79a669e114e452da9fe11d92cb76f2e35c256885036cbc0801251b5b7`
- Pack: `AKS-RQ-003` v1.0.0; digest: `f4f9e64dabd50569063c8b3264932bc5c0c9f0855032f91347377ef55be1cc3a`; review ratio: 0.9

## Recommendations

### 1. Review CPU request risk for synthetic/api

- **ID:** `AKS-RQ-003-add67f939342`
- **Rule:** `AKS-RQ-003` v1.0.0
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

