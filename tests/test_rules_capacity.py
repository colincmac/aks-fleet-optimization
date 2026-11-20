from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_assessment import payload, profile
from test_rules import AS_OF, eligible_snapshot

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.rules.engine import analyze

PACK = "AKS-NP-002"
CONSOLIDATION_PACK = "AKS-NP-003"
DAEMONSET_PACK = "AKS-NP-004"


@pytest.mark.parametrize(("minute", "active"), [(0, True), (59, True), (60, False)])
def test_nap_policy_reference_uses_utc_schedule_and_static_boundaries(
    minute: int, active: bool
) -> None:
    from aks_fleet_efficiency.nap_policy import NapPolicyInput, review_nap_policy

    clock = AS_OF.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
    evidence = NapPolicyInput(
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id="synthetic-cluster-resource-id",
        cluster_uid="synthetic-cluster-uid",
        nodepool_uid="synthetic-nodepool-uid",
        object_version="synthetic-version",
        generation=1,
        observed_at=clock,
        supply_mode="dynamic",
        node_count=3,
        consolidation_policy="WhenEmptyOrUnderutilized",
        consolidate_after="0s",
        budgets=[{"nodes": "10%", "schedule": "0 0 * * *", "duration": "1h", "reasons": ["Empty"]}],
    )
    result = review_nap_policy(evidence, as_of=clock, maximum_source_age_seconds=3600)
    assert result.budgets[0].active == active
    assert result.reasons["Empty"].configured_limit == (1 if active else None)
    assert result.controller_admission == "unverified"
    evidence.supply_mode = "static"
    evidence.replicas = 3
    static = review_nap_policy(evidence, as_of=clock, maximum_source_age_seconds=3600)
    assert static.consolidation_interpretation == "ignored_for_static_pool"
    assert static.disruption_feasibility == "unknown"


def daemonset_payload() -> dict[str, Any]:
    return payload("daemonset-overhead-assessment")


def nap_policy_input() -> Any:
    from aks_fleet_efficiency.nap_policy import NapPolicyInput

    return NapPolicyInput(
        tenant_id="00000000-0000-0000-0000-000000000000",
        cluster_resource_id=eligible_snapshot().clusters[0].resource_id,
        cluster_uid="synthetic-cluster-uid",
        nodepool_uid="synthetic-nodepool-uid",
        object_version="synthetic-version",
        generation=1,
        observed_at=AS_OF,
        supply_mode="dynamic",
        node_count=11,
        consolidation_policy="WhenEmpty",
        consolidate_after="0s",
        budgets=[{"nodes": "10%"}, {"nodes": "1", "reasons": ["Empty"]}],
    )


