from __future__ import annotations

from datetime import datetime
from math import isfinite

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    DaemonSetPodOverhead,
    Evidence,
    NapPoolEvidence,
    Recommendation,
    Severity,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment
from aks_fleet_efficiency.rules.scheduling import assess_scheduling


def assess_capacity(
    cluster: ClusterSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    inventory = cluster.capacity
    reasons = []
    pools = []
    if inventory is None:
        reasons.append("missing_capacity_inventory")
    else:
        if (
            inventory.cluster_resource_id != cluster.resource_id
            or inventory.cluster_uid is None
            or inventory.cluster_uid != cluster.uid
        ):
            reasons.append("capacity_identity_mismatch")
        for observed_at in [inventory.azure_observed_at, inventory.kubernetes_observed_at]:
            if observed_at is None:
                reasons.append("missing_capacity_metadata")
            elif observed_at > evaluated_at:
                reasons.append("future_capacity_inventory")
            elif (
                evaluated_at - observed_at
            ).total_seconds() > config.thresholds.maximum_evidence_age_hours * 3600:
                reasons.append("stale_capacity_inventory")
        ids = [pool.resource_id for pool in inventory.pools]
        if not ids and not inventory.nap_pools and not inventory.nap_managed_nodes:
            reasons.append("missing_capacity_supply")
        if len(set(ids)) != len(ids):
            reasons.append("ambiguous_capacity_identity")
        for pool in inventory.pools:
            if pool.resource_id != f"{cluster.resource_id}/agentPools/{pool.name}":
                reasons.append("capacity_pool_identity_mismatch")
            intent = pool.intent
            if intent is not None and (
                intent.cluster_resource_id != cluster.resource_id
                or intent.pool_resource_id != pool.resource_id
            ):
                reasons.append("capacity_intent_identity_mismatch")
            pools.append(
                {
                    "resource_id": pool.resource_id,
                    "management": (
                        "unknown"
                        if pool.autoscaling_enabled is None
                        else "cas"
                        if pool.autoscaling_enabled
                        else "fixed"
                    ),
                    "role": pool.mode or "unknown",
                    "spot": pool.spot,
                    "os_type": pool.os_type,
                    "vm_size": pool.vm_size,
                    "zones": pool.zones,
                    "node_count": pool.node_count,
                    "min_count": pool.min_count,
                    "max_count": pool.max_count,
                    "fixed_bounds": (
                        pool.min_count == pool.max_count
                        if pool.autoscaling_enabled is True
                        and pool.min_count is not None
                        and pool.max_count is not None
                        else None
                    ),
                    "intent": intent.classification if intent else "unknown",
                    "intent_owner": intent.owner if intent else None,
                    "intent_reference": intent.reference if intent else None,
                    "intent_is_approval": False,
                }
            )
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=pack.title,
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            category="node-pool-efficiency",
            evidence=[
                Evidence(
                    metric="current_pool_management",
                    value=f"{pool['resource_id']}: {pool['management']}; intent={pool['intent']}",
                    unit="classification",
                    source="azure-inventory"
                    if pool["intent"] == "unknown"
                    else "azure-inventory + owner-declaration",
                )
                for pool in pools
            ]
            + [
                Evidence(
                    metric="current_node_provisioning_mode",
                    value=inventory.provisioning_mode if inventory else None,
                    unit="mode",
                    source="azure-inventory",
                ),
                Evidence(
                    metric="uid_provider_bound_nap_nodes",
                    value=len(inventory.nap_managed_nodes) if inventory else None,
                    unit="observed nodes; not complete supply or removable nodes",
                    source="kubernetes-metadata",
                ),
                Evidence(
                    metric="nap_eligibility",
                    value=(
                        "unknown: network, identity, quota/SKU, workload/disruption fit, "
                        "operational acceptance"
                    ),
                    unit="unverified prerequisites",
                    source="not collected",
                ),
                Evidence(
                    metric="nap_configuration_issues",
                    value=", ".join(inventory.issues) if inventory and inventory.issues else None,
                    unit="reason codes; no attestation",
                    source="kubernetes-metadata",
                ),
            ],
            metadata={
                "current_only": True,
                "provisioning_mode": inventory.provisioning_mode if inventory else None,
                "pools": pools,
                "nap_api_status": inventory.nap_api_status if inventory else {},
                "nap_pools": [item.model_dump() for item in inventory.nap_pools]
                if inventory
                else [],
                "nap_managed_nodes": [item.model_dump() for item in inventory.nap_managed_nodes]
                if inventory
                else [],
                "capacity_issues": inventory.issues if inventory else [],
                "nap_prerequisites": {
                    "windows": (
                        "unsupported"
                        if any(pool["os_type"] == "Windows" for pool in pools)
                        else "unknown"
                        if not pools or any(pool["os_type"] is None for pool in pools)
                        else "not_observed"
                    ),
                    "cas_transition": (
                        "review_required"
                        if any(pool["management"] == "cas" for pool in pools)
                        else "unknown"
                    ),
                    "network": "unknown",
                    "identity": "unknown",
                    "regional_sku_quota": "unknown",
                    "workload_disruption_fit": "unknown",
                    "stop_start_and_egress_acceptance": "unknown",
                    "migration_approval": "not_granted",
                },
            },
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
        ),
        metrics=None,
        reasons=reasons,
        has_signal=inventory is not None,
    )


