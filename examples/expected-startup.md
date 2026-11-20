# AKS Fleet Efficiency Advisor Report

Generated: 2026-10-29T12:00:00+00:00
Assessment mode: `baseline`
Observation window: 2026-09-29T00:00:00+00:00 to 2026-10-29T00:00:00+00:00

## Summary

- Clusters analyzed: 1
- Snapshot ARM node-pool records: 0
- Snapshot vertical-workload records: 1
- Recommendations: 1
- High or critical: 0
- Blocked findings: 0
- `AKS-START-001` subjects evaluated: 1
Subject counts use each pack's evaluation unit, include blocked/no-finding evaluations, and are not additive workload counts or evidence of complete inventory.
- Snapshot digest: `3542bfd9927b389dc6f9b74f0c4ceca61da2a9a2612f4369c5ded510c5a7f684`
- Configuration digest: `e2edb39c53a4e02f6076c91d23f79b3fb640477b59fc5acd32555af0b7c1ed9c`
- Pack: `AKS-START-001` v1.0.0; digest: `8450c0d16acdcf131818821a967882bd5656213773902a1349af13724819933d`; inventory-only

## Data quality warnings

- Independent metric context: Metric coverage 0% is below the configured minimum 85%. Not required by the selected packs.
- Collection is partial overall; selected findings are gated independently on their required, complete, correctly scoped sources.

## Recommendations

### 1. Investigate observed readiness and subsequent demand

- **ID:** `AKS-START-001-ec25ef211ae2`
- **Rule:** `AKS-START-001` v1.0.0
- **Severity / confidence:** info / medium
- **Cluster:** `aks-synthetic`
- **Scope:** `synthetic` / `synthetic`
- **Category:** reliability

Saved samples bracket an observed Pod readiness transition. This is not application startup duration, proof of a first attempt or a safe resource setting.

**Evidence**

- `observed_readiness_lower` = `480.0` seconds since Pod creation; sampled proxy (saved-lifecycle-history)
- `observed_readiness_upper` = `540.0` seconds since Pod creation; sampled proxy (saved-lifecycle-history)

**Prerequisites**

- Obtain approved existing saved lifecycle evidence; do not install an observer, collect Events/logs or infer history from current status.

**Proposed actions**

- Review the observed readiness bracket and independent measurement gaps with the workload owner; do not choose a resource or replica target.

**Validation and safety**

- Review exact Pod/container identity, original receipts, sample cadence and readiness criterion before interpreting the observed bracket.
- Review independent application startup, SLO, peak, failover and representative usage evidence before considering any change.
- Risk: Pod readiness may reflect probes or readiness gates rather than application initialization, and sampling can miss transitions or peaks.

**Rollback**

- No change is proposed; preserve original settings for rollback of any separately approved experiment.

## Interpretation

This report proposes investigations and controlled changes; it does not authorize or apply changes. Validate recommendations against workload SLOs, resilience requirements, business cycles, and representative load.

