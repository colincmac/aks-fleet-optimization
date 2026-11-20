from __future__ import annotations

from datetime import datetime

from aks_fleet_efficiency.catalog.models import PackManifest
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    Confidence,
    Evidence,
    PodDisruptionBudgetEvidence,
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


def assess_optimization_constraints(
    cluster: ClusterSnapshot,
    subject: SchedulingPodEvidence | PodDisruptionBudgetEvidence,
    config: AdvisorConfig,
    pack: PackManifest,
    recommendation_id: str,
    evaluated_at: datetime,
) -> RuleAssessment:
    inventory = cluster.scheduling
    reasons: list[str] = []
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

    if isinstance(subject, SchedulingPodEvidence):
        reasons.extend(subject.issues)
        if not all(
            [
                subject.namespace_uid,
                subject.workload_uid,
                subject.workload_name,
                subject.workload_kind,
            ]
        ):
            reasons.append("missing_scheduling_identity")
        if not subject.container_probes:
            reasons.append("missing_probe_evidence")
        missing_probes = {
            container.container: [
                name
                for name, present in [
                    ("liveness", container.liveness_probe),
                    ("readiness", container.readiness_probe),
                    ("startup", container.startup_probe),
                ]
                if not present
            ]
            for container in subject.container_probes
            if not all(
                [
                    container.liveness_probe,
                    container.readiness_probe,
                    container.startup_probe,
                ]
            )
        }
        workload_kind_supported = subject.workload_kind in {"Deployment", "StatefulSet"}
        replicated_workload = (
            subject.workload_replicas is not None and subject.workload_replicas >= 2
        )
        topology_status = (
            "not_observed"
            if not subject.topology_spread
            else "skew_greater_than_one_observed"
            if any(item.max_skew > 1 for item in subject.topology_spread)
            else "observed"
        )
        has_signal = workload_kind_supported and bool(
            missing_probes or (replicated_workload and topology_status != "observed")
        )
        evidence = [
            Evidence(
                metric="containers_with_missing_probe_types",
                value=len(missing_probes),
                unit="containers",
                source="kubernetes-metadata",
            ),
            Evidence(
                metric="topology_spread_constraints",
                value=len(subject.topology_spread),
                unit="current admitted constraints",
                source="kubernetes-metadata",
            ),
        ]
        metadata = {
            "constraint_kind": "workload-readiness",
            "current_only": True,
            "pod_uid": subject.pod_uid,
            "namespace_uid": subject.namespace_uid,
            "workload_uid": subject.workload_uid,
            "workload_kind": subject.workload_kind,
            "workload_replicas": subject.workload_replicas,
            "workload_kind_supported": workload_kind_supported,
            "missing_probes": missing_probes,
            "topology_spread": topology_status,
            "topology_constraints": [
                item.model_dump(mode="json") for item in subject.topology_spread
            ],
            "constrained_optimizations": [
                "horizontal-scaling",
                "voluntary-disruption",
                "nap-consolidation",
                "fleet-portability",
            ],
        }
        namespace = subject.namespace
        workload = subject.workload_name
    else:
        reasons.extend(issue for issue in subject.issues if issue != "missing_pdb_availability")
        missing_availability = "missing_pdb_availability" in subject.issues
        if subject.disruptions_allowed is None and not missing_availability:
            reasons.append("missing_pdb_disruption_status")
        has_signal = missing_availability or subject.disruptions_allowed == 0
        evidence = [
            Evidence(
                metric="disruptions_allowed",
                value=subject.disruptions_allowed,
                unit="pods at observation time",
                source="kubernetes-metadata",
            ),
            Evidence(
                metric="expected_pods",
                value=subject.expected_pods,
                unit="pods at observation time",
                source="kubernetes-metadata",
            ),
        ]
        metadata = {
            "constraint_kind": "voluntary-disruption",
            "current_only": True,
            "pdb_uid": subject.uid,
            "pdb_name": subject.name,
            "pdb_matching": "unknown",
            "min_available": subject.min_available,
            "selector_evidence": subject.model_dump(
                mode="json",
                include={
                    "namespace_uid",
                    "selector_match_status",
                    "selector_matched_pod_uids",
                    "selector_unmatched_pod_uids",
                    "selector_unknown_pod_uids",
                    "selector_issues",
                    "disruption_feasibility",
                },
            ),
            "max_unavailable": subject.max_unavailable,
            "disruptions_allowed": subject.disruptions_allowed,
            "expected_pods": subject.expected_pods,
            "availability_configuration": ("missing" if missing_availability else "observed"),
            "constrained_optimizations": [
                "voluntary-disruption",
                "nap-consolidation",
            ],
        }
        namespace = subject.namespace
        workload = None

    return RuleAssessment(
        recommendation=Recommendation(
            id=recommendation_id,
            rule_id=pack.id,
            rule_version=pack.version,
            title=pack.title,
            summary=pack.baseline_summary if config.mode == "baseline" else pack.guarded_summary,
            resource_id=cluster.resource_id,
            cluster_name=cluster.name,
            namespace=namespace,
            workload=workload,
            severity=Severity.INFO,
            confidence=Confidence.LOW,
            category="scheduling",
            evidence=evidence,
            metadata=metadata,
            prerequisites=pack.prerequisites,
            risks=pack.risks,
            validation_steps=pack.validation,
            rollback_steps=pack.rollback,
            proposed_actions=pack.actions[config.mode],
        ),
        metrics=None,
        reasons=reasons,
        has_signal=has_signal,
    )


CONSTRAINT_EVALUATORS = {"optimization-constraints": assess_optimization_constraints}
