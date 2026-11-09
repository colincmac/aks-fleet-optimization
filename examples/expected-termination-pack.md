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
- Configuration digest: `60a69990bef870dbdac58478b5e8cf6791104a432cb2ee413ca7f98bbcd59ac1`
- Pack: `AKS-REL-002` v2.0.0; digest: `929ec47b9f67b3bf82e3d40bc375e220a7e9a9e66010e9fbe278899cb4ea589f`; inventory-only

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review reported termination context for synthetic

- **ID:** `AKS-REL-002-d6524572d3bf`
- **Rule:** `AKS-REL-002` v2.0.0
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

