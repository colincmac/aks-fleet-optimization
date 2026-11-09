from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_assessment import assess
from test_prometheus import entity, profile
from test_rules import AS_OF, eligible_snapshot
from test_rules_autoscaler_completion import replica_payload

from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
from aks_fleet_efficiency.catalog import load_catalog, render_pack_queries
from aks_fleet_efficiency.config import AdvisorConfig, load_onboarding_config
from aks_fleet_efficiency.models import HPA_REPLICA_METRICS, WORKLOAD_REPLICA_METRICS, MetricEntity
from aks_fleet_efficiency.rules.engine import analyze

AUTOSCALERS = [f"AKS-AS-{index:03}" for index in range(1, 8)]
CURRENT = ["AKS-AS-001", "AKS-AS-002", "AKS-AS-004", "AKS-AS-007"]


def test_all_nineteen_rules_have_closed_packs_and_autoscaler_cards() -> None:
    catalog = load_catalog()
    assert set(catalog.manifests) == {item.id for item in catalog.inventory}
    for name in AUTOSCALERS:
        pack = catalog.pack(name)
        assert pack.version == "2.0.0"
        assert pack.family == "autoscaler"
        assert pack.title and pack.purpose and pack.limitations
        assert pack.required_evidence and pack.risks and pack.validation and pack.rollback
        assert pack.parameters.review_ratio is None
        with pytest.raises(ValidationError):
            AdvisorConfig(packs=[name], pack_parameters={name: {"review_ratio": 0.2}})
    for name in CURRENT:
        assert catalog.pack(name).evidence_kind == "inventory"
        assert catalog.provenance(name).queries == []
    for name in ["AKS-AS-003", "AKS-AS-006"]:
        assert set(catalog.pack(name).queries["baseline"]["hpa"]) == set(HPA_REPLICA_METRICS)
    floor = catalog.pack("AKS-AS-005")
    assert set(floor.queries["guarded"]["workload"]) == set(WORKLOAD_REPLICA_METRICS)
    assert len(catalog.provenance(floor.id).queries) == 7


@pytest.mark.parametrize(
    ("case", "pack_id"),
    [
        ("autoscalers", "AKS-AS-002"),
        ("hpa-history", "AKS-AS-003"),
        ("keda", "AKS-AS-004"),
        ("replica-floor", "AKS-AS-005"),
        ("vpa-bounds", "AKS-AS-007"),
    ],
)
def test_selected_autoscaler_pack_preserves_evidence_and_locked_replay(
    case: str, pack_id: str
) -> None:
    fragments = AssessmentFragments.model_validate_json(
        Path(f"examples/fixtures/{case}-assessment.json").read_bytes()
    )
    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis = AdvisorConfig(mode="guarded", packs=[pack_id])
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    assert finding.rule_id == pack_id
    assert finding.rule_version == "2.0.0"
    assert finding.proposed_requests is None and finding.proposed_limits is None
    assert finding.estimated_monthly_savings is None
    if pack_id == "AKS-AS-005":
        assert (finding.current_replica_floor, finding.proposed_replica_floor) == (2, 1)
    else:
        assert finding.proposed_replica_floor is None
    locked = settings.analysis.model_copy(
        update={"pack_locks": {item.id: item.digest for item in result.report.pack_provenance}}
    )
    assert analyze(result.snapshot, locked, as_of=AS_OF) == result.report
    with pytest.raises(ValueError, match="pack lock"):
        analyze(result.snapshot, locked.model_copy(update={"pack_locks": {pack_id: "a" * 64}}))


def test_current_fixed_replica_review_is_inventory_only_and_uses_exact_threshold() -> None:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    snapshot.clusters[0].workloads = [workload]
    workload.autoscaling.hpa = workload.autoscaling.keda = False
    settings = AdvisorConfig(packs=["AKS-AS-001"])
    workload.replicas = settings.thresholds.minimum_replicas_for_autoscaling_review
    report = analyze(snapshot, settings, as_of=AS_OF)
    assert len(report.recommendations) == 1
    assert report.recommendations[0].rule_version == "2.0.0"
    workload.replicas -= 1
    assert not analyze(snapshot, settings, as_of=AS_OF).recommendations


