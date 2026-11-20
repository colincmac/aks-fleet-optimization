# Facilitate An AKS Efficiency Assessment

[Documentation home](../README.md) | [Participant workbook](participant-workbook.md) | [Hypothesis template](assessment-hypothesis.md)

## Purpose And Audience

Help a customer team learn the concepts, interpret a fictional assessment and decide whether a small real assessment is justified. This guide supports self-directed team sessions and Value-Based Delivery (VBD) engagements. It is not an official Microsoft assessment method, certification or savings commitment.

Invite the application/service, platform and monitoring owners needed for the selected question, with security/data review as applicable. Include FinOps only for a financial question. A sponsor agrees the desired outcome; a facilitator keeps observations and decisions distinct. One person may hold several roles, but access approval and change approval remain separate.

## Pre-Session Checklist

- [ ] Inspect a relevant existing Prometheus/Grafana, Advisor/workbook/AOE, VPA or cost-tool observation; record only the question it has not already answered.
- [ ] Agree audience, application classes, one to three questions and non-regression measures.
- [ ] Confirm a reviewed checkout, Python setup and approved dependency source before the session.
- [ ] Rehearse the fictional commands and their expected exits; use the examples' stated date.
- [ ] Prepare fresh local output paths; never overwrite earlier assessment files.
- [ ] Keep cloud credentials, portal identity panes and real customer metadata off the demonstration screen.
- [ ] Use fictional reports for anyone not authorized to see customer environment details.
- [ ] Assign owners for data/access, SLOs, change/rollback and later financial validation.
- [ ] Agree where customer workbook/report copies will be protected, retained and deleted.

