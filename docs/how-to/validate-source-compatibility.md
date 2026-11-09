# Check Whether Your Data Can Answer The Question

[Documentation home](../README.md) | [Next: bounded pilot](plan-a-bounded-pilot.md)

## Goal And Prerequisites

This is the human review before a customer assessment, not an automatic test
or permission to query a service. Platform, monitoring and security owners
should review one selected question together. Read the
[evidence lesson](../learning/04-evidence-quality-and-historical-identity.md) first.
No command, credential or customer endpoint is needed to read this guide.

The exact formats and supported cases remain in the
[source compatibility reference](../source-compatibility.md). Here **source**
means the inventory, configuration, monitoring system or saved file supplying
assessment data, not Python code.

## 1. Select A Question And Supported Input Shape

Start with [check selection](choose-recommendation-packs.md). Current placement
or configuration reviews can use approved fresh inventory without 30 days of
metrics. Historical resource suggestions need much more. Do not request
everything merely because the cluster has a monitoring dashboard.

## 2. Review Four Different Questions

| Question | Required owner answer | What it does not prove |
|---|---|---|
| Can the approved runner read the input? | Reviewed endpoint/exporter identity, read-only effective rights and supported network/TLS path | Correct metric meaning, complete history or change safety |
| Are the required fields and units present? | Definitions for each selected metric/configuration field; reviewed source/producer versions | That similarly named recordings have the right meaning |
| Does history identify the actual objects? | Exact historical workload/Pod/node/controller identifiers and required complete membership | That today's objects or matching display names represent deleted members |
| Is the period and quality sufficient? | Actual retained range, resolution, gaps, fresh tail and representative demand/reliability information | That retention duration alone captures every peak or satisfies every pack |

Permissions must be reviewed including inherited/group grants. Read-only code
is not proof that the identity lacks write privileges. Do not grant stronger
roles because a source read fails.

## 3. Record A Decision Per Question

Use the [authoritative pilot worksheet](../source-compatibility.md#pilot-evidence-worksheet)
in protected customer storage. Include the owner, review date, scope, evidence
reference, unresolved fact and next action. These human decisions do not change
the CLI readiness status or certify a source.

**Example: fictional source review.** Current metadata is approved and complete.
CPU samples have Pod names but no required historical UID enrichment. Record
current-configuration review as a supported subset and the historical identity
gap as blocked/unknown as appropriate. Do not attach today's UIDs to old samples.

Ordinary name-only telemetry can support unresolved baseline measurements under
its supported profile. It does not become workload-bound history or a numeric
target. New recordings cannot backfill missing past observations.

## 4. Stop Or Narrow The Pilot When Needed

Stop on unverified cluster identity, unexpected privileges, forbidden fields,
unsupported private-network/proxy/certificate requirements or missing consent.
The CLI uses approved sanitized Kubernetes exports; it does not load kubeconfig
plugins. SDK decoding may transiently receive excluded Pod fields before
projection. If that is prohibited, use an approved sanitized reader/export or stop.

Do not disable TLS, open an unapproved tunnel, dump arbitrary labels/objects,
install telemetry or fabricate a complete receipt to resolve a gap. Use
synthetic failure cases unless actual failure probes are separately authorized.

## Completion

Finish with an explicitly supported subset, known blockers, unknowns, owners and
next actions. A decision to postpone historical checks is valid. Customer-source
acceptance requires independent owner review and an approved live slice where
needed; offline examples and test suites do not establish it.

Next, [plan the bounded pilot](plan-a-bounded-pilot.md). Exact mapping,
identity/recording and consent requirements remain in
[source compatibility](../source-compatibility.md),
[source profiles](../source-profiles.md) and
[security and privacy](../security-and-privacy.md).