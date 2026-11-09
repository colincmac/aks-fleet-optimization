from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_assessment import AS_OF, assess, envelope_payload, memory_safety_payload, observation
from test_rules_autoscalers import controller
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import FleetSnapshot, Recommendation
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown
from aks_fleet_efficiency.rules.engine import analyze
from scripts.verify import _verify_memory_shape


def add_evictions(value: dict[str, Any], count: int = 0) -> None:
    template = observation(
        value,
        "replica_oom_events"
        if any(
            item["metric"] == "replica_oom_events" for item in value["metrics"][0]["observations"]
        )
        else "oom_events",
    )
    item = json.loads(json.dumps(template))
    item["entity"] = json.loads(json.dumps(observation(value, "desired_replicas")["entity"]))
    item.update(metric="evictions", minimum=0, p50=0, p95=0, p99=0, maximum=count, total=count)
    item["quality"].update(unit="events", minimum=0, maximum=count)
    value["metrics"][0]["observations"].append(item)


def limit_payload() -> dict[str, Any]:
    value = memory_safety_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"]["api"][
        "allow_request_reduction"
    ] = False
    total = json.loads(json.dumps(observation(value, "memory_usage")))
    total.update(metric="memory_total_usage", minimum=128, p50=256, p95=320, p99=384, maximum=400)
    total["quality"].update(minimum=128, maximum=400)
    value["metrics"][0]["observations"].append(total)
    add_evictions(value)
    value["kubernetes"][0]["api_availability"]["v1/limitranges"] = "available"
    value["kubernetes"][0]["resource_versions"]["v1/limitranges"] = "synthetic-limits-version"
    value["workload_assessments"][0]["safety_policy"]["memory_limits"] = {
        "api": {
            "allow_limit_reduction": True,
            "minimum_limit_mib": 512,
            "maximum_reduction_ratio": 0.5,
            "headroom_factor": 1.25,
            "startup_total_peak_mib": 448,
            "failover_total_peak_mib": 480,
            "allocator_cache_reviewed": True,
            "evidence_reference": "synthetic-total-memory-review",
        }
    }
    from aks_fleet_efficiency.rules.memory import memory_limit_configuration_digest

    value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"][
        "configuration_digest"
    ] = memory_limit_configuration_digest(assess(value).snapshot.clusters[0].workloads[0])
    return value


def replica_memory_payload() -> dict[str, Any]:
    value = envelope_payload()
    value["kubernetes"][0]["api_availability"]["v1/limitranges"] = "available"
    value["kubernetes"][0]["resource_versions"]["v1/limitranges"] = "synthetic-limits-version"
    direct = memory_safety_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"] = direct["workload_assessments"][0][
        "safety_policy"
    ]["memory"]
    value["workload_assessments"][0]["safety_policy"]["memory"]["api"][
        "allow_request_reduction"
    ] = True
    for pod in [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]:
        pod["spec"]["containers"][0]["resources"].update(
            requests={"cpu": "1", "memory": "512Mi"}, limits={"memory": "1Gi"}
        )
        pod["status"]["qosClass"] = "Burstable"
    keys = {
        "memory_usage": ["replica_memory_envelope"],
        "memory_request": ["replica_memory_request_min", "replica_memory_request_max"],
        "memory_limit": ["replica_memory_limit_min", "replica_memory_limit_max"],
        "restarts": ["replica_restarts"],
    }
    for original in direct["metrics"][0]["observations"]:
        for metric in keys.get(original["metric"], []):
            item = json.loads(json.dumps(original))
            item["entity"] = json.loads(
                json.dumps(observation(value, "replica_cpu_envelope")["entity"])
            )
            item["metric"] = metric
            value["metrics"][0]["observations"].append(item)
    add_evictions(value)
    return value


def finding(value: dict[str, Any], rule_id: str) -> Recommendation:
    return next(item for item in assess(value).report.recommendations if item.rule_id == rule_id)


def blocked(value: dict[str, Any], rule_id: str) -> list[str]:
    report = assess(value).report
    assert not any(item.rule_id == rule_id for item in report.recommendations)
    return next(
        item.reason_codes for item in report.blocked_recommendations if item.rule_id == rule_id
    )


