# Assess Your AKS Environment

[Documentation home](../README.md) | [Learn first](getting-started.md) | [Next: implementation](implementation-guide.md)

Use this guide when the team can explain a fictional report and is ready to
investigate a small part of its own AKS environment. You will agree a question,
prepare approved data, run an assessment and assign owners to findings and gaps.
No hosted service or replacement monitoring system is required.

**Expected outcome:** a reviewed report with clear limits and next decisions.
It may conclude that more information is needed or current capacity should be
retained. A numeric suggestion, implemented change or savings claim is not
required to complete an assessment.

## Before You Begin

Complete the [first-run lab](getting-started.md) and
[report interpretation](../tutorials/interpret-your-first-report.md). For a real
assessment, get the application, platform, monitoring and security owners
involved before access is requested. Include FinOps for any financial question.

| Input | Meaning and owner |
|---|---|
| Assessment profile | A configuration file describing approved scope, input systems and selected checks; [prepare it with the platform owner](../how-to/prepare-an-onboarding-profile.md) |
| Approved saved data or collection plan | Files meeting the advisor's input contracts, or a separately authorized plan for limited real reads |
| Input-system review | Actual identities, permissions, network access and historical data verified by their owners; [review the sources](../how-to/validate-source-compatibility.md) |
| Protected output location | An existing parent folder, a new assessment directory, and agreed access/encryption/retention |
| Application requirements | Representative demand/peaks, service-level objectives and constraints supplied by the owner |

Commands below run from the repository root in either Windows PowerShell or
Linux/macOS after installation. Names such as `approved-profile.yaml`,
`approved-fragments.json` and `approved-plan.json` are placeholders for reviewed
customer files, not supplied live configurations. Do not copy fictional IDs,
access settings or owner policies into a customer run.

## 1. Agree Scope And Responsibilities

Start with one approved tenant, one cluster or a small explicit cluster list,
one workload class and one to three questions. For example: "Which placement
restrictions should their owners review?" or "Does qualified CPU history justify
investigating this request?" Do not turn low average fleet usage into a target.

Use the [pilot plan](../how-to/plan-a-bounded-pilot.md) and
[workbook](../facilitator/participant-workbook.md) to record the question,
desired outcome, exclusions, non-regression measures, dates and acceptance owner.
The [questionnaire](../onboarding-questionnaire.md) provides the exact discovery/
profile reference, not a requirement to answer every advanced topic before the
first fictional lesson.

| Owner | Responsibility |
|---|---|
| Sponsor/service owner | Outcome, scope, acceptance and next decision |
| Platform operator | Exact cluster identity, configuration, approved reader/network and effective read-only rights |
| Monitoring owner | Actual retained measurements, meaning/units, historical identifiers, gaps and query budget |
| Application/reliability owner | Demand, SLOs, startup/failover/disruption requirements and workload-specific policy |
| FinOps owner | Cost period/currency, attribution, commitments and independent financial review |
| Security/data owner | Approved fields, access consent, storage, report audience and retention |

One person can hold multiple roles, but collection approval and production
change approval remain separate decisions.

**Checkpoint:** everyone can explain what is in scope, what must not regress,
who can approve reads and what counts as a useful result. Shared/dedicated,
stateful, regional and specialized workloads may need different assessments;
do not extrapolate this pilot to them.

## 2. Choose The Smallest Useful Assessment

Use [check selection](../how-to/choose-recommendation-packs.md) before requesting
more data. A pack is a rule's input requirements and review guidance.

| Question | Starting data/check | Limit of the result |
|---|---|---|
| Current placement or capacity classes | Fresh complete approved inventory; `AKS-SCHED-001` / `AKS-NP-002` | No packing simulation, removable-node count or NAP migration approval |
| Missing requests or interacting scaling settings | Current metadata and selected inventory checks | Current observations do not prove historical absence or safe targets |
| CPU usage versus request | Qualified exact-identity history; `AKS-RQ-002`, baseline first | Name-only history does not become workload-bound evidence |
| Memory or replica behavior | That pack's separate current/history, reliability and owner inputs | CPU-ready data do not establish another dimension's readiness |
| Financial attribution | Separate [approved cost projection](../cost-reconciliation.md) and exact period/resource mapping | Attribution is not a forecast or realized savings |

**Evidence required:** review actual input shape, freshness, periods, units,
historical unique identifiers and complete membership with the monitoring/
platform owners. Thirty days of retention alone is insufficient. Today's names
cannot reconstruct old identities. New recordings cannot backfill missing past
data. Supported name-only measurements and current-inventory reviews can remain
useful while affected historical suggestions stay blocked.

## 3. Prepare And Preview Offline

