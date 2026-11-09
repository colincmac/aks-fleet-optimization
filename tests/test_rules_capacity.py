from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from test_assessment import payload, profile
from test_rules import AS_OF, eligible_snapshot

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.rules.engine import analyze

PACK = "AKS-NP-002"


def capacity_report(value: dict[str, Any] | None = None) -> OfflineAssessment:
    fragments = AssessmentFragments.model_validate(payload() if value is None else value)
    config = profile()
    config.analysis = AdvisorConfig(packs=[PACK])
    return assess_fragments(fragments, config, as_of=AS_OF)


@pytest.mark.parametrize("enabled, expected", [(True, "cas"), (False, "fixed"), (None, "unknown")])
def test_current_capacity_classification_is_independent_of_metrics(
    enabled: bool | None, expected: str
) -> None:
    value = payload()
    value["metrics"] = []
    pool = value["azure"][0]["clusters"][0]["node_pools"][0]
    pool["autoscaling_enabled"] = enabled
    result = capacity_report(value)
    assert not result.snapshot.clusters[0].node_pools
    finding = result.report.recommendations[0]
    assert finding.metadata["pools"][0]["management"] == expected
    assert finding.metadata["pools"][0]["resource_id"] == pool["resource_id"]
    assert finding.metadata["pools"][0]["intent"] == "unknown"
    assert finding.metadata["nap_prerequisites"]["network"] == "unknown"
    assert finding.metadata["nap_prerequisites"]["identity"] == "unknown"
    assert finding.proposed_requests is None
    assert finding.proposed_limits is None
    assert finding.proposed_replica_floor is None
    assert finding.estimated_monthly_savings is None


@pytest.mark.parametrize("pack_id", [PACK, "AKS-SCHED-001"])
@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_current_investigations_do_not_claim_history_from_low_coverage(
    pack_id: str, mode: str
) -> None:
    from test_rules_scheduling import scheduling_fragments

    fragments = scheduling_fragments()
    for source in fragments.metrics:
        for item in source.observations:
            item.quality.window.coverage_ratio = 0.1
    config = profile()
    config.analysis = AdvisorConfig(packs=[pack_id], mode=mode)
    result = assess_fragments(fragments, config, as_of=AS_OF)
    assert len(result.report.recommendations) == 1
    assert result.report.recommendations[0].estimated_monthly_savings is None


def test_equal_cas_bounds_are_not_owner_intent_or_a_safe_lower_minimum() -> None:
    value = payload()
    pool = value["azure"][0]["clusters"][0]["node_pools"][0]
    pool.update(autoscaling_enabled=True, min_count=3, max_count=3)
    finding = capacity_report(value).report.recommendations[0]
    assert finding.metadata["pools"][0]["fixed_bounds"] is True
    assert finding.metadata["pools"][0]["intent"] == "unknown"
    assert finding.metadata["nap_prerequisites"]["cas_transition"] == "review_required"


@pytest.mark.parametrize("role, spot, os_type", [("System", True, "Windows"), (None, None, None)])
def test_capacity_does_not_invent_pool_role_market_or_os(
    role: str | None, spot: bool | None, os_type: str | None
) -> None:
    value = payload()
    value["azure"][0]["clusters"][0]["node_pools"][0].update(mode=role, spot=spot, os_type=os_type)
    finding = capacity_report(value).report.recommendations[0]
    pool = finding.metadata["pools"][0]
    assert pool["role"] == (role or "unknown")
    assert pool["spot"] == spot
    assert pool["os_type"] == os_type
    assert finding.metadata["nap_prerequisites"]["windows"] == (
        "unsupported" if os_type == "Windows" else "unknown"
    )


def test_nap_auto_mode_does_not_relabel_existing_arm_pools_as_nap_managed() -> None:
    value = payload()
    value["azure"][0]["clusters"][0]["node_provisioning_mode"] = "Auto"
    finding = capacity_report(value).report.recommendations[0]
    assert finding.metadata["provisioning_mode"] == "Auto"
    assert finding.metadata["pools"][0]["management"] != "nap"
    assert finding.metadata["nap_api_status"]["karpenter.sh/v1/nodepools"] == "unknown"
    assert finding.metadata["nap_managed_nodes"] == []


