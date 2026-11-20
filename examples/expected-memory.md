# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `7d4d9a790e0fc8a73d204620eb9943faf06b87b00942907dae73aebdd6fcff13`
Profile digest: `59f6462848af4e070c63b15cdf613fd2f35e447b7ab7527d2368263ee7eb188e`

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
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 6
- High or critical: 0
- Blocked findings: 5
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
- Snapshot digest: `4c9554d9b73ddfa22abde0a18455411ba13f51de68474b1f2364b4f14c6d1464`
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
  - `memory_total_usage`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-005` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `memory_total_usage`: not\_collected
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-003` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-003` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-002` / `baseline`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
  - `observed_replicas`: not\_collected
  - `unschedulable_pods`: not\_collected
  - `evictions`: not\_collected
- `synthetic` / `AKS-MEM-002` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared
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
- `synthetic` / `AKS-REL-001` / `guarded`: `unknown` (`identity-enriched`).
  - `profile.versions`: versions\_not\_declared

## Recommendations

### 1. Validate memory request candidate for synthetic/api

- **ID:** `AKS-MEM-003-1c2d8743035d`
- **Rule:** `AKS-MEM-003` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** memory-efficiency

The upstream memory request candidate is not below the accelerator safety floor and passed the required admission, QoS, reliability and owner-policy gates.

**Evidence**

- **Owner:** synthetic-owner
- **Memory request:** 512.0 to 313.0 MiB per replica
- `request_memory_mib` = `512.0` MiB (synthetic)
- `limit_memory_mib` = `1024.0` MiB (synthetic)
- `usage_memory_p95_mib` = `160.0` MiB (synthetic)
- `usage_memory_p99_mib` = `192.0` MiB (synthetic)
- `memory_oom_events` = `0` events (synthetic)
- `restart_events` = `0` events (synthetic)
- `memory_observation_basis` = `pod` (normalized-history)
- `memory_membership_digest` = `None` (approved-binding)
- `current_replicas` = `1` pods (current-kubernetes-projection)
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

- Review the validated upstream 313.0 MiB candidate for this container only; keep limits unchanged and obtain owner approval.

**Validation and safety**

- Canary only the approved memory request under startup, peak load and failover; confirm the limit and QoS remain unchanged.
- Compare OOM, restarts, evictions, placement and owner-declared SLOs with the pre-change baseline before promotion.
- Risk: Working-set samples can omit relevant memory and short peaks.
- Risk: Lower requests reduce eviction protection and can increase node pressure or change placement despite unchanged Burstable QoS.

**Rollback**

- If OOM, restarts, evictions or owner-declared SLOs regress, stop promotion and restore the original 512.0 MiB memory request through the owning delivery pipeline; keep all other settings unchanged.

### 2. Review CPU request for synthetic/api

- **ID:** `AKS-RQ-002-3d127b89e9ee`
- **Rule:** `AKS-RQ-002` v1.0.0
- **Severity / confidence:** medium / high
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** workload-rightsizing

The upstream CPU request candidate is not below the accelerator safety floor and passed the required evidence gates; validate it through a separately approved canary.

**Evidence**

- **Owner:** synthetic-owner
- **CPU request:** 1000.0 to 500.0 mCPU per replica
- `cpu_p95_to_request_ratio` = `0.1` ratio (synthetic)
- `cpu_observation_basis` = `pod` (normalized-evidence)
- `potential_cpu_request_reduction` = `500.0` mCPU per replica (derived)

**Prerequisites**

- Confirm the metric window contains peak and business-critical periods.
- Review P99 usage, throttling, startup and failover behavior.

**Proposed actions**

- Review the validated upstream request candidate and rollback criteria before any customer-owned PR.

**Validation and safety**

- Run VPA in Off mode and compare recommendations.
- Canary an independently approved request change and verify SLOs under load.
- Risk: Historical usage might not represent future peaks.
- Risk: Lower requests can change placement and noisy-neighbor behavior.

**Rollback**

- Restore the previous CPU request of 1000.0 mCPU in source configuration through the owning delivery pipeline.
- Stop promotion if SLOs, throttling, OOM or restarts regress; remeasure before proposing another change.

### 3. Review memory safety for synthetic/api

- **ID:** `AKS-MEM-002-f3643c0f7e4f`
- **Rule:** `AKS-MEM-002` v1.0.0
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
- `memory_observation_basis` = `pod` (normalized-history)
- `memory_membership_digest` = `None` (approved-binding)
- `current_replicas` = `1` pods (current-kubernetes-projection)
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

### 4. Review effective Pod memory for synthetic

- **ID:** `AKS-MEM-004-77c7af2a65cb`
- **Rule:** `AKS-MEM-004` v1.0.0
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
- `memory_limit_configuration_digest` = `feac46340b0fa9a9552481f67192bf37d5a234972bc8c57f471e965467f1998e` (current-configuration)

**Prerequisites**

- Verify admitted quantities, native sidecar ordering and overhead.

**Proposed actions**

- Review accounting only; no request or limit change is proposed.

**Validation and safety**

- Compare the current effective request with the admitted Pod configuration.
- Risk: Current accounting does not establish historical usage or packing feasibility.

**Rollback**

- If a separately approved change regresses guardrails, stop promotion and revert its Git commit through the owning delivery pipeline.

### 5. Review capacity management and NAP prerequisites

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

### 6. Review current optimization constraints

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

- `AKS-AS-005` / `AKS-AS-005-2a7d3e5faf0e` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_replica_safety_policy`
- `AKS-AS-007` / `AKS-AS-007-e677c293136d` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_vpa_policy_bounds`
- `AKS-MEM-005` / `AKS-MEM-005-ac457d31871f` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_memory_limit_policy`, `missing_metric`, `missing_metric_quality`
- `AKS-REL-002` / `AKS-REL-002-d6524572d3bf` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_termination_context`
- `AKS-REL-003` / `AKS-REL-003-e400a56f5eb5` / `aks-synthetic` / `synthetic` / `synthetic`: `missing_metric`, `missing_metric_quality`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

