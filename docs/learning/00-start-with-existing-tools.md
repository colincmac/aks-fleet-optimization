# 0. Start With Existing Microsoft And FinOps Tools

[Documentation home](../README.md) | [Next: application outcomes](01-why-fleet-efficiency.md)

## Why This Matters

The accelerator extends the customer’s existing AKS and FinOps practices. It is not a replacement cost platform, monitoring system, autoscaler, or recommendation service.

## Learning Objectives

- Identify which questions Microsoft Cost Management, AKS Cost Analysis, Azure Advisor, the Cost Optimization workbook, Azure Optimization Engine, VPA, OpenCost or Kubecost already answer.
- State the unresolved enterprise question before running accelerator analysis.
- Separate upstream observations and candidates from accelerator validation.

## Existing Foundation

Review the tools already approved and operating in the environment before requesting new data:

| Existing tool | What it already answers | Additional question for the accelerator | Owner and existing handoff |
| --- | --- | --- | --- |
| [Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/quick-acm-cost-analysis) or FinOps hubs | Billing scope, period, currency, cost basis, commitments and resource costs | Does the approved allocation preserve historical identity and the ledger's financial semantics? | FinOps owner retains the original amounts and attaches the optional reconciliation report to existing financial review. |
| [AKS Cost Analysis](https://learn.microsoft.com/en-us/azure/aks/cost-analysis) | Eligible cluster/namespace/asset attribution and idle/system/service charges | Which separate workload evidence could explain a reviewed cost observation without treating allocation as savings? | FinOps/platform owners keep the portal view and link a bounded workload investigation from their current backlog. |
| [Azure Advisor](https://learn.microsoft.com/en-us/azure/aks/cost-advisors) | Existing AKS cost recommendations and enablement gaps | What exact workload/controller/reliability constraint remains unresolved? | Platform owner retains the Advisor recommendation ID and avoids a duplicate enablement ticket. |
| [Cost Optimization workbook](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/workbooks/optimization) | Rate and usage optimization insights, Advisor recommendations and resource-level investigations, including AKS | Does one workload's current configuration or historical evidence support further review of that resource-level observation? | Workbook/FinOps owner links the saved report to the existing triage/change record, not another dashboard. |
| [Azure Optimization Engine (AOE)](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/optimization-engine/overview) | Customizable Advisor and Azure resource optimization insights, recommendation history and suppression | Does an existing AKS/VMSS investigation need workload identity, controller or reliability evidence before an owner decides? | Existing AOE operator retains its recommendation/history record and adds a protected advisor-report reference to the current review workflow. |
| [VPA recommendation mode](https://learn.microsoft.com/en-us/azure/aks/vertical-pod-autoscaler) | Per-container CPU/memory targets from the existing recommender | Is the saved target identity-bound, fresh and compatible with independently reviewed workload history, peaks and policy? | Application/platform owners use the saved-VPA handoff, then approve or defer a one-dimension experiment through current delivery tooling. |
| [HPA and KEDA](https://learn.microsoft.com/azure/aks/concepts-scale) | HPA changes replicas; KEDA can create and manage an HPA for event-driven scale. Microsoft advises against a competing HPA on the same KEDA target or active HPA and VPA acting on the same resource metric. | Is this HPA the one KEDA owns? Would changing a CPU request alter the utilization signal used to scale replicas? | Review target identity, controller ownership, metric and VPA mode before testing one change. A KEDA-owned HPA is not itself evidence of a conflict. |
| [Cluster Autoscaler and AKS node auto-provisioning](https://learn.microsoft.com/azure/aks/concepts-scale) | Cluster Autoscaler changes node counts in configured pools; [NAP](https://learn.microsoft.com/azure/aks/node-auto-provisioning) manages Karpenter provisioning for pending workloads. | Could DaemonSet reservations, placement constraints or disruption budgets explain why apparently idle capacity should be retained? | Platform owners review the evidence; the accelerator neither selects a VM nor certifies that a node can be drained. |
| [OpenCost](https://www.opencost.io/docs/integrations/api/) or existing Kubecost | Allocation, idle/shared policy and the installation's pricing basis | Does an optional reviewed saved projection have the claimed cost basis, period and identity limits? | Existing cost-tool owner preserves its allocation and dashboard; FinOps reviews any separate billing-ledger provenance. |
| Enterprise Prometheus/Grafana | Existing CPU/request measurements and workload dashboards | Can selected series support an unresolved measurement, a historical investigation or candidate validation? | Monitoring owner supplies only the selected query contract; application owners retain current dashboards and intentional reserve. |
| [Azure Kubernetes Fleet Manager](https://learn.microsoft.com/en-us/azure/kubernetes-fleet/overview) | Existing multi-cluster orchestration capabilities | What placement/resilience constraints should the fleet owner consider? | Fleet owner receives design context; this advisor neither places nor migrates workloads. |

These are alternatives already available to your owners, not an installation checklist. In particular, AOE has its own deployed resources and operating responsibilities; using this local accelerator does not require deploying AOE, FinOps hubs, the workbook or a monitoring stack. No native outbound AOE/workbook ingestion or hosted connector is implemented. A report reference in an existing ticket/review is a manual evidence handoff, not a compatible product import schema or approval.

## What To Record

Record the installed tool and version, protected evidence reference, period, cost basis, allocation policy, recommendation identifier, what owners already reviewed, and the advanced question that remains unresolved. “Use the accelerator” is not itself a business outcome.

Record only fields relevant to the question: a metadata investigation needs no billing period or financial export, and ordinary CPU measurements need no new recommender. Choose one of the [three entry points](../how-to/choose-recommendation-packs.md#three-ways-to-start), name the next owner, and allow a deliberate no-change or deferred dimension. The Cost Optimization workbook's optional quick fixes are outside this advisor and require the customer's separate change approval; a local report does not authorize them.

## Solution Boundary

The advisor does not enable these products, query billing, install OpenCost, call an undocumented managed AKS Cost Analysis endpoint, apply VPA recommendations, convert currencies, forecast savings, or replace customer support and governance processes.

Managed AKS/Cost Management products retain their documented service/support boundaries. FinOps Toolkit solutions, including its workbook/AOE distribution, are provided as-is; issues in underlying managed products go to that product's support channel. See [FinOps Toolkit support](https://learn.microsoft.com/en-us/cloud-computing/finops/toolkit/help/support). This accelerator's synthetic characterization does not extend any product's support or certify your installation.

## Participant Exercise

Choose one existing finding and write two sentences: what the existing tool established, and what additional evidence or constraint the accelerator should evaluate. If there is no additional question, do not introduce a parallel analysis path.

## Expected Output

“AKS Cost Analysis identified namespace-attributed cost and idle cost for the reviewed period. The accelerator will not recalculate those amounts; it will investigate whether one VPA request candidate is identity-bound and compatible with the workload’s HPA, peaks, reliability policy and current admitted configuration.”

## Key Takeaways

Start with supported products and existing enterprise tools. Use the accelerator only for additional evidence and validation, preserve upstream provenance, and keep implementation and financial conclusions with their accountable owners.

## Deeper Reference

- [Financial source profiles](../financial-source-profiles.md)
- [Offline cost reconciliation](../cost-reconciliation.md)
- [Advanced controller and scheduling analysis](../orchestration-and-scheduling.md)
