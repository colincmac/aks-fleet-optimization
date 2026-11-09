import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.fixture import FixtureCollector
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import AutoscalingState, FleetSnapshot, Severity
from aks_fleet_efficiency.reporting.markdown import render_markdown
from aks_fleet_efficiency.rules.engine import analyze

FIXTURE = Path("examples/fixtures/fleet-snapshot.json")
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def eligible_snapshot_payload() -> dict[str, Any]:
    payload = FixtureCollector(FIXTURE).collect().model_dump(mode="json")
    payload.update(schema_version="1.0", generated_at="2026-10-29T11:02:00Z")
    window = {
        "start": "2026-09-29T00:00:00Z",
        "end": "2026-10-29T00:00:00Z",
        "sample_count": 8640,
        "coverage_ratio": 0.97,
    }
    payload["metric_window"] = window.copy()
    cluster = payload["clusters"][0]
    cluster["uid"] = "synthetic-cluster-uid"
    pool = cluster["node_pools"][0]
    pool["resource_id"] = f"{cluster['resource_id']}/agentPools/{pool['name']}"

    def quality(unit: str, maximum: float) -> dict[str, Any]:
        return {
            "source": payload["source"],
            "query_version": "synthetic-v1",
            "step_seconds": 300,
            "observed_at": "2026-10-29T11:00:00Z",
            "window": window.copy(),
            "unit": unit,
            "minimum": 0,
            "maximum": maximum,
        }

    pool["metric_quality"] = {"usage_cpu_p95_mcores": quality("mCPU", 6000)}
    for index, workload in enumerate(cluster["workloads"]):
        workload["uid"] = f"synthetic-workload-{index}"
        workload["autoscaling"]["vpa"] = False
        workload["autoscaling"]["vpa_mode"] = None
        workload["safety_policy"] = {
            "owner": "synthetic-owner",
            "slo_reference": "synthetic-policy/slo",
            "reviewed_window_start": window["start"],
            "reviewed_window_end": window["end"],
            "disruption_reviewed": True,
            "minimum_cpu_request_mcores": 100,
            "maximum_cpu_reduction_ratio": 0.5,
            "cpu_headroom_factor": 1.25,
            "maximum_cpu_throttled_ratio": 0.01,
        }
        for container in workload["containers"]:
            container["resources"]["cpu_request_observed"] = True
            container["resources"]["cpu_observation_basis"] = "pod"
            container["resources"]["restart_events"] = 0
            container["resources"]["metric_quality"] = {
                "usage_cpu_p95_mcores": quality("mCPU", 800 if index else 600),
                "usage_cpu_p99_mcores": quality("mCPU", 800 if index else 600),
                "cpu_throttled_ratio": quality("ratio", 0.01),
                "memory_oom_events": quality("events", 0),
                "restart_events": quality("events", 0),
            }
    results = []
    for collector in ["azure-inventory", "kubernetes-metadata", "prometheus"]:
        scope = (
            cluster["subscription_id"] if collector == "azure-inventory" else cluster["resource_id"]
        )
        results.append(
            {
                "collector": collector,
                "status": "complete",
                "requested_scope": [scope],
                "completed_scope": [scope],
                "started_at": "2026-10-29T11:00:00Z",
                "completed_at": "2026-10-29T11:01:00Z",
                "source_observed_at": "2026-10-29T11:00:00Z",
                "pagination_complete": True,
            }
        )
    payload["collection_manifest"] = {
        "tenant_id": "synthetic-tenant",
        "status": "complete",
        "results": results,
        "source_results": results,
    }
    return payload


def eligible_snapshot() -> FleetSnapshot:
    return FleetSnapshot.model_validate(eligible_snapshot_payload())


def memory_review_payload() -> dict[str, Any]:
    value = eligible_snapshot_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["qos_class"] = "Burstable"
    workload["safety_policy"]["memory"] = {
        workload["containers"][0]["name"]: {
            "minimum_request_mib": 128,
            "maximum_reduction_ratio": 0.5,
            "headroom_factor": 1.25,
            "startup_peak_mib": 250,
            "failover_peak_mib": 300,
            "eviction_events": 0,
            "qos_class": "Burstable",
            "evidence_reference": "synthetic-review/memory",
        }
    }
    resources = workload["containers"][0]["resources"]
    resources.update(
        memory_request_observed=True,
        memory_limit_observed=True,
        memory_observation_basis="pod",
        request_memory_mib=1024,
        limit_memory_mib=2048,
        usage_memory_p95_mib=100,
        usage_memory_p99_mib=150,
    )
    for metric, minimum, maximum in [
        ("request_memory_mib", 1024, 1024),
        ("limit_memory_mib", 2048, 2048),
        ("usage_memory_p95_mib", 50, 200),
        ("usage_memory_p99_mib", 50, 200),
    ]:
        quality = json.loads(json.dumps(resources["metric_quality"]["memory_oom_events"]))
        quality.update(unit="MiB", minimum=minimum, maximum=maximum)
        resources["metric_quality"][metric] = quality
    return value


def memory_review_reasons(value: dict[str, Any], *, as_of: datetime = AS_OF) -> list[str]:
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=as_of
    )
    assert "AKS-MEM-002" not in {item.rule_id for item in report.recommendations}
    return next(
        item.reason_codes
        for item in report.blocked_recommendations
        if item.rule_id == "AKS-MEM-002"
        and item.workload == value["clusters"][0]["workloads"][0]["name"]
    )


def memory_proposal_payload() -> dict[str, Any]:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["replicas"] = 1
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]][
        "allow_request_reduction"
    ] = True
    for quality in workload["containers"][0]["resources"]["metric_quality"].values():
        quality["window"]["coverage_ratio"] = 1
    return value


def memory_proposal_reasons(value: dict[str, Any], *, as_of: datetime = AS_OF) -> list[str]:
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=as_of
    )
    assert "AKS-MEM-003" not in {item.rule_id for item in report.recommendations}
    return next(
        item.reason_codes
        for item in report.blocked_recommendations
        if item.rule_id == "AKS-MEM-003"
        and item.workload == value["clusters"][0]["workloads"][0]["name"]
    )


