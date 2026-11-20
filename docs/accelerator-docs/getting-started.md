# Getting Started

[Documentation home](../README.md) | [Next: interpret the report](../tutorials/interpret-your-first-report.md)

Run the advisor against fictional cluster data, read the report, and decide what you would ask an application or platform owner before considering a change. These are **synthetic examples**: none of their measurements, workload names or suggested values describe your environment.

**Who this is for:** application owners, AKS platform engineers and team leads trying the advisor for the first time. Basic familiarity with Pods and CPU/memory settings helps; no prior knowledge of the advisor's commands is needed.

Prefer to learn before running commands? The [concept lessons](../learning/01-why-fleet-efficiency.md) introduce resources, scaling, historical data, findings and financial value with worked exercises. They are optional preparation, not a requirement to read all references.

**Time and tools:** allow about 60 minutes after setup. You need a reviewed repository checkout and Python 3.15. Package installation needs access to your approved package feed; the labs run without a network connection once installed. No Azure subscription, Kubernetes access, Fleet Manager enrollment, cloud credentials or AI model is required. No cloud resources are created.

By the end, you will be able to:

- Explain what a report says and what it cannot establish.
- Distinguish an investigation, missing information and a suggested numeric setting.
- Save the inputs and settings needed to repeat an analysis without collecting new data.
- Identify the owners and additional information needed for a customer assessment.

You will produce a report and a folder containing its inputs and analysis settings. In this guide, **evidence** means the configuration, measurements and dates supporting a finding. A **recommendation pack** describes one rule's required inputs and review guidance.

## 1. Prepare Your Workstation

Use Python 3.15, the repository's minimum version and development baseline. For these labs you also need the supplied fictional files; the wheel installs the CLI and its query catalog, not the lab files. Run the lab commands from the repository root. Inspect the package and dependencies under your organization's software policy and use your approved package feed; no cloud credentials belong in the setup.

The pip commands explicitly disable PyYAML's optional C extension because PyYAML 6.0.3 has no Python 3.15 Windows wheel. This uses its supported pure-Python implementation without requiring C++ Build Tools. If using uv instead, `uv sync --locked` applies the repository's equivalent build setting automatically; then activate the environment.

Windows PowerShell:

```powershell
py -3.15 -m venv .venv
$env:PYYAML_FORCE_LIBYAML = "0"
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\Activate.ps1
```

Linux/macOS with Python 3.15 installed:

```bash
python3.15 -m venv .venv
PYYAML_FORCE_LIBYAML=0 .venv/bin/python -m pip install .
source .venv/bin/activate
```

