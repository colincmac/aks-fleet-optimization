# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-AS-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `8ca11fc6b619fbfba4e0f619bd71857833215303aac06df842ced2a03313e1f6`
- Configuration digest: `e709c546d5bd152107084ea4c9ae10a49084715a4e2ddc1208ec17e770848774`
- Pack: `AKS-AS-001` v1.0.0; digest: `fac572d7cd4dd5802b9576c8dd503fa1542af662b53b565a34102f8242ea0ab0`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.

## Recommendations

### 1. Review autoscaling for synthetic/synthetic

- **ID:** `AKS-AS-001-cb1dc22295a2`
- **Rule:** `AKS-AS-001` v1.0.0
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

