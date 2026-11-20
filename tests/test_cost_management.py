from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.cost_management import CostManagementCollector
from aks_fleet_efficiency.cost import CostImport, CostReconciliation
from aks_fleet_efficiency.models import FleetSnapshot

TENANT = "00000000-0000-0000-0000-000000000000"
SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/providers/"
    "Microsoft.ContainerService/managedClusters/aks-synthetic"
)
POOL = f"{CLUSTER}/agentPools/apps"
RESOURCE = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-nodes/providers/"
    "Microsoft.Compute/virtualMachineScaleSets/synthetic"
)
START = "2026-09-29T00:00:00Z"
END = "2026-10-29T00:00:00Z"
AS_OF = datetime.fromisoformat("2026-10-29T12:00:00+00:00")


def test_financial_contracts_use_first_release_advisor_versions() -> None:
    from aks_fleet_efficiency.catalog import load_catalog
    from aks_fleet_efficiency.cost import (
        AllocationContext,
        AllocationObservation,
        ClusterCostReviewOrder,
    )
    from aks_fleet_efficiency.cost_sources.azure import AzureCostDetailsProjection
    from aks_fleet_efficiency.cost_sources.focus import FocusProjection

    for model in [
        CostImport,
        CostReconciliation,
        AllocationContext,
        AllocationObservation,
        ClusterCostReviewOrder,
    ]:
        assert model.model_fields["schema_version"].default == "1.0"
    assert (
        AzureCostDetailsProjection.model_json_schema()["properties"]["schema_version"]["const"]
        == "azure-cost-details-projection-v1"
    )
    assert (
        FocusProjection.model_json_schema()["properties"]["schema_version"]["const"]
        == "finops-focus-projection-v1"
    )
    assert all(
        source.projection_format.endswith("-v1")
        for source in load_catalog().financial_sources.values()
    )


def snapshot_payload() -> dict[str, Any]:
    payload = json.loads(Path("examples/fixtures/cost-snapshot.json").read_text(encoding="utf-8"))
    payload["metric_window"]["start"] = "2026-10-01T00:00:00Z"
    return payload


def import_payload(*, basis: str = "amortized") -> dict[str, Any]:
    period = {"start": START, "end": END}
    return {
        "schema_version": "1.0",
        "ledger_profile": {
            "id": "azure-cost-details-amortized",
            "version": "1.0.0",
            "producer_version": "2025.05.01",
        },
        "cost_basis": basis,
        "tenant_id": TENANT,
        "subscription_ids": [SUBSCRIPTION],
        "period": period,
        "source_reference": "synthetic-export",
        "source_observed_at": END,
        "export_complete": True,
        "rows": [
            {
                "id": "row-1",
                "subscription_id": SUBSCRIPTION,
                "resource_id": RESOURCE,
                "period": period,
                "amount": "100.00",
                "currency": "USD",
                "charge_category": "compute",
                "source_category": "Compute",
                "charge_type": "Usage",
                "pricing_model": "Reservation",
                "benefit_id": "synthetic-reservation",
            }
        ],
        "bindings": [
            {
                "resource_id": RESOURCE,
                "cluster_resource_id": CLUSTER,
                "cluster_uid": "cluster-uid",
                "pool_resource_id": POOL,
                "valid_period": period,
                "identity_basis": "exact-historical",
                "reference": "synthetic-historical-binding",
            }
        ],
        "allocation": {
            "profile": {
                "id": "reviewed-allocation-shares",
                "version": "1.0.0",
                "producer_version": "1.0.0",
            },
            "source_reference": "synthetic-reviewed-shares",
            "cost_basis": basis,
            "period": period,
            "complete": True,
            "allocation_policy": "not-shared",
            "shares": [
                {
                    "row_id": "row-1",
                    "fraction": "0.60",
                    "category": "allocated",
                    "granularity": "container",
                    "cluster_resource_id": CLUSTER,
                    "namespace": "apps",
                    "workload_name": "synthetic",
                    "workload_uid": "workload-uid",
                    "container": "app",
                    "identity_basis": "exact-historical",
                    "valid_period": period,
                    "reference": "synthetic-workload-history",
                },
                {"row_id": "row-1", "fraction": "0.25", "category": "idle"},
                {"row_id": "row-1", "fraction": "0.15", "category": "system"},
            ],
            "amounts": [],
        },
    }


