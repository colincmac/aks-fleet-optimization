# Compare Two Fictional Clusters

Run this lab to find an issue that recurs on two clusters, then see when a comparison is not valid. All inputs are fictional; the assessment does not contact Azure, Kubernetes, Prometheus, or a billing endpoint. You do not need an AI model or any optional advisor dependencies.

## Set Up

Run the commands from the **repository root** or the **root of the extracted trial ZIP** (the folder containing `examples/`), not from `examples/` itself. You need Python 3.15 and the base advisor. If the advisor is already installed, confirm that `aks-fleet-advisor --help` works in your terminal and skip the install.

If you received a reviewed wheel with the ZIP, put the wheel in the extracted root. The examples below use `aks_fleet_efficiency_advisor-0.1.0-py3-none-any.whl`; use the actual filename supplied to you. If installing from a reviewed checkout instead, replace the quoted wheel path with `.`. Dependency installation may need network access to your approved package feed; the lab itself runs offline afterward.

**Windows PowerShell**

```powershell
py -3.15 -m venv .venv
$env:PYYAML_FORCE_LIBYAML = "0"
.\.venv\Scripts\python.exe -m pip install './aks_fleet_efficiency_advisor-0.1.0-py3-none-any.whl'
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS with Python 3.15 installed**

```bash
python3.15 -m venv .venv
PYYAML_FORCE_LIBYAML=0 .venv/bin/python -m pip install './aks_fleet_efficiency_advisor-0.1.0-py3-none-any.whl'
source .venv/bin/activate
```

If activation is restricted, use `./.venv/Scripts/aks-fleet-advisor.exe` on Windows or `./.venv/bin/aks-fleet-advisor` on Linux/macOS in place of `aks-fleet-advisor`. Do not change execution policy to run the lab.

The build setting selects PyYAML's supported pure-Python implementation when no Python 3.15 wheel is available, avoiding a C++ compiler requirement. It does not change the advisor's safe YAML loaders.

Create the `.local` parent directory if it does not exist (`New-Item -ItemType Directory -Force .local` in PowerShell or `mkdir -p .local` in Bash). Choose fresh output directory names on repeat runs and use them consistently. When running in a shell configured to stop on nonzero exits, run the `assess` commands individually: exit `3` is expected here.

## Assess and Compare

1. Assess each cluster from its supplied inputs. Both commands select the missing CPU request check and use the same fixed example date. Expect exit `3` for each: incomplete evidence does not prevent the advisor from saving the bundle.

   ```text
   aks-fleet-advisor assess --fragments examples/fixtures/workload-assessment.json --config examples/pool-assessment-config.yaml --mode baseline --pack AKS-RQ-001 --as-of 2026-10-29T12:00:00Z --artifacts .local/fleet-lab-a
   aks-fleet-advisor assess --fragments examples/fixtures/fleet-peer-assessment.json --config examples/fleet-peer-config.yaml --mode baseline --pack AKS-RQ-001 --as-of 2026-10-29T12:00:00Z --artifacts .local/fleet-lab-b
   ```

2. Compare the saved bundles without editing their files. Expect exit `0`, **Comparable assessments: yes**, and two `AKS-RQ-001` findings, one per cluster. The workloads share display names, but the clusters have different resource IDs and Kubernetes fingerprints. Ask each workload owner to verify the admitted CPU request and how the workload scales. The finding does not establish a safe replacement request or a saving.

   ```text
   aks-fleet-advisor fleet summarize --assessment .local/fleet-lab-a/assessment.json --peer-group nonproduction --assessment .local/fleet-lab-b/assessment.json --peer-group nonproduction --as-of 2026-10-29T12:00:00Z --format markdown
   ```

3. Assess the second cluster again with a placement check instead. Expect exit `3` from `assess` and exit `0` from `fleet summarize`, but **Comparable assessments: no**. Both reports are valid; they answer different questions. Do not treat the absence of the CPU finding in the second report as a fix or use the counts to rank the clusters.

   ```text
   aks-fleet-advisor assess --fragments examples/fixtures/fleet-peer-assessment.json --config examples/fleet-peer-config.yaml --mode baseline --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --artifacts .local/fleet-lab-b-placement
   aks-fleet-advisor fleet summarize --assessment .local/fleet-lab-a/assessment.json --peer-group nonproduction --assessment .local/fleet-lab-b-placement/assessment.json --peer-group nonproduction --as-of 2026-10-29T12:00:00Z --format markdown
   ```

When you finish, explain why the first comparison is useful and what makes the second comparison invalid for ranking. Record one next action for a workload owner. No cloud cleanup is needed; the three output directories contain only fictional reports and inputs.