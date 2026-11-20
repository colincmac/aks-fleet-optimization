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
- `AKS-REL-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `17c8bf12dac87de326b4b9916e9ea7a82cc02aee9dc300dee6490542bef9250e`
- Configuration digest: `faf086c6dcb4c0ec836ade36a347b1a9aa7ae5e4349de16e375126da6d9567b3`
- Pack: `AKS-REL-002` v1.0.0; digest: `d9e19bb911e79d39e3dcf7a4bddee292b51e092cd78ed42c244516325ddd5349`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.

## Recommendations

### 1. Review reported termination context for synthetic

- **ID:** `AKS-REL-002-d6524572d3bf`
- **Rule:** `AKS-REL-002` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** termination-context

Current UID-bound last-termination status reports a reason and exit code. It does not establish the cause of all restarts, historical frequency, node pressure or SLO impact; exit code 137 alone is not proof of OOM.

**Evidence**

- `pod_uid` = `pod-uid` (current-kubernetes-status)
- `container` = `api` (current-kubernetes-status)
- `reported_termination_reason` = `Error` (current-kubernetes-status)
- `reported_exit_code` = `137` (current-kubernetes-status)
- `termination_finished_at` = `2026-10-28T23:55:00+00:00` (current-kubernetes-status)

**Prerequisites**

- Confirm the exact current Pod/container and reported termination time.

**Proposed actions**

- Investigate reported context; no resource change is proposed.

**Validation and safety**

- Correlate approved incident/change evidence with owner-declared SLOs.
- Risk: Retained last-state metadata is not a complete incident history.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

