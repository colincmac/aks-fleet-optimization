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
- `AKS-SCHED-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `fd1c1324af9046b6c9689f6b9878bc839778a47d6540b36805d7b75fe6638e52`
- Configuration digest: `caf25bdeab480d77bc496c81519d297e992415d0c958f7ef168ffaebe46524c6`
- Pack: `AKS-SCHED-001` v1.0.0; digest: `420359fdf0a9ef15bef7836a1544ceaa729e2bac461bb97f6a81830c10c5f71b`; inventory-only

## Recommendations

### 1. Investigate current placement constraints

- **ID:** `AKS-SCHED-001-8815405b8943`
- **Rule:** `AKS-SCHED-001` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** scheduling

Observed current constraints may restrict placement. These are review candidates, not proof of stranded capacity, scheduler failure, PDB matching or removable nodes.

**Evidence**

- `hard_topology_spread` = `1` entries (kubernetes-metadata)
- `node_selector` = `1` entries (kubernetes-metadata)
- `persistent_volume_claims` = `1` entries (kubernetes-metadata)
- `priority_class` = `1` entries (kubernetes-metadata)
- `required_pod_anti_affinity` = `1` entries (kubernetes-metadata)
- `tolerations` = `1` entries (kubernetes-metadata)
- `tainted_node_context` = `0` observed objects; not matched or historical (kubernetes-metadata)
- `cordoned_node_context` = `0` observed objects; not matched or historical (kubernetes-metadata)
- `daemonset_context` = `0` observed objects; not matched or historical (kubernetes-metadata)
- `namespace_pdb_candidates` = `0` observed objects; not matched or historical (kubernetes-metadata)

**Prerequisites**

- Review the admitted Pod, matching node labels/taints, volume topology and actual PDB selectors with its owner.

**Proposed actions**

- Investigate current placement restrictions; do not remove nodes or relax policy from this report.

**Validation and safety**

- Correlate each observed restriction with approved pending-Pod history and scheduler capacity evidence.
- Check daemon and init/sidecar overhead, Pod/IP slots, priorities, volumes and zonal failover before any packing claim.
- Keep hard requirements and soft preferences separate; verify unknown fields rather than assuming absence.
- Risk: Relaxing affinity, topology, taints or disruption policy can violate isolation, availability or storage requirements.

**Rollback**

- No change is proposed. Any later owner-approved experiment requires a separate canary and exact configuration rollback.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

