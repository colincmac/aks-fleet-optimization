# 5. Turn A Finding Into A Review Decision

[Previous: evidence](04-evidence-quality-and-historical-identity.md) | [Next: cost](06-cost-attribution-versus-savings.md)

## Why This Matters

A report can contain a useful finding and still be incomplete. A high-confidence
investigation is not a safe replacement setting, and a suggested setting is
not permission to implement it.

## Learning Objectives

- Distinguish observation, investigation, gap and numeric suggestion.
- Explain the limits of severity, confidence and exit codes.
- Assign a next action without skipping approval or validation.

## Before You Begin

Complete [the evidence module](04-evidence-quality-and-historical-identity.md).
No tools are required for this lesson. The advisor's command-line modes are
`baseline`, for investigations without replacement values, and `guarded`, for
evaluating supported suggestions subject to all requirements.

## Concept

**Concept:** keep these stages separate:

1. An observation records a configuration or measurement.
2. An investigation asks an owner to review its significance.
3. A gap records information that is missing, failed or unsupported.
4. A guarded proposal suggests a supported numeric setting after its requirements pass.
5. Customer approval authorizes a particular test/change outside the advisor.
6. Implementation and outcome validation use the customer's own processes.

These are learning distinctions, not new advisor schema/status values.

## In AKS

A request can be low relative to usage or high relative to typical demand.
Neither ratio alone establishes service saturation, a safe reduction, application
health or bill impact. The application owner reviews reliability and demand;
the platform owner reviews controllers, placement and operational constraints.

## How The Advisor Uses This

Findings retain the rule/version, scope, measurements, risk and validation
guidance. Confidence describes the supporting evidence for that finding, not
the chance a change will be safe. Severity is not a financial priority score.
Known reliability evidence can veto a reduction even when owner policy allows it.

## What It Cannot Conclude

**Solution boundary:** the advisor never approves or applies changes. Guarded
mode does not bypass unsupported shapes or enable default-off owner opt-ins.
An empty list, vanished finding or successful command does not prove health,
resolution, approval or savings.

## Synthetic Example

**Example: fictional CPU assessment.** The overall status is `partial` because
node-pool evidence is unsupported. One workload has a qualified high-confidence
CPU investigation in baseline mode. Declared monitoring-version information
can still be unknown.

Those statements can coexist: a local investigation is supported without a
complete estate assessment or an approved request change. In the separate
guarded fixture, a bounded 1000-to-500 mCPU suggestion remains a suggestion.

## Participant Exercise

**Participant exercise:** write separate sentences for the observation, its
possible significance, the unresolved gap and the next owner action. State
whether any customer change is authorized.

## Expected Output

"Measured usage is low relative to the request, so the application owner should
review representative peaks and reliability requirements. Platform/monitoring
owners must resolve the pool/version gaps as appropriate to the next question.
No change is authorized by this report. Any numeric suggestion still needs a
separate approved one-dimension test and rollback plan."

## Discuss

- Why can an incomplete assessment still contain a useful finding?
- What would you ask before acting on a high-confidence finding?
- Who decides business priority and who authorizes implementation?

## Common Misconceptions

- `baseline` does not mean a financially validated before-change baseline.
- `guarded` does not mean approved, universally supported or risk-free.
- Exit `3` has command-specific meanings; read the report and the command guide.

## Key Takeaways

Give every investigation and gap an owner. Distinguish a supported finding from
an authorized change and from a validated outcome. Preserve the original report
and review record instead of editing evidence to obtain a better status.

## Deeper Reference

- [Rule gates and confidence](../metrics-and-scoring.md#rule-gates)
- [Finding and replay contract](../data-contracts.md#recommendation-and-replay)
- [Customer change validation](../accelerator-docs/implementation-guide.md)