from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import (
    AnalysisReport,
    AnalysisSummary,
    BlockedRecommendation,
    ClusterSnapshot,
    CollectionStatus,
    Confidence,
    FleetSnapshot,
    MetricQuality,
    PodDisruptionBudgetEvidence,
    Recommendation,
    ResourceCandidate,
    SchedulingPodEvidence,
    Severity,
    StartupHistoryEvidence,
)
from aks_fleet_efficiency.rules.autoscaler_rules import AUTOSCALER_EVALUATORS
from aks_fleet_efficiency.rules.capacity import (
    CAPACITY_EVALUATORS,
    CONSOLIDATION_EVALUATORS,
    DAEMONSET_EVALUATORS,
    nap_attribution_observed,
)
from aks_fleet_efficiency.rules.cpu import CPU_EVALUATORS
from aks_fleet_efficiency.rules.evidence import quality_reasons as _quality_reasons
from aks_fleet_efficiency.rules.memory_rules import MEMORY_EVALUATORS
from aks_fleet_efficiency.rules.pools import POOL_EVALUATORS
from aks_fleet_efficiency.rules.scheduling import CONSTRAINT_EVALUATORS, SCHEDULING_EVALUATORS
from aks_fleet_efficiency.rules.startup import assess_startup


def _recommendation_id(rule_id: str, resource_id: str, subject: str) -> str:
    digest = sha256(f"{rule_id}|{resource_id}|{subject}".encode()).hexdigest()[:12]
    return f"{rule_id}-{digest}"


def _confidence(coverage: float) -> Confidence:
    if coverage >= 0.95:
        return Confidence.HIGH
    if coverage >= 0.85:
        return Confidence.MEDIUM
    return Confidence.LOW


def _digest(model: BaseModel) -> str:
    serialized = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode()).hexdigest()


def _collection_reasons(
    snapshot: FleetSnapshot,
    cluster: ClusterSnapshot,
    needs_metrics: bool,
    evaluated_at: datetime,
    maximum_age: float,
) -> list[str]:
    manifest = snapshot.collection_manifest
    if manifest is None:
        return ["missing_collection_manifest"]
    required = ["azure-inventory", "kubernetes-metadata"]
    if needs_metrics:
        required.append("prometheus")
    reasons = []
    for name in required:
        candidates = [
            result
            for result in manifest.source_results or []
            if result.collector == name
            and (
                cluster.resource_id in result.requested_scope
                or (name == "azure-inventory" and cluster.subscription_id in result.requested_scope)
            )
        ]
        result = candidates[0] if len(candidates) == 1 else None
        if result is None:
            reasons.append(
                "ambiguous_collection_scope" if candidates else "missing_required_collector"
            )
            continue
        if result.status != CollectionStatus.COMPLETE:
            reasons.append("incomplete_collection")
        scoped = cluster.resource_id in result.completed_scope
        if name == "azure-inventory":
            scoped = scoped or cluster.subscription_id in result.completed_scope
        if not scoped:
            reasons.append("uncollected_scope")
        if result.completed_at > snapshot.generated_at:
            reasons.append("inconsistent_collection_time")
        if result.completed_at > evaluated_at:
            reasons.append("future_collection")
        if result.source_observed_at is None:
            reasons.append("unknown_source_freshness")
        elif (evaluated_at - result.source_observed_at).total_seconds() > maximum_age:
            reasons.append("stale_source")
    return reasons


