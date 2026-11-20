from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_assessment import profile
from test_history import TENANT, write_run
from test_rules_capacity import nap_payload
from typer.testing import CliRunner

from aks_fleet_efficiency.assessment import AssessmentFragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.scheduling import SchedulingResourceComparison
from aks_fleet_efficiency.scheduling_fit import (
    PendingNapConstraintReview,
    SchedulingNecessaryFitProfile,
    SchedulingNecessaryFitReview,
    review_pending_nap_constraints,
)

AS_OF = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


@pytest.fixture
def nap_fragmentation_input() -> dict[str, Any]:
    payload = nap_payload()
    metadata = payload["kubernetes"][0]
    pods = [item for item in metadata["resources"] if item["kind"] == "Pod"]
    node = next(item for item in metadata["resources"] if item["kind"] == "Node")
    claim = next(item for item in metadata["resources"] if item["kind"] == "NodeClaim")
    pending = deepcopy(pods[0])
    pending.update(uid="pending-pod", name="pending-pod", status={"phase": "Pending"})
    pending["spec"].pop("nodeName")
    pending["spec"]["containers"][0]["resources"]["requests"] = {
        "cpu": "600m",
        "memory": "128Mi",
    }
    node["status"] = {"allocatable": {"cpu": "900m", "memory": "2048Mi", "pods": "12"}}
    for key in ["v1/namespaces", "v1/nodes", "v1/pods"]:
        metadata["resource_versions"][key] = "synthetic-version"
    for pod in pods:
        pod["status"]["phase"] = "Running"
        pod["spec"].update(resources={}, initContainers=[], overhead={})
        pod["spec"]["containers"][0]["resources"]["requests"] = {
            "cpu": "500m",
            "memory": "256Mi",
        }
    pending["spec"].update(resources={}, initContainers=[], overhead={})
    second_node = deepcopy(node)
    second_node.update(uid="second-node", name="second-node")
    first_identity = metadata["nodes"][0]
    resource_id = first_identity["azure_resource_id"].rsplit("/", 1)[0] + "/2"
    provider = "azure://" + resource_id
    second_node["spec"].update(
        providerID=provider, taints=[{"key": "demo", "value": "reserved", "effect": "NoSchedule"}]
    )
    second_node["status"]["allocatable"]["cpu"] = "500m"
    pending["spec"]["tolerations"] = []
    second_claim = deepcopy(claim)
    second_claim.update(uid="second-claim", name="second-claim")
    second_claim["status"].update(providerID=provider, nodeName="second-node")
    metadata["nodes"].append(
        first_identity
        | {
            "node_uid": "second-node",
            "azure_resource_id": resource_id,
            "provider_id": provider,
        }
    )
    metadata["resources"].extend([pending, second_node, second_claim])
    return payload


def _review_nap(payload: dict[str, Any]) -> PendingNapConstraintReview:
    metadata = payload["kubernetes"][0]
    return review_pending_nap_constraints(
        AssessmentFragments.model_validate(payload),
        profile(),
        cluster_resource_id=metadata["cluster_resource_id"],
        cluster_uid=metadata["cluster_uid"],
        nodepool_uid="synthetic-nap-pool-uid",
        pod_uid="pending-pod",
        as_of=AS_OF,
        maximum_source_age_seconds=24 * 3600,
    )


def test_nap_review_separates_scattered_resources_from_a_hard_taint(
    nap_fragmentation_input: dict[str, Any],
) -> None:
    result = _review_nap(nap_fragmentation_input)
    assert result.fragmentation == "scattered_across_nodes"
    assert result.fit_status == "blocked"
    assert result.removable_nodes == "not_calculated"
    assert result.protection_effectiveness == "unknown"
    assert {"topology_spread", "storage", "extended_resources"} <= set(result.not_evaluated)
    second = next(item for item in result.nodes if item.binding.node_uid == "second-node")
    assert second.binding.nodeclaim_uid == "second-claim"
    assert second.resources.cpu_available_mcpu == 500
    assert second.resources.memory_available_mib == 2048
    assert second.resources.pod_slots_available == 12
    assert second.placement.constraints["hard_taints"] == "excluded"
    first = next(item for item in result.nodes if item.binding.node_uid == "synthetic-node-uid")
    assert first.resources.cpu_available_mcpu == 400
    assert first.resources.pod_slots_available == 11


