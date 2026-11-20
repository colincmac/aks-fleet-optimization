from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aks_fleet_efficiency.memory_metadata import effective_pod_request
from aks_fleet_efficiency.models import (
    CollectionStatus,
    CollectorResult,
    ContainerProbeEvidence,
    DaemonSetCoverageEvidence,
    DaemonSetPodOverhead,
    KubernetesMetadataSnapshot,
    KubernetesObjectMetadata,
    NodeResourceEvidence,
    NonEmptyString,
    PodDisruptionBudgetEvidence,
    SchedulingConstraint,
    SchedulingInventory,
    SchedulingPodEvidence,
    TopologySpreadEvidence,
    UtcDatetime,
)
from aks_fleet_efficiency.workload_normalization import (
    _cpu_quantity,
    _memory_quantity,
    _owner_matches,
)

CONTROLLERS = {
    "Deployment": "apps/v1/deployments",
    "StatefulSet": "apps/v1/statefulsets",
    "DaemonSet": "apps/v1/daemonsets",
    "Job": "batch/v1/jobs",
}
MAXIMUM_PDB_SELECTOR_PAIRS = 100_000
MAXIMUM_PLACEMENT_PAIRS = 100_000
MAXIMUM_PLACEMENT_WORK = 1_000_000


class NodeReservationAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    node_uid: NonEmptyString
    node_name: NonEmptyString
    pod_uids: list[NonEmptyString]
    observed_cpu_request_mcpu: float | None = Field(default=None, ge=0)
    observed_memory_request_mib: float | None = Field(default=None, ge=0)
    observed_nonterminal_pod_count: int | None = Field(default=None, ge=0, strict=True)
    issues: list[NonEmptyString] = Field(default_factory=list)


class SchedulingCompletenessAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["sanitized-metadata-reservation-audit"] = "sanitized-metadata-reservation-audit"
    tenant_id: NonEmptyString
    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString
    metadata_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_generated_at: UtcDatetime
    evaluated_at: UtcDatetime
    maximum_source_age_seconds: int = Field(gt=0, strict=True)
    collection: CollectorResult
    fit_status: Literal["blocked"] = "blocked"
    unobserved_dimensions: list[NonEmptyString] = Field(
        default_factory=lambda: [
            "pod_os",
            "host_ports",
            "host_network",
            "scheduling_gates",
            "dra",
            "extended_resources",
            "hugepages",
            "node_conditions",
            "scheduler_configuration",
            "producer_field_completeness",
        ]
    )
    nodes: list[NodeReservationAudit]
    pending_pod_uids: list[NonEmptyString]
    unresolved_assignment_pod_uids: list[NonEmptyString]
    terminal_pod_uids: list[NonEmptyString]
    issues: list[NonEmptyString]


