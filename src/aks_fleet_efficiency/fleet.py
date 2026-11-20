from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from hashlib import sha256
from math import fsum, isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from aks_fleet_efficiency.assessment import OfflineAssessment
from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.catalog.models import AssessmentMode
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.fleet_context import (
    FleetContext,
    FleetContextReview,
    review_fleet_context,
)
from aks_fleet_efficiency.models import (
    ClusterSnapshot,
    MetricWindow,
    SchedulingInventory,
    SourceCapability,
    UtcDatetime,
)
from aks_fleet_efficiency.node_history import (
    HistoricalNodeEvidence,
    HistoricalNodeReview,
    _finite_percentile,
    _finite_sum,
    review_node_history,
)
from aks_fleet_efficiency.rules.engine import _collection_reasons, analyze

PeerGroup = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128),
]
CapabilityStatus = Literal["available", "unavailable", "unknown", "unsupported"]
InventoryStatus = Literal["available", "partial", "unknown"]
SupplyClass = Literal["fixed", "cas", "nap_static", "nap_dynamic", "unknown"]
ArmPoolMarket = Literal["spot", "regular", "unknown"]
ReviewOwnerStatus = Literal["declared", "unknown"]
Count = Annotated[int, Field(ge=0, strict=True)]
ComparabilityReason = Literal[
    "observation_windows_differ",
    "analysis_modes_differ",
    "pack_definitions_differ",
    "configurations_differ",
]


class FleetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FleetAssessment(FleetModel):
    peer_group: PeerGroup
    assessment: OfflineAssessment
    analysis_config: AdvisorConfig
    node_history: list[HistoricalNodeEvidence] = Field(
        default_factory=list, max_length=1000, exclude_if=lambda value: not value
    )
    external_context: list[FleetContext] = Field(
        default_factory=list, max_length=1000, exclude_if=lambda value: not value
    )


class FleetArmPoolMarket(FleetModel):
    status: InventoryStatus = "unknown"
    pool_counts: dict[ArmPoolMarket, Count] | None = None
    observed_at: UtcDatetime | None = None
    reason_codes: list[str] = Field(default_factory=lambda: ["missing_capacity_inventory"])
    unit: Literal["observed ARM pool priority; not Nodes, NAP policy or historical fallback"] = (
        "observed ARM pool priority; not Nodes, NAP policy or historical fallback"
    )


class FleetSupplyInventory(FleetModel):
    status: InventoryStatus
    pool_counts: dict[SupplyClass, Count] | None = None
    azure_observed_at: UtcDatetime | None = None
    kubernetes_observed_at: UtcDatetime | None = None
    reason_codes: list[str] = Field(default_factory=list)
    arm_pool_market: FleetArmPoolMarket = Field(default_factory=FleetArmPoolMarket)
    unit: Literal["observed current pool objects; not nodes or workload placement"] = (
        "observed current pool objects; not nodes or workload placement"
    )


class FleetWorkloadSupply(FleetModel):
    status: InventoryStatus = "unknown"
    pod_counts: dict[SupplyClass, Count] | None = None
    observed_at: UtcDatetime | None = None
    reason_codes: list[str] = Field(default_factory=list)
    unit: Literal[
        "listed current Pods by exact observed supply; not placement, Node market or history"
    ] = "listed current Pods by exact observed supply; not placement, Node market or history"


class FleetWorkloadInvestigation(FleetModel):
    namespace: str
    namespace_uid: str
    workload_uid: str
    workload_kind: str
    workload_name: str
    review_owner_status: ReviewOwnerStatus = "unknown"
    reason_codes: list[str] = Field(default_factory=list)
    observed_supply: FleetWorkloadSupply = Field(default_factory=FleetWorkloadSupply)
    scope_notice: Literal["review declaration only; not business ownership or change approval"] = (
        "review declaration only; not business ownership or change approval"
    )


class FleetNamespaceWorkloads(FleetModel):
    namespace: str
    namespace_uid: str | None
    workload_counts: dict[str, Count]
    observed_pods: Count
    unresolved_pods: Count


class FleetWorkloadInventory(FleetModel):
    status: InventoryStatus
    workload_counts: dict[str, Count] | None = None
    observed_pods: Count | None = None
    unresolved_pods: Count | None = None
    namespace_distribution: list[FleetNamespaceWorkloads] | None = None
    review_owner_status_counts: dict[ReviewOwnerStatus, Count] | None = None
    workload_investigations: list[FleetWorkloadInvestigation] | None = None
    observed_at: UtcDatetime | None = None
    reason_codes: list[str] = Field(default_factory=list)
    unit: Literal["distinct UID-bound current owners with listed Pods; not ready replicas"] = (
        "distinct UID-bound current owners with listed Pods; not ready replicas"
    )


class FleetResourceAmount(FleetModel):
    status: InventoryStatus = "unknown"
    cpu_mcpu: float | None = Field(default=None, ge=0, strict=True)
    memory_mib: float | None = Field(default=None, ge=0, strict=True)
    reason_codes: list[str] = Field(default_factory=list)
    cpu_unit: Literal["mCPU"] = "mCPU"
    memory_unit: Literal["MiB"] = "MiB"


GapReason = Literal[
    "unqualified_inventory",
    "invalid_node_accounting",
    "incomplete_node_accounting",
    "incomplete_pod_accounting",
    "namespace_scope_mismatch",
]


class FleetGapDimension(FleetModel):
    value: float | None = None
    nodes_expected: Count | None = None
    nodes_covered: Count | None = None
    pods_expected: Count | None = None
    pods_covered: Count | None = None
    reason: GapReason | None = "unqualified_inventory"


class FleetGapPair(FleetModel):
    cpu: FleetGapDimension = Field(default_factory=FleetGapDimension)
    memory: FleetGapDimension = Field(default_factory=FleetGapDimension)
    cpu_unit: Literal["mCPU"] = "mCPU"
    memory_unit: Literal["MiB"] = "MiB"


