from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from pydantic import RootModel
from test_collection import AS_OF, plan
from test_history import TENANT, write_run
from test_prometheus import FakeMetricReader, entity, profile
from typer.testing import CliRunner

from aks_fleet_efficiency.catalog import (
    digest_json,
    load_catalog,
    render_pack_queries,
    render_query_bundle,
)
from aks_fleet_efficiency.catalog.models import (
    QueryBundleExportManifest,
    RenderedQuery,
    SourceDefinition,
)
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.metric_queries import metric_labels
from aks_fleet_efficiency.collectors.prometheus import (
    PrometheusMetricCollector,
    RangeQueryResult,
)
from aks_fleet_efficiency.config import OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.models import MetricEntity
from aks_fleet_efficiency.operator import (
    RetainedAssessmentQuality,
    build_operator_catalog,
    configure_profile,
    grafana_dashboard,
    preview_execution,
    render_operator_catalog,
    retained_query_quality,
)
from aks_fleet_efficiency.source_acceptance import (
    PrometheusQueryAcceptance,
    PrometheusSourceAcceptance,
)


def test_generated_cards_cover_every_pack_and_explain_parameters_and_safety() -> None:
    catalog = load_catalog()
    guide = build_operator_catalog(catalog)
    assert {card.manifest.id for card in guide.cards} == set(catalog.manifests)
    cpu = next(card for card in guide.cards if card.manifest.id == "AKS-RQ-002")
    assert cpu.provenance == catalog.provenance("AKS-RQ-002")
    assert cpu.parameter_guidance["review_ratio"].unit == "ratio"
    assert "owner" in guide.guarded_notice.lower()
    assert cpu.synthetic_example.packs == ["AKS-RQ-002"]
    assert cpu.synthetic_example.mode == "baseline"
    rendered = render_operator_catalog(guide)
    assert "Glossary" in rendered and "synthetic" in rendered.lower()
    assert all(pack.id in rendered for pack in catalog.manifests.values())
    assert "template" in rendered.lower()


def test_catalog_markdown_escapes_untrusted_text_and_has_no_untrusted_links() -> None:
    guide = build_operator_catalog(load_catalog())
    guide.cards[0].manifest.title = "<script>x</script> [click](javascript:alert(1))"
    rendered = render_operator_catalog(guide)
    assert "<script>" not in rendered
    assert "[click](javascript:" not in rendered


@pytest.mark.parametrize("ratio", [0.01, 0.4, 0.99])
def test_local_configuration_is_locked_and_does_not_create_owner_approval(ratio: float) -> None:
    original = profile()
    configured = configure_profile(original, ["AKS-RQ-002"], "guarded", {"AKS-RQ-002": ratio})
    assert original.analysis.packs is None
    assert configured.analysis.mode == "guarded"
    assert configured.analysis.pack_parameters["AKS-RQ-002"].review_ratio == ratio
    assert configured.analysis.pack_locks == {
        "AKS-RQ-002": load_catalog().provenance("AKS-RQ-002").digest
    }
    assert configured.ownership == original.ownership


@pytest.mark.parametrize("ratio", [0, 1, -1, float("nan"), float("inf")])
def test_configuration_rejects_out_of_bound_review_parameter(ratio: float) -> None:
    with pytest.raises(ValueError):
        configure_profile(profile(), ["AKS-RQ-002"], "baseline", {"AKS-RQ-002": ratio})


def test_configuration_rejects_owner_bound_override_and_unselected_parameters() -> None:
    for selected, parameters in [
        (["AKS-MEM-003"], {"AKS-MEM-003": 0.5}),
        (["AKS-RQ-001"], {"AKS-RQ-002": 0.5}),
        (["not-a-pack"], {}),
    ]:
        with pytest.raises(ValueError):
            configure_profile(profile(), selected, "baseline", parameters)


