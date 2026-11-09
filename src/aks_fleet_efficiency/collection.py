from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aks_fleet_efficiency.assessment import AssessmentFragments, _validate_bindings
from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.collectors.azure_resource_graph import (
    AzureResourceGraphCollector,
    InventoryPage,
    InventoryReader,
    InventoryReadError,
)
from aks_fleet_efficiency.collectors.kubernetes_metadata import (
    KubernetesMetadataCollector,
    KubernetesPage,
    KubernetesReader,
    KubernetesReadError,
    validate_metadata_projection,
)
from aks_fleet_efficiency.collectors.prometheus import (
    QUERY_CATALOG,
    MetricReader,
    MetricReadError,
    PrometheusMetricCollector,
    RangeQueryResult,
)
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import (
    CollectionError,
    CollectionStatus,
    CollectorResult,
    KubernetesMetadataSnapshot,
    MetricEntity,
    NonEmptyString,
    PrometheusMetricsSnapshot,
    UtcDatetime,
)
from aks_fleet_efficiency.workload_history import WorkloadAssessmentBinding


class ClusterCollectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    resource_id: NonEmptyString
    expected_cluster_uid: NonEmptyString
    expected_node_resource_group: str | None = None
    metadata_export: Path | None = None
    entities: list[MetricEntity] = Field(default_factory=list, max_length=10000)
    metrics: list[str] = Field(default_factory=lambda: list(QUERY_CATALOG))
    node_history_reference: NonEmptyString | None = None


class CollectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    schema_version: Literal["1.0"] = "1.0"
    window_start: UtcDatetime | None = None
    window_end: UtcDatetime | None = None
    step_seconds: int = Field(default=300, ge=1, le=300)
    clusters: list[ClusterCollectionPlan] = Field(min_length=1, max_length=100)
    workload_assessments: list[WorkloadAssessmentBinding] = Field(default_factory=list)
    maximum_reads: int = Field(default=2000, ge=1, le=10000)
    maximum_objects: int = Field(default=50000, ge=1, le=1000000)
    maximum_queries: int = Field(default=10000, ge=1, le=100000)
    maximum_duration_seconds: int = Field(default=600, ge=1, le=3600)
    maximum_metric_evaluations: int = Field(default=5000000, ge=1, le=100000000)
    maximum_series_per_response: int = Field(default=10000, ge=1, le=10000)

    @model_validator(mode="after")
    def validate_plan(self) -> CollectionPlan:
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("provide both collection window bounds or neither")
        if (
            self.window_start is not None
            and self.window_end is not None
            and self.window_end <= self.window_start
        ):
            raise ValueError("collection window must be ordered")
        if len({item.resource_id for item in self.clusters}) != len(self.clusters):
            raise ValueError("collection targets must be unique")
        if sum(len(item.entities) for item in self.clusters) > 10000:
            raise ValueError("collection entity limit exceeded")
        for item in self.clusters:
            if (
                not item.metrics
                or len(set(item.metrics)) != len(item.metrics)
                or any(name not in QUERY_CATALOG for name in item.metrics)
            ):
                raise ValueError("select distinct approved metric catalog keys")
            if any(entity.cluster_resource_id != item.resource_id for entity in item.entities):
                raise ValueError("metric entity exceeds its exact planned scope")
        return self


@dataclass
class CollectionReaders:
    inventory: InventoryReader
    kubernetes: Mapping[str, KubernetesReader] = field(default_factory=dict)
    metrics: Mapping[str, MetricReader] = field(default_factory=dict)
    metadata_snapshots: Mapping[str, KubernetesMetadataSnapshot] = field(default_factory=dict)


def selected_metric_inputs(
    profile: OnboardingConfig, target: ClusterCollectionPlan
) -> tuple[list[str], list[MetricEntity]]:
    requirements = (
        None
        if profile.analysis.packs is None
        else {
            name
            for pack_id in profile.analysis.packs
            for references in load_catalog().pack(pack_id).queries[profile.analysis.mode].values()
            for name in references
        }
    )
    metrics = [name for name in target.metrics if requirements is None or name in requirements]
    entities = [
        entity
        for entity in target.entities
        if any(
            QUERY_CATALOG[name].kind == entity.kind
            or (entity.kind == "unresolved_container" and name in {"cpu_usage", "cpu_request"})
            for name in metrics
        )
    ]
    return metrics, entities


