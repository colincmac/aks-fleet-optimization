from __future__ import annotations

from datetime import datetime
from math import ceil, isfinite

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    ContainerSnapshot,
    Evidence,
    FleetSnapshot,
    MemorySafetyPolicy,
    MetricQuality,
    Recommendation,
    ResourceLimits,
    ResourceObservation,
    ResourceRequests,
    Severity,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.rules.autoscalers import _configuration_reasons
from aks_fleet_efficiency.rules.cpu import autoscaler_reasons as _autoscaler_reasons
from aks_fleet_efficiency.rules.evidence import RuleAssessment
from aks_fleet_efficiency.rules.evidence import metric_source as _metric_source
from aks_fleet_efficiency.rules.evidence import quality_reasons as _quality_reasons
from aks_fleet_efficiency.rules.memory import (
    memory_limit_assessment,
    memory_limit_configuration_digest,
    termination_review_reasons,
)


def _memory_review_reasons(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    resources: ResourceObservation,
    container_name: str,
    config: AdvisorConfig,
) -> list[str]:
    reasons = _autoscaler_reasons(workload)
    if not cluster.uid or not workload.uid:
        reasons.append("missing_identity")
    if config.environment_risk.get(cluster.environment or "") not in {"low", "medium", "high"}:
        reasons.append("unknown_environment_policy")
    if resources.memory_observation_basis not in {"pod", "replica-envelope"}:
        reasons.append("unsupported_memory_history")
    if resources.memory_observation_basis == "replica-envelope" and (
        not resources.memory_membership_digest
    ):
        reasons.append("missing_memory_membership_digest")
    if workload.eviction_events is not None and workload.eviction_events > 0:
        reasons.append("collected_eviction_history")
    reasons.extend(termination_review_reasons(snapshot, workload))
    if not resources.memory_request_observed:
        reasons.append("missing_memory_request_observation")
    if not resources.memory_limit_observed:
        reasons.append("missing_memory_limit_observation")
    for field, amount, code in [
        ("request_memory_mib", resources.request_memory_mib, "unstable_memory_request"),
        ("limit_memory_mib", resources.limit_memory_mib, "unstable_memory_limit"),
    ]:
        quality = resources.metric_quality.get(field)
        if quality is not None and (
            not (
                amount is not None and amount > 0 and (quality.minimum == quality.maximum == amount)
            )
        ):
            reasons.append(code)
    if (
        resources.request_memory_mib is not None
        and resources.limit_memory_mib is not None
        and (resources.request_memory_mib >= resources.limit_memory_mib)
    ):
        reasons.append("memory_limit_change_review_required")
    for count, code in [
        (resources.memory_oom_events, "oom_history"),
        (resources.restart_events, "restart_history"),
    ]:
        if count is not None and count > 0:
            reasons.append(code)
    for field, count in [
        ("memory_oom_events", resources.memory_oom_events),
        ("restart_events", resources.restart_events),
    ]:
        quality = resources.metric_quality.get(field)
        if quality is not None and count == 0:
            if quality.minimum != 0 or quality.maximum != 0:
                reasons.append("inconsistent_reliability_history")
    p95 = resources.metric_quality.get("usage_memory_p95_mib")
    p99 = resources.metric_quality.get("usage_memory_p99_mib")
    if p95 is None or p99 is None or p95.maximum is None or (p99.maximum is None):
        reasons.append("missing_memory_peak")
    if (
        resources.usage_memory_p95_mib is not None
        and resources.usage_memory_p99_mib is not None
        and (resources.usage_memory_p95_mib > resources.usage_memory_p99_mib)
    ) or (
        p95 is not None
        and p99 is not None
        and (
            (p95.source, p95.query_version, p95.step_seconds, p95.minimum, p95.maximum)
            != (p99.source, p99.query_version, p99.step_seconds, p99.minimum, p99.maximum)
        )
    ):
        reasons.append("inconsistent_memory_usage")
    if workload.qos_class is None:
        reasons.append("unknown_qos_class")
    policy = workload.safety_policy
    memory = policy.memory.get(container_name) if policy is not None else None
    if policy is None or memory is None:
        return [*reasons, "missing_memory_safety_policy"]
    if not policy.disruption_reviewed:
        reasons.append("unreviewed_disruption")
    if (
        policy.reviewed_window_start != snapshot.metric_window.start
        or policy.reviewed_window_end != snapshot.metric_window.end
    ):
        reasons.append("unreviewed_window")
    if memory.qos_class is None:
        reasons.append("unreviewed_qos_class")
    elif memory.qos_class != workload.qos_class:
        reasons.append("qos_class_mismatch")
    if workload.qos_class is not None and workload.qos_class != "Burstable":
        reasons.append("qos_preservation_review_required")
    if memory.startup_peak_mib is None:
        reasons.append("missing_startup_memory_review")
    if memory.failover_peak_mib is None:
        reasons.append("missing_failover_memory_review")
    if memory.eviction_events is None:
        reasons.append("missing_eviction_review")
    elif memory.eviction_events > 0:
        reasons.append("eviction_history")
    request = resources.request_memory_mib
    if request is not None:
        if request <= memory.minimum_request_mib:
            reasons.append("memory_policy_floor")
        peaks = [
            memory.startup_peak_mib,
            memory.failover_peak_mib,
            p95.maximum if p95 is not None else None,
            p99.maximum if p99 is not None else None,
        ]
        if any(peak is not None and peak * memory.headroom_factor >= request for peak in peaks):
            reasons.append("insufficient_memory_headroom")
    return reasons