class FleetCurrentGaps(FleetModel):
    capacity_minus_allocatable: FleetGapPair = Field(default_factory=FleetGapPair)
    allocatable_minus_requests: FleetGapPair = Field(default_factory=FleetGapPair)
    requests_minus_usage: Literal["aligned_cluster_usage_unavailable"] = (
        "aligned_cluster_usage_unavailable"
    )


class FleetResourceEnvelope(FleetModel):
    node_capacity: FleetResourceAmount = Field(default_factory=FleetResourceAmount)
    allocatable: FleetResourceAmount = Field(default_factory=FleetResourceAmount)
    requested: FleetResourceAmount = Field(default_factory=FleetResourceAmount)
    observed_usage: FleetResourceAmount = Field(
        default_factory=lambda: FleetResourceAmount(
            reason_codes=["aligned_cluster_usage_unavailable"]
        )
    )
    observation_times: list[UtcDatetime] = Field(default_factory=list)
    current_gaps: FleetCurrentGaps | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    current_only: Literal[True] = True
    scope_notice: Literal[
        "all listed Nodes; included nonterminal Pod requests; not free or movable capacity"
    ] = "all listed Nodes; included nonterminal Pod requests; not free or movable capacity"


class FleetClusterInsight(FleetModel):
    tenant_id: str
    cluster_resource_id: str
    cluster_uid: str
    cluster_name: str
    subscription_id: str
    location: str
    environment: str | None = None
    peer_group: PeerGroup
    assessment_status: Literal["complete", "partial"]
    mode: AssessmentMode
    generated_at: UtcDatetime
    observation_window: MetricWindow
    recommendations: int = Field(ge=0)
    blocked_recommendations: int = Field(ge=0)
    high_or_critical: int = Field(ge=0)
    source_capabilities: list[SourceCapability]
    source_status_counts: dict[CapabilityStatus, int]
    data_quality_warnings: list[str]
    excluded_namespaces: list[str]
    supply_inventory: FleetSupplyInventory
    workload_inventory: FleetWorkloadInventory
    rule_counts: dict[str, Count]
    category_counts: dict[str, Count]
    blocked_reason_counts: dict[str, Count]
    resource_envelope: FleetResourceEnvelope

    historical_usage: HistoricalNodeReview | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    external_context: FleetContextReview | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class HistoricalPeerUsage(FleetModel):
    cluster_resource_ids: list[str]
    window_start: UtcDatetime | None = None
    window_end: UtcDatetime | None = None
    step_seconds: int | None = None
    cpu_p95_mcpu: float | None = Field(default=None, ge=0)
    memory_p99_working_set_mib: float | None = Field(default=None, ge=0)
    cpu_gaps: list[str]
    memory_gaps: list[str]
    source_admission: Literal["unverified_saved_contributions"] = "unverified_saved_contributions"


class FleetPeerGroupInsight(FleetModel):
    peer_group: PeerGroup
    clusters: Count
    cluster_resource_ids: list[str]
    comparable: bool
    comparability_reasons: list[ComparabilityReason]
    recommendations: Count
    blocked_recommendations: Count
    high_or_critical: Count
    rule_counts: dict[str, Count]
    category_counts: dict[str, Count]
    blocked_reason_counts: dict[str, Count]
    source_status_counts: dict[CapabilityStatus, Count]
    inventory_status_counts: dict[
        Literal["supply", "workloads", "arm_pool_market"], dict[InventoryStatus, Count]
    ]
    supply_pool_counts: dict[SupplyClass, Count] | None
    arm_pool_market_counts: dict[ArmPoolMarket, Count] | None
    review_owner_status_counts: dict[ReviewOwnerStatus, Count] | None
    workload_counts: dict[str, Count] | None
    resource_envelope: FleetResourceEnvelope
    historical_usage: HistoricalPeerUsage | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class FleetInsightSummary(FleetModel):
    clusters: int = Field(ge=2)
    peer_groups: int = Field(ge=1)
    recommendations: int = Field(ge=0)
    blocked_recommendations: int = Field(ge=0)
    high_or_critical: int = Field(ge=0)
    estimated_monthly_savings: None = None


