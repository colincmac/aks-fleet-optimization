# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `4abe420ea3ce51a431ec61fe4815a29f6b75e99c390b0a3754d1a23ee988ae7f`
Profile digest: `f6f6001b4d52c877066e27a02cc2396001e81ea3f68059327f7bbeeb400fcb08`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `missing-metrics-fragment`
- `/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic-denied`: `missing-cluster`

## Source Receipts

Eligibility requires a complete, fresh matching receipt; completed scope alone is insufficient.

- `azure-inventory` / `00000000-0000-0000-0000-000000000000`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `azure-inventory` / `11111111-1111-1111-1111-111111111111`: `failed`; completed: `False`; pages complete: `False`; source observed: `unknown`
- Failure: `11111111-1111-1111-1111-111111111111` / `forbidden`
- Missing field: `/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic-denied/inventory`
- `kubernetes-metadata` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `kubernetes-metadata` / `/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic-denied`: `failed`; completed: `False`; pages complete: `False`; source observed: `unknown`
- Failure: `/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic-denied` / `unavailable`
- `prometheus` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `failed`; completed: `False`; pages complete: `False`; source observed: `unknown`
- `prometheus` / `/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic-denied`: `failed`; completed: `False`; pages complete: `False`; source observed: `unknown`
- Failure: `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic` / `unavailable`
- Failure: `/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic-denied` / `unavailable`

# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 0
- Workloads analyzed: 1
- Recommendations: 1
- High or critical: 1
- Blocked findings: 17
- Snapshot digest: `7d083cd84b1840db06ff9e31a3e70b46420daba105eb73edfa5b746ebee1f0a8`
- Configuration digest: `06c29c364433692088978ed06141ac200ed58a84d23fd18ff15fb8522b5aa9be`
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
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-006` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-006` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-006` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-006` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-005` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-005` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-AS-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-005` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-005` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-NP-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-NP-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-NP-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-NP-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-MEM-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-001` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected
- `synthetic` / `AKS-REL-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `source.evidence`: not\_collected

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.
- Collection is partial; findings require complete, correctly scoped sources.

## Recommendations

### 1. Review missing CPU request for synthetic/api

- **ID:** `AKS-RQ-001-a112364a0e6b`
- **Rule:** `AKS-RQ-001` v2.0.0
- **Severity / confidence:** high / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** resource-governance

No positive CPU request was explicitly observed. Requests support reliable scheduling, rightsizing and cost attribution. This is an investigation, not a numeric target.

**Evidence**

- `request_cpu_mcores` = `None` mCPU (kubernetes-api)

**Prerequisites**

- Collect representative CPU usage before selecting a value.

**Proposed actions**

- Use VPA recommendation mode or historical percentiles to propose a request.

**Validation and safety**

- Load test and monitor throttling and latency.
- Risk: An arbitrarily low request can cause contention or poor placement.

**Rollback**

- No numeric change is proposed; restore any separately approved change through the owning delivery pipeline.

## Blocked findings

These checks are not actionable recommendations.

- `AKS-AS-001` / `AKS-AS-001-cb2a1c469235` / `aks-synthetic` / `synthetic` / `synthetic`: `unknown_autoscaler`
- `AKS-AS-002` / `AKS-AS-002-428b77c533dc` / `aks-synthetic` / `synthetic` / `synthetic`: `unknown_hpa_configuration`, `unknown_vpa_configuration`
- `AKS-AS-003` / `AKS-AS-003-d511905ba381` / `aks-synthetic` / `synthetic` / `synthetic`: `unknown_hpa_configuration`
- `AKS-AS-004` / `AKS-AS-004-46a6f7c0c152` / `aks-synthetic` / `synthetic` / `synthetic`: `unknown_hpa_configuration`, `unknown_keda_configuration`, `unknown_vpa_configuration`
- `AKS-AS-005` / `AKS-AS-005-2a7d3e5faf0e` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_replica_safety_policy`, `uncollected_scope`, `unknown_hpa_configuration`, `unknown_keda_configuration`, `unknown_source_freshness`, `unknown_vpa_configuration`
- `AKS-AS-006` / `AKS-AS-006-59f970c25453` / `aks-synthetic` / `synthetic` / `synthetic`: `unknown_hpa_configuration`
- `AKS-AS-007` / `AKS-AS-007-e677c293136d` / `aks-synthetic` / `synthetic` / `synthetic`: `unknown_hpa_configuration`, `unknown_vpa_configuration`
- `AKS-MEM-001` / `AKS-MEM-001-685a32f8cba0` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-MEM-002` / `AKS-MEM-002-f3643c0f7e4f` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_autoscaler`, `unknown_qos_class`, `unknown_source_freshness`, `unsupported_memory_history`
- `AKS-MEM-003` / `AKS-MEM-003-1c2d8743035d` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `memory_request_reduction_not_enabled`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_autoscaler`, `unknown_qos_class`, `unknown_source_freshness`, `unsupported_memory_history`
- `AKS-MEM-004` / `AKS-MEM-004-77c7af2a65cb` / `aks-synthetic` / `synthetic` / `synthetic`: `unsupported_or_unknown_effective_pod_memory`
- `AKS-MEM-005` / `AKS-MEM-005-ac457d31871f` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_autoscaler`, `unknown_hpa_configuration`, `unknown_keda_configuration`, `unknown_source_freshness`, `unknown_vpa_configuration`
- `AKS-NP-002` / `AKS-NP-002-d572caa86976` / `aks-synthetic` / `-` / `-`: `missing_capacity_supply`
- `AKS-REL-001` / `AKS-REL-001-f0a3852e4777` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-REL-002` / `AKS-REL-002-d6524572d3bf` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_termination_context`
- `AKS-REL-003` / `AKS-REL-003-e400a56f5eb5` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-RQ-003` / `AKS-RQ-003-add67f939342` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

