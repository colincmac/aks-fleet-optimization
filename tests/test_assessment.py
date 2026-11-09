import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aks_fleet_efficiency import workload_normalization
from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import OnboardingConfig, load_onboarding_config
from aks_fleet_efficiency.models import FleetSnapshot
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown
from aks_fleet_efficiency.rules.engine import analyze
from aks_fleet_efficiency.workload_history import WorkloadAssessmentBinding

AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)
SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)


def payload(name: str = "history-assessment") -> dict[str, Any]:
    result: dict[str, Any] = json.loads(
        Path(f"examples/fixtures/{name}.json").read_text(encoding="utf-8")
    )
    return result


def profile(name: str = "pool-assessment-config") -> OnboardingConfig:
    return load_onboarding_config(Path(f"examples/{name}.yaml"))


def assess(
    value: dict[str, Any], *, as_of: datetime = AS_OF, config: str = "pool-assessment-config"
) -> OfflineAssessment:
    return assess_fragments(AssessmentFragments.model_validate(value), profile(config), as_of=as_of)


def observation(value: dict[str, Any], metric: str) -> dict[str, Any]:
    return next(item for item in value["metrics"][0]["observations"] if item["metric"] == metric)


def container_payload(value: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")[
        "spec"
    ]["containers"][0]


def memory_history_payload() -> dict[str, Any]:
    value = payload()
    resources = container_payload(value)["resources"]
    resources["requests"]["memory"] = "512Mi"
    resources["limits"] = {"memory": "1Gi"}
    for metric, amount in [("memory_request", 512), ("memory_limit", 1024)]:
        item = json.loads(json.dumps(observation(value, "cpu_request")))
        item.update(
            metric=metric, minimum=amount, p50=amount, p95=amount, p99=amount, maximum=amount
        )
        item["quality"].update(unit="MiB", minimum=amount, maximum=amount)
        value["metrics"][0]["observations"].append(item)
    return value


def memory_safety_payload() -> dict[str, Any]:
    value = memory_history_payload()
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["status"]["qosClass"] = "Burstable"
    memory = json.loads(json.dumps(observation(value, "cpu_usage")))
    memory.update(metric="memory_usage", minimum=64, p50=128, p95=160, p99=192, maximum=200)
    memory["quality"].update(unit="MiB", minimum=64, maximum=200)
    restart = json.loads(json.dumps(observation(value, "oom_events")))
    restart["metric"] = "restarts"
    value["metrics"][0]["observations"].extend([memory, restart])
    value["workload_assessments"][0]["safety_policy"]["memory"] = {
        container_payload(value)["name"]: {
            "minimum_request_mib": 128,
            "maximum_reduction_ratio": 0.5,
            "headroom_factor": 1.25,
            "startup_peak_mib": 240,
            "failover_peak_mib": 250,
            "eviction_events": 0,
            "qos_class": "Burstable",
            "evidence_reference": "synthetic-review/memory",
        }
    }
    return value


@pytest.mark.parametrize("missing_cpu", [False, True])
def test_memory_safety_assessment_is_independent_and_replayable(missing_cpu: bool) -> None:
    value = memory_safety_payload()
    if missing_cpu:
        value["metrics"][0]["observations"].remove(observation(value, "cpu_usage"))
    fragments = AssessmentFragments.model_validate(value)
    before = fragments.model_dump_json()
    result = assess_fragments(fragments, profile(), as_of=AS_OF)
    finding = next(item for item in result.report.recommendations if item.rule_id == "AKS-MEM-002")
    assert finding.current_requests.memory_mib == 512
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert fragments.model_dump_json() == before
    assert OfflineAssessment.model_validate_json(result.model_dump_json()) == result
    assert analyze(result.snapshot, profile().analysis, as_of=AS_OF) == result.report
    assert all(
        item.proposed_requests is None or item.proposed_requests.memory_mib is None
        for item in result.report.recommendations
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_memory_review_cli_artifacts_replay_the_same_findings(
    tmp_path: Path, enabled: bool
) -> None:
    value = memory_safety_payload()
    policy = value["workload_assessments"][0]["safety_policy"]["memory"][
        container_payload(value)["name"]
    ]
    policy["allow_request_reduction"] = enabled
    source = tmp_path / "memory.json"
    source.write_text(json.dumps(value), encoding="utf-8")
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
    assessment = OfflineAssessment.model_validate_json(result.stdout)
    assert any(item.rule_id == "AKS-MEM-002" for item in assessment.report.recommendations)
    numeric = [item for item in assessment.report.recommendations if item.rule_id == "AKS-MEM-003"]
    assert bool(numeric) is enabled
    if enabled:
        assert numeric[0].proposed_requests.memory_mib == 313
        assert numeric[0].proposed_requests.cpu_mcores is None
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
    assert json.loads(replay.stdout) == assessment.report.model_dump(mode="json")


@pytest.mark.parametrize("missing_cpu", [False, True])
def test_memory_request_proposal_normalizes_and_replays_independently(missing_cpu: bool) -> None:
    value = memory_safety_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"][container_payload(value)["name"]][
        "allow_request_reduction"
    ] = True
    if missing_cpu:
        value["metrics"][0]["observations"].remove(observation(value, "cpu_usage"))
    fragments = AssessmentFragments.model_validate(value)
    before = fragments.model_dump_json()
    result = assess_fragments(fragments, profile(), as_of=AS_OF)
    finding = next(item for item in result.report.recommendations if item.rule_id == "AKS-MEM-003")
    assert finding.current_requests.memory_mib == 512
    assert finding.proposed_requests.memory_mib == 313
    assert finding.estimated_monthly_savings is None
    assert fragments.model_dump_json() == before
    assert OfflineAssessment.model_validate_json(result.model_dump_json()) == result
    assert analyze(result.snapshot, profile().analysis, as_of=AS_OF) == result.report
    rendered = render_assessment_markdown(result)
    assert "**Memory request:** 512.0 to 313.0 MiB per replica" in rendered
    assert "CPU and memory proposals require separate owner approval" in rendered


