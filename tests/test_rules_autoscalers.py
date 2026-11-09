from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_assessment import AS_OF, assess, payload
from test_rules import eligible_snapshot
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import FleetSnapshot, Recommendation, Severity
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown
from aks_fleet_efficiency.rules.engine import analyze

RULE_ID = "AKS-AS-002"
HPA_API = "autoscaling/v2/horizontalpodautoscalers"
VPA_API = "autoscaling.k8s.io/v1/verticalpodautoscalers"


def interaction_payload() -> dict[str, Any]:
    value = payload()
    metadata = value["kubernetes"][0]
    metadata["api_availability"][VPA_API] = "available"
    metadata["resource_versions"][VPA_API] = "synthetic-vpa-version"
    target = {"apiVersion": "apps/v1", "kind": "StatefulSet", "name": "synthetic"}
    metadata["resources"].extend(
        [
            {
                "api_version": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "name": "synthetic-hpa",
                "namespace": "synthetic",
                "uid": "synthetic-hpa-uid",
                "spec": {
                    "scaleTargetRef": target.copy(),
                    "metrics": [
                        {
                            "type": "Resource",
                            "resource": {
                                "name": "cpu",
                                "target": {"type": "Utilization", "averageUtilization": 75},
                            },
                        }
                    ],
                },
            },
            {
                "api_version": "autoscaling.k8s.io/v1",
                "kind": "VerticalPodAutoscaler",
                "name": "synthetic-vpa",
                "namespace": "synthetic",
                "uid": "synthetic-vpa-uid",
                "spec": {
                    "targetRef": target.copy(),
                    "updatePolicy": {"updateMode": "Recreate"},
                    "resourcePolicy": {
                        "containerPolicies": [
                            {
                                "containerName": "*",
                                "mode": "Auto",
                                "controlledResources": ["cpu", "memory"],
                                "controlledValues": "RequestsOnly",
                            }
                        ]
                    },
                },
            },
        ]
    )
    return value


def controller(value: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == kind)


def findings(value: dict[str, Any]) -> list[Recommendation]:
    return [item for item in assess(value).report.recommendations if item.rule_id == RULE_ID]


def blocked_reasons(value: dict[str, Any]) -> list[str]:
    result = assess(value)
    assert not any(item.rule_id == RULE_ID for item in result.report.recommendations)
    return next(
        item.reason_codes
        for item in result.report.blocked_recommendations
        if item.rule_id == RULE_ID
    )


def test_current_hpa_vpa_denominator_conflict_has_bound_evidence_not_a_change() -> None:
    value = interaction_payload()
    result = assess(value)
    finding = next(item for item in result.report.recommendations if item.rule_id == RULE_ID)
    assert finding.rule_version == "2.0.0"
    assert finding.severity == Severity.MEDIUM
    assert finding.confidence.value == "high"
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert finding.current_requests is None
    evidence = {item.metric: item.value for item in finding.evidence}
    assert evidence["hpa_uid"] == "synthetic-hpa-uid"
    assert evidence["vpa_uid"] == "synthetic-vpa-uid"
    assert evidence["resource"] == "cpu"
    assert evidence["container"] == "api"
    assert evidence["average_utilization"] == 75
    assert evidence["vpa_update_mode"] == "Recreate"
    assert finding.prerequisites and finding.risks
    assert finding.validation_steps and finding.rollback_steps
    assert "no controller change" in " ".join(finding.proposed_actions).lower()
    assert analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF) == result.report
    assert result.snapshot == FleetSnapshot.model_validate_json(result.snapshot.model_dump_json())
    assert not any(
        item.rule_id in {"AKS-RQ-002", "AKS-MEM-003"} for item in result.report.recommendations
    )


@pytest.mark.parametrize("resource", ["cpu", "memory"])
@pytest.mark.parametrize("mode", ["Auto", "Recreate", "Initial", "InPlaceOrRecreate"])
def test_mutating_vpa_modes_overlap_only_matching_utilization_resources(
    resource: str, mode: str
) -> None:
    value = interaction_payload()
    hpa = controller(value, "HorizontalPodAutoscaler")
    hpa["spec"]["metrics"][0]["resource"]["name"] = resource
    controller(value, "VerticalPodAutoscaler")["spec"]["updatePolicy"]["updateMode"] = mode
    assert len(findings(value)) == 1