def test_nap_policy_reason_minima_and_empty_reasons_are_not_defaults() -> None:
    from aks_fleet_efficiency.nap_policy import SuppliedNapBudget, review_nap_policy

    evidence = nap_policy_input()
    result = review_nap_policy(evidence, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert result.reasons["Empty"].configured_limit == 1
    assert result.reasons["Drifted"].configured_limit == 2
    assert result.reasons["Unhealthy"].configured_limit == 2
    evidence.budgets = (SuppliedNapBudget(nodes="0", reasons=()),)
    empty = review_nap_policy(evidence, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert all(row.status == "no_applicable_active_budget" for row in empty.reasons.values())
    evidence.budgets = None
    missing = review_nap_policy(evidence, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert all(row.status == "unknown" for row in missing.reasons.values())
    assert missing.actual_disruption_headroom == "not_calculated"


@pytest.mark.parametrize(
    "problem",
    [
        "timezone",
        "seconds",
        "extension",
        "duration",
        "missing_duration",
        "percent",
        "negative",
        "integer_overflow",
        "stale",
        "future",
        "missing_clock",
        "missing_count",
    ],
)
def test_nap_policy_invalid_or_missing_evidence_stays_unknown(problem: str) -> None:
    from aks_fleet_efficiency.nap_policy import SuppliedNapBudget, review_nap_policy

    evidence = nap_policy_input()
    budget = {"nodes": "10%", "schedule": "0 * * * *", "duration": "1h"}
    if problem == "timezone":
        budget["schedule"] = "TZ=Europe/London 0 * * * *"
    elif problem == "seconds":
        budget["schedule"] = "0 0 * * * *"
    elif problem == "extension":
        budget["schedule"] = "0 0 L * *"
    elif problem == "duration":
        budget["duration"] = "30s"
    elif problem == "missing_duration":
        del budget["duration"]
    elif problem in {"percent", "negative", "integer_overflow"}:
        budget["nodes"] = {"percent": "101%", "negative": "-1", "integer_overflow": str(2**31)}[
            problem
        ]
    elif problem == "stale":
        evidence.observed_at -= timedelta(seconds=3601)
    elif problem == "future":
        evidence.observed_at += timedelta(seconds=1)
    elif problem == "missing_clock":
        evidence.observed_at = None
    else:
        evidence.node_count = None
    evidence.budgets = (SuppliedNapBudget.model_validate(budget),)
    result = review_nap_policy(evidence, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert result.reasons["Empty"].configured_limit is None
    assert result.reasons["Empty"].status == "unknown"
    assert result.controller_admission == "unverified"
    assert result.disruption_feasibility == "unknown"


def test_nap_policy_age_equality_and_configured_never_are_independent() -> None:
    from aks_fleet_efficiency.nap_policy import review_nap_policy

    evidence = nap_policy_input()
    evidence.observed_at -= timedelta(seconds=3600)
    evidence.consolidate_after = "Never"
    result = review_nap_policy(evidence, as_of=AS_OF, maximum_source_age_seconds=3600)
    assert result.consolidation_interpretation == "disabled_by_never"
    assert result.reasons["Empty"].configured_limit == 1
    assert result.controller_admission == "unverified"


def test_nap_policy_native_projection_preserves_roster_and_unknown_population() -> None:
    from aks_fleet_efficiency.nap_policy import project_nap_policy_inputs, review_nap_policy

    metadata = AssessmentFragments.model_validate(nap_payload()).kubernetes[0]
    native = [
        {
            "apiVersion": row.api_version,
            "kind": row.kind,
            "metadata": {
                "name": row.name,
                "uid": row.uid,
                "resourceVersion": "synthetic-version",
                "generation": 1,
                "labels": row.labels,
                "ownerReferences": row.owner_references,
                "annotations": {"unapproved": "SENSITIVE-ANNOTATION"},
            },
            "spec": row.spec,
            "status": row.status,
        }
        for row in metadata.resources
        if row.kind == "NodePool"
    ]
    projected = project_nap_policy_inputs(metadata, nodepools=native)
    assert len(projected) == 1 and projected[0].node_count is None
    assert "SENSITIVE" not in projected[0].model_dump_json()
    result = review_nap_policy(projected[0], as_of=AS_OF, maximum_source_age_seconds=86400)
    assert result.consolidation_interpretation == "ignored_for_static_pool"
    assert result.reasons["Empty"].configured_limit == 0
    with pytest.raises(ValueError):
        project_nap_policy_inputs(metadata, nodepools=[])
    with pytest.raises(ValueError):
        project_nap_policy_inputs(metadata, nodepools=native + native)


def test_nap_policy_cli_is_scoped_exclusive_and_redacted(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from aks_fleet_efficiency.cli import app

    evidence = nap_policy_input()
    source = tmp_path / "policy.json"
    source.write_text(evidence.model_dump_json(), encoding="utf-8")
    output = tmp_path / "review.json"
    args = [
        "review-nap-policy",
        "--policy",
        str(source),
        "--tenant",
        str(evidence.tenant_id),
        "--cluster",
        evidence.cluster_resource_id,
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    runner = CliRunner()
    response = runner.invoke(app, args)
    assert response.exit_code == 0, response.output
    assert json.loads(output.read_text())["controller_admission"] == "unverified"
    original = output.read_bytes()
    assert runner.invoke(app, args).exit_code == 1 and output.read_bytes() == original
    output.unlink()
    value = evidence.model_dump(mode="json") | {"commands": ["SENSITIVE-NOT-EXECUTABLE"]}
    source.write_text(json.dumps(value), encoding="utf-8")
    denied = runner.invoke(app, args)
    assert denied.exit_code == 2 and not output.exists()
    assert "SENSITIVE" not in denied.output


def daemonset_report(value: dict[str, Any] | None = None) -> OfflineAssessment:
    fragments = AssessmentFragments.model_validate(daemonset_payload() if value is None else value)
    config = profile()
    config.analysis = AdvisorConfig(packs=[DAEMONSET_PACK])
    return assess_fragments(fragments, config, as_of=AS_OF)


def test_daemonset_overhead_normalization_preserves_current_identity_and_effective_requests() -> (
    None
):
    from aks_fleet_efficiency.scheduling import normalize_scheduling

    metadata = AssessmentFragments.model_validate(daemonset_payload()).kubernetes[0]
    result = normalize_scheduling(metadata)

    assert result.daemonset_overhead_observed
    assert not result.daemonset_overhead_issues
    assert len(result.daemonset_overhead) == 2
    assert {item.cpu_request_mcpu for item in result.daemonset_overhead} == {750.0}
    assert {item.memory_request_mib for item in result.daemonset_overhead} == {352.0}
    assert {item.node_uid for item in result.daemonset_overhead} == {
        "synthetic-node-uid",
        "synthetic-other-node-uid",
    }
    assert all(not item.issues for item in result.daemonset_overhead)
    assert result.resource_accounting_observed
    assert len(result.node_resources) == 2
    assert {item.effective_cpu_request_mcpu for item in result.pods} == {750.0}
    assert {item.effective_memory_request_mib for item in result.pods} == {352.0}
    assert {item.node_uid for item in result.pods} == {
        "synthetic-node-uid",
        "synthetic-other-node-uid",
    }


def test_daemonset_overhead_compares_effective_requests_on_exact_current_nodes() -> None:
    result = daemonset_report()

    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    assert finding.metadata["daemonset_uid"] == "synthetic-daemonset-uid"
    nodes = finding.metadata["nodes"]
    assert {node["cpu_request_mcpu"] for node in nodes} == {750.0}
    assert {node["memory_request_mib"] for node in nodes} == {352.0}
    assert {node["cpu_allocatable_share"] for node in nodes} == {0.375, 0.1875}
    assert {node["memory_allocatable_share"] for node in nodes} == {0.34375, 0.171875}
    from aks_fleet_efficiency.reporting.markdown import render_markdown

    assert "37.5" in render_markdown(result.report)
    assert "percent of current allocatable cpu" in render_markdown(result.report)
    assert finding.proposed_requests is None
    assert finding.proposed_limits is None
    assert finding.estimated_monthly_savings is None
    assert not result.report.blocked_recommendations


def test_daemonset_coverage_preserves_controller_counts_without_inventing_desired_membership() -> (
    None
):
    value = daemonset_payload()
    controller = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "DaemonSet"
    )
    controller["status"] = {"desiredNumberScheduled": 3, "numberReady": 1}
    result = daemonset_report(value)
    coverage = result.snapshot.clusters[0].scheduling.daemonset_coverage[0]
    assert coverage.daemonset_uid == controller["uid"]
    assert coverage.desired_number_scheduled == 3
    assert coverage.number_ready == 1
    assert coverage.observed_nonterminal_pod_count == 2
    assert len(coverage.observed_node_uids) == 2
    assert coverage.desired_minus_observed_nodes == 1
    assert coverage.desired_node_membership == "unknown"
    assert coverage.controller_status_binding == "generation_unverified"
    assert coverage.disruption_feasibility == "unknown"
    assert not coverage.observation_issues
    finding = result.report.recommendations[0]
    assert finding.metadata["coverage"] == coverage.model_dump(mode="json")
    assert finding.estimated_monthly_savings is None
    assert finding.proposed_requests is None


def test_daemonset_coverage_missing_status_does_not_erase_observed_request_shares() -> None:
    value = daemonset_payload()
    next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "DaemonSet")[
        "status"
    ] = {}
    result = daemonset_report(value)
    coverage = result.snapshot.clusters[0].scheduling.daemonset_coverage[0]
    assert coverage.desired_number_scheduled is None
    assert coverage.number_ready is None
    assert coverage.desired_minus_observed_nodes is None
    assert coverage.observed_nonterminal_pod_count == 2
    assert coverage.status_issues == ["desired_count_unknown", "ready_count_unknown"]
    assert len(result.report.recommendations) == 1
    assert not result.report.blocked_recommendations


@pytest.mark.parametrize("count", [None, True, -1, 1.5, "2"])
def test_daemonset_coverage_rejects_malformed_controller_counts_independently(count: Any) -> None:
    from aks_fleet_efficiency.scheduling import normalize_scheduling

    metadata = AssessmentFragments.model_validate(daemonset_payload()).kubernetes[0]
    controller = next(item for item in metadata.resources if item.kind == "DaemonSet")
    controller.status = {"desiredNumberScheduled": count, "numberReady": 0}
    coverage = normalize_scheduling(metadata).daemonset_coverage[0]
    assert coverage.desired_number_scheduled is None
    assert coverage.number_ready == 0
    assert coverage.observed_nonterminal_pod_count == 2
    assert coverage.status_issues == ["desired_count_unknown"]
    assert coverage.desired_minus_observed_nodes is None


@pytest.mark.parametrize("desired", [0, 1, 2, 3])
def test_daemonset_coverage_count_difference_is_signed_and_not_membership(desired: int) -> None:
    from aks_fleet_efficiency.scheduling import normalize_scheduling

    metadata = AssessmentFragments.model_validate(daemonset_payload()).kubernetes[0]
    controller = next(item for item in metadata.resources if item.kind == "DaemonSet")
    controller.status = {"desiredNumberScheduled": desired, "numberReady": 2}
    coverage = normalize_scheduling(metadata).daemonset_coverage[0]
    assert coverage.desired_minus_observed_nodes == desired - 2
    assert coverage.desired_node_membership == "unknown"
    assert coverage.controller_status_binding == "generation_unverified"


@pytest.mark.parametrize("problem", ["partial", "missing-list", "foreign-owner", "unknown-phase"])
def test_daemonset_coverage_incomplete_observation_is_not_zero(problem: str) -> None:
    from aks_fleet_efficiency.models import CollectionStatus
    from aks_fleet_efficiency.scheduling import normalize_scheduling

    metadata = AssessmentFragments.model_validate(daemonset_payload()).kubernetes[0]
    controller = next(item for item in metadata.resources if item.kind == "DaemonSet")
    controller.status = {"desiredNumberScheduled": 2, "numberReady": 1}
    pod = next(item for item in metadata.resources if item.kind == "Pod")
    if problem == "partial":
        metadata.collection.status = CollectionStatus.PARTIAL
    elif problem == "missing-list":
        metadata.resource_versions.pop("v1/pods")
    elif problem == "foreign-owner":
        pod.owner_references[0]["uid"] = "foreign-daemonset"
    else:
        pod.status["phase"] = "Unknown"
    coverage = normalize_scheduling(metadata).daemonset_coverage[0]
    assert coverage.desired_number_scheduled == 2
    assert coverage.number_ready == 1
    assert coverage.observed_nonterminal_pod_count is None
    assert coverage.observed_pod_uids is None
    assert coverage.observed_node_uids is None
    assert coverage.desired_minus_observed_nodes is None
    assert coverage.observation_issues


@pytest.mark.parametrize("problem", ["unassigned", "duplicate-placement", "terminal", "empty"])
def test_daemonset_coverage_keeps_pod_and_node_counts_separate(problem: str) -> None:
    from aks_fleet_efficiency.scheduling import normalize_scheduling

    metadata = AssessmentFragments.model_validate(daemonset_payload()).kubernetes[0]
    controller = next(item for item in metadata.resources if item.kind == "DaemonSet")
    controller.status = {"desiredNumberScheduled": 2, "numberReady": 1}
    pods = [item for item in metadata.resources if item.kind == "Pod"]
    if problem == "unassigned":
        pods[0].spec.pop("nodeName")
        pods[0].status["phase"] = "Pending"
    elif problem == "duplicate-placement":
        pods[1].spec["nodeName"] = pods[0].spec["nodeName"]
    elif problem == "terminal":
        pods[0].status["phase"] = "Succeeded"
    else:
        metadata.resources = [item for item in metadata.resources if item.kind != "Pod"]
    coverage = normalize_scheduling(metadata).daemonset_coverage[0]
    if problem == "unassigned":
        assert coverage.observed_nonterminal_pod_count == 2
        assert coverage.observed_node_uids is None
        assert coverage.desired_minus_observed_nodes is None
        assert "unresolved_daemonset_node" in coverage.observation_issues
    elif problem == "duplicate-placement":
        assert coverage.observed_nonterminal_pod_count == 2
        assert len(coverage.observed_node_uids) == 1
        assert coverage.duplicate_node_uids == coverage.observed_node_uids
        assert "duplicate_daemonset_node_placement" in coverage.observation_issues
    elif problem == "terminal":
        assert coverage.observed_nonterminal_pod_count == 1
        assert coverage.observed_pod_uids == [pods[1].uid]
        assert len(coverage.observed_node_uids) == 1
    else:
        assert coverage.observed_nonterminal_pod_count == 0
        assert coverage.observed_pod_uids == coverage.observed_node_uids == []
        assert coverage.desired_minus_observed_nodes == 2
    assert coverage.desired_node_membership == "unknown"
    assert coverage.disruption_feasibility == "unknown"


def test_daemonset_coverage_order_and_inputs_are_preserved() -> None:
    from aks_fleet_efficiency.scheduling import normalize_scheduling

    metadata = AssessmentFragments.model_validate(daemonset_payload()).kubernetes[0]
    original = metadata.model_dump_json()
    coverage = normalize_scheduling(metadata).daemonset_coverage
    assert metadata.model_dump_json() == original
    metadata.resources.reverse()
    assert normalize_scheduling(metadata).daemonset_coverage == coverage


def test_inventory_summary_counts_selected_subjects_and_scopes_metric_warnings() -> None:
    snapshot = daemonset_report().snapshot
    snapshot.metric_window.coverage_ratio = 0

    report = analyze(snapshot, AdvisorConfig(packs=[DAEMONSET_PACK]), as_of=AS_OF)

    assert report.summary.pack_subject_counts == {DAEMONSET_PACK: 1}
    assert len(report.recommendations) == 1
    assert not report.blocked_recommendations
    assert any(
        warning.startswith("Independent metric context:")
        for warning in report.summary.data_quality_warnings
    )
    from aks_fleet_efficiency.reporting.markdown import render_markdown

    rendered = render_markdown(report)
    assert "AKS-NP-004` subjects evaluated: 1" in rendered
    assert "Snapshot vertical-workload records: 0" in rendered


def test_daemonset_overhead_does_not_invent_zero_requests_when_evidence_is_missing() -> None:
    value = daemonset_payload()
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["spec"]["containers"][0]["resources"]["requests"].pop("cpu")

    result = daemonset_report(value)

    assert not result.report.recommendations
    assert result.report.summary.pack_subject_counts == {DAEMONSET_PACK: 1}
    assert any(
        "unknown_daemonset_requests" in item.reason_codes
        for item in result.report.blocked_recommendations
    )


@pytest.mark.parametrize(
    "problem",
    [
        "missing-overhead",
        "pod-budget",
        "missing-node",
        "zero-capacity",
        "mixed-requests",
        "duplicate-placement",
        "invalid-phase",
        "foreign-owner",
        "missing-api",
        "duplicate-container",
    ],
)
def test_daemonset_overhead_blocks_unsupported_current_evidence(problem: str) -> None:
    value = daemonset_payload()
    metadata = value["kubernetes"][0]
    pods = [item for item in metadata["resources"] if item["kind"] == "Pod"]
    pod = pods[0]
    if problem == "missing-overhead":
        pod["spec"].pop("overhead")
    elif problem == "pod-budget":
        pod["spec"]["resources"] = {"requests": {"cpu": "1"}}
    elif problem == "missing-node":
        pod["spec"]["nodeName"] = "foreign-node"
    elif problem == "zero-capacity":
        next(item for item in metadata["resources"] if item["kind"] == "Node")["status"][
            "allocatable"
        ]["cpu"] = "0"
    elif problem == "mixed-requests":
        pod["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "1000m"
    elif problem == "duplicate-placement":
        pods[1]["spec"]["nodeName"] = pod["spec"]["nodeName"]
    elif problem == "invalid-phase":
        pod["status"]["phase"] = ["Running"]
    elif problem == "foreign-owner":
        pod["owner_references"][0]["uid"] = "foreign-daemonset"
    elif problem == "missing-api":
        metadata["resource_versions"].pop("apps/v1/daemonsets")
    else:
        pod["spec"]["containers"].append(json.loads(json.dumps(pod["spec"]["containers"][0])))

    result = daemonset_report(value)

    assert not result.report.recommendations
    assert result.report.blocked_recommendations


@pytest.mark.parametrize("problem", ["homogeneous", "zero-requests", "terminal"])
def test_daemonset_overhead_emits_no_difference_for_supported_negative_cases(problem: str) -> None:
    value = daemonset_payload()
    for item in value["kubernetes"][0]["resources"]:
        if problem == "homogeneous" and item["kind"] == "Node":
            item["status"]["allocatable"] = {"cpu": "2", "memory": "1024Mi"}
        elif item["kind"] == "Pod":
            if problem == "terminal":
                item["status"]["phase"] = "Succeeded"
            elif problem == "zero-requests":
                for container in item["spec"]["containers"] + item["spec"]["initContainers"]:
                    container["resources"]["requests"] = {"cpu": "0", "memory": "0"}
                item["spec"]["overhead"] = {}

    result = daemonset_report(value)

    assert not result.report.recommendations
    assert not result.report.blocked_recommendations


@pytest.mark.parametrize("problem", ["stale", "future", "partial", "identity"])
def test_daemonset_overhead_requires_fresh_complete_exact_scoped_evidence(problem: str) -> None:
    result = daemonset_report()
    snapshot = result.snapshot
    if problem == "stale":
        snapshot.clusters[0].scheduling.observed_at = AS_OF - timedelta(hours=25)
    elif problem == "future":
        snapshot.clusters[0].scheduling.observed_at = AS_OF + timedelta(seconds=1)
    elif problem == "identity":
        snapshot.clusters[0].scheduling.cluster_uid = "foreign-fingerprint"
    else:
        from aks_fleet_efficiency.models import CollectionStatus

        receipt = next(
            item
            for item in snapshot.collection_manifest.source_results
            if item.collector == "kubernetes-metadata"
        )
        receipt.status = CollectionStatus.PARTIAL

    report = analyze(snapshot, AdvisorConfig(packs=[DAEMONSET_PACK]), as_of=AS_OF)

    assert not report.recommendations
    assert report.blocked_recommendations


def test_daemonset_overhead_ignores_metric_coverage_and_passes_freshness_equality() -> None:
    snapshot = daemonset_report().snapshot
    snapshot.metric_window.coverage_ratio = 0
    times = [
        item.source_observed_at
        for item in snapshot.collection_manifest.source_results
        if item.source_observed_at is not None
    ]
    config = AdvisorConfig(packs=[DAEMONSET_PACK], mode="guarded")

    report = analyze(snapshot, config, as_of=min(times) + timedelta(hours=24))

    assert len(report.recommendations) == 1
    assert not report.blocked_recommendations
    assert report.recommendations[0].proposed_requests is None


def test_daemonset_overhead_respects_excluded_namespaces() -> None:
    snapshot = daemonset_report().snapshot
    namespace = snapshot.clusters[0].scheduling.daemonset_overhead[0].namespace

    report = analyze(
        snapshot,
        AdvisorConfig(packs=[DAEMONSET_PACK], excluded_namespaces=[namespace]),
        as_of=AS_OF,
    )

    assert not report.recommendations
    assert not report.blocked_recommendations
    assert report.summary.pack_subject_counts == {DAEMONSET_PACK: 0}


def test_daemonset_overhead_keeps_an_independent_healthy_daemonset() -> None:
    snapshot = daemonset_report().snapshot
    inventory = snapshot.clusters[0].scheduling
    other = inventory.daemonset_overhead[0].model_copy(deep=True)
    other.daemonset_uid = "other-daemonset-uid"
    other.daemonset_name = "other-daemonset"
    other.pod_uid = "other-pod-uid"
    other.cpu_request_mcpu = None
    other.issues = ["unknown_daemonset_requests"]
    inventory.daemonset_uids.append(other.daemonset_uid)
    inventory.daemonset_overhead.append(other)

    report = analyze(snapshot, AdvisorConfig(packs=[DAEMONSET_PACK]), as_of=AS_OF)

    assert len(report.recommendations) == 1
    assert report.recommendations[0].metadata["daemonset_uid"] == "synthetic-daemonset-uid"
    assert len(report.blocked_recommendations) == 1


def test_daemonset_overhead_is_not_applicable_to_known_non_daemonset_pods() -> None:
    result = daemonset_report(payload())

    assert not result.report.recommendations
    assert not result.report.blocked_recommendations


def capacity_report(value: dict[str, Any] | None = None) -> OfflineAssessment:
    fragments = AssessmentFragments.model_validate(payload() if value is None else value)
    config = profile()
    config.analysis = AdvisorConfig(packs=[PACK])
    return assess_fragments(fragments, config, as_of=AS_OF)


@pytest.mark.parametrize("enabled, expected", [(True, "cas"), (False, "fixed"), (None, "unknown")])
def test_current_capacity_classification_is_independent_of_metrics(
    enabled: bool | None, expected: str
) -> None:
    value = payload()
    value["metrics"] = []
    pool = value["azure"][0]["clusters"][0]["node_pools"][0]
    pool["autoscaling_enabled"] = enabled
    result = capacity_report(value)
    assert not result.snapshot.clusters[0].node_pools
    finding = result.report.recommendations[0]
    assert finding.metadata["pools"][0]["management"] == expected
    assert finding.metadata["pools"][0]["resource_id"] == pool["resource_id"]
    assert finding.metadata["pools"][0]["intent"] == "unknown"
    assert finding.metadata["nap_prerequisites"]["network"] == "unknown"
    assert finding.metadata["nap_prerequisites"]["identity"] == "unknown"
    assert finding.proposed_requests is None
    assert finding.proposed_limits is None
    assert finding.proposed_replica_floor is None
    assert finding.estimated_monthly_savings is None


@pytest.mark.parametrize("pack_id", [PACK, "AKS-SCHED-001"])
@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_current_investigations_do_not_claim_history_from_low_coverage(
    pack_id: str, mode: str
) -> None:
    from test_rules_scheduling import scheduling_fragments

    fragments = scheduling_fragments()
    for source in fragments.metrics:
        for item in source.observations:
            item.quality.window.coverage_ratio = 0.1
    config = profile()
    config.analysis = AdvisorConfig(packs=[pack_id], mode=mode)
    result = assess_fragments(fragments, config, as_of=AS_OF)
    assert len(result.report.recommendations) == 1
    assert result.report.recommendations[0].estimated_monthly_savings is None


def test_equal_cas_bounds_are_not_owner_intent_or_a_safe_lower_minimum() -> None:
    value = payload()
    pool = value["azure"][0]["clusters"][0]["node_pools"][0]
    pool.update(autoscaling_enabled=True, min_count=3, max_count=3)
    finding = capacity_report(value).report.recommendations[0]
    assert finding.metadata["pools"][0]["fixed_bounds"] is True
    assert finding.metadata["pools"][0]["intent"] == "unknown"
    assert finding.metadata["nap_prerequisites"]["cas_transition"] == "review_required"


@pytest.mark.parametrize("role, spot, os_type", [("System", True, "Windows"), (None, None, None)])
def test_capacity_does_not_invent_pool_role_market_or_os(
    role: str | None, spot: bool | None, os_type: str | None
) -> None:
    value = payload()
    value["azure"][0]["clusters"][0]["node_pools"][0].update(mode=role, spot=spot, os_type=os_type)
    finding = capacity_report(value).report.recommendations[0]
    pool = finding.metadata["pools"][0]
    assert pool["role"] == (role or "unknown")
    assert pool["spot"] == spot
    assert pool["os_type"] == os_type
    assert finding.metadata["nap_prerequisites"]["windows"] == (
        "unsupported" if os_type == "Windows" else "unknown"
    )


def test_nap_auto_mode_does_not_relabel_existing_arm_pools_as_nap_managed() -> None:
    value = payload()
    value["azure"][0]["clusters"][0]["node_provisioning_mode"] = "Auto"
    finding = capacity_report(value).report.recommendations[0]
    assert finding.metadata["provisioning_mode"] == "Auto"
    assert finding.metadata["pools"][0]["management"] != "nap"
    assert finding.metadata["nap_api_status"]["karpenter.sh/v1/nodepools"] == "unknown"
    assert finding.metadata["nap_managed_nodes"] == []


def test_pool_intent_is_an_exact_bound_owner_declaration_not_approval() -> None:
    value = payload()
    cluster = value["azure"][0]["clusters"][0]
    value["pool_intents"] = [
        {
            "cluster_resource_id": cluster["resource_id"],
            "pool_resource_id": cluster["node_pools"][0]["resource_id"],
            "owner": "synthetic-owner",
            "classification": "intentionally-reserved",
            "reference": "synthetic-review/resilience",
        }
    ]
    finding = capacity_report(value).report.recommendations[0]
    assert finding.metadata["pools"][0]["intent"] == "intentionally-reserved"
    assert finding.metadata["pools"][0]["intent_is_approval"] is False
    value["pool_intents"][0]["pool_resource_id"] += "-foreign"
    with pytest.raises(ValueError, match="pool intent"):
        capacity_report(value)


@pytest.mark.parametrize("field", ["reference", "owner"])
def test_pool_intent_rejects_empty_declarations(field: str) -> None:
    value = payload()
    cluster = value["azure"][0]["clusters"][0]
    value["pool_intents"] = [
        {
            "cluster_resource_id": cluster["resource_id"],
            "pool_resource_id": cluster["node_pools"][0]["resource_id"],
            "owner": "synthetic-owner",
            "classification": "specialized",
            "reference": "synthetic-review/hardware",
        }
    ]
    value["pool_intents"][0][field] = " "
    with pytest.raises(ValueError):
        capacity_report(value)


def test_native_capacity_missing_evidence_is_blocked() -> None:
    result = analyze(eligible_snapshot(), AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert result.blocked_recommendations[0].reason_codes == ["missing_capacity_inventory"]


def test_missing_current_supply_is_not_a_healthy_capacity_review() -> None:
    result = capacity_report()
    result.snapshot.clusters[0].capacity.pools.clear()
    report = analyze(result.snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert "missing_capacity_supply" in report.blocked_recommendations[0].reason_codes


@pytest.mark.parametrize("problem", ["stale", "future", "identity", "partial"])
def test_current_capacity_keeps_scope_freshness_and_receipt_gates(problem: str) -> None:
    result = capacity_report()
    snapshot = result.snapshot
    context = snapshot.clusters[0].capacity
    if problem == "stale":
        context.azure_observed_at = AS_OF - timedelta(hours=25)
    elif problem == "future":
        context.azure_observed_at = AS_OF + timedelta(seconds=1)
    elif problem == "identity":
        context.cluster_resource_id += "-foreign"
    else:
        from aks_fleet_efficiency.models import CollectionStatus

        receipt = next(
            item
            for item in snapshot.collection_manifest.source_results
            if item.collector == "azure-inventory"
        )
        receipt.status = CollectionStatus.PARTIAL
    report = analyze(snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations


def nap_payload() -> dict[str, Any]:
    value = payload()
    value["azure"][0]["clusters"][0]["node_provisioning_mode"] = "Auto"
    metadata = value["kubernetes"][0]
    for key in [
        "karpenter.sh/v1/nodepools",
        "karpenter.sh/v1/nodeclaims",
        "karpenter.azure.com/v1beta1/aksnodeclasses",
    ]:
        metadata["api_availability"][key] = "available"
        metadata["resource_versions"][key] = "synthetic-version"
    provider = "azure://" + metadata["nodes"][0]["azure_resource_id"]
    metadata["nodes"][0]["provider_id"] = provider
    metadata["nodes"][0]["node_pool_resource_id"] = None
    metadata["nodes"][0]["state"] = "unknown"
    node = next(item for item in metadata["resources"] if item["kind"] == "Node")
    node["spec"] = {"providerID": provider}
    for pod in metadata["resources"]:
        if pod["kind"] == "Pod":
            pod["spec"]["nodeName"] = node["name"]
    metadata["resources"].extend(
        [
            {
                "api_version": "karpenter.sh/v1",
                "kind": "NodePool",
                "uid": "synthetic-nap-pool-uid",
                "name": "synthetic-nap",
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "nodeClassRef": {
                                "group": "karpenter.azure.com",
                                "kind": "AKSNodeClass",
                                "name": "synthetic-class",
                            },
                            "requirements": [
                                {
                                    "key": "node.kubernetes.io/instance-type",
                                    "operator": "In",
                                    "values": ["synthetic-sku"],
                                }
                            ],
                            "taints": [],
                            "startupTaints": [{"key": "synthetic-startup", "effect": "NoSchedule"}],
                        }
                    },
                    "limits": {"cpu": "100"},
                    "disruption": {
                        "consolidationPolicy": "WhenEmpty",
                        "consolidateAfter": "30s",
                        "budgets": [{"nodes": "0"}],
                    },
                },
            },
            {
                "api_version": "karpenter.azure.com/v1beta1",
                "kind": "AKSNodeClass",
                "uid": "synthetic-class-uid",
                "name": "synthetic-class",
            },
            {
                "api_version": "karpenter.sh/v1",
                "kind": "NodeClaim",
                "uid": "synthetic-claim-uid",
                "name": "synthetic-claim",
                "owner_references": [
                    {
                        "apiVersion": "karpenter.sh/v1",
                        "kind": "NodePool",
                        "name": "synthetic-nap",
                        "uid": "synthetic-nap-pool-uid",
                        "controller": True,
                    }
                ],
                "status": {"providerID": provider, "nodeName": node["name"]},
            },
        ]
    )
    return value


def consolidation_report(
    value: dict[str, Any] | None = None,
    *,
    mode: str = "baseline",
    excluded_namespaces: list[str] | None = None,
) -> OfflineAssessment:
    fragments = AssessmentFragments.model_validate(nap_payload() if value is None else value)
    config = profile()
    config.analysis = AdvisorConfig(
        packs=[CONSOLIDATION_PACK],
        mode=mode,
        excluded_namespaces=excluded_namespaces or ["kube-system", "gatekeeper-system"],
    )
    return assess_fragments(fragments, config, as_of=AS_OF)


def test_nap_topology_preserves_declared_zones_and_exact_current_bound_observations() -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    pool = next(item for item in metadata["resources"] if item["kind"] == "NodePool")
    pool["spec"]["template"]["spec"]["requirements"].append(
        {
            "key": "topology.kubernetes.io/zone",
            "operator": "In",
            "values": ["synthetic-zone-b", "synthetic-zone-a"],
            "minValues": 2,
        }
    )
    node = next(item for item in metadata["resources"] if item["kind"] == "Node")
    node.setdefault("labels", {})["topology.kubernetes.io/zone"] = "synthetic-zone-a"
    result = consolidation_report(value)
    topology = result.snapshot.clusters[0].capacity.nap_pools[0].topology
    assert topology.zone_requirements[0].operator == "In"
    assert topology.zone_requirements[0].values == ["synthetic-zone-a", "synthetic-zone-b"]
    assert topology.zone_requirements[0].min_values == 2
    assert topology.observed_zone_nodes == {"synthetic-zone-a": [node["uid"]]}
    assert topology.unknown_zone_node_uids == []
    assert topology.observation_status == "current-bound-only"
    assert topology.domain_effectiveness == "not_calculated"
    assert topology.placement_feasibility == "unknown"
    assert result.report.recommendations[0].metadata["topology"] == topology.model_dump(mode="json")


def test_nap_topology_missing_zone_labels_are_unknown_not_absent_domains() -> None:
    value = nap_payload()
    node = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Node")
    node.setdefault("labels", {}).pop("topology.kubernetes.io/zone", None)
    result = consolidation_report(value)
    topology = result.snapshot.clusters[0].capacity.nap_pools[0].topology
    assert topology.observed_zone_nodes == {}
    assert topology.unknown_zone_node_uids == [node["uid"]]
    assert topology.placement_feasibility == "unknown"
    evidence = {item.metric: item.value for item in result.report.recommendations[0].evidence}
    assert evidence["nap_observed_zone_count"] is None
    assert evidence["nap_unknown_zone_node_count"] == 1
    assert result.report.recommendations[0].estimated_monthly_savings is None


@pytest.mark.parametrize(
    ("operator", "values", "minimum", "expected"),
    [
        ("In", ["synthetic-zone"], None, "observed"),
        ("NotIn", ["synthetic-zone"], None, "observed"),
        ("Exists", [], None, "observed"),
        ("DoesNotExist", [], None, "observed"),
        ("Gt", ["2"], None, "unknown"),
        ("In", [], None, "unknown"),
        ("Exists", ["synthetic-zone"], None, "unknown"),
        ("In", ["synthetic-zone", "synthetic-zone"], None, "unknown"),
        ("In", ["SENSITIVE-INVALID\nZONE"], None, "unknown"),
        ("In", [{"SENSITIVE-UNEXPECTED": "VALUE"}], None, "unknown"),
        ("In", "synthetic-zone", None, "unknown"),
        ("In", ["synthetic-zone"], True, "unknown"),
        ("In", ["synthetic-zone"], 0, "unknown"),
        ("NotIn", ["synthetic-zone"], 2, "unknown"),
    ],
)
def test_nap_topology_requirement_shapes_are_explicit_and_never_grant_feasibility(
    operator: str,
    values: Any,
    minimum: Any,
    expected: str,
) -> None:
    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    pool["spec"]["template"]["spec"]["requirements"] = [
        {
            "key": "topology.kubernetes.io/zone",
            "operator": operator,
            "values": values,
            "minValues": minimum,
        }
    ]
    if isinstance(values, list) and any(isinstance(item, dict) for item in values):
        from aks_fleet_efficiency.collectors.kubernetes_metadata import KubernetesReadError

        with pytest.raises(KubernetesReadError, match="invalid-response"):
            consolidation_report(value)
        return
    result = consolidation_report(value)
    topology = result.snapshot.clusters[0].capacity.nap_pools[0].topology
    assert topology.requirement_status == expected
    assert bool(topology.requirement_issues) == (expected == "unknown")
    assert (topology.zone_requirements is None) == (expected == "unknown")
    assert topology.domain_effectiveness == "not_calculated"
    assert topology.placement_feasibility == "unknown"
    assert "SENSITIVE-" not in str(result.report.recommendations[0].metadata["topology"])


@pytest.mark.parametrize("shape", ["missing", "empty", "partial", "malformed"])
def test_nap_topology_preserves_independent_requirement_quality(shape: str) -> None:
    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    spec = pool["spec"]["template"]["spec"]
    if shape == "missing":
        spec.pop("requirements")
    elif shape == "empty":
        spec["requirements"] = []
    elif shape == "malformed":
        spec["requirements"] = [{"operator": "In", "values": ["SENSITIVE-UNKNOWN-KEY"]}]
    else:
        spec["requirements"] = [
            {"key": "topology.kubernetes.io/zone", "operator": "In", "values": ["synthetic-zone"]},
            {"key": "topology.kubernetes.io/zone", "operator": "Unsupported", "values": []},
        ]
    result = consolidation_report(value)
    context = result.snapshot.clusters[0].capacity.nap_pools[0].topology
    assert context.requirement_status == (
        "partial" if shape == "partial" else "observed" if shape == "empty" else "unknown"
    )
    if shape == "partial":
        assert len(context.zone_requirements) == 1
    elif shape == "empty":
        assert context.zone_requirements == []
    else:
        assert context.zone_requirements is None
    assert result.report.recommendations[0].metadata["consolidation_policy"] == "WhenEmpty"


@pytest.mark.parametrize(
    "problem",
    ["partial", "missing-node-list", "missing-claim-list", "foreign-owner", "duplicate-claim"],
)
def test_nap_topology_incomplete_observation_is_unknown_not_empty_supply(problem: str) -> None:
    from aks_fleet_efficiency.capacity import normalize_capacity

    value = nap_payload()
    metadata = value["kubernetes"][0]
    if problem == "partial":
        metadata["collection"]["status"] = "partial"
        metadata["collection"]["missing_fields"] = ["synthetic-incomplete-list"]
    elif problem == "missing-node-list":
        metadata["resource_versions"].pop("v1/nodes")
    elif problem == "missing-claim-list":
        metadata["resource_versions"].pop("karpenter.sh/v1/nodeclaims")
    else:
        claim = next(item for item in metadata["resources"] if item["kind"] == "NodeClaim")
        if problem == "foreign-owner":
            claim["owner_references"][0]["uid"] = "foreign-pool-uid"
        else:
            other = json.loads(json.dumps(claim))
            other.update(uid="synthetic-other-claim-uid", name="synthetic-other-claim")
            metadata["resources"].append(other)
    fragments = AssessmentFragments.model_validate(value)
    result = normalize_capacity(
        fragments.azure[0].clusters[0], fragments.azure[0].generated_at, fragments.kubernetes[0], []
    )
    context = result.nap_pools[0].topology
    assert context.observation_status == "unknown"
    assert context.observed_zone_nodes is None
    assert context.unknown_zone_node_uids is None
    assert context.observation_issues


def test_nap_topology_does_not_inherit_unrelated_pool_nodes_or_labels() -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    node = next(item for item in metadata["resources"] if item["kind"] == "Node")
    node.setdefault("labels", {})["topology.kubernetes.io/zone"] = "synthetic-zone"
    pool = next(item for item in metadata["resources"] if item["kind"] == "NodePool")
    other = json.loads(json.dumps(pool))
    other.update(uid="synthetic-unrelated-pool-uid", name="synthetic-unrelated-pool")
    metadata["resources"].append(other)
    result = consolidation_report(value)
    contexts = {item.uid: item.topology for item in result.snapshot.clusters[0].capacity.nap_pools}
    assert contexts[pool["uid"]].observed_zone_nodes == {"synthetic-zone": [node["uid"]]}
    assert contexts[other["uid"]].observed_zone_nodes == {}
    assert contexts[other["uid"]].unknown_zone_node_uids == []


@pytest.mark.parametrize("budget", ["requirements", "values"])
def test_nap_topology_exceeded_budgets_are_withheld_without_truncation(
    budget: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import capacity as module

    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    requirement = {
        "key": "topology.kubernetes.io/zone",
        "operator": "In",
        "values": ["synthetic-zone"],
    }
    if budget == "requirements":
        monkeypatch.setattr(module, "MAXIMUM_NAP_REQUIREMENTS", 1)
        pool["spec"]["template"]["spec"]["requirements"] = [requirement, requirement]
        issue = "nap_requirement_budget_exceeded"
    else:
        monkeypatch.setattr(module, "MAXIMUM_NAP_ZONE_VALUES", 1)
        requirement["values"] = ["synthetic-zone-a", "synthetic-zone-b"]
        pool["spec"]["template"]["spec"]["requirements"] = [requirement]
        issue = "nap_zone_value_budget_exceeded"
    result = consolidation_report(value)
    context = result.snapshot.clusters[0].capacity.nap_pools[0].topology
    assert context.zone_requirements is None and context.requirement_status == "unknown"
    assert context.requirement_issues == [issue]
    assert result.report.recommendations[0].metadata["consolidation_policy"] == "WhenEmpty"


def test_nap_topology_budget_equality_and_input_order_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aks_fleet_efficiency import capacity as module

    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    pool["spec"]["template"]["spec"]["requirements"] = [
        {
            "key": "topology.kubernetes.io/zone",
            "operator": "In",
            "values": ["synthetic-zone-b", "synthetic-zone-a"],
        },
    ]
    monkeypatch.setattr(module, "MAXIMUM_NAP_REQUIREMENTS", 1)
    monkeypatch.setattr(module, "MAXIMUM_NAP_ZONE_VALUES", 2)
    original = json.dumps(value, sort_keys=True)
    first = consolidation_report(value).snapshot.clusters[0].capacity.nap_pools[0].topology
    assert first.requirement_status == "observed" and not first.requirement_issues
    assert json.dumps(value, sort_keys=True) == original
    value["kubernetes"][0]["resources"].reverse()
    pool["spec"]["template"]["spec"]["requirements"][0]["values"].reverse()
    second = consolidation_report(value).snapshot.clusters[0].capacity.nap_pools[0].topology
    assert second == first


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_nap_topology_does_not_change_freshness_or_numeric_boundaries(mode: str) -> None:
    from aks_fleet_efficiency.reporting.markdown import render_markdown

    result = consolidation_report(mode=mode)
    config = AdvisorConfig(packs=[CONSOLIDATION_PACK], mode=mode)
    finding = result.report.recommendations[0]
    assert "nap_observed_zone_count" in render_markdown(result.report)
    assert finding.proposed_requests is None and finding.proposed_limits is None
    assert finding.estimated_monthly_savings is None
    result.snapshot.clusters[0].capacity.kubernetes_observed_at = AS_OF - timedelta(hours=25)
    report = analyze(result.snapshot, config, as_of=AS_OF)
    assert not report.recommendations
    assert report.blocked_recommendations


def test_nap_topology_original_artifacts_replay_with_locked_pack_and_unchanged_files(
    tmp_path: Path,
) -> None:
    from aks_fleet_efficiency.artifacts import write_assessment_artifacts
    from aks_fleet_efficiency.history import _read_verified_archive

    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    pool["spec"]["template"]["spec"]["requirements"].append(
        {
            "key": "topology.kubernetes.io/zone",
            "operator": "In",
            "values": ["synthetic-zone"],
        }
    )
    fragments = AssessmentFragments.model_validate(value)
    configuration = profile()
    configuration.analysis = AdvisorConfig(packs=[CONSOLIDATION_PACK])
    assessment = assess_fragments(fragments, configuration, as_of=AS_OF)
    directory = tmp_path / "original"
    write_assessment_artifacts(directory, fragments, assessment, configuration.analysis)
    original = {item.name: item.read_bytes() for item in directory.iterdir()}
    _, replayed, locked = _read_verified_archive(directory, tenant_id=configuration.scope.tenant_id)
    assert replayed == assessment
    assert locked.pack_locks == {CONSOLIDATION_PACK: assessment.report.pack_provenance[0].digest}
    assert assessment.report.pack_provenance[0].version == "1.0.0"
    assert (
        replayed.report.recommendations[0].metadata["topology"]["placement_feasibility"]
        == "unknown"
    )
    assert {item.name: item.read_bytes() for item in directory.iterdir()} == original


@pytest.mark.parametrize("problem", ["none", "unknown-reason", "missing-duration"])
def test_nap_budget_review_preserves_reason_schedule_context_without_activation_claim(
    problem: str,
) -> None:
    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    budget = {
        "nodes": "0",
        "reasons": ["Underutilized"],
        "schedule": "0 9 * * mon-fri",
        "duration": "8h",
    }
    if problem == "unknown-reason":
        budget["reasons"] = ["SENSITIVE-UNSUPPORTED-REASON"]
    elif problem == "missing-duration":
        budget.pop("duration")
    pool["spec"]["disruption"]["budgets"] = [budget]
    result = consolidation_report(value)
    detail = result.snapshot.clusters[0].capacity.nap_pools[0].disruption_budgets[0]
    assert detail.nodes == "0" and detail.schedule == "0 9 * * mon-fri"
    assert detail.active == "unknown" and detail.effectiveness == "not_calculated"
    assert bool(detail.issues) == (problem != "none")
    if problem == "none":
        assert detail.reasons == ["Underutilized"] and detail.duration == "8h"
    elif problem == "unknown-reason":
        assert detail.reasons is None
    exported = result.report.recommendations[0].metadata["disruption_budget_configuration"]
    assert exported[0]["active"] == "unknown"
    assert "SENSITIVE-UNSUPPORTED-REASON" not in str(exported)
    assert result.report.recommendations[0].estimated_monthly_savings is None


@pytest.mark.parametrize(
    ("nodes", "valid"),
    [("0%", True), ("100%", True), ("101%", False), ("-1", False), ("1.5", False)],
)
def test_nap_budget_context_preserves_literal_node_boundaries_without_effectiveness(
    nodes: str, valid: bool
) -> None:
    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    pool["spec"]["disruption"]["budgets"] = [{"nodes": nodes, "reasons": ["Empty"]}]
    result = consolidation_report(value)
    budget = result.snapshot.clusters[0].capacity.nap_pools[0].disruption_budgets[0]
    assert budget.nodes == (nodes if valid else None)
    assert ("invalid_budget_nodes" in budget.issues) == (not valid)
    assert budget.active == "unknown" and budget.effectiveness == "not_calculated"
    payload = budget.model_dump(mode="json")
    payload["active"] = True
    with pytest.raises(ValueError):
        type(budget).model_validate(payload)


def test_nap_budget_context_does_not_invent_omitted_reasons_or_copy_malformed_duration() -> None:
    value = nap_payload()
    pool = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool")
    pool["spec"]["disruption"]["budgets"] = [{"nodes": "0", "duration": 8, "schedule": "0 0 * * *"}]
    result = consolidation_report(value)
    budget = result.snapshot.clusters[0].capacity.nap_pools[0].disruption_budgets[0]
    assert budget.reasons is None and budget.duration is None
    assert set(budget.issues) == {
        "unknown_budget_reasons",
        "invalid_budget_duration",
        "unpaired_budget_schedule_duration",
    }


def test_nap_consolidation_readiness_reports_exact_policy_blockers_without_removal_claim() -> None:
    result = consolidation_report()

    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    assert finding.metadata["nodepool_uid"] == "synthetic-nap-pool-uid"
    assert finding.metadata["blockers"] == [
        "consolidation_policy_when_empty",
        "zero_node_disruption_budget",
    ]
    assert finding.metadata["pdb_matching"] == "unknown"
    assert finding.metadata["daemonset_overhead"] == "not_calculated"
    assert "removable" in finding.summary
    assert finding.proposed_requests is None
    assert finding.proposed_limits is None
    assert finding.proposed_replica_floor is None
    assert finding.estimated_monthly_savings is None


@pytest.mark.parametrize("mode", ["baseline", "guarded"])
def test_nap_consolidation_readiness_emits_nothing_for_observed_policy_without_blockers(
    mode: str,
) -> None:
    value = nap_payload()
    nodepool = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool"
    )
    nodepool["spec"]["disruption"].update(
        consolidationPolicy="WhenEmptyOrUnderutilized",
        budgets=[{"nodes": "10%"}],
    )

    result = consolidation_report(value, mode=mode)

    assert not result.report.recommendations
    assert not result.report.blocked_recommendations


def test_nap_consolidation_readiness_correlates_placement_storage_and_pdb_context() -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    nodepool = next(item for item in metadata["resources"] if item["kind"] == "NodePool")
    nodepool["spec"]["disruption"].update(
        consolidationPolicy="WhenEmptyOrUnderutilized",
        budgets=[{"nodes": "10%"}],
    )
    pod = next(item for item in metadata["resources"] if item["kind"] == "Pod")
    pod["spec"].update(
        nodeSelector={"synthetic.example/pool": "special"},
        volumes=[{"name": "scratch", "emptyDir": {}}],
    )
    metadata["resources"].append(
        {
            "api_version": "policy/v1",
            "kind": "PodDisruptionBudget",
            "name": "synthetic-pdb",
            "namespace": "synthetic",
            "uid": "synthetic-pdb-uid",
            "spec": {"maxUnavailable": 1},
            "status": {"disruptionsAllowed": 0, "expectedPods": 1},
        }
    )

    finding = consolidation_report(value).report.recommendations[0]

    assert finding.metadata["blockers"] == [
        "hard_placement_constraints",
        "local_storage_context",
        "namespace_pdb_zero_disruptions",
    ]
    assert finding.metadata["pdb_matching"] == "unknown"
    assert finding.metadata["local_storage_pods"] == 1


def test_nap_constraints_are_not_copied_to_unrelated_nodepools() -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    pool = next(item for item in metadata["resources"] if item["kind"] == "NodePool")
    pool["spec"]["disruption"].update(
        consolidationPolicy="WhenEmptyOrUnderutilized", budgets=[{"nodes": "10%"}]
    )
    other = json.loads(json.dumps(pool))
    other.update(uid="other-pool-uid", name="other-pool")
    metadata["resources"].append(other)
    pod = next(item for item in metadata["resources"] if item["kind"] == "Pod")
    pod["spec"]["nodeName"] = next(
        item["name"] for item in metadata["resources"] if item["kind"] == "Node"
    )
    pod["spec"]["nodeSelector"] = {"synthetic.example/role": "restricted"}

    report = consolidation_report(value).report

    assert len(report.recommendations) == 1
    assert report.recommendations[0].metadata["nodepool_uid"] == "synthetic-nap-pool-uid"
    assert report.recommendations[0].metadata["pod_attribution"] == "current-nodeclaim-bound"
    assert not report.blocked_recommendations


def test_nap_unknown_attribution_preserves_independent_policy_finding() -> None:
    value = nap_payload()
    value["kubernetes"][0]["resource_versions"].pop("karpenter.sh/v1/nodeclaims")
    value["kubernetes"][0]["resources"] = [
        item for item in value["kubernetes"][0]["resources"] if item["kind"] != "NodeClaim"
    ]

    report = consolidation_report(value).report

    assert len(report.recommendations) == 1
    assert report.recommendations[0].metadata["hard_placement_pods"] is None
    assert report.recommendations[0].metadata["pod_attribution"] == "unknown"
    assert any(
        "nap_pod_attribution_unknown" in item.reason_codes
        for item in report.blocked_recommendations
    )


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("consolidationPolicy", "missing_nap_consolidation_policy"),
        ("budgets", "missing_nap_disruption_budget"),
    ],
)
def test_nap_consolidation_readiness_blocks_missing_nodepool_policy(
    field: str, reason: str
) -> None:
    value = nap_payload()
    nodepool = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool"
    )
    nodepool["spec"]["disruption"].pop(field)

    result = consolidation_report(value)

    assert not result.report.recommendations
    assert reason in result.report.blocked_recommendations[0].reason_codes


def test_nap_consolidation_readiness_blocks_unavailable_nodepool_inventory() -> None:
    value = nap_payload()
    value["kubernetes"][0]["resource_versions"].pop("karpenter.sh/v1/nodepools")

    result = consolidation_report(value)

    assert not result.report.recommendations
    assert result.report.blocked_recommendations[0].reason_codes == [
        "nap_nodepool_inventory_unavailable"
    ]


@pytest.mark.parametrize("pdb_list_observed", [True, False])
def test_nap_consolidation_readiness_is_not_applicable_without_observed_nap(
    pdb_list_observed: bool,
) -> None:
    value = payload()
    if not pdb_list_observed:
        value["kubernetes"][0]["resource_versions"].pop("policy/v1/poddisruptionbudgets")
    result = consolidation_report(value)

    assert result.snapshot.clusters[0].capacity.provisioning_mode != "Auto"
    assert not result.snapshot.clusters[0].capacity.nap_pools
    assert not result.report.recommendations
    assert not result.report.blocked_recommendations


def test_nap_consolidation_readiness_surfaces_missing_pdb_status() -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    nodepool = next(item for item in metadata["resources"] if item["kind"] == "NodePool")
    nodepool["spec"]["disruption"].update(
        consolidationPolicy="WhenEmptyOrUnderutilized", budgets=[{"nodes": "10%"}]
    )
    metadata["resources"].append(
        {
            "api_version": "policy/v1",
            "kind": "PodDisruptionBudget",
            "name": "synthetic-pdb",
            "namespace": "synthetic",
            "uid": "synthetic-pdb-uid",
            "spec": {"minAvailable": 1},
            "status": {},
        }
    )

    result = consolidation_report(value)

    assert len(result.report.recommendations) == 1
    finding = result.report.recommendations[0]
    assert finding.metadata["blockers"] == ["pdb_availability_unknown"]
    assert finding.metadata["namespace_pdbs_with_availability_issues"] == 1


def test_nap_consolidation_readiness_preserves_policy_when_pdb_inventory_is_unknown() -> None:
    value = nap_payload()
    value["kubernetes"][0]["resource_versions"].pop("policy/v1/poddisruptionbudgets")

    result = consolidation_report(value)

    assert len(result.report.recommendations) == 1
    assert result.report.recommendations[0].metadata["namespace_pdbs_with_zero_disruptions"] is None
    assert any(
        "incomplete_pdb_inventory" in finding.reason_codes
        for finding in result.report.blocked_recommendations
    )


def test_nap_consolidation_readiness_isolates_invalid_pool_configuration() -> None:
    value = nap_payload()
    nodepool = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool"
    )
    other = json.loads(json.dumps(nodepool))
    other.update(name="other-synthetic-pool", uid="other-synthetic-pool-uid")
    other["spec"]["replicas"] = "invalid"
    value["kubernetes"][0]["resources"].append(other)

    result = consolidation_report(value)

    assert len(result.report.recommendations) == 1
    assert result.report.recommendations[0].metadata["nodepool_uid"] == nodepool["uid"]
    assert len(result.report.blocked_recommendations) == 1
    assert result.report.blocked_recommendations[0].reason_codes == ["invalid_nap_static_replicas"]


@pytest.mark.parametrize("problem", ["stale", "future", "partial", "missing-scheduling"])
def test_nap_consolidation_readiness_blocks_untrusted_current_evidence(problem: str) -> None:
    result = consolidation_report()
    snapshot = result.snapshot
    if problem == "stale":
        snapshot.clusters[0].capacity.kubernetes_observed_at = AS_OF - timedelta(hours=25)
    elif problem == "future":
        snapshot.clusters[0].scheduling.observed_at = AS_OF + timedelta(seconds=1)
    elif problem == "partial":
        from aks_fleet_efficiency.models import CollectionStatus

        receipt = next(
            item
            for item in snapshot.collection_manifest.source_results
            if item.collector == "kubernetes-metadata"
        )
        receipt.status = CollectionStatus.PARTIAL
    else:
        snapshot.clusters[0].scheduling = None

    report = analyze(snapshot, AdvisorConfig(packs=[CONSOLIDATION_PACK]), as_of=AS_OF)

    assert not report.recommendations
    assert report.blocked_recommendations


def test_nap_consolidation_readiness_ignores_metric_coverage_at_freshness_boundary() -> None:
    result = consolidation_report()
    snapshot = result.snapshot
    snapshot.metric_window.coverage_ratio = 0
    observed_times = [
        item.source_observed_at
        for item in snapshot.collection_manifest.source_results
        if item.source_observed_at is not None
    ]

    report = analyze(
        snapshot,
        AdvisorConfig(packs=[CONSOLIDATION_PACK]),
        as_of=min(observed_times) + timedelta(hours=24),
    )

    assert report.recommendations
    assert not report.blocked_recommendations


def test_nap_consolidation_readiness_respects_namespace_exclusions() -> None:
    value = nap_payload()
    nodepool = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool"
    )
    nodepool["spec"]["disruption"].update(
        consolidationPolicy="WhenEmptyOrUnderutilized",
        budgets=[{"nodes": "10%"}],
    )
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["spec"]["nodeSelector"] = {"synthetic.example/pool": "special"}

    result = consolidation_report(value, excluded_namespaces=["synthetic"])

    assert not result.report.recommendations
    assert not result.report.blocked_recommendations


