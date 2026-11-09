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
- Snapshot digest: `ea75276dbe9f57ba5d763c90ae80391ed9d56ea88062e9dd27c41fe747508bb5`
- Configuration digest: `75ab7a84358380fcc07f902f23351be5a37f3b2f8261b2316a176900f9586081`
- Pack: `AKS-REL-003` v2.0.0; digest: `26ae8db918931762d9b10ef12206ef979401239ca10bdb59f915682b35c347ce`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Investigate workload evictions for synthetic

- **ID:** `AKS-REL-003-e400a56f5eb5`
- **Rule:** `AKS-REL-003` v2.0.0
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