@pytest.mark.parametrize(
    "metric_type", ["Resource", "ContainerResource", "External", "Pods", "Object"]
)
def test_absolute_and_external_hpa_signals_are_not_request_denominator_conflicts(
    metric_type: str,
) -> None:
    value = interaction_payload()
    body: dict[str, Any] = {"target": {"type": "AverageValue", "averageValue": "10"}}
    key = metric_type[0].lower() + metric_type[1:]
    if metric_type in {"Resource", "ContainerResource"}:
        body["name"] = "cpu"
        if metric_type == "ContainerResource":
            body["container"] = "api"
    else:
        body["metric"] = {"name": "synthetic-demand"}
        if metric_type == "Object":
            body["describedObject"] = {"apiVersion": "v1", "kind": "Service", "name": "synthetic"}
    controller(value, "HorizontalPodAutoscaler")["spec"]["metrics"] = [
        {"type": metric_type, key: body}
    ]
    result = assess(value)
    assert not any(item.rule_id == RULE_ID for item in result.report.recommendations)
    assert not any(item.rule_id == RULE_ID for item in result.report.blocked_recommendations)
    assert not any(
        item.rule_id in {"AKS-RQ-002", "AKS-MEM-003"} for item in result.report.recommendations
    )


@pytest.mark.parametrize(
    "policy", ["vpa-off", "container-off", "different-resource", "exact-override"]
)
def test_vpa_resource_and_container_policy_prevent_false_conflicts(policy: str) -> None:
    value = interaction_payload()
    spec = controller(value, "VerticalPodAutoscaler")["spec"]
    if policy == "vpa-off":
        spec["updatePolicy"]["updateMode"] = "Off"
        spec.pop("resourcePolicy")
    elif policy == "container-off":
        spec["resourcePolicy"]["containerPolicies"][0]["mode"] = "Off"
    elif policy == "different-resource":
        spec["resourcePolicy"]["containerPolicies"][0]["controlledResources"] = ["memory"]
    else:
        spec["resourcePolicy"]["containerPolicies"].append({"containerName": "api", "mode": "Off"})
    assert not findings(value)
    assert not any(item.rule_id == RULE_ID for item in assess(value).report.blocked_recommendations)


@pytest.mark.parametrize("container_name, expect_conflict", [("api", True), ("sidecar", False)])
def test_container_resource_hpa_respects_vpa_exact_container_policy(
    container_name: str, expect_conflict: bool
) -> None:
    value = interaction_payload()
    pod = controller(value, "Pod")
    pod["spec"]["containers"].append(
        {"name": "sidecar", "resources": {"requests": {"cpu": "100m"}}}
    )
    controller(value, "HorizontalPodAutoscaler")["spec"]["metrics"] = [
        {
            "type": "ContainerResource",
            "containerResource": {
                "name": "cpu",
                "container": container_name,
                "target": {"type": "Utilization", "averageUtilization": 75},
            },
        }
    ]
    controller(value, "VerticalPodAutoscaler")["spec"]["resourcePolicy"]["containerPolicies"] = [
        {"containerName": "*", "mode": "Off"},
        {"containerName": "api", "mode": "Auto", "controlledResources": ["cpu"]},
    ]
    assert bool(findings(value)) is expect_conflict