If your organization supplied a compatible, reviewed wheel, use its local path instead of `.` in the install argument. For example, `python -m pip install './aks_fleet_efficiency_advisor-0.1.0-py3-none-any.whl'` in the activated environment. Use the actual filename supplied to you. For the [standalone fleet lab](../fleet-insights.md#try-it-with-two-fictional-clusters), run from the extracted bundle's root instead of a checkout.

The base install is enough for `catalog list`, the placement snapshot and the two-cluster fleet lab. No Azure or metrics extra is needed for these labs. If activation is restricted, use the virtual environment's executable in place of `aks-fleet-advisor`: `.\.venv\Scripts\aks-fleet-advisor.exe` on Windows or `.venv/bin/aks-fleet-advisor` on Linux/macOS. Do not weaken machine execution policy just to activate the environment.

Check the install. These commands work in Windows PowerShell and Linux/macOS after environment setup:

```text
aks-fleet-advisor --help
aks-fleet-advisor catalog list
```

Checkpoint: command help and the pack list appear without authentication. The full developer verification toolchain is optional for learning; maintainers should follow [Contributing](../../CONTRIBUTING.md), including its explicit pinned-tool setup. Do not substitute unreviewed tooling to satisfy that gate.

## 2. Understand The Decisions

An application can use little CPU most of the day and still need capacity for startup, a traffic burst or recovery from a failure. The first question is whether the observations justify an investigation, not what percentage to remove.

| Concept | Meaning in an assessment |
| --- | --- |
| Usage | What the monitoring system measured during a stated period; samples can miss peaks |
| Request | CPU/memory used by the scheduler to reserve space for a Pod, not how much it consumes |
| Limit | A runtime bound, separate from the request; deciding a safe memory limit needs more than a working-set measurement |
| Allocatable capacity | Node capacity available to workloads after system reservations |
| Baseline | The default mode: identify a setting to investigate without choosing a replacement value |
| Guarded | A mode that permits supported numeric suggestions only when measurements, reliability checks and owner policies pass |
| Blocked/unknown | A requirement has failed or has not been established; missing usage is not zero usage |
| Savings | Not calculated here; a financial outcome needs separate billing evidence and FinOps review |

Application owners provide demand peaks and service-level objectives (SLOs): the reliability/performance measures a change must preserve. Platform teams review capacity, scaling tools and Pod placement. FinOps teams check whether an engineering result actually changes billed cost.

### Why The Commands Include A Date

The saved examples represent an assessment on October 29, 2026. `--as-of 2026-10-29T12:00:00Z` tells the advisor to check data age as of noon UTC on that date instead of today. It does not change your computer's clock or contact a cluster. Using the same inputs, settings, compatible package and date lets you repeat that assessment; this is called **offline replay**.

For a current customer assessment, omit `--as-of` so the advisor uses the current time. Never select an old date just to make outdated customer measurements pass the age checks. Every command block below labelled `text` works in both Windows PowerShell and Linux/macOS after setup.

## 3. Lab: Review Placement Without Metric History

**Scenario:** a platform engineer needs to understand scheduling restrictions before considering changes to node capacity. Inspect the scheduling rule, then analyze its fictional snapshot: a saved description of cluster/workload configuration. `--pack` selects this one check instead of all available checks.

```text
aks-fleet-advisor catalog show AKS-SCHED-001
aks-fleet-advisor analyze --snapshot examples/fixtures/scheduling-review-snapshot.json --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --format markdown
```

**Expected result:** the analysis exits `0`, reports one recommendation titled **Investigate current placement constraints**, and reports zero blocked findings. Compare with the [fictional expected report](../../examples/expected-scheduling-review.md). Exit `0` means the analysis completed, not that placement is optimal.

**Worked interpretation:** the report observes one node selector, a rule that restricts which node labels a Pod can use. Ask the platform/application owners why the restriction exists and whether it is still required. It could protect isolation, hardware or availability requirements; the report does not prove it is wasteful or safe to remove. It also does not prove that a node can be removed.

**Participant exercise:** choose another observed restriction in the report. Write what it tells you, one thing it cannot prove and which owner should review it. Do not propose a new setting. This current-configuration check does not need 30 days of usage history.

## 4. Lab: Investigate CPU Before Choosing A Target

This lab reads native resource quantities from saved files. Before continuing, install the `kubernetes` extra: in the setup command above replace `.` with `'.[kubernetes]'`, or add `[kubernetes]` inside the quotes at the end of the reviewed wheel filename. Use the same virtual environment and approved package feed. The quantity parser does not connect to a cluster.

**Scenario:** an application owner sees low CPU usage relative to requests. Create a local output parent from the repository root:

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force .local/aks-advisor | Out-Null
```

Linux/macOS:

```bash
mkdir -p .local/aks-advisor
```

The assessment directory must not already exist. If you have run this example before, choose a new directory and use that same path in the replay command. These outputs are synthetic; use approved protected storage for real evidence.

Select only the CPU rule and explicitly use baseline mode, which asks for investigation rather than a replacement CPU request. `assess --fragments` reads saved collector files and assembles the report without contacting their systems. `--artifacts` saves the report, inputs and settings together for later review.

```text
aks-fleet-advisor catalog show AKS-RQ-002
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/cpu-pack-config.yaml --pack AKS-RQ-002 --mode baseline --as-of 2026-10-29T12:00:00Z --format markdown --artifacts .local/aks-advisor/first-assessment
```

### Assessment Files

The command writes these files under `.local/aks-advisor/first-assessment`:

| File | Purpose |
| --- | --- |
| `report.md` | Human-readable findings, evidence and blocked reasons |
| `assessment.json` | Structured assessment, including normalized evidence and report |
| `snapshot.json` | Cluster/workload data assembled into the format the analysis accepts |
| `analysis-config.json` | Analysis settings and rule-definition checks needed to repeat the run |
| `fragments.json` | Original saved data from the collectors |
| `manifest.json` | File checksums, written last to record a completed export |

Keep the complete set. A directory without its final manifest is not a completed export. Checksums help detect changed files; they do not prove that the original measurements were trustworthy or that anyone approved a change.

**Expected result:** exit `3`, assessment status `partial`, and one CPU request investigation. The report lists an `unsupported-pool-evidence` gap: the supplied files do not support the node-pool analysis. That does not erase the independently supported CPU finding for the workload.

**Worked interpretation:** `cpu_p95_to_request_ratio = 0.1` compares the 95th percentile of measured CPU usage with the current CPU request. This is a question for the owner, not a recommendation to reduce the request by 90%. Startup peaks, failover requirements and reliability still need review. The high confidence in this investigation does not approve a change; source-version information can still be unknown and the overall assessment can still be partial.

**Participant exercise:** find the measurement period, rule version, ratio and missing-information section. Write a two-sentence handoff: what should the application owner investigate, and what should the platform/monitoring owner provide? Compare with the [baseline report](../../examples/expected-cpu-pack-baseline.md).

Repeat against the same **synthetic** evidence in guarded mode:

```text
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/cpu-pack-config.yaml --pack AKS-RQ-002 --mode guarded --as-of 2026-10-29T12:00:00Z --format markdown
```

Both CPU runs exit `3` because the assessment remains partial; the scoped CPU finding is still available. This is an expected evidence outcome, not a setup failure. Compare the synthetic [baseline report](../../examples/expected-cpu-pack-baseline.md) and [guarded report](../../examples/expected-cpu-pack-guarded.md).

The synthetic owner policy and complete supporting evidence permit a bounded 1000-to-500 mCPU proposal: one CPU core of requested capacity to half a core. Those values belong to this fictional example, not your workload, and do not mean a 50% bill reduction. Never copy fictional owner policies into a customer profile or enable guarded mode to work around missing information.

Replay the saved baseline findings without collecting new evidence:

```text
aks-fleet-advisor analyze --snapshot .local/aks-advisor/first-assessment/snapshot.json --config .local/aks-advisor/first-assessment/analysis-config.json --as-of 2026-10-29T12:00:00Z --format markdown
```

Repeating this analysis uses the saved baseline settings, not the guarded mode from the separate example. Keep the original compatible package, saved rule definitions and `--as-of` date. `analyze` reproduces the analysis findings in `assessment.json`'s `report` field; the saved `report.md` also includes the assessment's normalization gaps and source receipts, so its full Markdown is not identical to `analyze` output. Here normalization gaps are input data the advisor could not assemble for an analysis; source receipts record which requested reads completed. Neither means that every intended measurement was available or representative.

Checkpoint: name the owner, peak/reliability evidence, independent approval and rollback plan you would need before evaluating the same type of change yourself.

### Optional Lab: Review An Existing VPA Target

The generated [memory assessment](../../examples/fixtures/memory-assessment.json) contains a sanitized fictional VPA status, not hand-authored request candidates. Run only the CPU and memory-request checks; your existing Prometheus/Grafana and delivery workflows remain the owners of measurements and approved changes:

```text
aks-fleet-advisor assess --fragments examples/fixtures/memory-assessment.json --config examples/pool-assessment-config.yaml --pack AKS-RQ-002 --pack AKS-MEM-003 --as-of 2026-10-29T12:00:00Z --format json
```

Expect upstream targets of 500 mCPU and 313 MiB, an unchanged 1024 MiB memory limit, null savings and exit `3` for unsupported evidence elsewhere. Find the workload's `resource_candidates` in the normalized snapshot and compare their values with the VPA's saved `target` quantities. The advisor validates those targets; it does not calculate competing ones.

Exercise: identify the fictional independent freshness record under `workload_assessments[].vpa_recommendation`, then explain why the VPA collection clock cannot replace it. Omitting its `generated_at` would retain the targets but block proposals with `candidate_freshness_unknown`. Stop there if your actual source has no trustworthy freshness or historical identity evidence. Ask the platform/source owner about that gap, not for a new monitoring stack. The [saved-VPA runbook](../operations/runbook.md#saved-vpa-request-candidates) describes the exact export, binding and replay steps; a synthetic exercise does not certify live source compatibility or approve either change.

## 5. Lab: Recognize Unknown Readiness

**Scenario:** your monitoring owner has described a metrics service and the clusters to assess, but no one has verified access or the required retained data. Run this fictional offline check of those declarations:

```text
aks-fleet-advisor readiness --config examples/onboarding-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown
```

Expect exit `3` (`unknown`), not `0`. No service is contacted, sign-in attempted or permissions verified. The command checks supplied configuration/files; it cannot prove that your monitoring system stores the required measurements and historical identifiers. `readiness` exit `4` means an explicit blocker. For `assess`, exit `3` means partial/blocked evidence, not the readiness status. Inspect the command's report as well as its exit code; see the [complete exit-code reference](../onboarding-questionnaire.md#offline-readiness).

**Worked interpretation:** a valid address in a configuration file does not prove that your approved reader can reach the service or that the right history exists. Ask the monitoring and platform owners to verify those facts before a separately approved collection. A source is an input system/file, not Python code.

**Participant exercise:** name one unknown, who can resolve it and what information you would request. For example, a monitoring owner might establish whether retained measurements identify the exact workload and Pod instances that existed during the assessment period. Current names cannot reconstruct missing historical identifiers.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Command not found | Use the virtual environment's executable shown in setup; do not install into an unrelated Python environment. |
| Install fails | Check Python 3.15, the PyYAML build setting above and your approved package feed or proxy. Do not disable TLS verification. |
| CPU assessment exits `3` | Expected for these partial synthetic fragments. Open the report and distinguish the scoped finding from the remaining gaps. |
| Readiness exits `3` | Expected `unknown`: declarations do not establish live access or historical identity. |
| Output directory already exists | Choose a fresh assessment directory. The advisor does not overwrite prior evidence. |
| Saved pack locks do not match | Replay with a compatible reviewed package or create a new assessment; never edit the saved hashes. |

## Finish And Choose Your Next Step

You have completed the labs when you can explain a finding and a gap in your own words, point to their supporting data/dates and name an owner for the next action. Neither an investigation nor a suggested setting authorizes a change. Those skills prepare you to scope an assessment, not to assume your environment is ready.

Next, [interpret your first report](../tutorials/interpret-your-first-report.md) and record a finding, a gap and their owners. Use the [assessment guide](assessment-guide.md) and [customer pilot plan](../how-to/plan-a-bounded-pilot.md) only when ready to review your own data and access. Optional advanced exercises are in the [pack guide](../recommendation-packs.md), [cost reconciliation](../cost-reconciliation.md) and [local artifact history](../operations/history.md). Use the [operations runbook](../operations/runbook.md) for approved saved evidence and bounded read-only collection; live access is not a requirement for these labs.

No cloud resources were created by this path. Remove the virtual environment and local synthetic outputs only when you no longer need them, using your normal workstation process. Report problems through [Support](../../SUPPORT.md) using synthetic reproductions, never customer evidence or credentials.
