from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.collectors.kubernetes_metadata import project_metadata
from aks_fleet_efficiency.models import DaemonSetCoverageEvidence, KubernetesMetadataSnapshot
from aks_fleet_efficiency.node_history import Digest, Reference, _receipt_gaps, _utc
from aks_fleet_efficiency.scheduling import (
    DaemonSetStatusProjection,
    _all_matches,
    _hard_taint_match,
    _required_node_affinity,
    _selector_match,
    normalize_scheduling,
    project_daemonset_status,
)

MAXIMUM_DAEMONSET_MEMBERSHIP_OBJECTS = 100_000
MAXIMUM_DAEMONSET_MEMBERSHIP_PAIRS = 100_000
MAXIMUM_DAEMONSET_MEMBERSHIP_WORK = 1_000_000
MAXIMUM_DAEMONSET_MEMBERSHIP_BYTES = 32 * 1024 * 1024


class _MembershipModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DaemonSetNodeSelection(_MembershipModel):
    daemonset_uid: Reference
    node_uid: Reference
    selection: Literal["selected", "excluded", "unknown"]
    reason_codes: list[str]
    resource_and_storage_fit: Literal["not_calculated"] = "not_calculated"


class DaemonSetModeledMembership(_MembershipModel):
    daemonset_uid: Reference
    namespace_uid: Reference
    generation: Annotated[int, Field(ge=1)] | None
    modeled_desired_node_uids: list[Reference] | None
    original_observed_coverage: DaemonSetCoverageEvidence | None
    reason_codes: list[str]
    reconciliation_completion: Literal["unknown"] = "unknown"


class DaemonSetMembershipReview(_MembershipModel):
    schema_version: Literal["1.0"] = "1.0"
    mapping_reference: Literal["kubernetes-daemon-controller@v1.36.0"] = (
        "kubernetes-daemon-controller@v1.36.0"
    )
    status_projection: DaemonSetStatusProjection
    approved_binding_digest: Digest
    source_issues: list[str]
    daemonsets: list[DaemonSetModeledMembership]
    comparisons: list[DaemonSetNodeSelection]
    desired_membership_admission: Literal["unverified"] = "unverified"
    fit_status: Literal["blocked"] = "blocked"
    disruption_feasibility: Literal["unknown"] = "unknown"


def _controller_tolerations(spec: dict[str, Any]) -> dict[str, Any] | None:
    original = spec.get("tolerations")
    if not isinstance(original, list) or type(spec.get("hostNetwork")) is not bool:
        return None
    defaults = [
        {"key": f"node.kubernetes.io/{condition}", "operator": "Exists", "effect": effect}
        for condition, effect in [
            ("not-ready", "NoExecute"),
            ("unreachable", "NoExecute"),
            ("disk-pressure", "NoSchedule"),
            ("memory-pressure", "NoSchedule"),
            ("pid-pressure", "NoSchedule"),
            ("unschedulable", "NoSchedule"),
        ]
    ]
    if spec["hostNetwork"]:
        defaults.append(
            {
                "key": "node.kubernetes.io/network-unavailable",
                "operator": "Exists",
                "effect": "NoSchedule",
            }
        )
    return {"tolerations": [*original, *defaults]}