CAPACITY_EVALUATORS = {"capacity-review": assess_capacity}


def nap_attribution_observed(cluster: ClusterSnapshot) -> bool:
    capacity, scheduling = cluster.capacity, cluster.scheduling
    return bool(
        capacity
        and scheduling
        and scheduling.resource_accounting_observed
        and capacity.provisioning_mode == "Auto"
        and capacity.nap_api_status.get("karpenter.sh/v1/nodepools") == "available"
        and capacity.nap_api_status.get("karpenter.sh/v1/nodeclaims") == "available"
    )


def assess_nap_consolidation_readiness(
    cluster: ClusterSnapshot,
    pool: NapPoolEvidence,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    capacity = cluster.capacity
    scheduling = cluster.scheduling
    reasons: list[str] = []
    if capacity is None:
        reasons.append("missing_capacity_inventory")
    else:
        reasons.extend(issue for issue in capacity.issues if issue != "invalid_nap_static_replicas")
        if pool.supply_mode == "unknown":
            reasons.append("invalid_nap_static_replicas")
        if (
            capacity.cluster_resource_id != cluster.resource_id
            or capacity.cluster_uid != cluster.uid
        ):
            reasons.append("capacity_identity_mismatch")
        for observed_at in [capacity.azure_observed_at, capacity.kubernetes_observed_at]:
            if observed_at is None:
                reasons.append("missing_capacity_metadata")
            elif observed_at > evaluated_at:
                reasons.append("future_capacity_inventory")
            elif (
                evaluated_at - observed_at
            ).total_seconds() > config.thresholds.maximum_evidence_age_hours * 3600:
                reasons.append("stale_capacity_inventory")
        if pool.nodeclass_uid is None:
            reasons.append("missing_nap_nodeclass_binding")
        if pool.consolidation_policy is None:
            reasons.append("missing_nap_consolidation_policy")
        if (
            pool.disruption_budget_count is None
            or pool.zero_node_disruption_budget_configured is None
        ):
            reasons.append("missing_nap_disruption_budget")

    hard_constraints = {
        "node_selector",
        "required_node_affinity",
        "required_pod_affinity",
        "required_pod_anti_affinity",
        "hard_topology_spread",
        "persistent_volume_claims",
        "priority_class",
        "runtime_class",
        "custom_scheduler",
    }
    pods = []
    pdbs = []
    if scheduling is None:
        reasons.append("missing_scheduling_inventory")
    else:
        reasons.extend(scheduling.issues)
        if (
            scheduling.cluster_resource_id != cluster.resource_id
            or scheduling.cluster_uid != cluster.uid
        ):
            reasons.append("scheduling_identity_mismatch")
        if scheduling.observed_at > evaluated_at:
            reasons.append("future_scheduling_inventory")
        elif (
            evaluated_at - scheduling.observed_at
        ).total_seconds() > config.thresholds.maximum_evidence_age_hours * 3600:
            reasons.append("stale_scheduling_inventory")
        members = (
            {item.node_uid for item in capacity.nap_managed_nodes if item.nodepool_uid == pool.uid}
            if capacity
            else set()
        )
        pods = [
            item
            for item in scheduling.pods
            if item.namespace not in config.excluded_namespaces and item.node_uid in members
        ]
        namespaces = {item.namespace for item in pods}
        pdbs = [item for item in scheduling.pdbs if item.namespace in namespaces]
        reasons.extend(
            issue for pod in pods for issue in pod.issues if issue != "unresolved_workload_identity"
        )

    attribution = nap_attribution_observed(cluster)
    hard_placement_pods = (
        sum(bool(set(pod.constraints) & hard_constraints) for pod in pods) if attribution else None
    )
    local_storage_pods = (
        sum("local_emptydir_volumes" in pod.constraints for pod in pods) if attribution else None
    )
    unresolved_owner_pods = (
        sum("unresolved_workload_identity" in pod.issues for pod in pods) if attribution else None
    )
    pdb_inventory_observed = bool(
        attribution
        and scheduling
        and "policy/v1/poddisruptionbudgets" not in scheduling.unobserved_context
    )
    zero_disruption_pdbs = (
        sum(pdb.disruptions_allowed == 0 for pdb in pdbs) if pdb_inventory_observed else None
    )
    unknown_pdb_availability = (
        sum(bool(pdb.issues) or pdb.disruptions_allowed is None for pdb in pdbs)
        if pdb_inventory_observed
        else None
    )
    blockers: list[str] = []
    if pool.consolidation_policy == "WhenEmpty":
        blockers.append("consolidation_policy_when_empty")
    if pool.zero_node_disruption_budget_configured is True:
        blockers.append("zero_node_disruption_budget")
    if hard_placement_pods:
        blockers.append("hard_placement_constraints")
    if local_storage_pods:
        blockers.append("local_storage_context")
    if unresolved_owner_pods:
        blockers.append("unresolved_workload_ownership")
    if zero_disruption_pdbs:
        blockers.append("namespace_pdb_zero_disruptions")
    if unknown_pdb_availability:
        blockers.append("pdb_availability_unknown")

    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=pack.title,
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            category="node-pool-efficiency",
            evidence=[
                Evidence(
                    metric="nap_consolidation_policy",
                    value=pool.consolidation_policy,
                    unit="current NodePool policy",
                    source="kubernetes-metadata",
                ),
                Evidence(
                    metric="zero_node_disruption_budget",
                    value=pool.zero_node_disruption_budget_configured,
                    unit="configured literal zero-node budgets",
                    source="kubernetes-metadata",
                ),
                Evidence(
                    metric="hard_placement_constraint_pods",
                    value=hard_placement_pods,
                    unit="current Pods",
                    source="kubernetes-metadata",
                ),
                Evidence(
                    metric="nap_observed_zone_count",
                    value=len(pool.topology.observed_zone_nodes)
                    if pool.topology.observed_zone_nodes is not None
                    and not pool.topology.unknown_zone_node_uids
                    else None,
                    unit="distinct labels on current bound Nodes; not eligible domains",
                    source="kubernetes-metadata",
                ),
                Evidence(
                    metric="nap_unknown_zone_node_count",
                    value=len(pool.topology.unknown_zone_node_uids)
                    if pool.topology.unknown_zone_node_uids is not None
                    else None,
                    unit="current bound Nodes with unknown zone labels",
                    source="kubernetes-metadata",
                ),
                Evidence(
                    metric="namespace_pdbs_with_zero_disruptions",
                    value=zero_disruption_pdbs,
                    unit="current PDBs; not matched to Pods",
                    source="kubernetes-metadata",
                ),
            ],
            metadata={
                "current_only": True,
                "nodepool_uid": pool.uid,
                "nodepool_name": pool.name,
                "nodeclass_uid": pool.nodeclass_uid,
                "topology": pool.topology.model_dump(mode="json"),
                "supply_mode": pool.supply_mode,
                "consolidation_policy": pool.consolidation_policy,
                "consolidate_after": pool.consolidate_after,
                "disruption_budget_count": pool.disruption_budget_count,
                "disruption_budget_configuration": [
                    item.model_dump(mode="json") for item in pool.disruption_budgets
                ]
                if pool.disruption_budgets is not None
                else None,
                "disruption_budget_effectiveness": "not_calculated",
                "zero_node_disruption_budget_configured": (
                    pool.zero_node_disruption_budget_configured
                ),
                "blockers": blockers,
                "pod_attribution": "current-nodeclaim-bound" if attribution else "unknown",
                "attributed_node_uids": sorted(
                    {
                        item.node_uid
                        for item in capacity.nap_managed_nodes
                        if item.nodepool_uid == pool.uid
                    }
                )
                if capacity and attribution
                else [],
                "attributed_pod_uids": sorted(item.pod_uid for item in pods) if attribution else [],
                "hard_placement_pods": hard_placement_pods,
                "local_storage_pods": local_storage_pods,
                "unresolved_owner_pods": unresolved_owner_pods,
                "namespace_pdbs_with_zero_disruptions": zero_disruption_pdbs,
                "namespace_pdbs_with_availability_issues": unknown_pdb_availability,
                "pdb_inventory": "observed" if pdb_inventory_observed else "unknown",
                "pdb_matching": "unknown",
                "namespace_pdb_selector_evidence": [
                    {
                        "pdb_uid": budget.uid,
                        **budget.model_dump(
                            mode="json",
                            include={
                                "namespace_uid",
                                "selector_match_status",
                                "selector_matched_pod_uids",
                                "selector_unmatched_pod_uids",
                                "selector_unknown_pod_uids",
                                "selector_issues",
                                "disruption_feasibility",
                            },
                        ),
                    }
                    for budget in scheduling.pdbs
                    if budget.namespace in {pod.namespace for pod in pods}
                ]
                if scheduling and pdb_inventory_observed and attribution
                else None,
                "daemonset_count": len(scheduling.daemonset_uids) if scheduling else None,
                "daemonset_overhead": "not_calculated",
                "do_not_disrupt_annotations": "not_collected",
                "packing_feasibility": "not_calculated",
                "removable_nodes": "not_calculated",
            },
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
        ),
        metrics=None,
        reasons=reasons,
        has_signal=bool(blockers),
    )


