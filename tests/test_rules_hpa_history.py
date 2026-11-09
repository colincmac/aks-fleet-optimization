from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_assessment import AS_OF, assess, observation
from test_rules_autoscalers import controller, interaction_payload
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import FleetSnapshot, Severity
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown
from aks_fleet_efficiency.rules.engine import analyze

RULE_ID = "AKS-AS-003"
HPA_METRICS = (
    "hpa_min_replicas",
    "hpa_max_replicas",
    "hpa_desired_replicas",
    "hpa_current_replicas",
)


def pinning_payload(state: str = "floor") -> dict[str, Any]:
    value = interaction_payload()
    metadata = value["kubernetes"][0]
    hpa = controller(value, "HorizontalPodAutoscaler")
    minimum, maximum = (2, 2) if state == "fixed" else (1, 3)
    replicas = maximum if state in {"ceiling", "fixed"} else minimum
    hpa["spec"].update(minReplicas=minimum, maxReplicas=maximum)
    hpa["status"] = {"currentReplicas": replicas, "desiredReplicas": replicas}
    controller(value, "VerticalPodAutoscaler")["spec"] = {
        "targetRef": {"apiVersion": "apps/v1", "kind": "StatefulSet", "name": "synthetic"},
        "updatePolicy": {"updateMode": "Off"},
    }
    controller(value, "StatefulSet")["spec"]["replicas"] = replicas
    pod = controller(value, "Pod")
    binding = value["workload_assessments"][0]
    binding["hpa_uid"] = hpa["uid"]
    binding["history_reference"] = "synthetic-approved-hpa-history/reference"
    for index in range(1, replicas):
        extra = json.loads(json.dumps(pod))
        extra.update(uid=f"synthetic-extra-pod-{index}", name=f"synthetic-{index}")
        metadata["resources"].append(extra)
        metadata["workload_bindings"][extra["uid"]] = binding["workload_uid"]
        binding["pod_uids"].append(extra["uid"])
    for metric, count in zip(HPA_METRICS, [minimum, maximum, replicas, replicas], strict=True):
        item = json.loads(json.dumps(observation(value, "desired_replicas")))
        item["entity"].update(kind="hpa", hpa_uid=hpa["uid"])
        item.update(metric=metric, minimum=count, p50=count, p95=count, p99=count, maximum=count)
        item["quality"].update(minimum=count, maximum=count)
        value["metrics"][0]["observations"].append(item)
    return value


def reasons(value: dict[str, Any], *, as_of: datetime = AS_OF) -> list[str]:
    report = assess(value, as_of=as_of).report
    assert not any(item.rule_id == RULE_ID for item in report.recommendations)
    return next(
        item.reason_codes for item in report.blocked_recommendations if item.rule_id == RULE_ID
    )


@pytest.mark.parametrize("state", ["floor", "ceiling", "fixed"])
def test_full_window_exact_hpa_history_identifies_bound_without_a_replica_proposal(
    state: str,
) -> None:
    value = pinning_payload(state)
    result = assess(value)
    finding = next(item for item in result.report.recommendations if item.rule_id == RULE_ID)
    evidence = {item.metric: item.value for item in finding.evidence}
    assert evidence["bound_state"] == state
    assert evidence["hpa_uid"] == "synthetic-hpa-uid"
    assert evidence["minimum_replicas"] == (2 if state == "fixed" else 1)
    assert evidence["maximum_replicas"] == (2 if state == "fixed" else 3)
    assert finding.rule_version == "2.0.0"
    assert finding.severity == Severity.MEDIUM
    assert finding.confidence.value == "high"
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert finding.prerequisites and finding.risks
    assert finding.validation_steps and finding.rollback_steps
    assert "no replica target" in " ".join(finding.proposed_actions).lower()
    assert all(item.proposed_requests is None for item in result.report.recommendations)
    assert any(
        item.entity.kind == "hpa"
        for history in result.workload_history
        for item in history.observations
    )
    assert analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF) == result.report
    assert result.snapshot == FleetSnapshot.model_validate_json(result.snapshot.model_dump_json())


def test_current_hpa_at_a_bound_does_not_substitute_for_history_or_binding() -> None:
    value = pinning_payload()
    value["workload_assessments"][0].pop("hpa_uid")
    assert "missing_hpa_replica_history" in reasons(value)
    value = pinning_payload()
    value["metrics"][0]["observations"] = [
        item for item in value["metrics"][0]["observations"] if item["metric"] not in HPA_METRICS
    ]
    assert "missing_hpa_history_metric" in reasons(value)


@pytest.mark.parametrize("metric", HPA_METRICS)
@pytest.mark.parametrize(
    "defect", ["missing", "duplicate", "coverage", "tail", "fractional", "identity"]
)
def test_hpa_pinning_requires_complete_identity_bound_metric_history(
    metric: str, defect: str
) -> None:
    value = pinning_payload()
    item = observation(value, metric)
    if defect == "missing":
        value["metrics"][0]["observations"].remove(item)
        expected = "missing_hpa_history_metric"
    elif defect == "duplicate":
        value["metrics"][0]["observations"].append(json.loads(json.dumps(item)))
        with pytest.raises(ValueError, match="duplicate metric observation"):
            assess(value)
        return
    elif defect == "coverage":
        item["quality"]["window"]["coverage_ratio"] = 0.84
        expected = "incomplete_hpa_history"
    elif defect == "tail":
        item["latest_sample_at"] = "2026-10-28T23:50:00Z"
        expected = "unsupported_hpa_history_metric"
    elif defect == "fractional":
        for name in ["minimum", "p50", "p95", "p99", "maximum"]:
            item[name] = 1.5
        item["quality"].update(minimum=1.5, maximum=1.5)
        expected = "unsupported_hpa_history_metric"
    else:
        item["entity"]["hpa_uid"] = "synthetic-recreated-hpa"
        expected = "hpa_history_identity_mismatch"
    assert expected in reasons(value)


