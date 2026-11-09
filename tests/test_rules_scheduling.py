from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from test_assessment import payload, profile
from test_rules import AS_OF

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    CollectionStatus,
    FleetSnapshot,
    KubernetesObjectMetadata,
)
from aks_fleet_efficiency.rules.engine import analyze

PACK = "AKS-SCHED-001"


def scheduling_fragments() -> AssessmentFragments:
    value = payload()
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["spec"].update(
        nodeSelector={"synthetic.example/pool": "special"},
        affinity={
            "podAntiAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": [
                    {"topologyKey": "topology.kubernetes.io/zone"}
                ]
            }
        },
        topologySpreadConstraints=[
            {"maxSkew": 1, "whenUnsatisfiable": "DoNotSchedule", "topologyKey": "zone"}
        ],
        tolerations=[{"key": "dedicated", "effect": "NoSchedule", "operator": "Exists"}],
        volumes=[{"name": "data", "persistentVolumeClaim": {"claimName": "synthetic"}}],
        priorityClassName="synthetic-priority",
    )
    return AssessmentFragments.model_validate(value)


def scheduling_report(fragments: AssessmentFragments) -> OfflineAssessment:
    config = profile()
    config.analysis = AdvisorConfig(packs=[PACK])
    return assess_fragments(fragments, config, as_of=AS_OF)


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_scheduling_reviews_current_constraints_without_history_or_numeric_claims(
    mode: str,
) -> None:
    fragments = scheduling_fragments()
    fragments.metrics.clear()
    before = fragments.model_dump_json()
    config = profile()
    config.analysis = AdvisorConfig(mode=mode, packs=[PACK])
    result = assess_fragments(fragments, config, as_of=AS_OF)
    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    evidence = {item.metric: item.value for item in finding.evidence}
    assert evidence["node_selector"] == 1
    assert evidence["required_pod_anti_affinity"] == 1
    assert evidence["hard_topology_spread"] == 1
    assert evidence["tolerations"] == 1
    assert evidence["persistent_volume_claims"] == 1
    assert evidence["priority_class"] == 1
    assert finding.proposed_requests is None
    assert finding.proposed_limits is None
    assert finding.proposed_replica_floor is None
    assert finding.estimated_monthly_savings is None
    assert "not" in finding.summary
    assert fragments.model_dump_json() == before
    assert analyze(result.snapshot, config.analysis, as_of=AS_OF) == result.report
    assert FleetSnapshot.model_validate_json(result.snapshot.model_dump_json()) == result.snapshot


def test_scheduling_is_independent_of_vertical_normalization_and_pdb_matching() -> None:
    fragments = scheduling_fragments()
    fragments.kubernetes[0].resources.append(
        KubernetesObjectMetadata(
            api_version="policy/v1",
            kind="PodDisruptionBudget",
            name="synthetic-pdb",
            namespace="synthetic",
            uid="synthetic-pdb-uid",
            spec={"selector": {"matchLabels": {"unobserved": "value"}}, "minAvailable": 1},
            status={"disruptionsAllowed": 0},
        )
    )
    result = scheduling_report(fragments)
    assert not result.snapshot.clusters[0].workloads
    finding = result.report.recommendations[0]
    assert finding.metadata["namespace_pdb_candidates"] == ["synthetic-pdb-uid"]
    assert finding.metadata["pdb_matching"] == "unknown"
    assert finding.metadata["pod_uid"]


@pytest.mark.parametrize("problem", ["binding", "namespace", "api", "partial", "stale", "future"])
def test_scheduling_rejects_untrusted_or_incomplete_current_evidence(problem: str) -> None:
    fragments = scheduling_fragments()
    metadata = fragments.kubernetes[0]
    pod = next(item for item in metadata.resources if item.kind == "Pod")
    if problem == "binding":
        metadata.workload_bindings[pod.uid] = "synthetic-recreated-workload"
    elif problem == "namespace":
        metadata.resources = [
            item
            for item in metadata.resources
            if not (item.kind == "Namespace" and item.name == "synthetic")
        ]
    elif problem == "api":
        metadata.resource_versions.pop("v1/pods")
    elif problem == "partial":
        metadata.collection.pagination_complete = False
        metadata.collection.status = CollectionStatus.PARTIAL
    else:
        metadata.generated_at = AS_OF + timedelta(days=1 if problem == "future" else -2)
        if problem == "stale":
            metadata.collection.started_at -= timedelta(days=2)
            metadata.collection.completed_at -= timedelta(days=2)
            metadata.collection.source_observed_at -= timedelta(days=2)
    result = scheduling_report(fragments)
    assert not result.report.recommendations
    assert result.report.blocked_recommendations


