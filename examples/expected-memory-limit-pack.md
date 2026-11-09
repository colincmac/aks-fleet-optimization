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
- Snapshot digest: `68a0cbb7df3d0f1ac48e0f305bb878c8a424245e44ae2aac5cf5db692a190153`
- Configuration digest: `d69973e4679ffad204315c93c6d4a333a246217c6b48dba5adc33aee78b5a59f`
- Pack: `AKS-MEM-005` v2.0.0; digest: `8a8ea234def4ae4454b4d970ecb34d8a5c6f03e083f5cb81da7dbb588386d040`; inventory-only

## Recommendations

### 1. Review bounded memory limit for synthetic/api

- **ID:** `AKS-MEM-005-ac457d31871f`
- **Rule:** `AKS-MEM-005` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** memory-limit-review

An explicitly opted-in, configuration-bound memory limit proposal uses complete total-memory usage, not working set alone, plus reviewed allocator/cache, startup and failover peaks. Requests, CPU and other containers remain unchanged; owner declarations are not source attestation or approval.

**Evidence**

- **Owner:** synthetic-owner
- **Memory limit:** 1024.0 to 600.0 MiB; requests unchanged
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)
- `total_memory_usage_p99_mib` = `384.0` MiB (synthetic)
- `memory_oom_events` = `0` events (synthetic)
- `restart_events` = `0` events (synthetic)
- `workload_eviction_events` = `0` events (synthetic)
- `minimum_limit_mib` = `512.0` MiB (owner-policy)
- `maximum_reduction_ratio` = `0.5` ratio (owner-policy)
- `headroom_factor` = `1.25` factor (owner-policy)
- `startup_total_peak_mib` = `448.0` MiB (owner-policy)
- `failover_total_peak_mib` = `480.0` MiB (owner-policy)
- `configuration_digest` = `b9204c549ebed60504192c35eb7f1bc614d6b3c8c46d78e350d592c6362d18c4` (owner-policy)
- `review_reference` = `synthetic-total-memory-review` (owner-policy)
- `admission_minimum_limit_mib` = `None` MiB (owner-policy)
- `admission_maximum_limit_mib` = `None` MiB (owner-policy)
- `admission_maximum_limit_request_ratio` = `None` ratio (owner-policy)

**Prerequisites**

- Obtain separate approval for the exact container/configuration, limit and evidence window.
- Independently verify allocator/cache and full-memory scenario evidence; preserve requests and QoS.

**Proposed actions**

- Review this limit-only proposal with the owner; no change is authorized or applied.

**Validation and safety**

- Canary the memory limit only under startup, peak and failover load; leave all requests unchanged.
- Stop promotion on OOM, restarts, evictions or owner SLO regression.
- Risk: Lower hard limits can cause OOM despite unchanged requests and Burstable QoS.
- Risk: Sampled total-memory peaks are not proof that all future peaks were observed.

**Rollback**

- Restore the original 1024.0 MiB limit through customer delivery tooling on regression; the advisor never rolls back.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