@pytest.mark.parametrize("metric", ["hpa_desired_replicas", "hpa_current_replicas"])
def test_variable_replica_history_is_not_reported_as_pinned(metric: str) -> None:
    value = pinning_payload()
    item = observation(value, metric)
    item.update(maximum=2, p95=2, p99=2)
    item["quality"]["maximum"] = 2
    result = assess(value)
    assert not any(item.rule_id == RULE_ID for item in result.report.recommendations)
    assert not any(item.rule_id == RULE_ID for item in result.report.blocked_recommendations)


@pytest.mark.parametrize(
    "defect, expected",
    [
        ("changing-bound", "changing_hpa_bounds"),
        ("current-bound", "hpa_bounds_changed"),
        ("missing-bound", "missing_hpa_bounds"),
        ("status", "hpa_replica_status_changed"),
        ("missing-status", "missing_hpa_replica_status"),
        ("binding", "hpa_history_identity_mismatch"),
        ("window", "unreviewed_hpa_history_window"),
        ("partial-source", "incomplete_collection"),
    ],
)
def test_pinning_does_not_extrapolate_changed_or_unapproved_hpa_context(
    defect: str, expected: str
) -> None:
    value = pinning_payload()
    hpa = controller(value, "HorizontalPodAutoscaler")
    if defect == "changing-bound":
        item = observation(value, "hpa_max_replicas")
        item["minimum"] = item["quality"]["minimum"] = 2
    elif defect == "current-bound":
        hpa["spec"]["maxReplicas"] = 4
    elif defect == "missing-bound":
        hpa["spec"].pop("minReplicas")
    elif defect == "status":
        hpa["status"]["desiredReplicas"] = 2
    elif defect == "missing-status":
        hpa.pop("status")
    elif defect == "binding":
        value["workload_assessments"][0]["hpa_uid"] = "synthetic-other-hpa"
    elif defect == "window":
        value["workload_assessments"][0]["safety_policy"]["reviewed_window_start"] = (
            "2026-09-28T00:00:00Z"
        )
    else:
        value["metrics"][0]["collection"].update(status="partial", pagination_complete=False)
    assert expected in reasons(value)


@pytest.mark.parametrize(
    "start, samples", [("2026-10-28T00:00:00Z", 288), ("2026-09-29T00:05:00Z", 8639)]
)
def test_short_and_stale_hpa_history_stays_blocked(start: str, samples: int) -> None:
    value = pinning_payload()
    value["window_start"] = start
    value["metrics"][0]["query_start"] = value["window_start"]
    value["workload_assessments"][0]["safety_policy"]["reviewed_window_start"] = value[
        "window_start"
    ]
    for item in value["metrics"][0]["observations"]:
        item["quality"]["window"].update(start=value["window_start"], sample_count=samples)
    assert "short_window" in reasons(value)
    assert "stale_metrics" in reasons(
        pinning_payload(), as_of=AS_OF + timedelta(hours=12, seconds=1)
    )


def test_native_hpa_history_cannot_overstate_a_complete_grid() -> None:
    result = assess(pinning_payload())
    history = result.snapshot.clusters[0].workloads[0].hpa_replica_history
    assert history is not None
    history.metrics["hpa_min_replicas"].quality.window.sample_count -= 1
    report = analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert not any(item.rule_id == RULE_ID for item in report.recommendations)
    assert any(
        item.rule_id == RULE_ID and "incomplete_hpa_history" in item.reason_codes
        for item in report.blocked_recommendations
    )


def test_hpa_history_references_are_untrusted_text_never_executed() -> None:
    value = pinning_payload()
    value["workload_assessments"][0]["history_reference"] = "<script>history</script>\n# forged"
    rendered = render_assessment_markdown(assess(value))
    assert "<script>" not in rendered
    assert "\n# forged" not in rendered
    assert "&lt;script&gt;" in rendered


def test_hpa_review_does_not_require_absent_or_valid_vpa_policy() -> None:
    value = pinning_payload()
    controller(value, "VerticalPodAutoscaler")["spec"]["updatePolicy"].pop("updateMode")
    assert any(item.rule_id == RULE_ID for item in assess(value).report.recommendations)


def test_historical_hpa_evidence_vetoes_vertical_reductions_without_hiding_oom() -> None:
    value = pinning_payload()
    value["kubernetes"][0]["resources"] = [
        item
        for item in value["kubernetes"][0]["resources"]
        if item["kind"] not in {"HorizontalPodAutoscaler", "VerticalPodAutoscaler"}
    ]
    value["kubernetes"][0]["api_availability"]["autoscaling.k8s.io/v1/verticalpodautoscalers"] = (
        "absent"
    )
    oom = observation(value, "oom_events")
    oom.update(total=1, maximum=1)
    oom["quality"]["maximum"] = 1
    result = assess(value)
    assert any(item.rule_id == "AKS-MEM-001" for item in result.report.recommendations)
    assert not any(
        item.rule_id in {"AKS-RQ-002", "AKS-MEM-003"} for item in result.report.recommendations
    )


def test_hpa_pinning_cli_artifact_replay_is_identical(tmp_path: Path) -> None:
    source = tmp_path / "hpa-history.json"
    source.write_text(json.dumps(pinning_payload()), encoding="utf-8")
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
    report = json.loads(result.stdout)["report"]
    assert any(item["rule_id"] == RULE_ID for item in report["recommendations"])
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
    assert json.loads(replay.stdout) == report