Prepare the profile and, for proposed collection, the exact approved plan.
Keep customer files separate from the fictional examples. An onboarding profile
contains `analysis`; an analysis-only file saved for `analyze` is not a collection
profile. Exact fields remain in the [profile reference](../onboarding-questionnaire.md#versioned-onboarding-profile).

Check supplied configuration/files without contacting services:

```text
aks-fleet-advisor readiness --config approved-profile.yaml --format markdown
```

Expect `3` for unknown facts or `4` for an explicit blocker; review the report.
Offline readiness does not produce proof of live acceptance. Invalid input is
exit `2`; an output-write failure is `1`.

For planned real reads, preview their operations and limits:

```text
aks-fleet-advisor preview --config approved-profile.yaml --plan approved-plan.json
```

Preview normally exits `0` when the request can be described; it may still list
unresolved prerequisites. Review scope, identities, period/queries, installed
rule definitions, budgets and explicit destination. Neither command verifies
connectivity/permissions, authenticates sources or creates the output directory.
A flag, reference or content hash is not consent.

Protect the artifact location with customer-approved access, encryption,
retention and audience controls. Sanitized metadata still identifies workloads.
Never commit customer reports, real IDs, credentials or raw exports. Review
the [excluded data and transient Pod-decoding boundary](../security-and-privacy.md#kubernetes-clusterrole-sketch):
if transient full Pod decoding is prohibited, use an approved sanitized reader/
export or stop. Do not treat projection as server-side field exclusion.

## 4. Import Or Collect Approved Evidence

Choose one workflow. Start with approved saved files where possible. Files
must meet [the input contracts](../data-contracts.md); arbitrary `kubectl` or
dashboard exports do not. Never edit completion records or fabricate identities.

### Import Saved Evidence

This command reads reviewed files and makes no service requests:

```text
aks-fleet-advisor assess --config approved-profile.yaml --fragments approved-fragments.json --mode baseline --format markdown --artifacts new-assessment
```

Replace `new-assessment` with a new directory below your existing approved
storage parent. The advisor refuses overwrites; the profile destination is not
used implicitly. Use the current time, not the fictional examples' date, for a
current customer assessment.

### Collect Approved Evidence

**Separate authorization required:** this workflow performs real Azure/metrics
reads. Obtain approval for exact scope/source, independently verified cluster
binding, principal/runner, period/queries, budgets, destination, consent expiry
and stop contact before running it. The CLI uses sanitized Kubernetes exports,
not kubeconfig/login plugins. A `--allow-live` flag alone is not approval.

Follow the [runbook's installation and transport requirements](../operations/runbook.md#installation-and-preflight)
for the `azure,kubernetes,metrics` extras and supported network/authentication
path. Private proxy/CA/cloud needs require explicit validation, not disabled TLS
or an unapproved tunnel. Only after independent approval:

```text
aks-fleet-advisor assess --config approved-profile.yaml --plan approved-plan.json --allow-live --mode baseline --format markdown --artifacts new-assessment
```

Review effective inherited/group permissions: GET-only code is not proof of a
read-only identity. No Contributor, cluster-admin or write grants belong on the
advisor identity. The operator demo's setup writes are not production onboarding.
Stop on identity/TLS mismatch, unsafe fields, unexpected privileges, exhausted
budgets or expired/withdrawn consent; do not broaden access to finish the run.

## 5. Review Your Report

Both assessment workflows return `0` for complete supported-scope assessment,
`3` for partial/blocked, `2` for invalid input/prerequisites and `1` for output
failure. `collect` uses `0` for complete requested collection and `3` for partial
receipts; do not confuse these with readiness meanings.

Open the saved `report.md` and use the
[interpretation tutorial](../tutorials/interpret-your-first-report.md). Explain
the exact target, dates, units, rule/version, risk and next owner action.
Distinguish observations, investigations, missing/unsupported information and
independently eligible guarded suggestions. High confidence does not approve change.

Keep all [six assessment files](getting-started.md#assessment-files) together.
An interrupted folder without the final manifest is not a completed export.
File hashes help detect changes; they do not prove truth, source completeness
or approval. To repeat a past analysis, retain its original compatible package,
saved rule/configuration definitions, inputs and evaluation date. Do not edit
hashes to conceal differences or reuse that past date to qualify a current change.

No successful exit or empty recommendations list certifies health, source
acceptance, production readiness or change approval. Independently useful
current findings can coexist with historical gaps.

## 6. Record Your Next Actions

Use the [workbook](../facilitator/participant-workbook.md) or customer work
tracker for one row per investigation, suggestion or gap. This is a human review
record, not a computed priority score.

| Field | Required content |
|---|---|
| Finding and evidence | ID, pack/version, exact target, period and protected artifact reference |
| Decision | Investigate, gather information, retain settings, evaluate a suggestion, defer or reject, with rationale |
| Priority | Owner-reviewed reliability urgency, business relevance, dependencies and blast radius |
| Owner/date | Accountable next action and review date |
| Candidate test | A [hypothesis](../facilitator/assessment-hypothesis.md), independently approved test, rollback and acceptance evidence if justified |
| Financial state | Unassessed, attribution only or separately validated outcome; advisor savings stay `null` |

Complete when owners understand the report's limits and own the next decisions.
For an approved candidate, continue to [change validation](implementation-guide.md).
If the next step is more information, retain/defer that decision explicitly.
Expand only after representative evidence and independent acceptance for the
next scope, not because the fictional demonstration worked.