from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
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
SUBSCRIPTION = TENANT
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)
POOL = f"{CLUSTER}/agentPools/apps"
RESOURCE = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-nodes/"
    "providers/Microsoft.Compute/virtualMachineScaleSets/synthetic"
)
START = "2026-09-29T00:00:00Z"
END = "2026-10-29T00:00:00Z"
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def snapshot_payload() -> dict[str, Any]:
    receipts = [
        {
            "collector": name,
            "status": "complete",
            "requested_scope": [scope],
            "completed_scope": [scope],
            "started_at": END,
            "completed_at": END,
            "source_observed_at": END,
            "pagination_complete": True,
        }
        for name, scope in [("azure-inventory", SUBSCRIPTION), ("kubernetes-metadata", CLUSTER)]
    ]
    return {
        "generated_at": END,
        "source": "synthetic",
        "metric_window": {"start": START, "end": END, "sample_count": 0, "coverage_ratio": 0},
        "collection_manifest": {
            "tenant_id": TENANT,
            "status": "complete",
            "results": receipts,
            "source_results": receipts,
        },
        "clusters": [
            {
                "resource_id": CLUSTER,
                "uid": "cluster-uid",
                "name": "aks-synthetic",
                "subscription_id": SUBSCRIPTION,
                "resource_group": "rg-synthetic",
                "location": "eastus2",
                "node_pools": [
                    {
                        "resource_id": POOL,
                        "name": "apps",
                        "vm_size": "Standard_D4s_v5",
                        "node_count": 1,
                        "allocatable_cpu_mcores": 4000,
                        "allocatable_memory_mib": 16000,
                    }
                ],
                "workloads": [
                    {
                        "kind": "Deployment",
                        "name": "synthetic",
                        "namespace": "apps",
                        "uid": "workload-uid",
                        "replicas": 1,
                        "containers": [{"name": "app", "resources": {}}],
                    }
                ],
            }
        ],
    }


def import_payload() -> dict[str, Any]:
    return {
        "tenant_id": TENANT,
        "subscription_ids": [SUBSCRIPTION],
        "period": {"start": START, "end": END},
        "source_profile": "azure-cost-details-projection-v1",
        "cost_basis": "amortized",
        "source_reference": "synthetic-export",
        "source_observed_at": END,
        "export_complete": True,
        "rows": [
            {
                "id": "row-1",
                "subscription_id": SUBSCRIPTION,
                "resource_id": RESOURCE,
                "period": {"start": START, "end": END},
                "amount": "100.00",
                "currency": "USD",
                "charge_category": "compute",
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
                "reference": "synthetic-historical-binding",
            }
        ],
        "allocation": {
            "source": "opencost",
            "source_reference": "synthetic-reviewed-shares",
            "basis": "reviewed-shares",
            "shared_idle": False,
            "period": {"start": START, "end": END},
            "shares": [
                {
                    "row_id": "row-1",
                    "fraction": "0.60",
                    "category": "allocated",
                    "namespace": "apps",
                    "workload_uid": "workload-uid",
                    "container": "app",
                },
                {"row_id": "row-1", "fraction": "0.25", "category": "idle"},
                {"row_id": "row-1", "fraction": "0.15", "category": "system"},
            ],
        },
    }


def reconcile(payload: dict[str, Any] | None = None, **kwargs: Any) -> CostReconciliation:
    return CostManagementCollector().collect_costs(
        CostImport.model_validate(payload if payload is not None else import_payload()),
        FleetSnapshot.model_validate(snapshot_payload()),
        as_of=AS_OF,
        **kwargs,
    )


def test_amortized_cost_is_partitioned_once_with_exact_decimal_reconciliation() -> None:
    result = reconcile()
    assert result.status == "reconciled"
    assert result.reason_codes == []
    summary = result.currencies[0]
    assert summary.total == Decimal("100.00")
    assert summary.matched == Decimal("100")
    assert summary.allocation_coverage == Decimal("1")
    assert summary.by_charge == {"compute": Decimal("100")}
    assert summary.by_attribution == {
        "allocated": Decimal("60"),
        "idle": Decimal("25"),
        "system": Decimal("15"),
        "unallocated": Decimal("0"),
    }
    assert sum(summary.by_attribution.values()) == summary.total
    assert result.rows[0].original.benefit_id == "synthetic-reservation"
    assert result.rows[0].binding.reference == "synthetic-historical-binding"
    assert result.estimated_monthly_savings is None
    assert CostReconciliation.model_validate_json(result.model_dump_json()) == result
    assert reconcile().model_dump_json() == result.model_dump_json()


