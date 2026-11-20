# AKS Fleet Efficiency Advisor

Use this read-only accelerator when your existing Azure Kubernetes Service (AKS) tools show something worth investigating but do not settle what to do. For example, Grafana shows low CPU usage and VPA recommends a smaller request. Would that change how the workload's CPU-based Horizontal Pod Autoscaler (HPA) scales replicas during a peak?

Start with one workload. The local CLI checks configuration and measurements against fixed rules, orders findings by severity, and explains what evidence is missing. Then [compare saved assessments across clusters](docs/fleet-insights.md) to see which findings or gaps recur among comparable peers. This is not a fleet efficiency score or a ranking by savings.

No cluster changes, billing access or AI model are needed for the [fictional quick start](#quick-start). Optional AI explains selected findings; it does not generate them or approve a change.

**If the question is cost allocation**, start with [AKS Cost Analysis in Microsoft Cost Management](https://learn.microsoft.com/azure/aks/cost-analysis), or the customer's existing OpenCost or Kubecost installation. Stop there if it answers the question. For a separate comparison, the advisor can [read a reviewed, saved allocation](docs/cost-reconciliation.md#inspect-saved-allocation-without-a-ledger); it does not connect to those products, change their amounts or infer a lower bill.

## Start here

Choose the outcome you need. The first two paths do not require Python or an advisor deployment.

| Start here | What you need | What you get |
| --- | --- | --- |
| [Learn with an existing Microsoft or FinOps tool](docs/learning/00-start-with-existing-tools.md) | A browser; fictional examples are included | Decide whether your existing tool already answers the question. If it does, stop there. |
| [Investigate low CPU in Grafana](docs/how-to/investigate-low-cpu.md) | A browser for the worked example; an approved Prometheus datasource for your own queries | Two scoped queries, an importable dashboard, and a decision to retain the request or investigate further. |
| [Run the optional advisor](#quick-start) | Python and the supplied fictional files; no cloud credentials | A repeatable report with findings and missing evidence. Start with one workload before comparing clusters. |
| [Operate recurring assessments](docs/how-to/schedule-assessments.md) | Fresh approved inputs and a customer-owned scheduler; optional Headlamp host | Replayable per-cluster bundles, a generated assessment feed, and a checklist to detect and recover missed runs. |

## One Scoped Journey

For example, your existing Grafana panel shows low CPU usage beside a high request. That observation does not establish a safe replacement request or a financial saving. Start with one cluster, one application and one unanswered question:

1. Retain the existing-tool observation and its date/source reference; stop if it already answers the question.
2. Select current-metadata checks, ordinary CPU measurements or optional qualified candidate validation using the [three entry points](docs/how-to/choose-recommendation-packs.md#three-ways-to-start). No billing import, VPA deployment or new monitoring is required for basic entry points.
3. Run only the relevant checks over approved evidence and review observed facts, missing history and owner constraints. Name-only samples remain unresolved, not invented workload history.
4. Record one owned decision: retain intentional capacity, defer a dimension, investigate a gap or request separate approval to test one candidate. Use the existing [participant workbook](docs/facilitator/participant-workbook.md#worked-exercises).
5. Only after independent approval, test one dimension through existing delivery tools with representative load, SLO/abort measures and exact rollback. FinOps may separately review bill effects; advisor savings stay `null`.

The outcome is a better owner decision, not a green report or a fleet-wide rollout. The worked exercises include recommendation-only VPA, two-container selection, missing history and an intentional no-change decision. Start with the fictional quick start below, then follow the [assessment](docs/accelerator-docs/assessment-guide.md) and [change-validation](docs/accelerator-docs/implementation-guide.md) guides for your chosen scope.

Application owners bring knowledge of demand and reliability requirements; platform engineers bring cluster and monitoring knowledge; FinOps practitioners review financial outcomes. The [documentation home](docs/README.md) connects learning, assessment and change validation, with [a bounded pilot guide](docs/how-to/plan-a-bounded-pilot.md) for the next decision. This can support a larger Well-Architected or FinOps delivery, but it does not replace that engagement's assessment or approval process.

## Assessment outcomes

- Find workloads whose CPU or memory settings warrant owner review.
- Review scaling settings and restrictions on where Pods can run.
- See which conclusions the available data support and which need more information.
- Save reports and their inputs so another reviewer can repeat the analysis.
- Normalize approved saved Cost Management/FOCUS ledgers and reviewed AKS Cost Analysis/OpenCost/Kubecost attribution without replacing those tools. Actual or aggregate evidence remains `attributed`; compatible amortized/effective row partitions can become `reconciled`; savings remain `null`.

## Quick start

Allow about 15 minutes after setup. Python 3.15 or newer is required. Follow the [workstation setup](docs/accelerator-docs/getting-started.md#1-prepare-your-workstation) for Windows or Linux/macOS, then run this example from the repository root. This snapshot check works with the base advisor; the optional Kubernetes extra is used in later saved-fragment labs, not to connect to a cluster.

**Example: fictional cluster data.** The following command reads a supplied snapshot, a saved description of cluster and workload configuration. It checks restrictions on where a Pod can run and prints a report. It makes no Azure or Kubernetes requests and creates no cloud resources.

The example's data are dated October 29, 2026. `--as-of` tells the advisor to evaluate their age as of that date, rather than today, so the example remains repeatable. It does not change your computer's clock. For a current customer assessment, omit this option; an old date must not be used to make outdated measurements appear current.

Run this command in either Windows PowerShell or Linux/macOS after setup:

```text
aks-fleet-advisor analyze --snapshot examples/fixtures/scheduling-review-snapshot.json --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --format markdown
```

Here `--pack AKS-SCHED-001` selects the scheduling-review rule, rather than every available check. A **recommendation pack** describes a rule's required inputs and review guidance.

**Expected result:** exit code `0`, one recommendation titled **Investigate current placement constraints**, and zero blocked findings. Compare the [example report](examples/expected-scheduling-review.md). The recommendation asks you to review placement restrictions; it does not say they are unnecessary or that a node can be removed. Exit `0` means the analysis ran successfully, not that the cluster is healthy or ready for a change.

Next, complete the [guided labs](docs/accelerator-docs/getting-started.md) to investigate CPU settings, interpret missing information and save analysis files. The quick-start command prints its report without creating output files; no cloud cleanup is required. For setup failures, use the [troubleshooting guide](docs/accelerator-docs/getting-started.md#troubleshooting).

<a id="brownfield-onboarding"></a>

## Use your own cluster data

A **data source** is a system or file supplying information for the assessment: Azure cluster inventory, Kubernetes configuration, a Prometheus-compatible monitoring system, or a separately prepared cost export. It does not mean the advisor's Python source code.

Before a pilot, check whether those systems provide the information needed for your chosen question, in the expected format and over the required period. The guides call this **source compatibility**. For example, being able to query CPU metrics does not prove that the retained data identify the exact workloads and Pods that ran during the measurement period. Today's Pod names cannot fill in that missing history.

Your platform and monitoring owners must also verify the runner's network access and effective read-only permissions. Start with one cluster and a small set of questions using the [customer assessment guide](docs/accelerator-docs/assessment-guide.md). Use the [data-source checklist](docs/source-compatibility.md) when preparing the actual inputs. If historical metrics are unavailable, some current-configuration reviews can still be useful; keep the missing information visible.

The `readiness` command checks configuration and supplied files without contacting these systems. Its `unknown` result means facts such as connectivity or retained history have not been verified. See the [readiness guide](docs/onboarding-questionnaire.md#offline-readiness) for exact checks and exit codes. A working fictional example does not validate customer data.

## Safety and offline replay

By default, the advisor identifies settings to investigate without choosing replacement values. The command-line name for this is **`baseline` mode**. For example, it may ask an owner to review a low CPU-usage-to-request ratio; it does not turn that observation into a safe CPU setting.

**`guarded` mode** allows supported checks to propose numeric settings only when their required measurements, reliability checks and workload-owner policies are present and pass. Some proposal types also require a separate owner opt-in. Choosing this mode does not approve a change or bypass missing information.

The customer owns testing, approval, implementation and rollback. Test one change at a time through the [change-validation guide](docs/accelerator-docs/implementation-guide.md). No findings, missing measurements or a successful command are proof that a workload is healthy. Missing values are unknown, not zero.

**Offline replay** means repeating the analysis of saved inputs without collecting new data. Keep the original inputs, configuration, compatible package and evaluation date together. This reproduces a past assessment; it does not show that the same conditions hold today. See [saved assessment files](docs/accelerator-docs/getting-started.md#assessment-files) and [exact replay requirements](docs/recommendation-packs.md#replay-and-provenance).

## Architecture

The advisor reads approved cluster/configuration data and, where required, historical measurements. It checks whether the information is sufficient for each selected rule, then writes findings and missing-information explanations to a human-readable Markdown report or a structured JSON report.

The [architecture guide](docs/architecture.md) explains the components. Engineers preparing integrations can look up the exact input requirements in [data contracts](docs/data-contracts.md) and the calculation rules in [metrics and scoring](docs/metrics-and-scoring.md); these are references, not prerequisites for the first example.

## Assessment Workflow

1. Learn with the fictional examples and explain a finding in your own words.
2. Agree the cluster/workload scope, question, owners and success measures.
3. Check the required data, permissions and storage arrangements with their owners.
4. Analyze approved saved files, or separately approve a small, read-only collection.
5. Review findings and gaps; assign an owner and next action to each.
6. Use your existing change process to test any approved improvement and measure the outcome.

The [assessment guide](docs/accelerator-docs/assessment-guide.md) provides the steps and decision records. Collection commands and their permission, data and network requirements are in the [operations runbook](docs/operations/runbook.md). To repeat an assessment, run [`assess-batch` in your existing scheduler](docs/how-to/schedule-assessments.md) after your approved input producer finishes. The advisor does not deploy a monitoring service or schedule collection for you.

## Headlamp Review UI

An optional [Headlamp preview](plugins/headlamp-fleet-efficiency/README.md) lets you explore fictional findings and simulated review decisions in a browser. It is separate from the command-line example and does not import your live assessment. Simulated approvals do not change a cluster or create a production approval system. Production actions remain disabled unless an independently supplied authenticated governance service is integrated.

For your own assessments, use the separate [read-only Assessments tab](docs/how-to/schedule-assessments.md). It reads the generated feed from an authorized Headlamp route and does not need the review CRD or governance backend.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/aks_fleet_efficiency/` | Domain models, collectors, analysis, rules, CLI, and reports |
| `schemas/` | Portable JSON Schemas for snapshots and recommendations |
| `examples/` | Safe synthetic inputs and configuration |
| `docs/` | Customer learning, assessment, implementation, security, contracts and operations |
| `infra/` | Optional infrastructure templates; not required for local assessments |
| `plugins/headlamp-fleet-efficiency/` | Optional browser preview and Headlamp integration |
| `deploy/headlamp/` | Advanced Headlamp installation templates requiring operator review |

## Additional workflows

- [Financial source profiles](docs/financial-source-profiles.md) and [cost attribution](docs/cost-reconciliation.md): normalize approved existing-tool evidence and check attribution; not a savings calculation.
- [Synthetic cost tutorial](docs/tutorials/reconcile-existing-cost-evidence.md): project and reconcile saved evidence without source access.
- [Assessment history](docs/operations/history.md): compare compatible saved reports; a disappearing finding does not prove a problem was fixed.
- [Operations runbook](docs/operations/runbook.md): prepare approved saved evidence or invoke the bounded read-only collector interfaces without a separate demo credential path.
- [Contributing](CONTRIBUTING.md): developer setup and software verification, separate from the customer learning path.

## Trust model

Findings retain the measurements, dates, units and rule versions behind them. Confidence describes the supporting information, not a guarantee of application safety. Cluster/workload names and report text are data, not commands to execute. Customer reports still contain environment details and need approved access, storage and retention. See [security and privacy](docs/security-and-privacy.md).

## License

Provided under the [MIT License](LICENSE). Validate organizational requirements before use.
