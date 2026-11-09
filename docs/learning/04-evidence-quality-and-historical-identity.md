# 4. Decide What The Data Can Tell You

[Previous: scaling](03-horizontal-vertical-and-node-scaling.md) | [Next: findings](05-recommendations-risk-and-confidence.md)

## Why This Matters

A working dashboard or a reachable metrics service does not prove that the
advisor can answer every question. The measurements must identify the right
resources, cover the right period and have the meaning the chosen check needs.

## Learning Objectives

- Distinguish connection access from usable assessment data.
- Explain why names cannot reconstruct missing historical identity.
- Separate missing values, observed zero and complete observation.

## Before You Begin

Complete [the outcome module](01-why-fleet-efficiency.md). No tools or cloud
access are required. **Evidence** means configuration, measurements, dates and
supporting review records. A **data source** is the system/file supplying them:
inventory, Kubernetes configuration, monitoring or a cost export, not Python code.

## Concept

**Concept:** ask four separate questions: can the approved reader connect; are
the expected metrics/fields and units present; do they identify the actual
historical resource; and is the period/quality sufficient for this check?
The reference pages call checking these inputs **source compatibility**.

A unique identifier (UID) distinguishes an object instance from a later object
with the same name. An observation window is the period being assessed.
Coverage describes returned expected evaluation points, not proof that raw
scrapes were complete or that no brief peaks occurred between points.

## In AKS

Pods and controllers can be deleted and recreated. Current inventory says what
exists now; it cannot establish every member that existed during the last month.
Some historical checks need existing UID-enriched series or approved complete-
roster recordings, including deleted members. Installing a recording today
cannot create missing past identity or measurements.

## How The Advisor Uses This

Each check has its own identity, time, unit, completeness and reliability
requirements. Current-configuration investigations can remain useful when
historical metrics are unavailable. Offline `readiness` checks supplied
configuration/files; it does not contact a service or certify its data.

## What It Cannot Conclude

**Solution boundary:** current names do not relabel old measurements. An absent
series is not zero, unknown controller discovery is not observed absence and
30 retained days are not automatically representative. A hash checks integrity,
not truth, completeness or owner approval.

## Synthetic Example

**Example: fictional workload history.** A Deployment named `example-api` with
UID A is deleted halfway through a month. Another Deployment with that name
has UID B. A monitoring export retains only the name and CPU samples.

The name-only samples cannot establish which exact workload instance produced
each observation. Today's UID B cannot be attached to all of the old data.
That gap can block a numeric suggestion while current inventory still supports
a configuration investigation.

## Participant Exercise

**Participant exercise:** classify these statements as established, unknown or
insufficient: "HTTPS responds"; "the required UID history is absent"; "an OOM
counter is missing"; "the current node selector is explicitly observed".
Name an owner and next action for one gap. OOM means out of memory.

## Expected Output

"Reachability establishes only transport behavior. Missing UID history cannot
support that historical claim. Missing OOM data are unknown, not zero incidents.
Current selector evidence may support an eligible current review, not historical
placement or safe consolidation. The monitoring owner must review retained
identity; we must not manufacture it from today's inventory."

## Discuss

- Could complete samples still miss a rare business peak?
- Who can establish historical membership including deleted objects?
- Which current-inventory question remains useful if history is unsupported?

## Common Misconceptions

- A configured endpoint is not verified access or source acceptance.
- Complete requests are not the same as complete historical measurements.
- Lowering a quality threshold does not repair missing identities.

## Key Takeaways

Record what is observed and what remains unknown, per question. Preserve useful
supported checks without pretending missing data are complete. Ask the source
owner for proof appropriate to the exact period and resource.

## Deeper Reference

- [Historical metric contract](../data-contracts.md#historical-metrics)
- [Data-source validation worksheet](../source-compatibility.md#pilot-evidence-worksheet)
- [Declared source formats and limitations](../source-profiles.md)