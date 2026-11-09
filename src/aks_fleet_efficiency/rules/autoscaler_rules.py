from __future__ import annotations

from datetime import datetime

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    Evidence,
    FleetSnapshot,
    Recommendation,
    Severity,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.rules.autoscalers import (
    AutoscalerAssessment,
    autoscaler_conflict_evidence,
    controller_responsibility_assessment,
    hpa_change_assessment,
    hpa_pinning_assessment,
    replica_floor_assessment,
    vpa_bounds_assessment,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment


def _assessment(
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    result: AutoscalerAssessment,
    category: str,
    *,
    metadata: dict[str, str | bool | None] | None = None,
    bound_state: str | None = None,
) -> RuleAssessment:
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=f"{pack.title.replace('__bound_state__', bound_state or 'replica-bound')} "
            f"for {workload.name}",
            summary=" ".join(
                pack.summary_variants[code]
                if code != "default"
                else (pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary)
                for code in result.summary_codes
            ),
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            category=category,
            evidence=result.evidence,
            owner=workload.safety_policy.owner if workload.safety_policy else None,
            current_replica_floor=result.current_floor,
            proposed_replica_floor=result.proposed_floor,
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=[
                step.replace("__current_floor__", str(result.current_floor))
                for step in pack.rollback
            ],
            proposed_actions=pack.actions[config.mode],
            metadata=metadata if metadata is not None else {"workload_uid": workload.uid},
        ),
        metrics=result.metrics,
        qualities=result.qualities,
        reasons=result.reasons,
        has_signal=result.has_signal,
    )


def fixed_replica_review(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment | None:
    autoscaling = workload.autoscaling
    controllers = workload.autoscaler_configuration
    if (
        workload.replicas < config.thresholds.minimum_replicas_for_autoscaling_review
        or autoscaling.hpa is True
        or autoscaling.keda is True
        or (controllers is not None and (controllers.hpas or controllers.kedas))
    ):
        return None
    result = _assessment(
        cluster,
        workload,
        config,
        pack,
        recommendation_id,
        AutoscalerAssessment(
            evidence=[
                Evidence(
                    metric="replicas", value=workload.replicas, unit="pods", source="kubernetes-api"
                ),
                Evidence(metric="hpa_present", value=False, source="kubernetes-api"),
                Evidence(metric="keda_present", value=False, source="kubernetes-api"),
            ],
            reasons=["unknown_autoscaler"]
            if autoscaling.hpa is None
            or autoscaling.keda is None
            or (controllers is not None and (not controllers.hpa_observed or controllers.issues))
            else [],
            has_signal=True,
        ),
        "workload-autoscaling",
        metadata={},
    )
    result.recommendation.title = f"{pack.title} for {workload.namespace}/{workload.name}"
    result.recommendation.owner = None
    result.recommendation.severity = Severity.LOW
    coverage = snapshot.metric_window.coverage_ratio
    result.recommendation.confidence = (
        Confidence.HIGH
        if coverage >= 0.95
        else Confidence.MEDIUM
        if coverage >= 0.85
        else Confidence.LOW
    )
    return result


def autoscaler_interaction(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    evidence, reasons = autoscaler_conflict_evidence(
        snapshot,
        cluster,
        workload,
        evaluated_at,
        config.thresholds.maximum_evidence_age_hours * 3600,
    )
    return _assessment(
        cluster,
        workload,
        config,
        pack,
        recommendation_id,
        AutoscalerAssessment(evidence=evidence, reasons=reasons, has_signal=bool(evidence)),
        "autoscaler-interaction",
        metadata={"current_only": True, "workload_uid": workload.uid},
    )


def hpa_pinning(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    pinning = hpa_pinning_assessment(
        snapshot,
        cluster,
        workload,
        evaluated_at,
        config.thresholds.maximum_evidence_age_hours * 3600,
    )
    return _assessment(
        cluster,
        workload,
        config,
        pack,
        recommendation_id,
        AutoscalerAssessment(
            metrics=pinning.metrics,
            qualities=pinning.qualities,
            reasons=pinning.reasons,
            evidence=pinning.evidence,
            has_signal=pinning.bound_state is not None,
        ),
        "autoscaler-replica-bound",
        metadata={"bound_state": pinning.bound_state},
        bound_state=pinning.bound_state,
    )


def controller_responsibility(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    result = controller_responsibility_assessment(
        snapshot,
        cluster,
        workload,
        evaluated_at,
        config.thresholds.maximum_evidence_age_hours * 3600,
    )
    return _assessment(
        cluster, workload, config, pack, recommendation_id, result, "autoscaler-investigation"
    )


def hpa_floor_proposal(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    result = replica_floor_assessment(
        snapshot,
        cluster,
        workload,
        evaluated_at,
        config.thresholds.maximum_evidence_age_hours * 3600,
    )
    if config.environment_risk.get(cluster.environment or "") not in {"low", "medium", "high"}:
        result.reasons.append("unknown_environment_policy")
    return _assessment(
        cluster, workload, config, pack, recommendation_id, result, "autoscaler-replica-floor"
    )


def hpa_change_review(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    result = hpa_change_assessment(
        snapshot,
        cluster,
        workload,
        evaluated_at,
        config.thresholds.maximum_evidence_age_hours * 3600,
    )
    return _assessment(
        cluster, workload, config, pack, recommendation_id, result, "autoscaler-investigation"
    )


def vpa_bounds_review(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    result = vpa_bounds_assessment(
        snapshot,
        cluster,
        workload,
        evaluated_at,
        config.thresholds.maximum_evidence_age_hours * 3600,
    )
    return _assessment(
        cluster, workload, config, pack, recommendation_id, result, "autoscaler-investigation"
    )


AUTOSCALER_EVALUATORS = {
    "fixed-replica-review": fixed_replica_review,
    "autoscaler-interaction": autoscaler_interaction,
    "hpa-pinning": hpa_pinning,
    "controller-responsibility": controller_responsibility,
    "hpa-floor-proposal": hpa_floor_proposal,
    "hpa-change-review": hpa_change_review,
    "vpa-bounds-review": vpa_bounds_review,
}
