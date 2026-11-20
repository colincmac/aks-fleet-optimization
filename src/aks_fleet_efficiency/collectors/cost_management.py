from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from aks_fleet_efficiency.catalog import digest_json, load_catalog
from aks_fleet_efficiency.catalog.models import FinancialSourceDefinition
from aks_fleet_efficiency.cost import (
    AggregateAllocation,
    AllocationShare,
    Attribution,
    ChargeCategory,
    CostBasis,
    CostImport,
    CostReconciliation,
    CostResourceBinding,
    CurrencyReconciliation,
    FinancialProfileReference,
    ReconciledCostRow,
    ReconciledShare,
    resource_subscription,
)
from aks_fleet_efficiency.models import ClusterSnapshot, FleetSnapshot

ProfileKind = Literal["ledger", "allocation"]


def _profile(
    reference: FinancialProfileReference, expected_kind: ProfileKind
) -> FinancialSourceDefinition | None:
    catalog = load_catalog()
    try:
        profile = catalog.financial_source(reference.id)
    except ValueError:
        return None
    if (
        profile.version != reference.version
        or profile.evidence_kind != expected_kind
        or not profile.supports_producer_version(reference.producer_version)
    ):
        return None
    return profile


def _binding_cluster(
    binding: CostResourceBinding | None, snapshot: FleetSnapshot | None
) -> ClusterSnapshot | None:
    if binding is None or snapshot is None:
        return None
    clusters = [
        item for item in snapshot.clusters if item.resource_id == binding.cluster_resource_id
    ]
    if len(clusters) != 1:
        return None
    cluster = clusters[0]
    if (
        cluster.uid != binding.cluster_uid
        or str(resource_subscription(cluster.resource_id)) != cluster.subscription_id
    ):
        return None
    if binding.pool_resource_id is not None:
        pools = [
            pool for pool in cluster.node_pools if pool.resource_id == binding.pool_resource_id
        ]
        if len(pools) != 1:
            return None
    return cluster


def _current_context_issues(
    binding: CostResourceBinding | None,
    shares: list[AllocationShare],
    snapshot: FleetSnapshot | None,
) -> list[str]:
    if snapshot is None:
        return []
    cluster = _binding_cluster(binding, snapshot)
    if cluster is None:
        return ["current-resource-not-observed"]
    for share in shares:
        if share.category != "allocated" or share.granularity not in {"workload", "container"}:
            continue
        workloads = [
            item
            for item in cluster.workloads
            if item.namespace == share.namespace and item.uid == share.workload_uid
        ]
        if len(workloads) != 1:
            return ["current-workload-not-observed"]
        if (
            share.granularity == "container"
            and sum(container.name == share.container for container in workloads[0].containers) != 1
        ):
            return ["current-container-not-observed"]
    return []


def _share_is_historical(share: AllocationShare, row_period: object) -> bool:
    return share.category != "allocated" or (
        share.identity_basis == "exact-historical"
        and share.valid_period is not None
        and share.valid_period.contains(row_period)  # type: ignore[arg-type]
    )


