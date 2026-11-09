from __future__ import annotations

from math import ceil, isfinite

from aks_fleet_efficiency.analysis.efficiency import safe_ratio
from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    ContainerSnapshot,
    Evidence,
    FleetSnapshot,
    Recommendation,
    ResourceObservation,
    ResourceRequests,
    Severity,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment


def autoscaler_reasons(workload: WorkloadSnapshot) -> list[str]:
    reasons = []
    autoscaling = workload.autoscaling
    if autoscaling.hpa is None or autoscaling.keda is None:
        reasons.append("unknown_autoscaler")
    if autoscaling.vpa is None and autoscaling.vpa_mode is None:
        reasons.append("unknown_autoscaler")
    if autoscaling.vpa is True and autoscaling.vpa_mode is None:
        reasons.append("unknown_autoscaler")
    if autoscaling.hpa or autoscaling.keda or autoscaling.vpa_mode not in {None, "Off"}:
        reasons.append("autoscaler_interaction_review_required")
    configuration = workload.autoscaler_configuration
    if workload.hpa_replica_history is not None:
        reasons.append("autoscaler_interaction_review_required")
    if configuration is not None:
        if (
            configuration.hpas
            or configuration.kedas
            or any(item.update_mode != "Off" for item in configuration.vpas)
        ):
            reasons.append("autoscaler_interaction_review_required")
        if (
            configuration.issues
            or not configuration.hpa_observed
            or not configuration.vpa_observed
            or not configuration.keda_observed
        ):
            reasons.append("unknown_autoscaler")
    return reasons


def cpu_proposal(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    resources: ResourceObservation,
    config: AdvisorConfig,
) -> tuple[float | None, list[str]]:
    reasons = []
    if not cluster.uid or not workload.uid:
        reasons.append("missing_identity")
    if resources.cpu_observation_basis is None:
        reasons.append("unknown_metric_aggregation")
    if not resources.cpu_request_observed or "request_cpu_mcores" not in resources.model_fields_set:
        reasons.append("missing_request_observation")
    if config.environment_risk.get(cluster.environment or "") not in {"low", "medium", "high"}:
        reasons.append("unknown_environment_policy")
    reasons.extend(autoscaler_reasons(workload))
    if resources.memory_oom_events is not None and resources.memory_oom_events > 0:
        reasons.append("oom_history")
    if workload.eviction_events is not None and workload.eviction_events > 0:
        reasons.append("collected_eviction_history")
    policy = workload.safety_policy
    if policy is None:
        return None, [*reasons, "missing_safety_policy"]
    if not policy.disruption_reviewed:
        reasons.append("unreviewed_disruption")
    if (
        policy.reviewed_window_start != snapshot.metric_window.start
        or policy.reviewed_window_end != snapshot.metric_window.end
    ):
        reasons.append("unreviewed_window")
    if (
        resources.cpu_throttled_ratio is not None
        and resources.cpu_throttled_ratio > policy.maximum_cpu_throttled_ratio
    ):
        reasons.append("elevated_throttling")
    if resources.request_cpu_mcores is None or resources.usage_cpu_p99_mcores is None:
        return None, [*reasons, "missing_metric"]
    peak = resources.usage_cpu_p99_mcores
    for name in ["usage_cpu_p95_mcores", "usage_cpu_p99_mcores"]:
        quality = resources.metric_quality.get(name)
        if quality is not None and quality.maximum is not None:
            peak = max(peak, quality.maximum)
    target = max(
        policy.minimum_cpu_request_mcores,
        resources.request_cpu_mcores * (1 - policy.maximum_cpu_reduction_ratio),
        peak * policy.cpu_headroom_factor,
    )
    if not isfinite(target):
        return None, [*reasons, "no_safe_reduction"]
    proposed = float(ceil(target))
    if proposed >= resources.request_cpu_mcores:
        reasons.append("no_safe_reduction")
    return proposed, reasons