def test_offline_preview_uses_execution_queries_and_budgets_without_readers() -> None:
    settings = configure_profile(profile(), ["AKS-RQ-002"], "baseline", {})
    request = plan()
    request.clusters[0].entities = [entity()]
    preview = preview_execution(settings, request, as_of=AS_OF)
    expected = render_pack_queries(
        load_catalog(), "AKS-RQ-002", settings, "synthetic", [entity()], "baseline"
    )
    assert {query.expression for query in preview.queries} == {
        query.expression for query in expected
    }
    assert preview.query_plan.unique_queries == 2
    assert preview.query_plan.requests == 18
    assert preview.query_plan.expected_evaluations == 17280
    assert preview.budgets["maximum_queries"] == request.maximum_queries
    assert preview.artifact_destination == str(settings.report_directory)
    assert preview.unresolved_prerequisites
    assert any("metadata_export" in item for item in preview.unresolved_prerequisites)
    assert any("Secrets" in item for item in preview.excluded_fields)
    assert any(op.endpoint.endswith("/api/v1/query_range") for op in preview.operations)
    assert preview.mode == "offline"


def test_offline_preview_uses_query_specific_label_mappings() -> None:
    payload = profile().model_dump(mode="json")
    payload["metric_sources"][0]["query_label_mappings"] = {
        "cpu_usage": {"cluster_resource_id": "cluster_name"}
    }
    settings = configure_profile(
        OnboardingConfig.model_validate(payload), ["AKS-RQ-002"], "baseline", {}
    )
    request = plan()
    request.clusters[0].entities = [entity()]
    expressions = {
        query.metric: query.expression
        for query in preview_execution(settings, request, as_of=AS_OF).queries
    }
    assert 'cluster_name="' in expressions["cpu_usage"]
    assert 'azure_resource_id="' in expressions["cpu_request"]


def test_inventory_preview_needs_no_metric_source_and_scope_and_budgets_fail_closed() -> None:
    settings = configure_profile(profile(), ["AKS-RQ-001"], "baseline", {})
    request = plan()
    preview = preview_execution(settings, request, as_of=AS_OF)
    assert not preview.queries
    assert preview.query_plan.requests == 0
    assert all("query_range" not in op.endpoint for op in preview.operations)
    request.clusters[0].resource_id += "-foreign"
    with pytest.raises(ValueError, match="scope"):
        preview_execution(settings, request, as_of=AS_OF)
    request = plan()
    request.clusters[0].entities = [entity()]
    request.maximum_queries = 1
    with pytest.raises(ValueError, match=r"bound|budget"):
        preview_execution(
            configure_profile(profile(), ["AKS-RQ-002"], "baseline", {}), request, as_of=AS_OF
        )


def test_grafana_assets_use_only_source_bound_queries_and_no_evaluation() -> None:
    catalog = load_catalog()
    queries = render_pack_queries(
        catalog, "AKS-RQ-002", profile(), "synthetic", [entity()], "guarded"
    )
    source_profile = catalog.source(profile().metric_sources[0].catalog_profile)
    dashboard = grafana_dashboard(queries, source_profile)
    measurements = [panel for panel in dashboard["panels"] if panel["type"] == "timeseries"]
    expressions = {panel["targets"][0]["expr"] for panel in measurements}
    assert expressions == {query.expression for query in queries}
    assert all(panel["datasource"]["uid"] == "${DS_PROMETHEUS}" for panel in measurements)
    assert {panel["title"] for panel in dashboard["panels"] if panel["type"] == "row"} == {
        "Workload CPU",
        "Reliability",
    }
    quality = next(panel for panel in dashboard["panels"] if panel["type"] == "text")
    assert quality["title"] == "Evidence quality and missing series"
    assert source_profile.id in quality["options"]["content"]
    assert source_profile.version in quality["options"]["content"]
    assert all(
        term in quality["options"]["content"].lower()
        for term in ["coverage", "freshness", "missing series", "unknown"]
    )
    assert all("step" in panel["description"].lower() for panel in measurements)
    assert "approval" in dashboard["description"].lower()


