from __future__ import annotations

from aks_fleet_efficiency.models import (
    KubernetesMetadataSnapshot,
    SchedulingConstraint,
    SchedulingInventory,
    SchedulingPodEvidence,
)
from aks_fleet_efficiency.workload_normalization import _owner_matches

CONTROLLERS = {
    "Deployment": "apps/v1/deployments",
    "StatefulSet": "apps/v1/statefulsets",
    "DaemonSet": "apps/v1/daemonsets",
    "Job": "batch/v1/jobs",
}


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
                elif value.get("whenUnsatisfiable") in ("DoNotSchedule", "ScheduleAnyway"):
                    signal = (
                        "hard_topology_spread"
                        if value["whenUnsatisfiable"] == "DoNotSchedule"
                        else "soft_topology_spread"
                    )
                    item.constraints[signal] = item.constraints.get(signal, 0) + 1
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
    result.unobserved_context.sort()
    return SchedulingInventory.model_validate(result)
