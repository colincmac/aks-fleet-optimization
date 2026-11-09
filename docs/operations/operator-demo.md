# Operator self-validation and local demo

Use this walkthrough with **your disposable demo AKS clusters**, existing
**Azure Monitor managed Prometheus** and Windows PowerShell.
Review and run every environment command under your own approved scope.
For multiple demo clusters, repeat the walkthrough with a separate explicit
context, local run directory, profile, plan and report for each. The helper is
deliberately single-cluster; do not combine independently collected receipts
by editing their scope or completeness claims.

## What this validates

Keep three clearly separated tracks:

| Track | Source and what you can demonstrate | What it does not prove |
|---|---|---|
| A: real current inventory | Fresh approved Azure/Kubernetes metadata; current capacity classes and scheduling restrictions; explicit gaps and deterministic replay | Historical utilization, safe rightsizing, packing, removable nodes, NAP migration or savings |
| B: synthetic historical examples | Committed synthetic snapshots at their fixed clock; CPU/memory/HPA evidence gates and separately guarded proposals | Measurements or recommendations for your demo clusters |
| C: local Headlamp preview | Synthetic catalog, evidence and simulated review states | Live import of Track A, real authentication, durable approvals, Git operations or deployed-host acceptance |

Installing a test workload today does not
produce 30 days of history. Do not lower the 30-day, identity, coverage or owner
gates to manufacture numeric findings. Managed Prometheus presence alone does
not guarantee the advisor's Azure resource-ID labels, historical UIDs or
recording semantics. The optional source-inspection section is preparation,
not part of the same-day current-inventory collection.

This walkthrough can supply demo-environment evidence for your own review.
It does not establish customer source compatibility, independent operator
comprehension, Linux/container support or production Headlamp readiness.

## 1. Guardrails and prerequisites

- Use only a disposable/nonproduction cluster you own, with approved budget,
  connectivity and report audience. Never use a customer kubeconfig here.
- Confirm at least one Linux node can accommodate one `100m`/`128Mi` Pod.
  The optional HPA can run two Pods. Limits are `500m`/`512Mi` per Pod.
  Allocated requests can cause existing CAS/NAP to provision capacity: stop
  if the Pod is Pending; do not expand pools merely to make the demo green.
- Do not enable/disable NAP, CAS, VPA, KEDA, monitoring, policies, networking or
  admission defaults. No cluster provisioning or telemetry installation is needed.
- The test image is a pinned-version Kubernetes `agnhost serve-hostname`
  fixture, not a production application or command-execution server.
  Review/scan or mirror it under your image policy.
  This runbook has not verified its pull or startup on your nodes.
- Separate your **platform operator** (applies demo objects and mints a temporary
  token) from collection identities. Kubernetes collection uses a dedicated
  get/list-only ServiceAccount. Azure collection uses an independently reviewed
  **Reader-only Azure CLI principal**, not your Owner/Contributor login.
- Review inherited/group grants too. GET-only code is not proof of read-only
  identity permissions. Do not grant the advisor write permissions.
- Metadata collection is **cluster-wide**, including projected objects outside
  the demo namespace. Namespace filters are not an authorization boundary.
  Optional API reads are listed in the reader role; remove only deliberately,
  accepting partial results rather than fabricating absence.
- SDK list responses transiently decode Pod specs before projection. Only the
  existing allowlisted metadata leaves the reader. If that transient access is
  unacceptable, stop and supply an independently approved sanitized export.
  Never save raw `kubectl get pods -o json`, kubeconfigs, logs or credentials.
- Keep evidence on an encrypted/ACL-protected local disk under the ignored
  `.local` directory. No source artifacts, tokens or real IDs belong in Git.
  Approve the exact report fields before showing them to a customer.

Run commands from the repository root in an isolated PowerShell session.
Use your platform/operator account only for the explicitly marked setup steps.
If `.venv` does not exist yet, complete the fresh setup immediately below before
running this variable-initialization block.

```powershell
$Python = (Resolve-Path .\.venv\Scripts\python.exe).Path
$Advisor = (Resolve-Path .\.venv\Scripts\aks-fleet-advisor.exe).Path
$Demo = (Resolve-Path .\examples\phase1-demo).Path
$Run = Join-Path (Get-Location) ('.local\operator-demo-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $Run | Out-Null
```

