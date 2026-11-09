# Participant Workbook

[Documentation home](../README.md) | [Facilitator guide](delivery-guide.md) | [Hypothesis template](assessment-hypothesis.md)

Use this blank customer template during discovery and assessment. It is not an
agent work plan, executable configuration, source certification or approval.
Keep populated versions in approved customer storage, not Git. Do not enter
credentials, raw telemetry, Secret/ConfigMap contents or unapproved identifiers.
Use protected references to reviewed records instead of copying sensitive data.

For training, label every entry **fictional**. For a real engagement, record
scope, owner, date and source of each answer; unknown is an acceptable answer
when it has an accountable next action.

## 1. Scope And Desired Outcomes

| Field | Your answer |
|---|---|
| Engagement/workbook reference and review date | |
| Sponsor and accountable application/platform owners | |
| Engineering question and desired outcome | |
| What must not regress | |
| Approved scope reference: tenant/subscriptions/exact clusters | |
| Environments/workload classes included | |
| Explicit exclusions and why | |
| Success/stop criteria and next decision date | |

Prompt: is the intended outcome an investigation, better information, a tested
engineering change or a separately validated financial outcome? Keep them distinct.

## 2. Workload Classes And Reliability

| Workload class / protected target reference | Demand/startup/peak behavior | SLO/failure/disruption requirements | Owner / missing information |
|---|---|---|---|
| | | | |
| | | | |

SLO means service-level objective. Record actual customer requirements for
latency/errors/throughput/availability and relevant failover/batch scenarios.
Do not use the example settings or a quiet monitoring interval as acceptance.

## 3. Current Controls

| Control or constraint | Observed configuration / protected reference | Intent and owner | Unknown / next action |
|---|---|---|---|
| Requests/limits and admission defaults | | | |
| HPA/VPA/KEDA or fixed replicas | | | |
| Node pools, cluster autoscaler or NAP | | | |
| Placement, topology, disruption and storage | | | |
| Shared/dedicated/specialized or reserved capacity | | | |

HPA/VPA change replicas/resources; KEDA supports event-driven scaling; NAP is
node auto-provisioning. Use the [scaling lesson](../learning/03-horizontal-vertical-and-node-scaling.md)
for responsibilities, not assumptions that these tools are installed or approved.

## 4. Data And Source Readiness

| Question / selected pack | Required input shape | Observed facts and protected reference | Missing/unsupported information | Owner / date |
|---|---|---|---|---|
| | | | | |
| | | | | |

Record actual periods/units, retained historical identities and membership,
resolution/coverage/freshness, current source receipts and approved producer
meaning. "We have 30 days" or "HTTPS responds" does not answer all these questions.
Use the [exact source worksheet](../source-compatibility.md#pilot-evidence-worksheet)
for the source record; this summary does not replace it.

## 5. Access And Data Handling

| Required decision | Protected record / owner / unresolved action |
|---|---|
| Exact identity, runner and independently verified cluster binding | |
| Effective read-only permissions, including inherited rights | |
| Supported network/TLS and transient Pod-decoding policy | |
| Approval for live sources, period, queries, budgets and expiry | Not granted by this template |
| Stop contact and independently bounded transport | |
| Artifact storage, access, encryption, audience and retention/deletion | |

Collection permission is not change permission. Never broaden advisor roles
or disable TLS to complete the workbook.

## 6. Findings And Candidate Hypotheses

| Finding/pack/version and protected artifact | Observed fact | Investigation or gap | Candidate hypothesis, if justified | Owner / next action |
|---|---|---|---|---|
| | | | | |
| | | | | |

Keep measurement, owner declaration and interpretation separate. A guarded
proposal is not approval. Use the [hypothesis template](assessment-hypothesis.md)
only when there is a specific candidate worth independent review.

## 7. Risk, Testing And Rollback

| Field | Your answer |
|---|---|
| Single dimension and exact proposed scope, if any | |
| Original configuration and restoration reference | |
| Representative demand/scenarios and independent measures | |
| Numeric customer guardrails and observation period | |
| Canary cohort and authorized implementation/observation owners | |
| Abort trigger, tested rollback procedure and recovery verification | |
| Independent approval record | Not granted by this template |

Do not combine request, limit and replica-floor changes in a single test.
Unsupported targets need separate engineering work, not a copied policy.

## 8. Financial Validation Assumptions

| Field | Your answer |
|---|---|
| Financial question and FinOps owner | |
| Approved cost basis, period and currency | |
| Allocation/binding/completeness evidence and unmatched amounts | |
| Commitment/discount/price assumptions | |
| Expected engineering effect versus separately owned forecast | |
| Actual comparison evidence, demand/release confounders and double-counting controls | |
| Current conclusion: unassessed / attribution only / inconclusive / separately validated result | |

The advisor's savings fields remain null even after reconciliation. No financial
value is established by filling this table. See the [cost lesson](../learning/06-cost-attribution-versus-savings.md).

## 9. Decisions And Next Actions

| Decision or unresolved question | Rationale / evidence reference | Accountable owner | Next action / date |
|---|---|---|---|
| | | | |
| | | | |

Include investigate, gather evidence, retain current capacity, defer, reject,
request independent test approval, rollback or inconclusive as appropriate.
An absent finding is not automatic resolution.

## Completion Check

- [ ] I can explain a finding and a gap without claiming an approved change.
- [ ] Each unknown has an owner; no missing value became zero or assumed absence.
- [ ] Access, implementation and financial decisions have distinct owners/records.
- [ ] Scope, dates, source/rule references and next review are recorded.
- [ ] Populated workbook and reports are protected under customer policy.

Exact boundaries remain in [security](../security-and-privacy.md),
[data contracts](../data-contracts.md) and
[customer change validation](../accelerator-docs/implementation-guide.md).