def test_nap_residuals_count_bound_daemonset_once(nap_fragmentation_input: dict[str, Any]) -> None:
    metadata = nap_fragmentation_input["kubernetes"][0]
    bound = next(
        item for item in metadata["resources"] if item.get("status", {}).get("phase") == "Running"
    )
    metadata["api_availability"]["apps/v1/daemonsets"] = "available"
    metadata["resource_versions"]["apps/v1/daemonsets"] = "synthetic-version"
    metadata["resources"].append(
        {
            "kind": "DaemonSet",
            "api_version": "apps/v1",
            "uid": "synthetic-daemonset",
            "name": "synthetic-daemonset",
            "namespace": bound["namespace"],
        }
    )
    bound["owner_references"] = [
        {
            "kind": "DaemonSet",
            "apiVersion": "apps/v1",
            "uid": "synthetic-daemonset",
            "name": "synthetic-daemonset",
            "controller": True,
        }
    ]
    metadata["workload_bindings"][bound["uid"]] = "synthetic-daemonset"
    result = _review_nap(nap_fragmentation_input)
    first = next(item for item in result.nodes if item.binding.node_uid == "synthetic-node-uid")
    assert first.observed_daemonset_pods == 1
    assert first.observed_daemonset_cpu_mcpu == 500
    assert first.observed_daemonset_memory_mib == 256
    assert first.resources.cpu_available_mcpu == 400
    assert first.resources.pod_slots_available == 11


def test_nap_review_preserves_shortfall_evidence_but_does_not_invent_slots(
    nap_fragmentation_input: dict[str, Any],
) -> None:
    metadata = nap_fragmentation_input["kubernetes"][0]
    target = next(item for item in metadata["resources"] if item["uid"] == "second-node")
    target["status"]["allocatable"].pop("pods")
    result = _review_nap(nap_fragmentation_input)
    second = next(item for item in result.nodes if item.binding.node_uid == "second-node")
    assert second.resources.status == "blocked"
    assert second.resources.cpu_available_mcpu == 500
    assert second.resources.pod_slots_available is None
    assert result.fragmentation == "unknown"


def test_nap_review_never_ignores_an_unresolved_competing_pod(
    nap_fragmentation_input: dict[str, Any],
) -> None:
    metadata = nap_fragmentation_input["kubernetes"][0]
    bound = next(
        item for item in metadata["resources"] if item.get("status", {}).get("phase") == "Running"
    )
    bound["spec"]["nodeName"] = "unresolved-node-name"
    result = _review_nap(nap_fragmentation_input)
    assert result.fragmentation == "unknown"
    assert all("unresolved_pod_assignment" in row.resources.issues for row in result.nodes)
    assert all(row.resources.cpu_available_mcpu is None for row in result.nodes)


@pytest.mark.parametrize(
    "problem", ["recreated_pool", "missing_claim_list", "duplicate_provider", "stale"]
)
def test_nap_review_withholds_unknown_rosters(
    nap_fragmentation_input: dict[str, Any], problem: str
) -> None:
    metadata = nap_fragmentation_input["kubernetes"][0]
    if problem == "recreated_pool":
        next(item for item in metadata["resources"] if item["kind"] == "NodePool")["uid"] = (
            "new-pool"
        )
    elif problem == "missing_claim_list":
        metadata["resource_versions"].pop("karpenter.sh/v1/nodeclaims")
    elif problem == "duplicate_provider":
        provider = metadata["nodes"][0]["provider_id"]
        metadata["nodes"][1].update(
            provider_id=provider, azure_resource_id=metadata["nodes"][0]["azure_resource_id"]
        )
        for item in metadata["resources"]:
            if item["uid"] == "second-node":
                item["spec"]["providerID"] = provider
            elif item["uid"] == "second-claim":
                item["status"]["providerID"] = provider
    else:
        metadata["collection"]["source_observed_at"] = "2026-10-25T12:00:00Z"
    result = _review_nap(nap_fragmentation_input)
    assert result.fragmentation == "unknown"
    assert not result.nodes
    assert result.reason_codes


