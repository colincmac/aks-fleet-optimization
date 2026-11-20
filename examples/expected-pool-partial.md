# AKS Fleet Assessment

Status: partial
Assessment scope: `fleet-assessment`
Input digest: `60e6dea8ee26c0f07bae1ffd092785ef01ef54fdada2bdf300a46c5d54d94294`
Profile digest: `59f6462848af4e070c63b15cdf613fd2f35e447b7ab7527d2368263ee7eb188e`

CPU and memory proposals require separate owner approval; no changes or cash savings are authorized.
Replica-envelope statistics describe a conservative per-replica upper envelope, not workload-total percentiles. Missing or unsupported evidence remains explicit.

## Normalization Gaps

- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `missing-kubernetes-fragment`
- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `missing-metrics-fragment`
- `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic/agentPools/userpool`: `unsupported-pool-evidence`

## Source Receipts

Eligibility requires a complete, fresh matching receipt; completed scope alone is insufficient.

- `azure-inventory` / `00000000-0000-0000-0000-000000000000`: `complete`; completed: `True`; pages complete: `True`; source observed: `2026-10-29T10:00:00+00:00`
- `kubernetes-metadata` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `failed`; completed: `False`; pages complete: `False`; source observed: `unknown`
- Failure: `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic` / `unavailable`
- `prometheus` / `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic`: `failed`; completed: `False`; pages complete: `False`; source observed: `unknown`
- Failure: `/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic` / `unavailable`

# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `guarded`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 0
- Recommendations: 0
- High or critical: 0
- Blocked findings: 4
- `AKS-AS-001` subjects evaluated: 0
- `AKS-AS-002` subjects evaluated: 0
- `AKS-AS-003` subjects evaluated: 0
- `AKS-AS-004` subjects evaluated: 0
- `AKS-AS-005` subjects evaluated: 0
- `AKS-AS-006` subjects evaluated: 0
- `AKS-AS-007` subjects evaluated: 0
- `AKS-MEM-001` subjects evaluated: 0
- `AKS-MEM-002` subjects evaluated: 0
- `AKS-MEM-003` subjects evaluated: 0
- `AKS-MEM-004` subjects evaluated: 0
- `AKS-MEM-005` subjects evaluated: 0
- `AKS-NP-001` subjects evaluated: 0
- `AKS-NP-002` subjects evaluated: 1
- `AKS-NP-003` subjects evaluated: 0
- `AKS-NP-004` subjects evaluated: 0
- `AKS-REL-001` subjects evaluated: 0
- `AKS-REL-002` subjects evaluated: 0
- `AKS-REL-003` subjects evaluated: 0
- `AKS-RQ-001` subjects evaluated: 0
- `AKS-RQ-002` subjects evaluated: 0
- `AKS-RQ-003` subjects evaluated: 0
- `AKS-SCHED-001` subjects evaluated: 0
- `AKS-SCHED-002` subjects evaluated: 0
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `7153922f239a1879da88d09fd0cdd42b672caf6ce4c72938b9a67f5d62e884be`
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

## Data quality warnings

- Metric coverage 0% is below the configured minimum 85%.
- Collection is partial overall; selected findings are gated independently on their required, complete, correctly scoped sources.

## Recommendations

No recommendations were generated.
## Blocked findings

These checks are not actionable recommendations.

- `AKS-NP-002` / `AKS-NP-002-724ea564ef4e` / `aks-synthetic` / `-` / `-`: `capacity_identity_mismatch`, `incomplete_collection`, `missing_capacity_metadata`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-NP-004` / `AKS-NP-004-34a37b03aa5e` / `aks-synthetic` / `-` / `-`: `missing_scheduling_inventory`
- `AKS-SCHED-001` / `AKS-SCHED-001-3376b7339c3a` / `aks-synthetic` / `-` / `-`: `incomplete_collection`, `missing_scheduling_inventory`, `uncollected_scope`, `unknown_source_freshness`
- `AKS-SCHED-002` / `AKS-SCHED-002-c29aa86c3430` / `aks-synthetic` / `-` / `-`: `missing_scheduling_inventory`

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

