from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil

from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import FleetSnapshot, MetricQuality, Recommendation


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