def comparison(*, status: str = "satisfied") -> SchedulingResourceComparison:
    return SchedulingResourceComparison(
        pod_uid="pod-uid-synthetic",
        node_uid="node-uid-synthetic",
        status=status,
        cpu_required_mcpu=500,
        memory_required_mib=256,
        cpu_available_mcpu=1000,
        memory_available_mib=512,
        pod_slots_available=10,
        issues=[] if status != "blocked" else ["storage_constraint_unknown"],
    )


def review(
    pair: SchedulingResourceComparison,
    *,
    status: str = "blocked",
) -> SchedulingNecessaryFitReview:
    return SchedulingNecessaryFitReview(
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=(
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/"
            "managedClusters/aks-synthetic"
        ),
        cluster_uid="cluster-uid-synthetic",
        evaluated_at=AS_OF,
        source_observed_at=AS_OF,
        profile=SchedulingNecessaryFitProfile(),
        profile_digest=DIGEST,
        source_collection_digest=DIGEST,
        calculation_digest=DIGEST,
        status=status,
        reason_codes=["source_and_profile_admission_blocked"],
        pairs=[pair],
    )


def test_necessary_fit_contract_admits_only_the_pinned_profile() -> None:
    result = review(comparison())

    assert result.status == "blocked"
    assert result.source_admission == result.profile_admission == "blocked"
    assert result.profile.kubernetes_minor == "1.36"
    assert result.profile.scheduler_name == "default-scheduler"
    assert result.simultaneous_placement == "not_calculated"
    assert result.removable_nodes == "not_calculated"


def test_necessary_fit_contract_cannot_overstate_blocked_pairs() -> None:
    with pytest.raises(ValidationError, match="status"):
        review(comparison(status="blocked"), status="satisfied")


def test_necessary_fit_cannot_promote_resource_arithmetic_to_verified_fit() -> None:
    with pytest.raises(ValidationError, match="status"):
        review(comparison(), status="satisfied")


@pytest.mark.parametrize("field", ["source_admission", "profile_admission"])
def test_necessary_fit_refuses_caller_verified_admission(field: str) -> None:
    payload = review(comparison()).model_dump()
    payload[field] = "verified"

    with pytest.raises(ValidationError, match=field):
        SchedulingNecessaryFitReview.model_validate(payload)


def test_necessary_fit_contract_rejects_unmodeled_scheduler() -> None:
    with pytest.raises(ValidationError):
        SchedulingNecessaryFitProfile(scheduler_name="custom-scheduler")


def test_necessary_fit_contract_rejects_issues_on_satisfied_pairs() -> None:
    pair = comparison()
    pair.issues = ["unexpected_issue"]

    with pytest.raises(ValidationError, match="non-blocked pairs cannot retain issues"):
        review(pair)


def test_retained_capacity_review_reports_replayed_pack_evidence(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    output = tmp_path / "retained-capacity.md"
    arguments = [
        "review-retained-capacity",
        "--assessment",
        str(directory / "assessment.json"),
        "--tenant",
        TENANT,
        "--output",
        str(output),
    ]

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0, result.output
    report = output.read_text(encoding="utf-8")
    assert "Assessment run:" in report
    assert "| AKS-NP-001 |" in report
    assert "| AKS-NP-003 |" in report
    assert "no subjects evaluated" in report
    assert "Scheduler fit: blocked" in report
    assert "Removable nodes: not calculated" in report
    assert CliRunner().invoke(app, arguments).exit_code == 1
    assert output.read_text(encoding="utf-8") == report
    (directory / "report.md").write_text("not the original report", encoding="utf-8")
    rejected_output = tmp_path / "rejected.md"
    rejected = CliRunner().invoke(app, [*arguments[:-1], str(rejected_output)])
    assert rejected.exit_code == 2
    assert not rejected_output.exists()
