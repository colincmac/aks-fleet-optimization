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
- Snapshot digest: `fd47df956c7172ea3983d0a9d7a12b458284501f1d7fc4982884f6dac2e682f6`
- Configuration digest: `66c1072cf2ff21486de10687f30ac2c2cdafaabaaef6e1ee9456eb553902005f`
- Pack: `AKS-AS-002` v2.0.0; digest: `7870961887f0fd1b2ccc7ec3bf8c8153b3d4e1d965a05a8331d21cac904f48f8`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review HPA/VPA resource interaction for synthetic

- **ID:** `AKS-AS-002-428b77c533dc`
- **Rule:** `AKS-AS-002` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-interaction

A current HPA utilization target uses a resource request that a matching VPA may change. Review the shared request denominator; configuration alone does not establish oscillation or SLO impact. Initial mode affects new Pods rather than continuously updating them.

**Evidence**

- **Owner:** synthetic-owner
- `hpa_uid` = `synthetic-hpa-uid` (kubernetes-api)
- `hpa_name` = `synthetic-hpa` (kubernetes-api)
- `vpa_uid` = `synthetic-vpa-uid` (kubernetes-api)
- `vpa_name` = `synthetic-vpa` (kubernetes-api)
- `container` = `api` (kubernetes-api)
- `resource` = `cpu` (kubernetes-api)
- `hpa_metric_type` = `Resource` (kubernetes-api)
- `average_utilization` = `75` percent (kubernetes-api)
- `vpa_update_mode` = `Recreate` (kubernetes-api)

**Prerequisites**

- Have the owner verify the exact current HPA/VPA UIDs, target workload and container resource policy before interpreting the interaction.
- Distinguish utilization percentages from absolute/external signals; KEDA ownership does not remove a generated HPA&\#x27;s request denominator.

**Proposed actions**

- Review controller responsibilities and resource signals with the owner; no controller change or numeric resource reduction is proposed.

**Validation and safety**

- Use approved operational tools to correlate replica/request history with demand, controller behavior and owner-declared SLOs.
- Validate any separately approved controller change in an isolated canary with explicit availability and rollback criteria.
- Risk: Changing requests can change utilization feedback and replica decisions.
- Risk: External or absolute signals do not eliminate per-Pod throughput risk; no conflict finding is not proof of safe rightsizing.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

