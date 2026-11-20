from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal, cast

from aks_fleet_efficiency.collectors.kubernetes_metadata import project_current_container_attempts
from aks_fleet_efficiency.models import (
    CollectionStatus,
    KubernetesMetadataSnapshot,
    PrometheusMetricsSnapshot,
    StartupHistoryEvidence,
    StartupLifecycleSample,
)


def _qualify_post_readiness_usage(evidence: StartupHistoryEvidence) -> StartupHistoryEvidence:
    from aks_fleet_efficiency.catalog import load_catalog
    from aks_fleet_efficiency.collectors.metric_queries import render_query

    usage = evidence.usage
    values: dict[str, float | None] = {
        "post_readiness_cpu_p95_mcpu": None,
        "post_readiness_memory_p99_mib": None,
    }
    issues = []
    transition = next(
        (sample.observed_at for sample in evidence.samples if sample.ready == "True"), None
    )
    catalog = load_catalog()
    if usage is None:
        return evidence.model_copy(
            update=values | {"usage_issues": ["post_readiness_usage_missing"]}
        )
    profile = usage.source_profile
    receipt = usage.collection
    if (
        evidence.status != "observed_transition"
        or transition is None
        or usage.tenant_id != evidence.tenant_id
        or profile is None
        or profile.identity != "historical"
        or catalog.sources.get(profile.id) != profile
        or receipt.collector != "prometheus"
        or receipt.status != CollectionStatus.COMPLETE
        or receipt.requested_scope != [evidence.cluster_resource_id]
        or receipt.completed_scope != [evidence.cluster_resource_id]
        or receipt.source_observed_at is None
        or receipt.completed_at > usage.generated_at
        or usage.generated_at > evidence.evaluated_at
        or (evidence.evaluated_at - receipt.source_observed_at).total_seconds()
        > evidence.maximum_source_age_seconds
        or usage.query_start <= transition
        or usage.query_end > evidence.window_end
        or (evidence.evaluated_at - usage.query_end).total_seconds()
        > evidence.maximum_source_age_seconds
        or (usage.query_start - evidence.window_start).total_seconds() % evidence.step_seconds
        or (usage.query_end - usage.query_start).total_seconds() % usage.step_seconds
    ):
        return evidence.model_copy(
            update=values | {"usage_issues": ["post_readiness_window_or_source_unqualified"]}
        )
    for metric, statistic, unit, field in (
        ("cpu_usage", "p95", "mCPU", "post_readiness_cpu_p95_mcpu"),
        ("memory_usage", "p99", "MiB", "post_readiness_memory_p99_mib"),
    ):
        matches = [item for item in usage.observations if item.metric == metric]
        if len(matches) != 1:
            issues.append(f"{metric}_missing_or_ambiguous")
            continue
        observation = matches[0]
        entity, quality, asset = observation.entity, observation.quality, catalog.queries[metric]
        fields = ("cluster_resource_id", "namespace", "workload_kind", "workload", "container")
        labels = {
            profile.labels[name]: str(getattr(entity, name))
            for name in fields
            if name in profile.labels
        }
        labels.update(workload_uid=str(entity.workload_uid), pod_uid=str(entity.pod_uid))
        value = getattr(observation, statistic)
        expected_count = (
            int((usage.query_end - usage.query_start).total_seconds() / usage.step_seconds) + 1
        )
        if (
            entity.kind != "container"
            or (
                entity.cluster_resource_id,
                entity.namespace,
                entity.workload_uid,
                entity.pod_uid,
                entity.container,
            )
            != (
                evidence.cluster_resource_id,
                evidence.namespace,
                evidence.workload_uid,
                evidence.pod_uid,
                evidence.container,
            )
            or observation.issues
            or value is None
            or value < 0
            or quality.source != usage.source_name
            or quality.unit != unit
            or quality.query_version != usage.query_version
            or quality.query_asset_version != asset.version
            or len(labels) != 7
            or quality.query_expression
            != render_query(asset.expression, labels, usage.step_seconds)
            or quality.window.coverage_ratio != 1
            or quality.window.sample_count != expected_count
            or quality.observed_at > usage.generated_at
            or observation.latest_sample_at != usage.query_end
            or quality.minimum is None
            or quality.maximum is None
            or not quality.minimum <= value <= quality.maximum
            or (metric == "cpu_usage" and (usage.query_start - transition).total_seconds() < 300)
        ):
            issues.append(f"{metric}_unqualified")
            continue
        values[field] = value
    return evidence.model_copy(update=values | {"usage_issues": sorted(issues)})