@dataclass
class _Budget:
    plan: CollectionPlan
    clock: Callable[[], datetime]
    started: datetime
    reads: int = 0
    objects: int = 0

    def within_deadline(self) -> bool:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None or now < self.started:
            raise ValueError("collection clock must be causal and timezone-aware")
        return (now - self.started).total_seconds() <= self.plan.maximum_duration_seconds

    def take(self) -> bool:
        if (
            not self.within_deadline()
            or self.reads >= self.plan.maximum_reads
            or self.objects > self.plan.maximum_objects
        ):
            return False
        self.reads += 1
        return True

    def receive(self, objects: int) -> bool:
        self.objects += objects
        return self.objects <= self.plan.maximum_objects and self.within_deadline()


class _InventoryReader:
    def __init__(self, reader: InventoryReader, budget: _Budget) -> None:
        self.reader, self.budget, self.tenant_id = reader, budget, reader.tenant_id

    def query(
        self, *, subscription_id: str, query: str, skip_token: str | None, page_size: int
    ) -> InventoryPage:
        if not self.budget.take():
            raise InventoryReadError("timeout")
        result = self.reader.query(
            subscription_id=subscription_id, query=query, skip_token=skip_token, page_size=page_size
        )
        if not self.budget.receive(len(result.rows)):
            raise InventoryReadError("timeout")
        return result


class _KubernetesReader:
    def __init__(self, reader: KubernetesReader, budget: _Budget) -> None:
        self.reader, self.budget, self.cluster_resource_id = (
            reader,
            budget,
            reader.cluster_resource_id,
        )

    def discover(self) -> set[str]:
        if not self.budget.take():
            raise KubernetesReadError("timeout")
        result = self.reader.discover()
        if not self.budget.receive(0):
            raise KubernetesReadError("timeout")
        return result

    def list_page(
        self, resource: str, *, continue_token: str | None, page_size: int
    ) -> KubernetesPage:
        if not self.budget.take():
            raise KubernetesReadError("timeout")
        result = self.reader.list_page(resource, continue_token=continue_token, page_size=page_size)
        if not self.budget.receive(len(result.items)):
            raise KubernetesReadError("timeout")
        return result


class _MetricReader:
    def __init__(self, reader: MetricReader, budget: _Budget) -> None:
        self.reader, self.budget, self.source_name = reader, budget, reader.source_name

    def query_range(
        self, *, query: str, start: datetime, end: datetime, step_seconds: int
    ) -> RangeQueryResult:
        if not self.budget.take():
            raise MetricReadError("timeout")
        result = self.reader.query_range(
            query=query, start=start, end=end, step_seconds=step_seconds
        )
        if not self.budget.receive(0):
            raise MetricReadError("timeout")
        return result


def _failure(name: str, scope: str, now: datetime) -> CollectorResult:
    return CollectorResult(
        collector=name,
        status=CollectionStatus.FAILED,
        requested_scope=[scope],
        started_at=now,
        completed_at=now,
        errors=[CollectionError(scope=scope, code="unavailable")],
    )


def validate_metadata_binding(
    snapshot: KubernetesMetadataSnapshot, target: ClusterCollectionPlan, profile: OnboardingConfig
) -> None:
    validate_metadata_projection(snapshot)
    if (
        snapshot.tenant_id != str(profile.scope.tenant_id)
        or snapshot.cluster_resource_id != target.resource_id
    ):
        raise ValueError("metadata export exceeds approved tenant or scope")
    if snapshot.cluster_uid != target.expected_cluster_uid:
        if snapshot.collection.status != CollectionStatus.FAILED or snapshot.resources:
            raise ValueError(
                "metadata fingerprint does not match the independently approved binding"
            )
    if (
        snapshot.collection.collector != "kubernetes-metadata"
        or snapshot.collection.requested_scope != [target.resource_id]
    ):
        raise ValueError("metadata receipt does not match approved scope")
    if snapshot.resources:
        fingerprints = [
            item.uid
            for item in snapshot.resources
            if item.kind == "Namespace" and item.name == "kube-system"
        ]
        if fingerprints != [target.expected_cluster_uid]:
            raise ValueError("metadata namespace fingerprint does not match approved binding")