def test_nap_supply_requires_exact_claim_owner_and_provider_bound_node() -> None:
    value = nap_payload()
    result = capacity_report(value)
    finding = result.report.recommendations[0]
    assert finding.metadata["nap_managed_nodes"] == [
        {
            "node_uid": "synthetic-node-uid",
            "nodeclaim_uid": "synthetic-claim-uid",
            "nodepool_uid": "synthetic-nap-pool-uid",
        }
    ]
    pool = finding.metadata["nap_pools"][0]
    assert pool["nodeclass_uid"] == "synthetic-class-uid"
    assert pool["requirement_count"] == 1
    assert pool["taint_count"] == 0
    assert pool["startup_taint_count"] == 1
    assert pool["supply_mode"] == "static"
    assert pool["static_replicas"] == 2
    assert pool["consolidation_policy"] == "WhenEmpty"
    assert pool["consolidate_after"] == "30s"
    assert pool["disruption_budget_count"] == 1
    assert pool["zero_node_disruption_budget_configured"] is True
    assert pool["limits_observed"] is True
    assert analyze(result.snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF) == result.report


def test_dynamic_nap_pool_retains_disruption_policy_without_inventing_static_replicas() -> None:
    value = nap_payload()
    nodepool = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool"
    )
    nodepool["spec"].pop("replicas")
    nodepool["spec"]["disruption"]["budgets"] = [{"nodes": "10%"}]

    pool = capacity_report(value).report.recommendations[0].metadata["nap_pools"][0]
    assert pool["supply_mode"] == "dynamic"
    assert pool["static_replicas"] is None
    assert pool["zero_node_disruption_budget_configured"] is False


