from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from aks_fleet_efficiency.config import ClusterTarget
from aks_fleet_efficiency.models import UtcDatetime

Text = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"\S")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
ChargeCategory = Literal["compute", "storage", "network", "other"]
Attribution = Literal["allocated", "idle", "system", "unallocated"]


def _decimal_input(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("financial values require decimal strings, not floats or booleans")
    return value


Money = Annotated[Decimal, BeforeValidator(_decimal_input), Field(max_digits=30, decimal_places=12)]
Fraction = Annotated[
    Decimal,
    BeforeValidator(_decimal_input),
    Field(ge=0, le=1, max_digits=19, decimal_places=18),
]


def resource_subscription(resource_id: str) -> UUID:
    match = re.fullmatch(
        r"/subscriptions/([^/]+)/resourceGroups/[^/]+/providers/[^/]+/(?:[^/]+/[^/]+)(?:/[^/]+/[^/]+)*",
        resource_id,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise ValueError("an exact subscription-scoped Azure resource ID is required")
    return UUID(match.group(1))


class CostModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, hide_input_in_errors=True, frozen=True
    )


class CostPeriod(CostModel):
    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def validate_order(self) -> CostPeriod:
        if self.end <= self.start:
            raise ValueError("cost period must be a nonempty half-open UTC interval")
        return self


class CostRow(CostModel):
    id: Text
    subscription_id: UUID
    resource_id: Text | None
    period: CostPeriod
    amount: Money
    currency: Currency
    charge_category: ChargeCategory
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

    @model_validator(mode="after")
    def validate_resource_scope(self) -> CostRow:
        if (
            self.resource_id is not None
            and resource_subscription(self.resource_id) != self.subscription_id
        ):
            raise ValueError("cost row resource must belong to its declared subscription")
        return self


class CostResourceBinding(CostModel):
    resource_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    pool_resource_id: Text | None = None
    reference: Text

    @model_validator(mode="after")
    def validate_ids(self) -> CostResourceBinding:
        ClusterTarget(resource_id=self.cluster_resource_id)
        for value in (self.resource_id, self.cluster_resource_id, self.pool_resource_id):
            if value is not None:
                resource_subscription(value)
        return self


class AllocationShare(CostModel):
    row_id: Text
    fraction: Fraction = Field(gt=0)
    category: Attribution
    namespace: Text | None = None
    workload_uid: Text | None = None
    container: Text | None = None

    @model_validator(mode="after")
    def validate_target(self) -> AllocationShare:
        target = (self.namespace, self.workload_uid, self.container)
        if self.category == "allocated":
            if any(value is None for value in target):
                raise ValueError("allocated shares require exact workload and container identity")
        elif any(value is not None for value in target):
            raise ValueError("idle/system/unallocated shares cannot also target a workload")
        return self


class CostAllocation(CostModel):
    profile: Literal["reviewed-allocation-shares-v1"] = "reviewed-allocation-shares-v1"
    source: Literal["aks-cost-analysis", "opencost", "kubecost"]
    source_reference: Text
    basis: Literal["reviewed-shares"]
    shared_idle: Literal[False]
    period: CostPeriod
    shares: list[AllocationShare] = Field(max_length=100_000)


class CostImport(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    source_profile: Literal["azure-cost-details-projection-v1"]
    cost_basis: Literal["amortized"]
    tenant_id: UUID
    subscription_ids: list[UUID] = Field(min_length=1, max_length=1000)
    period: CostPeriod
    source_reference: Text
    source_observed_at: UtcDatetime
    export_complete: bool = Field(default=False, strict=True)
    rows: list[CostRow] = Field(max_length=100_000)
    bindings: list[CostResourceBinding] = Field(default_factory=list, max_length=100_000)
    allocation: CostAllocation | None = None

    @model_validator(mode="after")
    def validate_import(self) -> CostImport:
        from decimal import localcontext

        if len(set(self.subscription_ids)) != len(self.subscription_ids):
            raise ValueError("cost subscription scope must be distinct")
        if self.period.end > self.source_observed_at:
            raise ValueError("cost source observation must not precede the period end")
        rows = {row.id: row for row in self.rows}
        if len(rows) != len(self.rows):
            raise ValueError("cost row IDs must be distinct within the one source export")
        if len({item.resource_id for item in self.bindings}) != len(self.bindings):
            raise ValueError("cost resource bindings must be unambiguous")
        for row in self.rows:
            if row.subscription_id not in self.subscription_ids:
                raise ValueError("cost rows must belong to the approved subscription scope")
            if row.period.start < self.period.start or row.period.end > self.period.end:
                raise ValueError("cost row period must be contained in the export period")
        for binding in self.bindings:
            for value in (
                binding.resource_id,
                binding.cluster_resource_id,
                binding.pool_resource_id,
            ):
                if value is not None and resource_subscription(value) not in self.subscription_ids:
                    raise ValueError("cost bindings must stay within the approved subscriptions")
        if self.allocation is not None:
            seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
            totals: dict[str, Decimal] = {}
            with localcontext() as context:
                context.prec = 60
                for share in self.allocation.shares:
                    if share.row_id not in rows:
                        raise ValueError("allocation shares must reference an original cost row")
                    key = (
                        share.row_id,
                        share.category,
                        share.namespace,
                        share.workload_uid,
                        share.container,
                    )
                    if key in seen:
                        raise ValueError("duplicate allocation target for the same cost row")
                    seen.add(key)
                    totals[share.row_id] = totals.get(share.row_id, Decimal(0)) + share.fraction
                    if totals[share.row_id] > 1:
                        raise ValueError("allocation shares must not exceed the billed row")
        return self


class ReconciledShare(CostModel):
    original: AllocationShare
    amount: Decimal


class ReconciledCostRow(CostModel):
    original: CostRow
    binding: CostResourceBinding | None
    allocations: list[ReconciledShare]
    unallocated: Decimal
    issues: list[Text]


class CurrencyReconciliation(CostModel):
    currency: Currency
    total: Decimal
    positive_cost: Decimal
    matched: Decimal
    unmatched: Decimal
    allocated: Decimal
    allocation_coverage: Decimal | None
    by_charge: dict[ChargeCategory, Decimal]
    by_attribution: dict[Attribution, Decimal]


class CostReconciliation(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    evaluated_at: UtcDatetime
    input_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    snapshot_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    evidence: CostImport
    minimum_allocation_coverage: Fraction
    maximum_evidence_age_hours: Annotated[int, Field(gt=0, le=8760, strict=True)]
    status: Literal["reconciled", "blocked"]
    reason_codes: list[Text]
    rows: list[ReconciledCostRow]
    currencies: list[CurrencyReconciliation]
    estimated_monthly_savings: None = None
    notice: Literal[
        "Reconciled attribution is not avoidable cost, realized savings, "
        "source attestation or change approval."
    ] = (
        "Reconciled attribution is not avoidable cost, realized savings, "
        "source attestation or change approval."
    )

    @model_validator(mode="after")
    def validate_status(self) -> CostReconciliation:
        if (self.status == "blocked") != bool(self.reason_codes):
            raise ValueError("cost status must reflect every reconciliation gate")
        return self