def test_scheduling_rejects_supported_kind_with_foreign_controller_api() -> None:
    fragments = scheduling_fragments()
    metadata = fragments.kubernetes[0]
    parent = next(item for item in metadata.resources if item.kind == "StatefulSet")
    pod = next(item for item in metadata.resources if item.kind == "Pod")
    parent.api_version = "synthetic.example/v1"
    pod.owner_references[0]["apiVersion"] = parent.api_version
    result = scheduling_report(fragments)
    assert not result.report.recommendations
    assert "unresolved_workload_identity" in result.report.blocked_recommendations[0].reason_codes


def test_empty_constraints_do_not_mean_packing_or_removal_is_safe() -> None:
    fragments = scheduling_fragments()
    pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
    pod.spec = {"containers": pod.spec["containers"]}
    result = scheduling_report(fragments)
    assert not result.report.recommendations
    assert "unobserved_fields" in result.snapshot.clusters[0].scheduling.pods[0].model_dump()


def test_scheduling_respects_namespace_exclusions() -> None:
    fragments = scheduling_fragments()
    config = profile()
    config.analysis = AdvisorConfig(packs=[PACK], excluded_namespaces=["synthetic"])
    result = assess_fragments(fragments, config, as_of=AS_OF)
    assert not result.report.recommendations
    assert not result.report.blocked_recommendations


def test_native_scheduling_contract_rejects_duplicate_pod_identities() -> None:
    snapshot = scheduling_report(scheduling_fragments()).snapshot.model_dump(mode="json")
    pods = snapshot["clusters"][0]["scheduling"]["pods"]
    pods.append(pods[0].copy())
    with pytest.raises(ValueError, match="Scheduling Pod identities"):
        FleetSnapshot.model_validate(snapshot)


def test_duplicate_names_are_blocked_without_hiding_healthy_current_capacity() -> None:
    fragments = scheduling_fragments()
    metadata = fragments.kubernetes[0]
    duplicate = next(item for item in metadata.resources if item.kind == "Pod").model_copy(
        deep=True
    )
    duplicate.uid = "synthetic-second-pod"
    metadata.resources.append(duplicate)
    metadata.workload_bindings[duplicate.uid] = metadata.workload_bindings["pod-uid"]
    config = profile()
    config.analysis = AdvisorConfig(packs=[PACK, "AKS-NP-002"])
    result = assess_fragments(fragments, config, as_of=AS_OF)
    assert {item.rule_id for item in result.report.recommendations} == {"AKS-NP-002"}
    blocked = [item for item in result.report.blocked_recommendations if item.rule_id == PACK]
    assert len(blocked) == 2
    assert all("ambiguous_scheduling_identity" in item.reason_codes for item in blocked)


