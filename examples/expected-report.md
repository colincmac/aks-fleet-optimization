# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-10-14T00:00:00+00:00 to 2026-10-28T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 1
- Snapshot vertical-workload records: 2
- Recommendations: 0
- High or critical: 0
- Blocked findings: 41
- `AKS-AS-001` subjects evaluated: 2
- `AKS-AS-002` subjects evaluated: 2
- `AKS-AS-003` subjects evaluated: 2
- `AKS-AS-004` subjects evaluated: 2
- `AKS-AS-005` subjects evaluated: 2
- `AKS-AS-006` subjects evaluated: 2
- `AKS-AS-007` subjects evaluated: 2
- `AKS-MEM-001` subjects evaluated: 2
- `AKS-MEM-002` subjects evaluated: 2
- `AKS-MEM-003` subjects evaluated: 2
- `AKS-MEM-004` subjects evaluated: 2
- `AKS-MEM-005` subjects evaluated: 2
- `AKS-NP-001` subjects evaluated: 1
- `AKS-NP-002` subjects evaluated: 1
- `AKS-NP-003` subjects evaluated: 0
- `AKS-NP-004` subjects evaluated: 0
- `AKS-REL-001` subjects evaluated: 2
- `AKS-REL-002` subjects evaluated: 2
- `AKS-REL-003` subjects evaluated: 2
- `AKS-RQ-001` subjects evaluated: 2
- `AKS-RQ-002` subjects evaluated: 2
- `AKS-RQ-003` subjects evaluated: 2
- `AKS-SCHED-001` subjects evaluated: 0
- `AKS-SCHED-002` subjects evaluated: 0
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `ffa7764e0ba217f698ecac673e7c2448debba8d36574394af70ed60eb7a0110e`
- Configuration digest: `c9aea58f714d1dfe6ee6a76bfcd3401d7b7985434ff67da044b7ea64c713a28a`
- Pack: `AKS-AS-001` v1.0.0; digest: `fac572d7cd4dd5802b9576c8dd503fa1542af662b53b565a34102f8242ea0ab0`; inventory-only
- Pack: `AKS-AS-002` v1.0.0; digest: `bc2fc328dc8244e004bdcf6b452344a87948fb232c5021c63c1245f6ae03f376`; inventory-only
- Pack: `AKS-AS-003` v1.0.0; digest: `129fc1650bd91b20c8a2415cd824b56913c06881d2e5db041f5e9298be088592`; inventory-only
- Pack: `AKS-AS-004` v1.0.0; digest: `de32fe82374db00e8ee980be1abc2246ba947c9fcefd27e137a6dfb96518e14d`; inventory-only
- Pack: `AKS-AS-005` v1.0.0; digest: `aa841b1ac664b2ad990ecb3c069a531d57cda5b04e2421341650ef5eb5a388f0`; inventory-only
- Pack: `AKS-AS-006` v1.0.0; digest: `abf0c1f18ad7f1856d2a0dce4c76be3d0b07bc87dc620c1bc799658a00f874c0`; inventory-only
- Pack: `AKS-AS-007` v1.0.0; digest: `94b5bc8f0b4e303252079dca55dd6ae7b6adc9e4ae8f7aa600e743d16ff409f1`; inventory-only
- Pack: `AKS-MEM-001` v1.0.0; digest: `f69012630c4d2a464a20053c932d05b8669666311d1237b3bc198c398c3c4c42`; inventory-only
- Pack: `AKS-MEM-002` v1.0.0; digest: `a1c26aa2a90c056b93c48279c9df977c97d9e9d9f26d6a275a8cadd414a1f52a`; inventory-only
- Pack: `AKS-MEM-003` v1.0.0; digest: `24ac10817abfeb3f6ad2641646310ada00dd1c61113f60dd14a3985f9560d369`; inventory-only
- Pack: `AKS-MEM-004` v1.0.0; digest: `c6cdb8cf9cc9bb99fbea9fc5fcf5a5f68c5d907dbde5e71b53d3f009fa281480`; inventory-only
- Pack: `AKS-MEM-005` v1.0.0; digest: `bb86c88b2d765e4de7e7596fe02ac0cc2f37fa808334b802534a667b0bd5312b`; inventory-only
- Pack: `AKS-NP-001` v1.0.0; digest: `f9209222647295f9d7c0db4518fdd6170f77f2f39567ff4ab402d345e1abebe8`; review ratio: 0.2
- Pack: `AKS-NP-002` v1.0.0; digest: `96fd7b91e3b77b99e6e7c67ab1e10130f0e31664774746999231cc1467808d7b`; inventory-only
- Pack: `AKS-NP-003` v1.0.0; digest: `341da7cf1a7589dcb068f3a4090306fe0e3a9591ea31634fedabeeb6c0f51124`; inventory-only
- Pack: `AKS-NP-004` v1.0.0; digest: `99962096cbf4483b8ab0a938f7b41ed7ad00818346286e990d3bb894f733d949`; inventory-only
- Pack: `AKS-REL-001` v1.0.0; digest: `94e2af087bbcfbab390f68d3b7c631f83f61cebca51bb83e7d55c0fe3ab2c503`; inventory-only
- Pack: `AKS-REL-002` v1.0.0; digest: `d9e19bb911e79d39e3dcf7a4bddee292b51e092cd78ed42c244516325ddd5349`; inventory-only
- Pack: `AKS-REL-003` v1.0.0; digest: `a210621d7cddb3b84709712cd7daf7b34a221cc97f8d270e4f120bb7998ab569`; inventory-only
- Pack: `AKS-RQ-001` v1.0.0; digest: `64dbc1e4751804bd9f762d1bb37c2dd90d7a1b9884d138034c326136cfaa2e16`; inventory-only
- Pack: `AKS-RQ-002` v1.0.0; digest: `d7f0b7902c6400c9b2be49472a75ee4f949ac164dd6db69f80b2b86f0ff5bd56`; review ratio: 0.4
- Pack: `AKS-RQ-003` v1.0.0; digest: `f4f9e64dabd50569063c8b3264932bc5c0c9f0855032f91347377ef55be1cc3a`; review ratio: 0.9
- Pack: `AKS-SCHED-001` v1.0.0; digest: `420359fdf0a9ef15bef7836a1544ceaa729e2bac461bb97f6a81830c10c5f71b`; inventory-only
- Pack: `AKS-SCHED-002` v1.0.0; digest: `254907cebd33f0d8f68d0693dc70856de408a17924a17eace4c08e8a15d3b9cb`; inventory-only

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
- `AKS-MEM-003` / `AKS-MEM-003-3341c47c3fcf` / `aks-demo` / `orders` / `orders-api`: `existing_candidate_required`, `memory_request_reduction_not_enabled`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_request_observation`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-003` / `AKS-MEM-003-8254c801b850` / `aks-demo` / `checkout` / `checkout-worker`: `existing_candidate_required`, `memory_request_reduction_not_enabled`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_request_observation`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_autoscaler`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-004` / `AKS-MEM-004-00d7ae43891c` / `aks-demo` / `checkout` / `checkout-worker`: `missing_collection_manifest`, `missing_effective_pod_memory`
- `AKS-MEM-004` / `AKS-MEM-004-c4c437ac4806` / `aks-demo` / `orders` / `orders-api`: `missing_collection_manifest`, `missing_effective_pod_memory`
- `AKS-MEM-005` / `AKS-MEM-005-3d79c8125918` / `aks-demo` / `checkout` / `checkout-worker`: `missing_autoscaler_configuration`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`, `unknown_autoscaler`
- `AKS-MEM-005` / `AKS-MEM-005-7e9f9e8c7802` / `aks-demo` / `orders` / `orders-api`: `missing_autoscaler_configuration`, `missing_collection_manifest`, `missing_identity`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-NP-001` / `AKS-NP-001-fe7705a4414e` / `aks-demo` / `-` / `-`: `missing_collection_manifest`, `missing_identity`, `missing_metric_quality`, `short_window`, `stale_metrics`
- `AKS-NP-002` / `AKS-NP-002-528738a6d6d8` / `aks-demo` / `-` / `-`: `missing_capacity_inventory`, `missing_collection_manifest`
- `AKS-NP-003` / `AKS-NP-003-a6b9affd31b7` / `aks-demo` / `-` / `-`: `missing_capacity_inventory`
- `AKS-NP-004` / `AKS-NP-004-a12ffdb4168a` / `aks-demo` / `-` / `-`: `missing_scheduling_inventory`
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
- `AKS-SCHED-002` / `AKS-SCHED-002-f5a209c38b24` / `aks-demo` / `-` / `-`: `missing_scheduling_inventory`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.