def review_daemonset_membership(
    metadata: KubernetesMetadataSnapshot,
    *,
    daemonsets: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> DaemonSetMembershipReview:
    evaluated_at = _utc(as_of)
    if (
        len(daemonsets) + len(nodes) > MAXIMUM_DAEMONSET_MEMBERSHIP_OBJECTS
        or len(metadata.resources) > MAXIMUM_DAEMONSET_MEMBERSHIP_OBJECTS
    ):
        raise ValueError("DaemonSet membership exceeds its object budget")
    if len(daemonsets) * len(nodes) > MAXIMUM_DAEMONSET_MEMBERSHIP_PAIRS:
        raise ValueError("DaemonSet membership exceeds its pair budget")
    status = project_daemonset_status(
        metadata,
        daemonsets=daemonsets,
        as_of=evaluated_at,
        maximum_source_age_seconds=maximum_source_age_seconds,
    )
    original_nodes = {row.uid: row for row in metadata.resources if row.kind == "Node"}
    projected_nodes = {}
    node_versions = {}
    for row in nodes:
        if row.get("apiVersion") != "v1" or row.get("kind") != "Node":
            raise ValueError("DaemonSet membership requires native v1 Node identities")
        projected = project_metadata("v1/nodes", row)
        if projected.uid in projected_nodes or original_nodes.get(projected.uid) != projected:
            raise ValueError(
                "DaemonSet membership requires each original approved Node exactly once"
            )
        projected_nodes[projected.uid] = projected
        version = row.get("metadata", {}).get("resourceVersion")
        node_versions[projected.uid] = isinstance(version, str) and 0 < len(version) <= 199
    if projected_nodes.keys() != original_nodes.keys():
        raise ValueError("DaemonSet membership requires the complete original Node roster")
    source_issues = list(status.source_issues)
    source_issues.extend(
        _receipt_gaps(
            metadata.collection,
            scope=metadata.cluster_resource_id,
            clock=evaluated_at,
            maximum_age=maximum_source_age_seconds,
        )
    )
    if metadata.api_availability.get(
        "v1/nodes"
    ) != "available" or not metadata.resource_versions.get("v1/nodes"):
        source_issues.append("incomplete_original_node_list")
    work = 0
    templates = {}
    for row in daemonsets:
        template = row.get("spec", {}).get("template")
        spec = template.get("spec") if isinstance(template, dict) else None
        spec = spec if isinstance(spec, dict) else {}
        uid = row["metadata"]["uid"]
        templates[uid] = spec
        selected_fields = {
            key: spec.get(key)
            for key in ["nodeName", "nodeSelector", "affinity", "tolerations", "hostNetwork"]
        }
        work += len(json.dumps(selected_fields, allow_nan=False).encode("utf-8")) * len(nodes)
        if work > MAXIMUM_DAEMONSET_MEMBERSHIP_WORK:
            raise ValueError("DaemonSet membership exceeds its predicate work budget")
    coverage = {row.daemonset_uid: row for row in normalize_scheduling(metadata).daemonset_coverage}
    native = {row["metadata"]["uid"]: row for row in daemonsets}
    comparisons = []
    memberships = []
    for controller in status.daemonsets:
        spec = templates[controller.daemonset_uid]
        tolerations = _controller_tolerations(spec)
        rows = []
        for node in sorted(projected_nodes.values(), key=lambda row: row.uid):
            reasons = list(source_issues)
            if not node_versions[node.uid]:
                reasons.append("node_object_version_unknown")
            name = spec.get("nodeName")
            name_match = None if not isinstance(name, str) else name in ("", node.name)
            selector = (
                _selector_match({"matchLabels": spec["nodeSelector"]}, node.labels)
                if "nodeSelector" in spec
                else None
            )
            affinity = _required_node_affinity(spec, node)
            taints = None if tolerations is None else _hard_taint_match(tolerations, node)
            checks = {
                "template_node_name": name_match,
                "template_node_selector": selector,
                "required_node_affinity": affinity,
                "controller_taint_tolerations": taints,
            }
            reasons.extend(f"{key}_unknown" for key, value in checks.items() if value is None)
            reasons.extend(
                f"{key}_excludes_node" for key, value in checks.items() if value is False
            )
            selection = (
                None
                if source_issues or not node_versions[node.uid]
                else _all_matches(list(checks.values()))
            )
            rows.append(
                DaemonSetNodeSelection(
                    daemonset_uid=controller.daemonset_uid,
                    node_uid=node.uid,
                    selection="selected"
                    if selection is True
                    else "excluded"
                    if selection is False
                    else "unknown",
                    reason_codes=sorted(set(reasons)),
                )
            )
        reasons = list(source_issues)
        if controller.generation_relation != "equal":
            reasons.append("controller_generation_not_equal")
        if native[controller.daemonset_uid]["metadata"].get("deletionTimestamp") is not None:
            reasons.append("deleting_controller")
        if any(row.selection == "unknown" for row in rows):
            reasons.append("unknown_node_selection")
        memberships.append(
            DaemonSetModeledMembership(
                daemonset_uid=controller.daemonset_uid,
                namespace_uid=controller.namespace_uid,
                generation=controller.metadata_generation,
                modeled_desired_node_uids=None
                if reasons
                else [row.node_uid for row in rows if row.selection == "selected"],
                original_observed_coverage=coverage.get(controller.daemonset_uid),
                reason_codes=sorted(set(reasons)),
            )
        )
        comparisons.extend(rows)
    result = DaemonSetMembershipReview(
        status_projection=status,
        approved_binding_digest=digest_json(
            {
                "status": status.model_dump(mode="json"),
                "nodes": [
                    row.model_dump(mode="json")
                    for row in sorted(projected_nodes.values(), key=lambda row: row.uid)
                ],
                "comparisons": [row.model_dump(mode="json") for row in comparisons],
            }
        ),
        source_issues=sorted(set(source_issues)),
        daemonsets=memberships,
        comparisons=comparisons,
    )
    if len(result.model_dump_json().encode("utf-8")) > MAXIMUM_DAEMONSET_MEMBERSHIP_BYTES:
        raise ValueError("DaemonSet membership exceeds its output byte budget")
    return result
