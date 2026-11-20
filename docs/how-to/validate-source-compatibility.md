# Check Whether Your Data Can Answer The Question

[Documentation home](../README.md) | [Next: bounded pilot](plan-a-bounded-pilot.md)

## Goal And Prerequisites

This is the human review before a customer assessment, not an automatic test or permission to query a service. Platform, monitoring and security owners should review one selected question together. Read the [evidence lesson](../learning/04-evidence-quality-and-historical-identity.md) first. No command, credential or customer endpoint is needed to read this guide.

The exact formats and supported cases remain in the [source compatibility reference](../source-compatibility.md). Here **source** means the inventory, configuration, monitoring system or saved file supplying assessment data, not Python code.

## 1. Select A Question And Supported Input Shape

Start with [check selection](choose-recommendation-packs.md). Current placement or configuration reviews can use approved fresh inventory without 30 days of metrics. Historical resource suggestions need much more. Do not request everything merely because the cluster has a monitoring dashboard.

## 2. Review Four Different Questions

| Question | Required owner answer | What it does not prove |
| --- | --- | --- |
| Can the approved runner read the input? | Reviewed endpoint/exporter identity, read-only effective rights and supported network/TLS path | Correct metric meaning, complete history or change safety |
| Are the required fields and units present? | Definitions for each selected metric/configuration field; reviewed source/producer versions | That similarly named recordings have the right meaning |
| Does history identify the actual objects? | Exact historical workload/Pod/node/controller identifiers and required complete membership | That today's objects or matching display names represent deleted members |
| Is the period and quality sufficient? | Actual retained range, resolution, gaps, fresh tail and representative demand/reliability information | That retention duration alone captures every peak or satisfies every pack |

Permissions must be reviewed including inherited/group grants. Read-only code is not proof that the identity lacks write privileges. Do not grant stronger roles because a source read fails.

## 3. Record A Decision Per Question