def review_startup_history(
    evidence: StartupHistoryEvidence, *, as_of: datetime, maximum_source_age_seconds: int
) -> StartupHistoryEvidence:
    evidence = StartupHistoryEvidence.model_validate(evidence.model_dump())
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Startup review requires an aware evaluation clock")
    if type(maximum_source_age_seconds) is not int or maximum_source_age_seconds <= 0:
        raise ValueError("Startup review requires a positive integer source age policy")
    as_of = as_of.astimezone(UTC)
    duration = (evidence.window_end - evidence.window_start).total_seconds()
    if (
        duration <= 0
        or duration % evidence.step_seconds
        or duration / evidence.step_seconds >= 10_000
    ):
        raise ValueError("Startup history requires a bounded aligned observation window")
    samples = sorted(
        evidence.samples,
        key=lambda item: item.observed_at or item.observation.metadata_generated_at,
    )
    issues = [issue for sample in samples for issue in sample.issues]
    expected_count = int(duration / evidence.step_seconds) + 1
    times = [sample.observed_at for sample in samples]
    if len(samples) != expected_count or any(
        sample.observed_at is None
        or (sample.observed_at - evidence.window_start).total_seconds()
        != index * evidence.step_seconds
        for index, sample in enumerate(samples)
    ):
        issues.append("incomplete_lifecycle_grid")
    attempts = []
    versions: dict[str, tuple[object, ...]] = {}
    for sample in samples:
        observation = sample.observation
        if (
            observation.tenant_id,
            observation.cluster_resource_id,
            observation.cluster_uid,
            observation.namespace_uid,
            observation.namespace,
            observation.workload_uid,
            observation.pod_uid,
        ) != (
            evidence.tenant_id,
            evidence.cluster_resource_id,
            evidence.cluster_uid,
            evidence.namespace_uid,
            evidence.namespace,
            evidence.workload_uid,
            evidence.pod_uid,
        ):
            raise ValueError("Startup history requires one exact original lifecycle identity")
        matches = [item for item in observation.containers if item.name == evidence.container]
        if len(matches) != 1:
            raise ValueError("Startup history requires one exact regular container")
        attempt = matches[0]
        attempts.append((attempt.container_id_digest, attempt.restart_count, attempt.started_at))
        if (
            attempt.state != "running"
            or None in attempts[-1]
            or observation.pod_created_at is None
            or observation.pod_resource_version is None
            or sample.ready == "Unknown"
        ):
            issues.append("unknown_lifecycle_observation")
        version = observation.pod_resource_version
        facts = (sample.ready, observation.pod_created_at, *attempts[-1])
        if version is not None:
            if version in versions and versions[version] != facts:
                raise ValueError(
                    "One supplied Pod resource version has contradictory lifecycle facts"
                )
            versions[version] = facts
        receipt = observation.collection
        if receipt.status != CollectionStatus.COMPLETE:
            issues.append("incomplete_lifecycle_source")
        if sample.observed_at is None or sample.observed_at != receipt.source_observed_at:
            issues.append("lifecycle_source_clock_unknown")
        if observation.metadata_generated_at > as_of:
            issues.append("future_lifecycle_source")
        if sample.observed_at is not None and any(
            instant is not None and instant > sample.observed_at
            for instant in (observation.pod_created_at, attempt.started_at)
        ):
            issues.append("lifecycle_fields_after_source_clock")
    if (
        len(set(attempts)) != 1
        or len({sample.observation.pod_created_at for sample in samples}) != 1
    ):
        issues.append("changed_or_missing_container_attempt")
    if evidence.window_end > as_of:
        issues.append("future_lifecycle_window")
    elif (as_of - evidence.window_end).total_seconds() > maximum_source_age_seconds:
        issues.append("stale_lifecycle_window")
    transition = None
    status: Literal["observed_transition", "not_observed", "blocked"] = "blocked"
    if not issues:
        if samples[0].ready == "True":
            issues.append("left_censored_readiness")
        else:
            transition = next(
                (index for index in range(1, len(samples)) if samples[index].ready == "True"), None
            )
            if transition is not None and any(
                sample.ready != "True" for sample in samples[transition:]
            ):
                issues.append("readiness_changed_after_transition")
            else:
                status = "observed_transition" if transition is not None else "not_observed"
    lower = upper = None
    if status == "observed_transition" and transition is not None:
        created = samples[transition].observation.pod_created_at
        before, after = times[transition - 1], times[transition]
        if created is not None and before is not None and after is not None:
            lower, upper = (before - created).total_seconds(), (after - created).total_seconds()
    result = evidence.model_copy(
        update={
            "samples": samples,
            "status": status,
            "evaluated_at": as_of,
            "maximum_source_age_seconds": maximum_source_age_seconds,
            "pod_to_observed_ready_lower_seconds": lower,
            "pod_to_observed_ready_upper_seconds": upper,
            "post_readiness_cpu_p95_mcpu": None,
            "post_readiness_memory_p99_mib": None,
            "issues": sorted(set(issues)),
            "usage_issues": ["post_readiness_usage_missing"]
            if evidence.usage is None
            else ["usage_not_qualified"],
        }
    )
    return _qualify_post_readiness_usage(result)


