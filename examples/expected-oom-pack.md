# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 1
- Blocked findings: 0
- `AKS-MEM-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `68da665807e23f6679cae687137659f900917db09598313a4ba57ab8f57a3012`
- Configuration digest: `fc9a952bc6795f8937ad62a6e437697635566dc084613d8020180aa9299ff28a`
- Pack: `AKS-MEM-001` v1.0.0; digest: `f69012630c4d2a464a20053c932d05b8669666311d1237b3bc198c398c3c4c42`; inventory-only

## Recommendations

### 1. Investigate OOM events for synthetic/api

- **ID:** `AKS-MEM-001-685a32f8cba0`
- **Rule:** `AKS-MEM-001` v1.0.0
- **Severity / confidence:** high / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** reliability-guardrail

OOM events were observed in the assessment window. Investigate memory limits, workload behavior and node pressure before any resource reduction; event counts alone do not identify the cause.

**Evidence**

- **Owner:** synthetic-owner
- `memory_oom_events` = `1` events (synthetic)
- `usage_memory_p95_mib` = `160.0` MiB (synthetic)
- `usage_memory_p99_mib` = `192.0` MiB (synthetic)
- `observed_memory_working_set_peak_mib` = `200.0` MiB (synthetic)
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)

**Prerequisites**

- Have the workload owner correlate OOM timing with memory limits, node pressure, restarts and application SLOs through approved tools.

**Proposed actions**

- Investigate memory reliability before considering rightsizing; no numeric memory reduction is proposed.

**Validation and safety**

- Review startup, peak load and failover memory behavior.
- Validate any separately approved change against OOM, restarts, evictions and owner-declared SLOs.
- Risk: Lowering memory requests or limits can worsen eviction or OOM risk.
- Risk: Working-set samples can miss short peaks and do not prove a safe memory limit or request.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