@pytest.mark.parametrize(
    "defect",
    [
        "churn",
        "init",
        "runtime",
        "request-change",
        "replica-change",
        "unknown-controller",
        "identity",
    ],
)
def test_numeric_memory_opt_in_never_overrides_unsupported_normalization(defect: str) -> None:
    value = memory_safety_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"][container_payload(value)["name"]][
        "allow_request_reduction"
    ] = True
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    if defect == "churn":
        value["workload_assessments"][0]["pod_uids"].append("synthetic-deleted-pod")
    elif defect == "init":
        pod["spec"].pop("initContainers")
    elif defect == "runtime":
        pod["spec"]["runtimeClassName"] = "synthetic-runtime"
    elif defect in {"request-change", "replica-change"}:
        metric = "memory_request" if defect == "request-change" else "desired_replicas"
        item = observation(value, metric)
        item["minimum"] = item["quality"]["minimum"] = 0
    elif defect == "unknown-controller":
        value["kubernetes"][0]["api_availability"][
            "autoscaling.k8s.io/v1/verticalpodautoscalers"
        ] = "unsupported"
    else:
        observation(value, "memory_usage")["entity"]["pod_uid"] = "synthetic-recreated-pod"
    result = assess(value)
    assert not any(item.rule_id == "AKS-MEM-003" for item in result.report.recommendations)
    assert any(item.rule_id == "AKS-MEM-003" for item in result.report.blocked_recommendations)


def test_direct_memory_basis_and_qos_survive_missing_cpu_history() -> None:
    value = memory_history_payload()
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    pod["status"]["qosClass"] = "Burstable"
    value["metrics"][0]["observations"].remove(observation(value, "cpu_usage"))
    result = assess(value)
    workload = result.snapshot.clusters[0].workloads[0]
    assert workload.qos_class == "Burstable"
    assert workload.containers[0].resources.memory_observation_basis == "pod"
    assert workload.autoscaling.hpa is False
    assert workload.autoscaling.keda is False
    assert workload.autoscaling.vpa is False
    assert "AKS-RQ-002" not in {item.rule_id for item in result.report.recommendations}
    assert any(
        item.metric == "desired_replicas" for item in result.workload_history[0].observations
    )


@pytest.mark.parametrize("defect", ["startup-overhead", "controller", "replicas", "churn"])
def test_memory_basis_does_not_hide_unsupported_history(defect: str) -> None:
    value = memory_history_payload()
    if defect == "startup-overhead":
        pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
        pod["spec"].pop("initContainers")
    elif defect == "controller":
        item = observation(value, "hpa_present")
        for field in ["minimum", "p50", "p95", "p99", "maximum"]:
            item[field] = 1
        item["quality"].update(minimum=1, maximum=1)
    elif defect == "replicas":
        item = observation(value, "desired_replicas")
        item["minimum"] = item["quality"]["minimum"] = 0
    else:
        value["workload_assessments"][0]["pod_uids"].append("synthetic-deleted-pod")
    result = assess(value)
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert resources.memory_observation_basis is None


@pytest.mark.parametrize("qos", [None, "unsupported", "Guaranteed", "BestEffort", "Burstable"])
def test_current_qos_is_observed_not_inferred(qos: str | None) -> None:
    value = payload()
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    if qos is None:
        pod["status"].pop("qosClass", None)
    else:
        pod["status"]["qosClass"] = qos
    result = assess(value)
    assert result.snapshot.clusters[0].workloads[0].qos_class == (
        qos if qos in {"Guaranteed", "BestEffort", "Burstable"} else None
    )


def test_mixed_current_qos_does_not_become_a_workload_wide_class() -> None:
    value = envelope_payload()
    pods = [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]
    pods[0]["status"]["qosClass"] = "Burstable"
    pods[1]["status"]["qosClass"] = "Guaranteed"
    result = assess(value)
    assert result.snapshot.clusters[0].workloads[0].qos_class is None


def assert_no_reduction(result: OfflineAssessment) -> None:
    assert "AKS-RQ-002" not in {item.rule_id for item in result.report.recommendations}
    assert result.status == "partial"
    assert all(
        "proposed_requests" not in item.model_dump()
        for item in result.report.blocked_recommendations
    )


def envelope_payload() -> dict[str, Any]:
    value = payload()
    metadata = value["kubernetes"][0]
    next(item for item in metadata["resources"] if item["kind"] == "StatefulSet")["spec"][
        "replicas"
    ] = 2
    pod = json.loads(
        json.dumps(next(item for item in metadata["resources"] if item["kind"] == "Pod"))
    )
    pod.update(uid="pod-uid-2", name="synthetic-1")
    metadata["resources"].append(pod)
    metadata["workload_bindings"][pod["uid"]] = "workload-uid"
    value["workload_assessments"][0]["pod_uids"] = [
        "pod-uid",
        "pod-uid-2",
        "historical-deleted-pod",
    ]
    digest = WorkloadAssessmentBinding.model_validate(
        value["workload_assessments"][0]
    ).membership_digest
    mapped = []
    keys = {
        "cpu_usage": ["replica_cpu_envelope"],
        "cpu_request": ["replica_cpu_request_min", "replica_cpu_request_max"],
        "cpu_throttling": ["replica_cpu_throttling"],
        "oom_events": ["replica_oom_events"],
    }
    for original in value["metrics"][0]["observations"]:
        for metric in keys.get(original["metric"], [original["metric"]]):
            item = json.loads(json.dumps(original))
            item["metric"] = metric
            if item["entity"]["kind"] == "container":
                item["entity"].update(
                    kind="workload_container", pod_uid=None, membership_digest=digest
                )
            elif metric in {"desired_replicas", "available_replicas"}:
                for field in ["p50", "p95", "p99", "minimum", "maximum"]:
                    item[field] = 2
                item["quality"].update(minimum=2, maximum=2)
            mapped.append(item)
    observed = json.loads(
        json.dumps(next(item for item in mapped if item["metric"] == "available_replicas"))
    )
    observed["metric"] = "observed_replicas"
    mapped.append(observed)
    value["metrics"][0]["observations"] = mapped
    return value


