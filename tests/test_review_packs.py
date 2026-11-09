from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import NoReturn

import pytest
from pydantic import ValidationError
from test_prometheus import entity, profile
from test_rules import AS_OF, eligible_snapshot
from typer.testing import CliRunner

from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
from aks_fleet_efficiency.catalog import load_catalog, render_pack_queries
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig, OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.models import FleetSnapshot, MetricEntity
from aks_fleet_efficiency.rules.engine import analyze

PACKS = ["AKS-RQ-001", "AKS-RQ-003", "AKS-NP-001"]


def test_all_review_rules_have_complete_closed_manifests() -> None:
    catalog = load_catalog()
    assert {"AKS-RQ-002", *PACKS} <= set(catalog.manifests)
    for name in PACKS:
        pack = catalog.pack(name)
        assert pack.version == "2.0.0"
        assert pack.purpose and pack.limitations and pack.required_evidence
        assert pack.risks and pack.validation and pack.rollback
    inventory = catalog.pack("AKS-RQ-001")
    assert inventory.evidence_kind == "inventory"
    assert inventory.queries == {"baseline": {}, "guarded": {}}
    assert catalog.provenance(inventory.id).queries == []


@pytest.mark.parametrize("observed", [True, False])
@pytest.mark.parametrize("amount", [None, 0])
def test_missing_request_distinguishes_observed_absence_and_unknown(
    observed: bool, amount: float | None
) -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads = [snapshot.clusters[0].workloads[0]]
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.request_cpu_mcores = amount
    resources.cpu_request_observed = observed
    report = analyze(snapshot, AdvisorConfig(packs=["AKS-RQ-001"]), as_of=AS_OF)
    if observed:
        assert len(report.recommendations) == 1
        finding = report.recommendations[0]
        assert finding.rule_id == "AKS-RQ-001"
        assert finding.evidence[0].value == amount
        assert finding.proposed_requests is None
        assert finding.estimated_monthly_savings is None
    else:
        assert not report.recommendations
        assert any(
            "missing_request_observation" in item.reason_codes
            for item in report.blocked_recommendations
        )


def test_inventory_only_request_review_does_not_require_metrics() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads = [snapshot.clusters[0].workloads[0]]
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.request_cpu_mcores = None
    resources.metric_quality.clear()
    receipt = next(
        item
        for item in snapshot.collection_manifest.source_results
        if item.collector == "prometheus"
    )
    receipt.source_observed_at = None
    result = analyze(snapshot, AdvisorConfig(packs=["AKS-RQ-001"]), as_of=AS_OF)
    assert len(result.recommendations) == 1
    assert result.recommendations[0].rule_id == "AKS-RQ-001"


def risk_snapshot() -> FleetSnapshot:
    snapshot = eligible_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.usage_cpu_p95_mcores = 1100
    resources.metric_quality["usage_cpu_p95_mcores"].maximum = 1500
    return snapshot


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_request_risk_is_not_saturation_or_a_numeric_proposal(mode: str) -> None:
    report = analyze(risk_snapshot(), AdvisorConfig(mode=mode, packs=["AKS-RQ-003"]), as_of=AS_OF)
    assert len(report.recommendations) == 1
    finding = report.recommendations[0]
    assert finding.rule_id == "AKS-RQ-003"
    assert "does not establish saturation" in finding.summary
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None