def _memory_request_proposal(
    resources: ResourceObservation, policy: MemorySafetyPolicy
) -> tuple[float | None, list[str]]:
    reasons = []
    for name in [
        "request_memory_mib",
        "limit_memory_mib",
        "usage_memory_p95_mib",
        "usage_memory_p99_mib",
        "memory_oom_events",
        "restart_events",
    ]:
        quality = resources.metric_quality.get(name)
        if quality is None:
            reasons.append("missing_metric_quality")
            continue
        duration = (quality.window.end - quality.window.start).total_seconds()
        if (
            quality.window.coverage_ratio != 1
            or duration % quality.step_seconds != 0
            or quality.window.sample_count != duration / quality.step_seconds
        ):
            reasons.append("incomplete_memory_history")
    if reasons:
        return (None, reasons)
    usage = resources.metric_quality["usage_memory_p99_mib"]
    request = resources.request_memory_mib
    if (
        request is None
        or resources.usage_memory_p99_mib is None
        or usage.maximum is None
        or (policy.startup_peak_mib is None)
        or (policy.failover_peak_mib is None)
    ):
        return (None, ["missing_metric"])
    peak = max(
        resources.usage_memory_p99_mib,
        usage.maximum,
        policy.startup_peak_mib,
        policy.failover_peak_mib,
    )
    lower_bound = max(
        policy.minimum_request_mib,
        request * (1 - policy.maximum_reduction_ratio),
        peak * policy.headroom_factor,
    )
    if not isfinite(lower_bound) or lower_bound >= request:
        return (None, ["no_safe_memory_reduction"])
    proposed = float(ceil(lower_bound))
    if proposed >= request:
        return (None, ["no_safe_memory_reduction"])
    return (proposed, [])


