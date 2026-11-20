from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from math import ceil
from typing import Literal

from aks_fleet_efficiency.catalog.models import SummaryCode
from aks_fleet_efficiency.models import (
    HPA_REPLICA_METRICS,
    WORKLOAD_REPLICA_METRICS,
    ClusterSnapshot,
    Evidence,
    FleetSnapshot,
    MetricQuality,
    WorkloadSnapshot,
)


def _configuration_reasons(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
    *,
    require_vpa: bool = True,
    require_keda: bool = False,
) -> list[str]:
    configuration = workload.autoscaler_configuration
    if configuration is None:
        return ["missing_autoscaler_configuration"]
    reasons: list[str] = [
        issue
        for issue in configuration.issues
        if (require_vpa or issue != "unsupported_vpa_configuration")
        and (require_keda or issue != "unsupported_keda_configuration")
    ]
    if not cluster.uid or not workload.uid or not configuration.namespace_uid:
        reasons.append("missing_identity")
    if (
        configuration.cluster_resource_id != cluster.resource_id
        or configuration.cluster_uid != cluster.uid
        or configuration.namespace != workload.namespace
        or configuration.workload_uid != workload.uid
        or configuration.target_kind != workload.kind
        or configuration.target_name != workload.name
    ):
        reasons.append("autoscaler_identity_mismatch")
    if not configuration.hpa_observed:
        reasons.append("unknown_hpa_configuration")
    if require_vpa and not configuration.vpa_observed:
        reasons.append("unknown_vpa_configuration")
    if require_keda and not configuration.keda_observed:
        reasons.append("unknown_keda_configuration")
    if configuration.observed_at > evaluated_at:
        reasons.append("future_autoscaler_configuration")
    elif (evaluated_at - configuration.observed_at).total_seconds() > maximum_age:
        reasons.append("stale_autoscaler_configuration")
    if configuration.observed_at > snapshot.generated_at:
        reasons.append("inconsistent_autoscaler_configuration_time")
    return reasons


def _full_grid_reasons(quality: MetricQuality, source: str, query_version: str) -> list[str]:
    reasons = []
    duration = (quality.window.end - quality.window.start).total_seconds()
    if (
        quality.window.coverage_ratio != 1
        or duration % quality.step_seconds != 0
        or quality.window.sample_count != duration / quality.step_seconds
    ):
        reasons.append("incomplete_hpa_history")
    if quality.source != source or quality.query_version != query_version:
        reasons.append("hpa_history_source_mismatch")
    return reasons


def autoscaler_conflict_evidence(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
) -> tuple[list[Evidence], list[str]]:
    reasons = _configuration_reasons(snapshot, cluster, workload, evaluated_at, maximum_age)
    configuration = workload.autoscaler_configuration
    if reasons or configuration is None:
        return [], reasons
    evidence: list[Evidence] = []
    containers = {item.name for item in workload.containers}
    seen: set[tuple[str, str, str, str, str, int]] = set()
    for hpa in configuration.hpas:
        for signal in hpa.metrics:
            if signal.target_type != "Utilization" or signal.resource not in {"cpu", "memory"}:
                continue
            if signal.metric_type == "ContainerResource" and signal.container not in containers:
                reasons.append("unsupported_hpa_configuration")
                continue
            affected = [signal.container] if signal.container is not None else sorted(containers)
            for vpa in configuration.vpas:
                if vpa.update_mode == "Off":
                    continue
                policies = {item.container_name: item for item in vpa.container_policies}
                for container in affected:
                    policy = policies.get(container, policies.get("*"))
                    if policy is None:
                        reasons.append("unsupported_vpa_configuration")
                        continue
                    if policy.mode == "Off":
                        continue
                    if policy.controlled_resources is None:
                        reasons.append("unsupported_vpa_configuration")
                        continue
                    if signal.resource not in policy.controlled_resources:
                        continue
                    if signal.average_utilization is None:
                        reasons.append("unsupported_hpa_configuration")
                        continue
                    pair = (
                        hpa.uid,
                        vpa.uid,
                        container,
                        signal.resource,
                        signal.metric_type,
                        signal.average_utilization,
                    )
                    if pair in seen:
                        continue
                    seen.add(pair)
                    values: list[tuple[str, str | int, str | None]] = [
                        ("hpa_uid", hpa.uid, None),
                        ("hpa_name", hpa.name, None),
                        ("vpa_uid", vpa.uid, None),
                        ("vpa_name", vpa.name, None),
                        ("container", container, None),
                        ("resource", signal.resource, None),
                        ("hpa_metric_type", signal.metric_type, None),
                        ("average_utilization", signal.average_utilization, "percent"),
                        ("vpa_update_mode", vpa.update_mode, None),
                    ]
                    for metric, value, unit in values:
                        evidence.append(
                            Evidence(metric=metric, value=value, unit=unit, source="kubernetes-api")
                        )
    return evidence, reasons


