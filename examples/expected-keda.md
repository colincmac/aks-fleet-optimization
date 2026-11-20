# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `c355d6a14f9f2eca49310fb771c7a61463f4f70eb2c65c4108bc1977acb0be9c`
Profile digest: `59f6462848af4e070c63b15cdf613fd2f35e447b7ab7527d2368263ee7eb188e`

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
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 5
- High or critical: 0
- Blocked findings: 12
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
- `AKS-SCHED-001` subjects evaluated: 1
- `AKS-SCHED-002` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `bde09252872cc375e053c89842961d7f9fc1c90986115b9964c31dbdcc7a4a6c`
- Configuration digest: `392c38b920dc6dcfb1007467ab8603980207c341dad2170cac50c455374f6fc6`
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
- `synthetic` / `AKS-RQ-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
- `synthetic` / `AKS-RQ-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
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
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_total_usage`: not\_collected
  - `restarts`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_total_usage`: not\_collected
  - `restarts`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `restarts`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `restarts`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `restarts`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_request`: not\_collected
  - `memory_limit`: not\_collected
  - `memory_usage`: not\_collected
  - `restarts`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
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
  - `restarts`: not\_collected
- `synthetic` / `AKS-REL-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `restarts`: not\_collected

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.

## Recommendations

### 1. Review HPA/VPA resource interaction for synthetic

- **ID:** `AKS-AS-002-428b77c533dc`
- **Rule:** `AKS-AS-002` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-interaction

A current HPA utilization target uses a resource request that a matching VPA may change. Review the shared request denominator; configuration alone does not establish oscillation or SLO impact. Initial mode affects new Pods rather than continuously updating them.

**Evidence**

- **Owner:** synthetic-owner
- `hpa_uid` = `synthetic-hpa-uid` (kubernetes-api)
- `hpa_name` = `synthetic-hpa` (kubernetes-api)
- `vpa_uid` = `synthetic-vpa-uid` (kubernetes-api)
- `vpa_name` = `synthetic-vpa` (kubernetes-api)
- `container` = `api` (kubernetes-api)
- `resource` = `cpu` (kubernetes-api)
- `hpa_metric_type` = `Resource` (kubernetes-api)
- `average_utilization` = `75` percent (kubernetes-api)
- `vpa_update_mode` = `Recreate` (kubernetes-api)

**Prerequisites**

- Have the owner verify the exact current HPA/VPA UIDs, target workload and container resource policy before interpreting the interaction.
- Distinguish utilization percentages from absolute/external signals; KEDA ownership does not remove a generated HPA&\#x27;s request denominator.

**Proposed actions**

- Review controller responsibilities and resource signals with the owner; no controller change or numeric resource reduction is proposed.

**Validation and safety**

- Use approved operational tools to correlate replica/request history with demand, controller behavior and owner-declared SLOs.
- Validate any separately approved controller change in an isolated canary with explicit availability and rollback criteria.
- Risk: Changing requests can change utilization feedback and replica decisions.
- Risk: External or absolute signals do not eliminate per-Pod throughput risk; no conflict finding is not proof of safe rightsizing.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### 2. Review controller ownership and activation for synthetic

- **ID:** `AKS-AS-004-46a6f7c0c152`
- **Rule:** `AKS-AS-004` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-investigation

KEDA owns the observed generated HPA; these are one scaling chain, not two competing HPAs. Trigger types and metric types are current configuration, not proof of demand or activation. A declared zero minimum is only a scale-to-zero review candidate; verify activation, cold-start, state and availability requirements.

**Evidence**

- **Owner:** synthetic-owner
- `keda_uid` = `synthetic-keda-uid` (kubernetes-api)
- `generated_hpa_uid` = `synthetic-hpa-uid` (kubernetes-api)
- `keda_minimum_replicas` = `0` pods (kubernetes-api)
- `keda_maximum_replicas` = `5` pods (kubernetes-api)
- `scale_to_zero` = `True` (kubernetes-api)
- `polling_interval` = `30` seconds (kubernetes-api)
- `cooldown_period` = `300` seconds (kubernetes-api)
- `trigger_type` = `prometheus` (kubernetes-api)
- `trigger_metric_type` = `AverageValue` (kubernetes-api)
- `generated_hpa_metric_type` = `Resource` (kubernetes-api)
- `generated_hpa_target_type` = `Utilization` (kubernetes-api)

**Prerequisites**

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.
- For KEDA, verify activation, trigger authentication and generated HPA behavior in operator tools; trigger values and credentials are never collected by the advisor.

**Proposed actions**

- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

**Validation and safety**

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.
- Risk: Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.
- Risk: Scale-to-zero can violate cold-start, state, quorum, throughput or availability requirements.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### 3. Review VPA recommendation and policy bounds for synthetic

- **ID:** `AKS-AS-007-e677c293136d`
- **Rule:** `AKS-AS-007` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** autoscaler-investigation

Current VPA status retains resource targets and bounds, not an advisor rightsizing authorization. Metadata freshness does not establish the VPA recommendation&\#x27;s generation time or representative history.

**Evidence**

