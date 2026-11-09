from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_prometheus import entity, profile
from test_rules import AS_OF, eligible_snapshot
from typer.testing import CliRunner

from aks_fleet_efficiency.catalog import (
    PackManifest,
    load_catalog,
    render_pack_queries,
)
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import MetricEntity
from aks_fleet_efficiency.rules.engine import analyze

PACK = "AKS-RQ-002"


@pytest.mark.parametrize("defect", ["duplicate-pack", "unknown-query", "duplicate-key", "no-scope"])
def test_catalog_rejects_corrupt_packaged_assets(tmp_path: Path, defect: str) -> None:
    original = Path("src/aks_fleet_efficiency/catalog")
    root = tmp_path / "catalog"
    shutil.copytree(original, root, ignore=shutil.ignore_patterns("__pycache__"))
    manifest = root / "packs/cpu-request.yaml"
    if defect == "duplicate-pack":
        shutil.copyfile(manifest, root / "packs/duplicate.yaml")
    elif defect == "unknown-query":
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace("cpu_usage", "unknown_metric"),
            encoding="utf-8",
        )
    elif defect == "duplicate-key":
        manifest.write_text(manifest.read_text(encoding="utf-8") + "\nid: AKS-RQ-002\n")
    else:
        (root / "queries/cpu-usage.promql").write_text("vector(0)", encoding="utf-8")
    with pytest.raises(ValueError):
        load_catalog(root)


def test_pack_contract_has_typed_queries_parameters_and_closed_evaluator() -> None:
    catalog = load_catalog()
    pack = catalog.pack(PACK)
    assert pack.id == PACK
    assert pack.version == "2.1.0"
    assert pack.evaluator == "cpu-request-review"
    assert pack.parameters.review_ratio == 0.4
    assert pack.queries["baseline"]["container"] == ["cpu_usage", "cpu_request"]
    assert pack.queries["guarded"]["container"] == [
        "cpu_usage",
        "cpu_request",
        "cpu_throttling",
        "oom_events",
    ]
    assert len(catalog.inventory) == 21
    assert all(item.id.startswith("AKS-") for item in catalog.inventory)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evaluator", "os.system"),
        ("version", "latest"),
        ("sources", ["unapproved"]),
        ("parameters", {"review_ratio": 0}),
        ("parameters", {"review_ratio": float("nan")}),
        ("parameters", {"review_ratio": 0.4, "execute": "anything"}),
        ("queries", {"baseline": {"container": []}}),
    ],
)
def test_pack_rejects_invalid_contract(field: str, value: object) -> None:
    payload = load_catalog().pack(PACK).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        PackManifest.model_validate(payload)


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_export_uses_same_scope_and_expression_as_collector(mode: str) -> None:
    result = render_pack_queries(load_catalog(), PACK, profile(), "synthetic", [entity()], mode)
    assert len(result) == (2 if mode == "baseline" else 4)
    usage = next(query for query in result if query.metric == "cpu_usage")
    assert usage.expression.startswith("rate(container_cpu_usage_seconds_total{")
    assert f'azure_resource_id="{entity().cluster_resource_id}"' in usage.expression
    assert 'workload_uid="workload-uid"' in usage.expression
    assert 'pod_uid="pod-uid"' in usage.expression
    assert "__scope__" not in usage.expression
    assert len(usage.expression_digest) == 64


def test_export_escapes_untrusted_identity_and_does_not_expand_scope() -> None:
    target = entity().model_copy(update={"container": 'api"} or vector(0) #'})
    query = render_pack_queries(load_catalog(), PACK, profile(), "synthetic", [target], "baseline")[
        0
    ]
    assert 'container="api\\"} or vector(0) #"' in query.expression


