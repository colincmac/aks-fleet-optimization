from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest
from pydantic import ValidationError
from test_assessment import assess, container_payload, memory_safety_payload, payload
from test_rules import AS_OF, eligible_snapshot

from aks_fleet_efficiency.assessment import AssessmentFragments
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import ExistingToolObservation, ResourceCandidate
from aks_fleet_efficiency.rules.cpu import _cpu_candidate
from aks_fleet_efficiency.rules.engine import analyze
from aks_fleet_efficiency.rules.memory_rules import _memory_candidate

CandidateDimension = Literal["cpu-request", "memory-request"]


def candidate(recommended: float = 800, *, workload_uid: str | None = None) -> ResourceCandidate:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    return ResourceCandidate(
        source="vpa",
        source_version="1.4.0",
        recommendation_id="vpa-synthetic",
        observed_at=snapshot.generated_at,
        dimension="cpu-request",
        cluster_resource_id=snapshot.clusters[0].resource_id,
        namespace=workload.namespace,
        workload_uid=workload_uid or workload.uid,
        container=workload.containers[0].name,
        current_value=1000,
        recommended_value=recommended,
        unit="mCPU",
        reference="synthetic-vpa-status",
        limitations=["synthetic recommendation"],
    )


def cpu_finding():
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads[0].resource_candidates = [candidate()]
    report = analyze(snapshot, AdvisorConfig(mode="guarded", packs=["AKS-RQ-002"]), as_of=AS_OF)
    return report.recommendations[0]


def dimensional_candidate(dimension: CandidateDimension, **changes: object) -> ResourceCandidate:
    payload = candidate().model_dump(mode="json")
    if dimension == "memory-request":
        payload.update(dimension=dimension, current_value=512, recommended_value=400, unit="MiB")
    payload.update(changes)
    return ResourceCandidate.model_validate(payload)