def test_memory_request_proposal_is_explicit_bounded_and_request_only() -> None:
    snapshot = FleetSnapshot.model_validate(memory_proposal_payload())
    before = snapshot.model_dump_json()
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-003")
    assert finding.rule_version == "2.0.0"
    assert finding.severity == Severity.MEDIUM
    assert finding.owner == "synthetic-owner"
    assert finding.current_requests.memory_mib == 1024
    assert finding.proposed_requests.memory_mib == 512
    assert finding.current_requests.cpu_mcores is None
    assert finding.proposed_requests.cpu_mcores is None
    assert finding.estimated_monthly_savings is None
    assert finding.currency is None
    evidence = {item.metric: item.value for item in finding.evidence}
    assert evidence["limit_memory_mib"] == 2048
    assert evidence["observed_memory_working_set_peak_mib"] == 200
    assert evidence["startup_peak_mib"] == 250
    assert evidence["failover_peak_mib"] == 300
    assert evidence["allow_request_reduction"] is True
    assert finding.prerequisites and finding.risks
    assert finding.validation_steps and finding.rollback_steps
    assert any("1024" in step for step in finding.rollback_steps)
    assert "limits unchanged" in " ".join(finding.proposed_actions).lower()
    readiness = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-002")
    assert readiness.proposed_requests is None
    assert snapshot.model_dump_json() == before
    assert report == analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)


@pytest.mark.parametrize("enabled", [None, False])
def test_memory_request_proposals_default_off_without_changing_readiness(
    enabled: bool | None,
) -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    policy = workload["safety_policy"]["memory"][workload["containers"][0]["name"]]
    if enabled is None:
        policy.pop("allow_request_reduction")
    else:
        policy["allow_request_reduction"] = enabled
    assert "memory_request_reduction_not_enabled" in memory_proposal_reasons(value)
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert any(item.rule_id == "AKS-MEM-002" for item in report.recommendations)


@pytest.mark.parametrize("enabled", [None, 0, 1, "true", "false"])
def test_memory_request_opt_in_requires_an_explicit_boolean(enabled: Any) -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]][
        "allow_request_reduction"
    ] = enabled
    with pytest.raises(ValueError):
        FleetSnapshot.model_validate(value)


@pytest.mark.parametrize(
    "field, amount, expected",
    [
        ("minimum_request_mib", 600.1, 601),
        ("maximum_reduction_ratio", 0.1, 922),
        ("startup_peak_mib", 600.1, 751),
        ("failover_peak_mib", 600.1, 751),
        ("headroom_factor", 2.1, 630),
    ],
)
def test_memory_request_target_obeys_every_owner_bound_and_rounds_up(
    field: str, amount: float, expected: float
) -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    policy = workload["safety_policy"]["memory"][workload["containers"][0]["name"]]
    policy[field] = amount
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-003")
    assert finding.proposed_requests.memory_mib == expected
    assert finding.proposed_requests.memory_mib >= policy["minimum_request_mib"]
    assert finding.proposed_requests.memory_mib >= 1024 * (1 - policy["maximum_reduction_ratio"])
    assert (
        finding.proposed_requests.memory_mib
        >= policy["startup_peak_mib"] * policy["headroom_factor"]
    )
    assert (
        finding.proposed_requests.memory_mib
        >= policy["failover_peak_mib"] * policy["headroom_factor"]
    )


def test_observed_memory_peak_not_p95_or_p99_drives_the_request_target() -> None:
    value = memory_proposal_payload()
    resources = value["clusters"][0]["workloads"][0]["containers"][0]["resources"]
    for metric in ["usage_memory_p95_mib", "usage_memory_p99_mib"]:
        resources["metric_quality"][metric]["maximum"] = 700.1
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-003")
    assert finding.proposed_requests.memory_mib == 876


@pytest.mark.parametrize(
    "metric",
    [
        "request_memory_mib",
        "limit_memory_mib",
        "usage_memory_p95_mib",
        "usage_memory_p99_mib",
        "memory_oom_events",
        "restart_events",
    ],
)
@pytest.mark.parametrize("defect", ["missing", "coverage", "samples", "stale", "unit"])
def test_numeric_memory_requires_complete_independent_metric_history(
    metric: str, defect: str
) -> None:
    value = memory_proposal_payload()
    resources = value["clusters"][0]["workloads"][0]["containers"][0]["resources"]
    quality = resources["metric_quality"][metric]
    as_of = AS_OF
    if defect == "missing":
        del resources["metric_quality"][metric]
        reason = "missing_metric_quality"
    elif defect == "coverage":
        quality["window"]["coverage_ratio"] = 0.999
        reason = "incomplete_memory_history"
    elif defect == "samples":
        quality["window"]["sample_count"] -= 1
        reason = "incomplete_memory_history"
    elif defect == "stale":
        quality["observed_at"] = "2026-10-29T00:00:00Z"
        as_of += timedelta(hours=12, seconds=1)
        reason = "stale_metric_observation"
    else:
        quality["unit"] = "unsupported"
        reason = "metric_unit_mismatch"
    assert reason in memory_proposal_reasons(value, as_of=as_of)


@pytest.mark.parametrize(
    "defect, reason",
    [
        ("replicas", "unsupported_memory_history"),
        ("basis", "unsupported_memory_history"),
        ("request-observation", "missing_memory_request_observation"),
        ("limit-observation", "missing_memory_limit_observation"),
        ("oom", "oom_history"),
        ("restart", "restart_history"),
        ("eviction", "eviction_history"),
        ("startup", "missing_startup_memory_review"),
        ("failover", "missing_failover_memory_review"),
        ("qos", "qos_preservation_review_required"),
        ("controller", "autoscaler_interaction_review_required"),
        ("window", "unreviewed_window"),
        ("owner", "missing_memory_owner"),
        ("slo", "missing_memory_slo_reference"),
        ("source", "incomplete_collection"),
    ],
)
def test_memory_numeric_proposals_cannot_bypass_readiness_or_owner_safety(
    defect: str, reason: str
) -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    resources = workload["containers"][0]["resources"]
    policy = workload["safety_policy"]["memory"][workload["containers"][0]["name"]]
    if defect == "replicas":
        workload["replicas"] = 2
    elif defect == "basis":
        resources["memory_observation_basis"] = None
    elif defect == "request-observation":
        resources["memory_request_observed"] = False
    elif defect == "limit-observation":
        resources["memory_limit_observed"] = False
    elif defect in {"oom", "restart"}:
        resources["memory_oom_events" if defect == "oom" else "restart_events"] = 1
    elif defect == "eviction":
        policy["eviction_events"] = 1
    elif defect in {"startup", "failover"}:
        policy[f"{defect}_peak_mib"] = None
    elif defect == "qos":
        workload["qos_class"] = policy["qos_class"] = "Guaranteed"
    elif defect == "controller":
        workload["autoscaling"]["hpa"] = True
    elif defect == "window":
        workload["safety_policy"]["reviewed_window_start"] = "2026-09-28T00:00:00Z"
    elif defect == "owner":
        workload["safety_policy"]["owner"] = "  "
    elif defect == "slo":
        workload["safety_policy"]["slo_reference"] = "  "
    else:
        receipt = value["collection_manifest"]["results"][2]
        receipt.update(status="partial", pagination_complete=False)
        value["collection_manifest"]["status"] = "partial"
    assert reason in memory_proposal_reasons(value)