Use the [authoritative pilot worksheet](../source-compatibility.md#pilot-evidence-worksheet) in protected customer storage. Include the owner, review date, scope, evidence reference, unresolved fact and next action. These human decisions do not change the CLI readiness status or certify a source.

**Example: fictional source review.** Current metadata is approved and complete. CPU samples have Pod names but no required historical UID enrichment. Record current-configuration review as a supported subset and the historical identity gap as blocked/unknown as appropriate. Do not attach today's UIDs to old samples.

Ordinary name-only telemetry can support unresolved baseline measurements under its supported profile. It does not become workload-bound history or a numeric target. New recordings cannot backfill missing past observations.

## Validate Financial And Recommendation Sources Separately

Financial and recommendation inputs have different contracts from Prometheus metrics. For a ledger, verify the Cost Management or FOCUS profile/version, cost basis, exact Azure resource IDs, period, currency, charge categories, completeness and historical resource bindings. For AKS Cost Analysis/OpenCost/Kubecost attribution, verify producer version, granularity, pricing basis, allocation policy and idle/shared/system/service treatment; aggregate names do not become historical workload UIDs.

For VPA or characterized vendor candidates, verify exact cluster/workload/container identity, source and producer version, observation time, current and recommended value, unit and protected reference. A candidate is input to guarded validation, not approval. Azure Advisor findings should be recorded once per exact source/recommendation/cluster identity to avoid duplicate enablement analysis; foreign cluster scope and duplicate identities are rejected, and findings are not converted into per-container numeric targets. AKS Cost Analysis remains reviewed financial attribution under its own profile rather than recommendation annotation.

Use the [financial source profile matrix](../financial-source-profiles.md). Unsupported versions or semantics remain blocked; do not relabel them as a nearby profile.

## 4. Stop Or Narrow The Pilot When Needed

Stop on unverified cluster identity, unexpected privileges, forbidden fields, unsupported private-network/proxy/certificate requirements or missing consent. The CLI uses approved sanitized Kubernetes exports; it does not load kubeconfig plugins. SDK decoding may transiently receive excluded Pod fields before projection. If that is prohibited, use an approved sanitized reader/export or stop.

Do not disable TLS, open an unapproved tunnel, dump arbitrary labels/objects, install telemetry or fabricate a complete receipt to resolve a gap. Use synthetic failure cases unless actual failure probes are separately authorized.

## Optional Demo Rehearsal

Use this procedure only in your own isolated demo environment. These are operator actions, not commands the advisor executes or permission for an agent to deploy resources. Keep the existing approved kubeconfig, explicit context, verified TLS and read-only assessment identity. A separate operator identity owns any application deployment, monitoring changes and cleanup. Do not deploy the advisor into the cluster, grant it write access, or install an observer to complete this test. NAP can provision billed capacity even for a demo: review existing limits and your spend ceiling first.

1. Confirm connectivity with an explicitly selected context and a supported client/server version pair. Through Bastion, preserve the configured TLS server name; do not use `--insecure-skip-tls-verify`. API discovery proves only that an API is served, not its controller version or completeness.
2. Resolve authentication before evaluating missing series. HTTP `401` is an authentication failure, not zero metrics; refresh the approved scoped credential locally and never paste it into chat or put it in a command argument. HTTP `403` requires a scope/role review, not a stronger role by default. Keep the query endpoint and permitted cluster/time range explicit.
3. In the approved Prometheus/Grafana query editor, run the presence queries below for the actual cluster-label value. These are source-shape checks, not exact-identity admission or engineering catalog assets. Repeat once after the known scrape/ingestion delay; do not poll indefinitely or treat a long retention setting as existing history.

```promql
count(node_memory_working_set_bytes{cluster="<approved-cluster-label>"})
count(node_cpu_usage_seconds_total{cluster="<approved-cluster-label>"})
count(count_over_time(node_memory_working_set_bytes{cluster="<approved-cluster-label>"}[15m]))
count(count_over_time(node_cpu_usage_seconds_total{cluster="<approved-cluster-label>"}[15m]))
count(kube_node_info{cluster="<approved-cluster-label>"})
count(kube_pod_created{cluster="<approved-cluster-label>"})
count(kube_pod_status_ready{cluster="<approved-cluster-label>"})
```

An empty result is missing evidence, not an observed zero. The selected Node measures should not need a new application to exist. Microsoft's [default managed-Prometheus ingestion reference](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-default) lists different default kubelet, cAdvisor and node-exporter metrics. Verify the actual scrape endpoint and metric keep-list with your monitoring configuration owner before assuming a startup delay; adding a keep-list cannot expose a measure that the target never emits. Review the [customization guidance](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-configuration) for a separately approved narrow change. Do not disable minimal ingestion globally, enable all annotations, fetch arbitrary ConfigMap bodies or install recordings as an automatic repair. Do not substitute container working set or total-minus-available for Node working set.

4. For an application rehearsal, use an existing expendable stateless demo Deployment, or deploy your own reviewed application into a dedicated namespace using your normal delivery process. A suitable test has one replica, explicit resource requests/limits, no credentials or persistent data, a bounded known initialization delay, and startup/readiness endpoints whose meaning you can explain. It needs no public LoadBalancer, HPA, VPA mutation, storage allocation or privileged access. Resource values are operator-chosen test inputs, not advisor recommendations. Review the [official stateless Deployment tutorial](https://kubernetes.io/docs/tasks/run-application/run-stateless-application-deployment/) when preparing a new application; use your approved image and manifests rather than applying a remote manifest blindly.
5. Before creating a new test Pod, record the UTC test start and the old workload UID, if any. Record new Namespace/workload/Pod UIDs, Pod creation time and the operator-defined readiness criterion after deployment. Use explicit-context, namespaced `kubectl get` commands with selected output fields, not logs, Events, environment dumps, exec or watches. Record several bounded manual observations of not-ready and ready state around the known delay. A current Ready condition, zero restarts or its last transition time is not proof of first-ever application startup; manual notes are not a complete admitted history contract.
6. Confirm the test application's `kube_pod_created`, `kube_pod_status_ready` and `kube_pod_container_status_restarts_total` series include its exact Pod UID. Review separately whether container-attempt identity and historical workload ownership are actually retained. Keep CPU and working-set usage in a distinct post-readiness interval; a five-minute CPU rate must not look back across the readiness boundary. A short demo cannot satisfy ordinary representative-history/rightsizing gates or establish peaks, SLO compliance or a safe resource setting.
7. For NAP, inspect only the approved versioned NodePool/NodeClaim/NodeClass fields and current exact owner/provider bindings. Record the deployed controller version if independently available; a referenced upstream release or `karpenter.sh/v1` API is not deployment attestation. Do not scale demand merely to force a Node replacement, drain a Node, alter budgets or test disruption without separate approval. No current Node set supplies historical Node-UID membership or past Spot/fallback behavior.
8. Retain protected source timestamps, exact query range/step, receipt/projection references, missing-series results and scope/version limits. Share only approved allowlisted exports with the advisor. Preserve unknown gaps rather than fabricating a full receipt or relabeling historical names with today's UIDs. Delete only your own demo application/namespace through your normal operator process, after retaining approved test evidence; do not delete pre-existing resources or touch NAP-managed infrastructure for cleanup.

The saved [startup review](../data-contracts.md#saved-startup-investigation), [historical Node envelope](../fleet-insights.md#review-saved-historical-contributions), [storage projection](../data-contracts.md#optional-storage-binding-and-topology-projection), [DaemonSet model](../data-contracts.md#optional-modeled-daemonset-node-membership) and [NAP policy reference](../data-contracts.md#optional-nap-policy-reference) remain distinct workflows. A demo can validate a bounded source shape or expose a gap; it cannot manufacture missing history or certify all versions, scheduler plugins, volume semantics or release acceptance.

## Completion

Finish with an explicitly supported subset, known blockers, unknowns, owners and next actions. A decision to postpone historical checks is valid. Customer-source acceptance requires independent owner review and an approved live slice where needed; offline examples and test suites do not establish it.

Next, [plan the bounded pilot](plan-a-bounded-pilot.md). Exact mapping, identity/recording and consent requirements remain in [source compatibility](../source-compatibility.md), [source profiles](../source-profiles.md) and [security and privacy](../security-and-privacy.md).