class FleetInsightReport(FleetModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: str
    generated_at: UtcDatetime
    comparable: bool
    comparability_reasons: list[ComparabilityReason]
    summary: FleetInsightSummary
    clusters: list[FleetClusterInsight] = Field(min_length=2, max_length=1000)
    rule_counts: dict[str, int]
    blocked_reason_counts: dict[str, int]
    category_counts: dict[str, Count]
    peer_groups: list[FleetPeerGroupInsight]


def _inventory_reasons(
    assessment: OfflineAssessment, cluster: ClusterSnapshot, config: AdvisorConfig
) -> list[str]:
    evaluated_at = assessment.report.generated_at
    maximum_age = config.thresholds.maximum_evidence_age_hours * 3600
    reasons = _collection_reasons(assessment.snapshot, cluster, False, evaluated_at, maximum_age)
    if assessment.snapshot.generated_at > evaluated_at:
        reasons.append("future_snapshot")
    elif (evaluated_at - assessment.snapshot.generated_at).total_seconds() > maximum_age:
        reasons.append("stale_snapshot")
    return reasons


def _clock_reasons(
    observed_at: datetime | None, assessment: OfflineAssessment, config: AdvisorConfig
) -> list[str]:
    if observed_at is None:
        return ["missing_inventory_time"]
    if (
        observed_at > assessment.report.generated_at
        or observed_at > assessment.snapshot.generated_at
    ):
        return ["future_inventory"]
    if (
        assessment.report.generated_at - observed_at
    ).total_seconds() > config.thresholds.maximum_evidence_age_hours * 3600:
        return ["stale_inventory"]
    return []


def _quantity_sum(values: list[float | None], reason: str) -> tuple[float | None, list[str]]:
    if any(value is None for value in values):
        return None, [reason]
    try:
        total = fsum(value for value in values if value is not None)
        if not isfinite(total):
            raise OverflowError("nonfinite resource total")
        return total, []
    except OverflowError:
        return None, ["nonfinite_resource_total"]


def _resource_amount(cpu: list[float | None], memory: list[float | None]) -> FleetResourceAmount:
    cpu_value, cpu_reasons = _quantity_sum(cpu, "incomplete_cpu_accounting")
    memory_value, memory_reasons = _quantity_sum(memory, "incomplete_memory_accounting")
    return FleetResourceAmount(
        status="available"
        if cpu_value is not None and memory_value is not None
        else "unknown"
        if cpu_value is None and memory_value is None
        else "partial",
        cpu_mcpu=cpu_value,
        memory_mib=memory_value,
        reason_codes=sorted(set(cpu_reasons + memory_reasons)),
    )


def _gap_dimension(
    envelope: FleetResourceEnvelope,
    inventory: SchedulingInventory,
    resource: Literal["cpu", "memory"],
    excluded_namespaces: list[str],
) -> tuple[FleetGapDimension, FleetGapDimension]:
    pairs = [
        (node.capacity_cpu_mcpu, node.allocatable_cpu_mcpu)
        if resource == "cpu"
        else (node.capacity_memory_mib, node.allocatable_memory_mib)
        for node in inventory.node_resources
    ]
    invalid = any(c is not None and a is not None and a > c for c, a in pairs)
    nodes = len(pairs)
    matched = sum(c is not None and a is not None and c >= a for c, a in pairs)
    allocatable_count = sum(a is not None and (c is None or c >= a) for c, a in pairs)
    capacity = (
        envelope.node_capacity.cpu_mcpu if resource == "cpu" else envelope.node_capacity.memory_mib
    )
    allocatable = (
        envelope.allocatable.cpu_mcpu if resource == "cpu" else envelope.allocatable.memory_mib
    )
    requested = envelope.requested.cpu_mcpu if resource == "cpu" else envelope.requested.memory_mib

    reservation = FleetGapDimension(nodes_expected=nodes, nodes_covered=matched, reason=None)
    unreserved = FleetGapDimension(
        nodes_expected=nodes, nodes_covered=allocatable_count, reason=None
    )
    pods = [pod for pod in inventory.pods if pod.resource_phase not in {"Succeeded", "Failed"}]
    unreserved.pods_expected = len(pods)
    unreserved.pods_covered = sum(
        pod.namespace not in excluded_namespaces
        and pod.resource_phase in {"Pending", "Running"}
        and "ambiguous_scheduling_identity" not in pod.issues
        and (
            pod.effective_cpu_request_mcpu
            if resource == "cpu"
            else pod.effective_memory_request_mib
        )
        is not None
        for pod in pods
    )
    if invalid:
        reservation.reason = unreserved.reason = "invalid_node_accounting"
        return reservation, unreserved

    if capacity is None or allocatable is None or matched != nodes:
        reservation.reason = "incomplete_node_accounting"
    else:
        reservation.value = capacity - allocatable

    if allocatable is None or allocatable_count != nodes:
        unreserved.reason = "incomplete_node_accounting"
    elif any(pod.namespace in excluded_namespaces for pod in pods):
        unreserved.reason = "namespace_scope_mismatch"
    elif requested is None or unreserved.pods_covered != unreserved.pods_expected:
        unreserved.reason = "incomplete_pod_accounting"
    else:
        unreserved.value = allocatable - requested
    return reservation, unreserved


def _resource_envelope(
    assessment: OfflineAssessment, cluster: ClusterSnapshot, config: AdvisorConfig
) -> FleetResourceEnvelope:
    inventory = cluster.scheduling
    result = FleetResourceEnvelope()
    reasons = _inventory_reasons(assessment, cluster, config)
    if inventory is None:
        reasons.append("missing_resource_inventory")
    else:
        result.observation_times = [inventory.observed_at]
        reasons.extend(_clock_reasons(inventory.observed_at, assessment, config))
        reasons.extend(inventory.issues)
        if (
            inventory.cluster_resource_id != cluster.resource_id
            or inventory.cluster_uid != cluster.uid
        ):
            reasons.append("scheduling_identity_mismatch")
        if not inventory.resource_accounting_observed:
            reasons.append("unobserved_resource_accounting")
    if reasons or inventory is None:
        for field in ["node_capacity", "allocatable", "requested"]:
            setattr(result, field, FleetResourceAmount(reason_codes=sorted(set(reasons))))
        result.current_gaps = FleetCurrentGaps()
        return result
    nodes = inventory.node_resources
    if len({node.node_uid for node in nodes}) != len(nodes) or len(
        {node.node_name for node in nodes}
    ) != len(nodes):
        result.node_capacity = FleetResourceAmount(
            reason_codes=["ambiguous_node_resource_identity"]
        )
        result.allocatable = FleetResourceAmount(reason_codes=["ambiguous_node_resource_identity"])
    else:
        result.node_capacity = _resource_amount(
            [node.capacity_cpu_mcpu for node in nodes], [node.capacity_memory_mib for node in nodes]
        )
        result.allocatable = _resource_amount(
            [node.allocatable_cpu_mcpu for node in nodes],
            [node.allocatable_memory_mib for node in nodes],
        )
    pods = [
        pod
        for pod in inventory.pods
        if pod.namespace not in config.excluded_namespaces
        and pod.resource_phase not in {"Succeeded", "Failed"}
    ]
    if any(
        pod.resource_phase not in {"Pending", "Running"}
        or "ambiguous_scheduling_identity" in pod.issues
        for pod in pods
    ):
        result.requested = FleetResourceAmount(reason_codes=["unknown_nonterminal_pod_accounting"])
    else:
        result.requested = _resource_amount(
            [pod.effective_cpu_request_mcpu for pod in pods],
            [pod.effective_memory_request_mib for pod in pods],
        )
    if "ambiguous_node_resource_identity" in result.allocatable.reason_codes:
        result.current_gaps = FleetCurrentGaps()
    else:
        cpu_reservation, cpu_unreserved = _gap_dimension(
            result, inventory, "cpu", config.excluded_namespaces
        )
        memory_reservation, memory_unreserved = _gap_dimension(
            result, inventory, "memory", config.excluded_namespaces
        )
        result.current_gaps = FleetCurrentGaps(
            capacity_minus_allocatable=FleetGapPair(cpu=cpu_reservation, memory=memory_reservation),
            allocatable_minus_requests=FleetGapPair(cpu=cpu_unreserved, memory=memory_unreserved),
        )
    return result


def _group_resource_envelope(
    members: list[FleetClusterInsight], comparable: bool
) -> FleetResourceEnvelope:
    result = FleetResourceEnvelope(
        observation_times=sorted(
            {time for member in members for time in member.resource_envelope.observation_times}
        )
    )
    for field in ["node_capacity", "allocatable", "requested"]:
        if not comparable:
            amount = FleetResourceAmount(reason_codes=["peer_group_not_comparable"])
        else:
            amounts = [getattr(member.resource_envelope, field) for member in members]
            amount = _resource_amount(
                [item.cpu_mcpu for item in amounts], [item.memory_mib for item in amounts]
            )
        setattr(result, field, amount)
    return result


def _supply_inventory(
    assessment: OfflineAssessment, cluster: ClusterSnapshot, config: AdvisorConfig
) -> FleetSupplyInventory:
    capacity = cluster.capacity
    if capacity is None:
        return FleetSupplyInventory(status="unknown", reason_codes=["missing_capacity_inventory"])
    result = FleetSupplyInventory(
        status="unknown",
        azure_observed_at=capacity.azure_observed_at,
        kubernetes_observed_at=capacity.kubernetes_observed_at,
    )
    reasons = _inventory_reasons(assessment, cluster, config)
    reasons.extend(_clock_reasons(capacity.azure_observed_at, assessment, config))
    reasons.extend(_clock_reasons(capacity.kubernetes_observed_at, assessment, config))
    if capacity.cluster_resource_id != cluster.resource_id or capacity.cluster_uid != cluster.uid:
        reasons.append("capacity_identity_mismatch")
    ids = [pool.resource_id for pool in capacity.pools]
    nap_ids = [pool.uid for pool in capacity.nap_pools]
    if len(set(ids)) != len(ids) or len(set(nap_ids)) != len(nap_ids):
        reasons.append("ambiguous_capacity_identity")
    if any(
        pool.resource_id != f"{cluster.resource_id}/agentPools/{pool.name}"
        for pool in capacity.pools
    ):
        reasons.append("capacity_pool_identity_mismatch")
    if reasons:
        result.reason_codes = sorted(set(reasons))
        result.arm_pool_market = FleetArmPoolMarket(
            observed_at=capacity.azure_observed_at,
            reason_codes=sorted(set(reasons)),
        )
        return result
    counts: Counter[SupplyClass] = Counter()
    market_counts: Counter[ArmPoolMarket] = Counter()
    for pool in capacity.pools:
        market_counts["unknown" if pool.spot is None else "spot" if pool.spot else "regular"] += 1
        counts[
            "unknown"
            if pool.autoscaling_enabled is None
            else "cas"
            if pool.autoscaling_enabled
            else "fixed"
        ] += 1
    result.arm_pool_market = FleetArmPoolMarket(
        status="partial" if market_counts["unknown"] else "available",
        pool_counts=dict(sorted(market_counts.items())),
        observed_at=capacity.azure_observed_at,
        reason_codes=["unknown_arm_pool_market"] if market_counts["unknown"] else [],
    )
    reasons.extend(capacity.issues)
    state = capacity.nap_api_status.get("karpenter.sh/v1/nodepools", "unknown")
    if state == "available":
        for nap_pool in capacity.nap_pools:
            if (
                capacity.provisioning_mode != "Auto"
                or nap_pool.nodeclass_uid is None
                or capacity.nap_api_status.get("karpenter.azure.com/v1beta1/aksnodeclasses")
                != "available"
            ):
                counts["unknown"] += 1
                reasons.append("unverified_nap_supply_class")
                continue
            key: SupplyClass = (
                "nap_static"
                if nap_pool.supply_mode == "static"
                else "nap_dynamic"
                if nap_pool.supply_mode == "dynamic"
                else "unknown"
            )
            counts[key] += 1
    elif state != "absent":
        reasons.append(f"nap_nodepool_inventory_{state}")
    elif capacity.nap_pools:
        result.reason_codes = ["inconsistent_nap_inventory"]
        return result
    if counts["unknown"]:
        reasons.append("unknown_supply_class")
    result.status = "partial" if reasons else "available"
    result.pool_counts = dict(sorted(counts.items()))
    result.reason_codes = sorted(set(reasons))
    return result


def _workload_supply(
    workload_uid: str,
    assessment: OfflineAssessment,
    cluster: ClusterSnapshot,
    config: AdvisorConfig,
) -> FleetWorkloadSupply:
    result = FleetWorkloadSupply()
    inventory, capacity = cluster.scheduling, cluster.capacity
    if inventory is None or capacity is None:
        result.reason_codes = ["missing_supply_attribution_inventory"]
        return result
    result.observed_at = inventory.observed_at
    reasons = _inventory_reasons(assessment, cluster, config)
    reasons.extend(_clock_reasons(capacity.azure_observed_at, assessment, config))
    reasons.extend(_clock_reasons(capacity.kubernetes_observed_at, assessment, config))
    if (
        capacity.cluster_resource_id != cluster.resource_id
        or capacity.cluster_uid != cluster.uid
        or capacity.kubernetes_observed_at != inventory.observed_at
    ):
        reasons.append("supply_attribution_binding_mismatch")
    if reasons:
        result.reason_codes = sorted(set(reasons))
        return result
    metadata = [
        item
        for item in assessment.metadata_evidence
        if item.cluster_resource_id == cluster.resource_id
        and item.cluster_uid == cluster.uid
        and item.generated_at == inventory.observed_at
    ]
    counts: Counter[SupplyClass] = Counter()
    for pod in inventory.pods:
        if pod.workload_uid != workload_uid or pod.namespace in config.excluded_namespaces:
            continue
        classes: set[SupplyClass] = set()
        if pod.node_uid is not None:
            managed = [item for item in capacity.nap_managed_nodes if item.node_uid == pod.node_uid]
            if len(managed) == 1 and capacity.provisioning_mode == "Auto":
                pools = [item for item in capacity.nap_pools if item.uid == managed[0].nodepool_uid]
                if (
                    len(pools) == 1
                    and pools[0].nodeclass_uid
                    and capacity.nap_api_status.get("karpenter.sh/v1/nodepools") == "available"
                    and capacity.nap_api_status.get("karpenter.azure.com/v1beta1/aksnodeclasses")
                    == "available"
                ):
                    if pools[0].supply_mode == "static":
                        classes.add("nap_static")
                    elif pools[0].supply_mode == "dynamic":
                        classes.add("nap_dynamic")
            if len(metadata) == 1:
                nodes = [
                    item
                    for item in metadata[0].nodes
                    if item.node_uid == pod.node_uid and item.state == "matched"
                ]
                if len(nodes) == 1:
                    arm_pools = [
                        item
                        for item in capacity.pools
                        if item.resource_id == nodes[0].node_pool_resource_id
                    ]
                    if len(arm_pools) == 1 and arm_pools[0].autoscaling_enabled is not None:
                        classes.add("cas" if arm_pools[0].autoscaling_enabled else "fixed")
        if len(classes) != 1:
            counts["unknown"] += 1
            reasons.append("ambiguous_pod_supply" if classes else "unresolved_pod_supply")
        else:
            counts[next(iter(classes))] += 1
    result.pod_counts = dict(sorted(counts.items()))
    result.reason_codes = sorted(set(reasons))
    result.status = "partial" if reasons else "available"
    return result


def _review_context(
    uid: str,
    identity: tuple[str, str, str, str],
    assessment: OfflineAssessment,
    cluster: ClusterSnapshot,
) -> FleetWorkloadInvestigation:
    namespace, namespace_uid, kind, name = identity
    result = FleetWorkloadInvestigation(
        namespace=namespace,
        namespace_uid=namespace_uid,
        workload_uid=uid,
        workload_kind=kind,
        workload_name=name,
    )
    candidates = [workload for workload in cluster.workloads if workload.uid == uid]
    if len(candidates) > 1:
        result.reason_codes = ["ambiguous_review_policy_identity"]
    elif not candidates or candidates[0].safety_policy is None:
        result.reason_codes = ["missing_admitted_review_policy"]
    else:
        workload = candidates[0]
        policy = workload.safety_policy
        assert policy is not None
        if (workload.namespace, workload.kind, workload.name) != (namespace, kind, name):
            result.reason_codes = ["review_policy_identity_mismatch"]
        elif (
            policy.reviewed_window_start != assessment.snapshot.metric_window.start
            or policy.reviewed_window_end != assessment.snapshot.metric_window.end
        ):
            result.reason_codes = ["review_policy_window_mismatch"]
        elif not policy.owner.strip():
            result.reason_codes = ["review_owner_unknown"]
        else:
            result.review_owner_status = "declared"
    return result


def _workload_inventory(
    assessment: OfflineAssessment, cluster: ClusterSnapshot, config: AdvisorConfig
) -> FleetWorkloadInventory:
    inventory = cluster.scheduling
    if inventory is None:
        return FleetWorkloadInventory(
            status="unknown", reason_codes=["missing_scheduling_inventory"]
        )
    result = FleetWorkloadInventory(status="unknown", observed_at=inventory.observed_at)
    reasons = _inventory_reasons(assessment, cluster, config)
    reasons.extend(_clock_reasons(inventory.observed_at, assessment, config))
    reasons.extend(inventory.issues)
    if inventory.cluster_resource_id != cluster.resource_id or inventory.cluster_uid != cluster.uid:
        reasons.append("scheduling_identity_mismatch")
    if reasons:
        result.reason_codes = sorted(set(reasons))
        return result
    pods = [pod for pod in inventory.pods if pod.namespace not in config.excluded_namespaces]
    owners: dict[str, tuple[str, str, str, str]] = {}
    ambiguous: set[str] = set()
    unresolved_pod_uids: set[str] = set()
    unresolved = 0
    for pod in pods:
        if (
            not all([pod.namespace_uid, pod.workload_uid, pod.workload_kind, pod.workload_name])
            or pod.workload_kind not in {"Deployment", "StatefulSet", "DaemonSet", "Job"}
            or "ambiguous_scheduling_identity" in pod.issues
            or "invalid_scheduling_identity" in pod.issues
        ):
            unresolved += 1
            unresolved_pod_uids.add(pod.pod_uid)
            continue
        assert pod.workload_uid is not None and pod.namespace_uid is not None
        assert pod.workload_kind is not None and pod.workload_name is not None
        identity = (pod.namespace, pod.namespace_uid, pod.workload_kind, pod.workload_name)
        if pod.workload_uid in owners and owners[pod.workload_uid] != identity:
            ambiguous.add(pod.workload_uid)
        owners[pod.workload_uid] = identity
    unresolved += sum(pod.workload_uid in ambiguous for pod in pods)
    unresolved_pod_uids.update(pod.pod_uid for pod in pods if pod.workload_uid in ambiguous)
    counts = Counter(owner[2] for uid, owner in owners.items() if uid not in ambiguous)
    if unresolved:
        reasons.append("unresolved_workload_identity")
    if ambiguous:
        reasons.append("ambiguous_workload_identity")
    result.status = "partial" if reasons else "available"
    result.workload_counts = dict(sorted(counts.items()))
    result.observed_pods = len(pods)
    result.unresolved_pods = unresolved
    result.workload_investigations = [
        _review_context(uid, owner, assessment, cluster)
        for uid, owner in sorted(owners.items())
        if uid not in ambiguous
    ]
    result.review_owner_status_counts = dict(
        sorted(Counter(item.review_owner_status for item in result.workload_investigations).items())
    )
    for investigation in result.workload_investigations:
        investigation.observed_supply = _workload_supply(
            investigation.workload_uid, assessment, cluster, config
        )
    result.namespace_distribution = []
    namespace_keys = {(pod.namespace, pod.namespace_uid) for pod in pods}
    for namespace, namespace_uid in sorted(namespace_keys, key=lambda key: (key[0], key[1] or "")):
        members = [
            pod for pod in pods if (pod.namespace, pod.namespace_uid) == (namespace, namespace_uid)
        ]
        namespace_counts = Counter(
            owner[2]
            for uid, owner in owners.items()
            if uid not in ambiguous and (owner[0], owner[1]) == (namespace, namespace_uid)
        )
        result.namespace_distribution.append(
            FleetNamespaceWorkloads(
                namespace=namespace,
                namespace_uid=namespace_uid,
                workload_counts=dict(sorted(namespace_counts.items())),
                observed_pods=len(members),
                unresolved_pods=sum(pod.pod_uid in unresolved_pod_uids for pod in members),
            )
        )
    result.reason_codes = sorted(set(reasons))
    return result


def _pack_basis(assessment: OfflineAssessment) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((item.id, item.digest) for item in assessment.report.pack_provenance))


