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
- `AKS-MEM-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `cfd91f1fd824c6ba109692b262d494574b317a789a6cca8968a1ffa48266ab5d`
- Configuration digest: `fc880de9529f8dd40c89a7ef1693cf48e532a2a362db7a5515e0ebd4bcc11899`
- Pack: `AKS-MEM-002` v1.0.0; digest: `a1c26aa2a90c056b93c48279c9df977c97d9e9d9f26d6a275a8cadd414a1f52a`; inventory-only

## Recommendations

### 1. Review memory safety for synthetic/api

- **ID:** `AKS-MEM-002-f3643c0f7e4f`
- **Rule:** `AKS-MEM-002` v1.0.0
- **Severity / confidence:** info / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** memory-safety-review

Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.

**Evidence**

- **Owner:** synthetic-owner
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)
- `usage_memory_p95_mib` = `160.0` MiB (synthetic)
- `usage_memory_p99_mib` = `192.0` MiB (synthetic)
- `memory_oom_events` = `0` events (synthetic)
- `restart_events` = `0` events (synthetic)
- `memory_observation_basis` = `pod` (normalized-history)
- `memory_membership_digest` = `None` (approved-binding)
- `current_replicas` = `1` pods (current-kubernetes-projection)
- `startup_peak_mib` = `240.0` MiB (owner-reviewed:synthetic-review/memory)
- `failover_peak_mib` = `250.0` MiB (owner-reviewed:synthetic-review/memory)
- `reviewed_eviction_events` = `0` events (owner-reviewed:synthetic-review/memory)
- `minimum_request_mib` = `128.0` MiB (owner-reviewed:synthetic-review/memory)
- `maximum_reduction_ratio` = `0.5` ratio (owner-reviewed:synthetic-review/memory)
- `headroom_factor` = `1.25` ratio (owner-reviewed:synthetic-review/memory)
- `observed_memory_working_set_peak_mib` = `200.0` MiB (synthetic)
- `qos_class` = `Burstable` (kubernetes-api)

**Prerequisites**

- Independently verify owner-reviewed startup, failover and eviction evidence; references and declarations are not source attestation.
- Keep limits and QoS unchanged; any future target needs separate owner approval and effective-Pod validation.

**Proposed actions**

- Review memory safety evidence only; no numeric memory request or limit change is proposed.

**Validation and safety**

- Validate startup, peak load and failover against owner-declared SLOs, OOM, restarts and evictions before approving any change.
- Risk: Working set and sampled peaks can omit relevant memory and bursts.
- Risk: Lower requests can increase node-pressure eviction risk even when the QoS class is unchanged.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

