# Interpret Your First Report

[Documentation home](../README.md) | [First-run lab](../accelerator-docs/getting-started.md)

## Before You Begin

**Audience:** application owners, platform engineers and facilitators who have
completed workstation setup in the first-run lab. **Time:** about 25 minutes.
**Tools:** the installed advisor and a terminal at the repository root.
**Cloud access:** none. **Data:** every example here is fictional/synthetic.

All `text` command blocks work in Windows PowerShell and Linux/macOS after
environment setup. They print reports without writing files or contacting
Azure, Kubernetes, monitoring or billing systems. Installation itself requires
an approved package feed and is not part of this offline exercise.

You will produce a short review note: one observed fact, one investigation,
one gap, the limit of each conclusion and an accountable next action.

## 1. Read A Current-Configuration Finding

Run the scheduling check on its saved fictional configuration:

```text
aks-fleet-advisor analyze --snapshot examples/fixtures/scheduling-review-snapshot.json --pack AKS-SCHED-001 --as-of 2026-10-29T12:00:00Z --format markdown
```

Expect exit `0`, one **Investigate current placement constraints** recommendation
and zero blocked findings. Compare the [expected report](../../examples/expected-scheduling-review.md).
The fixed date matches the saved example; it checks age as of October 29, 2026,
not today. It does not change your computer's clock. Current customer assessments
must not use a past date to make outdated inputs appear current.

Read these parts in order:

| Report part | Reader question | This example |
|---|---|---|
| Summary and mode | Which scope/check ran? | One selected scheduling pack in baseline mode |
| Scope and dates | Which objects and observations support the finding? | The fictional cluster/workload, with stated observation dates |
| Evidence | What was actually observed? | One node selector and other current placement restrictions |
| Proposed actions | What is being requested? | Investigation, not a replacement setting |
| Prerequisites and risks | What remains to review? | Owner intent, matching constraints, storage and availability |

**Worked answer:** "The report observes a node selector. The platform and
application owners should explain whether it protects hardware, isolation or
availability. It does not prove spare resources are recoverable or a node can
be removed. No change is authorized."

## 2. Read A Useful Finding In A Partial Assessment

Run the CPU check in baseline mode, which proposes no replacement request:

```text
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/cpu-pack-config.yaml --pack AKS-RQ-002 --mode baseline --as-of 2026-10-29T12:00:00Z --format markdown
```

Expect exit `3`, overall status `partial` and one CPU request investigation.
Compare the [baseline report](../../examples/expected-cpu-pack-baseline.md).
The `unsupported-pool-evidence` normalization gap means some supplied inputs
cannot support pool analysis; it does not erase the qualified workload finding.

The CPU ratio `0.1` compares the 95th percentile of measured usage with the
request. P95 summarizes observed samples, not startup/failover safety or a safe
replacement value. High confidence concerns this investigation's supporting
data. Declared source-version information can still be unknown, and the whole
assessment can remain partial.

**Worked answer:** "Investigate low measured CPU relative to the request with
the application owner. Review representative demand, peaks, controllers and
reliability before choosing a test. Keep the pool/source gaps owned separately;
do not treat them as zero usage or dismiss them because one finding is useful."

## 3. Distinguish A Suggestion From Approval

Run the same fictional inputs in guarded mode:

```text
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/cpu-pack-config.yaml --pack AKS-RQ-002 --mode guarded --as-of 2026-10-29T12:00:00Z --format markdown
```

Expect exit `3`, still partial, with a policy-bounded 1000-to-500 mCPU proposal.
1000 mCPU is one CPU core. Compare the [guarded report](../../examples/expected-cpu-pack-guarded.md).
This example has the required supporting data and fictional owner policy;
it is not a setting for your application or a 50% cost-saving claim.

**Solution boundary:** guarded mode does not approve implementation, bypass
requirements or enable every owner opt-in. Never copy a fictional policy to
make a customer candidate eligible. A separate owner-approved test and rollback
plan remain necessary.

## 4. Interpret Unknown Readiness

Check the fictional onboarding declarations without contacting their services:

```text
aks-fleet-advisor readiness --config examples/onboarding-config.yaml --as-of 2026-10-29T12:00:00Z --format markdown
```

Expect exit `3` and status `unknown`, not a pass. A configured address does not
prove access, retained identity or measurement meaning. For this command, exit
`4` means an explicit blocker. The same exit number can have a different meaning
for another command; use the [readiness reference](../onboarding-questionnaire.md#offline-readiness).

**Worked answer:** "The configuration can be read, but the platform/monitoring
owners must independently verify access and required data before approved live
collection. There is no customer-source certification here."

## Participant Exercise

**Participant exercise:** write four sentences: one observed fact; one
investigation; one missing fact with its owner; and one statement of what is not
authorized. Use dates, units and exact restricted artifact references in a real
review, not copied fictional workload identities.

**Expected output:** a reviewer can trace your statements to the report and
understand the next decision without assuming that partial, high confidence or
command success means a safe change. Use the
[assessment hypothesis](../facilitator/assessment-hypothesis.md) for a later
customer-owned record; filling it does not approve a change.

## Troubleshooting And Cleanup

Command-not-found or installation problems belong in the
[first-run troubleshooting guide](../accelerator-docs/getting-started.md#troubleshooting).
Unexpected counts or lock errors need a reviewed compatible package and original
inputs, not edited hashes or weaker safety checks. Exit `2` means invalid
arguments/prerequisites; inspect the command report instead of forcing success.

No output files or cloud resources were created by these commands. Keep your
review note as needed; customer notes require approved storage and audience.

## Next Step

Read [what the input data can tell you](../learning/04-evidence-quality-and-historical-identity.md),
then [prepare an onboarding profile](../how-to/prepare-an-onboarding-profile.md).
Exact finding/replay semantics remain in [data contracts](../data-contracts.md#recommendation-and-replay).