If the environment is not installed yet, follow [Contributing](../../CONTRIBUTING.md)
and install the reviewed package with `.[dev,kubernetes,azure]`. The Azure and
Kubernetes extras are needed for Track A. The `metrics` extra is only needed for
later explicitly approved metric collection. For a fresh setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,kubernetes,azure]'
```

Resolve `$Python` and `$Advisor` after installation. No install grants roles.
If you want to recheck the software baseline before testing:

```powershell
& $Python scripts\verify.py
npm --prefix plugins\headlamp-fleet-efficiency run verify
```

The Python verifier also requires the pinned local `promtool`; follow the
[explicit setup instructions](../source-profiles.md#required-pinned-tool) if
missing. It never downloads tooling silently.

## 2. Establish exact cluster and credential provenance

**Platform operator, trusted existing context:** choose an explicit context
and resource scope. Do not use whatever current context happens to be selected.
Replace the three descriptive strings below with your demo settings:

```powershell
$Context = 'YOUR-EXISTING-VERIFIED-DEMO-CONTEXT'
$ResourceGroup = 'YOUR-DEMO-RESOURCE-GROUP'
$ClusterName = 'YOUR-DEMO-CLUSTER'
$TenantId = az account show --query tenantId -o tsv
$SubscriptionId = az account show --query id -o tsv
if ($LASTEXITCODE -ne 0 -or -not $TenantId -or -not $SubscriptionId) { throw 'Azure scope lookup failed' }
$Arm = az aks show --subscription $SubscriptionId --resource-group $ResourceGroup `
  --name $ClusterName `
  --query '{id:id,fqdn:fqdn,privateFqdn:privateFqdn,nodeResourceGroup:nodeResourceGroup}' -o json |
  ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $Arm.id) { throw 'AKS identity lookup failed' }
$ClusterId = $Arm.id
$Server = kubectl --context $Context config view --minify `
  -o 'jsonpath={.clusters[0].cluster.server}'
if ($LASTEXITCODE -ne 0 -or -not $Server) { throw 'Context endpoint lookup failed' }
```

Compare the HTTPS hostname in `$Server` with the trusted ARM public/private FQDN
and your known context. Resolve any alias/private-network difference explicitly;
never disable TLS or create an API tunnel/proxy as a workaround. Read the
`kube-system` UID only after verifying that endpoint through your trusted
platform context. Retain the identity binding in your local evidence record.

```powershell
$ClusterUid = kubectl --context $Context get namespace kube-system `
  -o 'jsonpath={.metadata.uid}'
if ($LASTEXITCODE -ne 0 -or -not $ClusterUid) { throw 'Fingerprint lookup failed' }
$CaBase64 = kubectl --context $Context config view --raw --minify `
  -o 'jsonpath={.clusters[0].cluster.certificate-authority-data}'
if ($LASTEXITCODE -ne 0 -or -not $CaBase64) {
  throw 'Obtain the trusted public CA certificate through your platform process'
}
$CaFile = Join-Path $Run 'api-ca.crt'
[IO.File]::WriteAllBytes($CaFile, [Convert]::FromBase64String($CaBase64))
Remove-Variable CaBase64
```

Here `config view --raw` outputs **only the public CA field**, never a complete
kubeconfig. If your context references a CA file instead, copy that approved
public certificate to `$CaFile`; do not export the rest of the configuration.
The helper takes explicit endpoint/CA/token inputs and never loads kubeconfig,
executes login plugins, reads credential environment variables or logs tokens.

## 3. Prepare local profile and bounded plan

Copy the templates, then replace only synthetic placeholders in local files:

```powershell
$Profile = Join-Path $Run 'inventory-profile.yaml'
$Plan = Join-Path $Run 'inventory-plan.json'
$TemplateCluster = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/managedClusters/aks-synthetic'
$Text = Get-Content (Join-Path $Demo 'inventory-profile.yaml') -Raw
$Text = $Text.Replace($TemplateCluster, $ClusterId)
$Text = $Text.Replace('tenant_id: 00000000-0000-0000-0000-000000000000', "tenant_id: $TenantId")
$Text = $Text.Replace('- 00000000-0000-0000-0000-000000000000', "- $SubscriptionId")
[IO.File]::WriteAllText($Profile, $Text, [Text.UTF8Encoding]::new($false))
$Request = Get-Content (Join-Path $Demo 'inventory-plan.json') -Raw | ConvertFrom-Json
$Request.clusters[0].resource_id = $ClusterId
$Request.clusters[0].expected_cluster_uid = $ClusterUid
$Request.clusters[0].expected_node_resource_group = $Arm.nodeResourceGroup
[IO.File]::WriteAllText($Plan, ($Request | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
```