@pytest.mark.parametrize(
    "fraction,expected_status", [("0.9499", "blocked"), ("0.95", "reconciled")]
)
def test_allocation_coverage_threshold_is_exact(fraction: str, expected_status: str) -> None:
    payload = import_payload()
    payload["allocation"]["shares"] = [payload["allocation"]["shares"][0] | {"fraction": fraction}]
    result = reconcile(payload)
    assert result.status == expected_status
    summary = result.currencies[0]
    assert summary.allocation_coverage == Decimal(fraction)
    assert summary.by_attribution["unallocated"] == Decimal("100") * (1 - Decimal(fraction))
    assert ("allocation-coverage-below-threshold" in result.reason_codes) == (
        expected_status == "blocked"
    )


@pytest.mark.parametrize(
    "change", ["resource", "cluster", "pool", "cluster-uid", "workload", "container"]
)
def test_foreign_or_recreated_identities_are_retained_not_name_joined(change: str) -> None:
    payload = import_payload()
    if change == "resource":
        payload["rows"][0]["resource_id"] += "-foreign"
    elif change in {"cluster", "pool", "cluster-uid"}:
        key = {
            "cluster": "cluster_resource_id",
            "pool": "pool_resource_id",
            "cluster-uid": "cluster_uid",
        }[change]
        payload["bindings"][0][key] += "-foreign"
    else:
        key = "workload_uid" if change == "workload" else "container"
        payload["allocation"]["shares"][0][key] += "-foreign"
    result = reconcile(payload)
    assert result.status == "blocked"
    assert result.rows[0].issues
    assert result.currencies[0].by_attribution["unallocated"] >= Decimal("60")
    assert result.rows[0].original.amount == Decimal("100")
    assert result.estimated_monthly_savings is None


def test_missing_allocation_and_unmatched_rows_preserve_denominator() -> None:
    payload = import_payload()
    payload["rows"].append(
        payload["rows"][0] | {"id": "unmatched", "resource_id": None, "amount": "25"}
    )
    del payload["allocation"]
    result = reconcile(payload)
    summary = result.currencies[0]
    assert summary.total == Decimal("125")
    assert summary.matched == Decimal("100")
    assert summary.unmatched == Decimal("25")
    assert summary.allocation_coverage == 0
    assert summary.by_attribution["unallocated"] == Decimal("125")
    assert len(result.rows) == 2
    assert result.status == "blocked"


def test_mixed_currency_never_combines_totals_or_enables_savings() -> None:
    payload = import_payload()
    payload["rows"].append(payload["rows"][0] | {"id": "eur", "currency": "EUR"})
    result = reconcile(payload)
    assert result.status == "blocked"
    assert "mixed-currency" in result.reason_codes
    assert {item.currency: item.total for item in result.currencies} == {
        "EUR": Decimal("100"),
        "USD": Decimal("100"),
    }


@pytest.mark.parametrize(
    "change,reason",
    [
        ("partial", "export-incomplete"),
        ("period", "period-mismatch"),
        ("allocation-period", "allocation-period-mismatch"),
        ("benefit", "benefit-metadata-missing"),
        ("credit", "unsupported-charge"),
        ("zero", "no-positive-cost"),
        ("empty", "no-positive-cost"),
    ],
)
def test_incomplete_or_unsupported_financial_evidence_blocks(change: str, reason: str) -> None:
    payload = import_payload()
    if change == "partial":
        payload["export_complete"] = False
    elif change == "period":
        payload["period"]["start"] = "2026-09-28T00:00:00Z"
    elif change == "allocation-period":
        payload["allocation"]["period"]["start"] = "2026-09-28T00:00:00Z"
    elif change == "benefit":
        payload["rows"][0]["benefit_id"] = None
    elif change == "credit":
        payload["rows"][0].update(amount="-100", charge_type="Refund")
    elif change == "zero":
        payload["rows"][0]["amount"] = "0"
    else:
        payload["rows"] = []
        payload["allocation"]["shares"] = []
    result = reconcile(payload)
    assert result.status == "blocked"
    assert reason in result.reason_codes
    assert result.estimated_monthly_savings is None
    if change == "credit":
        assert result.currencies[0].total == Decimal("-100")
        assert result.currencies[0].allocation_coverage is None