def test_rounding_cannot_turn_a_memory_review_into_a_non_reduction() -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]][
        "minimum_request_mib"
    ] = 1023.1
    assert "no_safe_memory_reduction" in memory_proposal_reasons(value)
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert any(item.rule_id == "AKS-MEM-002" for item in report.recommendations)


def test_memory_numeric_and_cpu_proposals_are_independent() -> None:
    value = memory_proposal_payload()
    resources = value["clusters"][0]["workloads"][0]["containers"][0]["resources"]
    resources["usage_cpu_p95_mcores"] = None
    resources["usage_cpu_p99_mcores"] = None
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert any(item.rule_id == "AKS-MEM-003" for item in report.recommendations)
    assert not any(item.rule_id == "AKS-RQ-002" for item in report.recommendations)


def test_numeric_memory_low_coverage_cannot_be_offset_by_other_metrics() -> None:
    value = memory_proposal_payload()
    resources = value["clusters"][0]["workloads"][0]["containers"][0]["resources"]
    resources["metric_quality"]["usage_memory_p99_mib"]["window"]["coverage_ratio"] = 0.84
    reasons = memory_proposal_reasons(value)
    assert "low_entity_coverage" in reasons
    assert "incomplete_memory_history" in reasons


def test_memory_headroom_overflow_blocks_instead_of_crashing_or_proposing() -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]]["headroom_factor"] = (
        1e308
    )
    assert "insufficient_memory_headroom" in memory_proposal_reasons(value)


def test_numeric_memory_opt_in_cannot_transfer_to_another_container() -> None:
    value = memory_proposal_payload()
    workload = value["clusters"][0]["workloads"][0]
    name = workload["containers"][0]["name"]
    memory = workload["safety_policy"]["memory"]
    memory["synthetic-other-container"] = memory.pop(name)
    assert "missing_memory_safety_policy" in memory_proposal_reasons(value)


def test_memory_request_proposal_markdown_has_memory_units_not_null_cpu_values() -> None:
    report = analyze(
        FleetSnapshot.model_validate(memory_proposal_payload()),
        AdvisorConfig(mode="guarded"),
        as_of=AS_OF,
    )
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-003")
    report.recommendations = [finding]
    rendered = render_markdown(report)
    assert "**Memory request:** 1024.0 to 512.0 MiB per replica" in rendered
    assert "**CPU request:**" not in rendered
    assert "None to None" not in rendered


def test_memory_safety_review_is_not_a_numeric_proposal_or_savings_claim() -> None:
    snapshot = FleetSnapshot.model_validate(memory_review_payload())
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-002")
    assert finding.severity == Severity.INFO
    assert finding.rule_version == "2.0.0"
    assert finding.owner == "synthetic-owner"
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert finding.current_requests.memory_mib == 1024
    evidence = {item.metric: item for item in finding.evidence}
    assert evidence["observed_memory_working_set_peak_mib"].value == 200
    assert evidence["startup_peak_mib"].source == "owner-reviewed:synthetic-review/memory"
    assert evidence["failover_peak_mib"].value == 300
    assert evidence["reviewed_eviction_events"].value == 0
    assert finding.prerequisites and finding.risks
    assert finding.validation_steps and finding.rollback_steps
    assert "no numeric" in " ".join(finding.proposed_actions).lower()
    assert report == analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert snapshot == FleetSnapshot.model_validate_json(snapshot.model_dump_json())


@pytest.mark.parametrize(
    "path, replacement, reason",
    [
        (("safety_policy",), None, "missing_memory_safety_policy"),
        (("safety_policy", "memory"), {}, "missing_memory_safety_policy"),
        (("safety_policy", "disruption_reviewed"), False, "unreviewed_disruption"),
        (
            ("safety_policy", "reviewed_window_start"),
            "2026-09-28T00:00:00Z",
            "unreviewed_window",
        ),
        (("qos_class",), None, "unknown_qos_class"),
        (("qos_class",), "Guaranteed", "qos_class_mismatch"),
        (("autoscaling", "hpa"), True, "autoscaler_interaction_review_required"),
        (("autoscaling", "vpa"), None, "unknown_autoscaler"),
    ],
)
def test_memory_review_requires_workload_specific_safety(
    path: tuple[str, ...], replacement: Any, reason: str
) -> None:
    value = memory_review_payload()
    target = value["clusters"][0]["workloads"][0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    assert reason in memory_review_reasons(value)


@pytest.mark.parametrize(
    "field, replacement, reason",
    [
        ("startup_peak_mib", None, "missing_startup_memory_review"),
        ("failover_peak_mib", None, "missing_failover_memory_review"),
        ("eviction_events", None, "missing_eviction_review"),
        ("eviction_events", 1, "eviction_history"),
        ("qos_class", None, "unreviewed_qos_class"),
        ("qos_class", "Guaranteed", "qos_class_mismatch"),
        ("startup_peak_mib", 820, "insufficient_memory_headroom"),
        ("failover_peak_mib", 820, "insufficient_memory_headroom"),
        ("minimum_request_mib", 1024, "memory_policy_floor"),
    ],
)
def test_memory_owner_review_does_not_infer_missing_or_safe_scenarios(
    field: str, replacement: Any, reason: str
) -> None:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]][field] = replacement
    assert reason in memory_review_reasons(value)


@pytest.mark.parametrize(
    "field, replacement, reason",
    [
        ("memory_request_observed", False, "missing_memory_request_observation"),
        ("memory_limit_observed", False, "missing_memory_limit_observation"),
        ("memory_observation_basis", None, "unsupported_memory_history"),
        ("request_memory_mib", None, "missing_metric"),
        ("limit_memory_mib", None, "missing_metric"),
        ("limit_memory_mib", 1024, "memory_limit_change_review_required"),
        ("memory_oom_events", 1, "oom_history"),
        ("restart_events", 1, "restart_history"),
        ("usage_memory_p95_mib", 160, "inconsistent_memory_usage"),
    ],
)
def test_memory_review_requires_observed_bounds_and_reliability(
    field: str, replacement: Any, reason: str
) -> None:
    value = memory_review_payload()
    resources = value["clusters"][0]["workloads"][0]["containers"][0]["resources"]
    resources[field] = replacement
    assert reason in memory_review_reasons(value)


