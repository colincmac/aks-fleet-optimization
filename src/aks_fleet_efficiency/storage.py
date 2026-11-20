from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.models import (
    CollectorResult,
    KubernetesMetadataSnapshot,
    KubernetesObjectMetadata,
    UtcDatetime,
)
from aks_fleet_efficiency.node_history import Digest, Reference, _receipt_gaps, _utc
from aks_fleet_efficiency.scheduling import (
    SchedulingCompletenessAudit,
    _required_node_affinity,
    audit_scheduling_completeness,
)

MAXIMUM_STORAGE_OBJECTS = 100_000
MAXIMUM_STORAGE_PAIRS = 100_000
MAXIMUM_STORAGE_WORK = 1_000_000
MAXIMUM_STORAGE_BYTES = 32 * 1024 * 1024
STORAGE_KINDS = {
    "PersistentVolumeClaim",
    "PersistentVolume",
    "StorageClass",
    "CSINode",
    "CSIDriver",
}
TOPOLOGY_KEYS = {
    "topology.kubernetes.io/zone",
    "topology.kubernetes.io/region",
    "kubernetes.io/hostname",
    "kubernetes.io/os",
    "kubernetes.io/arch",
    "topology.disk.csi.azure.com/zone",
}
AccessMode = Literal["ReadWriteOnce", "ReadOnlyMany", "ReadWriteMany", "ReadWriteOncePod"]
StorageType = Literal["csi", "local", "hostPath", "other", "unknown"]


class _StorageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class StorageIdentity(_StorageModel):
    uid: Reference
    name: Annotated[str, Field(strict=True, min_length=1, max_length=253)]
    resource_version: Reference | None
    issues: list[str] = Field(default_factory=list)


class StorageClaim(StorageIdentity):
    namespace_uid: Reference | None
    namespace: str
    volume_name: str | None
    storage_class_name: str | None
    access_modes: tuple[AccessMode, ...] | None
    volume_mode: Literal["Filesystem", "Block"] | None
    bound_volume_uid: Reference | None = None


class StorageVolume(StorageIdentity):
    claim_uid: Reference | None
    claim_name: str | None
    claim_namespace: str | None
    storage_class_name: str | None
    access_modes: tuple[AccessMode, ...] | None
    volume_mode: Literal["Filesystem", "Block"] | None
    storage_type: StorageType
    csi_driver: str | None
    node_affinity: dict[str, JsonValue] | None


class StorageClassContext(StorageIdentity):
    provisioner: str | None
    binding_mode: Literal["Immediate", "WaitForFirstConsumer"] | None
    allowed_topology: dict[str, JsonValue] | None


class CsiNodeDriver(_StorageModel):
    name: Annotated[str, Field(strict=True, min_length=1, max_length=253)]
    maximum_volumes: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)] | None
    topology_keys: tuple[str, ...] | None
    issues: list[str]


class CsiNodeContext(StorageIdentity):
    node_uid: Reference | None
    drivers: list[CsiNodeDriver]


class CsiDriverContext(StorageIdentity):
    attach_required: bool | None


class StorageNodeComparison(_StorageModel):
    claim_uid: Reference
    node_uid: Reference
    bound_volume_topology: Literal["matched", "excluded", "unknown"]
    storage_class_topology: Literal["matched", "excluded", "unknown"]
    reason_codes: list[str]
    storage_feasibility: Literal["unknown"] = "unknown"


