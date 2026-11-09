# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `6c460cd806265079cb4bcf492314526d07ed1f06d790a24ca5f18cddb7907e15`
Profile digest: `97278dd38cb4573e2ca8aabd6b5d2e9a4dd3f802863002f5db1801431563439b`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/agentPools/userpool`: `unsupported-pool-evidence`

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
- Recommendations: 6
- High or critical: 0
- Blocked findings: 3
- Snapshot digest: `9dd8731e8689f5af668925573c5b3b61c0c6c5ec1553c2615df807d5fe0274b4`
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
- `synthetic` / `AKS-AS-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
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
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `unschedulable_pods`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
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

## Recommendations

### 1. Review lower memory request for synthetic/api

- **ID:** `AKS-MEM-003-1c2d8743035d`
- **Rule:** `AKS-MEM-003` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** memory-efficiency

A request-only memory proposal obeys the declared owner minimum, maximum reduction and peak/startup/failover headroom. It preserves the observed memory limit and Burstable QoS; it does not prove node removability, financial savings or change approval.

**Evidence**

- **Owner:** synthetic-owner
- **Memory request:** 512.0 to 313.0 MiB per replica
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)
- `usage_memory_p95_mib` = `160.0` MiB (synthetic)
- `usage_memory_p99_mib` = `192.0` MiB (synthetic)
- `memory_oom_events` = `0` events (synthetic)
- `restart_events` = `0` events (synthetic)
- `workload_eviction_events` = `0` events (synthetic)
- `memory_observation_basis` = `replica-envelope` (normalized-history)
- `memory_membership_digest` = `317b65a425a883954b66399ffec654884cf24b4ce3c9fa4b6447247cc9d5b322` (approved-binding)
- `current_replicas` = `2` pods (current-kubernetes-projection)
- `startup_peak_mib` = `240.0` MiB (owner-reviewed:synthetic-review/memory)
- `failover_peak_mib` = `250.0` MiB (owner-reviewed:synthetic-review/memory)
- `reviewed_eviction_events` = `0` events (owner-reviewed:synthetic-review/memory)
- `minimum_request_mib` = `128.0` MiB (owner-reviewed:synthetic-review/memory)
- `maximum_reduction_ratio` = `0.5` ratio (owner-reviewed:synthetic-review/memory)
- `headroom_factor` = `1.25` ratio (owner-reviewed:synthetic-review/memory)
- `observed_memory_working_set_peak_mib` = `200.0` MiB (synthetic)
- `qos_class` = `Burstable` (kubernetes-api)
- `allow_request_reduction` = `True` (owner-policy)

**Prerequisites**

- Obtain separate owner approval for this specific request-only change; enabling proposals is not approval to apply them.
- Independently verify the reviewed scenario/eviction evidence, supported direct or approved-envelope history, absent overhead and current admitted settings.
- Keep CPU requests, all limits and other containers unchanged; do not combine independent CPU and memory proposals in one canary.

**Proposed actions**

- Propose 313.0 MiB memory request per replica for this container only; keep limits unchanged and obtain owner approval.

**Validation and safety**

- Canary only the approved memory request under startup, peak load and failover; confirm the limit and QoS remain unchanged.
- Compare OOM, restarts, evictions, placement and owner-declared SLOs with the pre-change baseline before promotion.
- Risk: Working-set samples can omit relevant memory and short peaks.
- Risk: Lower requests reduce eviction protection and can increase node pressure or change placement despite unchanged Burstable QoS.

**Rollback**

- If OOM, restarts, evictions or owner-declared SLOs regress, stop promotion and restore the original 512.0 MiB memory request through the owning delivery pipeline; keep all other settings unchanged.

### 2. Review CPU request for synthetic/api

- **ID:** `AKS-RQ-002-3d127b89e9ee`
- **Rule:** `AKS-RQ-002` v2.1.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** workload-rightsizing

Historical CPU usage is below the request. The proposal respects observed peaks, declared headroom and owner policy; validate it through a separately approved canary.

**Evidence**

- **Owner:** synthetic-owner
- **CPU request:** 1000.0 to 500.0 mCPU per replica
- `cpu_p95_to_request_ratio` = `0.1` ratio (synthetic)
- `cpu_observation_basis` = `replica-envelope` (normalized-evidence)
- `potential_cpu_request_reduction` = `500.0` mCPU per replica (derived)

**Prerequisites**

- Confirm the metric window contains peak and business-critical periods.
- Review P99 usage, throttling, startup and failover behavior.

**Proposed actions**

- Open a review PR with the proposed request and rollback criteria.

**Validation and safety**

- Run VPA in Off mode and compare recommendations.
- Canary an independently approved request change and verify SLOs under load.
- Risk: Historical usage might not represent future peaks.
- Risk: Lower requests can change placement and noisy-neighbor behavior.

**Rollback**

- Restore the previous CPU request of 1000.0 mCPU in source configuration through the owning delivery pipeline.
- Stop promotion if SLOs, throttling, OOM or restarts regress; remeasure before proposing another change.

### 3. Review autoscaling for synthetic/synthetic

- **ID:** `AKS-AS-001-cb2a1c469235`
- **Rule:** `AKS-AS-001` v2.0.0
- **Severity / confidence:** low / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** workload-autoscaling

