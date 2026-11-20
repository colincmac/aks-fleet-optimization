from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from aks_fleet_efficiency.catalog.models import (
    CANDIDATE_PRODUCER_VERSIONS,
    AssessmentMode,
    PackProvenance,
    SourceDefinition,
)


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_normalize_utc)]
NonEmptyString = Annotated[str, Field(min_length=1)]
QosClass = Literal["Guaranteed", "Burstable", "BestEffort"]


class CollectionStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


CollectionErrorCode = Literal[
    "unauthorized",
    "forbidden",
    "timeout",
    "throttled",
    "unavailable",
    "invalid-response",
    "response-budget-exceeded",
    "identity-mismatch",
]


class CollectionError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: NonEmptyString
    code: CollectionErrorCode


class CollectorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    collector: NonEmptyString
    status: CollectionStatus
    requested_scope: list[NonEmptyString] = Field(min_length=1)
    completed_scope: list[NonEmptyString] = Field(default_factory=list)
    started_at: UtcDatetime
    completed_at: UtcDatetime
    source_observed_at: UtcDatetime | None = None
    pagination_complete: bool = False
    retry_count: int = Field(default=0, ge=0)
    errors: list[CollectionError] = Field(default_factory=list)
    missing_fields: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_collection(self) -> CollectorResult:
        if self.completed_at < self.started_at:
            raise ValueError("collection completion must not precede its start")
        if self.source_observed_at is not None and self.source_observed_at > self.completed_at:
            raise ValueError("source observation must not follow collection completion")
        requested = set(self.requested_scope)
        completed = set(self.completed_scope)
        if len(requested) != len(self.requested_scope) or len(completed) != len(
            self.completed_scope
        ):
            raise ValueError("collection scope must not contain duplicates")
        if not completed <= requested:
            raise ValueError("completed scope must be within requested scope")
        error_scopes = {error.scope for error in self.errors}
        if not error_scopes <= requested or error_scopes & completed:
            raise ValueError("errors must refer to requested, uncompleted scope")
        is_complete = (
            requested == completed
            and self.pagination_complete
            and not self.errors
            and not self.missing_fields
        )
        if self.status == CollectionStatus.COMPLETE and not is_complete:
            raise ValueError("complete collection requires all scope, pages, and required fields")
        if self.status == CollectionStatus.PARTIAL and is_complete:
            raise ValueError("partial collection must identify incomplete evidence")
        if self.status == CollectionStatus.FAILED and (completed or not self.errors):
            raise ValueError("failed collection requires errors and no completed scope")
        return self


def merge_collector_results(receipts: list[CollectorResult]) -> CollectorResult:
    if not receipts or len({receipt.collector for receipt in receipts}) != 1:
        raise ValueError("aggregation requires receipts from one collector")
    requested = {scope for receipt in receipts for scope in receipt.requested_scope}
    completed = {scope for receipt in receipts for scope in receipt.completed_scope}
    errors = {(error.scope, error.code) for receipt in receipts for error in receipt.errors}
    if {scope for scope, _ in errors} & completed:
        raise ValueError("conflicting collection receipts")
    complete = all(receipt.status == CollectionStatus.COMPLETE for receipt in receipts)
    source_times = [receipt.source_observed_at for receipt in receipts]
    return CollectorResult(
        collector=receipts[0].collector,
        status=(
            CollectionStatus.COMPLETE
            if complete
            else CollectionStatus.FAILED
            if not completed and errors
            else CollectionStatus.PARTIAL
        ),
        requested_scope=sorted(requested),
        completed_scope=sorted(completed),
        started_at=min(receipt.started_at for receipt in receipts),
        completed_at=max(receipt.completed_at for receipt in receipts),
        source_observed_at=(
            min(time for time in source_times if time is not None)
            if all(time is not None for time in source_times)
            else None
        ),
        pagination_complete=all(receipt.pagination_complete for receipt in receipts),
        retry_count=sum(receipt.retry_count for receipt in receipts),
        errors=[CollectionError(scope=scope, code=code) for scope, code in sorted(errors)],
        missing_fields=sorted({field for receipt in receipts for field in receipt.missing_fields}),
    )


class CollectionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    tenant_id: NonEmptyString
    status: CollectionStatus
    results: list[CollectorResult] = Field(min_length=1)
    source_results: list[CollectorResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self) -> CollectionManifest:
        names = [result.collector for result in self.results]
        if len(set(names)) != len(names):
            raise ValueError("manifest requires one result per collector")
        statuses = {result.status for result in self.results}
        expected = statuses.pop() if len(statuses) == 1 else CollectionStatus.PARTIAL
        if self.status != expected:
            raise ValueError("manifest status must reflect every collector result")
        grouped: dict[str, list[CollectorResult]] = {}
        scopes: set[tuple[str, str]] = set()
        for result in self.source_results:
            for scope in result.requested_scope:
                key = (result.collector, scope)
                if key in scopes:
                    raise ValueError("source receipts must not overlap within a collector")
                scopes.add(key)
            grouped.setdefault(result.collector, []).append(result)
        if set(grouped) != set(names):
            raise ValueError("every aggregate requires its source receipts")
        for result in self.results:
            if result != merge_collector_results(grouped[result.collector]):
                raise ValueError("aggregate must exactly reflect its source receipts")
        return self


class CurrentContainerAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    name: NonEmptyString
    state: Literal["running", "waiting", "terminated", "unknown"]
    restart_count: int | None = Field(default=None, ge=0, strict=True)
    started_at: UtcDatetime | None = None
    container_id_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    pod_to_attempt_start_seconds: float | None = Field(default=None, ge=0)
    issues: list[NonEmptyString] = Field(default_factory=list)


