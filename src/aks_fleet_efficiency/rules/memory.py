from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from math import ceil, isfinite

from aks_fleet_efficiency.models import Evidence, FleetSnapshot, MetricQuality, WorkloadSnapshot
from aks_fleet_efficiency.rules.autoscalers import replica_configuration_digest


def memory_limit_configuration_digest(workload: WorkloadSnapshot) -> str:
    value = {
        "configuration": replica_configuration_digest(workload),
        "qos_class": workload.qos_class,
        "admission_digest": workload.memory_admission_digest,
        "admission_observed": workload.memory_admission_observed,
    }
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def termination_review_reasons(snapshot: FleetSnapshot, workload: WorkloadSnapshot) -> list[str]:
    reasons = list(workload.termination_issues)
    if any(
        item.finished_at >= snapshot.metric_window.start
        and (item.exit_code != 0 or item.reason != "Completed")
        for item in workload.termination_context
    ):
        reasons.append("current_termination_review_required")
    return reasons


@dataclass
class MemoryLimitAssessment:
    metrics: dict[str, tuple[float | int | None, str]] = field(default_factory=dict)
    qualities: dict[str, MetricQuality] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    proposed_mib: float | None = None


def memory_limit_assessment(
    snapshot: FleetSnapshot, workload: WorkloadSnapshot, container_name: str
) -> MemoryLimitAssessment:
    container = next(item for item in workload.containers if item.name == container_name)
    resources = container.resources
    result = MemoryLimitAssessment(
        metrics={
            "request_memory_mib": (resources.request_memory_mib, "MiB"),
            "limit_memory_mib": (resources.limit_memory_mib, "MiB"),
            "total_memory_usage_p99_mib": (resources.total_memory_usage_p99_mib, "MiB"),
            "memory_oom_events": (resources.memory_oom_events, "events"),
            "restart_events": (resources.restart_events, "events"),
            "workload_eviction_events": (workload.eviction_events, "events"),
        },
        qualities=dict(resources.metric_quality),
        reasons=termination_review_reasons(snapshot, workload),
    )
    if workload.eviction_quality is not None:
        result.qualities["workload_eviction_events"] = workload.eviction_quality
    result.evidence = [
        Evidence(
            metric=name,
            value=value,
            unit=unit,
            source=result.qualities[name].source if name in result.qualities else "unknown",
        )
        for name, (value, unit) in result.metrics.items()
    ]
    policy = workload.safety_policy
    limit = policy.memory_limits.get(container_name) if policy is not None else None
    if limit is None:
        result.reasons.append("missing_memory_limit_policy")
        return result
    if not limit.allow_limit_reduction:
        result.reasons.append("memory_limit_reduction_not_enabled")
    if policy is None:
        result.reasons.append("missing_safety_policy")
        return result
    if not policy.owner.strip() or not policy.slo_reference.strip():
        result.reasons.append("missing_memory_owner_or_slo")
    if not policy.disruption_reviewed:
        result.reasons.append("unreviewed_disruption")
    if (
        policy.reviewed_window_start != snapshot.metric_window.start
        or policy.reviewed_window_end != snapshot.metric_window.end
    ):
        result.reasons.append("unreviewed_window")
    if workload.replicas != 1 or resources.memory_observation_basis != "pod":
        result.reasons.append("unsupported_memory_limit_history")
    if not workload.memory_admission_observed:
        result.reasons.append("unobserved_memory_admission")
    result.reasons.extend(workload.memory_admission_issues)
    if workload.qos_class != "Burstable":
        result.reasons.append("qos_preservation_review_required")
    if not resources.memory_request_observed or not resources.memory_limit_observed:
        result.reasons.append("missing_memory_request_or_limit_observation")
    if limit.configuration_digest != memory_limit_configuration_digest(workload):
        result.reasons.append("unreviewed_memory_limit_configuration")
    if limit.allocator_cache_reviewed is not True:
        result.reasons.append("unreviewed_allocator_cache_memory")
    if limit.startup_total_peak_mib is None or limit.failover_total_peak_mib is None:
        result.reasons.append("missing_total_memory_scenario_review")
    for name, count in [
        ("oom", resources.memory_oom_events),
        ("restart", resources.restart_events),
        ("eviction", workload.eviction_events),
    ]:
        if count != 0:
            result.reasons.append(f"unknown_or_positive_memory_{name}")
    for name in result.metrics:
        quality = result.qualities.get(name)
        if quality is None:
            result.reasons.append("missing_metric_quality")
            continue
        duration = (quality.window.end - quality.window.start).total_seconds()
        if (
            quality.window.coverage_ratio != 1
            or duration % quality.step_seconds != 0
            or quality.window.sample_count != duration / quality.step_seconds
        ):
            result.reasons.append("incomplete_memory_limit_history")
    for name, value in [
        ("request_memory_mib", resources.request_memory_mib),
        ("limit_memory_mib", resources.limit_memory_mib),
    ]:
        quality = result.qualities.get(name)
        if (
            value is None
            or value <= 0
            or quality is None
            or quality.minimum != quality.maximum
            or quality.minimum != value
        ):
            result.reasons.append("unstable_memory_request_or_limit")
    usage = result.qualities.get("total_memory_usage_p99_mib")
    working = result.qualities.get("usage_memory_p99_mib")
    if usage is None or usage.maximum is None or resources.total_memory_usage_p99_mib is None:
        result.reasons.append("missing_total_memory_peak")
    elif working is not None:
        if (
            (working.maximum is not None and usage.maximum < working.maximum)
            or (
                working.minimum is not None
                and usage.minimum is not None
                and usage.minimum < working.minimum
            )
            or (
                resources.usage_memory_p99_mib is not None
                and resources.total_memory_usage_p99_mib < resources.usage_memory_p99_mib
            )
        ):
            result.reasons.append("contradictory_total_memory_peak")
    if (
        len(
            {
                (item.window.start, item.window.end, item.step_seconds)
                for name, item in result.qualities.items()
                if name in result.metrics
            }
        )
        != 1
    ):
        result.reasons.append("misaligned_memory_limit_history")
    if (
        len(
            {
                (item.source, item.query_version)
                for name, item in result.qualities.items()
                if name in result.metrics
            }
        )
        != 1
    ):
        result.reasons.append("inconsistent_memory_limit_source")
    if result.reasons:
        return result
    assert usage is not None and usage.maximum is not None
    assert resources.request_memory_mib is not None and resources.limit_memory_mib is not None
    assert limit.startup_total_peak_mib is not None and limit.failover_total_peak_mib is not None
    peak = max(usage.maximum, limit.startup_total_peak_mib, limit.failover_total_peak_mib)
    lower = max(
        limit.minimum_limit_mib,
        workload.memory_admission_minimum_mib or 0,
        resources.limit_memory_mib * (1 - limit.maximum_reduction_ratio),
        resources.request_memory_mib + 1,
        peak + 1,
        peak * limit.headroom_factor,
    )
    if not isfinite(lower) or lower >= resources.limit_memory_mib:
        result.reasons.append("no_safe_memory_limit_reduction")
        return result
    proposed = float(ceil(lower))
    if (
        workload.memory_admission_maximum_mib is not None
        and proposed > workload.memory_admission_maximum_mib
    ) or (
        workload.memory_admission_limit_request_ratio is not None
        and proposed / resources.request_memory_mib > workload.memory_admission_limit_request_ratio
    ):
        result.reasons.append("memory_admission_constraint")
        return result
    if (
        proposed >= resources.limit_memory_mib
        or proposed <= peak
        or proposed <= resources.request_memory_mib
    ):
        result.reasons.append("no_safe_memory_limit_reduction")
        return result
    result.proposed_mib = proposed
    values: list[tuple[str, float | str | None, str | None]] = [
        ("minimum_limit_mib", limit.minimum_limit_mib, "MiB"),
        ("maximum_reduction_ratio", limit.maximum_reduction_ratio, "ratio"),
        ("headroom_factor", limit.headroom_factor, "factor"),
        ("startup_total_peak_mib", limit.startup_total_peak_mib, "MiB"),
        ("failover_total_peak_mib", limit.failover_total_peak_mib, "MiB"),
        ("configuration_digest", limit.configuration_digest, None),
        ("review_reference", limit.evidence_reference, None),
        ("admission_minimum_limit_mib", workload.memory_admission_minimum_mib, "MiB"),
        ("admission_maximum_limit_mib", workload.memory_admission_maximum_mib, "MiB"),
        (
            "admission_maximum_limit_request_ratio",
            workload.memory_admission_limit_request_ratio,
            "ratio",
        ),
    ]
    for metric, policy_value, unit in values:
        result.evidence.append(
            Evidence(metric=metric, value=policy_value, unit=unit, source="owner-policy")
        )
    return result
