from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_prometheus import AS_OF, CLUSTER, END, START, FakeMetricReader, entity, matrix, profile
from typer.testing import CliRunner

from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.catalog import load_catalog, render_pack_queries
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.prometheus import PrometheusMetricCollector, RangeQueryResult
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import MetricEntity, PrometheusMetricsSnapshot


def ordinary_profile(*, managed: bool = False) -> OnboardingConfig:
    payload = profile().model_dump()
    source = payload["metric_sources"][0]
    source.update(
        catalog_profile="cadvisor-ksm",
        component_versions={"prometheus": "3.16.0-rc.2", "kube-state-metrics": "2.17.0"},
        label_mapping={
            "cluster_resource_id": "azure_resource_id",
            "namespace": "namespace",
            "pod": "pod",
            "container": "container",
        },
    )
    if managed:
        source.update(
            type="azure-managed-prometheus",
            endpoint="https://synthetic.prometheus.monitor.azure.com",
            authentication="default-azure-credential",
        )
    return OnboardingConfig.model_validate(payload)


def unresolved() -> MetricEntity:
    return MetricEntity(
        kind="unresolved_container",
        cluster_resource_id=CLUSTER,
        namespace="synthetic",
        pod="synthetic-pod",
        container="api",
    )


def ordinary_matrix(*, values: list[float] | None = None) -> RangeQueryResult:
    response = matrix(values or [100, 200, 300, 400])
    response.series[0]["metric"] = {
        "azure_resource_id": CLUSTER,
        "namespace": "synthetic",
        "pod": "synthetic-pod",
        "container": "api",
    }
    return response


@pytest.mark.parametrize("managed", [False, True])
def test_declared_ordinary_source_collects_measurements_without_inventing_uids(
    managed: bool,
) -> None:
    settings = ordinary_profile(managed=managed)
    reader = FakeMetricReader([ordinary_matrix(), ordinary_matrix(values=[1000] * 4)])
    result = PrometheusMetricCollector(
        settings,
        source_name="synthetic",
        reader=reader,
        entities=[unresolved()],
        clock=lambda: AS_OF,
    ).collect_observations(start=START, end=END, metrics=["cpu_usage", "cpu_request"])
    assert result.collection.status == "complete"
    assert result.observations[0].p95 == pytest.approx(385)
    assert result.source_profile.id == "cadvisor-ksm"
    assert all(
        item.entity.workload_uid is None and item.entity.pod_uid is None
        for item in result.observations
    )
    assert all("workload_uid" not in call[0] and "pod_uid" not in call[0] for call in reader.calls)
    exported = render_pack_queries(
        load_catalog(), "AKS-RQ-002", settings, "synthetic", [unresolved()], "baseline"
    )
    assert {item.expression for item in exported} == {call[0] for call in reader.calls}
    with pytest.raises(ValueError, match="guarded"):
        render_pack_queries(
            load_catalog(), "AKS-RQ-002", settings, "synthetic", [unresolved()], "guarded"
        )


def historical_fragment() -> PrometheusMetricsSnapshot:
    payload = json.loads(
        Path("examples/fixtures/history-assessment.json").read_text(encoding="utf-8")
    )
    return PrometheusMetricsSnapshot.model_validate(payload["metrics"][0])


@pytest.mark.parametrize(
    ("defect", "status", "reason"),
    [
        ("complete", "available", "series_observed"),
        ("missing", "unavailable", "missing_series"),
        ("not-collected", "unknown", "not_collected"),
        ("stale", "unknown", "stale_evidence"),
        ("duplicate", "unsupported", "ambiguous_series"),
        ("partial", "unknown", "partial_source"),
        ("version", "unsupported", "uncharacterized_version"),
    ],
)
def test_capability_matrix_distinguishes_observed_unknown_and_unsupported(
    defect: str, status: str, reason: str
) -> None:
    settings = profile()
    settings.metric_sources[0].component_versions = {
        "prometheus": "3.16.0-rc.2",
        "kube-state-metrics": "2.17.0",
    }
    result = historical_fragment()
    if defect == "missing":
        item = next(item for item in result.observations if item.metric == "cpu_usage")
        item.p95 = None
        item.issues = ["missing-series"]
    elif defect == "not-collected":
        result.observations = [item for item in result.observations if item.metric != "cpu_usage"]
    elif defect == "stale":
        result.generated_at = AS_OF - timedelta(days=2)
    elif defect == "duplicate":
        result.observations.append(result.observations[0].model_copy(deep=True))
    elif defect == "partial":
        result.collection.status = "partial"
        result.collection.missing_fields.append("synthetic-gap")
    elif defect == "version":
        settings.metric_sources[0].component_versions["kube-state-metrics"] = "99.0.0"
    capability = evaluate_source_capabilities(
        settings, [result], pack_id="AKS-RQ-002", as_of=AS_OF
    )[0]
    assert capability.mode == "baseline"
    assert capability.status == status
    assert any(reason in item.reason_codes for item in capability.checks)