def test_one_contract_supports_current_inventory_and_guarded_history() -> None:
    result = assess(payload())
    assert (
        result.schema_version
        == result.snapshot.schema_version
        == result.report.schema_version
        == "1.0"
    )
    assert result.assessment_scope == "fleet-assessment"
    assert result.snapshot.collection_manifest.source_results
    proposal = next(item for item in result.report.recommendations if item.rule_id == "AKS-RQ-002")
    assert proposal.rule_version == "2.1.0"
    assert proposal.owner == "synthetic-owner"
    assert proposal.current_requests.cpu_mcores == 1000
    assert proposal.proposed_requests.cpu_mcores == 500
    assert proposal.estimated_monthly_savings is None
    assert proposal.validation_steps and proposal.rollback_steps and proposal.prerequisites
    assert result.workload_history
    assert result.metadata_evidence


@pytest.mark.parametrize("envelope", [False, True])
def test_oom_history_is_preserved_for_investigation_without_cpu_reduction(
    envelope: bool,
) -> None:
    value = envelope_payload() if envelope else payload()
    item = observation(value, "replica_oom_events" if envelope else "oom_events")
    item["total"] = 2
    item["maximum"] = item["quality"]["maximum"] = 1
    result = assess(value)
    assert_no_reduction(result)
    finding = next(item for item in result.report.recommendations if item.rule_id == "AKS-MEM-001")
    assert finding.evidence[0].value == 2
    assert finding.proposed_requests is None
    assert result.workload_history
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert resources.memory_oom_events == 2
    assert resources.cpu_observation_basis is None
    assert any(issue.code == "workload-history-guardrail" for issue in result.issues)
    assert analyze(result.snapshot, profile().analysis, as_of=AS_OF) == result.report


def test_oom_investigation_retains_direct_working_set_context() -> None:
    value = payload()
    oom = observation(value, "oom_events")
    oom["total"] = 2
    oom["maximum"] = oom["quality"]["maximum"] = 1
    memory = json.loads(json.dumps(observation(value, "cpu_usage")))
    memory.update(metric="memory_usage", minimum=64, p50=128, p95=256, p99=384, maximum=512)
    memory["quality"].update(unit="MiB", minimum=64, maximum=512)
    value["metrics"][0]["observations"].append(memory)
    result = assess(value)
    assert_no_reduction(result)
    finding = next(item for item in result.report.recommendations if item.rule_id == "AKS-MEM-001")
    assert {item.metric: item.value for item in finding.evidence} == {
        "memory_oom_events": 2,
        "usage_memory_p95_mib": 256,
        "usage_memory_p99_mib": 384,
        "observed_memory_working_set_peak_mib": 512,
    }
    assert any(item.metric == "memory_usage" for item in result.workload_history[0].observations)


def test_restart_history_is_preserved_when_cpu_history_is_unavailable() -> None:
    value = payload()
    restart = json.loads(json.dumps(observation(value, "oom_events")))
    restart.update(metric="restarts", total=2, maximum=1)
    restart["quality"]["maximum"] = 1
    value["metrics"][0]["observations"].append(restart)
    value["metrics"][0]["observations"].remove(observation(value, "cpu_usage"))
    result = assess(value)
    assert_no_reduction(result)
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert resources.model_dump().get("restart_events") == 2
    assert resources.metric_quality["restart_events"].minimum == 2
    assert resources.metric_quality["restart_events"].maximum == 2
    assert any(item.metric == "restarts" for item in result.workload_history[0].observations)
    finding = next(item for item in result.report.recommendations if item.rule_id == "AKS-REL-001")
    assert finding.evidence[0].metric == "restart_events"
    assert finding.evidence[0].value == 2
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert analyze(result.snapshot, profile().analysis, as_of=AS_OF) == result.report


def test_admitted_memory_requests_and_limits_keep_independent_historical_quality() -> None:
    result = assess(memory_history_payload())
    observed = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert observed.request_memory_mib == 512
    assert observed.limit_memory_mib == 1024
    assert observed.memory_request_observed is True
    assert observed.memory_limit_observed is True
    for field in ["request_memory_mib", "limit_memory_mib"]:
        assert observed.metric_quality[field].unit == "MiB"
        assert observed.metric_quality[field].minimum == observed.metric_quality[field].maximum
    assert {"memory_request", "memory_limit"} <= {
        item.metric for item in result.workload_history[0].observations
    }
    assert analyze(result.snapshot, profile().analysis, as_of=AS_OF) == result.report
    assert all(
        item.proposed_requests is None or item.proposed_requests.memory_mib is None
        for item in result.report.recommendations
    )


