from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from aks_fleet_efficiency.models import (
    AzureClusterInventory,
    CapacityInventory,
    CapacityPoolEvidence,
    CollectionStatus,
    KubernetesMetadataSnapshot,
    NapDisruptionBudget,
    NapManagedNode,
    NapPoolEvidence,
    NapTopologyContext,
    NapZoneRequirement,
    PoolIntentBinding,
    UtcDatetime,
)

NAP_APIS = (
    "karpenter.sh/v1/nodepools",
    "karpenter.sh/v1/nodeclaims",
    "karpenter.azure.com/v1beta1/aksnodeclasses",
)
MAXIMUM_NAP_REQUIREMENTS = 100
MAXIMUM_NAP_ZONE_VALUES = 1000


def _zone_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[-A-Za-z0-9_.]*[A-Za-z0-9])?", value) is not None
    )


def _zone_requirements(requirements: object) -> NapTopologyContext:
    context = NapTopologyContext()
    if not isinstance(requirements, list):
        context.requirement_issues.append("unknown_nap_requirements")
        return context
    if len(requirements) > MAXIMUM_NAP_REQUIREMENTS:
        context.requirement_issues.append("nap_requirement_budget_exceeded")
        return context
    context.zone_requirements = []
    value_count = 0
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("key"), str):
            context.requirement_issues.append("unclassified_nap_requirement")
            continue
        if requirement["key"] != "topology.kubernetes.io/zone":
            continue
        operator, values = requirement.get("operator"), requirement.get("values")
        minimum = requirement.get("minValues")
        if isinstance(values, list):
            value_count += len(values)
        if value_count > MAXIMUM_NAP_ZONE_VALUES:
            context.zone_requirements = None
            context.requirement_issues = ["nap_zone_value_budget_exceeded"]
            return context
        if (
            operator not in ("In", "NotIn", "Exists", "DoesNotExist")
            or not isinstance(values, list)
            or len(values) > 100
            or any(not _zone_value(value) for value in values)
            or len(set(values)) != len(values)
            or (operator in ("In", "NotIn") and not values)
            or (operator in ("Exists", "DoesNotExist") and values)
            or (
                minimum is not None
                and (
                    isinstance(minimum, bool)
                    or not isinstance(minimum, int)
                    or not 1 <= minimum <= 100
                    or operator not in ("In", "Exists")
                )
            )
        ):
            context.requirement_issues.append("unsupported_nap_zone_requirement")
            continue
        context.zone_requirements.append(
            NapZoneRequirement(
                operator=operator,
                values=sorted(values),
                min_values=minimum,
            )
        )
    context.requirement_issues = sorted(set(context.requirement_issues))
    context.zone_requirements.sort(
        key=lambda item: (item.operator, item.values, item.min_values or 0)
    )
    if context.requirement_issues:
        context.requirement_status = "partial" if context.zone_requirements else "unknown"
        if not context.zone_requirements:
            context.zone_requirements = None
    else:
        context.requirement_status = "observed"
    return context


def _observed_nap_zones(metadata: KubernetesMetadataSnapshot, capacity: CapacityInventory) -> None:
    required = ("v1/nodes", "karpenter.sh/v1/nodepools", "karpenter.sh/v1/nodeclaims")
    complete = (
        metadata.collection.status == CollectionStatus.COMPLETE
        and metadata.collection.requested_scope == [capacity.cluster_resource_id]
        and metadata.cluster_resource_id == capacity.cluster_resource_id
        and metadata.cluster_uid == capacity.cluster_uid
        and metadata.cluster_uid is not None
        and capacity.provisioning_mode == "Auto"
        and all(
            metadata.api_availability.get(key) == "available"
            and metadata.resource_versions.get(key)
            for key in required
        )
        and not {
            "unresolved_nap_nodeclaim",
            "ambiguous_nap_nodeclaim",
            "unverified_nap_provisioning_mode",
        }.intersection(capacity.issues)
        and len({item.uid for item in metadata.resources}) == len(metadata.resources)
    )
    nodes = {
        item.uid: item
        for item in metadata.resources
        if item.kind == "Node" and item.api_version == "v1"
    }
    members: dict[str, list[str]] = {}
    for binding in capacity.nap_managed_nodes:
        members.setdefault(binding.nodepool_uid, []).append(binding.node_uid)
    for pool in capacity.nap_pools:
        context = pool.topology
        if not complete:
            context.observation_issues.append("incomplete_or_unresolved_nap_zone_inventory")
            continue
        context.observation_status = "current-bound-only"
        context.observed_zone_nodes = {}
        context.unknown_zone_node_uids = []
        for uid in sorted(members.get(pool.uid, [])):
            node = nodes.get(uid)
            zone = node.labels.get("topology.kubernetes.io/zone") if node else None
            if not isinstance(zone, str) or not _zone_value(zone):
                context.unknown_zone_node_uids.append(uid)
            else:
                context.observed_zone_nodes.setdefault(zone, []).append(uid)
        context.observed_zone_nodes = dict(sorted(context.observed_zone_nodes.items()))
        if context.unknown_zone_node_uids:
            context.observation_issues.append("unknown_observed_node_zone")


