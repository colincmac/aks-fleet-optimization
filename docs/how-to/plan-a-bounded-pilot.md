# Plan A Small Customer Pilot

[Documentation home](../README.md) | [Assessment steps](../accelerator-docs/assessment-guide.md)

## Goal And Prerequisites

A pilot checks a small approved question in the customer's actual environment.
It is not a fleet-wide rollout or a demand for a numeric recommendation.
Complete the fictional labs and review [input readiness](validate-source-compatibility.md)
with platform, monitoring, application and security owners first. This guide
contains no command that contacts a source or changes a cluster.

Use the [workbook](../facilitator/participant-workbook.md) for the agreed record.
Keep the populated record, profiles and reports in approved customer storage.

## 1. Agree One Useful Outcome

**Example: fictional scope.** One nonproduction cluster, one application class
and a current-placement investigation. The desired output is an owner-reviewed
explanation of restrictions and missing data, not permission to consolidate.

Choose one to three questions and explicit exclusions. Record the desired
outcome, non-regression requirements, owners, report audience and review date.
Do not extrapolate to production or another workload class from this slice.

## 2. Distinguish The Approval Gates

| Gate | Decision owner | Required record |
|---|---|---|
| Discovery/data review | Platform, monitoring and application owners | Exact scope, selected checks, input shape and unresolved information |
| Data handling and live reads | Authorized source/security/platform approvers | Approved principal/runner, source/endpoint, identities, period/queries, budgets, destination, consent expiry and stop contact |
| Any later implementation | Customer change/application/platform approvers | A separately reviewed hypothesis, canary, numeric guardrails, rollback and accountable operator |
| Financial conclusion | FinOps/business owner | Period/currency, matched actual billing evidence, commitments, confounders and explicit conclusion limits |

A profile, digest, worksheet or `--allow-live` flag alone satisfies none of these
approval gates. Independent collection and change permissions stay separate.

## 3. Set Bounds Before Collection

Use exact approved identities, not matching display names. Review effective
read-only permissions including inherited grants and the runner's supported
network/certificate path. Agree maximum reads, objects, queries and elapsed
time, plus independent transport timeouts and a way to stop the runner.

The [source validation plan](../source-compatibility.md#bounded-validation-plan)
defines the detailed consent and proposed ceiling template. Have operators
approve the actual values; do not copy documentation defaults as consent.
If full required history exceeds the budget, narrow the selected entities/checks
or obtain revised approval, not a shorter undeclared observation window.

## 4. Define Stop And Acceptance Conditions

Stop on identity/TLS mismatch, unsafe fields, unexpected privileges, withdrawn
or expired consent, budget exhaustion or unsupported connectivity. Do not
broaden access, disable security checks or edit receipts to complete a run.
Use approved sanitized exports if transient full Pod decoding is prohibited.

A short transport test establishes only transport/shape, not the longer history
needed for a recommendation. Test failures with synthetic inputs unless a live
failure scenario is explicitly included in the consent.

Accept the assessment when owners understand its supported subset, partial/
blocked results, exact dates/units and next actions, and can repeat the saved
analysis with its original settings. Acceptance may be "gather more evidence",
"retain intentional capacity" or "defer". It need not include an implemented
change or claimed savings.

## 5. Handoff Without Changing The Advisor's Role

Use the [assessment sequence](../accelerator-docs/assessment-guide.md) for actual
execution and the [hypothesis record](../facilitator/assessment-hypothesis.md)
for a candidate intervention. Implementation uses customer tooling and separate
authorized identities; never grant the advisor writes for the next stage.

In Well-Architected or FinOps engagements, this is a bounded evidence workstream,
not an official score, certification, comprehensive cost review or savings
guarantee. Agree the larger engagement's required artifacts with its owner.

## Completion

You have a useful pilot plan when an operator can identify exactly what is
approved, when to stop, which output counts as completion and who owns the next
decision. There is no resource cleanup from reading/preparing this plan; any
later collection, storage retention or customer experiment has its own approved
handling and rollback requirements.

Authoritative boundaries: [security](../security-and-privacy.md),
[collection contracts](../data-contracts.md#collection-plan-and-artifacts) and
[source-specific pilot validation](../source-compatibility.md).