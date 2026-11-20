# AKS Fleet Advisor Demo Kit

Run two contrasting workload sets on independent AKS clusters. Cluster A shows CPU-driven scaling and intentionally constrained workload settings; Cluster B shows fixed HPA bounds and a smaller admitted request with placement and disruption controls on the same-named workload. Neither cluster needs to join Azure Kubernetes Fleet Manager. Use live manifests for current observations. Use the fictional replays for qualified history, guarded proposals, finance, and AI.

## Before You Deploy

- Use two disposable demo clusters in the same tenant, with schedulable Linux capacity. These manifests target Kubernetes 1.36 and use native sidecars. Use explicit kubeconfig contexts with verified TLS, and review dry runs against each cluster's actual admission policies.
- Use your operator identity to deploy and clean up. The advisor runs outside the clusters with its existing read-only identities; the kit installs no advisor, permissions, Secrets, monitoring, VPA/KEDA add-ons, or public endpoints. All containers use the same digest-pinned official Python image. Use an approved mirror of that digest if Docker Hub is not permitted.
- Check the budget first. A starts at five Pods and can reach six, requesting 510–560 mCPU and 360–392 MiB before admission defaults and Pod overhead. B has four Pods and requests approximately 260 mCPU and 264 MiB. Even these small workloads can cause an existing autoscaler to add capacity. The optional NAP Job can incur **VM charges**; optional storage can incur **disk charges**. Do not use shared production capacity or change cluster policy to admit this kit.
- Run commands from the repository root. [Cluster A](cluster-a/kustomization.yaml) and [Cluster B](cluster-b/kustomization.yaml) are the recommended profiles; the [top-level profile](kustomization.yaml) remains the shared baseline without HPAs. The A and B profiles require no VPA or KEDA CRDs and do not install fault workloads, storage, or Jobs by default. Preview with `kubectl kustomize deploy/aks-fleet-demo/cluster-a` or `kubectl kustomize deploy/aks-fleet-demo/cluster-b`. Do not apply the directory recursively.

## 1. Deploy The Two Profiles

Set `$ContextA` and `$ContextB` to two distinct contexts. Confirm the cluster names, exact Azure resource IDs, and Kubernetes fingerprints independently; different context aliases alone do not prove these are different clusters. This block is for fresh installations and refuses to reuse an existing namespace. If both clusters already have this demo, verify those namespaces belong exclusively to it and run only the profile dry-run and apply lines below. Applying an updated profile does not remove previously installed optional workloads; review and clean up those exact demo resources separately if no longer needed. Do not use blanket pruning.

```powershell
$ContextA = 'replace-with-first-demo-context'
$ContextB = 'replace-with-second-demo-context'
$Demo = 'deploy/aks-fleet-demo'
if ($ContextA -eq $ContextB) { throw 'Choose two different demo contexts.' }
foreach ($Context in @($ContextA, $ContextB)) {
    $Existing = kubectl --context $Context get namespace aks-fleet-demo --ignore-not-found -o name
    if ($LASTEXITCODE -ne 0 -or $Existing) { throw "Namespace preflight failed for $Context." }
}
$Targets = @(
    @{ Context = $ContextA; Profile = 'cluster-a' }
    @{ Context = $ContextB; Profile = 'cluster-b' }
)
foreach ($Target in $Targets) {
    kubectl --context $Target.Context create -f "$Demo/base/00-namespace.yaml"
    if ($LASTEXITCODE -ne 0) { throw "Namespace creation failed: $($Target.Profile)." }
    kubectl --context $Target.Context apply --dry-run=server -k "$Demo/$($Target.Profile)"
    if ($LASTEXITCODE -ne 0) { throw "Profile dry run failed: $($Target.Profile)." }
    kubectl --context $Target.Context apply -k "$Demo/$($Target.Profile)"
    if ($LASTEXITCODE -ne 0) { throw "Profile apply failed: $($Target.Profile)." }
}
```