def _budget_context(value: object) -> NapDisruptionBudget:
    result = NapDisruptionBudget()
    if not isinstance(value, dict):
        result.issues.extend(["invalid_budget_nodes", "unknown_budget_reasons"])
        return result
    nodes = value.get("nodes")
    if (
        isinstance(nodes, str)
        and 1 <= len(nodes) <= 64
        and nodes.isascii()
        and (
            nodes.isdecimal()
            or (nodes.endswith("%") and nodes[:-1].isdecimal() and int(nodes[:-1]) <= 100)
        )
    ):
        result.nodes = nodes
    else:
        result.issues.append("invalid_budget_nodes")
    reasons = value.get("reasons")
    if reasons is None:
        result.issues.append("unknown_budget_reasons")
    elif (
        not isinstance(reasons, list)
        or len(reasons) > 3
        or any(
            not isinstance(item, str) or item not in {"Empty", "Underutilized", "Drifted"}
            for item in reasons
        )
        or len(set(reasons)) != len(reasons)
    ):
        result.issues.append("unsupported_budget_reasons")
    else:
        result.reasons = reasons
    for field, maximum in [("schedule", 256), ("duration", 64)]:
        raw = value.get(field)
        if raw is None:
            continue
        if (
            isinstance(raw, str)
            and raw.strip()
            and len(raw) <= maximum
            and all(ord(character) >= 32 for character in raw)
        ):
            setattr(result, field, raw)
        else:
            result.issues.append(
                "invalid_budget_schedule" if field == "schedule" else "invalid_budget_duration"
            )
    if (result.schedule is None) != (result.duration is None):
        result.issues.append("unpaired_budget_schedule_duration")
    return result