def test_grafana_source_acceptance_panel_is_fixed_window_not_live_attestation() -> None:
    catalog = load_catalog()
    queries = render_pack_queries(
        catalog, "AKS-RQ-002", profile(), "synthetic", [entity()], "guarded"
    )
    source_profile = catalog.source(profile().metric_sources[0].catalog_profile)
    acceptance = PrometheusSourceAcceptance(
        tenant_id=TENANT,
        cluster_resource_id=entity().cluster_resource_id,
        cluster_uid="synthetic-cluster-uid",
        source="synthetic",
        source_profile_id=source_profile.id,
        source_profile_version=source_profile.version,
        evaluated_at=AS_OF,
        window_start=AS_OF - timedelta(hours=1),
        window_end=AS_OF,
        step_seconds=300,
        status="accepted",
        reason_codes=[],
        input_digest="a" * 64,
        configuration_digest="b" * 64,
        records=[
            PrometheusQueryAcceptance(
                query_id=query.metric,
                query_version=query.version,
                expression_digest=query.expression_digest,
                unit=catalog.queries[query.metric].unit,
                status="accepted",
                reason_codes=[],
                required_label_keys=["azure_resource_id"],
                observed_series=1,
                matched_expected_entities=1,
                expected_entities=1,
                duplicate_series=0,
                latest_sample_at=AS_OF,
            )
            for query in queries
        ],
    )

    dashboard = grafana_dashboard(queries, source_profile, source_acceptance=acceptance)

    panel = next(
        item for item in dashboard["panels"] if item["title"] == "Supplied source acceptance"
    )
    content = panel["options"]["content"].lower()
    assert "fixed window" in content
    assert "not independently replayed" in content
    assert "live time picker: unknown" in content
    assert acceptance.input_digest in panel["options"]["content"]


def _retained_run(
    tmp_path: Path,
    *,
    change: Callable[[dict[str, Any]], None] | None = None,
    as_of: datetime = AS_OF,
) -> tuple[Path, list[RenderedQuery], SourceDefinition]:
    catalog = load_catalog()
    settings = load_onboarding_config(Path("examples/cpu-pack-config.yaml"))
    targets = (
        RootModel[list[MetricEntity]]
        .model_validate_json(Path("examples/pool-pack-entities.json").read_text(encoding="utf-8"))
        .root
    )
    queries = render_pack_queries(catalog, "AKS-NP-001", settings, "synthetic", targets, "baseline")
    source_profile = catalog.source(settings.metric_sources[0].catalog_profile)

    def executed(payload: dict[str, Any]) -> None:
        for fragment in payload["metrics"]:
            fragment["source_profile"] = source_profile.model_dump(mode="json")
            for observation in fragment["observations"]:
                entity_digest = digest_json(
                    MetricEntity.model_validate(observation["entity"]).model_dump(mode="json")
                )
                for query in queries:
                    if (observation["metric"], entity_digest) == (
                        query.metric,
                        query.entity_digest,
                    ):
                        observation["quality"]["query_expression"] = query.expression
                        observation["quality"]["query_asset_version"] = query.version
        if change is not None:
            change(payload)

    directory = write_run(tmp_path, "executed", change=executed, as_of=as_of)
    return directory, queries, source_profile


def test_retained_quality_matches_original_execution_without_qualifying_live_charts(
    tmp_path: Path,
) -> None:
    directory, queries, source_profile = _retained_run(tmp_path)
    quality = retained_query_quality(directory, queries, source_profile, tenant_id=TENANT)
    assert quality.evaluated_at == AS_OF
    assert quality.cluster_uid == "synthetic-cluster-uid"
    assert quality.live_quality == "unknown"
    assert len(quality.records) == len(queries)
    assert all(record.status == "matched" for record in quality.records)
    assert quality.receipts
    assert all(record.receipt_digest is not None for record in quality.records)
    dashboard = grafana_dashboard(queries, source_profile, retained_quality=quality)
    panels = [panel for panel in dashboard["panels"] if panel["type"] == "text"]
    assert "unknown" in panels[0]["options"]["content"].lower()
    retained = next(panel for panel in panels if panel["title"] == "Retained assessment quality")
    assert quality.run_id in retained["options"]["content"]
    assert "not live" in retained["options"]["content"].lower()