def collect_fragments(
    profile: OnboardingConfig,
    plan: CollectionPlan,
    readers: CollectionReaders,
    *,
    allow_live: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AssessmentFragments:
    if not allow_live:
        raise PermissionError("collection requires explicit operator consent")
    targets = {target.resource_id: target for target in profile.clusters}
    if not targets or set(targets) != {item.resource_id for item in plan.clusters}:
        raise ValueError("collection plan must match explicit approved cluster scope")
    planned_targets = {item.resource_id: item for item in plan.clusters}
    seen_bindings: set[tuple[str, str]] = set()
    for binding in plan.workload_assessments:
        key = (binding.cluster_resource_id, binding.workload_uid)
        if (
            key in seen_bindings
            or binding.tenant_id != str(profile.scope.tenant_id)
            or binding.cluster_resource_id not in targets
            or binding.source_name != targets[binding.cluster_resource_id].metric_source
            or binding.cluster_uid
            != planned_targets[binding.cluster_resource_id].expected_cluster_uid
        ):
            raise ValueError("historical policy binding exceeds approved collection scope")
        seen_bindings.add(key)
    if readers.inventory.tenant_id != str(profile.scope.tenant_id):
        raise ValueError("inventory reader tenant does not match approved scope")
    if (set(readers.kubernetes) | set(readers.metadata_snapshots)) - set(targets):
        raise ValueError("metadata readers exceed approved scope")
    if set(readers.kubernetes) & set(readers.metadata_snapshots):
        raise ValueError("one explicit metadata source is required per target")
    if any(reader.cluster_resource_id != scope for scope, reader in readers.kubernetes.items()):
        raise ValueError("metadata reader binding does not match approved scope")
    if set(readers.metrics) - {source.name for source in profile.metric_sources}:
        raise ValueError("metric readers exceed approved source scope")
    if any(reader.source_name != source for source, reader in readers.metrics.items()):
        raise ValueError("metric reader binding does not match approved source")
    started = clock()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("collection clock must be timezone-aware")
    end = plan.window_end or started.astimezone(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = plan.window_start or end - timedelta(
        days=profile.analysis.thresholds.minimum_observation_days
    )
    if end > started or plan.step_seconds > profile.analysis.thresholds.maximum_metric_step_seconds:
        raise ValueError("collection window or resolution exceeds approved bounds")
    if any(
        binding.safety_policy.reviewed_window_start != start
        or binding.safety_policy.reviewed_window_end != end
        for binding in plan.workload_assessments
    ):
        raise ValueError("historical policy must review the exact requested window")
    if (
        sum(len(item.resources) for item in readers.metadata_snapshots.values())
        > plan.maximum_objects
    ):
        raise ValueError("metadata exports exceed the total object budget")
    budget = _Budget(
        plan,
        clock,
        started,
        objects=sum(len(item.resources) for item in readers.metadata_snapshots.values()),
    )
    prepared_metrics: dict[str, PrometheusMetricCollector] = {}
    selected_metrics: dict[str, list[str]] = {}
    query_count = 0
    evaluation_count = 0
    for target in plan.clusters:
        if target.resource_id in readers.metadata_snapshots:
            validate_metadata_binding(
                readers.metadata_snapshots[target.resource_id], target, profile
            )
        source_name = targets[target.resource_id].metric_source
        metrics, entities = selected_metric_inputs(profile, target)
        selected_metrics[target.resource_id] = metrics
        if entities:
            if source_name is None or source_name not in readers.metrics:
                raise ValueError("an explicitly injected approved metric reader is required")
            collector = PrometheusMetricCollector(
                profile,
                source_name=source_name,
                reader=_MetricReader(readers.metrics[source_name], budget),
                entities=entities,
                clock=clock,
                max_retries=0,
                max_queries=plan.maximum_queries,
                node_history_complete=target.node_history_reference is not None,
                maximum_evaluations=plan.maximum_metric_evaluations,
                maximum_series=plan.maximum_series_per_response,
            )
            prepared_metrics[target.resource_id] = collector
            query_plan = collector.plan_queries(
                start=start, end=end, step_seconds=plan.step_seconds, metrics=metrics
            )
            query_count += query_plan.requests
            evaluation_count += query_plan.expected_evaluations
    if query_count > plan.maximum_queries or evaluation_count > plan.maximum_metric_evaluations:
        raise ValueError("collection exceeds the total query/evaluation budget")
    inventories = []
    for subscription in sorted({str(target.subscription_id) for target in profile.clusters}):
        scoped_payload = profile.model_dump(mode="json")
        scoped_payload["scope"]["subscription_ids"] = [subscription]
        scoped_payload["clusters"] = [
            target.model_dump(mode="json")
            for target in profile.clusters
            if str(target.subscription_id) == subscription
        ]
        scoped_payload["ownership"] = [
            owner.model_dump(mode="json")
            for owner in profile.ownership
            if owner.cluster_resource_id
            in {target["resource_id"] for target in scoped_payload["clusters"]}
        ]
        scoped = OnboardingConfig.model_validate(scoped_payload)
        inventories.append(
            AzureResourceGraphCollector(
                scoped,
                reader=_InventoryReader(readers.inventory, budget),
                clock=clock,
                max_retries=0,
                max_pages=20,
                page_size=250,
            ).collect()
        )
    metadata = []
    observations = []
    for target in sorted(plan.clusters, key=lambda item: item.resource_id):
        if target.resource_id in readers.metadata_snapshots:
            snapshot = readers.metadata_snapshots[target.resource_id].model_copy(deep=True)
        elif target.resource_id in readers.kubernetes:
            azure_cluster = next(
                (
                    cluster
                    for inventory in inventories
                    for cluster in inventory.clusters
                    if cluster.resource_id == target.resource_id
                ),
                None,
            )
            snapshot = KubernetesMetadataCollector(
                profile,
                cluster_resource_id=target.resource_id,
                expected_cluster_uid=target.expected_cluster_uid,
                reader=_KubernetesReader(readers.kubernetes[target.resource_id], budget),
                azure_cluster=azure_cluster,
                expected_node_resource_group=target.expected_node_resource_group,
                clock=clock,
                max_retries=0,
                max_pages=20,
                page_size=250,
            ).collect()
        else:
            now = clock()
            snapshot = KubernetesMetadataSnapshot(
                tenant_id=str(profile.scope.tenant_id),
                cluster_resource_id=target.resource_id,
                generated_at=now,
                collection=_failure("kubernetes-metadata", target.resource_id, now),
                api_availability={},
                resources=[],
            )
        metadata.append(snapshot)
        if target.resource_id in prepared_metrics:
            observations.append(
                prepared_metrics[target.resource_id].collect_observations(
                    start=start,
                    end=end,
                    step_seconds=plan.step_seconds,
                    metrics=selected_metrics[target.resource_id],
                )
            )
        else:
            now = clock()
            source = targets[target.resource_id].metric_source or "unconfigured"
            observations.append(
                PrometheusMetricsSnapshot(
                    tenant_id=str(profile.scope.tenant_id),
                    source_name=source,
                    generated_at=now,
                    query_start=start,
                    query_end=end,
                    step_seconds=plan.step_seconds,
                    collection=_failure("prometheus", target.resource_id, now),
                    observations=[],
                )
            )
    fragments = AssessmentFragments(
        window_start=start,
        window_end=end,
        azure=inventories,
        kubernetes=metadata,
        metrics=[
            item
            for item in observations
            if targets[item.collection.requested_scope[0]].metric_source is not None
        ],
        workload_assessments=plan.workload_assessments,
    )
    _validate_bindings(fragments, profile)
    return fragments
