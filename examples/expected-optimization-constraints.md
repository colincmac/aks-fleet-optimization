# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-SCHED-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `fd1c1324af9046b6c9689f6b9878bc839778a47d6540b36805d7b75fe6638e52`
- Configuration digest: `a824a7ae65050f6f676d43819cebe8d0d5f76f68f57aea97e5e6a81a5097c08d`
- Pack: `AKS-SCHED-002` v1.0.0; digest: `254907cebd33f0d8f68d0693dc70856de408a17924a17eace4c08e8a15d3b9cb`; inventory-only

## Recommendations

### 1. Review current optimization constraints

- **ID:** `AKS-SCHED-002-f376a3f3d861`
- **Rule:** `AKS-SCHED-002` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** scheduling

Current probe, topology or voluntary-disruption evidence may constrain scaling, disruption, consolidation or portability. The finding is an owner investigation, not a selector match, universal policy judgment or generated configuration.

**Evidence**

- `containers_with_missing_probe_types` = `1` containers (kubernetes-metadata)
- `topology_spread_constraints` = `1` current admitted constraints (kubernetes-metadata)

**Prerequisites**

- Ask the workload owner which startup, health, availability, failure-domain and disruption behavior the application requires.
- Verify actual PDB selectors and eligible Pods with approved Kubernetes tooling before relating a budget to a workload.

**Proposed actions**

- Review the observed constraints with the workload and platform owners; do not generate or apply configuration from this finding.

**Validation and safety**

- Validate probe behavior during startup, steady state, dependency failure and graceful termination using owner-approved tests.
- Validate replica placement and failure-domain behavior before any topology-policy experiment.
- Recheck actual PDB selectors, desired healthy counts and disruptions allowed immediately before any separately approved voluntary disruption.
- Risk: Adding probes without application semantics can cause restart loops or remove healthy endpoints from service.
- Risk: Changing topology or disruption policy can reduce availability, violate storage constraints or increase correlated failure risk.

**Rollback**

- No configuration is generated or applied. Restore any separately approved probe, topology or PDB experiment through the owner&\#x27;s delivery system if validation regresses.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

