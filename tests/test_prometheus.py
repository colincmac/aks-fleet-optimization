from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from aks_fleet_efficiency.collectors import prometheus as prometheus_module
from aks_fleet_efficiency.collectors.prometheus import (
    MetricEntity,
    MetricReadError,
    PrometheusHttpReader,
    PrometheusMetricCollector,
    RangeQueryResult,
)
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import PrometheusMetricsSnapshot

SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)
START = datetime(2026, 10, 28, tzinfo=UTC)
END = START + timedelta(minutes=20)
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def profile() -> OnboardingConfig:
    return OnboardingConfig.model_validate(
        {
            "scope": {"tenant_id": SUBSCRIPTION, "subscription_ids": [SUBSCRIPTION]},
            "report_directory": "reports",
            "metric_sources": [
                {
                    "name": "synthetic",
                    "type": "prometheus",
                    "endpoint": "https://metrics.example.invalid",
                    "authentication": "anonymous",
                    "label_mapping": {
                        "cluster_resource_id": "azure_resource_id",
                        "namespace": "namespace",
                        "workload": "workload",
                        "workload_kind": "workload_kind",
                        "container": "container",
                    },
                }
            ],
            "clusters": [{"resource_id": CLUSTER, "metric_source": "synthetic"}],
        }
    )


def entity() -> MetricEntity:
    return MetricEntity(
        cluster_resource_id=CLUSTER,
        namespace="orders",
        workload_kind="Deployment",
        workload="orders",
        workload_uid="workload-uid",
        pod_uid="pod-uid",
        container="api",
    )


def labels() -> dict[str, str]:
    return {
        "azure_resource_id": CLUSTER,
        "namespace": "orders",
        "workload_kind": "Deployment",
        "workload": "orders",
        "workload_uid": "workload-uid",
        "pod_uid": "pod-uid",
        "container": "api",
    }


def matrix(values: list[float], *, start: datetime = START) -> RangeQueryResult:
    return RangeQueryResult(
        series=[
            {
                "metric": labels(),
                "values": [
                    [(start + timedelta(seconds=index * 300)).timestamp(), str(value)]
                    for index, value in enumerate(values)
                ],
            }
        ],
        observed_at=AS_OF,
    )


class FakeMetricReader:
    source_name = "synthetic"

    def __init__(self, results: list[RangeQueryResult | MetricReadError]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, datetime, datetime, int]] = []

    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult:
        self.calls.append((query, start, end, step_seconds))
        result = self.results.pop(0)
        if isinstance(result, MetricReadError):
            raise result
        return result


def collect(reader: FakeMetricReader, **options: Any) -> Any:
    return PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[entity()],
        clock=lambda: AS_OF,
        sleep=lambda _: None,
        **options,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=["cpu_usage"])


def test_aligned_samples_produce_percentiles_without_raw_sample_output() -> None:
    reader = FakeMetricReader([matrix([100, 200, 300, 400])])
    result = collect(reader)
    assert result.collection.status == "complete"
    observation = result.observations[0]
    assert observation.p50 == 250
    assert observation.p95 == pytest.approx(385)
    assert observation.p99 == pytest.approx(397)
    assert observation.maximum == 400
    assert observation.quality.window.sample_count == 4
    assert observation.quality.window.coverage_ratio == 1
    assert '"values"' not in result.model_dump_json()
    assert '"samples"' not in result.model_dump_json()


@pytest.mark.parametrize(
    "metric",
    ["hpa_min_replicas", "hpa_max_replicas", "hpa_desired_replicas", "hpa_current_replicas"],
)
def test_hpa_catalog_queries_require_workload_and_controller_uid(metric: str) -> None:
    target = MetricEntity(
        kind="hpa",
        cluster_resource_id=CLUSTER,
        namespace="orders",
        workload_kind="Deployment",
        workload="orders",
        workload_uid="workload-uid",
        hpa_uid="synthetic-hpa-uid",
    )
    response = matrix([1, 1, 1, 1])
    response.series[0]["metric"] = {
        key: value for key, value in labels().items() if key not in {"pod_uid", "container"}
    }
    response.series[0]["metric"]["hpa_uid"] = target.hpa_uid
    reader = FakeMetricReader([response])
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[target],
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=[metric])
    assert result.collection.status == "complete"
    assert result.observations[0].entity.hpa_uid == target.hpa_uid
    assert result.observations[0].minimum == result.observations[0].maximum == 1
    assert result.observations[0].quality.unit == "pods"
    assert result.observations[0].quality.window.coverage_ratio == 1
    query = reader.calls[0][0]
    assert f"aks_advisor:{metric}" in query
    assert 'hpa_uid="synthetic-hpa-uid"' in query
    assert 'workload_uid="workload-uid"' in query
    assert "pod_uid" not in query


