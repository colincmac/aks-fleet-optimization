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
- `AKS-REL-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `e9a842ce9a279aeab5d0fc396b581e64d19c741172d89b92487a1b8cc4cf8055`
- Configuration digest: `da5ac168afc43b910db6a9238a41ab5d67b918cef8a2b5072e398d7e6e7d7e23`
- Pack: `AKS-REL-001` v1.0.0; digest: `94e2af087bbcfbab390f68d3b7c631f83f61cebca51bb83e7d55c0fe3ab2c503`; inventory-only

## Recommendations

### 1. Investigate restarts for synthetic/api

- **ID:** `AKS-REL-001-f0a3852e4777`
- **Rule:** `AKS-REL-001` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** reliability-guardrail

Container restarts were observed in the assessment window. Correlate them with owner-declared SLOs and approved operational evidence; the count alone does not establish memory pressure, an OOM cause or an application failure.

**Evidence**

- **Owner:** synthetic-owner
- `restart_events` = `1` events (synthetic)

**Prerequisites**

- Have the workload owner distinguish expected restarts from probe, application, OOM or node-related failures using approved tools.

**Proposed actions**

- Investigate restart causes before considering memory rightsizing; no resource change is proposed.

**Validation and safety**

- Correlate restart timing with changes and owner-declared SLOs.
- Validate any separately approved change under startup, peak load and failover conditions, checking OOM and restart behavior.
- Risk: Restart counts do not identify their cause or prove SLO impact.
- Risk: Resource changes without cause analysis can worsen reliability.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