def test_retained_quality_accepts_actual_collector_provenance(tmp_path: Path) -> None:
    settings = load_onboarding_config(Path("examples/cpu-pack-config.yaml"))
    target = (
        RootModel[list[MetricEntity]]
        .model_validate_json(Path("examples/pool-pack-entities.json").read_text(encoding="utf-8"))
        .root[0]
    )
    start, end = AS_OF - timedelta(minutes=25), AS_OF - timedelta(minutes=5)
    metrics = ["node_cpu_usage", "node_allocatable_cpu", "node_allocatable_memory"]
    reader = FakeMetricReader(
        [
            RangeQueryResult(
                series=[
                    {
                        "metric": metric_labels(target, settings.metric_sources[0], metric),
                        "values": [
                            [(start + timedelta(seconds=index * 300)).timestamp(), "100"]
                            for index in range(4)
                        ],
                    }
                ],
                observed_at=AS_OF,
            )
            for metric in metrics
        ]
    )
    collected = PrometheusMetricCollector(
        settings,
        source_name="synthetic",
        reader=reader,
        entities=[target],
        node_history_complete=True,
        clock=lambda: AS_OF,
        sleep=lambda _: None,
    ).collect_observations(start=start, end=end, step_seconds=300, metrics=metrics)

    def change(payload: dict[str, Any]) -> None:
        payload["window_start"], payload["window_end"] = start.isoformat(), end.isoformat()
        payload["metrics"] = [collected.model_dump(mode="json")]

    directory, queries, source_profile = _retained_run(tmp_path, change=change)
    quality = retained_query_quality(directory, queries, source_profile, tenant_id=TENANT)
    assert len(reader.calls) == 3
    assert all(record.status == "matched" for record in quality.records), [
        (record.query.metric, record.reason_codes) for record in quality.records
    ]
    assert quality.window_start == start and quality.window_end == end