@pytest.mark.parametrize("uid", [None, "synthetic-other-hpa"])
def test_hpa_history_never_falls_back_to_display_names(uid: str | None) -> None:
    target = MetricEntity(
        kind="hpa",
        cluster_resource_id=CLUSTER,
        namespace="orders",
        workload_kind="Deployment",
        workload="orders",
        workload_uid="workload-uid",
        hpa_uid="synthetic-hpa-uid",
    )
    response = matrix([1, 1, 1, 1])
    response.series[0]["metric"] = {
        key: value for key, value in labels().items() if key not in {"pod_uid", "container"}
    }
    if uid is not None:
        response.series[0]["metric"]["hpa_uid"] = uid
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=FakeMetricReader([response]),
        entities=[target],
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=["hpa_min_replicas"])
    assert result.collection.status == "partial"
    assert result.observations[0].minimum is None
    assert result.observations[0].issues


def test_hpa_entity_requires_its_uid_and_cannot_claim_pod_identity() -> None:
    value = entity().model_dump()
    value.update(kind="hpa", pod_uid=None, container=None)
    with pytest.raises(ValidationError):
        MetricEntity.model_validate(value)
    value.update(hpa_uid="synthetic-hpa-uid", pod_uid="synthetic-pod")
    with pytest.raises(ValidationError):
        MetricEntity.model_validate(value)


def test_approved_replica_envelope_queries_bind_historical_membership() -> None:
    response = matrix([100, 200, 300, 400])
    response.series[0]["metric"]["membership_digest"] = "a" * 64
    reader = FakeMetricReader([response])
    target = MetricEntity(
        kind="workload_container",
        cluster_resource_id=CLUSTER,
        namespace="orders",
        workload_kind="Deployment",
        workload="orders",
        workload_uid="workload-uid",
        container="api",
        membership_digest="a" * 64,
    )
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[target],
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=["replica_cpu_envelope"])
    assert result.observations[0].p95 == pytest.approx(385)
    assert 'membership_digest="' + "a" * 64 + '"' in reader.calls[0][0]
    assert "pod_uid=" not in reader.calls[0][0]
    assert result.collection.status == "complete"


def test_missing_series_is_unknown_not_zero_usage() -> None:
    result = collect(FakeMetricReader([RangeQueryResult(series=[], observed_at=AS_OF)]))
    assert result.collection.status == "partial"
    observation = result.observations[0]
    assert observation.p95 is None
    assert observation.quality.window.coverage_ratio == 0
    assert result.collection.missing_fields


def test_recreated_pod_name_cannot_join_another_uid() -> None:
    response = matrix([100, 200, 300, 400])
    response.series[0]["metric"]["pod_uid"] = "different-pod-uid"
    result = collect(FakeMetricReader([response]))
    assert result.collection.status != "complete"
    assert result.observations[0].p95 is None


@pytest.mark.parametrize("missing_label", ["workload_uid", "pod_uid"])
def test_retained_name_only_series_cannot_supply_historical_identity(
    missing_label: str,
) -> None:
    response = matrix([100, 200, 300, 400])
    del response.series[0]["metric"][missing_label]
    result = collect(FakeMetricReader([response]))
    assert result.collection.status == "partial"
    assert result.collection.missing_fields
    assert "insufficient-coverage" in result.observations[0].issues
    assert result.observations[0].p95 is None
    assert result.observations[0].quality.window.sample_count == 0
    assert result.observations[0].quality.window.coverage_ratio == 0


def test_throttling_retries_are_counted_and_bounded() -> None:
    reader = FakeMetricReader(
        [MetricReadError("throttled", retry_after_seconds=1), matrix([1, 2, 3, 4])]
    )
    result = collect(reader, max_retries=1)
    assert result.collection.status == "complete"
    assert result.collection.retry_count == 1