def _comparability_reasons(
    assessments: list[OfflineAssessment],
) -> list[ComparabilityReason]:
    reasons: list[ComparabilityReason] = []
    if (
        len(
            {
                (item.report.observation_window.start, item.report.observation_window.end)
                for item in assessments
            }
        )
        != 1
    ):
        reasons.append("observation_windows_differ")
    if len({item.report.mode for item in assessments}) != 1:
        reasons.append("analysis_modes_differ")
    if len({_pack_basis(item) for item in assessments}) != 1:
        reasons.append("pack_definitions_differ")
    if len({item.report.configuration_digest for item in assessments}) != 1:
        reasons.append("configurations_differ")
    return reasons


def _merge_counts[Key: str](
    values: list[dict[Key, int] | None],
) -> dict[Key, int] | None:
    observed = [value for value in values if value is not None]
    if not observed:
        return None
    counts: Counter[Key] = Counter()
    for value in observed:
        counts.update(value)
    return dict(sorted(counts.items()))


def _group_historical_usage(members: list[FleetClusterInsight]) -> HistoricalPeerUsage | None:
    histories = [item.historical_usage for item in members if item.historical_usage is not None]
    if not histories:
        return None
    result = HistoricalPeerUsage(
        cluster_resource_ids=sorted(item.cluster_resource_id for item in members),
        cpu_gaps=[],
        memory_gaps=[],
    )
    if len(histories) != len(members):
        result.cpu_gaps = result.memory_gaps = ["missing_cluster_history"]
        return result
    basis = {
        (
            item.window_start,
            item.window_end,
            item.step_seconds,
            item.source_version,
            item.profile,
            item.profile_version,
            item.mapping_reference,
            item.cpu_rate_window_seconds,
        )
        for item in histories
    }
    if len(basis) != 1:
        result.cpu_gaps = result.memory_gaps = ["incompatible_historical_basis"]
        return result
    result.window_start = histories[0].window_start
    result.window_end = histories[0].window_end
    result.step_seconds = histories[0].step_seconds
    result.cpu_gaps = sorted({gap for item in histories for gap in item.cpu_gaps})
    result.memory_gaps = sorted({gap for item in histories for gap in item.memory_gaps})
    aligned = list(zip(*(item.points for item in histories), strict=True))
    if any(len({point.timestamp for point in points}) != 1 for points in aligned):
        raise ValueError("historical peer contributions must align exactly")
    if not result.cpu_gaps:
        cpu_totals = [
            _finite_sum([point.cpu_mcpu for point in points if point.cpu_mcpu is not None])
            for points in aligned
        ]
        result.cpu_p95_mcpu = (
            None
            if None in cpu_totals
            else _finite_percentile([value for value in cpu_totals if value is not None], 95)
        )
        if result.cpu_p95_mcpu is None:
            result.cpu_gaps = ["nonfinite_peer_resource_total_or_percentile"]
    if not result.memory_gaps:
        memory_totals = [
            _finite_sum(
                [
                    point.memory_working_set_mib
                    for point in points
                    if point.memory_working_set_mib is not None
                ]
            )
            for points in aligned
        ]
        result.memory_p99_working_set_mib = (
            None
            if None in memory_totals
            else _finite_percentile([value for value in memory_totals if value is not None], 99)
        )
        if result.memory_p99_working_set_mib is None:
            result.memory_gaps = ["nonfinite_peer_resource_total_or_percentile"]
    return result


