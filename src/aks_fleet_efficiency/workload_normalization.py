from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, DecimalException
from importlib import import_module
from math import isfinite
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from aks_fleet_efficiency.models import (
    ContainerSnapshot,
    KubernetesMetadataSnapshot,
    KubernetesObjectMetadata,
    QosClass,
    ResourceObservation,
    UtcDatetime,
    WorkloadSnapshot,
)


class WorkloadInventoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_resource_id: str
    namespace_uid: str
    workload_uid: str
    pod_uid: str
    observed_at: UtcDatetime
    current_only: Literal[True] = True


class WorkloadInventoryIssue(BaseModel):
    scope: str
    code: Literal[
        "unsupported-workload-evidence", "unknown-workload-request", "quantity-parser-unavailable"
    ]


class QuantityParserUnavailable(ValueError):
    pass


def _quantity(value: object, multiplier: Decimal, resource: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"unsupported {resource} quantity")
    try:
        parser = cast(
            Callable[[str], Decimal], import_module("kubernetes.utils.quantity").parse_quantity
        )
    except ImportError as error:
        raise QuantityParserUnavailable("install the optional Kubernetes extra") from error
    try:
        parsed = parser(value) * multiplier
        if not parsed.is_finite() or parsed < 0:
            raise ValueError(f"invalid {resource} quantity")
        result = float(parsed)
    except (DecimalException, OverflowError) as error:
        raise ValueError(f"invalid {resource} quantity") from error
    if not isfinite(result) or (parsed > 0 and result == 0):
        raise ValueError(f"{resource} quantity exceeds finite range")
    return result


def _cpu_quantity(value: object) -> float | None:
    return _quantity(value, Decimal(1000), "CPU")


def _memory_quantity(value: object) -> float | None:
    return _quantity(value, Decimal(1) / Decimal(1048576), "memory")


def _owner_matches(
    pod: KubernetesObjectMetadata,
    workload: KubernetesObjectMetadata,
    resources: dict[str, KubernetesObjectMetadata],
    metadata: KubernetesMetadataSnapshot,
) -> bool:
    current = pod
    visited: set[str] = set()
    while current.uid not in visited:
        visited.add(current.uid)
        references = [item for item in current.owner_references if item.get("controller") is True]
        if len(references) != 1:
            return False
        reference = references[0]
        parent_uid = reference.get("uid")
        parent = resources.get(parent_uid) if isinstance(parent_uid, str) else None
        if (
            parent is None
            or any(
                reference.get(field) != expected
                for field, expected in [
                    ("apiVersion", parent.api_version),
                    ("kind", parent.kind),
                    ("name", parent.name),
                ]
            )
            or parent.namespace != pod.namespace
        ):
            return False
        if parent.uid == workload.uid:
            return True
        if parent.kind != "ReplicaSet" or parent.api_version != "apps/v1":
            return False
        if metadata.api_availability.get(
            "apps/v1/replicasets"
        ) != "available" or not metadata.resource_versions.get("apps/v1/replicasets"):
            return False
        current = parent
    return False


def _containers(pod: KubernetesObjectMetadata) -> list[ContainerSnapshot]:
    raw = pod.spec.get("containers")
    if not isinstance(raw, list) or not raw:
        raise ValueError("missing admitted containers")
    result: list[ContainerSnapshot] = []
    names: set[str] = set()
    for container in raw:
        if not isinstance(container, dict):
            raise ValueError("invalid admitted container")
        name = container.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("invalid or duplicate container identity")
        names.add(name)
        resources = container.get("resources")
        requests = resources.get("requests") if isinstance(resources, dict) else None
        observed = isinstance(requests, dict)
        cpu = _cpu_quantity(requests.get("cpu")) if isinstance(requests, dict) else None
        memory = ResourceObservation(request_cpu_mcores=cpu, cpu_request_observed=observed)
        for key in ["requests", "limits"]:
            fields = resources.get(key) if isinstance(resources, dict) else None
            if not isinstance(fields, dict):
                continue
            try:
                amount = _memory_quantity(fields.get("memory"))
            except ValueError:
                continue
            if key == "requests":
                memory.request_memory_mib = amount
                memory.memory_request_observed = True
            else:
                memory.limit_memory_mib = amount
                memory.memory_limit_observed = True
        result.append(
            ContainerSnapshot(
                name=name,
                resources=memory,
            )
        )
    return result