def test_query_uses_literal_scope_and_declared_identity_labels() -> None:
    reader = FakeMetricReader([matrix([1, 2, 3, 4])])
    collect(reader)
    query = reader.calls[0][0]
    assert f'azure_resource_id="{CLUSTER}"' in query
    assert 'pod_uid="pod-uid"' in query
    assert 'workload_uid="workload-uid"' in query


@pytest.mark.parametrize(
    ("metric", "expression", "unit", "counter"),
    [
        ("cpu_usage", "rate(container_cpu_usage_seconds_total", "mCPU", False),
        ("cpu_request", "kube_pod_container_resource_requests", "mCPU", False),
        ("cpu_throttling", "rate(container_cpu_cfs_throttled_periods_total", "ratio", False),
        ("oom_events", "increase(container_oom_events_total", "events", True),
    ],
)
def test_identity_enriched_source_shape_preserves_canonical_uid_labels(
    metric: str, expression: str, unit: str, counter: bool
) -> None:
    payload = profile().model_dump(mode="json")
    mapping = {
        "cluster_resource_id": "azure_cluster",
        "namespace": "ns",
        "workload_kind": "controller_kind",
        "workload": "controller",
        "container": "container_name",
    }
    payload["metric_sources"][0]["label_mapping"] = mapping
    response = matrix([0, 0, 0, 0], start=START + timedelta(seconds=300) if counter else START)
    response.series[0]["metric"] = {
        mapping.get("cluster_resource_id" if name == "azure_resource_id" else name, name): value
        for name, value in labels().items()
    }
    reader = FakeMetricReader([response])
    result = PrometheusMetricCollector(
        OnboardingConfig.model_validate(payload),
        source_name="synthetic",
        reader=reader,
        entities=[entity()],
        clock=lambda: AS_OF,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=[metric])
    observation = result.observations[0]
    assert result.collection.status == "complete"
    assert observation.quality.unit == unit
    assert observation.quality.window.coverage_ratio == 1
    assert (observation.total if counter else observation.p95) == 0
    query = reader.calls[0][0]
    assert expression in query
    assert f'azure_cluster="{CLUSTER}"' in query
    assert 'controller_kind="Deployment"' in query
    assert 'controller="orders"' in query
    assert 'ns="orders"' in query
    assert 'container_name="api"' in query
    assert 'workload_uid="workload-uid"' in query
    assert 'pod_uid="pod-uid"' in query


def test_range_batches_are_disjoint_and_preserve_coverage() -> None:
    reader = FakeMetricReader(
        [matrix([100, 200]), matrix([300, 400], start=START + timedelta(minutes=10))]
    )
    result = collect(reader, chunk_samples=2)
    assert result.collection.status == "complete"
    assert [(call[1], call[2]) for call in reader.calls] == [
        (START, START + timedelta(minutes=5)),
        (START + timedelta(minutes=10), START + timedelta(minutes=15)),
    ]
    assert result.observations[0].quality.window.sample_count == 4


@pytest.mark.parametrize("value", ["NaN", "+Inf", "-1", True])
def test_invalid_samples_never_qualify_as_complete(value: Any) -> None:
    response = matrix([1, 2, 3, 4])
    response.series[0]["values"][0][1] = value
    result = collect(FakeMetricReader([response]))
    assert result.collection.status != "complete"
    assert result.collection.errors[0].code == "invalid-response"


def test_partial_history_has_entity_specific_coverage() -> None:
    result = collect(FakeMetricReader([matrix([100, 200])]))
    assert result.observations[0].quality.window.coverage_ratio == 0.5
    assert "insufficient-coverage" in result.observations[0].issues
    assert result.collection.status == "partial"


def test_ambiguous_duplicate_series_are_not_averaged() -> None:
    response = matrix([1, 2, 3, 4])
    response.series.append(response.series[0].copy())
    result = collect(FakeMetricReader([response]))
    assert result.collection.errors[0].code == "identity-mismatch"
    assert result.observations[0].p95 is None


def test_identity_label_collisions_cannot_drop_the_cluster_scope() -> None:
    payload = profile().model_dump(mode="json")
    payload["metric_sources"][0]["label_mapping"]["cluster_resource_id"] = "pod_uid"
    reader = FakeMetricReader([])
    with pytest.raises(ValueError):
        PrometheusMetricCollector(
            OnboardingConfig.model_validate(payload),
            source_name="synthetic",
            reader=reader,
            entities=[entity()],
        )
    assert not reader.calls