Review the two files. The profile selects only `AKS-NP-002` and
`AKS-SCHED-001`, baseline mode, and **no metric source**. This deliberately does
not query your managed Prometheus workspace. The plan selects one exact cluster,
no metric entities/history declarations, at most 250 reader calls, 10,000
objects and 300 seconds. A currently unused metric key is required by the
collection-plan contract; it causes no metric request without entities.
The deadline is cooperative; a running reader still has its own 15-second
transport timeout. Review every external command's exit code and stop on
nonzero rather than assuming PowerShell throws for native executables.

```powershell
& $Advisor readiness --config $Profile --format markdown `
  --output (Join-Path $Run 'readiness.md')
$ReadinessExit = $LASTEXITCODE
if ($ReadinessExit -notin @(0, 3)) { throw 'Resolve the offline readiness blocker before collection' }
& $Advisor preview --config $Profile --plan $Plan `
  --output (Join-Path $Run 'preview.json')
if ($LASTEXITCODE -ne 0) { throw 'Offline preview failed; inspect configuration' }
```

`readiness` exit `3` is expected for unknown live facts. Exit `4` means an
explicit blocker to investigate, not permission to proceed. Preview is offline:
it cannot verify your Kubernetes identity or endpoint and may retain the CLI's
sanitized-export prerequisite, because the demo helper uses the library's
separately approved injected reader instead of the CLI export loader.

## 4. Apply the isolated test workload yourself

**Platform operator only; these commands write demo resources.** Review each
file. Do not apply the entire artifact directory recursively: optional scenarios
and role bindings must be deliberate. First check whether the namespace or
cluster-wide role names already exist; do not adopt somebody else's objects.

```powershell
kubectl --context $Context get namespace fleet-advisor-demo --ignore-not-found
kubectl --context $Context get clusterrole advisor-demo-reader --ignore-not-found
kubectl --context $Context get clusterrolebinding advisor-demo-reader --ignore-not-found
```

If any exists, stop and inspect ownership. For a fresh demo:

```powershell
kubectl --context $Context apply -f (Join-Path $Demo 'namespace.yaml')
if ($LASTEXITCODE -ne 0) { throw 'Demo namespace setup failed' }
kubectl --context $Context apply -f (Join-Path $Demo 'resourcequota.yaml')
kubectl --context $Context apply -f (Join-Path $Demo 'deployment.yaml')
kubectl --context $Context apply -f (Join-Path $Demo 'service.yaml')
kubectl --context $Context -n fleet-advisor-demo rollout status deployment/advisor-demo-web --timeout=120s
if ($LASTEXITCODE -ne 0) { throw 'Stop: inspect scheduling/image/admission, do not add capacity blindly' }
```

The service is ClusterIP only: no ingress, public IP, or load balancer. The
development fixture omits probes; rollout completion is not application/SLO
validation. It has no application credentials or mounted ServiceAccount token,
no privileged fields, and a Linux node selector to make a current scheduling
review observable. No stress, OOM, eviction or scale-down experiment is needed.

## 5. Install and review the read-only collection identity

**Platform operator only.** Inspect the get/list-only role before applying:

```powershell
kubectl --context $Context apply -f (Join-Path $Demo 'reader\serviceaccount.yaml')
kubectl --context $Context apply -f (Join-Path $Demo 'reader\clusterrole.yaml')
kubectl --context $Context apply -f (Join-Path $Demo 'reader\clusterrolebinding.yaml')
if ($LASTEXITCODE -ne 0) { throw 'Reader setup failed; do not broaden permissions' }
```

The reader has no Secrets, ConfigMaps, Events/logs, exec, token creation,
RBAC mutation or workload mutation grants. Discovery GETs and approved optional
VPA/KEDA/NAP list reads are explicit; installing CRDs is not required.
Review all bindings to this ServiceAccount and inherited authorization, not
only this role file. On Azure-RBAC-enabled AKS, verify the actual service-account
authorization path rather than assigning a broad Azure cluster role.

Mint one short-lived token using the platform operator, retaining it only in
this session's memory. Do not enable transcripts, echo it, save it in files,
put it on a command line or use `tee`. Do not specify an Azure resource
audience: this is a Kubernetes API ServiceAccount token.