@pytest.mark.parametrize(
    "defect, reason",
    [
        ("missing-quality", "missing_metric_quality"),
        ("low-coverage", "low_entity_coverage"),
        ("stale", "stale_metric_observation"),
        ("short", "short_window"),
        ("unit", "metric_unit_mismatch"),
        ("peak", "missing_memory_peak"),
        ("changing-request", "unstable_memory_request"),
        ("changing-limit", "unstable_memory_limit"),
        ("partial-source", "incomplete_collection"),
        ("missing-identity", "missing_identity"),
    ],
)
def test_memory_review_keeps_metric_and_collection_gates(defect: str, reason: str) -> None:
    value = memory_review_payload()
    cluster = value["clusters"][0]
    resources = cluster["workloads"][0]["containers"][0]["resources"]
    quality = resources["metric_quality"]["usage_memory_p99_mib"]
    if defect == "missing-quality":
        del resources["metric_quality"]["usage_memory_p99_mib"]
    elif defect == "low-coverage":
        quality["window"]["coverage_ratio"] = 0.84
    elif defect == "stale":
        quality["observed_at"] = "2026-10-29T00:00:00Z"
        return_time = AS_OF + timedelta(hours=12, seconds=1)
        assert reason in memory_review_reasons(value, as_of=return_time)
        return
    elif defect == "short":
        value["metric_window"]["start"] = "2026-10-28T00:00:00Z"
    elif defect == "unit":
        quality["unit"] = "bytes"
    elif defect == "peak":
        quality["maximum"] = None
    elif defect in {"changing-request", "changing-limit"}:
        field = "request_memory_mib" if defect == "changing-request" else "limit_memory_mib"
        resources["metric_quality"][field]["minimum"] = 0
    elif defect == "partial-source":
        receipt = value["collection_manifest"]["results"][2]
        receipt.update(status="partial", pagination_complete=False)
        value["collection_manifest"]["status"] = "partial"
    else:
        cluster["uid"] = None
    assert reason in memory_review_reasons(value)


def test_memory_review_coverage_and_peak_headroom_boundaries() -> None:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    resources = workload["containers"][0]["resources"]
    for quality in resources["metric_quality"].values():
        quality["window"]["coverage_ratio"] = 0.85
    policy = workload["safety_policy"]["memory"][workload["containers"][0]["name"]]
    policy["failover_peak_mib"] = 819.2
    assert "insufficient_memory_headroom" in memory_review_reasons(value)
    policy["failover_peak_mib"] = 819.19
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-002")
    assert finding.confidence.value == "medium"


def test_memory_review_does_not_borrow_another_containers_policy() -> None:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    policy = workload["safety_policy"]["memory"].pop(workload["containers"][0]["name"])
    workload["safety_policy"]["memory"]["synthetic-other-container"] = policy
    assert "missing_memory_safety_policy" in memory_review_reasons(value)


def test_memory_review_reference_is_untrusted_text_not_an_executable_link() -> None:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]]["evidence_reference"] = (
        "<script>review</script>\n# forged [click](javascript:alert(1))"
    )
    rendered = render_markdown(
        analyze(FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=AS_OF)
    )
    assert "<script>" not in rendered
    assert "\n# forged" not in rendered
    assert "[click](javascript:" not in rendered
    assert "&lt;script&gt;" in rendered


@pytest.mark.parametrize("qos", ["Guaranteed", "BestEffort"])
def test_memory_review_does_not_authorize_a_qos_transition(qos: str) -> None:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["qos_class"] = qos
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]]["qos_class"] = qos
    assert "qos_preservation_review_required" in memory_review_reasons(value)


@pytest.mark.parametrize("metric", ["memory_oom_events", "restart_events"])
def test_memory_review_zero_total_cannot_hide_positive_reliability_intervals(metric: str) -> None:
    value = memory_review_payload()
    resources = value["clusters"][0]["workloads"][0]["containers"][0]["resources"]
    resources["metric_quality"][metric]["maximum"] = 1
    assert "inconsistent_reliability_history" in memory_review_reasons(value)


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("minimum_request_mib", 0),
        ("minimum_request_mib", True),
        ("maximum_reduction_ratio", 0),
        ("maximum_reduction_ratio", 1),
        ("headroom_factor", 0.99),
        ("headroom_factor", float("inf")),
        ("startup_peak_mib", -1),
        ("startup_peak_mib", 0),
        ("failover_peak_mib", float("nan")),
        ("eviction_events", -1),
        ("eviction_events", 0.5),
        ("eviction_events", True),
        ("eviction_events", "0"),
        ("evidence_reference", ""),
        ("evidence_reference", "  "),
        ("qos_class", "unknown"),
    ],
)
def test_memory_policy_rejects_invalid_or_ambiguous_evidence(field: str, replacement: Any) -> None:
    value = memory_review_payload()
    workload = value["clusters"][0]["workloads"][0]
    workload["safety_policy"]["memory"][workload["containers"][0]["name"]][field] = replacement
    with pytest.raises(ValueError):
        FleetSnapshot.model_validate(value)


def test_oom_investigation_does_not_depend_on_cpu_request_or_usage() -> None:
    snapshot = eligible_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.request_cpu_mcores = None
    resources.usage_cpu_p95_mcores = None
    resources.memory_oom_events = 2
    resources.metric_quality["memory_oom_events"].maximum = 2
    resources.usage_memory_p95_mib = 128
    resources.usage_memory_p99_mib = 256
    for metric in ["usage_memory_p95_mib", "usage_memory_p99_mib"]:
        quality = resources.metric_quality["memory_oom_events"].model_copy(deep=True)
        quality.unit = "MiB"
        quality.minimum = 64
        quality.maximum = 512
        resources.metric_quality[metric] = quality
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-001")
    assert finding.severity == Severity.HIGH
    assert finding.rule_version == "2.0.0"
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert finding.owner == "synthetic-owner"
    assert finding.evidence[0].metric == "memory_oom_events"
    assert finding.evidence[0].value == 2
    assert finding.evidence[0].unit == "events"
    assert {item.metric: item.value for item in finding.evidence} == {
        "memory_oom_events": 2,
        "usage_memory_p95_mib": 128,
        "usage_memory_p99_mib": 256,
        "observed_memory_working_set_peak_mib": 512,
    }
    assert finding.prerequisites and finding.risks
    assert finding.validation_steps and finding.rollback_steps


@pytest.mark.parametrize(
    "metric, rule_id", [("memory_oom_events", "AKS-MEM-001"), ("restart_events", "AKS-REL-001")]
)
@pytest.mark.parametrize("count", [0, None])
def test_zero_and_unknown_reliability_history_are_distinct(
    metric: str, rule_id: str, count: int | None
) -> None:
    snapshot = eligible_snapshot()
    setattr(snapshot.clusters[0].workloads[0].containers[0].resources, metric, count)
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert rule_id not in {item.rule_id for item in report.recommendations}
    blocked = [item for item in report.blocked_recommendations if item.rule_id == rule_id]
    if count is None:
        assert len(blocked) == 1
        assert "missing_metric" in blocked[0].reason_codes
    else:
        assert not blocked


