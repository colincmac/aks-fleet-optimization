from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aks_fleet_efficiency.controller_evidence import (
    ControllerEvidence,
    ControllerScope,
    ControllerWindow,
)
from aks_fleet_efficiency.vpa_review import (
    CurrentVpaEvidence,
    VpaGenerationEvidence,
    VpaReview,
    VpaScope,
    review_current_vpa,
    vpa_recommendation_digest,
)

AT = datetime(2026, 11, 19, 12, tzinfo=UTC)
END = AT + timedelta(minutes=1)
WORKLOAD = {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "cluster_resource_id": (
        "/subscriptions/00000000-0000-0000-0000-000000000002/resourcegroups/fixture"
        "/providers/Microsoft.ContainerService/managedClusters/fixture"
    ),
    "cluster_uid": "fixture-cluster",
    "namespace_uid": "fixture-namespace",
    "workload_uid": "fixture-deployment",
    "workload_kind": "Deployment",
}
VPA_SCOPE = VpaScope.model_validate(WORKLOAD | {"vpa_uid": "fixture-vpa"})
HPA_SCOPE = ControllerScope.model_validate(
    WORKLOAD
    | {
        "hpa_uid": "fixture-hpa",
        "metric_kind": "Resource",
        "resource": "cpu",
        "target_type": "Utilization",
        "unit": "percent",
        "producer": "fixture-source",
    }
)
WINDOW = ControllerWindow(start=AT, end=END, step_seconds=60)


@pytest.fixture
def current() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "scope": VPA_SCOPE,
        "source_status": "complete",
        "observed_at": END,
        "container": "app",
        "request_cpu_mcpu": 500,
        "request_memory_mib": 1024,
        "cpu_basis": {
            "hpa_uid": HPA_SCOPE.hpa_uid,
            "configuration_revision": "controller-v1",
            "request_revision": "request-v1",
            "sole_container": "app",
        },
        "vpa": {
            "uid": VPA_SCOPE.vpa_uid,
            "name": "same-display-name",
            "update_mode": "Off",
            "container_policies": [
                {
                    "container_name": "app",
                    "mode": "Auto",
                    "controlled_resources": ["cpu", "memory"],
                    "controlled_values": "RequestsOnly",
                    "min_allowed": {"cpu_mcores": 100, "memory_mib": 128},
                    "max_allowed": {"cpu_mcores": 1000, "memory_mib": 2048},
                }
            ],
            "recommendations": [
                {
                    "container_name": "app",
                    "target": {"cpu_mcores": 250, "memory_mib": 512},
                    "lower_bound": {"cpu_mcores": 125, "memory_mib": 256},
                    "upper_bound": {"cpu_mcores": 400, "memory_mib": 768},
                    "uncapped_target": {"cpu_mcores": 175, "memory_mib": 480},
                }
            ],
        },
    }


def _history(*, request: float = 500, target: bool = True) -> ControllerEvidence:
    sample = {
        "scope": HPA_SCOPE,
        "configuration_revision": "controller-v1",
        "request_revision": "request-v1",
        "observed_at": AT,
        "captured_at": END,
        "observation_ref": "fixture-observation",
    }
    return ControllerEvidence.model_validate(
        {
            "schema_version": "1.0",
            "window": WINDOW,
            "source_status": "complete",
            "signal": [sample | {"value": 50}],
            "target": [sample | {"value": 75}] if target else [],
            "hpa_replicas": [sample | {"value": {"desired": 3, "current": 3}}],
            "request_mcpu_per_pod": [sample | {"value": request}],
        }
    )


def _review(
    current: dict[str, Any],
    *,
    history: ControllerEvidence | None = None,
    generation_at: datetime | None = AT,
    digest: str | None = None,
    hpa_scope: ControllerScope = HPA_SCOPE,
) -> VpaReview:
    evidence = CurrentVpaEvidence.model_validate(current)
    generation = (
        None
        if generation_at is None
        else VpaGenerationEvidence(
            recommendation_digest=digest or vpa_recommendation_digest(evidence),
            generated_at=generation_at,
        )
    )
    return review_current_vpa(
        evidence,
        expected_scope=VPA_SCOPE,
        as_of=END,
        max_age=timedelta(minutes=5),
        generation=generation,
        hpa_evidence=history,
        expected_hpa_scope=hpa_scope,
        reviewed_window=WINDOW,
    )


