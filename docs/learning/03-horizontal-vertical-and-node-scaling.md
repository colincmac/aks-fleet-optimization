# 3. Identify Which Scaling Decision You Own

[Previous: resources](02-requests-limits-and-utilization.md) | [Next: data quality](04-evidence-quality-and-historical-identity.md)

## Why This Matters

Changing a Pod request, changing application copies and adding nodes solve
different problems. A change at one layer can change the signals another layer
uses. Choose the decision before choosing a tool.

## Learning Objectives

- Identify resource, replica, placement and node-supply decisions.
- Explain how a CPU request affects utilization-based scaling.
- Recognize why spare fleet totals do not prove a Pod fits anywhere.

## Before You Begin

Complete [the resource module](02-requests-limits-and-utilization.md). A replica
is a copy of an application workload. A controller observes configuration and
state and takes action toward its desired behavior. No tools or cloud access
are needed for this lesson.

## Concept

**Concept:** horizontal scaling changes the number of copies; vertical sizing
changes resources per copy. Scheduling selects a feasible node for a Pod.
Node provisioning supplies eligible infrastructure. These are related decisions,
not interchangeable ways to increase a utilization percentage.

## In AKS

| Tool or mechanism | Main responsibility |
|---|---|
| Horizontal Pod Autoscaler (HPA) | Adjust workload replicas using configured metrics |
| Vertical Pod Autoscaler (VPA) | Recommend or, in supported mutating modes, change Pod resource settings |
| Kubernetes Event-driven Autoscaling (KEDA) | Event-based scaling/activation; a ScaledObject and its generated HPA form one ownership chain |
| Scheduler | Place Pods according to resources and placement requirements |
| Cluster autoscaler | Adjust eligible configured node pools |
| Node auto-provisioning (NAP) | Provision eligible nodes under approved policies |

VPA mode matters: `Off` provides recommendations; `Initial` can change newly
created Pods. Not every VPA mode is observation-only. Tool/version support and
interactions need independent review before implementation.

## How The Advisor Uses This

The advisor reviews selected current configurations and supported history. It
can identify a utilization-denominator overlap between HPA and mutating VPA,
but it does not operate these controllers. A valid platform design is not
automatically an eligible numeric suggestion in the advisor.

## What It Cannot Conclude

**Solution boundary:** it does not simulate packing, choose a migration to NAP,
move workloads across clusters or determine a safe removable-node count.
An observed configuration interaction is not proof of oscillation or an SLO
failure. Active or unknown controllers can block numeric reductions.

## Synthetic Example

**Example: fictional CPU-scaled service.** Usage is 300 mCPU. With a 1000 mCPU
request, utilization is 30%. With a 500 mCPU request, it is 60%, even though
traffic did not change. HPA's response also depends on its other settings and
observations; this calculation is not a replica forecast.

**Example: fictional placement problem.** Node A has 2 free CPU cores and
16 GiB free memory; Node B has 4 cores and 2 GiB. A Pod needs 3 cores and 4 GiB.
The combined spare resources look sufficient, but neither node can fit it.

## Participant Exercise

**Participant exercise:** explain which decision the HPA example affects and
why the Pod cannot fit in the placement example. Name the application and
platform owners needed before changing either setting.

## Expected Output

"A request change changes the denominator of utilization-based HPA feedback;
it needs separate scaling/throughput review. The pending Pod needs both resources
on one eligible node, not totals across nodes. We need application requirements
and actual placement/capacity evidence, not an instruction to remove a node."

## Discuss

- When might a low replica minimum violate startup or failure-recovery requirements?
- Why are KEDA and its generated HPA not necessarily two competing controllers?
- Could a placement restriction be an intentional isolation requirement?

## Common Misconceptions

- Node provisioning does not choose safe application requests.
- Lower requests do not automatically move existing Pods.
- A low sampled replica count is not permission to lower the minimum.

## Key Takeaways

Identify each tool's job and ownership. Evaluate related effects together but
change one dimension at a time through the customer's approval process.

## Deeper Reference

- [Advanced control-layer and tool guidance](../orchestration-and-scheduling.md#start-with-the-control-layer)
- [Current HPA/VPA interaction semantics](../metrics-and-scoring.md#current-autoscaler-interaction)
- [Narrow replica-floor proposal requirements](../data-contracts.md#opt-in-replica-floor-proposal)