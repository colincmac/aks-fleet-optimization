from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from aks_fleet_efficiency.cost import (
    ChargeCategory,
    CostImport,
    CostPeriod,
    CostResourceBinding,
    CostRow,
    Currency,
    FinancialProfileReference,
    Money,
    Text,
)
from aks_fleet_efficiency.cost_sources.base import ProjectionModel, projection_profile
from aks_fleet_efficiency.models import UtcDatetime


class AzureCostDetailsRow(ProjectionModel):
    row_id: Text
    subscription_id: UUID
    resource_id: Text | None
    period_start: UtcDatetime
    period_end: UtcDatetime
    cost_in_billing_currency: Money
    billing_currency: Currency
    charge_category: ChargeCategory
    meter_category: Text
    charge_type: Literal[
        "Usage",
        "Purchase",
        "Refund",
        "UnusedReservation",
        "UnusedSavingsPlan",
        "RoundingAdjustment",
    ]
    pricing_model: Literal["OnDemand", "Reservation", "SavingsPlan", "Spot"]
    benefit_id: Text | None = None
    reservation_id: Text | None = None


class AzureCostDetailsProjection(ProjectionModel):
    schema_version: Literal["azure-cost-details-projection-v1"]
    producer_version: Text
    cost_basis: Literal["actual", "amortized"]
    tenant_id: UUID
    subscription_ids: list[UUID] = Field(min_length=1, max_length=1000)
    period: CostPeriod
    source_reference: Text
    source_observed_at: UtcDatetime
    export_complete: bool = Field(strict=True)
    rows: list[AzureCostDetailsRow] = Field(max_length=100_000)
    bindings: list[CostResourceBinding] = Field(default_factory=list, max_length=100_000)


def project_azure(profile_id: str, payload: object) -> CostImport:
    source = AzureCostDetailsProjection.model_validate(payload)
    expected = {
        "actual": "azure-cost-details-actual",
        "amortized": "azure-cost-details-amortized",
    }[source.cost_basis]
    if profile_id != expected:
        raise ValueError("Azure cost basis does not match the selected financial profile")
    profile = projection_profile(profile_id, source.producer_version, source.schema_version)
    rows = [
        CostRow(
            id=item.row_id,
            subscription_id=item.subscription_id,
            resource_id=item.resource_id,
            period=CostPeriod(start=item.period_start, end=item.period_end),
            amount=item.cost_in_billing_currency,
            currency=item.billing_currency,
            charge_category=item.charge_category,
            source_category=item.meter_category,
            charge_type=item.charge_type,
            pricing_model=item.pricing_model,
            benefit_id=item.benefit_id,
            reservation_id=item.reservation_id,
        )
        for item in source.rows
    ]
    return CostImport(
        ledger_profile=FinancialProfileReference(
            id=profile_id, version=profile.version, producer_version=source.producer_version
        ),
        cost_basis=source.cost_basis,
        tenant_id=source.tenant_id,
        subscription_ids=source.subscription_ids,
        period=source.period,
        source_reference=source.source_reference,
        source_observed_at=source.source_observed_at,
        export_complete=source.export_complete,
        rows=rows,
        bindings=source.bindings,
    )