@pytest.mark.parametrize(
    ("defect", "status", "reason"),
    [
        ("profile-missing", "unknown", "source_profile_unknown"),
        ("profile-version", "blocked", "source_profile_mismatch"),
        ("expression-missing", "unknown", "query_expression_unknown"),
        ("expression", "blocked", "query_expression_mismatch"),
        ("version", "blocked", "query_version_mismatch"),
        ("asset-version-missing", "unknown", "query_asset_version_unknown"),
        ("adapter-version", "blocked", "query_adapter_version_mismatch"),
        ("unit", "blocked", "unit_mismatch"),
        ("partial", "blocked", "incomplete_source"),
        ("source-clock", "unknown", "source_clock_unknown"),
        ("stale-source", "blocked", "stale_source"),
        ("missing-series", "unknown", "missing_entity_series"),
        ("foreign-entity", "unknown", "missing_entity_series"),
        ("latest-missing", "unknown", "latest_sample_unknown"),
        ("stale-tail", "blocked", "stale_sample_tail"),
        ("coverage", "blocked", "low_coverage"),
        ("false-coverage", "blocked", "inconsistent_coverage"),
        ("future-observation", "blocked", "future_metric_observation"),
        ("issues", "blocked", "observation_issues"),
        ("window", "invalid", "mixed metric windows"),
        ("stale-metric", "blocked", "stale_metric_observation"),
    ],
)
def test_retained_quality_keeps_provenance_and_quality_failures_explicit(
    tmp_path: Path, defect: str, status: str, reason: str
) -> None:
    def change(payload: dict[str, Any]) -> None:
        fragment = payload["metrics"][0]
        observation = next(
            item for item in fragment["observations"] if item["metric"] == "node_cpu_usage"
        )
        quality = observation["quality"]
        if defect == "profile-missing":
            fragment.pop("source_profile")
        elif defect == "profile-version":
            fragment["source_profile"]["version"] = "9.0.0"
        elif defect == "expression-missing":
            quality.pop("query_expression")
        elif defect == "expression":
            quality["query_expression"] = "vector(0)"
        elif defect == "version":
            quality["query_asset_version"] = "9.0.0"
        elif defect == "asset-version-missing":
            quality.pop("query_asset_version")
        elif defect == "adapter-version":
            quality["query_version"] = "9.0"
        elif defect == "unit":
            quality["unit"] = "MiB"
        elif defect == "partial":
            fragment["collection"].update(status="partial", pagination_complete=False)
        elif defect == "source-clock":
            fragment["collection"].pop("source_observed_at")
        elif defect == "stale-source":
            fragment["collection"]["source_observed_at"] = "2026-10-28T10:00:00Z"
        elif defect == "missing-series":
            fragment["observations"].remove(observation)
        elif defect == "foreign-entity":
            observation["entity"]["node_uid"] = "different-node-uid"
        elif defect == "latest-missing":
            observation.pop("latest_sample_at")
        elif defect == "stale-tail":
            observation["latest_sample_at"] = "2026-10-28T23:50:00Z"
        elif defect == "coverage":
            quality["window"].update(sample_count=4320, coverage_ratio=0.5)
        elif defect == "false-coverage":
            quality["window"].update(sample_count=1, coverage_ratio=1)
        elif defect == "future-observation":
            quality["observed_at"] = "2026-10-29T13:00:00Z"
        elif defect == "issues":
            observation["issues"] = ["SENSITIVE-SOURCE-TEXT"]
        elif defect == "stale-metric":
            quality["observed_at"] = payload["window_end"]
        elif defect == "window":
            fragment["query_start"] = "2026-09-30T00:00:00Z"
            for item in fragment["observations"]:
                item["quality"]["window"]["start"] = fragment["query_start"]

    if status == "invalid":
        with pytest.raises(ValueError, match=reason):
            _retained_run(tmp_path, change=change)
        return
    directory, queries, source_profile = _retained_run(
        tmp_path,
        change=change,
        as_of=AS_OF + timedelta(days=1) if defect == "stale-metric" else AS_OF,
    )
    result = retained_query_quality(directory, queries, source_profile, tenant_id=TENANT)
    record = next(item for item in result.records if item.query.metric == "node_cpu_usage")
    assert record.status == status
    assert reason in record.reason_codes
    assert result.live_quality == "unknown"
    assert "SENSITIVE-SOURCE-TEXT" not in result.model_dump_json()
    if defect not in {
        "profile-missing",
        "profile-version",
        "partial",
        "source-clock",
        "stale-source",
        "window",
        "stale-metric",
    }:
        assert all(
            item.status == "matched"
            for item in result.records
            if item.query.metric != "node_cpu_usage"
        )


def test_retained_quality_binds_step_and_preserves_freshness_boundary(tmp_path: Path) -> None:
    def boundary(payload: dict[str, Any]) -> None:
        payload["metrics"][0]["collection"]["source_observed_at"] = "2026-10-28T12:00:00Z"

    directory, queries, source_profile = _retained_run(tmp_path, change=boundary)
    quality = retained_query_quality(directory, queries, source_profile, tenant_id=TENANT)
    assert all(record.status == "matched" for record in quality.records)
    changed = [query.model_copy(update={"step_seconds": 60}) for query in queries]
    mismatch = retained_query_quality(directory, changed, source_profile, tenant_id=TENANT)
    assert all("step_mismatch" in record.reason_codes for record in mismatch.records)
    with pytest.raises(ValueError, match="exact exported"):
        grafana_dashboard(changed, source_profile, retained_quality=quality)


def test_retained_quality_rejects_rehashed_report_and_foreign_tenant(tmp_path: Path) -> None:
    directory, queries, source_profile = _retained_run(tmp_path)
    with pytest.raises(ValueError):
        retained_query_quality(
            directory, queries, source_profile, tenant_id="11111111-1111-1111-1111-111111111111"
        )
    path = directory / "assessment.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report"]["summary"]["pack_subject_counts"]["AKS-NP-001"] += 1
    encoded = json.dumps(payload).encode()
    path.write_bytes(encoded)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["assessment.json"] = sha256(encoded).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="replay"):
        retained_query_quality(directory, queries, source_profile, tenant_id=TENANT)