def actual_payload() -> dict[str, Any]:
    payload = import_payload(basis="actual")
    payload["ledger_profile"] = {
        "id": "azure-cost-details-actual",
        "version": "1.0.0",
        "producer_version": "2025.05.01",
    }
    payload["allocation"] = {
        "profile": {
            "id": "aks-cost-analysis",
            "version": "1.0.0",
            "producer_version": "1.0.0",
        },
        "source_reference": "synthetic-aks-cost-analysis",
        "cost_basis": "actual",
        "period": payload["period"],
        "complete": True,
        "allocation_policy": "source-native",
        "shares": [],
        "amounts": [
            {
                "amount": "60",
                "currency": "USD",
                "category": "allocated",
                "granularity": "namespace",
                "cluster_resource_id": CLUSTER,
                "namespace": "apps",
                "identity_basis": "name-only",
                "reference": "synthetic-aks-cost-analysis",
            }
        ],
    }
    return payload


def reconcile(
    payload: dict[str, Any] | None = None, snapshot: dict[str, Any] | None = None, **kwargs: Any
) -> CostReconciliation:
    return CostManagementCollector().collect_costs(
        CostImport.model_validate(payload if payload is not None else import_payload()),
        FleetSnapshot.model_validate(snapshot) if snapshot is not None else None,
        as_of=AS_OF,
        **kwargs,
    )


@pytest.mark.parametrize("schema_version", ["2.0", "1.1", "latest"])
def test_cost_import_rejects_noninitial_schema_versions(schema_version: str) -> None:
    payload = import_payload()
    CostImport.model_validate(payload)
    payload["schema_version"] = schema_version
    with pytest.raises(ValidationError) as error:
        CostImport.model_validate(payload)
    assert [item["loc"] for item in error.value.errors()] == [("schema_version",)]


def test_first_release_amortized_row_partition_reconciles() -> None:
    result = reconcile(snapshot=snapshot_payload())
    assert result.schema_version == "1.0"
    assert result.status == "reconciled"
    assert result.reason_codes == []
    assert result.snapshot_digest is not None
    summary = result.currencies[0]
    assert summary.cost_basis == "amortized"
    assert summary.total == Decimal("100.00")
    assert summary.by_charge == {"compute": Decimal("100.00")}
    assert summary.by_attribution == {
        "allocated": Decimal("60"),
        "idle": Decimal("25"),
        "shared": Decimal("0"),
        "system": Decimal("15"),
        "unallocated": Decimal("0"),
    }
    assert result.estimated_monthly_savings is None
    assert CostReconciliation.model_validate_json(result.model_dump_json()) == result


def test_actual_cost_is_preserved_as_attributed_not_reconciled() -> None:
    payload = actual_payload()
    result = reconcile(payload)
    assert result.status == "attributed"
    assert "actual-cost-not-financially-reconciled" in result.reason_codes
    assert result.currencies[0].total == Decimal("100.00")
    assert result.estimated_monthly_savings is None


def test_cost_period_is_independent_of_metric_window() -> None:
    result = reconcile(snapshot=snapshot_payload())
    assert result.status == "reconciled"
    assert "period-mismatch" not in result.reason_codes


def test_deleted_current_workload_does_not_erase_historical_attribution() -> None:
    snapshot = snapshot_payload()
    snapshot["clusters"][0]["workloads"] = []
    result = reconcile(snapshot=snapshot)
    assert result.status == "reconciled"
    assert result.rows[0].current_context_issues == ["current-workload-not-observed"]
    assert result.currencies[0].by_attribution["allocated"] == Decimal("60")