@pytest.mark.parametrize("with_history", [False, True])
def test_oom_report_only_includes_memory_bounds_backed_by_history(with_history: bool) -> None:
    value = memory_history_payload()
    if not with_history:
        value["metrics"][0]["observations"] = [
            item
            for item in value["metrics"][0]["observations"]
            if item["metric"] not in {"memory_request", "memory_limit"}
        ]
    oom = observation(value, "oom_events")
    oom["total"] = 2
    oom["maximum"] = oom["quality"]["maximum"] = 1
    result = assess(value)
    assert_no_reduction(result)
    finding = next(item for item in result.report.recommendations if item.rule_id == "AKS-MEM-001")
    evidence = {item.metric: item.value for item in finding.evidence}
    if with_history:
        assert evidence["request_memory_mib"] == 512
        assert evidence["limit_memory_mib"] == 1024
    else:
        assert "request_memory_mib" not in evidence
        assert "limit_memory_mib" not in evidence
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None


@pytest.mark.parametrize(
    "key, field, flag",
    [
        ("requests", "request_memory_mib", "memory_request_observed"),
        ("limits", "limit_memory_mib", "memory_limit_observed"),
    ],
)
@pytest.mark.parametrize(
    "quantity, expected",
    [
        ("512Mi", 512),
        ("1Gi", 1024),
        ("1073741824", 1024),
        ("1G", 1_000_000_000 / 1048576),
        ("1e9", 1_000_000_000 / 1048576),
        ("1536Ki", 1.5),
        ("0.5Gi", 512),
        ("0", 0),
    ],
)
def test_current_memory_quantities_do_not_fabricate_history(
    key: str, field: str, flag: str, quantity: str, expected: float
) -> None:
    value = payload()
    container_payload(value)["resources"].setdefault(key, {})["memory"] = quantity
    result = assess(value)
    observed = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert getattr(observed, field) == pytest.approx(expected)
    assert getattr(observed, flag) is True
    assert field not in observed.metric_quality
    assert all(item.current_only for item in result.workload_inventory)


@pytest.mark.parametrize(
    "key, field, flag",
    [
        ("requests", "request_memory_mib", "memory_request_observed"),
        ("limits", "limit_memory_mib", "memory_limit_observed"),
    ],
)
@pytest.mark.parametrize("state", ["omitted", "empty", "null", "zero"])
def test_memory_absence_is_distinct_from_unknown_and_zero(
    key: str, field: str, flag: str, state: str
) -> None:
    value = payload()
    resources = container_payload(value)["resources"]
    if state == "omitted":
        resources.pop(key, None)
    else:
        resources[key] = {} if state == "empty" else {"memory": None if state == "null" else "0"}
    result = assess(value)
    observed = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert getattr(observed, field) == (0 if state == "zero" else None)
    assert getattr(observed, flag) is (state != "omitted")
    assert field not in observed.metric_quality


@pytest.mark.parametrize("key", ["requests", "limits"])
@pytest.mark.parametrize("quantity", ["-1Mi", "NaN", "Infinity", "invalid", "1e9999", "1e-9999"])
def test_invalid_memory_quantities_remain_unknown_without_discarding_cpu(
    key: str, quantity: str
) -> None:
    value = payload()
    container_payload(value)["resources"].setdefault(key, {})["memory"] = quantity
    result = assess(value)
    observed = result.snapshot.clusters[0].workloads[0].containers[0].resources
    field, flag = (
        ("request_memory_mib", "memory_request_observed")
        if key == "requests"
        else ("limit_memory_mib", "memory_limit_observed")
    )
    assert getattr(observed, field) is None
    assert getattr(observed, flag) is False
    assert field not in observed.metric_quality
    assert observed.request_cpu_mcores == 1000


@pytest.mark.parametrize(
    "metric, field",
    [("memory_request", "request_memory_mib"), ("memory_limit", "limit_memory_mib")],
)
@pytest.mark.parametrize(
    "defect", ["missing", "changing", "mismatch", "coverage", "unit", "source", "tail", "identity"]
)
def test_memory_history_never_inherits_current_values_or_cpu_quality(
    metric: str, field: str, defect: str
) -> None:
    value = memory_history_payload()
    item = observation(value, metric)
    if defect == "missing":
        value["metrics"][0]["observations"].remove(item)
    elif defect == "changing":
        item["minimum"] = item["quality"]["minimum"] = 256
    elif defect == "mismatch":
        item.update(minimum=256, p50=256, p95=256, p99=256, maximum=256)
        item["quality"].update(minimum=256, maximum=256)
    elif defect == "coverage":
        item["quality"]["window"]["coverage_ratio"] = 0.5
    elif defect == "unit":
        item["quality"]["unit"] = "bytes"
    elif defect == "source":
        item["quality"]["source"] = "synthetic-other-source"
    elif defect == "tail":
        item["latest_sample_at"] = "2026-10-28T23:50:00Z"
    else:
        item["entity"]["pod_uid"] = "synthetic-recreated-pod"
    result = assess(value)
    observed = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert observed.request_memory_mib == 512
    assert observed.limit_memory_mib == 1024
    assert field not in observed.metric_quality
    assert all(
        item.metric != metric
        for history in result.workload_history
        for item in history.observations
    )


def test_current_memory_values_do_not_establish_a_churned_rosters_history() -> None:
    value = memory_history_payload()
    value["workload_assessments"][0]["pod_uids"].append("synthetic-deleted-pod")
    result = assess(value)
    observed = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert observed.request_memory_mib == 512
    assert observed.limit_memory_mib == 1024
    assert "request_memory_mib" not in observed.metric_quality
    assert "limit_memory_mib" not in observed.metric_quality
    assert_no_reduction(result)