def test_full_memory_limit_proposal_is_separate_default_off_and_replayable() -> None:
    value = limit_payload()
    result = assess(value)
    rec = finding(value, "AKS-MEM-005")
    assert rec.current_limits.memory_mib == 1024
    assert rec.proposed_limits.memory_mib == 600
    assert rec.proposed_requests is None
    assert rec.current_requests is None
    assert rec.estimated_monthly_savings is None
    assert rec.owner and rec.prerequisites and rec.validation_steps and rec.rollback_steps
    assert "1024" in " ".join(rec.rollback_steps)
    assert "Memory limit" in render_assessment_markdown(result)
    assert analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF) == result.report
    assert FleetSnapshot.model_validate_json(result.snapshot.model_dump_json()) == result.snapshot
    value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"].pop(
        "allow_limit_reduction"
    )
    assert "memory_limit_reduction_not_enabled" in blocked(value, "AKS-MEM-005")


@pytest.mark.parametrize(
    "defect",
    [
        "total-missing",
        "working-set-only",
        "coverage",
        "oom",
        "restart",
        "eviction",
        "startup",
        "failover",
        "allocator",
        "minimum",
        "headroom",
        "digest",
        "request",
        "qos",
        "overhead",
        "owner",
        "controller",
    ],
)
def test_memory_limits_require_every_independent_guard(defect: str) -> None:
    value = limit_payload()
    policy = value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"]
    if defect in {"total-missing", "working-set-only"}:
        value["metrics"][0]["observations"].remove(observation(value, "memory_total_usage"))
    elif defect == "coverage":
        observation(value, "memory_total_usage")["quality"]["window"]["coverage_ratio"] = 0.99
    elif defect in {"oom", "restart", "eviction"}:
        item = observation(
            value, {"oom": "oom_events", "restart": "restarts", "eviction": "evictions"}[defect]
        )
        item["maximum"] = item["quality"]["maximum"] = item["total"] = 1
    elif defect in {"startup", "failover"}:
        policy.pop(f"{defect}_total_peak_mib")
    elif defect == "allocator":
        policy["allocator_cache_reviewed"] = False
    elif defect == "minimum":
        policy["minimum_limit_mib"] = 1024
    elif defect == "headroom":
        policy["headroom_factor"] = 3
    elif defect == "digest":
        policy["configuration_digest"] = "0" * 64
    elif defect == "request":
        for pod in [item for item in value["kubernetes"][0]["resources"] if item["kind"] == "Pod"]:
            pod["spec"]["containers"][0]["resources"]["requests"]["memory"] = "768Mi"
    elif defect == "qos":
        controller(value, "Pod")["status"]["qosClass"] = "Guaranteed"
    elif defect == "overhead":
        controller(value, "Pod")["spec"]["overhead"] = {"memory": "32Mi"}
    elif defect == "owner":
        value["workload_assessments"][0]["safety_policy"]["owner"] = " "
    else:
        value["kubernetes"][0]["api_availability"]["autoscaling/v2/horizontalpodautoscalers"] = (
            "unsupported"
        )
        value["kubernetes"][0]["resource_versions"].pop("autoscaling/v2/horizontalpodautoscalers")
    assert blocked(value, "AKS-MEM-005")


def test_replica_churn_memory_envelopes_never_sum_percentiles_and_support_guarded_requests() -> (
    None
):
    value = replica_memory_payload()
    result = assess(value)
    rec = finding(value, "AKS-MEM-003")
    assert rec.rule_version == "2.0.0"
    assert rec.proposed_requests.memory_mib == 313
    assert rec.proposed_limits is None
    resources = result.snapshot.clusters[0].workloads[0].containers[0].resources
    assert resources.memory_observation_basis == "replica-envelope"
    assert resources.usage_memory_p99_mib == 192
    assert resources.memory_membership_digest
    assert analyze(result.snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF) == result.report


@pytest.mark.parametrize(
    "defect", ["missing-max", "changed-request", "roster", "coverage", "eviction", "restart"]
)
def test_replica_memory_missing_or_unsafe_history_blocks_requests(defect: str) -> None:
    value = replica_memory_payload()
    if defect == "missing-max":
        value["metrics"][0]["observations"].remove(observation(value, "replica_memory_request_max"))
    elif defect == "changed-request":
        observation(value, "replica_memory_request_max")["maximum"] = 768
        observation(value, "replica_memory_request_max")["quality"]["maximum"] = 768
    elif defect == "roster":
        observation(value, "replica_memory_envelope")["entity"]["membership_digest"] = "0" * 64
    elif defect == "coverage":
        observation(value, "replica_memory_envelope")["quality"]["window"]["coverage_ratio"] = 0.99
    else:
        item = observation(value, "evictions" if defect == "eviction" else "replica_restarts")
        item["maximum"] = item["quality"]["maximum"] = item["total"] = 1
    assert blocked(value, "AKS-MEM-003")