@pytest.mark.parametrize("replicas", [True, -1, "2"])
def test_invalid_static_nap_replicas_remain_unknown(replicas: object) -> None:
    value = nap_payload()
    nodepool = next(
        item for item in value["kubernetes"][0]["resources"] if item["kind"] == "NodePool"
    )
    nodepool["spec"]["replicas"] = replicas

    finding = capacity_report(value).report.recommendations[0]
    pool = finding.metadata["nap_pools"][0]
    assert pool["supply_mode"] == "unknown"
    assert pool["static_replicas"] is None
    assert "invalid_nap_static_replicas" in finding.metadata["capacity_issues"]


@pytest.mark.parametrize(
    "problem", ["owner", "provider", "scope", "node-name", "node-api", "claim-api", "class-api"]
)
def test_nap_never_infers_management_from_names_or_unverified_apis(problem: str) -> None:
    value = nap_payload()
    metadata = value["kubernetes"][0]
    claim = next(item for item in metadata["resources"] if item["kind"] == "NodeClaim")
    if problem == "owner":
        claim["owner_references"][0]["uid"] += "-recreated"
    elif problem == "provider":
        claim["status"]["providerID"] += "-foreign"
    elif problem == "scope":
        metadata["nodes"][0]["azure_resource_id"] = None
    elif problem == "node-name":
        claim["status"]["nodeName"] += "-recreated"
    elif problem == "node-api":
        metadata["resource_versions"].pop("v1/nodes")
    elif problem == "claim-api":
        metadata["resource_versions"].pop("karpenter.sh/v1/nodeclaims")
    else:
        metadata["resource_versions"].pop("karpenter.azure.com/v1beta1/aksnodeclasses")
    finding = capacity_report(value).report.recommendations[0]
    if problem == "class-api":
        assert finding.metadata["nap_pools"][0]["nodeclass_uid"] is None
    else:
        assert not finding.metadata["nap_managed_nodes"]
    assert finding.estimated_monthly_savings is None


def test_pool_intents_cannot_repeat_or_transfer_to_recreated_native_pools() -> None:
    result = capacity_report()
    context = result.snapshot.clusters[0].capacity
    from aks_fleet_efficiency.models import PoolIntentBinding

    pool = context.pools[0]
    pool.intent = PoolIntentBinding(
        cluster_resource_id=context.cluster_resource_id,
        pool_resource_id=pool.resource_id + "-foreign",
        owner="synthetic-owner",
        classification="specialized",
        reference="synthetic-review/hardware",
    )
    report = analyze(result.snapshot, AdvisorConfig(packs=[PACK]), as_of=AS_OF)
    assert not report.recommendations
    assert "capacity_intent_identity_mismatch" in report.blocked_recommendations[0].reason_codes


@pytest.mark.parametrize("problem", ["duplicate-claim", "manual-mode"])
def test_ambiguous_nap_supply_is_never_selected_by_list_order(problem: str) -> None:
    value = nap_payload()
    if problem == "manual-mode":
        value["azure"][0]["clusters"][0]["node_provisioning_mode"] = "Manual"
    else:
        import copy

        resources = value["kubernetes"][0]["resources"]
        second = copy.deepcopy(next(item for item in resources if item["kind"] == "NodeClaim"))
        second["uid"] = "synthetic-second-claim-uid"
        second["name"] = "synthetic-second-claim"
        resources.append(second)
    finding = capacity_report(value).report.recommendations[0]
    assert not finding.metadata["nap_managed_nodes"]
    assert finding.metadata["capacity_issues"]


@pytest.mark.parametrize("problem", ["duplicate", "foreign-pool", "manual-mode"])
def test_native_nap_contract_rejects_ambiguous_or_unbound_supply(problem: str) -> None:
    from aks_fleet_efficiency.models import FleetSnapshot

    snapshot = capacity_report(nap_payload()).snapshot.model_dump(mode="json")
    context = snapshot["clusters"][0]["capacity"]
    if problem == "duplicate":
        context["nap_managed_nodes"].append(context["nap_managed_nodes"][0].copy())
    elif problem == "foreign-pool":
        context["nap_managed_nodes"][0]["nodepool_uid"] += "-foreign"
    else:
        context["provisioning_mode"] = "Manual"
    with pytest.raises(ValueError, match="NAP supply"):
        FleetSnapshot.model_validate(snapshot)
