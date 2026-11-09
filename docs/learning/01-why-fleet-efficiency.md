# 1. Start With An Application Outcome

[Documentation home](../README.md) | [Next: resources](02-requests-limits-and-utilization.md)

## Why This Matters

An application that looks idle may be keeping capacity ready for the next burst
or a failure. Reducing that capacity is not automatically an improvement.
Start with what the application needs to deliver, then investigate its settings.

## Learning Objectives

- Turn a utilization observation into a testable question.
- Separate application reliability, reserved capacity and financial outcomes.
- Identify who must help decide whether a change is worth testing.

## Before You Begin

No tools or cloud access are needed. Know which application or service you own.
Azure Kubernetes Service (AKS) runs applications in Pods on worker machines
called nodes. Here a fleet means the clusters included in your assessment;
Azure Kubernetes Fleet Manager enrollment is not required.

## Concept

**Concept:** efficiency means using resources appropriately for the required
outcome, not driving every workload toward the same utilization percentage.
An observation is something measured or read from configuration. A hypothesis
is an explanation or proposed improvement that still needs testing.

A service-level objective (SLO) states a reliability or performance requirement,
such as an agreed response-time or availability target. The application owner
defines it; the advisor does not infer it from CPU usage.

## In AKS

CPU and memory settings affect how Pods share and reserve node capacity.
Replica counts affect available application copies. Node settings affect
infrastructure supply. These decisions interact, but different teams and tools
may own them. Low average CPU does not identify which decision should change.

## How The Advisor Uses This

The advisor reads approved configuration and measurements and applies fixed
rules. Its report identifies investigations, missing information and, for
narrowly supported cases, numeric suggestions. It does not call an AI model.
Begin with a small question, not a goal to obtain the most recommendations.

## What It Cannot Conclude

**Solution boundary:** the advisor does not approve or apply changes, prove that
an SLO is met, determine removable nodes or calculate savings. A report without
findings is not proof of health. Missing information remains unknown.

## Synthetic Example

**Example: fictional service.** A service requests one CPU core per copy and
usually consumes much less. It has a brief startup peak and must recover
quickly after a node failure. A team suggests halving the request because the
average is low.

That observation supports a question: can a different request preserve startup,
throughput and recovery behavior? It does not establish a safe replacement
value or a smaller bill. A CPU request is not a hard consumption limit.

## Participant Exercise

**Participant exercise:** write one desired application outcome, one measurement
that prompted the question, one requirement that must not regress and one
unknown that could change the decision. Do not select a replacement setting.

## Expected Output

A suitable fictional answer: "Investigate whether the CPU request can change
without worsening startup or response time at representative demand. We know
usage is usually low, but need startup/failure tests and the owner-approved SLO.
The application owner and platform engineer will review those inputs."

## Discuss

- What would make retaining the current request a good outcome?
- Who can explain the next business peak or recovery requirement?
- Which observation could disprove the improvement hypothesis?

## Common Misconceptions

- Low usage does not by itself prove waste.
- A request reduction is not the same as a node reduction or cash savings.
- Collecting better information or deciding not to change is a valid result.

## Key Takeaways

Name the outcome and non-regression requirement before discussing settings.
Keep observations, hypotheses and decisions separate. Start small enough that
the accountable owners can review the result.

## Deeper Reference

- [Why there is no universal utilization target](../metrics-and-scoring.md#why-there-is-no-universal-utilization-target)
- [Assessment scope and responsibilities](../accelerator-docs/assessment-guide.md#1-agree-scope-and-responsibilities)
- [Technical execution boundaries](../architecture.md#execution-boundary)