def test_mixed_current_memory_requests_do_not_become_a_homogeneous_workload() -> None:
    value = envelope_payload()
    pods = [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]
    pods[0]["spec"]["containers"][0]["resources"]["requests"]["memory"] = "512Mi"
    pods[1]["spec"]["containers"][0]["resources"]["requests"]["memory"] = "1Gi"
    result = assess(value)
    assert not result.snapshot.clusters[0].workloads
    assert any(issue.code == "unsupported-workload-evidence" for issue in result.issues)


@pytest.mark.parametrize(
    "metric, field, rule_id",
    [
        ("oom_events", "memory_oom_events", "AKS-MEM-001"),
        ("restarts", "restart_events", "AKS-REL-001"),
    ],
)
@pytest.mark.parametrize(
    "total, minimum, maximum",
    [(None, 0, 1), (0.5, 0, 1), (2, 0, 0), (1, 0, 2), (1, 1, 1), (9000, 0, 1)],
)
def test_invalid_reliability_counter_totals_remain_unknown(
    metric: str, field: str, rule_id: str, total: float | None, minimum: float, maximum: float
) -> None:
    value = payload()
    if metric == "restarts":
        value["metrics"][0]["observations"].append(
            json.loads(json.dumps(observation(value, "oom_events")))
        )
        value["metrics"][0]["observations"][-1]["metric"] = metric
    item = observation(value, metric)
    item["total"] = total
    item["minimum"] = item["quality"]["minimum"] = minimum
    item["maximum"] = item["quality"]["maximum"] = maximum
    if minimum:
        item.update(p50=minimum, p95=minimum, p99=minimum)
    result = assess(value)
    if metric == "oom_events":
        assert_no_reduction(result)
    assert rule_id not in {item.rule_id for item in result.report.recommendations}
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert getattr(resources, field) is None


@pytest.mark.parametrize("count", [0, 1])
def test_restart_history_is_not_inferred_for_replica_envelopes(count: int) -> None:
    value = envelope_payload()
    restart = json.loads(json.dumps(observation(value, "replica_oom_events")))
    restart.update(metric="restarts", total=count, maximum=count)
    restart["quality"]["maximum"] = count
    value["metrics"][0]["observations"].append(restart)
    result = assess(value)
    assert result.snapshot.clusters[0].workloads[0].containers[0].resources.restart_events is None
    assert "AKS-REL-001" not in {item.rule_id for item in result.report.recommendations}
    blocked = next(
        item for item in result.report.blocked_recommendations if item.rule_id == "AKS-REL-001"
    )
    assert "missing_metric" in blocked.reason_codes


@pytest.mark.parametrize("defect", ["partial", "unit", "issues", "identity", "missing-tail"])
def test_restart_history_gaps_cannot_become_zero_or_a_reliability_finding(defect: str) -> None:
    value = payload()
    restart = json.loads(json.dumps(observation(value, "oom_events")))
    restart.update(metric="restarts", total=1, maximum=1)
    restart["quality"]["maximum"] = 1
    if defect == "partial":
        restart["quality"]["window"]["coverage_ratio"] = 0.5
    elif defect == "unit":
        restart["quality"]["unit"] = "MiB"
    elif defect == "issues":
        restart["issues"] = ["insufficient-coverage"]
    elif defect == "identity":
        restart["entity"]["pod_uid"] = "synthetic-recreated-pod"
    else:
        restart["latest_sample_at"] = "2026-10-28T23:55:00Z"
    value["metrics"][0]["observations"].append(restart)
    result = assess(value)
    assert result.snapshot.clusters[0].workloads[0].containers[0].resources.restart_events is None
    assert "AKS-REL-001" not in {item.rule_id for item in result.report.recommendations}


@pytest.mark.parametrize(
    "name, config, expected",
    [
        ("pool-assessment", "pool-assessment-config", "AKS-NP-001"),
        ("workload-assessment", "pool-assessment-config", "AKS-RQ-001"),
        ("scoped-assessment", "scoped-assessment-config", "AKS-RQ-002"),
        ("azure-fragments-assessment", "azure-fragments-config", "AKS-RQ-001"),
        ("replica-inventory-assessment", "azure-fragments-config", "AKS-RQ-001"),
    ],
)
def test_unified_examples_are_useful_without_requiring_optional_cost(
    name: str, config: str, expected: str
) -> None:
    result = assess(payload(name), config=config)
    assert expected in {item.rule_id for item in result.report.recommendations}
    assert all(item.estimated_monthly_savings is None for item in result.report.recommendations)


@pytest.mark.parametrize("version", ["1.1", "2.0", "3.0", "4.0", "5.0", "6.0", "99.0"])
def test_removed_unreleased_feature_versions_are_rejected(version: str) -> None:
    value = payload()
    value["schema_version"] = version
    with pytest.raises(ValueError):
        AssessmentFragments.model_validate(value)