def test_pool_intent_is_an_exact_bound_owner_declaration_not_approval() -> None:
    value = payload()
    cluster = value["azure"][0]["clusters"][0]
    value["pool_intents"] = [
        {
            "cluster_resource_id": cluster["resource_id"],
            "pool_resource_id": cluster["node_pools"][0]["resource_id"],
            "owner": "synthetic-owner",
            "classification": "intentionally-reserved",
            "reference": "synthetic-review/resilience",
        }
    ]
    finding = capacity_report(value).report.recommendations[0]
    assert finding.metadata["pools"][0]["intent"] == "intentionally-reserved"
    assert finding.metadata["pools"][0]["intent_is_approval"] is False
    value["pool_intents"][0]["pool_resource_id"] += "-foreign"
    with pytest.raises(ValueError, match="pool intent"):
        capacity_report(value)


@pytest.mark.parametrize("field", ["reference", "owner"])
def test_pool_intent_rejects_empty_declarations(field: str) -> None:
    value = payload()
    cluster = value["azure"][0]["clusters"][0]
    value["pool_intents"] = [
        {
            "cluster_resource_id": cluster["resource_id"],
            "pool_resource_id": cluster["node_pools"][0]["resource_id"],
            "owner": "synthetic-owner",
            "classification": "specialized",
            "reference": "synthetic-review/hardware",
        }
    ]
    value["pool_intents"][0][field] = " "
    with pytest.raises(ValueError):
        capacity_report(value)