def normalize_workload_inventory(
    metadata: KubernetesMetadataSnapshot,
) -> tuple[list[WorkloadSnapshot], list[WorkloadInventoryEvidence], list[WorkloadInventoryIssue]]:
    workloads: list[WorkloadSnapshot] = []
    evidence: list[WorkloadInventoryEvidence] = []
    issues: list[WorkloadInventoryIssue] = []
    resources = {resource.uid: resource for resource in metadata.resources}
    consumed_pods: set[str] = set()
    candidates = [
        resource
        for resource in metadata.resources
        if resource.kind
        in {
            "Deployment",
            "StatefulSet",
            "DaemonSet",
            "Job",
            "CronJob",
        }
    ]
    for workload in sorted(candidates, key=lambda item: item.uid):
        scope = f"{metadata.cluster_resource_id}/workloads/{workload.uid}"
        pods = [
            resource
            for resource in metadata.resources
            if resource.kind == "Pod"
            and metadata.workload_bindings.get(resource.uid) == workload.uid
        ]
        pods.sort(key=lambda item: item.uid)
        consumed_pods.update(pod.uid for pod in pods)
        namespaces = [
            resource
            for resource in metadata.resources
            if resource.kind == "Namespace" and resource.name == workload.namespace
        ]
        replicas = workload.spec.get("replicas")
        pdb_key = "policy/v1/poddisruptionbudgets"
        controller_key = {
            "Deployment": "apps/v1/deployments",
            "StatefulSet": "apps/v1/statefulsets",
        }.get(workload.kind, "unsupported")
        if (
            not metadata.cluster_uid
            or workload.kind not in {"Deployment", "StatefulSet"}
            or workload.api_version != "apps/v1"
            or not workload.namespace
            or len(namespaces) != 1
            or type(replicas) is not int
            or not 1 <= replicas <= 100
            or len(pods) != replicas
            or len({pod.name for pod in pods}) != len(pods)
            or any(
                pod.namespace != workload.namespace
                or pod.status.get("phase") != "Running"
                or not _owner_matches(pod, workload, resources, metadata)
                or pod.api_version != "v1"
                for pod in pods
            )
            or any(
                metadata.api_availability.get(key) != "available"
                or not metadata.resource_versions.get(key)
                for key in ["v1/namespaces", "v1/pods", controller_key, pdb_key]
            )
            or any(
                resource.kind == "PodDisruptionBudget" and resource.namespace == workload.namespace
                for resource in metadata.resources
            )
            or sum(
                resource.kind == workload.kind
                and resource.name == workload.name
                and resource.namespace == workload.namespace
                for resource in metadata.resources
            )
            != 1
        ):
            issues.append(WorkloadInventoryIssue(scope=scope, code="unsupported-workload-evidence"))
            continue
        try:
            pod_containers = [sorted(_containers(pod), key=lambda item: item.name) for pod in pods]
            containers = pod_containers[0]
            if any(items != containers for items in pod_containers[1:]):
                raise ValueError("replica container requests differ or are inconsistently observed")
        except QuantityParserUnavailable:
            issues.append(WorkloadInventoryIssue(scope=scope, code="quantity-parser-unavailable"))
            continue
        except ValueError:
            issues.append(WorkloadInventoryIssue(scope=scope, code="unsupported-workload-evidence"))
            continue
        if any(not container.resources.cpu_request_observed for container in containers):
            issues.append(WorkloadInventoryIssue(scope=scope, code="unknown-workload-request"))
        qos_classes: dict[str, QosClass] = {
            "Guaranteed": "Guaranteed",
            "Burstable": "Burstable",
            "BestEffort": "BestEffort",
        }
        qos = pods[0].status.get("qosClass")
        qos_class = (
            qos_classes.get(qos)
            if isinstance(qos, str) and all(pod.status.get("qosClass") == qos for pod in pods)
            else None
        )
        workloads.append(
            WorkloadSnapshot(
                kind=workload.kind,
                name=workload.name,
                uid=workload.uid,
                namespace=workload.namespace,
                replicas=replicas,
                disruption_budget_present=False,
                qos_class=qos_class,
                containers=containers,
            )
        )
        evidence.extend(
            WorkloadInventoryEvidence(
                cluster_resource_id=metadata.cluster_resource_id,
                namespace_uid=namespaces[0].uid,
                workload_uid=workload.uid,
                pod_uid=pod.uid,
                observed_at=metadata.generated_at,
            )
            for pod in pods
        )
    issues.extend(
        WorkloadInventoryIssue(
            scope=f"{metadata.cluster_resource_id}/pods/{resource.uid}",
            code="unsupported-workload-evidence",
        )
        for resource in metadata.resources
        if resource.kind == "Pod" and resource.uid not in consumed_pods
    )
    return workloads, evidence, issues