def test_replica_restart_total_survives_missing_cpu_usage_without_inventing_cause() -> None:
    value = replica_memory_payload()
    value["metrics"][0]["observations"].remove(observation(value, "replica_cpu_envelope"))
    item = observation(value, "replica_restarts")
    item["maximum"] = item["quality"]["maximum"] = item["total"] = 3
    rec = finding(value, "AKS-REL-001")
    assert rec.rule_version == "2.0.0"
    assert next(item.value for item in rec.evidence if item.metric == "restart_events") == 3
    assert rec.proposed_requests is None and rec.proposed_limits is None


def test_collected_workload_evictions_are_reported_once_and_veto_owner_zero() -> None:
    value = limit_payload()
    item = observation(value, "evictions")
    item["maximum"] = item["quality"]["maximum"] = item["total"] = 2
    rec = finding(value, "AKS-REL-003")
    assert (
        next(item.value for item in rec.evidence if item.metric == "workload_eviction_events") == 2
    )
    assert blocked(value, "AKS-MEM-005")
    assert blocked(value, "AKS-MEM-003")


def test_effective_pod_memory_accounts_for_ordered_restartable_init_and_overhead() -> None:
    value = memory_safety_payload()
    pod = controller(value, "Pod")
    pod["spec"]["initContainers"] = [
        {
            "name": "sidecar-a",
            "restartPolicy": "Always",
            "resources": {"requests": {"memory": "128Mi"}},
        },
        {"name": "initialize", "resources": {"requests": {"memory": "1Gi"}}},
        {
            "name": "sidecar-b",
            "restartPolicy": "Always",
            "resources": {"requests": {"memory": "64Mi"}},
        },
    ]
    pod["spec"]["overhead"] = {"memory": "32Mi"}
    rec = finding(value, "AKS-MEM-004")
    evidence = {item.metric: item.value for item in rec.evidence}
    assert evidence["effective_pod_memory_request"] == 1184
    assert rec.proposed_requests is None and rec.proposed_limits is None
    assert blocked(value, "AKS-MEM-003")


def test_last_termination_reason_is_uid_bound_current_context_not_the_cause_of_all_restarts() -> (
    None
):
    value = memory_safety_payload()
    controller(value, "Pod")["status"]["containerStatuses"] = [
        {
            "name": "api",
            "lastState": {
                "terminated": {
                    "reason": "Error",
                    "exitCode": 137,
                    "finishedAt": "2026-10-28T23:55:00Z",
                }
            },
        }
    ]
    rec = finding(value, "AKS-REL-002")
    assert any(
        item.metric == "reported_termination_reason" and item.value == "Error"
        for item in rec.evidence
    )
    assert "all restarts" in rec.summary
    assert rec.proposed_requests is None and rec.proposed_limits is None


def test_limit_cli_artifacts_preserve_exact_one_dimension_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "synthetic-limit.json"
    source.write_text(json.dumps(limit_payload()), encoding="utf-8")
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
    report = json.loads(result.output)["report"]
    rec = next(item for item in report["recommendations"] if item["rule_id"] == "AKS-MEM-005")
    assert rec["proposed_limits"]["memory_mib"] == 600
    assert rec["proposed_requests"] is None
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
    assert json.loads(replay.output) == report


@pytest.mark.parametrize(
    "metric",
    ["memory_total_usage", "memory_request", "memory_limit", "oom_events", "restarts", "evictions"],
)
@pytest.mark.parametrize("defect", ["missing", "partial", "fractional"])
def test_limit_required_series_never_defaults_missing_or_partial_history(
    metric: str, defect: str
) -> None:
    value = limit_payload()
    item = observation(value, metric)
    if defect == "missing":
        value["metrics"][0]["observations"].remove(item)
    elif defect == "partial":
        item["quality"]["window"]["coverage_ratio"] = 0.84
    elif metric in {"oom_events", "restarts", "evictions"}:
        item["maximum"] = item["quality"]["maximum"] = item["total"] = 0.5
    else:
        item["minimum"] = item["quality"]["minimum"] = 0.5
    assert blocked(value, "AKS-MEM-005")


@pytest.mark.parametrize("peak, target", [(480, 600), (818.4, 1023), (819.2, None)])
def test_limit_upward_rounding_never_crosses_current_limit(peak: float, target: int | None) -> None:
    value = limit_payload()
    value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"][
        "failover_total_peak_mib"
    ] = peak
    if target is None:
        assert "no_safe_memory_limit_reduction" in blocked(value, "AKS-MEM-005")
    else:
        assert finding(value, "AKS-MEM-005").proposed_limits.memory_mib == target


