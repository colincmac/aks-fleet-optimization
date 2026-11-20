# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `19561d593cf12c0fc089c1e45ebf42109c0a18d0f3acb973991d5a3e10f04a2d`
Profile digest: `f9effe6175fa48b20f8c93dd1c543b4b93a1713a8f1094b703b90f5f0c9e60ce`

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
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 3
- High or critical: 1
- Blocked findings: 17
- `AKS-AS-001` subjects evaluated: 1
- `AKS-AS-002` subjects evaluated: 1
- `AKS-AS-003` subjects evaluated: 1
- `AKS-AS-004` subjects evaluated: 1
- `AKS-AS-005` subjects evaluated: 1
- `AKS-AS-006` subjects evaluated: 1
- `AKS-AS-007` subjects evaluated: 1
- `AKS-MEM-001` subjects evaluated: 1
- `AKS-MEM-002` subjects evaluated: 1
- `AKS-MEM-003` subjects evaluated: 1
- `AKS-MEM-004` subjects evaluated: 1
- `AKS-MEM-005` subjects evaluated: 1
- `AKS-NP-001` subjects evaluated: 0
- `AKS-NP-002` subjects evaluated: 1
- `AKS-NP-003` subjects evaluated: 0
- `AKS-NP-004` subjects evaluated: 0
- `AKS-REL-001` subjects evaluated: 1
- `AKS-REL-002` subjects evaluated: 1
- `AKS-REL-003` subjects evaluated: 1
- `AKS-RQ-001` subjects evaluated: 1
- `AKS-RQ-002` subjects evaluated: 1
- `AKS-RQ-003` subjects evaluated: 1
- `AKS-SCHED-001` subjects evaluated: 2
- `AKS-SCHED-002` subjects evaluated: 2
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `7f46de3bdf5333ffdefe9bcb7925d90652ece1ea1a40f9ab49bad057cfa9f2b9`
- Configuration digest: `177fa6d6998aabce325d15ff2f27aadaf0e123bf408446b53289f462a1fadc7c`
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
- Collection is partial overall; selected findings are gated independently on their required, complete, correctly scoped sources.

## Recommendations

### 1. Review missing CPU request for synthetic/api

- **ID:** `AKS-RQ-001-a112364a0e6b`
- **Rule:** `AKS-RQ-001` v1.0.0
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

### 2. Review current optimization constraints

- **ID:** `AKS-SCHED-002-13bbbae1c695`
- **Rule:** `AKS-SCHED-002` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** scheduling

Current probe, topology or voluntary-disruption evidence may constrain scaling, disruption, consolidation or portability. The finding is an owner investigation, not a selector match, universal policy judgment or generated configuration.

**Evidence**

- `containers_with_missing_probe_types` = `1` containers (kubernetes-metadata)
- `topology_spread_constraints` = `0` current admitted constraints (kubernetes-metadata)

**Prerequisites**

- Ask the workload owner which startup, health, availability, failure-domain and disruption behavior the application requires.
- Verify actual PDB selectors and eligible Pods with approved Kubernetes tooling before relating a budget to a workload.

**Proposed actions**

- Review the observed constraints with the workload and platform owners; do not generate or apply configuration from this finding.

**Validation and safety**

- Validate probe behavior during startup, steady state, dependency failure and graceful termination using owner-approved tests.
- Validate replica placement and failure-domain behavior before any topology-policy experiment.
- Recheck actual PDB selectors, desired healthy counts and disruptions allowed immediately before any separately approved voluntary disruption.
- Risk: Adding probes without application semantics can cause restart loops or remove healthy endpoints from service.
- Risk: Changing topology or disruption policy can reduce availability, violate storage constraints or increase correlated failure risk.

**Rollback**

- No configuration is generated or applied. Restore any separately approved probe, topology or PDB experiment through the owner&\#x27;s delivery system if validation regresses.

### 3. Review current optimization constraints

- **ID:** `AKS-SCHED-002-f376a3f3d861`
- **Rule:** `AKS-SCHED-002` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** scheduling

Current probe, topology or voluntary-disruption evidence may constrain scaling, disruption, consolidation or portability. The finding is an owner investigation, not a selector match, universal policy judgment or generated configuration.

**Evidence**

- `containers_with_missing_probe_types` = `1` containers (kubernetes-metadata)
- `topology_spread_constraints` = `0` current admitted constraints (kubernetes-metadata)

**Prerequisites**

- Ask the workload owner which startup, health, availability, failure-domain and disruption behavior the application requires.
- Verify actual PDB selectors and eligible Pods with approved Kubernetes tooling before relating a budget to a workload.

**Proposed actions**

- Review the observed constraints with the workload and platform owners; do not generate or apply configuration from this finding.

**Validation and safety**

- Validate probe behavior during startup, steady state, dependency failure and graceful termination using owner-approved tests.
- Validate replica placement and failure-domain behavior before any topology-policy experiment.
- Recheck actual PDB selectors, desired healthy counts and disruptions allowed immediately before any separately approved voluntary disruption.
- Risk: Adding probes without application semantics can cause restart loops or remove healthy endpoints from service.
- Risk: Changing topology or disruption policy can reduce availability, violate storage constraints or increase correlated failure risk.

**Rollback**

- No configuration is generated or applied. Restore any separately approved probe, topology or PDB experiment through the owner&\#x27;s delivery system if validation regresses.

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
- `AKS-MEM-003` / `AKS-MEM-003-1c2d8743035d` / `aks-synthetic` / `synthetic` / `synthetic`: `existing_candidate_required`, `incomplete_collection`, `memory_request_reduction_not_enabled`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_autoscaler`, `unknown_qos_class`, `unknown_source_freshness`, `unsupported_memory_history`
- `AKS-MEM-004` / `AKS-MEM-004-77c7af2a65cb` / `aks-synthetic` / `synthetic` / `synthetic`: `unsupported_or_unknown_effective_pod_memory`
- `AKS-MEM-005` / `AKS-MEM-005-ac457d31871f` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_autoscaler`, `unknown_hpa_configuration`, `unknown_keda_configuration`, `unknown_source_freshness`, `unknown_vpa_configuration`
- `AKS-NP-002` / `AKS-NP-002-d572caa86976` / `aks-synthetic` / `-` / `-`: `missing_capacity_supply`
- `AKS-REL-001` / `AKS-REL-001-f0a3852e4777` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-REL-002` / `AKS-REL-002-d6524572d3bf` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_termination_context`
- `AKS-REL-003` / `AKS-REL-003-e400a56f5eb5` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-RQ-003` / `AKS-RQ-003-add67f939342` / `aks-synthetic` / `synthetic` / `synthetic`: `incomplete_collection`, `missing_metric`, `missing_metric_quality`, `uncollected_scope`, `unknown_source_freshness`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

