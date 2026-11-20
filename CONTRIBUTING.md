# Contributing

1. Create an issue using the feature or rule template.
2. Keep one backlog ID per pull request.
3. Add a failing test or fixture before implementation.
4. Preserve read-only behavior and deterministic output.
5. Run focused verification during edits and `python scripts/verify.py` or `make verify` at phase boundaries and before a pull request; the full commands use the same gates.
6. Update contracts, rule version, and docs when semantics change.

## Development setup

Python 3.15 is the minimum required version and development baseline; Python 3.12-3.14 are no longer supported. CI is configured to verify Python 3.15 on Windows and Linux. Release certification requires complete runtime/platform evidence; configuring CI alone does not establish it. Install the development and Kubernetes extras before verification; the v3 historical assessment golden needs the optional CPU quantity parser, not a live Kubernetes client or credentials.

Keep `requires-python`, Ruff and mypy compatibility targets at Python 3.15. Development dependencies require Ruff 0.17.3+ and mypy 1.20.2+, the verified tools for this target. The matrix uses standard GIL-enabled interpreters, not free-threaded or explicitly enabled experimental JIT builds. The development interpreter is pinned by `.python-version`.

PyYAML 6.0.3 has no Python 3.15 Windows wheel. Its supported `PYYAML_FORCE_LIBYAML=0` build setting disables the optional C extension without changing the advisor's safe YAML loaders. `uv sync` applies this setting from `pyproject.toml`; pip does not read uv settings, so pip setup below, CI and Docker explicitly set it. No C++ compiler is needed for PyYAML. Use the approved package feed; do not bypass TLS or integrity checks.

With uv:

```text
uv sync --locked --extra dev --extra kubernetes
uv run --no-sync python scripts/setup_promtool.py --download
uv run --no-sync python scripts/verify.py
```

Linux/macOS with Python 3.15 installed:

```bash
python3.15 -m venv .venv
PYYAML_FORCE_LIBYAML=0 .venv/bin/python -m pip install -e '.[dev,kubernetes]'
.venv/bin/python scripts/setup_promtool.py --download
.venv/bin/python scripts/verify.py
```

Windows PowerShell with Python 3.15 installed:

```powershell
py -3.15 -m venv .venv
$env:PYYAML_FORCE_LIBYAML = "0"
.\.venv\Scripts\python.exe -m pip install -e '.[dev,kubernetes]'
.\.venv\Scripts\python.exe scripts\setup_promtool.py --download
.\.venv\Scripts\python.exe scripts/verify.py
```

Activation and GNU Make are optional. An activated environment can use `python scripts/verify.py`; `make verify` delegates to that runner, and `make PYTHON=.venv/bin/python verify` selects an explicit interpreter.

## Prepare An Offline Fleet Lab

From a clean, reviewed revision, build the wheel and a separate ZIP containing the [standalone fleet guide](examples/fleet-lab.md) and its four fictional inputs. These commands assume that `HEAD` is the reviewed revision and the development dependencies are installed:

```text
python -m build --wheel --no-isolation
git archive --format=zip --output=dist/aks-fleet-lab.zip HEAD examples/fleet-lab.md examples/fixtures/workload-assessment.json examples/pool-assessment-config.yaml examples/fixtures/fleet-peer-assessment.json examples/fleet-peer-config.yaml
```

Pair the wheel and ZIP from the same revision. Before distributing, install the base wheel without extras into a fresh environment using the approved package feed, extract the ZIP outside the checkout, and run the fleet lab from its root. Keep the ZIP input allowlist explicit; never include customer evidence, `.local`, or generated customer reports. These commands create local files only; they do not publish a release or replace release verification.

## Verification

### During Small Changes

Use the focused verifier with the affected test files or pytest node IDs. Repeat `--test` for related modules, shared callers and regression tests:

```powershell
python scripts/verify.py --quick --test tests/test_fleet.py --test tests/test_history.py
```

This runs Ruff lint/format, strict mypy, read-only documentation/schema/catalog checks and only the selected tests. It skips coverage collection, promtool, full-suite execution, golden CLI replays, wheel builds and installed-wheel comparisons. It requires explicit existing test files or node IDs and prints that full verification was not run. Individual checks and the verifier report elapsed time.

For a tiny local edit, running the affected pytest test directly is also appropriate before the focused verifier. Include neighboring integration tests when changing shared admission, normalization or rule-engine behavior; selecting fewer tests is not permission to omit a required safety regression.

### At Phase Boundaries

Run the full verifier after a major change, phase or epic and before a pull request or release. Run it earlier for packaging, dependencies, shared contracts, query assets or cross-module changes whose risks are not covered by the focused slice. CI continues to run the full verifier; `--quick` is not an acceptance or release gate. It is not necessary to repeat the full source/wheel replay after every small edit.