def test_metrics_fragment_does_not_invent_fleet_wide_sample_coverage() -> None:
    result = collect(FakeMetricReader([matrix([1, 2, 3, 4])]))
    assert result.query_start == START
    assert result.query_end == END
    assert "metric_window" not in result.model_dump()


def test_node_pool_percentile_is_computed_after_aligned_summation() -> None:
    pool_id = f"{CLUSTER}/agentPools/apps"
    nodes = [
        MetricEntity(
            kind="node",
            cluster_resource_id=CLUSTER,
            node_uid=f"node-{index}",
            node_resource_id=f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-nodes/providers/Microsoft.Compute/virtualMachines/node-{index}",
            node_pool_resource_id=pool_id,
        )
        for index in range(2)
    ]
    responses = []
    for node, values in zip(nodes, [[1, 9, 1, 9], [9, 1, 9, 1]], strict=True):
        response = matrix(values)
        response.series[0]["metric"] = {
            "azure_resource_id": CLUSTER,
            "node_uid": node.node_uid,
            "node_resource_id": node.node_resource_id,
        }
        responses.append(response)
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=FakeMetricReader(responses),
        entities=nodes,
        clock=lambda: AS_OF,
        node_history_complete=True,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=["node_cpu_usage"])
    pool = next(item for item in result.observations if item.entity.kind == "node_pool")
    assert pool.entity.node_pool_resource_id == pool_id
    assert pool.p95 == 10
    assert pool.quality.window.coverage_ratio == 1


def fake_http(
    monkeypatch: pytest.MonkeyPatch, *, status: int = 200, body: bytes | None = None
) -> SimpleNamespace:
    state = SimpleNamespace(
        calls=[], options={}, closed=False, token_scopes=None, token_options=None
    )
    payload = (
        body
        if body is not None
        else json.dumps(
            {
                "status": "success",
                "data": {"resultType": "matrix", "result": matrix([1, 2, 3, 4]).series},
            }
        ).encode()
    )

    class Response:
        status_code = status
        headers: ClassVar[dict[str, str]] = {
            "Date": "Thu, 29 Oct 2026 12:00:00 GMT",
            "Retry-After": "2",
        }

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            state.response_closed = True

        def iter_bytes(self) -> Any:
            yield payload

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            state.options = kwargs

        def stream(self, method: str, url: str, **kwargs: Any) -> Response:
            state.calls.append((method, url, kwargs))
            return Response()

        def close(self) -> None:
            state.closed = True

    class Credential:
        def __init__(self, **kwargs: Any) -> None:
            state.credential_options = kwargs

        def get_token(self, *scopes: str, **kwargs: Any) -> SimpleNamespace:
            state.token_scopes = scopes
            state.token_options = kwargs
            claims = (
                base64.urlsafe_b64encode(json.dumps({"tid": SUBSCRIPTION}).encode())
                .decode()
                .rstrip("=")
            )
            return SimpleNamespace(token=f"synthetic.{claims}.signature")

        def close(self) -> None:
            state.credential_closed = True

    modules = {
        "httpx": SimpleNamespace(
            Client=Client,
            HTTPError=type("SyntheticHttpError", (Exception,), {}),
            TimeoutException=type("SyntheticTimeout", (Exception,), {}),
        ),
        "azure.identity": SimpleNamespace(DefaultAzureCredential=Credential),
        "azure.core.exceptions": SimpleNamespace(
            ClientAuthenticationError=type("SyntheticAuthenticationError", (Exception,), {}),
            ServiceRequestError=type("SyntheticServiceError", (Exception,), {}),
        ),
    }
    monkeypatch.setattr(prometheus_module, "import_module", lambda name: modules[name])
    return state


