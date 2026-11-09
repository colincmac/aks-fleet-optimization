# Choose Checks For Your Assessment Question

[Documentation home](../README.md) | [Next: customer assessment](../accelerator-docs/assessment-guide.md)

## Goal And Prerequisites

A recommendation pack describes a rule's required inputs and review guidance.
Select a small set that answers your question instead of treating every blocked
check as a request for more access. This guide is for application/platform
owners after [the first labs](../accelerator-docs/getting-started.md).
Allow about 15 minutes for offline inspection; no cloud access is required.

## 1. Start With The Question

| Question | Starting check | Important boundary |
|---|---|---|
| What restricts current Pod placement? | `AKS-SCHED-001` | Configuration investigation, not packing simulation or removable nodes |
| What current capacity classes need review? | `AKS-NP-002` | Current pool/provisioning context, not a NAP migration decision |
| Are admitted CPU requests missing? | `AKS-RQ-001` | Current request investigation, not a replacement value |
| Is qualified CPU usage low relative to requests? | `AKS-RQ-002`, baseline first | Owner investigation; guarded values need independent additional requirements |
| Do resource-utilization HPA and mutating VPA policies overlap? | `AKS-AS-002` | Current interaction, not proof of oscillation or an SLO failure |
| Do memory or replica settings warrant review? | Inspect the relevant family in the pack reference | CPU-ready data do not establish memory/replica readiness |

HPA means Horizontal Pod Autoscaler; VPA means Vertical Pod Autoscaler; NAP
means node auto-provisioning. Their roles are introduced in the
[scaling lesson](../learning/03-horizontal-vertical-and-node-scaling.md).

## 2. Inspect Requirements Without Accessing A Cluster

From the repository root after installing the advisor, these commands work in
Windows PowerShell and Linux/macOS and normally exit `0`:

```text
aks-fleet-advisor catalog list
aks-fleet-advisor catalog show AKS-SCHED-001
aks-fleet-advisor catalog show AKS-RQ-002
```

`list` shows the installed checks; `show` prints the selected manifest and
provenance. Neither command contacts a service, creates output files or obtains
credentials. Unknown pack IDs are errors, not permission to substitute a check.

Read evidence dependencies, supported modes, limitations, review actions and
validation/rollback guidance. The [generated catalog](../operator-catalog.md)
is exact reference, not a first-run lesson or source certification.

## 3. Record The Selection

For each question, record its pack ID, installed version, mode, needed input
shape, unsupported cases and missing information owner. Keep exact versions and
configuration with saved reports rather than copying counts/versions into a
customer procedure that may drift.

Start in `baseline`: investigations without replacement values. `guarded`
permits eligible numeric suggestions but is not approval, does not enable
default-off owner policies and cannot bypass identity/reliability requirements.
Changing a review ratio is not choosing a safe resource target.

## Completion And Next Step

Finish when the owners can explain why each check was selected and what its
output cannot conclude. An inventory-only scope is a useful outcome when
history is unavailable. No files/cloud resources were created; no cleanup is
needed for these inspection commands.

Continue with [data-source review](validate-source-compatibility.md) and
[customer assessment](../accelerator-docs/assessment-guide.md). Exact pack
contracts and supported parameters remain in [recommendation packs](../recommendation-packs.md)
and [rule gates](../metrics-and-scoring.md#rule-gates).