@pytest.mark.parametrize("defect", ["baseline", "opt-in", "missing", "coverage", "stale"])
def test_selected_floor_pack_stays_default_off_and_requires_all_history(defect: str) -> None:
    snapshot = assess(replica_payload()).snapshot
    workload = snapshot.clusters[0].workloads[0]
    config = AdvisorConfig(mode="guarded", packs=["AKS-AS-005"])
    if defect == "baseline":
        config.mode = "baseline"
    elif defect == "opt-in":
        workload.safety_policy.replicas.allow_floor_reduction = False
    elif defect == "missing":
        workload.hpa_replica_history.workload_metrics.pop("observed_replicas")
    elif defect == "coverage":
        workload.hpa_replica_history.metrics["hpa_min_replicas"].quality.window.coverage_ratio = 0.5
    else:
        config.thresholds.maximum_evidence_age_hours = 1
        snapshot.generated_at -= timedelta(hours=2)
    report = analyze(snapshot, config, as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations
    assert all(item.rule_version == "2.0.0" for item in report.blocked_recommendations)


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_shared_hpa_query_export_preserves_distinct_controller_uids(mode: str) -> None:
    target = MetricEntity(
        kind="hpa",
        cluster_resource_id=entity().cluster_resource_id,
        namespace="synthetic",
        workload_kind="Deployment",
        workload="synthetic",
        workload_uid="synthetic-workload-uid",
        hpa_uid="synthetic-hpa-one",
    )
    other = target.model_copy(update={"hpa_uid": "synthetic-hpa-two"})
    queries = render_pack_queries(
        load_catalog(), "AKS-AS-005", profile(), "synthetic", [target, other], mode
    )
    assert len(queries) == 8
    assert len({item.entity_digest for item in queries}) == 2
    assert all('workload_uid="synthetic-workload-uid"' in item.expression for item in queries)
    assert sum('hpa_uid="synthetic-hpa-one"' in item.expression for item in queries) == 4
    assert sum('hpa_uid="synthetic-hpa-two"' in item.expression for item in queries) == 4
    assert all("__scope__" not in item.expression for item in queries)


def test_current_reviews_survive_missing_history_without_manufacturing_pinning() -> None:
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/vpa-bounds-assessment.json").read_bytes()
    )
    fragments.metrics = []
    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis = AdvisorConfig(packs=["AKS-AS-002", "AKS-AS-003", "AKS-AS-007"])
    result = assess_fragments(fragments, settings, as_of=AS_OF)
    assert {item.rule_id for item in result.report.recommendations} == {"AKS-AS-002", "AKS-AS-007"}
    assert any(
        item.rule_id == "AKS-AS-003" and "missing_hpa_replica_history" in item.reason_codes
        for item in result.report.blocked_recommendations
    )


def test_selected_pack_does_not_execute_unrelated_autoscaler_evaluators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency.rules.autoscaler_rules import AUTOSCALER_EVALUATORS

    def unexpected(*args: object) -> None:
        pytest.fail("Unselected autoscaler evaluator must not execute")

    for name in AUTOSCALER_EVALUATORS:
        if name != "fixed-replica-review":
            monkeypatch.setitem(AUTOSCALER_EVALUATORS, name, unexpected)
    report = analyze(eligible_snapshot(), AdvisorConfig(packs=["AKS-AS-001"]), as_of=AS_OF)
    assert report.recommendations
    assert {item.id for item in report.pack_provenance} == {"AKS-AS-001"}


def test_floor_capabilities_include_missing_workload_availability_not_only_hpa() -> None:
    from aks_fleet_efficiency.capabilities import evaluate_source_capabilities

    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/replica-floor-assessment.json").read_bytes()
    )
    fragment = fragments.metrics[0]
    fragment.observations = [item for item in fragment.observations if item.entity.kind == "hpa"]
    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    capabilities = evaluate_source_capabilities(
        settings, [fragment], pack_id="AKS-AS-005", as_of=AS_OF
    )
    for capability in capabilities:
        checks = {item.code: item for item in capability.checks}
        assert all(checks[name].status == "available" for name in HPA_REPLICA_METRICS)
        assert all(checks[name].status == "unknown" for name in WORKLOAD_REPLICA_METRICS)


def test_autoscaler_pack_collection_deduplicates_shared_queries_not_controller_identity() -> None:
    from test_collection import Inventory, Metadata
    from test_prometheus import END, START, FakeMetricReader, matrix

    from aks_fleet_efficiency.collection import CollectionPlan, CollectionReaders, collect_fragments
    from aks_fleet_efficiency.collectors.metric_queries import metric_labels

    settings = profile()
    settings.analysis = AdvisorConfig(packs=["AKS-AS-003", "AKS-AS-005", "AKS-AS-006"])
    hpa = MetricEntity(
        kind="hpa",
        cluster_resource_id=entity().cluster_resource_id,
        namespace="synthetic",
        workload_kind="Deployment",
        workload="synthetic",
        workload_uid="synthetic-workload-uid",
        hpa_uid="synthetic-hpa-one",
    )
    other = hpa.model_copy(update={"hpa_uid": "synthetic-hpa-two"})
    workload = MetricEntity.model_validate(hpa.model_dump() | {"kind": "workload", "hpa_uid": None})
    metrics = [*HPA_REPLICA_METRICS, *WORKLOAD_REPLICA_METRICS, "cpu_usage"]
    plan = CollectionPlan(
        window_start=START,
        window_end=END,
        clusters=[
            {
                "resource_id": entity().cluster_resource_id,
                "expected_cluster_uid": "synthetic-cluster-uid",
                "entities": [hpa, other, workload],
                "metrics": metrics,
            }
        ],
    )
    responses = []
    for target, names in [
        (hpa, HPA_REPLICA_METRICS),
        (other, HPA_REPLICA_METRICS),
        (workload, WORKLOAD_REPLICA_METRICS),
    ]:
        for _ in names:
            response = matrix([2, 2, 2, 2])
            response.series[0]["metric"] = metric_labels(target, settings.metric_sources[0])
            responses.append(response)
    reader = FakeMetricReader(responses)
    result = collect_fragments(
        settings,
        plan,
        CollectionReaders(
            inventory=Inventory(),
            kubernetes={entity().cluster_resource_id: Metadata()},
            metrics={"synthetic": reader},
        ),
        allow_live=True,
        clock=lambda: AS_OF,
    )
    assert len(reader.calls) == 11
    assert {item.metric for item in result.metrics[0].observations} == set(metrics) - {"cpu_usage"}
    assert {
        item.entity.hpa_uid for item in result.metrics[0].observations if item.entity.kind == "hpa"
    } == {"synthetic-hpa-one", "synthetic-hpa-two"}
    assert plan.clusters[0].metrics == metrics
