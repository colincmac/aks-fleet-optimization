from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from aks_fleet_efficiency.catalog import digest_json
from aks_fleet_efficiency.cost import (
    AllocationShare,
    Attribution,
    ChargeCategory,
    CostImport,
    CostReconciliation,
    CostResourceBinding,
    CurrencyReconciliation,
    ReconciledCostRow,
    ReconciledShare,
    resource_subscription,
)
from aks_fleet_efficiency.models import ClusterSnapshot, FleetSnapshot


def _binding_cluster(
    binding: CostResourceBinding | None, snapshot: FleetSnapshot
) -> ClusterSnapshot | None:
    if binding is None:
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
        prefix = f"{cluster.resource_id}/agentPools/"
        if (
            not binding.pool_resource_id.startswith(prefix)
            or "/" in binding.pool_resource_id[len(prefix) :]
        ):
            return None
        pools = [
            pool for pool in cluster.node_pools if pool.resource_id == binding.pool_resource_id
        ]
        if len(pools) != 1:
            return None
    return cluster


def _workload_matches(share: AllocationShare, cluster: ClusterSnapshot) -> bool:
    workloads = [
        item
        for item in cluster.workloads
        if item.namespace == share.namespace and item.uid == share.workload_uid
    ]
    return (
        len(workloads) == 1
        and sum(container.name == share.container for container in workloads[0].containers) == 1
    )


def _inventory_complete(snapshot: FleetSnapshot, as_of: datetime, maximum_age: timedelta) -> bool:
    manifest = snapshot.collection_manifest
    if manifest is None or not snapshot.clusters:
        return False
    if not timedelta(0) <= as_of - snapshot.generated_at <= maximum_age:
        return False
    for cluster in snapshot.clusters:
        for collector, scopes in (
            ("azure-inventory", {cluster.resource_id, cluster.subscription_id}),
            ("kubernetes-metadata", {cluster.resource_id}),
        ):
            receipts = [
                item
                for item in manifest.source_results
                if item.collector == collector and scopes.intersection(item.requested_scope)
            ]
            if len(receipts) != 1:
                return False
            receipt = receipts[0]
            if (
                receipt.status != "complete"
                or receipt.source_observed_at is None
                or not timedelta(0) <= as_of - receipt.source_observed_at <= maximum_age
                or receipt.completed_at > as_of
            ):
                return False
    return True


def _reconcile_rows(evidence: CostImport, snapshot: FleetSnapshot) -> list[ReconciledCostRow]:
    bindings = {item.resource_id: item for item in evidence.bindings}
    shares: dict[str, list[AllocationShare]] = {}
    if evidence.allocation is not None and evidence.allocation.period == evidence.period:
        for share in evidence.allocation.shares:
            shares.setdefault(share.row_id, []).append(share)
    result = []
    for row in sorted(evidence.rows, key=lambda item: item.id):
        issues = []
        binding = bindings.get(row.resource_id) if row.resource_id is not None else None
        cluster = _binding_cluster(binding, snapshot)
        if cluster is None:
            issues.append("resource-unmatched")
        if row.charge_type != "Usage" or row.amount < 0:
            issues.append("unsupported-charge")
        if (row.pricing_model == "Reservation" and not (row.reservation_id or row.benefit_id)) or (
            row.pricing_model == "SavingsPlan" and not row.benefit_id
        ):
            issues.append("benefit-metadata-missing")
        allocations = []
        for share in sorted(
            shares.get(row.id, []),
            key=lambda item: (
                item.category,
                item.namespace or "",
                item.workload_uid or "",
                item.container or "",
            ),
        ):
            if cluster is None or row.amount < 0 or row.charge_type != "Usage":
                continue
            if share.category == "allocated" and not _workload_matches(share, cluster):
                issues.append("workload-unmatched")
                continue
            allocations.append(ReconciledShare(original=share, amount=row.amount * share.fraction))
        allocated = sum((item.amount for item in allocations), Decimal(0))
        result.append(
            ReconciledCostRow(
                original=row,
                binding=binding if cluster is not None else None,
                allocations=allocations,
                unallocated=row.amount - allocated,
                issues=sorted(set(issues)),
            )
        )
    return result