@dataclass
class HpaPinningAssessment:
    metrics: dict[str, tuple[float | int | None, str]] | None = None
    qualities: dict[str, MetricQuality] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    bound_state: Literal["floor", "ceiling", "fixed"] | None = None


def hpa_pinning_assessment(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
) -> HpaPinningAssessment:
    result = HpaPinningAssessment(
        reasons=_configuration_reasons(
            snapshot, cluster, workload, evaluated_at, maximum_age, require_vpa=False
        )
    )
    configuration = workload.autoscaler_configuration
    if result.reasons or configuration is None or not configuration.hpas:
        return result
    if len(configuration.hpas) != 1:
        result.reasons.append("ambiguous_hpa_controller")
        return result
    hpa = configuration.hpas[0]
    result.metrics = {name: (None, "pods") for name in HPA_REPLICA_METRICS}
    history = workload.hpa_replica_history
    if history is None:
        result.reasons.append("missing_hpa_replica_history")
        return result
    result.reasons.extend(history.issues)
    if (
        history.cluster_resource_id != cluster.resource_id
        or history.cluster_uid != cluster.uid
        or history.namespace_uid != configuration.namespace_uid
        or history.workload_uid != workload.uid
        or history.hpa_uid != hpa.uid
    ):
        result.reasons.append("hpa_history_identity_mismatch")
    for name in HPA_REPLICA_METRICS:
        item = history.metrics.get(name)
        if item is None:
            result.reasons.append("missing_hpa_history_metric")
            continue
        result.metrics[name] = (item.minimum, "pods")
        quality = item.quality
        result.qualities[name] = quality
        result.reasons.extend(
            _full_grid_reasons(quality, history.source_name, history.query_version)
        )
    if result.reasons:
        return result
    if (
        len(
            {
                (item.window.start, item.window.end, item.step_seconds)
                for item in result.qualities.values()
            }
        )
        != 1
    ):
        result.reasons.append("misaligned_hpa_history")
        return result
    minimum = history.metrics["hpa_min_replicas"]
    maximum = history.metrics["hpa_max_replicas"]
    if minimum.minimum != minimum.maximum or maximum.minimum != maximum.maximum:
        result.reasons.append("changing_hpa_bounds")
        return result
    if minimum.minimum > maximum.minimum or maximum.minimum == 0:
        result.reasons.append("invalid_hpa_bounds")
        return result
    if hpa.min_replicas is None or hpa.max_replicas is None:
        result.reasons.append("missing_hpa_bounds")
        return result
    if hpa.min_replicas != minimum.minimum or hpa.max_replicas != maximum.minimum:
        result.reasons.append("hpa_bounds_changed")
        return result
    desired = history.metrics["hpa_desired_replicas"]
    current = history.metrics["hpa_current_replicas"]
    if not (desired.minimum == desired.maximum == current.minimum == current.maximum):
        return result
    count = desired.minimum
    if count == minimum.minimum == maximum.minimum:
        result.bound_state = "fixed"
    elif count == minimum.minimum:
        result.bound_state = "floor"
    elif count == maximum.minimum:
        result.bound_state = "ceiling"
    else:
        return result
    if hpa.current_replicas is None or hpa.desired_replicas is None:
        result.reasons.append("missing_hpa_replica_status")
    elif not (hpa.current_replicas == hpa.desired_replicas == workload.replicas == count):
        result.reasons.append("hpa_replica_status_changed")
    values: list[tuple[str, str | int | None, str | None, str]] = [
        ("hpa_uid", hpa.uid, None, "kubernetes-api"),
        ("bound_state", result.bound_state, None, history.source_name),
        ("minimum_replicas", minimum.minimum, "pods", history.source_name),
        ("maximum_replicas", maximum.minimum, "pods", history.source_name),
        ("hpa_desired_replicas_min", desired.minimum, "pods", history.source_name),
        ("hpa_desired_replicas_max", desired.maximum, "pods", history.source_name),
        ("hpa_current_replicas_min", current.minimum, "pods", history.source_name),
        ("hpa_current_replicas_max", current.maximum, "pods", history.source_name),
        ("history_reference", history.history_reference, None, "approved-binding"),
        (
            "replica_configuration_digest",
            replica_configuration_digest(workload),
            None,
            "current-configuration",
        ),
    ]
    for metric, value, unit, source in values:
        result.evidence.append(Evidence(metric=metric, value=value, unit=unit, source=source))
    return result