@pytest.mark.parametrize(
    "defect",
    [
        "tenant",
        "source",
        "scope",
        "subscription",
        "pool-id",
        "duplicate-cluster",
        "duplicate-kubernetes",
        "duplicate-metrics",
        "duplicate-observation",
        "mixed-window",
        "unscoped-record",
    ],
)
def test_conflicting_fragment_identity_or_scope_is_rejected(defect: str) -> None:
    value = payload()
    if defect == "tenant":
        value["kubernetes"][0]["tenant_id"] = "11111111-1111-1111-1111-111111111111"
    elif defect == "source":
        value["metrics"][0]["source_name"] = "foreign"
    elif defect == "scope":
        value["azure"][0]["collection"]["requested_scope"] = ["foreign"]
        value["azure"][0]["collection"]["completed_scope"] = ["foreign"]
    elif defect == "subscription":
        value["azure"][0]["clusters"][0]["subscription_id"] = "foreign"
    elif defect == "pool-id":
        value["azure"][0]["clusters"][0]["node_pools"][0]["resource_id"] = "foreign"
    elif defect == "duplicate-cluster":
        value["azure"][0]["clusters"].append(value["azure"][0]["clusters"][0].copy())
    elif defect == "duplicate-kubernetes":
        value["kubernetes"].append(value["kubernetes"][0].copy())
    elif defect == "duplicate-metrics":
        value["metrics"].append(value["metrics"][0].copy())
    elif defect == "duplicate-observation":
        value["metrics"][0]["observations"].append(value["metrics"][0]["observations"][0].copy())
    elif defect == "mixed-window":
        value["window_start"] = "2026-09-28T00:00:00Z"
    else:
        value["azure"][0]["collection"].update(
            requested_scope=[CLUSTER + "-foreign"], completed_scope=[CLUSTER + "-foreign"]
        )
    with pytest.raises(ValueError):
        assess(value)


@pytest.mark.parametrize(
    "field", ["cluster_uid", "namespace_uid", "workload_uid", "workload", "namespace"]
)
def test_policy_binding_is_invalidated_by_recreation_or_foreign_identity(field: str) -> None:
    value = payload()
    value["workload_assessments"][0][field] = "recreated-or-foreign"
    result = assess(value)
    assert_no_reduction(result)
    assert "workload-history-identity-mismatch" in {item.code for item in result.issues}


@pytest.mark.parametrize(
    "defect",
    [
        "wrong-pod",
        "missing-binding",
        "duplicate-binding",
        "foreign-tenant",
        "foreign-source",
        "duplicate-member",
    ],
)
def test_policy_roster_and_source_are_explicit(defect: str) -> None:
    value = payload()
    binding = value["workload_assessments"][0]
    if defect == "wrong-pod":
        binding["pod_uids"] = ["recreated-pod"]
    elif defect == "missing-binding":
        value["workload_assessments"] = []
    elif defect == "duplicate-binding":
        value["workload_assessments"].append(binding.copy())
    elif defect == "foreign-tenant":
        binding["tenant_id"] = "foreign"
    elif defect == "foreign-source":
        binding["source_name"] = "foreign"
    else:
        binding["pod_uids"].append(binding["pod_uids"][0])
    if defect in {"duplicate-binding", "foreign-tenant", "foreign-source", "duplicate-member"}:
        with pytest.raises(ValueError):
            assess(value)
    else:
        assert_no_reduction(assess(value))


@pytest.mark.parametrize(
    "metric, field, replacement",
    [
        ("cpu_request", "maximum", 1100),
        ("desired_replicas", "maximum", 2),
        ("available_replicas", "minimum", 0),
        ("hpa_present", "maximum", 1),
        ("oom_events", "total", None),
        ("oom_events", "total", 1),
        ("cpu_usage", "latest_sample_at", "2026-10-28T23:58:00Z"),
    ],
)
def test_temporal_or_counter_gaps_cannot_authorize_reduction(
    metric: str, field: str, replacement: Any
) -> None:
    value = payload()
    item = observation(value, metric)
    item[field] = replacement
    if field in {"minimum", "maximum"}:
        item["quality"][field] = replacement
    assert_no_reduction(assess(value))


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("unit", "cores"),
        ("source", "foreign"),
        ("query_version", "foreign"),
        ("observed_at", "2026-10-30T00:00:00Z"),
    ],
)
def test_metric_quality_is_required_per_series(field: str, replacement: str) -> None:
    value = payload()
    observation(value, "cpu_usage")["quality"][field] = replacement
    assert_no_reduction(assess(value))


@pytest.mark.parametrize(
    "defect",
    [
        "coverage",
        "sample-count",
        "missing-usage",
        "missing-api",
        "active-hpa",
        "init-unknown",
        "runtime-unknown",
        "policy-window",
    ],
)
def test_missing_or_unreviewed_history_stays_blocked(defect: str) -> None:
    value = payload()
    metadata = value["kubernetes"][0]
    if defect == "coverage":
        observation(value, "cpu_usage")["quality"]["window"]["coverage_ratio"] = 0.84
    elif defect == "sample-count":
        observation(value, "cpu_usage")["quality"]["window"]["sample_count"] = 1
    elif defect == "missing-usage":
        value["metrics"][0]["observations"].remove(observation(value, "cpu_usage"))
    elif defect == "missing-api":
        metadata["api_availability"].pop("autoscaling/v2/horizontalpodautoscalers")
    elif defect == "active-hpa":
        metadata["resources"].append(
            {
                "api_version": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "name": "synthetic-hpa",
                "namespace": "synthetic",
                "uid": "hpa-uid",
            }
        )
    elif defect in {"init-unknown", "runtime-unknown"}:
        pod = next(item for item in metadata["resources"] if item["kind"] == "Pod")
        pod["spec"].pop("initContainers" if defect == "init-unknown" else "runtimeClassName")
    else:
        value["workload_assessments"][0]["safety_policy"]["reviewed_window_start"] = (
            "2026-09-30T00:00:00Z"
        )
    assert_no_reduction(assess(value))


@pytest.mark.parametrize("kind", ["azure", "kubernetes", "metrics"])
@pytest.mark.parametrize(
    "defect, reason",
    [
        ("partial", "incomplete_collection"),
        ("unknown", "unknown_source_freshness"),
        ("stale", "stale_source"),
    ],
)
def test_complete_metrics_never_override_own_source_receipt(
    kind: str, defect: str, reason: str
) -> None:
    value = payload()
    receipt = value[kind][0]["collection"]
    if defect == "partial":
        receipt.update(status="partial", missing_fields=["unobserved-required-field"])
    else:
        receipt["source_observed_at"] = None if defect == "unknown" else "2026-10-27T00:00:00Z"
    result = assess(value)
    assert_no_reduction(result)
    assert any(reason in item.reason_codes for item in result.report.blocked_recommendations)