@pytest.mark.parametrize(
    "defect, reason",
    [
        ("hpa-api", "unknown_hpa_configuration"),
        ("vpa-api", "unknown_vpa_configuration"),
        ("hpa-list-version", "unknown_hpa_configuration"),
        ("vpa-list-version", "unknown_vpa_configuration"),
        ("target", "ambiguous_autoscaler_target"),
        ("hpa-metrics", "unsupported_hpa_configuration"),
        ("utilization", "unsupported_hpa_configuration"),
        ("vpa-mode", "unsupported_vpa_configuration"),
        ("vpa-policy", "unsupported_vpa_configuration"),
        ("controlled-resources", "unsupported_vpa_configuration"),
        ("container-mode", "unsupported_vpa_configuration"),
        ("duplicate-policy", "unsupported_vpa_configuration"),
    ],
)
def test_missing_or_ambiguous_controller_configuration_stays_blocked(
    defect: str, reason: str
) -> None:
    value = interaction_payload()
    metadata = value["kubernetes"][0]
    hpa = controller(value, "HorizontalPodAutoscaler")["spec"]
    vpa = controller(value, "VerticalPodAutoscaler")["spec"]
    if defect == "hpa-api":
        metadata["api_availability"][HPA_API] = "unsupported"
    elif defect == "vpa-api":
        metadata["api_availability"][VPA_API] = "unsupported"
    elif defect == "hpa-list-version":
        metadata["resource_versions"].pop(HPA_API)
    elif defect == "vpa-list-version":
        metadata["resource_versions"].pop(VPA_API)
    elif defect == "target":
        hpa["scaleTargetRef"].pop("apiVersion")
    elif defect == "hpa-metrics":
        hpa.pop("metrics")
    elif defect == "utilization":
        hpa["metrics"][0]["resource"]["target"]["averageUtilization"] = 0
    elif defect == "vpa-mode":
        vpa["updatePolicy"].pop("updateMode")
    elif defect == "vpa-policy":
        vpa.pop("resourcePolicy")
    elif defect == "controlled-resources":
        vpa["resourcePolicy"]["containerPolicies"][0].pop("controlledResources")
    elif defect == "container-mode":
        vpa["resourcePolicy"]["containerPolicies"][0].pop("mode")
    else:
        vpa["resourcePolicy"]["containerPolicies"].append(
            vpa["resourcePolicy"]["containerPolicies"][0].copy()
        )
    assert reason in blocked_reasons(value)


@pytest.mark.parametrize("different", ["namespace", "workload", "kind"])
def test_current_target_reconciliation_never_matches_another_workload(different: str) -> None:
    value = interaction_payload()
    hpa = controller(value, "HorizontalPodAutoscaler")
    if different == "namespace":
        hpa["namespace"] = "synthetic-other"
    elif different == "workload":
        hpa["spec"]["scaleTargetRef"]["name"] = "synthetic-other"
    else:
        hpa["spec"]["scaleTargetRef"]["kind"] = "Deployment"
    assert not findings(value)


@pytest.mark.parametrize("field, invalid", [("name", 7), ("kind", False), ("name", "")])
def test_invalid_target_reference_values_are_ambiguous_not_other_workloads(
    field: str, invalid: Any
) -> None:
    value = interaction_payload()
    controller(value, "HorizontalPodAutoscaler")["spec"]["scaleTargetRef"][field] = invalid
    assert "ambiguous_autoscaler_target" in blocked_reasons(value)


def test_configuration_review_does_not_require_prometheus_or_a_historical_window() -> None:
    value = interaction_payload()
    value["metrics"] = []
    value["workload_assessments"] = []
    value["window_start"] = "2026-10-28T00:00:00Z"
    assert len(findings(value)) == 1


@pytest.mark.parametrize("quantity", ["0", "-1", "invalid", "NaN", "Inf", 1])
def test_invalid_absolute_hpa_targets_are_unknown_not_nonconflicting(quantity: Any) -> None:
    value = interaction_payload()
    controller(value, "HorizontalPodAutoscaler")["spec"]["metrics"][0]["resource"]["target"] = {
        "type": "AverageValue",
        "averageValue": quantity,
    }
    assert "unsupported_hpa_configuration" in blocked_reasons(value)


@pytest.mark.parametrize(
    "defect, reason", [("partial", "incomplete_collection"), ("stale", "stale_source")]
)
def test_current_configuration_needs_a_complete_fresh_scoped_source(
    defect: str, reason: str
) -> None:
    value = interaction_payload()
    receipt = value["kubernetes"][0]["collection"]
    if defect == "partial":
        receipt.update(status="partial", pagination_complete=False)
    else:
        receipt["source_observed_at"] = "2026-10-27T11:00:00Z"
    assert reason in blocked_reasons(value)


def test_keda_owned_hpa_is_not_mistaken_for_a_different_scaling_signal() -> None:
    value = interaction_payload()
    controller(value, "HorizontalPodAutoscaler")["owner_references"] = [
        {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "name": "synthetic-scaled-object",
            "uid": "synthetic-keda-uid",
            "controller": True,
        }
    ]
    assert len(findings(value)) == 1


