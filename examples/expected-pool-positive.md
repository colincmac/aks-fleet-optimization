# AKS Fleet Assessment

Status: complete
Assessment scope: `fleet-assessment`
Input digest: `612f9e08f89fe291ead2918b556d6b651c8097c3ae84fb28e753752859e57f05`
Profile digest: `97278dd38cb4573e2ca8aabd6b5d2e9a4dd3f802863002f5db1801431563439b`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

No normalization gaps in the supported scope.

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
- Node pools analyzed: 1
- Workloads analyzed: 0
- Recommendations: 2
- High or critical: 0
- Blocked findings: 0
- Snapshot digest: `c8f8d05eefea0edd1e704401646134884af936744b826e8467960f954c8073ca`
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
  - `cpu_usage`: not\_collected
  - `cpu_request`: not\_collected
  - `cpu_throttling`: not\_collected
  - `replica_cpu_envelope`: not\_collected
  - `replica_cpu_request_min`: not\_collected
  - `replica_cpu_request_max`: not\_collected
  - `replica_cpu_throttling`: not\_collected
- `synthetic` / `AKS-RQ-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `cpu_usage`: not\_collected
  - `cpu_request`: not\_collected
  - `cpu_throttling`: not\_collected
  - `replica_cpu_envelope`: not\_collected
  - `replica_cpu_request_min`: not\_collected
  - `replica_cpu_request_max`: not\_collected
  - `replica_cpu_throttling`: not\_collected
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `cpu_usage`: not\_collected
  - `cpu_request`: not\_collected
  - `replica_cpu_envelope`: not\_collected
  - `replica_cpu_request_min`: not\_collected
  - `replica_cpu_request_max`: not\_collected
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `cpu_usage`: not\_collected
  - `cpu_request`: not\_collected
  - `cpu_throttling`: not\_collected
  - `oom_events`: not\_collected
  - `replica_cpu_envelope`: not\_collected
  - `replica_cpu_request_min`: not\_collected
  - `replica_cpu_request_max`: not\_collected
  - `replica_cpu_throttling`: not\_collected
  - `replica_oom_events`: not\_collected
- `synthetic` / `AKS-REL-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `evictions`: not\_collected
- `synthetic` / `AKS-REL-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `evictions`: not\_collected
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
  - `desired_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `available_replicas`: not\_collected
- `synthetic` / `AKS-AS-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `hpa_min_replicas`: not\_collected
  - `hpa_max_replicas`: not\_collected
  - `hpa_desired_replicas`: not\_collected
  - `hpa_current_replicas`: not\_collected
  - `desired_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `available_replicas`: not\_collected
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
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_total_usage`: not\_collected
  - `oom_events`: not\_collected
  - `restarts`: not\_collected
  - `desired_replicas`: not\_collected
  - `available_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `hpa_present`: not\_collected
  - `keda_present`: not\_collected
  - `vpa_present`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_total_usage`: not\_collected
  - `oom_events`: not\_collected
  - `restarts`: not\_collected
  - `desired_replicas`: not\_collected
  - `available_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `hpa_present`: not\_collected
  - `keda_present`: not\_collected
  - `vpa_present`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `oom_events`: not\_collected
  - `restarts`: not\_collected
  - `replica_memory_envelope`: not\_collected
  - `replica_memory_request_min`: not\_collected
  - `replica_memory_request_max`: not\_collected
  - `replica_memory_limit_min`: not\_collected
  - `replica_memory_limit_max`: not\_collected
  - `replica_oom_events`: not\_collected
  - `replica_restarts`: not\_collected
  - `desired_replicas`: not\_collected
  - `available_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `hpa_present`: not\_collected
  - `keda_present`: not\_collected
  - `vpa_present`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `oom_events`: not\_collected
  - `restarts`: not\_collected
  - `replica_memory_envelope`: not\_collected
  - `replica_memory_request_min`: not\_collected
  - `replica_memory_request_max`: not\_collected
  - `replica_memory_limit_min`: not\_collected
  - `replica_memory_limit_max`: not\_collected
  - `replica_oom_events`: not\_collected
  - `replica_restarts`: not\_collected
  - `desired_replicas`: not\_collected
  - `available_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `hpa_present`: not\_collected
  - `keda_present`: not\_collected
  - `vpa_present`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `oom_events`: not\_collected
  - `restarts`: not\_collected
  - `replica_memory_envelope`: not\_collected
  - `replica_memory_request_min`: not\_collected
  - `replica_memory_request_max`: not\_collected
  - `replica_memory_limit_min`: not\_collected
  - `replica_memory_limit_max`: not\_collected
  - `replica_oom_events`: not\_collected
  - `replica_restarts`: not\_collected
  - `desired_replicas`: not\_collected
  - `available_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `hpa_present`: not\_collected
  - `keda_present`: not\_collected
  - `vpa_present`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `oom_events`: not\_collected
  - `restarts`: not\_collected
  - `replica_memory_envelope`: not\_collected
  - `replica_memory_request_min`: not\_collected
  - `replica_memory_request_max`: not\_collected
  - `replica_memory_limit_min`: not\_collected
  - `replica_memory_limit_max`: not\_collected
  - `replica_oom_events`: not\_collected
  - `replica_restarts`: not\_collected
  - `desired_replicas`: not\_collected
  - `available_replicas`: not\_collected
  - `observed_replicas`: not\_collected
  - `hpa_present`: not\_collected
  - `keda_present`: not\_collected
  - `vpa_present`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-NP-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-NP-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-MEM-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `oom_events`: not\_collected
  - `replica_oom_events`: not\_collected
- `synthetic` / `AKS-MEM-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `oom_events`: not\_collected
  - `replica_oom_events`: not\_collected
- `synthetic` / `AKS-REL-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `restarts`: not\_collected
  - `replica_restarts`: not\_collected
- `synthetic` / `AKS-REL-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `restarts`: not\_collected
  - `replica_restarts`: not\_collected

## Recommendations

### 1. Review low-utilization node pool userpool

- **ID:** `AKS-NP-001-ec1a7b48d9eb`
- **Rule:** `AKS-NP-001` v2.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `-` / `-`
- **Category:** node-pool-efficiency

P95 CPU utilization is below the configured review threshold. This is not proof a node can be removed; validate resilience and scheduling constraints before a separately approved change.

**Evidence**

- `node_pool_cpu_p95_utilization` = `0.0571` ratio (synthetic)
- `node_count` = `1` nodes (inventory)

**Prerequisites**

- Confirm pod disruption budgets and zonal resilience.
- Check pending pods, daemonset overhead and scale-up latency.

**Proposed actions**

- Review minimum node count and autoscaler profile.
- Investigate existing placement and resilience requirements.

**Validation and safety**

- Load test any separately proposed minimum capacity.
- Compare P95/P99 saturation, pending pods and SLOs before and after.
- Risk: Reducing warm capacity can increase scale-up latency.
- Risk: Average or P95 utilization alone can hide short bursts.

**Rollback**

- No node target is proposed; revert a separately approved capacity change through the owning delivery pipeline on regression.

### 2. Review capacity management and NAP prerequisites

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

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

