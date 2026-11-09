from __future__ import annotations

from datetime import datetime

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    Evidence,
    Recommendation,
    SchedulingPodEvidence,
    Severity,
)
from aks_fleet_efficiency.rules.evidence import RuleAssessment


def assess_scheduling(
    cluster: ClusterSnapshot,
    pod: SchedulingPodEvidence | None,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    inventory = cluster.scheduling
    reasons = []
    if inventory is None:
        reasons.append("missing_scheduling_inventory")
    else:
        reasons.extend(inventory.issues)
        if (
            inventory.cluster_resource_id != cluster.resource_id
            or inventory.cluster_uid is None
            or inventory.cluster_uid != cluster.uid
        ):
            reasons.append("scheduling_identity_mismatch")
        if inventory.observed_at > evaluated_at:
            reasons.append("future_scheduling_inventory")
        elif (
            evaluated_at - inventory.observed_at
        ).total_seconds() > config.thresholds.maximum_evidence_age_hours * 3600:
            reasons.append("stale_scheduling_inventory")
    if pod is not None:
        reasons.extend(pod.issues)
        if not all([pod.namespace_uid, pod.workload_uid, pod.workload_name, pod.workload_kind]):
            reasons.append("missing_scheduling_identity")
    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=pack.title,
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=pod.namespace if pod else None,
            workload=pod.workload_name if pod else None,
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            category="scheduling",
            evidence=[
                Evidence(metric=key, value=value, unit="entries", source="kubernetes-metadata")
                for key, value in sorted(pod.constraints.items() if pod else [])
            ]
            + [
                Evidence(
                    metric=key,
                    value=value,
                    unit="observed objects; not matched or historical",
                    source="kubernetes-metadata",
                )
                for key, value in [
                    (
                        "tainted_node_context",
                        len(inventory.tainted_node_uids) if inventory else None,
                    ),
                    (
                        "cordoned_node_context",
                        len(inventory.cordoned_node_uids) if inventory else None,
                    ),
                    ("daemonset_context", len(inventory.daemonset_uids) if inventory else None),
                    (
                        "namespace_pdb_candidates",
                        len(pod.namespace_pdb_candidates) if pod else None,
                    ),
                ]
            ],
            metadata={
                "current_only": True,
                "pod_uid": pod.pod_uid if pod else None,
                "namespace_uid": pod.namespace_uid if pod else None,
                "workload_uid": pod.workload_uid if pod else None,
                "namespace_pdb_candidates": pod.namespace_pdb_candidates if pod else [],
                "pdb_matching": "unknown",
                "unobserved_fields": pod.unobserved_fields if pod else [],
                "tainted_node_uids": inventory.tainted_node_uids if inventory else [],
                "cordoned_node_uids": inventory.cordoned_node_uids if inventory else [],
                "daemonset_uids": inventory.daemonset_uids if inventory else [],
                "unobserved_context": inventory.unobserved_context if inventory else [],
                "label_matching": "unsupported_projected_labels",
            },
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
        ),
        metrics=None,
        reasons=reasons,
        has_signal=bool(pod and (pod.constraints or pod.namespace_pdb_candidates)),
    )


SCHEDULING_EVALUATORS = {"scheduling-review": assess_scheduling}
