# Configuration And Operator Runbook

## Installation Gate

For assessment-only use, install the stock plugin and set up the authenticated feed below. Do not install the review CRD or grant additional Kubernetes permissions. The same feed is shown from each Headlamp cluster context; the feed route authorizes its own audience, independent of the cluster selector.

Only if opting into review, use the management cluster and review the generated CRD, RBAC (no bindings), sample inputs, and optional network-policy template. No script installs them automatically. See the architecture contract before supplying `configureFleetAdvisor({ enableReview: true, namespace, governanceRequest })` and keep engine and governance identities separate. Never add GitHub tokens, kubeconfigs, or source credentials to browser config.

## Schedule Assessment Publication

**Assessments** is independent of the governance backend. It reads a static JSON feed instead of querying a Kubernetes CRD. No operator, VPA access, new cluster permissions or Grafana datasource is required. Try it first with `npm run dev` in the plugin directory and open [the synthetic assessment](http://127.0.0.1:5173/fleet-efficiency/assessments).

1. Use the [scheduled assessment guide](../../../docs/how-to/schedule-assessments.md) to run `assess-batch` in your existing scheduler. It creates one original bundle per cluster and generates the feed in one invocation from fresh saved fragments. A failed batch leaves the previous feed in place. Monitor job failures and compare the displayed UTC evaluation time with your expected cadence.
2. If you already have original bundles and only want to publish them, use the [standalone publisher](../../../scripts/publish_headlamp_assessments.py) with the same compatible advisor package. Pass the approved tenant and repeat `--bundle` for each cluster. The standalone publisher preserves the original evaluation time; it does not make old evidence current. Do not point it at a feed with an active batch writer.
3. Serve only `/advisor-data/assessments.json` and, for batch runs, its generated companion `/advisor-data/assessments-status.json` from authenticated same-origin routes on the Headlamp host. Apply the same reader authorization independently to both routes at the reverse proxy or web server; neither Headlamp sign-in nor cluster selection grants feed access. Use separate audience-scoped endpoints/installations for data that must not be shared. Return `Content-Type: application/json`, `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`. Do not expose originals or publish to a generally accessible plugin-assets route.
4. Open **Fleet Efficiency** in Headlamp. The stock plugin uses `/advisor-data/assessments.json`; no custom build configuration is needed. A host integration that needs a different same-origin JSON path may set `assessmentFeedPath` via `configureFleetAdvisor` before routes mount. Keep other integration options in the same call. Assessments fetches immediately and polls once a minute while open. Refresh rereads the feed; it never runs the assessment. Access errors and malformed data are not an empty healthy fleet.

Headlamp requests the companion only after the feed is admitted. Missing, denied, malformed, or mismatched status is shown as unavailable, without converting a failed feed request into a successful read. A newer recorded failure does not refresh the published evaluation clock. The two files are individually atomically replaced, not one transaction; the browser may temporarily see a mismatch while publishing. A standalone publication has no companion: suspend the scheduled writer and withdraw the old status route if switching that endpoint to standalone publishing.

With the optional [mixed-age policy](../../../docs/how-to/schedule-assessments.md#optional-publish-mixed-age-results), expect a partial batch when only some targets succeed. **Targets in published roster** includes published clusters and failed targets recorded by the feed, including those with **No saved result**. With matching batch status, a failed batch shows zero reporting and labels previously published evaluations **Prior results**. A stale evaluation is marked separately using that cluster's original evaluation time. Without matching status, reporting is unknown. The published roster is not the configured roster if a failed publication could not record a target change. Select a cluster and use **Jump to selected assessment** to focus its details without requesting any additional endpoint.

Serialize publishers for each endpoint and use a local filesystem with atomic replacement. Limit the web origin to read access; ensure its service identity can read the published file through approved permissions or a secure delivery step. A publish uses a restrictive temporary file and does not inherit the previous file's permissions. Set retention for the protected bundle directory independently. The publisher accepts at most 32 clusters and a 4 MiB feed. It checks original hashes, tenant and replay consistency, not source authenticity. The feed contains exact cluster/workload identifiers, namespace and finding text, assessment clocks, blocker codes, and selected evidence and guarded values. It omits original inputs, report metadata objects, dedicated owner/reference fields and financial amounts. Treat both data and rendered views as protected and untrusted.

## Troubleshooting

| Symptom | Checks / safe response |
| --- | --- |
| Missing CRD / 404 | Confirm management context, `optimization.aks.io/v1alpha1` is served and the review CRD is installed; do not broaden permissions blindly |
| Missing VPA | Embedded bounds still render; verify optional VPA API/version and namespace scope; unknown mode is not Off |
| Recommendation missing | Check management namespace, publisher receipts and backend-owned status; CRD creation alone does not populate status |
| Unsupported record | Check generated runtime schema, advisor schema 1.0, required workflow status and exact finding/target scope |
| Assessment feed unavailable | Check that `/advisor-data/assessments.json` (or your approved override) is served as JSON without redirects, authorized for this session, and within the supported size/format |
| Old assessment time | Check scheduler execution and source freshness. Polling does not renew the original evidence clock; a failed publish preserves the last good file |
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

Run package `npm run verify` and `npm run test:e2e`, plus the repository's Python verifier. Unit/component/mock-API coverage is offline and synthetic. Browser tests do not exercise a real GitHub or Kubernetes service. Docker Desktop's local daemon was unavailable during implementation; disposable-cluster acceptance was not run.

Before a production pilot, use a separately approved disposable management cluster:

1. Install the review CRD, an approved VPA CRD and narrow test-only role bindings.
2. Publish synthetic recommendations using a test controller that writes status through the status subresource and retains actual assigned UID/resourceVersion.
3. Include a target Deployment as evidence only, two VPA objects for one target, all workflow/validation outcomes, missing/denied APIs, stale, expired and superseded records. Do not give the plugin any write access to that Deployment.
4. Load the built plugin in the exact supported host. Check namespace list/detail, management-context isolation and missing-CRD/error states.
5. Use a test governance service with a fake GitHub provider to verify independent SAR decisions, audit atomicity, conflict/CSRF denial and duplicate PR prevention.
6. Verify no target request, VPA, HPA, KEDA, NodePool or AKSNodeClass changes from any UI action. Test denied actions by submitting directly, not just hiding UI.

Do not run these operations against an existing production kube-context. Live access, role bindings and repository mappings require explicit operator approval.