def test_native_capacity_missing_evidence_is_blocked() -> None:
    result = analyze(eligible_snapshot(), AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert result.blocked_recommendations[0].reason_codes == ["missing_capacity_inventory"]


def test_missing_current_supply_is_not_a_healthy_capacity_review() -> None:
    result = capacity_report()
    result.snapshot.clusters[0].capacity.pools.clear()
    report = analyze(result.snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert "missing_capacity_supply" in report.blocked_recommendations[0].reason_codes


@pytest.mark.parametrize("problem", ["stale", "future", "identity", "partial"])
def test_current_capacity_keeps_scope_freshness_and_receipt_gates(problem: str) -> None:
    result = capacity_report()
    snapshot = result.snapshot
    context = snapshot.clusters[0].capacity
    if problem == "stale":
        context.azure_observed_at = AS_OF - timedelta(hours=25)
    elif problem == "future":
        context.azure_observed_at = AS_OF + timedelta(seconds=1)
    elif problem == "identity":
        context.cluster_resource_id += "-foreign"
    else:
        from aks_fleet_efficiency.models import CollectionStatus

        receipt = next(
            item
            for item in snapshot.collection_manifest.source_results
            if item.collector == "azure-inventory"
        )
        receipt.status = CollectionStatus.PARTIAL
    report = analyze(snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations


def nap_payload() -> dict[str, Any]:
    value = payload()
    value["azure"][0]["clusters"][0]["node_provisioning_mode"] = "Auto"
    metadata = value["kubernetes"][0]
    for key in [
        "karpenter.sh/v1/nodepools",
        "karpenter.sh/v1/nodeclaims",
        "karpenter.azure.com/v1beta1/aksnodeclasses",
    ]:
        metadata["api_availability"][key] = "available"
        metadata["resource_versions"][key] = "synthetic-version"
    provider = "azure://" + metadata["nodes"][0]["azure_resource_id"]
    metadata["nodes"][0]["provider_id"] = provider
    metadata["nodes"][0]["node_pool_resource_id"] = None
    metadata["nodes"][0]["state"] = "unknown"
    node = next(item for item in metadata["resources"] if item["kind"] == "Node")
    node["spec"] = {"providerID": provider}
    metadata["resources"].extend(
        [
            {
                "api_version": "karpenter.sh/v1",
                "kind": "NodePool",
                "uid": "synthetic-nap-pool-uid",
                "name": "synthetic-nap",
                "spec": {
                    "template": {
                        "spec": {
                            "nodeClassRef": {
                                "group": "karpenter.azure.com",
                                "kind": "AKSNodeClass",
                                "name": "synthetic-class",
                            },
                            "requirements": [
                                {
                                    "key": "node.kubernetes.io/instance-type",
                                    "operator": "In",
                                    "values": ["synthetic-sku"],
                                }
                            ],
                            "taints": [],
                        }
                    },
                    "limits": {"cpu": "100"},
                    "disruption": {"budgets": [{"nodes": "0"}]},
                },
            },
            {
                "api_version": "karpenter.azure.com/v1beta1",
                "kind": "AKSNodeClass",
                "uid": "synthetic-class-uid",
                "name": "synthetic-class",
            },
            {
                "api_version": "karpenter.sh/v1",
                "kind": "NodeClaim",
                "uid": "synthetic-claim-uid",
                "name": "synthetic-claim",
                "owner_references": [
                    {
                        "apiVersion": "karpenter.sh/v1",
                        "kind": "NodePool",
                        "name": "synthetic-nap",
                        "uid": "synthetic-nap-pool-uid",
                        "controller": True,
                    }
                ],
                "status": {"providerID": provider, "nodeName": node["name"]},
            },
        ]
    )
    return value


def test_nap_supply_requires_exact_claim_owner_and_provider_bound_node() -> None:
    value = nap_payload()
    result = capacity_report(value)
    finding = result.report.recommendations[0]
    assert finding.metadata["nap_managed_nodes"] == [
        {
            "node_uid": "synthetic-node-uid",
            "nodeclaim_uid": "synthetic-claim-uid",
            "nodepool_uid": "synthetic-nap-pool-uid",
        }
    ]
    pool = finding.metadata["nap_pools"][0]
    assert pool["nodeclass_uid"] == "synthetic-class-uid"
    assert pool["requirement_count"] == 1
    assert pool["disruption_budget_count"] == 1
    assert pool["limits_observed"] is True
    assert analyze(result.snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF) == result.report


@pytest.mark.parametrize(
    "problem", ["owner", "provider", "scope", "node-name", "node-api", "claim-api", "class-api"]
)
def test_nap_never_infers_management_from_names_or_unverified_apis(problem: str) -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    claim = next(item for item in metadata["resources"] if item["kind"] == "NodeClaim")
    if problem == "owner":
        claim["owner_references"][0]["uid"] += "-recreated"
    elif problem == "provider":
        claim["status"]["providerID"] += "-foreign"
    elif problem == "scope":
        metadata["nodes"][0]["azure_resource_id"] = None
    elif problem == "node-name":
        claim["status"]["nodeName"] += "-recreated"
    elif problem == "node-api":
        metadata["resource_versions"].pop("v1/nodes")
    elif problem == "claim-api":
        metadata["resource_versions"].pop("karpenter.sh/v1/nodeclaims")
    else:
        metadata["resource_versions"].pop("karpenter.azure.com/v1beta1/aksnodeclasses")
    finding = capacity_report(value).report.recommendations[0]
    if problem == "class-api":
        assert finding.metadata["nap_pools"][0]["nodeclass_uid"] is None
    else:
        assert not finding.metadata["nap_managed_nodes"]
    assert finding.estimated_monthly_savings is None


def test_pool_intents_cannot_repeat_or_transfer_to_recreated_native_pools() -> None:
    result = capacity_report()
    context = result.snapshot.clusters[0].capacity
    from aks_fleet_efficiency.models import PoolIntentBinding

    pool = context.pools[0]
    pool.intent = PoolIntentBinding(
        cluster_resource_id=context.cluster_resource_id,
        pool_resource_id=pool.resource_id + "-foreign",
        owner="synthetic-owner",
        classification="specialized",
        reference="synthetic-review/hardware",
    )
    report = analyze(result.snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert "capacity_intent_identity_mismatch" in report.blocked_recommendations[0].reason_codes


@pytest.mark.parametrize("problem", ["duplicate-claim", "manual-mode"])
def test_ambiguous_nap_supply_is_never_selected_by_list_order(problem: str) -> None:
    value = nap_payload()
    if problem == "manual-mode":
        value["azure"][0]["clusters"][0]["node_provisioning_mode"] = "Manual"
    else:
        import copy

        resources = value["kubernetes"][0]["resources"]
        second = copy.deepcopy(next(item for item in resources if item["kind"] == "NodeClaim"))
        second["uid"] = "synthetic-second-claim-uid"
        second["name"] = "synthetic-second-claim"
        resources.append(second)
    finding = capacity_report(value).report.recommendations[0]
    assert not finding.metadata["nap_managed_nodes"]
    assert finding.metadata["capacity_issues"]


@pytest.mark.parametrize("problem", ["duplicate", "foreign-pool", "manual-mode"])
def test_native_nap_contract_rejects_ambiguous_or_unbound_supply(problem: str) -> None:
    from aks_fleet_efficiency.models import FleetSnapshot

    snapshot = capacity_report(nap_payload()).snapshot.model_dump(mode="json")
    context = snapshot["clusters"][0]["capacity"]
    if problem == "duplicate":
        context["nap_managed_nodes"].append(context["nap_managed_nodes"][0].copy())
    elif problem == "foreign-pool":
        context["nap_managed_nodes"][0]["nodepool_uid"] += "-foreign"
    else:
        context["provisioning_mode"] = "Manual"
    with pytest.raises(ValueError, match="NAP supply"):
        FleetSnapshot.model_validate(snapshot)