def test_stale_future_and_freshness_boundary_are_explicit() -> None:
    collector = CostManagementCollector()
    evidence = CostImport.model_validate(import_payload())
    snapshot = FleetSnapshot.model_validate(snapshot_payload())
    assert (
        collector.collect_costs(evidence, snapshot, as_of=AS_OF + timedelta(hours=12)).status
        == "reconciled"
    )
    result = collector.collect_costs(
        evidence, snapshot, as_of=AS_OF + timedelta(hours=12, seconds=1)
    )
    assert "cost-source-stale" in result.reason_codes
    result = collector.collect_costs(evidence, snapshot, as_of=AS_OF - timedelta(days=1))
    assert "cost-source-in-future" in result.reason_codes


def test_missing_snapshot_receipts_and_tenant_mismatch_do_not_reconcile() -> None:
    collector = CostManagementCollector()
    evidence = CostImport.model_validate(import_payload())
    payload = snapshot_payload()
    del payload["collection_manifest"]
    result = collector.collect_costs(evidence, FleetSnapshot.model_validate(payload), as_of=AS_OF)
    assert "inventory-evidence-incomplete" in result.reason_codes
    payload = snapshot_payload()
    payload["collection_manifest"]["tenant_id"] = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(ValueError, match="tenant"):
        collector.collect_costs(evidence, FleetSnapshot.model_validate(payload), as_of=AS_OF)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate-row",
        "duplicate-binding",
        "duplicate-share",
        "overallocated",
        "unknown-row",
        "actual",
        "list-price",
        "shared-idle",
        "nan",
        "float",
        "foreign-subscription",
        "resource-subscription",
        "naive",
        "reverse-period",
        "extra",
    ],
)
def test_invalid_or_ambiguous_import_is_rejected(change: str) -> None:
    payload = import_payload()
    if change == "duplicate-row":
        payload["rows"].append(deepcopy(payload["rows"][0]))
    elif change == "duplicate-binding":
        payload["bindings"].append(deepcopy(payload["bindings"][0]))
    elif change == "duplicate-share":
        payload["allocation"]["shares"].append(deepcopy(payload["allocation"]["shares"][0]))
    elif change == "overallocated":
        payload["allocation"]["shares"][0]["fraction"] = "0.61"
    elif change == "unknown-row":
        payload["allocation"]["shares"][0]["row_id"] = "not-a-row"
    elif change == "actual":
        payload["cost_basis"] = "actual"
    elif change == "list-price":
        payload["allocation"]["basis"] = "list-price"
    elif change == "shared-idle":
        payload["allocation"]["shared_idle"] = True
    elif change == "nan":
        payload["rows"][0]["amount"] = "NaN"
    elif change == "float":
        payload["rows"][0]["amount"] = 0.1
    elif change == "foreign-subscription":
        payload["rows"][0]["subscription_id"] = "00000000-0000-0000-0000-000000000001"
    elif change == "resource-subscription":
        payload["rows"][0]["resource_id"] = RESOURCE.replace(
            SUBSCRIPTION, "00000000-0000-0000-0000-000000000001"
        )
    elif change == "naive":
        payload["source_observed_at"] = END.removesuffix("Z")
    elif change == "reverse-period":
        payload["period"]["end"] = START
    else:
        payload["rows"][0]["tags"] = {"unapproved": "data"}
    with pytest.raises(ValidationError):
        CostImport.model_validate(payload)


def test_cost_cli_replay_exit_codes_redaction_and_exclusive_output(tmp_path: Path) -> None:
    costs = tmp_path / "costs.json"
    snapshot = tmp_path / "snapshot.json"
    output = tmp_path / "reconciled.json"
    costs.write_text(json.dumps(import_payload()), encoding="utf-8")
    snapshot.write_text(json.dumps(snapshot_payload()), encoding="utf-8")
    args = [
        "reconcile-costs",
        "--costs",
        str(costs),
        "--snapshot",
        str(snapshot),
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "reconciled"
    assert runner.invoke(app, args).exit_code == 1
    payload = import_payload()
    payload["bindings"] = []
    costs.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, args[:-2])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["status"] == "blocked"
    payload["rows"][0]["amount"] = "SENSITIVE-INVALID-INPUT"
    costs.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, args[:-2])
    assert result.exit_code == 2
    assert "SENSITIVE-INVALID-INPUT" not in result.output