def _historical_usage(
    entry: FleetAssessment, assessment: OfflineAssessment, cluster: ClusterSnapshot
) -> HistoricalNodeReview | None:
    histories = [
        item for item in entry.node_history if item.cluster_resource_id == cluster.resource_id
    ]
    if not histories:
        return None
    history = histories[0]
    manifest = assessment.snapshot.collection_manifest
    if (
        len(histories) != 1
        or manifest is None
        or str(history.tenant_id) != manifest.tenant_id
        or history.cluster_uid != cluster.uid
        or not assessment.report.observation_window.start
        <= history.window_start
        <= history.window_end
        <= assessment.report.observation_window.end
    ):
        raise ValueError("fleet history requires exact original scope, fingerprint and window")
    return review_node_history(
        history,
        as_of=assessment.report.generated_at,
        maximum_source_age_seconds=max(
            1, int(entry.analysis_config.thresholds.maximum_evidence_age_hours * 3600)
        ),
    )


def _external_context(
    entry: FleetAssessment, assessment: OfflineAssessment, cluster: ClusterSnapshot
) -> FleetContextReview | None:
    contexts = [
        item for item in entry.external_context if item.cluster_resource_id == cluster.resource_id
    ]
    if not contexts:
        return None
    if len(contexts) != 1 or cluster.uid is None:
        raise ValueError("fleet supplemental context requires one exact cluster binding")
    manifest = assessment.snapshot.collection_manifest
    if manifest is None:
        raise ValueError("fleet supplemental context requires original tenant provenance")
    inventory = _workload_inventory(assessment, cluster, entry.analysis_config)
    return review_fleet_context(
        contexts[0],
        tenant_id=manifest.tenant_id,
        cluster_resource_id=cluster.resource_id,
        cluster_uid=cluster.uid,
        window_start=assessment.report.observation_window.start,
        window_end=assessment.report.observation_window.end,
        as_of=assessment.report.generated_at,
        maximum_source_age_seconds=max(
            1, int(entry.analysis_config.thresholds.maximum_evidence_age_hours * 3600)
        ),
        workload_identities=[
            (item.namespace_uid, item.workload_uid)
            for item in inventory.workload_investigations or []
        ],
    )


