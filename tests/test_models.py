import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from aks_fleet_efficiency.collectors.fixture import FixtureCollector
from aks_fleet_efficiency.config import AdvisorConfig, load_config
from aks_fleet_efficiency.models import (
    AnalysisReport,
    AutoscalingState,
    CollectionManifest,
    CollectorResult,
    FleetSnapshot,
    MetricQuality,
    MetricWindow,
    ResourceObservation,
    WorkloadSafetyPolicy,
    merge_collector_results,
)


def collector_result_payload() -> dict[str, Any]:
    return {
        "collector": "azure-inventory",
        "status": "complete",
        "requested_scope": ["synthetic-subscription"],
        "completed_scope": ["synthetic-subscription"],
        "started_at": "2026-10-29T00:00:00Z",
        "completed_at": "2026-10-29T00:01:00Z",
        "source_observed_at": "2026-10-29T00:00:00Z",
        "pagination_complete": True,
        "retry_count": 0,
    }


def metric_quality_payload() -> dict[str, Any]:
    return {
        "source": "synthetic-prometheus",
        "query_version": "cpu-usage-v1",
        "step_seconds": 300,
        "observed_at": "2026-10-29T00:01:00Z",
        "window": {
            "start": "2026-09-29T00:00:00Z",
            "end": "2026-10-29T00:00:00Z",
            "sample_count": 8640,
            "coverage_ratio": 1,
        },
        "unit": "mCPU",
        "minimum": 0,
        "maximum": 250,
    }


def test_fixture_is_valid() -> None:
    snapshot = FixtureCollector(Path("examples/fixtures/fleet-snapshot.json")).collect()
    assert snapshot.schema_version == "1.0"


def test_metric_window_rejects_reverse_range() -> None:
    with pytest.raises(ValidationError):
        MetricWindow.model_validate(
            {
                "start": "2026-10-28T00:00:00Z",
                "end": "2026-10-27T00:00:00Z",
                "sample_count": 1,
                "coverage_ratio": 1,
            }
        )


@pytest.mark.parametrize("field", ["start", "end"])
def test_metric_window_rejects_naive_timestamps(field: str) -> None:
    payload = metric_quality_payload()["window"]
    payload[field] = payload[field].removesuffix("Z")
    with pytest.raises(ValidationError):
        MetricWindow.model_validate(payload)


def test_metric_window_normalizes_offsets_to_utc() -> None:
    window = MetricWindow(
        start=datetime(2026, 9, 29, tzinfo=UTC),
        end=datetime.fromisoformat("2026-10-29T02:00:00+02:00"),
        sample_count=10,
        coverage_ratio=1,
    )
    assert window.end == datetime(2026, 10, 29, tzinfo=UTC)
    assert window.end.utcoffset() == timedelta(0)


def test_zero_samples_cannot_claim_positive_coverage() -> None:
    payload = metric_quality_payload()["window"]
    payload.update(sample_count=0, coverage_ratio=0.5)
    with pytest.raises(ValidationError):
        MetricWindow.model_validate(payload)


def test_collection_result_round_trip() -> None:
    result = CollectorResult.model_validate(collector_result_payload())
    assert CollectorResult.model_validate_json(result.model_dump_json()) == result
    assert result.schema_version == "1.0"


@pytest.mark.parametrize(
    "overrides",
    [
        {"pagination_complete": False},
        {"completed_scope": []},
        {"completed_scope": ["out-of-scope-subscription"]},
        {"requested_scope": []},
        {"requested_scope": ["synthetic-subscription", "synthetic-subscription"]},
        {"completed_scope": ["synthetic-subscription", "synthetic-subscription"]},
        {"missing_fields": ["node_pools.vm_size"]},
        {"errors": [{"scope": "synthetic-subscription", "code": "forbidden"}]},
        {"retry_count": -1},
        {"requested_scope": [""]},
        {"completed_at": "2026-10-28T00:00:00Z"},
        {"started_at": "2026-10-29T00:00:00"},
        {"completed_at": "2026-10-29T00:01:00"},
        {"source_observed_at": "2026-10-29T00:00:00"},
        {"source_observed_at": "2026-10-29T00:02:00Z"},
        {"schema_version": "99.0"},
        {"status": "partial"},
        {
            "status": "partial",
            "completed_scope": [],
            "errors": [{"scope": "out-of-scope-subscription", "code": "forbidden"}],
        },
        {
            "status": "failed",
            "completed_scope": [],
            "errors": [
                {"scope": "synthetic-subscription", "code": "forbidden", "message": "raw text"}
            ],
        },
    ],
)
def test_collection_result_rejects_invalid_completeness(overrides: dict[str, Any]) -> None:
    payload = collector_result_payload() | overrides
    with pytest.raises(ValidationError):
        CollectorResult.model_validate(payload)