@dataclass
class AutoscalerAssessment:
    evidence: list[Evidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, tuple[float | int | None, str]] | None = None
    qualities: dict[str, MetricQuality] = field(default_factory=dict)
    has_signal: bool = False
    summary_codes: list[SummaryCode] = field(default_factory=lambda: ["default"])
    current_floor: int | None = None
    proposed_floor: int | None = None


def controller_responsibility_assessment(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
) -> AutoscalerAssessment:
    result = AutoscalerAssessment(
        reasons=_configuration_reasons(
            snapshot, cluster, workload, evaluated_at, maximum_age, require_keda=True
        ),
    )
    configuration = workload.autoscaler_configuration
    if result.reasons or configuration is None:
        return result
    if len(configuration.hpas) > 1 or len(configuration.vpas) > 1 or len(configuration.kedas) > 1:
        result.has_signal = True
        result.summary_codes = ["multiple-controllers"]
        for metric, value in [
            ("hpa_count", len(configuration.hpas)),
            ("vpa_count", len(configuration.vpas)),
            ("keda_count", len(configuration.kedas)),
        ]:
            result.evidence.append(Evidence(metric=metric, value=value, source="kubernetes-api"))
    for keda in configuration.kedas:
        if (
            keda.min_replicas is None
            or keda.max_replicas is None
            or keda.polling_interval_seconds is None
            or keda.cooldown_period_seconds is None
            or any(item.metric_type is None for item in keda.triggers)
        ):
            result.reasons.append("incomplete_keda_signal_configuration")
        candidates = [item for item in configuration.hpas if item.name == keda.generated_hpa_name]
        if keda.generated_hpa_name is None or len(candidates) != 1:
            result.reasons.append("unknown_keda_generated_hpa")
            continue
        hpa = candidates[0]
        owners = [item for item in hpa.owner_references if item.controller]
        if len(owners) != 1 or (
            owners[0].api_version != "keda.sh/v1alpha1"
            or owners[0].kind != "ScaledObject"
            or owners[0].uid != keda.uid
            or owners[0].name != keda.name
        ):
            result.reasons.append("keda_hpa_ownership_mismatch")
            continue
        result.has_signal = True
        resource_only = all(item.type in {"cpu", "memory"} for item in keda.triggers)
        if len(configuration.hpas) == len(configuration.kedas) == 1:
            result.summary_codes = ["keda-chain"]
        if keda.min_replicas == 0 and resource_only:
            result.summary_codes.append("cpu-memory-only")
        elif keda.min_replicas == 0:
            result.summary_codes.append("zero-minimum")
        keda_values: list[tuple[str, str | int | bool | None, str | None]] = [
            ("keda_uid", keda.uid, None),
            ("generated_hpa_uid", hpa.uid, None),
            ("keda_minimum_replicas", keda.min_replicas, "pods"),
            ("keda_maximum_replicas", keda.max_replicas, "pods"),
            ("scale_to_zero", keda.min_replicas == 0, None),
            ("polling_interval", keda.polling_interval_seconds, "seconds"),
            ("cooldown_period", keda.cooldown_period_seconds, "seconds"),
        ]
        for metric, keda_value, unit in keda_values:
            result.evidence.append(
                Evidence(metric=metric, value=keda_value, unit=unit, source="kubernetes-api")
            )
        for trigger in keda.triggers:
            result.evidence.extend(
                [
                    Evidence(metric="trigger_type", value=trigger.type, source="kubernetes-api"),
                    Evidence(
                        metric="trigger_metric_type",
                        value=trigger.metric_type,
                        source="kubernetes-api",
                    ),
                ]
            )
        for signal in hpa.metrics:
            result.evidence.extend(
                [
                    Evidence(
                        metric="generated_hpa_metric_type",
                        value=signal.metric_type,
                        source="kubernetes-api",
                    ),
                    Evidence(
                        metric="generated_hpa_target_type",
                        value=signal.target_type,
                        source="kubernetes-api",
                    ),
                ]
            )
    for hpa in configuration.hpas:
        for owner in hpa.owner_references:
            if (
                owner.controller
                and owner.kind == "ScaledObject"
                and not any(
                    item.uid == owner.uid and item.name == owner.name
                    for item in configuration.kedas
                )
            ):
                result.reasons.append("unresolved_keda_hpa_owner")
    return result


