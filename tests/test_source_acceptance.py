from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from aks_fleet_efficiency.catalog import digest_json, load_catalog
from aks_fleet_efficiency.catalog.models import RenderedQuery
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.metric_queries import render_query
from aks_fleet_efficiency.collectors.prometheus import MetricReadError, RangeQueryResult
from aks_fleet_efficiency.config import OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.source_acceptance import (
    PrometheusQueryAcceptance,
    PrometheusQueryExecution,
    PrometheusQueryRequest,
    PrometheusSourceAcceptance,
    PrometheusSourceAcceptancePlan,
    collect_prometheus_source_acceptance,
    evaluate_prometheus_source_acceptance,
)

WINDOW_START = datetime(2026, 10, 29, 11, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64
CLUSTER = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/"
    "managedClusters/aks-synthetic"
)


def query_acceptance(
    *,
    status: str = "accepted",
    reason_codes: list[str] | None = None,
) -> PrometheusQueryAcceptance:
    return PrometheusQueryAcceptance(
        query_id="cpu_usage",
        query_version="1.0.0",
        expression_digest=DIGEST,
        unit="mCPU",
        status=status,
        reason_codes=[] if reason_codes is None else reason_codes,
        required_label_keys=["cluster_name", "namespace", "pod", "container"],
        observed_series=3,
        matched_expected_entities=3,
        expected_entities=3,
        duplicate_series=0,
        latest_sample_at=WINDOW_END,
    )


def source_acceptance(
    record: PrometheusQueryAcceptance,
    *,
    status: str = "accepted",
) -> PrometheusSourceAcceptance:
    return PrometheusSourceAcceptance(
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=(
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/"
            "managedClusters/aks-synthetic"
        ),
        cluster_uid="cluster-uid-synthetic",
        source="synthetic",
        source_profile_id="identity-enriched",
        source_profile_version="1.0.0",
        evaluated_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        step_seconds=60,
        status=status,
        reason_codes=[],
        input_digest=DIGEST,
        configuration_digest=DIGEST,
        records=[record],
    )


def test_prometheus_source_acceptance_admits_complete_fixed_window_evidence() -> None:
    accepted = source_acceptance(query_acceptance())

    assert accepted.status == "accepted"
    assert accepted.records[0].required_label_keys == [
        "cluster_name",
        "namespace",
        "pod",
        "container",
    ]
    assert accepted.endpoint is None
    assert accepted.live_time_picker_quality == "unknown"


@pytest.mark.parametrize("status", ["partial", "blocked"])
def test_prometheus_query_acceptance_requires_reasons_when_not_accepted(status: str) -> None:
    with pytest.raises(ValidationError, match="explicit reasons"):
        query_acceptance(status=status)


def test_prometheus_source_acceptance_cannot_overstate_query_records() -> None:
    record = query_acceptance(status="blocked", reason_codes=["cluster_label_value_mismatch"])

    with pytest.raises(ValidationError, match="must reflect query records"):
        source_acceptance(record)


def test_prometheus_source_acceptance_rejects_unordered_window() -> None:
    payload = source_acceptance(query_acceptance()).model_dump(mode="python")
    payload["window_start"] = WINDOW_END

    with pytest.raises(ValidationError, match="ordered fixed window"):
        PrometheusSourceAcceptance.model_validate(payload)


def execution(
    *, cluster: str = CLUSTER, duplicate: bool = False, samples: list[list[object]] | None = None
) -> PrometheusQueryExecution:
    expected_labels = {
        "cluster_name": CLUSTER,
        "namespace": "orders",
        "pod": "orders-abc",
        "container": "api",
    }
    observed_labels = {
        "cluster_name": cluster,
        "namespace": "orders",
        "pod": "orders-abc",
        "container": "api",
    }
    series = [
        {
            "metric": observed_labels,
            "values": samples
            if samples is not None
            else [
                [timestamp, "100"]
                for timestamp in range(
                    int(WINDOW_START.timestamp()), int(WINDOW_END.timestamp()) + 1, 60
                )
            ],
        }
    ]
    if duplicate:
        series.append(series[0])
    return PrometheusQueryExecution(
        query=RenderedQuery(
            metric="cpu_usage",
            version="1.0.0",
            source="synthetic",
            expression="sum(rate(container_cpu_usage_seconds_total[5m]))",
            expression_digest=DIGEST,
            entity_digest="b" * 64,
            step_seconds=60,
        ),
        unit="mCPU",
        required_label_keys=("cluster_name", "namespace", "pod", "container"),
        expected_label_sets=(expected_labels,),
        result=RangeQueryResult(series=series, observed_at=WINDOW_END),
    )


def evaluate(item: PrometheusQueryExecution) -> PrometheusSourceAcceptance:
    return evaluate_prometheus_source_acceptance(
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=CLUSTER,
        cluster_uid="cluster-uid-synthetic",
        source_profile_id="identity-enriched",
        source_profile_version="1.0.0",
        evaluated_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        step_seconds=60,
        configuration_digest=DIGEST,
        executions=[item],
    )


