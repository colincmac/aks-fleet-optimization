from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_rules import AS_OF, eligible_snapshot

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.rules import engine


def test_collector_uses_only_packaged_query_assets() -> None:
    from aks_fleet_efficiency.collectors import prometheus

    assert prometheus.QUERY_CATALOG == load_catalog().queries
    assert not hasattr(prometheus, "QueryDefinition")
    assert {"cpu_limit", "node_memory_usage"}.isdisjoint(prometheus.QUERY_CATALOG)


@pytest.mark.parametrize("pack_id", list(load_catalog().manifests))
def test_catalog_rejects_missing_rule_pack(tmp_path: Path, pack_id: str) -> None:
    root = tmp_path / "catalog"
    shutil.copytree(
        Path("src/aks_fleet_efficiency/catalog"),
        root,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    pack = load_catalog().pack(pack_id)
    for path in (root / "packs").glob("*.yaml"):
        if f"id: {pack.id}\n" in path.read_text(encoding="utf-8"):
            path.unlink()
            break
    else:
        pytest.fail(f"Missing test manifest for {pack_id}")
    with pytest.raises(ValueError, match="missing packs"):
        load_catalog(root)


def test_report_has_no_obsolete_unpacked_rule_contract() -> None:
    report = engine.analyze(eligible_snapshot(), AdvisorConfig(), as_of=AS_OF)
    assert "unpacked_rule_ids" not in report.model_dump()
    versions = {pack.id: pack.version for pack in report.pack_provenance}
    assert len(versions) == 21
    assert all(
        finding.rule_version == versions[finding.rule_id]
        for finding in [*report.recommendations, *report.blocked_recommendations]
    )
    with pytest.raises(ValueError, match="unpacked_rule_ids"):
        type(report).model_validate(report.model_dump() | {"unpacked_rule_ids": []})


def test_every_pack_has_exactly_one_registered_family_evaluator() -> None:
    registries = [
        engine.CPU_EVALUATORS,
        engine.POOL_EVALUATORS,
        engine.MEMORY_EVALUATORS,
        engine.AUTOSCALER_EVALUATORS,
        engine.SCHEDULING_EVALUATORS,
        engine.CAPACITY_EVALUATORS,
    ]
    evaluators = [name for registry in registries for name in registry]
    assert len(evaluators) == len(set(evaluators)) == 21
    assert set(evaluators) == {pack.evaluator for pack in load_catalog().manifests.values()}


def test_engine_delegates_cpu_signal_selection_to_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def assess(*args: object) -> None:
        calls.append(args)

    monkeypatch.setitem(engine.CPU_EVALUATORS, "cpu-request-review", assess)
    snapshot = eligible_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.usage_cpu_p95_mcores = resources.request_cpu_mcores
    engine.analyze(snapshot, AdvisorConfig(packs=["AKS-RQ-002"]), as_of=AS_OF)
    assert any(args[3] is snapshot.clusters[0].workloads[0].containers[0] for args in calls)


def test_controller_summary_is_owned_by_selected_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import catalog as catalog_module
    from aks_fleet_efficiency.assessment import AssessmentFragments, assess_fragments
    from aks_fleet_efficiency.config import load_onboarding_config

    catalog = load_catalog()
    pack = catalog.pack("AKS-AS-004")
    pack.summary_variants["keda-chain"] = "Synthetic selected pack guidance."
    monkeypatch.setattr(catalog_module, "load_catalog", lambda: catalog)
    monkeypatch.setattr(engine, "load_catalog", lambda: catalog)
    settings = load_onboarding_config(Path("examples/pool-assessment-config.yaml"))
    settings.analysis = AdvisorConfig(packs=[pack.id])
    fragments = AssessmentFragments.model_validate_json(
        Path("examples/fixtures/keda-assessment.json").read_bytes()
    )
    report = assess_fragments(fragments, settings, as_of=AS_OF).report
    assert report.recommendations[0].summary.startswith("Synthetic selected pack guidance.")


@pytest.mark.parametrize("defect", ["missing", "unknown", "wrong-pack"])
def test_summary_variants_are_closed_and_evaluator_specific(defect: str) -> None:
    payload = load_catalog().pack("AKS-AS-004").model_dump()
    if defect == "missing":
        payload["summary_variants"].pop("keda-chain")
    elif defect == "unknown":
        payload["summary_variants"]["arbitrary-expression"] = "Not executable."
    else:
        payload = load_catalog().pack("AKS-RQ-001").model_dump()
        payload["summary_variants"] = {"keda-chain": "Wrong family."}
    with pytest.raises(ValueError):
        PackManifest.model_validate(payload)