PromQL verification requires the checksum/version/revision-pinned binary from [eng/promtool-lock.json](eng/promtool-lock.json). Existing local `eng/promtool.exe` or an exactly matching installed binary can be reused. Explicit setup may download the pinned public GitHub release; the verifier itself never downloads or skips missing tooling. See [source profiles and tool setup](docs/source-profiles.md).

To change the Prometheus/promtool release without manually calculating revisions or checksums, run `python scripts/setup_promtool.py --update-lock VERSION --download`, review the generated lock, then run `python scripts/setup_promtool.py --download --replace` and the full verifier. Use an exact published version without a leading `v`; see [the version-update workflow](docs/source-profiles.md#change-the-prometheuspromtool-version). Source-profile compatibility declarations require separate characterization and are not changed by this command.

The shared [verification runner](scripts/verify.py) stops on the first failure and performs:

1. Ruff lint and formatting checks, then strict mypy on source and developer scripts.
2. Read-only schema checking, actual offline `promtool` syntax/expression/recording tests, generated operator-catalog drift checking, and the offline pytest suite with coverage.
3. JSON and Markdown fixture replay at a fixed aware timestamp, including the committed expected report comparison.
4. Wheel build, offline scratch installation, installed console entry-point checks, and source/wheel report comparison. Catalog/configuration/preview and query-only Grafana exports are also checked across source and installed-wheel execution. The offline cost replay must preserve its exact decimal allocation partition and null savings in both.

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

CI runs the same complete verifier for Python 3.15 on `ubuntu-latest` and `windows-latest`, with commit-pinned actions and `contents: read` only. No lane uses `--quick` or allows failures; artifacts include both OS and Python version to avoid collisions and preserve attribution. Dependency installation requires the approved Python package feed; CI also accesses GitHub Actions and artifact storage. Verification itself makes no Azure or Kubernetes calls and uploads only synthetic fixture reports and coverage, retained for seven days. No customer credentials or cloud write permissions are required. Configuring a lane does not prove it has run; local Windows success alone is not Linux, remote CI or full source/wheel acceptance.

A prior Windows/Python 3.14.1 covered run intermittently failed with `NameError: name 'summary_variants' is not defined`. A later full-order instrumented run passed without changing the validator, but the cause is unresolved. Retain the first traceback and exact Python/dependency versions if it recurs; do not suppress the exception, weaken catalog validation or mark the failure resolved from a passing subset. Review the [3.13](https://docs.python.org/3.13/whatsnew/3.13.html#porting-to-python-3-13), [3.14](https://docs.python.org/3.14/whatsnew/3.14.html#porting-to-python-3-14) and [3.15](https://docs.python.org/3.15/whatsnew/3.15.html#porting-to-python-3-15) porting guidance for demonstrated failures. Deferred annotations, UTF-8 defaults and C-extension compatibility warrant validation; this baseline change does not require adopting lazy imports, new builtins or unrelated syntax rewrites.

## Publish The Advisor Container

The [Publish Python image to ACR workflow](.github/workflows/publish-python-image.yml) runs on `main` when image inputs change or when you select `main` under **Actions > Publish Python image to ACR > Run workflow**. It builds the root [Dockerfile](Dockerfile) for `linux/amd64`, runs the advisor's `--help` without network access, and pushes `crzavaplatformprimary.azurecr.io/aks-fleet-advisor:<full-commit-sha>`. The run summary records the digest reference; use it for deployments that need an immutable image. The workflow does not push a `latest` tag, deploy to AKS, or change the demo workloads.

1. In GitHub, create the `acr-publish` environment and restrict its deployment branches to `main`. Set the environment variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` for the registry's Azure subscription and the dedicated publishing identity.
2. Set up [GitHub OIDC federation in Microsoft Entra](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) for that identity. Select the GitHub environment entity type, with subject `repo:<owner>/<repository>:environment:acr-publish` and audience `api://AzureADTokenExchange`. Use a user-assigned managed identity or a dedicated app registration; no client secret or ACR admin password is needed.
3. Give only the publishing identity the appropriate [registry role](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-built-in-roles-overview): `Container Registry Repository Writer` with a condition limiting access to `aks-fleet-advisor` for an ABAC-enabled registry, or `AcrPush` scoped to the registry in registry-only RBAC mode. Do not assign this role to the advisor's runtime identity.

The GitHub-hosted runner needs HTTPS access to GitHub, Docker Hub, the Python package index, Microsoft Entra, Azure Resource Manager, and the registry endpoints. If the registry requires private connectivity, use an approved runner with that connectivity rather than opening the registry. After setup, dispatch the workflow on `main` and verify the tag and digest in ACR. If login or push fails, check the exact federated subject, registry role mode and runner connectivity before rerunning.

## Rule checklist

- Required evidence and missing-data behavior defined.
- Positive, negative, boundary, and low-coverage tests included.
- Reliability guardrails and validation steps included.
- Savings left null unless cost evidence supports the claim.
- Stable recommendation ID and rule version updated.

## Commit style

Use concise conventional prefixes: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `build:`, or `chore:`.
