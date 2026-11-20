# AKS Fleet Efficiency Advisor: Learn, Assess And Validate

Use the advisor to investigate resource settings across your Azure Kubernetes Service (AKS) clusters before deciding what to change. It reads approved configuration and measurements and produces reports: what was observed, what needs investigation and what information is missing.

For example, a low CPU-usage measurement can suggest a request deserves review. It cannot tell you whether that request protects startup or failover behavior. Your application and platform owners supply those requirements and decide what to test. The tool does not approve or apply changes or calculate savings.

**You can start without Azure or Kubernetes access.** The learning path uses fictional data, called synthetic data in the examples. No cloud identity or AI model is required. The advisor's analysis is fixed-rule code, not an AI model.

## Start Here

Choose a pace. You do not need to read the technical references before trying the fictional assessment.

| Your goal | Start with | What you produce |
| --- | --- | --- |
| Learn the concepts before running anything | [Seven short learning modules](#learn-the-concepts) | Existing-tool baseline plus worked answers about resources, scaling, data quality and value |
| Investigate without installing Python | [Low CPU in Grafana](how-to/investigate-low-cpu.md) | Two scoped PromQL queries, a dashboard, and a question for the workload owner |
| Try the optional advisor and understand a report | [First-run lab](accelerator-docs/getting-started.md), then [interpret the report](tutorials/interpret-your-first-report.md) | A saved fictional report and an explanation of a finding/gap |
| Assess your existing clusters | [Customer assessment](accelerator-docs/assessment-guide.md) | Agreed scope, reviewed inputs, a report and owned next actions |
| Run regularly | [Schedule assessments](how-to/schedule-assessments.md) | Replayable bundles and a generated Headlamp feed from fresh approved files |
| Lead a customer/team engagement | [Facilitator delivery guide](facilitator/delivery-guide.md) | Session outputs, a workbook and a clear pilot decision |
| Validate a separately approved improvement | [Change and value validation](accelerator-docs/implementation-guide.md) | Test/rollback evidence and a measured result, possibly inconclusive |
| Look up exact requirements | [Reference library](#reference-library) | Authoritative field, rule, source and security definitions |

### Choose Your Role

- **Application owner:** start with [outcomes](learning/01-why-fleet-efficiency.md) and [resources](learning/02-requests-limits-and-utilization.md); bring demand peaks and service-level objectives, the measures a change must preserve.
- **Platform/monitoring engineer:** complete the shared lab, then [choose checks](how-to/choose-recommendation-packs.md), [prepare a profile](how-to/prepare-an-onboarding-profile.md) and [review data sources](how-to/validate-source-compatibility.md).
- **FinOps practitioner:** start with [existing Microsoft and FinOps tools](learning/00-start-with-existing-tools.md), then read [cost attribution versus savings](learning/06-cost-attribution-versus-savings.md); own source selection, financial baseline and outcome review.
- **Security/governance reviewer:** review [data/access decisions](how-to/plan-a-bounded-pilot.md) and [security boundaries](security-and-privacy.md); collection consent is not change approval.
- **Facilitator/team lead:** use the [delivery guide](facilitator/delivery-guide.md), [workbook](facilitator/participant-workbook.md) and [hypothesis template](facilitator/assessment-hypothesis.md); populated customer records stay in approved storage, not Git.

### First-Session Checkpoints

Allow about 60-90 minutes after workstation setup for the lab and interpretation. Dependency installation depends on your approved package source and network.

- [ ] Run a fictional assessment and explain its expected exit code.
- [ ] Identify a configuration/measurement, its date and units behind one finding.
- [ ] Explain one gap without treating missing information as zero or healthy.
- [ ] Distinguish an investigation, a numeric suggestion and independent approval.
- [ ] Name the owner and evidence needed for the next customer question.

These are learning outcomes, not certification of your source or permission to change a workload. A participant explanation matters more than a green command.

<a id="learn-the-optimization-model"></a>

## Learn The Concepts

Each page has a fictional scenario, an exercise, an expected answer and links to exact requirements. Read in sequence or revisit the concept blocking your task.

0. [Start with existing Microsoft and FinOps tools](learning/00-start-with-existing-tools.md): identify what supported products and approved enterprise tools already establish before adding accelerator analysis.
1. [Why efficiency starts with an application outcome](learning/01-why-fleet-efficiency.md): low utilization can be intentional reserve.
2. [Requests, limits and usage](learning/02-requests-limits-and-utilization.md): distinguish settings, measurements and whole-Pod accounting.
3. [Resources, replicas and node scaling](learning/03-horizontal-vertical-and-node-scaling.md): understand which tool owns which decision.
4. [Data quality and historical identity](learning/04-evidence-quality-and-historical-identity.md): a reachable service is not necessarily sufficient history.
5. [Findings, risk and confidence](learning/05-recommendations-risk-and-confidence.md): supported investigations and suggestions are not approval.
6. [Cost attribution versus financial value](learning/06-cost-attribution-versus-savings.md): assigned cost is not forecast or realized savings.

## The Adoption Journey

1. **Inspect an existing observation:** retain its tool, date and protected reference from current Prometheus/Grafana, Advisor/workbook/AOE, VPA or cost-tool review. State the question those tools have not already answered.
2. **Choose one useful entry point:** current metadata, ordinary CPU measurements, or qualified history and an upstream candidate. [Select only relevant checks](how-to/choose-recommendation-packs.md#three-ways-to-start); finance and advanced integrations are optional.
3. **Run and explain:** complete the [fictional lab](accelerator-docs/getting-started.md), then [interpret the report](tutorials/interpret-your-first-report.md). For customer data, first obtain the scoped [source/access review](how-to/validate-source-compatibility.md) and [pilot approval](how-to/plan-a-bounded-pilot.md).
4. **Review constraints and decide:** use the [worked exercises](facilitator/participant-workbook.md#worked-exercises) to record observed versus declared facts, missing evidence, intentional reserve, an owner and a next date. Retain/defer is as valid as requesting a test.
5. **Test only after separate approval:** [validate one dimension](accelerator-docs/implementation-guide.md) through current customer delivery and monitoring tools, with independent SLO/scenario/rollback evidence. Optional FinOps review remains separate; request percentages are not financial value.

The common example is an existing low-CPU observation: ordinary name-only series support bounded measurements, while a fresh saved VPA target additionally needs exact identities, qualified history and owner policy before guarded validation. The [assessment guide](accelerator-docs/assessment-guide.md#worked-enterprise-question) carries this example through the owner handoff; the workbook covers missing history, two containers and a no-change outcome. No new service, recommender, Grafana instance or complete telemetry overhaul is part of this journey.

Start with one cluster, a small workload class and one to three questions. "Fleet" means the approved clusters, not a requirement for Azure Kubernetes Fleet Manager. The advisor does not place or migrate workloads between clusters.

An outcome can be better information, retained intentional capacity, a deferred change or an inconclusive test. Do not expand scope just to obtain a proposal.

## What You Can Use Today

The advisor is a local command-line tool. It can analyze approved saved files or perform separately approved, limited read-only collection. The CLI uses sanitized Kubernetes exports; it does not sign in through kubeconfig plugins. Exact supported transports and data shapes need review for your environment.

By default, `baseline` mode identifies investigations without replacement values. `guarded` mode evaluates supported numeric suggestions only when all required data, reliability checks and owner policies pass. Some proposal types also need an explicit owner opt-in. Neither mode approves changes.

The separate cost workflow normalizes approved saved financial evidence. Source-native or actual evidence remains `attributed`; compatible amortized/effective original-row partitions can become `reconciled`. Savings remain `null` for every status. Saved assessments can be compared directly under [artifact comparison rules](operations/history.md#compare-artifact-directories), without importing a store, but a disappearing finding does not prove resolution or savings.

The optional [Headlamp Assessments dashboard](../plugins/headlamp-fleet-efficiency/docs/operations.md#schedule-assessment-publication) displays published advisor evaluations, retained workloads and blocked checks. Use an existing scheduler and an authorized same-origin endpoint; no Kubernetes operator is required. The separate [governance preview](../plugins/headlamp-fleet-efficiency/README.md) uses fictional records and simulated review states. Production governance, Git delivery and an authenticated governance backend are not supplied.

## Principles To Carry Forward

- There is no universal safe utilization target.
- Missing evidence is unknown, not zero or proof of health.
- Current names cannot reconstruct deleted or recreated historical objects.
- No report, owner declaration, hash or successful exit approves a change.
- Test request, limit and replica-floor changes separately through customer tooling.
- Do not give the advisor write privileges or disable security checks to finish a run.
- A lower request or reconciled allocation does not establish a lower bill.
- Customer reports still contain environment details; protect their storage and audience.

For a Well-Architected or FinOps delivery, these materials support a bounded evidence workstream. They do not provide an official framework score, certification, complete cost review or savings commitment. The [facilitator guide](facilitator/delivery-guide.md) describes the handoff.

## Reference Library

These pages specify exact behavior. Use them when a task calls for their details; they are not the beginner learning sequence.

| Requirement | Authoritative reference |
| --- | --- |
| Execution and components | [Architecture](architecture.md) |
| Input fields, identities, validation and saved files | [Data contracts](data-contracts.md) |
| Calculations, eligibility and confidence | [Metrics and scoring](metrics-and-scoring.md) |
| Profile fields and offline readiness exits | [Onboarding reference](onboarding-questionnaire.md) |
| Required source fields, history and pilot evidence | [Source compatibility](source-compatibility.md), [source profiles](source-profiles.md) |
| Pack versions, parameters and operator workflow | [Recommendation packs](recommendation-packs.md), [generated catalog](operator-catalog.md) |
| Permissions, excluded data and privacy | [Security and privacy](security-and-privacy.md) |
| Financial source/version capabilities | [Financial source profiles](financial-source-profiles.md) |
| Exact financial projection/allocation | [Cost reconciliation](cost-reconciliation.md) |
| Approved collection, APIs and troubleshooting | [Operations runbook](operations/runbook.md) |
| Advanced scaling/placement design | [Orchestration and scheduling](orchestration-and-scheduling.md) |
| Existing-tool versus accelerator coverage | [Scenario coverage](scenario-coverage.md) |
| Aggregate explicit assessment artifacts | [Fleet insights](fleet-insights.md) |
| Prepare optional pseudonymous AI summaries offline | [AI summary handoff and unverified draft checks](operations/ai-evidence.md) |

Use [Support](../SUPPORT.md) for synthetic reproductions and [Security](../SECURITY.md) for private reporting. Never attach customer data or credentials to public issues. Developer setup remains in [Contributing](../CONTRIBUTING.md), separate from participant prerequisites.
