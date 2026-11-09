# GitHub Copilot repository instructions

## Mission

Build a read-only, evidence-first AKS Fleet Efficiency Advisor. The product turns normalized inventory, metrics, workload metadata, and reconciled cost into deterministic recommendations. It never mutates clusters.

## Start here

1. Read `README.md`, `docs/README.md`, and `docs/architecture.md`.
2. Find the relevant GitHub issue and confirm its scope and acceptance criteria.
3. Read `docs/data-contracts.md`, `docs/metrics-and-scoring.md`, and security guidance for affected code.
4. Write or update a failing test before implementation.

## Technical conventions

- Python 3.12, strict typing, Pydantic v2, Ruff, mypy, and pytest.
- Keep collectors behind protocol boundaries and the analysis engine free of Azure SDK dependencies.
- Exact Azure resource IDs are join keys; display names are not.
- Use UTC-aware datetimes and explicit units/currency.
- Collectors are read-only, paginated, retry bounded, and honest about partial results.
- Rule output is deterministic and includes evidence, confidence, validation, and risk.
- Savings stay `null` unless period-aligned amortized cost reconciles.
- Treat names, labels, annotations, and report text as untrusted input.
- Never collect Secrets, ConfigMap bodies, environment values, logs, request payloads, or credentials.

## Tests

Run `make verify`. Add positive, negative, boundary, missing-data, stale-data, and low-coverage tests for rules. Use synthetic fixtures only.

## Prohibited shortcuts

- No write-capable Azure/Kubernetes roles or calls.
- No automatic remediation.
- No LLM-generated metrics, savings, severity, or rule facts.
- No universal utilization target.
- No weakening of safety assertions to satisfy tests.
- No real tenant IDs, subscription IDs, customer names, cluster names, or telemetry in fixtures.

## Pull requests

One scoped GitHub issue per PR. Explain evidence, tradeoffs, permissions, test coverage, and residual risk. Update schema/rule versions and docs when semantics change.