def test_retained_quality_rejects_replayed_foreign_fingerprint(tmp_path: Path) -> None:
    from aks_fleet_efficiency.artifacts import read_model, write_assessment_artifacts
    from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment
    from aks_fleet_efficiency.config import AdvisorConfig
    from aks_fleet_efficiency.rules.engine import analyze

    directory, queries, source_profile = _retained_run(tmp_path)
    fragments = read_model(directory / "fragments.json", AssessmentFragments)
    assessment = read_model(directory / "assessment.json", OfflineAssessment)
    configuration = read_model(directory / "analysis-config.json", AdvisorConfig)
    assessment.snapshot.clusters[0].uid = "foreign-fingerprint"
    assessment.report = analyze(assessment.snapshot, configuration, as_of=AS_OF)
    rebound = tmp_path / "rebound"
    write_assessment_artifacts(rebound, fragments, assessment, configuration)
    with pytest.raises(ValueError, match="fingerprint"):
        retained_query_quality(rebound, queries, source_profile, tenant_id=TENANT)


def test_catalog_export_retains_original_quality_without_changing_live_queries(
    tmp_path: Path,
) -> None:
    directory, queries, source_profile = _retained_run(tmp_path)
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    arguments = [
        "catalog",
        "export",
        "AKS-NP-001",
        "--config",
        "examples/cpu-pack-config.yaml",
        "--entities",
        "examples/pool-pack-entities.json",
        "--source",
        "synthetic",
        "--grafana",
        "--assessment-artifacts",
        str(directory),
    ]
    output = tmp_path / "retained-export"
    runner = CliRunner()
    result = runner.invoke(app, [*arguments, "--output", str(output)])
    assert result.exit_code == 0, result.output
    quality = RetainedAssessmentQuality.model_validate_json(
        (output / "retained-quality.json").read_text(encoding="utf-8")
    )
    assert quality == retained_query_quality(directory, queries, source_profile, tenant_id=TENANT)
    assert all(record.status == "matched" for record in quality.records)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["queries"] == [query.model_dump(mode="json") for query in queries]
    dashboard = json.loads((output / "dashboard.json").read_text(encoding="utf-8"))
    assert any(panel["title"] == "Retained assessment quality" for panel in dashboard["panels"])
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before
    assert runner.invoke(app, [*arguments, "--output", str(output)]).exit_code == 1
    original = directory / "assessment.json"
    original.write_text("SENSITIVE-BROKEN-ARTIFACT", encoding="utf-8")
    invalid_output = tmp_path / "invalid-export"
    invalid = runner.invoke(app, [*arguments, "--output", str(invalid_output)])
    assert invalid.exit_code == 2
    assert "SENSITIVE-BROKEN-ARTIFACT" not in invalid.output
    assert not invalid_output.exists()


def test_catalog_export_attaches_exact_source_acceptance(tmp_path: Path) -> None:
    settings = load_onboarding_config(Path("examples/cpu-pack-config.yaml"))
    catalog = load_catalog()
    targets = (
        RootModel[list[MetricEntity]]
        .model_validate_json(Path("examples/cpu-pack-entities.json").read_text(encoding="utf-8"))
        .root
    )
    queries = render_pack_queries(catalog, "AKS-RQ-002", settings, "synthetic", targets, "baseline")
    source_profile = catalog.source(settings.metric_sources[0].catalog_profile)
    acceptance = PrometheusSourceAcceptance(
        tenant_id=str(settings.scope.tenant_id),
        cluster_resource_id=targets[0].cluster_resource_id,
        cluster_uid="synthetic-cluster-uid",
        source="synthetic",
        source_profile_id=source_profile.id,
        source_profile_version=source_profile.version,
        evaluated_at=AS_OF,
        window_start=AS_OF - timedelta(hours=1),
        window_end=AS_OF,
        step_seconds=300,
        status="accepted",
        reason_codes=[],
        input_digest="a" * 64,
        configuration_digest=digest_json(settings.model_dump(mode="json")),
        records=[
            PrometheusQueryAcceptance(
                query_id=query.metric,
                query_version=query.version,
                expression_digest=query.expression_digest,
                unit=catalog.queries[query.metric].unit,
                status="accepted",
                reason_codes=[],
                required_label_keys=["azure_resource_id"],
                observed_series=1,
                matched_expected_entities=1,
                expected_entities=1,
                duplicate_series=0,
                latest_sample_at=AS_OF,
            )
            for query in queries
        ],
    )
    acceptance_path = tmp_path / "source-acceptance.json"
    acceptance_path.write_text(acceptance.model_dump_json(), encoding="utf-8")
    output = tmp_path / "accepted-export"
    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "export",
            "AKS-RQ-002",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--entities",
            "examples/cpu-pack-entities.json",
            "--source",
            "synthetic",
            "--grafana",
            "--source-acceptance",
            str(acceptance_path),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (
        PrometheusSourceAcceptance.model_validate_json(
            (output / "source-acceptance.json").read_text(encoding="utf-8")
        )
        == acceptance
    )
    dashboard = json.loads((output / "dashboard.json").read_text(encoding="utf-8"))
    assert any(panel["title"] == "Supplied source acceptance" for panel in dashboard["panels"])