@pytest.mark.parametrize("hpa_known", [True, False])
def test_current_configuration_also_vetoes_contradictory_legacy_absence_flags(
    hpa_known: bool,
) -> None:
    snapshot = eligible_snapshot()
    baseline = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert any(item.rule_id == "AKS-RQ-002" for item in baseline.recommendations)
    cluster = snapshot.clusters[0]
    workload = cluster.workloads[0]
    configuration = (
        assess(interaction_payload()).snapshot.clusters[0].workloads[0].autoscaler_configuration
    )
    configuration.cluster_resource_id = cluster.resource_id
    configuration.cluster_uid = cluster.uid
    configuration.namespace = workload.namespace
    configuration.workload_uid = workload.uid
    configuration.target_name = workload.name
    configuration.target_kind = "Deployment"
    if not hpa_known:
        configuration.hpas = []
        configuration.hpa_observed = False
    workload.autoscaler_configuration = configuration
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert not any(
        item.rule_id == "AKS-AS-001" and item.workload == workload.name
        for item in report.recommendations
    )
    if not hpa_known:
        assert any(
            item.rule_id == "AKS-AS-001" and "unknown_autoscaler" in item.reason_codes
            for item in report.blocked_recommendations
        )
    assert not any(item.rule_id == "AKS-RQ-002" for item in report.recommendations)
    assert any(
        item.rule_id == "AKS-RQ-002"
        and "autoscaler_interaction_review_required" in item.reason_codes
        for item in report.blocked_recommendations
    )


def test_current_configuration_is_additive_unknown_when_omitted_and_never_historical() -> None:
    snapshot = eligible_snapshot()
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert any(
        item.rule_id == RULE_ID and "missing_autoscaler_configuration" in item.reason_codes
        for item in report.blocked_recommendations
    )
    result = assess(interaction_payload())
    value = result.snapshot.model_dump(mode="json")
    value["clusters"][0]["workloads"][0]["autoscaler_configuration"]["current_only"] = False
    with pytest.raises(ValueError):
        FleetSnapshot.model_validate(value)


def test_explicit_successful_empty_api_lists_mean_no_configuration_conflict() -> None:
    result = assess(payload())
    configuration = result.snapshot.clusters[0].workloads[0].autoscaler_configuration
    assert configuration.hpa_observed is True
    assert configuration.vpa_observed is True
    assert not configuration.hpas and not configuration.vpas
    assert not any(item.rule_id == RULE_ID for item in result.report.recommendations)
    assert not any(item.rule_id == RULE_ID for item in result.report.blocked_recommendations)


@pytest.mark.parametrize("age_seconds, blocked", [(86400, False), (86401, True)])
def test_configuration_freshness_boundary_is_independent(age_seconds: int, blocked: bool) -> None:
    result = assess(interaction_payload())
    configuration = result.snapshot.clusters[0].workloads[0].autoscaler_configuration
    configuration.observed_at = AS_OF - timedelta(seconds=age_seconds)
    report = analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert bool([item for item in report.recommendations if item.rule_id == RULE_ID]) is not blocked
    if blocked:
        assert any(
            item.rule_id == RULE_ID and "stale_autoscaler_configuration" in item.reason_codes
            for item in report.blocked_recommendations
        )


@pytest.mark.parametrize("identity", ["cluster_resource_id", "cluster_uid", "workload_uid"])
def test_replayed_configuration_must_match_exact_current_identities(identity: str) -> None:
    result = assess(interaction_payload())
    configuration = result.snapshot.clusters[0].workloads[0].autoscaler_configuration
    setattr(configuration, identity, "synthetic-wrong-identity")
    report = analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert not any(item.rule_id == RULE_ID for item in report.recommendations)
    assert any(
        item.rule_id == RULE_ID and "autoscaler_identity_mismatch" in item.reason_codes
        for item in report.blocked_recommendations
    )


def test_configuration_analysis_is_deterministic_under_source_order_and_escapes_text() -> None:
    value = interaction_payload()
    controller(value, "HorizontalPodAutoscaler")["name"] = "<script>hpa</script>\n# forged"
    first = assess(value)
    value["kubernetes"][0]["resources"].reverse()
    assert first.report == assess(value).report
    rendered = render_assessment_markdown(first)
    assert "<script>" not in rendered
    assert "\n# forged" not in rendered
    assert "&lt;script&gt;" in rendered


def test_autoscaler_configuration_cli_artifacts_replay_the_same_current_finding(
    tmp_path: Path,
) -> None:
    source = tmp_path / "autoscalers.json"
    source.write_text(json.dumps(interaction_payload()), encoding="utf-8")
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
    expected = json.loads(result.stdout)["report"]
    assert any(item["rule_id"] == RULE_ID for item in expected["recommendations"])
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
    assert json.loads(replay.stdout) == expected