def _readiness_basis(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> tuple[
    dict[str, tuple[float | int | None, str]],
    dict[str, MetricQuality],
    list[Evidence],
    list[str],
    MemorySafetyPolicy | None,
]:
    assert container is not None
    resources = container.resources
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    review_metrics: dict[str, tuple[float | int | None, str]] = {
        "request_memory_mib": (resources.request_memory_mib, "MiB"),
        "limit_memory_mib": (resources.limit_memory_mib, "MiB"),
        "usage_memory_p95_mib": (resources.usage_memory_p95_mib, "MiB"),
        "usage_memory_p99_mib": (resources.usage_memory_p99_mib, "MiB"),
        "memory_oom_events": (resources.memory_oom_events, "events"),
        "restart_events": (resources.restart_events, "events"),
    }
    review_qualities = dict(resources.metric_quality)
    if (
        resources.memory_observation_basis == "replica-envelope"
        or workload.eviction_quality is not None
    ):
        review_metrics["workload_eviction_events"] = (workload.eviction_events, "events")
        if workload.eviction_quality is not None:
            review_qualities["workload_eviction_events"] = workload.eviction_quality
    review_evidence = [
        Evidence(metric=name, value=value, unit=unit, source=_metric_source(review_qualities, name))
        for name, (value, unit) in review_metrics.items()
    ]
    review_evidence.extend(
        [
            Evidence(
                metric="memory_observation_basis",
                value=resources.memory_observation_basis,
                source="normalized-history",
            ),
            Evidence(
                metric="memory_membership_digest",
                value=resources.memory_membership_digest,
                source="approved-binding",
            ),
            Evidence(
                metric="current_replicas",
                value=workload.replicas,
                unit="pods",
                source="current-kubernetes-projection",
            ),
        ]
    )
    memory_policy = (
        workload.safety_policy.memory.get(container.name)
        if workload.safety_policy is not None
        else None
    )
    if memory_policy is not None:
        review_evidence.extend(
            (
                Evidence(
                    metric=name,
                    value=value,
                    unit=unit,
                    source=f"owner-reviewed:{memory_policy.evidence_reference}",
                )
                for name, value, unit in [
                    ("startup_peak_mib", memory_policy.startup_peak_mib, "MiB"),
                    ("failover_peak_mib", memory_policy.failover_peak_mib, "MiB"),
                    ("reviewed_eviction_events", memory_policy.eviction_events, "events"),
                    ("minimum_request_mib", memory_policy.minimum_request_mib, "MiB"),
                    ("maximum_reduction_ratio", memory_policy.maximum_reduction_ratio, "ratio"),
                    ("headroom_factor", memory_policy.headroom_factor, "ratio"),
                ]
            )
        )
    peak_quality = resources.metric_quality.get("usage_memory_p99_mib")
    review_evidence.extend(
        [
            Evidence(
                metric="observed_memory_working_set_peak_mib",
                value=peak_quality.maximum if peak_quality is not None else None,
                unit="MiB",
                source=_metric_source(resources.metric_quality, "usage_memory_p99_mib"),
            ),
            Evidence(metric="qos_class", value=workload.qos_class, source="kubernetes-api"),
        ]
    )
    review_reasons = _memory_review_reasons(
        snapshot, cluster, workload, resources, container.name, config
    )
    if resources.memory_observation_basis == "replica-envelope":
        if not workload.memory_admission_observed:
            review_reasons.append("unobserved_memory_admission")
        review_reasons.extend(
            _configuration_reasons(
                snapshot, cluster, workload, evaluated_at, maximum_age, require_keda=True
            )
        )
    return (review_metrics, review_qualities, review_evidence, review_reasons, memory_policy)


def oom_investigation(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    assert container is not None
    resources = container.resources
    memory_metrics: dict[str, tuple[float | int | None, str]] = {
        "memory_oom_events": (resources.memory_oom_events, "events")
    }
    memory_evidence = [
        Evidence(
            metric="memory_oom_events",
            value=resources.memory_oom_events,
            unit="events",
            source=_metric_source(resources.metric_quality, "memory_oom_events"),
        )
    ]
    for name, value in [
        ("usage_memory_p95_mib", resources.usage_memory_p95_mib),
        ("usage_memory_p99_mib", resources.usage_memory_p99_mib),
        (
            "request_memory_mib",
            resources.request_memory_mib if resources.memory_request_observed else None,
        ),
        (
            "limit_memory_mib",
            resources.limit_memory_mib if resources.memory_limit_observed else None,
        ),
    ]:
        if _quality_reasons(
            snapshot,
            {name: (value, "MiB")},
            resources.metric_quality,
            config,
            evaluated_at,
            maximum_age,
        ):
            continue
        memory_metrics[name] = (value, "MiB")
        memory_evidence.append(
            Evidence(
                metric=name,
                value=value,
                unit="MiB",
                source=_metric_source(resources.metric_quality, name),
            )
        )
        quality = resources.metric_quality[name]
        if name == "usage_memory_p99_mib" and quality.maximum is not None:
            memory_evidence.append(
                Evidence(
                    metric="observed_memory_working_set_peak_mib",
                    value=quality.maximum,
                    unit="MiB",
                    source=quality.source,
                )
            )
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}/{container.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.HIGH,
            confidence=Confidence.LOW,
            category="reliability-guardrail",
            evidence=memory_evidence,
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            metadata={"container": container.name},
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics=memory_metrics,
        qualities=resources.metric_quality,
        reasons=[] if cluster.uid and workload.uid else ["missing_identity"],
        has_signal=resources.memory_oom_events != 0,
    )


def memory_safety_review(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    assert container is not None
    resources = container.resources
    review_metrics, review_qualities, review_evidence, review_reasons, _memory_policy = (
        _readiness_basis(
            snapshot, cluster, workload, container, config, pack, recommendation_id, evaluated_at
        )
    )
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}/{container.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            category="memory-safety-review",
            evidence=review_evidence,
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            current_requests=ResourceRequests(memory_mib=resources.request_memory_mib)
            if resources.request_memory_mib is not None and resources.request_memory_mib > 0
            else None,
            metadata={"container": container.name},
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics=review_metrics,
        qualities=review_qualities,
        reasons=review_reasons,
        has_signal=True,
    )


def memory_request_proposal(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    assert container is not None
    resources = container.resources
    review_metrics, review_qualities, review_evidence, review_reasons, memory_policy = (
        _readiness_basis(
            snapshot, cluster, workload, container, config, pack, recommendation_id, evaluated_at
        )
    )
    proposal_reasons = review_reasons.copy()
    if memory_policy is None or not memory_policy.allow_request_reduction:
        proposal_reasons.append("memory_request_reduction_not_enabled")
    if workload.replicas != 1 and resources.memory_observation_basis != "replica-envelope":
        proposal_reasons.append("unsupported_memory_history")
    if workload.safety_policy is not None:
        if not workload.safety_policy.owner.strip():
            proposal_reasons.append("missing_memory_owner")
        if not workload.safety_policy.slo_reference.strip():
            proposal_reasons.append("missing_memory_slo_reference")
    memory_target = None
    proposal_reasons.extend(workload.memory_admission_issues)
    if not proposal_reasons and memory_policy is not None:
        memory_target, target_reasons = _memory_request_proposal(resources, memory_policy)
        proposal_reasons.extend(target_reasons)
    if memory_target is not None and workload.memory_admission_observed:
        if (
            (
                workload.memory_admission_minimum_mib is not None
                and memory_target < workload.memory_admission_minimum_mib
            )
            or (
                workload.memory_admission_maximum_mib is not None
                and memory_target > workload.memory_admission_maximum_mib
            )
            or (
                workload.memory_admission_maximum_mib is not None
                and resources.limit_memory_mib is not None
                and (resources.limit_memory_mib > workload.memory_admission_maximum_mib)
            )
            or (
                workload.memory_admission_limit_request_ratio is not None
                and resources.limit_memory_mib is not None
                and (
                    resources.limit_memory_mib / memory_target
                    > workload.memory_admission_limit_request_ratio
                )
            )
        ):
            proposal_reasons.append("memory_admission_constraint")
            memory_target = None
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}/{container.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            category="memory-efficiency",
            evidence=[
                *(item.model_copy(deep=True) for item in review_evidence),
                Evidence(
                    metric="allow_request_reduction",
                    value=memory_policy.allow_request_reduction
                    if memory_policy is not None
                    else False,
                    source="owner-policy",
                ),
            ],
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            current_requests=ResourceRequests(memory_mib=resources.request_memory_mib)
            if resources.request_memory_mib is not None and resources.request_memory_mib > 0
            else None,
            proposed_requests=ResourceRequests(memory_mib=memory_target)
            if memory_target is not None
            else None,
            metadata={"container": container.name},
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                memory_target,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics=review_metrics,
        qualities=review_qualities,
        reasons=proposal_reasons,
        has_signal=True,
    )


def pod_memory_accounting(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    accounting_evidence: list[Evidence] = []
    accounting_reasons = []
    for accounting in workload.pod_memory_accounting:
        accounting_reasons.extend(accounting.issues)
        if accounting.observed_at > evaluated_at or accounting.observed_at > snapshot.generated_at:
            accounting_reasons.append("future_memory_metadata")
        elif (evaluated_at - accounting.observed_at).total_seconds() > maximum_age:
            accounting_reasons.append("stale_memory_metadata")
        for metric, value in [
            ("pod_uid", accounting.pod_uid),
            ("application_memory_request", accounting.application_request_mib),
            ("init_peak_memory_request", accounting.init_peak_request_mib),
            ("pod_memory_overhead", accounting.overhead_mib),
            ("effective_pod_memory_request", accounting.effective_request_mib),
        ]:
            accounting_evidence.append(
                Evidence(
                    metric=metric,
                    value=value,
                    unit=None if metric == "pod_uid" else "MiB",
                    source="current-kubernetes-projection",
                )
            )
    if not workload.pod_memory_accounting:
        accounting_reasons.append("missing_effective_pod_memory")
    accounting_evidence.append(
        Evidence(
            metric="memory_limit_configuration_digest",
            value=memory_limit_configuration_digest(workload),
            source="current-configuration",
        )
    )
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
            category="effective-pod-memory",
            evidence=accounting_evidence,
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics=None,
        qualities=None,
        reasons=accounting_reasons,
        has_signal=True,
    )


def memory_limit_proposal(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    assert container is not None
    resources = container.resources
    limit_assessment = memory_limit_assessment(snapshot, workload, container.name)
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}/{container.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            category="memory-limit-review",
            evidence=limit_assessment.evidence,
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            current_limits=ResourceLimits(memory_mib=resources.limit_memory_mib)
            if resources.limit_memory_mib is not None and resources.limit_memory_mib > 0
            else None,
            proposed_limits=ResourceLimits(memory_mib=limit_assessment.proposed_mib)
            if limit_assessment.proposed_mib is not None
            else None,
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            metadata={"container": container.name},
        ),
        metrics=limit_assessment.metrics,
        qualities=limit_assessment.qualities,
        reasons=[
            *limit_assessment.reasons,
            *_autoscaler_reasons(workload),
            *_configuration_reasons(
                snapshot, cluster, workload, evaluated_at, maximum_age, require_keda=True
            ),
            *([] if cluster.uid and workload.uid else ["missing_identity"]),
            *(
                []
                if config.environment_risk.get(cluster.environment or "")
                in {"low", "medium", "high"}
                else ["unknown_environment_policy"]
            ),
        ],
        has_signal=limit_assessment.proposed_mib is not None,
    )