| Workload | What to show |
| --- | --- |
| `missing-cpu` | No CPU request **or** limit, so Kubernetes does not copy a limit into the request. `AKS-RQ-001` should see a missing admitted request unless a LimitRange, webhook, or policy added one. Verify the admitted Pod, not just this YAML; do not remove admission defaults to force a finding. |
| `idle-fixed` | Two fixed replicas in both clusters. A asks for `200m` CPU and `96Mi` per Pod, omits probes and topology spread, and allows no voluntary disruption via its PDB. B asks for `100m` and `64Mi`, adds worker process probes and hostname spread, and permits up to one unavailable Pod by policy. Compare `AKS-SCHED-001`/`002` and `AKS-AS-001` when metadata is complete and controller absence is known. Policy does not prove actual disruption permission or safe request reduction. Do not test by draining a node. |
| `startup-profile` | One native sidecar, one regular init container, a 75-second app delay, and startup/readiness/liveness probes against a loopback-only listener. `AKS-MEM-004` can show the 104 MiB effective request before any admitted overhead (`max(24+80, 24+48)`). Show readiness before and after the delay; `AKS-START-001` needs retained exact-attempt samples and a distinct qualified post-readiness interval, not just the current Ready condition. |
| HPA | A's `cpu-pulse` alternates 90 seconds of CPU-bound work and 30 seconds idle under a 100 mCPU limit, with a CPU target of 70% of a 50 mCPU request and bounds `1–2`. B's `startup-fixed` HPA targets `startup-profile` with bounds `1–1`. After the Kubernetes resource metrics API and Prometheus HPA gauges are available, use [Rightsizing & Scaling Review](../grafana/aks-rightsizing-scaling-review.json): select each approved cluster alias, namespace `aks-fleet-demo`, and its HPA. Contrast A's sampled response with B's fixed bound; current replicas are not Ready replicas. An HPA transition, metric sample or qualified historic finding is not guaranteed. |

For live evidence, observe selected fields only. Run these once early and once after readiness; no dump of Pod bodies, logs, Events, or credentials is needed.

```powershell
kubectl --context $ContextA -n aks-fleet-demo get pods -l app.kubernetes.io/part-of=aks-fleet-demo -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,CREATED:.metadata.creationTimestamp,READY:.status.conditions[?(@.type=="Ready")].status,CPU_REQUEST:.spec.containers[*].resources.requests.cpu'
kubectl --context $ContextA -n aks-fleet-demo get pdb idle-fixed -o 'custom-columns=NAME:.metadata.name,ALLOWED:.status.disruptionsAllowed'
kubectl --context $ContextB -n aks-fleet-demo get pdb idle-fixed -o 'custom-columns=NAME:.metadata.name,ALLOWED:.status.disruptionsAllowed'
kubectl --context $ContextA -n aks-fleet-demo get hpa cpu-pulse
kubectl --context $ContextB -n aks-fleet-demo get hpa startup-fixed
```

## 2. Add Optional Scenarios To Cluster A

Keep Cluster B on its default profile for contrast. Stage the individual scenarios you want in A; none of the files below is included in A's default profile. For example, with VPA already installed:

```powershell
kubectl --context $ContextA apply --dry-run=server -f "$Demo/cluster-a/21-vpa-off.yaml"
if ($LASTEXITCODE -ne 0) { throw 'VPA demo dry run failed.' }
kubectl --context $ContextA apply -f "$Demo/cluster-a/21-vpa-off.yaml"
if ($LASTEXITCODE -ne 0) { throw 'VPA demo apply failed.' }
```

Use the same dry-run pattern for the other opted-in files except the NAP template, which has its own procedure below. A dry run does not exercise every Pod admission webhook or confirm image pulls, scheduling, CSI mounts, or controller behavior. The offline reports cover unavailable features.