def select_candidate(
    dimension: CandidateDimension,
    candidates: list[ResourceCandidate],
    *,
    container_name: str | None = None,
) -> tuple[ResourceCandidate | None, list[str]]:
    snapshot = eligible_snapshot()
    cluster = snapshot.clusters[0]
    workload = cluster.workloads[0]
    original = workload.containers[0]
    original.resources.request_memory_mib = 512
    workload.containers.append(original.model_copy(deep=True, update={"name": "sidecar"}))
    workload.resource_candidates = candidates
    container = next(
        item for item in workload.containers if item.name == (container_name or original.name)
    )
    selector = _cpu_candidate if dimension == "cpu-request" else _memory_candidate
    return selector(snapshot, cluster, workload, container, 0, 24)


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
def test_candidate_selection_is_per_container(dimension: CandidateDimension) -> None:
    primary = dimensional_candidate(dimension)
    sidecar = dimensional_candidate(dimension, container="sidecar", recommendation_id="sidecar")
    selected, reasons = select_candidate(dimension, [primary, sidecar])
    assert selected == primary
    assert reasons == []
    selected, reasons = select_candidate(dimension, [primary, sidecar], container_name="sidecar")
    assert selected == sidecar
    assert reasons == []


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
def test_duplicate_candidates_only_block_their_exact_target(dimension: CandidateDimension) -> None:
    primary = dimensional_candidate(dimension)
    sidecar = dimensional_candidate(dimension, container="sidecar", recommendation_id="sidecar")
    selected, reasons = select_candidate(dimension, [primary, primary, sidecar])
    assert selected is None
    assert reasons == ["candidate_ambiguous"]
    selected, reasons = select_candidate(
        dimension, [primary, primary, sidecar], container_name="sidecar"
    )
    assert selected == sidecar
    assert reasons == []


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
def test_cpu_and_memory_candidate_dimensions_are_independent(dimension: CandidateDimension) -> None:
    candidates = [dimensional_candidate("cpu-request"), dimensional_candidate("memory-request")]
    selected, reasons = select_candidate(dimension, candidates)
    assert selected is not None
    assert selected.dimension == dimension
    assert reasons == []


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("cluster_resource_id", "foreign-cluster"),
        ("namespace", "foreign-namespace"),
        ("workload_uid", "foreign-workload"),
        ("container", "missing-container"),
    ],
)
def test_candidate_foreign_target_is_explicitly_blocked(
    dimension: CandidateDimension, field: str, value: str
) -> None:
    _, reasons = select_candidate(dimension, [dimensional_candidate(dimension, **{field: value})])
    assert "candidate_identity_mismatch" in reasons


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
@pytest.mark.parametrize("source,version", [("vpa", "99.0.0"), ("kubecost", "unknown-future")])
def test_candidate_uncharacterized_source_version_is_blocked(
    dimension: CandidateDimension, source: str, version: str
) -> None:
    _, reasons = select_candidate(
        dimension, [dimensional_candidate(dimension, source=source, source_version=version)]
    )
    assert "candidate_source_version_unsupported" in reasons


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
@pytest.mark.parametrize("hours,reason", [(-25, "candidate_stale"), (1, "candidate_in_future")])
def test_candidate_timestamp_gates_remain_enforced(
    dimension: CandidateDimension, hours: int, reason: str
) -> None:
    _, reasons = select_candidate(
        dimension,
        [dimensional_candidate(dimension, observed_at=AS_OF + timedelta(hours=hours))],
    )
    assert reason in reasons


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
@pytest.mark.parametrize("source,version", [("vpa", "1.4.0"), ("kubecost", "2.4.0")])
def test_characterized_candidate_sources_remain_eligible(
    dimension: CandidateDimension, source: str, version: str
) -> None:
    selected, reasons = select_candidate(
        dimension, [dimensional_candidate(dimension, source=source, source_version=version)]
    )
    assert selected is not None
    assert reasons == []


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
def test_other_container_candidate_is_not_a_substitute(dimension: CandidateDimension) -> None:
    selected, reasons = select_candidate(
        dimension, [dimensional_candidate(dimension, container="sidecar")]
    )
    assert selected is None
    assert reasons == ["existing_candidate_required"]


@pytest.mark.parametrize("dimension", ["cpu-request", "memory-request"])
def test_candidate_current_value_must_match_admitted_request(dimension: CandidateDimension) -> None:
    _, reasons = select_candidate(dimension, [dimensional_candidate(dimension, current_value=1024)])
    assert "candidate_current_value_mismatch" in reasons


def test_cpu_and_memory_rules_evaluate_two_container_candidates_independently() -> None:
    value = memory_safety_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"][container_payload(value)["name"]][
        "allow_request_reduction"
    ] = True
    snapshot = assess(value).snapshot
    workload = snapshot.clusters[0].workloads[0]
    workload.containers.append(
        workload.containers[0].model_copy(deep=True, update={"name": "sidecar"})
    )
    workload.safety_policy.memory["sidecar"] = workload.safety_policy.memory[
        workload.containers[0].name
    ].model_copy(deep=True)
    workload.resource_candidates.extend(
        item.model_copy(
            deep=True,
            update={
                "container": "sidecar",
                "recommendation_id": f"{item.recommendation_id}-sidecar",
            },
        )
        for item in list(workload.resource_candidates)
    )
    report = analyze(
        snapshot, AdvisorConfig(mode="guarded", packs=["AKS-RQ-002", "AKS-MEM-003"]), as_of=AS_OF
    )
    proposals = {
        (item.rule_id, item.metadata["container"]): item for item in report.recommendations
    }
    for container in [workload.containers[0].name, "sidecar"]:
        assert proposals[("AKS-RQ-002", container)].proposed_requests.cpu_mcores == 500
        assert proposals[("AKS-MEM-003", container)].proposed_requests.memory_mib == 313
    assert len(proposals) == 4
    assert all(item.estimated_monthly_savings is None for item in proposals.values())