def test_partial_collection_preserves_failures_and_uncompleted_scope() -> None:
    payload = collector_result_payload()
    payload.update(
        status="partial",
        requested_scope=["synthetic-subscription", "denied-subscription"],
        errors=[{"scope": "denied-subscription", "code": "forbidden"}],
    )
    result = CollectorResult.model_validate(payload)
    assert result.completed_scope == ["synthetic-subscription"]
    assert result.errors[0].code == "forbidden"


def test_failed_collection_cannot_claim_completed_scope() -> None:
    payload = collector_result_payload() | {"status": "failed"}
    with pytest.raises(ValidationError):
        CollectorResult.model_validate(payload)


@pytest.mark.parametrize(
    ("statuses", "manifest_status"),
    [
        (["complete"], "complete"),
        (["complete", "failed"], "partial"),
        (["failed"], "failed"),
        (["partial"], "partial"),
    ],
)
def test_manifest_status_matches_collector_results(
    statuses: list[str], manifest_status: str
) -> None:
    results = []
    for index, status in enumerate(statuses):
        payload = collector_result_payload() | {"collector": f"source-{index}", "status": status}
        if status == "failed":
            payload.update(
                completed_scope=[],
                pagination_complete=False,
                errors=[{"scope": "synthetic-subscription", "code": "timeout"}],
            )
        elif status == "partial":
            payload.update(pagination_complete=False)
        results.append(payload)
    manifest = CollectionManifest.model_validate(
        {
            "tenant_id": "synthetic-tenant",
            "status": manifest_status,
            "results": results,
            "source_results": results,
        }
    )
    assert CollectionManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_manifest_cannot_hide_partial_collection() -> None:
    result = collector_result_payload() | {"status": "partial", "pagination_complete": False}
    with pytest.raises(ValidationError):
        CollectionManifest.model_validate(
            {"tenant_id": "synthetic-tenant", "status": "complete", "results": [result]}
        )


def test_manifest_requires_collector_results() -> None:
    with pytest.raises(ValidationError):
        CollectionManifest.model_validate(
            {"tenant_id": "synthetic-tenant", "status": "complete", "results": []}
        )


def test_manifest_rejects_duplicate_collectors() -> None:
    with pytest.raises(ValidationError):
        CollectionManifest.model_validate(
            {
                "tenant_id": "synthetic-tenant",
                "status": "complete",
                "results": [collector_result_payload(), collector_result_payload()],
            }
        )


def scoped_manifest_payload() -> dict[str, Any]:
    complete = CollectorResult.model_validate(collector_result_payload())
    failed = CollectorResult.model_validate(
        collector_result_payload()
        | {
            "status": "failed",
            "requested_scope": ["denied-subscription"],
            "completed_scope": [],
            "pagination_complete": False,
            "source_observed_at": None,
            "retry_count": 2,
            "errors": [{"scope": "denied-subscription", "code": "forbidden"}],
        }
    )
    return {
        "schema_version": "1.0",
        "tenant_id": "synthetic-tenant",
        "status": "partial",
        "results": [merge_collector_results([complete, failed]).model_dump(mode="json")],
        "source_results": [complete.model_dump(mode="json"), failed.model_dump(mode="json")],
    }


def test_scoped_manifest_retains_receipt_clocks_failures_and_exact_aggregate() -> None:
    manifest = CollectionManifest.model_validate(scoped_manifest_payload())
    assert manifest.results[0].retry_count == 2
    assert manifest.results[0].source_observed_at is None
    assert manifest.source_results[0].source_observed_at is not None
    assert manifest.source_results[1].errors[0].code == "forbidden"
    assert CollectionManifest.model_validate_json(manifest.model_dump_json()) == manifest