class StorageContextProjection(_StorageModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: str
    cluster_resource_id: str
    cluster_uid: Reference
    evaluated_at: UtcDatetime
    maximum_source_age_seconds: Annotated[int, Field(strict=True, ge=1)]
    mapping_reference: Literal["kubernetes-core-storage-v1@v1.36.0"] = (
        "kubernetes-core-storage-v1@v1.36.0"
    )
    input_digest: Digest
    audit: SchedulingCompletenessAudit
    receipts: dict[str, CollectorResult]
    source_issues: list[str]
    claims: list[StorageClaim]
    volumes: list[StorageVolume]
    storage_classes: list[StorageClassContext]
    csi_nodes: list[CsiNodeContext]
    csi_drivers: list[CsiDriverContext]
    comparisons: list[StorageNodeComparison]
    source_admission: Literal["unverified_supplied_native_objects"] = (
        "unverified_supplied_native_objects"
    )
    attachment_headroom: Literal["not_calculated"] = "not_calculated"
    fit_status: Literal["blocked"] = "blocked"


def _text(value: object, *, maximum: int = 253) -> str | None:
    return (
        value
        if isinstance(value, str)
        and 0 < len(value) <= maximum
        and all(32 < ord(char) < 127 for char in value)
        else None
    )


def _modes(value: object) -> tuple[AccessMode, ...] | None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 4
        or len(set(item for item in value if isinstance(item, str))) != len(value)
    ):
        return None
    if any(
        item not in {"ReadWriteOnce", "ReadOnlyMany", "ReadWriteMany", "ReadWriteOncePod"}
        for item in value
    ):
        return None
    return tuple(sorted(value))


def _affinity(value: object) -> dict[str, JsonValue] | None:
    if not isinstance(value, dict) or set(value) != {"nodeSelectorTerms"}:
        return None
    terms = value["nodeSelectorTerms"]
    if not isinstance(terms, list) or len(terms) > 100:
        return None
    cleaned: list[JsonValue] = []
    for term in terms:
        if not isinstance(term, dict) or set(term) - {"matchExpressions", "matchFields"}:
            return None
        row: dict[str, JsonValue] = {}
        for field in ["matchExpressions", "matchFields"]:
            if field not in term:
                continue
            requirements = term[field]
            if not isinstance(requirements, list) or len(requirements) > 100:
                return None
            selected: list[JsonValue] = []
            for requirement in requirements:
                if not isinstance(requirement, dict) or set(requirement) != {
                    "key",
                    "operator",
                    "values",
                }:
                    return None
                key, operator, values = (
                    requirement[name] for name in ["key", "operator", "values"]
                )
                if (
                    not isinstance(key, str)
                    or not isinstance(operator, str)
                    or key
                    not in (TOPOLOGY_KEYS if field == "matchExpressions" else {"metadata.name"})
                    or operator not in {"In", "NotIn", "Exists", "DoesNotExist", "Gt", "Lt"}
                    or not isinstance(values, list)
                    or len(values) > 100
                    or any(_text(item) is None for item in values)
                ):
                    return None
                selected.append({"key": key, "operator": operator, "values": list(values)})
            row[field] = selected
        cleaned.append(row)
    return {"nodeSelectorTerms": cleaned}


def _allowed_topology(value: object) -> dict[str, JsonValue] | None:
    if not isinstance(value, list) or len(value) > 100:
        return None
    if not value:
        return {}
    terms = []
    for term in value:
        if (
            not isinstance(term, dict)
            or set(term) != {"matchLabelExpressions"}
            or not isinstance(term["matchLabelExpressions"], list)
        ):
            return None
        terms.append(
            {
                "matchExpressions": [
                    {"key": item.get("key"), "operator": "In", "values": item.get("values")}
                    if isinstance(item, dict) and set(item) == {"key", "values"}
                    else {}
                    for item in term["matchLabelExpressions"]
                ]
            }
        )
    return _affinity({"nodeSelectorTerms": terms})


def _topology_matches(
    required: dict[str, JsonValue], node: KubernetesObjectMetadata
) -> bool | None:
    node_affinity = {"requiredDuringSchedulingIgnoredDuringExecution": required}
    spec = {"affinity": {"nodeAffinity": node_affinity}}
    return _required_node_affinity(spec, node)


