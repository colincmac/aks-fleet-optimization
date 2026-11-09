from __future__ import annotations

from collections import Counter
from typing import Literal

from aks_fleet_efficiency.models import (
    AzureClusterInventory,
    CapacityInventory,
    CapacityPoolEvidence,
    KubernetesMetadataSnapshot,
    NapManagedNode,
    NapPoolEvidence,
    PoolIntentBinding,
    UtcDatetime,
)

NAP_APIS = (
    "karpenter.sh/v1/nodepools",
    "karpenter.sh/v1/nodeclaims",
    "karpenter.azure.com/v1beta1/aksnodeclasses",
)


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
        result.nap_pools.append(
            NapPoolEvidence(
                uid=pool.uid,
                name=pool.name,
                nodeclass_uid=nodeclass_uid,
                requirement_count=len(requirements) if isinstance(requirements, list) else None,
                taint_count=len(taints) if isinstance(taints, list) else None,
                disruption_budget_count=len(budgets) if isinstance(budgets, list) else None,
                limits_observed=isinstance(pool.spec.get("limits"), dict),
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
    result.issues = sorted(set(result.issues))
    return result
