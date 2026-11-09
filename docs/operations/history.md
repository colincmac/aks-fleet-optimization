# Offline assessment history

Use local history to retain and compare verified assessment artifacts, not as a
deployed monitoring service. It imports only existing `assess --artifacts` directories. Import,
listing and comparison never contact Azure, Kubernetes, metrics or billing
endpoints.

## Import And Inspect

From the repository root, create a synthetic assessment using the existing
fixture. Its exit code is `3` because the assessment is partial:

```powershell
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli assess --fragments examples/fixtures/history-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z --format json --artifacts history-example
```

Import into a new local store whose parent directory already exists:

```powershell
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli history import --artifacts history-example --store assessment-history --tenant 00000000-0000-0000-0000-000000000000
.\.venv\Scripts\python.exe -m aks_fleet_efficiency.cli history list --store assessment-history --tenant 00000000-0000-0000-0000-000000000000
```

The import emits its SHA-256 `run_id`. Repeating an identical import returns the
same run without overwriting anything. Listing a nonexistent store returns `[]`
without creating directories. Import/list/compare return `0` on valid operations,
including partial evidence; invalid input, tenant, integrity, version, time order
or limits returns `2`. Neither command success nor assessment `complete` means
findings are safe, approved, resolved or financially reconciled.

Import a separately produced later assessment, then compare the exact returned
run IDs in PowerShell:

```powershell
python -m aks_fleet_efficiency.cli history compare --store assessment-history --tenant 00000000-0000-0000-0000-000000000000 --previous $PreviousRunId --current $CurrentRunId
```

Comparisons require strictly increasing evaluation times and nondecreasing
window ends. Out-of-order imports are allowed; listing sorts by evaluation time,
window end and content ID. No implicit latest-run selection is performed.

## Evidence And Trends

Every imported run preserves the original five artifact files as UTF-8 payloads
with their original hash manifest. Import checks the exact file allowlist,
hashes, tenant, snapshot/configuration/input bindings and deterministic report
replay against the installed locked packs before writing. Hashes provide
integrity, not authenticity, source attestation or approval. No cost artifacts
or approval/delivery/outcome events are mixed into assessment history.

Finding IDs are the engine's exact recreation-aware IDs, never display-name
joins. Comparisons require equal tenant, cluster IDs/fingerprints, requested
source scopes, effective configuration, original pack definitions/parameters and
window duration. A changed basis gives `not_comparable`, not an improvement.
Matching findings are `persistent` or `changed` according to their entire
original finding record; a newly eligible finding is `new`. Current explicit
blocked records remain `blocked`. An absent prior finding is `not_observed`,
even on a complete run. Losing all pool history can prevent pool normalization:
that absence is not a fabricated blocked record or proof of resolution.
First/last observed times refer only to eligible observations in the selected
pair, not a lifetime history. There is deliberately no `resolved` state, claimed
capacity released, financial trend, savings calculation or governance decision.
Savings remain null.

## Storage And Operations

- Schema `1.0`: one tenant-bound `store.json` and one content-addressed JSON
  envelope per run. Snapshots, original configurations/pack versions, receipts,
  reports and their hashes remain together; summaries are rebuilt, not mutable
  indexes. Independent `history-run`/`history-trend` schemas describe CLI output.
- Bounds: 32 MiB total original artifact payload per import, 64 MiB per stored
  envelope, 1,000 runs and 128 MiB total run files. Limits fail visibly without
  pruning evidence. A SHA-256 filename is required; links/junctions and unknown
  store entries are rejected. No input-controlled artifact path is followed.
- Use one writer on a trusted local filesystem supporting same-directory hard
  links, with exclusive customer-controlled access. Complete, flushed temporary
  files are published without overwriting an existing run. Interrupted temporary
  files are not visible runs. This is application-level immutability, not WORM
  storage, multiwriter coordination, a power-loss durability guarantee or an
  authentication/authorization boundary.
- Tenant flags are binding checks only. The CLI provides no Entra authentication,
  encryption, ACL provisioning, report-audience control or audit service. Owners
  must supply approved local access, encryption, residency and retention. Treat
  names, metadata and report text as untrusted; do not render archived content
  as executable markup or share it without audience approval.
- Back up the entire quiescent store using customer tooling, restore into a new
  protected directory, then run `history list` to validate tenant, schemas and
  content hashes. Original UTF-8 artifact bytes can be recovered from envelope
  `payloads`; changing a stored envelope invalidates its content ID. Copies are
  not authenticated backups. No online backup/restore service is claimed.
- Retention/deletion remains an explicit customer data-handling operation;
  there is no automatic expiration or CLI deletion. Set retention before use,
  rotate stores before limits, and preserve required audit evidence separately.
- Unknown schema versions fail closed; no in-place migration exists. Listing
  and comparing originals do not re-evaluate findings, but all commands validate
  original configuration locks against installed packs. Retain a compatible
  package version to read old stores; incompatible pack upgrades fail visibly
  before comparison. Cross-version continuity is not implemented. New imports
  additionally require deterministic replay; old locks are never resealed.

Local history does not provide remote persistence, lifecycle-wide first/last-seen,
supersession, automatic schedules, notifications, retention enforcement,
migrations or authenticated APIs. Importing or comparing artifacts authorizes
no source access or change to the estate.