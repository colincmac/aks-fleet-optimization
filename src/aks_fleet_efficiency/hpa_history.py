from __future__ import annotations

from aks_fleet_efficiency.models import (
    HPA_REPLICA_METRICS,
    WORKLOAD_REPLICA_METRICS,
    HpaReplicaHistory,
    HpaReplicaMetric,
    KubernetesMetadataSnapshot,
    PrometheusMetricsSnapshot,
    WorkloadSnapshot,
)
from aks_fleet_efficiency.workload_history import (
    WorkloadAssessmentBinding,
    WorkloadHistoryEvidence,
    usable_metric_summary,
)


def normalize_hpa_history(
    metadata: KubernetesMetadataSnapshot,
    metrics: PrometheusMetricsSnapshot | None,
    workload: WorkloadSnapshot,
    binding: WorkloadAssessmentBinding | None,
) -> WorkloadHistoryEvidence | None:
    if binding is None or binding.hpa_uid is None or metrics is None:
        return None
    history = HpaReplicaHistory(
        cluster_resource_id=binding.cluster_resource_id,
        cluster_uid=binding.cluster_uid,
        namespace_uid=binding.namespace_uid,
        workload_uid=binding.workload_uid,
        hpa_uid=binding.hpa_uid,
        source_name=binding.source_name,
        history_reference=binding.history_reference,
        query_version=metrics.query_version,
    )
    workload.hpa_replica_history = history
    configuration = workload.autoscaler_configuration
    if (
        configuration is None
        or binding.cluster_uid != metadata.cluster_uid
        or binding.namespace_uid != configuration.namespace_uid
        or binding.namespace != workload.namespace
        or binding.workload_uid != workload.uid
        or binding.workload != workload.name
        or binding.workload_kind != workload.kind
        or binding.source_name != metrics.source_name
    ):
        history.issues.append("hpa_history_identity_mismatch")
        return None
    if (
        binding.safety_policy.reviewed_window_start != metrics.query_start
        or binding.safety_policy.reviewed_window_end != metrics.query_end
    ):
        history.issues.append("unreviewed_hpa_history_window")
        return None
    workload.safety_policy = binding.safety_policy.model_copy(deep=True)
    relevant = [
        item
        for item in metrics.observations
        if item.entity.kind == "hpa"
        and item.entity.cluster_resource_id == binding.cluster_resource_id
        and (
            item.entity.workload_uid == binding.workload_uid
            or (
                item.entity.namespace == binding.namespace
                and item.entity.workload == binding.workload
                and item.entity.workload_kind == binding.workload_kind
            )
        )
    ]
    if any(
        item.entity.namespace != binding.namespace
        or item.entity.workload != binding.workload
        or item.entity.workload_kind != binding.workload_kind
        or item.entity.workload_uid != binding.workload_uid
        or item.entity.hpa_uid != binding.hpa_uid
        for item in relevant
    ):
        history.issues.append("hpa_history_identity_mismatch")
        return None
    for metric in HPA_REPLICA_METRICS:
        candidates = [item for item in relevant if item.metric == metric]
        if not candidates:
            continue
        item = candidates[0]
        if (
            len(candidates) != 1
            or not usable_metric_summary(item, metrics)
            or item.minimum is None
            or item.maximum is None
            or not item.minimum.is_integer()
            or not item.maximum.is_integer()
        ):
            history.issues.append("unsupported_hpa_history_metric")
            continue
        history.metrics[metric] = HpaReplicaMetric(
            minimum=int(item.minimum),
            maximum=int(item.maximum),
            quality=item.quality.model_copy(deep=True),
        )
    availability = [
        item
        for item in metrics.observations
        if item.entity.kind == "workload"
        and item.metric in {"desired_replicas", "observed_replicas", "available_replicas"}
        and item.entity.cluster_resource_id == binding.cluster_resource_id
        and (
            item.entity.workload_uid == binding.workload_uid
            or (
                item.entity.namespace == binding.namespace
                and item.entity.workload == binding.workload
                and item.entity.workload_kind == binding.workload_kind
            )
        )
    ]
    for workload_metric in WORKLOAD_REPLICA_METRICS:
        candidates = [item for item in availability if item.metric == workload_metric]
        if not candidates:
            continue
        item = candidates[0]
        if (
            item.entity.namespace != binding.namespace
            or item.entity.workload != binding.workload
            or item.entity.workload_kind != binding.workload_kind
            or item.entity.workload_uid != binding.workload_uid
        ):
            history.availability_issues.append("replica_history_identity_mismatch")
            continue
        if (
            len(candidates) != 1
            or not usable_metric_summary(item, metrics)
            or item.minimum is None
            or item.maximum is None
            or not item.minimum.is_integer()
            or not item.maximum.is_integer()
        ):
            history.availability_issues.append("unsupported_replica_availability_history")
            continue
        history.workload_metrics[workload_metric] = HpaReplicaMetric(
            minimum=int(item.minimum),
            maximum=int(item.maximum),
            quality=item.quality.model_copy(deep=True),
        )
    history.availability_issues = sorted(set(history.availability_issues))
    reliability = [
        item
        for item in metrics.observations
        if item.entity.cluster_resource_id == binding.cluster_resource_id
        and item.entity.namespace == binding.namespace
        and item.entity.workload_uid == binding.workload_uid
        and item.entity.workload_kind == binding.workload_kind
        and item.entity.workload == binding.workload
        and item.metric in {"oom_events", "replica_oom_events", "restarts"}
        and (
            (item.entity.kind == "container" and item.entity.pod_uid in binding.pod_uids)
            or (
                item.entity.kind == "workload_container"
                and item.entity.membership_digest == binding.membership_digest
            )
        )
    ]
    if any(
        usable_metric_summary(item, metrics, counter=True)
        and item.total is not None
        and item.total > 0
        for item in reliability
    ):
        history.reliability_issues.append("observed_replica_reliability_events")
    history.issues = sorted(set(history.issues))
    return WorkloadHistoryEvidence(
        binding=binding.model_copy(deep=True),
        observations=[
            item.model_copy(deep=True) for item in [*relevant, *availability, *reliability]
        ],
    )
