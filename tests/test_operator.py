from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_collection import AS_OF, plan
from test_prometheus import entity, profile
from typer.testing import CliRunner

from aks_fleet_efficiency.catalog import load_catalog, render_pack_queries
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import load_onboarding_config
from aks_fleet_efficiency.operator import (
    build_operator_catalog,
    configure_profile,
    grafana_dashboard,
    preview_execution,
    render_operator_catalog,
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
    queries = render_pack_queries(
        load_catalog(), "AKS-RQ-002", profile(), "synthetic", [entity()], "baseline"
    )
    dashboard = grafana_dashboard(queries)
    expressions = {panel["targets"][0]["expr"] for panel in dashboard["panels"]}
    assert expressions == {query.expression for query in queries}
    assert all(panel["datasource"]["uid"] == "${DS_PROMETHEUS}" for panel in dashboard["panels"])
    assert "approval" in dashboard["description"].lower()


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
    assert json.loads((exported / "dashboard.json").read_text())["panels"]
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
