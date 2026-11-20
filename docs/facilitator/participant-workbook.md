# Participant Workbook

[Documentation home](../README.md) | [Facilitator guide](delivery-guide.md) | [Hypothesis template](assessment-hypothesis.md)

Use this blank customer template during discovery and assessment. It is not an agent work plan, executable configuration, source certification or approval. Keep populated versions in approved customer storage, not Git. Do not enter credentials, raw telemetry, Secret/ConfigMap contents or unapproved identifiers. Use protected references to reviewed records instead of copying sensitive data.

For training, label every entry **fictional**. For a real engagement, record scope, owner, date and source of each answer; unknown is an acceptable answer when it has an accountable next action.

## 1. Scope And Desired Outcomes

| Field | Your answer |
| --- | --- |
| Engagement/workbook reference and review date |  |
| Sponsor and accountable application/platform owners |  |
| Existing Microsoft/vendor tools and reviewed findings |  |
| Advanced question not already answered by those tools |  |
| Engineering question and desired outcome |  |
| Selected entry point, pack/mode and existing monitoring/delivery workflow |  |
| Deferred dimensions or optional integrations, with rationale |  |
| What must not regress |  |
| Approved scope reference: tenant/subscriptions/exact clusters |  |
| Environments/workload classes included |  |
| Explicit exclusions and why |  |
| Success/stop criteria and next decision date |  |

Prompt: is the intended outcome an investigation, better information, a tested engineering change or a separately validated financial outcome? Keep them distinct.

## 2. Workload Classes And Reliability

| Workload class / protected target reference | Demand/startup/peak behavior | SLO/failure/disruption requirements | Owner / missing information |
| --- | --- | --- | --- |
|  |  |  |  |
|  |  |  |  |

SLO means service-level objective. Record actual customer requirements for latency/errors/throughput/availability and relevant failover/batch scenarios. Do not use the example settings or a quiet monitoring interval as acceptance.

## 3. Current Controls

| Control or constraint | Observed configuration / protected reference | Intent and owner | Unknown / next action |
| --- | --- | --- | --- |
| Requests/limits and admission defaults |  |  |  |
| Azure Advisor/VPA/vendor recommendations already reviewed |  |  |  |
| HPA/VPA/KEDA or fixed replicas |  |  |  |
| Node pools, cluster autoscaler or NAP |  |  |  |
| Placement, topology, disruption and storage |  |  |  |
| Shared/dedicated/specialized or reserved capacity |  |  |  |

HPA/VPA change replicas/resources; KEDA supports event-driven scaling; NAP is node auto-provisioning. Use the [scaling lesson](../learning/03-horizontal-vertical-and-node-scaling.md) for responsibilities, not assumptions that these tools are installed or approved.

## 4. Data And Source Readiness

| Question / selected pack | Required input shape | Observed facts and protected reference | Missing/unsupported information | Owner / date |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