def _reconcile_rows(
    evidence: CostImport,
    snapshot: FleetSnapshot | None,
    allocation_profile: FinancialSourceDefinition | None,
) -> list[ReconciledCostRow]:
    bindings = {item.resource_id: item for item in evidence.bindings}
    shares: dict[str, list[AllocationShare]] = {}
    allocation = evidence.allocation
    shares_eligible = (
        allocation is not None
        and allocation.period == evidence.period
        and allocation.complete
        and allocation_profile is not None
        and allocation_profile.reconciliation == "ledger-row-partition"
        and bool(allocation.shares)
    )
    if shares_eligible and allocation is not None:
        for share in allocation.shares:
            shares.setdefault(share.row_id, []).append(share)
    result: list[ReconciledCostRow] = []
    for row in sorted(evidence.rows, key=lambda item: item.id):
        issues: list[str] = []
        binding = bindings.get(row.resource_id) if row.resource_id is not None else None
        if binding is None or not binding.valid_period.contains(row.period):
            issues.append("resource-unmatched")
        if row.charge_type != "Usage" or row.amount < 0:
            issues.append("unsupported-charge")
        if row.pricing_model in {None, "Other"}:
            issues.append("unsupported-pricing-model")
        if (row.pricing_model == "Reservation" and not (row.reservation_id or row.benefit_id)) or (
            row.pricing_model in {"SavingsPlan", "Committed"} and not row.benefit_id
        ):
            issues.append("benefit-metadata-missing")
        focus = row.focus
        if evidence.ledger_profile.id == "finops-focus" and focus is None:
            issues.append("focus-metadata-missing")
        if focus is not None:
            if focus.charge_class == "Correction" or focus.commitment_discount_status == "Unused":
                issues.append("unsupported-charge")
            if row.pricing_model == "Committed":
                if focus.commitment_discount_status is None:
                    issues.append("commitment-status-unknown")
                if (
                    focus.commitment_discount_category is None
                    or focus.commitment_discount_type is None
                ):
                    issues.append("benefit-metadata-missing")
            elif row.charge_type == "Usage" and any(
                value is not None
                for value in (
                    focus.commitment_discount_category,
                    focus.commitment_discount_id,
                    focus.commitment_discount_status,
                    focus.commitment_discount_type,
                )
            ):
                issues.append("focus-pricing-inconsistent")
        allocations: list[ReconciledShare] = []
        candidates = sorted(
            shares.get(row.id, []),
            key=lambda item: (
                item.category,
                item.namespace or "",
                item.workload_uid or "",
                item.container or "",
            ),
        )
        for share in candidates:
            if not _share_is_historical(share, row.period):
                issues.append("allocation-identity-insufficient")
            if (
                share.category == "allocated"
                and binding is not None
                and share.cluster_resource_id != binding.cluster_resource_id
            ):
                issues.append("allocation-cluster-mismatch")
        if not issues:
            allocations = [
                ReconciledShare(original=share, amount=row.amount * share.fraction)
                for share in candidates
            ]
        attributed = sum((item.amount for item in allocations), Decimal(0))
        result.append(
            ReconciledCostRow(
                original=row,
                binding=binding if "resource-unmatched" not in issues else None,
                allocations=allocations,
                unallocated=row.amount - attributed,
                issues=sorted(set(issues)),
                current_context_issues=_current_context_issues(binding, candidates, snapshot),
            )
        )
    return result


def _currency_summary(
    currency: str,
    basis: CostBasis,
    rows: list[ReconciledCostRow],
    aggregates: list[AggregateAllocation],
) -> CurrencyReconciliation:
    selected = [item for item in rows if item.original.currency == currency]
    total = sum((item.original.amount for item in selected), Decimal(0))
    positive = sum((max(item.original.amount, Decimal(0)) for item in selected), Decimal(0))
    matched = sum(
        (item.original.amount for item in selected if item.binding is not None), Decimal(0)
    )
    by_charge: dict[ChargeCategory, Decimal] = {}
    by_source: dict[str, Decimal] = {}
    by_attribution: dict[Attribution, Decimal] = {
        "allocated": Decimal(0),
        "idle": Decimal(0),
        "shared": Decimal(0),
        "system": Decimal(0),
        "unallocated": Decimal(0),
    }
    aggregate_by_attribution: dict[Attribution, Decimal] = {
        "allocated": Decimal(0),
        "idle": Decimal(0),
        "shared": Decimal(0),
        "system": Decimal(0),
        "unallocated": Decimal(0),
    }
    for item in selected:
        category = item.original.charge_category
        by_charge[category] = by_charge.get(category, Decimal(0)) + item.original.amount
        source_category = item.original.source_category
        by_source[source_category] = (
            by_source.get(source_category, Decimal(0)) + item.original.amount
        )
        by_attribution["unallocated"] += item.unallocated
        for allocation in item.allocations:
            by_attribution[allocation.original.category] += allocation.amount
    for aggregate in aggregates:
        if aggregate.currency == currency:
            aggregate_by_attribution[aggregate.category] += aggregate.amount
    allocated = sum(
        (amount for category, amount in by_attribution.items() if category != "unallocated"),
        Decimal(0),
    )
    return CurrencyReconciliation(
        currency=currency,
        cost_basis=basis,
        total=total,
        positive_cost=positive,
        matched=matched,
        unmatched=total - matched,
        allocated=allocated,
        allocation_coverage=allocated / positive if positive else None,
        by_charge=by_charge,
        by_source_category=by_source,
        by_attribution=by_attribution,
        aggregate_by_attribution=aggregate_by_attribution,
    )