def test_source_acceptance_evaluator_admits_exact_identity_and_window() -> None:
    result = evaluate(execution())

    assert result.status == "accepted"
    assert result.records[0].matched_expected_entities == 1
    assert result.records[0].duplicate_series == 0
    assert "metrics.example" not in result.model_dump_json()


def test_source_acceptance_reports_single_endpoint_sample_as_partial() -> None:
    result = evaluate(execution(samples=[[WINDOW_END.timestamp(), "100"]]))

    assert result.status == "partial"
    assert result.records[0].matched_expected_entities == 1
    assert "sample_grid_incomplete" in result.reason_codes


@pytest.mark.parametrize(
    ("samples", "reason"),
    [
        ([[WINDOW_START.timestamp() + 1, "100"]], "sample_clock_off_grid"),
        ([[WINDOW_START.timestamp() - 60, "100"]], "sample_clock_outside_window"),
        ([[WINDOW_END.timestamp(), "NaN"]], "sample_value_invalid"),
        ([[WINDOW_END.timestamp(), "0"], [WINDOW_END.timestamp(), "0"]], "duplicate_sample_clock"),
    ],
)
def test_source_acceptance_blocks_invalid_sample_grids(
    samples: list[list[object]], reason: str
) -> None:
    result = evaluate(execution(samples=samples))

    assert result.status == "blocked"
    assert reason in result.reason_codes


def test_source_acceptance_evaluator_blocks_cross_cluster_series() -> None:
    result = evaluate(execution(cluster=CLUSTER + "-other"))

    assert result.status == "blocked"
    assert "unexpected_identity" in result.reason_codes


def test_source_acceptance_evaluator_blocks_duplicate_series() -> None:
    result = evaluate(execution(duplicate=True))

    assert result.status == "blocked"
    assert result.records[0].duplicate_series == 1
    assert "duplicate_series" in result.records[0].reason_codes


class AcceptanceReader:
    source_name = "synthetic"

    def __init__(self, result: RangeQueryResult) -> None:
        self.result = result
        self.calls: list[tuple[str, datetime, datetime, int]] = []

    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult:
        self.calls.append((query, start, end, step_seconds))
        return self.result


def request() -> PrometheusQueryRequest:
    item = execution()
    return PrometheusQueryRequest(
        query=item.query,
        unit=item.unit,
        required_label_keys=item.required_label_keys,
        expected_label_sets=item.expected_label_sets,
    )


def test_source_acceptance_sdk_executes_exact_bounded_query() -> None:
    item = execution()
    reader = AcceptanceReader(item.result)
    result = collect_prometheus_source_acceptance(
        reader=reader,
        requests=[request()],
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=CLUSTER,
        cluster_uid="cluster-uid-synthetic",
        source_profile_id="identity-enriched",
        source_profile_version="1.0.0",
        evaluated_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        step_seconds=60,
        configuration_digest=DIGEST,
    )

    assert result.status == "accepted"
    assert reader.calls == [(item.query.expression, WINDOW_START, WINDOW_END, 60)]


def test_source_acceptance_sdk_refuses_foreign_reader_before_io() -> None:
    reader = AcceptanceReader(execution().result)
    reader.source_name = "foreign"

    with pytest.raises(ValueError, match="bound reader"):
        collect_prometheus_source_acceptance(
            reader=reader,
            requests=[request()],
            tenant_id="00000000-0000-0000-0000-000000000000",
            cluster_resource_id=CLUSTER,
            cluster_uid="cluster-uid-synthetic",
            source_profile_id="identity-enriched",
            source_profile_version="1.0.0",
            evaluated_at=WINDOW_END,
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            step_seconds=60,
            configuration_digest=DIGEST,
        )

    assert reader.calls == []


class FailingAcceptanceReader(AcceptanceReader):
    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult:
        self.calls.append((query, start, end, step_seconds))
        raise MetricReadError("unauthorized")


def test_source_acceptance_sdk_retains_redacted_read_failure() -> None:
    reader = FailingAcceptanceReader(execution().result)
    result = collect_prometheus_source_acceptance(
        reader=reader,
        requests=[request()],
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=CLUSTER,
        cluster_uid="cluster-uid-synthetic",
        source_profile_id="identity-enriched",
        source_profile_version="1.0.0",
        evaluated_at=WINDOW_END,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        step_seconds=60,
        configuration_digest=DIGEST,
    )

    assert result.status == "blocked"
    assert result.reason_codes == ["source_unauthorized"]
    assert "metrics.example" not in result.model_dump_json()


def test_source_acceptance_plan_binds_source_window_and_configuration() -> None:
    plan = PrometheusSourceAcceptancePlan(
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=CLUSTER,
        cluster_uid="cluster-uid-synthetic",
        source="synthetic",
        source_profile_id="identity-enriched",
        source_profile_version="1.0.0",
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        step_seconds=60,
        configuration_digest=DIGEST,
        requests=[request()],
    )

    assert plan.requests[0].expected_label_sets[0]["cluster_name"] == CLUSTER


