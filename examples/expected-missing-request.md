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
- `AKS-RQ-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `0537a18e899d8602068e449c570f2548b9ae17c7b155205be2efa1e204adc978`
- Configuration digest: `02852cd8049bcedfcc1f26132ad3621282e6dabba44a38e837e589d9c3c0c774`
- Pack: `AKS-RQ-001` v1.0.0; digest: `64dbc1e4751804bd9f762d1bb37c2dd90d7a1b9884d138034c326136cfaa2e16`; inventory-only

## Recommendations

### 1. Review missing CPU request for synthetic/api

- **ID:** `AKS-RQ-001-a112364a0e6b`
- **Rule:** `AKS-RQ-001` v1.0.0
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