def test_catalog_export_combines_packs_in_one_deduplicated_dashboard(tmp_path: Path) -> None:
    output = tmp_path / "combined"
    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "export",
            "AKS-RQ-002",
            "--pack",
            "AKS-MEM-001",
            "--pack",
            "AKS-RQ-003",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--entities",
            "examples/cpu-pack-entities.json",
            "--source",
            "synthetic",
            "--grafana",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    QueryBundleExportManifest.model_validate(manifest)
    assert {pack["id"] for pack in manifest["packs"]} == {"AKS-RQ-002", "AKS-RQ-003", "AKS-MEM-001"}
    keys = [(query["metric"], query["entity_digest"]) for query in manifest["queries"]]
    assert len(keys) == len(set(keys))
    dashboard = json.loads((output / "dashboard.json").read_text(encoding="utf-8"))
    assert len([panel for panel in dashboard["panels"] if panel["type"] == "timeseries"]) == len(
        keys
    )
    assert {panel["title"] for panel in dashboard["panels"] if panel["type"] == "row"} == {
        "Workload CPU",
        "Reliability",
    }
    assert len(list(output.glob("*.promql"))) == len(keys)


@pytest.mark.parametrize("problem", ["foreign", "missing-entity", "inventory", "duplicate", "lock"])
def test_query_bundle_rejects_ambiguous_or_unapproved_selection(problem: str) -> None:
    settings = profile()
    targets = [entity()]
    packs = ["AKS-RQ-002", "AKS-MEM-001"]
    if problem == "foreign":
        targets[0] = targets[0].model_copy(
            update={"cluster_resource_id": targets[0].cluster_resource_id + "-foreign"}
        )
    elif problem == "missing-entity":
        packs.append("AKS-NP-001")
    elif problem == "inventory":
        packs.append("AKS-NP-004")
    elif problem == "duplicate":
        packs.append("AKS-RQ-002")
    else:
        settings.analysis.pack_locks = {"AKS-RQ-002": "0" * 64}
    with pytest.raises(ValueError):
        render_query_bundle(load_catalog(), packs, settings, "synthetic", targets, "baseline")


def test_query_bundle_is_order_independent_and_preserves_profile_mappings() -> None:
    settings = profile()
    settings.metric_sources[0].query_label_mappings = {
        "cpu_usage": {"cluster_resource_id": "custom_cluster"}
    }
    packs = ["AKS-RQ-002", "AKS-MEM-001", "AKS-RQ-003"]
    first = render_query_bundle(
        load_catalog(), packs, settings, "synthetic", [entity()], "baseline"
    )
    second = render_query_bundle(
        load_catalog(), list(reversed(packs)), settings, "synthetic", [entity()], "baseline"
    )
    assert first == second
    cpu = next(query for query in first[1] if query.metric == "cpu_usage")
    assert 'custom_cluster="' in cpu.expression
    dashboard = grafana_dashboard(
        first[1], load_catalog().source(settings.metric_sources[0].catalog_profile)
    )
    assert all(
        panel["targets"][0]["interval"] == "300s"
        for panel in dashboard["panels"]
        if panel["type"] == "timeseries"
    )


