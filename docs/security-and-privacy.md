# Security and privacy

## Security posture

The advisor is read-only. Collection and analysis identities must not have permission to mutate Azure or Kubernetes resources. Remediation is deliberately outside the runtime boundary.

The advisory import/admission safety test explicitly permits Pydantic's exact `os.getenv("PYDANTIC_DISABLE_PLUGINS")` read of non-secret framework configuration, including its normal default behavior. Within that guarded test, all other `os.getenv` calls remain forbidden, and the existing network, file, home-directory and subprocess guards are unchanged. This test-only exception does not authorize credential discovery, collection of workload environment values or plugin I/O, and does not change production configuration or disable validation.

## Threats and controls

| Threat | Control |
| --- | --- |
| Credential leakage | Workload identity or managed identity; no static cloud credentials |
| Secret collection | Resource allowlist; no Secret reads; contract tests reject forbidden fields |
| Excessive Azure scope | Management-group/subscription allowlist and least-privilege role assignments |
| Untrusted labels/names and report text | Treat collected strings as inert data; never execute report content or interpret it as instructions |
| Cost-data disclosure | Separate RBAC, encryption, retention, and audience-specific report views |
| Cross-tenant confusion | Tenant ID validation and exact resource-ID joins |
| Destructive recommendation | Human review, test plan, rollback criteria, and no runtime mutation capability |
| Supply-chain compromise | Review dependencies and use the repository's dependency scanning, CodeQL and pinned-tool checks; do not bypass integrity failures |

## Data handling

Optional retained-assessment quality export uses bounded original-artifact reads and locked replay with an explicit tenant and original fingerprint binding. It adds no source client, credential acquisition, endpoint request or data collection. The sidecar and Grafana text panel contain protected identity/source/quality context and require the assessment's approved audience, storage and retention. The CLI regenerates context from originals, never trusts an imported sidecar, and redacts admission errors. Logical source names, hashes, matched records and a live panel do not authenticate a datasource or establish change approval. Live Grafana quality remains unknown; untrusted identity/reason text is escaped in the generated Markdown panel.