| Manifest | Prerequisite and expected observation |
| --- | --- |
| [21-vpa-off.yaml](cluster-a/21-vpa-off.yaml) | After HPA, only if VPA is already installed. Inspect recommendation evidence and policy bounds (`AKS-AS-007`) if the recommender populates them. VPA `updateMode: "Off"` is recommendation-only; container policy `mode: Auto` allows recommendations for that container, not changes. Contrast with the saved `AKS-AS-002` mutating-overlap case instead of enabling mutation. |
| [22-keda.yaml](cluster-a/22-keda.yaml) | Only if KEDA is already installed and can read resource metrics. `event-owner` has its own CPU-only `ScaledObject`, 1–2 replicas, no trigger credentials, and no competing authored HPA. `AKS-AS-004` can show one ownership chain after KEDA creates the HPA and its exact owner reference. This intentionally does not scale to zero. |
| [30-fault-once.yaml](cluster-a/30-fault-once.yaml) | **Opt in on a disposable cluster.** Each new test Pod starts two limited containers. After about two minutes, one exits `42`, the other attempts to exceed its own 48 MiB limit. Per-container `emptyDir` marker files prevent repeated failures within that Pod; replacement Pods repeat the experiment. Inspect only last termination reasons, exit codes, and restart counts. `AKS-REL-002` uses current status; `AKS-MEM-001` and `AKS-REL-001` need complete, independently qualified historical counts. Do not infer OOM from exit code alone. No node-pressure or eviction injection. |
| [40-daemonset.yaml](cluster-a/40-daemonset.yaml) | One small Pod per eligible Linux AKS user node with label `kubernetes.azure.com/mode=user`, subject to taints/admission. `AKS-NP-004` can compare observed request fractions when node shapes differ; one shape or no eligible nodes is a useful limitation. Desired membership and disruption are separate reviews. |
| [41-storage.yaml](cluster-a/41-storage.yaml) | **Optional, billable.** Check that the existing `managed-csi` StorageClass is appropriate and review its reclaim policy and rate; otherwise skip. The 1 GiB claim can allocate a larger billed disk tier. The StatefulSet mounts an empty disk; its app does not write data. Use the actual PVC/PV/class/CSI bindings for storage context, not a scheduler-fit claim. The headless Service is internal only; the app does not listen on it. |
| [50-placement-gate.yaml](cluster-a/50-placement-gate.yaml) | One short-lived Job with a [Pod scheduling gate](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-scheduling-readiness/). Show the unassigned Pending Pod as held before scheduling, not rejected by a Node or evidence of insufficient capacity. Do not remove the gate. Capture `PodScheduled` while the Job is active; use the replay below for per-node resource exhaustion, taints, and fragmentation. |
| [51-nap-provisioning.yaml](cluster-a/51-nap-provisioning.yaml) | **Optional, may incur VM charges.** The Job is suspended as shipped. The separate procedure below starts at most one Pod bound to a named, approved dynamic NAP NodePool. It does not create or patch the pool. |

Inspect the recommendation or fault status with bounded reads, only after opting into the corresponding scenario:

```powershell
kubectl --context $ContextA -n aks-fleet-demo get vpa cpu-pulse-observe -o 'jsonpath={.spec.updatePolicy.updateMode}{"\n"}{.status.recommendation.containerRecommendations[*]}{"\n"}'
kubectl --context $ContextA -n aks-fleet-demo get pods -l app.kubernetes.io/name=fault-once -o 'custom-columns=NAME:.metadata.name,CONTAINERS:.status.containerStatuses[*].name,RESTARTS:.status.containerStatuses[*].restartCount,LAST_REASON:.status.containerStatuses[*].lastState.terminated.reason,LAST_CODE:.status.containerStatuses[*].lastState.terminated.exitCode'
```

After creating `gated-placement`, `kubectl --context $ContextA -n aks-fleet-demo get pods -l app.kubernetes.io/name=gated-placement -o 'custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,PHASE:.status.phase,SCHEDULER_REASON:.status.conditions[?(@.type=="PodScheduled")].reason'` shows the named condition without reading logs or Events. The Job has a ten-minute deadline; do not rely on its continued presence during a long demo.

### Opt Into NAP Provisioning

