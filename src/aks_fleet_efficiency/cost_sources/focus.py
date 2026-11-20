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
    FocusChargeMetadata,
    Money,
    Text,
)
from aks_fleet_efficiency.cost_sources.base import ProjectionModel, projection_profile
from aks_fleet_efficiency.models import UtcDatetime


class FocusRow(FocusChargeMetadata):
    charge_id: Text
    sub_account_id: UUID
    resource_id: Text | None
    charge_period_start: UtcDatetime
    charge_period_end: UtcDatetime
    effective_cost: Money
    billing_currency: Currency
    service_category: Text


class FocusProjection(ProjectionModel):
    schema_version: Literal["finops-focus-projection-v1"]
    producer_version: Text
    tenant_id: UUID
    subscription_ids: list[UUID] = Field(min_length=1, max_length=1000)
    period: CostPeriod
    source_reference: Text
    source_observed_at: UtcDatetime
    export_complete: bool = Field(strict=True)
    rows: list[FocusRow] = Field(max_length=100_000)
    bindings: list[CostResourceBinding] = Field(default_factory=list, max_length=100_000)


def _category(value: str) -> ChargeCategory:
    normalized = value.casefold()
    if normalized == "compute":
        return "compute"
    if normalized == "storage":
        return "storage"
    if normalized in {"network", "networking"}:
        return "network"
    if normalized == "service":
        return "service"
    return "other"


def project_focus(profile_id: str, payload: object) -> CostImport:
    if profile_id != "finops-focus":
        raise ValueError("FOCUS evidence requires the finops-focus profile")
    source = FocusProjection.model_validate(payload)
    profile = projection_profile(profile_id, source.producer_version, source.schema_version)
    rows = [
        CostRow(
            id=item.charge_id,
            subscription_id=item.sub_account_id,
            resource_id=item.resource_id,
            period=CostPeriod(start=item.charge_period_start, end=item.charge_period_end),
            amount=item.effective_cost,
            currency=item.billing_currency,
            charge_category=_category(item.service_category),
            source_category=item.service_category,
            charge_type=item.charge_category,
            pricing_model="OnDemand"
            if item.pricing_category == "Standard"
            else item.pricing_category,
            benefit_id=item.commitment_discount_id,
            focus=FocusChargeMetadata.model_validate(
                item.model_dump(include=set(FocusChargeMetadata.model_fields))
            ),
        )
        for item in source.rows
    ]
    return CostImport(
        ledger_profile=FinancialProfileReference(
            id=profile_id, version=profile.version, producer_version=source.producer_version
        ),
        cost_basis="effective",
        tenant_id=source.tenant_id,
        subscription_ids=source.subscription_ids,
        period=source.period,
        source_reference=source.source_reference,
        source_observed_at=source.source_observed_at,
        export_complete=source.export_complete,
        rows=rows,
        bindings=source.bindings,
    )