def replica_configuration_digest(workload: WorkloadSnapshot) -> str:
    configuration = workload.autoscaler_configuration
    value = {
        "workload_uid": workload.uid,
        "kind": workload.kind,
        "name": workload.name,
        "namespace": workload.namespace,
        "replicas": workload.replicas,
        "cluster_resource_id": configuration.cluster_resource_id if configuration else None,
        "cluster_uid": configuration.cluster_uid if configuration else None,
        "namespace_uid": configuration.namespace_uid if configuration else None,
        "pod_configuration_digest": configuration.replica_pod_configuration_digest
        if configuration
        else None,
        "hpas": [
            item.model_dump(mode="json", exclude={"current_replicas", "desired_replicas"})
            for item in configuration.hpas
        ]
        if configuration
        else None,
        "containers": [
            {
                "name": container.name,
                "cpu_request_mcores": container.resources.request_cpu_mcores,
                "cpu_limit_mcores": container.resources.limit_cpu_mcores,
                "memory_request_mib": container.resources.request_memory_mib,
                "memory_limit_mib": container.resources.limit_memory_mib,
                "cpu_request_observed": container.resources.cpu_request_observed,
                "memory_request_observed": container.resources.memory_request_observed,
                "memory_limit_observed": container.resources.memory_limit_observed,
            }
            for container in sorted(workload.containers, key=lambda item: item.name)
        ],
    }
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def replica_floor_assessment(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
) -> AutoscalerAssessment:
    pinning = hpa_pinning_assessment(snapshot, cluster, workload, evaluated_at, maximum_age)
    metrics: dict[str, tuple[float | int | None, str]] = (
        dict(pinning.metrics) if pinning.metrics is not None else {}
    )
    result = AutoscalerAssessment(
        evidence=list(pinning.evidence),
        reasons=list(pinning.reasons),
        metrics=metrics,
        qualities=dict(pinning.qualities),
    )
    result.reasons.extend(
        _configuration_reasons(
            snapshot, cluster, workload, evaluated_at, maximum_age, require_keda=True
        )
    )
    policy = workload.safety_policy
    if policy is None or policy.replicas is None:
        result.reasons.append("missing_replica_safety_policy")
        return result
    safety = policy.replicas
    if not safety.allow_floor_reduction:
        result.reasons.append("replica_floor_reduction_not_enabled")
        return result
    if (
        not policy.owner.strip()
        or not policy.slo_reference.strip()
        or not safety.evidence_reference.strip()
    ):
        result.reasons.append("missing_replica_owner_evidence")
    if not policy.disruption_reviewed:
        result.reasons.append("unreviewed_disruption")
    if (
        policy.reviewed_window_start != snapshot.metric_window.start
        or policy.reviewed_window_end != snapshot.metric_window.end
    ):
        result.reasons.append("unreviewed_window")
    for name, reviewed in [
        ("peak_load", safety.peak_load_reviewed),
        ("startup", safety.startup_reviewed),
        ("throughput", safety.throughput_reviewed),
        ("zone_failure", safety.zone_failure_reviewed),
        ("reliability", safety.reliability_reviewed),
    ]:
        if reviewed is not True:
            result.reasons.append(f"unreviewed_replica_{name}")
    if safety.configuration_digest != replica_configuration_digest(workload):
        result.reasons.append("unreviewed_replica_configuration")
    for name, count in [
        ("oom", safety.oom_events),
        ("restart", safety.restart_events),
        ("eviction", safety.eviction_events),
    ]:
        if count != 0:
            result.reasons.append(f"unknown_or_positive_reviewed_replica_{name}")
    if safety.failover_reserve_replicas is None or safety.maximum_unavailable_replicas is None:
        result.reasons.append("unknown_replica_availability_bounds")
    configuration = workload.autoscaler_configuration
    history = workload.hpa_replica_history
    if configuration is None or history is None or len(configuration.hpas) != 1:
        result.reasons.append("ambiguous_hpa_controller")
        return result
    if configuration.kedas or any(item.update_mode != "Off" for item in configuration.vpas):
        result.reasons.append("replica_controller_interaction_review_required")
    if any(item.controller for item in configuration.hpas[0].owner_references):
        result.reasons.append("managed_hpa_floor_unsupported")
    if workload.kind != "Deployment":
        result.reasons.append("unsupported_replica_availability_kind")
    if configuration.replica_constraint_issues is None:
        result.reasons.append("unknown_replica_constraints")
    else:
        result.reasons.extend(configuration.replica_constraint_issues)
    if configuration.replica_pod_configuration_digest is None:
        result.reasons.append("unknown_replica_pod_configuration")
    if workload.disruption_budget_present:
        result.reasons.append("unsupported_replica_pdb_matching")
    if configuration.workload_available_replicas != workload.replicas:
        result.reasons.append("missing_or_changed_current_availability")
    if safety.hpa_uid != history.hpa_uid:
        result.reasons.append("replica_policy_controller_mismatch")
    if pinning.bound_state != "floor":
        result.reasons.append("not_stable_hpa_floor")
    result.reasons.extend(history.availability_issues)
    result.reasons.extend(history.reliability_issues)
    for name in WORKLOAD_REPLICA_METRICS:
        item = history.workload_metrics.get(name)
        metrics[name] = (item.minimum if item else None, "pods")
        if item is None:
            result.reasons.append("missing_replica_availability_history")
            continue
        result.qualities[name] = item.quality
        result.reasons.extend(
            _full_grid_reasons(item.quality, history.source_name, history.query_version)
        )
        if item.minimum != item.maximum or item.minimum != workload.replicas:
            result.reasons.append("changing_or_unavailable_replicas")
    if (
        len(
            {
                (item.window.start, item.window.end, item.step_seconds)
                for item in result.qualities.values()
            }
        )
        != 1
    ):
        result.reasons.append("misaligned_replica_history")
    if result.reasons:
        return result
    current = configuration.hpas[0].min_replicas
    if (
        current is None
        or safety.failover_reserve_replicas is None
        or safety.maximum_unavailable_replicas is None
    ):
        result.reasons.append("unknown_replica_availability_bounds")
        return result
    proposed = max(
        ceil(current * (1 - safety.maximum_reduction_ratio)),
        safety.tested_replicas,
        safety.minimum_available_replicas
        + safety.failover_reserve_replicas
        + safety.maximum_unavailable_replicas,
    )
    if not 1 <= proposed < current:
        result.reasons.append("no_safe_replica_floor_reduction")
        return result
    result.current_floor, result.proposed_floor, result.has_signal = current, proposed, True
    values: list[tuple[str, str | int | float | None, str | None]] = [
        ("tested_replicas", safety.tested_replicas, "pods"),
        ("minimum_available_replicas", safety.minimum_available_replicas, "pods"),
        ("failover_reserve_replicas", safety.failover_reserve_replicas, "pods"),
        ("maximum_unavailable_replicas", safety.maximum_unavailable_replicas, "pods"),
        ("maximum_reduction_ratio", safety.maximum_reduction_ratio, "ratio"),
        ("owner_evidence_reference", safety.evidence_reference, None),
        ("slo_reference", policy.slo_reference, None),
        ("reviewed_configuration_digest", safety.configuration_digest, None),
        ("reviewed_oom_events", safety.oom_events, "events"),
        ("reviewed_restart_events", safety.restart_events, "events"),
        ("reviewed_eviction_events", safety.eviction_events, "events"),
    ]
    for metric, value, unit in values:
        result.evidence.append(
            Evidence(metric=metric, value=value, unit=unit, source="owner-policy")
        )
    return result