```powershell
$ReaderToken = kubectl --context $Context -n fleet-advisor-demo `
  create token advisor-demo-reader --duration=10m
if ($LASTEXITCODE -ne 0 -or -not $ReaderToken) { throw 'Short-lived reader token request failed' }
```

Now select an existing **Reader-only Azure identity in the same tenant**, using
your approved Azure CLI login process. This is a separate operator action;
the helper does not log in or grant roles. Verify subscription, tenant and
effective inherited/group permissions before continuing. Do not leave an
Owner/Contributor account selected. The helper explicitly uses a tenant-bound
`AzureCliCredential`, so an ambient environment credential cannot silently
replace the reviewed CLI principal.

Keep the Kubernetes context/CA/resource-ID binding from the trusted setup step.
You need not run a kubeconfig login plugin as the Reader-only Azure identity:
collection uses the already minted ServiceAccount token. If ten minutes expire,
return to the platform operator and mint a new token; do not create a static
token Secret or weaken TLS.

## 6. Collect projected real current inventory

This is the first advisor live read in this walkthrough. Review the exact
tenant/cluster/endpoint/identity/budget and local destination again. The helper
uses the existing bounded collection pipeline and existing projected SDK reader;
it has no apply/remediation path. It requests Resource Graph inventory and
Kubernetes metadata, **not managed Prometheus, logs, Secret bodies or costs**.

```powershell
$Fragments = Join-Path $Run 'live-fragments.json'
try {
  $ReaderToken | & $Python scripts\collect_demo_inventory.py `
    --config $Profile --plan $Plan --server $Server --ca-file $CaFile `
    --token-stdin --allow-live --output $Fragments
  $CollectExit = $LASTEXITCODE
} finally {
  Remove-Variable ReaderToken -ErrorAction SilentlyContinue
}
if ($CollectExit -notin @(0, 3)) { throw 'Collection did not produce valid demo evidence' }
```

`0` means requested inventory collection completed; `3` preserves partial
receipts. Neither means the fleet is healthy or historical metrics exist.
ARG is eventually consistent and visibility-limited. Denied optional APIs,
missing required ARG properties, private-network failures and stale fingerprints
remain visible; do not edit receipts to complete.

```powershell
$Bundle = Get-Content $Fragments -Raw | ConvertFrom-Json
$Bundle.azure | ForEach-Object { $_.collection | Select-Object collector,status,missing_fields,errors }
$Bundle.kubernetes | ForEach-Object { $_.collection | Select-Object collector,status,missing_fields,errors }
```

If a new cluster returns missing fields, stop and record the precise unsupported
shape. Do not substitute `az aks show` fields into a supposedly complete ARG
receipt. There is no automatic ARM fallback.

## 7. Assess and replay offline

```powershell
$AsOf = [DateTimeOffset]::UtcNow.ToString('o')
$Assessment = Join-Path $Run 'live-assessment.json'
$Artifacts = Join-Path $Run 'live-artifacts'
& $Advisor assess --config $Profile --fragments $Fragments --as-of $AsOf `
  --format json --output $Assessment --artifacts $Artifacts
$AssessmentExit = $LASTEXITCODE
if ($AssessmentExit -notin @(0, 3)) { throw 'Assessment rejected its inputs/output destination' }
$Result = Get-Content $Assessment -Raw | ConvertFrom-Json
$Result.report.recommendations | Select-Object rule_id,namespace,workload,title
$Result.report.blocked_recommendations | Select-Object rule_id,namespace,workload,reason_codes
```

Open `live-artifacts\report.md` in VS Code. Expected observations:

- `AKS-SCHED-001` can review the demo Pod's Linux selector when exact owner and
  complete/fresh scoped metadata are present. It does not prove stranded capacity.
- `AKS-NP-002` can classify current ARM pool facts and preserve NAP prerequisites
  as unknown. Auto cluster mode does not relabel ARM pools as NAP-managed.
- Other cluster workloads can also appear: collection is cluster-wide.
- Missing metrics and unsupported normalizations can make the overall assessment
  partial even when these two inventory findings are valid.
- Every resource/replica proposal and financial savings value remains null.
  These baseline packs do not choose resource targets.

Use the **same clock and saved lock configuration** for replay:

