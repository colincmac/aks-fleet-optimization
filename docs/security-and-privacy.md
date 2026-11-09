# Security and privacy

## Security posture

The advisor is read-only. Collection and analysis identities must not have permission to mutate Azure or Kubernetes resources. Remediation is deliberately outside the runtime boundary.

## Threats and controls

| Threat | Control |
|---|---|
| Credential leakage | Workload identity or managed identity; no static cloud credentials |
| Secret collection | Resource allowlist; no Secret reads; contract tests reject forbidden fields |
| Excessive Azure scope | Management-group/subscription allowlist and least-privilege role assignments |
| Untrusted labels/names and report text | Treat collected strings as inert data; never execute report content or interpret it as instructions |
| Cost-data disclosure | Separate RBAC, encryption, retention, and audience-specific report views |
| Cross-tenant confusion | Tenant ID validation and exact resource-ID joins |
| Destructive recommendation | Human review, test plan, rollback criteria, and no runtime mutation capability |
| Supply-chain compromise | Review dependencies and use the repository's dependency scanning, CodeQL and pinned-tool checks; do not bypass integrity failures |

## Data handling

1. Classify snapshots and reports according to the source environment.
2. Encrypt in transit and at rest.
3. Use the shortest retention that supports trend analysis and audit.
4. Redact owner/contact labels from external reports.
5. Log access to reports, not raw application telemetry.
6. The advisor calls no AI model. Any external AI-assisted review needs separate data approval; never upload credentials, raw telemetry or unapproved customer artifacts.

The offline cost path requires no identity, billing API access or
permissions. It accepts only the versioned sanitized projection and reviewed
shares; arbitrary tags, account/contact fields and raw export bodies are not
accepted. Invalid input is reported without echoing financial values. Original
amounts, resource/benefit IDs and untrusted reference text remain in the
financial artifact and require customer-controlled access, encryption and
retention. References are never fetched; declarations and content hashes do
not attest source authenticity. No cost input is sent to AI or an external
system. See [the projection boundary](cost-reconciliation.md).

The local history store validates tenant IDs in the normalized
manifest and every original Azure/Kubernetes/metrics fragment and retained
metadata record, including consistently rehashed imports. Artifact hashes and
locked report replay are integrity/consistency checks, not source attestation.
Tenant selection is not authentication: use a trusted single-writer local
filesystem with customer-controlled access, encryption, residency and retention.
Archived originals may contain owner and resource metadata. No report sharing,
cloud access, deletion, service role or governance authority is introduced.
See [history storage and operations](operations/history.md#storage-and-operations).

## Kubernetes ClusterRole sketch

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

Do not grant access to secrets, exec, attach, port-forward, impersonate, create, update, patch, or delete.

Current scheduling/capacity investigations reuse these approved metadata reads;
they add no roles, Events/log reads, volume-body reads or telemetry installation.
Constraint labels, owner intent and reference text remain untrusted. References
are never fetched; exact-pool intent is not attestation or change approval.
NAP supply needs exact owner/provider identities and observed Auto mode, not
name-only joins or CRD presence. Unknown prerequisites cannot authorize migration.

Memory and reliability assessment requires no additional permissions or Events/log collection. Approved Pod projection includes only current container last-termination reason, exit code and finished UTC time; termination messages, application request payloads, environment values and logs remain excluded. Workload eviction/restart histories come from separately approved bounded metrics, not inferred Kubernetes event bodies. Current LimitRange memory bounds/limit-request ratios are nonsensitive selected metadata. Policy references/digests are untrusted declarations/integrity identifiers and never fetched or treated as approval. Memory-limit and request proposals require separate owner canaries; existing Headlamp request approval explicitly refuses memory-limit records, including mixed imported proposals.
