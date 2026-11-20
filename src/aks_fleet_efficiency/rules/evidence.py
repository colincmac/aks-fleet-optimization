from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Literal

from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    ContainerSnapshot,
    FleetSnapshot,
    MetricQuality,
    Recommendation,
    ResourceCandidate,
    WorkloadSnapshot,
)


@dataclass(frozen=True)
class RuleAssessment:
    recommendation: Recommendation
    metrics: dict[str, tuple[float | int | None, str]] | None
    reasons: list[str]
    has_signal: bool
    qualities: dict[str, MetricQuality] | None = None


def metric_source(qualities: dict[str, MetricQuality], name: str) -> str:
    quality = qualities.get(name)
    return quality.source if quality is not None else "unknown"


def select_resource_candidate(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot,
    dimension: Literal["cpu-request", "memory-request"],
    safety_floor: float | None,
    maximum_age_hours: float,
) -> tuple[ResourceCandidate | None, list[str]]:
    dimensional = [item for item in workload.resource_candidates if item.dimension == dimension]
    candidates = [item for item in dimensional if item.container == container.name]
    if not candidates:
        names = {item.name for item in workload.containers}
        reason = (
            "candidate_identity_mismatch"
            if any(item.container not in names for item in dimensional)
            else "existing_candidate_required"
        )
        return None, [reason]
    if any(
        item.cluster_resource_id != cluster.resource_id
        or item.namespace != workload.namespace
        or item.workload_uid != workload.uid
        for item in candidates
    ):
        return None, ["candidate_identity_mismatch"]
    if len(candidates) != 1:
        return None, ["candidate_ambiguous"]
    candidate = candidates[0]
    reasons: list[str] = []
    if candidate.source not in {"vpa", "kubecost"}:
        reasons.append("unsupported_candidate_source")
    elif not candidate.has_characterized_source:
        reasons.append("candidate_source_version_unsupported")
    current = (
        container.resources.request_cpu_mcores
        if dimension == "cpu-request"
        else container.resources.request_memory_mib
    )
    if candidate.current_value != current:
        reasons.append("candidate_current_value_mismatch")
    if candidate.observed_at is None:
        reasons.append("candidate_freshness_unknown")
    else:
        age = (snapshot.generated_at - candidate.observed_at).total_seconds()
        if age < 0 or (
            candidate.collected_at is not None
            and (
                candidate.observed_at > candidate.collected_at
                or candidate.collected_at > snapshot.generated_at
            )
        ):
            reasons.append("candidate_in_future")
        elif age > maximum_age_hours * 3600:
            reasons.append("candidate_stale")
    if safety_floor is not None and candidate.recommended_value < safety_floor:
        reasons.append("candidate_below_safety_bound")
    return candidate, reasons


def quality_reasons(
    snapshot: FleetSnapshot,
    metrics: dict[str, tuple[float | int | None, str]],
    qualities: dict[str, MetricQuality],
    config: AdvisorConfig,
    evaluated_at: datetime,
    maximum_age: float,
) -> list[str]:
    reasons = []
    for name, (value, unit) in metrics.items():
        if value is None:
            reasons.append("missing_metric")
        quality = qualities.get(name)
        if quality is None:
            reasons.append("missing_metric_quality")
            continue
        if quality.unit != unit:
            reasons.append("metric_unit_mismatch")
        if quality.step_seconds > config.thresholds.maximum_metric_step_seconds:
            reasons.append("coarse_metric_resolution")
        if (
            quality.window.start != snapshot.metric_window.start
            or quality.window.end != snapshot.metric_window.end
        ):
            reasons.append("misaligned_metric_window")
        if quality.window.sample_count == 0:
            reasons.append("missing_samples")
        expected_samples = ceil(
            (quality.window.end - quality.window.start).total_seconds() / quality.step_seconds
        )
        if quality.window.coverage_ratio > min(
            1, (quality.window.sample_count + 1) / expected_samples
        ):
            reasons.append("inconsistent_metric_coverage")
        if quality.window.coverage_ratio < config.thresholds.minimum_coverage_ratio:
            reasons.append("low_entity_coverage")
        if quality.observed_at > evaluated_at:
            reasons.append("future_metric_observation")
        elif (evaluated_at - quality.observed_at).total_seconds() > maximum_age:
            reasons.append("stale_metric_observation")
        if quality.observed_at > snapshot.generated_at:
            reasons.append("inconsistent_metric_time")
        if value is not None and (
            (quality.minimum is not None and value < quality.minimum)
            or (quality.maximum is not None and value > quality.maximum)
        ):
            reasons.append("inconsistent_metric_value")
    return reasons