```powershell
$Replay = Join-Path $Run 'live-replay.json'
& $Advisor analyze --snapshot (Join-Path $Artifacts 'snapshot.json') `
  --config (Join-Path $Artifacts 'analysis-config.json') --as-of $AsOf `
  --format json --output $Replay
if ($LASTEXITCODE -ne 0) { throw 'Offline replay failed' }
& $Python -c "import json,sys; a=json.load(open(sys.argv[1],encoding='utf-8')); b=json.load(open(sys.argv[2],encoding='utf-8')); assert a['report']==b, 'Replay differs'; print('Exact engine-report replay passed')" $Assessment $Replay
if ($LASTEXITCODE -ne 0) { throw 'Replay mismatch' }
```

All destinations must be new. For another capture use new filenames/directories,
not overwrites or changed hashes. Before a meeting, close credentials and replay
this saved evidence offline; disclose its capture time.

## 8. Optional HPA and PDB scenarios

Use the platform operator again for these writes; repeat token minting and
Reader-only Azure identity selection before any new collection.

### HPA: current configuration, not historical pinning

Confirm the existing resource metrics API serves the demo Pod. If unavailable,
skip HPA; do not install Metrics Server just for this demo.

```powershell
kubectl --context $Context -n fleet-advisor-demo top pods
kubectl --context $Context apply -f (Join-Path $Demo 'optional\hpa.yaml')
kubectl --context $Context -n fleet-advisor-demo get hpa advisor-demo-web
```

This controller may change the demo Deployment between one and two replicas.
No load generator is supplied. Capture a new inventory and assess with new
paths. Inspect the normalized workload's `autoscaler_configuration`, or projected
HPA metadata if current replicas are not yet stable. Only the two selected
inventory packs run; no HPA finding is promised. Current HPA values do not prove
sampled floor/ceiling behavior or authorize a lower minimum.

### PDB: unmatched candidates and conservative gaps

```powershell
kubectl --context $Context apply -f (Join-Path $Demo 'optional\pdb.yaml')
kubectl --context $Context -n fleet-advisor-demo get pdb advisor-demo-web
```

The PDB allows one voluntary unavailability, avoiding a zero-disruption budget
for this disposable single-Pod fixture. It is not a production availability
recommendation. Never drain/delete nodes or test involuntary disruption here.
After a new capture, scheduling context can show the namespace PDB candidate
with matching explicitly unknown. Current vertical normalization conservatively
excludes PDB-bearing namespaces; that visible gap is expected, not a reason to
remove safeguards. Delete the optional objects before reapplying the base
Deployment or doing manual replica experiments.

## 9. Clearly labeled synthetic history and safety demonstrations

Use **only repository synthetic fixtures** for same-day numeric examples.
Keep them in a separate `synthetic-*` output path, never merge them into live
fragments. The reference clock belongs to those fixtures, not to your cluster.

```powershell
$SyntheticClock = '2026-10-29T12:00:00Z'
& $Advisor analyze --snapshot examples\fixtures\memory-request-pack-snapshot.json `
  --pack AKS-MEM-003 --mode guarded --as-of $SyntheticClock --format markdown `
  --output (Join-Path $Run 'synthetic-memory-request.md')
& $Advisor analyze --snapshot examples\fixtures\memory-limit-pack-snapshot.json `
  --pack AKS-MEM-005 --mode guarded --as-of $SyntheticClock --format markdown `
  --output (Join-Path $Run 'synthetic-memory-limit.md')
& $Advisor analyze --snapshot examples\fixtures\hpa-floor-pack-snapshot.json `
  --pack AKS-AS-005 --mode guarded --as-of $SyntheticClock --format markdown `
  --output (Join-Path $Run 'synthetic-hpa-floor.md')
```

These reproduce 313 MiB per-replica request, a separate 600 MiB memory limit
with the request unchanged, and a separate 2-to-1 HPA floor respectively.
They are policy/evidence examples, **not** measured targets for your cluster.
Do not apply these numbers to the demo Deployment.

Failure/reliability examples do not require breaking a real cluster:

```powershell
& $Advisor assess --config examples\pool-assessment-config.yaml `
  --fragments examples\fixtures\pool-assessment-partial.json `
  --as-of $SyntheticClock --format markdown `
  --output (Join-Path $Run 'synthetic-partial.md')
