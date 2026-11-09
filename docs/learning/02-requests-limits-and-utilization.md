# 2. Understand Requests, Limits And Usage

[Previous: outcomes](01-why-fleet-efficiency.md) | [Next: scaling](03-horizontal-vertical-and-node-scaling.md)

## Why This Matters

"The application uses less than it requests" compares two different quantities.
Understanding them prevents a monitoring observation from becoming an
unsupported setting or financial claim.

## Learning Objectives

- Distinguish usage, requests, limits and node capacity available to workloads.
- Read CPU and memory units correctly.
- Explain why a Pod's scheduling requirement can exceed its application containers' requests.

## Before You Begin

Complete [the outcome module](01-why-fleet-efficiency.md). No commands, cloud
access or customer data are required. A container runs inside a Pod; a Pod can
contain application containers and initialization or supporting containers.

## Concept

**Concept:** usage is measured consumption over time. A request is the amount
used by the scheduler to account for a Pod's resource needs. A limit is a
separate runtime bound. A CPU request is not a CPU cap; changing a memory request
does not automatically change the memory limit.

1000 millicores (mCPU) means one CPU core. A mebibyte (MiB) is 1,048,576 bytes;
it is not a decimal megabyte. Compare values only when their units match.
Allocatable capacity is node capacity available after system reservations.

## In AKS

Use the resources admitted on actual Pods, not only values in a deployment
template: admission settings may change them. For scheduling, initialization,
restartable sidecars and runtime overhead can affect the effective Pod request.
A dashboard showing one application container is not the whole Pod.

## How The Advisor Uses This

Different checks investigate missing requests, compare qualified usage with
requests, or account for current Pod memory. Numeric request and limit
suggestions have separate requirements. Memory working set is a useful
measurement but is not the full memory evidence required for a limit suggestion.

## What It Cannot Conclude

**Solution boundary:** a percentile or ratio alone does not choose a safe value.
The advisor does not infer omitted settings as zero, fill missing history from
today's configuration or turn current Pod accounting into removable capacity.

## Synthetic Example

**Example: fictional Pod.** Its application containers request 512 MiB and
128 MiB. One regular initialization container requests 900 MiB, runs before the
applications, and does not keep running. Explicit runtime overhead is 32 MiB.
There are no restartable initialization sidecars or Pod-level resource budgets.

The application sum is 640 MiB. For this simple scenario, the scheduling
requirement is the larger of 640 and 900, plus 32: **932 MiB**, not 640 MiB.
This is request accounting, not measured usage or a memory-limit target.

## Participant Exercise

**Participant exercise:** explain why the application sum is not sufficient.
Then consider a container requesting 1000 mCPU whose measured CPU usage is
usually 100 mCPU. List two other facts you need before evaluating a reduction.

## Expected Output

"The initialization container and overhead determine this Pod's larger request.
For CPU, we need representative startup/business peaks and owner reliability
requirements, plus the applicable scaling and safety evidence. A ratio alone
does not justify a 90% reduction."

## Discuss

- Could an admission policy make template and running-Pod resources differ?
- Why does a lower memory request not prove a lower memory limit is safe?
- Which team can establish initialization and sidecar behavior?

## Common Misconceptions

- A request is not consumption or a hard CPU limit.
- Memory working set is not interchangeable with full-memory usage.
- Missing, explicitly absent and observed zero are different states.

## Key Takeaways

Compare like units and distinguish settings from measurements. Account for the
whole Pod. Request, limit and replica changes need separate reviews and tests.

## Deeper Reference

- [Admitted resource observations](../data-contracts.md#current-workload-inventory)
- [Effective Pod accounting](../data-contracts.md#effective-pod-and-termination-context)
- [Separate memory-limit requirements](../data-contracts.md#separate-memory-limit-proposal)