@pytest.mark.parametrize(
    "metric, rule_id", [("memory_oom_events", "AKS-MEM-001"), ("restart_events", "AKS-REL-001")]
)
@pytest.mark.parametrize(
    "defect, reason",
    [
        ("missing-quality", "missing_metric_quality"),
        ("unit", "metric_unit_mismatch"),
        ("coverage", "low_entity_coverage"),
        ("samples", "inconsistent_metric_coverage"),
        ("step", "coarse_metric_resolution"),
        ("alignment", "misaligned_metric_window"),
        ("short-window", "short_window"),
        ("stale", "stale_metric_observation"),
        ("missing-manifest", "missing_collection_manifest"),
        ("partial-source", "incomplete_collection"),
        ("wrong-scope", "missing_required_collector"),
        ("cluster-identity", "missing_identity"),
        ("workload-identity", "missing_identity"),
    ],
)
def test_reliability_investigation_requires_valid_evidence(
    metric: str, rule_id: str, defect: str, reason: str
) -> None:
    value = eligible_snapshot_payload()
    cluster = value["clusters"][0]
    workload = cluster["workloads"][0]
    resources = workload["containers"][0]["resources"]
    resources[metric] = 1
    quality = resources["metric_quality"][metric]
    quality["maximum"] = 1
    evaluated_at = AS_OF
    if defect == "missing-quality":
        del resources["metric_quality"][metric]
    elif defect == "unit":
        quality["unit"] = "MiB"
    elif defect == "coverage":
        quality["window"]["coverage_ratio"] = 0.84
    elif defect == "samples":
        quality["window"]["sample_count"] = 1
    elif defect == "step":
        quality["step_seconds"] = 600
    elif defect == "alignment":
        quality["window"]["start"] = "2026-09-30T00:00:00Z"
    elif defect == "short-window":
        value["metric_window"]["start"] = "2026-10-20T00:00:00Z"
    elif defect == "stale":
        evaluated_at += timedelta(days=2)
    elif defect == "missing-manifest":
        value["collection_manifest"] = None
    elif defect == "partial-source":
        value["collection_manifest"].update(status="partial")
        value["collection_manifest"]["source_results"][2].update(
            status="partial", pagination_complete=False
        )
    elif defect == "wrong-scope":
        value["collection_manifest"]["source_results"][2].update(
            requested_scope=["synthetic-other-cluster"], completed_scope=["synthetic-other-cluster"]
        )
    elif defect == "cluster-identity":
        cluster["uid"] = None
    else:
        workload["uid"] = None
    report = analyze(
        FleetSnapshot.model_validate(value), AdvisorConfig(mode="guarded"), as_of=evaluated_at
    )
    assert rule_id not in {item.rule_id for item in report.recommendations}
    blocked = next(item for item in report.blocked_recommendations if item.rule_id == rule_id)
    assert reason in blocked.reason_codes


@pytest.mark.parametrize(
    "metric, rule_id", [("memory_oom_events", "AKS-MEM-001"), ("restart_events", "AKS-REL-001")]
)
def test_reliability_investigation_boundaries_identity_and_replay(
    metric: str, rule_id: str
) -> None:
    snapshot = eligible_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    setattr(resources, metric, 1)
    resources.metric_quality[metric].maximum = 1
    resources.metric_quality[metric].window.coverage_ratio = 0.85
    boundary = snapshot.metric_window.end + timedelta(hours=24)
    before = snapshot.model_dump_json()
    first = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=boundary)
    finding = next(item for item in first.recommendations if item.rule_id == rule_id)
    assert finding.confidence.value == "medium"
    assert snapshot.model_dump_json() == before
    assert first == analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=boundary)
    expired = analyze(
        snapshot, AdvisorConfig(mode="guarded"), as_of=boundary + timedelta(microseconds=1)
    )
    assert rule_id not in {item.rule_id for item in expired.recommendations}
    snapshot.clusters[0].workloads[0].uid = "synthetic-recreated-workload"
    recreated = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=boundary)
    assert finding.id != next(
        item.id for item in recreated.recommendations if item.rule_id == rule_id
    )


def test_restart_investigation_does_not_infer_oom_or_require_cpu_or_absent_autoscalers() -> None:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    workload.autoscaling = AutoscalingState(hpa=True, keda=True, vpa=True, vpa_mode="Auto")
    resources = workload.containers[0].resources
    resources.memory_oom_events = None
    resources.usage_cpu_p95_mcores = None
    resources.request_cpu_mcores = None
    resources.restart_events = 1
    resources.metric_quality["restart_events"].maximum = 1
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-REL-001")
    assert finding.rule_version == "2.0.0"
    assert finding.severity == Severity.MEDIUM
    assert finding.owner == "synthetic-owner"
    assert finding.proposed_requests is None
    assert finding.estimated_monthly_savings is None
    assert finding.evidence[0].source == resources.metric_quality["restart_events"].source
    assert finding.prerequisites and finding.risks
    assert finding.validation_steps and finding.rollback_steps
    assert "count alone does not establish memory pressure" in finding.summary
    assert "AKS-MEM-001" not in {item.rule_id for item in report.recommendations}


@pytest.mark.parametrize("count", [-1, 0.5, float("nan"), float("inf")])
def test_restart_counts_must_be_nonnegative_integers(count: float) -> None:
    value = eligible_snapshot_payload()
    value["clusters"][0]["workloads"][0]["containers"][0]["resources"]["restart_events"] = count
    with pytest.raises(ValueError, match="restart_events"):
        FleetSnapshot.model_validate(value)


def test_invalid_optional_working_set_does_not_hide_valid_oom_risk() -> None:
    snapshot = eligible_snapshot()
    workload = snapshot.clusters[0].workloads[0]
    workload.autoscaling = AutoscalingState(hpa=True, vpa=True, vpa_mode="Auto", keda=True)
    resources = workload.containers[0].resources
    resources.memory_oom_events = 1
    resources.metric_quality["memory_oom_events"].maximum = 1
    resources.usage_memory_p95_mib = 128
    resources.usage_memory_p99_mib = 256
    quality = resources.metric_quality["memory_oom_events"].model_copy(deep=True)
    quality.unit = "bytes"
    quality.maximum = 512
    resources.metric_quality["usage_memory_p95_mib"] = quality
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-MEM-001")
    assert [item.metric for item in finding.evidence] == ["memory_oom_events"]
    assert finding.proposed_requests is None
    assert "AKS-RQ-002" not in {item.rule_id for item in report.recommendations}