def hpa_change_assessment(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
) -> AutoscalerAssessment:
    pinning = hpa_pinning_assessment(snapshot, cluster, workload, evaluated_at, maximum_age)
    changes = {"changing_hpa_bounds", "hpa_bounds_changed", "hpa_replica_status_changed"}
    result = AutoscalerAssessment(
        reasons=[item for item in pinning.reasons if item not in changes],
        metrics=pinning.metrics,
        qualities=pinning.qualities,
        has_signal=bool(changes.intersection(pinning.reasons)),
    )
    history = workload.hpa_replica_history
    if history is not None:
        if not pinning.reasons and any(
            item.minimum != item.maximum
            for name, item in history.metrics.items()
            if name in {"hpa_desired_replicas", "hpa_current_replicas"}
        ):
            result.has_signal = True
            result.evidence.append(
                Evidence(
                    metric="sampled_replica_counts_vary", value=True, source=history.source_name
                )
            )
        for name, item in sorted(history.metrics.items()):
            result.evidence.extend(
                [
                    Evidence(
                        metric=f"{name}_min",
                        value=item.minimum,
                        unit="pods",
                        source=history.source_name,
                    ),
                    Evidence(
                        metric=f"{name}_max",
                        value=item.maximum,
                        unit="pods",
                        source=history.source_name,
                    ),
                ]
            )
        result.evidence.append(
            Evidence(metric="hpa_uid", value=history.hpa_uid, source=history.source_name)
        )
    for change in sorted(changes.intersection(pinning.reasons)):
        result.evidence.append(
            Evidence(metric="observed_controller_change", value=change, source="aligned-history")
        )
    return result