@pytest.mark.parametrize("invalid", ["true", 1, None])
def test_memory_limit_opt_in_is_strict(invalid: object) -> None:
    value = limit_payload()
    value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"][
        "allow_limit_reduction"
    ] = invalid
    with pytest.raises(ValueError):
        assess(value)


@pytest.mark.parametrize("hours", [25, -24])
def test_limit_never_uses_stale_or_future_evidence(hours: int) -> None:
    report = assess(limit_payload(), as_of=AS_OF + timedelta(hours=hours)).report
    assert not any(item.rule_id == "AKS-MEM-005" for item in report.recommendations)
    assert any(item.rule_id == "AKS-MEM-005" for item in report.blocked_recommendations)


def test_limit_total_memory_peak_cannot_be_smaller_than_working_set_peak() -> None:
    value = limit_payload()
    item = observation(value, "memory_total_usage")
    item.update(minimum=64, p50=80, p95=100, p99=110, maximum=120)
    item["quality"].update(minimum=64, maximum=120)
    assert "contradictory_total_memory_peak" in blocked(value, "AKS-MEM-005")


def test_unknown_total_memory_does_not_disable_the_existing_request_only_rule() -> None:
    value = memory_safety_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"]["api"][
        "allow_request_reduction"
    ] = True
    assert finding(value, "AKS-MEM-003").proposed_requests.memory_mib == 313
    assert blocked(value, "AKS-MEM-005")


def test_envelope_limits_remain_unsupported_even_when_owner_opts_in() -> None:
    value = replica_memory_payload()
    value["workload_assessments"][0]["safety_policy"]["memory_limits"] = limit_payload()[
        "workload_assessments"
    ][0]["safety_policy"]["memory_limits"]
    assert "unsupported_memory_limit_history" in blocked(value, "AKS-MEM-005")


@pytest.mark.parametrize("field", ["initContainers", "overhead"])
def test_unknown_effective_pod_components_are_not_zero(field: str) -> None:
    value = memory_safety_payload()
    controller(value, "Pod")["spec"].pop(field)
    assert "unsupported_or_unknown_effective_pod_memory" in blocked(value, "AKS-MEM-004")


def test_pod_level_resources_are_explicitly_unsupported_not_ignored() -> None:
    value = memory_safety_payload()
    controller(value, "Pod")["spec"]["resources"] = {"requests": {"memory": "2Gi"}}
    assert blocked(value, "AKS-MEM-004")
    assert blocked(value, "AKS-MEM-003")


def test_effective_pod_accounting_respects_native_sidecar_startup_order() -> None:
    value = memory_safety_payload()
    pod = controller(value, "Pod")
    pod["spec"]["initContainers"] = [
        {"name": "a", "restartPolicy": "Always", "resources": {"requests": {"memory": "128Mi"}}},
        {"name": "b", "restartPolicy": "Always", "resources": {"requests": {"memory": "64Mi"}}},
        {"name": "c", "resources": {"requests": {"memory": "1Gi"}}},
    ]
    pod["spec"]["overhead"] = {"memory": "32Mi"}
    rec = finding(value, "AKS-MEM-004")
    assert (
        next(item.value for item in rec.evidence if item.metric == "effective_pod_memory_request")
        == 1248
    )


@pytest.mark.parametrize("defect", ["container", "time", "missing", "duplicate"])
def test_termination_context_is_honest_about_identity_and_causal_unknowns(defect: str) -> None:
    value = memory_safety_payload()
    status = {
        "name": "api",
        "lastState": {
            "terminated": {
                "reason": "OOMKilled",
                "exitCode": 137,
                "finishedAt": "2026-10-28T23:55:00Z",
            }
        },
    }
    if defect == "container":
        status["name"] = "synthetic-other"
    elif defect == "time":
        status["lastState"]["terminated"]["finishedAt"] = "2026-10-30T00:00:00Z"
    elif defect == "missing":
        status["lastState"]["terminated"].pop("reason")
    controller(value, "Pod")["status"]["containerStatuses"] = (
        [status, status.copy()] if defect == "duplicate" else [status]
    )
    assert "unsupported_termination_context" in blocked(value, "AKS-REL-002")
    assert blocked(value, "AKS-MEM-003")


def test_termination_text_is_escaped_and_message_payload_is_never_collected() -> None:
    value = memory_safety_payload()
    status = {
        "name": "api",
        "lastState": {
            "terminated": {
                "reason": "<script>alert(1)</script>",
                "exitCode": 137,
                "finishedAt": "2026-10-28T23:55:00Z",
            }
        },
    }
    controller(value, "Pod")["status"]["containerStatuses"] = [status]
    text = render_assessment_markdown(assess(value))
    assert "<script>" not in text and "&lt;script&gt;" in text
    status["lastState"]["terminated"]["message"] = "synthetic-excluded-payload"
    with pytest.raises(ValueError, match="approved projection"):
        assess(value)