def test_historical_allocation_reconciles_without_current_inventory() -> None:
    result = reconcile()
    assert result.status == "reconciled"
    assert result.snapshot_digest is None
    assert result.rows[0].current_context_issues == []
    assert result.currencies[0].by_attribution["allocated"] == Decimal("60")
    assert result.estimated_monthly_savings is None


@pytest.mark.parametrize("allocation_kind", ["shares", "amounts"])
def test_allocation_targets_reject_unapproved_subscriptions(allocation_kind: str) -> None:
    payload = import_payload() if allocation_kind == "shares" else actual_payload()
    payload["allocation"][allocation_kind][0]["cluster_resource_id"] = CLUSTER.replace(
        SUBSCRIPTION, "11111111-1111-1111-1111-111111111111"
    )
    with pytest.raises(ValidationError, match="allocation targets must stay within"):
        CostImport.model_validate(payload)


@pytest.mark.parametrize("with_snapshot", [False, True])
@pytest.mark.parametrize("other_subscription", [False, True])
def test_row_share_target_must_match_historical_cluster(
    with_snapshot: bool, other_subscription: bool
) -> None:
    payload = import_payload()
    target = f"{CLUSTER}-other"
    if other_subscription:
        subscription = "11111111-1111-1111-1111-111111111111"
        payload["subscription_ids"].append(subscription)
        target = target.replace(SUBSCRIPTION, subscription)
    payload["allocation"]["shares"][0]["cluster_resource_id"] = target
    result = reconcile(payload, snapshot_payload() if with_snapshot else None)
    assert result.status == "blocked"
    assert "allocation-cluster-mismatch" in result.reason_codes
    row = result.rows[0]
    assert "allocation-cluster-mismatch" in row.issues
    assert row.allocations == []
    assert row.unallocated == Decimal("100")
    assert result.currencies[0].by_attribution["allocated"] == 0
    assert result.estimated_monthly_savings is None


def test_invalid_later_share_prevents_partial_acceptance_of_a_row() -> None:
    payload = import_payload()
    valid = payload["allocation"]["shares"][0]
    valid["fraction"] = "0.30"
    invalid = deepcopy(valid)
    invalid.update(
        cluster_resource_id=f"{CLUSTER}-other",
        namespace="zzz-other",
        workload_uid="other-workload-uid",
    )
    payload["allocation"]["shares"].append(invalid)
    result = reconcile(payload)
    assert result.status == "blocked"
    assert "allocation-cluster-mismatch" in result.reason_codes
    assert result.rows[0].allocations == []
    assert result.rows[0].unallocated == Decimal("100")


def test_native_aggregate_target_is_scoped_without_inventing_a_row_binding() -> None:
    payload = actual_payload()
    target = f"{CLUSTER}-other"
    payload["allocation"]["amounts"][0]["cluster_resource_id"] = target
    result = reconcile(payload)
    assert result.status == "attributed"
    assert result.aggregate_allocations[0].cluster_resource_id == target
    assert result.aggregate_allocations[0].amount == Decimal("60")
    assert result.rows[0].allocations == []
    assert result.estimated_monthly_savings is None


def test_source_native_aggregate_allocation_is_attributed() -> None:
    payload = actual_payload()
    payload["allocation"] = {
        "profile": {"id": "opencost-allocation", "version": "1.0.0", "producer_version": "1.117.6"},
        "source_reference": "synthetic-opencost",
        "cost_basis": "actual",
        "pricing_basis": "billing-ledger",
        "period": payload["period"],
        "complete": True,
        "allocation_policy": "source-native",
        "shares": [],
        "amounts": [
            {
                "amount": "60",
                "currency": "USD",
                "category": "allocated",
                "granularity": "namespace",
                "cluster_resource_id": CLUSTER,
                "namespace": "apps",
                "identity_basis": "name-only",
                "reference": "synthetic-opencost-allocation",
            }
        ],
    }
    result = reconcile(payload)
    assert result.status == "attributed"
    assert "aggregate-allocation-not-ledger-partition" in result.reason_codes
    assert result.aggregate_allocations[0].amount == Decimal("60")


