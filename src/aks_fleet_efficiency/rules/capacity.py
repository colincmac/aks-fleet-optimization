from __future__ import annotations

from datetime import datetime

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    Evidence,
    Recommendation,
    Severity,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment


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