def audit_scheduling_completeness(
    metadata: KubernetesMetadataSnapshot,
    *,
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> SchedulingCompletenessAudit:
    return _audit_scheduling_completeness(
        metadata, as_of=as_of, maximum_source_age_seconds=maximum_source_age_seconds
    )


def _audit_scheduling_completeness(
    metadata: KubernetesMetadataSnapshot,
    *,
    as_of: datetime,
    maximum_source_age_seconds: int,
    pending_candidate_uid: str | None = None,
) -> SchedulingCompletenessAudit:
    from aks_fleet_efficiency.collectors.kubernetes_metadata import validate_metadata_projection

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Scheduling audit requires an aware evaluation clock")
    if (
        isinstance(maximum_source_age_seconds, bool)
        or not isinstance(maximum_source_age_seconds, int)
        or maximum_source_age_seconds <= 0
    ):
        raise ValueError("Scheduling audit requires a positive integer source age budget")
    as_of = as_of.astimezone(UTC)
    metadata = KubernetesMetadataSnapshot.model_validate(metadata.model_dump())
    validate_metadata_projection(metadata)
    fingerprints = [
        item.uid
        for item in metadata.resources
        if item.kind == "Namespace" and item.api_version == "v1" and item.name == "kube-system"
    ]
    if not metadata.cluster_uid or fingerprints != [metadata.cluster_uid]:
        raise ValueError("Scheduling audit requires the exact original namespace fingerprint")
    if len({item.uid for item in metadata.resources}) != len(metadata.resources):
        raise ValueError("Scheduling audit requires distinct object identities")
    identities = [
        (item.api_version, item.kind, item.namespace, item.name) for item in metadata.resources
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("Scheduling audit requires unambiguous current object names")
    receipt = metadata.collection
    if receipt.collector != "kubernetes-metadata" or receipt.requested_scope != [
        metadata.cluster_resource_id
    ]:
        raise ValueError("Scheduling audit requires the original exact-scoped metadata receipt")
    issues: list[str] = []
    if receipt.status != CollectionStatus.COMPLETE:
        issues.append("incomplete_metadata")
    for key in ["v1/namespaces", "v1/nodes", "v1/pods"]:
        if metadata.api_availability.get(key) != "available" or not metadata.resource_versions.get(
            key
        ):
            issues.append("incomplete_reservation_lists")
    if metadata.generated_at > as_of or receipt.completed_at > metadata.generated_at:
        issues.append("invalid_metadata_clock")
    source_time = receipt.source_observed_at
    if source_time is None:
        issues.append("metadata_source_clock_unknown")
    elif source_time > as_of:
        issues.append("future_metadata_source")
    elif (as_of - source_time).total_seconds() > maximum_source_age_seconds:
        issues.append("stale_metadata_source")
    inventory = normalize_scheduling(metadata)
    resources = {item.uid: item for item in metadata.resources}
    terminal = {
        pod.pod_uid for pod in inventory.pods if pod.resource_phase in {"Succeeded", "Failed"}
    }
    active = [pod for pod in inventory.pods if pod.pod_uid not in terminal]
    unresolved = sorted(pod.pod_uid for pod in active if pod.node_uid is None)
    # The NAP comparison excludes only its explicitly unbound pending candidate.
    if any(uid != pending_candidate_uid for uid in unresolved):
        issues.append("unresolved_pod_assignment")
    nodes: list[NodeReservationAudit] = []
    for node in inventory.node_resources:
        pods = [pod for pod in active if pod.node_uid == node.node_uid]
        node_issues = list(issues)
        if any(pod.resource_phase not in {"Running", "Pending"} for pod in pods):
            node_issues.append("unknown_pod_phase")
        cpu = [pod.effective_cpu_request_mcpu for pod in pods]
        memory = [pod.effective_memory_request_mib for pod in pods]
        budget_known = all(
            isinstance(resources[pod.pod_uid].spec.get("resources"), dict) for pod in pods
        )
        if not budget_known:
            node_issues.append("unknown_pod_resource_budget")
        if None in cpu:
            node_issues.append("unknown_cpu_request")
        if None in memory:
            node_issues.append("unknown_memory_request")
        phase_known = not issues and "unknown_pod_phase" not in node_issues
        nodes.append(
            NodeReservationAudit(
                node_uid=node.node_uid,
                node_name=node.node_name,
                pod_uids=sorted(pod.pod_uid for pod in pods),
                observed_cpu_request_mcpu=sum(value for value in cpu if value is not None)
                if phase_known and budget_known and None not in cpu
                else None,
                observed_memory_request_mib=sum(value for value in memory if value is not None)
                if phase_known and budget_known and None not in memory
                else None,
                observed_nonterminal_pod_count=len(pods) if phase_known else None,
                issues=sorted(set(node_issues)),
            )
        )
    return SchedulingCompletenessAudit(
        tenant_id=metadata.tenant_id,
        cluster_resource_id=metadata.cluster_resource_id,
        cluster_uid=metadata.cluster_uid,
        metadata_digest=sha256(
            json.dumps(
                metadata.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
        metadata_generated_at=metadata.generated_at,
        evaluated_at=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
        collection=receipt,
        nodes=nodes,
        pending_pod_uids=sorted(
            pod.pod_uid for pod in inventory.pods if pod.resource_phase == "Pending"
        ),
        unresolved_assignment_pod_uids=unresolved,
        terminal_pod_uids=sorted(terminal),
        issues=sorted(set(issues)),
    )


MAXIMUM_DAEMONSET_STATUS_OBJECTS = 100_000
MAXIMUM_DAEMONSET_STATUS_BYTES = 32 * 1024 * 1024


class DaemonSetStatusObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    daemonset_uid: NonEmptyString
    daemonset_name: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: NonEmptyString
    resource_version: NonEmptyString | None
    metadata_generation: int | None = Field(ge=1, le=2**63 - 1, strict=True)
    observed_generation: int | None = Field(ge=0, le=2**63 - 1, strict=True)
    generation_relation: Literal["equal", "lagging", "contradictory", "unknown"]
    desired_number_scheduled: int | None = Field(ge=0, le=2**31 - 1, strict=True)
    number_ready: int | None = Field(ge=0, le=2**31 - 1, strict=True)
    desired_node_membership: Literal["unknown"] = "unknown"
    disruption_feasibility: Literal["unknown"] = "unknown"
    issues: list[NonEmptyString]


class DaemonSetStatusProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    schema_version: Literal["1.0"] = "1.0"
    mapping_reference: Literal["kubernetes-apps-v1@v1.36.0"] = "kubernetes-apps-v1@v1.36.0"
    source_binding: Literal["unverified_supplied_native_objects"] = (
        "unverified_supplied_native_objects"
    )
    tenant_id: NonEmptyString
    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString
    metadata_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata_generated_at: UtcDatetime
    evaluated_at: UtcDatetime
    maximum_source_age_seconds: int = Field(gt=0, strict=True)
    collection: CollectorResult
    daemonsets: list[DaemonSetStatusObservation] = Field(max_length=100_000)
    source_issues: list[NonEmptyString]


def _daemonset_status_integer(value: object, *, minimum: int, maximum: int) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum
        else None
    )


def project_daemonset_status(
    metadata: KubernetesMetadataSnapshot,
    *,
    daemonsets: list[dict[str, Any]],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> DaemonSetStatusProjection:
    from aks_fleet_efficiency.collectors.kubernetes_metadata import (
        project_metadata,
        validate_metadata_projection,
    )

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("DaemonSet status requires an aware evaluation clock")
    if (
        isinstance(maximum_source_age_seconds, bool)
        or not isinstance(maximum_source_age_seconds, int)
        or maximum_source_age_seconds <= 0
    ):
        raise ValueError("DaemonSet status requires a positive integer source age budget")
    if max(len(daemonsets), len(metadata.resources)) > MAXIMUM_DAEMONSET_STATUS_OBJECTS:
        raise ValueError("DaemonSet status exceeds its object budget")
    as_of = as_of.astimezone(UTC)
    metadata = KubernetesMetadataSnapshot.model_validate(metadata.model_dump())
    validate_metadata_projection(metadata)
    fingerprints = [
        item.uid
        for item in metadata.resources
        if item.kind == "Namespace" and item.api_version == "v1" and item.name == "kube-system"
    ]
    identities = [
        (item.api_version, item.kind, item.namespace, item.name) for item in metadata.resources
    ]
    if (
        not metadata.cluster_uid
        or fingerprints != [metadata.cluster_uid]
        or len({item.uid for item in metadata.resources}) != len(metadata.resources)
        or len(set(identities)) != len(identities)
    ):
        raise ValueError("DaemonSet status requires exact unambiguous original identities")
    receipt = metadata.collection
    if receipt.collector != "kubernetes-metadata" or receipt.requested_scope != [
        metadata.cluster_resource_id
    ]:
        raise ValueError("DaemonSet status requires the original exact-scoped metadata receipt")
    source_issues = []
    if receipt.status != CollectionStatus.COMPLETE:
        source_issues.append("incomplete_metadata")
    if any(
        metadata.api_availability.get(key) != "available" or not metadata.resource_versions.get(key)
        for key in ("v1/namespaces", "apps/v1/daemonsets")
    ):
        source_issues.append("incomplete_daemonset_lists")
    if metadata.generated_at > as_of or receipt.completed_at > metadata.generated_at:
        source_issues.append("invalid_metadata_clock")
    source_time = receipt.source_observed_at
    if source_time is None:
        source_issues.append("metadata_source_clock_unknown")
    elif source_time > as_of or source_time > receipt.completed_at:
        source_issues.append("future_metadata_source")
    elif (as_of - source_time).total_seconds() > maximum_source_age_seconds:
        source_issues.append("stale_metadata_source")
    expected = {item.uid: item for item in metadata.resources if item.kind == "DaemonSet"}
    namespaces = {
        item.name: item.uid
        for item in metadata.resources
        if item.kind == "Namespace" and item.api_version == "v1"
    }
    seen: set[str] = set()
    observations = []
    for row in daemonsets:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("metadata"), dict)
            or row.get("apiVersion") != "apps/v1"
            or row.get("kind") != "DaemonSet"
        ):
            raise ValueError("DaemonSet status requires native apps/v1 DaemonSet identities")
        projected = project_metadata("apps/v1/daemonsets", row)
        namespace_uid = namespaces.get(projected.namespace or "")
        if (
            projected.uid in seen
            or expected.get(projected.uid) != projected
            or namespace_uid is None
        ):
            raise ValueError("DaemonSet status must match every original approved projection")
        seen.add(projected.uid)
        identity = row["metadata"]
        version = identity.get("resourceVersion")
        version = version if isinstance(version, str) and version.strip() else None
        status = row.get("status")
        status = status if isinstance(status, dict) else {}
        generation = _daemonset_status_integer(
            identity.get("generation"), minimum=1, maximum=2**63 - 1
        )
        observed = _daemonset_status_integer(
            status.get("observedGeneration"), minimum=0, maximum=2**63 - 1
        )
        desired = _daemonset_status_integer(
            status.get("desiredNumberScheduled"), minimum=0, maximum=2**31 - 1
        )
        ready = _daemonset_status_integer(status.get("numberReady"), minimum=0, maximum=2**31 - 1)
        issues = [
            issue
            for value, issue in [
                (version, "resource_version_unknown"),
                (generation, "metadata_generation_unknown"),
                (observed, "observed_generation_unknown"),
                (desired, "desired_count_unknown"),
                (ready, "ready_count_unknown"),
            ]
            if value is None
        ]
        relation: Literal["equal", "lagging", "contradictory", "unknown"] = "unknown"
        if version is not None and generation is not None and observed is not None:
            if observed == generation:
                relation = "equal"
            elif observed < generation:
                relation = "lagging"
                issues.append("controller_generation_lagging")
            else:
                relation = "contradictory"
                issues.append("observed_generation_ahead")
        observations.append(
            DaemonSetStatusObservation(
                daemonset_uid=projected.uid,
                daemonset_name=projected.name,
                namespace=projected.namespace or "",
                namespace_uid=namespace_uid,
                resource_version=version,
                metadata_generation=generation,
                observed_generation=observed,
                generation_relation=relation,
                desired_number_scheduled=desired,
                number_ready=ready,
                issues=sorted(issues),
            )
        )
    if seen != set(expected):
        raise ValueError("DaemonSet status requires the entire original roster without truncation")
    result = DaemonSetStatusProjection(
        tenant_id=metadata.tenant_id,
        cluster_resource_id=metadata.cluster_resource_id,
        cluster_uid=metadata.cluster_uid,
        metadata_digest=sha256(
            json.dumps(
                metadata.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest(),
        metadata_generated_at=metadata.generated_at,
        evaluated_at=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
        collection=receipt,
        daemonsets=sorted(observations, key=lambda item: item.daemonset_uid),
        source_issues=sorted(set(source_issues)),
    )
    if len(result.model_dump_json().encode("utf-8")) > MAXIMUM_DAEMONSET_STATUS_BYTES:
        raise ValueError("DaemonSet status exceeds its output byte budget")
    return result


ShapePresence = Literal["present", "absent", "unknown"]
ProtectionState = Literal["true", "false", "absent", "unknown"]


class ObjectDisruptionProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["Pod", "Node"]
    uid: NonEmptyString
    state: ProtectionState
    effectiveness: Literal["unknown"] = "unknown"


class DisruptionProtectionProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    annotation_key: Literal["karpenter.sh/do-not-disrupt"] = "karpenter.sh/do-not-disrupt"
    source_binding: Literal["unverified_supplied_native_objects"] = (
        "unverified_supplied_native_objects"
    )
    audit: SchedulingCompletenessAudit
    observations: list[ObjectDisruptionProtection] = Field(max_length=100_000)


def _disruption_protection_observation(
    row: dict[str, Any], projected: KubernetesObjectMetadata
) -> ObjectDisruptionProtection:
    annotations = row["metadata"].get("annotations")
    state: ProtectionState = "unknown"
    if isinstance(annotations, dict):
        if "karpenter.sh/do-not-disrupt" not in annotations:
            state = "absent"
        else:
            value = annotations["karpenter.sh/do-not-disrupt"]
            if isinstance(value, str) and value in {"true", "false"}:
                state = cast(ProtectionState, value)
    return ObjectDisruptionProtection(
        kind=cast(Literal["Pod", "Node"], projected.kind), uid=projected.uid, state=state
    )


def project_disruption_protection(
    metadata: KubernetesMetadataSnapshot,
    *,
    pods: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> DisruptionProtectionProjection:
    from aks_fleet_efficiency.collectors.kubernetes_metadata import project_metadata

    if len(pods) + len(nodes) > 100_000 or len(metadata.resources) > 100_000:
        raise ValueError("Protection projection exceeds its object budget")
    audit = audit_scheduling_completeness(
        metadata, as_of=as_of, maximum_source_age_seconds=maximum_source_age_seconds
    )
    observations = []
    for kind, resource, rows in [("Pod", "v1/pods", pods), ("Node", "v1/nodes", nodes)]:
        expected = {item.uid: item for item in metadata.resources if item.kind == kind}
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("metadata"), dict):
                raise ValueError("Protection projection requires original native identities")
            projected = project_metadata(resource, row)
            if projected.uid in seen or expected.get(projected.uid) != projected:
                raise ValueError("Protection rows must match every original approved projection")
            seen.add(projected.uid)
            observations.append(_disruption_protection_observation(row, projected))
        if seen != set(expected):
            raise ValueError("Protection projection requires all original Pods and Nodes")
    return DisruptionProtectionProjection(
        audit=audit, observations=sorted(observations, key=lambda item: (item.kind, item.uid))
    )


NodeCondition = Literal[
    "Ready", "MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable"
]
ShapeFeature = Literal[
    "host_network",
    "host_ports",
    "volumes",
    "resource_claims",
    "scheduling_gates",
    "node_selector",
    "affinity",
    "topology_spread",
    "tolerations",
    "priority_class",
    "runtime_class",
    "pod_resource_budget",
    "init_containers",
    "pod_overhead",
    "extended_resources",
    "hugepages",
    "ephemeral_storage",
    "taints",
    "cordoned",
]


class SchedulingPodShape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pod_uid: NonEmptyString
    resource_version: NonEmptyString | None
    os_name: Literal["linux", "windows", "unknown"]
    scheduler_name: NonEmptyString | None
    features: dict[ShapeFeature, ShapePresence]


class SchedulingNodeShape(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_uid: NonEmptyString
    resource_version: NonEmptyString | None
    os_name: Literal["linux", "windows", "unknown"]
    architecture: NonEmptyString | None
    allocatable_pod_slots: int | None = Field(ge=0, strict=True)
    features: dict[ShapeFeature, ShapePresence]
    conditions: dict[NodeCondition, Literal["True", "False", "Unknown"]]


class SchedulingShapeProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    mapping_reference: Literal["kubernetes-core-v1@v1.36.0"] = "kubernetes-core-v1@v1.36.0"
    source_binding: Literal["unverified_supplied_native_objects"] = (
        "unverified_supplied_native_objects"
    )
    audit: SchedulingCompletenessAudit
    pods: list[SchedulingPodShape] = Field(max_length=100_000)
    nodes: list[SchedulingNodeShape] = Field(max_length=100_000)


def _approved_projection_digest(projected: KubernetesObjectMetadata) -> str:
    return sha256(
        json.dumps(
            projected.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class SchedulingObjectObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["Pod", "Node"]
    uid: NonEmptyString
    approved_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    shape: SchedulingPodShape | SchedulingNodeShape
    protection: ObjectDisruptionProtection

    @model_validator(mode="after")
    def validate_identity(self) -> SchedulingObjectObservation:
        shape_uid = (
            self.shape.pod_uid
            if isinstance(self.shape, SchedulingPodShape)
            else self.shape.node_uid
        )
        shape_kind = "Pod" if isinstance(self.shape, SchedulingPodShape) else "Node"
        if (
            self.uid != shape_uid
            or self.kind != shape_kind
            or self.protection.uid != self.uid
            or self.protection.kind != self.kind
        ):
            raise ValueError("Scheduling observation identities must agree")
        return self


class SchedulingListObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: Literal["v1/namespaces", "v1/nodes", "v1/pods"]
    started_at: UtcDatetime
    completed_at: UtcDatetime
    source_observed_at: UtcDatetime | None = None
    successful_pages: int = Field(default=0, ge=0, strict=True)
    observed_objects: int = Field(default=0, ge=0, strict=True)
    failed_attempts: int = Field(default=0, ge=0, strict=True)
    resource_version: NonEmptyString | None = None
    pagination_complete: bool = Field(default=False, strict=True)


class SchedulingSourceCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    producer_version: Literal["1.0.0"] = "1.0.0"
    mapping_reference: Literal["kubernetes-core-v1@v1.36.0"] = "kubernetes-core-v1@v1.36.0"
    protection_annotation_key: Literal["karpenter.sh/do-not-disrupt"] = (
        "karpenter.sh/do-not-disrupt"
    )
    execution_binding: Literal["executed_injected_reader_unverified_source"] = (
        "executed_injected_reader_unverified_source"
    )
    scheduler_admission: Literal["unverified"] = "unverified"
    fit_status: Literal["blocked"] = "blocked"
    metadata: KubernetesMetadataSnapshot
    audit: SchedulingCompletenessAudit
    observations: list[SchedulingObjectObservation] = Field(max_length=100_000)
    lists: list[SchedulingListObservation] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_observation_bindings(self) -> SchedulingSourceCollection:
        metadata_digest = sha256(
            json.dumps(
                self.metadata.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if (
            (
                self.audit.tenant_id,
                self.audit.cluster_resource_id,
                self.audit.cluster_uid,
                self.audit.metadata_generated_at,
            )
            != (
                self.metadata.tenant_id,
                self.metadata.cluster_resource_id,
                self.metadata.cluster_uid,
                self.metadata.generated_at,
            )
            or self.audit.collection != self.metadata.collection
            or self.audit.metadata_digest != metadata_digest
        ):
            raise ValueError("Scheduling audit must bind to the exact original metadata")
        expected = {
            item.uid: item for item in self.metadata.resources if item.kind in {"Pod", "Node"}
        }
        if len({item.uid for item in self.observations}) != len(self.observations) or {
            item.uid for item in self.observations
        } != set(expected):
            raise ValueError("Scheduling observations require the exact retained Pod/Node roster")
        for item in self.observations:
            original = expected[item.uid]
            if (
                item.kind != original.kind
                or item.approved_projection_digest != _approved_projection_digest(original)
            ):
                raise ValueError("Scheduling observation does not bind to original metadata")
        if len({item.resource for item in self.lists}) != len(self.lists):
            raise ValueError("Scheduling list observations must be distinct")
        for listing in self.lists:
            if (
                listing.completed_at < listing.started_at
                or listing.started_at < self.metadata.collection.started_at
                or listing.completed_at > self.metadata.collection.completed_at
            ) or (
                listing.pagination_complete
                and (
                    listing.successful_pages == 0
                    or listing.resource_version
                    != self.metadata.resource_versions.get(listing.resource)
                    or listing.observed_objects
                    != sum(
                        item.kind
                        == {"v1/pods": "Pod", "v1/nodes": "Node", "v1/namespaces": "Namespace"}[
                            listing.resource
                        ]
                        for item in self.metadata.resources
                    )
                )
            ):
                raise ValueError("Scheduling list execution evidence is inconsistent")
        return self


ShapeDiagnosticStatus = Literal["within_initial_shape", "unsupported", "unknown"]
PodShapeIssue = Literal[
    "pod_os_unknown",
    "pod_os_unsupported",
    "scheduler_name_unknown",
    "scheduler_name_unsupported",
    "object_resource_version_unknown",
]
NodeShapeIssue = Literal[
    "node_os_unknown",
    "node_os_unsupported",
    "node_architecture_unknown",
    "pod_slots_unknown",
    "pod_slots_empty",
    "object_resource_version_unknown",
]


class SchedulingPodDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pod_uid: NonEmptyString
    status: ShapeDiagnosticStatus
    unsupported_features: list[ShapeFeature]
    unknown_features: list[ShapeFeature]
    issues: list[PodShapeIssue]


class SchedulingNodeDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_uid: NonEmptyString
    status: ShapeDiagnosticStatus
    unsupported_features: list[ShapeFeature]
    unknown_features: list[ShapeFeature]
    unsuitable_conditions: list[NodeCondition]
    unknown_conditions: list[NodeCondition]
    issues: list[NodeShapeIssue]


class SchedulingShapeDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["unverified-native-shape-review"] = "unverified-native-shape-review"
    fit_status: Literal["blocked"] = "blocked"
    admission_blockers: tuple[
        Literal["producer_completeness_unverified"],
        Literal["scheduler_configuration_unverified"],
    ] = ("producer_completeness_unverified", "scheduler_configuration_unverified")
    projection: SchedulingShapeProjection
    pods: list[SchedulingPodDiagnostic] = Field(max_length=100_000)
    nodes: list[SchedulingNodeDiagnostic] = Field(max_length=100_000)


class SchedulingResourceComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pod_uid: NonEmptyString
    node_uid: NonEmptyString
    status: Literal["satisfied", "unsatisfied", "blocked"]
    cpu_required_mcpu: float | None = Field(default=None, ge=0)
    memory_required_mib: float | None = Field(default=None, ge=0)
    pod_slots_required: Literal[1] = 1
    cpu_available_mcpu: float | None = None
    memory_available_mib: float | None = None
    pod_slots_available: int | None = Field(default=None, strict=True)
    issues: list[NonEmptyString]


class SchedulingResourceFragmentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pod_uid: NonEmptyString
    status: Literal["scattered_across_nodes", "not_observed", "unknown"]


class SchedulingConstraintCalculation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["supplied-current-three-resource-constraints"] = (
        "supplied-current-three-resource-constraints"
    )
    fit_status: Literal["blocked"] = "blocked"
    source_admission: Literal["unverified"] = "unverified"
    scheduler_admission: Literal["unverified"] = "unverified"
    simultaneous_placement: Literal["not_calculated"] = "not_calculated"
    removable_nodes: Literal["not_calculated"] = "not_calculated"
    diagnostics: SchedulingShapeDiagnostics
    pairs: list[SchedulingResourceComparison] = Field(max_length=100_000)
    fragmentation: list[SchedulingResourceFragmentation] = Field(max_length=100_000)


def _resource_fragmentation(
    pairs: list[SchedulingResourceComparison],
) -> list[SchedulingResourceFragmentation]:
    groups: dict[str, list[SchedulingResourceComparison]] = {}
    for pair in pairs:
        groups.setdefault(pair.pod_uid, []).append(pair)
    result = []
    for uid, comparisons in sorted(groups.items()):
        status: Literal["scattered_across_nodes", "not_observed", "unknown"] = "unknown"
        if all(item.status != "blocked" for item in comparisons):
            aggregate_sufficient = all(
                required is not None
                and sum(Decimal(str(max(0, value or 0))) for value in values)
                >= Decimal(str(required))
                for required, values in (
                    (
                        comparisons[0].cpu_required_mcpu,
                        [item.cpu_available_mcpu for item in comparisons],
                    ),
                    (
                        comparisons[0].memory_required_mib,
                        [item.memory_available_mib for item in comparisons],
                    ),
                    (1, [item.pod_slots_available for item in comparisons]),
                )
            )
            status = (
                "scattered_across_nodes"
                if aggregate_sufficient
                and all(item.status == "unsatisfied" for item in comparisons)
                else "not_observed"
            )
        result.append(SchedulingResourceFragmentation(pod_uid=uid, status=status))
    return result


def _available_resource(
    capacity: float | None,
    reserved: float | None,
    candidate: float | None,
    *,
    already_bound: bool,
) -> float | None:
    if capacity is None or reserved is None or candidate is None:
        return None
    return float(
        Decimal(str(capacity))
        - Decimal(str(reserved))
        + (Decimal(str(candidate)) if already_bound else Decimal(0))
    )


def _retained_pod_slots(allocatable: object) -> int | None:
    slots = allocatable.get("pods") if isinstance(allocatable, dict) else None
    return (
        int(slots)
        if isinstance(slots, str)
        and len(slots) <= 10
        and slots.isascii()
        and slots.isdecimal()
        and int(slots) <= 2**31 - 1
        else None
    )


def _unmodeled_scheduler_state(row: dict[str, Any]) -> bool:
    spec, status = row.get("spec", {}), row.get("status", {})
    if any(
        spec.get(field) not in (None, {}, [], "", 0)
        for field in ("schedulingGroup", "preemptionPolicy", "priority")
    ) or any(
        status.get(field) not in (None, {}, [])
        for field in ("resources", "allocatedResources", "nodeAllocatableResourceClaimStatuses")
    ):
        return True
    containers = status.get("containerStatuses", [])
    if not isinstance(containers, list):
        return True
    return any(
        not isinstance(item, dict)
        or any(
            item.get(field) not in (None, {}, []) for field in ("resources", "allocatedResources")
        )
        for item in containers
    )


def calculate_scheduling_constraints(
    metadata: KubernetesMetadataSnapshot,
    *,
    pods: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> SchedulingConstraintCalculation:
    if len(pods) * len(nodes) > MAXIMUM_PLACEMENT_PAIRS:
        raise ValueError("Scheduling calculation exceeds its pair budget")
    diagnostics = diagnose_scheduling_shapes(
        metadata,
        pods=pods,
        nodes=nodes,
        as_of=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )
    inventory = normalize_scheduling(metadata)
    pod_shapes = {item.pod_uid: item for item in diagnostics.pods}
    node_shapes = {item.node_uid: item for item in diagnostics.nodes}
    node_slots = {
        item.node_uid: item.allocatable_pod_slots for item in diagnostics.projection.nodes
    }
    reservations = {item.node_uid: item for item in diagnostics.projection.audit.nodes}
    unmodeled_native = {row["metadata"]["uid"] for row in pods if _unmodeled_scheduler_state(row)}
    unsupported_competitors = any(
        pod_shapes[item.pod_uid].status != "within_initial_shape"
        or item.pod_uid in unmodeled_native
        for item in inventory.pods
        if item.resource_phase not in {"Succeeded", "Failed"}
    )
    pairs = []
    for candidate in sorted(inventory.pods, key=lambda item: item.pod_uid):
        if candidate.resource_phase in {"Succeeded", "Failed"}:
            continue
        for node in sorted(inventory.node_resources, key=lambda item: item.node_uid):
            reservation = reservations[node.node_uid]
            issues = list(reservation.issues)
            if candidate.workload_kind != "Deployment" or not candidate.namespace_uid:
                issues.append("candidate_controller_unsupported")
            if pod_shapes[candidate.pod_uid].status != "within_initial_shape":
                issues.append("candidate_shape_unmodeled")
            if node_shapes[node.node_uid].status != "within_initial_shape":
                issues.append("node_shape_unmodeled")
            if unsupported_competitors:
                issues.append("competitor_shape_unmodeled")
            if any(
                metadata.api_availability.get(key) != "available"
                or not metadata.resource_versions.get(key)
                for key in ("apps/v1/deployments", "apps/v1/replicasets")
            ):
                issues.append("controller_lists_incomplete")
            already_bound = candidate.pod_uid in reservation.pod_uids
            cpu = _available_resource(
                node.allocatable_cpu_mcpu,
                reservation.observed_cpu_request_mcpu,
                candidate.effective_cpu_request_mcpu,
                already_bound=already_bound,
            )
            memory = _available_resource(
                node.allocatable_memory_mib,
                reservation.observed_memory_request_mib,
                candidate.effective_memory_request_mib,
                already_bound=already_bound,
            )
            slots = node_slots[node.node_uid]
            count = reservation.observed_nonterminal_pod_count
            available_slots = (
                slots - count + int(already_bound)
                if slots is not None and count is not None
                else None
            )
            if cpu is None:
                issues.append("cpu_constraint_unknown")
            if memory is None:
                issues.append("memory_constraint_unknown")
            if available_slots is None:
                issues.append("pod_slot_constraint_unknown")
            insufficient = (
                (
                    cpu is not None
                    and candidate.effective_cpu_request_mcpu is not None
                    and cpu < candidate.effective_cpu_request_mcpu
                )
                or (
                    memory is not None
                    and candidate.effective_memory_request_mib is not None
                    and memory < candidate.effective_memory_request_mib
                )
                or (available_slots is not None and available_slots < 1)
            )
            pairs.append(
                SchedulingResourceComparison(
                    pod_uid=candidate.pod_uid,
                    node_uid=node.node_uid,
                    status="blocked" if issues else "unsatisfied" if insufficient else "satisfied",
                    cpu_required_mcpu=candidate.effective_cpu_request_mcpu,
                    memory_required_mib=candidate.effective_memory_request_mib,
                    cpu_available_mcpu=cpu,
                    memory_available_mib=memory,
                    pod_slots_available=available_slots,
                    issues=sorted(set(issues)),
                )
            )
    result = SchedulingConstraintCalculation(
        diagnostics=diagnostics, pairs=pairs, fragmentation=_resource_fragmentation(pairs)
    )
    if len(result.model_dump_json().encode("utf-8")) > 32 * 1024 * 1024:
        raise ValueError("Scheduling calculation exceeds its output byte budget")
    return result


def _os_shape(value: object) -> Literal["linux", "windows", "unknown"]:
    if isinstance(value, str):
        if value == "linux":
            return "linux"
        if value == "windows":
            return "windows"
    return "unknown"


def _shape_presence(fields: dict[str, Any], key: str, expected: type) -> ShapePresence:
    value = fields.get(key)
    if not isinstance(value, expected):
        return "unknown"
    return "present" if value else "absent"


def _resource_shapes(spec: dict[str, Any]) -> dict[ShapeFeature, ShapePresence]:
    found: dict[ShapeFeature, ShapePresence] = {
        "extended_resources": "absent",
        "hugepages": "absent",
        "ephemeral_storage": "absent",
        "host_ports": "absent",
        "resource_claims": _shape_presence(spec, "resourceClaims", list),
    }
    unknown_resources = not isinstance(spec.get("resources"), dict)
    unknown_ports = False
    resource_maps: list[Any] = [spec["resources"]] if spec.get("resources") else []
    for key in ["containers", "initContainers"]:
        containers = spec.get(key)
        if not isinstance(containers, list):
            unknown_resources = unknown_ports = True
            continue
        for container in containers:
            if not isinstance(container, dict):
                unknown_resources = unknown_ports = True
                continue
            resource_maps.append(container.get("resources"))
            ports = container.get("ports")
            if not isinstance(ports, list):
                unknown_ports = True
                continue
            for port in ports:
                value = port.get("hostPort") if isinstance(port, dict) else None
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535:
                    unknown_ports = True
                elif value:
                    found["host_ports"] = "present"
    for resources in resource_maps:
        if isinstance(resources, dict):
            claims = resources.get("claims")
            if isinstance(claims, list) and claims:
                found["resource_claims"] = "present"
            elif claims is not None and not isinstance(claims, list):
                if found["resource_claims"] != "present":
                    found["resource_claims"] = "unknown"
        for field in ["requests", "limits"]:
            quantities = resources.get(field) if isinstance(resources, dict) else None
            if not isinstance(quantities, dict):
                unknown_resources = True
                continue
            for resource in quantities:
                if resource == "ephemeral-storage":
                    found["ephemeral_storage"] = "present"
                elif isinstance(resource, str) and resource.startswith("hugepages-"):
                    found["hugepages"] = "present"
                elif resource not in {"cpu", "memory"}:
                    found["extended_resources"] = "present"
    for feature in list(found):
        if feature == "resource_claims":
            continue
        if found[feature] != "present" and (
            unknown_ports if feature == "host_ports" else unknown_resources
        ):
            found[feature] = "unknown"
    return found


def _scheduling_object_shape(
    row: dict[str, Any], projected: KubernetesObjectMetadata
) -> SchedulingPodShape | SchedulingNodeShape:
    identity = row["metadata"]
    version = identity.get("resourceVersion")
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise ValueError("Scheduling shapes require valid object resource versions")
    spec, status = row.get("spec", {}), row.get("status", {})
    if not isinstance(spec, dict) or not isinstance(status, dict):
        raise ValueError("Scheduling shapes require native object fields")
    if projected.kind == "Pod":
        features = _resource_shapes(spec)
        fields: list[tuple[str, ShapeFeature, type]] = [
            ("hostNetwork", "host_network", bool),
            ("volumes", "volumes", list),
            ("schedulingGates", "scheduling_gates", list),
            ("nodeSelector", "node_selector", dict),
            ("affinity", "affinity", dict),
            ("topologySpreadConstraints", "topology_spread", list),
            ("tolerations", "tolerations", list),
            ("priorityClassName", "priority_class", str),
            ("runtimeClassName", "runtime_class", str),
            ("resources", "pod_resource_budget", dict),
            ("initContainers", "init_containers", list),
            ("overhead", "pod_overhead", dict),
        ]
        for field, feature, field_type in fields:
            features[feature] = _shape_presence(spec, field, field_type)
        operating_system = spec.get("os")
        os_name = operating_system.get("name") if isinstance(operating_system, dict) else None
        scheduler = spec.get("schedulerName")
        return SchedulingPodShape(
            pod_uid=projected.uid,
            resource_version=version,
            os_name=_os_shape(os_name),
            scheduler_name=scheduler if isinstance(scheduler, str) and scheduler.strip() else None,
            features=features,
        )
    labels = identity.get("labels", {})
    os_name = labels.get("kubernetes.io/os") if isinstance(labels, dict) else None
    architecture = labels.get("kubernetes.io/arch") if isinstance(labels, dict) else None
    slot_count = _retained_pod_slots(status.get("allocatable"))
    conditions: dict[NodeCondition, Literal["True", "False", "Unknown"]] = {}
    native_conditions = status.get("conditions")
    condition_types: list[NodeCondition] = [
        "Ready",
        "MemoryPressure",
        "DiskPressure",
        "PIDPressure",
        "NetworkUnavailable",
    ]
    for condition_type in condition_types:
        matches = (
            [
                item.get("status")
                for item in native_conditions
                if isinstance(item, dict) and item.get("type") == condition_type
            ]
            if isinstance(native_conditions, list)
            else []
        )
        conditions[condition_type] = (
            cast(Literal["True", "False", "Unknown"], matches[0])
            if len(matches) == 1
            and isinstance(matches[0], str)
            and matches[0] in {"True", "False", "Unknown"}
            else "Unknown"
        )
    return SchedulingNodeShape(
        node_uid=projected.uid,
        resource_version=version,
        os_name=_os_shape(os_name),
        architecture=architecture
        if isinstance(architecture, str) and architecture.strip()
        else None,
        allocatable_pod_slots=slot_count,
        features={
            "taints": _shape_presence(spec, "taints", list),
            "cordoned": _shape_presence(spec, "unschedulable", bool),
        },
        conditions=conditions,
    )


def project_scheduling_observation(
    resource: str, row: dict[str, Any]
) -> SchedulingObjectObservation:
    from aks_fleet_efficiency.collectors.kubernetes_metadata import project_metadata

    if resource not in {"v1/pods", "v1/nodes"} or not isinstance(row.get("metadata"), dict):
        raise ValueError("Scheduling observations require native Pod or Node identities")
    projected = project_metadata(resource, row)
    return SchedulingObjectObservation(
        kind=cast(Literal["Pod", "Node"], projected.kind),
        uid=projected.uid,
        approved_projection_digest=_approved_projection_digest(projected),
        shape=_scheduling_object_shape(row, projected),
        protection=_disruption_protection_observation(row, projected),
    )


def project_scheduling_shapes(
    metadata: KubernetesMetadataSnapshot,
    *,
    pods: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> SchedulingShapeProjection:
    from aks_fleet_efficiency.collectors.kubernetes_metadata import project_metadata

    if len(pods) + len(nodes) > 100_000 or len(metadata.resources) > 100_000:
        raise ValueError("Scheduling shape projection exceeds its object budget")
    audit = audit_scheduling_completeness(
        metadata, as_of=as_of, maximum_source_age_seconds=maximum_source_age_seconds
    )
    pod_shapes = []
    node_shapes = []
    for kind, resource, rows in [("Pod", "v1/pods", pods), ("Node", "v1/nodes", nodes)]:
        expected = {item.uid: item for item in metadata.resources if item.kind == kind}
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("metadata"), dict):
                raise ValueError("Scheduling shape projection requires native object identities")
            projected = project_metadata(resource, row)
            if projected.uid in seen or expected.get(projected.uid) != projected:
                raise ValueError(
                    "Scheduling shapes must exactly match every original approved projection"
                )
            seen.add(projected.uid)
            shape = _scheduling_object_shape(row, projected)
            if isinstance(shape, SchedulingPodShape):
                pod_shapes.append(shape)
            else:
                node_shapes.append(shape)
        if seen != set(expected):
            raise ValueError(
                "Scheduling shapes require every original Pod and Node without truncation"
            )
    return SchedulingShapeProjection(
        audit=audit,
        pods=sorted(pod_shapes, key=lambda item: item.pod_uid),
        nodes=sorted(node_shapes, key=lambda item: item.node_uid),
    )


def diagnose_scheduling_shapes(
    metadata: KubernetesMetadataSnapshot,
    *,
    pods: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> SchedulingShapeDiagnostics:
    projection = project_scheduling_shapes(
        metadata,
        pods=pods,
        nodes=nodes,
        as_of=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )
    pod_features: tuple[ShapeFeature, ...] = (
        "host_network",
        "host_ports",
        "volumes",
        "resource_claims",
        "scheduling_gates",
        "node_selector",
        "affinity",
        "topology_spread",
        "tolerations",
        "priority_class",
        "runtime_class",
        "pod_resource_budget",
        "init_containers",
        "pod_overhead",
        "extended_resources",
        "hugepages",
        "ephemeral_storage",
    )
    node_features: tuple[ShapeFeature, ...] = ("taints", "cordoned")
    pod_diagnostics = []
    for pod in projection.pods:
        unsupported = sorted(
            feature for feature in pod_features if pod.features.get(feature) == "present"
        )
        unknown = sorted(
            feature for feature in pod_features if pod.features.get(feature, "unknown") == "unknown"
        )
        pod_issues: list[PodShapeIssue] = []
        if pod.os_name == "unknown":
            pod_issues.append("pod_os_unknown")
        elif pod.os_name != "linux":
            pod_issues.append("pod_os_unsupported")
        if pod.scheduler_name is None:
            pod_issues.append("scheduler_name_unknown")
        elif pod.scheduler_name != "default-scheduler":
            pod_issues.append("scheduler_name_unsupported")
        if pod.resource_version is None:
            pod_issues.append("object_resource_version_unknown")
        pod_diagnostics.append(
            SchedulingPodDiagnostic(
                pod_uid=pod.pod_uid,
                status="unsupported"
                if unsupported or any(issue.endswith("_unsupported") for issue in pod_issues)
                else "unknown"
                if unknown or pod_issues
                else "within_initial_shape",
                unsupported_features=unsupported,
                unknown_features=unknown,
                issues=sorted(pod_issues),
            )
        )
    node_diagnostics = []
    for node in projection.nodes:
        unsupported = sorted(
            feature for feature in node_features if node.features.get(feature) == "present"
        )
        unknown = sorted(
            feature
            for feature in node_features
            if node.features.get(feature, "unknown") == "unknown"
        )
        unknown_conditions = sorted(
            condition for condition, state in node.conditions.items() if state == "Unknown"
        )
        unsuitable_conditions = sorted(
            condition
            for condition, state in node.conditions.items()
            if state != "Unknown" and state != ("True" if condition == "Ready" else "False")
        )
        node_issues: list[NodeShapeIssue] = []
        if node.os_name == "unknown":
            node_issues.append("node_os_unknown")
        elif node.os_name != "linux":
            node_issues.append("node_os_unsupported")
        if node.architecture is None:
            node_issues.append("node_architecture_unknown")
        if node.allocatable_pod_slots is None:
            node_issues.append("pod_slots_unknown")
        elif node.allocatable_pod_slots == 0:
            node_issues.append("pod_slots_empty")
        if node.resource_version is None:
            node_issues.append("object_resource_version_unknown")
        node_diagnostics.append(
            SchedulingNodeDiagnostic(
                node_uid=node.node_uid,
                status="unsupported"
                if unsupported
                or unsuitable_conditions
                or any(issue in {"node_os_unsupported", "pod_slots_empty"} for issue in node_issues)
                else "unknown"
                if unknown or unknown_conditions or node_issues
                else "within_initial_shape",
                unsupported_features=unsupported,
                unknown_features=unknown,
                unsuitable_conditions=unsuitable_conditions,
                unknown_conditions=unknown_conditions,
                issues=sorted(node_issues),
            )
        )
    return SchedulingShapeDiagnostics(
        projection=projection, pods=pod_diagnostics, nodes=node_diagnostics
    )


def _pdb_availability(value: object, issues: list[str]) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.strip():
        return value
    issues.append("invalid_pdb_availability")
    return None


def _pdb_count(value: object, issues: list[str]) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if value is not None:
        issues.append("invalid_pdb_status")
    return None


def normalize_scheduling(metadata: KubernetesMetadataSnapshot) -> SchedulingInventory:
    def listed(key: str) -> bool:
        return metadata.api_availability.get(key) == "available" and bool(
            metadata.resource_versions.get(key)
        )

    result = SchedulingInventory(
        cluster_resource_id=metadata.cluster_resource_id,
        cluster_uid=metadata.cluster_uid,
        observed_at=metadata.generated_at,
        pods=[],
    )
    resources = {item.uid: item for item in metadata.resources}
    if len(resources) != len(metadata.resources):
        result.issues.append("ambiguous_scheduling_identity")
    for key in ["v1/namespaces", "v1/pods"]:
        if not listed(key):
            result.issues.append("incomplete_scheduling_inventory")
    for key in ["v1/nodes", "apps/v1/daemonsets", "policy/v1/poddisruptionbudgets"]:
        if not listed(key):
            result.unobserved_context.append(key)
    if listed("policy/v1/poddisruptionbudgets"):
        for resource in sorted(metadata.resources, key=lambda item: item.uid):
            if resource.kind != "PodDisruptionBudget" or resource.api_version != "policy/v1":
                continue
            issues: list[str] = []
            min_available = _pdb_availability(resource.spec.get("minAvailable"), issues)
            max_unavailable = _pdb_availability(resource.spec.get("maxUnavailable"), issues)
            if min_available is None and max_unavailable is None:
                issues.append("missing_pdb_availability")
            elif min_available is not None and max_unavailable is not None:
                issues.append("ambiguous_pdb_availability")
            result.pdbs.append(
                PodDisruptionBudgetEvidence(
                    uid=resource.uid,
                    name=resource.name,
                    namespace=resource.namespace or "unknown",
                    min_available=min_available,
                    max_unavailable=max_unavailable,
                    disruptions_allowed=_pdb_count(
                        resource.status.get("disruptionsAllowed"), issues
                    ),
                    expected_pods=_pdb_count(resource.status.get("expectedPods"), issues),
                    issues=sorted(set(issues)),
                )
            )
    for resource in sorted(metadata.resources, key=lambda item: item.uid):
        if resource.kind == "Node" and listed("v1/nodes"):
            taints = resource.spec.get("taints")
            if not isinstance(taints, list):
                result.unobserved_context.append(f"node_taints:{resource.uid}")
            elif taints:
                result.tainted_node_uids.append(resource.uid)
            if resource.spec.get("unschedulable") is True:
                result.cordoned_node_uids.append(resource.uid)
            elif resource.spec.get("unschedulable") is not False:
                result.unobserved_context.append(f"node_cordon:{resource.uid}")
        elif resource.kind == "DaemonSet" and listed("apps/v1/daemonsets"):
            result.daemonset_uids.append(resource.uid)
        if resource.kind != "Pod":
            continue
        item = SchedulingPodEvidence(
            pod_uid=resource.uid,
            pod_name=resource.name,
            namespace=resource.namespace or "unknown",
            constraints={},
        )
        namespaces = [
            entry
            for entry in metadata.resources
            if entry.kind == "Namespace" and entry.name == resource.namespace
        ]
        if len(namespaces) == 1 and namespaces[0].api_version == "v1":
            item.namespace_uid = namespaces[0].uid
        else:
            item.issues.append("missing_namespace_identity")
        parent_uid = metadata.workload_bindings.get(resource.uid)
        parent = resources.get(parent_uid) if parent_uid else None
        if (
            parent is not None
            and parent.kind in CONTROLLERS
            and parent.api_version == CONTROLLERS[parent.kind].rsplit("/", 1)[0]
            and listed(CONTROLLERS[parent.kind])
            and _owner_matches(resource, parent, resources, metadata)
        ):
            item.workload_uid = parent.uid
            item.workload_name = parent.name
            item.workload_kind = parent.kind
            replicas = parent.spec.get("replicas")
            if parent.kind in {"Deployment", "StatefulSet"}:
                if isinstance(replicas, int) and not isinstance(replicas, bool) and replicas >= 0:
                    item.workload_replicas = replicas
                elif replicas is None:
                    item.unobserved_fields.append("workload.replicas")
                else:
                    item.issues.append("invalid_workload_replicas")
        else:
            item.issues.append("unresolved_workload_identity")
        if resource.api_version != "v1" or not resource.namespace:
            item.issues.append("invalid_scheduling_identity")
        if listed("policy/v1/poddisruptionbudgets"):
            item.namespace_pdb_candidates = sorted(
                entry.uid
                for entry in metadata.resources
                if entry.kind == "PodDisruptionBudget" and entry.namespace == resource.namespace
            )
        spec = resource.spec
        containers = spec.get("containers")
        if isinstance(containers, list):
            for container in containers:
                if not isinstance(container, dict):
                    item.issues.append("invalid_probe_evidence")
                    continue
                container_name = container.get("name")
                if not isinstance(container_name, str) or not container_name:
                    item.issues.append("invalid_probe_evidence")
                    continue
                probe_fields = ["livenessProbe", "readinessProbe", "startupProbe"]
                if any(
                    field in container and not isinstance(container[field], dict)
                    for field in probe_fields
                ):
                    item.issues.append("invalid_probe_evidence")
                    continue
                item.container_probes.append(
                    ContainerProbeEvidence(
                        container=container_name,
                        liveness_probe="livenessProbe" in container,
                        readiness_probe="readinessProbe" in container,
                        startup_probe="startupProbe" in container,
                    )
                )
        elif containers is not None:
            item.issues.append("invalid_probe_evidence")
        fields: list[tuple[str, SchedulingConstraint, type]] = [
            ("nodeSelector", "node_selector", dict),
            ("tolerations", "tolerations", list),
            ("priorityClassName", "priority_class", str),
            ("runtimeClassName", "runtime_class", str),
            ("initContainers", "init_containers", list),
            ("overhead", "pod_overhead", dict),
            ("resources", "pod_resource_budget", dict),
        ]
        for field, signal, expected in fields:
            value = spec.get(field)
            if field not in spec or value is None:
                item.unobserved_fields.append(field)
            elif not isinstance(value, expected):
                item.issues.append("invalid_scheduling_field")
            elif value:
                item.constraints[signal] = len(value) if isinstance(value, (dict, list)) else 1
        for field in ["affinity", "topologySpreadConstraints", "volumes", "schedulerName"]:
            if field not in spec or spec[field] is None:
                item.unobserved_fields.append(field)
        affinity = spec.get("affinity", {})
        if not isinstance(affinity, dict):
            item.issues.append("invalid_scheduling_field")
        else:
            affinity_fields: list[tuple[str, SchedulingConstraint, SchedulingConstraint]] = [
                ("nodeAffinity", "required_node_affinity", "preferred_node_affinity"),
                ("podAffinity", "required_pod_affinity", "preferred_pod_affinity"),
                ("podAntiAffinity", "required_pod_anti_affinity", "preferred_pod_anti_affinity"),
            ]
            for field, hard, soft in affinity_fields:
                part = affinity.get(field, {})
                if not isinstance(part, dict):
                    item.issues.append("invalid_scheduling_field")
                    continue
                affinity_signals: list[tuple[str, SchedulingConstraint]] = [
                    ("requiredDuringSchedulingIgnoredDuringExecution", hard),
                    ("preferredDuringSchedulingIgnoredDuringExecution", soft),
                ]
                for key, signal_name in affinity_signals:
                    value = part.get(key)
                    if value:
                        if not isinstance(value, (dict, list)):
                            item.issues.append("invalid_scheduling_field")
                        else:
                            item.constraints[signal_name] = len(value)
        for field in ["topologySpreadConstraints", "volumes"]:
            values = spec.get(field, [])
            if not isinstance(values, list):
                item.issues.append("invalid_scheduling_field")
                continue
            for value in values:
                if not isinstance(value, dict):
                    item.issues.append("invalid_scheduling_field")
                elif field == "volumes":
                    volume_fields: list[tuple[str, SchedulingConstraint]] = [
                        ("persistentVolumeClaim", "persistent_volume_claims"),
                        ("emptyDir", "local_emptydir_volumes"),
                    ]
                    for key, signal in volume_fields:
                        if key in value:
                            item.constraints[signal] = item.constraints.get(signal, 0) + 1
                elif value.get("whenUnsatisfiable") == "DoNotSchedule":
                    topology_signal: SchedulingConstraint = "hard_topology_spread"
                    topology_when: Literal["DoNotSchedule", "ScheduleAnyway"] = "DoNotSchedule"
                    item.constraints[topology_signal] = item.constraints.get(topology_signal, 0) + 1
                    max_skew = value.get("maxSkew")
                    topology_key = value.get("topologyKey")
                    min_domains = value.get("minDomains")
                    if (
                        isinstance(max_skew, int)
                        and not isinstance(max_skew, bool)
                        and max_skew > 0
                        and isinstance(topology_key, str)
                        and topology_key
                        and (
                            min_domains is None
                            or (
                                isinstance(min_domains, int)
                                and not isinstance(min_domains, bool)
                                and min_domains > 0
                            )
                        )
                    ):
                        item.topology_spread.append(
                            TopologySpreadEvidence(
                                max_skew=max_skew,
                                topology_key=topology_key,
                                when_unsatisfiable=topology_when,
                                min_domains=min_domains,
                            )
                        )
                    else:
                        item.unobserved_fields.append("topologySpreadConstraints.detail")
                elif value.get("whenUnsatisfiable") == "ScheduleAnyway":
                    topology_signal = "soft_topology_spread"
                    topology_when = "ScheduleAnyway"
                    item.constraints[topology_signal] = item.constraints.get(topology_signal, 0) + 1
                    max_skew = value.get("maxSkew")
                    topology_key = value.get("topologyKey")
                    min_domains = value.get("minDomains")
                    if (
                        isinstance(max_skew, int)
                        and not isinstance(max_skew, bool)
                        and max_skew > 0
                        and isinstance(topology_key, str)
                        and topology_key
                        and (
                            min_domains is None
                            or (
                                isinstance(min_domains, int)
                                and not isinstance(min_domains, bool)
                                and min_domains > 0
                            )
                        )
                    ):
                        item.topology_spread.append(
                            TopologySpreadEvidence(
                                max_skew=max_skew,
                                topology_key=topology_key,
                                when_unsatisfiable=topology_when,
                                min_domains=min_domains,
                            )
                        )
                    else:
                        item.unobserved_fields.append("topologySpreadConstraints.detail")
                else:
                    item.issues.append("invalid_scheduling_field")
        scheduler = spec.get("schedulerName")
        if scheduler and scheduler != "default-scheduler":
            if isinstance(scheduler, str):
                item.constraints["custom_scheduler"] = 1
            else:
                item.issues.append("invalid_scheduling_field")
        item.issues = sorted(set(item.issues))
        item.unobserved_fields.sort()
        result.pods.append(item)
    _pdb_selector_matches(metadata, result)
    _resource_accounting(metadata, result)
    _daemonset_overhead(metadata, result)
    _daemonset_coverage(metadata, result)
    result.unobserved_context.sort()
    return SchedulingInventory.model_validate(result)


ConstraintMatch = Literal["matched", "excluded", "unknown"]
PlacementConstraint = Literal["node_selector", "required_node_affinity", "hard_taints", "cordon"]


class PodNodeConstraintReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pod_uid: NonEmptyString
    node_uid: NonEmptyString
    constraints: dict[PlacementConstraint, ConstraintMatch]
    status: Literal["no_observed_exclusion", "excluded_by_observed_constraint", "unknown"]
    issues: list[NonEmptyString] = Field(default_factory=list)


class SchedulingPlacementReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["current-retained-hard-constraint-review"] = (
        "current-retained-hard-constraint-review"
    )
    fit_status: Literal["blocked"] = "blocked"
    audit: SchedulingCompletenessAudit
    pairs: list[PodNodeConstraintReview] = Field(max_length=100_000)
    admission_blockers: tuple[
        Literal["producer_completeness_unverified"],
        Literal["scheduler_configuration_unverified"],
    ] = ("producer_completeness_unverified", "scheduler_configuration_unverified")
    unassessed_dimensions: list[NonEmptyString] = Field(
        default_factory=lambda: [
            "resources",
            "pod_slots",
            "pod_affinity",
            "pod_anti_affinity",
            "topology_spread",
            "storage",
            "host_ports",
            "host_network",
            "resource_claims",
            "extended_resources",
            "os_runtime_compatibility",
            "node_conditions",
            "disruption_feasibility",
        ]
    )


def _all_matches(values: list[bool | None]) -> bool | None:
    return False if False in values else None if None in values else True


def _any_match(values: list[bool | None]) -> bool | None:
    return True if True in values else None if None in values else False


def _selector_integer(value: object) -> int | None:
    if not isinstance(value, str) or len(value) > 20 or not re.fullmatch(r"[+-]?[0-9]+", value):
        return None
    parsed = int(value)
    return parsed if -(2**63) <= parsed < 2**63 else None


def _node_requirement(requirement: object, labels: dict[str, str]) -> bool | None:
    if not isinstance(requirement, dict) or set(requirement) != {"key", "operator", "values"}:
        return None
    key, operator, values = (requirement[field] for field in ["key", "operator", "values"])
    if not isinstance(key, str) or not key or not isinstance(operator, str):
        return None
    if operator not in {"Gt", "Lt"}:
        return _selector_match({"matchExpressions": [requirement]}, labels)
    if not isinstance(values, list) or len(values) != 1:
        return None
    expected = _selector_integer(values[0])
    actual = _selector_integer(labels.get(key))
    if expected is None or actual is None:
        return None
    return actual > expected if operator == "Gt" else actual < expected


def _required_node_affinity(spec: dict[str, Any], node: KubernetesObjectMetadata) -> bool | None:
    affinity = spec.get("affinity")
    if not isinstance(affinity, dict):
        return None
    if not affinity:
        return True
    node_affinity = affinity.get("nodeAffinity")
    if not isinstance(node_affinity, dict):
        return None
    if not node_affinity:
        return True
    required = node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution")
    if not isinstance(required, dict) or set(required) != {"nodeSelectorTerms"}:
        return None
    terms = required["nodeSelectorTerms"]
    if not isinstance(terms, list):
        return None
    matches: list[bool | None] = []
    for term in terms:
        if not isinstance(term, dict) or set(term) - {"matchExpressions", "matchFields"}:
            matches.append(None)
            continue
        expressions, fields = term.get("matchExpressions", []), term.get("matchFields", [])
        if not isinstance(expressions, list) or not isinstance(fields, list):
            matches.append(None)
            continue
        requirements = [_node_requirement(expression, node.labels) for expression in expressions]
        for field in fields:
            if (
                not isinstance(field, dict)
                or set(field) != {"key", "operator", "values"}
                or field["key"] != "metadata.name"
                or field["operator"] not in ("In", "NotIn")
                or not isinstance(field["values"], list)
                or len(field["values"]) != 1
                or not isinstance(field["values"][0], str)
                or not field["values"][0]
            ):
                requirements.append(None)
            else:
                requirements.append((node.name in field["values"]) == (field["operator"] == "In"))
        matches.append(_all_matches(requirements) if requirements else False)
    return _any_match(matches)


def _tolerates(taint: dict[str, str], toleration: object) -> bool | None:
    if not isinstance(toleration, dict) or set(toleration) - {
        "key",
        "operator",
        "value",
        "effect",
        "tolerationSeconds",
    }:
        return None
    key, operator, effect = (toleration.get(field) for field in ["key", "operator", "effect"])
    if (
        not isinstance(key, str)
        or operator not in ("Equal", "Exists")
        or not isinstance(effect, str)
        or effect not in {"", "NoSchedule", "NoExecute", "PreferNoSchedule"}
    ):
        return None
    seconds = toleration.get("tolerationSeconds")
    if seconds is not None and (
        isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0
    ):
        return None
    value = toleration.get("value")
    if operator == "Equal" and (not key or not isinstance(value, str)):
        return None
    if operator == "Exists" and value not in (None, ""):
        return None
    if effect and effect != taint["effect"]:
        return False
    if operator == "Exists":
        return not key or key == taint["key"]
    return key == taint["key"] and value == taint["value"]


def _hard_taint_match(spec: dict[str, Any], node: KubernetesObjectMetadata) -> bool | None:
    taints = node.spec.get("taints")
    if not isinstance(taints, list):
        return None
    checks: list[bool | None] = []
    tolerations = spec.get("tolerations")
    for taint in taints:
        if (
            not isinstance(taint, dict)
            or set(taint) != {"key", "value", "effect"}
            or not isinstance(taint["key"], str)
            or not taint["key"]
            or not isinstance(taint["value"], str)
            or taint["effect"] not in ("NoSchedule", "NoExecute", "PreferNoSchedule")
        ):
            checks.append(None)
        elif taint["effect"] == "PreferNoSchedule":
            continue
        elif not isinstance(tolerations, list):
            checks.append(None)
        else:
            checks.append(
                _any_match([_tolerates(cast(dict[str, str], taint), item) for item in tolerations])
            )
    return _all_matches(checks)


def _cordon_match(spec: dict[str, Any], node: KubernetesObjectMetadata) -> bool | None:
    cordon = node.spec.get("unschedulable")
    if not isinstance(cordon, bool):
        return None
    if not cordon:
        return True
    tolerations = spec.get("tolerations")
    if not isinstance(tolerations, list):
        return None
    taint = {"key": "node.kubernetes.io/unschedulable", "value": "", "effect": "NoSchedule"}
    return _any_match([_tolerates(taint, item) for item in tolerations])


def _placement_work_budget(
    pods: list[KubernetesObjectMetadata], nodes: list[KubernetesObjectMetadata]
) -> None:
    requirement_work = 0
    toleration_work = 0
    for pod in pods:
        selector = pod.spec.get("nodeSelector")
        requirement_work += len(selector) if isinstance(selector, dict) else 1
        tolerations = pod.spec.get("tolerations")
        toleration_work += max(1, len(tolerations)) if isinstance(tolerations, list) else 1
        affinity = pod.spec.get("affinity")
        node_affinity = affinity.get("nodeAffinity") if isinstance(affinity, dict) else None
        required = (
            node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution")
            if isinstance(node_affinity, dict)
            else None
        )
        terms = required.get("nodeSelectorTerms") if isinstance(required, dict) else None
        if not isinstance(terms, list):
            continue
        for term in terms:
            requirement_work += 1
            if not isinstance(term, dict):
                continue
            for key in ["matchExpressions", "matchFields"]:
                requirements = term.get(key)
                if not isinstance(requirements, list):
                    continue
                for requirement in requirements:
                    values = requirement.get("values") if isinstance(requirement, dict) else None
                    requirement_work += 1 + (len(values) if isinstance(values, list) else 0)
            if requirement_work * len(nodes) > MAXIMUM_PLACEMENT_WORK:
                raise ValueError("Scheduling placement review exceeds its constraint work budget")
    taint_work = 0
    for node in nodes:
        taints = node.spec.get("taints")
        taint_work += len(taints) if isinstance(taints, list) else 1
    work = len(pods) * len(nodes) * 4 + len(nodes) * (requirement_work + toleration_work)
    work += taint_work * toleration_work
    if work > MAXIMUM_PLACEMENT_WORK:
        raise ValueError("Scheduling placement review exceeds its constraint work budget")


def review_scheduling_placement(
    metadata: KubernetesMetadataSnapshot,
    *,
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> SchedulingPlacementReview:
    return _review_scheduling_placement(
        metadata, as_of=as_of, maximum_source_age_seconds=maximum_source_age_seconds
    )


def _review_scheduling_placement(
    metadata: KubernetesMetadataSnapshot,
    *,
    as_of: datetime,
    maximum_source_age_seconds: int,
    audit: SchedulingCompletenessAudit | None = None,
    pod_uid: str | None = None,
    node_uids: set[str] | None = None,
) -> SchedulingPlacementReview:
    pods = [item for item in metadata.resources if item.kind == "Pod" and item.api_version == "v1"]
    nodes = [
        item for item in metadata.resources if item.kind == "Node" and item.api_version == "v1"
    ]
    if pod_uid is not None:
        pods = [item for item in pods if item.uid == pod_uid]
    if node_uids is not None:
        nodes = [item for item in nodes if item.uid in node_uids]
    if len(metadata.resources) > 100_000 or len(pods) * len(nodes) > MAXIMUM_PLACEMENT_PAIRS:
        raise ValueError("Scheduling placement review exceeds its object or pair budget")
    _placement_work_budget(pods, nodes)
    if audit is None:
        audit = audit_scheduling_completeness(
            metadata, as_of=as_of, maximum_source_age_seconds=maximum_source_age_seconds
        )
    source_issues = [issue for issue in audit.issues if issue != "unresolved_pod_assignment"]
    pairs = []
    nodes = sorted(nodes, key=lambda item: item.uid)
    for pod in sorted(pods, key=lambda item: item.uid):
        if pod.status.get("phase") in ("Succeeded", "Failed"):
            continue
        for node in nodes:
            issues = list(source_issues)
            if pod.status.get("phase") not in ("Running", "Pending"):
                issues.append("pod_phase_unknown")
            observations: dict[PlacementConstraint, bool | None] = {
                "node_selector": _selector_match(
                    {"matchLabels": pod.spec.get("nodeSelector")}, node.labels
                ),
                "required_node_affinity": _required_node_affinity(pod.spec, node),
                "hard_taints": _hard_taint_match(pod.spec, node),
                "cordon": _cordon_match(pod.spec, node),
            }
            if issues:
                observations = {key: None for key in observations}
            constraints: dict[PlacementConstraint, ConstraintMatch] = {
                key: "unknown" if value is None else "matched" if value else "excluded"
                for key, value in observations.items()
            }
            pairs.append(
                PodNodeConstraintReview(
                    pod_uid=pod.uid,
                    node_uid=node.uid,
                    constraints=constraints,
                    status="excluded_by_observed_constraint"
                    if "excluded" in constraints.values()
                    else "unknown"
                    if "unknown" in constraints.values()
                    else "no_observed_exclusion",
                    issues=sorted(issues),
                )
            )
    return SchedulingPlacementReview(audit=audit, pairs=pairs)


def _selector_match(selector: object, labels: dict[str, str]) -> bool | None:
    if not isinstance(selector, dict) or set(selector) - {"matchLabels", "matchExpressions"}:
        return None
    required = selector.get("matchLabels", {})
    expressions = selector.get("matchExpressions", [])
    if not isinstance(required, dict) or not isinstance(expressions, list):
        return None
    checks: list[bool | None] = []
    for key, value in required.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            return None
        checks.append(labels[key] == value if key in labels else None)
    for expression in expressions:
        if not isinstance(expression, dict) or set(expression) - {"key", "operator", "values"}:
            return None
        key, operator = expression.get("key"), expression.get("operator")
        values = expression.get("values", [])
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(operator, str)
            or operator not in {"In", "NotIn", "Exists", "DoesNotExist"}
            or not isinstance(values, list)
            or any(not isinstance(value, str) for value in values)
            or (operator in {"In", "NotIn"} and not values)
            or (operator in {"Exists", "DoesNotExist"} and values)
        ):
            return None
        if key not in labels:
            checks.append(None)
        elif operator == "In":
            checks.append(labels[key] in values)
        elif operator == "NotIn":
            checks.append(labels[key] not in values)
        else:
            checks.append(operator == "Exists")
    return False if False in checks else None if None in checks else True


def _pdb_selector_matches(
    metadata: KubernetesMetadataSnapshot, inventory: SchedulingInventory
) -> None:
    required = ["v1/namespaces", "v1/pods", "policy/v1/poddisruptionbudgets"]
    observed = (
        metadata.collection.status == CollectionStatus.COMPLETE
        and metadata.collection.requested_scope == [metadata.cluster_resource_id]
        and all(
            metadata.api_availability.get(key) == "available"
            and metadata.resource_versions.get(key)
            for key in required
        )
        and "ambiguous_scheduling_identity" not in inventory.issues
    )
    objects = {item.uid: item for item in metadata.resources}
    namespaces_by_name: dict[str, list[KubernetesObjectMetadata]] = {}
    pods_by_namespace: dict[str | None, list[KubernetesObjectMetadata]] = {}
    for item in metadata.resources:
        if item.api_version != "v1":
            continue
        if item.kind == "Namespace":
            namespaces_by_name.setdefault(item.name, []).append(item)
        elif item.kind == "Pod":
            pods_by_namespace.setdefault(item.namespace, []).append(item)
    pairs = sum(len(pods_by_namespace.get(budget.namespace, [])) for budget in inventory.pdbs)
    for budget in inventory.pdbs:
        if pairs > MAXIMUM_PDB_SELECTOR_PAIRS:
            budget.selector_issues = ["selector_pair_budget_exceeded"]
            continue
        namespaces = namespaces_by_name.get(budget.namespace, [])
        original = objects.get(budget.uid)
        originals = (
            [original]
            if original is not None
            and original.kind == "PodDisruptionBudget"
            and original.api_version == "policy/v1"
            and original.namespace == budget.namespace
            else []
        )
        if not observed or len(namespaces) != 1 or len(originals) != 1:
            budget.selector_issues = ["incomplete_selector_inventory"]
            continue
        budget.namespace_uid = namespaces[0].uid
        budget.selector_matched_pod_uids = []
        budget.selector_unmatched_pod_uids = []
        budget.selector_unknown_pod_uids = []
        selector = originals[0].spec.get("selector")
        pods = pods_by_namespace.get(budget.namespace, [])
        for pod in sorted(pods, key=lambda item: item.uid):
            matched = _selector_match(selector, pod.labels)
            if matched is True:
                budget.selector_matched_pod_uids.append(pod.uid)
            elif matched is False:
                budget.selector_unmatched_pod_uids.append(pod.uid)
            else:
                budget.selector_unknown_pod_uids.append(pod.uid)
        if budget.selector_unknown_pod_uids:
            budget.selector_issues = ["unobserved_or_unsupported_selector_labels"]
            budget.selector_match_status = (
                "partial"
                if budget.selector_matched_pod_uids or budget.selector_unmatched_pod_uids
                else "unknown"
            )
        elif not isinstance(selector, dict) or (not pods and _selector_match(selector, {}) is None):
            budget.selector_issues = ["selector_shape_unknown"]
        else:
            budget.selector_match_status = "complete"


def _resource_accounting(
    metadata: KubernetesMetadataSnapshot, inventory: SchedulingInventory
) -> None:
    inventory.resource_accounting_observed = all(
        metadata.api_availability.get(key) == "available" and metadata.resource_versions.get(key)
        for key in ["v1/namespaces", "v1/nodes", "v1/pods"]
    )
    resources = {item.uid: item for item in metadata.resources}
    for node in sorted(metadata.resources, key=lambda item: item.uid):
        if node.kind != "Node" or node.api_version != "v1":
            continue
        current = NodeResourceEvidence(node_uid=node.uid, node_name=node.name)
        for field in ["capacity", "allocatable"]:
            quantities = node.status.get(field)
            for resource, suffix, parser in [
                ("cpu", "cpu_mcpu", _cpu_quantity),
                ("memory", "memory_mib", _memory_quantity),
            ]:
                try:
                    value = (
                        parser(quantities.get(resource)) if isinstance(quantities, dict) else None
                    )
                    if value is None:
                        raise ValueError("unknown current Node quantity")
                    setattr(current, f"{field}_{suffix}", value)
                except ValueError:
                    current.issues.append(f"unknown_{field}_{resource}")
        inventory.node_resources.append(current)
    for subject in inventory.pods:
        pod = resources[subject.pod_uid]
        phase = pod.status.get("phase")
        if isinstance(phase, str) and phase in {
            "Pending",
            "Running",
            "Succeeded",
            "Failed",
            "Unknown",
        }:
            subject.resource_phase = cast(
                Literal["Pending", "Running", "Succeeded", "Failed", "Unknown"], phase
            )
        nodes = [
            node for node in inventory.node_resources if node.node_name == pod.spec.get("nodeName")
        ]
        if len(nodes) == 1 and inventory.resource_accounting_observed:
            subject.node_uid = nodes[0].node_uid
        request_resources: list[tuple[Literal["cpu", "memory"], str]] = [
            ("cpu", "effective_cpu_request_mcpu"),
            ("memory", "effective_memory_request_mib"),
        ]
        for request_resource, attribute in request_resources:
            try:
                names: set[str] = set()
                for field in ["containers", "initContainers"]:
                    components = pod.spec.get(field)
                    if not isinstance(components, list):
                        raise ValueError("unknown current Pod components")
                    for component in components:
                        name = component.get("name") if isinstance(component, dict) else None
                        if not isinstance(name, str) or not name or name in names:
                            raise ValueError("ambiguous current container identity")
                        names.add(name)
                value = effective_pod_request(pod, request_resource)[3]
                setattr(subject, attribute, value)
            except ValueError:
                subject.resource_accounting_issues.append(f"unknown_{request_resource}_request")


def _daemonset_coverage(
    metadata: KubernetesMetadataSnapshot, inventory: SchedulingInventory
) -> None:
    required = ("v1/namespaces", "v1/pods", "v1/nodes", "apps/v1/daemonsets")
    complete = (
        metadata.collection.status == CollectionStatus.COMPLETE
        and not inventory.issues
        and all(
            metadata.api_availability.get(key) == "available"
            and metadata.resource_versions.get(key)
            for key in required
        )
    )
    resources = {item.uid: item for item in metadata.resources}
    namespaces: dict[str, list[str]] = {}
    for resource in metadata.resources:
        if resource.kind == "Namespace" and resource.api_version == "v1":
            namespaces.setdefault(resource.name, []).append(resource.uid)
    grouped: dict[str, list[SchedulingPodEvidence]] = {}
    unresolved_namespaces: set[str] = set()
    for pod in inventory.pods:
        if pod.workload_kind == "DaemonSet" and pod.workload_uid is not None:
            grouped.setdefault(pod.workload_uid, []).append(pod)
        elif any(
            owner.get("kind") == "DaemonSet" for owner in resources[pod.pod_uid].owner_references
        ):
            unresolved_namespaces.add(pod.namespace)
    for controller in sorted(metadata.resources, key=lambda item: item.uid):
        if controller.kind != "DaemonSet" or controller.api_version != "apps/v1":
            continue
        namespace_uids = namespaces.get(controller.namespace or "", [])
        item = DaemonSetCoverageEvidence(
            daemonset_uid=controller.uid,
            daemonset_name=controller.name,
            namespace=controller.namespace or "unknown",
            namespace_uid=namespace_uids[0] if len(namespace_uids) == 1 else None,
        )
        for field, attribute, issue in [
            ("desiredNumberScheduled", "desired_number_scheduled", "desired_count_unknown"),
            ("numberReady", "number_ready", "ready_count_unknown"),
        ]:
            value = controller.status.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(item, attribute, value)
            else:
                item.status_issues.append(issue)
        if not complete:
            item.observation_issues.append("incomplete_daemonset_coverage_inventory")
        if item.namespace_uid is None:
            item.observation_issues.append("missing_daemonset_namespace_identity")
        if item.namespace in unresolved_namespaces:
            item.observation_issues.append("unresolved_daemonset_ownership")
        subjects = grouped.get(controller.uid, [])
        active = []
        for subject in subjects:
            if subject.resource_phase in {"Succeeded", "Failed"}:
                continue
            active.append(subject)
            if subject.resource_phase not in {"Running", "Pending"}:
                item.observation_issues.append("unknown_daemonset_pod_phase")
            if subject.namespace_uid != item.namespace_uid or subject.namespace != item.namespace:
                item.observation_issues.append("daemonset_pod_identity_mismatch")
        if len({subject.pod_uid for subject in active}) != len(active):
            item.observation_issues.append("ambiguous_daemonset_pod_identity")
        if not item.observation_issues:
            item.observed_pod_uids = sorted(subject.pod_uid for subject in active)
            item.observed_nonterminal_pod_count = len(active)
            assignments = Counter(subject.node_uid for subject in active)
            item.duplicate_node_uids = sorted(
                uid for uid, count in assignments.items() if uid is not None and count > 1
            )
            if None in assignments:
                item.observation_issues.append("unresolved_daemonset_node")
            else:
                item.observed_node_uids = sorted(uid for uid in assignments if uid is not None)
                if item.desired_number_scheduled is not None:
                    item.desired_minus_observed_nodes = item.desired_number_scheduled - len(
                        item.observed_node_uids
                    )
            if item.duplicate_node_uids:
                item.observation_issues.append("duplicate_daemonset_node_placement")
        item.status_issues = sorted(set(item.status_issues))
        item.observation_issues = sorted(set(item.observation_issues))
        inventory.daemonset_coverage.append(item)


def _daemonset_overhead(
    metadata: KubernetesMetadataSnapshot, inventory: SchedulingInventory
) -> None:
    required = ["v1/namespaces", "v1/pods", "v1/nodes", "apps/v1/daemonsets"]
    inventory.daemonset_overhead_observed = all(
        metadata.api_availability.get(key) == "available" and metadata.resource_versions.get(key)
        for key in required
    )
    if not inventory.issues and all(
        pod.workload_kind is not None and pod.workload_kind != "DaemonSet" for pod in inventory.pods
    ):
        inventory.daemonset_overhead_observed = True
        return
    if not inventory.daemonset_overhead_observed:
        inventory.daemonset_overhead_issues.append("incomplete_daemonset_inventory")
    resources = {item.uid: item for item in metadata.resources}
    for subject in inventory.pods:
        pod = resources[subject.pod_uid]
        if subject.workload_kind != "DaemonSet":
            if any(owner.get("kind") == "DaemonSet" for owner in pod.owner_references):
                inventory.daemonset_overhead_issues.append("unresolved_daemonset_ownership")
            continue
        phase = pod.status.get("phase")
        if isinstance(phase, str) and phase in {"Succeeded", "Failed"}:
            continue
        if subject.workload_uid is None or subject.workload_name is None:
            inventory.daemonset_overhead_issues.append("unresolved_daemonset_ownership")
            continue
        item = DaemonSetPodOverhead(
            pod_uid=subject.pod_uid,
            daemonset_uid=subject.workload_uid,
            daemonset_name=subject.workload_name,
            namespace=subject.namespace,
            namespace_uid=subject.namespace_uid,
            issues=list(subject.issues),
        )
        if not isinstance(phase, str) or phase not in {"Pending", "Running"}:
            item.issues.append("unknown_daemonset_pod_phase")
        if subject.namespace_uid is None:
            item.issues.append("missing_daemonset_namespace_identity")
        node_name = pod.spec.get("nodeName")
        nodes = [
            node
            for node in metadata.resources
            if node.kind == "Node" and node.api_version == "v1" and node.name == node_name
        ]
        if len(nodes) != 1:
            item.issues.append("unresolved_daemonset_node")
        else:
            item.node_uid = nodes[0].uid
            allocatable = nodes[0].status.get("allocatable")
            try:
                if not isinstance(allocatable, dict):
                    raise ValueError("unknown allocatable resources")
                cpu = _cpu_quantity(allocatable.get("cpu"))
                memory = _memory_quantity(allocatable.get("memory"))
                if cpu is None or memory is None or cpu <= 0 or memory <= 0:
                    raise ValueError("invalid allocatable resources")
                item.allocatable_cpu_mcpu = cpu
                item.allocatable_memory_mib = memory
            except ValueError:
                item.issues.append("unknown_daemonset_node_allocatable")
        try:
            names: set[str] = set()
            for field in ["containers", "initContainers"]:
                containers = pod.spec.get(field)
                if not isinstance(containers, list):
                    raise ValueError("unknown admitted containers")
                for container in containers:
                    name = container.get("name") if isinstance(container, dict) else None
                    if not isinstance(name, str) or not name or name in names:
                        raise ValueError("ambiguous admitted container identity")
                    names.add(name)
            item.cpu_request_mcpu = effective_pod_request(pod, "cpu")[3]
            item.memory_request_mib = effective_pod_request(pod, "memory")[3]
        except ValueError:
            item.issues.append("unknown_daemonset_requests")
        item.issues = sorted(set(item.issues))
        inventory.daemonset_overhead.append(item)
    inventory.daemonset_overhead_issues = sorted(set(inventory.daemonset_overhead_issues))
