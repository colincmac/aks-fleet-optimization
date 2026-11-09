# Configuration And Operator Runbook

## Installation Gate

Use the management cluster, not every source cluster. Review the generated CRD,
RBAC (no bindings), sample inputs and optional network-policy template. No script
in this package installs them automatically. Read-only engine identities must
remain separate from a future governance publisher/controller identity.

The plugin has no configured production backend by default. See the architecture
contract before supplying an authenticated same-origin `governanceRequest`.
Never add GitHub tokens, kubeconfig files or source credentials to browser config.
The default namespace is `fleet-efficiency-system`; build-time integration can
change it via `configureFleetAdvisor` before routes mount. Role changes in the
standalone preview are synthetic and are absent from the actual plugin.

## Troubleshooting

| Symptom | Checks / safe response |
|---|---|
| Missing CRD / 404 | Confirm management context, `optimization.aks.io/v1alpha1` is served and the review CRD is installed; do not broaden permissions blindly |
| Missing VPA | Embedded bounds still render; verify optional VPA API/version and namespace scope; unknown mode is not Off |
| Recommendation missing | Check management namespace, publisher receipts and backend-owned status; CRD creation alone does not populate status |
| Unsupported record | Check generated runtime schema, advisor schema 1.0, required workflow status and exact finding/target scope |
| Approval disabled | Inspect freshness, source drift, completeness, required checks, independent role and observed generation; backend absence denies all |
| Authorization denied | Backend must re-evaluate the exact record/action; UI visibility never grants access; verify ownership/SAR rather than using admin |
| PR failed | Check backend safe error, repository allowlist, current approvals and existing PR/idempotency reservation before retrying |
| Expired | Generate/review fresh evidence; do not edit the browser clock or override expiry locally |
| Superseded | Open the replacement generation through the refreshed list and re-review inputs; approvals do not transfer |
| Stale/partial | Recollect complete approved evidence; missing telemetry is not zero; an empty list is not fleet health |
| Metrics unavailable | Read embedded values and collection timestamp; no synthetic chart fallback in the plugin |
| Validation stuck | Verify deployment identity, baseline, observation window and backend telemetry; PR merge is not a pass |
| Version mismatch | Rebuild with the pinned SDK and test on the operator's exact Headlamp/AKS Desktop release |
| Concurrent decision | Refresh and review changed resourceVersion/generation/evidence; do not automatically resubmit a changed decision |

## Verification

Run package `npm run verify` and `npm run test:e2e`, plus the repository's Python
verifier. Unit/component/mock-API coverage is offline and synthetic. Browser tests
do not exercise a real GitHub or Kubernetes service. Docker Desktop's local daemon
was unavailable during implementation; disposable-cluster acceptance was not run.

Before a production pilot, use a separately approved disposable management cluster:

1. Install the review CRD, an approved VPA CRD and narrow test-only role bindings.
2. Publish synthetic recommendations using a test controller that writes status
   through the status subresource and retains actual assigned UID/resourceVersion.
3. Include a target Deployment as evidence only, two VPA objects for one target,
   all workflow/validation outcomes, missing/denied APIs, stale, expired and
   superseded records. Do not give the plugin any write access to that Deployment.
4. Load the built plugin in the exact supported host. Check namespace list/detail,
   management-context isolation and missing-CRD/error states.
5. Use a test governance service with a fake GitHub provider to verify independent
   SAR decisions, audit atomicity, conflict/CSRF denial and duplicate PR prevention.
6. Verify no target request, VPA, HPA, KEDA, NodePool or AKSNodeClass changes from
   any UI action. Test denied actions by submitting directly, not just hiding UI.

Do not run these operations against an existing production kube-context. Live
access, role bindings and repository mappings require explicit operator approval.