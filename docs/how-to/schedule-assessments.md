# Schedule assessments for an AKS fleet

Start with one non-production cluster. Run the same command manually once, then schedule it with an existing job runner. The command reads fresh, approved files, saves one replayable bundle per cluster, and generates the JSON that the optional Headlamp Assessments tab reads. No custom resource, governance backend, billing access, or Azure/Kubernetes credentials are needed by this command.

To see fictional results instead, open the [Headlamp preview](../../plugins/headlamp-fleet-efficiency/README.md#develop) at `/fleet-efficiency/assessments`. If your question is about live CPU data, start with the [Grafana walkthrough](investigate-low-cpu.md); it does not depend on the batch runner or Headlamp.

## Choose a pilot

| Path | What you can validate now | What must be checked in your environment |
| --- | --- | --- |
| Local synthetic preview | Assessment navigation and the distinction between findings and evidence gaps. | Synthetic fixtures do not validate host authentication, source access, or a scheduler. |
| Existing scheduler and Headlamp web | Fresh saved-fragment processing, replay, and authenticated static publication. | Confirm your pinned Headlamp version and reader groups, including a direct unauthorized request to **both** feed routes. AKS Desktop is not yet a certified pilot host. |
| Existing Grafana | Import the [Azure Monitor managed Prometheus cluster dashboard](../../deploy/grafana/aks-cluster-efficiency.json) for cluster, namespace and Pod trends. Follow the [CPU walkthrough](investigate-low-cpu.md) for a single container. Neither needs Headlamp. | Verify the unique cluster alias, required series and retention. Name-only samples do not establish historical workload identity. A fleet rollup and controller-level workload attribution remain follow-up work. |

Before any live run, use this checklist. A replay-tested workflow, reference-host validation (record the scheduler, image and host versions), and qualification in your own deployment are distinct checks.

- [ ] Record the exact non-production cluster ID/fingerprint, accepted source semantics and approved private network path. Use a non-personal, scoped identity for each automated responsibility.
- [ ] Choose a pinned runner, UTC cadence, lead time for the producer, and a team destination for overdue, failed, and repeated partial runs. Identify who can suspend jobs and withdraw publication.
- [ ] Choose protected input and archive locations, retention/deletion policy, and a separate approved read audience. Use an allowed and a denied test identity for each published route and run reference.
- [ ] Ask a second operator to add a cluster by configuration, detect a missed run, restore fresh input, replay one saved run, and explain one changed or blocked finding. Do not advance to more clusters before that succeeds.

Do not copy real scope IDs, role bindings, or evidence into repository examples. A passing offline `readiness` check does not verify connectivity or permissions.

## 1. Prepare one approved input

| What you need | Who supplies it |
| --- | --- |
| A one-cluster [onboarding profile](prepare-an-onboarding-profile.md) with the exact Azure cluster resource ID. Start in baseline mode with the checks you need. | Platform owner |
| A separately verified cluster fingerprint (`cluster_uid` in sanitized metadata), and one fresh `AssessmentFragments` JSON file for the cluster. | Approved evidence producer |
| Two protected directories: an archive for original bundles, and a separate directory for the published feed. Use a filesystem that supports atomic replacement. | Platform operator |
| An authorized same-origin Headlamp route, if using the UI. | Headlamp operator |

Use one of these input paths. The batch command only consumes files; it never queries a source or refreshes its clocks.

- **Separate approved inventory exports:** for the one-cluster, inventory-only pilot, use [`stage-assessment-input`](#stage-separate-inventory-exports) to combine the approved Azure and sanitized Kubernetes files without hand-editing assessment JSON.
- **Existing approved producer:** deliver one schema-1.0 [assessment fragments](../../schemas/assessment-fragments.schema.json) file per target with exact tenant/cluster/fingerprint and the original source receipts.
- **Advisor collector with a customer export:** use [the collection workflow](../operations/runbook.md#collection-and-assessment) to run `collect --output` into a new staging file. That CLI path still needs a fresh sanitized Kubernetes export. The [injected reader workflow](../operations/runbook.md#kubernetes-metadata-api) is a starting point for an independently approved producer; it does not provision its identity or fetch a kubeconfig. Do not feed raw object dumps into the runner.

Deliver the completed staging file to the configured path with an atomic rename on the same protected filesystem. Never stream a partially written file into that path. If collection fails, leave the prior file unmodified and surface the producer failure. Do not update source observation clocks to match a file write, scheduler run or retry. Check the target profile with `aks-fleet-advisor readiness --config <profile>` before scheduling.

### Stage separate inventory exports

Configure one target in `batch.json`, set `slot_input_window_minutes`, and select explicit inventory-only packs in baseline mode in the cluster profile. Point `targets[0].fragments` to a protected JSON file outside the archive and feed directory. Use one producer writer per staging path, serialized across manual runs, scheduled runs, and retries.

```text
aks-fleet-advisor stage-assessment-input --batch batch.json --inventory azure-inventory.json --metadata kubernetes-metadata.json --slot <scheduled-utc-time>
```

The command reads two complete, scoped exports within the configured slot window and verifies their tenant, cluster, and Kubernetes fingerprint bindings. It writes one inventory-only input atomically, retaining both original source receipts. Its assessment window ends at the earlier source observation; it is not a metric history window. With a single writer, an older delivery or an invalid input cannot replace the last staged file. Exit `0` means the input was staged, not that the batch ran or published. Exit `2` means staging failed; check the producer and protected destination rather than editing inputs or clocks. This is format and scope validation, not source authentication. It does not collect either export or use Prometheus.

## 2. Run on demand

Copy the [batch profile example](../../examples/assessment-batch.json) and substitute the approved tenant, target config path, fragments path, and verified fingerprint. Relative paths in the batch profile resolve next to that file, not relative to the scheduler's working directory. The supplied example is a template: its historical fixtures intentionally fail the freshness check. Use the preview to see those fictional results; do not change file timestamps or evidence clocks to make them pass. If your batch profile enables a slot input window, use the same `--slot` for staging and assessment even in a manual rehearsal.

Run this from a protected directory containing your `batch.json`, existing `runs` archive and existing `feed` directory. The same command works in PowerShell or a POSIX shell:

```text
aks-fleet-advisor assess-batch --batch batch.json --artifacts runs --feed feed/assessments.json
```

| Exit code | Meaning | What to do |
| --- | --- | --- |
| `0` | A complete batch was published for the selected scope. | Confirm each expected cluster and its evidence window. This does not certify health. |
| `3` | A batch was published with a partial assessment or an isolated target failure. | Review blocked checks, retained results, and missing targets; record a warning. |
| `2` | Batch input was refused, for example because of a stale clock, duplicate cluster or fingerprint mismatch. | Correct the input. The prior feed is unchanged. |
| `1` | Runner could not acquire the writer lock or finish storage, replay, or publication. | Inspect the job and prerequisites. Retain the prior feed. |

The runner uses current UTC and rejects a missing, future, or stale Azure/Kubernetes source observation or assessment window end, using the profile's evidence age limit (24 hours by default). Individual metric and rule gates still apply. By default, a hard failure on one target leaves the previous feed intact for the entire audience; newly written bundles may remain in the archive, but their presence does not mean the batch published.

For recurring runs, set the optional top-level `"slot_input_window_minutes": 60` in the batch profile and always pass `--slot`. That example accepts the original Azure/Kubernetes source observation clocks and the assessment window end **after** `slot − 60 minutes` and **at or before** `slot`, in addition to the ordinary age checks. Set the value to cover the producer's delivery timing without exceeding the shortest gap between slots (supported range: 1–1,440 minutes). The runner rejects overlapping input windows. A file left behind after a producer outage cannot advance the feed merely because it is still within the general age limit. For a failed slot, a retry can receive a late delivery with in-window evidence; if observations were made after that slot, use the next scheduled slot. Clients without the option retain the existing maximum-age behavior.

Follow [Headlamp host setup](../../plugins/headlamp-fleet-efficiency/docs/operations.md#schedule-assessment-publication) to expose the feed and its `assessments-status.json` companion under the same authorization. The companion reports the last recorded attempt and outcome; a failure can update it without replacing the evidence. It does not contain input details. Headlamp polls the files; it never starts a job. Keep the archive and other directory contents out of public document roots.

## 3. Add a schedule and alerts

1. Use the same command and pinned advisor environment in your existing scheduler. For a daily pilot, choose a UTC slot after the evidence producer's expected finish; set a job timeout and prevent overlapping jobs. Pass `--slot` the original scheduled ISO 8601 UTC timestamp (for example `2026-10-29T11:00:00Z`), not the retry's start time. Use absolute paths if the scheduler does not set a working directory.
2. Before onboarding more clusters, run two cycles with genuinely fresh inputs. Then stop the producer but leave the scheduler running and the last input in place. Confirm the prior feed and its evaluation time do not change, the new attempt reports failure, and an alert reaches the team. Restore collection and replay the previously published original using its pinned engine version. Exercise denial against both routes. Headlamp warns when a newer recorded attempt failed or the published evaluation is older than `stale_after_hours` (default 26 hours for a daily pilot; set it to cadence plus grace). A publication clock is not a source observation clock. Keep scheduler alerts for jobs that never start, exit before recording status, or cannot write status. If the feed was written but its status could not be updated, the command exits `1` and reports that separately.
3. Keep the archive under the retention policy and monitor disk usage. The runner does not garbage-collect bundles. With `--slot`, a retry of the latest published slot recognizes the exact feed, restores its original companion status if needed, and does not create another run. If that slot has not been published, retrying may create a new run directory. Older jobs are refused once a newer slot starts, even if the newer attempt fails. Once a feed uses slots, invoke unslotted manual runs against a separate destination. Keep the private `.assessments.json.slot` state file with the feed and never serve it over HTTP. The local lock prevents simultaneous `assess-batch` writers; do not use the standalone publisher against the same active feed. After a crash, confirm the runner is stopped before removing only the empty `.assessments.json.lock` directory beside the feed.
4. Add clusters to the batch profile only after verifying their inputs and access. Keep one authorized audience and one tenant per feed. Each endpoint exposes all of its records to authorized readers; split feeds by audience and never rely on browser filters for access control. Each feed is capped at 32 clusters and 4 MiB. No records are silently dropped. To suspend, disable the scheduler and withdraw the feed route if its data must no longer be shared.

### Optional: publish mixed-age results

Set `"allow_mixed_age": true` in the batch profile and pass `--slot` to publish the targets that completed an evaluation even when another target's evidence cannot be read or admitted. Headlamp marks the failed target **Prior results** when the previous verified feed contains the same cluster ID and fingerprint. Otherwise it lists the target as failed with no published assessment. Retained results keep their original evaluation window and never count as a successful assessment for the current slot. If every target fails, a cluster profile cannot establish the expected scope, or feed publication itself fails, the whole feed remains unchanged. Do not copy a feed between audiences; a manually restored feed with no matching protected slot state is not eligible as a source of retained results.

This is the saved-fragment path for an existing scheduler. It does not configure a managed job, deploy a Headlamp host, automate evidence collection, or provide a billing or Grafana datasource.

### Rehearse without a cluster

From a developer checkout with the documented dev and Kubernetes extras, run `python -m pytest tests/test_headlamp_publication.py -k scheduled_input_window`. The fictional producer stages two fresh pairs of inventory exports, goes offline while the last file remains, then recovers. The test verifies both feed preservation and replay from the original bundle. It does not validate customer identity, delivery networks, external alerting or either UI host.

### Recover or suspend the workflow

1. Compare the producer's latest source observation with the recorded attempt, the feed's evaluation time and the next expected slot. If the scheduler never ran or status could not be written, use the scheduler alert and logs; the old feed alone cannot identify the cause. Examine protected operator logs, not raw evidence on the dashboard.
2. Restore the authorized delivery path and verify the input's source clocks and fingerprint. Retry the original slot only with evidence from that slot's window; otherwise use the next scheduled slot. Do not replace the status, feed or watermark by hand.
3. To verify an older result after restore or upgrade, use the matching pinned runner and replay the manifest-backed original into a **separate protected destination**. Compare it with the original projection; this is a replay, not a current run. To suspend or retire the deployment, stop producer and scheduler jobs, revoke publishing and viewer access as appropriate, and apply the customer's archive retention policy.