@pytest.mark.parametrize("change", ["partial", "scope", "stale", "duplicate-cluster"])
def test_invalid_inventory_cannot_be_promoted_by_fresh_costs(change: str) -> None:
    payload = snapshot_payload()
    if change == "partial":
        payload["collection_manifest"]["status"] = "partial"
    if change == "duplicate-cluster":
        payload["clusters"].append(deepcopy(payload["clusters"][0]) | {"uid": "another-uid"})
    else:
        for receipts in ("results", "source_results"):
            receipt = payload["collection_manifest"][receipts][1]
            if change == "partial":
                receipt.update(status="partial", completed_scope=[], pagination_complete=False)
            elif change == "scope":
                receipt["requested_scope"] = [CLUSTER + "-foreign"]
                receipt["completed_scope"] = [CLUSTER + "-foreign"]
            else:
                receipt["source_observed_at"] = "2026-10-27T00:00:00Z"
                receipt["started_at"] = "2026-10-27T00:00:00Z"
    result = CostManagementCollector().collect_costs(
        CostImport.model_validate(import_payload()),
        FleetSnapshot.model_validate(payload),
        as_of=AS_OF,
    )
    assert result.status == "blocked"
    assert (
        "resource-unmatched" in result.reason_codes
        if change == "duplicate-cluster"
        else ("inventory-evidence-incomplete" in result.reason_codes)
    )
    assert result.estimated_monthly_savings is None


def test_decimal_partition_preserves_subcent_residue_and_input_objects() -> None:
    payload = import_payload()
    payload["rows"][0]["amount"] = "0.01"
    payload["allocation"]["shares"] = [
        payload["allocation"]["shares"][0] | {"fraction": "0.333333333333333333"},
        payload["allocation"]["shares"][1] | {"fraction": "0.333333333333333333"},
        payload["allocation"]["shares"][2] | {"fraction": "0.333333333333333333"},
    ]
    evidence = CostImport.model_validate(payload)
    snapshot = FleetSnapshot.model_validate(snapshot_payload())
    before = evidence.model_dump_json(), snapshot.model_dump_json()
    result = CostManagementCollector().collect_costs(evidence, snapshot, as_of=AS_OF)
    assert result.currencies[0].total == Decimal("0.01")
    assert result.currencies[0].by_attribution["unallocated"] == Decimal("0.00000000000000000001")
    assert (evidence.model_dump_json(), snapshot.model_dump_json()) == before


@pytest.mark.parametrize("threshold", [Decimal("-0.01"), Decimal("1.01"), Decimal("NaN"), 0.95])
def test_invalid_coverage_threshold_cannot_disable_gates(threshold: Any) -> None:
    with pytest.raises(ValueError, match="coverage"):
        reconcile(minimum_allocation_coverage=threshold)


def test_all_charge_dimensions_and_pricing_models_remain_separate() -> None:
    payload = import_payload()
    for category, pricing in [
        ("storage", "OnDemand"),
        ("network", "Spot"),
        ("other", "SavingsPlan"),
    ]:
        payload["rows"].append(
            payload["rows"][0]
            | {
                "id": category,
                "charge_category": category,
                "pricing_model": pricing,
                "amount": "10",
            }
        )
        payload["allocation"]["shares"].append(
            {
                "row_id": category,
                "fraction": "1",
                "category": "system",
            }
        )
    result = reconcile(payload)
    summary = result.currencies[0]
    assert result.status == "reconciled"
    assert summary.by_charge == {
        "compute": Decimal("100"),
        "storage": Decimal("10"),
        "network": Decimal("10"),
        "other": Decimal("10"),
    }
    assert summary.total == sum(summary.by_charge.values()) == sum(summary.by_attribution.values())
    assert {row.original.pricing_model for row in result.rows} == {
        "OnDemand",
        "Spot",
        "Reservation",
        "SavingsPlan",
    }
