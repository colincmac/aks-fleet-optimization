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
- Snapshot digest: `b2a51f5afc56b97919fa42bea9624e6de8e45eaccfa0cda539d7a65b36fdedd3`
- Configuration digest: `a8a94898fbfd226bbc04e5074611fae1a14b59a276fed4e8370ef3215c8c6768`
- Pack: `AKS-REL-001` v2.0.0; digest: `d15a8c1b06e1f3a28c28023b5db85ea5872174b0a399f6ec73e76c8509909d5e`; inventory-only

## Recommendations

### 1. Investigate restarts for synthetic/api

- **ID:** `AKS-REL-001-f0a3852e4777`
- **Rule:** `AKS-REL-001` v2.0.0
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