The workload has multiple replicas but no HPA or KEDA signal in the current snapshot. Confirm whether fixed capacity is an explicit requirement; no numeric replica proposal is made.

**Evidence**

- `replicas` = `2` pods (kubernetes-api)
- `hpa_present` = `False` (kubernetes-api)
- `keda_present` = `False` (kubernetes-api)

**Prerequisites**

- Identify a scaling signal tied to user demand or queue depth.

**Proposed actions**

- Document why fixed replicas are required, or prototype HPA/KEDA.

**Validation and safety**

- Validate scaling behavior with representative load.
- Risk: A poorly selected signal can cause oscillation or SLO regressions.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### 4. Review memory safety for synthetic/api

- **ID:** `AKS-MEM-002-f3643c0f7e4f`
- **Rule:** `AKS-MEM-002` v2.0.0
- **Severity / confidence:** info / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** memory-safety-review

Supported memory evidence and owner-reviewed scenarios pass the readiness gates. This is not a safe memory target, a waste claim or approval to change requests or limits.

**Evidence**

- **Owner:** synthetic-owner
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)
- `usage_memory_p95_mib` = `160.0` MiB (synthetic)
- `usage_memory_p99_mib` = `192.0` MiB (synthetic)
- `memory_oom_events` = `0` events (synthetic)
- `restart_events` = `0` events (synthetic)
- `workload_eviction_events` = `0` events (synthetic)
- `memory_observation_basis` = `replica-envelope` (normalized-history)
- `memory_membership_digest` = `317b65a425a883954b66399ffec654884cf24b4ce3c9fa4b6447247cc9d5b322` (approved-binding)
- `current_replicas` = `2` pods (current-kubernetes-projection)
- `startup_peak_mib` = `240.0` MiB (owner-reviewed:synthetic-review/memory)
- `failover_peak_mib` = `250.0` MiB (owner-reviewed:synthetic-review/memory)
- `reviewed_eviction_events` = `0` events (owner-reviewed:synthetic-review/memory)
- `minimum_request_mib` = `128.0` MiB (owner-reviewed:synthetic-review/memory)
- `maximum_reduction_ratio` = `0.5` ratio (owner-reviewed:synthetic-review/memory)
- `headroom_factor` = `1.25` ratio (owner-reviewed:synthetic-review/memory)
- `observed_memory_working_set_peak_mib` = `200.0` MiB (synthetic)
- `qos_class` = `Burstable` (kubernetes-api)

**Prerequisites**

- Independently verify owner-reviewed startup, failover and eviction evidence; references and declarations are not source attestation.
- Keep limits and QoS unchanged; any future target needs separate owner approval and effective-Pod validation.

**Proposed actions**

- Review memory safety evidence only; no numeric memory request or limit change is proposed.

**Validation and safety**

- Validate startup, peak load and failover against owner-declared SLOs, OOM, restarts and evictions before approving any change.
- Risk: Working set and sampled peaks can omit relevant memory and bursts.
- Risk: Lower requests can increase node-pressure eviction risk even when the QoS class is unchanged.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### 5. Review effective Pod memory for synthetic

- **ID:** `AKS-MEM-004-77c7af2a65cb`
- **Rule:** `AKS-MEM-004` v2.0.0
- **Severity / confidence:** info / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** effective-pod-memory

Current admitted memory requests include concurrent restartable init containers, sequential initialization peaks and Pod overhead. These are scheduler request bounds, not observed usage, Pod-level limits or node-removal proof.

**Evidence**

- `pod_uid` = `pod-uid` (current-kubernetes-projection)
- `application_memory_request` = `512.0` MiB (current-kubernetes-projection)
- `init_peak_memory_request` = `0.0` MiB (current-kubernetes-projection)
- `pod_memory_overhead` = `0.0` MiB (current-kubernetes-projection)
- `effective_pod_memory_request` = `512.0` MiB (current-kubernetes-projection)
- `pod_uid` = `synthetic-memory-extra-pod` (current-kubernetes-projection)
- `application_memory_request` = `512.0` MiB (current-kubernetes-projection)
- `init_peak_memory_request` = `0.0` MiB (current-kubernetes-projection)
- `pod_memory_overhead` = `0.0` MiB (current-kubernetes-projection)
- `effective_pod_memory_request` = `512.0` MiB (current-kubernetes-projection)
- `memory_limit_configuration_digest` = `b5a41404b5e54e269554cfe4a779f1a5198bc75245608e89074af62468907289` (current-configuration)

**Prerequisites**

- Verify admitted quantities, native sidecar ordering and overhead.

**Proposed actions**

- Review accounting only; no request or limit change is proposed.

**Validation and safety**

- Compare the current effective request with the admitted Pod configuration.
- Risk: Current accounting does not establish historical usage or packing feasibility.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### 6. Review capacity management and NAP prerequisites

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

## Blocked findings

These checks are not actionable recommendations.

- `AKS-AS-005` / `AKS-AS-005-2a7d3e5faf0e` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_replica_safety_policy`
- `AKS-MEM-005` / `AKS-MEM-005-ac457d31871f` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`
- `AKS-REL-002` / `AKS-REL-002-d6524572d3bf` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_termination_context`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