def test_http_reader_uses_verified_https_bounded_get_and_no_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = fake_http(monkeypatch)
    with PrometheusHttpReader(profile(), source_name="synthetic") as reader:
        response = reader.query_range(query="up", start=START, end=END, step_seconds=300)
    method, url, parameters = state.calls[0]
    assert method == "GET"
    assert url == "https://metrics.example.invalid/api/v1/query_range"
    assert parameters["params"]["step"] == 300
    assert state.options["verify"] is True
    assert state.options["follow_redirects"] is False
    assert state.options["trust_env"] is False
    assert response.observed_at == AS_OF
    assert state.closed is True


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (301, "invalid-response"),
        (401, "unauthorized"),
        (403, "forbidden"),
        (429, "throttled"),
        (503, "unavailable"),
    ],
)
def test_http_errors_are_sanitized(monkeypatch: pytest.MonkeyPatch, status: int, code: str) -> None:
    fake_http(monkeypatch, status=status, body=b"synthetic-private-provider-body")
    with PrometheusHttpReader(profile(), source_name="synthetic") as reader:
        with pytest.raises(MetricReadError) as error:
            reader.query_range(query="up", start=START, end=END, step_seconds=300)
    assert error.value.code == code
    assert "synthetic-private" not in str(error.value)


def test_http_size_limit_is_enforced_without_persisting_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http(monkeypatch, body=b"x" * 2048)
    with PrometheusHttpReader(
        profile(), source_name="synthetic", max_response_bytes=1024
    ) as reader:
        with pytest.raises(MetricReadError):
            reader.query_range(query="up", start=START, end=END, step_seconds=300)


def test_bearer_environment_profile_is_not_read_implicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = profile().model_dump(mode="json")
    payload["metric_sources"][0].update(
        authentication="bearer-environment", token_environment_variable="SYNTHETIC_TOKEN"
    )
    state = fake_http(monkeypatch)
    monkeypatch.setenv("SYNTHETIC_TOKEN", "synthetic-secret")
    with pytest.raises(ValueError):
        PrometheusHttpReader(OnboardingConfig.model_validate(payload), source_name="synthetic")
    assert not state.calls


def test_managed_prometheus_uses_the_declared_tenant_and_metrics_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = profile().model_dump(mode="json")
    payload["metric_sources"][0].update(
        type="azure-managed-prometheus",
        authentication="default-azure-credential",
        endpoint="https://synthetic.eastus.prometheus.monitor.azure.com",
    )
    state = fake_http(monkeypatch)
    with PrometheusHttpReader(
        OnboardingConfig.model_validate(payload), source_name="synthetic"
    ) as reader:
        reader.query_range(query="up", start=START, end=END, step_seconds=300)
    assert state.token_scopes == ("https://prometheus.monitor.azure.com/.default",)
    assert state.token_options["tenant_id"] == SUBSCRIPTION
    assert state.credential_options["exclude_interactive_browser_credential"] is True


def test_managed_token_cannot_be_sent_to_a_generic_host(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = profile().model_dump(mode="json")
    payload["metric_sources"][0].update(
        type="azure-managed-prometheus", authentication="default-azure-credential"
    )
    state = fake_http(monkeypatch)
    with pytest.raises(ValueError):
        PrometheusHttpReader(OnboardingConfig.model_validate(payload), source_name="synthetic")
    assert not state.calls


def test_unverified_historical_node_membership_does_not_create_pool_opportunities() -> None:
    node = MetricEntity(
        kind="node",
        cluster_resource_id=CLUSTER,
        node_uid="node-uid",
        node_resource_id=f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-nodes/providers/Microsoft.Compute/virtualMachines/node",
        node_pool_resource_id=f"{CLUSTER}/agentPools/apps",
    )
    response = matrix([1, 2, 3, 4])
    response.series[0]["metric"] = {
        "azure_resource_id": CLUSTER,
        "node_uid": node.node_uid,
        "node_resource_id": node.node_resource_id,
    }
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=FakeMetricReader([response]),
        entities=[node],
        clock=lambda: AS_OF,
    ).collect_observations(start=START, end=END, metrics=["node_cpu_usage"])
    pool = next(item for item in result.observations if item.entity.kind == "node_pool")
    assert pool.p95 is None
    assert "unverified-historical-membership" in pool.issues
    assert result.collection.status == "partial"


def test_query_budget_rejection_happens_before_any_request() -> None:
    reader = FakeMetricReader([])
    collector = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[entity()],
        clock=lambda: AS_OF,
        chunk_samples=1,
        max_queries=1,
    )
    with pytest.raises(ValueError, match="query bound"):
        collector.collect_observations(start=START, end=END, metrics=["cpu_usage"])
    assert not reader.calls