@pytest.mark.parametrize(
    "field, replacement, reason",
    [
        ("disruption_reviewed", False, "unreviewed_disruption"),
        ("maximum_cpu_throttled_ratio", 0.0001, "elevated_throttling"),
    ],
)
def test_policy_declaration_is_not_change_approval(
    field: str, replacement: Any, reason: str
) -> None:
    value = payload()
    value["workload_assessments"][0]["safety_policy"][field] = replacement
    result = assess(value)
    assert_no_reduction(result)
    assert any(reason in item.reason_codes for item in result.report.blocked_recommendations)


def test_observed_peaks_cannot_be_hidden_by_low_percentiles() -> None:
    value = payload()
    item = observation(value, "cpu_usage")
    item["maximum"] = item["quality"]["maximum"] = 1000
    result = assess(value)
    assert_no_reduction(result)
    assert any(
        "no_safe_reduction" in item.reason_codes for item in result.report.blocked_recommendations
    )


def test_current_homogeneous_replicas_never_acquire_history_from_metrics() -> None:
    value = payload("replica-inventory-assessment")
    result = assess(value, config="azure-fragments-config")
    assert result.snapshot.clusters[0].workloads[0].replicas == 2
    assert len(result.workload_inventory) == 2
    assert all(item.current_only for item in result.workload_inventory)
    assert not result.workload_history
    assert any(
        "unknown_autoscaler" in item.reason_codes for item in result.report.blocked_recommendations
    )
    assert all(item.proposed_requests is None for item in result.report.recommendations)


@pytest.mark.parametrize(
    "defect",
    [
        "different-request",
        "one-unknown",
        "missing-pod",
        "duplicate-name",
        "bad-owner",
        "pending",
        "too-many",
    ],
)
def test_current_population_mismatch_stays_visible(defect: str) -> None:
    value = payload("replica-inventory-assessment")
    metadata = value["kubernetes"][0]
    pods = [item for item in metadata["resources"] if item["kind"] == "Pod"]
    if defect == "different-request":
        pods[1]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "1"
    elif defect == "one-unknown":
        pods[1]["spec"]["containers"] = [{"name": "api"}]
    elif defect == "missing-pod":
        metadata["resources"].remove(pods[1])
    elif defect == "duplicate-name":
        pods[1]["name"] = pods[0]["name"]
    elif defect == "bad-owner":
        pods[1]["owner_references"][0]["uid"] = "recreated-controller"
    elif defect == "pending":
        pods[1]["status"]["phase"] = "Pending"
    else:
        next(item for item in metadata["resources"] if item["kind"] == "StatefulSet")["spec"][
            "replicas"
        ] = 101
    result = assess(value, config="azure-fragments-config")
    assert "unsupported-workload-evidence" in {item.code for item in result.issues}
    assert "AKS-RQ-001" not in {item.rule_id for item in result.report.recommendations}


@pytest.mark.parametrize(
    "quantity", ["NaN", "-1m", "bad-unit", "1e9999", "1e-9999", "1e1000000", True, 1000]
)
def test_invalid_cpu_quantities_never_become_zero_requests(quantity: Any) -> None:
    pytest.importorskip("kubernetes.utils.quantity")
    value = payload("workload-assessment")
    container_payload(value)["resources"]["requests"]["cpu"] = quantity
    result = assess(value)
    assert "unsupported-workload-evidence" in {item.code for item in result.issues}
    assert not result.snapshot.clusters[0].workloads


@pytest.mark.parametrize("quantity, expected", [("1", 1000), ("500m", 500), ("1e-3", 1), ("0", 0)])
def test_valid_quantities_use_proven_parser_without_fabricating_usage(
    quantity: str, expected: float
) -> None:
    value = payload("workload-assessment")
    container_payload(value)["resources"]["requests"]["cpu"] = quantity
    result = assess(value)
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert resources.request_cpu_mcores == expected
    assert resources.usage_cpu_p95_mcores is None
    assert not resources.metric_quality


def test_parser_absence_is_a_gap_not_a_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(workload_normalization, "import_module", unavailable)
    value = payload("workload-assessment")
    container_payload(value)["resources"]["requests"]["cpu"] = "1"
    result = assess(value)
    assert "quantity-parser-unavailable" in {item.code for item in result.issues}
    assert not result.snapshot.clusters[0].workloads


def test_omitted_requests_remain_unknown_not_absent() -> None:
    value = payload("workload-assessment")
    container_payload(value).pop("resources")
    result = assess(value)
    assert not result.snapshot.clusters[0].workloads[0].containers[0].resources.cpu_request_observed
    assert "AKS-RQ-001" not in {item.rule_id for item in result.report.recommendations}
    assert "unknown-workload-request" in {item.code for item in result.issues}


@pytest.mark.parametrize(
    "defect", ["missing-cluster", "missing-kubernetes", "missing-metrics", "empty-series"]
)
def test_missing_evidence_stays_partial_and_visible(defect: str) -> None:
    value = payload()
    if defect == "missing-cluster":
        value["azure"][0]["clusters"] = []
    elif defect == "missing-kubernetes":
        value["kubernetes"] = []
    elif defect == "missing-metrics":
        value["metrics"] = []
    else:
        value["metrics"][0]["observations"] = []
    result = assess(value)
    assert_no_reduction(result)
    assert result.issues
    assert result.snapshot.collection_manifest