$PartialExit = $LASTEXITCODE
if ($PartialExit -ne 3) { throw 'Expected an explicit partial synthetic assessment' }
```

Use the existing test suite for missing/stale/foreign identities; never revoke
cluster access, forge UIDs, kill Pods or disable telemetry during a customer demo.

## 10. Existing managed Prometheus: inspect prerequisites, do not assume them

There is deliberately no monitoring installation/configuration manifest.
Copy [managed-prometheus-profile.yaml](../../examples/phase1-demo/managed-prometheus-profile.yaml)
to your local run directory, replace exact scope and the workspace's actual
query endpoint, and review labels/retention with the source owner.

For source inventory, an independently authorized operator can inspect the
selected Azure Monitor workspace's `properties.metrics.prometheusQueryEndpoint`
through the portal or a scoped `az resource show` projection. Query access needs
the workspace's appropriate `Monitoring Data Reader` authorization; AKS Azure
Reader or the Kubernetes reader role is not that permission. Do not print tokens.

In the existing approved Prometheus explorer, inspect a bounded sample of
`container_cpu_usage_seconds_total` and
`kube_pod_container_resource_requests{resource="cpu",unit="core"}` for your demo
namespace. Check actual retained label keys/values before editing mappings:

- The name-only `cadvisor-ksm` profile still needs the **exact Azure cluster
  resource ID in an existing source label**. An AKS cluster name or workspace
  resource ID is not a substitute.
- Name-only observations remain unresolved baseline measurements, not historical
  workload UIDs. Do not relabel today's Pod ownership onto earlier data.
- Leave component versions and retention unknown until independently verified.
  New recordings cannot backfill missing historical identity.
- If those source labels are absent, record the unsupported mapping and continue
  with Track A/B. Do not query arbitrary metrics or reconfigure scraping to
  manufacture acceptance.

Use [source profiles](../source-profiles.md) and the
[source worksheet](../source-compatibility.md#pilot-evidence-worksheet) before
any separately approved metric collection. Neither `readiness` nor a successful
workspace request certifies source compatibility or clears the historical gates.

## 11. Optional local UI customer demo

```powershell
npm --prefix plugins\headlamp-fleet-efficiency run dev
```

Open `http://127.0.0.1:5173/fleet-efficiency/catalog` for the 21-pack catalog.
Use `/fleet-efficiency?scenario=guarded`, `unsupported`, `limit`, `floor`,
`denied` or `empty` for synthetic review/failure stories.

Tell the audience: **this local UI uses synthetic in-memory records**.
It does not import your live CLI report. Show Track A Markdown/JSON separately.
Simulated approvals/PRs are not real permissions, persistent audit, Git delivery
or cluster changes. Do not install the governance CRD/backend or expose this
preview publicly. Stop the dev server with Ctrl+C after the demo.

## 12. Suggested 15-minute customer narrative

1. **2 min:** read-only collection, declared scope and evidence boundaries.
2. **4 min:** your approved saved real-inventory report: current restrictions,
   capacity classes, source receipts and honest unknowns.
3. **4 min:** explicitly synthetic memory/HPA examples; explain why owner policy,
   independent history and one-dimensional validation matter.
4. **3 min:** synthetic Headlamp catalog and unsupported/denied states.
5. **2 min:** replay proof and next evidence needed; no savings or remediation claim.

Use a private display without terminal tokens, kubeconfig details or portal
identity panes. Review reports for real IDs, names, labels/tags and owner fields
before screen sharing. For an audience not approved to see that metadata, use
synthetic reports instead; do not rewrite live evidence to look synthetic.

## 13. Record results locally

Copy this checklist to an approved local evidence record, not a repository fixture:

- [ ] Demo cluster, tenant/subscription, trusted endpoint/CA and fingerprint reviewed.
- [ ] Operator writes and exact collection identity permissions reviewed separately.
- [ ] Image policy, resource budget and optional controller effects accepted.
- [ ] Software package/version and exact command/clock recorded.
- [ ] Collection receipt status/errors/missing fields reviewed per source.
- [ ] Current scheduling/capacity observations match the visible demo configuration.
- [ ] Partial/missing data is shown as unknown, never healthy/zero.
- [ ] No numeric or savings claim is made from live current-only evidence.
- [ ] Saved snapshot/config/clock reproduces the exact engine report.
- [ ] Synthetic examples and preview are explicitly labeled, never mixed with live data.
- [ ] Report audience approved; no credentials or real environment data committed.
- [ ] Optional objects and collection role bindings removed; tokens expired/revoked.
- [ ] Residual source mapping, pilot, unfamiliar-operator and runtime gates recorded.