def test_invalid_combined_export_creates_no_partial_files(tmp_path: Path) -> None:
    output = tmp_path / "not-created"
    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "export",
            "AKS-RQ-002",
            "--pack",
            "AKS-NP-001",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--source",
            "synthetic",
            "--entities",
            "examples/cpu-pack-entities.json",
            "--grafana",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2
    assert not output.exists()


def test_operator_cli_exports_guide_configuration_dashboard_and_report(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "guide.md"
    result = runner.invoke(app, ["catalog", "guide", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "AKS-MEM-005" in output.read_text(encoding="utf-8")
    config = tmp_path / "config.yaml"
    result = runner.invoke(
        app,
        [
            "configure",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--no-interactive",
            "--pack",
            "AKS-RQ-002",
            "--review-ratio",
            "AKS-RQ-002=0.3",
            "--output",
            str(config),
        ],
    )
    assert result.exit_code == 0, result.output
    assert load_onboarding_config(config).analysis.pack_parameters["AKS-RQ-002"].review_ratio == 0.3
    exported = tmp_path / "queries"
    result = runner.invoke(
        app,
        [
            "catalog",
            "export",
            "AKS-RQ-002",
            "--config",
            str(config),
            "--source",
            "synthetic",
            "--entities",
            "examples/cpu-pack-entities.json",
            "--grafana",
            "--output",
            str(exported),
        ],
    )
    assert result.exit_code == 0, result.output
    dashboard = json.loads((exported / "dashboard.json").read_text())
    assert any(panel["type"] == "row" for panel in dashboard["panels"])
    assert any(panel["type"] == "text" for panel in dashboard["panels"])
    assert all(
        panel["targets"][0]["expr"]
        for panel in dashboard["panels"]
        if panel["type"] == "timeseries"
    )
    report = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "assess",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--config",
            str(config),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(report),
        ],
    )
    assert result.exit_code in {0, 3}, result.output
    assert report.is_file()
    assert runner.invoke(app, ["catalog", "guide", "--output", str(output)]).exit_code != 0


def test_guided_configuration_creates_inventory_only_profile_without_credentials(
    tmp_path: Path,
) -> None:
    from test_collection import CLUSTER, TENANT

    output = tmp_path / "guided.yaml"
    result = CliRunner().invoke(
        app,
        ["configure", "--output", str(output)],
        input="\n".join([TENANT, TENANT, CLUSTER, "n", "", "", "AKS-RQ-001", "baseline", ""]),
    )
    assert result.exit_code == 0, result.output
    config = load_onboarding_config(output)
    assert config.analysis.packs == ["AKS-RQ-001"]
    assert config.analysis.mode == "baseline"
    assert not config.metric_sources
    assert "owner" in result.output
    assert "No endpoint or credential" in result.output


def test_preview_cli_does_not_read_metadata_export_or_construct_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import cli

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Offline preview attempted to construct live clients")

    monkeypatch.setattr(cli, "builtin_readers", forbidden)
    request = plan()
    request.clusters[0].entities = [entity()]
    request.clusters[0].metadata_export = tmp_path / "not-present.json"
    path = tmp_path / "plan.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    output = tmp_path / "preview.json"
    result = CliRunner().invoke(
        app,
        [
            "preview",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--plan",
            str(path),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "offline"
    assert len(payload["queries"]) == 2
    assert payload["capabilities"][0]["status"] == "unknown"


def test_preview_never_resolves_metadata_export_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = plan()
    request.clusters[0].metadata_export = Path("not-present.json")
    path = tmp_path / "plan.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    original = Path.resolve

    def forbid_export_resolution(self: Path, strict: bool = False) -> Path:
        if self.name == "not-present.json":
            pytest.fail("Offline preview resolved a source-export path")
        return original(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", forbid_export_resolution)
    result = CliRunner().invoke(
        app,
        [
            "preview",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--plan",
            str(path),
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert result.exit_code == 0, result.output