@pytest.mark.parametrize(
    "problem", ["source", "scope", "kind", "duplicate", "mapping", "missing-uid", "invalid-label"]
)
def test_export_rejects_unknown_or_ambiguous_source_scope(problem: str) -> None:
    source = profile()
    targets = [entity()]
    name = "synthetic"
    if problem == "source":
        name = "unknown"
    elif problem == "scope":
        targets = [
            entity().model_copy(update={"cluster_resource_id": entity().cluster_resource_id + "x"})
        ]
    elif problem == "kind":
        targets = [
            MetricEntity(
                kind="workload",
                cluster_resource_id=entity().cluster_resource_id,
                namespace="synthetic",
                workload_kind="Deployment",
                workload="synthetic",
                workload_uid="synthetic-uid",
            )
        ]
    elif problem == "duplicate":
        targets.append(entity())
    elif problem == "mapping":
        source.metric_sources[0].label_mapping["container"] = "workload_uid"
    elif problem == "missing-uid":
        targets = [entity().model_copy(update={"pod_uid": None})]
    else:
        source.metric_sources[0].label_mapping["container"] = "invalid-label"
    with pytest.raises(ValueError):
        render_pack_queries(load_catalog(), PACK, source, name, targets, "baseline")


def test_replica_queries_require_membership_and_never_fake_pod_identity() -> None:
    target = MetricEntity(
        kind="workload_container",
        cluster_resource_id=entity().cluster_resource_id,
        namespace="synthetic",
        workload_kind="Deployment",
        workload="synthetic",
        workload_uid="synthetic-uid",
        container="api",
        membership_digest="a" * 64,
    )
    result = render_pack_queries(load_catalog(), PACK, profile(), "synthetic", [target], "guarded")
    assert len(result) == 5
    assert all('membership_digest="' in item.expression for item in result)
    assert all("pod_uid" not in item.expression for item in result)


@pytest.mark.parametrize("metric", list(load_catalog().queries))
def test_export_expression_is_exactly_the_query_sent_by_collector(metric: str) -> None:
    from test_prometheus import END, START, FakeMetricReader, matrix

    from aks_fleet_efficiency.collectors.metric_queries import metric_labels
    from aks_fleet_efficiency.collectors.prometheus import PrometheusMetricCollector

    target = entity()
    pack_id = PACK
    if load_catalog().queries[metric].kind == "workload_container":
        payload = target.model_dump()
        payload.update(kind="workload_container", pod_uid=None, membership_digest="a" * 64)
        target = MetricEntity.model_validate(payload)
    elif load_catalog().queries[metric].kind == "node":
        target = MetricEntity(
            kind="node",
            cluster_resource_id=entity().cluster_resource_id,
            node_resource_id="/synthetic/node",
            node_uid="synthetic-node-uid",
        )
        pack_id = "AKS-NP-001"
    elif load_catalog().queries[metric].kind == "workload":
        target = MetricEntity(
            kind="workload",
            cluster_resource_id=entity().cluster_resource_id,
            namespace="synthetic",
            workload_kind="Deployment",
            workload="synthetic",
            workload_uid="synthetic-workload-uid",
        )
    elif load_catalog().queries[metric].kind == "hpa":
        target = MetricEntity(
            kind="hpa",
            cluster_resource_id=entity().cluster_resource_id,
            namespace="synthetic",
            workload_kind="Deployment",
            workload="synthetic",
            workload_uid="synthetic-workload-uid",
            hpa_uid="synthetic-hpa-uid",
        )
    pack_id = next(
        pack.id
        for pack in load_catalog().manifests.values()
        if metric in pack.queries["guarded"].get(target.kind, [])
    )
    response = matrix([0, 0, 0, 0])
    response.series[0]["metric"] = metric_labels(target, profile().metric_sources[0])
    reader = FakeMetricReader([response])
    collected = PrometheusMetricCollector(
        profile(), source_name="synthetic", reader=reader, entities=[target], clock=lambda: AS_OF
    ).collect_observations(start=START, end=END, step_seconds=300, metrics=[metric])
    exported = next(
        item
        for item in render_pack_queries(
            load_catalog(), pack_id, profile(), "synthetic", [target], "guarded"
        )
        if item.metric == metric
    )
    assert reader.calls[0][0] == exported.expression
    assert collected.observations[0].quality.query_expression == exported.expression