def restart_investigation(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    assert container is not None
    resources = container.resources
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}/{container.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            category="reliability-guardrail",
            evidence=[
                Evidence(
                    metric="restart_events",
                    value=resources.restart_events,
                    unit="events",
                    source=_metric_source(resources.metric_quality, "restart_events"),
                )
            ],
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            metadata={"container": container.name},
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics={"restart_events": (resources.restart_events, "events")},
        qualities=resources.metric_quality,
        reasons=[] if cluster.uid and workload.uid else ["missing_identity"],
        has_signal=resources.restart_events != 0,
    )


def termination_context(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    termination_evidence: list[Evidence] = []
    termination_reasons = list(workload.termination_issues)
    for context in workload.termination_context:
        if context.observed_at > evaluated_at or context.observed_at > snapshot.generated_at:
            termination_reasons.append("future_termination_metadata")
        elif (evaluated_at - context.observed_at).total_seconds() > maximum_age:
            termination_reasons.append("stale_termination_metadata")
        termination_values: list[tuple[str, str | int]] = [
            ("pod_uid", context.pod_uid),
            ("container", context.container),
            ("reported_termination_reason", context.reason),
            ("reported_exit_code", context.exit_code),
            ("termination_finished_at", context.finished_at.isoformat()),
        ]
        for metric, context_value in termination_values:
            termination_evidence.append(
                Evidence(metric=metric, value=context_value, source="current-kubernetes-status")
            )
    if not workload.termination_context:
        termination_reasons.append("missing_termination_context")
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            category="termination-context",
            evidence=termination_evidence,
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics=None,
        qualities=None,
        reasons=termination_reasons,
        has_signal=any(
            item.exit_code != 0 or item.reason != "Completed"
            for item in workload.termination_context
        ),
    )


