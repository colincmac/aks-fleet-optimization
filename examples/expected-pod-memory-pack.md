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
- `AKS-MEM-004` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `17c8bf12dac87de326b4b9916e9ea7a82cc02aee9dc300dee6490542bef9250e`
- Configuration digest: `8e6bcc7fede3de732f4e3abc6ecc855101be2a516ce0cd697842bc13bc33a9be`
- Pack: `AKS-MEM-004` v1.0.0; digest: `c6cdb8cf9cc9bb99fbea9fc5fcf5a5f68c5d907dbde5e71b53d3f009fa281480`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.

## Recommendations

### 1. Review effective Pod memory for synthetic

- **ID:** `AKS-MEM-004-77c7af2a65cb`
- **Rule:** `AKS-MEM-004` v1.0.0
- **Severity / confidence:** info / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** effective-pod-memory

Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.

**Evidence**

- `pod_uid` = `pod-uid` (current-kubernetes-projection)
- `application_memory_request` = `704.0` MiB (current-kubernetes-projection)
- `init_peak_memory_request` = `1152.0` MiB (current-kubernetes-projection)
- `pod_memory_overhead` = `32.0` MiB (current-kubernetes-projection)
- `effective_pod_memory_request` = `1184.0` MiB (current-kubernetes-projection)
- `memory_limit_configuration_digest` = `23c8f8155f56f7e810cc9ca91da295aa4b7f35ab2e949b193e09aebaa219c9cb` (current-configuration)

**Prerequisites**

- Verify admitted quantities, native sidecar ordering and overhead.

**Proposed actions**

- Review accounting only; no request or limit change is proposed.

**Validation and safety**

- Compare the current effective request with the admitted Pod configuration.
- Risk: Current accounting does not establish historical usage or packing feasibility.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