@pytest.mark.parametrize(
    "defect",
    [
        "missing-sources",
        "overlap",
        "retry-count",
        "source-clock",
        "missing-collector",
        "incomplete-pagination",
        "changed-status",
        "legacy-version",
    ],
)
def test_scoped_manifest_cannot_launder_or_omit_source_receipts(defect: str) -> None:
    payload = scoped_manifest_payload()
    if defect == "missing-sources":
        payload["source_results"] = []
    elif defect == "overlap":
        payload["source_results"].append(payload["source_results"][0].copy())
    elif defect == "retry-count":
        payload["results"][0]["retry_count"] = 0
    elif defect == "source-clock":
        payload["results"][0]["source_observed_at"] = "2026-10-29T00:00:00Z"
    elif defect == "missing-collector":
        payload["source_results"][1]["collector"] = "foreign-collector"
    elif defect == "incomplete-pagination":
        payload["results"][0]["pagination_complete"] = True
    elif defect == "changed-status":
        payload["source_results"][0].update(
            status="failed",
            pagination_complete=False,
            completed_scope=[],
            errors=[{"scope": "synthetic-subscription", "code": "forbidden"}],
        )
    else:
        payload["schema_version"] = "2.0"
    with pytest.raises(ValueError):
        CollectionManifest.model_validate(payload)


def test_manifest_serialization_always_retains_source_receipts() -> None:
    manifest = CollectionManifest(
        tenant_id="synthetic",
        status="complete",
        results=[CollectorResult.model_validate(collector_result_payload())],
        source_results=[CollectorResult.model_validate(collector_result_payload())],
    )
    assert "source_results" in manifest.model_dump(mode="json")
    assert "source_results" in json.loads(manifest.model_dump_json())


def test_metric_quality_round_trip_and_zero_is_not_missing() -> None:
    quality = MetricQuality.model_validate(metric_quality_payload())
    resources = ResourceObservation(
        usage_cpu_p95_mcores=0,
        metric_quality={"usage_cpu_p95_mcores": quality},
    )
    assert resources.usage_cpu_p95_mcores == 0
    assert resources.metric_quality["usage_cpu_p95_mcores"].minimum == 0
    assert ResourceObservation.model_validate_json(resources.model_dump_json()) == resources


