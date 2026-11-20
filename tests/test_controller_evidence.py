import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from aks_fleet_efficiency.controller_evidence import (
    ControllerEvidence,
    ControllerScope,
    ControllerTimeline,
    ControllerWindow,
    qualify_controller_timeline,
)

START = datetime(2026, 11, 19, 12, tzinfo=UTC)
END = START + timedelta(minutes=3)
SCOPE = {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "cluster_resource_id": (
        "/subscriptions/00000000-0000-0000-0000-000000000002/resourcegroups/fixture"
        "/providers/Microsoft.ContainerService/managedClusters/fixture"
    ),
    "cluster_uid": "fixture-cluster-incarnation",
    "namespace_uid": "fixture-namespace",
    "workload_uid": "fixture-deployment",
    "hpa_uid": "fixture-hpa",
    "workload_kind": "Deployment",
    "metric_kind": "Resource",
    "resource": "cpu",
    "target_type": "Utilization",
    "unit": "percent",
    "producer": "synthetic-controller-v1",
}
WINDOW = {"start": START.isoformat(), "end": END.isoformat(), "step_seconds": 60}


@pytest.fixture
def saved_controller_evidence() -> dict[str, Any]:
    def series(*values: object) -> list[dict[str, Any]]:
        return [
            {
                "scope": dict(SCOPE),
                "configuration_revision": "hpa-v1",
                "request_revision": "pod-template-v1",
                "observed_at": (START + timedelta(minutes=i)).isoformat(),
                "captured_at": END.isoformat(),
                "observation_ref": f"fixture-row-{i}",
                "value": value,
            }
            for i, value in enumerate(values)
        ]

    return {
        "schema_version": "1.0",
        "window": dict(WINDOW),
        "source_status": "complete",
        "signal": series(50, 0, 76),
        "target": series(70, 70, 70),
        "hpa_replicas": series(*({"desired": 4, "current": 3},) * 3),
        "request_mcpu_per_pod": series(500, 500, 500),
        "deployment_availability": series(*({"ready": 2, "available": 0},) * 3),
    }


def _qualify(saved: dict[str, Any], *, as_of: datetime = END) -> ControllerTimeline:
    return qualify_controller_timeline(
        ControllerEvidence.model_validate_json(json.dumps(saved)),
        expected_scope=ControllerScope.model_validate(SCOPE),
        reviewed_window=ControllerWindow.model_validate(WINDOW),
        as_of=as_of,
        max_age=timedelta(minutes=5),
    )


def test_aligns_actual_signal_and_target_without_substituting_hpa_current_for_ready(
    saved_controller_evidence: dict[str, Any],
) -> None:
    saved_controller_evidence["signal"].reverse()
    result = _qualify(saved_controller_evidence)
    assert result.status == "qualified"
    assert result.covered_slots == result.expected_slots == 3
    assert result.segment_starts == (START,)
    first, second, _ = result.points
    assert first.signal is not None and first.signal.value == 50
    assert first.signal.observed_at == START and first.signal.captured_at == END
    assert first.target is not None and first.target.value == 70
    assert first.request_mcpu_per_pod is not None and first.request_mcpu_per_pod.value == 500
    assert first.hpa_replicas is not None and first.hpa_replicas.value.current == 3
    assert first.deployment_availability is not None
    assert first.deployment_availability.value.ready == 2
    assert first.deployment_availability.value.available == 0
    assert second.signal is not None and second.signal.value == 0


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("tenant_id", "00000000-0000-0000-0000-000000000003"),
        ("cluster_resource_id", str(SCOPE["cluster_resource_id"]) + "-other"),
        ("cluster_uid", "replacement-cluster"),
        ("namespace_uid", "replacement-namespace"),
        ("workload_uid", "replacement-deployment"),
        ("hpa_uid", "replacement-hpa"),
        ("producer", "other-producer"),
    ],
)
def test_unreviewed_scope_cannot_join(
    saved_controller_evidence: dict[str, Any], field: str, replacement: str
) -> None:
    saved_controller_evidence["signal"][0]["scope"][field] = replacement
    result = _qualify(saved_controller_evidence)
    assert result.status == "blocked"
    assert result.issues == ("scope_mismatch",)
    assert result.points == ()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("metric_kind", "ContainerResource"), ("target_type", "AverageValue"), ("unit", "mCPU")],
)
def test_rejects_non_cpu_utilization_shape(
    saved_controller_evidence: dict[str, Any], field: str, replacement: str
) -> None:
    saved_controller_evidence["signal"][0]["scope"][field] = replacement
    with pytest.raises(ValidationError):
        _qualify(saved_controller_evidence)


@pytest.mark.parametrize(
    ("revision", "series", "new_value"),
    [("configuration_revision", "target", 80), ("request_revision", "request_mcpu_per_pod", 250)],
)
def test_splits_changed_configuration_or_request_basis(
    saved_controller_evidence: dict[str, Any], revision: str, series: str, new_value: int
) -> None:
    for key in (
        "signal",
        "target",
        "hpa_replicas",
        "request_mcpu_per_pod",
        "deployment_availability",
    ):
        for sample in saved_controller_evidence[key][1:]:
            sample[revision] = "v2"
    for sample in saved_controller_evidence[series][1:]:
        sample["value"] = new_value
    result = _qualify(saved_controller_evidence)
    assert result.status == "segmented"
    assert result.segment_starts == (START, START + timedelta(minutes=1))
    assert result.covered_slots == 3


