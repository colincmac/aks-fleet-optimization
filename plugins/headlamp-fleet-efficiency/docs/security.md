# Permissions And Threat Model

The existing collector/analysis runtime remains unchanged and read-only. Governance
is a different service identity and control boundary. Merely loading this plugin
does not grant authority to approve or mutate anything.

| Threat | Control / required server gate |
|---|---|
| Unauthorized approval | Per-object backend SubjectAccessReview for every action; fail-closed capability hints |
| Stolen browser session | Host authentication, short-lived sessions, CSRF/origin checks, audit, independent approvals |
| Recommendation tampering | Publisher/controller-only spec/status writes; generation/evidence/revision binding and admission |
| Stale or superseded evidence | Server clock, expiry, max evidence age, observed generation, source drift re-read |
| Prompt injection / AI HTML | React text rendering; no raw HTML, markdown execution, eval, commands or AI-derived proposals |
| Malicious repo mapping | Backend allowlists for org/repo/base/path/template; reject traversal and untrusted destinations |
| Duplicate PR / decision | Durable idempotency and atomic version checks; reconcile unknown GitHub outcomes |
| Direct workload mutation | No workload write client or role in plugin; GitOps executes separately reviewed repository state |
| Cross-cluster escalation | Management context only; exact target identity is data, never a browser credential context |
| Secret exposure | No GitHub token input/storage; backend GitHub App credentials and managed identity boundaries |
| Audit manipulation | Append-only external audit retention/outbox; separation of reviewer and audit administration |
| Partial evidence | Invalid/incomplete lists fail closed; partial records visibly block approval |
| Supply chain | Lockfile, pinned SDK, immutable CI actions, operator-reviewed plugin packaging |

## Roles

`deploy/headlamp/rbac.yaml` supplies namespace-scoped example roles, without bindings:

- `FleetRecommendationViewer`: get/list/watch recommendation records only.
- `ApplicationRecommendationApprover`: approve/reject/defer/request-observation/exception.
- `PlatformRecommendationApprover`: those decisions plus create-pull-request/cancel.
- `FleetRecommendationAdministrator`: administrative-configuration authorization
  attribute only; does not imply workloads/status/secret write rights.

The custom verbs only become meaningful when a backend checks them. Kubernetes
does not materialize custom action endpoints for these roles. Reviewers cannot
patch `optimizationrecommendations/status` or edit spec. Assign role identities
and required independence in the backend, scoped to approved ownership/repository
mappings. Namespace RBAC alone cannot enforce per-application ownership: use
resourceNames and independent backend ownership checks before production grants.
Do not grant all roles to one user or to the Headlamp service account.

VPA live reads are optional, not part of viewer defaults. A separately approved
Role/RoleBinding can grant get/list in particular source namespaces in the current
management context; cross-cluster access is not requested. No Secret, ConfigMap,
pod exec, workload patch, or source-cluster admin permissions are required.

## Network And Residual Risk

The supplied network policy denies egress for a deliberately labelled dedicated
Headlamp workload until an operator adds precise API/DNS/identity/backend permits.
Do not apply it to a shared Headlamp deployment without reviewing its existing
network requirements. Kubernetes NetworkPolicy cannot allowlist GitHub DNS names;
the future backend requires an approved egress proxy/firewall. The frontend makes
no GitHub API calls. External PR links are HTTPS github.com PR paths only.

The localhost simulator is not a security boundary or an immutable audit store.
Production backend auth, audit integrity, publisher provenance, admission policy,
repository templates and host acceptance have not been independently implemented
or assessed. UI checks never replace these controls.