Use an existing, [approved dynamic AKS NAP NodePool](https://learn.microsoft.com/azure/aks/node-auto-provisioning-node-pools) on either demo cluster. Confirm NAP is enabled, the chosen pool and its NodeClass are ready, and its limits, quotas, taints, permitted instance types, consolidation behavior, and expected charges are acceptable. The template supplies no particular NodePool, tolerations, Spot requirement, or node-count guarantee. Do not drain nodes, change floors or policies, or add artificial load to force provisioning. If approved capacity is unavailable or the constraints do not match, use the saved replay.

```powershell
$NapContext = $ContextA # Or the verified Cluster B context if it hosts the approved pool.
$Pool = 'replace-with-approved-pool-name'
if ($NapContext -notin @($ContextA, $ContextB) -or $Pool -eq 'replace-with-approved-pool-name' -or
    $Pool -cnotmatch '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$') { throw 'Choose the approved demo pool.' }
$PoolState = kubectl --context $NapContext get nodepool.karpenter.sh $Pool -o 'jsonpath={.spec.replicas}{"|"}{.status.conditions[?(@.type=="Ready")].status}'
if ($LASTEXITCODE -ne 0 -or $PoolState -ne '|True') { throw 'Expected a ready dynamic NodePool.' }
$ClaimsView = 'custom-columns=CLAIM:.metadata.name,UID:.metadata.uid,OWNER_UID:.metadata.ownerReferences[*].uid,NODE:.status.nodeName,PROVIDER:.status.providerID,CREATED:.metadata.creationTimestamp'
kubectl --context $NapContext get nodeclaims.karpenter.sh -l "karpenter.sh/nodepool=$Pool" -o $ClaimsView
if ($LASTEXITCODE -ne 0) { throw 'Could not record the starting NodeClaim roster.' }
$Manifest = Get-Content -Raw "$Demo/cluster-a/51-nap-provisioning.yaml"
$Manifest = $Manifest.Replace('replace-with-approved-nap-pool', $Pool) -creplace '(?m)^  suspend: true\r?$', '  suspend: false'
$Manifest | kubectl --context $NapContext create --dry-run=server -f -
if ($LASTEXITCODE -ne 0) { throw 'NAP demo dry run failed.' }
$Manifest | kubectl --context $NapContext create -f -
if ($LASTEXITCODE -ne 0) { throw 'NAP demo was not created.' }
```

Record the pool's current NodeClaims **before** starting the Job, then use these field-only reads while it runs. The Pod may use an existing Node, trigger provisioning, or stay Pending. Compare the records before claiming a new Node was created; correlate the exact Pod, Node, NodeClaim and NodePool, not just labels. Inspect `AKS-NP-002`/`003` and the [pending NAP constraint review](../../docs/data-contracts.md#optional-pending-nap-constraint-review) where qualified. Neither a binding nor a provisioned Node establishes removability, savings, or scheduler fit.

```powershell
kubectl --context $NapContext get nodeclaims.karpenter.sh -l "karpenter.sh/nodepool=$Pool" -o $ClaimsView
kubectl --context $NapContext -n aks-fleet-demo get pods -l app.kubernetes.io/name=nap-capacity-demo -o 'custom-columns=POD:.metadata.name,UID:.metadata.uid,NODE:.spec.nodeName,PHASE:.status.phase'
```

The Job requests 250 mCPU and 128 MiB, runs for three minutes once placed, and has a ten-minute deadline. Its deadline and TTL limit workload lifetime, not VM lifetime or spend. To stop early, delete only `job/nap-capacity-demo` in `aks-fleet-demo` on that context. Confirm any added Node is handled by the pool's existing lifecycle policy; never delete Nodes or NodeClaims as part of this demo. For an offline fallback, use the [saved NAP policy example](../../docs/data-contracts.md#optional-nap-policy-reference).

## 3. Compare Two Independent Clusters

Start with current checks so metric retention is not a prerequisite. For each cluster, obtain the approved exact-scoped [sanitized Kubernetes export and inventory fragments](../../docs/operations/runbook.md#collection-and-assessment) using the existing-source workflow and [source-compatibility checks](../../docs/source-compatibility.md). Limit workload subjects to `aks-fleet-demo` with the reviewed profile and plan; keep any cluster-scoped evidence the selected checks require. Raw `kubectl get` output is not an export in the advisor contract. Use an actual common UTC observation window, selection, analysis config and tool version. Preserve each cluster's own identity, receipts and missing evidence. If isolation or required source access is unavailable, use the [two fictional cluster rehearsal](../../examples/fleet-lab.md).

The commands below assume approved fragments and profiles were prepared independently under `.local/`. Choose fresh output directories. `assess` can exit `3` for partial evidence with a valid saved bundle; inspect the saved blockers. Do not use the example clock from the offline section for current source data.

```powershell
$AssessmentClock = [DateTimeOffset]::UtcNow.ToString('o')
$Packs = @('--pack','AKS-RQ-001','--pack','AKS-AS-001','--pack','AKS-AS-004','--pack','AKS-AS-007','--pack','AKS-SCHED-001','--pack','AKS-SCHED-002','--pack','AKS-MEM-004','--pack','AKS-NP-002','--pack','AKS-NP-003','--pack','AKS-NP-004','--pack','AKS-REL-002')
aks-fleet-advisor assess --fragments .local/demo-a-fragments.json --config .local/demo-a-profile.yaml --mode baseline @Packs --as-of $AssessmentClock --artifacts .local/demo-a-run1
aks-fleet-advisor assess --fragments .local/demo-b-fragments.json --config .local/demo-b-profile.yaml --mode baseline @Packs --as-of $AssessmentClock --artifacts .local/demo-b-run1
aks-fleet-advisor fleet summarize --assessment .local/demo-a-run1/assessment.json --peer-group demo --assessment .local/demo-b-run1/assessment.json --peer-group demo --as-of $AssessmentClock --format markdown
```

Show that `missing-cpu` has the same display name but independent identities and evidence. Compare only when the report says the inputs are comparable. Then reassess B with only `--pack AKS-SCHED-001` and a new output directory; rerun the fleet summary with that bundle to show an intentionally incompatible comparison. It is not a regression or a fix.

To show recurrence, independently collect a second window for A and B using the same basis (including history duration), assess to fresh `demo-a-run2` and `demo-b-run2` directories at a later actual evaluation time, then run:

```powershell
$Tenant = 'replace-with-approved-tenant-id'
aks-fleet-advisor fleet trends --assessment .local/demo-a-run1/assessment.json --peer-group demo --assessment .local/demo-a-run2/assessment.json --peer-group demo --assessment .local/demo-b-run1/assessment.json --peer-group demo --assessment .local/demo-b-run2/assessment.json --peer-group demo --tenant $Tenant
```

Finding recurrence counts selected assessments, not continuous conditions or financial improvement. Use [historical Node contribution](../../docs/fleet-insights.md#review-saved-historical-contributions) and [market/owner context](../../docs/fleet-insights.md#supply-declared-routing-and-market-context) separately. Neither current ARM pool priority nor two screenshots establish historical membership or fallback.

For [Grafana Fleet Evidence import](../../docs/fleet-insights.md#export-a-protected-grafana-evidence-snapshot), use the same inputs with `--format grafana` and an actual UTC evaluation time at or after the last run. The snapshot shows observed quantities and qualified inventory differences; its time picker does not refresh them. `R − U` stays unknown unless compatible usage evidence is admitted. Save and import real data only within the approved assessment audience.

```powershell
$ComparisonClock = [DateTimeOffset]::UtcNow.ToString('o')
aks-fleet-advisor fleet trends --assessment .local/demo-a-run1/assessment.json --peer-group demo --assessment .local/demo-a-run2/assessment.json --peer-group demo --assessment .local/demo-b-run1/assessment.json --peer-group demo --assessment .local/demo-b-run2/assessment.json --peer-group demo --tenant $Tenant --format grafana --as-of $ComparisonClock > .local/demo-fleet-grafana.json
```

## 4. Replay What A Short Live Demo Cannot Prove

With the advisor installed, run the [pack replay](replay-packs.ps1) in PowerShell 7 from the repository root. It runs all 25 packs individually at the canonical fictional clock, including guarded CPU request, memory request, memory limit, and HPA floor examples. A run with zero evaluated subjects is not a positive example: use the separate saved NAP example above for configured policy evidence, or an already configured NAP cluster for the `AKS-NP-003` current inventory rule. Do not treat synthetic dates or history as live qualifications.

```powershell
./deploy/aks-fleet-demo/replay-packs.ps1 -OutputDir .local/demo-pack-replay
```

| Show next | Replay or workflow |
| --- | --- |
| Baseline versus guarded evidence | Compare [CPU baseline](../../examples/expected-cpu-pack-baseline.md) with [guarded](../../examples/expected-cpu-pack-guarded.md). Show the [saved VPA freshness gap](../../docs/operations/runbook.md#saved-vpa-request-candidates), and run the [example with partial pool history](../../examples/expected-pool-partial.md). A candidate can be blocked even while an independent finding is valid. |
| Retained sources and Grafana | Run [catalog query export](../../docs/recommendation-packs.md#operator-workflow), [retained-quality export](../../docs/recommendation-packs.md#retained-assessment-quality), and the [protected Fleet Evidence snapshot](../../docs/fleet-insights.md#export-a-protected-grafana-evidence-snapshot). A live HPA chart does not satisfy the UID-bound `AKS-AS-003`/`006` history contract; a VPA recommendation does not imply a verified generation time or qualify a CPU request change. |
| Startup, placement, storage, and capacity | Use the saved [startup replay](../../docs/data-contracts.md#saved-startup-investigation), [offline scheduling calculation](../../docs/data-contracts.md#offline-scheduling-resource-calculations), [storage/CSI projection](../../docs/data-contracts.md#optional-storage-binding-and-topology-projection), and [DaemonSet membership review](../../docs/data-contracts.md#optional-modeled-daemonset-node-membership). Separate observed parts, calculated necessary constraints, and blocked fit. |
| Before and after a CPU request change | Use the synthetic [CPU request outcome review](../../docs/data-contracts.md#optional-cpu-request-outcome-review). The different A and B request settings are an illustration, not a controlled experiment or an observed savings result. |
| Cost and value | Start with [allocation and reconciliation](../../docs/tutorials/reconcile-existing-cost-evidence.md), then show [separate comparable cluster-cost ordering](../../docs/cost-reconciliation.md#order-a-separate-cluster-cost-review). Use [experiment handoff and outcome records](../../docs/accelerator-docs/implementation-guide.md) to discuss a canary, rollback, and independent engineering/capacity/bill evidence. Requests released, nodes removed, and costs reconciled are separate claims; estimated savings remain null. |
| Optional UI | Run the [standalone Headlamp preview](../../plugins/headlamp-fleet-efficiency/README.md#develop) with fictional findings. It is not a live importer, production approval service, or required deployment for this kit. |

## 5. Show AI Assistance Without Cluster Access

Use the tracked fictional [assessment bundle](../../history-example/assessment.json), not live exports. The local demo drafts below illustrate three distinct tasks: explain a finding with citations, organize the next human checks, and review a non-executable experiment with an explicit no-change alternative. None generates facts, numeric targets, or approval. Run in PowerShell from the repository root with the advisor's Python environment active:

```powershell
$AiRun = '.local/demo-ai-replay'
New-Item -ItemType Directory -Path $AiRun -ErrorAction Stop | Out-Null
$Synthetic = @('--assessment','history-example/assessment.json','--tenant','00000000-0000-0000-0000-000000000000','--as-of','2026-10-29T12:00:00Z')
aks-fleet-advisor ai export @Synthetic --allow-ai-export --output "$AiRun/summary.json"
python deploy/aks-fleet-demo/prepare-synthetic-ai.py "$AiRun/summary.json" "$AiRun/drafts"
aks-fleet-advisor ai validate-explanation @Synthetic --package "$AiRun/summary.json" --draft "$AiRun/drafts/explanation.json"
aks-fleet-advisor ai validate-checklist @Synthetic --package "$AiRun/summary.json" --intent "$AiRun/drafts/review-intent.json" --draft "$AiRun/drafts/checklist.json"
aks-fleet-advisor ai validate-experiment @Synthetic --package "$AiRun/summary.json" --intent "$AiRun/drafts/experiment-intent.json" --draft "$AiRun/drafts/experiment.json"
aks-fleet-advisor ai validate-explanation @Synthetic --package "$AiRun/summary.json" --draft "$AiRun/drafts/tampered-explanation.json"
```

Expect three successful but unverified states and exit `2` for the deliberately changed digest. For a live model demo, use the [Fleet Evidence Reviewer instructions](../../docs/operations/ai-evidence.md#local-copilot-reviewer) with separately approved **fictional** summary facts and revalidate the response; the CLI itself never invokes a model. Optionally rerun the export to a fresh path with `--allow-ai-measurements` as well, and show why the sample lacks the provenance to admit its numeric values. A local export flag is not permission to share actual cluster material with a provider.

## 6. Clean Up

Retain only approved assessment artifacts off-cluster. Confirm the two contexts and that the namespaces were created for this demo, then delete only those namespaces with the operator identity. Never remove finalizers or delete unrelated PVs, NodePools, VMs, or monitors to clear a pending cleanup. If you enabled storage, confirm the demo claim's backing disk was reclaimed according to the pre-reviewed policy; a retained disk can continue billing.

```powershell
kubectl --context $ContextA delete namespace aks-fleet-demo --wait=false
kubectl --context $ContextB delete namespace aks-fleet-demo --wait=false
```