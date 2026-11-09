from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from math import fsum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aks_fleet_efficiency.autoscaler_normalization import normalize_autoscaler_configuration
from aks_fleet_efficiency.capabilities import evaluate_source_capabilities
from aks_fleet_efficiency.capacity import normalize_capacity
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.collectors.kubernetes_metadata import validate_metadata_projection
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.hpa_history import normalize_hpa_history
from aks_fleet_efficiency.memory_metadata import normalize_memory_metadata
from aks_fleet_efficiency.models import (
    AnalysisReport,
    AzureInventorySnapshot,
    AzureNodePoolInventory,
    ClusterSnapshot,
    CollectionError,
    CollectionErrorCode,
    CollectionManifest,
    CollectionStatus,
    CollectorResult,
    FleetSnapshot,
    KubernetesMetadataSnapshot,
    MetricObservation,
    MetricWindow,
    NodePoolSnapshot,
    PoolIntentBinding,
    PrometheusMetricsSnapshot,
    UtcDatetime,
    WorkloadSnapshot,
    merge_collector_results,
)
from aks_fleet_efficiency.rules.engine import analyze
from aks_fleet_efficiency.scheduling import normalize_scheduling
from aks_fleet_efficiency.workload_history import (
    WorkloadAssessmentBinding,
    WorkloadHistoryEvidence,
    normalize_workload_history,
)
from aks_fleet_efficiency.workload_history import (
    usable_metric_summary as _usable_summary,
)
from aks_fleet_efficiency.workload_normalization import (
    WorkloadInventoryEvidence,
    normalize_workload_inventory,
)


