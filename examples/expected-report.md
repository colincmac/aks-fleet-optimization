# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-10-14T00:00:00+00:00 to 2026-10-28T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Node pools analyzed: 1
- Workloads analyzed: 2
- Recommendations: 0
- High or critical: 0
- Blocked findings: 38
- Snapshot digest: `648afca30f83ecc52a8bc927024035b1186e3961edeeea0335a8b91d9154c8ac`
- Configuration digest: `fc70120ba0fa3a09a2532be0cb583fedf2c14dccedb1218000a2d49416d405f6`
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

## Data quality warnings

- Observation window is 14.0 days; at least 30 days is recommended.
- stale\_metrics
- Collection provenance is missing; supplied observations are not actionable.

## Recommendations

No recommendations were generated.
## Blocked findings

These checks are not actionable recommendations.

- `AKS-AS-001` / `AKS-AS-001-2b293663d0d8` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`
- `AKS-AS-001` / `AKS-AS-001-944112df2b30` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`
- `AKS-AS-002` / `AKS-AS-002-8fc2071725ed` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-002` / `AKS-AS-002-f652a8b55965` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-003` / `AKS-AS-003-47afe6094bf9` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-003` / `AKS-AS-003-8ed64b088cb8` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-004` / `AKS-AS-004-2dd32640ed0e` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-004` / `AKS-AS-004-4e40b3a2b805` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-005` / `AKS-AS-005-3d5a2a950d70` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`, `missing_replica_safety_policy`, `short_window`, `stale_metrics`
- `AKS-AS-005` / `AKS-AS-005-4f5df28c9c9a` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`, `missing_replica_safety_policy`, `short_window`, `stale_metrics`
- `AKS-AS-006` / `AKS-AS-006-2d378561798c` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-006` / `AKS-AS-006-e3b8e7050364` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-007` / `AKS-AS-007-63d368f1ca3b` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-AS-007` / `AKS-AS-007-caf59f8f52a5` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`
- `AKS-MEM-001` / `AKS-MEM-001-65b31f65e846` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_identity`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-MEM-001` / `AKS-MEM-001-97bae6f271c3` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_identity`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-MEM-002` / `AKS-MEM-002-0fc0181258ce` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_request_observation`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-002` / `AKS-MEM-002-bd0c4aba0c2f` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_request_observation`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_autoscaler`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-003` / `AKS-MEM-003-3341c47c3fcf` / `aks-demo` / `orders` / `orders-api`: `memory_request_reduction_not_enabled`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_request_observation`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-003` / `AKS-MEM-003-8254c801b850` / `aks-demo` / `checkout` / `checkout-worker`: `memory_request_reduction_not_enabled`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_request_observation`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_autoscaler`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-004` / `AKS-MEM-004-00d7ae43891c` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_effective_pod_memory`
- `AKS-MEM-004` / `AKS-MEM-004-c4c437ac4806` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_effective_pod_memory`
- `AKS-MEM-005` / `AKS-MEM-005-3d79c8125918` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_autoscaler`
- `AKS-MEM-005` / `AKS-MEM-005-7e9f9e8c7802` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-NP-001` / `AKS-NP-001-fe7705a4414e` / `aks-demo` / `-` / `-`: `missing_collection_manifest`, `missing_identity`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-NP-002` / `AKS-NP-002-528738a6d6d8` / `aks-demo` / `-` / `-`: `missing_capacity_inventory`, `missing_collection_manifest`
- `AKS-REL-001` / `AKS-REL-001-58139d7a8803` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_identity`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-REL-001` / `AKS-REL-001-b619a48c1238` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_identity`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-REL-002` / `AKS-REL-002-8164259e8d87` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_termination_context`
- `AKS-REL-002` / `AKS-REL-002-fd81cc8ac0b0` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_termination_context`
- `AKS-REL-003` / `AKS-REL-003-ac31897b3375` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-REL-003` / `AKS-REL-003-bb5cd14bad5e` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-RQ-001` / `AKS-RQ-001-1436ba3bca3b` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_request_observation`
- `AKS-RQ-001` / `AKS-RQ-001-320ddf4be784` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_request_observation`
- `AKS-RQ-002` / `AKS-RQ-002-46cc9202e85e` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_identity`, `missing_metric_quality`, `missing_request_observation`, `short_window`, `stale_metrics`, `unknown_metric_aggregation`
- `AKS-RQ-003` / `AKS-RQ-003-48f265d0c2ed` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_identity`, `missing_metric`, `missing_metric_quality`, `missing_request_observation`, `short_window`, `stale_metrics`
- `AKS-RQ-003` / `AKS-RQ-003-667a4b45f83e` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_identity`, `missing_metric_quality`, `missing_request_observation`, `short_window`, `stale_metrics`
- `AKS-SCHED-001` / `AKS-SCHED-001-fee5bfc085dc` / `aks-demo` / `-` / `-`: `missing_collection_manifest`, `missing_scheduling_inventory`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.