def test_collected_zero_evictions_produce_no_reliability_finding() -> None:
    result = assess(limit_payload())
    assert not any(item.rule_id == "AKS-REL-003" for item in result.report.recommendations)
    assert not any(item.rule_id == "AKS-REL-003" for item in result.report.blocked_recommendations)


def test_request_and_limit_proposals_cannot_be_combined_in_one_finding() -> None:
    value = finding(limit_payload(), "AKS-MEM-005").model_dump(mode="json")
    value["proposed_requests"] = {"memory_mib": 256}
    with pytest.raises(ValueError, match="one dimension"):
        Recommendation.model_validate(value)


def test_limit_must_remain_strictly_above_observed_total_peak_even_at_unit_headroom() -> None:
    value = limit_payload()
    policy = value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"]
    policy["headroom_factor"] = 1
    item = observation(value, "memory_total_usage")
    item["maximum"] = item["quality"]["maximum"] = 600
    assert finding(value, "AKS-MEM-005").proposed_limits.memory_mib == 601


@pytest.mark.parametrize("bound", ["minimum", "maximum", "ratio", "pod"])
def test_known_memory_admission_constraints_cannot_be_bypassed(bound: str) -> None:
    value = limit_payload()
    constraint = {
        "type": "Pod" if bound == "pod" else "Container",
        **({"min": {"memory": "1Gi"}} if bound in {"minimum", "pod"} else {}),
        **({"max": {"memory": "512Mi"}} if bound == "maximum" else {}),
        **({"maxLimitRequestRatio": {"memory": "1"}} if bound == "ratio" else {}),
    }
    value["kubernetes"][0]["resources"].append(
        {
            "api_version": "v1",
            "kind": "LimitRange",
            "name": "synthetic-memory-limits",
            "namespace": "synthetic",
            "uid": "synthetic-memory-limits-uid",
            "spec": {"limits": [constraint]},
        }
    )
    assert blocked(value, "AKS-MEM-005")


def test_memory_limit_requires_observed_admission_lists_even_after_digest_resealing() -> None:
    value = limit_payload()
    value["kubernetes"][0]["resource_versions"].pop("v1/limitranges")
    from aks_fleet_efficiency.rules.memory import memory_limit_configuration_digest

    value["workload_assessments"][0]["safety_policy"]["memory_limits"]["api"][
        "configuration_digest"
    ] = memory_limit_configuration_digest(assess(value).snapshot.clusters[0].workloads[0])
    assert "unobserved_memory_admission" in blocked(value, "AKS-MEM-005")


@pytest.mark.parametrize("case", ["memory-envelope", "memory-limit", "memory-context"])
def test_packaged_memory_shapes_check_actual_outputs_and_reject_missing_findings(case: str) -> None:
    value = json.loads(
        (Path("examples") / "fixtures" / f"{case}-assessment.json").read_text(encoding="utf-8")
    )
    result = assess(value).model_dump(mode="json")
    _verify_memory_shape(case, result)
    result["report"]["recommendations"] = []
    with pytest.raises(RuntimeError, match="must contain one"):
        _verify_memory_shape(case, result)


@pytest.mark.parametrize("bound", ["minimum", "maximum", "ratio", "unchanged-limit"])
def test_request_proposals_respect_known_admission_and_unchanged_limit(bound: str) -> None:
    value = limit_payload()
    value["workload_assessments"][0]["safety_policy"]["memory"]["api"][
        "allow_request_reduction"
    ] = True
    constraint = {
        "type": "Container",
        **({"min": {"memory": "512Mi"}} if bound == "minimum" else {}),
        **(
            {"max": {"memory": "256Mi" if bound == "maximum" else "512Mi"}}
            if bound in {"maximum", "unchanged-limit"}
            else {}
        ),
        **({"maxLimitRequestRatio": {"memory": "2"}} if bound == "ratio" else {}),
    }
    value["kubernetes"][0]["resources"].append(
        {
            "api_version": "v1",
            "kind": "LimitRange",
            "name": "synthetic-request-limits",
            "namespace": "synthetic",
            "uid": "synthetic-request-limits-uid",
            "spec": {"limits": [constraint]},
        }
    )
    assert "memory_admission_constraint" in blocked(value, "AKS-MEM-003")