def scoped_snapshot_payload() -> dict[str, Any]:
    payload = eligible_snapshot_payload()
    payload["schema_version"] = "1.0"
    manifest = payload["collection_manifest"]
    manifest["schema_version"] = "1.0"
    return payload


def test_scoped_rules_use_entity_quality_not_the_global_coverage_floor() -> None:
    payload = scoped_snapshot_payload()
    payload["metric_window"].update(coverage_ratio=0, sample_count=0)
    report = analyze(
        FleetSnapshot.model_validate(payload), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert report.schema_version == "1.0"
    reduction = next(item for item in report.recommendations if item.rule_id == "AKS-RQ-002")
    assert reduction.rule_version == "2.1.0"
    assert reduction.confidence.value == "high"
    assert reduction.estimated_monthly_savings is None
    assert report.summary.data_quality_warnings


@pytest.mark.parametrize(
    "defect, reason",
    [
        ("coverage", "low_entity_coverage"),
        ("sample-count", "inconsistent_metric_coverage"),
        ("missing-quality", "missing_metric_quality"),
        ("coarse-step", "coarse_metric_resolution"),
        ("short-window", "short_window"),
        ("stale-metrics", "stale_metrics"),
    ],
)
def test_scoped_metric_gates_remain_fail_closed(defect: str, reason: str) -> None:
    payload = scoped_snapshot_payload()
    quality = payload["clusters"][0]["workloads"][0]["containers"][0]["resources"]["metric_quality"]
    if defect == "coverage":
        quality["usage_cpu_p95_mcores"]["window"]["coverage_ratio"] = 0.84
    elif defect == "sample-count":
        quality["usage_cpu_p95_mcores"]["window"]["sample_count"] = 1
    elif defect == "missing-quality":
        quality.clear()
    elif defect == "coarse-step":
        quality["usage_cpu_p95_mcores"]["step_seconds"] = 600
    elif defect == "short-window":
        payload["metric_window"]["start"] = "2026-10-20T00:00:00Z"
    else:
        payload["metric_window"]["end"] = "2026-10-27T00:00:00Z"
    assert reason in cpu_reduction_reasons(FleetSnapshot.model_validate(payload))


def test_scoped_manifest_cannot_be_smuggled_into_a_legacy_snapshot() -> None:
    payload = scoped_snapshot_payload()
    payload["schema_version"] = "2.0"
    with pytest.raises(ValueError):
        FleetSnapshot.model_validate(payload)


def cpu_reduction_reasons(snapshot: FleetSnapshot) -> list[str]:
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert "AKS-RQ-002" not in {item.rule_id for item in report.recommendations}
    blocked = [item for item in report.blocked_recommendations if item.rule_id == "AKS-RQ-002"]
    assert len(blocked) == 1
    return blocked[0].reason_codes


def test_eligible_evidence_generates_expected_rule_families() -> None:
    report = analyze(eligible_snapshot(), AdvisorConfig(mode="guarded"), as_of=AS_OF)
    rule_ids = {item.rule_id for item in report.recommendations}
    assert {"AKS-NP-001", "AKS-AS-001", "AKS-RQ-001", "AKS-RQ-002"} <= rule_ids
    assert report.summary.clusters_analyzed == 1
    assert report.summary.high_or_critical >= 1


def test_recommendations_include_evidence_and_validation() -> None:
    report = analyze(eligible_snapshot(), AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert report.recommendations
    for item in report.recommendations:
        assert item.evidence
        assert item.validation_steps
        assert item.rollback_steps
        assert item.severity in set(Severity)


def test_ids_are_stable() -> None:
    snapshot = eligible_snapshot()
    first = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    second = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    first_ids = [item.id for item in first.recommendations]
    second_ids = [item.id for item in second.recommendations]
    assert first_ids == second_ids
    assert first == second


def test_short_window_cannot_emit_cpu_reduction() -> None:
    snapshot = eligible_snapshot()
    snapshot.metric_window.start = snapshot.metric_window.end - timedelta(days=14)
    assert "short_window" in cpu_reduction_reasons(snapshot)


def test_stale_snapshot_cannot_emit_capacity_recommendations() -> None:
    snapshot = eligible_snapshot()
    snapshot.generated_at = datetime(2000, 1, 1, tzinfo=UTC)
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert not {"AKS-RQ-002", "AKS-NP-001"} & {item.rule_id for item in report.recommendations}
    assert "stale_snapshot" in cpu_reduction_reasons(snapshot)


def test_missing_autoscaler_observations_are_unknown() -> None:
    state = AutoscalingState()
    assert state.hpa is None
    assert state.keda is None


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("collection_manifest",), None, "missing_collection_manifest"),
        (("generated_at",), "2026-10-30T00:00:00Z", "future_snapshot"),
        (
            (
                "clusters",
                0,
                "workloads",
                0,
                "containers",
                0,
                "resources",
                "metric_quality",
                "usage_cpu_p95_mcores",
                "window",
                "coverage_ratio",
            ),
            0.84,
            "low_entity_coverage",
        ),
        (
            ("clusters", 0, "workloads", 0, "containers", 0, "resources", "cpu_observation_basis"),
            None,
            "unknown_metric_aggregation",
        ),
        (("clusters", 0, "workloads", 0, "uid"), None, "missing_identity"),
        (("clusters", 0, "workloads", 0, "safety_policy"), None, "missing_safety_policy"),
        (
            ("clusters", 0, "workloads", 0, "safety_policy", "disruption_reviewed"),
            False,
            "unreviewed_disruption",
        ),
        (
            ("clusters", 0, "workloads", 0, "safety_policy", "reviewed_window_start"),
            "2026-09-30T00:00:00Z",
            "unreviewed_window",
        ),
        (("clusters", 0, "workloads", 0, "autoscaling", "hpa"), None, "unknown_autoscaler"),
        (
            ("clusters", 0, "workloads", 0, "autoscaling", "hpa"),
            True,
            "autoscaler_interaction_review_required",
        ),
        (
            ("clusters", 0, "workloads", 0, "autoscaling", "keda"),
            True,
            "autoscaler_interaction_review_required",
        ),
        (("clusters", 0, "workloads", 0, "autoscaling", "vpa"), None, "unknown_autoscaler"),
        (
            ("clusters", 0, "workloads", 0, "containers", 0, "resources", "cpu_throttled_ratio"),
            0.02,
            "elevated_throttling",
        ),
        (
            ("clusters", 0, "workloads", 0, "containers", 0, "resources", "memory_oom_events"),
            1,
            "oom_history",
        ),
        (
            ("clusters", 0, "workloads", 0, "containers", 0, "resources", "metric_quality"),
            {},
            "missing_metric_quality",
        ),
    ],
)
def test_ineligible_reductions_have_explicit_reasons(
    path: tuple[str | int, ...], value: Any, reason: str
) -> None:
    payload = eligible_snapshot_payload()
    target: Any = payload
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    assert reason in cpu_reduction_reasons(FleetSnapshot.model_validate(payload))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("coverage_ratio", 0.84, "low_entity_coverage"),
        ("start", "2026-09-30T00:00:00Z", "misaligned_metric_window"),
    ],
)
def test_entity_quality_cannot_inherit_fleet_coverage(field: str, value: Any, reason: str) -> None:
    payload = eligible_snapshot_payload()
    quality = payload["clusters"][0]["workloads"][0]["containers"][0]["resources"]["metric_quality"]
    quality["usage_cpu_p95_mcores"]["window"][field] = value
    assert reason in cpu_reduction_reasons(FleetSnapshot.model_validate(payload))


