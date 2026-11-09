---
name: implement-collector
description: Implement a read-only collector against the normalized snapshot contract.
disable-model-invocation: true
---
Implement the requested collector using read-only permissions. Page all results, bound retry/concurrency, preserve exact IDs and UTC windows, record coverage and partial failures, and return normalized models. Use mocked contract tests and synthetic fixtures. Do not collect secrets, logs, payloads, or configuration bodies. Run `make verify`.