def vpa_bounds_assessment(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    evaluated_at: datetime,
    maximum_age: float,
) -> AutoscalerAssessment:
    result = AutoscalerAssessment(
        reasons=_configuration_reasons(snapshot, cluster, workload, evaluated_at, maximum_age)
    )
    configuration = workload.autoscaler_configuration
    if result.reasons or configuration is None or not configuration.vpas:
        return result
    if len(configuration.vpas) != 1:
        result.reasons.append("ambiguous_vpa_controller")
        return result
    vpa = configuration.vpas[0]
    result.reasons.extend(vpa.evidence_issues)
    if not vpa.recommendations:
        result.reasons.append("missing_vpa_recommendation")
        return result
    policies = {item.container_name: item for item in vpa.container_policies}
    containers = {item.name: item for item in workload.containers}
    for recommendation in vpa.recommendations:
        container = containers.get(recommendation.container_name)
        policy = policies.get(recommendation.container_name, policies.get("*"))
        if container is None:
            result.reasons.append("vpa_recommendation_container_mismatch")
            continue
        if policy is None or policy.min_allowed is None or policy.max_allowed is None:
            result.reasons.append("missing_vpa_policy_bounds")
            continue
        found_resource = False
        uncapped = recommendation.uncapped_target
        for attribute, unit, target, lower, upper, minimum, maximum, raw_target in [
            (
                "cpu_mcores",
                "mCPU",
                recommendation.target.cpu_mcores,
                recommendation.lower_bound.cpu_mcores,
                recommendation.upper_bound.cpu_mcores,
                policy.min_allowed.cpu_mcores,
                policy.max_allowed.cpu_mcores,
                uncapped.cpu_mcores if uncapped is not None else None,
            ),
            (
                "memory_mib",
                "MiB",
                recommendation.target.memory_mib,
                recommendation.lower_bound.memory_mib,
                recommendation.upper_bound.memory_mib,
                policy.min_allowed.memory_mib,
                policy.max_allowed.memory_mib,
                uncapped.memory_mib if uncapped is not None else None,
            ),
        ]:
            if all(item is None for item in [target, lower, upper, minimum, maximum]):
                continue
            found_resource = True
            if (
                target is None
                or lower is None
                or upper is None
                or minimum is None
                or maximum is None
            ):
                result.reasons.append("incomplete_vpa_resource_bounds")
                continue
            if not (0 < lower <= target <= upper and 0 <= minimum <= target <= maximum):
                result.reasons.append("contradictory_vpa_resource_bounds")
                continue
            for metric, value in [
                (f"vpa_target_{attribute}", target),
                (f"vpa_lower_{attribute}", lower),
                (f"vpa_upper_{attribute}", upper),
                (f"vpa_min_allowed_{attribute}", minimum),
                (f"vpa_max_allowed_{attribute}", maximum),
                (
                    f"vpa_uncapped_{attribute}",
                    raw_target,
                ),
            ]:
                result.evidence.append(
                    Evidence(metric=metric, value=value, unit=unit, source="kubernetes-api")
                )
        if not found_resource:
            result.reasons.append("missing_vpa_resource_bounds")
        result.evidence.append(
            Evidence(
                metric="container", value=recommendation.container_name, source="kubernetes-api"
            )
        )
    result.evidence.extend(
        [
            Evidence(metric="vpa_uid", value=vpa.uid, source="kubernetes-api"),
            Evidence(metric="vpa_update_mode", value=vpa.update_mode, source="kubernetes-api"),
        ]
    )
    result.has_signal = bool(vpa.recommendations) and not result.reasons
    return result