def test_ordinary_profile_guarded_capability_is_not_authorized_by_current_names() -> None:
    settings = ordinary_profile()
    result = historical_fragment()
    result.observations = [
        item.model_copy(update={"entity": unresolved()})
        for item in result.observations
        if item.metric in {"cpu_usage", "cpu_request"}
    ]
    capabilities = evaluate_source_capabilities(
        settings, [result], pack_id="AKS-RQ-002", as_of=AS_OF
    )
    guarded = next(item for item in capabilities if item.mode == "guarded")
    assert guarded.status == "unsupported"
    assert any("historical_identity_unavailable" in item.reason_codes for item in guarded.checks)


def test_unresolved_entities_cannot_claim_historical_or_membership_identity() -> None:
    for field in ["workload_uid", "pod_uid", "membership_digest", "hpa_uid", "node_uid"]:
        payload = unresolved().model_dump()
        payload[field] = "a" * 64
        with pytest.raises(ValidationError):
            MetricEntity.model_validate(payload)
    settings = profile()
    with pytest.raises(ValueError):
        PrometheusMetricCollector(
            settings,
            source_name="synthetic",
            reader=FakeMetricReader([]),
            entities=[unresolved()],
            clock=lambda: AS_OF,
        )


def test_duplicate_series_are_not_deduplicated_into_success() -> None:
    response = ordinary_matrix()
    response.series.append(response.series[0].copy())
    result = PrometheusMetricCollector(
        ordinary_profile(),
        source_name="synthetic",
        reader=FakeMetricReader([response]),
        entities=[unresolved()],
        clock=lambda: AS_OF,
    ).collect_observations(start=START, end=END, metrics=["cpu_usage"])
    assert result.collection.status == "failed"
    assert "identity-mismatch" in result.observations[0].issues
    assert result.observations[0].p95 is None


def test_capability_cli_is_offline_and_rejects_unapproved_scopes(tmp_path: Path) -> None:
    configuration = tmp_path / "profile.json"
    configuration.write_text(profile().model_dump_json(), encoding="utf-8")
    evidence = tmp_path / "metrics.json"
    evidence.write_text(historical_fragment().model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "capabilities",
            "AKS-RQ-002",
            "--config",
            str(configuration),
            "--metrics",
            str(evidence),
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)["capabilities"]) == 2
    foreign = historical_fragment()
    foreign.observations[0].entity = entity().model_copy(
        update={"cluster_resource_id": CLUSTER + "x"}
    )
    evidence.write_text(foreign.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "capabilities",
            "AKS-RQ-002",
            "--config",
            str(configuration),
            "--metrics",
            str(evidence),
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert result.exit_code == 2


def test_query_plan_reports_deduplication_and_exact_evaluation_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency.collectors.prometheus import QUERY_CATALOG

    monkeypatch.setitem(QUERY_CATALOG, "cpu_request", QUERY_CATALOG["cpu_usage"])
    collector = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=FakeMetricReader([matrix([100, 200, 300, 400])]),
        entities=[entity()],
        clock=lambda: AS_OF,
    )
    result = collector.collect_observations(
        start=START, end=END, metrics=["cpu_usage", "cpu_request"]
    )
    assert len(collector.reader.calls) == 1
    assert result.query_plan.logical_queries == 2
    assert result.query_plan.unique_queries == 1
    assert result.query_plan.expected_evaluations == 4
    assert result.query_plan.requests == 1
    assert {item.metric for item in result.observations} == {"cpu_usage", "cpu_request"}
    assert result.observations[0].p95 == result.observations[1].p95
    assert result.observations[0].quality == result.observations[1].quality


def test_query_plan_distinguishes_delta_interval_offsets(monkeypatch: pytest.MonkeyPatch) -> None:
    from aks_fleet_efficiency.collectors.prometheus import QUERY_CATALOG

    usage = QUERY_CATALOG["cpu_usage"]
    monkeypatch.setitem(
        QUERY_CATALOG,
        "cpu_request",
        usage.model_copy(update={"delta": True}),
    )
    reader = FakeMetricReader([])
    collector = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[entity()],
        clock=lambda: AS_OF,
        max_queries=1,
    )
    with pytest.raises(ValueError, match="query bound"):
        collector.plan_queries(
            start=START, end=END, step_seconds=300, metrics=["cpu_usage", "cpu_request"]
        )
    assert not reader.calls