The first session needs no Azure/Kubernetes access. Select one [entry point](../how-to/choose-recommendation-packs.md#three-ways-to-start), not every tool or advanced data contract. Financial review and guarded candidate validation are optional. Do not silently substitute the disposable-cluster operator demo; that requires separate authorization for real reads/setup writes and has different prerequisites.

## Suggested Engagement Sequence

Adapt timing to the team's experience and the larger engagement's required artifacts. Installation and customer source validation are not assumed to fit inside the learning session.

| Session | Learning/decision goal | Expected output |
| --- | --- | --- |
| Discovery, about 45 minutes | Agree outcome, scope, reliability constraints and roles | Workbook scope and owned unanswered questions |
| Fictional learning, about 60-90 minutes after setup | Explain one finding, one gap and why neither approves change | Annotated report and participant teach-back |
| Readiness/pilot review, timing agreed with source owners | Establish supported input subset and explicit consent/stop conditions | Supported/blocked/unknown record and bounded pilot decision |
| Assessment review and later change/value review | Hand off owned hypotheses; approve/test separately where justified | Reviewed report, hypothesis, independent change record and measured outcome |

### Session 1: Discover The Application Need

Ask the sponsor what decision the team needs to make, not what utilization percentage it should achieve. Use [the outcome lesson](../learning/01-why-fleet-efficiency.md).

Discovery prompts, with sufficient answers:

- **Application owner:** what must not regress? Obtain named SLO measures and representative startup/peak/failure scenarios, not "the app is important".
- **Platform owner:** what is the exact scope and why is capacity separated? Obtain approved resource identities, workload classes and intentional isolation/reserve, not a list of similar names.
- **Monitoring owner:** what observations exist for that question? Obtain actual retained fields/units, periods, gaps and historical identifiers, not only "we have Prometheus".
- **FinOps owner:** which existing financial tool/profile/version and financial decision are in scope? Obtain protected evidence reference, period/currency, cost basis, allocation/commitment assumptions and review owner, not a request-to-currency conversion.
- **Security/data owner:** what may be read and shown? Obtain effective read-only permission review, data/transient-decoding constraints, storage/audience and consent owner, not broad role grants.

**Checkpoint:** the team can state an outcome and a falsifiable question with one application/platform owner. If it cannot, continue discovery rather than requesting collection access.

### Session 2: Demonstrate And Ask Participants To Explain

Begin with [existing tools](../learning/00-start-with-existing-tools.md). Use the [first labs](../accelerator-docs/getting-started.md), then [interpret the report](../tutorials/interpret-your-first-report.md). The latter contains exact commands, expected exits, failure meanings and cleanup.

Use the [worked exercises](participant-workbook.md#worked-exercises) as the common thread: an existing observation, one unanswered question, selected evidence, constraints, then an owned retain/defer/test decision. Choose the relevant exercises; do not make finance, VPA or every dimension mandatory.

1. Review intentional warm capacity: retain it when independently reviewed requirements justify it, or defer pending the named test. A low average or idle allocation does not prove waste.
2. Run current metadata or ordinary CPU baseline: one current finding or unresolved measurement can be useful while advanced history remains unavailable.
3. Optionally inspect saved Off-mode VPA status: preserve the upstream 500 mCPU/313 MiB targets and separate collection time from independently established generation age. Current Off mode alone does not establish historical mode or SLO compliance.
4. Work through app/sidecar selection: ambiguity is per exact container and dimension, not permission to change the whole manifest.
5. Record one outcome and owner/date in workbook section 9. Request separate one-dimension test approval only when justified; optional financial review never converts request percentages into cash.

**Facilitator note:** let participants identify dates, units, observed facts, missing information, rule version and next owner action before explaining your answer. Ask what could disprove their interpretation. Do not count successful command execution as demonstrated understanding.

Expected answers:

| Prompt | Sufficient interpretation |
| --- | --- |
| What does the node selector establish? | A current placement restriction; owner intent and fit still need review |
| Why is the CPU result partial? | Unsupported pool input remains visible without erasing independently valid workload evidence |
| Does high confidence approve a request change? | No; it describes supporting information for the finding |
| Why is readiness unknown? | Actual access, retained identities and source facts remain unverified |
| What did the fixed date do? | Repeated a past fictional assessment; it must not make stale customer inputs eligible today |
| Can we keep our Grafana and defer advanced history? | Yes; use only supported selected measurements/current checks and record the remaining gap |
| Does VPA collection time prove candidate age? | No; missing independent generation evidence blocks numeric request validation |
| Must the two containers receive the same decision? | No; each exact target/dimension has independent candidate, policy and evidence gates |

**Checkpoint:** each participant can explain a finding and a gap in their own words. Revisit the relevant [learning module](../learning/01-why-fleet-efficiency.md) when they cannot; do not make a live pilot the learning exercise.

### Session 3: Make A Readiness Decision

Complete [data-source review](../how-to/validate-source-compatibility.md) and [pilot planning](../how-to/plan-a-bounded-pilot.md) with the actual owners. Use the authoritative source worksheet for exact shapes and consent limits.

Pause or narrow the pilot when:

- Required ownership, exact scope or customer approval is absent.
- The reader's effective identity has write privileges or provenance is unverified.
- Required historical identities/membership or metric meaning are missing.
- Network/certificate/transient-data requirements are unsupported.
- The selected period misses business peaks or current evidence is stale.
- Reports cannot be stored/shared under an approved policy.
- No owner can define SLO/test/rollback criteria for a proposed later change.

An inventory-only assessment or a gap backlog can be a valid outcome. Missing financial data block a financial conclusion, not an independently eligible current-configuration investigation. Do not lower safety requirements to create a more impressive demonstration.

### Session 4: Handoff To Owners, Not Automatic Remediation

Run the [assessment sequence](../accelerator-docs/assessment-guide.md) only within independent approval. Review the report and preserve the original saved files. Use one [hypothesis record](assessment-hypothesis.md) per candidate intervention. That template does not authorize implementation.

The customer change owner separately agrees and tests one dimension with representative load, explicit abort/rollback criteria and independent reliability signals. Follow [change validation](../accelerator-docs/implementation-guide.md). FinOps separately establishes any financial outcome from comparable approved billing evidence. Advisor savings remain null, including after reconciliation.

Retain the customer's current Grafana/SLO views, change pipeline, rollback tooling and review record. A protected report reference in an existing ticket is enough; no accelerator control plane or workbook/AOE connector is supplied. If reserve is retained or a dimension deferred, complete the rationale/owner/date without inventing a change record or a financial outcome. Automated command checks are facilitator rehearsal evidence, not proof that an unfamiliar participant understood or adopted the solution.

## Handling Common Objections

| Objection | Discussion response |
| --- | --- |
| We already have monitoring | Good; verify whether the retained fields, identities and periods answer this particular question |
| Just show the savings | First establish engineering behavior and billed-resource effects; allocation/request percentages are not savings |
| Guarded means safe | It means supported eligibility checks passed, not owner approval or proof under future demand |
| Missing metrics mean no incidents | Missing is unknown; complete observed zero is a different state |
| Can we shorten history to get a target? | A shorter transport test is not recommendation history; narrow/re-scope instead of bypassing a gate |
| Can the tool implement it? | No; use the customer's authorized delivery and rollback process, not writes on the advisor identity |

## Debrief And Expected Handoff

Ask: what changed in your interpretation, what remains unknown, who resolves it, what would disprove the hypothesis, and what decision happens next? Record retained intentional capacity, deferment, rejection, rollback and inconclusive results as legitimate outcomes.

Hand over the completed customer workbook, reviewed report with protected artifact references, gap owners, hypothesis/change records where applicable, and the next review/retention responsibilities. Never attach customer evidence to a public repository issue; use synthetic reproductions for support.

In larger Well-Architected or FinOps engagements, map these outputs to the engagement owner's artifacts. The advisor supplies a bounded evidence workstream, not a framework score, full cost assessment or authority over change.

## Authoritative Boundaries

[Data handling and permissions](../security-and-privacy.md), [source acceptance](../source-compatibility.md), [findings](../data-contracts.md#recommendation-and-replay) and [always-null savings](../metrics-and-scoring.md#savings-rules) remain authoritative.

## Run An Uncoached First-Use Check

Choose a platform operator who has not used the accelerator. Give them only the repository README and, for the fleet task, a reviewed checkout or a compatible wheel and fictional input ZIP. Ask them to start from the README and narrate where they get stuck. Do not send customer records or provide real credentials. The [low-CPU walkthrough](../how-to/investigate-low-cpu.md) has a browser-only worked case; using a prepared synthetic Grafana datasource is an optional, separate test of the import experience.

| Ask the operator | Listen for after they answer |
| --- | --- |
| Explain the low-CPU observation and hand one decision to a workload owner. | Correct usage and request units, the historical identity gap, and why changing a request could affect a CPU-utilization HPA. A retain or defer decision names the owner and evidence still needed. |
| Compare the two fictional clusters, then explain the result after reviewing a different check on the peer. | Partial assessment exits still produce bundles. The same finding can recur in comparable assessments, but a different check makes the comparison unsuitable for ranking or claiming a fix. |

For each task, record the revision, environment, time to first useful result, first point of confusion, any help you supplied, and the operator's explanation. Mark **unassisted**, **with help**, or **not completed** separately for each task. Keep notes in approved storage. An automated rehearsal can confirm command and dashboard behavior, but cannot pass this check for the operator.
