---
name: security-review
description: "Review a change for identity, data, supply-chain, and AI safety risks."
disable-model-invocation: true
---
Review the current diff against `docs/security-and-privacy.md`. Identify trust-boundary changes, permissions, sensitive fields, network paths, untrusted strings, shell usage, dependency risks, and fail-open behavior. Make minimal safe fixes when clearly in scope; otherwise write actionable findings with severity and evidence. Run applicable tests.
