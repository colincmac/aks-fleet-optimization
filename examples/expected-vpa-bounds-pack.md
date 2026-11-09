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
- Snapshot digest: `3bd2ad00035ed4ff081bd9f2da856787ba5aa6edd92086b0857bbfba31f2bf03`
- Configuration digest: `d511842e7652b0fd62288b8cbd4f93f6d488db55fe3d89fbaab8fc09f08f9706`
- Pack: `AKS-AS-007` v2.0.0; digest: `67390629e7dfd5919fecb831653b6b72117b9d8ed88c96f2cc12630a9552b1b2`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review VPA recommendation and policy bounds for synthetic

- **ID:** `AKS-AS-007-e677c293136d`
- **Rule:** `AKS-AS-007` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-investigation

Current VPA status retains resource targets and bounds, not an advisor rightsizing authorization. Metadata freshness does not establish the VPA recommendation&\#x27;s generation time or representative history.

**Evidence**

- **Owner:** synthetic-owner
- `vpa_target_cpu_mcores` = `500.0` mCPU (kubernetes-api)
- `vpa_lower_cpu_mcores` = `200.0` mCPU (kubernetes-api)
- `vpa_upper_cpu_mcores` = `800.0` mCPU (kubernetes-api)
- `vpa_min_allowed_cpu_mcores` = `100.0` mCPU (kubernetes-api)
- `vpa_max_allowed_cpu_mcores` = `1000.0` mCPU (kubernetes-api)
- `vpa_uncapped_cpu_mcores` = `1200.0` mCPU (kubernetes-api)
- `vpa_target_memory_mib` = `512.0` MiB (kubernetes-api)
- `vpa_lower_memory_mib` = `256.0` MiB (kubernetes-api)
- `vpa_upper_memory_mib` = `768.0` MiB (kubernetes-api)
- `vpa_min_allowed_memory_mib` = `128.0` MiB (kubernetes-api)
- `vpa_max_allowed_memory_mib` = `1024.0` MiB (kubernetes-api)
- `vpa_uncapped_memory_mib` = `512.0` MiB (kubernetes-api)
- `container` = `api` (kubernetes-api)
- `vpa_uid` = `synthetic-vpa-uid` (kubernetes-api)
- `vpa_update_mode` = `Recreate` (kubernetes-api)

**Prerequisites**

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.

**Proposed actions**

- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

**Validation and safety**

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.
- Risk: Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

