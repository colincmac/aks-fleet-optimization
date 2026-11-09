# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `596d36649d66d4979ccf5760b1c997eaf4cb0ac267ce82d6c990e591e1efd599`
Profile digest: `97278dd38cb4573e2ca8aabd6b5d2e9a4dd3f802863002f5db1801431563439b`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/agentPools/userpool`: `unsupported-pool-evidence`
- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/workloads/workload-uid`: `unsupported-workload-history`

## Source Receipts

Eligibility requires a complete, fresh matching receipt; completed scope alone is insufficient.

- `azure-inventory` / `00000000-0000-0000-0000-000000000000`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `kubernetes-metadata` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `prometheus` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`

# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 0
- Workloads analyzed: 1
- Recommendations: 5
- High or critical: 0
- Blocked findings: 6
- Snapshot digest: `a5ca82a6dd89942b9f827810f58cea55fb652265f9fd84fcbced715c2d518f99`
- Configuration digest: `bb8beda1e402d19bde1283df7d2e6b92d43a35f5e012d722f2b18d53cfba3566`
- Pack: `AKS-AS-001` v2.0.0; digest: `4c38704d699841a3b9cbfb4365989efdc6255353761e9a092f0a3b81ef4ebc20`; inventory-only
- Pack: `AKS-AS-002` v2.0.0; digest: `7870961887f0fd1b2ccc7ec3bf8c8153b3d4e1d965a05a8331d21cac904f48f8`; inventory-only
- Pack: `AKS-AS-003` v2.0.0; digest: `b1fde20fccf7620b29df2056348ac4d95c4a6131ae814b0b1cf00386165a5480`; inventory-only
- Pack: `AKS-AS-004` v2.0.0; digest: `d68e0d2a9aee2f6056cae5b11759a856819df8cbc354d9bf5c2b36114865cacd`; inventory-only
- Pack: `AKS-AS-005` v2.0.0; digest: `1919c70059e05df837cdd842d72fba8d8464e2b8f6d39c25dd9f3f6967619d26`; inventory-only
- Pack: `AKS-AS-006` v2.0.0; digest: `d6af639b6f013410e0005f8d70e1650671d646500c9839fc0ccd42dba2d95d02`; inventory-only
- Pack: `AKS-AS-007` v2.0.0; digest: `67390629e7dfd5919fecb831653b6b72117b9d8ed88c96f2cc12630a9552b1b2`; inventory-only
- Pack: `AKS-MEM-001` v2.0.0; digest: `5aa9bd2eab3c67ac864d9665236a55084974dfbf400767d28a6412b5c314aaff`; inventory-only
- Pack: `AKS-MEM-002` v2.0.0; digest: `a8f370ee0397ffc2b5a70ef5a767dab1065c57a74c4f9c8d7a23a8b9444b0b96`; inventory-only
- Pack: `AKS-MEM-003` v2.0.0; digest: `4f9e63453b810bc0c85a40469d982fcedbc0861cf7b821a3b7d41e528b09d8d1`; inventory-only
- Pack: `AKS-MEM-004` v2.0.0; digest: `06a6565d5c06f7b7d7a38848f37f9931236d18375752fbfdd03567718e899155`; inventory-only
- Pack: `AKS-MEM-005` v2.0.0; digest: `8a8ea234def4ae4454b4d970ecb34d8a5c6f03e083f5cb81da7dbb588386d040`; inventory-only
- Pack: `AKS-NP-001` v2.0.0; digest: `bb6d38a357d12431b92179a4fcf382f9ade0f3a262c776c402cb2533c15ee747`; review ratio: 0.2
- Pack: `AKS-NP-002` v1.0.0; digest: `96fd7b91e3b77b99e6e7c67ab1e10130f0e31664774746999231cc1467808d7b`; inventory-only
- Pack: `AKS-REL-001` v2.0.0; digest: `d15a8c1b06e1f3a28c28023b5db85ea5872174b0a399f6ec73e76c8509909d5e`; inventory-only
- Pack: `AKS-REL-002` v2.0.0; digest: `929ec47b9f67b3bf82e3d40bc375e220a7e9a9e66010e9fbe278899cb4ea589f`; inventory-only
- Pack: `AKS-REL-003` v2.0.0; digest: `26ae8db918931762d9b10ef12206ef979401239ca10bdb59f915682b35c347ce`; inventory-only
- Pack: `AKS-RQ-001` v2.0.0; digest: `5ad78cbaccf1bb5a22dcce6a4cf28baaf58e89134f76369715b27b64f8944823`; inventory-only
- Pack: `AKS-RQ-002` v2.1.0; digest: `b347d11ef3b28bf5b7e851d3d01cff46b461a8d9ae120e4fdab983513ab66344`; review ratio: 0.4
- Pack: `AKS-RQ-003` v2.0.0; digest: `3686fb298e7a8ccb1e776d818e87608eae7630b790e07f2b980cd30d139724be`; review ratio: 0.9
- Pack: `AKS-SCHED-001` v1.0.0; digest: `420359fdf0a9ef15bef7836a1544ceaa729e2bac461bb97f6a81830c10c5f71b`; inventory-only

## Source capabilities

Metric availability is not source attestation or safe-change approval.
- `synthetic` / `AKS-RQ-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-REL-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-REL-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-AS-006` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
- `synthetic` / `AKS-AS-006` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
- `synthetic` / `AKS-AS-005` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
  - `observed_replicas`: not\_collected
- `synthetic` / `AKS-AS-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
  - `observed_replicas`: not\_collected