def project_startup_history(
    frames: list[tuple[KubernetesMetadataSnapshot, dict[str, Any]]],
    *,
    container: str,
    window_start: datetime,
    window_end: datetime,
    step_seconds: int,
    as_of: datetime,
    maximum_source_age_seconds: int,
    usage: PrometheusMetricsSnapshot | None = None,
) -> StartupHistoryEvidence:
    if (
        not frames
        or len(frames) > 10_000
        or sum(len(metadata.resources) for metadata, _ in frames) > 100_000
    ):
        raise ValueError("Startup native history exceeds its bounded frame/object contract")
    samples = []
    for metadata, pod in frames:
        observation = project_current_container_attempts(metadata, pod)
        conditions = pod.get("status", {}).get("conditions")
        states = (
            [
                item.get("status")
                for item in conditions
                if isinstance(item, dict) and item.get("type") == "Ready"
            ]
            if isinstance(conditions, list)
            else []
        )
        ready = states[0] if len(states) == 1 and states[0] in ("True", "False") else "Unknown"
        samples.append(
            StartupLifecycleSample(
                observed_at=observation.collection.source_observed_at,
                metadata_digest=sha256(
                    json.dumps(
                        metadata.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
                observation=observation,
                ready=cast(Literal["True", "False", "Unknown"], ready),
                issues=["incomplete_lifecycle_lists"]
                if any(
                    metadata.api_availability.get(key) != "available"
                    or not metadata.resource_versions.get(key)
                    for key in ("v1/pods", "v1/namespaces")
                )
                else [],
            )
        )
    first = samples[0].observation
    if first.workload_uid is None:
        raise ValueError("Startup history requires exact workload ownership")
    result = review_startup_history(
        StartupHistoryEvidence(
            tenant_id=first.tenant_id,
            cluster_resource_id=first.cluster_resource_id,
            cluster_uid=first.cluster_uid,
            namespace=first.namespace,
            namespace_uid=first.namespace_uid,
            workload_uid=first.workload_uid,
            pod_uid=first.pod_uid,
            container=container,
            window_start=window_start,
            window_end=window_end,
            step_seconds=step_seconds,
            evaluated_at=as_of,
            maximum_source_age_seconds=maximum_source_age_seconds,
            samples=samples,
            usage=usage,
        ),
        as_of=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )
    if len(result.model_dump_json().encode()) > 32 * 1024 * 1024:
        raise ValueError("Startup history exceeds its output byte budget")
    return result