@pytest.mark.parametrize(
    "problem", ["missing-usage", "missing-quality", "low-coverage", "unknown-request"]
)
def test_request_risk_keeps_its_own_evidence_gates(problem: str) -> None:
    snapshot = risk_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    if problem == "missing-usage":
        resources.usage_cpu_p95_mcores = None
    elif problem == "missing-quality":
        resources.metric_quality.pop("cpu_throttled_ratio")
    elif problem == "low-coverage":
        resources.metric_quality["usage_cpu_p95_mcores"].window.coverage_ratio = 0.1
    else:
        resources.cpu_request_observed = False
    report = analyze(snapshot, AdvisorConfig(packs=["AKS-RQ-003"]), as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations


def test_request_risk_threshold_is_independent_of_reduction_threshold() -> None:
    snapshot = eligible_snapshot()
    report = analyze(
        snapshot,
        AdvisorConfig(packs=["AKS-RQ-003"], pack_parameters={"AKS-RQ-003": {"review_ratio": 0.2}}),
        as_of=AS_OF,
    )
    assert any(item.rule_id == "AKS-RQ-003" for item in report.recommendations)
    snapshot.clusters[0].workloads[0].containers[0].resources.usage_cpu_p95_mcores = 200
    report = analyze(
        snapshot,
        AdvisorConfig(packs=["AKS-RQ-003"], pack_parameters={"AKS-RQ-003": {"review_ratio": 0.2}}),
        as_of=AS_OF,
    )
    assert not report.recommendations


@pytest.mark.parametrize(
    "problem", ["missing-usage", "missing-quality", "low-coverage", "identity"]
)
def test_pool_pack_retains_evidence_and_identity_gates(problem: str) -> None:
    snapshot = eligible_snapshot()
    pool = snapshot.clusters[0].node_pools[0]
    if problem == "missing-usage":
        pool.usage_cpu_p95_mcores = None
    elif problem == "missing-quality":
        pool.metric_quality.clear()
    elif problem == "low-coverage":
        pool.metric_quality["usage_cpu_p95_mcores"].window.coverage_ratio = 0.1
    else:
        pool.resource_id = None
    report = analyze(snapshot, AdvisorConfig(packs=["AKS-NP-001"]), as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations


def test_pool_pack_is_review_only_and_excludes_nap_or_empty_pools() -> None:
    snapshot = eligible_snapshot()
    report = analyze(snapshot, AdvisorConfig(packs=["AKS-NP-001"]), as_of=AS_OF)
    assert len(report.recommendations) == 1
    assert "not proof" in report.recommendations[0].summary
    assert report.recommendations[0].proposed_requests is None
    pool = snapshot.clusters[0].node_pools[0]
    for changes in [{"nap_managed": True}, {"nap_managed": False, "node_count": 0}]:
        for key, value in changes.items():
            setattr(pool, key, value)
        assert not analyze(
            snapshot, AdvisorConfig(packs=["AKS-NP-001"]), as_of=AS_OF
        ).recommendations


@pytest.mark.parametrize(
    ("pack_id", "ratio"),
    [
        ("AKS-RQ-001", 0.4),
        ("AKS-RQ-002", 1),
        ("AKS-RQ-003", 0),
        ("AKS-NP-001", -0.1),
        ("AKS-NP-001", 1),
    ],
)
def test_parameters_are_validated_for_the_selected_evaluator(pack_id: str, ratio: float) -> None:
    with pytest.raises(ValidationError):
        AdvisorConfig(packs=[pack_id], pack_parameters={pack_id: {"review_ratio": ratio}})
    AdvisorConfig(packs=["AKS-RQ-003"], pack_parameters={"AKS-RQ-003": {"review_ratio": 1.5}})
    AdvisorConfig(packs=["AKS-NP-001"], pack_parameters={"AKS-NP-001": {"review_ratio": 0.0}})


def test_pool_export_requires_explicit_historical_node_identity() -> None:
    settings = profile()
    node = MetricEntity(
        kind="node",
        cluster_resource_id=entity().cluster_resource_id,
        node_resource_id="/synthetic/node-1",
        node_uid="synthetic-node-uid",
        node_pool_resource_id=entity().cluster_resource_id + "/agentPools/userpool",
    )
    queries = render_pack_queries(
        load_catalog(), "AKS-NP-001", settings, "synthetic", [node], "baseline"
    )
    assert {item.metric for item in queries} == {
        "node_cpu_usage",
        "node_allocatable_cpu",
        "node_allocatable_memory",
    }
    assert all('node_uid="synthetic-node-uid"' in item.expression for item in queries)
    assert all("__scope__" not in item.expression for item in queries)
    with pytest.raises(ValueError):
        render_pack_queries(
            load_catalog(),
            "AKS-NP-001",
            settings,
            "synthetic",
            [
                MetricEntity(
                    kind="node_pool",
                    cluster_resource_id=node.cluster_resource_id,
                    node_pool_resource_id=node.node_pool_resource_id,
                )
            ],
            "baseline",
        )


@pytest.mark.parametrize("defect", ["membership", "capacity"])
def test_pool_normalization_does_not_use_current_nodes_or_changing_capacity(defect: str) -> None:
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/pool-assessment.json").read_bytes()
    )
    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis.packs = ["AKS-NP-001"]
    if defect == "membership":
        fragments.metrics[0].observations = [
            item for item in fragments.metrics[0].observations if item.entity.kind != "node"
        ]
    else:
        item = next(
            item
            for item in fragments.metrics[0].observations
            if item.metric == "pool_allocatable_cpu"
        )
        item.maximum = item.minimum + 1
        item.quality.maximum = item.maximum
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    assert not result.report.recommendations
    assert any(item.code == "unsupported-pool-evidence" for item in result.issues)


def test_inventory_pack_cli_explains_no_promql_and_does_not_create_export(tmp_path: Path) -> None:
    shown = CliRunner().invoke(app, ["catalog", "show", "AKS-RQ-001"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["manifest"]["evidence_kind"] == "inventory"
    output = tmp_path / "queries"
    result = CliRunner().invoke(
        app,
        [
            "catalog",
            "export",
            "AKS-RQ-001",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--source",
            "synthetic",
            "--entities",
            "examples/cpu-pack-entities.json",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2
    assert not output.exists()


def test_pool_boundary_and_stale_quality_keep_review_blocked() -> None:
    from datetime import timedelta

    snapshot = eligible_snapshot()
    pool = snapshot.clusters[0].node_pools[0]
    ratio = pool.usage_cpu_p95_mcores / pool.allocatable_cpu_mcores
    report = analyze(
        snapshot,
        AdvisorConfig(
            packs=["AKS-NP-001"], pack_parameters={"AKS-NP-001": {"review_ratio": ratio}}
        ),
        as_of=AS_OF,
    )
    assert not report.recommendations
    pool.metric_quality["usage_cpu_p95_mcores"].observed_at = AS_OF - timedelta(days=2)
    report = analyze(snapshot, AdvisorConfig(packs=["AKS-NP-001"]), as_of=AS_OF)
    assert not report.recommendations
    assert any(
        "stale_metric_observation" in item.reason_codes for item in report.blocked_recommendations
    )


def test_inventory_only_readiness_does_not_demand_a_metric_source() -> None:
    from test_collection import profile as inventory_profile

    from aks_fleet_efficiency.readiness import evaluate_readiness

    settings = inventory_profile()
    settings.analysis = AdvisorConfig(packs=["AKS-RQ-001"])
    result = evaluate_readiness(settings, as_of=AS_OF)
    assert not any(item.code == "source.configuration" for item in result.checks)
    assert result.status == "unknown"


def test_inventory_only_collection_never_constructs_metric_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from contextlib import contextmanager

    from aks_fleet_efficiency import live_collection
    from aks_fleet_efficiency.collection import CollectionPlan

    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis = AdvisorConfig(packs=["AKS-RQ-001"])
    settings.metric_sources[0].authentication = "bearer-environment"
    settings.metric_sources[0].token_environment_variable = "SYNTHETIC_TOKEN"
    request = CollectionPlan(
        clusters=[
            {
                "resource_id": settings.clusters[0].resource_id,
                "expected_cluster_uid": "synthetic-cluster-uid",
                "metadata_export": Path("examples/fixtures/kubernetes-export.json"),
                "entities": [entity()],
            }
        ],
    )

    @contextmanager
    def inventory_reader(profile: OnboardingConfig) -> Iterator[object]:
        yield object()

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("Inventory-only selection constructed a metric/credential client")

    monkeypatch.setattr(live_collection, "AzureSdkInventoryReader", inventory_reader)
    monkeypatch.setattr(live_collection, "PrometheusHttpReader", forbidden)
    with live_collection.builtin_readers(settings, request, allow_live=True) as readers:
        assert not readers.metrics


def test_risk_review_requires_workload_identity() -> None:
    snapshot = risk_snapshot()
    snapshot.clusters[0].workloads[0].uid = None
    result = analyze(snapshot, AdvisorConfig(packs=["AKS-RQ-003"]), as_of=AS_OF)
    assert not result.recommendations
    assert any("missing_identity" in item.reason_codes for item in result.blocked_recommendations)
