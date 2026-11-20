# GitHub Copilot repository instructions

## Mission

Build a read-only, evidence-first AKS Fleet Efficiency Advisor. The product turns normalized inventory, metrics, workload metadata, and reconciled cost into deterministic recommendations. It never mutates clusters.

This is an open-source accelerator for platform teams operating AKS at enterprise scale. Complement existing Azure and Kubernetes tools rather than recreating their dashboards, recommendations, or control loops. For proposed capabilities, name the operator question those tools do not already answer.

Design for the second operator. A supported recurring workflow should be configurable without source edits, run without its original author or personal credentials, expose stale or missing evidence, and have a documented recovery path. Preserve the one-shot CLI and offline replay; do not require a new service where an existing customer tool suffices.

Separate what the accelerator can prove with synthetic fixtures, what has been validated on a named reference environment, and what each deployment must verify. A missing deployment-specific approval or data source blocks that deployment or capability—not unrelated accelerator development.

## Start here

1. Read `README.md`, `docs/README.md`, and `docs/architecture.md`.
2. Find the relevant GitHub issue and confirm its scope and acceptance criteria.
3. Read `docs/data-contracts.md`, `docs/metrics-and-scoring.md`, and security guidance for affected code.
4. Write or update a failing test before implementation.

## Technical conventions

- Python 3.15, strict typing, Pydantic v2, Ruff, mypy, and pytest.
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

## Markdown formatting

- Write each prose paragraph on one physical line; do not hard-wrap at a character limit.
- Preserve structural newlines for headings, lists, tables, code blocks, and intentional hard breaks.
- Separate paragraphs with a blank line.