def test_no_applicable_metric_is_not_successful_empty_collection() -> None:
    node = MetricEntity(
        kind="node",
        cluster_resource_id=CLUSTER,
        node_uid="node-uid",
        node_resource_id="synthetic-node-id",
    )
    reader = FakeMetricReader([])
    collector = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[node], clock=lambda: AS_OF
    )
    with pytest.raises(ValueError):
        collector.collect_observations(start=START, end=END, metrics=["cpu_usage"])
    assert not reader.calls


def test_default_window_uses_thirty_complete_utc_days() -> None:
    reader = FakeMetricReader([RangeQueryResult(series=[], observed_at=AS_OF)] * 9)
    result = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[entity()], clock=lambda: AS_OF
    ).collect_observations(metrics=["cpu_usage"])
    assert result.query_start == datetime(2026, 9, 29, tzinfo=UTC)
    assert result.query_end == datetime(2026, 10, 29, tzinfo=UTC)
    assert len(reader.calls) == 9


def test_missing_counter_series_does_not_claim_zero_oom_history() -> None:
    reader = FakeMetricReader([RangeQueryResult(series=[], observed_at=AS_OF)])
    result = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[entity()], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END, metrics=["oom_events"])
    assert result.observations[0].total is None
    assert "increase(container_oom_events_total" in reader.calls[0][0]
    assert "[300s]" in reader.calls[0][0]


def test_partial_counter_interval_cannot_claim_a_full_window_total() -> None:
    reader = FakeMetricReader([matrix([1, 1, 1, 1], start=START + timedelta(minutes=5))])
    result = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[entity()], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END + timedelta(seconds=1), metrics=["oom_events"])
    assert result.collection.status != "complete"
    assert "partial-delta-interval" in result.observations[0].issues
    assert result.observations[0].total is None
    assert all(call[2] <= END + timedelta(seconds=1) for call in reader.calls)


def test_optional_metrics_transport_is_declared() -> None:
    import tomllib
    from pathlib import Path

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert any(
        value.startswith("httpx>=0.28")
        for value in project["project"]["optional-dependencies"]["metrics"]
    )


def test_cpu_query_catalog_golden_expression() -> None:
    reader = FakeMetricReader([matrix([1, 2, 3, 4])])
    collect(reader)
    expected = (
        "rate(container_cpu_usage_seconds_total{azure_resource_id="
        + json.dumps(CLUSTER)
        + ',container="api",namespace="orders",pod_uid="pod-uid",workload="orders",'
        'workload_kind="Deployment",workload_uid="workload-uid"}[5m]) * 1000'
    )
    assert reader.calls[0][0] == expected


def test_counter_queries_cover_disjoint_intervals_and_preserve_last_sample_time() -> None:
    reader = FakeMetricReader([matrix([1, 0, 2, 0], start=START + timedelta(minutes=5))])
    result = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[entity()], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END, metrics=["oom_events"])
    assert result.collection.status == "complete"
    assert result.observations[0].total == 3
    assert reader.calls[0][1] == START + timedelta(minutes=5)
    assert reader.calls[0][2] == END
    assert result.observations[0].latest_sample_at == END


def test_provider_warnings_make_the_receipt_partial_without_echoing_text() -> None:
    response = RangeQueryResult(
        series=matrix([1, 2, 3, 4]).series, observed_at=AS_OF, warnings=True
    )
    result = collect(FakeMetricReader([response]))
    assert result.collection.status == "partial"
    assert "provider-warning" in result.observations[0].issues


def test_http_reader_with_installed_client_and_mock_transport() -> None:
    httpx = pytest.importorskip("httpx")
    requests: list[Any] = []

    def respond(request: Any) -> Any:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"Date": "Thu, 29 Oct 2026 12:00:00 GMT"},
            json={"status": "success", "data": {"resultType": "matrix", "result": []}},
        )

    with PrometheusHttpReader(
        profile(), source_name="synthetic", transport=httpx.MockTransport(respond)
    ) as reader:
        response = reader.query_range(query="up", start=START, end=END, step_seconds=300)
    assert response.series == []
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v1/query_range"


def test_metrics_fragment_round_trip_and_committed_schema_parity() -> None:
    result = collect(FakeMetricReader([matrix([1, 2, 3, 4])]))
    assert PrometheusMetricsSnapshot.model_validate_json(result.model_dump_json()) == result
    committed = json.loads(
        Path("schemas/prometheus-metrics.schema.json").read_text(encoding="utf-8")
    )
    assert committed == PrometheusMetricsSnapshot.model_json_schema()


