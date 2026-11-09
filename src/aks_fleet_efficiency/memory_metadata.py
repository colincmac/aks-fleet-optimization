from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from math import isfinite

from pydantic import JsonValue

from aks_fleet_efficiency.models import (
    ContainerTerminationContext,
    KubernetesMetadataSnapshot,
    KubernetesObjectMetadata,
    PodMemoryAccounting,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.workload_normalization import _quantity


def _memory_request(container: JsonValue) -> float:
    if not isinstance(container, dict):
        raise ValueError("unsupported memory container")
    resources = container.get("resources")
    requests = resources.get("requests") if isinstance(resources, dict) else None
    if not isinstance(requests, dict) or "memory" not in requests:
        raise ValueError("explicit admitted memory request required")
    value = _quantity(requests["memory"], Decimal(1) / Decimal(1048576), "memory")
    if value is None:
        raise ValueError("unknown admitted memory request")
    return value


def _pod_accounting(
    pod: KubernetesObjectMetadata, result: PodMemoryAccounting
) -> PodMemoryAccounting:
    try:
        if pod.spec.get("resources"):
            raise ValueError("unsupported Pod-level resources")
        containers = pod.spec.get("containers")
        initializers = pod.spec.get("initContainers")
        overhead = pod.spec.get("overhead")
        if (
            not isinstance(containers, list)
            or not containers
            or not isinstance(initializers, list)
            or not isinstance(overhead, dict)
        ):
            raise ValueError("unknown Pod memory components")
        application = sum(_memory_request(item) for item in containers)
        sidecars = 0.0
        init_peak = 0.0
        for initializer in initializers:
            if not isinstance(initializer, dict):
                raise ValueError("invalid init container")
            restart = initializer.get("restartPolicy")
            if restart is not None and (not isinstance(restart, str) or restart != "Always"):
                raise ValueError("unsupported init restart policy")
            request = _memory_request(initializer)
            if restart == "Always":
                sidecars += request
                init_peak = max(init_peak, sidecars)
            else:
                init_peak = max(init_peak, request + sidecars)
        fixed = _quantity(overhead.get("memory"), Decimal(1) / Decimal(1048576), "Pod overhead")
        if "memory" in overhead and fixed is None:
            raise ValueError("unknown Pod overhead")
        fixed = 0.0 if fixed is None else fixed
        effective = max(application + sidecars, init_peak) + fixed
        if not isfinite(effective):
            raise ValueError("Pod memory total exceeds finite range")
        result.application_request_mib = application + sidecars
        result.init_peak_request_mib = init_peak
        result.overhead_mib = fixed
        result.effective_request_mib = effective
    except ValueError:
        result.issues.append("unsupported_or_unknown_effective_pod_memory")
    return result


def _memory_admission(metadata: KubernetesMetadataSnapshot, workload: WorkloadSnapshot) -> None:
    key = "v1/limitranges"
    workload.memory_admission_observed = metadata.api_availability.get(key) == "available" and bool(
        metadata.resource_versions.get(key)
    )
    ranges = sorted(
        [
            item
            for item in metadata.resources
            if item.kind == "LimitRange" and item.namespace == workload.namespace
        ],
        key=lambda item: item.uid,
    )
    if workload.memory_admission_observed:
        workload.memory_admission_digest = sha256(
            json.dumps(
                [
                    {"uid": item.uid, "namespace": item.namespace, "spec": item.spec}
                    for item in ranges
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    minima: list[float] = []
    maxima: list[float] = []
    ratios: list[float] = []
    for resource in ranges:
        try:
            limits = resource.spec.get("limits")
            if not isinstance(limits, list) or not limits:
                raise ValueError("explicit admission limits required")
            for item in limits:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("type"), str)
                    or item.get("type") not in {"Container", "Pod"}
                ):
                    raise ValueError("unsupported admission limit type")
                for field, values, scale in [
                    ("min", minima, Decimal(1) / Decimal(1048576)),
                    ("max", maxima, Decimal(1) / Decimal(1048576)),
                    ("maxLimitRequestRatio", ratios, Decimal(1)),
                ]:
                    bound = item.get(field)
                    if bound is None and field not in item:
                        continue
                    if not isinstance(bound, dict):
                        raise ValueError("unknown admission memory bound")
                    if "memory" not in bound:
                        continue
                    if item["type"] == "Pod":
                        raise ValueError("Pod-level admission memory is unsupported")
                    value = _quantity(bound["memory"], scale, "admission memory")
                    if value is None or (field == "maxLimitRequestRatio" and value <= 0):
                        raise ValueError("invalid admission memory bound")
                    values.append(value)
        except ValueError:
            workload.memory_admission_issues.append("unsupported_memory_admission")
    workload.memory_admission_minimum_mib = max(minima) if minima else None
    workload.memory_admission_maximum_mib = min(maxima) if maxima else None
    workload.memory_admission_limit_request_ratio = min(ratios) if ratios else None
    if minima and maxima and max(minima) > min(maxima):
        workload.memory_admission_issues.append("contradictory_memory_admission")
    workload.memory_admission_issues = sorted(set(workload.memory_admission_issues))


def normalize_memory_metadata(
    metadata: KubernetesMetadataSnapshot, workload: WorkloadSnapshot
) -> None:
    _memory_admission(metadata, workload)
    pods = sorted(
        [
            item
            for item in metadata.resources
            if item.kind == "Pod" and metadata.workload_bindings.get(item.uid) == workload.uid
        ],
        key=lambda item: item.uid,
    )
    for pod in pods:
        workload.pod_memory_accounting.append(
            _pod_accounting(
                pod, PodMemoryAccounting(pod_uid=pod.uid, observed_at=metadata.generated_at)
            )
        )
        statuses = pod.status.get("containerStatuses")
        if statuses is None:
            continue
        if not isinstance(statuses, list):
            workload.termination_issues.append("unsupported_termination_context")
            continue
        seen: set[str] = set()
        for status in statuses:
            try:
                if not isinstance(status, dict):
                    raise ValueError("invalid container status")
                name = status.get("name")
                if (
                    not isinstance(name, str)
                    or name in seen
                    or name not in {item.name for item in workload.containers}
                ):
                    raise ValueError("ambiguous termination container")
                seen.add(name)
                last = status.get("lastState")
                terminated = last.get("terminated") if isinstance(last, dict) else None
                if terminated is None:
                    continue
                if not isinstance(terminated, dict):
                    raise ValueError("invalid termination context")
                context = ContainerTerminationContext.model_validate(
                    {
                        "pod_uid": pod.uid,
                        "container": name,
                        "reason": terminated.get("reason"),
                        "exit_code": terminated.get("exitCode"),
                        "finished_at": terminated.get("finishedAt"),
                        "observed_at": metadata.generated_at,
                    }
                )
                if context.finished_at > context.observed_at:
                    raise ValueError("future termination context")
                workload.termination_context.append(context)
            except ValueError:
                workload.termination_issues.append("unsupported_termination_context")
    workload.termination_issues = sorted(set(workload.termination_issues))