def _peer_group_insights(
    entries: list[FleetAssessment],
    assessments: list[OfflineAssessment],
    clusters: list[FleetClusterInsight],
) -> list[FleetPeerGroupInsight]:
    groups = []
    for peer_group in sorted({item.peer_group for item in clusters}):
        members = [item for item in clusters if item.peer_group == peer_group]
        reasons = _comparability_reasons(
            [
                assessment
                for entry, assessment in zip(entries, assessments, strict=True)
                if entry.peer_group == peer_group
            ]
        )
        groups.append(
            FleetPeerGroupInsight(
                peer_group=peer_group,
                clusters=len(members),
                cluster_resource_ids=[item.cluster_resource_id for item in members],
                comparable=not reasons,
                comparability_reasons=reasons,
                recommendations=sum(item.recommendations for item in members),
                blocked_recommendations=sum(item.blocked_recommendations for item in members),
                high_or_critical=sum(item.high_or_critical for item in members),
                rule_counts=_merge_counts([item.rule_counts for item in members]) or {},
                category_counts=_merge_counts([item.category_counts for item in members]) or {},
                blocked_reason_counts=_merge_counts(
                    [item.blocked_reason_counts for item in members]
                )
                or {},
                source_status_counts=_merge_counts([item.source_status_counts for item in members])
                or {},
                inventory_status_counts={
                    "supply": dict(
                        sorted(Counter(item.supply_inventory.status for item in members).items())
                    ),
                    "workloads": dict(
                        sorted(Counter(item.workload_inventory.status for item in members).items())
                    ),
                    "arm_pool_market": dict(
                        sorted(
                            Counter(
                                item.supply_inventory.arm_pool_market.status for item in members
                            ).items()
                        )
                    ),
                },
                supply_pool_counts=_merge_counts(
                    [item.supply_inventory.pool_counts for item in members]
                ),
                arm_pool_market_counts=_merge_counts(
                    [item.supply_inventory.arm_pool_market.pool_counts for item in members]
                ),
                review_owner_status_counts=_merge_counts(
                    [item.workload_inventory.review_owner_status_counts for item in members]
                ),
                workload_counts=_merge_counts(
                    [item.workload_inventory.workload_counts for item in members]
                ),
                resource_envelope=_group_resource_envelope(members, not reasons),
                historical_usage=_group_historical_usage(members),
            )
        )
    return groups


