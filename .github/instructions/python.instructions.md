---
applyTo: "src/**/*.py,tests/**/*.py,scripts/**/*.py"
---
Use Python 3.12, full annotations, small pure functions, and explicit domain types. Keep I/O at adapters. Do not catch broad exceptions without re-raising a typed, actionable error. Test deterministic behavior and missing data. Format with Ruff and pass strict mypy.
