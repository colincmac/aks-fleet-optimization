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
- `AKS-MEM-003` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `c305016f25cc2625c59c8a2007c46a9a9634e7d2ebc931015a7831e3b6739931`
- Configuration digest: `2b9c7dc77a95dba67a6d9a5d179a092950440074c74452a4b4bef095f58946ae`
- Pack: `AKS-MEM-003` v1.0.0; digest: `24ac10817abfeb3f6ad2641646310ada00dd1c61113f60dd14a3985f9560d369`; inventory-only

## Recommendations

### 1. Validate memory request candidate for synthetic/api

- **ID:** `AKS-MEM-003-1c2d8743035d`
- **Rule:** `AKS-MEM-003` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** memory-efficiency

The upstream memory request candidate is not below the accelerator safety floor and passed the required admission, QoS, reliability and owner-policy gates.

**Evidence**

- **Owner:** synthetic-owner
- **Memory request:** 512.0 to 313.0 MiB per replica
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)
- `usage_memory_p95_mib` = `160.0` MiB (synthetic)
- `usage_memory_p99_mib` = `192.0` MiB (synthetic)
- `memory_oom_events` = `0` events (synthetic)
- `restart_events` = `0` events (synthetic)
- `workload_eviction_events` = `0` events (synthetic)
- `memory_observation_basis` = `replica-envelope` (normalized-history)
- `memory_membership_digest` = `317b65a425a883954b66399ffec654884cf24b4ce3c9fa4b6447247cc9d5b322` (approved-binding)
- `current_replicas` = `2` pods (current-kubernetes-projection)
- `startup_peak_mib` = `240.0` MiB (owner-reviewed:synthetic-review/memory)
- `failover_peak_mib` = `250.0` MiB (owner-reviewed:synthetic-review/memory)
- `reviewed_eviction_events` = `0` events (owner-reviewed:synthetic-review/memory)
- `minimum_request_mib` = `128.0` MiB (owner-reviewed:synthetic-review/memory)
- `maximum_reduction_ratio` = `0.5` ratio (owner-reviewed:synthetic-review/memory)
- `headroom_factor` = `1.25` ratio (owner-reviewed:synthetic-review/memory)
- `observed_memory_working_set_peak_mib` = `200.0` MiB (synthetic)
- `qos_class` = `Burstable` (kubernetes-api)
- `allow_request_reduction` = `True` (owner-policy)

**Prerequisites**

- Obtain separate owner approval for this specific request-only change; enabling proposals is not approval to apply them.
- Independently verify the reviewed scenario/eviction evidence, supported direct or approved-envelope history, absent overhead and current admitted settings.
- Keep CPU requests, all limits and other containers unchanged; do not combine independent CPU and memory proposals in one canary.

**Proposed actions**

- Review the validated upstream 313.0 MiB candidate for this container only; keep limits unchanged and obtain owner approval.

**Validation and safety**

- Canary only the approved memory request under startup, peak load and failover; confirm the limit and QoS remain unchanged.
- Compare OOM, restarts, evictions, placement and owner-declared SLOs with the pre-change baseline before promotion.
- Risk: Working-set samples can omit relevant memory and short peaks.
- Risk: Lower requests reduce eviction protection and can increase node pressure or change placement despite unchanged Burstable QoS.

**Rollback**

- If OOM, restarts, evictions or owner-declared SLOs regress, stop promotion and restore the original 512.0 MiB memory request through the owning delivery pipeline; keep all other settings unchanged.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

