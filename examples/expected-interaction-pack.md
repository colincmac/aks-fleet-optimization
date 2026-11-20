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
- `AKS-AS-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `9cbadf1bbc04ca48e3811119ce6a7fdc32f3de6817b07a5396bc930522641453`
- Configuration digest: `3b0684fb82f3a436dd87ed64b7279582e2bcfcb608947301bc502aeee8a7bec0`
- Pack: `AKS-AS-002` v1.0.0; digest: `bc2fc328dc8244e004bdcf6b452344a87948fb232c5021c63c1245f6ae03f376`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.

## Recommendations

### 1. Review HPA/VPA resource interaction for synthetic

- **ID:** `AKS-AS-002-428b77c533dc`
- **Rule:** `AKS-AS-002` v1.0.0
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