def test_partial_inventory_blocks_reductions() -> None:
    payload = eligible_snapshot_payload()
    payload["collection_manifest"]["status"] = "partial"
    payload["collection_manifest"]["results"][0].update(status="partial", pagination_complete=False)
    assert "incomplete_collection" in cpu_reduction_reasons(FleetSnapshot.model_validate(payload))


def test_complete_but_wrong_collection_scope_blocks_reductions() -> None:
    payload = eligible_snapshot_payload()
    payload["collection_manifest"]["results"][1].update(
        requested_scope=["different-cluster-id"], completed_scope=["different-cluster-id"]
    )
    assert "missing_required_collector" in cpu_reduction_reasons(
        FleetSnapshot.model_validate(payload)
    )


def test_optional_cost_failure_does_not_block_capacity_findings() -> None:
    payload = eligible_snapshot_payload()
    payload["collection_manifest"]["status"] = "partial"
    payload["collection_manifest"]["results"].append(
        {
            "collector": "cost",
            "status": "failed",
            "requested_scope": ["synthetic-subscription"],
            "started_at": "2026-10-29T11:00:00Z",
            "completed_at": "2026-10-29T11:01:00Z",
            "errors": [{"scope": "synthetic-subscription", "code": "forbidden"}],
        }
    )
    report = analyze(
        FleetSnapshot.model_validate(payload), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert "AKS-RQ-002" in {item.rule_id for item in report.recommendations}
    assert all(item.estimated_monthly_savings is None for item in report.recommendations)


def test_cpu_proposal_respects_peaks_headroom_and_policy_floor() -> None:
    report = analyze(eligible_snapshot(), AdvisorConfig(mode="guarded"), as_of=AS_OF)
    reduction = next(item for item in report.recommendations if item.rule_id == "AKS-RQ-002")
    assert reduction.current_requests.cpu_mcores == 1000
    assert reduction.proposed_requests.cpu_mcores == 750
    assert reduction.owner == "synthetic-owner"
    assert reduction.rollback_steps
    assert report.snapshot_digest
    assert report.configuration_digest


def test_policy_caps_reduction_without_a_universal_utilization_target() -> None:
    payload = eligible_snapshot_payload()
    payload["clusters"][0]["workloads"][0]["safety_policy"]["maximum_cpu_reduction_ratio"] = 0.1
    report = analyze(
        FleetSnapshot.model_validate(payload), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    reduction = next(item for item in report.recommendations if item.rule_id == "AKS-RQ-002")
    assert reduction.proposed_requests.cpu_mcores == 900


def test_no_headroom_to_reduce_is_blocked() -> None:
    payload = eligible_snapshot_payload()
    payload["clusters"][0]["workloads"][0]["safety_policy"]["minimum_cpu_request_mcores"] = 1000
    assert "no_safe_reduction" in cpu_reduction_reasons(FleetSnapshot.model_validate(payload))


def test_unknown_autoscaler_cannot_be_reported_as_absent() -> None:
    snapshot = eligible_snapshot()
    for workload in snapshot.clusters[0].workloads:
        workload.autoscaling = AutoscalingState()
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert "AKS-AS-001" not in {item.rule_id for item in report.recommendations}
    assert any("unknown_autoscaler" in item.reason_codes for item in report.blocked_recommendations)


def test_legacy_fixture_is_readable_but_not_actionable_without_provenance() -> None:
    report = analyze(
        FixtureCollector(FIXTURE).collect(), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert not report.recommendations
    assert report.blocked_recommendations
    assert report.summary.blocked_recommendations == len(report.blocked_recommendations)


def test_explicit_clock_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        analyze(eligible_snapshot(), AdvisorConfig(mode="guarded"), as_of=datetime(2026, 10, 29))


def test_analysis_does_not_mutate_evidence_and_digests_track_changes() -> None:
    snapshot = eligible_snapshot()
    before = snapshot.model_dump_json()
    first = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert snapshot.model_dump_json() == before
    snapshot.clusters[0].workloads[0].uid = "recreated-workload-uid"
    second = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert first.snapshot_digest != second.snapshot_digest
    first_id = next(item.id for item in first.recommendations if item.rule_id == "AKS-RQ-002")
    second_id = next(item.id for item in second.recommendations if item.rule_id == "AKS-RQ-002")
    assert first_id != second_id


def test_unobserved_cpu_request_cannot_be_asserted_missing() -> None:
    payload = eligible_snapshot_payload()
    del payload["clusters"][0]["workloads"][1]["containers"][0]["resources"]["request_cpu_mcores"]
    report = analyze(
        FleetSnapshot.model_validate(payload), AdvisorConfig(mode="guarded"), as_of=AS_OF
    )
    assert "AKS-RQ-001" not in {item.rule_id for item in report.recommendations}
    assert any(
        "missing_request_observation" in item.reason_codes
        for item in report.blocked_recommendations
    )


@pytest.mark.parametrize("collector_index", [0, 1, 2])
def test_unknown_source_freshness_is_not_inferred_from_collection_time(
    collector_index: int,
) -> None:
    payload = eligible_snapshot_payload()
    del payload["collection_manifest"]["results"][collector_index]["source_observed_at"]
    assert "unknown_source_freshness" in cpu_reduction_reasons(
        FleetSnapshot.model_validate(payload)
    )


def test_freshness_boundary_is_inclusive_and_then_expires() -> None:
    snapshot = eligible_snapshot()
    boundary = snapshot.metric_window.end + timedelta(hours=24)
    first = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=boundary)
    assert "AKS-RQ-002" in {item.rule_id for item in first.recommendations}
    expired = analyze(
        snapshot, AdvisorConfig(mode="guarded"), as_of=boundary + timedelta(microseconds=1)
    )
    assert "AKS-RQ-002" not in {item.rule_id for item in expired.recommendations}
    assert any("stale_metrics" in item.reason_codes for item in expired.blocked_recommendations)


def test_coverage_boundary_is_inclusive() -> None:
    snapshot = eligible_snapshot()
    snapshot.metric_window.coverage_ratio = 0.85
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    for quality in resources.metric_quality.values():
        quality.window.coverage_ratio = 0.85
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert "AKS-RQ-002" in {item.rule_id for item in report.recommendations}


def test_inventory_findings_do_not_depend_on_metric_coverage() -> None:
    snapshot = eligible_snapshot()
    snapshot.metric_window.coverage_ratio = 0.2
    for workload in snapshot.clusters[0].workloads:
        for container in workload.containers:
            for quality in container.resources.metric_quality.values():
                quality.window.coverage_ratio = 0.2
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert {"AKS-RQ-001", "AKS-AS-001"} <= {item.rule_id for item in report.recommendations}
    assert "AKS-RQ-002" not in {item.rule_id for item in report.recommendations}


def test_markdown_exposes_prerequisites_rollback_and_blocked_findings() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].workloads[0].safety_policy = None
    rendered = render_markdown(analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF))
    assert "## Blocked findings" in rendered
    assert "missing_safety_policy" in rendered
    assert "**Prerequisites**" in rendered
    assert "**Rollback**" in rendered


