# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 0
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-NP-004` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `192713cc27601f1dcb7aea6ed37e665c6551f97fb5fc9a44763d3584fdba70d1`
- Configuration digest: `0c8696a712d72a5d557967492334ab473628172c7b508dbd80318d40a9ea8088`
- Pack: `AKS-NP-004` v1.0.0; digest: `99962096cbf4483b8ab0a938f7b41ed7ad00818346286e990d3bb894f733d949`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.
- Collection is partial overall; selected findings are gated independently on their required, complete, correctly scoped sources.

## Recommendations

### 1. Review DaemonSet overhead across current node shapes

- **ID:** `AKS-NP-004-c629afdcc243`
- **Rule:** `AKS-NP-004` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic-agent`
- **Category:** node-pool-efficiency

Identical admitted DaemonSet requests occupy different fractions of current node allocatable capacity. This is owner-review context, not a universal target, usage measurement, placement claim or savings.

**Evidence**

- `observed_daemonset_nodes` = `2` current nodes; not full cluster coverage (kubernetes-metadata)
- `cpu_request_mcpu/synthetic-node-uid` = `750.0` mCPU effective admitted request (kubernetes-metadata)
- `memory_request_mib/synthetic-node-uid` = `352.0` MiB effective admitted request (kubernetes-metadata)
- `allocatable_cpu_mcpu/synthetic-node-uid` = `2000.0` mCPU current allocatable capacity (kubernetes-metadata)
- `allocatable_memory_mib/synthetic-node-uid` = `1024.0` MiB current allocatable capacity (kubernetes-metadata)
- `cpu_request_share_percent/synthetic-node-uid` = `37.5` percent of current allocatable cpu; not a target (kubernetes-metadata)
- `memory_request_share_percent/synthetic-node-uid` = `34.375` percent of current allocatable memory; not a target (kubernetes-metadata)
- `cpu_request_mcpu/synthetic-other-node-uid` = `750.0` mCPU effective admitted request (kubernetes-metadata)
- `memory_request_mib/synthetic-other-node-uid` = `352.0` MiB effective admitted request (kubernetes-metadata)
- `allocatable_cpu_mcpu/synthetic-other-node-uid` = `4000.0` mCPU current allocatable capacity (kubernetes-metadata)
- `allocatable_memory_mib/synthetic-other-node-uid` = `2048.0` MiB current allocatable capacity (kubernetes-metadata)
- `cpu_request_share_percent/synthetic-other-node-uid` = `18.75` percent of current allocatable cpu; not a target (kubernetes-metadata)
- `memory_request_share_percent/synthetic-other-node-uid` = `17.1875` percent of current allocatable memory; not a target (kubernetes-metadata)
- `observed_nonterminal_daemonset_pods` = `2` listed nonterminal Pods; not desired Node coverage (kubernetes-metadata)

**Prerequisites**

- Confirm the DaemonSet owner and whether heterogeneous nodes need distinct resource policies using approved tooling.

**Proposed actions**

- Review observed request-share differences with the DaemonSet and platform owners; do not generate or apply node-specific sizing.

**Validation and safety**

- Recheck exact Pod/controller/node identities and admitted requests, init ordering, Pod overhead and allocatable capacity.
- Review controller desired/ready status separately from complete current owned-Pod and Node counts; unknown status does not invalidate independent observed request shares.
- Review node-specific demand, startup and reliability evidence independently before any separately approved sizing experiment.
- Risk: Current requests may protect initialization, restartable sidecars or failure scenarios; lower percentages do not authorize a reduction.

**Rollback**

- No change is proposed. Preserve exact original DaemonSet settings for rollback of any separately approved experiment.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