def test_current_vpa_context_and_cpu_sensitivity_have_separate_evidence(
    current: dict[str, Any],
) -> None:
    result = _review(current, history=_history())
    assert result.context is not None
    assert result.context.update_mode == "Off"
    assert result.context.observed_at == END
    assert result.context.recommendation_age == timedelta(minutes=1)
    assert result.context.cpu is not None and result.context.memory is not None
    assert result.context.cpu.current_request == 500
    assert result.context.cpu.uncapped == 175
    assert result.context.memory.unit == "MiB"
    assert result.context.memory.target == 512
    assert result.context.memory.policy_maximum == 2048
    assert result.sensitivity is not None
    assert result.sensitivity.observed_at == AT
    assert result.sensitivity.observed_utilization_percent == 50
    assert result.sensitivity.unchanged_usage_utilization_percent == 100


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("no_history", "missing_hpa_timeline"),
        ("no_target", "unqualified_hpa_timeline"),
        ("changed_request", "request_basis_mismatch"),
        ("zero_request", "request_basis_mismatch"),
        ("different_hpa", "hpa_scope_mismatch"),
        ("different_workload", "hpa_scope_mismatch"),
        ("different_revision", "request_basis_mismatch"),
        ("heterogeneous_basis", "unsupported_cpu_request_basis"),
        ("no_generation", "unverified_recommendation_generation"),
        ("wrong_digest", "unverified_recommendation_generation"),
        ("stale_generation", "unverified_recommendation_generation"),
    ],
)
def test_current_context_does_not_make_sensitivity_eligible(
    current: dict[str, Any], case: str, reason: str
) -> None:
    history = (
        None
        if case == "no_history"
        else _history(request=450 if case == "changed_request" else 500, target=case != "no_target")
    )
    generation_at = AT
    expected_scope = HPA_SCOPE
    if case == "different_hpa":
        current["cpu_basis"]["hpa_uid"] = "recreated-hpa"
    if case == "different_workload":
        expected_scope = HPA_SCOPE.model_copy(update={"workload_uid": "recreated-deployment"})
    if case == "different_revision":
        current["cpu_basis"]["request_revision"] = "new-template"
    if case == "heterogeneous_basis":
        current.pop("cpu_basis")
    if case == "zero_request":
        current["request_cpu_mcpu"] = 0
    if case == "stale_generation":
        generation_at -= timedelta(minutes=6)
    result = _review(
        current,
        history=history,
        generation_at=None if case == "no_generation" else generation_at,
        digest="0" * 64 if case == "wrong_digest" else None,
        hpa_scope=expected_scope,
    )
    assert result.context is not None
    assert result.sensitivity is None
    assert result.sensitivity_blocker == reason


def test_unmatched_generation_cannot_borrow_freshness_from_status(
    current: dict[str, Any],
) -> None:
    result = _review(current, history=_history(), digest="0" * 64)
    assert result.context is not None and result.context.recommendation_age is None


@pytest.mark.parametrize("case", ["different_vpa", "mutating", "stale", "partial"])
def test_unreviewed_current_vpa_cannot_produce_a_card(current: dict[str, Any], case: str) -> None:
    if case == "different_vpa":
        current["vpa"]["uid"] = "recreated-vpa"
    elif case == "mutating":
        current["vpa"]["update_mode"] = "Auto"
    elif case == "stale":
        current["observed_at"] = AT - timedelta(minutes=6)
    else:
        current["source_status"] = "partial"
    result = _review(current, history=_history())
    assert result.context is None and result.context_blocker is not None
    assert result.sensitivity is None


def test_invalid_cpu_does_not_hide_independent_memory_context(current: dict[str, Any]) -> None:
    current["vpa"]["recommendations"][0]["target"]["cpu_mcores"] = 0
    result = _review(current, history=_history())
    assert result.context is not None
    assert result.context.cpu is None and result.context.memory is not None
    assert result.sensitivity is None
    assert result.sensitivity_blocker == "missing_cpu_context"