class CostManagementCollector:
    """Reconcile sanitized saved financial evidence; no SDK, network, or credentials."""

    def collect_costs(
        self,
        evidence: CostImport,
        snapshot: FleetSnapshot | None = None,
        *,
        as_of: datetime,
        minimum_allocation_coverage: Decimal = Decimal("0.95"),
        maximum_evidence_age_hours: int = 24,
    ) -> CostReconciliation:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("cost evaluation time must be timezone-aware")
        if (
            not isinstance(minimum_allocation_coverage, Decimal)
            or not minimum_allocation_coverage.is_finite()
            or not 0 <= minimum_allocation_coverage <= 1
        ):
            raise ValueError("allocation coverage must be a finite Decimal from zero to one")
        if (
            type(maximum_evidence_age_hours) is not int
            or not 0 < maximum_evidence_age_hours <= 8760
        ):
            raise ValueError("maximum evidence age must be an integer from 1 to 8760 hours")
        if snapshot is not None:
            manifest = snapshot.collection_manifest
            if manifest is not None and manifest.tenant_id != str(evidence.tenant_id):
                raise ValueError("cost and inventory tenant must match exactly")
            if any(
                cluster.subscription_id not in {str(item) for item in evidence.subscription_ids}
                for cluster in snapshot.clusters
            ):
                raise ValueError("snapshot subscriptions must belong to the cost import scope")

        fatal: list[str] = []
        attribution_only: list[str] = []
        maximum_age = timedelta(hours=maximum_evidence_age_hours)
        ledger_profile = _profile(evidence.ledger_profile, "ledger")
        if ledger_profile is None or ledger_profile.cost_basis not in {
            evidence.cost_basis,
            "source-declared",
        }:
            fatal.append("ledger-source-profile-unsupported")
        if not evidence.export_complete:
            fatal.append("export-incomplete")
        if evidence.source_observed_at > as_of:
            fatal.append("cost-source-in-future")
        elif as_of - evidence.source_observed_at > maximum_age:
            fatal.append("cost-source-stale")

        allocation_profile: FinancialSourceDefinition | None = None
        if evidence.allocation is None:
            fatal.append("allocation-missing")
        else:
            allocation = evidence.allocation
            allocation_profile = _profile(allocation.profile, "allocation")
            if allocation_profile is None:
                fatal.append("allocation-source-profile-unsupported")
            elif (
                allocation_profile.pricing_provenance == "reviewed"
                and allocation.pricing_basis != "billing-ledger"
            ):
                fatal.append("allocation-pricing-unverified")
            if allocation.period != evidence.period:
                fatal.append("allocation-period-mismatch")
            if allocation.cost_basis != evidence.cost_basis:
                fatal.append("allocation-cost-basis-mismatch")
            if not allocation.complete:
                fatal.append("allocation-incomplete")
            if allocation.amounts:
                attribution_only.append("aggregate-allocation-not-ledger-partition")
            elif (
                allocation_profile is not None
                and allocation_profile.reconciliation != "ledger-row-partition"
            ):
                attribution_only.append("allocation-source-cannot-partition-ledger")

        rows = _reconcile_rows(evidence, snapshot, allocation_profile)
        aggregates = evidence.allocation.amounts if evidence.allocation is not None else []
        currencies = sorted(
            {item.original.currency for item in rows} | {item.currency for item in aggregates}
        )
        summaries = [
            _currency_summary(currency, evidence.cost_basis, rows, aggregates)
            for currency in currencies
        ]
        if len(currencies) > 1:
            fatal.append("mixed-currency")
        if not summaries or all(item.positive_cost == 0 for item in summaries):
            fatal.append("no-positive-cost")
        if evidence.allocation is not None and evidence.allocation.shares:
            if any(
                item.allocation_coverage is None
                or item.allocation_coverage < minimum_allocation_coverage
                for item in summaries
            ):
                fatal.append("allocation-coverage-below-threshold")
        fatal.extend(issue for row in rows for issue in row.issues)
        if evidence.cost_basis == "actual":
            attribution_only.append("actual-cost-not-financially-reconciled")

        fatal = sorted(set(fatal))
        attribution_only = sorted(set(attribution_only))
        status: Literal["reconciled", "attributed", "blocked"]
        if fatal:
            status = "blocked"
        elif attribution_only:
            status = "attributed"
        else:
            status = "reconciled"
        return CostReconciliation(
            evaluated_at=as_of,
            input_digest=digest_json(evidence.model_dump(mode="json")),
            snapshot_digest=(
                digest_json(snapshot.model_dump(mode="json")) if snapshot is not None else None
            ),
            ledger_source=ledger_profile,
            allocation_source=allocation_profile,
            evidence=evidence,
            minimum_allocation_coverage=minimum_allocation_coverage,
            maximum_evidence_age_hours=maximum_evidence_age_hours,
            status=status,
            reason_codes=fatal or attribution_only,
            rows=rows,
            aggregate_allocations=aggregates,
            currencies=summaries,
        )