def _validated_assessment(entry: FleetAssessment) -> OfflineAssessment:
    assessment = OfflineAssessment.model_validate(entry.assessment.model_dump(mode="python"))
    config = AdvisorConfig.model_validate(entry.analysis_config.model_dump(mode="python"))
    snapshot_digest = sha256(
        json.dumps(
            assessment.snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if assessment.report.snapshot_digest != snapshot_digest:
        raise ValueError("fleet snapshot integrity check failed")
    if assessment.report.observation_window != assessment.snapshot.metric_window:
        raise ValueError("fleet report window must match its snapshot")
    locks = {item.id: item.digest for item in assessment.report.pack_provenance}
    if (
        not config.pack_locks
        or config.pack_locks != locks
        or assessment.report.configuration_digest != digest_json(config.model_dump(mode="json"))
    ):
        raise ValueError("fleet aggregation requires matching locked configuration provenance")
    if (
        analyze(assessment.snapshot, config, as_of=assessment.report.generated_at)
        != assessment.report
    ):
        raise ValueError("fleet assessment report does not match deterministic replay")
    return assessment


def aggregate_fleet(
    entries: list[FleetAssessment], *, generated_at: datetime
) -> FleetInsightReport:
    if not 2 <= len(entries) <= 1000:
        raise ValueError("fleet aggregation requires 2 to 1000 assessments")

    assessments = [_validated_assessment(entry) for entry in entries]
    manifests = [item.snapshot.collection_manifest for item in assessments]
    if any(manifest is None for manifest in manifests):
        raise ValueError("fleet aggregation requires collection provenance")
    tenant_ids = {manifest.tenant_id for manifest in manifests if manifest is not None}
    if len(tenant_ids) != 1:
        raise ValueError("fleet aggregation requires one tenant")
    tenant_id = next(iter(tenant_ids))

    clusters: list[FleetClusterInsight] = []
    identities: set[tuple[str, str]] = set()
    rule_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    blocked_reason_counts: Counter[str] = Counter()

    for entry, assessment in zip(entries, assessments, strict=True):
        report = assessment.report
        snapshot_clusters = {
            cluster.resource_id: cluster for cluster in assessment.snapshot.clusters
        }
        if len(snapshot_clusters) != len(assessment.snapshot.clusters):
            raise ValueError("fleet assessment cluster identities must be distinct")
        if any(item.cluster_resource_id not in snapshot_clusters for item in entry.node_history):
            raise ValueError("fleet history cannot include foreign cluster scope")
        if any(
            item.cluster_resource_id not in snapshot_clusters for item in entry.external_context
        ):
            raise ValueError("fleet supplemental context cannot include foreign cluster scope")
        if any(
            item.tenant_id != tenant_id or item.cluster_resource_id not in snapshot_clusters
            for item in assessment.metadata_evidence
        ):
            raise ValueError("fleet retained metadata must match tenant and cluster scope")
        finding_resource_ids = {item.resource_id for item in report.recommendations} | {
            item.resource_id for item in report.blocked_recommendations
        }
        capability_resource_ids = {item.cluster_resource_id for item in report.source_capabilities}
        if not finding_resource_ids <= snapshot_clusters.keys() or not capability_resource_ids <= (
            snapshot_clusters.keys()
        ):
            raise ValueError("fleet findings and capabilities require snapshot cluster identity")

        for cluster in snapshot_clusters.values():
            if cluster.uid is None:
                raise ValueError("fleet aggregation requires exact cluster fingerprints")
            identity = (cluster.resource_id, cluster.uid)
            if identity in identities:
                raise ValueError("fleet aggregation requires distinct cluster identities")
            if any(
                resource_id == cluster.resource_id and uid != cluster.uid
                for resource_id, uid in identities
            ):
                raise ValueError("fleet aggregation rejects conflicting cluster incarnations")
            identities.add(identity)

            recommendations = [
                item for item in report.recommendations if item.resource_id == cluster.resource_id
            ]
            blocked = [
                item
                for item in report.blocked_recommendations
                if item.resource_id == cluster.resource_id
            ]
            capabilities = sorted(
                (
                    item
                    for item in report.source_capabilities
                    if item.cluster_resource_id == cluster.resource_id
                ),
                key=lambda item: (item.pack_id, item.mode, item.source),
            )
            source_status_counts: Counter[CapabilityStatus] = Counter(
                item.status for item in capabilities
            )
            rule_counts.update(item.rule_id for item in recommendations)
            category_counts.update(item.category for item in recommendations)
            blocked_reason_counts.update(reason for item in blocked for reason in item.reason_codes)
            clusters.append(
                FleetClusterInsight(
                    tenant_id=tenant_id,
                    cluster_resource_id=cluster.resource_id,
                    cluster_uid=cluster.uid,
                    cluster_name=cluster.name,
                    subscription_id=cluster.subscription_id,
                    location=cluster.location,
                    environment=cluster.environment,
                    peer_group=entry.peer_group,
                    assessment_status=assessment.status,
                    mode=report.mode,
                    generated_at=report.generated_at,
                    observation_window=report.observation_window,
                    recommendations=len(recommendations),
                    blocked_recommendations=len(blocked),
                    high_or_critical=sum(
                        item.severity.value in {"high", "critical"} for item in recommendations
                    ),
                    source_capabilities=capabilities,
                    source_status_counts=dict(sorted(source_status_counts.items())),
                    data_quality_warnings=report.summary.data_quality_warnings,
                    excluded_namespaces=entry.analysis_config.excluded_namespaces,
                    supply_inventory=_supply_inventory(assessment, cluster, entry.analysis_config),
                    workload_inventory=_workload_inventory(
                        assessment, cluster, entry.analysis_config
                    ),
                    resource_envelope=_resource_envelope(
                        assessment, cluster, entry.analysis_config
                    ),
                    historical_usage=_historical_usage(entry, assessment, cluster),
                    external_context=_external_context(entry, assessment, cluster),
                    rule_counts=dict(
                        sorted(Counter(item.rule_id for item in recommendations).items())
                    ),
                    category_counts=dict(
                        sorted(Counter(item.category for item in recommendations).items())
                    ),
                    blocked_reason_counts=dict(
                        sorted(
                            Counter(
                                reason for item in blocked for reason in item.reason_codes
                            ).items()
                        )
                    ),
                )
            )

    reasons = _comparability_reasons(assessments)
    clusters.sort(key=lambda item: (item.cluster_resource_id, item.cluster_uid))
    return FleetInsightReport(
        tenant_id=tenant_id,
        generated_at=generated_at,
        comparable=not reasons,
        comparability_reasons=reasons,
        summary=FleetInsightSummary(
            clusters=len(clusters),
            peer_groups=len({item.peer_group for item in clusters}),
            recommendations=sum(item.recommendations for item in clusters),
            blocked_recommendations=sum(item.blocked_recommendations for item in clusters),
            high_or_critical=sum(item.high_or_critical for item in clusters),
        ),
        clusters=clusters,
        rule_counts=dict(sorted(rule_counts.items())),
        blocked_reason_counts=dict(sorted(blocked_reason_counts.items())),
        category_counts=dict(sorted(category_counts.items())),
        peer_groups=_peer_group_insights(entries, assessments, clusters),
    )
