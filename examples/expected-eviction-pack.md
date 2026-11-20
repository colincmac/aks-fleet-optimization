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
- `AKS-REL-003` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `17c8bf12dac87de326b4b9916e9ea7a82cc02aee9dc300dee6490542bef9250e`
- Configuration digest: `2ebe92b1d356eb57f3009bf48ab8757cb49f994e54d44afd336fec9b266f76bb`
- Pack: `AKS-REL-003` v1.0.0; digest: `a210621d7cddb3b84709712cd7daf7b34a221cc97f8d270e4f120bb7998ab569`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Investigate workload evictions for synthetic

- **ID:** `AKS-REL-003-e400a56f5eb5`
- **Rule:** `AKS-REL-003` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** eviction-investigation

Identity-bound workload eviction counts were observed over the declared window. They are reported once per workload, not multiplied by containers; counts do not establish node-pressure causes or SLO impact.

**Evidence**

- `workload_eviction_events` = `2` events (synthetic)

**Prerequisites**

- Verify the approved historical eviction producer and workload identity.

**Proposed actions**

- Investigate workload eviction risk; no numeric change is proposed.

**Validation and safety**

- Review approved incident metadata and availability evidence before reductions.
- Risk: Evictions may have multiple causes; missing history is not zero.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

