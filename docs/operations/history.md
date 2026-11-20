# Offline assessment history

Compare two saved assessments directly when you only need a pairwise trend. An optional local history store retains copies for later inspection, but comparison does not require importing them. Both workflows use existing `assess --artifacts` directories and never contact Azure, Kubernetes, metrics or billing endpoints.

## Compare Artifact Directories

From the repository root after installation/activation, create two fictional assessment bundles in fresh directories. Both `assess` commands exit `3` because this example has partial evidence. The second command evaluates the same retained evidence one hour later; it demonstrates comparison, not new measurements or an improvement.

```powershell
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z --format json --artifacts comparison-previous
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T13:00:00Z --format json --artifacts comparison-current
aks-fleet-advisor compare --previous comparison-previous --current comparison-current --tenant 00000000-0000-0000-0000-000000000000
```

The comparison exits `0` and prints `history-trend` JSON with `comparable: true` and `savings: null`. For your own inputs, provide the original earlier and later artifact directories and their approved tenant. Each directory needs `manifest.json` and all five original files: `fragments.json`, `snapshot.json`, `analysis-config.json`, `assessment.json` and `report.md`. An individual snapshot or report is not a complete bundle.

`compare` validates both bundles' hashes, original tenant/input/snapshot/configuration bindings and exact deterministic replay at each original report time before computing trends. It creates no store, copies or output directories and does not modify inputs. Its content IDs, states and pair-scoped first/last observations match importing and comparing the same pair. The caller must retain a package with compatible installed pack locks; comparison never reseals locks, changes evidence dates or establishes source authenticity.

Valid operations return `0`, including partial evidence and a `not_comparable` pair. Invalid tenant, integrity, replay, time order, missing files or limits returns `2`, with input values omitted from the error. Reads are bounded to 32 MiB of original payload per bundle; links and junctions are rejected. Choose directories explicitly; there is no implicit latest-run selection. Source freshness remains evaluated at each saved report time, not refreshed by comparison.

## Import And Inspect

From the repository root, create a synthetic assessment using the existing fixture. Ensure the ignored `.local` parent directory exists and choose a fresh output directory; do not overwrite the supplied canonical `history-example` bundle. Its exit code is `3` because the assessment is partial:

```powershell
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli assess --fragments examples/fixtures/history-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z --format json --artifacts .local/history-example
```

Import into a new local store whose parent directory already exists:

```powershell
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli history import --artifacts .local/history-example --store assessment-history --tenant 00000000-0000-0000-0000-000000000000
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli history list --store assessment-history --tenant 00000000-0000-0000-0000-000000000000
```

The import emits its SHA-256 `run_id`. Repeating an identical import returns the same run without overwriting anything. Listing a nonexistent store returns `[]` without creating directories. Import/list/compare return `0` on valid operations, including partial evidence; invalid input, tenant, integrity, version, time order or limits returns `2`. Neither command success nor assessment `complete` means findings are safe, approved, resolved or financially reconciled.

Import a separately produced later assessment, then compare the exact returned run IDs in PowerShell:

```powershell
python -m aks_fleet_efficiency.cli history compare --store assessment-history --tenant 00000000-0000-0000-0000-000000000000 --previous $PreviousRunId --current $CurrentRunId
```

Comparisons require strictly increasing evaluation times and nondecreasing window ends. Out-of-order imports are allowed; listing sorts by evaluation time, window end and content ID. No implicit latest-run selection is performed.

## Evidence And Trends

Every imported run preserves the original five artifact files as UTF-8 payloads with their original hash manifest. Import checks the exact file allowlist, hashes, tenant, snapshot/configuration/input bindings and deterministic report replay against the installed locked packs before writing. Hashes provide integrity, not authenticity, source attestation or approval. No cost artifacts or approval/delivery/outcome events are mixed into assessment history.

Finding IDs are the engine's exact recreation-aware IDs, never display-name joins. Comparisons require equal tenant, cluster IDs/fingerprints, requested source scopes, effective configuration, original pack definitions/parameters and window duration. A changed basis gives `not_comparable`, not an improvement. Matching findings are `persistent` or `changed` according to their entire original finding record; a newly eligible finding is `new`. Current explicit blocked records remain `blocked`. An absent prior finding is `not_observed`, even on a complete run. Losing all pool history can prevent pool normalization: that absence is not a fabricated blocked record or proof of resolution. First/last observed times refer only to eligible observations in the selected pair, not a lifetime history. These same rules apply to direct `compare` and store-based `history compare`. There is deliberately no `resolved` state, claimed capacity released, financial trend, savings calculation or governance decision. Savings remain null.

## Storage And Operations

- Schema `1.0`: one tenant-bound `store.json` and one content-addressed JSON envelope per run. Snapshots, original configurations/pack versions, receipts, reports and their hashes remain together; summaries are rebuilt, not mutable indexes. Independent `history-run`/`history-trend` schemas describe CLI output.
- Bounds: 32 MiB total original artifact payload per import, 64 MiB per stored envelope, 1,000 runs and 128 MiB total run files. Limits fail visibly without pruning evidence. A SHA-256 filename is required; links/junctions and unknown store entries are rejected. No input-controlled artifact path is followed.
- Use one writer on a trusted local filesystem supporting same-directory hard links, with exclusive customer-controlled access. Complete, flushed temporary files are published without overwriting an existing run. Interrupted temporary files are not visible runs. This is application-level immutability, not WORM storage, multiwriter coordination, a power-loss durability guarantee or an authentication/authorization boundary.
- Tenant flags are binding checks only. The CLI provides no Entra authentication, encryption, ACL provisioning, report-audience control or audit service. Owners must supply approved local access, encryption, residency and retention. Treat names, metadata and report text as untrusted; do not render archived content as executable markup or share it without audience approval.
- Back up the entire quiescent store using customer tooling, restore into a new protected directory, then run `history list` to validate tenant, schemas and content hashes. Original UTF-8 artifact bytes can be recovered from envelope `payloads`; changing a stored envelope invalidates its content ID. Copies are not authenticated backups. No online backup/restore service is claimed.
- Retention/deletion remains an explicit customer data-handling operation; there is no automatic expiration or CLI deletion. Set retention before use, rotate stores before limits, and preserve required audit evidence separately.
- Unknown schema versions fail closed; no in-place migration exists. Listing and comparing originals do not re-evaluate findings, but all commands validate original configuration locks against installed packs. Retain a compatible package version to read old stores; incompatible pack upgrades fail visibly before comparison. Cross-version continuity is not implemented. New imports additionally require deterministic replay; old locks are never resealed.

Direct comparison adds no storage service; the store remains optional. Local history does not provide remote persistence, lifecycle-wide first/last-seen, supersession, automatic schedules, notifications, retention enforcement, migrations or authenticated APIs. Importing or comparing artifacts authorizes no source access or change to the estate.
