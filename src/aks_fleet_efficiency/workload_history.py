from __future__ import annotations

import json
from hashlib import sha256
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aks_fleet_efficiency.models import (
    AutoscalingState,
    KubernetesMetadataSnapshot,
    MetricObservation,
    NonEmptyString,
    PrometheusMetricsSnapshot,
    ResourceObservation,
    WorkloadSafetyPolicy,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.workload_normalization import WorkloadInventoryEvidence


class WorkloadAssessmentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    tenant_id: NonEmptyString
    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: NonEmptyString
    workload_kind: Literal["Deployment", "StatefulSet"]
    workload: NonEmptyString
    workload_uid: NonEmptyString
    pod_uids: list[NonEmptyString] = Field(min_length=1, max_length=10000)
    source_name: NonEmptyString
    history_reference: NonEmptyString
    hpa_uid: NonEmptyString | None = None
    safety_policy: WorkloadSafetyPolicy

    @model_validator(mode="after")
    def validate_members(self) -> WorkloadAssessmentBinding:
        if len(set(self.pod_uids)) != len(self.pod_uids):
            raise ValueError("historical membership must not contain duplicate Pod UIDs")
        return self

    @property
    def membership_digest(self) -> str:
        return sha256(
            json.dumps(
                {
                    "cluster_resource_id": self.cluster_resource_id,
                    "cluster_uid": self.cluster_uid,
                    "namespace_uid": self.namespace_uid,
                    "workload_uid": self.workload_uid,
                    "pod_uids": sorted(self.pod_uids),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


class WorkloadHistoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding: WorkloadAssessmentBinding
    observations: list[MetricObservation]


class WorkloadHistoryIssue(BaseModel):
    scope: str
    code: Literal[
        "missing-workload-assessment",
        "workload-history-identity-mismatch",
        "unsupported-workload-history",
        "workload-history-guardrail",
    ]


def usable_metric_summary(
    item: MetricObservation,
    fragment: PrometheusMetricsSnapshot,
    *,
    counter: bool = False,
) -> bool:
    quality = item.quality
    expected = ceil(
        (fragment.query_end - fragment.query_start).total_seconds() / fragment.step_seconds
    )
    values = [item.minimum, item.p50, item.p95, item.p99, item.maximum]
    latest = item.latest_sample_at
    return (
        not item.issues
        and all(value is not None and value >= 0 for value in values)
        and values == sorted(value for value in values if value is not None)
        and quality.minimum == item.minimum
        and quality.maximum == item.maximum
        and quality.source == fragment.source_name
        and quality.query_version == fragment.query_version
        and quality.window.start == fragment.query_start
        and quality.window.end == fragment.query_end
        and quality.step_seconds == fragment.step_seconds
        and fragment.query_end <= quality.observed_at <= fragment.generated_at
        and 0 < quality.window.sample_count <= expected
        and quality.window.coverage_ratio <= quality.window.sample_count / expected
        and latest is not None
        and (latest - fragment.query_start).total_seconds() % fragment.step_seconds == 0
        and (
            latest == fragment.query_end
            if counter
            else 0 < (fragment.query_end - latest).total_seconds() <= fragment.step_seconds
        )
    )


def _full_summary(
    item: MetricObservation | None,
    metrics: PrometheusMetricsSnapshot,
    unit: str,
    *,
    constant: float | None = None,
    counter: bool = False,
) -> bool:
    return (
        item is not None
        and usable_metric_summary(item, metrics, counter=counter)
        and item.quality.unit == unit
        and item.quality.window.coverage_ratio == 1
        and (constant is None or item.minimum == item.maximum == constant)
    )


def _valid_counter(item: MetricObservation | None, metrics: PrometheusMetricsSnapshot) -> bool:
    return (
        _full_summary(item, metrics, "events", counter=True)
        and item is not None
        and item.total is not None
        and item.total.is_integer()
        and item.minimum is not None
        and item.maximum is not None
        and max(item.maximum, item.minimum * item.quality.window.sample_count)
        <= item.total
        <= item.maximum * item.quality.window.sample_count
    )


def _current_absence(
    metadata: KubernetesMetadataSnapshot, key: str, kind: str, namespace: str
) -> bool:
    state = metadata.api_availability.get(key)
    return (
        state in {"absent", "available"}
        and (state == "absent" or bool(metadata.resource_versions.get(key)))
        and not any(
            resource.kind == kind and resource.namespace == namespace
            for resource in metadata.resources
        )
    )


def _current_autoscalers_absent(metadata: KubernetesMetadataSnapshot, namespace: str) -> bool:
    return all(
        _current_absence(metadata, key, kind, namespace)
        for key, kind in [
            ("autoscaling/v2/horizontalpodautoscalers", "HorizontalPodAutoscaler"),
            ("autoscaling.k8s.io/v1/verticalpodautoscalers", "VerticalPodAutoscaler"),
            ("keda.sh/v1alpha1/scaledobjects", "ScaledObject"),
            ("keda.sh/v1alpha1/scaledjobs", "ScaledJob"),
        ]
    )


def _history_observations(
    binding: WorkloadAssessmentBinding,
    metrics: PrometheusMetricsSnapshot,
    workload: WorkloadSnapshot,
) -> list[MetricObservation] | None:
    relevant = [
        item
        for item in metrics.observations
        if item.entity.cluster_resource_id == binding.cluster_resource_id
        and item.entity.kind != "hpa"
        and (
            item.entity.workload_uid == binding.workload_uid
            or (
                item.entity.namespace == binding.namespace
                and item.entity.workload == binding.workload
                and item.entity.workload_kind == binding.workload_kind
            )
        )
    ]
    for item in relevant:
        entity = item.entity
        if (
            entity.cluster_resource_id != binding.cluster_resource_id
            or entity.namespace != binding.namespace
            or entity.workload != binding.workload
            or entity.workload_uid != binding.workload_uid
            or entity.workload_kind != binding.workload_kind
            or entity.kind not in {"container", "workload", "workload_container"}
            or (
                entity.kind == "container"
                and (
                    entity.pod_uid not in binding.pod_uids
                    or entity.container not in {container.name for container in workload.containers}
                )
            )
            or (
                entity.kind == "workload_container"
                and (
                    entity.membership_digest != binding.membership_digest
                    or entity.container not in {container.name for container in workload.containers}
                )
            )
            or (
                entity.kind == "workload"
                and (entity.pod_uid is not None or entity.container is not None)
            )
        ):
            return None
    return relevant


def _stable_controller_history(
    workload: WorkloadSnapshot,
    observations: list[MetricObservation],
    metrics: PrometheusMetricsSnapshot,
    *,
    envelope: bool,
) -> list[MetricObservation] | None:
    consumed: list[MetricObservation] = []
    histories = {item.metric: item for item in observations if item.entity.kind == "workload"}
    for name, value, unit in [
        ("desired_replicas", workload.replicas, "pods"),
        ("available_replicas", workload.replicas, "pods"),
        ("hpa_present", 0, "boolean"),
        ("keda_present", 0, "boolean"),
        ("vpa_present", 0, "boolean"),
    ]:
        item = histories.get(name)
        if not _full_summary(item, metrics, unit, constant=value):
            return None
        assert item is not None
        consumed.append(item)
    if envelope:
        observed = histories.get("observed_replicas")
        if not _full_summary(observed, metrics, "pods", constant=workload.replicas):
            return None
        assert observed is not None
        consumed.append(observed)
    return consumed


def _map_history(
    workload: WorkloadSnapshot,
    observations: list[MetricObservation],
    metrics: PrometheusMetricsSnapshot,
    *,
    envelope: bool,
) -> tuple[dict[str, ResourceObservation] | None, list[MetricObservation]]:
    consumed = _stable_controller_history(workload, observations, metrics, envelope=envelope)
    if consumed is None:
        return None, []
    mapped: dict[str, ResourceObservation] = {}
    for container in workload.containers:
        items = {
            item.metric: item
            for item in observations
            if item.entity.kind == ("workload_container" if envelope else "container")
            and item.entity.container == container.name
        }
        request = items.get("replica_cpu_request_min" if envelope else "cpu_request")
        request_max = items.get("replica_cpu_request_max") if envelope else request
        usage = items.get("replica_cpu_envelope" if envelope else "cpu_usage")
        throttle = items.get("replica_cpu_throttling" if envelope else "cpu_throttling")
        oom = items.get("replica_oom_events" if envelope else "oom_events")
        current = container.resources.request_cpu_mcores
        if (
            not container.resources.cpu_request_observed
            or current is None
            or current <= 0
            or not _full_summary(request, metrics, "mCPU", constant=current)
            or not _full_summary(request_max, metrics, "mCPU", constant=current)
            or not _full_summary(usage, metrics, "mCPU")
            or not _full_summary(throttle, metrics, "ratio")
            or not _full_summary(oom, metrics, "events", constant=0, counter=True)
            or oom is None
            or oom.total != 0
            or throttle is None
            or throttle.maximum is None
            or throttle.maximum > 1
        ):
            return None, []
        assert request is not None and usage is not None
        resources = container.resources.model_copy(deep=True)
        resources.cpu_observation_basis = "replica-envelope" if envelope else "pod"
        resources.usage_cpu_p50_mcores = usage.p50
        resources.usage_cpu_p95_mcores = usage.p95
        resources.usage_cpu_p99_mcores = usage.p99
        resources.cpu_throttled_ratio = throttle.maximum
        resources.memory_oom_events = 0
        resources.metric_quality.update(
            {
                name: item.quality.model_copy(deep=True)
                for name, item in [
                    ("usage_cpu_p95_mcores", usage),
                    ("usage_cpu_p99_mcores", usage),
                    ("cpu_throttled_ratio", throttle),
                    ("memory_oom_events", oom),
                ]
            }
        )
        mapped[container.name] = resources
        consumed.extend([request, usage, throttle, oom])
        if envelope:
            assert request_max is not None
            consumed.append(request_max)
    return mapped, consumed


def _map_memory_evidence(
    workload: WorkloadSnapshot,
    observations: list[MetricObservation],
    metrics: PrometheusMetricsSnapshot,
    *,
    envelope: bool,
) -> list[MetricObservation]:
    consumed: list[MetricObservation] = []
    eviction = [
        item
        for item in observations
        if item.entity.kind == "workload" and item.metric == "evictions"
    ]
    if len(eviction) == 1 and _valid_counter(eviction[0], metrics):
        item = eviction[0]
        assert item.total is not None
        workload.eviction_events = int(item.total)
        workload.eviction_quality = item.quality.model_copy(deep=True)
        workload.eviction_quality.minimum = workload.eviction_quality.maximum = item.total
        consumed.append(item)
    for container in workload.containers:
        kind = "workload_container" if envelope else "container"
        memory = [
            item
            for item in observations
            if item.entity.kind == kind
            and item.entity.container == container.name
            and item.metric == ("replica_memory_envelope" if envelope else "memory_usage")
        ]
        if len(memory) == 1 and _full_summary(memory[0], metrics, "MiB"):
            item = memory[0]
            container.resources.usage_memory_p50_mib = item.p50
            container.resources.usage_memory_p95_mib = item.p95
            container.resources.usage_memory_p99_mib = item.p99
            for name in ["usage_memory_p95_mib", "usage_memory_p99_mib"]:
                container.resources.metric_quality[name] = item.quality.model_copy(deep=True)
            consumed.append(item)
        if not envelope:
            total = [
                item
                for item in observations
                if item.entity.kind == kind
                and item.entity.container == container.name
                and item.metric == "memory_total_usage"
            ]
            if len(total) == 1 and _full_summary(total[0], metrics, "MiB"):
                item = total[0]
                container.resources.total_memory_usage_p99_mib = item.p99
                container.resources.metric_quality["total_memory_usage_p99_mib"] = (
                    item.quality.model_copy(deep=True)
                )
                consumed.append(item)
        for metric, field, current, observed in [
            (
                "memory_request",
                "request_memory_mib",
                container.resources.request_memory_mib,
                container.resources.memory_request_observed,
            ),
            (
                "memory_limit",
                "limit_memory_mib",
                container.resources.limit_memory_mib,
                container.resources.memory_limit_observed,
            ),
        ]:
            names = [f"replica_{metric}_min", f"replica_{metric}_max"] if envelope else [metric]
            candidates = [
                item
                for item in observations
                if item.entity.kind == kind
                and item.entity.container == container.name
                and item.metric in names
            ]
            if (
                observed
                and current is not None
                and len(candidates) == len(names)
                and {item.metric for item in candidates} == set(names)
                and all(
                    _full_summary(item, metrics, "MiB", constant=current) for item in candidates
                )
            ):
                container.resources.metric_quality[field] = candidates[0].quality.model_copy(
                    deep=True
                )
                consumed.extend(candidates)
        counters = [("replica_oom_events" if envelope else "oom_events", "memory_oom_events")]
        counters.append(("replica_restarts" if envelope else "restarts", "restart_events"))
        for metric, field in counters:
            candidates = [
                item
                for item in observations
                if item.entity.kind == kind
                and item.entity.container == container.name
                and item.metric == metric
            ]
            if len(candidates) != 1:
                continue
            item = candidates[0]
            if not _valid_counter(item, metrics):
                continue
            assert item.total is not None
            if field == "memory_oom_events":
                container.resources.memory_oom_events = int(item.total)
            else:
                container.resources.restart_events = int(item.total)
            quality = item.quality.model_copy(deep=True)
            quality.minimum = quality.maximum = item.total
            container.resources.metric_quality[field] = quality
            consumed.append(item)
    return consumed


def normalize_workload_history(
    metadata: KubernetesMetadataSnapshot,
    metrics: PrometheusMetricsSnapshot | None,
    workloads: list[WorkloadSnapshot],
    current_evidence: list[WorkloadInventoryEvidence],
    bindings: list[WorkloadAssessmentBinding],
) -> tuple[list[WorkloadHistoryEvidence], list[WorkloadHistoryIssue]]:
    evidence: list[WorkloadHistoryEvidence] = []
    issues: list[WorkloadHistoryIssue] = []
    by_uid = {item.workload_uid: item for item in bindings}
    seen: set[str] = set()
    for workload in workloads:
        scope = f"{metadata.cluster_resource_id}/workloads/{workload.uid}"
        binding = by_uid.get(workload.uid or "")
        if binding is None:
            issues.append(WorkloadHistoryIssue(scope=scope, code="missing-workload-assessment"))
            continue
        seen.add(binding.workload_uid)
        current = [item for item in current_evidence if item.workload_uid == workload.uid]
        if (
            not current
            or binding.cluster_uid != metadata.cluster_uid
            or any(binding.namespace_uid != item.namespace_uid for item in current)
            or not {item.pod_uid for item in current} <= set(binding.pod_uids)
            or binding.namespace != workload.namespace
            or binding.workload != workload.name
            or binding.workload_kind != workload.kind
        ):
            issues.append(
                WorkloadHistoryIssue(scope=scope, code="workload-history-identity-mismatch")
            )
            continue
        pods = [
            resource
            for resource in metadata.resources
            if resource.uid in {item.pod_uid for item in current}
        ]
        if (
            metrics is None
            or metrics.source_name != binding.source_name
            or (metrics.query_end - metrics.query_start).total_seconds() % metrics.step_seconds != 0
            or binding.safety_policy.reviewed_window_start != metrics.query_start
            or binding.safety_policy.reviewed_window_end != metrics.query_end
        ):
            issues.append(WorkloadHistoryIssue(scope=scope, code="unsupported-workload-history"))
            continue
        observations = _history_observations(binding, metrics, workload)
        if observations is None:
            issues.append(
                WorkloadHistoryIssue(scope=scope, code="workload-history-identity-mismatch")
            )
            continue
        envelope = workload.replicas != 1 or len(binding.pod_uids) != 1
        memory_observations = _map_memory_evidence(
            workload, observations, metrics, envelope=envelope
        )
        if memory_observations:
            workload.safety_policy = binding.safety_policy.model_copy(deep=True)
            evidence.append(
                WorkloadHistoryEvidence(
                    binding=binding.model_copy(deep=True),
                    observations=[item.model_copy(deep=True) for item in memory_observations],
                )
            )
        if any(
            item.entity.kind == "hpa"
            and item.entity.cluster_resource_id == metadata.cluster_resource_id
            and item.entity.workload_uid == workload.uid
            for item in metrics.observations
        ):
            issues.append(WorkloadHistoryIssue(scope=scope, code="workload-history-guardrail"))
            continue
        if not _current_autoscalers_absent(metadata, binding.namespace) or any(
            pod.spec.get("initContainers") != []
            or pod.spec.get("overhead") != {}
            or bool(pod.spec.get("resources"))
            or "runtimeClassName" not in pod.spec
            or pod.spec["runtimeClassName"] is not None
            for pod in pods
        ):
            issues.append(WorkloadHistoryIssue(scope=scope, code="unsupported-workload-history"))
            continue
        if any(
            item.metric in {"oom_events", "replica_oom_events"}
            and item.total is not None
            and item.total > 0
            for item in observations
        ):
            issues.append(WorkloadHistoryIssue(scope=scope, code="workload-history-guardrail"))
            continue
        controllers = _stable_controller_history(workload, observations, metrics, envelope=envelope)
        if controllers is not None and memory_observations:
            for container in workload.containers:
                container.resources.memory_observation_basis = (
                    "replica-envelope" if envelope else "pod"
                )
                container.resources.memory_membership_digest = (
                    binding.membership_digest if envelope else None
                )
            workload.autoscaling = AutoscalingState(hpa=False, keda=False, vpa=False)
            evidence[-1].observations.extend(item.model_copy(deep=True) for item in controllers)
        mapped, consumed = _map_history(
            workload,
            observations,
            metrics,
            envelope=envelope,
        )
        if mapped is None:
            issues.append(WorkloadHistoryIssue(scope=scope, code="unsupported-workload-history"))
            continue
        for container in workload.containers:
            container.resources = mapped[container.name]
        workload.safety_policy = binding.safety_policy.model_copy(deep=True)
        workload.autoscaling = AutoscalingState(hpa=False, keda=False, vpa=False)
        if memory_observations:
            evidence[-1].observations.extend(
                item.model_copy(deep=True)
                for item in consumed
                if item not in evidence[-1].observations
            )
        else:
            evidence.append(
                WorkloadHistoryEvidence(
                    binding=binding.model_copy(deep=True),
                    observations=[item.model_copy(deep=True) for item in consumed],
                )
            )
    issues.extend(
        WorkloadHistoryIssue(
            scope=f"{metadata.cluster_resource_id}/workloads/{binding.workload_uid}",
            code="workload-history-identity-mismatch",
        )
        for binding in bindings
        if binding.workload_uid not in seen
    )
    return evidence, issues