def eviction_investigation(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}",
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            category="eviction-investigation",
            evidence=[
                Evidence(
                    metric="workload_eviction_events",
                    value=workload.eviction_events,
                    unit="events",
                    source=workload.eviction_quality.source
                    if workload.eviction_quality
                    else "unknown",
                )
            ],
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=memory_guidance(
                pack.actions[config.mode],
                container.resources if container is not None else None,
                None,
            ),
            rollback_steps=memory_guidance(
                pack.rollback, container.resources if container is not None else None
            ),
        ),
        metrics={"workload_eviction_events": (workload.eviction_events, "events")},
        qualities={"workload_eviction_events": workload.eviction_quality}
        if workload.eviction_quality
        else {},
        reasons=[],
        has_signal=workload.eviction_events != 0,
    )


def memory_guidance(
    items: list[str], resources: ResourceObservation | None, proposed: float | None = None
) -> list[str]:
    return [
        item.replace(
            "__current_request_mib__", str(resources.request_memory_mib if resources else None)
        )
        .replace("__current_limit_mib__", str(resources.limit_memory_mib if resources else None))
        .replace("__proposed_request_mib__", str(proposed))
        for item in items
    ]


MEMORY_EVALUATORS = {
    "oom-investigation": oom_investigation,
    "memory-safety-review": memory_safety_review,
    "memory-request-proposal": memory_request_proposal,
    "pod-memory-accounting": pod_memory_accounting,
    "memory-limit-proposal": memory_limit_proposal,
    "restart-investigation": restart_investigation,
    "termination-context": termination_context,
    "eviction-investigation": eviction_investigation,
}
