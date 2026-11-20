from __future__ import annotations

from datetime import datetime

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    Evidence,
    Recommendation,
    Severity,
    StartupHistoryEvidence,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment
from aks_fleet_efficiency.startup import review_startup_history


def assess_startup(
    cluster: ClusterSnapshot,
    workload: WorkloadSnapshot,
    history: StartupHistoryEvidence | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    context = (
        review_startup_history(
            history,
            as_of=evaluated_at,
            maximum_source_age_seconds=min(
                history.maximum_source_age_seconds,
                int(config.thresholds.maximum_evidence_age_hours * 3600),
            ),
        )
        if history is not None
        else None
    )
    reasons = list(context.issues) if context else ["missing_startup_history"]
    if context and (
        context.cluster_resource_id,
        context.cluster_uid,
        context.namespace,
        context.workload_uid,
    ) != (cluster.resource_id, cluster.uid, workload.namespace, workload.uid):
        reasons.append("startup_identity_mismatch")
    values = [
        (
            "observed_readiness_lower",
            context.pod_to_observed_ready_lower_seconds if context else None,
            "seconds since Pod creation; sampled proxy",
        ),
        (
            "observed_readiness_upper",
            context.pod_to_observed_ready_upper_seconds if context else None,
            "seconds since Pod creation; sampled proxy",
        ),
        (
            "post_readiness_cpu_p95",
            context.post_readiness_cpu_p95_mcpu if context else None,
            "mCPU",
        ),
        (
            "post_readiness_memory_p99",
            context.post_readiness_memory_p99_mib if context else None,
            "MiB working set",
        ),
    ]
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=pack.title,
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=workload.namespace,
            workload=workload.name,
            severity=Severity.INFO,
            confidence=Confidence.MEDIUM,
            category="reliability",
            evidence=[
                Evidence(metric=name, value=value, unit=unit, source="saved-lifecycle-history")
                for name, value, unit in values
                if value is not None
            ],
            metadata={
                "first_startup": "unknown",
                "application_startup_duration_seconds": None,
                "source_admission": context.source_admission if context else "unknown",
                "usage_issues": context.usage_issues if context else [],
                "pod_uid": context.pod_uid if context else None,
                "container": context.container if context else None,
            },
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
        ),
        metrics=None,
        reasons=reasons,
        has_signal=bool(context and context.status == "observed_transition"),
    )