- `synthetic` / `AKS-AS-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
- `synthetic` / `AKS-AS-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
- `synthetic` / `AKS-MEM-005` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_total_usage`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_total_usage`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-NP-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `node_cpu_usage`: not\_collected
  - `node_allocatable_cpu`: not\_collected
  - `node_allocatable_memory`: not\_collected
- `synthetic` / `AKS-NP-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `node_cpu_usage`: not\_collected
  - `node_allocatable_cpu`: not\_collected
  - `node_allocatable_memory`: not\_collected
- `synthetic` / `AKS-MEM-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-MEM-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-REL-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-REL-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared

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

### 2. Investigate workload evictions for synthetic

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

### 3. Review effective Pod memory for synthetic

- **ID:** `AKS-MEM-004-77c7af2a65cb`
- **Rule:** `AKS-MEM-004` v2.0.0
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

### 4. Review capacity management and NAP prerequisites

- **ID:** `AKS-NP-002-d572caa86976`
- **Rule:** `AKS-NP-002` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `-` / `-`
- **Category:** node-pool-efficiency

Current capacity configuration and declared intent support investigation only, not NAP eligibility, migration approval, lower minima, removable nodes or financial savings.

**Evidence**

- `current_pool_management` = `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/agentPools/userpool: fixed; intent=unknown` classification (azure-inventory)
- `current_node_provisioning_mode` = `Manual` mode (azure-inventory)
- `uid_provider_bound_nap_nodes` = `0` observed nodes; not complete supply or removable nodes (kubernetes-metadata)
- `nap_eligibility` = `unknown: network, identity, quota/SKU, workload/disruption fit, operational acceptance` unverified prerequisites (not collected)
- `nap_configuration_issues` = `None` reason codes; no attestation (kubernetes-metadata)

**Prerequisites**

- Review current Microsoft AKS NAP support for the exact version, region, networking and identity.
- Preserve system capacity, Spot interruption tolerance, hardware, zoning and owner-reserved capacity.
- Compare CAS tuning with a separately approved transition; do not enable NAP or disable CAS from this report.

**Proposed actions**

- Investigate capacity classes and missing prerequisites; guarded mode does not authorize migration.

**Validation and safety**

- Confirm complete NAP API lists, exact owner/provider identities, node-class requirements, limits and disruption budgets.
- Validate all unknown prerequisites using separately approved sanitized evidence and current AKS documentation.
- Require workload-fit, pending-Pod, availability and packing evidence before a separate migration proposal.
- Risk: Removing minima or migrating capacity can violate disruption, storage, specialized hardware and failover requirements.
- Risk: NAP has unsupported configurations and stop/start and egress constraints; configuration eligibility alone is insufficient.

**Rollback**

- No change is proposed. A later approved experiment must retain original capacity and define an owner-controlled rollback.

### 5. Investigate current placement constraints

- **ID:** `AKS-SCHED-001-8815405b8943`
- **Rule:** `AKS-SCHED-001` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** scheduling

Observed current constraints may restrict placement. These are review candidates, not proof of stranded capacity, scheduler failure, PDB matching or removable nodes.

**Evidence**

- `init_containers` = `3` entries (kubernetes-metadata)
- `pod_overhead` = `1` entries (kubernetes-metadata)
- `tainted_node_context` = `0` observed objects; not matched or historical (kubernetes-metadata)
- `cordoned_node_context` = `0` observed objects; not matched or historical (kubernetes-metadata)
- `daemonset_context` = `0` observed objects; not matched or historical (kubernetes-metadata)
- `namespace_pdb_candidates` = `0` observed objects; not matched or historical (kubernetes-metadata)

**Prerequisites**

- Review the admitted Pod, matching node labels/taints, volume topology and actual PDB selectors with its owner.

**Proposed actions**

- Investigate current placement restrictions; guarded mode does not authorize a scheduling change.

**Validation and safety**

- Correlate each observed restriction with approved pending-Pod history and scheduler capacity evidence.
- Check daemon and init/sidecar overhead, Pod/IP slots, priorities, volumes and zonal failover before any packing claim.
- Keep hard requirements and soft preferences separate; verify unknown fields rather than assuming absence.
- Risk: Relaxing affinity, topology, taints or disruption policy can violate isolation, availability or storage requirements.

**Rollback**

- No change is proposed. Any later owner-approved experiment requires a separate canary and exact configuration rollback.

## Blocked findings

These checks are not actionable recommendations.

- `AKS-AS-005` / `AKS-AS-005-2a7d3e5faf0e` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_replica_safety_policy`
- `AKS-MEM-002` / `AKS-MEM-002-f3643c0f7e4f` / `aks-synthetic` / `synthetic` / `synthetic`: `collected_eviction_history`, `current_termination_review_required`, `unknown_autoscaler`, `unsupported_memory_history`
- `AKS-MEM-003` / `AKS-MEM-003-1c2d8743035d` / `aks-synthetic` / `synthetic` / `synthetic`: `collected_eviction_history`, `current_termination_review_required`, `unknown_autoscaler`, `unsupported_memory_history`
- `AKS-MEM-005` / `AKS-MEM-005-ac457d31871f` / `aks-synthetic` / `synthetic` / `synthetic`: `current_termination_review_required`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `unknown_autoscaler`
- `AKS-RQ-002` / `AKS-RQ-002-3d127b89e9ee` / `aks-synthetic` / `synthetic` / `synthetic`: `collected_eviction_history`, `missing_metric`, `missing_metric_quality`, `unknown_autoscaler`, `unknown_metric_aggregation`
- `AKS-RQ-003` / `AKS-RQ-003-add67f939342` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_metric`, `missing_metric_quality`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

