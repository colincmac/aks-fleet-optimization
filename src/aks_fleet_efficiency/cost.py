from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from math import isfinite
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from aks_fleet_efficiency.catalog import load_catalog
from aks_fleet_efficiency.catalog.models import FinancialSourceDefinition, FinancialSourceVersion
from aks_fleet_efficiency.config import ClusterTarget
from aks_fleet_efficiency.models import UtcDatetime

Text = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"\S")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
ChargeCategory = Literal["compute", "storage", "network", "service", "other"]
Attribution = Literal["allocated", "idle", "shared", "system", "unallocated"]
CostBasis = Literal["actual", "amortized", "effective"]
Granularity = Literal["resource", "cluster", "namespace", "workload", "container", "asset"]
IdentityBasis = Literal["exact-historical", "current-only", "name-only"]


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

    def contains(self, other: CostPeriod) -> bool:
        return self.start <= other.start and self.end >= other.end


class FinancialProfileReference(CostModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    producer_version: FinancialSourceVersion


class FocusChargeMetadata(CostModel):
    charge_category: Literal["Usage", "Purchase", "Tax", "Credit", "Adjustment"]
    pricing_category: Literal["Standard", "Dynamic", "Committed", "Other"] | None
    charge_class: Literal["Correction"] | None = None
    commitment_discount_category: Literal["Usage", "Spend"] | None = None
    commitment_discount_id: Text | None = None
    commitment_discount_status: Literal["Used", "Unused"] | None = None
    commitment_discount_type: Text | None = None

    @model_validator(mode="after")
    def validate_pricing_category(self) -> FocusChargeMetadata:
        if self.charge_category == "Tax" and self.pricing_category is not None:
            raise ValueError("FOCUS tax pricing category must be null")
        if (
            self.charge_category in {"Usage", "Purchase"}
            and self.charge_class != "Correction"
            and self.pricing_category is None
        ):
            raise ValueError("FOCUS usage and purchase require a pricing category")
        return self


class CostRow(CostModel):
    id: Text
    subscription_id: UUID
    resource_id: Text | None
    period: CostPeriod
    amount: Money
    currency: Currency
    charge_category: ChargeCategory
    source_category: Text
    charge_type: Literal[
        "Usage",
        "Purchase",
        "Refund",
        "UnusedReservation",
        "UnusedSavingsPlan",
        "RoundingAdjustment",
        "Tax",
        "Credit",
        "Adjustment",
    ]
    pricing_model: (
        Literal["OnDemand", "Reservation", "SavingsPlan", "Spot", "Dynamic", "Committed", "Other"]
        | None
    )
    benefit_id: Text | None = None
    reservation_id: Text | None = None
    focus: FocusChargeMetadata | None = None

    @model_validator(mode="after")
    def validate_resource_scope(self) -> CostRow:
        if (
            self.resource_id is not None
            and resource_subscription(self.resource_id) != self.subscription_id
        ):
            raise ValueError("cost row resource must belong to its declared subscription")
        if self.focus is not None:
            pricing = (
                "OnDemand"
                if self.focus.pricing_category == "Standard"
                else self.focus.pricing_category
            )
            if (
                self.charge_type != self.focus.charge_category
                or self.pricing_model != pricing
                or self.benefit_id != self.focus.commitment_discount_id
            ):
                raise ValueError(
                    "normalized financial fields must match the retained FOCUS metadata"
                )
        return self


class CostResourceBinding(CostModel):
    resource_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    pool_resource_id: Text | None = None
    valid_period: CostPeriod
    identity_basis: Literal["exact-historical"]
    reference: Text

    @model_validator(mode="after")
    def validate_ids(self) -> CostResourceBinding:
        ClusterTarget(resource_id=self.cluster_resource_id)
        for value in (self.resource_id, self.cluster_resource_id, self.pool_resource_id):
            if value is not None:
                resource_subscription(value)
        return self


class TargetedAttribution(CostModel):
    category: Attribution
    granularity: Granularity | None = None
    cluster_resource_id: Text | None = None
    namespace: Text | None = None
    workload_name: Text | None = None
    workload_uid: Text | None = None
    container: Text | None = None
    asset_id: Text | None = None
    identity_basis: IdentityBasis | None = None
    valid_period: CostPeriod | None = None
    reference: Text | None = None

    @model_validator(mode="after")
    def validate_target(self) -> TargetedAttribution:
        target = (
            self.granularity,
            self.cluster_resource_id,
            self.namespace,
            self.workload_name,
            self.workload_uid,
            self.container,
            self.asset_id,
            self.identity_basis,
            self.valid_period,
            self.reference,
        )
        if self.category != "allocated":
            if any(value is not None for value in target):
                raise ValueError("nonallocated attribution cannot also target a resource")
            return self
        if self.granularity is None or self.cluster_resource_id is None:
            raise ValueError("allocated attribution requires a granularity and cluster identity")
        ClusterTarget(resource_id=self.cluster_resource_id)
        if self.granularity in {"namespace", "workload", "container"} and self.namespace is None:
            raise ValueError("namespace, workload, and container attribution require a namespace")
        if self.granularity in {"workload", "container"} and self.workload_name is None:
            raise ValueError("workload and container attribution require a workload name")
        if self.granularity == "container" and self.container is None:
            raise ValueError("container attribution requires a container name")
        if self.granularity == "asset" and self.asset_id is None:
            raise ValueError("asset attribution requires an asset identity")
        if self.identity_basis is None or self.reference is None:
            raise ValueError("allocated attribution requires identity basis and source reference")
        if self.identity_basis == "exact-historical":
            if self.valid_period is None:
                raise ValueError("historical attribution requires a validity period")
            if self.granularity in {"workload", "container"} and self.workload_uid is None:
                raise ValueError("historical workload attribution requires a workload UID")
        elif self.workload_uid is not None:
            raise ValueError(
                "current or name-only attribution cannot claim historical workload UID"
            )
        return self


class AllocationShare(TargetedAttribution):
    row_id: Text
    fraction: Fraction = Field(gt=0)


class AggregateAllocation(TargetedAttribution):
    amount: Money
    currency: Currency


class CostAllocation(CostModel):
    profile: FinancialProfileReference
    source_reference: Text
    cost_basis: CostBasis
    pricing_basis: Literal["billing-ledger", "source-declared"] = "source-declared"
    period: CostPeriod
    complete: bool = Field(strict=True)
    allocation_policy: Literal["not-shared", "source-native"]
    shares: list[AllocationShare] = Field(default_factory=list, max_length=100_000)
    amounts: list[AggregateAllocation] = Field(default_factory=list, max_length=100_000)

    @model_validator(mode="after")
    def validate_shape(self) -> CostAllocation:
        if bool(self.shares) == bool(self.amounts):
            raise ValueError("allocation requires exactly one of row shares or aggregate amounts")
        if self.shares and self.allocation_policy != "not-shared":
            raise ValueError("row shares must preserve explicit idle and shared attribution")
        if self.amounts and self.allocation_policy != "source-native":
            raise ValueError("aggregate amounts require their source-native allocation policy")
        return self


class AllocationObservation(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    subscription_id: UUID
    cluster_resource_id: Text
    cluster_uid: Text
    source_observed_at: UtcDatetime
    binding_reference: Text
    allocation: CostAllocation

    @model_validator(mode="after")
    def validate_scope(self) -> AllocationObservation:
        ClusterTarget(resource_id=self.cluster_resource_id)
        if resource_subscription(self.cluster_resource_id) != self.subscription_id:
            raise ValueError("allocation observation subscription binding is invalid")
        if self.source_observed_at < self.allocation.period.end:
            raise ValueError("allocation source observation precedes the source period")
        if self.allocation.shares:
            raise ValueError("row allocation requires an authoritative ledger")
        if any(
            item.cluster_resource_id is not None
            and item.cluster_resource_id != self.cluster_resource_id
            for item in self.allocation.amounts
        ):
            raise ValueError("allocation targets must remain within the declared cluster")
        return self


class AllocationContext(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    observation: AllocationObservation
    requested_period: CostPeriod
    evaluated_at: UtcDatetime
    status: Literal["qualified", "blocked"]
    reason_codes: list[
        Literal[
            "allocation_source_future",
            "allocation_source_stale",
            "allocation_period_mismatch",
            "allocation_incomplete",
            "allocation_profile_unsupported",
            "allocation_pricing_unsupported",
            "allocation_negative_amount",
        ]
    ]
    estimated_monthly_savings: None = None

    @model_validator(mode="after")
    def validate_status(self) -> AllocationContext:
        if (self.status == "blocked") != bool(self.reason_codes):
            raise ValueError("allocation context status must reflect its qualification gaps")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("allocation context reasons must be distinct")
        return self


class ClusterCostReviewRow(CostModel):
    context: AllocationContext
    allocated_amount: Money = Field(ge=0)
    currency: Currency
    nonallocated_amounts: list[AggregateAllocation]


class ClusterCostReviewOrder(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    evaluated_at: UtcDatetime
    period: CostPeriod
    profile: FinancialProfileReference
    source_reference: Text
    cost_basis: CostBasis
    pricing_basis: Literal["billing-ledger", "source-declared"]
    currency: Currency
    rows: list[ClusterCostReviewRow] = Field(min_length=2, max_length=1000)
    original_assessment_run_ids: dict[Text, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]] = (
        Field(default_factory=dict)
    )
    maximum_evidence_age_hours: float = Field(gt=0)
    engineering_order_changed: Literal[False] = False
    estimated_monthly_savings: None = None
    scope_notice: Literal[
        "source-native cluster review order; not reconciliation, savings or engineering priority"
    ] = "source-native cluster review order; not reconciliation, savings or engineering priority"


def order_cluster_cost_reviews(
    contexts: list[AllocationContext], *, maximum_evidence_age_hours: float = 24
) -> ClusterCostReviewOrder:
    if not 2 <= len(contexts) <= 1000:
        raise ValueError("Cost review ordering requires two to 1000 exact cluster contexts")
    contexts = [AllocationContext.model_validate(item.model_dump()) for item in contexts]
    first = contexts[0]
    baseline = first.observation.allocation
    rows = []
    clusters: set[str] = set()
    fingerprints: set[str] = set()
    currencies: set[str] = set()
    for context in contexts:
        observation = context.observation
        allocation = observation.allocation
        if (
            observation.tenant_id != first.observation.tenant_id
            or context.evaluated_at != first.evaluated_at
            or context.requested_period != first.requested_period
            or allocation.profile != baseline.profile
            or allocation.source_reference != baseline.source_reference
            or allocation.cost_basis != baseline.cost_basis
            or allocation.pricing_basis != baseline.pricing_basis
        ):
            raise ValueError(
                "Cost review contexts require one declared source, profile, period, "
                "clock and pricing basis"
            )
        qualified = qualify_allocation_observation(
            observation,
            tenant_id=str(first.observation.tenant_id),
            cluster_resource_id=observation.cluster_resource_id,
            cluster_uid=observation.cluster_uid,
            period=first.requested_period,
            as_of=first.evaluated_at,
            maximum_evidence_age_hours=maximum_evidence_age_hours,
        )
        if qualified.status != "qualified" or context.status != "qualified":
            raise ValueError("Cost review ordering refuses blocked allocation context")
        if observation.cluster_resource_id in clusters or observation.cluster_uid in fingerprints:
            raise ValueError(
                "Cost review ordering refuses overlapping or recreated cluster contexts"
            )
        clusters.add(observation.cluster_resource_id)
        fingerprints.add(observation.cluster_uid)
        allocated = [item for item in allocation.amounts if item.category == "allocated"]
        if len(allocated) != 1:
            raise ValueError(
                "Cost review requires exactly one nonoverlapping cluster allocated amount"
            )
        amount = allocated[0]
        if (
            amount.granularity != "cluster"
            or amount.cluster_resource_id != observation.cluster_resource_id
            or amount.identity_basis not in {"current-only", "exact-historical"}
            or any(
                value is not None
                for value in (
                    amount.namespace,
                    amount.workload_name,
                    amount.workload_uid,
                    amount.container,
                    amount.asset_id,
                )
            )
            or (amount.valid_period is not None and amount.valid_period != allocation.period)
        ):
            raise ValueError(
                "Cost review refuses mixed grains or unresolved exact cluster attribution"
            )
        currencies.update(item.currency for item in allocation.amounts)
        rows.append(
            ClusterCostReviewRow(
                context=qualified,
                allocated_amount=amount.amount,
                currency=amount.currency,
                nonallocated_amounts=[
                    item for item in allocation.amounts if item.category != "allocated"
                ],
            )
        )
    if len(currencies) != 1:
        raise ValueError("Cost review ordering requires one explicit currency across all buckets")
    rows.sort(
        key=lambda item: (
            item.context.observation.cluster_resource_id,
            item.context.observation.cluster_uid,
        )
    )
    rows.sort(key=lambda item: item.allocated_amount, reverse=True)
    return ClusterCostReviewOrder(
        tenant_id=first.observation.tenant_id,
        evaluated_at=first.evaluated_at,
        period=first.requested_period,
        profile=baseline.profile,
        source_reference=baseline.source_reference,
        cost_basis=baseline.cost_basis,
        pricing_basis=baseline.pricing_basis,
        currency=rows[0].currency,
        rows=rows,
        maximum_evidence_age_hours=maximum_evidence_age_hours,
    )


def qualify_allocation_observation(
    observation: AllocationObservation,
    *,
    tenant_id: str,
    cluster_resource_id: str,
    cluster_uid: str,
    period: CostPeriod,
    as_of: datetime,
    maximum_evidence_age_hours: float = 24,
) -> AllocationContext:
    observation = AllocationObservation.model_validate(observation.model_dump())
    period = CostPeriod.model_validate(period.model_dump())
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("allocation context requires an aware evaluation clock")
    evaluated_at = as_of.astimezone(UTC)
    if (
        isinstance(maximum_evidence_age_hours, bool)
        or not isinstance(maximum_evidence_age_hours, (int, float))
        or not isfinite(maximum_evidence_age_hours)
        or maximum_evidence_age_hours <= 0
    ):
        raise ValueError("allocation freshness must be positive finite hours")
    if (
        observation.tenant_id != UUID(tenant_id)
        or observation.cluster_resource_id != cluster_resource_id
        or observation.cluster_uid != cluster_uid
    ):
        raise ValueError("allocation observation does not match the requested exact scope")
    reasons: list[str] = []
    allocation = observation.allocation
    if observation.source_observed_at > evaluated_at:
        reasons.append("allocation_source_future")
    elif (
        evaluated_at - observation.source_observed_at
    ).total_seconds() > maximum_evidence_age_hours * 3600:
        reasons.append("allocation_source_stale")
    if allocation.period != period:
        reasons.append("allocation_period_mismatch")
    if not allocation.complete:
        reasons.append("allocation_incomplete")
    profiles = load_catalog().financial_sources
    reference = allocation.profile
    profile = profiles.get(reference.id)
    if (
        profile is None
        or profile.evidence_kind != "allocation"
        or profile.reconciliation != "aggregate-attribution"
        or profile.version != reference.version
        or not profile.supports_producer_version(reference.producer_version)
        or profile.cost_basis not in {"source-declared", allocation.cost_basis}
    ):
        reasons.append("allocation_profile_unsupported")
    if allocation.pricing_basis != "billing-ledger" and (
        profile is None or profile.provider != "aks-cost-analysis"
    ):
        reasons.append("allocation_pricing_unsupported")
    if any(item.amount < 0 for item in allocation.amounts):
        reasons.append("allocation_negative_amount")
    return AllocationContext.model_validate(
        {
            "observation": observation,
            "requested_period": period,
            "evaluated_at": evaluated_at,
            "status": "blocked" if reasons else "qualified",
            "reason_codes": sorted(reasons),
        }
    )


class CostExportFile(CostModel):
    partition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=0, strict=True)
    row_count: int = Field(ge=0, strict=True)


class CostExportProvenance(CostModel):
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: list[CostExportFile] = Field(min_length=1, max_length=100)
    effective_cost_totals: dict[Currency, Money] = Field(min_length=1, max_length=100)


class CostImport(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    ledger_profile: FinancialProfileReference
    cost_basis: CostBasis
    tenant_id: UUID
    subscription_ids: list[UUID] = Field(min_length=1, max_length=1000)
    period: CostPeriod
    source_reference: Text
    source_observed_at: UtcDatetime
    export_complete: bool = Field(default=False, strict=True)
    rows: list[CostRow] = Field(max_length=100_000)
    bindings: list[CostResourceBinding] = Field(default_factory=list, max_length=100_000)
    allocation: CostAllocation | None = None
    export_provenance: CostExportProvenance | None = None

    @model_validator(mode="after")
    def validate_import(self) -> CostImport:
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
            if not self.period.contains(row.period):
                raise ValueError("cost row period must be contained in the export period")
        for binding in self.bindings:
            if not binding.valid_period.contains(self.period):
                raise ValueError("historical resource binding must cover the cost period")
            for value in (
                binding.resource_id,
                binding.cluster_resource_id,
                binding.pool_resource_id,
            ):
                if value is not None and resource_subscription(value) not in self.subscription_ids:
                    raise ValueError("cost bindings must stay within the approved subscriptions")
        if self.allocation is not None:
            for target in self.allocation.shares or self.allocation.amounts:
                if (
                    target.cluster_resource_id is not None
                    and resource_subscription(target.cluster_resource_id)
                    not in self.subscription_ids
                ):
                    raise ValueError(
                        "allocation targets must stay within the approved subscriptions"
                    )
        if self.allocation is not None and self.allocation.shares:
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
    current_context_issues: list[Text]


class CurrencyReconciliation(CostModel):
    currency: Currency
    cost_basis: CostBasis
    total: Decimal
    positive_cost: Decimal
    matched: Decimal
    unmatched: Decimal
    allocated: Decimal
    allocation_coverage: Decimal | None
    by_charge: dict[ChargeCategory, Decimal]
    by_source_category: dict[str, Decimal]
    by_attribution: dict[Attribution, Decimal]
    aggregate_by_attribution: dict[Attribution, Decimal]


class CostReconciliation(CostModel):
    schema_version: Literal["1.0"] = "1.0"
    evaluated_at: UtcDatetime
    input_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    snapshot_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    ledger_source: FinancialSourceDefinition | None
    allocation_source: FinancialSourceDefinition | None
    evidence: CostImport
    minimum_allocation_coverage: Fraction
    maximum_evidence_age_hours: Annotated[int, Field(gt=0, le=8760, strict=True)]
    status: Literal["reconciled", "attributed", "blocked"]
    reason_codes: list[Text]
    rows: list[ReconciledCostRow]
    aggregate_allocations: list[AggregateAllocation]
    currencies: list[CurrencyReconciliation]
    estimated_monthly_savings: None = None
    notice: Literal[
        "Cost attribution is not avoidable cost, realized savings, "
        "source attestation or change approval."
    ] = (
        "Cost attribution is not avoidable cost, realized savings, "
        "source attestation or change approval."
    )

    @model_validator(mode="after")
    def validate_status(self) -> CostReconciliation:
        if self.status == "reconciled" and self.reason_codes:
            raise ValueError("reconciled cost status cannot retain blocking or attribution reasons")
        if self.status != "reconciled" and not self.reason_codes:
            raise ValueError("non-reconciled cost status requires explicit reasons")
        return self