def test_metrics_fragment_rejects_reversed_query_range() -> None:
    result = collect(FakeMetricReader([matrix([1, 2, 3, 4])]))
    payload = result.model_dump() | {"query_start": END, "query_end": START}
    with pytest.raises(ValidationError):
        PrometheusMetricsSnapshot.model_validate(payload)


def test_acceptable_coverage_does_not_hide_a_stale_series_tail() -> None:
    configured = profile()
    configured.analysis.thresholds.minimum_coverage_ratio = 0.75
    configured.analysis.thresholds.maximum_evidence_age_hours = 0.01
    reader = FakeMetricReader([matrix([1, 2, 3])])
    result = PrometheusMetricCollector(
        configured, source_name="synthetic", reader=reader, entities=[entity()], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END, metrics=["cpu_usage"])
    assert result.observations[0].quality.window.coverage_ratio == 0.75
    assert "stale-series-tail" in result.observations[0].issues
    assert result.collection.status == "partial"


def test_workload_replica_history_uses_workload_uid_without_a_fabricated_pod() -> None:
    workload = MetricEntity(
        kind="workload",
        cluster_resource_id=CLUSTER,
        namespace="orders",
        workload_kind="Deployment",
        workload="orders",
        workload_uid="workload-uid",
    )
    response = matrix([2, 3, 4, 3])
    del response.series[0]["metric"]["container"]
    del response.series[0]["metric"]["pod_uid"]
    reader = FakeMetricReader([response])
    result = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[workload], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END, metrics=["desired_replicas"])
    assert result.collection.status == "complete"
    assert result.observations[0].p50 == 3
    assert 'workload_uid="workload-uid"' in reader.calls[0][0]
    assert "pod_uid=" not in reader.calls[0][0]


@pytest.mark.parametrize(
    "metric",
    [
        "desired_replicas",
        "available_replicas",
        "observed_replicas",
        "hpa_present",
        "keda_present",
        "vpa_present",
    ],
)
def test_absent_upstream_recording_is_not_zero_replica_or_controller_history(metric: str) -> None:
    target = entity().model_dump() | {"kind": "workload", "pod_uid": None, "container": None}
    reader = FakeMetricReader([RangeQueryResult(series=[], observed_at=AS_OF)])
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[MetricEntity.model_validate(target)],
        clock=lambda: AS_OF,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=[metric])
    observation = result.observations[0]
    assert result.collection.status == "partial"
    assert result.collection.missing_fields
    assert observation.minimum is None
    assert observation.maximum is None
    assert observation.p95 is None
    assert observation.quality.window.coverage_ratio == 0
    assert "aks_advisor:workload_" in reader.calls[0][0]


@pytest.mark.parametrize("digest", [None, "b" * 64])
def test_replica_source_without_matching_roster_digest_stays_unsupported(
    digest: str | None,
) -> None:
    response = matrix([100, 200, 300, 400])
    del response.series[0]["metric"]["pod_uid"]
    if digest is not None:
        response.series[0]["metric"]["membership_digest"] = digest
    target = entity().model_dump() | {
        "kind": "workload_container",
        "pod_uid": None,
        "membership_digest": "a" * 64,
    }
    reader = FakeMetricReader([response])
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[MetricEntity.model_validate(target)],
        clock=lambda: AS_OF,
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=["replica_cpu_envelope"])
    assert result.collection.status == "partial"
    assert result.collection.missing_fields
    assert result.observations[0].p95 is None
    assert result.observations[0].quality.window.coverage_ratio == 0
    assert 'membership_digest="' + "a" * 64 + '"' in reader.calls[0][0]


def test_minimum_catalog_includes_restart_replica_pending_and_autoscaler_history() -> None:
    assert {
        "restarts",
        "desired_replicas",
        "available_replicas",
        "unschedulable_pods",
        "hpa_present",
        "keda_present",
        "vpa_present",
    } <= prometheus_module.QUERY_CATALOG.keys()


def test_restart_intervals_use_counter_increase() -> None:
    reader = FakeMetricReader([matrix([0, 1, 0, 0], start=START + timedelta(minutes=5))])
    result = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[entity()], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END, metrics=["restarts"])
    assert result.observations[0].total == 1
    assert "increase(kube_pod_container_status_restarts_total" in reader.calls[0][0]