class PodContainerAttempts(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["supplied-current-container-attempt"] = "supplied-current-container-attempt"
    mapping_reference: Literal["kubernetes-core-v1@v1.36.0"] = "kubernetes-core-v1@v1.36.0"
    tenant_id: NonEmptyString
    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: NonEmptyString
    workload_uid: NonEmptyString | None = None
    pod_uid: NonEmptyString
    pod_resource_version: NonEmptyString | None = None
    pod_created_at: UtcDatetime | None = None
    metadata_generated_at: UtcDatetime
    collection: CollectorResult
    containers: list[CurrentContainerAttempt] = Field(min_length=1, max_length=1000)
    issues: list[NonEmptyString] = Field(default_factory=list)
    first_startup: Literal["unknown"] = "unknown"
    application_startup_duration_seconds: None = None
    post_startup_demand: None = None

    @model_validator(mode="after")
    def validate_attempts(self) -> PodContainerAttempts:
        if (
            self.collection.collector != "kubernetes-metadata"
            or self.collection.requested_scope != [self.cluster_resource_id]
            or self.collection.completed_at > self.metadata_generated_at
        ):
            raise ValueError("Current-attempt context requires original metadata scope and clocks")
        if self.pod_created_at is not None and self.pod_created_at > self.metadata_generated_at:
            raise ValueError("Pod creation must not follow metadata generation")
        names = [container.name for container in self.containers]
        if len(set(names)) != len(names):
            raise ValueError("Current-attempt containers must be distinct")
        for container in self.containers:
            started = container.started_at
            if started is not None and (
                container.state != "running"
                or started > self.metadata_generated_at
                or (self.pod_created_at is not None and started < self.pod_created_at)
            ):
                raise ValueError("Current running start must be inside the observed Pod lifetime")
            expected = (
                (started - self.pod_created_at).total_seconds()
                if started is not None and self.pod_created_at is not None
                else None
            )
            if container.pod_to_attempt_start_seconds != expected:
                raise ValueError("Current-attempt elapsed time must match the supplied clocks")
        return self


class StartupLifecycleSample(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    observed_at: UtcDatetime | None
    metadata_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation: PodContainerAttempts
    ready: Literal["True", "False", "Unknown"]
    issues: list[NonEmptyString] = Field(default_factory=list)


class StartupHistoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["sampled-pod-readiness-proxy"] = "sampled-pod-readiness-proxy"
    source_admission: Literal["unverified_saved_native_observations"] = (
        "unverified_saved_native_observations"
    )
    tenant_id: NonEmptyString
    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: NonEmptyString
    workload_uid: NonEmptyString
    pod_uid: NonEmptyString
    container: NonEmptyString
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: int = Field(gt=0, le=300, strict=True)
    evaluated_at: UtcDatetime
    maximum_source_age_seconds: int = Field(gt=0, strict=True)
    samples: list[StartupLifecycleSample] = Field(max_length=10_000)
    usage: PrometheusMetricsSnapshot | None = None
    status: Literal["observed_transition", "not_observed", "blocked"] = "blocked"
    pod_to_observed_ready_lower_seconds: float | None = Field(default=None, ge=0)
    pod_to_observed_ready_upper_seconds: float | None = Field(default=None, ge=0)
    post_readiness_cpu_p95_mcpu: float | None = Field(default=None, ge=0)
    post_readiness_memory_p99_mib: float | None = Field(default=None, ge=0)
    first_startup: Literal["unknown"] = "unknown"
    application_startup_duration_seconds: None = None
    issues: list[NonEmptyString] = Field(default_factory=list)
    usage_issues: list[NonEmptyString] = Field(default_factory=list)


class AzureNodePoolInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    resource_id: NonEmptyString
    name: NonEmptyString
    vm_size: NonEmptyString
    mode: str | None = None
    node_count: int | None = Field(default=None, ge=0)
    min_count: int | None = Field(default=None, ge=0)
    max_count: int | None = Field(default=None, ge=0)
    autoscaling_enabled: bool | None = None
    spot: bool | None = None
    zones: list[str] | None = None
    os_type: str | None = None


class AzureClusterInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    resource_id: NonEmptyString
    name: NonEmptyString
    subscription_id: NonEmptyString
    resource_group: NonEmptyString
    location: NonEmptyString
    kubernetes_version: str | None = None
    sku_tier: str | None = None
    node_provisioning_mode: str | None = None
    cost_analysis_enabled: bool | None = None
    managed_prometheus_enabled: bool | None = None
    keda_enabled: bool | None = None
    vpa_enabled: bool | None = None
    fleet_ids: list[str] | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    node_pools: list[AzureNodePoolInventory]


class AzureInventorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    source: Literal["azure-resource-graph"] = "azure-resource-graph"
    query_version: Literal["1.0"] = "1.0"
    tenant_id: NonEmptyString
    generated_at: UtcDatetime
    collection: CollectorResult
    clusters: list[AzureClusterInventory]


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MetricWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: UtcDatetime
    end: UtcDatetime
    sample_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_window(self) -> MetricWindow:
        if self.end <= self.start:
            raise ValueError("metric window end must be after start")
        if self.sample_count == 0 and self.coverage_ratio > 0:
            raise ValueError("positive coverage requires observed samples")
        return self


class MetricQuality(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source: NonEmptyString
    query_version: NonEmptyString
    query_asset_version: NonEmptyString | None = None
    step_seconds: int = Field(gt=0)
    observed_at: UtcDatetime
    window: MetricWindow
    unit: NonEmptyString
    minimum: float | None = None
    maximum: float | None = None
    query_expression: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_quality(self) -> MetricQuality:
        if self.window.sample_count == 0 and (self.minimum is not None or self.maximum is not None):
            raise ValueError("observed extrema require observed samples")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("observed minimum must not exceed maximum")
        if self.observed_at < self.window.end:
            raise ValueError("observation timestamp must not precede the metric window end")
        return self


class ResourceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    request_cpu_mcores: float | None = Field(default=None, ge=0)
    cpu_request_observed: bool = False
    cpu_observation_basis: Literal["pod", "replica-envelope"] | None = None
    limit_cpu_mcores: float | None = Field(default=None, ge=0)
    usage_cpu_p50_mcores: float | None = Field(default=None, ge=0)
    usage_cpu_p95_mcores: float | None = Field(default=None, ge=0)
    usage_cpu_p99_mcores: float | None = Field(default=None, ge=0)
    request_memory_mib: float | None = Field(default=None, ge=0)
    memory_request_observed: bool = False
    memory_observation_basis: Literal["pod", "replica-envelope"] | None = None
    memory_membership_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    limit_memory_mib: float | None = Field(default=None, ge=0)
    memory_limit_observed: bool = False
    usage_memory_p50_mib: float | None = Field(default=None, ge=0)
    usage_memory_p95_mib: float | None = Field(default=None, ge=0)
    usage_memory_p99_mib: float | None = Field(default=None, ge=0)
    total_memory_usage_p99_mib: float | None = Field(default=None, ge=0)
    cpu_throttled_ratio: float | None = Field(default=None, ge=0, le=1)
    memory_oom_events: int | None = Field(default=None, ge=0)
    restart_events: int | None = Field(default=None, ge=0)
    metric_quality: dict[str, MetricQuality] = Field(default_factory=dict)


class AutoscalingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hpa: bool | None = None
    vpa: bool | None = None
    vpa_mode: str | None = None
    keda: bool | None = None
    min_replicas: int | None = Field(default=None, ge=0)
    max_replicas: int | None = Field(default=None, ge=0)


class ContainerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str | None = None
    resources: ResourceObservation


class MemorySafetyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    allow_request_reduction: bool = Field(default=False, strict=True)
    minimum_request_mib: float = Field(gt=0, strict=True)
    maximum_reduction_ratio: float = Field(gt=0, lt=1, strict=True)
    headroom_factor: float = Field(ge=1, strict=True)
    evidence_reference: Annotated[str, Field(min_length=1, pattern=r"\S")]
    startup_peak_mib: float | None = Field(default=None, gt=0, strict=True)
    failover_peak_mib: float | None = Field(default=None, gt=0, strict=True)
    eviction_events: int | None = Field(default=None, ge=0, strict=True)
    qos_class: QosClass | None = None


class MemoryLimitPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    allow_limit_reduction: bool = Field(default=False, strict=True)
    minimum_limit_mib: float = Field(gt=0, strict=True)
    maximum_reduction_ratio: float = Field(gt=0, lt=1, strict=True)
    headroom_factor: float = Field(ge=1, strict=True)
    startup_total_peak_mib: float | None = Field(default=None, gt=0, strict=True)
    failover_total_peak_mib: float | None = Field(default=None, gt=0, strict=True)
    allocator_cache_reviewed: bool | None = Field(default=None, strict=True)
    configuration_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_reference: Annotated[str, Field(min_length=1, pattern=r"\S")]


class ReplicaSafetyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    allow_floor_reduction: bool = Field(default=False, strict=True)
    hpa_uid: NonEmptyString
    minimum_available_replicas: int = Field(ge=1, strict=True)
    tested_replicas: int = Field(ge=1, strict=True)
    maximum_reduction_ratio: float = Field(gt=0, lt=1, strict=True)
    failover_reserve_replicas: int | None = Field(default=None, ge=0, strict=True)
    maximum_unavailable_replicas: int | None = Field(default=None, ge=0, strict=True)
    peak_load_reviewed: bool | None = Field(default=None, strict=True)
    startup_reviewed: bool | None = Field(default=None, strict=True)
    throughput_reviewed: bool | None = Field(default=None, strict=True)
    zone_failure_reviewed: bool | None = Field(default=None, strict=True)
    reliability_reviewed: bool | None = Field(default=None, strict=True)
    oom_events: int | None = Field(default=None, ge=0, strict=True)
    restart_events: int | None = Field(default=None, ge=0, strict=True)
    eviction_events: int | None = Field(default=None, ge=0, strict=True)
    configuration_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_reference: NonEmptyString


class WorkloadSafetyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    owner: NonEmptyString
    slo_reference: NonEmptyString
    reviewed_window_start: UtcDatetime
    reviewed_window_end: UtcDatetime
    disruption_reviewed: bool
    minimum_cpu_request_mcores: float = Field(gt=0)
    maximum_cpu_reduction_ratio: float = Field(gt=0, lt=1)
    cpu_headroom_factor: float = Field(ge=1)
    maximum_cpu_throttled_ratio: float = Field(ge=0, le=1)
    memory: dict[NonEmptyString, MemorySafetyPolicy] = Field(default_factory=dict)
    memory_limits: dict[NonEmptyString, MemoryLimitPolicy] = Field(default_factory=dict)
    replicas: ReplicaSafetyPolicy | None = None

    @model_validator(mode="after")
    def validate_reviewed_window(self) -> WorkloadSafetyPolicy:
        if self.reviewed_window_end <= self.reviewed_window_start:
            raise ValueError("reviewed window end must be after start")
        return self


class HpaMetricSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    metric_type: Literal["Resource", "ContainerResource", "External", "Pods", "Object"]
    resource: NonEmptyString | None = None
    container: NonEmptyString | None = None
    target_type: Literal["Utilization", "AverageValue", "Value"]
    average_utilization: int | None = Field(default=None, gt=0, strict=True)
    target_value: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_signal(self) -> HpaMetricSignal:
        resource_metric = self.metric_type in {"Resource", "ContainerResource"}
        if resource_metric != (self.resource is not None):
            raise ValueError("resource signals require an explicit resource only")
        if (self.metric_type == "ContainerResource") != (self.container is not None):
            raise ValueError("container resource signals require an exact container only")
        if self.target_type == "Utilization":
            if (
                not resource_metric
                or self.average_utilization is None
                or self.target_value is not None
            ):
                raise ValueError("utilization requires an explicit positive resource percentage")
        elif self.target_value is None or self.average_utilization is not None:
            raise ValueError("absolute signals require a quantity, not a utilization percentage")
        if resource_metric and self.target_type == "Value":
            raise ValueError("resource signals require utilization or an average value")
        if self.metric_type == "Pods" and self.target_type != "AverageValue":
            raise ValueError("Pod signals require an average value")
        return self


class AutoscalerOwnerReference(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    api_version: NonEmptyString
    kind: NonEmptyString
    name: NonEmptyString
    uid: NonEmptyString
    controller: bool = Field(strict=True)


class HpaConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    uid: NonEmptyString
    name: NonEmptyString
    metrics: list[HpaMetricSignal] = Field(min_length=1)
    min_replicas: int | None = Field(default=None, ge=0, strict=True)
    max_replicas: int | None = Field(default=None, gt=0, strict=True)
    current_replicas: int | None = Field(default=None, ge=0, strict=True)
    desired_replicas: int | None = Field(default=None, ge=0, strict=True)
    owner_references: list[AutoscalerOwnerReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bounds(self) -> HpaConfiguration:
        if self.min_replicas is not None and self.max_replicas is not None:
            if self.min_replicas > self.max_replicas:
                raise ValueError("HPA minimum must not exceed maximum")
        return self


HpaReplicaMetricName = Literal[
    "hpa_min_replicas", "hpa_max_replicas", "hpa_desired_replicas", "hpa_current_replicas"
]
HPA_REPLICA_METRICS: tuple[HpaReplicaMetricName, ...] = (
    "hpa_min_replicas",
    "hpa_max_replicas",
    "hpa_desired_replicas",
    "hpa_current_replicas",
)
WorkloadReplicaMetricName = Literal["desired_replicas", "observed_replicas", "available_replicas"]
WORKLOAD_REPLICA_METRICS: tuple[WorkloadReplicaMetricName, ...] = (
    "desired_replicas",
    "observed_replicas",
    "available_replicas",
)


class HpaReplicaMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    minimum: int = Field(ge=0, strict=True)
    maximum: int = Field(ge=0, strict=True)
    quality: MetricQuality

    @model_validator(mode="after")
    def validate_extrema(self) -> HpaReplicaMetric:
        if self.minimum > self.maximum or (
            self.minimum != self.quality.minimum or self.maximum != self.quality.maximum
        ):
            raise ValueError("HPA history extrema must match their observed quality")
        return self


class HpaReplicaHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString
    namespace_uid: NonEmptyString
    workload_uid: NonEmptyString
    hpa_uid: NonEmptyString
    source_name: NonEmptyString
    history_reference: NonEmptyString
    query_version: Literal["1.0"] = "1.0"
    metrics: dict[HpaReplicaMetricName, HpaReplicaMetric] = Field(default_factory=dict)
    workload_metrics: dict[WorkloadReplicaMetricName, HpaReplicaMetric] = Field(
        default_factory=dict
    )
    availability_issues: list[NonEmptyString] = Field(default_factory=list)
    reliability_issues: list[NonEmptyString] = Field(default_factory=list)
    issues: list[
        Literal[
            "hpa_history_identity_mismatch",
            "unsupported_hpa_history_metric",
            "unreviewed_hpa_history_window",
        ]
    ] = Field(default_factory=list)


class VpaResourceValues(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    cpu_mcores: float | None = Field(default=None, ge=0)
    memory_mib: float | None = Field(default=None, ge=0)


class VpaContainerRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    container_name: NonEmptyString
    target: VpaResourceValues
    lower_bound: VpaResourceValues
    upper_bound: VpaResourceValues
    uncapped_target: VpaResourceValues | None = None


class VpaContainerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    container_name: NonEmptyString
    mode: Literal["Auto", "Off"]
    controlled_resources: list[Literal["cpu", "memory"]] | None = None
    controlled_values: Literal["RequestsOnly", "RequestsAndLimits"] | None = None
    min_allowed: VpaResourceValues | None = None
    max_allowed: VpaResourceValues | None = None

    @model_validator(mode="after")
    def validate_resources(self) -> VpaContainerPolicy:
        if self.mode == "Auto" and not self.controlled_resources:
            raise ValueError("active policies require explicit controlled resources")
        if self.controlled_resources is not None and len(set(self.controlled_resources)) != len(
            self.controlled_resources
        ):
            raise ValueError("controlled resources must be unique")
        return self


class VpaConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    uid: NonEmptyString
    name: NonEmptyString
    update_mode: Literal["Off", "Initial", "Recreate", "Auto", "InPlaceOrRecreate"]
    container_policies: list[VpaContainerPolicy] = Field(default_factory=list)
    recommendations: list[VpaContainerRecommendation] = Field(default_factory=list)
    evidence_issues: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_policies(self) -> VpaConfiguration:
        if self.update_mode != "Off" and not self.container_policies:
            raise ValueError("mutating VPA requires explicit container policies")
        names = [item.container_name for item in self.container_policies]
        if len(set(names)) != len(names):
            raise ValueError("container policies must be unique")
        names = [item.container_name for item in self.recommendations]
        if len(set(names)) != len(names):
            raise ValueError("VPA recommendation containers must be unique")
        return self


class KedaTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    type: NonEmptyString
    metric_type: Literal["Utilization", "AverageValue", "Value"] | None = None


class KedaConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    uid: NonEmptyString
    name: NonEmptyString
    triggers: list[KedaTrigger] = Field(min_length=1)
    min_replicas: int | None = Field(default=None, ge=0, strict=True)
    max_replicas: int | None = Field(default=None, gt=0, strict=True)
    polling_interval_seconds: int | None = Field(default=None, gt=0, strict=True)
    cooldown_period_seconds: int | None = Field(default=None, ge=0, strict=True)
    generated_hpa_name: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> KedaConfiguration:
        if (
            self.min_replicas is not None
            and self.max_replicas is not None
            and self.min_replicas > self.max_replicas
        ):
            raise ValueError("KEDA minimum must not exceed maximum")
        return self


class WorkloadAutoscalerConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString | None
    namespace: NonEmptyString
    namespace_uid: NonEmptyString | None
    workload_uid: NonEmptyString | None
    target_api_version: Literal["apps/v1"]
    target_kind: Literal["Deployment", "StatefulSet"]
    target_name: NonEmptyString
    observed_at: UtcDatetime
    current_only: Literal[True] = True
    hpa_observed: bool = Field(default=False, strict=True)
    vpa_observed: bool = Field(default=False, strict=True)
    keda_observed: bool = Field(default=False, strict=True)
    hpas: list[HpaConfiguration] = Field(default_factory=list)
    vpas: list[VpaConfiguration] = Field(default_factory=list)
    kedas: list[KedaConfiguration] = Field(default_factory=list)
    workload_available_replicas: int | None = Field(default=None, ge=0, strict=True)
    replica_constraint_issues: list[NonEmptyString] | None = None
    replica_pod_configuration_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    issues: list[
        Literal[
            "ambiguous_autoscaler_target",
            "unsupported_hpa_configuration",
            "unsupported_vpa_configuration",
            "unsupported_keda_configuration",
        ]
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_controllers(self) -> WorkloadAutoscalerConfiguration:
        uids = (
            [item.uid for item in self.hpas]
            + [item.uid for item in self.vpas]
            + [item.uid for item in self.kedas]
        )
        if len(set(uids)) != len(uids):
            raise ValueError("autoscaler identities must be unique")
        for names in [
            [item.name for item in self.hpas],
            [item.name for item in self.vpas],
            [item.name for item in self.kedas],
        ]:
            if len(set(names)) != len(names):
                raise ValueError("autoscaler names must be unique within kind")
        return self


class PodMemoryAccounting(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pod_uid: NonEmptyString
    observed_at: UtcDatetime
    current_only: Literal[True] = True
    application_request_mib: float | None = Field(default=None, ge=0)
    init_peak_request_mib: float | None = Field(default=None, ge=0)
    overhead_mib: float | None = Field(default=None, ge=0)
    effective_request_mib: float | None = Field(default=None, ge=0)
    issues: list[NonEmptyString] = Field(default_factory=list)


class ContainerTerminationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    pod_uid: NonEmptyString
    container: NonEmptyString
    reason: NonEmptyString
    exit_code: int = Field(ge=0, strict=True)
    finished_at: UtcDatetime
    observed_at: UtcDatetime
    current_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_termination_time(self) -> ContainerTerminationContext:
        if self.finished_at > self.observed_at:
            raise ValueError("termination must not occur after observation")
        return self


class ResourceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source: Literal["vpa", "azure-advisor", "kubecost"]
    source_version: NonEmptyString
    recommendation_id: NonEmptyString
    observed_at: UtcDatetime | None = None
    collected_at: UtcDatetime | None = None
    dimension: Literal["cpu-request", "memory-request"]
    cluster_resource_id: NonEmptyString
    namespace: NonEmptyString
    workload_uid: NonEmptyString
    container: NonEmptyString
    current_value: float = Field(gt=0)
    recommended_value: float = Field(gt=0)
    unit: Literal["mCPU", "MiB"]
    reference: NonEmptyString
    limitations: list[NonEmptyString] = Field(min_length=1)

    @property
    def has_characterized_source(self) -> bool:
        return self.source_version in CANDIDATE_PRODUCER_VERSIONS.get(self.source, frozenset())

    @model_validator(mode="after")
    def validate_dimension(self) -> ResourceCandidate:
        expected = "mCPU" if self.dimension == "cpu-request" else "MiB"
        if self.unit != expected:
            raise ValueError("candidate unit must match its resource dimension")
        if self.recommended_value >= self.current_value:
            raise ValueError("resource candidate must be a strict reduction")
        return self


class WorkloadSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    uid: str | None = None
    namespace: str
    replicas: int = Field(ge=0)
    priority_class: str | None = None
    disruption_budget_present: bool = False
    qos_class: QosClass | None = None
    autoscaling: AutoscalingState = Field(default_factory=AutoscalingState)
    autoscaler_configuration: WorkloadAutoscalerConfiguration | None = None
    hpa_replica_history: HpaReplicaHistory | None = None
    safety_policy: WorkloadSafetyPolicy | None = None
    resource_candidates: list[ResourceCandidate] = Field(default_factory=list)
    pod_memory_accounting: list[PodMemoryAccounting] = Field(default_factory=list)
    termination_context: list[ContainerTerminationContext] = Field(default_factory=list)
    termination_issues: list[NonEmptyString] = Field(default_factory=list)
    startup_history: list[StartupHistoryEvidence] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    eviction_events: int | None = Field(default=None, ge=0)
    eviction_quality: MetricQuality | None = None
    memory_admission_observed: bool = Field(default=False, strict=True)
    memory_admission_minimum_mib: float | None = Field(default=None, ge=0)
    memory_admission_maximum_mib: float | None = Field(default=None, ge=0)
    memory_admission_limit_request_ratio: float | None = Field(default=None, gt=0)
    memory_admission_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    memory_admission_issues: list[NonEmptyString] = Field(default_factory=list)
    containers: list[ContainerSnapshot]
    labels: dict[str, str] = Field(default_factory=dict)


class NodePoolSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: str
    resource_id: str | None = None
    vm_size: str
    mode: str = "User"
    spot: bool = False
    nap_managed: bool = False
    autoscaling_enabled: bool = False
    node_count: int = Field(ge=0)
    min_count: int | None = Field(default=None, ge=0)
    max_count: int | None = Field(default=None, ge=0)
    allocatable_cpu_mcores: float = Field(ge=0)
    allocatable_memory_mib: float = Field(ge=0)
    usage_cpu_p95_mcores: float | None = Field(default=None, ge=0)
    usage_memory_p95_mib: float | None = Field(default=None, ge=0)
    monthly_cost: float | None = Field(default=None, ge=0)
    currency: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    metric_quality: dict[str, MetricQuality] = Field(default_factory=dict)


SchedulingConstraint = Literal[
    "node_selector",
    "required_node_affinity",
    "preferred_node_affinity",
    "required_pod_affinity",
    "preferred_pod_affinity",
    "required_pod_anti_affinity",
    "preferred_pod_anti_affinity",
    "hard_topology_spread",
    "soft_topology_spread",
    "tolerations",
    "persistent_volume_claims",
    "local_emptydir_volumes",
    "priority_class",
    "runtime_class",
    "custom_scheduler",
    "init_containers",
    "pod_overhead",
    "pod_resource_budget",
]


class SchedulingPodEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pod_uid: NonEmptyString
    pod_name: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: str | None = None
    workload_uid: str | None = None
    workload_name: str | None = None
    workload_kind: str | None = None
    workload_replicas: int | None = Field(default=None, ge=0, strict=True)
    constraints: dict[SchedulingConstraint, Annotated[int, Field(ge=1, strict=True)]]
    container_probes: list[ContainerProbeEvidence] = Field(default_factory=list)
    topology_spread: list[TopologySpreadEvidence] = Field(default_factory=list)
    namespace_pdb_candidates: list[NonEmptyString] = Field(default_factory=list)
    unobserved_fields: list[NonEmptyString] = Field(default_factory=list)
    issues: list[NonEmptyString] = Field(default_factory=list)
    node_uid: NonEmptyString | None = None
    resource_phase: Literal["Pending", "Running", "Succeeded", "Failed", "Unknown"] | None = None
    effective_cpu_request_mcpu: float | None = Field(default=None, ge=0, strict=True)
    effective_memory_request_mib: float | None = Field(default=None, ge=0, strict=True)
    resource_accounting_issues: list[NonEmptyString] = Field(default_factory=list)


class ContainerProbeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container: NonEmptyString
    liveness_probe: bool
    readiness_probe: bool
    startup_probe: bool


class TopologySpreadEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_skew: int = Field(gt=0, strict=True)
    topology_key: NonEmptyString
    when_unsatisfiable: Literal["DoNotSchedule", "ScheduleAnyway"]
    min_domains: int | None = Field(default=None, gt=0, strict=True)


PdbAvailability = Annotated[int, Field(ge=0, strict=True)] | NonEmptyString


class PodDisruptionBudgetEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: NonEmptyString
    name: NonEmptyString
    namespace: NonEmptyString
    min_available: PdbAvailability | None = None
    max_unavailable: PdbAvailability | None = None
    disruptions_allowed: int | None = Field(default=None, ge=0, strict=True)
    expected_pods: int | None = Field(default=None, ge=0, strict=True)
    namespace_uid: NonEmptyString | None = None
    selector_match_status: Literal["complete", "partial", "unknown"] = "unknown"
    selector_matched_pod_uids: list[NonEmptyString] | None = None
    selector_unmatched_pod_uids: list[NonEmptyString] | None = None
    selector_unknown_pod_uids: list[NonEmptyString] | None = None
    selector_issues: list[NonEmptyString] = Field(default_factory=list)
    disruption_feasibility: Literal["unknown"] = "unknown"
    issues: list[NonEmptyString] = Field(default_factory=list)


class DaemonSetPodOverhead(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pod_uid: NonEmptyString
    daemonset_uid: NonEmptyString
    daemonset_name: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: NonEmptyString | None = None
    node_uid: NonEmptyString | None = None
    cpu_request_mcpu: float | None = Field(default=None, ge=0, strict=True)
    memory_request_mib: float | None = Field(default=None, ge=0, strict=True)
    allocatable_cpu_mcpu: float | None = Field(default=None, gt=0, strict=True)
    allocatable_memory_mib: float | None = Field(default=None, gt=0, strict=True)
    issues: list[NonEmptyString] = Field(default_factory=list)


class DaemonSetCoverageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daemonset_uid: NonEmptyString
    daemonset_name: NonEmptyString
    namespace: NonEmptyString
    namespace_uid: NonEmptyString | None = None
    desired_number_scheduled: int | None = Field(default=None, ge=0, strict=True)
    number_ready: int | None = Field(default=None, ge=0, strict=True)
    observed_nonterminal_pod_count: int | None = Field(default=None, ge=0, strict=True)
    observed_pod_uids: list[NonEmptyString] | None = None
    observed_node_uids: list[NonEmptyString] | None = None
    duplicate_node_uids: list[NonEmptyString] = Field(default_factory=list)
    desired_minus_observed_nodes: int | None = Field(default=None, strict=True)
    desired_node_membership: Literal["unknown"] = "unknown"
    controller_status_binding: Literal["generation_unverified"] = "generation_unverified"
    disruption_feasibility: Literal["unknown"] = "unknown"
    status_issues: list[NonEmptyString] = Field(default_factory=list)
    observation_issues: list[NonEmptyString] = Field(default_factory=list)


class NodeResourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    node_uid: NonEmptyString
    node_name: NonEmptyString
    capacity_cpu_mcpu: float | None = Field(default=None, ge=0, strict=True)
    capacity_memory_mib: float | None = Field(default=None, ge=0, strict=True)
    allocatable_cpu_mcpu: float | None = Field(default=None, ge=0, strict=True)
    allocatable_memory_mib: float | None = Field(default=None, ge=0, strict=True)
    issues: list[NonEmptyString] = Field(default_factory=list)


class SchedulingInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString | None
    observed_at: UtcDatetime
    pods: list[SchedulingPodEvidence]
    pdbs: list[PodDisruptionBudgetEvidence] = Field(default_factory=list)
    tainted_node_uids: list[NonEmptyString] = Field(default_factory=list)
    cordoned_node_uids: list[NonEmptyString] = Field(default_factory=list)
    daemonset_uids: list[NonEmptyString] = Field(default_factory=list)
    daemonset_overhead_observed: bool = False
    daemonset_overhead: list[DaemonSetPodOverhead] = Field(default_factory=list)
    daemonset_overhead_issues: list[NonEmptyString] = Field(default_factory=list)
    daemonset_coverage: list[DaemonSetCoverageEvidence] = Field(default_factory=list)
    node_resources: list[NodeResourceEvidence] = Field(default_factory=list)
    resource_accounting_observed: bool = False
    unobserved_context: list[NonEmptyString] = Field(default_factory=list)
    issues: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pod_identities(self) -> SchedulingInventory:
        uids = [pod.pod_uid for pod in self.pods]
        if len(set(uids)) != len(uids):
            raise ValueError("Scheduling Pod identities must be distinct")
        names = Counter((pod.namespace, pod.pod_name) for pod in self.pods)
        for pod in self.pods:
            if (
                names[pod.namespace, pod.pod_name] > 1
                and "ambiguous_scheduling_identity" not in pod.issues
            ):
                pod.issues.append("ambiguous_scheduling_identity")
        pdb_uids = [pdb.uid for pdb in self.pdbs]
        if len(set(pdb_uids)) != len(pdb_uids):
            raise ValueError("Scheduling PDB identities must be distinct")
        daemonset_uids = [item.daemonset_uid for item in self.daemonset_coverage]
        if len(set(daemonset_uids)) != len(daemonset_uids):
            raise ValueError("Scheduling DaemonSet coverage identities must be distinct")
        return self


class PoolIntentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_resource_id: NonEmptyString
    pool_resource_id: NonEmptyString
    owner: Annotated[str, Field(min_length=1, pattern=r"\S")]
    classification: Literal["specialized", "intentionally-reserved"]
    reference: Annotated[str, Field(min_length=1, pattern=r"\S")]


class CapacityPoolEvidence(AzureNodePoolInventory):
    intent: PoolIntentBinding | None = None


class NapManagedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_uid: NonEmptyString
    nodeclaim_uid: NonEmptyString
    nodepool_uid: NonEmptyString


class NapDisruptionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    nodes: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    reasons: list[Literal["Empty", "Underutilized", "Drifted"]] | None = Field(
        default=None, max_length=3
    )
    schedule: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    duration: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    active: Literal["unknown"] = "unknown"
    effectiveness: Literal["not_calculated"] = "not_calculated"
    issues: list[
        Literal[
            "invalid_budget_nodes",
            "unknown_budget_reasons",
            "unsupported_budget_reasons",
            "invalid_budget_schedule",
            "invalid_budget_duration",
            "unpaired_budget_schedule_duration",
        ]
    ] = Field(default_factory=list)


class NapZoneRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: Literal["In", "NotIn", "Exists", "DoesNotExist"]
    values: list[Annotated[str, Field(min_length=1, max_length=63)]] = Field(max_length=100)
    min_values: int | None = Field(default=None, gt=0, le=100, strict=True)


class NapTopologyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_requirements: list[NapZoneRequirement] | None = Field(default=None, max_length=100)
    requirement_status: Literal["observed", "partial", "unknown"] = "unknown"
    requirement_issues: list[NonEmptyString] = Field(default_factory=list)
    observed_zone_nodes: dict[str, list[NonEmptyString]] | None = None
    unknown_zone_node_uids: list[NonEmptyString] | None = None
    observation_status: Literal["current-bound-only", "unknown"] = "unknown"
    observation_issues: list[NonEmptyString] = Field(default_factory=list)
    domain_effectiveness: Literal["not_calculated"] = "not_calculated"
    placement_feasibility: Literal["unknown"] = "unknown"


class NapPoolEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: NonEmptyString
    name: NonEmptyString
    nodeclass_uid: str | None = None
    supply_mode: Literal["static", "dynamic", "unknown"]
    static_replicas: int | None = Field(default=None, ge=0, strict=True)
    requirement_count: int | None = Field(default=None, ge=0)
    taint_count: int | None = Field(default=None, ge=0)
    startup_taint_count: int | None = Field(default=None, ge=0)
    consolidation_policy: str | None = None
    consolidate_after: str | None = None
    disruption_budget_count: int | None = Field(default=None, ge=0)
    disruption_budgets: list[NapDisruptionBudget] | None = Field(default=None, max_length=1000)
    zero_node_disruption_budget_configured: bool | None = None
    limits_observed: bool = False
    topology: NapTopologyContext = Field(default_factory=NapTopologyContext)

    @model_validator(mode="after")
    def validate_supply_mode(self) -> NapPoolEvidence:
        if (self.supply_mode == "static") != (self.static_replicas is not None):
            raise ValueError("static NAP supply requires an explicit replica count")
        return self


class CapacityInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_resource_id: NonEmptyString
    cluster_uid: NonEmptyString | None
    azure_observed_at: UtcDatetime
    kubernetes_observed_at: UtcDatetime | None
    provisioning_mode: str | None
    pools: list[CapacityPoolEvidence]
    nap_api_status: dict[str, Literal["available", "absent", "unsupported", "unknown"]]
    nap_pools: list[NapPoolEvidence] = Field(default_factory=list)
    nap_managed_nodes: list[NapManagedNode] = Field(default_factory=list)
    issues: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_nap_supply(self) -> CapacityInventory:
        nodes = [item.node_uid for item in self.nap_managed_nodes]
        claims = [item.nodeclaim_uid for item in self.nap_managed_nodes]
        pools = {item.uid for item in self.nap_pools}
        if (
            len(set(nodes)) != len(nodes)
            or len(set(claims)) != len(claims)
            or any(item.nodepool_uid not in pools for item in self.nap_managed_nodes)
            or (self.nap_managed_nodes and self.provisioning_mode != "Auto")
        ):
            raise ValueError("NAP supply requires distinct exact identities and Auto mode")
        return self


class ClusterSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    name: str
    uid: str | None = None
    subscription_id: str
    resource_group: str
    location: str
    kubernetes_version: str | None = None
    environment: str | None = None
    fleet_id: str | None = None
    sku_tier: str | None = None
    cost_analysis_enabled: bool | None = None
    managed_prometheus_enabled: bool | None = None
    node_pools: list[NodePoolSnapshot]
    workloads: list[WorkloadSnapshot]
    scheduling: SchedulingInventory | None = None
    capacity: CapacityInventory | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class CapabilityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: NonEmptyString
    status: Literal["available", "unavailable", "unknown", "unsupported"]
    reason_codes: list[NonEmptyString] = Field(min_length=1)


class SourceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: NonEmptyString
    mode: Literal["baseline", "guarded"]
    source: NonEmptyString
    cluster_resource_id: NonEmptyString
    observed_at: UtcDatetime
    source_profile: SourceDefinition
    status: Literal["available", "unavailable", "unknown", "unsupported"]
    checks: list[CapabilityCheck] = Field(min_length=1)
    notice: Literal["Metric capability is not source attestation or safe-change approval."] = (
        "Metric capability is not source attestation or safe-change approval."
    )

    @model_validator(mode="after")
    def validate_status(self) -> SourceCapability:
        statuses = {check.status for check in self.checks}
        expected = next(
            (value for value in ("unsupported", "unavailable", "unknown") if value in statuses),
            "available",
        )
        if self.status != expected:
            raise ValueError("Capability status must reflect all checks")
        return self


class SourceCapabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["offline"] = "offline"
    generated_at: UtcDatetime
    capabilities: list[SourceCapability]


class MetricQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_queries: int = Field(ge=0)
    unique_queries: int = Field(ge=0)
    requests: int = Field(ge=0)
    expected_evaluations: int = Field(ge=0)
    maximum_series: int = Field(ge=1)


class ExistingToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["azure-advisor"]
    source_version: NonEmptyString
    recommendation_id: NonEmptyString
    observed_at: UtcDatetime
    cluster_resource_id: NonEmptyString
    finding: Literal["enable-vpa", "use-aks-cost-analysis", "tune-cluster-autoscaler"]
    reference: NonEmptyString
    limitations: list[NonEmptyString] = Field(min_length=1)


class FleetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    generated_at: UtcDatetime
    metric_window: MetricWindow
    source: str
    clusters: list[ClusterSnapshot]
    collection_manifest: CollectionManifest | None = None
    source_capabilities: list[SourceCapability] = Field(default_factory=list)
    existing_tool_observations: list[ExistingToolObservation] = Field(default_factory=list)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float | int | str | bool | None
    unit: str | None = None
    source: str


class ResourceRequests(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    cpu_mcores: float | None = Field(default=None, gt=0)
    memory_mib: float | None = Field(default=None, gt=0)


class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    memory_mib: float = Field(gt=0)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rule_id: str
    rule_version: str
    title: str
    summary: str
    resource_id: str
    cluster_name: str
    namespace: str | None = None
    workload: str | None = None
    severity: Severity
    confidence: Confidence
    category: str
    existing_tool_observations: list[ExistingToolObservation] = Field(default_factory=list)
    estimated_monthly_savings: float | None = Field(default=None, ge=0)
    currency: str | None = None
    evidence: list[Evidence]
    prerequisites: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)
    owner: str | None = None
    current_requests: ResourceRequests | None = None
    proposed_requests: ResourceRequests | None = None
    current_limits: ResourceLimits | None = None
    proposed_limits: ResourceLimits | None = None
    current_replica_floor: int | None = Field(default=None, ge=1, strict=True)
    proposed_replica_floor: int | None = Field(default=None, ge=1, strict=True)
    resource_candidate: ResourceCandidate | None = None
    proposal_source: Literal["existing-tool-candidate", "accelerator-derived"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_proposal_provenance(self) -> Recommendation:
        has_proposal = any(
            value is not None
            for value in (
                self.proposed_requests,
                self.proposed_limits,
                self.proposed_replica_floor,
            )
        )
        if has_proposal != (self.proposal_source is not None):
            raise ValueError("numeric proposals require explicit proposal provenance")
        if self.proposal_source == "existing-tool-candidate":
            if self.resource_candidate is None or self.proposed_requests is None:
                raise ValueError("existing-tool proposals require their resource candidate")
            candidate = self.resource_candidate
            proposed = (
                self.proposed_requests.cpu_mcores
                if candidate.dimension == "cpu-request"
                else self.proposed_requests.memory_mib
            )
            if proposed != candidate.recommended_value:
                raise ValueError("proposal must preserve the validated upstream candidate value")
        return self

    @model_validator(mode="after")
    def validate_replica_proposal(self) -> Recommendation:
        if (self.current_replica_floor is None) != (self.proposed_replica_floor is None):
            raise ValueError("replica floor proposals require both current and proposed values")
        if self.current_replica_floor is not None and self.proposed_replica_floor is not None:
            if self.proposed_replica_floor >= self.current_replica_floor:
                raise ValueError("replica floor proposals must be strict reductions")
            if self.current_requests is not None or self.proposed_requests is not None:
                raise ValueError("replica proposals cannot also change resource requests")
            if self.estimated_monthly_savings is not None:
                raise ValueError("replica floor proposals do not establish financial savings")
        return self

    @model_validator(mode="after")
    def validate_limit_proposal(self) -> Recommendation:
        if self.proposed_limits is not None:
            if (
                self.current_limits is None
                or self.proposed_limits.memory_mib >= self.current_limits.memory_mib
            ):
                raise ValueError("memory limit proposals require a strictly lower positive limit")
            if self.proposed_requests is not None or self.proposed_replica_floor is not None:
                raise ValueError("memory limits must be proposed one dimension at a time")
            if self.estimated_monthly_savings is not None:
                raise ValueError("memory limit proposals cannot establish financial savings")
        return self


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clusters_analyzed: int
    node_pools_analyzed: int
    workloads_analyzed: int
    pack_subject_counts: dict[NonEmptyString, Annotated[int, Field(ge=0, strict=True)]]
    recommendations: int
    high_or_critical: int
    blocked_recommendations: int = 0
    data_quality_warnings: list[str] = Field(default_factory=list)


class BlockedRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rule_id: str
    rule_version: str
    resource_id: str
    cluster_name: str
    namespace: str | None = None
    workload: str | None = None
    reason_codes: list[NonEmptyString] = Field(min_length=1)
    resource_candidate: ResourceCandidate | None = None


class AnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    mode: AssessmentMode
    pack_provenance: list[PackProvenance]
    generated_at: UtcDatetime
    observation_window: MetricWindow
    summary: AnalysisSummary
    recommendations: list[Recommendation]
    blocked_recommendations: list[BlockedRecommendation] = Field(default_factory=list)
    snapshot_digest: str | None = None
    configuration_digest: str | None = None
    source_capabilities: list[SourceCapability] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_baseline(self) -> AnalysisReport:
        if self.mode == "baseline" and any(
            item.proposed_requests is not None
            or item.proposed_limits is not None
            or item.proposed_replica_floor is not None
            for item in self.recommendations
        ):
            raise ValueError("baseline reports cannot contain numeric proposals")
        if len({item.id for item in self.pack_provenance}) != len(self.pack_provenance):
            raise ValueError("report pack provenance must be distinct")
        return self


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: NonEmptyString
    status: Literal["pass", "blocked", "unknown"]
    scope: NonEmptyString
    message: NonEmptyString


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["offline"] = "offline"
    generated_at: UtcDatetime
    status: Literal["ready", "blocked", "unknown"]
    requested_subscriptions: int = Field(ge=1)
    requested_clusters: int = Field(ge=0)
    configuration_digest: str
    snapshot_digest: str | None = None
    checks: list[ReadinessCheck] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_readiness_status(self) -> ReadinessReport:
        expected = "ready"
        if any(check.status == "blocked" for check in self.checks):
            expected = "blocked"
        elif any(check.status == "unknown" for check in self.checks):
            expected = "unknown"
        if self.status != expected:
            raise ValueError("readiness status must reflect every check")
        identities = {(check.scope, check.code) for check in self.checks}
        if len(identities) != len(self.checks):
            raise ValueError("readiness checks must have unique scope and code pairs")
        return self


class KubernetesObjectMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    api_version: NonEmptyString
    kind: NonEmptyString
    name: NonEmptyString
    namespace: str | None = None
    uid: NonEmptyString
    labels: dict[str, str] = Field(default_factory=dict)
    owner_references: list[dict[str, JsonValue]] = Field(default_factory=list)
    spec: dict[str, JsonValue] = Field(default_factory=dict)
    status: dict[str, JsonValue] = Field(default_factory=dict)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class KubernetesNodeIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_uid: NonEmptyString
    provider_id: str | None = None
    azure_resource_id: str | None = None
    node_pool_resource_id: str | None = None
    state: Literal["matched", "unknown", "mismatch"]


class KubernetesMetadataSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    source: Literal["kubernetes-metadata"] = "kubernetes-metadata"
    tenant_id: NonEmptyString
    cluster_resource_id: NonEmptyString
    cluster_uid: str | None = None
    generated_at: UtcDatetime
    collection: CollectorResult
    api_availability: dict[str, Literal["available", "absent", "unsupported"]]
    resources: list[KubernetesObjectMetadata]
    nodes: list[KubernetesNodeIdentity] = Field(default_factory=list)
    workload_bindings: dict[str, str | None] = Field(default_factory=dict)
    resource_versions: dict[str, str] = Field(default_factory=dict)


class MetricEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "container",
        "workload",
        "workload_container",
        "hpa",
        "node",
        "node_pool",
        "unresolved_container",
    ] = "container"
    cluster_resource_id: NonEmptyString
    namespace: str | None = None
    pod: NonEmptyString | None = None
    workload_kind: str | None = None
    workload: str | None = None
    workload_uid: str | None = None
    hpa_uid: NonEmptyString | None = None
    pod_uid: str | None = None
    container: str | None = None
    node_resource_id: str | None = None
    node_uid: str | None = None
    node_pool_resource_id: str | None = None
    membership_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> MetricEntity:
        required = (
            [self.namespace, self.pod, self.container]
            if self.kind == "unresolved_container"
            else [
                self.namespace,
                self.workload_kind,
                self.workload,
                self.workload_uid,
                self.pod_uid,
                self.container,
            ]
            if self.kind == "container"
            else [
                self.namespace,
                self.workload_kind,
                self.workload,
                self.workload_uid,
                self.container,
                self.membership_digest,
            ]
            if self.kind == "workload_container"
            else [
                self.namespace,
                self.workload_kind,
                self.workload,
                self.workload_uid,
                self.hpa_uid,
            ]
            if self.kind == "hpa"
            else [self.namespace, self.workload_kind, self.workload, self.workload_uid]
            if self.kind == "workload"
            else [self.node_resource_id, self.node_uid]
            if self.kind == "node"
            else [self.node_pool_resource_id]
        )
        if not all(required):
            raise ValueError("metric entity requires explicit resource and UID identity")
        if self.kind == "unresolved_container" and any(
            value is not None
            for value in (
                self.workload_uid,
                self.workload,
                self.workload_kind,
                self.pod_uid,
                self.hpa_uid,
                self.membership_digest,
                self.node_uid,
                self.node_resource_id,
                self.node_pool_resource_id,
            )
        ):
            raise ValueError("Name-only series cannot claim historical or workload identity")
        if self.kind != "hpa" and self.hpa_uid is not None:
            raise ValueError("HPA identity belongs only to HPA history entities")
        if self.kind == "hpa" and any(
            item is not None
            for item in [
                self.pod_uid,
                self.container,
                self.membership_digest,
                self.node_uid,
                self.node_resource_id,
                self.node_pool_resource_id,
            ]
        ):
            raise ValueError("HPA history cannot claim Pod, aggregate or node identity")
        if self.kind == "workload_container" and self.pod_uid is not None:
            raise ValueError(
                "workload aggregates use membership identity, not a fabricated Pod UID"
            )
        return self


class MetricObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    entity: MetricEntity
    metric: NonEmptyString
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    total: float | None = None
    latest_sample_at: UtcDatetime | None = None
    quality: MetricQuality
    issues: list[str] = Field(default_factory=list)


class PrometheusMetricsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    source: Literal["prometheus"] = "prometheus"
    query_version: Literal["1.0"] = "1.0"
    tenant_id: NonEmptyString
    source_name: NonEmptyString
    generated_at: UtcDatetime
    query_start: UtcDatetime
    query_end: UtcDatetime
    step_seconds: int = Field(gt=0)
    collection: CollectorResult
    observations: list[MetricObservation]
    source_profile: SourceDefinition | None = None
    query_plan: MetricQueryPlan | None = None

    @model_validator(mode="after")
    def validate_query_range(self) -> PrometheusMetricsSnapshot:
        if self.query_end <= self.query_start or self.query_end > self.generated_at:
            raise ValueError("metrics query range must be ordered and no later than collection")
        for observation in self.observations:
            window = observation.quality.window
            if (
                window.start != self.query_start
                or window.end != self.query_end
                or observation.quality.step_seconds != self.step_seconds
            ):
                raise ValueError("metric quality must align with the requested range and step")
            if observation.entity.cluster_resource_id not in self.collection.requested_scope:
                raise ValueError("metric observation is outside the collection scope")
        return self
