# AKS Fleet Efficiency Advisor

Investigate how applications use CPU, memory and node capacity across your Azure
Kubernetes Service (AKS) clusters before deciding what to change.

For example, an application may request much more CPU than it usually consumes.
That could be an improvement opportunity, or it could protect a startup peak or
failover requirement. The advisor helps your team review the measurements,
configuration and missing information behind that question.

It runs as a local command-line tool and produces reports. It does not change
clusters, approve changes or calculate financial savings. Its analysis uses
fixed rules, not an AI model. You can try it with fictional data without an
Azure subscription or Kubernetes cluster.

## Start here

**New to the advisor?** Run the [quick start](#quick-start), then complete the
[guided labs](docs/accelerator-docs/getting-started.md) and
[report-interpretation tutorial](docs/tutorials/interpret-your-first-report.md).
Prefer concepts first? Follow the
[six-module learning path](docs/README.md#learn-the-concepts), with fictional
scenarios and expected answers. You do not need cloud access for either route.

| Goal | Guide |
|---|---|
| Learn with fictional data | [Getting started and guided labs](docs/accelerator-docs/getting-started.md) |
| Explain a report and its missing information | [Interpret your first report](docs/tutorials/interpret-your-first-report.md) |
| Plan an assessment of your clusters | [Customer assessment](docs/accelerator-docs/assessment-guide.md) |
| Lead a team/customer engagement | [Facilitator guide and participant workbook](docs/facilitator/delivery-guide.md) |
| Understand which scaling tool controls what | [Orchestration and scheduling](docs/orchestration-and-scheduling.md), for readers already familiar with Kubernetes |
| Test an independently approved change | [Implementation and value validation](docs/accelerator-docs/implementation-guide.md) |
| Compare saved assessments | [Local assessment history](docs/operations/history.md) |

Application owners bring knowledge of demand and reliability requirements;
platform engineers bring cluster and monitoring knowledge; FinOps practitioners
review financial outcomes. The [documentation home](docs/README.md) connects
learning, assessment and change validation, with
[a bounded pilot guide](docs/how-to/plan-a-bounded-pilot.md) for the next decision.
This can support a larger Well-Architected or FinOps delivery,
but it does not replace that engagement's assessment or approval process.

## Assessment outcomes

- Find workloads whose CPU or memory settings warrant owner review.
- Review scaling settings and restrictions on where Pods can run.
- See which conclusions the available data support and which need more information.
- Save reports and their inputs so another reviewer can repeat the analysis.
- Separately match approved cost records to resources and workloads. Attributed cost is not proof of savings; the advisor's savings fields remain `null`.

## Quick start

Allow about 15 minutes after obtaining the repository and dependencies; package
installation time depends on your network. Use Python 3.12, the tested baseline,
and run commands from the repository root. Install packages through your
organization's approved package feed.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[kubernetes]'
.\.venv\Scripts\Activate.ps1
```

Linux/macOS with Python 3.12 installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[kubernetes]'
source .venv/bin/activate
```

The `kubernetes` extra installs a library for reading resource quantities in the
example; it does not connect to a cluster. If environment activation is blocked,
use the executable paths in the [installation guide](docs/accelerator-docs/getting-started.md#1-prepare-your-workstation)
without changing your machine's security policy.

**Example: fictional cluster data.** The following command reads a supplied
snapshot, a saved description of cluster and workload configuration. It checks
restrictions on where a Pod can run and prints a report. It makes no Azure or
Kubernetes requests and creates no cloud resources.

The example's data are dated October 29, 2026. `--as-of` tells the advisor to
evaluate their age as of that date, rather than today, so the example remains
repeatable. It does not change your computer's clock. For a current customer
assessment, omit this option; an old date must not be used to make outdated
measurements appear current.

Run this command in either Windows PowerShell or Linux/macOS after setup:

```text
aks-fleet-advisor analyze --snapshot examples/fixtures/scheduling-review-snapshot.json --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --format markdown
```

Here `--pack AKS-SCHED-001` selects the scheduling-review rule, rather than every
available check. A **recommendation pack** describes a rule's required inputs
and review guidance.

**Expected result:** exit code `0`, one recommendation titled **Investigate
current placement constraints**, and zero blocked findings. Compare the
[example report](examples/expected-scheduling-review.md). The recommendation
asks you to review placement restrictions; it does not say they are unnecessary
or that a node can be removed. Exit `0` means the analysis ran successfully,
not that the cluster is healthy or ready for a change.

Next, complete the [guided labs](docs/accelerator-docs/getting-started.md) to
investigate CPU settings, interpret missing information and save analysis files.
The quick-start command prints its report without creating output files; no
cloud cleanup is required. For setup failures, use the
[troubleshooting guide](docs/accelerator-docs/getting-started.md#troubleshooting).

<a id="brownfield-onboarding"></a>

## Use your own cluster data

A **data source** is a system or file supplying information for the assessment:
Azure cluster inventory, Kubernetes configuration, a Prometheus-compatible
monitoring system, or a separately prepared cost export. It does not mean the
advisor's Python source code.

Before a pilot, check whether those systems provide the information needed for
your chosen question, in the expected format and over the required period. The
guides call this **source compatibility**. For example, being able to query CPU
metrics does not prove that the retained data identify the exact workloads and
Pods that ran during the measurement period. Today's Pod names cannot fill in
that missing history.

Your platform and monitoring owners must also verify the runner's network
access and effective read-only permissions. Start with one cluster and a small
set of questions using the [customer assessment guide](docs/accelerator-docs/assessment-guide.md).
Use the [data-source checklist](docs/source-compatibility.md) when preparing the
actual inputs. If historical metrics are unavailable, some current-configuration
reviews can still be useful; keep the missing information visible.

The `readiness` command checks configuration and supplied files without
contacting these systems. Its `unknown` result means facts such as connectivity
or retained history have not been verified. See the
[readiness guide](docs/onboarding-questionnaire.md#offline-readiness) for exact
checks and exit codes. A working fictional example does not validate customer data.

## Safety and offline replay

By default, the advisor identifies settings to investigate without choosing
replacement values. The command-line name for this is **`baseline` mode**.
For example, it may ask an owner to review a low CPU-usage-to-request ratio;
it does not turn that observation into a safe CPU setting.

**`guarded` mode** allows supported checks to propose numeric settings only
when their required measurements, reliability checks and workload-owner policies
are present and pass. Some proposal types also require a separate owner opt-in.
Choosing this mode does not approve a change or bypass missing information.

The customer owns testing, approval, implementation and rollback. Test one change
at a time through the [change-validation guide](docs/accelerator-docs/implementation-guide.md).
No findings, missing measurements or a successful command are proof that a
workload is healthy. Missing values are unknown, not zero.

**Offline replay** means repeating the analysis of saved inputs without
collecting new data. Keep the original inputs, configuration, compatible package
and evaluation date together. This reproduces a past assessment; it does not
show that the same conditions hold today. See
[saved assessment files](docs/accelerator-docs/getting-started.md#assessment-files)
and [exact replay requirements](docs/recommendation-packs.md#replay-and-provenance).

## Architecture

The advisor reads approved cluster/configuration data and, where required,
historical measurements. It checks whether the information is sufficient for
each selected rule, then writes findings and missing-information explanations
to a human-readable Markdown report or a structured JSON report.

The [architecture guide](docs/architecture.md) explains the components. Engineers
preparing integrations can look up the exact input requirements in
[data contracts](docs/data-contracts.md) and the calculation rules in
[metrics and scoring](docs/metrics-and-scoring.md); these are references, not
prerequisites for the first example.

## Assessment Workflow

1. Learn with the fictional examples and explain a finding in your own words.
2. Agree the cluster/workload scope, question, owners and success measures.
3. Check the required data, permissions and storage arrangements with their owners.
4. Analyze approved saved files, or separately approve a small, read-only collection.
5. Review findings and gaps; assign an owner and next action to each.
6. Use your existing change process to test any approved improvement and measure the outcome.

The [assessment guide](docs/accelerator-docs/assessment-guide.md) provides the
steps and decision records. Collection commands and their permission, data and
network requirements are in the [operations runbook](docs/operations/runbook.md).
The advisor does not deploy a monitoring service or schedule future collection.

## Headlamp Review UI

An optional [Headlamp preview](plugins/headlamp-fleet-efficiency/README.md)
lets you explore fictional findings and simulated review decisions in a browser.
It is separate from the command-line example and does not import your live
assessment. Simulated approvals do not change a cluster or create a production
approval system. Production actions remain disabled unless an independently
supplied authenticated governance service is integrated.

## Repository map

| Path | Purpose |
|---|---|
| `src/aks_fleet_efficiency/` | Domain models, collectors, analysis, rules, CLI, and reports |
| `schemas/` | Portable JSON Schemas for snapshots and recommendations |
| `examples/` | Safe synthetic inputs and configuration |
| `docs/` | Customer learning, assessment, implementation, security, contracts and operations |
| `infra/` | Optional infrastructure templates; not required for local assessments |
| `plugins/headlamp-fleet-efficiency/` | Optional browser preview and Headlamp integration |
| `deploy/headlamp/` | Advanced Headlamp installation templates requiring operator review |

## Additional workflows

- [Cost attribution](docs/cost-reconciliation.md): check how approved cost records are assigned to resources/workloads; not a savings calculation.
- [Assessment history](docs/operations/history.md): compare compatible saved reports; a disappearing finding does not prove a problem was fixed.
- [Operator demo](docs/operations/operator-demo.md): an advanced exercise using disposable clusters, with separate approval for real operations.
- [Contributing](CONTRIBUTING.md): developer setup and software verification, separate from the customer learning path.

## Trust model

Findings retain the measurements, dates, units and rule versions behind them.
Confidence describes the supporting information, not a guarantee of application
safety. Cluster/workload names and report text are data, not commands to execute.
Customer reports still contain environment details and need approved access,
storage and retention. See [security and privacy](docs/security-and-privacy.md).

## License

Provided under the [MIT License](LICENSE). Validate organizational requirements before use.