def test_denied_cluster_does_not_invalidate_complete_independent_sources() -> None:
    result = assess(payload("scoped-assessment"), config="scoped-assessment-config")
    assert {item.resource_id for item in result.report.recommendations} == {CLUSTER}
    assert result.status == "partial"
    assert result.snapshot.collection_manifest.status == "partial"
    assert "forbidden" in render_assessment_markdown(result)
    assert any(
        error.code == "forbidden"
        for receipt in result.snapshot.collection_manifest.source_results
        for error in receipt.errors
    )


def test_approved_envelope_covers_deleted_members_without_percentile_math() -> None:
    result = assess(envelope_payload())
    proposal = next(item for item in result.report.recommendations if item.rule_id == "AKS-RQ-002")
    assert proposal.proposed_requests.cpu_mcores == 500
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert resources.cpu_observation_basis == "replica-envelope"
    assert resources.usage_cpu_p95_mcores == 100
    assert resources.usage_cpu_p99_mcores == 150
    assert len(result.workload_history[0].binding.pod_uids) == 3


@pytest.mark.parametrize(
    "defect",
    [
        "wrong-membership",
        "missing-envelope",
        "partial-request",
        "missing-count",
        "oom",
        "missing-current-member",
    ],
)
def test_envelope_membership_and_guardrails_fail_closed(defect: str) -> None:
    value = envelope_payload()
    if defect == "wrong-membership":
        observation(value, "replica_cpu_envelope")["entity"]["membership_digest"] = "a" * 64
    elif defect == "missing-envelope":
        value["metrics"][0]["observations"].remove(observation(value, "replica_cpu_envelope"))
    elif defect == "partial-request":
        observation(value, "replica_cpu_request_min")["quality"]["window"]["coverage_ratio"] = 0.5
    elif defect == "missing-count":
        value["metrics"][0]["observations"].remove(observation(value, "observed_replicas"))
    elif defect == "oom":
        observation(value, "replica_oom_events")["total"] = 1
    else:
        value["workload_assessments"][0]["pod_uids"] = ["pod-uid"]
    assert_no_reduction(assess(value))


def test_stale_replay_and_input_immutability() -> None:
    fragments = AssessmentFragments.model_validate(payload())
    before = fragments.model_dump_json()
    first = assess_fragments(fragments, profile(), as_of=AS_OF)
    assert before == fragments.model_dump_json()
    assert first == assess_fragments(fragments, profile(), as_of=AS_OF)
    assert OfflineAssessment.model_validate_json(first.model_dump_json()) == first
    assert (
        analyze(
            FleetSnapshot.model_validate_json(first.snapshot.model_dump_json()),
            profile().analysis,
            as_of=AS_OF,
        )
        == first.report
    )
    stale = assess_fragments(fragments, profile(), as_of=datetime(2026, 11, 1, tzinfo=UTC))
    assert_no_reduction(stale)
    assert any(
        "stale_metrics" in item.reason_codes for item in stale.report.blocked_recommendations
    )


@pytest.mark.parametrize("defect", ["secret-kind", "environment", "arguments", "annotation-body"])
def test_unsanitized_exports_are_rejected_before_rendering(defect: str) -> None:
    value = payload()
    pod = next(item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod")
    if defect == "secret-kind":
        pod.update(kind="Secret", spec={"data": "synthetic-secret"})
    elif defect == "environment":
        pod["spec"]["containers"][0]["env"] = [{"name": "SYNTHETIC", "value": "synthetic-secret"}]
    elif defect == "arguments":
        pod["spec"]["containers"][0]["args"] = ["synthetic-secret"]
    else:
        pod.setdefault("attributes", {})["annotations"] = {"synthetic": "synthetic-secret"}
    with pytest.raises(ValueError):
        AssessmentFragments.model_validate(value)


def test_untrusted_display_values_are_escaped_and_no_network_is_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("offline assessment attempted external execution")

    value = payload()
    value["azure"][0]["clusters"][0]["name"] = "<script>synthetic</script>\n# forged"
    value["workload_assessments"][0]["safety_policy"]["owner"] = "<script>owner</script>"
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    rendered = render_assessment_markdown(assess(value))
    assert "<script>" not in rendered
    assert "\n# forged" not in rendered
    assert "&lt;script&gt;" in rendered


def test_cli_sanitizes_invalid_input_and_refuses_overwrite(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"credential":"synthetic-private-marker"}', encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["assess", "--fragments", str(invalid), "--config", "examples/pool-assessment-config.yaml"],
    )
    assert result.exit_code == 2
    assert "synthetic-private-marker" not in result.output
    existing = tmp_path / "report.md"
    existing.write_text("keep", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "--fragments",
            "examples/fixtures/history-assessment.json",
            "--config",
            "examples/pool-assessment-config.yaml",
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(existing),
        ],
    )
    assert result.exit_code == 1
    assert existing.read_text(encoding="utf-8") == "keep"


def test_schema_artifacts_match_one_executable_contract() -> None:
    for name, model in [
        ("assessment-fragments", AssessmentFragments),
        ("offline-assessment", OfflineAssessment),
    ]:
        assert (
            json.loads(Path(f"schemas/{name}.schema.json").read_text(encoding="utf-8"))
            == model.model_json_schema()
        )


def test_output_destination_is_not_evidence(tmp_path: Path) -> None:
    settings = profile()
    first = assess_fragments(AssessmentFragments.model_validate(payload()), settings, as_of=AS_OF)
    settings.report_directory = tmp_path / "different-checkout"
    second = assess_fragments(AssessmentFragments.model_validate(payload()), settings, as_of=AS_OF)
    assert first.profile_digest == second.profile_digest