def project_storage_context(
    metadata: KubernetesMetadataSnapshot,
    *,
    objects: list[dict[str, Any]],
    receipts: dict[str, CollectorResult],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> StorageContextProjection:
    evaluated_at = _utc(as_of)
    if len(objects) > MAXIMUM_STORAGE_OBJECTS:
        raise ValueError("storage projection exceeds its object budget")
    audit = audit_scheduling_completeness(
        metadata,
        as_of=evaluated_at,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )
    if metadata.cluster_uid is None:
        raise ValueError("storage projection requires an exact original cluster fingerprint")
    if set(receipts) - STORAGE_KINDS:
        raise ValueError("storage projection refuses unapproved resource receipts")
    receipts = {
        key: CollectorResult.model_validate(value.model_dump()) for key, value in receipts.items()
    }
    source_issues = _receipt_gaps(
        metadata.collection,
        scope=metadata.cluster_resource_id,
        clock=evaluated_at,
        maximum_age=maximum_source_age_seconds,
    )
    for resource in ["v1/namespaces", "v1/nodes"]:
        if metadata.api_availability.get(
            resource
        ) != "available" or not metadata.resource_versions.get(resource):
            source_issues.append("incomplete_original_node_or_namespace_list")
    for receipt_kind in sorted(STORAGE_KINDS):
        if receipt_kind not in receipts:
            source_issues.append(f"missing_{receipt_kind}_receipt")
        else:
            source_issues.extend(
                f"{receipt_kind}_{gap}"
                for gap in _receipt_gaps(
                    receipts[receipt_kind],
                    scope=metadata.cluster_resource_id,
                    clock=evaluated_at,
                    maximum_age=maximum_source_age_seconds,
                )
            )
    namespaces = {item.name: item.uid for item in metadata.resources if item.kind == "Namespace"}
    nodes = {item.name: item for item in metadata.resources if item.kind == "Node"}
    identities: set[tuple[str, str, str | None]] = set()
    uids: set[str] = set()
    claims, volumes, classes, csi_nodes, drivers = [], [], [], [], []
    for item in objects:
        kind = item.get("kind")
        if (
            not isinstance(kind, str)
            or kind not in STORAGE_KINDS
            or item.get("apiVersion")
            != (
                "v1"
                if kind in {"PersistentVolume", "PersistentVolumeClaim"}
                else "storage.k8s.io/v1"
            )
        ):
            raise ValueError("storage projection requires allowlisted native API identities")
        identity = item.get("metadata")
        if (
            not isinstance(identity, dict)
            or _text(identity.get("name")) is None
            or _text(identity.get("uid"), maximum=199) is None
        ):
            raise ValueError("storage projection requires exact native identities")
        uid, name = identity["uid"], identity["name"]
        namespace = identity.get("namespace") if kind == "PersistentVolumeClaim" else None
        if kind == "PersistentVolumeClaim" and not isinstance(namespace, str):
            raise ValueError("storage claim requires an explicit Namespace identity")
        key = (kind, name, namespace)
        if uid in uids or key in identities:
            raise ValueError("storage projection refuses duplicate identities")
        uids.add(uid)
        identities.add(key)
        issues = []
        version = _text(identity.get("resourceVersion"), maximum=199)
        if version is None:
            issues.append("missing_object_version")
        base = {"uid": uid, "name": name, "resource_version": version, "issues": issues}
        spec = item.get("spec")
        spec = spec if isinstance(spec, dict) else {}
        if kind == "PersistentVolumeClaim":
            if not isinstance(namespace, str) or namespace not in namespaces:
                raise ValueError("storage claim requires an exact original Namespace")
            claims.append(
                StorageClaim(
                    **base,
                    namespace=namespace,
                    namespace_uid=namespaces.get(namespace),
                    volume_name=_text(spec.get("volumeName")),
                    storage_class_name=_text(spec.get("storageClassName")),
                    access_modes=_modes(spec.get("accessModes")),
                    volume_mode=spec.get("volumeMode")
                    if spec.get("volumeMode") in ("Filesystem", "Block")
                    else None,
                )
            )
        elif kind == "PersistentVolume":
            reference = spec.get("claimRef")
            reference = reference if isinstance(reference, dict) else {}
            csi = spec.get("csi")
            storage_type: StorageType = (
                "csi"
                if isinstance(csi, dict)
                else "local"
                if "local" in spec
                else "hostPath"
                if "hostPath" in spec
                else "other"
            )
            affinity = spec.get("nodeAffinity")
            volumes.append(
                StorageVolume(
                    **base,
                    claim_uid=_text(reference.get("uid"), maximum=199),
                    claim_name=_text(reference.get("name")),
                    claim_namespace=_text(reference.get("namespace")),
                    storage_class_name=_text(spec.get("storageClassName")),
                    access_modes=_modes(spec.get("accessModes")),
                    volume_mode=spec.get("volumeMode")
                    if spec.get("volumeMode") in ("Filesystem", "Block")
                    else None,
                    storage_type=storage_type,
                    csi_driver=_text(csi.get("driver")) if isinstance(csi, dict) else None,
                    node_affinity=_affinity(affinity.get("required"))
                    if isinstance(affinity, dict)
                    else None,
                )
            )
        elif kind == "StorageClass":
            classes.append(
                StorageClassContext(
                    **base,
                    provisioner=_text(item.get("provisioner")),
                    binding_mode=item.get("volumeBindingMode")
                    if item.get("volumeBindingMode") in ("Immediate", "WaitForFirstConsumer")
                    else None,
                    allowed_topology=_allowed_topology(item.get("allowedTopologies")),
                )
            )
        elif kind == "CSIDriver":
            drivers.append(
                CsiDriverContext(
                    **base,
                    attach_required=spec.get("attachRequired")
                    if type(spec.get("attachRequired")) is bool
                    else None,
                )
            )
        else:
            owner_refs = identity.get("ownerReferences")
            node = nodes.get(name)
            matches = (
                [
                    owner
                    for owner in owner_refs
                    if isinstance(owner, dict)
                    and node is not None
                    and (
                        owner.get("apiVersion"),
                        owner.get("kind"),
                        owner.get("name"),
                        owner.get("uid"),
                    )
                    == ("v1", "Node", node.name, node.uid)
                ]
                if isinstance(owner_refs, list)
                else []
            )
            node_uid = node.uid if node is not None and len(matches) == 1 else None
            if node_uid is None:
                issues.append("unresolved_csi_node_owner")
            entries = spec.get("drivers")
            if not isinstance(entries, list) or len(entries) > 100:
                issues.append("invalid_csi_driver_list")
                entries = []
            selected = []
            for entry in entries:
                if not isinstance(entry, dict) or _text(entry.get("name")) is None:
                    raise ValueError("CSI Node drivers require exact names")
                allocatable = entry.get("allocatable")
                count = allocatable.get("count") if isinstance(allocatable, dict) else None
                count = count if type(count) is int and 0 <= count < 2**31 else None
                keys = entry.get("topologyKeys")
                keys = (
                    tuple(sorted(keys))
                    if isinstance(keys, list)
                    and len(keys) <= 100
                    and all(isinstance(key, str) and key in TOPOLOGY_KEYS for key in keys)
                    else None
                )
                selected.append(
                    CsiNodeDriver(
                        name=entry["name"],
                        maximum_volumes=count,
                        topology_keys=keys,
                        issues=[] if count is not None else ["attachment_limit_unknown"],
                    )
                )
            if len({entry.name for entry in selected}) != len(selected):
                raise ValueError("CSI Node driver identities must be distinct")
            csi_nodes.append(
                CsiNodeContext(
                    **(base | {"issues": issues}),
                    node_uid=node_uid,
                    drivers=sorted(selected, key=lambda row: row.name),
                )
            )
    if len(claims) * len(nodes) > MAXIMUM_STORAGE_PAIRS:
        raise ValueError("storage projection exceeds its comparison budget")
    volume_map = {row.name: row for row in volumes}
    class_map = {row.name: row for row in classes}
    work = 0
    for claim in claims:
        volume = volume_map.get(claim.volume_name or "")
        storage_class = class_map.get(claim.storage_class_name or "")
        for topology in [
            volume.node_affinity if volume is not None else None,
            storage_class.allowed_topology if storage_class is not None else None,
        ]:
            work += len(nodes) * len(json.dumps(topology, allow_nan=False).encode("utf-8"))
            if work > MAXIMUM_STORAGE_WORK:
                raise ValueError("storage projection exceeds its predicate work budget")
    comparisons = []
    for claim in sorted(claims, key=lambda row: row.uid):
        volume = volume_map.get(claim.volume_name or "")
        if volume is not None and (volume.claim_uid, volume.claim_name, volume.claim_namespace) == (
            claim.uid,
            claim.name,
            claim.namespace,
        ):
            claim.bound_volume_uid = volume.uid
        else:
            claim.issues.append("unresolved_exact_claim_volume_binding")
        storage_class = class_map.get(claim.storage_class_name or "")
        for node in sorted(nodes.values(), key=lambda row: row.uid):
            volume_match = None
            class_match = None
            gaps = list(source_issues) + list(claim.issues)
            if (
                not gaps
                and volume is not None
                and volume.resource_version
                and volume.node_affinity is not None
            ):
                volume_match = _topology_matches(volume.node_affinity, node)
            if (
                not gaps
                and storage_class is not None
                and storage_class.resource_version
                and storage_class.allowed_topology is not None
            ):
                class_match = (
                    True
                    if storage_class.allowed_topology == {}
                    else _topology_matches(storage_class.allowed_topology, node)
                )
            if volume_match is None:
                gaps.append("bound_volume_topology_unknown")
            if class_match is None:
                gaps.append("storage_class_topology_unknown")
            gaps.extend(
                [
                    "storage_capacity_and_access_semantics_unverified",
                    "attachment_usage_unavailable",
                    "scheduler_configuration_unverified",
                ]
            )
            comparisons.append(
                StorageNodeComparison(
                    claim_uid=claim.uid,
                    node_uid=node.uid,
                    bound_volume_topology="matched"
                    if volume_match is True
                    else "excluded"
                    if volume_match is False
                    else "unknown",
                    storage_class_topology="matched"
                    if class_match is True
                    else "excluded"
                    if class_match is False
                    else "unknown",
                    reason_codes=sorted(set(gaps)),
                )
            )
    result = StorageContextProjection(
        tenant_id=metadata.tenant_id,
        cluster_resource_id=metadata.cluster_resource_id,
        cluster_uid=metadata.cluster_uid,
        evaluated_at=evaluated_at,
        maximum_source_age_seconds=maximum_source_age_seconds,
        input_digest=digest_json(
            {
                "metadata": metadata.model_dump(mode="json"),
                "receipts": {
                    key: receipt.model_dump(mode="json") for key, receipt in receipts.items()
                },
                "claims": [
                    row.model_dump(mode="json") for row in sorted(claims, key=lambda row: row.uid)
                ],
                "volumes": [
                    row.model_dump(mode="json") for row in sorted(volumes, key=lambda row: row.uid)
                ],
                "classes": [
                    row.model_dump(mode="json") for row in sorted(classes, key=lambda row: row.uid)
                ],
                "csi_nodes": [
                    row.model_dump(mode="json")
                    for row in sorted(csi_nodes, key=lambda row: row.uid)
                ],
                "drivers": [
                    row.model_dump(mode="json") for row in sorted(drivers, key=lambda row: row.uid)
                ],
            }
        ),
        audit=audit,
        receipts=receipts,
        source_issues=sorted(set(source_issues)),
        claims=sorted(claims, key=lambda row: row.uid),
        volumes=sorted(volumes, key=lambda row: row.uid),
        storage_classes=sorted(classes, key=lambda row: row.uid),
        csi_nodes=sorted(csi_nodes, key=lambda row: row.uid),
        csi_drivers=sorted(drivers, key=lambda row: row.uid),
        comparisons=comparisons,
    )
    if len(result.model_dump_json().encode("utf-8")) > MAXIMUM_STORAGE_BYTES:
        raise ValueError("storage projection exceeds its output byte budget")
    return result