The [retained Fleet Evidence export](fleet-insights.md#export-a-protected-grafana-evidence-snapshot) likewise embeds protected cluster, fingerprint, run and resource context in the dashboard JSON. It publishes nothing and does not include raw bundles, workload identities, or arbitrary query execution. Treat the dashboard and its JSON alike as private after import; disable public sharing and verify the denied path directly for the intended audience.

The SDK-only [saved controller timeline](data-contracts.md#optional-saved-controller-timeline) accepts approved projections in memory; it never fetches original references, collects telemetry, or opens network or file connections. The caller must enforce byte limits before parsing and authorize the producer, originals, storage, and audience independently of structural qualification. Exact identities, clocks, values, and opaque references are protected assessment data; do not publish them in shared metrics, generic feeds, or AI exports. Treat references as inert and do not forward raw validation errors across a trust boundary.

The [current VPA review](data-contracts.md#optional-current-vpa-review) has the same SDK-only boundary. A status/policy digest binds a separately reviewed generation observation but cannot authenticate it. Do not copy raw workload/VPA objects, broaden Kubernetes permissions for optional evidence, or expose scope and numeric facts to a wider audience.

Optional SDK [current-container-attempt projection](data-contracts.md#optional-current-container-attempts) consumes an already approved metadata snapshot and caller-supplied Pod dictionary without network access, new permissions or default collection changes. It returns allowlisted identities/clocks/status and a digest, never raw container IDs or arbitrary status prose. The caller must enforce data approval and input/storage budgets before supplying native data; do not broaden Pod exports to obtain it. Exact field/identity consistency does not authenticate the payload, establish transaction/version/time equivalence with the snapshot or qualify freshness. Returned digests and exact identities are still protected correlatable data, not anonymization. First startup, readiness and post-startup demand remain unknown; no result permits remediation or a new engineering proposal.

Optional SDK [scheduling completeness audit](data-contracts.md#optional-scheduling-completeness-audit) revalidates existing sanitized metadata without collecting additional fields. Reservation coverage deliberately includes all namespaces and system/DaemonSet Pods; a display exclusion cannot remove competitors from arithmetic. Exact identities, source receipts and a metadata digest remain protected assessment data, not anonymization or source attestation. Do not treat imported audit JSON as an admission token: regenerate from approved original metadata with explicit clocks/age policy and existing input/record budgets. Fit is always blocked, independent of observed reservation totals, and no free-capacity, placement, disruption or mutation authority is implied.

Optional `ai export --allow-ai-export --allow-ai-measurements` is a distinct local data-release decision for exactly four admitted CPU/memory measurements and protected quality bindings. Ordinary summary export remains unchanged. Values without exact original identity/query/profile/receipt/quality/statistic agreement stay withheld. Raw names/UIDs, owner/SLO/report prose, source references/expressions, financial data, proposal values and executable fields are excluded. The richer package still needs approved access, storage, encryption, retention and audience controls; digests are not anonymization. `validate_ai_measurements` regenerates from original artifacts, not trusted package hashes. Local export consent does not permit provider disclosure or model invocation.

Optional `order-cost-review` reads approved financial observations and original assessment bundles, with exact tenant/fingerprint/period bindings, locked replay and fresh requalification. Its output remains protected financial data. It refuses overlapping/incomparable inputs, preserves other attribution buckets and never alters engineering findings or produces savings. Pure SDK context sorting does not authenticate its caller-supplied source. No financial endpoint or identity acquisition is added.

The opt-in native scheduling-shape SDK accepts separately approved caller data without broadening default collection. Only the closed field/presence projection leaves that boundary; raw environment values, handlers, addresses, claim/storage bodies, messages and arbitrary annotations/labels do not. Supplied-native source binding remains unverified, and fit remains blocked. Current PDB selector evidence similarly treats dropped labels as unknown and does not authorize disruption; literal NAP budget context does not evaluate activation or effectiveness.

Optional scheduling shape diagnostics regenerate that projection from approved originals, preserve the original audit and expose only closed feature/condition/issue classifications alongside protected identities. A simple supplied shape cannot remove producer/scheduler admission blockers or clear source/reservation gaps. No imported diagnostic is an admission token, and no fit, placement or mutation authority is introduced.

The SDK-only [pending NAP constraint review](data-contracts.md#optional-pending-nap-constraint-review) uses the same protected, sanitized originals and adds no source or permissions. Its exact Pod, Node, NodeClaim and NodePool identities and their quantities must stay within the approved assessment audience. An observed exclusion is not permission to change placement controls; a namespace PDB count or DaemonSet subtotal conveys no disruption approval.

Optional `review-placement` performs only bounded local reads of an approved saved fragment bundle and exclusive creation of one review file. It selects one exact tenant/cluster, reruns sanitized-projection and source admission, preserves original clocks/digests, and exposes protected Pod/Node UIDs with closed constraint statuses rather than raw selector, taint or toleration values. Label omissions remain unknown, complexity excess is refused rather than truncated, and redacted errors do not echo sensitive input. Current constraint matches never authenticate the source or remove producer/scheduler blockers; there is no live reader, identity acquisition, placement/remediation action or savings claim.

The separately approved `SchedulingKubernetesSdkReader` / `collect_scheduling()` API is an explicit opt-in injected-reader path, not a change to default collection or a grant of environment access. It reuses the existing TLS/GET-only allowlist and bounded page/retry/response controls, validates the original fingerprint before other resource lists, and records execution-derived per-list clocks/versions/completion. Only closed approved shape facts and the exact Pod/Node `karpenter.sh/do-not-disrupt` annotation state leave this boundary. All other annotation text and excluded object bodies are discarded; old/omitted annotation maps remain unknown. The pure `project_disruption_protection` SDK has the same exact-key boundary. Configured values never establish active protection or disruption/removal feasibility. Callers must separately approve any transient handling of full native API objects, access/storage/retention and actual source compatibility. No identity acquisition, live command, permission expansion, write, watch or installation is added. A saved execution record is neither source authentication nor proof the reader ran, and fit remains blocked.

1. Classify snapshots and reports according to the source environment.
2. Encrypt in transit and at rest.
3. Use the shortest retention that supports trend analysis and audit.
4. Redact owner/contact labels from external reports.
5. Log access to reports, not raw application telemetry.
6. The advisor calls no AI model. Any external AI-assisted review needs separate data approval; never upload credentials, raw telemetry or unapproved customer artifacts.

The offline financial path requires no identity, billing API or endpoint permissions. Normalized ledger/allocation projections reject arbitrary tags, account/contact fields, credentials, endpoint URLs and raw export bodies. The separate optional `convert-focus` adapter transiently parses approved local native CSV/manifest files and retains only allowlisted financial fields and audit digests/counts; excluded columns, raw manifest content and local paths never enter its output or error text. Use it only where local handling of those raw inputs is approved; it never downloads or logs them. Managed AKS Cost Analysis is treated as reviewed saved upstream evidence, not a public OpenCost endpoint. Invalid input is reported without echoing financial values. Original amounts, resource/benefit IDs, candidate references and untrusted source text remain in protected artifacts and require customer-controlled access, encryption and retention. References are never fetched; profile declarations and hashes do not attest authenticity. No financial or candidate input is sent to AI or an external system. See [financial profiles](financial-source-profiles.md) and [the projection boundary](cost-reconciliation.md).

The local history store validates tenant IDs in the normalized manifest and every original Azure/Kubernetes/metrics fragment and retained metadata record, including consistently rehashed imports. Artifact hashes and locked report replay are integrity/consistency checks, not source attestation. Tenant selection is not authentication: use a trusted single-writer local filesystem with customer-controlled access, encryption, residency and retention. Archived originals may contain owner and resource metadata. No report sharing, cloud access, deletion, service role or governance authority is introduced. See [history storage and operations](operations/history.md#storage-and-operations).

Direct artifact comparison applies the same bounded original-file, tenant and replay checks to both inputs without creating a history store or changing files. It adds no identity acquisition, network access, retention service or approval authority. Local artifact access and protection remain customer-controlled; names and report content stay inert data.

Fleet history additionally bounds the selected bundle count and total retained input payload; every sample still undergoes original tenant and locked replay admission. Peer groups and fingerprints do not grant access, imply portability or authenticate sources. Ledger-free allocation projection is protected source normalization only: it has no tenant/observation-clock admission and cannot qualify cost-based prioritization or financial conclusions. Row shares remain on the authoritative-ledger path.

The separate allocation-observation wrapper requires explicit tenant/subscription/cluster/fingerprint and genuine source-observation declarations. Qualification uses bounded link-free reads and original assessment hash/tenant/configuration/locked replay checks, preserving partial/stale/foreign-source limitations and lower-level identity semantics. It is not source authentication, financial reconciliation, permission to access billing data or authority to change severity, priority or eligibility. Financial amounts/references remain protected and are never forwarded to AI; savings remain null.

Optional [AI summary handoff](operations/ai-evidence.md) requires explicit local export consent and preserves the no-model/no-write-tool boundary. It emits only pseudonymous deterministic finding summaries and opaque blocker digests after original-artifact integrity and replay checks. Raw measurements, identifiers/names, owner/contact text, source references, report prose, metadata, cost evidence, proposal values and actions are withheld. Hashing is not anonymization, encryption, source authentication or permission to upload data; packages still need customer-approved storage and audience controls.

Explanation validation regenerates packages from original artifacts and checks copied facts, citations and clocks; the only accepted state is `unverified_interpretation`. Free-form interpretation and declared provider metadata remain untrusted, can be false or malicious, and must never be executed or treated as approval. No AI provider/tool/credential client is introduced. The existing inert-import/admission guards also cover this path without broadening their exact Pydantic configuration-read exception.

Checklist validation additionally binds a caller-controlled package/scope/objective intent and closed cited review-step types. The accepted state remains `unverified_checklist`; required test/abort, rollback and no-change review steps do not prove that a test or rollback is valid. No commands, scripts, patches, target values, approval fields, new export data or write tools are admitted. Free-form interpretation stays inert, declared intent is not authorization, and original-artifact regeneration and byte/time limits remain mandatory.

Experiment validation separately binds a caller-selected dimension/controller category, exact summary-package scope and cited explanation to closed staged checks, alternatives and unresolved prerequisites. Original-artifact regeneration and the existing byte/time/citation boundaries still apply. The only result is `unverified_experiment` with no execution authority; no numeric targets, executable configuration, model client, extra export fields or provider consent are added. Hypothesis and interpretation remain arbitrary untrusted prose, even when structurally accepted. Closed checks are review prompts, not validated SLO/abort/rollback policies or evidence that a change is safe.

Optional SDK [DaemonSet generation/status projection](data-contracts.md#optional-daemonset-generation-and-status) accepts separately approved caller-supplied native DaemonSets and original metadata, without source access, credentials, additional permissions or default collection changes. Only exact identity/version/generation fields, the two approved counters, original clocks/receipts/digest and machine gaps leave the projector; templates, arbitrary annotations, messages and other native fields are discarded. Enforce input budgets and protect returned identities, versions and digests as correlatable assessment data, not anonymization. Exact approved-projection equality and supplied matching generations neither authenticate the source nor prove transaction/time binding, completed reconciliation, desired Node membership or disruption feasibility. Imported JSON is not an admission token, and no assessment/rule integration, live reader or write capability is added.

## Kubernetes ClusterRole sketch

Optional saved historical contribution and fleet-context reviews add no collection or identity acquisition. Exact Node/Namespace/workload IDs, opaque owner references, source receipts and digests remain protected correlatable data. Complete supplied rosters and declared ownership are not source authentication. Historical/fleet context stays outside default AI packages. Source profiles, units and CPU/memory quality remain independent, including aggregate overflow; missing values never become zero.

Optional storage and DaemonSet reviews consume separately approved saved native objects under bounded input/output and comparison-work limits. Storage projection discards raw volume handles/paths, CSI attributes/Node IDs, Secret references, parameters, mount options and token-request fields; only selected exact bindings, modes, limits and topology/predicate results leave the boundary. DaemonSet templates yield closed controller-selection results, not persisted environment/handler/annotation bodies. The separate NAP policy reference uses a bounded parser and does not execute configuration or attest deployed controller/feature-gate support. Source clocks are not fabricated from local capture time. All three reviews preserve unverified admission and unknown full fit/disruption/removal rather than providing action authority. No default collector/role expansion is included.

Startup history and scheduler calculations add only opt-in offline handling of separately approved saved inputs, not new live collection or access. Startup projection retains exact closed identity/clocks/readiness/counters plus digested runtime IDs and original receipts; raw native frames are discarded. Scheduler CLI transiently reads approved native Pod/Node dictionaries under a combined byte budget and returns closed diagnostics/resource comparisons, never raw environment, addresses, ports, storage bodies or annotations. Readiness bounds and source digests do not authenticate history, and satisfied resource dimensions do not certify scheduler fit. Default AI exports and their richer-data consent boundaries are unchanged; these histories are not disclosed to a provider. Original saved assessments remain protected data with caller-owned input approval, access, encryption and retention.

Fixed-window Prometheus source acceptance adds an explicit `--allow-live` boundary without changing offline readiness or default collection. The CLI validates the protected plan, canonical configuration digest, installed expressions, source/profile/version, exact cluster label value and expected identity roster before constructing `PrometheusHttpReader`. Generic bearer-environment credentials remain refused by the CLI; approved injected readers are a Python API responsibility. HTTP/TLS/redirect/proxy/size/series controls remain those of the existing reader. Output excludes endpoint and credential data and reduces read failures to closed codes, but labels, exact cluster IDs, fingerprints and digests remain protected correlatable data. An accepted result is neither endpoint authentication nor ongoing source attestation.

Portable experiment, outcome and value bundles are local exclusive writes under caller-selected paths. Handoff preparation uses original artifact integrity, tenant binding and locked replay; bundle readers reject links, missing/extra files, byte excess and digest/status substitution. Owner/reviewer/change/test references and hypothesis text are untrusted inert data, not contact verification, authorization or executable instructions. Markdown escapes them, and no command contacts a ticket system or delivery tool. Operator-declared completion is not proof of execution. Value validation never changes rule facts/order and currently refuses positive financial values without a qualified adapter; financial evidence remains excluded from optional AI fields.

The exact resource list depends on the enabled rules. Start narrowly:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aks-fleet-efficiency-reader
rules:
  - apiGroups: [""]
    resources: ["namespaces", "nodes", "pods", "resourcequotas", "limitranges"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
    verbs: ["get", "list"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list"]
  - apiGroups: ["scheduling.k8s.io"]
    resources: ["priorityclasses"]
    verbs: ["get", "list"]
  - apiGroups: ["node.k8s.io"]
    resources: ["runtimeclasses"]
    verbs: ["get", "list"]
```

Optional collection needs separately approved `get/list` for VPA (`autoscaling.k8s.io/verticalpodautoscalers`), KEDA (`keda.sh/scaledobjects` and `scaledjobs`), and supported NAP objects (`karpenter.sh/nodepools`, `nodeclaims`, `karpenter.azure.com/aksnodeclasses`). Do not grant unrelated custom-resource access or create these roles automatically. Discovery access and cluster/namespace scope remain operator-approved. The reader starts no watches and requires no write-capable access review.

Kubernetes approved list responses may transiently contain excluded pod fields during JSON decoding because spec-field projection is not available server-side. The SDK reader projects them immediately before returning to the collector; no environment values, raw object payloads, or credentials are persisted or logged. For stricter customer boundaries, require an approved sanitized reader/export. Never enable SDK debug logging, disable TLS verification, or provide an impersonating client to bypass this boundary.

Probe collection retains only whether liveness, readiness or startup probes are present and their nonsensitive timing/threshold integers. Probe paths, hosts, headers, ports, gRPC service names and exec commands are discarded during the same projection boundary and never enter snapshots or reports.

Probe timing/threshold fields require strict integers: initial delay may be zero, while periods, timeouts and thresholds must be positive. Strings, lists, booleans, fractional values and invalid negative values are rejected before persistence in both live projection and sanitized-export admission; errors do not echo their content.

Do not grant access to secrets, exec, attach, port-forward, impersonate, create, update, patch, or delete.

Current scheduling/capacity investigations reuse these approved metadata reads; they add no roles, Events/log reads, volume-body reads or telemetry installation. Constraint labels, owner intent and reference text remain untrusted. References are never fetched; exact-pool intent is not attestation or change approval. NAP supply needs exact owner/provider identities and observed Auto mode, not name-only joins or CRD presence. Unknown prerequisites cannot authorize migration.

Memory and reliability assessment requires no additional permissions or Events/log collection. Approved Pod projection includes only current container last-termination reason, exit code and finished UTC time; termination messages, application request payloads, environment values and logs remain excluded. Workload eviction/restart histories come from separately approved bounded metrics, not inferred Kubernetes event bodies. Current LimitRange memory bounds/limit-request ratios are nonsensitive selected metadata. Policy references/digests are untrusted declarations/integrity identifiers and never fetched or treated as approval. Memory-limit and request proposals require separate owner canaries; existing Headlamp request approval explicitly refuses memory-limit records, including mixed imported proposals.