def test_markdown_treats_report_strings_as_untrusted_data() -> None:
    report = analyze(eligible_snapshot(), AdvisorConfig(mode="guarded"), as_of=AS_OF)
    attack = "<script>alert(1)</script>\n# injected [link](javascript:alert(1)) `escape`"
    recommendation = report.recommendations[0]
    recommendation.title = attack
    recommendation.cluster_name = attack
    recommendation.summary = attack
    recommendation.evidence[0].source = attack
    recommendation.prerequisites = [attack]
    recommendation.rollback_steps = [attack]
    report.summary.data_quality_warnings = [attack]
    rendered = render_markdown(report)
    assert "<script>" not in rendered
    assert "\n# injected" not in rendered
    assert "[link](javascript:" not in rendered
    assert "`escape`" not in rendered


@pytest.mark.parametrize(
    "field",
    ["usage_cpu_p95_mcores", "usage_cpu_p99_mcores", "cpu_throttled_ratio", "memory_oom_events"],
)
def test_missing_required_metric_is_blocked_not_silently_skipped(field: str) -> None:
    snapshot = eligible_snapshot()
    setattr(snapshot.clusters[0].workloads[0].containers[0].resources, field, None)
    assert "missing_metric" in cpu_reduction_reasons(snapshot)


def test_missing_pool_usage_is_explicitly_blocked() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].node_pools[0].usage_cpu_p95_mcores = None
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert "AKS-NP-001" not in {item.rule_id for item in report.recommendations}
    assert any(
        item.rule_id == "AKS-NP-001" and "missing_metric" in item.reason_codes
        for item in report.blocked_recommendations
    )


def test_entity_cannot_overstate_coverage_relative_to_its_sample_count() -> None:
    snapshot = eligible_snapshot()
    quality = (
        snapshot.clusters[0]
        .workloads[0]
        .containers[0]
        .resources.metric_quality["usage_cpu_p95_mcores"]
    )
    quality.window.sample_count = 1
    assert "inconsistent_metric_coverage" in cpu_reduction_reasons(snapshot)


def test_metric_observation_cannot_postdate_its_snapshot() -> None:
    snapshot = eligible_snapshot()
    quality = (
        snapshot.clusters[0]
        .workloads[0]
        .containers[0]
        .resources.metric_quality["usage_cpu_p95_mcores"]
    )
    quality.observed_at = datetime(2026, 10, 29, 11, 30, tzinfo=UTC)
    assert "inconsistent_metric_time" in cpu_reduction_reasons(snapshot)


def test_cli_supports_explicit_aware_clock_for_offline_replay() -> None:
    result = CliRunner().invoke(
        app,
        ["analyze", "--snapshot", str(FIXTURE), "--as-of", AS_OF.isoformat(), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert datetime.fromisoformat(report["generated_at"]) == AS_OF
    assert report["schema_version"] == "1.0"
    assert not report["recommendations"]
    assert report["blocked_recommendations"]


@pytest.mark.parametrize("value", ["2026-10-29T12:00:00", "not-a-date"])
def test_cli_rejects_ambiguous_evaluation_times(value: str) -> None:
    result = CliRunner().invoke(app, ["analyze", "--snapshot", str(FIXTURE), "--as-of", value])
    assert result.exit_code == 2
    assert "timezone-aware" in result.output


def test_coarse_retention_cannot_qualify_as_high_quality_history() -> None:
    snapshot = eligible_snapshot()
    quality = (
        snapshot.clusters[0]
        .workloads[0]
        .containers[0]
        .resources.metric_quality["usage_cpu_p95_mcores"]
    )
    quality.step_seconds = 3600
    assert "coarse_metric_resolution" in cpu_reduction_reasons(snapshot)


def test_cpu_request_risk_rule_requires_valid_observations_and_has_no_reduction() -> None:
    snapshot = eligible_snapshot()
    resources = snapshot.clusters[0].workloads[0].containers[0].resources
    resources.usage_cpu_p95_mcores = 1050
    resources.usage_cpu_p99_mcores = 1200
    for metric in ["usage_cpu_p95_mcores", "usage_cpu_p99_mcores"]:
        resources.metric_quality[metric].maximum = 1200
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    finding = next(item for item in report.recommendations if item.rule_id == "AKS-RQ-003")
    assert finding.category == "reliability-guardrail"
    assert finding.proposed_requests is None
    assert finding.rollback_steps
    resources.metric_quality["usage_cpu_p95_mcores"].window.coverage_ratio = 0.1
    blocked_report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert "AKS-RQ-003" not in {item.rule_id for item in blocked_report.recommendations}
    assert any(
        "low_entity_coverage" in item.reason_codes
        for item in blocked_report.blocked_recommendations
    )


def test_zero_node_pool_is_not_a_capacity_reduction_candidate() -> None:
    snapshot = eligible_snapshot()
    snapshot.clusters[0].node_pools[0].node_count = 0
    report = analyze(snapshot, AdvisorConfig(mode="guarded"), as_of=AS_OF)
    assert "AKS-NP-001" not in {item.rule_id for item in report.recommendations}
