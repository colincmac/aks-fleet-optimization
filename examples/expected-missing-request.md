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
- Snapshot digest: `2392cffd88d9add0d40556428d7193211200a8d3b62796f5f2a123a6f3be0094`
- Configuration digest: `1a6a6b428e7ebac963f90e86f9ef3c074d94863fe1204a439ff977c864052b9d`
- Pack: `AKS-RQ-001` v2.0.0; digest: `5ad78cbaccf1bb5a22dcce6a4cf28baaf58e89134f76369715b27b64f8944823`; inventory-only

## Recommendations

### 1. Review missing CPU request for synthetic/api

- **ID:** `AKS-RQ-001-a112364a0e6b`
- **Rule:** `AKS-RQ-001` v2.0.0
- **Severity / confidence:** high / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** resource-governance

No positive CPU request was explicitly observed. Requests support reliable scheduling, rightsizing and cost attribution. This is an investigation, not a numeric target.

**Evidence**

- `request_cpu_mcores` = `None` mCPU (kubernetes-api)

**Prerequisites**

- Collect representative CPU usage before selecting a value.

**Proposed actions**

- Use VPA recommendation mode or historical percentiles to propose a request.

**Validation and safety**

- Load test and monitor throttling and latency.
- Risk: An arbitrarily low request can cause contention or poor placement.

**Rollback**

- No numeric change is proposed; restore any separately approved change through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

