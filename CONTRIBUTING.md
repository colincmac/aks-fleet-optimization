# Contributing

1. Create an issue using the feature or rule template.
2. Keep one backlog ID per pull request.
3. Add a failing test or fixture before implementation.
4. Preserve read-only behavior and deterministic output.
5. Run `python scripts/verify.py` or `make verify`; both use the same gates.
6. Update contracts, rule version, and docs when semantics change.

## Development setup

CI uses Python 3.12 on Windows and Linux. Install the development and Kubernetes extras before verification; the v3 historical assessment golden needs the optional CPU quantity parser, not a live Kubernetes client or credentials.

Linux/macOS with Python 3.12 installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,kubernetes]'
.venv/bin/python scripts/setup_promtool.py --download
.venv/bin/python scripts/verify.py
```

Windows PowerShell with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,kubernetes]'
.\.venv\Scripts\python.exe scripts\setup_promtool.py --download
.\.venv\Scripts\python.exe scripts/verify.py
```

Activation and GNU Make are optional. An activated environment can use `python scripts/verify.py`; `make verify` delegates to that runner, and `make PYTHON=.venv/bin/python verify` selects an explicit interpreter.

## Verification

PromQL verification requires the checksum/version/revision-pinned binary from
[eng/promtool-lock.json](eng/promtool-lock.json). Existing local `eng/promtool.exe`
or an exactly matching installed binary can be reused. Explicit setup may download
the pinned public GitHub release; the verifier itself never downloads or skips
missing tooling. See [source profiles and tool setup](docs/source-profiles.md).

The shared [verification runner](scripts/verify.py) stops on the first failure and performs:

1. Ruff lint and formatting checks, then strict mypy on source and developer scripts.
2. Read-only schema checking, actual offline `promtool` syntax/expression/recording
   tests, generated operator-catalog drift checking, and the offline pytest suite
   with coverage.
3. JSON and Markdown fixture replay at a fixed aware timestamp, including the committed expected report comparison.
4. Wheel build, offline scratch installation, installed console entry-point checks, and source/wheel report comparison.
   Catalog/configuration/preview and query-only Grafana exports are also checked
   across source and installed-wheel execution. The offline cost replay must
   preserve its exact decimal allocation partition and null savings in both.

The wheel installation uses `--no-index --no-deps`. Its scratch environment explicitly reuses dependency directories from the invoking environment, while an isolated import probe requires the advisor itself to come from the installed wheel. This tests packaging and CLI behavior, not independent dependency resolution or Docker-image execution. Package build tools are declared in the development extra; the build does not create another dependency-resolution environment.

Reports and coverage normally live in a temporary directory. To retain synthetic artifacts outside the checkout:

```bash
python scripts/verify.py --output-dir ../advisor-verification
```

Schema verification never repairs artifacts. Regenerate deliberately after a contract change, review the diff, and rerun verification:

```bash
python scripts/generate_schemas.py
python scripts/generate_schemas.py --check
```

CI runs the same command on `ubuntu-latest` and `windows-latest`, with Python 3.12, commit-pinned actions, and `contents: read` only. Dependency installation requires the approved Python package feed; CI also accesses GitHub Actions and artifact storage. Verification itself makes no Azure or Kubernetes calls and uploads only synthetic fixture reports and coverage, retained for seven days. No customer credentials or cloud write permissions are required. Linux CI execution must still be observed in GitHub; local Windows success alone is not proof of a remote CI run.

## Rule checklist

- Required evidence and missing-data behavior defined.
- Positive, negative, boundary, and low-coverage tests included.
- Reliability guardrails and validation steps included.
- Savings left null unless cost evidence supports the claim.
- Stable recommendation ID and rule version updated.

## Commit style

Use concise conventional prefixes: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `build:`, or `chore:`.