@pytest.mark.parametrize(
    "field,value", [("unit", "MiB"), ("dimension", "memory-limit"), ("native_response", {})]
)
def test_candidate_contract_rejects_malformed_projection(field: str, value: object) -> None:
    payload = candidate().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        ResourceCandidate.model_validate(payload)


def test_guarded_cpu_validates_and_retains_upstream_candidate() -> None:
    finding = cpu_finding()
    assert finding.proposed_requests is not None
    assert finding.proposed_requests.cpu_mcores == 800
    assert finding.resource_candidate is not None
    assert finding.resource_candidate.source == "vpa"
    assert finding.proposal_source == "existing-tool-candidate"
    assert finding.estimated_monthly_savings is None


def test_guarded_cpu_without_candidate_does_not_create_competing_target() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads[0].resource_candidates = []
    report = analyze(
        snapshot,
        AdvisorConfig(mode="guarded", packs=["AKS-RQ-002"]),
        as_of=AS_OF,
    )
    assert report.recommendations == []
    finding = report.blocked_recommendations[0]
    assert "existing_candidate_required" in finding.reason_codes


def test_candidate_below_existing_safety_bound_is_blocked() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads[0].resource_candidates = [candidate(700)]
    report = analyze(snapshot, AdvisorConfig(mode="guarded", packs=["AKS-RQ-002"]), as_of=AS_OF)
    assert report.recommendations == []
    finding = report.blocked_recommendations[0]
    assert "candidate_below_safety_bound" in finding.reason_codes


def test_foreign_candidate_identity_is_blocked() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads[0].resource_candidates = [candidate(workload_uid="foreign")]
    report = analyze(snapshot, AdvisorConfig(mode="guarded", packs=["AKS-RQ-002"]), as_of=AS_OF)
    assert report.recommendations == []
    finding = report.blocked_recommendations[0]
    assert "candidate_identity_mismatch" in finding.reason_codes


def test_azure_advisor_observation_annotates_existing_autoscaling_review() -> None:
    snapshot = eligible_snapshot()
    cluster = snapshot.clusters[0]
    snapshot.existing_tool_observations = [
        ExistingToolObservation(
            source="azure-advisor",
            source_version="2026-11-01",
            recommendation_id="advisor-enable-vpa",
            observed_at=snapshot.generated_at,
            cluster_resource_id=cluster.resource_id,
            finding="enable-vpa",
            reference="synthetic-advisor-export",
            limitations=["cluster recommendation; not a per-container target"],
        )
    ]
    report = analyze(snapshot, AdvisorConfig(mode="baseline", packs=["AKS-AS-001"]), as_of=AS_OF)
    finding = report.recommendations[0]
    assert finding.existing_tool_observations[0].recommendation_id == "advisor-enable-vpa"
    assert finding.proposed_requests is None


@pytest.mark.parametrize("defect", ["foreign-cluster", "duplicate"])
def test_assessment_fragments_reject_unscoped_or_duplicate_advisor_observations(
    defect: str,
) -> None:
    value = payload()
    cluster_id = value["azure"][0]["clusters"][0]["resource_id"]
    observation = ExistingToolObservation(
        source="azure-advisor",
        source_version="2026-11-01",
        recommendation_id="advisor-enable-vpa",
        observed_at=AS_OF,
        cluster_resource_id=(
            f"{cluster_id}-foreign" if defect == "foreign-cluster" else cluster_id
        ),
        finding="enable-vpa",
        reference="synthetic-advisor-export",
        limitations=["cluster recommendation; not a per-container target"],
    ).model_dump(mode="json")
    value["existing_tool_observations"] = [observation]
    if defect == "duplicate":
        value["existing_tool_observations"].append(observation.copy())

    with pytest.raises(ValidationError, match="existing-tool observation"):
        AssessmentFragments.model_validate(value)
