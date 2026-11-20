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
- `AKS-AS-004` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `40680c311325d39dfcb756d30b9fd1b6b00358708993a83c40c24a067d4e2153`
- Configuration digest: `c77fc0ff8c9656a6de9b55254ff5c7d3c73a9c0979e01e6e5a4a5ba8a7f8ad83`
- Pack: `AKS-AS-004` v1.0.0; digest: `de32fe82374db00e8ee980be1abc2246ba947c9fcefd27e137a6dfb96518e14d`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.

## Recommendations

### 1. Review controller ownership and activation for synthetic

- **ID:** `AKS-AS-004-46a6f7c0c152`
- **Rule:** `AKS-AS-004` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-investigation

KEDA owns the observed generated HPA; these are one scaling chain, not two competing HPAs. Trigger types and metric types are current configuration, not proof of demand or activation. A declared zero minimum is only a scale-to-zero review candidate; verify activation, cold-start, state and availability requirements.

**Evidence**

- **Owner:** synthetic-owner
- `keda_uid` = `synthetic-keda-uid` (kubernetes-api)
- `generated_hpa_uid` = `synthetic-hpa-uid` (kubernetes-api)
- `keda_minimum_replicas` = `0` pods (kubernetes-api)
- `keda_maximum_replicas` = `5` pods (kubernetes-api)
- `scale_to_zero` = `True` (kubernetes-api)
- `polling_interval` = `30` seconds (kubernetes-api)
- `cooldown_period` = `300` seconds (kubernetes-api)
- `trigger_type` = `prometheus` (kubernetes-api)
- `trigger_metric_type` = `AverageValue` (kubernetes-api)
- `generated_hpa_metric_type` = `Resource` (kubernetes-api)
- `generated_hpa_target_type` = `Utilization` (kubernetes-api)

**Prerequisites**

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.
- For KEDA, verify activation, trigger authentication and generated HPA behavior in operator tools; trigger values and credentials are never collected by the advisor.

**Proposed actions**

- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

**Validation and safety**

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.
- Risk: Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.
- Risk: Scale-to-zero can violate cold-start, state, quorum, throughput or availability requirements.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

