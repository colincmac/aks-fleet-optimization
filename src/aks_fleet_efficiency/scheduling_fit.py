from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from aks_fleet_efficiency.assessment import AssessmentFragments, _validate_bindings
from aks_fleet_efficiency.capacity import NAP_APIS, normalize_capacity
from aks_fleet_efficiency.catalog.models import CatalogModel, Digest, Text
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import CollectionStatus, NapManagedNode, UtcDatetime
from aks_fleet_efficiency.scheduling import (
    MAXIMUM_PLACEMENT_PAIRS,
    PodNodeConstraintReview,
    SchedulingResourceComparison,
    _audit_scheduling_completeness,
    _available_resource,
    _resource_fragmentation,
    _retained_pod_slots,
    _review_scheduling_placement,
    normalize_scheduling,
)


class SchedulingNecessaryFitProfile(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    profile_id: Literal["kubernetes-1.36-linux-default-scheduler"] = (
        "kubernetes-1.36-linux-default-scheduler"
    )
    mapping_reference: Literal["kubernetes-core-v1@v1.36.0"] = "kubernetes-core-v1@v1.36.0"
    kubernetes_minor: Literal["1.36"] = "1.36"
    pod_os: Literal["linux"] = "linux"
    scheduler_name: Literal["default-scheduler"] = "default-scheduler"
    supported_constraints: tuple[
        Literal["cpu"],
        Literal["memory"],
        Literal["pod_slots"],
        Literal["required_node_selector"],
        Literal["required_node_affinity"],
        Literal["hard_taints"],
        Literal["cordon"],
        Literal["mandatory_node_conditions"],
        Literal["daemonset_reservations"],
        Literal["bound_volume_topology"],
        Literal["csi_attachment_limits"],
        Literal["nap_node_requirements"],
    ] = (
        "cpu",
        "memory",
        "pod_slots",
        "required_node_selector",
        "required_node_affinity",
        "hard_taints",
        "cordon",
        "mandatory_node_conditions",
        "daemonset_reservations",
        "bound_volume_topology",
        "csi_attachment_limits",
        "nap_node_requirements",
    )
    simultaneous_placement: Literal["unsupported"] = "unsupported"
    preemption: Literal["unsupported"] = "unsupported"
    custom_plugins_or_extenders: Literal["unsupported"] = "unsupported"


class SchedulingNecessaryFitReview(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["necessary-fit-review"] = "necessary-fit-review"
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    evaluated_at: UtcDatetime
    source_observed_at: UtcDatetime
    profile: SchedulingNecessaryFitProfile
    profile_digest: Digest
    source_collection_digest: Digest
    calculation_digest: Digest
    source_admission: Literal["blocked"] = "blocked"
    profile_admission: Literal["blocked"] = "blocked"
    status: Literal["blocked"] = "blocked"
    reason_codes: list[Text] = Field(default_factory=list, max_length=64)
    pairs: list[SchedulingResourceComparison] = Field(min_length=1, max_length=100_000)
    simultaneous_placement: Literal["not_calculated"] = "not_calculated"
    removable_nodes: Literal["not_calculated"] = "not_calculated"
    notice: Literal[
        "Resource comparisons only; source and scheduler admission remain blocked. No simultaneous "
        "placement, disruption feasibility, a removable-node result, approval or savings."
    ] = (
        "Resource comparisons only; source and scheduler admission remain blocked. No simultaneous "
        "placement, disruption feasibility, a removable-node result, approval or savings."
    )

    @model_validator(mode="after")
    def validate_review(self) -> SchedulingNecessaryFitReview:
        if self.source_observed_at > self.evaluated_at:
            raise ValueError("Necessary-fit source observation cannot follow evaluation")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Necessary-fit reasons must be distinct")
        pair_keys = [(pair.pod_uid, pair.node_uid) for pair in self.pairs]
        if len(set(pair_keys)) != len(pair_keys):
            raise ValueError("Necessary-fit Pod and Node pairs must be distinct")
        for pair in self.pairs:
            if pair.status == "blocked":
                if not pair.issues:
                    raise ValueError("Blocked pairs require explicit issues")
                continue
            if pair.issues:
                raise ValueError("Necessary-fit non-blocked pairs cannot retain issues")
            cpu_required = pair.cpu_required_mcpu
            memory_required = pair.memory_required_mib
            cpu_available = pair.cpu_available_mcpu
            memory_available = pair.memory_available_mib
            pod_slots_available = pair.pod_slots_available
            if (
                cpu_required is None
                or memory_required is None
                or cpu_available is None
                or memory_available is None
                or pod_slots_available is None
            ):
                raise ValueError("Necessary-fit non-blocked pairs require every resource")
            sufficient = (
                cpu_available >= cpu_required
                and memory_available >= memory_required
                and pod_slots_available >= pair.pod_slots_required
            )
            if (pair.status == "satisfied") != sufficient:
                raise ValueError("Necessary-fit pair status must reflect resource arithmetic")
        if not self.reason_codes:
            raise ValueError("Unsuccessful necessary-fit reviews require explicit reasons")
        return self


class NapNodeConstraintContext(CatalogModel):
    binding: NapManagedNode
    resources: SchedulingResourceComparison
    placement: PodNodeConstraintReview
    observed_daemonset_pods: int | None = Field(default=None, ge=0)
    observed_daemonset_cpu_mcpu: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_daemonset_memory_mib: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PendingNapConstraintReview(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    nodepool_uid: Text
    pod_uid: Text
    evaluated_at: UtcDatetime
    azure_observed_at: UtcDatetime | None
    kubernetes_observed_at: UtcDatetime | None
    metadata_digest: Digest
    nodes: list[NapNodeConstraintContext] = Field(default_factory=list, max_length=256)
    fragmentation: Literal["scattered_across_nodes", "not_observed", "unknown"] = "unknown"
    namespace_pdb_candidates: int | None = Field(default=None, ge=0)
    reason_codes: list[Text] = Field(default_factory=list)
    not_evaluated: tuple[
        Literal["topology_spread"],
        Literal["pod_affinity"],
        Literal["storage"],
        Literal["extended_resources"],
        Literal["node_conditions"],
        Literal["scheduler_plugins"],
        Literal["nap_provisioning"],
    ] = (
        "topology_spread",
        "pod_affinity",
        "storage",
        "extended_resources",
        "node_conditions",
        "scheduler_plugins",
        "nap_provisioning",
    )
    protection_effectiveness: Literal["unknown"] = "unknown"
    source_admission: Literal["blocked"] = "blocked"
    scheduler_admission: Literal["blocked"] = "blocked"
    fit_status: Literal["blocked"] = "blocked"
    simultaneous_placement: Literal["not_calculated"] = "not_calculated"
    removable_nodes: Literal["not_calculated"] = "not_calculated"


def review_pending_nap_constraints(
    fragments: AssessmentFragments,
    profile: OnboardingConfig,
    *,
    cluster_resource_id: str,
    cluster_uid: str,
    nodepool_uid: str,
    pod_uid: str,
    as_of: datetime,
    maximum_source_age_seconds: int,
) -> PendingNapConstraintReview:
    """Compare one currently unbound pending Pod with an observed NAP NodePool roster."""
    if (
        len(fragments.azure) != 1
        or len(fragments.azure[0].clusters) != 1
        or len(fragments.kubernetes) != 1
        or len(fragments.kubernetes[0].resources) > 10_000
    ):
        raise ValueError("NAP constraint review requires one bounded original inventory pair")
    _validate_bindings(fragments, profile)
    azure, metadata = fragments.azure[0], fragments.kubernetes[0]
    cluster = azure.clusters[0]
    pods = sum(item.kind == "Pod" for item in metadata.resources)
    nodes = sum(item.kind == "Node" for item in metadata.resources)
    if pods * nodes > MAXIMUM_PLACEMENT_PAIRS:
        raise ValueError("NAP constraint review exceeds the reservation pair budget")
    if (
        cluster.resource_id != cluster_resource_id
        or metadata.cluster_resource_id != cluster_resource_id
        or metadata.cluster_uid != cluster_uid
    ):
        raise ValueError(
            "NAP constraint review requires the exact approved cluster and fingerprint"
        )
    raw = {item.uid: item for item in metadata.resources}
    pending = raw.get(pod_uid)
    if (
        pending is None
        or pending.kind != "Pod"
        or pending.api_version != "v1"
        or pending.status.get("phase") != "Pending"
        or pending.spec.get("nodeName") not in (None, "")
    ):
        raise ValueError("NAP constraint review requires a currently unbound pending Pod UID")
    audit = _audit_scheduling_completeness(
        metadata,
        as_of=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
        pending_candidate_uid=pod_uid,
    )
    result = PendingNapConstraintReview(
        tenant_id=metadata.tenant_id,
        cluster_resource_id=cluster_resource_id,
        cluster_uid=cluster_uid,
        nodepool_uid=nodepool_uid,
        pod_uid=pod_uid,
        evaluated_at=as_of,
        azure_observed_at=azure.collection.source_observed_at,
        kubernetes_observed_at=metadata.collection.source_observed_at,
        metadata_digest=audit.metadata_digest,
    )
    source_time = result.azure_observed_at
    if (
        azure.collection.status != CollectionStatus.COMPLETE
        or source_time is None
        or azure.generated_at > as_of
        or not 0 <= (as_of - source_time).total_seconds() <= maximum_source_age_seconds
    ):
        result.reason_codes.append("unqualified_azure_inventory")
    result.reason_codes.extend(
        issue for issue in audit.issues if issue != "unresolved_pod_assignment"
    )
    if result.reason_codes:
        return result
    capacity = normalize_capacity(cluster, azure.generated_at, metadata, [])
    pool = next((item for item in capacity.nap_pools if item.uid == nodepool_uid), None)
    if (
        pool is None
        or not pool.nodeclass_uid
        or any(capacity.nap_api_status.get(api) != "available" for api in NAP_APIS)
        or capacity.provisioning_mode != "Auto"
        or {"unresolved_nap_nodeclaim", "ambiguous_nap_nodeclaim"}.intersection(capacity.issues)
    ):
        result.reason_codes.append("unqualified_nodepool_roster")
        return result
    bindings = sorted(
        (item for item in capacity.nap_managed_nodes if item.nodepool_uid == nodepool_uid),
        key=lambda item: item.node_uid,
    )
    if not bindings:
        result.reason_codes.append("no_observed_bound_nodes")
        return result
    if len(bindings) > 256:
        raise ValueError("NAP constraint review exceeds the NodePool roster budget")
    node_identity_counts = Counter(item.node_uid for item in metadata.nodes)
    provider_counts = Counter(
        item.azure_resource_id.casefold() for item in metadata.nodes if item.azure_resource_id
    )
    identities = {item.node_uid: item for item in metadata.nodes}
    for binding in bindings:
        identity = identities[binding.node_uid]
        resource_id = identity.azure_resource_id
        if (
            node_identity_counts[binding.node_uid] != 1
            or resource_id is None
            or provider_counts[resource_id.casefold()] != 1
            or identity.provider_id != f"azure://{resource_id}"
            or not resource_id.casefold().startswith(
                f"/subscriptions/{cluster.subscription_id.casefold()}/"
            )
        ):
            result.reason_codes.append("unqualified_nodepool_roster")
            return result

    inventory = normalize_scheduling(metadata)
    candidate = next(item for item in inventory.pods if item.pod_uid == pod_uid)
    if candidate.namespace_uid is None:
        raise ValueError("NAP constraint review requires the pending Pod's exact namespace UID")
    if metadata.api_availability.get(
        "policy/v1/poddisruptionbudgets"
    ) == "available" and metadata.resource_versions.get("policy/v1/poddisruptionbudgets"):
        result.namespace_pdb_candidates = len(candidate.namespace_pdb_candidates)
    placement = _review_scheduling_placement(
        metadata,
        as_of=as_of,
        maximum_source_age_seconds=maximum_source_age_seconds,
        audit=audit,
        pod_uid=pod_uid,
        node_uids={item.node_uid for item in bindings},
    )
    constraints = {item.node_uid: item for item in placement.pairs}
    effective_nodes = {item.node_uid: item for item in inventory.node_resources}
    reservations = {item.node_uid: item for item in audit.nodes}
    for binding in bindings:
        uid = binding.node_uid
        node, reserved = effective_nodes[uid], reservations[uid]
        cpu = _available_resource(
            node.allocatable_cpu_mcpu, reserved.observed_cpu_request_mcpu, 0, already_bound=False
        )
        memory = _available_resource(
            node.allocatable_memory_mib,
            reserved.observed_memory_request_mib,
            0,
            already_bound=False,
        )
        slots = _retained_pod_slots(raw[uid].status.get("allocatable"))
        count = reserved.observed_nonterminal_pod_count
        remaining_slots = slots - count if slots is not None and count is not None else None
        cpu_needed = candidate.effective_cpu_request_mcpu
        memory_needed = candidate.effective_memory_request_mib
        issues = list(reserved.issues)
        status: Literal["satisfied", "unsatisfied", "blocked"]
        if (
            cpu is None
            or memory is None
            or remaining_slots is None
            or (cpu_needed is None or memory_needed is None)
        ):
            status = "blocked"
            issues.append("incomplete_three_resource_evidence")
        else:
            status = (
                "unsatisfied"
                if cpu < cpu_needed or memory < memory_needed or remaining_slots < 1
                else "satisfied"
            )
        row = NapNodeConstraintContext(
            binding=binding,
            resources=SchedulingResourceComparison(
                pod_uid=pod_uid,
                node_uid=uid,
                status=status,
                cpu_required_mcpu=cpu_needed,
                memory_required_mib=memory_needed,
                cpu_available_mcpu=cpu,
                memory_available_mib=memory,
                pod_slots_available=remaining_slots,
                issues=sorted(set(issues)),
            ),
            placement=constraints[uid],
        )
        if (
            inventory.daemonset_overhead_observed
            and not inventory.daemonset_overhead_issues
            and count is not None
        ):
            bound_pods = set(reserved.pod_uids)
            subtotal = [item for item in inventory.daemonset_overhead if item.pod_uid in bound_pods]
            if all(
                not item.issues
                and item.cpu_request_mcpu is not None
                and item.memory_request_mib is not None
                for item in subtotal
            ):
                row.observed_daemonset_pods = len(subtotal)
                row.observed_daemonset_cpu_mcpu = sum(
                    item.cpu_request_mcpu for item in subtotal if item.cpu_request_mcpu is not None
                )
                row.observed_daemonset_memory_mib = sum(
                    item.memory_request_mib
                    for item in subtotal
                    if item.memory_request_mib is not None
                )
        result.nodes.append(row)
    result.fragmentation = _resource_fragmentation([item.resources for item in result.nodes])[
        0
    ].status
    return result