def test_scheduling_missing_native_evidence_is_explicitly_blocked() -> None:
    from test_rules import eligible_snapshot

    result = analyze(eligible_snapshot(), AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not result.recommendations
    assert result.blocked_recommendations[0].reason_codes == ["missing_scheduling_inventory"]


def test_complete_empty_pod_list_keeps_pool_assessment_complete_without_inventing_workloads() -> (
    None
):
    fragments = AssessmentFragments.model_validate(payload("pool-assessment"))
    result = assess_fragments(fragments, profile(), as_of=AS_OF)
    assert result.status == "complete"
    assert not result.snapshot.clusters[0].workloads
    assert not result.snapshot.clusters[0].scheduling.pods
    assert not result.report.blocked_recommendations
    fragments.kubernetes[0].resource_versions.pop("v1/pods")
    result = assess_fragments(fragments, profile(), as_of=AS_OF)
    assert result.status == "partial"
    assert any(
        item.rule_id == PACK and "incomplete_scheduling_inventory" in item.reason_codes
        for item in result.report.blocked_recommendations
    )


@pytest.mark.parametrize(
    "spec, expected",
    [
        ({"nodeSelector": {"agentpool": "synthetic"}}, "node_selector"),
        (
            {
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [{}]
                        }
                    }
                }
            },
            "required_node_affinity",
        ),
        (
            {
                "affinity": {
                    "nodeAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [{}]}
                }
            },
            "preferred_node_affinity",
        ),
        (
            {"affinity": {"podAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": [{}]}}},
            "required_pod_affinity",
        ),
        (
            {
                "affinity": {
                    "podAntiAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [{}]}
                }
            },
            "preferred_pod_anti_affinity",
        ),
        (
            {"topologySpreadConstraints": [{"whenUnsatisfiable": "ScheduleAnyway"}]},
            "soft_topology_spread",
        ),
        ({"volumes": [{"name": "local", "emptyDir": {}}]}, "local_emptydir_volumes"),
        ({"runtimeClassName": "synthetic-runtime"}, "runtime_class"),
        ({"schedulerName": "synthetic-scheduler"}, "custom_scheduler"),
        ({"initContainers": [{"name": "synthetic-init"}]}, "init_containers"),
        ({"overhead": {"memory": "1Mi"}}, "pod_overhead"),
        ({"resources": {"requests": {"cpu": "1"}}}, "pod_resource_budget"),
    ],
)
def test_scheduling_distinguishes_each_observed_constraint(
    spec: dict[str, Any], expected: str
) -> None:
    fragments = scheduling_fragments()
    pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
    pod.spec = spec
    result = scheduling_report(fragments)
    assert result.snapshot.clusters[0].scheduling.pods[0].constraints == {expected: 1}
    assert len(result.report.recommendations) == 1


@pytest.mark.parametrize(
    "field, value",
    [
        ("affinity", "invalid"),
        ("nodeSelector", []),
        ("tolerations", {}),
        ("volumes", "invalid"),
        ("topologySpreadConstraints", [{"whenUnsatisfiable": {}}]),
    ],
)
def test_malformed_scheduling_fields_are_visible_not_silently_dropped(
    field: str, value: Any
) -> None:
    fragments = scheduling_fragments()
    pod = next(item for item in fragments.kubernetes[0].resources if item.kind == "Pod")
    pod.spec[field] = value
    result = scheduling_report(fragments)
    assert not result.report.recommendations
    assert "invalid_scheduling_field" in result.report.blocked_recommendations[0].reason_codes


def test_scheduling_context_preserves_taints_cordons_and_daemonsets_without_matching() -> None:
    fragments = scheduling_fragments()
    metadata = fragments.kubernetes[0]
    node = next(item for item in metadata.resources if item.kind == "Node")
    node.spec = {"taints": [{"key": "dedicated", "effect": "NoSchedule"}], "unschedulable": True}
    metadata.api_availability["apps/v1/daemonsets"] = "available"
    metadata.resource_versions["apps/v1/daemonsets"] = "synthetic-version"
    metadata.resources.append(
        KubernetesObjectMetadata(
            kind="DaemonSet",
            api_version="apps/v1",
            uid="synthetic-daemon-uid",
            name="synthetic-daemon",
            namespace="synthetic",
        )
    )
    finding = scheduling_report(fragments).report.recommendations[0]
    assert finding.metadata["tainted_node_uids"] == [node.uid]
    assert finding.metadata["cordoned_node_uids"] == [node.uid]
    assert finding.metadata["daemonset_uids"] == ["synthetic-daemon-uid"]
    assert finding.metadata["label_matching"] == "unsupported_projected_labels"


@pytest.mark.parametrize("pack_id", [PACK, "AKS-NP-002"])
def test_current_review_freshness_equality_and_inconsistent_snapshot_time(pack_id: str) -> None:
    result = scheduling_report(scheduling_fragments())
    snapshot = result.snapshot
    cluster = snapshot.clusters[0]
    if pack_id == PACK:
        cluster.scheduling.observed_at = AS_OF - timedelta(hours=24)
    else:
        cluster.capacity.azure_observed_at = AS_OF - timedelta(hours=24)
        cluster.capacity.kubernetes_observed_at = AS_OF - timedelta(hours=24)
    assert analyze(snapshot, AdvisorConfig(packs=[pack_id]), as_of=AS_OF).recommendations
    if pack_id == PACK:
        cluster.scheduling.observed_at = AS_OF
    else:
        cluster.capacity.azure_observed_at = AS_OF
    report = analyze(snapshot, AdvisorConfig(packs=[pack_id]), as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations
