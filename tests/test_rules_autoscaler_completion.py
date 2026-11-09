from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_assessment import AS_OF, assess, observation
from test_rules_autoscalers import controller, interaction_payload
from test_rules_hpa_history import pinning_payload
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import FleetSnapshot
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown
from aks_fleet_efficiency.rules.autoscalers import replica_configuration_digest
from aks_fleet_efficiency.rules.engine import analyze
from scripts.verify import _verify_autoscaler_shape

KEDA_API = "keda.sh/v1alpha1/scaledobjects"


def keda_payload(trigger: str = "prometheus") -> dict[str, Any]:
    value = interaction_payload()
    metadata = value["kubernetes"][0]
    metadata["api_availability"][KEDA_API] = "available"
    metadata["resource_versions"][KEDA_API] = "synthetic-keda-version"
    metadata["resources"].append(
        {
            "api_version": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "name": "synthetic-keda",
            "namespace": "synthetic",
            "uid": "synthetic-keda-uid",
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "StatefulSet",
                    "name": "synthetic",
                },
                "minReplicaCount": 0,
                "maxReplicaCount": 5,
                "pollingInterval": 30,
                "cooldownPeriod": 300,
                "triggers": [{"type": trigger, "metricType": "AverageValue"}],
            },
            "status": {"hpaName": "synthetic-hpa"},
        }
    )
    controller(value, "HorizontalPodAutoscaler")["owner_references"] = [
        {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "name": "synthetic-keda",
            "uid": "synthetic-keda-uid",
            "controller": True,
        }
    ]
    return value


def replica_payload() -> dict[str, Any]:
    value = pinning_payload("fixed")
    metadata = value["kubernetes"][0]
    workload = controller(value, "StatefulSet")
    workload["kind"] = "Deployment"
    workload["status"] = {"replicas": 2, "availableReplicas": 2}
    metadata["api_availability"]["apps/v1/deployments"] = "available"
    metadata["resource_versions"]["apps/v1/deployments"] = "synthetic-deployment-version"
    for pod in [item for item in metadata["resources"] if item["kind"] == "Pod"]:
        pod["owner_references"][0]["kind"] = "Deployment"
    hpa = controller(value, "HorizontalPodAutoscaler")
    hpa["spec"]["scaleTargetRef"]["kind"] = "Deployment"
    hpa["spec"]["maxReplicas"] = 5
    controller(value, "VerticalPodAutoscaler")["spec"]["targetRef"]["kind"] = "Deployment"
    binding = value["workload_assessments"][0]
    binding["workload_kind"] = "Deployment"
    binding["safety_policy"]["replicas"] = {
        "allow_floor_reduction": True,
        "hpa_uid": hpa["uid"],
        "minimum_available_replicas": 1,
        "tested_replicas": 1,
        "maximum_reduction_ratio": 0.5,
        "failover_reserve_replicas": 0,
        "maximum_unavailable_replicas": 0,
        "peak_load_reviewed": True,
        "startup_reviewed": True,
        "throughput_reviewed": True,
        "zone_failure_reviewed": True,
        "reliability_reviewed": True,
        "oom_events": 0,
        "restart_events": 0,
        "eviction_events": 0,
        "evidence_reference": "synthetic-owner-reviewed-replica-canary",
    }
    for item in value["metrics"][0]["observations"]:
        item["entity"]["workload_kind"] = "Deployment"
        if item["metric"] in {
            "desired_replicas",
            "observed_replicas",
            "available_replicas",
            "hpa_min_replicas",
            "hpa_current_replicas",
            "hpa_desired_replicas",
        }:
            item.update(minimum=2, p50=2, p95=2, p99=2, maximum=2)
            item["quality"].update(minimum=2, maximum=2)
        if item["metric"] == "hpa_max_replicas":
            item.update(minimum=5, p50=5, p95=5, p99=5, maximum=5)
            item["quality"].update(minimum=5, maximum=5)
    observed = json.loads(json.dumps(observation(value, "desired_replicas")))
    observed["metric"] = "observed_replicas"
    value["metrics"][0]["observations"].append(observed)
    binding["safety_policy"]["replicas"]["configuration_digest"] = replica_configuration_digest(
        assess(value).snapshot.clusters[0].workloads[0]
    )
    return value


def rule(value: dict[str, Any], rule_id: str) -> Any:
    return next(item for item in assess(value).report.recommendations if item.rule_id == rule_id)


def blocked(value: dict[str, Any], rule_id: str) -> list[str]:
    report = assess(value).report
    assert not any(item.rule_id == rule_id for item in report.recommendations)
    return next(
        item.reason_codes for item in report.blocked_recommendations if item.rule_id == rule_id
    )


@pytest.mark.parametrize("trigger", ["prometheus", "cpu", "memory"])
def test_keda_generated_hpa_is_one_controller_and_scale_zero_is_only_a_review(trigger: str) -> None:
    value = keda_payload(trigger)
    result = assess(value)
    finding = rule(value, "AKS-AS-004")
    evidence = {item.metric: item.value for item in finding.evidence}
    assert evidence["generated_hpa_uid"] == "synthetic-hpa-uid"
    assert evidence["trigger_type"] == trigger
    assert evidence["scale_to_zero"] is True
    assert finding.proposed_replica_floor is None
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert "cannot activate" in finding.summary if trigger in {"cpu", "memory"} else True
    assert not any(
        item.rule_id in {"AKS-RQ-002", "AKS-MEM-003"} for item in result.report.recommendations
    )
    assert analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF) == result.report


@pytest.mark.parametrize("defect", ["uid", "name", "controller", "status", "triggers", "api"])
def test_keda_ownership_and_signal_unknowns_do_not_become_safe_absence(defect: str) -> None:
    value = keda_payload()
    hpa = controller(value, "HorizontalPodAutoscaler")
    if defect in {"uid", "name"}:
        hpa["owner_references"][0][defect] = "synthetic-other"
    elif defect == "controller":
        hpa["owner_references"][0]["controller"] = False
    elif defect == "status":
        controller(value, "ScaledObject").pop("status")
    elif defect == "triggers":
        controller(value, "ScaledObject")["spec"].pop("triggers")
    else:
        value["kubernetes"][0]["resource_versions"].pop(KEDA_API)
    assert blocked(value, "AKS-AS-004")
    result = assess(value)
    assert not any(item.rule_id == "AKS-AS-001" for item in result.report.recommendations)


def test_multiple_hpas_are_a_controller_responsibility_investigation_not_a_floor_proposal() -> None:
    value = replica_payload()
    extra = json.loads(json.dumps(controller(value, "HorizontalPodAutoscaler")))
    extra.update(uid="synthetic-second-hpa", name="synthetic-second-hpa")
    value["kubernetes"][0]["resources"].append(extra)
    finding = rule(value, "AKS-AS-004")
    assert "multiple" in finding.summary.lower()
    assert blocked(value, "AKS-AS-005")


def test_replica_floor_proposal_has_exact_typed_values_preserves_other_dimensions_and_replays() -> (
    None
):
    value = replica_payload()
    before = json.dumps(value, sort_keys=True)
    result = assess(value)
    finding = rule(value, "AKS-AS-005")
    assert finding.current_replica_floor == 2
    assert finding.proposed_replica_floor == 1
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert finding.owner
    assert finding.prerequisites and finding.validation_steps and finding.rollback_steps
    assert "2" in " ".join(finding.rollback_steps)
    assert "HPA minimum replicas" in render_assessment_markdown(result)
    assert FleetSnapshot.model_validate_json(result.snapshot.model_dump_json()) == result.snapshot
    assert analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF) == result.report
    assert json.dumps(value, sort_keys=True) == before
    assert not any(
        item.rule_id in {"AKS-RQ-002", "AKS-MEM-003"} for item in result.report.recommendations
    )


@pytest.mark.parametrize(
    "defect",
    [
        "disabled",
        "missing-policy",
        "owner",
        "hpa",
        "reserve",
        "minimum",
        "tested",
        "startup",
        "peak",
        "throughput",
        "zone",
        "disruption",
        "current-availability",
        "missing-history",
        "coverage",
        "unavailable",
        "fractional",
        "changed-floor",
        "vpa",
    ],
)
def test_replica_floor_requires_all_independent_safety_gates(defect: str) -> None:
    value = replica_payload()
    safety = value["workload_assessments"][0]["safety_policy"]
    policy = safety["replicas"]
    if defect == "disabled":
        policy.pop("allow_floor_reduction")
    elif defect == "missing-policy":
        safety.pop("replicas")
    elif defect == "owner":
        safety["owner"] = " "
    elif defect == "hpa":
        policy["hpa_uid"] = "synthetic-other-hpa"
    elif defect in {"reserve", "minimum", "tested"}:
        policy[
            {
                "reserve": "failover_reserve_replicas",
                "minimum": "minimum_available_replicas",
                "tested": "tested_replicas",
            }[defect]
        ] = 2
    elif defect in {"startup", "peak", "throughput", "zone"}:
        policy[
            {
                "startup": "startup_reviewed",
                "peak": "peak_load_reviewed",
                "throughput": "throughput_reviewed",
                "zone": "zone_failure_reviewed",
            }[defect]
        ] = False
    elif defect == "disruption":
        safety["disruption_reviewed"] = False
    elif defect == "current-availability":
        controller(value, "Deployment")["status"]["availableReplicas"] = 1
    elif defect == "missing-history":
        value["metrics"][0]["observations"].remove(observation(value, "available_replicas"))
    elif defect == "coverage":
        observation(value, "available_replicas")["quality"]["window"]["coverage_ratio"] = 0.84
    elif defect in {"unavailable", "fractional"}:
        item = observation(value, "available_replicas")
        item["minimum"] = item["quality"]["minimum"] = 1 if defect == "unavailable" else 1.5
    elif defect == "changed-floor":
        item = observation(value, "hpa_min_replicas")
        item["minimum"] = item["quality"]["minimum"] = 1
    else:
        vpa = controller(value, "VerticalPodAutoscaler")
        vpa["spec"]["updatePolicy"]["updateMode"] = "Auto"
        vpa["spec"]["resourcePolicy"] = {
            "containerPolicies": [
                {"containerName": "*", "mode": "Auto", "controlledResources": ["cpu"]}
            ]
        }
    assert blocked(value, "AKS-AS-005")


def test_changed_bounds_are_reviewed_without_claiming_oscillation_or_a_numeric_target() -> None:
    value = replica_payload()
    item = observation(value, "hpa_max_replicas")
    item["minimum"] = item["quality"]["minimum"] = 3
    finding = rule(value, "AKS-AS-006")
    assert finding.proposed_replica_floor is None
    assert "oscillation" in finding.summary
    assert blocked(value, "AKS-AS-005")


def test_vpa_status_and_policy_bounds_are_context_not_a_rightsizing_authorization() -> None:
    value = interaction_payload()
    vpa = controller(value, "VerticalPodAutoscaler")
    policy = vpa["spec"]["resourcePolicy"]["containerPolicies"][0]
    policy.update(minAllowed={"cpu": "100m"}, maxAllowed={"cpu": "1"})
    vpa["status"] = {
        "recommendation": {
            "containerRecommendations": [
                {
                    "containerName": "api",
                    "lowerBound": {"cpu": "200m"},
                    "target": {"cpu": "500m"},
                    "upperBound": {"cpu": "800m"},
                    "uncappedTarget": {"cpu": "1200m"},
                }
            ]
        }
    }
    finding = rule(value, "AKS-AS-007")
    evidence = {item.metric: item.value for item in finding.evidence}
    assert evidence["vpa_target_cpu_mcores"] == 500
    assert evidence["vpa_uncapped_cpu_mcores"] == 1200
    assert finding.proposed_requests is None
    assert finding.proposed_replica_floor is None
    assert "freshness" in finding.summary


@pytest.mark.parametrize("hours, expected", [(24, True), (24.01, False)])
def test_new_inventory_rules_use_exact_freshness_boundary(hours: float, expected: bool) -> None:
    result = assess(keda_payload())
    result.snapshot.clusters[0].workloads[0].autoscaler_configuration.observed_at = (
        AS_OF - timedelta(hours=hours)
    )
    report = analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert any(item.rule_id == "AKS-AS-004" for item in report.recommendations) is expected


def test_replica_floor_cli_artifacts_preserve_and_replay_exact_proposal(tmp_path: Path) -> None:
    source = tmp_path / "synthetic-replicas.json"
    source.write_text(json.dumps(replica_payload()), encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "assess",
            "--fragments",
            str(source),
            "--config",
            "examples/pool-assessment-config.yaml",
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
            "--artifacts",
            str(artifacts),
        ],
    )
    assert result.exit_code == 3, result.output
    assessment = json.loads(result.output)
    finding = next(
        item for item in assessment["report"]["recommendations"] if item["rule_id"] == "AKS-AS-005"
    )
    assert finding["current_replica_floor"] == 2 and finding["proposed_replica_floor"] == 1
    replay = runner.invoke(
        app,
        [
            "analyze",
            "--snapshot",
            str(artifacts / "snapshot.json"),
            "--config",
            str(artifacts / "analysis-config.json"),
            "--as-of",
            AS_OF.isoformat(),
            "--format",
            "json",
        ],
    )
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.output) == assessment["report"]


@pytest.mark.parametrize("field", ["nodeSelector", "affinity", "volumes", "runtimeClassName"])
def test_replica_floor_never_ignores_unmodeled_placement_or_state(field: str) -> None:
    value = replica_payload()
    for pod in [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]:
        pod["spec"][field] = {
            "nodeSelector": {"synthetic": "required"},
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {"key": "synthetic", "operator": "In", "values": ["required"]}
                                ]
                            }
                        ]
                    }
                }
            },
            "volumes": [{"name": "synthetic", "emptyDir": {}}],
            "runtimeClassName": "synthetic-runtime",
        }[field]
    assert blocked(value, "AKS-AS-005")


def test_replica_floor_requires_explicit_owner_reliability_review() -> None:
    value = replica_payload()
    value["workload_assessments"][0]["safety_policy"]["replicas"]["reliability_reviewed"] = False
    assert blocked(value, "AKS-AS-005")


@pytest.mark.parametrize("count", ["oom_events", "restart_events", "eviction_events"])
@pytest.mark.parametrize("value", [None, 1])
def test_unknown_and_positive_owner_reviewed_incidents_block_replica_floor(
    count: str, value: int | None
) -> None:
    payload = replica_payload()
    payload["workload_assessments"][0]["safety_policy"]["replicas"][count] = value
    assert blocked(payload, "AKS-AS-005")


@pytest.mark.parametrize("resource", ["cpu", "memory"])
def test_material_pod_resource_change_invalidates_the_reviewed_replica_configuration(
    resource: str,
) -> None:
    value = replica_payload()
    for pod in [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]:
        pod["spec"]["containers"][0]["resources"]["limits"] = {
            resource: "2" if resource == "cpu" else "2Gi"
        }
    assert "unreviewed_replica_configuration" in blocked(value, "AKS-AS-005")


def test_observed_oom_history_vetoes_an_owner_declaration_of_zero() -> None:
    value = replica_payload()
    item = observation(value, "oom_events")
    item.update(minimum=1, p50=1, p95=1, p99=1, maximum=1, total=8640)
    item["quality"].update(minimum=1, maximum=1)
    assert "observed_replica_reliability_events" in blocked(value, "AKS-AS-005")


@pytest.mark.parametrize("ratio, expected", [(0.5, True), (0.4999999, False), (0.5000001, True)])
def test_replica_floor_rounds_up_at_the_exact_owner_reduction_boundary(
    ratio: float, expected: bool
) -> None:
    value = replica_payload()
    value["workload_assessments"][0]["safety_policy"]["replicas"]["maximum_reduction_ratio"] = ratio
    report = assess(value).report
    assert any(item.rule_id == "AKS-AS-005" for item in report.recommendations) is expected


@pytest.mark.parametrize("invalid", ["true", 1, None])
def test_replica_opt_in_never_coerces_truthy_or_unknown_values(invalid: object) -> None:
    value = replica_payload()
    value["workload_assessments"][0]["safety_policy"]["replicas"]["allow_floor_reduction"] = invalid
    with pytest.raises(ValueError):
        assess(value)


@pytest.mark.parametrize(
    "defect", ["missing", "partial", "stale", "unit", "source", "identity", "grid"]
)
def test_replica_floor_requires_each_availability_series_and_exact_quality(defect: str) -> None:
    value = replica_payload()
    item = observation(value, "observed_replicas")
    if defect == "missing":
        value["metrics"][0]["observations"].remove(item)
    elif defect == "partial":
        item["quality"]["window"]["coverage_ratio"] = 0.99
    elif defect == "stale":
        item["quality"]["observed_at"] = "2026-10-28T00:00:00Z"
    elif defect == "unit":
        item["quality"]["unit"] = "nodes"
    elif defect == "source":
        item["quality"]["source"] = "synthetic-other"
    elif defect == "identity":
        item["entity"]["workload_uid"] = "synthetic-recreated-workload"
    else:
        item["quality"]["step_seconds"] = 600
    if defect in {"stale", "grid"}:
        with pytest.raises(ValueError):
            assess(value)
        return
    assert blocked(value, "AKS-AS-005")


def vpa_payload() -> dict[str, Any]:
    value = interaction_payload()
    vpa = controller(value, "VerticalPodAutoscaler")
    vpa["spec"]["resourcePolicy"]["containerPolicies"][0].update(
        minAllowed={"cpu": "100m", "memory": "128Mi"},
        maxAllowed={"cpu": "1", "memory": "1Gi"},
    )
    vpa["status"] = {
        "recommendation": {
            "containerRecommendations": [
                {
                    "containerName": "api",
                    "target": {"cpu": "500m", "memory": "512Mi"},
                    "lowerBound": {"cpu": "200m", "memory": "256Mi"},
                    "upperBound": {"cpu": "800m", "memory": "768Mi"},
                }
            ]
        }
    }
    return value


@pytest.mark.parametrize(
    "defect", ["missing", "lower", "policy", "quantity", "container", "duplicate"]
)
def test_vpa_bounds_missing_and_contradictory_evidence_never_become_a_resource_proposal(
    defect: str,
) -> None:
    value = vpa_payload()
    vpa = controller(value, "VerticalPodAutoscaler")
    recommendation = vpa["status"]["recommendation"]["containerRecommendations"][0]
    if defect == "missing":
        recommendation.pop("upperBound")
    elif defect == "lower":
        recommendation["lowerBound"]["cpu"] = "900m"
    elif defect == "policy":
        vpa["spec"]["resourcePolicy"]["containerPolicies"][0]["maxAllowed"]["cpu"] = "400m"
    elif defect == "quantity":
        recommendation["target"]["memory"] = "NaN"
    elif defect == "container":
        recommendation["containerName"] = "synthetic-other"
    else:
        vpa["status"]["recommendation"]["containerRecommendations"].append(recommendation.copy())
    assert blocked(value, "AKS-AS-007")
    assert rule(value, "AKS-AS-002").proposed_requests is None


def test_vpa_memory_bounds_have_explicit_mib_units_and_no_numeric_changes() -> None:
    finding = rule(vpa_payload(), "AKS-AS-007")
    evidence = {item.metric: (item.value, item.unit) for item in finding.evidence}
    assert evidence["vpa_target_memory_mib"] == (512, "MiB")
    assert finding.proposed_requests is None and finding.proposed_replica_floor is None


def test_varying_hpa_counts_are_reviewable_without_claiming_instability() -> None:
    value = replica_payload()
    item = observation(value, "hpa_desired_replicas")
    item["maximum"] = item["quality"]["maximum"] = 3
    finding = rule(value, "AKS-AS-006")
    assert finding.proposed_replica_floor is None
    assert "oscillation" in finding.summary
    assert blocked(value, "AKS-AS-005")


@pytest.mark.parametrize("rule_id", ["AKS-AS-004", "AKS-AS-007"])
@pytest.mark.parametrize(
    "defect", ["metadata-denied", "stale-configuration", "future-configuration"]
)
def test_new_current_rules_enforce_source_and_clock_guards(rule_id: str, defect: str) -> None:
    result = assess(keda_payload() if rule_id == "AKS-AS-004" else vpa_payload())
    snapshot = result.snapshot
    configuration = snapshot.clusters[0].workloads[0].autoscaler_configuration
    if defect == "metadata-denied":
        value = keda_payload() if rule_id == "AKS-AS-004" else vpa_payload()
        receipt = value["kubernetes"][0]["collection"]
        receipt["status"] = "partial"
        receipt["missing_fields"] = ["synthetic-required-list"]
        assert blocked(value, rule_id)
        return
    configuration.observed_at = (
        AS_OF + timedelta(seconds=1)
        if defect == "future-configuration"
        else AS_OF - timedelta(seconds=86401)
    )
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert any(item.rule_id == rule_id for item in report.blocked_recommendations)
    assert not any(item.rule_id == rule_id for item in report.recommendations)


def test_keda_review_does_not_require_prometheus_and_never_exports_authentication() -> None:
    value = keda_payload()
    value["metrics"] = []
    result = assess(value)
    assert any(item.rule_id == "AKS-AS-004" for item in result.report.recommendations)
    assert all(item.proposed_requests is None for item in result.report.recommendations)
    value = keda_payload()
    controller(value, "ScaledObject")["spec"]["triggers"][0]["authenticationRef"] = {
        "name": "synthetic-secret"
    }
    with pytest.raises(ValueError, match="approved projection"):
        assess(value)


def test_new_current_evidence_is_escaped_in_markdown() -> None:
    value = keda_payload()
    controller(value, "ScaledObject")["spec"]["triggers"][0]["type"] = (
        "<script>alert(1)</script>\n[link](https://synthetic.invalid)"
    )
    text = render_assessment_markdown(assess(value))
    assert "<script>" not in text and "[link](https://synthetic.invalid)" not in text
    assert "&lt;script&gt;" in text


@pytest.mark.parametrize("field", ["initContainers", "overhead"])
def test_unknown_pod_overhead_cannot_authorize_a_replica_floor(field: str) -> None:
    value = replica_payload()
    for pod in [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]:
        pod["spec"].pop(field)
    value["workload_assessments"][0]["safety_policy"]["replicas"]["configuration_digest"] = (
        replica_configuration_digest(assess(value).snapshot.clusters[0].workloads[0])
    )
    assert "unknown_replica_constraints" in blocked(value, "AKS-AS-005")


@pytest.mark.parametrize("case", ["keda", "replica-floor", "vpa-bounds"])
def test_packaged_autoscaler_shape_checks_real_outputs_and_rejects_missing_findings(
    case: str,
) -> None:
    value = {
        "keda": keda_payload,
        "replica-floor": replica_payload,
        "vpa-bounds": vpa_payload,
    }[case]()
    result = assess(value).model_dump(mode="json")
    _verify_autoscaler_shape(case, result)
    result["report"]["recommendations"] = []
    with pytest.raises(RuntimeError, match="must contain one"):
        _verify_autoscaler_shape(case, result)