Suggested verdict: "Validated only for the recorded current-inventory scenarios;
historical numeric examples are synthetic. Broader source and operational
compatibility are not established." Only mark checks after observing them.

## 14. Cleanup: platform operator only

Confirm the explicit context and ownership again. These commands remove only
the demo-named objects, not AKS clusters, node pools, monitoring or other namespaces.

```powershell
kubectl --context $Context delete -f (Join-Path $Demo 'optional\hpa.yaml') --ignore-not-found
kubectl --context $Context delete -f (Join-Path $Demo 'optional\pdb.yaml') --ignore-not-found
kubectl --context $Context delete -f (Join-Path $Demo 'reader\clusterrolebinding.yaml') --ignore-not-found
kubectl --context $Context delete -f (Join-Path $Demo 'reader\clusterrole.yaml') --ignore-not-found
kubectl --context $Context delete namespace fleet-advisor-demo --wait=true --timeout=120s
Remove-Variable ReaderToken -ErrorAction SilentlyContinue
```

Deleting the namespace removes the demo workload, quota, service and reader
ServiceAccount; deleting the binding removes its cluster-wide access immediately.
Verify absence using the trusted platform operator. Do not force-remove finalizers.
Retain/delete local evidence under your approved retention policy using the exact
resolved `$Run` path; no broad deletion command is provided.

## Troubleshooting

| Symptom | Interpretation and safe action |
|---|---|
| Helper exit `2` before collection | Review explicit opt-in, exact one-cluster baseline inventory profile, public CA/HTTPS, single bounded stdin token, dependencies and new output path. Never paste the token into an issue. |
| Helper exit `3` | Inspect preserved source receipts; refresh an expired short-lived token, verify read-only scope/network, or record unsupported fields. Do not promote partial to complete. |
| `401`/`403` | Review the specific identity/audience/role and optional API grants. Do not retry with admin credentials in the collector. |
| TLS/private DNS error | Use your approved in-network workstation and trusted CA; no TLS disabling, reverse proxy or tunnel. |
| No scheduling finding | Check selected pack, fresh complete source scope and exact Pod/controller identities; the selector must be present in admitted metadata. No findings is not a health verdict. |
| PDB/HPA causes normalization gaps | Expected conservative boundaries or transitional replicas; capture stable current state and retain qualified scheduling context. |
| Missing managed-Prometheus cluster-ID/UID labels | Source shape unsupported for that analysis. Use current-only and synthetic tracks; do not infer history. |
| Existing file/directory | Choose a new capture path; exclusive writes protect original evidence. |
| Live findings do not appear in Headlamp preview | Expected: preview is a separate synthetic simulator, not a live report importer. |
| Historical gates block today's workload | Correct: no 30-day history exists yet. Do not shorten safety thresholds to enable a target. |

See the [main runbook](runbook.md), [security guidance](../security-and-privacy.md)
and [source validation worksheet](../source-compatibility.md)
for the broader boundaries.

## Official reference material

- [Kubernetes short-lived ServiceAccount token command](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_token/)
- [Kubernetes RBAC and API discovery roles](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [AKS cluster authorization](https://learn.microsoft.com/azure/aks/concepts-cluster-authorization)
- [Managed Prometheus query API authentication](https://learn.microsoft.com/azure/azure-monitor/metrics/prometheus-api-promql#authentication)
- [Managed Prometheus scrape configuration and cluster labels](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-configuration)
- [Kubernetes agnhost serve-hostname test fixture](https://github.com/kubernetes/kubernetes/blob/master/test/images/agnhost/README.md#serve-hostname)
- [Versioned serve-hostname implementation and flags](https://github.com/kubernetes/kubernetes/blob/v1.32.0/test/images/agnhost/serve-hostname/serve_hostname.go)

These explain setup concepts, not live certification of your source, image
version or cluster. In particular, agnhost's nonroot/read-only fixture execution
must be checked by your bounded rollout; do not remove its security context
merely to make the fixture run.

## Validation boundary

Offline checks do not prove image pull/startup, server-side manifest validity,
effective identity permissions, metric-source compatibility or production UI
readiness. Complete the observed checklist for your exact environment and
retain the evidence under the approved audience and retention policy.
