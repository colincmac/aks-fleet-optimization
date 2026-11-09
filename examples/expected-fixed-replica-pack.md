# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 0
- Workloads analyzed: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- Snapshot digest: `ed26520adc6a6aa9b88bd03c06d29fb73e0cf53b19b58d1074f8add36d2350f7`
- Configuration digest: `407ee4e8e36cf77309ad59bc07ef6c95e28c7dd20242fd2a58a2ee64c217a7f8`
- Pack: `AKS-AS-001` v2.0.0; digest: `4c38704d699841a3b9cbfb4365989efdc6255353761e9a092f0a3b81ef4ebc20`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review autoscaling for synthetic/synthetic

- **ID:** `AKS-AS-001-cb1dc22295a2`
- **Rule:** `AKS-AS-001` v2.0.0
- **Severity / confidence:** low / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** workload-autoscaling

The workload has multiple replicas but no HPA or KEDA signal in the current snapshot. Confirm whether fixed capacity is an explicit requirement; no numeric replica proposal is made.

**Evidence**

- `replicas` = `2` pods (kubernetes-api)
- `hpa_present` = `False` (kubernetes-api)
- `keda_present` = `False` (kubernetes-api)

**Prerequisites**

- Identify a scaling signal tied to user demand or queue depth.

**Proposed actions**

- Document why fixed replicas are required, or prototype HPA/KEDA.

**Validation and safety**

- Validate scaling behavior with representative load.
- Risk: A poorly selected signal can cause oscillation or SLO regressions.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