CONSOLIDATION_EVALUATORS = {"nap-consolidation-readiness": assess_nap_consolidation_readiness}


def assess_daemonset_overhead(
    cluster: ClusterSnapshot,
    pods: list[DaemonSetPodOverhead],
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    result = assess_scheduling(cluster, None, config, pack, recommendation_id, evaluated_at)
    inventory = cluster.scheduling
    if inventory is None or not inventory.daemonset_overhead_observed:
        result.reasons.append("incomplete_daemonset_inventory")
    subject = pods[0]
    if inventory and subject.daemonset_uid not in inventory.daemonset_uids:
        result.reasons.append("unobserved_daemonset_identity")
    identities = {(pod.namespace, pod.namespace_uid, pod.daemonset_name) for pod in pods}
    if len(identities) != 1 or any(pod.namespace_uid is None for pod in pods):
        result.reasons.append("ambiguous_daemonset_identity")
    if len({pod.pod_uid for pod in pods}) != len(pods) or len(
        {pod.node_uid for pod in pods}
    ) != len(pods):
        result.reasons.append("ambiguous_daemonset_node_membership")
    nodes = []
    for pod in sorted(pods, key=lambda item: (item.node_uid or "", item.pod_uid)):
        result.reasons.extend(pod.issues)
        if inventory is None or not any(
            item.pod_uid == pod.pod_uid
            and item.workload_kind == "DaemonSet"
            and item.workload_uid == pod.daemonset_uid
            and item.namespace == pod.namespace
            and item.namespace_uid == pod.namespace_uid
            for item in inventory.pods
        ):
            result.reasons.append("daemonset_pod_identity_mismatch")
        if pod.node_uid is None:
            result.reasons.append("unresolved_daemonset_node")
        if pod.cpu_request_mcpu is None or pod.memory_request_mib is None:
            result.reasons.append("unknown_daemonset_requests")
            continue
        if (
            pod.allocatable_cpu_mcpu is None
            or pod.allocatable_memory_mib is None
            or pod.allocatable_cpu_mcpu <= 0
            or pod.allocatable_memory_mib <= 0
        ):
            result.reasons.append("unknown_daemonset_node_allocatable")
            continue
        cpu_share = pod.cpu_request_mcpu / pod.allocatable_cpu_mcpu
        memory_share = pod.memory_request_mib / pod.allocatable_memory_mib
        if not isfinite(cpu_share) or not isfinite(memory_share):
            result.reasons.append("invalid_daemonset_request_share")
            continue
        nodes.append(
            pod.model_dump(mode="json")
            | {"cpu_allocatable_share": cpu_share, "memory_allocatable_share": memory_share}
        )
    requests = {(pod.cpu_request_mcpu, pod.memory_request_mib) for pod in pods}
    shapes = {(pod.allocatable_cpu_mcpu, pod.allocatable_memory_mib) for pod in pods}
    if len(requests) != 1:
        result.reasons.append("nonuniform_daemonset_requests")
    shares = {(node["cpu_allocatable_share"], node["memory_allocatable_share"]) for node in nodes}
    has_signal = len(nodes) >= 2 and len(shapes) > 1 and len(shares) > 1
    finding = result.recommendation
    finding.namespace = subject.namespace
    finding.workload = subject.daemonset_name
    finding.category = "node-pool-efficiency"
    finding.evidence = [
        Evidence(
            metric="observed_daemonset_nodes",
            value=len(nodes),
            unit="current nodes; not full cluster coverage",
            source="kubernetes-metadata",
        )
    ]
    for node in nodes:
        for metric, unit in [
            ("cpu_request_mcpu", "mCPU effective admitted request"),
            ("memory_request_mib", "MiB effective admitted request"),
            ("allocatable_cpu_mcpu", "mCPU current allocatable capacity"),
            ("allocatable_memory_mib", "MiB current allocatable capacity"),
        ]:
            finding.evidence.append(
                Evidence(
                    metric=f"{metric}/{node['node_uid']}",
                    value=node[metric],
                    unit=unit,
                    source="kubernetes-metadata",
                )
            )
        for resource in ["cpu", "memory"]:
            finding.evidence.append(
                Evidence(
                    metric=f"{resource}_request_share_percent/{node['node_uid']}",
                    value=node[f"{resource}_allocatable_share"] * 100,
                    unit=f"percent of current allocatable {resource}; not a target",
                    source="kubernetes-metadata",
                )
            )
    finding.metadata = {
        "current_only": True,
        "daemonset_uid": subject.daemonset_uid,
        "namespace_uid": subject.namespace_uid,
        "nodes": nodes,
        "request_units": {"cpu": "mCPU", "memory": "MiB"},
        "share_unit": "ratio of effective request to current allocatable capacity",
        "usage": "not_calculated",
        "node_eligibility": "not_calculated",
        "missing_pods": "not_synthesized",
        "sizing_target": "not_calculated",
        "removable_nodes": "not_calculated",
    }
    coverage = (
        [
            item
            for item in inventory.daemonset_coverage
            if item.daemonset_uid == subject.daemonset_uid
            and item.daemonset_name == subject.daemonset_name
            and item.namespace == subject.namespace
            and item.namespace_uid == subject.namespace_uid
        ]
        if inventory is not None
        else []
    )
    finding.metadata["coverage"] = (
        coverage[0].model_dump(mode="json") if len(coverage) == 1 else None
    )
    if len(coverage) == 1:
        context = coverage[0]
        for metric, value, unit in [
            (
                "controller_desired_daemonset_nodes",
                context.desired_number_scheduled,
                "controller-reported nodes; generation unverified, not desired membership",
            ),
            (
                "controller_ready_daemonset_nodes",
                context.number_ready,
                "controller-reported nodes; generation unverified, not workload readiness",
            ),
            (
                "observed_nonterminal_daemonset_pods",
                context.observed_nonterminal_pod_count,
                "listed nonterminal Pods; not desired Node coverage",
            ),
        ]:
            if value is not None:
                finding.evidence.append(
                    Evidence(metric=metric, value=value, unit=unit, source="kubernetes-metadata")
                )
    return RuleAssessment(
        recommendation=finding, metrics=None, reasons=result.reasons, has_signal=has_signal
    )


DAEMONSET_EVALUATORS = {"daemonset-overhead-review": assess_daemonset_overhead}