@pytest.mark.parametrize("budget", ["queries", "evaluations", "series"])
def test_query_cost_bounds_fail_before_io_or_return_explicit_failure(budget: str) -> None:
    reader = FakeMetricReader([ordinary_matrix()])
    options = (
        {"maximum_evaluations": 1}
        if budget == "evaluations"
        else (
            {"maximum_series": 1} if budget == "series" else {"max_queries": 1, "chunk_samples": 1}
        )
    )
    collector = PrometheusMetricCollector(
        ordinary_profile(),
        source_name="synthetic",
        reader=reader,
        entities=[unresolved()],
        clock=lambda: AS_OF,
        **options,
    )
    if budget == "series":
        response = ordinary_matrix()
        response.series.append({"metric": {"foreign": "series"}, "values": []})
        reader.results = [response]
        result = collector.collect_observations(start=START, end=END, metrics=["cpu_usage"])
        assert result.collection.status == "failed"
        assert "response-budget-exceeded" in result.observations[0].issues
    else:
        with pytest.raises(ValueError, match="bound"):
            collector.collect_observations(start=START, end=END, metrics=["cpu_usage"])
        assert not reader.calls


def test_cached_failure_does_not_repeat_requests_or_inflate_retry_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency.collectors.prometheus import QUERY_CATALOG, MetricReadError

    monkeypatch.setitem(QUERY_CATALOG, "cpu_request", QUERY_CATALOG["cpu_usage"])
    reader = FakeMetricReader([MetricReadError("unavailable"), MetricReadError("unavailable")])
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[entity()],
        clock=lambda: AS_OF,
        sleep=lambda _: None,
        max_retries=1,
    ).collect_observations(start=START, end=END, metrics=["cpu_usage", "cpu_request"])
    assert len(reader.calls) == 2
    assert result.collection.retry_count == 1
    assert result.collection.status == "failed"
    assert all("unavailable" in item.issues and item.p95 is None for item in result.observations)


def test_reader_reuse_cannot_mutate_cached_measurements(monkeypatch: pytest.MonkeyPatch) -> None:
    from aks_fleet_efficiency.collectors.prometheus import QUERY_CATALOG

    monkeypatch.setitem(QUERY_CATALOG, "cpu_throttling", QUERY_CATALOG["cpu_usage"])

    class ReusingReader(FakeMetricReader):
        def query_range(self, **kwargs: object) -> RangeQueryResult:
            self.calls.append(kwargs)
            if len(self.calls) == 2:
                for value in self.results[0].series[0]["values"]:
                    value[1] = "900"
            return self.results[0]

    reader = ReusingReader([matrix([100] * 4)])
    result = PrometheusMetricCollector(
        profile(),
        source_name="synthetic",
        reader=reader,
        entities=[entity()],
        clock=lambda: AS_OF,
    ).collect_observations(
        start=START, end=END, metrics=["cpu_usage", "cpu_request", "cpu_throttling"]
    )
    assert len(reader.calls) == 2
    assert [item.p95 for item in result.observations] == [100, 900, 100]


def test_explicit_unsupported_profile_blocks_guarded_target() -> None:
    from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
    from aks_fleet_efficiency.config import AdvisorConfig, load_onboarding_config

    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis = AdvisorConfig(mode="guarded", packs=["AKS-RQ-002"])
    settings.metric_sources[0].component_versions = {"prometheus": "99.0.0"}
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/history-assessment.json").read_bytes()
    )
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    assert not result.report.recommendations
    assert any(
        "unsupported_source_profile" in item.reason_codes
        for item in result.report.blocked_recommendations
    )


def test_name_only_measurements_never_join_current_names_into_history() -> None:
    from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
    from aks_fleet_efficiency.config import AdvisorConfig

    settings = ordinary_profile()
    settings.analysis = AdvisorConfig(packs=["AKS-RQ-002"])
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/history-assessment.json").read_bytes()
    )
    fragments.workload_assessments = []
    fragments.metrics[0].source_profile = load_catalog().source("cadvisor-ksm")
    fragments.metrics[0].observations = [
        item.model_copy(update={"entity": unresolved()})
        for item in fragments.metrics[0].observations
        if item.metric in {"cpu_usage", "cpu_request"}
    ]
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    assert len(result.baseline_measurements) == 2
    assert result.baseline_measurements[0].p95 is not None
    assert not result.workload_history
    assert all(
        container.resources.usage_cpu_p95_mcores is None
        for cluster in result.snapshot.clusters
        for workload in cluster.workloads
        for container in workload.containers
    )
    assert (
        next(item for item in result.report.source_capabilities if item.mode == "baseline").status
        == "available"
    )
    assert (
        next(item for item in result.report.source_capabilities if item.mode == "guarded").status
        == "unsupported"
    )
    assert not any(item.proposed_requests for item in result.report.recommendations)


def test_missing_metrics_leave_independent_current_autoscaler_review_visible() -> None:
    from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
    from aks_fleet_efficiency.config import load_onboarding_config

    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis.mode = "baseline"
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/autoscalers-assessment.json").read_bytes()
    )
    fragments.metrics = []
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    assert any(item.rule_id == "AKS-AS-002" for item in result.report.recommendations)