def assess_cpu_request(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    review_ratio: float | None,
) -> RuleAssessment | None:
    if review_ratio is None:
        raise ValueError("CPU review ratio is required")
    resources = container.resources
    ratio = safe_ratio(resources.usage_cpu_p95_mcores, resources.request_cpu_mcores)
    if not (
        (
            resources.request_cpu_mcores is not None
            and resources.request_cpu_mcores > 0
            and (ratio is None or ratio < review_ratio)
        )
        or (config.packs is not None and ratio is None)
    ):
        return None
    guarded = config.mode == "guarded"
    reasons: list[str] = []
    proposed: float | None = None
    if guarded:
        proposed, reasons = cpu_proposal(snapshot, cluster, workload, resources, config)
    else:
        if not cluster.uid or not workload.uid:
            reasons.append("missing_identity")
        if resources.cpu_observation_basis is None:
            reasons.append("unknown_metric_aggregation")
        if not resources.cpu_request_observed:
            reasons.append("missing_request_observation")
    if ratio is None:
        reasons.append("missing_metric")
    metrics: dict[str, tuple[float | int | None, str]] = {
        "usage_cpu_p95_mcores": (resources.usage_cpu_p95_mcores, "mCPU"),
    }
    if guarded:
        metrics.update(
            usage_cpu_p99_mcores=(resources.usage_cpu_p99_mcores, "mCPU"),
            cpu_throttled_ratio=(resources.cpu_throttled_ratio, "ratio"),
            memory_oom_events=(resources.memory_oom_events, "events"),
        )
    quality = resources.metric_quality.get("usage_cpu_p95_mcores")
    evidence = [
        Evidence(
            metric="cpu_p95_to_request_ratio",
            value=round(ratio, 4) if ratio is not None else None,
            unit="ratio",
            source=quality.source if quality is not None else "unknown",
        ),
        Evidence(
            metric="cpu_observation_basis",
            value=resources.cpu_observation_basis,
            source="normalized-evidence",
        ),
    ]
    if guarded:
        evidence.append(
            Evidence(
                metric="potential_cpu_request_reduction",
                value=round(resources.request_cpu_mcores - proposed, 2)
                if resources.request_cpu_mcores is not None and proposed is not None
                else None,
                unit="mCPU per replica",
                source="derived",
            )
        )
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title} for {workload.name}/{container.name}",
            summary=pack.guarded_summary if guarded else pack.baseline_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            category="workload-rightsizing" if guarded else "cpu-request-investigation",
            evidence=evidence,
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            proposed_actions=pack.actions[config.mode],
            metadata={
                "container": container.name,
                "replicas": workload.replicas,
                "review_ratio": review_ratio,
                "slo_reference": workload.safety_policy.slo_reference
                if workload.safety_policy
                else None,
                "risk_level": config.environment_risk.get(cluster.environment or ""),
                "source_queries": {
                    name: resources.metric_quality[name].query_expression
                    for name in metrics
                    if name in resources.metric_quality
                },
            },
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            current_requests=ResourceRequests(cpu_mcores=resources.request_cpu_mcores)
            if guarded and resources.request_cpu_mcores is not None
            else None,
            proposed_requests=ResourceRequests(cpu_mcores=proposed)
            if guarded and proposed is not None
            else None,
            rollback_steps=[
                step.replace("__current_cpu_request__", str(resources.request_cpu_mcores))
                for step in pack.rollback
            ]
            if guarded
            else pack.baseline_rollback,
        ),
        metrics=metrics,
        reasons=reasons,
        has_signal=ratio is not None and ratio < review_ratio,
    )


def assess_missing_cpu_request(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    review_ratio: float | None,
) -> RuleAssessment:
    resources = container.resources
    observed = resources.cpu_request_observed and "request_cpu_mcores" in resources.model_fields_set
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
            confidence=Confidence.HIGH,
            category="resource-governance",
            evidence=[
                Evidence(
                    metric="request_cpu_mcores",
                    value=resources.request_cpu_mcores,
                    unit="mCPU",
                    source="kubernetes-api",
                )
            ],
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
            metadata={"container": container.name},
        ),
        metrics=None,
        reasons=[] if observed else ["missing_request_observation"],
        has_signal=resources.request_cpu_mcores is None or resources.request_cpu_mcores == 0,
    )


def assess_cpu_request_risk(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    container: ContainerSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    review_ratio: float | None,
) -> RuleAssessment:
    if review_ratio is None:
        raise ValueError("CPU risk review ratio is required")
    resources = container.resources
    ratio = safe_ratio(resources.usage_cpu_p95_mcores, resources.request_cpu_mcores)
    quality = resources.metric_quality.get("usage_cpu_p95_mcores")
    throttling = resources.metric_quality.get("cpu_throttled_ratio")
    reasons = [] if resources.cpu_request_observed else ["missing_request_observation"]
    if not cluster.uid or not workload.uid:
        reasons.append("missing_identity")
    if ratio is None:
        reasons.append("missing_metric")
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
            evidence=[
                Evidence(
                    metric="cpu_p95_to_request_ratio",
                    value=round(ratio, 4) if ratio is not None else None,
                    unit="ratio",
                    source=quality.source if quality is not None else "unknown",
                ),
                Evidence(
                    metric="cpu_throttled_ratio",
                    value=resources.cpu_throttled_ratio,
                    unit="ratio",
                    source=throttling.source if throttling is not None else "unknown",
                ),
            ],
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
            metadata={"container": container.name, "review_ratio": review_ratio},
        ),
        metrics={
            "usage_cpu_p95_mcores": (resources.usage_cpu_p95_mcores, "mCPU"),
            "cpu_throttled_ratio": (resources.cpu_throttled_ratio, "ratio"),
        },
        reasons=reasons,
        has_signal=ratio is not None and ratio > review_ratio,
    )


CPU_EVALUATORS = {
    "cpu-request-review": assess_cpu_request,
    "missing-cpu-request": assess_missing_cpu_request,
    "cpu-request-risk": assess_cpu_request_risk,
}