Record actual periods/units, retained historical identities and membership, resolution/coverage/freshness, current source receipts and approved producer meaning. "We have 30 days" or "HTTPS responds" does not answer all these questions. Use the [exact source worksheet](../source-compatibility.md#pilot-evidence-worksheet) for the source record; this summary does not replace it.

## 5. Access And Data Handling

| Required decision | Protected record / owner / unresolved action |
| --- | --- |
| Exact identity, runner and independently verified cluster binding |  |
| Effective read-only permissions, including inherited rights |  |
| Supported network/TLS and transient Pod-decoding policy |  |
| Approval for live sources, period, queries, budgets and expiry | Not granted by this template |
| Stop contact and independently bounded transport |  |
| Artifact storage, access, encryption, audience and retention/deletion |  |

Collection permission is not change permission. Never broaden advisor roles or disable TLS to complete the workbook.

## 6. Findings And Candidate Hypotheses

| Finding/pack/version and protected artifact | Observed fact or upstream candidate provenance | Accelerator validation, investigation or gap | Candidate hypothesis, if justified | Owner / next action |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
|  |  |  |  |  |

Keep measurement, owner declaration and interpretation separate. A guarded proposal is not approval. Use the [hypothesis template](assessment-hypothesis.md) only when there is a specific candidate worth independent review.

## 7. Risk, Testing And Rollback

Complete this section only for a separately approved experiment. A no-change/defer decision belongs in section 9; it does not require inventing test results. CPU request, memory request, memory limit and replica-floor changes have separate evidence and rollback boundaries.

| Field | Your answer |
| --- | --- |
| Single dimension and exact proposed scope, if any |  |
| Original configuration and restoration reference |  |
| Representative demand/scenarios and independent measures |  |
| Numeric customer guardrails and observation period |  |
| Canary cohort and authorized implementation/observation owners |  |
| Abort trigger, tested rollback procedure and recovery verification |  |
| Independent approval record | Not granted by this template |

Do not combine request, limit and replica-floor changes in a single test. Unsupported targets need separate engineering work, not a copied policy.

## 8. Financial Validation Assumptions

Optional: mark not in scope for an engineering-only assessment. Missing financial files do not block independently useful metadata/ordinary CPU work. If in scope, keep the FinOps source/basis review and any realized outcome separate from the SLO/change record.

| Field | Your answer |
| --- | --- |
| Financial question and FinOps owner |  |
| Existing financial tool/profile/version and protected evidence reference |  |
| Approved cost basis, period and currency |  |
| Allocation/binding/completeness evidence and unmatched amounts |  |
| Commitment/discount/price assumptions |  |
| Expected engineering effect versus separately owned forecast |  |
| Actual comparison evidence, demand/release confounders and double-counting controls |  |
| Current conclusion: unassessed / attributed / reconciled / blocked / inconclusive / separately validated result |  |

The advisor's savings fields remain null even after reconciliation. No financial value is established by filling this table. See the [cost lesson](../learning/06-cost-attribution-versus-savings.md).

## 9. Decisions And Next Actions

| Decision or unresolved question | Rationale / evidence reference | Accountable owner | Next action / date |
| --- | --- | --- | --- |
|  |  |  |  |
|  |  |  |  |

Include investigate, gather evidence, retain current capacity, defer, reject, request independent test approval, rollback or inconclusive as appropriate. An absent finding is not automatic resolution.

## Worked Exercises

These are fictional exercises, not import payloads or customer policies. Run commands from the repository root after installation using the stated example date; they contact no sources. The table-top cases deliberately omit full history/policy inputs and must not be presented as complete executable assessments. Use your existing Grafana and delivery workflows for any later approved customer work.

### Retain Intentional Capacity

Input: an existing dashboard shows low average CPU; the application owner records a warm failover/startup reserve, but the latest observation window did not exercise that scenario. If a cost tool also reports idle allocation, that is optional context, not a removable-node calculation.

Expected decision: retain settings or defer a candidate pending the independently approved peak/failover test. Stop without turning the low average, a green command or idle amount into a lower request, node count or savings claim. Application/SRE owns the scenario evidence; the platform owner records the capacity intent. Complete one section-9 row such as:

| Decision | Rationale and evidence | Owner | Next action |
| --- | --- | --- | --- |
| Retain CPU request; defer memory and finance | Fictional dashboard review plus declared warm reserve; failover behavior remains untested | Fictional application/SRE owner | Review the approved scenario next month; no rollout or financial claim |

### Validate Saved Recommendation-Only VPA

Input: the [existing memory fixture](../../examples/fixtures/memory-assessment.json) contains native-shaped sanitized VPA status in Off mode, not hand-built candidates. It has current CPU request 1000 mCPU, memory request 512 MiB and limit 1024 MiB, upstream targets 500 mCPU/313 MiB, independently qualified history/owner policy and a fictional digest-bound generation record.

```text
aks-fleet-advisor assess --fragments examples/fixtures/memory-assessment.json --config examples/pool-assessment-config.yaml --pack AKS-RQ-002 --pack AKS-MEM-003 --mode guarded --as-of 2026-10-29T12:00:00Z --format json
```

Expected result: exit `3` for remaining unsupported scope, two upstream request proposals at 500 mCPU and 313 MiB, unchanged memory limit and null savings. Inspect `vpa_recommendation`, the saved status `target`, and normalized candidate `observed_at` versus `collected_at`. Explain why the safety floor is not the source of the target. Removing independent `generated_at` would retain the status but block proposals with `candidate_freshness_unknown`; collection time, condition-transition time and checkpoint time do not replace it.

Stop if age, historical identity/controller evidence, current requests or policy are missing/changed. This supported example still requires independently qualified zero controller-presence history over the reviewed interval; today's Off mode does not qualify a continuously present VPA's historical mode. Platform/monitoring owners resolve those facts, and the application owner decides whether to seek a CPU-only or memory-request-only experiment, not both at once. Follow the [exact handoff and replay steps](../operations/runbook.md#saved-vpa-request-candidates).

### Evaluate App And Sidecar Independently

Table-top input: both containers belong to the same independently verified cluster/namespace/workload UID. Assume each otherwise has its own complete fresh history, controller/reliability evidence and applicable owner policy. Values below are CPU requests only, not a complete assessment bundle:

| Exact container | Current request | Upstream candidate | Independently validated safety floor | Expected selection |
| --- | --: | --: | --: | --- |
| app | 1000 mCPU | 500 mCPU | 500 mCPU | Evaluate the 500 mCPU candidate against its own gates |
| sidecar | 100 mCPU | 80 mCPU | 75 mCPU | Independently evaluate 80 mCPU; do not copy the app value |

Now add a second conflicting app candidate. Expected result: app is ambiguous and blocked; the valid sidecar target remains independently evaluable. Instead change only the sidecar candidate to 50 mCPU: it is below its floor and blocks, while the app remains independently evaluable. CPU and memory are also separate dimensions. Stop on any missing target-specific evidence, and never output a whole-manifest or other-container change. Platform/source owners resolve conflicts; each container's application owner owns approval/rollback for any later experiment.

### Use Missing History As A Stop Condition

Input: existing ordinary Prometheus CPU usage/request series retain cluster resource ID, namespace, Pod name and container, but no historical workload/Pod UIDs. Keep the existing Grafana rather than installing another source:

```text
aks-fleet-advisor assess --fragments examples/fixtures/ordinary-source-assessment.json --config examples/ordinary-source-config.yaml --pack AKS-RQ-002 --mode baseline --as-of 2026-10-29T12:00:00Z --format json
```

Expected result: exit `3`, two `baseline_measurements`, explicit gaps and no numeric request proposal. Current names cannot relabel those samples. The monitoring owner may review already retained identity evidence, but new recordings cannot backfill it. Choose a current-metadata question or stop with an owned gap; defer memory, guarded mode and financial inputs. Section 9 should state what remains useful, what was deferred and when the owner will revisit it. An unsupported guarded comparison does not invalidate the selected ordinary baseline measurements.

### Keep Financial Review Optional

For a FinOps question only, run the [financial tutorial](../tutorials/reconcile-existing-cost-evidence.md) with fresh paths. Expected fictional outcomes: native FOCUS without historical bindings remains `blocked` with USD 100 retained; reviewed amortized row shares produce `reconciled` USD 60 allocated, USD 25 idle and USD 15 system; actual/native aggregate evidence remains `attributed`. Savings stay null in all cases. These amounts partition one charge and must not be counted again as additional cost or converted from the request reduction ratio.

FinOps owns basis, period/currency, commitments and any later comparable financial outcome. Stop with unassessed/inconclusive financial effect when that evidence is absent, even if a separate engineering test succeeds. No billing permission, financial import or new tool is required for the other exercises.

## Completion Check

- [ ] I can explain a finding and a gap without claiming an approved change.
- [ ] Each unknown has an owner; no missing value became zero or assumed absence.
- [ ] At least one retain/defer/investigate/test decision has rationale, accountable owner and next date.
- [ ] Any approved test has a separate SLO/scenario/rollback record; finance has its own owner/record only when in scope.
- [ ] Scope, dates, source/rule references and next review are recorded.
- [ ] Populated workbook and reports are protected under customer policy.

Exact boundaries remain in [security](../security-and-privacy.md), [data contracts](../data-contracts.md) and [customer change validation](../accelerator-docs/implementation-guide.md).
