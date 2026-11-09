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
- Snapshot digest: `0993873f8e335dfd530af09e13b6e53e7d1c4ded2ce8276d5950e16b25761a44`
- Configuration digest: `084054fc2370b0e7a7a0e08dbf26c27e06fe3b444ba7a5cfea84a3af240e1eff`
- Pack: `AKS-AS-005` v2.0.0; digest: `1919c70059e05df837cdd842d72fba8d8464e2b8f6d39c25dd9f3f6967619d26`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review bounded HPA minimum replicas for synthetic

- **ID:** `AKS-AS-005-06b3c86d862e`
- **Rule:** `AKS-AS-005` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-replica-floor

An explicitly opted-in owner policy and complete stable HPA/workload availability history permit a bounded minimum-replica proposal. Owner review declarations are not source attestation or change approval. The HPA maximum, metric targets and resource requests remain unchanged; no savings or automatic remediation is implied.

**Evidence**

- **Owner:** synthetic-owner
- **HPA minimum replicas:** 2 to 1 pods; maximum and resource requests unchanged
- `hpa_uid` = `synthetic-hpa-uid` (kubernetes-api)
- `bound_state` = `floor` (synthetic)
- `minimum_replicas` = `2` pods (synthetic)
- `maximum_replicas` = `5` pods (synthetic)
- `hpa_desired_replicas_min` = `2` pods (synthetic)
- `hpa_desired_replicas_max` = `2` pods (synthetic)
- `hpa_current_replicas_min` = `2` pods (synthetic)
- `hpa_current_replicas_max` = `2` pods (synthetic)
- `history_reference` = `synthetic-approved-hpa-history/reference` (approved-binding)
- `replica_configuration_digest` = `7a8196b62d7559dabc9eb66ea8f19901f2d9378a409101d1a08624758e45cbbf` (current-configuration)
- `tested_replicas` = `1` pods (owner-policy)
- `minimum_available_replicas` = `1` pods (owner-policy)
- `failover_reserve_replicas` = `0` pods (owner-policy)
- `maximum_unavailable_replicas` = `0` pods (owner-policy)
- `maximum_reduction_ratio` = `0.5` ratio (owner-policy)
- `owner_evidence_reference` = `synthetic-owner-reviewed-replica-canary` (owner-policy)
- `slo_reference` = `synthetic-policy/slo` (owner-policy)
- `reviewed_configuration_digest` = `7a8196b62d7559dabc9eb66ea8f19901f2d9378a409101d1a08624758e45cbbf` (owner-policy)
- `reviewed_oom_events` = `0` events (owner-policy)
- `reviewed_restart_events` = `0` events (owner-policy)
- `reviewed_eviction_events` = `0` events (owner-policy)

**Prerequisites**

- Obtain separate owner approval bound to this exact workload/HPA UID, proposal, configuration and observation window.
- Reconfirm the reviewed load test, throughput, startup, zonal failure, failover reserve and disruption allowance for the proposed floor.

**Proposed actions**

- Review the structured HPA minimum proposal with the owner; this report does not approve or apply a change.

**Validation and safety**

- Canary only the HPA minimum; leave maximum, signals and CPU/memory requests unchanged. Verify availability and SLOs under peak load, startup and declared zone/failover scenarios.
- Stop promotion on pending/unavailable Pods, elevated throttling, OOM/restarts, scale-up latency or throughput/SLO regression.
- Risk: Lower warm capacity can delay scale-up or increase per-Pod load.
- Risk: PDB matching, stateful quorum, KEDA-managed floors, changing histories and unsupported scheduling constraints are not supported proposals.

**Rollback**

- Restore the original HPA minimum of 2 replicas through customer-owned delivery tooling on any guardrail regression; the advisor never changes controllers or performs rollback.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