def _currency_summary(currency: str, rows: list[ReconciledCostRow]) -> CurrencyReconciliation:
    selected = [item for item in rows if item.original.currency == currency]
    total = sum((item.original.amount for item in selected), Decimal(0))
    positive = sum((max(item.original.amount, Decimal(0)) for item in selected), Decimal(0))
    matched = sum(
        (item.original.amount for item in selected if item.binding is not None), Decimal(0)
    )
    by_charge: dict[ChargeCategory, Decimal] = {}
    by_attribution: dict[Attribution, Decimal] = {
        "allocated": Decimal(0),
        "idle": Decimal(0),
        "system": Decimal(0),
        "unallocated": Decimal(0),
    }
    for item in selected:
        category = item.original.charge_category
        by_charge[category] = by_charge.get(category, Decimal(0)) + item.original.amount
        by_attribution["unallocated"] += item.unallocated
        for allocation in item.allocations:
            by_attribution[allocation.original.category] += allocation.amount
    allocated = sum(
        (amount for category, amount in by_attribution.items() if category != "unallocated"),
        Decimal(0),
    )
    return CurrencyReconciliation(
        currency=currency,
        total=total,
        positive_cost=positive,
        matched=matched,
        unmatched=total - matched,
        allocated=allocated,
        allocation_coverage=allocated / positive if positive else None,
        by_charge=by_charge,
        by_attribution=by_attribution,
    )


class CostManagementCollector:
    """Reconcile one sanitized amortized export; no SDK, network or credentials."""

    def collect_costs(
        self,
        evidence: CostImport,
        snapshot: FleetSnapshot,
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
        manifest = snapshot.collection_manifest
        if manifest is not None and manifest.tenant_id != str(evidence.tenant_id):
            raise ValueError("cost and inventory tenant must match exactly")
        if any(
            cluster.subscription_id not in {str(value) for value in evidence.subscription_ids}
            for cluster in snapshot.clusters
        ):
            raise ValueError("snapshot subscriptions must belong to the cost import scope")
        reasons = []
        maximum_age = timedelta(hours=maximum_evidence_age_hours)
        if not evidence.export_complete:
            reasons.append("export-incomplete")
        if (
            evidence.period.start != snapshot.metric_window.start
            or evidence.period.end != snapshot.metric_window.end
        ):
            reasons.append("period-mismatch")
        if evidence.source_observed_at > as_of:
            reasons.append("cost-source-in-future")
        elif as_of - evidence.source_observed_at > maximum_age:
            reasons.append("cost-source-stale")
        if not _inventory_complete(snapshot, as_of, maximum_age):
            reasons.append("inventory-evidence-incomplete")
        if evidence.allocation is None:
            reasons.append("allocation-missing")
        elif evidence.allocation.period != evidence.period:
            reasons.append("allocation-period-mismatch")
        with localcontext() as context:
            # Bounded 30-digit amounts, 18-place shares and 100,000 rows fit exactly.
            context.prec = 60
            rows = _reconcile_rows(evidence, snapshot)
            currencies = [
                _currency_summary(currency, rows)
                for currency in sorted({item.original.currency for item in rows})
            ]
        if len(currencies) > 1:
            reasons.append("mixed-currency")
        if not currencies or any(item.positive_cost == 0 for item in currencies):
            reasons.append("no-positive-cost")
        for item in currencies:
            if (
                item.allocation_coverage is None
                or item.allocation_coverage < minimum_allocation_coverage
            ):
                reasons.append("allocation-coverage-below-threshold")
        reasons.extend(issue for row in rows for issue in row.issues)
        return CostReconciliation(
            evaluated_at=as_of,
            input_digest=digest_json(evidence.model_dump(mode="json")),
            snapshot_digest=digest_json(snapshot.model_dump(mode="json")),
            evidence=evidence,
            minimum_allocation_coverage=minimum_allocation_coverage,
            maximum_evidence_age_hours=maximum_evidence_age_hours,
            status="blocked" if reasons else "reconciled",
            reason_codes=sorted(set(reasons)),
            rows=rows,
            currencies=currencies,
        )