def analyze(
    snapshot: FleetSnapshot, config: AdvisorConfig, *, as_of: datetime | None = None
) -> AnalysisReport:
    catalog = load_catalog()
    selected = set(config.packs) if config.packs is not None else set(catalog.default_pack_ids)
    pack_subject_counts = dict.fromkeys(sorted(selected), 0)
    selected_metrics = any(catalog.pack(name).evidence_kind == "metrics" for name in selected)
    provenance = [
        catalog.provenance(name, config.pack_parameters.get(name)) for name in sorted(selected)
    ]
    versions = {item.id: item.version for item in provenance}
    locks = {item.id: item.digest for item in provenance}
    if config.pack_locks and config.pack_locks != locks:
        raise ValueError("Assessment pack lock does not match installed pack/query assets")
    config = AdvisorConfig.model_validate(config.model_dump() | {"pack_locks": locks})
    parameters = {item.id: item.parameters for item in provenance}
    evaluated_at = as_of if as_of is not None else datetime.now(UTC)
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("analysis evaluation time must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(UTC)
    recommendations: list[Recommendation] = []
    blocked: list[BlockedRecommendation] = []
    warnings: list[str] = []
    inventory_reasons: list[str] = []
    metric_reasons: list[str] = []
    window = snapshot.metric_window
    days = (window.end - window.start).total_seconds() / 86_400
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    if snapshot.generated_at > evaluated_at:
        inventory_reasons.append("future_snapshot")
    elif (evaluated_at - snapshot.generated_at).total_seconds() > maximum_age:
        inventory_reasons.append("stale_snapshot")
    if snapshot.generated_at < window.end:
        metric_reasons.append("inconsistent_snapshot_window")
    if window.end > evaluated_at:
        metric_reasons.append("future_metrics")
    elif (evaluated_at - window.end).total_seconds() > maximum_age:
        metric_reasons.append("stale_metrics")
    if window.coverage_ratio < config.thresholds.minimum_coverage_ratio:
        warnings.append(
            f"Metric coverage {window.coverage_ratio:.0%} is below the configured minimum "
            f"{config.thresholds.minimum_coverage_ratio:.0%}."
        )
    if days < config.thresholds.minimum_observation_days:
        metric_reasons.append("short_window")
        warnings.append(
            f"Observation window is {days:.1f} days; at least "
            f"{config.thresholds.minimum_observation_days} days is recommended."
        )
    warnings.extend(inventory_reasons)
    warnings.extend(
        reason for reason in metric_reasons if reason not in {"low_coverage", "short_window"}
    )
    if not selected_metrics:
        warnings = [
            warning
            if warning in inventory_reasons
            else f"Independent metric context: {warning} Not required by the selected packs."
            for warning in warnings
        ]
    if snapshot.collection_manifest is None:
        warnings.append(
            "Collection provenance is missing; supplied observations are not actionable."
        )
    elif snapshot.collection_manifest.status != CollectionStatus.COMPLETE:
        warnings.append(
            "Collection is partial overall; selected findings are gated independently on "
            "their required, complete, correctly scoped sources."
        )

    def record_blocked(
        recommendation_id: str,
        rule_id: str,
        cluster: ClusterSnapshot,
        reasons: list[str],
        *,
        namespace: str | None = None,
        workload: str | None = None,
        resource_candidate: ResourceCandidate | None = None,
    ) -> None:
        if rule_id not in selected:
            return
        blocked.append(
            BlockedRecommendation(
                id=recommendation_id,
                rule_id=rule_id,
                rule_version=versions[rule_id],
                resource_id=cluster.resource_id,
                cluster_name=cluster.name,
                namespace=namespace,
                workload=workload,
                reason_codes=sorted(set(reasons)),
                resource_candidate=resource_candidate,
            )
        )

    def emit(
        recommendation: Recommendation,
        *,
        cluster: ClusterSnapshot,
        metrics: dict[str, tuple[float | int | None, str]] | None = None,
        qualities: dict[str, MetricQuality] | None = None,
        extra_reasons: list[str] | None = None,
        has_signal: bool = True,
    ) -> None:
        if recommendation.rule_id not in selected:
            return
        recommendation.rule_version = versions[recommendation.rule_id]
        needs_metrics = metrics is not None
        reasons = inventory_reasons + (metric_reasons if needs_metrics else [])
        reasons += _collection_reasons(snapshot, cluster, needs_metrics, evaluated_at, maximum_age)
        if metrics is not None:
            reasons += _quality_reasons(
                snapshot, metrics, qualities or {}, config, evaluated_at, maximum_age
            )
        reasons += extra_reasons or []
        if (
            config.mode == "guarded"
            and (
                recommendation.proposed_requests is not None
                or recommendation.proposed_limits is not None
                or recommendation.proposed_replica_floor is not None
            )
            and any(
                capability.pack_id == recommendation.rule_id
                and capability.cluster_resource_id == cluster.resource_id
                and capability.mode == "guarded"
                and capability.status == "unsupported"
                for capability in snapshot.source_capabilities
            )
        ):
            reasons.append("unsupported_source_profile")
        if config.mode == "baseline" and (
            recommendation.proposed_requests is not None
            or recommendation.proposed_limits is not None
            or recommendation.proposed_replica_floor is not None
        ):
            reasons.append("guarded_mode_required")
        if reasons:
            record_blocked(
                recommendation.id,
                recommendation.rule_id,
                cluster,
                reasons,
                namespace=recommendation.namespace,
                workload=recommendation.workload,
                resource_candidate=recommendation.resource_candidate,
            )
        elif has_signal:
            if qualities and metrics:
                recommendation.confidence = _confidence(
                    min(
                        1,
                        *(qualities[name].window.coverage_ratio for name in metrics),
                    )
                )
            recommendations.append(recommendation)

    for cluster in snapshot.clusters:
        capacity = cluster.capacity
        nap_observed = bool(
            capacity
            and (
                capacity.provisioning_mode == "Auto"
                or capacity.nap_pools
                or capacity.nap_managed_nodes
            )
        )
        if (
            cluster.scheduling
            and cluster.scheduling.pods
            and "policy/v1/poddisruptionbudgets" in cluster.scheduling.unobserved_context
        ):
            for pack_id in ["AKS-SCHED-002", "AKS-NP-003"]:
                if pack_id in selected and (pack_id != "AKS-NP-003" or nap_observed):
                    record_blocked(
                        _recommendation_id(
                            pack_id, cluster.resource_id, f"pdb-context/{cluster.uid}"
                        ),
                        pack_id,
                        cluster,
                        ["incomplete_pdb_inventory"],
                    )
        if "AKS-NP-002" in selected:
            capacity_pack = catalog.pack("AKS-NP-002")
            pack_subject_counts[capacity_pack.id] += 1
            capacity_result = CAPACITY_EVALUATORS[capacity_pack.evaluator](
                cluster,
                config,
                capacity_pack,
                _recommendation_id(
                    capacity_pack.id, cluster.resource_id, f"capacity/{cluster.uid}"
                ),
                evaluated_at,
            )
            if cluster.capacity and any(
                time is not None and time > snapshot.generated_at
                for time in [
                    cluster.capacity.azure_observed_at,
                    cluster.capacity.kubernetes_observed_at,
                ]
            ):
                capacity_result.reasons.append("inconsistent_capacity_time")
            emit(
                capacity_result.recommendation,
                cluster=cluster,
                extra_reasons=capacity_result.reasons,
                has_signal=capacity_result.has_signal,
            )
        if "AKS-NP-003" in selected:
            pack = catalog.pack("AKS-NP-003")
            if capacity and capacity.nap_pools and not nap_attribution_observed(cluster):
                record_blocked(
                    _recommendation_id(
                        pack.id, cluster.resource_id, f"consolidation/{cluster.uid}/attribution"
                    ),
                    pack.id,
                    cluster,
                    ["nap_pod_attribution_unknown"],
                )
            if capacity is None:
                record_blocked(
                    _recommendation_id(
                        pack.id, cluster.resource_id, f"consolidation/{cluster.uid}/unknown"
                    ),
                    pack.id,
                    cluster,
                    ["missing_capacity_inventory"],
                )
            elif (
                nap_observed
                and capacity.nap_api_status.get("karpenter.sh/v1/nodepools") != "available"
            ):
                record_blocked(
                    _recommendation_id(
                        pack.id, cluster.resource_id, f"consolidation/{cluster.uid}/unknown"
                    ),
                    pack.id,
                    cluster,
                    ["nap_nodepool_inventory_unavailable"],
                )
            for nap_pool in capacity.nap_pools if capacity else []:
                pack_subject_counts[pack.id] += 1
                result = CONSOLIDATION_EVALUATORS[pack.evaluator](
                    cluster,
                    nap_pool,
                    config,
                    pack,
                    _recommendation_id(
                        pack.id,
                        cluster.resource_id,
                        f"consolidation/{cluster.uid}/{nap_pool.uid}",
                    ),
                    evaluated_at,
                )
                if capacity and any(
                    time is not None and time > snapshot.generated_at
                    for time in [capacity.azure_observed_at, capacity.kubernetes_observed_at]
                ):
                    result.reasons.append("inconsistent_capacity_time")
                if cluster.scheduling and cluster.scheduling.observed_at > snapshot.generated_at:
                    result.reasons.append("inconsistent_scheduling_time")
                emit(
                    result.recommendation,
                    cluster=cluster,
                    extra_reasons=result.reasons,
                    has_signal=result.has_signal,
                )
        if "AKS-START-001" in selected:
            pack = catalog.pack("AKS-START-001")
            for workload in cluster.workloads:
                if workload.namespace in config.excluded_namespaces:
                    continue
                histories: list[StartupHistoryEvidence | None] = list(workload.startup_history) or [
                    None
                ]
                for history in histories:
                    pack_subject_counts[pack.id] += 1
                    result = assess_startup(
                        cluster,
                        workload,
                        history,
                        config,
                        pack,
                        _recommendation_id(
                            pack.id,
                            cluster.resource_id,
                            f"startup/{workload.uid}/"
                            f"{history.pod_uid if history else 'unknown'}/"
                            f"{history.container if history else 'unknown'}",
                        ),
                        evaluated_at,
                    )
                    emit(
                        result.recommendation,
                        cluster=cluster,
                        extra_reasons=result.reasons,
                        has_signal=result.has_signal,
                    )
        if "AKS-NP-004" in selected:
            pack = catalog.pack("AKS-NP-004")
            inventory = cluster.scheduling
            if inventory is None or inventory.daemonset_overhead_issues:
                record_blocked(
                    _recommendation_id(
                        pack.id, cluster.resource_id, f"daemonset/{cluster.uid}/unknown"
                    ),
                    pack.id,
                    cluster,
                    inventory.daemonset_overhead_issues
                    if inventory
                    else ["missing_scheduling_inventory"],
                )
            if inventory is not None:
                groups = sorted(
                    {
                        item.daemonset_uid
                        for item in inventory.daemonset_overhead
                        if item.namespace not in config.excluded_namespaces
                    }
                )
                if (
                    not inventory.daemonset_overhead_observed
                    and not inventory.daemonset_overhead_issues
                ):
                    record_blocked(
                        _recommendation_id(
                            pack.id, cluster.resource_id, f"daemonset/{cluster.uid}/unknown"
                        ),
                        pack.id,
                        cluster,
                        ["incomplete_daemonset_inventory"],
                    )
                for daemonset_uid in groups:
                    pack_subject_counts[pack.id] += 1
                    result = DAEMONSET_EVALUATORS[pack.evaluator](
                        cluster,
                        [
                            item
                            for item in inventory.daemonset_overhead
                            if item.daemonset_uid == daemonset_uid
                            and item.namespace not in config.excluded_namespaces
                        ],
                        config,
                        pack,
                        _recommendation_id(
                            pack.id, cluster.resource_id, f"daemonset/{cluster.uid}/{daemonset_uid}"
                        ),
                        evaluated_at,
                    )
                    if inventory.observed_at > snapshot.generated_at:
                        result.reasons.append("inconsistent_scheduling_time")
                    emit(
                        result.recommendation,
                        cluster=cluster,
                        extra_reasons=result.reasons,
                        has_signal=result.has_signal,
                    )
        if "AKS-SCHED-001" in selected:
            pack = catalog.pack("AKS-SCHED-001")
            pods = (
                cluster.scheduling.pods
                if cluster.scheduling and cluster.scheduling.pods
                else [None]
            )
            for pod in pods:
                if pod is not None and pod.namespace in config.excluded_namespaces:
                    continue
                if pod is not None:
                    pack_subject_counts[pack.id] += 1
                result = SCHEDULING_EVALUATORS[pack.evaluator](
                    cluster,
                    pod,
                    config,
                    pack,
                    _recommendation_id(
                        pack.id,
                        cluster.resource_id,
                        f"scheduling/{cluster.uid}/{pod.pod_uid if pod else 'unknown'}",
                    ),
                    evaluated_at,
                )
                if cluster.scheduling and cluster.scheduling.observed_at > snapshot.generated_at:
                    result.reasons.append("inconsistent_scheduling_time")
                emit(
                    result.recommendation,
                    cluster=cluster,
                    extra_reasons=result.reasons,
                    has_signal=result.has_signal,
                )
        if "AKS-SCHED-002" in selected:
            pack = catalog.pack("AKS-SCHED-002")
            inventory = cluster.scheduling
            constraint_subjects: list[SchedulingPodEvidence | PodDisruptionBudgetEvidence] = []
            if inventory is not None:
                constraint_subjects.extend(inventory.pods)
                constraint_subjects.extend(inventory.pdbs)
            if inventory is None:
                record_blocked(
                    _recommendation_id(
                        pack.id, cluster.resource_id, f"constraints/{cluster.uid}/unknown"
                    ),
                    pack.id,
                    cluster,
                    ["missing_scheduling_inventory"],
                )
            for constraint_subject in constraint_subjects:
                if constraint_subject.namespace in config.excluded_namespaces:
                    continue
                pack_subject_counts[pack.id] += 1
                subject_kind = (
                    f"pod/{constraint_subject.pod_uid}"
                    if isinstance(constraint_subject, SchedulingPodEvidence)
                    else f"pdb/{constraint_subject.uid}"
                )
                result = CONSTRAINT_EVALUATORS[pack.evaluator](
                    cluster,
                    constraint_subject,
                    config,
                    pack,
                    _recommendation_id(
                        pack.id,
                        cluster.resource_id,
                        f"constraints/{cluster.uid}/{subject_kind}",
                    ),
                    evaluated_at,
                )
                if inventory and inventory.observed_at > snapshot.generated_at:
                    result.reasons.append("inconsistent_scheduling_time")
                emit(
                    result.recommendation,
                    cluster=cluster,
                    extra_reasons=result.reasons,
                    has_signal=result.has_signal,
                )
        for pool in cluster.node_pools:
            subject = f"nodepool/{pool.resource_id or pool.name}/{cluster.uid or 'unknown'}"
            if "AKS-NP-001" not in selected:
                continue
            pool_pack = catalog.pack("AKS-NP-001")
            pack_subject_counts[pool_pack.id] += 1
            pool_assessment = POOL_EVALUATORS["node-pool-review"](
                cluster,
                pool,
                config,
                pool_pack,
                _recommendation_id(pool_pack.id, cluster.resource_id, subject),
                parameters[pool_pack.id].review_ratio,
            )
            if pool_assessment is not None:
                emit(
                    pool_assessment.recommendation,
                    cluster=cluster,
                    metrics=pool_assessment.metrics,
                    qualities=pool.metric_quality,
                    extra_reasons=pool_assessment.reasons,
                    has_signal=pool_assessment.has_signal,
                )

        for workload in cluster.workloads:
            if workload.namespace in config.excluded_namespaces:
                continue
            memory_subject = (
                f"memory/{workload.namespace}/{workload.kind}/{workload.name}/"
                f"{workload.uid or 'unknown'}"
            )
            for memory_id in ("AKS-MEM-004", "AKS-REL-002", "AKS-REL-003"):
                if memory_id not in selected:
                    continue
                memory_pack = catalog.pack(memory_id)
                pack_subject_counts[memory_id] += 1
                memory_result = MEMORY_EVALUATORS[memory_pack.evaluator](
                    snapshot,
                    cluster,
                    workload,
                    None,
                    config,
                    memory_pack,
                    _recommendation_id(memory_id, cluster.resource_id, memory_subject),
                    evaluated_at,
                )
                emit(
                    memory_result.recommendation,
                    cluster=cluster,
                    metrics=memory_result.metrics,
                    qualities=memory_result.qualities,
                    extra_reasons=memory_result.reasons,
                    has_signal=memory_result.has_signal,
                )
            configuration_subject = (
                f"autoscalers/{workload.namespace}/{workload.kind}/{workload.name}/"
                f"{cluster.uid or 'unknown'}/{workload.uid or 'unknown'}"
            )
            for autoscaler_id in (
                "AKS-AS-002",
                "AKS-AS-003",
                "AKS-AS-004",
                "AKS-AS-006",
                "AKS-AS-007",
                "AKS-AS-005",
                "AKS-AS-001",
            ):
                if autoscaler_id not in selected:
                    continue
                autoscaler_pack = catalog.pack(autoscaler_id)
                pack_subject_counts[autoscaler_id] += 1
                subject = (
                    f"{workload.namespace}/{workload.kind}/{workload.name}/"
                    f"{workload.uid or 'unknown'}"
                    if autoscaler_id == "AKS-AS-001"
                    else configuration_subject
                )
                autoscaler_result = AUTOSCALER_EVALUATORS[autoscaler_pack.evaluator](
                    snapshot,
                    cluster,
                    workload,
                    config,
                    autoscaler_pack,
                    _recommendation_id(autoscaler_id, cluster.resource_id, subject),
                    evaluated_at,
                )
                if autoscaler_result is not None:
                    if autoscaler_id == "AKS-AS-001":
                        autoscaler_result.recommendation.existing_tool_observations = [
                            item.model_copy(deep=True)
                            for item in snapshot.existing_tool_observations
                            if item.cluster_resource_id == cluster.resource_id
                            and item.finding in {"enable-vpa", "tune-cluster-autoscaler"}
                        ]
                    emit(
                        autoscaler_result.recommendation,
                        cluster=cluster,
                        metrics=autoscaler_result.metrics,
                        qualities=autoscaler_result.qualities,
                        extra_reasons=autoscaler_result.reasons,
                        has_signal=autoscaler_result.has_signal,
                    )

            for container in workload.containers:
                subject = (
                    f"{workload.namespace}/{workload.kind}/{workload.name}/{container.name}/"
                    f"{cluster.uid or 'unknown'}/{workload.uid or 'unknown'}"
                )
                for memory_id in (
                    "AKS-MEM-001",
                    "AKS-REL-001",
                    "AKS-MEM-002",
                    "AKS-MEM-003",
                    "AKS-MEM-005",
                ):
                    if memory_id not in selected:
                        continue
                    memory_pack = catalog.pack(memory_id)
                    pack_subject_counts[memory_id] += 1
                    memory_result = MEMORY_EVALUATORS[memory_pack.evaluator](
                        snapshot,
                        cluster,
                        workload,
                        container,
                        config,
                        memory_pack,
                        _recommendation_id(memory_id, cluster.resource_id, subject),
                        evaluated_at,
                    )
                    emit(
                        memory_result.recommendation,
                        cluster=cluster,
                        metrics=memory_result.metrics,
                        qualities=memory_result.qualities,
                        extra_reasons=memory_result.reasons,
                        has_signal=memory_result.has_signal,
                    )
                for review_id in ("AKS-RQ-002", "AKS-RQ-001", "AKS-RQ-003"):
                    if review_id not in selected:
                        continue
                    review_pack = catalog.pack(review_id)
                    pack_subject_counts[review_id] += 1
                    review = CPU_EVALUATORS[review_pack.evaluator](
                        snapshot,
                        cluster,
                        workload,
                        container,
                        config,
                        review_pack,
                        _recommendation_id(review_id, cluster.resource_id, subject),
                        parameters[review_id].review_ratio,
                    )
                    if review is not None:
                        emit(
                            review.recommendation,
                            cluster=cluster,
                            metrics=review.metrics,
                            qualities=container.resources.metric_quality,
                            extra_reasons=review.reasons,
                            has_signal=review.has_signal,
                        )

    priority = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }
    recommendations.sort(key=lambda item: (priority[item.severity], item.cluster_name, item.id))
    blocked.sort(key=lambda item: (item.resource_id, item.id))
    summary = AnalysisSummary(
        clusters_analyzed=len(snapshot.clusters),
        node_pools_analyzed=sum(len(cluster.node_pools) for cluster in snapshot.clusters),
        workloads_analyzed=sum(len(cluster.workloads) for cluster in snapshot.clusters),
        pack_subject_counts=pack_subject_counts,
        recommendations=len(recommendations),
        high_or_critical=sum(
            rec.severity in {Severity.HIGH, Severity.CRITICAL} for rec in recommendations
        ),
        blocked_recommendations=len(blocked),
        data_quality_warnings=warnings,
    )
    return AnalysisReport(
        source_capabilities=snapshot.source_capabilities,
        mode=config.mode,
        pack_provenance=provenance,
        generated_at=evaluated_at,
        observation_window=window,
        summary=summary,
        recommendations=recommendations,
        blocked_recommendations=blocked,
        snapshot_digest=_digest(snapshot),
        configuration_digest=_digest(config),
    )