def normalize_capacity(
    inventory: AzureClusterInventory,
    observed_at: UtcDatetime,
    metadata: KubernetesMetadataSnapshot | None,
    intents: list[PoolIntentBinding],
) -> CapacityInventory:
    result = CapacityInventory(
        cluster_resource_id=inventory.resource_id,
        cluster_uid=metadata.cluster_uid if metadata else None,
        azure_observed_at=observed_at,
        kubernetes_observed_at=metadata.generated_at if metadata else None,
        provisioning_mode=inventory.node_provisioning_mode,
        pools=[
            CapacityPoolEvidence.model_validate(
                pool.model_dump()
                | {
                    "intent": next(
                        (item for item in intents if item.pool_resource_id == pool.resource_id),
                        None,
                    )
                }
            )
            for pool in sorted(inventory.node_pools, key=lambda item: item.resource_id)
        ],
        nap_api_status={key: "unknown" for key in NAP_APIS},
    )
    if metadata is None:
        result.issues.append("missing_capacity_metadata")
        return result
    for key in NAP_APIS:
        state: Literal["available", "absent", "unsupported", "unknown"] = (
            metadata.api_availability.get(key, "unknown")
        )
        result.nap_api_status[key] = (
            "unknown" if state == "available" and not metadata.resource_versions.get(key) else state
        )
    resources = {item.uid: item for item in metadata.resources}
    for pool in sorted(metadata.resources, key=lambda item: item.uid):
        if pool.kind != "NodePool" or pool.api_version != "karpenter.sh/v1":
            continue
        if result.nap_api_status[NAP_APIS[0]] != "available":
            result.issues.append("unverified_nap_nodepool")
            continue
        template = pool.spec.get("template")
        spec = template.get("spec") if isinstance(template, dict) else None
        ref = spec.get("nodeClassRef") if isinstance(spec, dict) else None
        nodeclasses = [
            item
            for item in metadata.resources
            if isinstance(ref, dict)
            and ref.get("group") == "karpenter.azure.com"
            and ref.get("kind") == "AKSNodeClass"
            and item.kind == "AKSNodeClass"
            and item.api_version == "karpenter.azure.com/v1beta1"
            and item.name == ref.get("name")
        ]
        nodeclass_uid = (
            nodeclasses[0].uid
            if len(nodeclasses) == 1 and result.nap_api_status[NAP_APIS[2]] == "available"
            else None
        )
        disruption = pool.spec.get("disruption")
        budgets = disruption.get("budgets") if isinstance(disruption, dict) else None
        requirements = spec.get("requirements") if isinstance(spec, dict) else None
        taints = spec.get("taints") if isinstance(spec, dict) else None
        startup_taints = spec.get("startupTaints") if isinstance(spec, dict) else None
        replicas = pool.spec.get("replicas")
        replicas_observed = "replicas" in pool.spec
        static_replicas = (
            replicas
            if isinstance(replicas, int) and not isinstance(replicas, bool) and replicas >= 0
            else None
        )
        supply_mode: Literal["static", "dynamic", "unknown"] = (
            "static"
            if static_replicas is not None
            else "unknown"
            if replicas_observed
            else "dynamic"
        )
        if supply_mode == "unknown":
            result.issues.append("invalid_nap_static_replicas")
        consolidation_policy = (
            disruption.get("consolidationPolicy") if isinstance(disruption, dict) else None
        )
        consolidate_after = (
            disruption.get("consolidateAfter") if isinstance(disruption, dict) else None
        )
        zero_node_budget = (
            any(
                isinstance(item, dict) and str(item.get("nodes", "")).strip() == "0"
                for item in budgets
            )
            if isinstance(budgets, list)
            else None
        )
        result.nap_pools.append(
            NapPoolEvidence(
                uid=pool.uid,
                name=pool.name,
                nodeclass_uid=nodeclass_uid,
                supply_mode=supply_mode,
                static_replicas=static_replicas,
                requirement_count=len(requirements) if isinstance(requirements, list) else None,
                taint_count=len(taints) if isinstance(taints, list) else None,
                startup_taint_count=(
                    len(startup_taints) if isinstance(startup_taints, list) else None
                ),
                consolidation_policy=(
                    consolidation_policy
                    if isinstance(consolidation_policy, str) and consolidation_policy
                    else None
                ),
                consolidate_after=(
                    consolidate_after
                    if isinstance(consolidate_after, str) and consolidate_after
                    else None
                ),
                disruption_budget_count=len(budgets) if isinstance(budgets, list) else None,
                disruption_budgets=[_budget_context(item) for item in budgets]
                if isinstance(budgets, list)
                else None,
                zero_node_disruption_budget_configured=zero_node_budget,
                limits_observed=isinstance(pool.spec.get("limits"), dict),
                topology=_zone_requirements(requirements),
            )
        )
    if result.nap_api_status[NAP_APIS[1]] == "available":
        for claim in sorted(metadata.resources, key=lambda item: item.uid):
            if claim.kind != "NodeClaim" or claim.api_version != "karpenter.sh/v1":
                continue
            owners = [owner for owner in claim.owner_references if owner.get("controller") is True]
            owner = owners[0] if len(owners) == 1 else {}
            owner_pool = resources.get(str(owner.get("uid", "")))
            provider = claim.status.get("providerID")
            nodes = [
                item
                for item in metadata.resources
                if item.kind == "Node"
                and item.api_version == "v1"
                and item.name == claim.status.get("nodeName")
                and isinstance(provider, str)
                and provider
                and item.spec.get("providerID") == provider
                and any(
                    node.node_uid == item.uid
                    and node.provider_id == provider
                    and node.azure_resource_id is not None
                    and node.state != "mismatch"
                    for node in metadata.nodes
                )
            ]
            if (
                owner_pool is None
                or owner.get("apiVersion") != "karpenter.sh/v1"
                or owner.get("kind") != "NodePool"
                or owner.get("name") != owner_pool.name
                or owner_pool.uid not in {item.uid for item in result.nap_pools}
                or metadata.api_availability.get("v1/nodes") != "available"
                or not metadata.resource_versions.get("v1/nodes")
                or len(nodes) != 1
            ):
                result.issues.append("unresolved_nap_nodeclaim")
            else:
                result.nap_managed_nodes.append(
                    NapManagedNode(
                        node_uid=nodes[0].uid,
                        nodeclaim_uid=claim.uid,
                        nodepool_uid=owner_pool.uid,
                    )
                )
    node_counts = Counter(item.node_uid for item in result.nap_managed_nodes)
    ambiguous_nodes = {uid for uid, count in node_counts.items() if count > 1}
    if ambiguous_nodes:
        result.nap_managed_nodes = [
            item for item in result.nap_managed_nodes if item.node_uid not in ambiguous_nodes
        ]
        result.issues.append("ambiguous_nap_nodeclaim")
    if result.nap_managed_nodes and inventory.node_provisioning_mode != "Auto":
        result.nap_managed_nodes = []
        result.issues.append("unverified_nap_provisioning_mode")
    _observed_nap_zones(metadata, result)
    result.issues = sorted(set(result.issues))
    return result