def test_service_charge_and_shared_attribution_remain_distinct() -> None:
    payload = import_payload()
    payload["rows"][0].update(charge_category="service", source_category="Uptime SLA")
    payload["allocation"]["shares"] = [{"row_id": "row-1", "fraction": "1", "category": "shared"}]
    result = reconcile(payload)
    assert result.status == "reconciled"
    assert result.currencies[0].by_charge == {"service": Decimal("100.00")}
    assert result.currencies[0].by_attribution["shared"] == Decimal("100.00")


def test_normalized_vendor_allocation_requires_reviewed_billing_pricing() -> None:
    payload = actual_payload()
    payload["allocation"]["profile"] = {
        "id": "opencost-allocation",
        "version": "1.0.0",
        "producer_version": "1.117.6",
    }
    result = reconcile(payload)
    assert result.status == "blocked"
    assert "allocation-pricing-unverified" in result.reason_codes
    assert result.aggregate_allocations[0].amount == Decimal("60")
    assert result.estimated_monthly_savings is None


@pytest.mark.parametrize(
    "profile_id,version", [("unknown", "1.0.0"), ("opencost-allocation", "99.0.0")]
)
def test_unknown_or_unsupported_financial_profile_blocks(profile_id: str, version: str) -> None:
    payload = import_payload()
    payload["allocation"]["profile"].update(id=profile_id, version=version)
    result = reconcile(payload)
    assert result.status == "blocked"
    assert "allocation-source-profile-unsupported" in result.reason_codes


def test_mixed_currency_and_unsupported_charges_still_block() -> None:
    payload = import_payload()
    payload["rows"].append(
        deepcopy(payload["rows"][0])
        | {"id": "eur", "currency": "EUR", "charge_type": "Refund", "amount": "-10"}
    )
    result = reconcile(payload)
    assert result.status == "blocked"
    assert {"mixed-currency", "unsupported-charge"}.issubset(result.reason_codes)
    assert result.estimated_monthly_savings is None


@pytest.mark.parametrize(
    "change", ["float", "nan", "overallocated", "shared-policy", "foreign-subscription", "extra"]
)
def test_invalid_financial_input_is_rejected(change: str) -> None:
    payload = import_payload()
    if change == "float":
        payload["rows"][0]["amount"] = 0.1
    elif change == "nan":
        payload["rows"][0]["amount"] = "NaN"
    elif change == "overallocated":
        payload["allocation"]["shares"][0]["fraction"] = "0.61"
    elif change == "shared-policy":
        payload["allocation"]["allocation_policy"] = "redistributed"
    elif change == "foreign-subscription":
        payload["rows"][0]["subscription_id"] = "11111111-1111-1111-1111-111111111111"
    else:
        payload["rows"][0]["tags"] = {"unapproved": "value"}
    with pytest.raises(ValidationError):
        CostImport.model_validate(payload)


def test_cost_cli_snapshot_is_optional_and_attributed_exit_is_three(tmp_path: Path) -> None:
    costs = tmp_path / "costs.json"
    output = tmp_path / "result.json"
    costs.write_text(json.dumps(import_payload()), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "reconcile-costs",
            "--costs",
            str(costs),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "reconciled"
    payload = actual_payload()
    costs.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(
        app, ["reconcile-costs", "--costs", str(costs), "--as-of", AS_OF.isoformat()]
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "attributed"


def test_stale_evidence_blocks_and_savings_remain_null() -> None:
    result = CostManagementCollector().collect_costs(
        CostImport.model_validate(import_payload()), None, as_of=AS_OF + timedelta(days=2)
    )
    assert result.status == "blocked"
    assert "cost-source-stale" in result.reason_codes
    assert result.estimated_monthly_savings is None