class AssessmentFragments(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    schema_version: Literal["1.0"] = "1.0"
    window_start: UtcDatetime
    window_end: UtcDatetime
    azure: Annotated[list[AzureInventorySnapshot], Field(min_length=1, max_length=1000)]
    kubernetes: list[KubernetesMetadataSnapshot] = Field(default_factory=list)
    metrics: list[PrometheusMetricsSnapshot] = Field(default_factory=list)
    workload_assessments: list[WorkloadAssessmentBinding] = Field(default_factory=list)
    pool_intents: list[PoolIntentBinding] = Field(default_factory=list)

    @property
    def azure_fragments(self) -> list[AzureInventorySnapshot]:
        return self.azure

    @model_validator(mode="after")
    def validate_window(self) -> AssessmentFragments:
        if self.window_end <= self.window_start:
            raise ValueError("assessment window must be ordered")
        for metadata in self.kubernetes:
            validate_metadata_projection(metadata)
        return self


class NormalizationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    code: Literal[
        "missing-cluster",
        "missing-kubernetes-fragment",
        "missing-metrics-fragment",
        "workload-analysis-unsupported",
        "unsupported-pool-evidence",
        "unsupported-workload-evidence",
        "unknown-workload-request",
        "quantity-parser-unavailable",
        "missing-workload-assessment",
        "workload-history-identity-mismatch",
        "unsupported-workload-history",
        "workload-history-guardrail",
    ]


class OfflineAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    assessment_scope: Literal["fleet-assessment"] = "fleet-assessment"
    status: Literal["complete", "partial"]
    input_digest: str
    profile_digest: str
    snapshot: FleetSnapshot
    report: AnalysisReport
    issues: list[NormalizationIssue]
    workload_inventory: list[WorkloadInventoryEvidence] = Field(default_factory=list)
    workload_history: list[WorkloadHistoryEvidence] = Field(default_factory=list)
    metadata_evidence: list[KubernetesMetadataSnapshot] = Field(default_factory=list)
    baseline_measurements: list[MetricObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report_version(self) -> OfflineAssessment:
        if self.report.schema_version != self.snapshot.schema_version:
            raise ValueError("assessment and analysis report versions must agree")
        return self


def _digest(model: BaseModel, *, exclude: set[str] | None = None) -> str:
    payload = json.dumps(
        model.model_dump(mode="json", exclude=exclude), sort_keys=True, separators=(",", ":")
    )
    return sha256(payload.encode()).hexdigest()


def _merge_receipts(
    name: str,
    receipts: list[CollectorResult],
    expected: set[str],
    generated_at: datetime,
) -> CollectorResult:
    if not receipts:
        return CollectorResult(
            collector=name,
            status=CollectionStatus.FAILED,
            requested_scope=sorted(expected),
            started_at=generated_at,
            completed_at=generated_at,
            errors=[CollectionError(scope=scope, code="unavailable") for scope in sorted(expected)],
        )
    requested = set().union(*(set(item.requested_scope) for item in receipts)) | expected
    completed = set().union(*(set(item.completed_scope) for item in receipts))
    missing = expected - set().union(*(set(item.requested_scope) for item in receipts))
    errors: set[tuple[str, CollectionErrorCode]] = {
        (error.scope, error.code) for item in receipts for error in item.errors
    }
    errors.update((scope, "unavailable") for scope in missing)
    if {scope for scope, _ in errors} & completed:
        raise ValueError("conflicting collection receipts")
    complete = not missing and all(item.status == CollectionStatus.COMPLETE for item in receipts)
    source_times = [item.source_observed_at for item in receipts]
    return CollectorResult(
        collector=name,
        status=(
            CollectionStatus.COMPLETE
            if complete
            else CollectionStatus.FAILED
            if not completed and errors
            else CollectionStatus.PARTIAL
        ),
        requested_scope=sorted(requested),
        completed_scope=sorted(completed),
        started_at=min(item.started_at for item in receipts),
        completed_at=max(item.completed_at for item in receipts),
        source_observed_at=(
            min(time for time in source_times if time is not None)
            if not missing and all(time is not None for time in source_times)
            else None
        ),
        pagination_complete=not missing and all(item.pagination_complete for item in receipts),
        retry_count=sum(item.retry_count for item in receipts),
        errors=[CollectionError(scope=scope, code=code) for scope, code in sorted(errors)],
        missing_fields=sorted({field for item in receipts for field in item.missing_fields}),
    )


def _source_receipts(
    receipts: list[CollectorResult],
    expected: set[str],
    name: str,
    generated_at: datetime,
) -> list[CollectorResult]:
    sources = [receipt.model_copy(deep=True) for receipt in receipts]
    missing = expected - {scope for receipt in sources for scope in receipt.requested_scope}
    if missing:
        sources.append(_merge_receipts(name, [], missing, generated_at))
    return sources


def _validate_bindings(fragments: AssessmentFragments, profile: OnboardingConfig) -> None:
    targets = {target.resource_id: target for target in profile.clusters}
    if not targets:
        raise ValueError("offline assessment requires explicit cluster targets")
    bound: set[tuple[str, str]] = set()
    for binding in fragments.workload_assessments:
        key = (binding.cluster_resource_id, binding.workload_uid)
        if (
            key in bound
            or binding.tenant_id != str(profile.scope.tenant_id)
            or binding.cluster_resource_id not in targets
            or binding.source_name != targets[binding.cluster_resource_id].metric_source
        ):
            raise ValueError("duplicate or foreign workload assessment binding")
        bound.add(key)
    subscriptions = {str(value) for value in profile.scope.subscription_ids}
    inventories = fragments.azure_fragments
    all_fragments: list[
        AzureInventorySnapshot | KubernetesMetadataSnapshot | PrometheusMetricsSnapshot
    ] = [*inventories, *fragments.kubernetes, *fragments.metrics]
    for fragment in all_fragments:
        if fragment.tenant_id != str(profile.scope.tenant_id):
            raise ValueError("fragment tenant does not match the approved tenant")
        if fragment.collection.completed_at > fragment.generated_at:
            raise ValueError("fragment predates its receipt")
    cluster_ids: set[str] = set()
    inventory_scopes: set[str] = set()
    for inventory in inventories:
        receipt = inventory.collection
        if receipt.collector != "azure-inventory":
            raise ValueError("invalid inventory receipt")
        if not set(receipt.requested_scope) <= subscriptions | targets.keys():
            raise ValueError("inventory receipt exceeds approved scope")
        for scope in receipt.requested_scope:
            if scope.casefold() in inventory_scopes:
                raise ValueError("overlapping inventory source scopes")
            inventory_scopes.add(scope.casefold())
        for cluster in inventory.clusters:
            if cluster.resource_id not in targets or cluster.resource_id in cluster_ids:
                raise ValueError("duplicate or foreign inventory cluster")
            target = targets[cluster.resource_id]
            if cluster.subscription_id != str(target.subscription_id):
                raise ValueError("inventory subscription conflicts with exact cluster identity")
            if not (
                cluster.resource_id in receipt.requested_scope
                or cluster.subscription_id in receipt.requested_scope
            ):
                raise ValueError("inventory cluster is outside its own source receipt")
            cluster_ids.add(cluster.resource_id)
            pool_ids: set[str] = set()
            for pool in cluster.node_pools:
                if (
                    pool.resource_id != f"{cluster.resource_id}/agentPools/{pool.name}"
                    or pool.resource_id in pool_ids
                ):
                    raise ValueError("duplicate or conflicting pool identity")
                pool_ids.add(pool.resource_id)
    for target in targets.values():
        if (
            target.resource_id.casefold() in inventory_scopes
            and str(target.subscription_id) in inventory_scopes
        ):
            raise ValueError("ambiguous exact-cluster and subscription inventory scopes")
    metadata_ids: set[str] = set()
    for metadata in fragments.kubernetes:
        cluster_id = metadata.cluster_resource_id
        if cluster_id not in targets or cluster_id in metadata_ids:
            raise ValueError("duplicate or foreign Kubernetes fragment")
        if (
            metadata.collection.collector != "kubernetes-metadata"
            or metadata.collection.requested_scope != [cluster_id]
        ):
            raise ValueError("invalid Kubernetes receipt binding")
        metadata_ids.add(cluster_id)
        identities = [resource.uid for resource in metadata.resources]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate Kubernetes UID")
        fingerprints = [
            resource.uid
            for resource in metadata.resources
            if resource.kind == "Namespace" and resource.name == "kube-system"
        ]
        if metadata.cluster_uid is not None and fingerprints != [metadata.cluster_uid]:
            raise ValueError("Kubernetes fingerprint does not match its namespace")
    metric_ids: set[str] = set()
    for metrics in fragments.metrics:
        if metrics.collection.collector != "prometheus":
            raise ValueError("invalid metric receipt")
        if (
            metrics.query_start != fragments.window_start
            or metrics.query_end != fragments.window_end
        ):
            raise ValueError("mixed metric windows are not supported")
        for cluster_id in metrics.collection.requested_scope:
            if cluster_id not in targets or cluster_id in metric_ids:
                raise ValueError("duplicate or foreign metrics scope")
            if targets[cluster_id].metric_source != metrics.source_name:
                raise ValueError("metric source does not match the cluster profile")
            metric_ids.add(cluster_id)
        keys = [(item.entity, item.metric) for item in metrics.observations]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate metric observation")


def _normalize_pool(
    pool: AzureNodePoolInventory,
    metadata: KubernetesMetadataSnapshot | None,
    observations: list[MetricObservation],
    metrics: PrometheusMetricsSnapshot | None,
) -> NodePoolSnapshot | None:
    if (
        metadata is None
        or metrics is None
        or metadata.cluster_uid is None
        or pool.node_count is None
        or pool.node_count <= 0
        or pool.spot is None
        or pool.autoscaling_enabled is None
        or pool.mode not in {"User", "System"}
    ):
        return None
    members = [node for node in metadata.nodes if node.node_pool_resource_id == pool.resource_id]
    if len(members) != pool.node_count or any(node.state != "matched" for node in members):
        return None
    node_uids = {node.node_uid for node in members}
    if len(node_uids) != len(members):
        return None
    resources = {resource.uid for resource in metadata.resources if resource.kind == "Node"}
    if not node_uids <= resources:
        return None
    for observation in observations:
        entity = observation.entity
        if entity.kind == "node" and entity.node_pool_resource_id == pool.resource_id:
            if not any(
                node.node_uid == entity.node_uid
                and node.azure_resource_id == entity.node_resource_id
                for node in members
            ):
                return None
    aggregates = {
        item.metric: item
        for item in observations
        if item.entity.kind == "node_pool" and item.entity.node_pool_resource_id == pool.resource_id
    }
    capacities: dict[str, float] = {}
    for name, unit in [
        ("pool_cpu_usage", "mCPU"),
        ("pool_allocatable_cpu", "mCPU"),
        ("pool_allocatable_memory", "MiB"),
    ]:
        item = aggregates.get(name)
        if item is None or not _usable_summary(item, metrics) or item.quality.unit != unit:
            return None
        node_items = [
            observation
            for observation in observations
            if observation.entity.kind == "node"
            and observation.entity.node_pool_resource_id == pool.resource_id
            and observation.metric == name.replace("pool_", "node_", 1)
        ]
        if (
            {observation.entity.node_uid for observation in node_items} != node_uids
            or len(node_items) != len(members)
            or any(
                not _usable_summary(observation, metrics) or observation.quality.unit != unit
                for observation in node_items
            )
        ):
            return None
        if name != "pool_cpu_usage":
            if (
                item.minimum is None
                or item.minimum <= 0
                or item.maximum != item.minimum
                or item.quality.window.coverage_ratio != 1
                or any(
                    observation.minimum != observation.maximum
                    or observation.quality.window.coverage_ratio != 1
                    for observation in node_items
                )
                or item.minimum != fsum(observation.minimum or 0 for observation in node_items)
            ):
                return None
            capacities[name] = item.minimum
    usage = aggregates.get("pool_cpu_usage")
    if usage is None or usage.issues or usage.quality.unit != "mCPU" or usage.p95 is None:
        return None
    return NodePoolSnapshot(
        name=pool.name,
        resource_id=pool.resource_id,
        vm_size=pool.vm_size,
        mode=pool.mode,
        spot=pool.spot,
        nap_managed=False,
        autoscaling_enabled=pool.autoscaling_enabled,
        node_count=pool.node_count,
        min_count=pool.min_count,
        max_count=pool.max_count,
        allocatable_cpu_mcores=capacities["pool_allocatable_cpu"],
        allocatable_memory_mib=capacities["pool_allocatable_memory"],
        usage_cpu_p95_mcores=usage.p95,
        metric_quality={"usage_cpu_p95_mcores": usage.quality},
    )


def assess_fragments(
    fragments: AssessmentFragments,
    profile: OnboardingConfig,
    *,
    as_of: datetime | None = None,
) -> OfflineAssessment:
    _validate_bindings(fragments, profile)
    pool_ids = {
        (cluster.resource_id, pool.resource_id)
        for source in fragments.azure_fragments
        for cluster in source.clusters
        for pool in cluster.node_pools
    }
    intent_ids = [
        (item.cluster_resource_id, item.pool_resource_id) for item in fragments.pool_intents
    ]
    if len(set(intent_ids)) != len(intent_ids) or not set(intent_ids) <= pool_ids:
        raise ValueError("Duplicate or foreign pool intent binding")
    inventories = fragments.azure_fragments
    generated_at = max(
        [item.generated_at for item in inventories]
        + [item.generated_at for item in fragments.kubernetes]
        + [item.generated_at for item in fragments.metrics]
    )
    targets = {target.resource_id: target for target in profile.clusters}
    metadata_by_cluster = {item.cluster_resource_id: item for item in fragments.kubernetes}
    metric_by_cluster = {
        scope: item for item in fragments.metrics for scope in item.collection.requested_scope
    }
    issues: list[NormalizationIssue] = []
    workload_inventory: list[WorkloadInventoryEvidence] = []
    workload_history: list[WorkloadHistoryEvidence] = []
    clusters: list[ClusterSnapshot] = []
    for cluster_id in sorted(targets):
        inventory = next(
            (
                item
                for source in inventories
                for item in source.clusters
                if item.resource_id == cluster_id
            ),
            None,
        )
        if inventory is None:
            issues.append(NormalizationIssue(scope=cluster_id, code="missing-cluster"))
            continue
        metadata = metadata_by_cluster.get(cluster_id)
        if metadata is None:
            issues.append(NormalizationIssue(scope=cluster_id, code="missing-kubernetes-fragment"))
        metrics = metric_by_cluster.get(cluster_id)
        if metrics is None:
            issues.append(NormalizationIssue(scope=cluster_id, code="missing-metrics-fragment"))
        observations = (
            [item for item in metrics.observations if item.entity.cluster_resource_id == cluster_id]
            if metrics is not None
            else []
        )
        pools: list[NodePoolSnapshot] = []
        for pool in sorted(inventory.node_pools, key=lambda item: item.resource_id):
            normalized = (
                _normalize_pool(pool, metadata, observations, metrics)
                if inventory.node_provisioning_mode == "Manual"
                else None
            )
            if normalized is None:
                issues.append(
                    NormalizationIssue(scope=pool.resource_id, code="unsupported-pool-evidence")
                )
            else:
                pools.append(normalized)
        workloads: list[WorkloadSnapshot] = []
        if metadata is not None:
            workloads, current_evidence, workload_issues = normalize_workload_inventory(
                metadata,
            )
            for workload in workloads:
                normalize_memory_metadata(metadata, workload)
                workload.autoscaler_configuration = normalize_autoscaler_configuration(
                    metadata, workload
                )
                hpa_evidence = normalize_hpa_history(
                    metadata,
                    metrics,
                    workload,
                    next(
                        (
                            item
                            for item in fragments.workload_assessments
                            if item.cluster_resource_id == cluster_id
                            and item.workload_uid == workload.uid
                        ),
                        None,
                    ),
                )
                if hpa_evidence is not None:
                    workload_history.append(hpa_evidence)
            workload_inventory.extend(current_evidence)
            issues.extend(
                NormalizationIssue(scope=item.scope, code=item.code) for item in workload_issues
            )
            if fragments.workload_assessments:
                history, history_issues = normalize_workload_history(
                    metadata,
                    metrics,
                    workloads,
                    current_evidence,
                    [
                        item
                        for item in fragments.workload_assessments
                        if item.cluster_resource_id == cluster_id
                    ],
                )
                workload_history.extend(history)
                issues.extend(
                    NormalizationIssue(scope=item.scope, code=item.code) for item in history_issues
                )
        clusters.append(
            ClusterSnapshot(
                resource_id=cluster_id,
                name=inventory.name,
                uid=metadata.cluster_uid if metadata is not None else None,
                subscription_id=inventory.subscription_id,
                resource_group=inventory.resource_group,
                location=inventory.location,
                kubernetes_version=inventory.kubernetes_version,
                environment=targets[cluster_id].environment,
                sku_tier=inventory.sku_tier,
                cost_analysis_enabled=inventory.cost_analysis_enabled,
                managed_prometheus_enabled=inventory.managed_prometheus_enabled,
                tags=inventory.tags,
                node_pools=pools,
                workloads=workloads,
                scheduling=normalize_scheduling(metadata) if metadata is not None else None,
                capacity=normalize_capacity(
                    inventory,
                    next(
                        source.generated_at
                        for source in inventories
                        if any(item.resource_id == cluster_id for item in source.clusters)
                    ),
                    metadata,
                    [
                        item
                        for item in fragments.pool_intents
                        if item.cluster_resource_id == cluster_id
                    ],
                ),
            )
        )
    inventory_receipts: list[CollectorResult] = []
    for inventory_source in inventories:
        receipt = inventory_source.collection.model_copy(deep=True)
        missing_clusters = set(targets) - {item.resource_id for item in inventory_source.clusters}
        missing_clusters = {
            cluster_id
            for cluster_id in missing_clusters
            if cluster_id in receipt.requested_scope
            or str(targets[cluster_id].subscription_id) in receipt.requested_scope
        }
        if missing_clusters:
            if receipt.status == CollectionStatus.COMPLETE:
                receipt.status = CollectionStatus.PARTIAL
            receipt.missing_fields.extend(
                f"{cluster_id}/inventory" for cluster_id in sorted(missing_clusters)
            )
        inventory_receipts.append(receipt)
    inventory_receipt = (
        inventory_receipts[0]
        if len(inventory_receipts) == 1
        else merge_collector_results(inventory_receipts)
    )
    inventory_expected = {
        target.resource_id
        if target.resource_id in inventory_receipt.requested_scope
        else str(target.subscription_id)
        if str(target.subscription_id) in inventory_receipt.requested_scope
        else target.resource_id
        for target in targets.values()
    }
    sources = [
        *_source_receipts(inventory_receipts, inventory_expected, "azure-inventory", generated_at),
        *_source_receipts(
            [item.collection for item in fragments.kubernetes],
            set(targets),
            "kubernetes-metadata",
            generated_at,
        ),
        *_source_receipts(
            [item.collection for item in fragments.metrics],
            set(targets),
            "prometheus",
            generated_at,
        ),
    ]
    sources.sort(key=lambda result: (result.collector, tuple(result.requested_scope)))
    results = [
        merge_collector_results([result for result in sources if result.collector == name])
        for name in ["azure-inventory", "kubernetes-metadata", "prometheus"]
    ]
    statuses = {result.status for result in results}
    manifest = CollectionManifest(
        tenant_id=str(profile.scope.tenant_id),
        status=next(iter(statuses)) if len(statuses) == 1 else CollectionStatus.PARTIAL,
        results=results,
        source_results=sources,
    )
    qualities = [
        pool.metric_quality["usage_cpu_p95_mcores"]
        for cluster in clusters
        for pool in cluster.node_pools
    ]
    qualities.extend(
        container.resources.metric_quality["usage_cpu_p95_mcores"]
        for cluster in clusters
        for workload in cluster.workloads
        for container in workload.containers
        if "usage_cpu_p95_mcores" in container.resources.metric_quality
    )
    snapshot = FleetSnapshot(
        generated_at=generated_at,
        metric_window=MetricWindow(
            start=fragments.window_start,
            end=fragments.window_end,
            sample_count=min((item.window.sample_count for item in qualities), default=0),
            coverage_ratio=min((item.window.coverage_ratio for item in qualities), default=0),
        ),
        source="approved-fragments",
        clusters=clusters,
        collection_manifest=manifest,
    )
    selected_packs = profile.analysis.packs or list(load_catalog().manifests)
    capabilities = [
        capability
        for pack_id in selected_packs
        for capability in evaluate_source_capabilities(
            profile, fragments.metrics, pack_id=pack_id, as_of=as_of or datetime.now(UTC)
        )
    ]
    snapshot.source_capabilities = capabilities
    report = analyze(snapshot, profile.analysis, as_of=as_of)
    return OfflineAssessment(
        status=(
            "partial"
            if issues or report.blocked_recommendations or manifest.status != "complete"
            else "complete"
        ),
        input_digest=_digest(fragments),
        profile_digest=_digest(profile, exclude={"report_directory"}),
        snapshot=snapshot,
        report=report,
        issues=sorted(issues, key=lambda item: (item.scope, item.code)),
        workload_inventory=workload_inventory,
        workload_history=workload_history,
        metadata_evidence=[item.model_copy(deep=True) for item in fragments.kubernetes],
        baseline_measurements=[
            observation.model_copy(deep=True)
            for fragment in fragments.metrics
            for observation in fragment.observations
            if observation.entity.kind == "unresolved_container"
        ],
    )
