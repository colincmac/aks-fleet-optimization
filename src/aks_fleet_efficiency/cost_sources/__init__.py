from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aks_fleet_efficiency.cost import (
    AllocationObservation,
    ClusterCostReviewOrder,
    CostAllocation,
    CostImport,
    CostPeriod,
    order_cluster_cost_reviews,
    qualify_allocation_observation,
)
from aks_fleet_efficiency.cost_sources.allocation import project_reviewed_allocation
from aks_fleet_efficiency.cost_sources.azure import project_azure
from aks_fleet_efficiency.cost_sources.focus import project_focus


def project_ledger(profile_id: str, payload: object) -> CostImport:
    if profile_id in {"azure-cost-details-actual", "azure-cost-details-amortized"}:
        return project_azure(profile_id, payload)
    if profile_id == "finops-focus":
        return project_focus(profile_id, payload)
    raise ValueError("selected financial profile is not a supported ledger projector")


def project_allocation(profile_id: str, payload: object) -> CostAllocation:
    return project_reviewed_allocation(profile_id, payload)


def order_saved_cost_reviews(
    inputs: list[tuple[Path, AllocationObservation]], *, tenant_id: str, as_of: datetime
) -> ClusterCostReviewOrder:
    from aks_fleet_efficiency.assessment import AssessmentFragments
    from aks_fleet_efficiency.history import _digest, _read_verified_archive

    if not 2 <= len(inputs) <= 1000:
        raise ValueError("Cost review requires two to 1000 original assessment/observation pairs")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Cost review requires an aware evaluation clock")
    tenant = UUID(tenant_id)
    clock = as_of.astimezone(UTC)
    remaining = 128 * 1024 * 1024
    contexts = []
    ages = []
    run_ids = {}
    for directory, observation in inputs:
        observation = AllocationObservation.model_validate(observation.model_dump())
        observation_bytes = len(observation.model_dump_json().encode("utf-8"))
        if observation_bytes > 32 * 1024 * 1024 or observation_bytes >= remaining:
            raise ValueError("Cost review exceeds its protected input byte budget")
        remaining -= observation_bytes
        archive, original, configuration = _read_verified_archive(
            directory, tenant_id=tenant, maximum_bytes=min(32 * 1024 * 1024, remaining)
        )
        remaining -= sum(len(value.encode("utf-8")) for value in archive.payloads.values())
        if len(original.snapshot.clusters) != 1 or clock < original.report.generated_at:
            raise ValueError("Cost review requires one original cluster and a nonfuture assessment")
        cluster = original.snapshot.clusters[0]
        fragments = AssessmentFragments.model_validate_json(archive.payloads["fragments.json"])
        metadata = [
            item for item in fragments.kubernetes if item.cluster_resource_id == cluster.resource_id
        ]
        if (
            not cluster.uid
            or len(metadata) != 1
            or metadata[0].cluster_uid != cluster.uid
            or [
                item.uid
                for item in metadata[0].resources
                if item.kind == "Namespace"
                and item.api_version == "v1"
                and item.name == "kube-system"
            ]
            != [cluster.uid]
        ):
            raise ValueError("Cost review requires the exact original Kubernetes fingerprint")
        if cluster.resource_id in run_ids:
            raise ValueError("Cost review refuses duplicate or recreated cluster inputs")
        run_ids[cluster.resource_id] = _digest(archive)
        ages.append(configuration.thresholds.maximum_evidence_age_hours)
        contexts.append(
            qualify_allocation_observation(
                observation,
                tenant_id=str(tenant),
                cluster_resource_id=cluster.resource_id,
                cluster_uid=cluster.uid,
                period=CostPeriod(
                    start=original.report.observation_window.start,
                    end=original.report.observation_window.end,
                ),
                as_of=clock,
                maximum_evidence_age_hours=ages[-1],
            )
        )
    result = order_cluster_cost_reviews(contexts, maximum_evidence_age_hours=min(ages))
    return ClusterCostReviewOrder.model_validate(
        result.model_dump()
        | {
            "original_assessment_run_ids": dict(sorted(run_ids.items())),
        }
    )


__all__ = ["order_saved_cost_reviews", "project_allocation", "project_ledger"]