def test_default_baseline_is_investigation_without_owner_or_reliability_claims() -> None:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    workload.safety_policy = None
    workload.autoscaling.hpa = True
    report = analyze(snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert report.mode == "baseline"
    assert {finding.rule_id for finding in report.recommendations} == {PACK}
    finding = report.recommendations[0]
    assert finding.proposed_requests is None
    assert finding.current_requests is None
    assert finding.estimated_monthly_savings is None
    assert not any(item.metric == "potential_cpu_request_reduction" for item in finding.evidence)
    assert "not a safe" in finding.summary
    assert report.pack_provenance[0].id == PACK


def test_guarded_slice_preserves_exact_target_policy_and_replay_lock() -> None:
    snapshot = eligible_snapshot()
    config = AdvisorConfig(mode="guarded", packs=[PACK])
    report = analyze(snapshot, config, as_of=AS_OF)
    finding = report.recommendations[0]
    assert finding.proposed_requests is not None
    assert finding.proposed_requests.cpu_mcores == 750
    assert finding.current_requests is not None
    assert finding.current_requests.cpu_mcores == 1000
    assert len(report.pack_provenance[0].digest) == 64
    replay = config.model_copy(
        update={"pack_locks": {item.id: item.digest for item in report.pack_provenance}}
    )
    assert analyze(snapshot, replay, as_of=AS_OF) == report
    replay.pack_locks[PACK] = "0" * 64
    with pytest.raises(ValueError, match="pack lock"):
        analyze(snapshot, replay, as_of=AS_OF)


def test_rule_version_comes_from_selected_manifest_not_a_duplicate_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import catalog as catalog_module
    from aks_fleet_efficiency.rules import engine

    catalog = load_catalog()
    catalog.manifests[PACK] = catalog.pack(PACK).model_copy(update={"version": "2.2.0"})
    monkeypatch.setattr(catalog_module, "load_catalog", lambda: catalog)
    monkeypatch.setattr(engine, "load_catalog", lambda: catalog)
    report = analyze(eligible_snapshot(), AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert report.pack_provenance[0].version == "2.2.0"
    assert report.recommendations[0].rule_version == "2.2.0"


@pytest.mark.parametrize(
    "problem",
    ["owner", "oom", "eviction", "throttling", "coverage", "stale", "identity"],
)
def test_guarded_pack_retains_existing_vetoes(problem: str) -> None:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    resources = workload.containers[0].resources
    if problem == "owner":
        workload.safety_policy = None
    elif problem == "oom":
        resources.memory_oom_events = 1
    elif problem == "eviction":
        workload.eviction_events = 1
    elif problem == "throttling":
        resources.cpu_throttled_ratio = 0.1
    elif problem == "coverage":
        resources.metric_quality["usage_cpu_p95_mcores"].window.coverage_ratio = 0.2
    elif problem == "stale":
        snapshot.generated_at = AS_OF - timedelta(days=2)
    else:
        workload.uid = None
    report = analyze(snapshot, AdvisorConfig(mode="guarded", packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations
    assert all(item.rule_id == PACK for item in report.blocked_recommendations)


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_no_signal_at_review_boundary(mode: str) -> None:
    snapshot = eligible_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.usage_cpu_p95_mcores = resources.request_cpu_mcores * 0.4
    resources.metric_quality["usage_cpu_p95_mcores"].maximum = 1000
    report = analyze(snapshot, AdvisorConfig(mode=mode, packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations


def test_review_parameter_is_typed_and_selection_rejects_unknown_packs() -> None:
    for payload in [
        {"packs": ["AKS-UNKNOWN-001"]},
        {"packs": []},
        {"packs": [PACK, PACK]},
        {"pack_parameters": {PACK: {"review_ratio": 1}}},
        {"pack_parameters": {"unknown": {"review_ratio": 0.4}}},
        {"pack_parameters": {PACK: {"unknown": 1}}},
        {"mode": "automatic"},
    ]:
        with pytest.raises(ValidationError):
            AdvisorConfig.model_validate(payload)
    config = AdvisorConfig(packs=[PACK], pack_parameters={PACK: {"review_ratio": 0.2}})
    assert not analyze(eligible_snapshot(), config, as_of=AS_OF).recommendations


def test_catalog_commands_are_offline_and_export_exclusive_assets(tmp_path: Path) -> None:
    runner = CliRunner()
    listed = runner.invoke(app, ["catalog", "list"])
    assert listed.exit_code == 0
    assert PACK in listed.stdout
    shown = runner.invoke(app, ["catalog", "show", PACK])
    assert shown.exit_code == 0
    assert "cpu-request-review" in shown.stdout
    assert json.loads(shown.stdout)["manifest"]["id"] == PACK
    config = tmp_path / "profile.json"
    config.write_text(profile().model_dump_json(), encoding="utf-8")
    targets = tmp_path / "entities.json"
    targets.write_text(json.dumps([entity().model_dump()]), encoding="utf-8")
    output = tmp_path / "queries"
    arguments = [
        "catalog",
        "export",
        PACK,
        "--config",
        str(config),
        "--source",
        "synthetic",
        "--entities",
        str(targets),
        "--output",
        str(output),
    ]
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert len(list(output.glob("*.promql"))) == 2
    receipt = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert receipt["pack"]["id"] == PACK
    assert receipt["mode"] == "baseline"
    repeated = runner.invoke(app, arguments)
    assert repeated.exit_code == 1
    assert runner.invoke(app, ["catalog", "show", "unknown"]).exit_code == 2


def test_cli_mode_selection_and_artifact_replay(tmp_path: Path) -> None:
    from aks_fleet_efficiency.config import load_onboarding_config

    runner = CliRunner()
    output = tmp_path / "assessment"
    assessed = runner.invoke(
        app,
        [
            "assess",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--config",
            "examples/pool-assessment-config.yaml",
            "--mode",
            "guarded",
            "--pack",
            PACK,
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
            "--artifacts",
            str(output),
        ],
    )
    assert assessed.exit_code == 3, assessed.output
    assessment = json.loads(assessed.stdout)
    assert assessment["issues"][0]["code"] == "unsupported-pool-evidence"
    saved = json.loads((output / "analysis-config.json").read_text(encoding="utf-8"))
    assert saved["mode"] == "guarded"
    assert saved["packs"] == [PACK]
    assert saved["pack_locks"][PACK] == assessment["report"]["pack_provenance"][0]["digest"]
    replayed = runner.invoke(
        app,
        [
            "analyze",
            "--snapshot",
            str(output / "snapshot.json"),
            "--config",
            str(output / "analysis-config.json"),
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
        ],
    )
    assert replayed.exit_code == 0, replayed.output
    assert json.loads(replayed.stdout) == assessment["report"]
    bad = runner.invoke(
        app,
        [
            "assess",
            "--config",
            "examples/pool-assessment-config.yaml",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--pack",
            "unknown",
        ],
    )
    assert bad.exit_code == 2
    assert load_onboarding_config(Path("examples/pool-assessment-config.yaml")).clusters


def test_baseline_never_emits_other_numeric_proposals() -> None:
    from test_rules import memory_proposal_payload

    from aks_fleet_efficiency.models import FleetSnapshot

    report = analyze(
        FleetSnapshot.model_validate(memory_proposal_payload()), AdvisorConfig(), as_of=AS_OF
    )
    assert all(
        item.proposed_requests is None
        and item.proposed_limits is None
        and item.proposed_replica_floor is None
        for item in report.recommendations
    )
    assert any(
        "guarded_mode_required" in item.reason_codes for item in report.blocked_recommendations
    )


def test_explicit_pack_collection_only_queries_selected_approved_dependencies() -> None:
    from test_collection import Inventory, Metadata
    from test_prometheus import END, START, FakeMetricReader, matrix

    from aks_fleet_efficiency.collection import CollectionPlan, CollectionReaders, collect_fragments

    settings = profile()
    settings.analysis = AdvisorConfig(packs=[PACK])
    request = CollectionPlan(
        window_start=START,
        window_end=END,
        clusters=[
            {
                "resource_id": entity().cluster_resource_id,
                "expected_cluster_uid": "synthetic-cluster-uid",
                "entities": [entity()],
                "metrics": ["cpu_usage", "cpu_request", "memory_usage"],
            }
        ],
    )
    reader = FakeMetricReader([matrix([1, 1, 1, 1]), matrix([100, 100, 100, 100])])
    result = collect_fragments(
        settings,
        request,
        CollectionReaders(
            inventory=Inventory(),
            kubernetes={entity().cluster_resource_id: Metadata()},
            metrics={"synthetic": reader},
        ),
        allow_live=True,
        clock=lambda: AS_OF,
    )
    assert len(reader.calls) == 2
    assert {item.metric for item in result.metrics[0].observations} == {"cpu_usage", "cpu_request"}
    assert request.clusters[0].metrics == ["cpu_usage", "cpu_request", "memory_usage"]
