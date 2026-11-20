from __future__ import annotations

from typing import Literal

from pydantic import Field

from aks_fleet_efficiency.cost import (
    AggregateAllocation,
    AllocationShare,
    CostAllocation,
    CostBasis,
    CostPeriod,
    FinancialProfileReference,
    Text,
)
from aks_fleet_efficiency.cost_sources.base import ProjectionModel, projection_profile


class ReviewedAllocationProjection(ProjectionModel):
    schema_version: Text
    producer_version: Text
    source_reference: Text
    cost_basis: CostBasis
    pricing_basis: Literal["billing-ledger", "source-declared", "list-price"] = "source-declared"
    period: CostPeriod
    complete: bool = Field(strict=True)
    allocation_policy: Literal["not-shared", "source-native"]
    shares: list[AllocationShare] = Field(default_factory=list, max_length=100_000)
    amounts: list[AggregateAllocation] = Field(default_factory=list, max_length=100_000)


def project_reviewed_allocation(profile_id: str, payload: object) -> CostAllocation:
    source = ReviewedAllocationProjection.model_validate(payload)
    profile = projection_profile(profile_id, source.producer_version, source.schema_version)
    if profile.evidence_kind != "allocation":
        raise ValueError("selected financial profile is not allocation evidence")
    if source.pricing_basis == "list-price":
        raise ValueError("list-price allocation pricing is not supported by the billing workflow")
    if profile.pricing_provenance == "reviewed" and source.pricing_basis != "billing-ledger":
        raise ValueError(
            "allocation pricing requires independently reviewed billing-ledger provenance"
        )
    return CostAllocation(
        profile=FinancialProfileReference(
            id=profile_id, version=profile.version, producer_version=source.producer_version
        ),
        source_reference=source.source_reference,
        cost_basis=source.cost_basis,
        pricing_basis=source.pricing_basis,
        period=source.period,
        complete=source.complete,
        allocation_policy=source.allocation_policy,
        shares=source.shares,
        amounts=source.amounts,
    )