- **Owner:** synthetic-owner
- `vpa_target_cpu_mcores` = `500.0` mCPU (kubernetes-api)
- `vpa_lower_cpu_mcores` = `200.0` mCPU (kubernetes-api)
- `vpa_upper_cpu_mcores` = `800.0` mCPU (kubernetes-api)
- `vpa_min_allowed_cpu_mcores` = `100.0` mCPU (kubernetes-api)
- `vpa_max_allowed_cpu_mcores` = `1000.0` mCPU (kubernetes-api)
- `vpa_uncapped_cpu_mcores` = `1200.0` mCPU (kubernetes-api)
- `vpa_target_memory_mib` = `512.0` MiB (kubernetes-api)
- `vpa_lower_memory_mib` = `256.0` MiB (kubernetes-api)
- `vpa_upper_memory_mib` = `768.0` MiB (kubernetes-api)
- `vpa_min_allowed_memory_mib` = `128.0` MiB (kubernetes-api)
- `vpa_max_allowed_memory_mib` = `1024.0` MiB (kubernetes-api)
- `vpa_uncapped_memory_mib` = `512.0` MiB (kubernetes-api)
- `container` = `api` (kubernetes-api)
- `vpa_uid` = `synthetic-vpa-uid` (kubernetes-api)
- `vpa_update_mode` = `Recreate` (kubernetes-api)

**Prerequisites**

- Verify exact workload/controller UIDs, approved source scope and owner-declared availability and SLO policy.

**Proposed actions**

- Investigate with the owner; no numeric resource request, replica target or controller change is proposed by this investigation.

**Validation and safety**

- Correlate approved controller/demand history with representative peak load, startup, failover and owner-declared SLOs.
- Canary any separately approved change one dimension at a time; stop promotion on availability or throughput regression.
- Risk: Current settings and sampled extrema do not establish controller health or safe resource/replica reductions.

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

### 5. Review current optimization constraints

- **ID:** `AKS-SCHED-002-f376a3f3d861`
- **Rule:** `AKS-SCHED-002` v1.0.0
- **Severity / confidence:** info / low
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** scheduling

Current probe, topology or voluntary-disruption evidence may constrain scaling, disruption, consolidation or portability. Guarded mode does not authorize a change or generate configuration.

**Evidence**

- `containers_with_missing_probe_types` = `1` containers (kubernetes-metadata)
- `topology_spread_constraints` = `0` current admitted constraints (kubernetes-metadata)

**Prerequisites**

- Ask the workload owner which startup, health, availability, failure-domain and disruption behavior the application requires.
- Verify actual PDB selectors and eligible Pods with approved Kubernetes tooling before relating a budget to a workload.

**Proposed actions**

- Review the observed constraints with the workload and platform owners; guarded mode does not authorize or generate a change.

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

- `AKS-AS-003` / `AKS-AS-003-d511905ba381` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_hpa_replica_history`, `missing_metric`, `missing_metric_quality`
- `AKS-AS-005` / `AKS-AS-005-2a7d3e5faf0e` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_hpa_replica_history`, `missing_metric`, `missing_metric_quality`, `missing_replica_safety_policy`
- `AKS-AS-006` / `AKS-AS-006-59f970c25453` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_hpa_replica_history`, `missing_metric`, `missing_metric_quality`
- `AKS-MEM-002` / `AKS-MEM-002-f3643c0f7e4f` / `aks-synthetic` / `synthetic` / `synthetic`: `autoscaler_interaction_review_required`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `unknown_autoscaler`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-003` / `AKS-MEM-003-1c2d8743035d` / `aks-synthetic` / `synthetic` / `synthetic`: `autoscaler_interaction_review_required`, `existing_candidate_required`, `memory_request_reduction_not_enabled`, `missing_memory_limit_observation`, `missing_memory_peak`, `missing_memory_safety_policy`, `missing_metric`, `missing_metric_quality`, `unknown_autoscaler`, `unknown_qos_class`, `unsupported_memory_history`
- `AKS-MEM-004` / `AKS-MEM-004-77c7af2a65cb` / `aks-synthetic` / `synthetic` / `synthetic`: `unsupported_or_unknown_effective_pod_memory`
- `AKS-MEM-005` / `AKS-MEM-005-ac457d31871f` / `aks-synthetic` / `synthetic` / `synthetic`: `autoscaler_interaction_review_required`, `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`, `unknown_autoscaler`
- `AKS-REL-001` / `AKS-REL-001-f0a3852e4777` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_metric`, `missing_metric_quality`
- `AKS-REL-002` / `AKS-REL-002-d6524572d3bf` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_termination_context`
- `AKS-REL-003` / `AKS-REL-003-e400a56f5eb5` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_metric`, `missing_metric_quality`
- `AKS-RQ-002` / `AKS-RQ-002-3d127b89e9ee` / `aks-synthetic` / `synthetic` / `synthetic`: `autoscaler_interaction_review_required`, `missing_metric`, `missing_metric_quality`, `unknown_autoscaler`, `unknown_metric_aggregation`
- `AKS-RQ-003` / `AKS-RQ-003-add67f939342` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_metric`, `missing_metric_quality`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

