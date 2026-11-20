"""Evaluate one approved roster of saved, fresh fragments without source access."""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from typing import Annotated, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from aks_fleet_efficiency.artifacts import (
    MAXIMUM_INPUT_BYTES,
    read_model,
    write_assessment_artifacts,
)
from aks_fleet_efficiency.assessment import (
    AssessmentFragments,
    OfflineAssessment,
    _validate_bindings,
    assess_fragments,
)
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.config import OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.models import (
    AzureInventorySnapshot,
    CollectionStatus,
    KubernetesMetadataSnapshot,
    UtcDatetime,
)
from aks_fleet_efficiency.reporting.headlamp import (
    MAX_BYTES,
    MAX_CLUSTERS,
    render_feed,
    replace_feed_file,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class BatchTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: Path
    fragments: Path
    cluster_uid: Annotated[str, Field(min_length=1, max_length=256)]


class BatchProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    targets: Annotated[list[BatchTarget], Field(min_length=1, max_length=MAX_CLUSTERS)]
    stale_after_hours: Annotated[int, Field(strict=True, ge=1, le=720)] = 26
    allow_mixed_age: Annotated[bool, Field(strict=True)] = False
    slot_input_window_minutes: Annotated[int, Field(strict=True, ge=1, le=1440)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class SlotPublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: Digest
    partial: bool


class SlotState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    profile_digest: Digest
    slot: UtcDatetime
    attempted_at: UtcDatetime
    publication: SlotPublication | None = None
    prior_digest: Digest | None = None


class BatchInputError(ValueError):
    """An operator-safe input error, with no protected values."""


class FeedLockedError(OSError):
    """Another writer owns the feed lock or needs to be recovered."""


class BatchStatusError(OSError):
    """The batch outcome could not be published."""


def _write_status(
    path: Path, now: datetime, outcome: Literal["complete", "partial", "failed"], hours: int
) -> None:
    payload = {
        "schemaVersion": "1",
        "attemptedAt": now.isoformat(),
        "outcome": outcome,
        "staleAfterHours": hours,
    }
    try:
        replace_feed_file(path, (json.dumps(payload) + "\n").encode())
    except OSError as error:
        raise BatchStatusError(
            "Assessment feed was published, but run status could not be updated."
            if outcome != "failed"
            else "Batch failed and run status could not be updated; check inputs and storage."
        ) from error


def _fresh(observed: datetime | None, now: datetime, maximum_hours: float) -> bool:
    return observed is not None and 0 <= (now - observed).total_seconds() <= maximum_hours * 3600


def _observations(fragments: AssessmentFragments) -> tuple[datetime | None, ...]:
    return (
        fragments.window_end,
        *(source.collection.source_observed_at for source in fragments.azure),
        fragments.kubernetes[0].collection.source_observed_at,
    )


def _check_freshness(
    fragments: AssessmentFragments,
    config: OnboardingConfig,
    *,
    now: datetime,
    input_window: tuple[datetime, timedelta] | None,
    index: int,
) -> None:
    clocks = _observations(fragments)
    hours = config.analysis.thresholds.maximum_evidence_age_hours
    if not all(_fresh(clock, now, hours) for clock in clocks):
        raise BatchInputError(f"Target {index}: input is stale, future-dated or missing clocks.")
    if input_window is not None:
        end, span = input_window
        if not all(clock is not None and timedelta(0) <= end - clock < span for clock in clocks):
            raise BatchInputError(
                f"Target {index}: evidence is outside the scheduled input window."
            )


def stage_assessment_input(
    batch_path: Path, inventory_path: Path, metadata_path: Path, *, now: datetime, slot: datetime
) -> None:
    """Stage a single target's exported inventory without contacting any source."""
    batch = read_model(batch_path, BatchProfile, maximum_bytes=64 * 1024)
    if len(batch.targets) != 1 or batch.slot_input_window_minutes is None:
        raise BatchInputError("Staging requires one batch target and a configured input window.")
    if now.utcoffset() is None or slot.utcoffset() is None or slot > now:
        raise BatchInputError("The schedule slot must be a timezone-aware time no later than now.")
    target = batch.targets[0]
    base = batch_path.absolute().parent
    config_path, output = base / target.config, base / target.fragments
    paths = (batch_path, config_path, inventory_path, metadata_path)
    if (
        output.suffix != ".json"
        or output.resolve() in {path.resolve() for path in paths}
        or (output.parent / "manifest.json").exists()
        or any(
            item.is_symlink() or item.is_junction()
            for path in (*paths, output)
            for item in (path, *path.parents)
        )
    ):
        raise BatchInputError("Use a separate JSON staging destination outside archives and links.")
    config = load_onboarding_config(config_path)
    if config.scope.tenant_id != batch.tenant_id or len(config.clusters) != 1:
        raise BatchInputError("Staging requires one cluster in the approved tenant.")
    catalog = load_catalog()
    if (
        config.analysis.mode != "baseline"
        or not config.analysis.packs
        or any(catalog.pack(pack).evidence_kind != "inventory" for pack in config.analysis.packs)
    ):
        raise BatchInputError("Staging requires explicitly selected inventory-only baseline packs.")

    inventory = read_model(inventory_path, AzureInventorySnapshot)
    metadata = read_model(metadata_path, KubernetesMetadataSnapshot)
    cluster_id = config.clusters[0].resource_id
    if (
        len(inventory.clusters) != 1
        or inventory.clusters[0].resource_id != cluster_id
        or metadata.cluster_uid != target.cluster_uid
        or metadata.cluster_resource_id != cluster_id
    ):
        raise BatchInputError("Staged input cluster scope or fingerprint does not match.")
    azure_at = inventory.collection.source_observed_at
    kube_at = metadata.collection.source_observed_at
    if (
        azure_at is None
        or kube_at is None
        or any(
            source.generated_at > now or source.collection.status != CollectionStatus.COMPLETE
            for source in (inventory, metadata)
        )
    ):
        raise BatchInputError("Staging requires complete exports with verified source clocks.")
    end = min(azure_at, kube_at)
    span = timedelta(minutes=batch.slot_input_window_minutes)
    slot = slot.astimezone(UTC)
    if not all(timedelta(0) <= slot - clock < span for clock in (azure_at, kube_at)):
        raise BatchInputError("Source evidence is outside the scheduled input window.")
    fragments = AssessmentFragments(
        schema_version="1.0",
        window_start=slot - span,
        window_end=end,
        azure=[inventory],
        kubernetes=[metadata],
    )
    _validate_bindings(fragments, config)
    _check_freshness(fragments, config, now=now, input_window=(slot, span), index=1)
    try:
        previous = read_model(output, AssessmentFragments)
    except FileNotFoundError:
        previous = None
    if previous is not None:
        _validate_bindings(previous, config)
        if (
            len(previous.azure) != 1
            or len(previous.kubernetes) != 1
            or previous.kubernetes[0].cluster_uid != target.cluster_uid
            or previous.metrics
            or previous.workload_assessments
            or previous.pool_intents
            or previous.existing_tool_observations
            or previous.startup_history
        ):
            raise BatchInputError("Existing staging data has a different scope or basis.")
        if any(
            prior is not None and (current is None or current < prior)
            for prior, current in zip(
                _observations(previous), _observations(fragments), strict=True
            )
        ):
            raise BatchInputError("Staging refused inputs older than the current delivery.")
    payload = (fragments.model_dump_json() + "\n").encode()
    if len(payload) > MAXIMUM_INPUT_BYTES:
        raise BatchInputError("Staged input exceeds the batch read limit.")
    replace_feed_file(output, payload)


def _feed_bytes(path: Path) -> bytes | None:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(data) > MAX_BYTES:
        raise BatchInputError("Existing feed exceeds the size limit.")
    return data


def _retain_clusters(data: bytes | None) -> dict[tuple[str, str], dict[str, object]]:
    if data is None:
        return {}
    feed = TypeAdapter(dict[str, object]).validate_json(data)
    result = {}
    for row in TypeAdapter(list[dict[str, object]]).validate_python(feed.get("clusters")):
        cluster_id, uid = row.get("id"), row.get("uid")
        if not isinstance(cluster_id, str) or not isinstance(uid, str):
            raise BatchInputError("Previously published cluster identity is invalid.")
        result[(cluster_id, uid)] = row
    return result


def _record_slot(path: Path, state: SlotState) -> None:
    replace_feed_file(path, (state.model_dump_json() + "\n").encode())


def _previous_slot(path: Path) -> SlotState | None:
    try:
        return read_model(path, SlotState, maximum_bytes=4096)
    except FileNotFoundError:
        return None
    except ValueError as error:
        raise BatchInputError("The protected scheduler state is invalid.") from error


def assess_batch(
    batch_path: Path, artifacts: Path, feed: Path, *, now: datetime, slot: datetime | None = None
) -> tuple[Path | None, bool]:
    try:
        batch = read_model(batch_path, BatchProfile, maximum_bytes=64 * 1024)
    except (OSError, ValueError) as error:
        raise BatchInputError(
            "Cannot read the batch profile; check its JSON and target list."
        ) from error
    base = batch_path.absolute().parent
    archive = artifacts.resolve()
    output = feed.resolve()
    status = output.with_name(f"{output.stem}-status.json")
    state_path = output.with_name(f".{output.name}.slot")
    inputs = {batch_path.resolve()}
    for target in batch.targets:
        inputs.update(((base / target.config).resolve(), (base / target.fragments).resolve()))
    if (
        feed.is_symlink()
        or status.is_symlink()
        or state_path.is_symlink()
        or output in inputs
        or status in inputs
        or state_path in inputs
        or output.is_relative_to(archive)
        or output.suffix != ".json"
        or output.stem.casefold().endswith("-status")
    ):
        raise BatchInputError(
            "Use a separate .json feed outside the archive and inputs, without a -status suffix."
        )
    if not archive.is_dir() or not output.parent.is_dir():
        raise OSError("The archive and feed parent must already exist.")
    if slot is not None and (slot.utcoffset() is None or slot > now):
        raise BatchInputError("The schedule slot must be a timezone-aware time no later than now.")
    if batch.allow_mixed_age and slot is None:
        raise BatchInputError("Mixed-age publication requires --slot.")
    input_window: tuple[datetime, timedelta] | None = None
    if batch.slot_input_window_minutes is not None:
        if slot is None:
            raise BatchInputError("The scheduled input window requires --slot.")
        input_window = (
            slot.astimezone(UTC),
            timedelta(minutes=batch.slot_input_window_minutes),
        )

    lock = output.with_name(f".{output.name}.lock")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise FeedLockedError from error
    try:
        previous = _previous_slot(state_path)
        if previous is not None and slot is None:
            raise BatchInputError(
                "This feed requires --slot; use a different feed for manual runs."
            )
        state = None
        retained = {}
        if slot is not None:
            data = _feed_bytes(output)
            digest = sha256(data).hexdigest() if data is not None else None
            prior_digest = None
            profile_digest = sha256(
                json.dumps([str(base.resolve()), str(archive), batch.model_dump_json()]).encode()
            ).hexdigest()
            if previous is not None:
                if previous.tenant_id != batch.tenant_id:
                    raise BatchInputError("The approved tenant does not match the scheduler state.")
                if slot < previous.slot or now < previous.attempted_at:
                    raise BatchInputError("This job is older than the recorded schedule state.")
                if (
                    slot > previous.slot
                    and input_window is not None
                    and input_window[0] - previous.slot < input_window[1]
                ):
                    raise BatchInputError("Scheduled input windows must not overlap.")
                if slot == previous.slot:
                    if previous.profile_digest != profile_digest:
                        raise BatchInputError("The batch profile changed within the same slot.")
                    saved = previous.publication
                    if saved is not None and digest == saved.digest:
                        _write_status(
                            status,
                            previous.attempted_at,
                            "partial" if saved.partial else "complete",
                            batch.stale_after_hours,
                        )
                        return None, saved.partial
                if digest is not None and (
                    digest == previous.prior_digest
                    or (previous.publication is not None and digest == previous.publication.digest)
                ):
                    prior_digest = digest
                    if batch.allow_mixed_age:
                        retained = _retain_clusters(data)
            state = SlotState(
                tenant_id=batch.tenant_id,
                profile_digest=profile_digest,
                slot=slot,
                attempted_at=now,
                prior_digest=prior_digest,
            )
            _record_slot(state_path, state)
        return _publish_batch(
            batch,
            archive,
            base,
            output,
            status,
            now,
            state_path,
            state,
            retained,
            input_window=input_window,
        )
    finally:
        lock.rmdir()


def _publish_batch(
    batch: BatchProfile,
    archive: Path,
    base: Path,
    output: Path,
    status: Path,
    now: datetime,
    state_path: Path,
    state: SlotState | None,
    previous_clusters: dict[tuple[str, str], dict[str, object]],
    *,
    input_window: tuple[datetime, timedelta] | None,
) -> tuple[Path, bool]:
    try:
        run = Path(mkdtemp(prefix="run-", dir=archive))
        bundles: list[Path] = []
        seen: set[str] = set()
        retained: dict[str, dict[str, object]] = {}
        failed: list[str] = []
        partial = False
        for index, target in enumerate(batch.targets, start=1):
            try:
                config = load_onboarding_config(base / target.config)
            except (OSError, ValueError, yaml.YAMLError) as error:
                raise BatchInputError(f"Target {index}: cannot read cluster profile.") from error
            if config.scope.tenant_id != batch.tenant_id or len(config.clusters) != 1:
                raise BatchInputError(
                    f"Target {index}: expected one cluster in the approved tenant."
                )
            cluster_id = config.clusters[0].resource_id
            if cluster_id in seen:
                raise BatchInputError(f"Target {index}: duplicate cluster in the batch.")
            seen.add(cluster_id)
            try:
                fragments, result = _assess_target(
                    base, target, config, index, now, input_window=input_window
                )
            except BatchInputError:
                if not batch.allow_mixed_age:
                    raise
                failed.append(cluster_id)
                old = previous_clusters.get((cluster_id, target.cluster_uid))
                if old is not None:
                    retained[cluster_id] = old
                continue
            bundle = run / f"cluster-{index:02d}"
            write_assessment_artifacts(bundle, fragments, result, config.analysis)
            bundles.append(bundle)
            partial |= result.status == "partial"
        if not bundles:
            raise BatchInputError(
                "No current cluster assessment succeeded; retained the prior feed."
            )
        partial |= bool(failed)
        payload = render_feed(bundles, batch.tenant_id, retained=retained, failed=failed)
        if state is not None:
            state.publication = SlotPublication(digest=sha256(payload).hexdigest(), partial=partial)
            _record_slot(state_path, state)
        replace_feed_file(output, payload)
    except OSError, ValueError:
        _write_status(status, now, "failed", batch.stale_after_hours)
        raise
    else:
        _write_status(status, now, "partial" if partial else "complete", batch.stale_after_hours)
    return run, partial


def _assess_target(
    base: Path,
    target: BatchTarget,
    config: OnboardingConfig,
    index: int,
    now: datetime,
    *,
    input_window: tuple[datetime, timedelta] | None,
) -> tuple[AssessmentFragments, OfflineAssessment]:
    try:
        fragments = read_model(base / target.fragments, AssessmentFragments)
    except (OSError, ValueError) as error:
        raise BatchInputError(f"Target {index}: cannot read fragments.") from error
    cluster_id = config.clusters[0].resource_id
    if (
        len(fragments.kubernetes) != 1
        or fragments.kubernetes[0].cluster_uid != target.cluster_uid
        or fragments.kubernetes[0].cluster_resource_id != cluster_id
        or {item.resource_id for source in fragments.azure for item in source.clusters}
        != {cluster_id}
        or any(
            set(source.collection.requested_scope) != {cluster_id} for source in fragments.metrics
        )
    ):
        raise BatchInputError(f"Target {index}: cluster scope or fingerprint does not match.")
    _check_freshness(fragments, config, now=now, input_window=input_window, index=index)
    try:
        return fragments, assess_fragments(fragments, config, as_of=now)
    except (ValueError, RuntimeError) as error:
        raise BatchInputError(f"Target {index}: assessment input was not admitted.") from error