@pytest.mark.parametrize(
    "overrides",
    [
        {"minimum": 300, "maximum": 250},
        {"minimum": float("nan")},
        {"maximum": float("inf")},
        {"step_seconds": 0},
        {"observed_at": "2026-10-29T00:01:00"},
        {"observed_at": "2026-10-28T00:00:00Z"},
        {"query_version": ""},
        {"source": ""},
    ],
)
def test_metric_quality_rejects_invalid_provenance(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MetricQuality.model_validate(metric_quality_payload() | overrides)


def test_missing_metric_series_is_distinct_from_zero_usage() -> None:
    payload = metric_quality_payload()
    payload["window"].update(sample_count=0, coverage_ratio=0)
    payload.update(minimum=None, maximum=None)
    resources = ResourceObservation(
        metric_quality={"usage_cpu_p95_mcores": MetricQuality.model_validate(payload)}
    )
    assert resources.usage_cpu_p95_mcores is None
    assert resources.metric_quality["usage_cpu_p95_mcores"].window.sample_count == 0
    assert ResourceObservation().metric_quality == {}


@pytest.mark.parametrize("field", ["minimum", "maximum"])
def test_missing_metric_series_cannot_claim_observed_extrema(field: str) -> None:
    payload = metric_quality_payload()
    payload["window"].update(sample_count=0, coverage_ratio=0)
    payload.update(minimum=None, maximum=None)
    payload[field] = 0
    with pytest.raises(ValidationError):
        MetricQuality.model_validate(payload)


def test_snapshot_supports_new_manifest_and_previous_fixture() -> None:
    original = FixtureCollector(Path("examples/fixtures/fleet-snapshot.json")).collect()
    assert original.schema_version == "1.0"
    assert original.collection_manifest is None
    payload = original.model_dump(mode="json")
    payload.update(
        schema_version="1.0",
        collection_manifest={
            "tenant_id": "synthetic-tenant",
            "status": "complete",
            "results": [collector_result_payload()],
            "source_results": [collector_result_payload()],
        },
    )
    current = FleetSnapshot.model_validate(payload)
    assert current.collection_manifest is not None
    assert FleetSnapshot.model_validate_json(current.model_dump_json()) == current


def test_new_snapshot_defaults_to_current_contract_and_preserves_identity_anchors() -> None:
    payload = FixtureCollector(Path("examples/fixtures/fleet-snapshot.json")).collect().model_dump()
    del payload["schema_version"]
    cluster = payload["clusters"][0]
    cluster["uid"] = "synthetic-cluster-uid"
    cluster["node_pools"][0]["resource_id"] = f"{cluster['resource_id']}/agentPools/apps"
    cluster["workloads"][0]["uid"] = "synthetic-workload-uid"
    current = FleetSnapshot.model_validate(payload)
    assert current.schema_version == "1.0"
    assert current.clusters[0].uid == "synthetic-cluster-uid"
    assert current.clusters[0].node_pools[0].resource_id == cluster["node_pools"][0]["resource_id"]
    assert current.clusters[0].workloads[0].uid == "synthetic-workload-uid"


def test_snapshot_rejects_naive_generation_timestamp() -> None:
    payload = FixtureCollector(Path("examples/fixtures/fleet-snapshot.json")).collect().model_dump()
    payload["generated_at"] = datetime(2026, 10, 29)
    with pytest.raises(ValidationError):
        FleetSnapshot.model_validate(payload)


def test_unsupported_snapshot_schema_is_rejected() -> None:
    payload = FixtureCollector(Path("examples/fixtures/fleet-snapshot.json")).collect().model_dump()
    payload["schema_version"] = "99.0"
    with pytest.raises(ValidationError):
        FleetSnapshot.model_validate(payload)


def test_assessment_defaults_to_thirty_days_with_explicit_override() -> None:
    assert AdvisorConfig().thresholds.minimum_observation_days == 30
    assert (
        load_config(Path("examples/advisor-config.yaml")).thresholds.minimum_observation_days == 30
    )
    assert (
        AdvisorConfig.model_validate(
            {"thresholds": {"minimum_observation_days": 45}}
        ).thresholds.minimum_observation_days
        == 45
    )


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("fleet-snapshot.schema.json", FleetSnapshot),
        ("analysis-report.schema.json", AnalysisReport),
    ],
)
def test_generated_schemas_match_executable_contracts(
    filename: str, model: type[BaseModel]
) -> None:
    committed = json.loads(Path("schemas", filename).read_text(encoding="utf-8"))
    assert committed == model.model_json_schema()


@pytest.mark.parametrize("version", ["1.0"])
def test_supported_snapshot_versions_preserve_explicit_observations(version: str) -> None:
    payload = FixtureCollector(Path("examples/fixtures/fleet-snapshot.json")).collect().model_dump()
    payload["schema_version"] = version
    snapshot = FleetSnapshot.model_validate(payload)
    assert snapshot.schema_version == version
    assert snapshot.clusters[0].workloads[0].autoscaling.hpa is False
    assert FleetSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_unobserved_safety_values_are_not_fabricated() -> None:
    assert AutoscalingState().hpa is None
    assert AutoscalingState().keda is None
    assert AutoscalingState().vpa is None
    assert ResourceObservation().memory_oom_events is None
    assert ResourceObservation().cpu_request_observed is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner", ""),
        ("slo_reference", ""),
        ("reviewed_window_start", "2026-09-29T00:00:00"),
        ("reviewed_window_end", "2026-09-28T00:00:00Z"),
        ("minimum_cpu_request_mcores", 0),
        ("maximum_cpu_reduction_ratio", 0),
        ("maximum_cpu_reduction_ratio", 1),
        ("cpu_headroom_factor", 0.99),
        ("cpu_headroom_factor", float("inf")),
        ("maximum_cpu_throttled_ratio", 1.01),
    ],
)
def test_safety_policy_rejects_invalid_owner_bounds_and_windows(field: str, value: Any) -> None:
    payload = {
        "owner": "synthetic-owner",
        "slo_reference": "synthetic-slo",
        "reviewed_window_start": "2026-09-29T00:00:00Z",
        "reviewed_window_end": "2026-10-29T00:00:00Z",
        "disruption_reviewed": True,
        "minimum_cpu_request_mcores": 100,
        "maximum_cpu_reduction_ratio": 0.5,
        "cpu_headroom_factor": 1.25,
        "maximum_cpu_throttled_ratio": 0.01,
    }
    payload[field] = value
    with pytest.raises(ValidationError):
        WorkloadSafetyPolicy.model_validate(payload)