def test_source_acceptance_plan_rejects_foreign_query_source() -> None:
    payload = request().model_dump(mode="python")
    payload["query"]["source"] = "foreign"

    with pytest.raises(ValidationError, match="source and step"):
        PrometheusSourceAcceptancePlan(
            tenant_id="00000000-0000-0000-0000-000000000000",
            cluster_resource_id=CLUSTER,
            cluster_uid="cluster-uid-synthetic",
            source="synthetic",
            source_profile_id="identity-enriched",
            source_profile_version="1.0.0",
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            step_seconds=60,
            configuration_digest=DIGEST,
            requests=[PrometheusQueryRequest.model_validate(payload)],
        )


def cli_profile() -> OnboardingConfig:
    return OnboardingConfig.model_validate(
        {
            "scope": {
                "tenant_id": "00000000-0000-0000-0000-000000000000",
                "subscription_ids": ["00000000-0000-0000-0000-000000000000"],
            },
            "report_directory": "reports",
            "metric_sources": [
                {
                    "name": "synthetic",
                    "type": "prometheus",
                    "endpoint": "https://metrics.example.invalid",
                    "authentication": "anonymous",
                    "catalog_profile": "cadvisor-ksm",
                    "label_mapping": {
                        "cluster_resource_id": "cluster_name",
                        "namespace": "namespace",
                        "pod": "pod",
                        "container": "container",
                    },
                }
            ],
            "clusters": [{"resource_id": CLUSTER, "metric_source": "synthetic"}],
        }
    )


def cli_plan(profile: OnboardingConfig) -> PrometheusSourceAcceptancePlan:
    labels = {
        "cluster_name": CLUSTER,
        "namespace": "orders",
        "pod": "orders-abc",
        "container": "api",
    }
    asset = load_catalog().queries["cpu_usage"]
    return PrometheusSourceAcceptancePlan(
        tenant_id=str(profile.scope.tenant_id),
        cluster_resource_id=CLUSTER,
        cluster_uid="cluster-uid-synthetic",
        source="synthetic",
        source_profile_id="cadvisor-ksm",
        source_profile_version="1.0.0",
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        step_seconds=60,
        configuration_digest=digest_json(profile.model_dump(mode="json")),
        requests=[
            PrometheusQueryRequest(
                query=RenderedQuery(
                    metric="cpu_usage",
                    version=asset.version,
                    source="synthetic",
                    expression=render_query(asset.expression, labels, 60),
                    expression_digest=digest_json(render_query(asset.expression, labels, 60)),
                    entity_digest="b" * 64,
                    step_seconds=60,
                ),
                unit="mCPU",
                required_label_keys=tuple(labels),
                expected_label_sets=(labels,),
            )
        ],
    )


class AcceptanceReaderContext(AcceptanceReader):
    def __init__(self, *_: object, **__: object) -> None:
        super().__init__(execution().result)

    def __enter__(self) -> AcceptanceReaderContext:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_accept_prometheus_source_cli_requires_live_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = cli_profile()
    config_path = tmp_path / "config.json"
    plan_path = tmp_path / "plan.json"
    config_path.write_text(profile.model_dump_json(), encoding="utf-8")
    plan_path.write_text(
        cli_plan(load_onboarding_config(config_path)).model_dump_json(), encoding="utf-8"
    )
    constructed = False

    def reader(*_: object, **__: object) -> AcceptanceReaderContext:
        nonlocal constructed
        constructed = True
        return AcceptanceReaderContext()

    monkeypatch.setattr("aks_fleet_efficiency.cli.PrometheusHttpReader", reader)
    response = CliRunner().invoke(
        app,
        [
            "accept-prometheus-source",
            "--config",
            str(config_path),
            "--plan",
            str(plan_path),
            "--as-of",
            "2026-10-29T12:00:00Z",
            "--output",
            str(tmp_path / "acceptance.json"),
        ],
    )

    assert response.exit_code == 2
    assert not constructed


def test_accept_prometheus_source_cli_writes_redacted_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = cli_profile()
    config_path = tmp_path / "config.json"
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "acceptance.json"
    config_path.write_text(profile.model_dump_json(), encoding="utf-8")
    plan_path.write_text(
        cli_plan(load_onboarding_config(config_path)).model_dump_json(), encoding="utf-8"
    )
    monkeypatch.setattr("aks_fleet_efficiency.cli.PrometheusHttpReader", AcceptanceReaderContext)

    response = CliRunner().invoke(
        app,
        [
            "accept-prometheus-source",
            "--config",
            str(config_path),
            "--plan",
            str(plan_path),
            "--as-of",
            "2026-10-29T12:00:00Z",
            "--output",
            str(output),
            "--allow-live",
        ],
    )

    assert response.exit_code == 0, response.output
    accepted = PrometheusSourceAcceptance.model_validate_json(output.read_text(encoding="utf-8"))
    assert accepted.status == "accepted"
    assert "metrics.example.invalid" not in output.read_text(encoding="utf-8")