def test_mixed_revisions_cannot_join_even_with_all_series_present(
    saved_controller_evidence: dict[str, Any],
) -> None:
    saved_controller_evidence["target"][1]["configuration_revision"] = "other-configuration"
    result = _qualify(saved_controller_evidence)
    assert result.status == "partial"
    assert result.issues == ("revision_mismatch",)
    assert result.covered_slots == 2
    assert result.segment_starts == ()
    assert result.points[1].signal is result.points[1].target is None


@pytest.mark.parametrize("series", ["target", "request_mcpu_per_pod"])
def test_rejects_value_changes_disguised_as_a_stable_revision(
    saved_controller_evidence: dict[str, Any], series: str
) -> None:
    saved_controller_evidence[series][1]["value"] += 1
    result = _qualify(saved_controller_evidence)
    assert result.status == "blocked"
    assert result.issues == ("inconsistent_revision",)


@pytest.mark.parametrize("indices", [[], [0, 2]])
def test_missing_or_low_coverage_remains_unknown(
    saved_controller_evidence: dict[str, Any], indices: list[int]
) -> None:
    original = saved_controller_evidence["signal"]
    saved_controller_evidence["signal"] = [original[i] for i in indices]
    saved_controller_evidence["request_mcpu_per_pod"].pop(1)
    saved_controller_evidence["deployment_availability"].pop(1)
    result = _qualify(saved_controller_evidence)
    assert result.status == "partial"
    assert result.issues == ("missing_hpa_observations",)
    assert result.covered_slots == len(indices)
    assert result.segment_starts == ()
    middle = result.points[1]
    assert middle.signal is None
    assert middle.request_mcpu_per_pod is None
    assert middle.deployment_availability is None
    assert middle.target is not None and middle.hpa_replicas is not None


def test_optional_context_can_be_missing_without_hiding_complete_hpa_history(
    saved_controller_evidence: dict[str, Any],
) -> None:
    saved_controller_evidence["deployment_availability"] = []
    saved_controller_evidence["request_mcpu_per_pod"].pop(0)
    result = _qualify(saved_controller_evidence)
    assert result.status == "qualified"
    assert result.points[0].request_mcpu_per_pod is None
    assert all(point.deployment_availability is None for point in result.points)


@pytest.mark.parametrize(
    ("offset", "issue"),
    [(timedelta(seconds=30), "off_grid"), (timedelta(minutes=3), "off_grid"), (None, "duplicate")],
)
def test_grid_does_not_round_deduplicate_or_use_end_as_a_sample(
    saved_controller_evidence: dict[str, Any], offset: timedelta | None, issue: str
) -> None:
    sample = deepcopy(saved_controller_evidence["signal"][0])
    if offset is not None:
        sample["observed_at"] = (START + offset).isoformat()
    saved_controller_evidence["signal"].append(sample)
    result = _qualify(saved_controller_evidence)
    assert result.status == "blocked"
    assert result.issues == (issue,)


def test_freshness_uses_observation_not_export_clock(
    saved_controller_evidence: dict[str, Any],
) -> None:
    exact_limit = START + timedelta(minutes=7)
    assert _qualify(saved_controller_evidence, as_of=exact_limit).status == "qualified"
    later = exact_limit + timedelta(seconds=1)
    for observation in saved_controller_evidence["signal"]:
        observation["captured_at"] = later.isoformat()
    result = _qualify(saved_controller_evidence, as_of=later)
    assert result.status == "blocked"
    assert result.issues == ("stale",)


def test_rejects_future_capture_and_unreviewed_window(
    saved_controller_evidence: dict[str, Any],
) -> None:
    assert _qualify(saved_controller_evidence, as_of=START).issues == ("future_window",)
    saved_controller_evidence["target"][0]["captured_at"] = (END + timedelta(seconds=1)).isoformat()
    assert _qualify(saved_controller_evidence).issues == ("invalid_capture_time",)
    saved_controller_evidence["window"]["step_seconds"] = 30
    assert _qualify(saved_controller_evidence).issues == ("window_mismatch",)


@pytest.mark.parametrize("source_status", ["partial", "denied"])
def test_source_gap_never_qualifies_even_with_apparently_complete_samples(
    saved_controller_evidence: dict[str, Any], source_status: str
) -> None:
    saved_controller_evidence["source_status"] = source_status
    result = _qualify(saved_controller_evidence)
    assert result.status == "blocked"
    assert result.issues == (f"source_{source_status}",)
    assert result.points == ()


@pytest.mark.parametrize(
    ("series", "value"),
    [
        ("signal", "50"),
        ("signal", True),
        ("target", 0),
        ("request_mcpu_per_pod", 0),
        ("deployment_availability", {"ready": 1, "available": 2}),
    ],
)
def test_invalid_observations_are_not_coerced(
    saved_controller_evidence: dict[str, Any], series: str, value: object
) -> None:
    saved_controller_evidence[series][0]["value"] = value
    with pytest.raises(ValidationError):
        _qualify(saved_controller_evidence)


def test_clock_and_window_must_be_explicit_and_bounded(
    saved_controller_evidence: dict[str, Any],
) -> None:
    saved_controller_evidence["signal"][0]["observed_at"] = int(START.timestamp())
    with pytest.raises(ValidationError, match="explicit timezone-aware timestamp"):
        _qualify(saved_controller_evidence)
    with pytest.raises(ValidationError, match="1440 whole grid slots"):
        ControllerWindow(start=START, end=START + timedelta(seconds=1441), step_seconds=1)
