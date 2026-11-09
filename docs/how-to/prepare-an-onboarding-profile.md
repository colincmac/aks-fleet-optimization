# Prepare An Assessment Profile

[Documentation home](../README.md) | [Next: validate data sources](validate-source-compatibility.md)

## Goal And Prerequisites

An onboarding profile is a configuration file describing which clusters and
data sources an assessment may use and which checks to run. It is not approval
to access those systems. A data source means an input system/file, not code.

This guide is for the platform engineer coordinating application, monitoring
and security owners. Complete [the first labs](../accelerator-docs/getting-started.md)
and [report interpretation](../tutorials/interpret-your-first-report.md) first.
Allow about 20 minutes for the fictional exercise; customer discovery takes
longer and needs its owners. No cloud access is needed for the commands here.

## 1. Collect Decisions Before Writing Fields

| Decision | Who provides it | Sufficient answer |
|---|---|---|
| Question and non-regression requirement | Application/sponsor | One testable question and the reliability/performance measures that must hold |
| Cluster scope | Platform owner | Exact approved tenant, subscriptions and cluster resource IDs; names alone are not join keys |
| Monitoring inputs | Monitoring owner | Known metric meanings/units, actual retained period and historical identifiers required by the chosen checks |
| Access and storage | Security/platform | Approved read-only principal/runner, network path, report location, audience and retention |
| Check selection | Platform/application | Small explicit pack list and supported input shape; start in baseline mode |

Record unknowns instead of guessing. A source URL or declared retention is not
proof of connectivity or retained data. Keep completed customer records in
approved storage using the [participant workbook](../facilitator/participant-workbook.md).

## 2. Practice With A Fictional Profile

From the repository root with the advisor installed, create the ignored output
parent. Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force .local | Out-Null
```

Linux/macOS:

```bash
mkdir -p .local
```

These commands only create a local folder and normally exit successfully.
Generate a new fictional baseline profile. This command works in either shell:

```text
aks-fleet-advisor configure --config examples/cpu-pack-config.yaml --no-interactive --mode baseline --pack AKS-RQ-002 --output .local/onboarding-example.yaml
```

Expect exit `0` and a new YAML configuration file. If it already exists, choose
a new output filename; the command refuses overwrites. It reads a fictional
example, makes no endpoint requests and does not add owner approval policies.
The output is a format exercise, not a customer-ready profile.

## 3. Understand The Main Fields

- `scope`: approved tenant/subscription/cluster identities and exclusions.
- `metric_sources`: named monitoring inputs, declared format and endpoint; no credential values.
- `ownership`: declared owners, not access grants or workload safety approval.
- `analysis`: selected packs/mode and supported settings, not a bypass for quality/reliability requirements.
- `report_directory`: a declared location; loading the profile does not create it or test write access.

Use the [profile field reference](../onboarding-questionnaire.md#versioned-onboarding-profile)
for exact meanings and validation. An analysis-only file saved for `analyze`
is not a collection/onboarding profile.

## 4. Prepare The Real Record Separately

Create a separate customer profile only after its owners supply reviewed facts.
Never reuse fictional IDs, anonymous access settings or safety policies. Do not
put passwords, tokens, kubeconfig bodies or raw customer exports in the profile
or repository. Exact source shapes, cloud/authentication limits and transport
requirements must be checked, not inferred from a valid file.

**Evidence required:** reviewed scope, data-owner answers, effective read-only
permissions and source validation for each chosen question. Offline `readiness`
can identify invalid inputs and unknowns, but never substitutes for that review.

## Completion And Cleanup

Complete when each field has a known owner and evidence reference or an explicit
gap/next action. A valid YAML file alone is not success. Remove only the local
fictional output when no longer needed, using normal workstation procedures;
no cloud cleanup is required.

Next, [validate the data sources](validate-source-compatibility.md) and
[choose the smallest useful checks](choose-recommendation-packs.md).
Authoritative contracts remain in the [onboarding reference](../onboarding-questionnaire.md)
and [security guidance](../security-and-privacy.md).