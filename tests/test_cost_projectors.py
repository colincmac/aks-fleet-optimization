from __future__ import annotations

import json
import socket
from csv import DictWriter
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_cost_management import (
    AS_OF,
    CLUSTER,
    END,
    RESOURCE,
    START,
    SUBSCRIPTION,
    TENANT,
    import_payload,
)
from test_fleet import assessment_inputs
from test_history import write_run
from typer.testing import CliRunner

from aks_fleet_efficiency.artifacts import write_assessment_artifacts
from aks_fleet_efficiency.assessment import assess_fragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.collectors.cost_management import CostManagementCollector
from aks_fleet_efficiency.cost import (
    AllocationContext,
    AllocationObservation,
    ClusterCostReviewOrder,
    CostAllocation,
    CostImport,
    CostPeriod,
    CostReconciliation,
    order_cluster_cost_reviews,
    qualify_allocation_observation,
)
from aks_fleet_efficiency.cost_sources import (
    order_saved_cost_reviews,
    project_allocation,
    project_ledger,
)


def allocation_observation() -> AllocationObservation:
    native = json.loads(
        Path("examples/fixtures/aks-cost-analysis-allocation.json").read_text(encoding="utf-8")
    )
    allocation = project_allocation("aks-cost-analysis", native)
    return AllocationObservation(
        tenant_id=TENANT,
        subscription_id=SUBSCRIPTION,
        cluster_resource_id=CLUSTER,
        cluster_uid="synthetic-cluster-uid",
        source_observed_at=AS_OF,
        binding_reference="synthetic-source-cluster-binding",
        allocation=allocation,
    )


def cluster_review_observation(name: str, amount: str) -> AllocationObservation:
    payload = allocation_observation().model_dump(mode="json")
    cluster = CLUSTER + "-" + name
    payload["cluster_resource_id"] = cluster
    payload["cluster_uid"] = "synthetic-cluster-uid-" + name
    original_amount = payload["allocation"]["amounts"][0]
    currency = original_amount["currency"]
    payload["allocation"]["amounts"] = [
        {
            "category": "allocated",
            "granularity": "cluster",
            "cluster_resource_id": cluster,
            "identity_basis": "current-only",
            "reference": "synthetic-source-binding",
            "amount": amount,
            "currency": currency,
        },
        {"category": "idle", "amount": "10", "currency": currency},
    ]
    return AllocationObservation.model_validate(payload)


def test_cluster_cost_review_order_is_decimal_separate_and_preserves_nonallocated_buckets() -> None:
    contexts = []
    for name, amount in [("small", "100.000000000001"), ("large", "100.000000000002")]:
        observation = cluster_review_observation(name, amount)
        contexts.append(
            qualify_allocation_observation(
                observation,
                tenant_id=TENANT,
                cluster_resource_id=observation.cluster_resource_id,
                cluster_uid=observation.cluster_uid,
                period=observation.allocation.period,
                as_of=AS_OF,
            )
        )
    original = [context.model_dump_json() for context in contexts]
    order = order_cluster_cost_reviews(contexts)
    assert [row.context.observation.cluster_resource_id for row in order.rows] == [
        CLUSTER + "-large",
        CLUSTER + "-small",
    ]
    assert order.rows[0].allocated_amount == Decimal("100.000000000002")
    assert order.rows[0].nonallocated_amounts[0].category == "idle"
    assert order.rows[0].nonallocated_amounts[0].amount == Decimal("10")
    assert order.estimated_monthly_savings is None and not order.engineering_order_changed
    assert [context.model_dump_json() for context in contexts] == original
    assert order_cluster_cost_reviews(list(reversed(contexts))) == order


@pytest.mark.parametrize(
    "problem",
    [
        "overlap",
        "namespace",
        "name-only",
        "currency",
        "source",
        "profile",
        "pricing",
        "period",
        "duplicate-cluster",
        "stale",
        "partial",
    ],
)
def test_cluster_cost_review_refuses_incompatible_or_overlapping_inputs(problem: str) -> None:
    contexts = []
    for name in ["first", "second"]:
        observation = cluster_review_observation(name, "100")
        contexts.append(
            qualify_allocation_observation(
                observation,
                tenant_id=TENANT,
                cluster_resource_id=observation.cluster_resource_id,
                cluster_uid=observation.cluster_uid,
                period=observation.allocation.period,
                as_of=AS_OF,
            ).model_dump(mode="json")
        )
    payload = contexts[1]
    allocation = payload["observation"]["allocation"]
    if problem == "overlap":
        allocation["amounts"].append(dict(allocation["amounts"][0]))
    elif problem == "namespace":
        allocation["amounts"][0].update(granularity="namespace", namespace="synthetic")
    elif problem == "name-only":
        allocation["amounts"][0]["identity_basis"] = "name-only"
    elif problem == "currency":
        allocation["amounts"][0]["currency"] = "EUR"
    elif problem == "source":
        allocation["source_reference"] = "SENSITIVE-OTHER-SOURCE"
    elif problem == "profile":
        allocation["profile"]["version"] = "0.0.0"
    elif problem == "pricing":
        allocation["pricing_basis"] = "billing-ledger"
    elif problem == "period":
        period_start = CostPeriod.model_validate(allocation["period"]).start
        allocation["period"]["start"] = (period_start + timedelta(days=1)).isoformat()
    elif problem == "duplicate-cluster":
        contexts[1] = contexts[0]
    elif problem == "stale":
        for context in contexts:
            context["evaluated_at"] = (AS_OF + timedelta(hours=25)).isoformat()
    else:
        allocation["complete"] = False
    with pytest.raises(ValueError) as error:
        order_cluster_cost_reviews([AllocationContext.model_validate(item) for item in contexts])
    assert "SENSITIVE-OTHER-SOURCE" not in str(error.value)


def test_cluster_cost_review_decimal_comparison_ignores_ambient_rounding() -> None:
    contexts = []
    for name, amount in [("first", "100.000000000001"), ("second", "100.000000000002")]:
        observation = cluster_review_observation(name, amount)
        contexts.append(
            qualify_allocation_observation(
                observation,
                tenant_id=TENANT,
                cluster_resource_id=observation.cluster_resource_id,
                cluster_uid=observation.cluster_uid,
                period=observation.allocation.period,
                as_of=AS_OF,
            )
        )
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        result = order_cluster_cost_reviews(contexts)
    assert result.rows[0].context.observation.cluster_resource_id == CLUSTER + "-second"
    assert result.rows[0].allocated_amount == Decimal("100.000000000002")


def saved_cost_review_inputs(tmp_path: Path) -> list[tuple[Path, AllocationObservation]]:
    inputs = []
    for name, amount in [("first", "100"), ("second", "200")]:
        fragments, profile = assessment_inputs(name)
        metadata = fragments.kubernetes[0]
        fingerprint = "synthetic-cost-fingerprint-" + name
        metadata.cluster_uid = fingerprint
        next(
            item
            for item in metadata.resources
            if item.kind == "Namespace" and item.name == "kube-system"
        ).uid = fingerprint
        result = assess_fragments(fragments, profile, as_of=AS_OF)
        directory = tmp_path / name
        write_assessment_artifacts(directory, fragments, result, profile.analysis)
        payload = cluster_review_observation(name, amount).model_dump(mode="json")
        payload["cluster_resource_id"] = metadata.cluster_resource_id
        payload["cluster_uid"] = fingerprint
        payload["allocation"]["amounts"][0]["cluster_resource_id"] = metadata.cluster_resource_id
        inputs.append((directory, AllocationObservation.model_validate(payload)))
    return inputs


def test_saved_cost_review_order_requires_original_replay_and_preserves_input_files(
    tmp_path: Path,
) -> None:
    inputs = saved_cost_review_inputs(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    order = order_saved_cost_reviews(inputs, tenant_id=TENANT, as_of=AS_OF)
    assert len(order.rows) == 2
    assert order.rows[0].allocated_amount == Decimal("200")
    assert len(order.original_assessment_run_ids) == 2
    assert {path: path.read_bytes() for path in before} == before
    assert order_saved_cost_reviews(list(reversed(inputs)), tenant_id=TENANT, as_of=AS_OF) == order
    (inputs[0][0] / "report.md").write_text("SENSITIVE-TAMPERED-REPORT", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        order_saved_cost_reviews(inputs, tenant_id=TENANT, as_of=AS_OF)
    assert "SENSITIVE-TAMPERED-REPORT" not in str(error.value)


def test_cost_review_cli_replays_originals_and_does_not_clobber_or_echo_input(
    tmp_path: Path,
) -> None:
    inputs = saved_cost_review_inputs(tmp_path)
    arguments = ["order-cost-review", "--tenant", TENANT, "--as-of", AS_OF.isoformat()]
    for index, (directory, observation) in enumerate(inputs):
        path = tmp_path / f"observation-{index}.json"
        path.write_text(observation.model_dump_json(), encoding="utf-8")
        arguments.extend(
            ["--assessment", str(directory / "assessment.json"), "--observation", str(path)]
        )
    output = tmp_path / "order.json"
    runner = CliRunner()
    result = runner.invoke(app, [*arguments, "--output", str(output)])
    assert result.exit_code == 0, result.output
    order = ClusterCostReviewOrder.model_validate_json(output.read_text(encoding="utf-8"))
    assert order.rows[0].allocated_amount == Decimal("200")
    original = output.read_bytes()
    assert runner.invoke(app, [*arguments, "--output", str(output)]).exit_code == 1
    assert output.read_bytes() == original
    arguments[2] = "SENSITIVE-INVALID-TENANT"
    failed_output = tmp_path / "invalid.json"
    invalid = runner.invoke(app, [*arguments, "--output", str(failed_output)])
    assert invalid.exit_code == 2 and not failed_output.exists()
    assert "SENSITIVE-INVALID-TENANT" not in invalid.output


def test_allocation_observation_qualifies_only_exact_scoped_fresh_context() -> None:
    observation = allocation_observation()
    before = observation.model_dump_json()
    context = qualify_allocation_observation(
        observation,
        tenant_id=TENANT,
        cluster_resource_id=CLUSTER,
        cluster_uid="synthetic-cluster-uid",
        period=observation.allocation.period,
        as_of=AS_OF,
    )

    assert context.status == "qualified"
    assert context.reason_codes == []
    assert context.observation == observation
    assert context.estimated_monthly_savings is None
    assert context.observation.allocation.amounts[0].identity_basis == "name-only"
    assert observation.model_dump_json() == before


@pytest.mark.parametrize("problem", ["stale", "future", "partial", "period", "profile", "negative"])
def test_allocation_context_preserves_blocked_evidence(problem: str) -> None:
    payload = allocation_observation().model_dump(mode="json")
    expected = f"allocation_{problem}"
    period = CostPeriod.model_validate(payload["allocation"]["period"])
    as_of = AS_OF
    if problem == "stale":
        as_of += timedelta(hours=24, seconds=1)
        expected = "allocation_source_stale"
    elif problem == "future":
        payload["source_observed_at"] = (AS_OF + timedelta(seconds=1)).isoformat()
        expected = "allocation_source_future"
    elif problem == "partial":
        payload["allocation"]["complete"] = False
        expected = "allocation_incomplete"
    elif problem == "period":
        period = CostPeriod(start=period.start + timedelta(days=1), end=period.end)
        expected = "allocation_period_mismatch"
    elif problem == "profile":
        payload["allocation"]["profile"]["producer_version"] = "unsupported"
        expected = "allocation_profile_unsupported"
    else:
        payload["allocation"]["amounts"][0]["amount"] = "-1"
        expected = "allocation_negative_amount"
    observation = AllocationObservation.model_validate(payload)
    context = qualify_allocation_observation(
        observation,
        tenant_id=TENANT,
        cluster_resource_id=CLUSTER,
        cluster_uid=observation.cluster_uid,
        period=period,
        as_of=as_of,
    )
    assert context.status == "blocked"
    assert expected in context.reason_codes
    assert context.observation == observation
    assert context.estimated_monthly_savings is None


@pytest.mark.parametrize("problem", ["tenant", "cluster", "fingerprint", "naive", "age"])
def test_allocation_context_rejects_foreign_scope_and_invalid_policy(problem: str) -> None:
    observation = allocation_observation()
    with pytest.raises(ValueError):
        qualify_allocation_observation(
            observation,
            tenant_id="11111111-1111-1111-1111-111111111111" if problem == "tenant" else TENANT,
            cluster_resource_id=CLUSTER + "-foreign" if problem == "cluster" else CLUSTER,
            cluster_uid="foreign" if problem == "fingerprint" else observation.cluster_uid,
            period=observation.allocation.period,
            as_of=AS_OF.replace(tzinfo=None) if problem == "naive" else AS_OF,
            maximum_evidence_age_hours=True if problem == "age" else 24,
        )


def test_allocation_context_passes_freshness_equality() -> None:
    observation = allocation_observation()
    assert (
        qualify_allocation_observation(
            observation,
            tenant_id=TENANT,
            cluster_resource_id=CLUSTER,
            cluster_uid=observation.cluster_uid,
            period=observation.allocation.period,
            as_of=AS_OF + timedelta(hours=24),
        ).status
        == "qualified"
    )


def test_allocation_context_cli_verifies_original_assessment_and_redacts_errors(
    tmp_path: Path,
) -> None:
    original = write_run(tmp_path, "original", as_of=AS_OF)
    observation = tmp_path / "observation.json"
    observation.write_text(allocation_observation().model_dump_json(), encoding="utf-8")
    output = tmp_path / "context.json"
    arguments = [
        "qualify-allocation",
        "--observation",
        str(observation),
        "--assessment",
        str(original / "assessment.json"),
        "--tenant",
        TENANT,
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["status"] == "qualified"
    assert CliRunner().invoke(app, arguments).exit_code != 0
    observation.write_text('{"sensitive-customer-input":true}', encoding="utf-8")
    arguments[-1] = str(tmp_path / "invalid.json")
    invalid = CliRunner().invoke(app, arguments)
    assert invalid.exit_code == 2
    assert "sensitive-customer-input" not in invalid.output
    assert not (tmp_path / "invalid.json").exists()


def native_focus_export(directory: Path, **changes: str) -> tuple[Path, Path, Path]:
    part = directory / "part0.csv"
    row = {
        "SubAccountId": SUBSCRIPTION,
        "ResourceId": RESOURCE,
        "ChargePeriodStart": START,
        "ChargePeriodEnd": END,
        "EffectiveCost": "100.000000000001",
        "BillingCurrency": "USD",
        "ServiceCategory": "Compute",
        "ChargeCategory": "Usage",
        "PricingCategory": "Standard",
        "ChargeClass": "",
        "CommitmentDiscountCategory": "",
        "CommitmentDiscountId": "",
        "CommitmentDiscountStatus": "",
        "CommitmentDiscountType": "",
        "Tags": '{"excluded":"synthetic-private-marker"}',
        "x_AccountOwnerId": "synthetic-private-marker",
    }
    row.update(changes)
    with part.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifestVersion": "2024-04-01",
                "byteCount": part.stat().st_size,
                "blobCount": 1,
                "dataRowCount": 1,
                "exportConfig": {"dataVersion": "1.2-preview", "type": "FocusCost"},
                "deliveryConfig": {"fileFormat": "Csv", "compressionMode": "None"},
                "runInfo": {"runId": "synthetic-run"},
                "blobs": [
                    {
                        "blobName": "synthetic-export/part0.csv",
                        "byteCount": part.stat().st_size,
                        "dataRowCount": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    review = directory / "review.json"
    review.write_text(
        json.dumps(
            {
                "tenant_id": TENANT,
                "subscription_ids": [SUBSCRIPTION],
                "period": {"start": START, "end": END},
                "source_reference": "synthetic-reviewed-export",
                "source_observed_at": END,
                "expected_totals": {"USD": "100.000000000001"},
            }
        ),
        encoding="utf-8",
    )
    return manifest, part, review


def test_native_focus_export_preserves_controls_without_retaining_sensitive_columns(
    tmp_path: Path,
) -> None:
    manifest, part, review = native_focus_export(tmp_path)
    output = tmp_path / "costs.json"
    arguments = [
        "convert-focus",
        "--manifest",
        str(manifest),
        "--part",
        str(part),
        "--review",
        str(review),
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    text = output.read_text(encoding="utf-8")
    ledger = CostImport.model_validate_json(text)
    assert ledger.rows[0].amount == Decimal("100.000000000001")
    assert ledger.bindings == []
    assert "synthetic-private-marker" not in text + result.output
    assert ledger.export_provenance.files[0].row_count == 1
    assert ledger.rows[0].id.endswith(":1")
    replay = CostManagementCollector().collect_costs(ledger, as_of=AS_OF)
    assert replay.status == "blocked"
    assert replay.estimated_monthly_savings is None
    assert replay.currencies[0].total == ledger.rows[0].amount
    assert CliRunner().invoke(app, arguments).exit_code != 0


@pytest.mark.parametrize(
    "defect", ["version", "missing-part", "rows", "bytes", "totals", "category"]
)
def test_native_focus_export_rejects_unproven_or_unsupported_input(
    tmp_path: Path, defect: str
) -> None:
    manifest, part, review = native_focus_export(tmp_path)
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if defect == "version":
        metadata["exportConfig"]["dataVersion"] = "unknown"
    elif defect == "missing-part":
        metadata["blobCount"] = 2
    elif defect == "rows":
        metadata["blobs"][0]["dataRowCount"] = 2
    elif defect == "bytes":
        metadata["blobs"][0]["byteCount"] += 1
    elif defect == "totals":
        controls = json.loads(review.read_text(encoding="utf-8"))
        controls["expected_totals"]["USD"] = "1"
        review.write_text(json.dumps(controls), encoding="utf-8")
    else:
        part.write_text(
            part.read_text(encoding="utf-8-sig").replace("Usage", "unknown"), encoding="utf-8-sig"
        )
        metadata["byteCount"] = metadata["blobs"][0]["byteCount"] = part.stat().st_size
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    output = tmp_path / "costs.json"
    result = CliRunner().invoke(
        app,
        [
            "convert-focus",
            "--manifest",
            str(manifest),
            "--part",
            str(part),
            "--review",
            str(review),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code != 0
    assert not output.exists()
    assert "synthetic-private-marker" not in result.output


@pytest.mark.parametrize("category", ["Purchase", "Tax", "Adjustment"])
def test_native_focus_unsupported_charges_keep_their_amounts(tmp_path: Path, category: str) -> None:
    from aks_fleet_efficiency.cost_sources.focus_export import convert_focus_export

    manifest, part, review = native_focus_export(
        tmp_path, ChargeCategory=category, PricingCategory="" if category == "Tax" else "Standard"
    )
    ledger = convert_focus_export(manifest, [part], review)
    result = CostManagementCollector().collect_costs(ledger, as_of=AS_OF)
    assert result.status == "blocked"
    assert "unsupported-charge" in result.reason_codes
    assert result.rows[0].original.charge_type == category
    assert result.currencies[0].total == Decimal("100.000000000001")
    assert result.estimated_monthly_savings is None


def test_native_focus_can_use_independently_reviewed_historical_shares(tmp_path: Path) -> None:
    from aks_fleet_efficiency.cost_sources.focus_export import convert_focus_export

    manifest, part, review = native_focus_export(tmp_path)
    controls = json.loads(review.read_text(encoding="utf-8"))
    controls["bindings"] = import_payload()["bindings"]
    review.write_text(json.dumps(controls), encoding="utf-8")
    ledger = convert_focus_export(manifest, [part], review)
    allocation = import_payload()["allocation"]
    allocation["cost_basis"] = "effective"
    for share in allocation["shares"]:
        share["row_id"] = ledger.rows[0].id
    evidence = CostImport.model_validate(ledger.model_dump() | {"allocation": allocation})
    result = CostManagementCollector().collect_costs(evidence, as_of=AS_OF)
    assert result.status == "reconciled"
    assert result.estimated_monthly_savings is None
    assert CostReconciliation.model_validate_json(result.model_dump_json()) == result


def test_native_focus_keeps_identical_content_partitions_distinct(tmp_path: Path) -> None:
    from aks_fleet_efficiency.cost_sources.focus_export import convert_focus_export

    manifest, part, review = native_focus_export(tmp_path)
    second = tmp_path / "part1.csv"
    second.write_bytes(part.read_bytes())
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata.update(blobCount=2, dataRowCount=2, byteCount=part.stat().st_size * 2)
    metadata["blobs"].append(metadata["blobs"][0] | {"blobName": "synthetic-export/part1.csv"})
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    controls = json.loads(review.read_text(encoding="utf-8"))
    controls["expected_totals"]["USD"] = "200.000000000002"
    review.write_text(json.dumps(controls), encoding="utf-8")
    ledger = convert_focus_export(manifest, [second, part], review)
    assert len(ledger.rows) == 2
    assert len({row.id for row in ledger.rows}) == 2
    assert len({file.sha256 for file in ledger.export_provenance.files}) == 1
    assert len({file.partition_sha256 for file in ledger.export_provenance.files}) == 2
    assert convert_focus_export(manifest, [part, second], review) == ledger


@pytest.mark.parametrize("field,value", [("byteCount", 33554433), ("dataRowCount", 100001)])
def test_native_focus_rejects_exports_beyond_the_bounded_scope(
    tmp_path: Path, field: str, value: int
) -> None:
    from aks_fleet_efficiency.cost_sources.focus_export import convert_focus_export

    manifest, part, review = native_focus_export(tmp_path)
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    metadata[field] = value
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid or unsupported FOCUS"):
        convert_focus_export(manifest, [part], review)


def azure_projection() -> dict[str, object]:
    normalized = import_payload()
    return {
        "schema_version": "azure-cost-details-projection-v1",
        "producer_version": "2025.05.01",
        "cost_basis": "amortized",
        "tenant_id": TENANT,
        "subscription_ids": [SUBSCRIPTION],
        "period": {"start": START, "end": END},
        "source_reference": "synthetic-azure-export",
        "source_observed_at": END,
        "export_complete": True,
        "rows": [
            {
                "row_id": "row-1",
                "subscription_id": SUBSCRIPTION,
                "resource_id": RESOURCE,
                "period_start": START,
                "period_end": END,
                "cost_in_billing_currency": "100.00",
                "billing_currency": "USD",
                "charge_category": "compute",
                "meter_category": "Virtual Machines",
                "charge_type": "Usage",
                "pricing_model": "Reservation",
                "benefit_id": "synthetic-reservation",
            }
        ],
        "bindings": normalized["bindings"],
    }


def focus_projection() -> dict[str, Any]:
    normalized = import_payload()
    return {
        "schema_version": "finops-focus-projection-v1",
        "producer_version": "1.2-preview",
        "tenant_id": TENANT,
        "subscription_ids": [SUBSCRIPTION],
        "period": {"start": START, "end": END},
        "source_reference": "synthetic-finops-hub",
        "source_observed_at": END,
        "export_complete": True,
        "rows": [
            {
                "charge_id": "focus-1",
                "sub_account_id": SUBSCRIPTION,
                "resource_id": RESOURCE,
                "charge_period_start": START,
                "charge_period_end": END,
                "effective_cost": "100.00",
                "billing_currency": "USD",
                "service_category": "Compute",
                "charge_category": "Usage",
                "pricing_category": "Standard",
            }
        ],
        "bindings": normalized["bindings"],
    }


def opencost_projection() -> dict[str, object]:
    return {
        "schema_version": "reviewed-opencost-allocation-v1",
        "producer_version": "1.117.6",
        "source_reference": "synthetic-opencost",
        "cost_basis": "actual",
        "pricing_basis": "billing-ledger",
        "period": {"start": START, "end": END},
        "complete": True,
        "allocation_policy": "source-native",
        "amounts": [
            {
                "amount": "60",
                "currency": "USD",
                "category": "allocated",
                "granularity": "namespace",
                "cluster_resource_id": CLUSTER,
                "namespace": "apps",
                "identity_basis": "name-only",
                "reference": "synthetic-opencost",
            }
        ],
    }


@pytest.mark.parametrize(
    "profile,projection_format,producer",
    [
        ("aks-cost-analysis", "reviewed-aks-cost-analysis-v1", "1.0.0"),
        ("opencost-allocation", "reviewed-opencost-allocation-v1", "1.117.6"),
        ("kubecost-allocation", "reviewed-kubecost-allocation-v1", "2.4.0"),
    ],
)
@pytest.mark.parametrize("complete", [False, True])
def test_project_allocation_cli_needs_no_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    projection_format: str,
    producer: str,
    complete: bool,
) -> None:
    projection = json.loads(json.dumps(opencost_projection()))
    projection.update(
        schema_version=projection_format, producer_version=producer, complete=complete
    )
    projection["amounts"].append({"amount": "12.125", "currency": "EUR", "category": "idle"})
    source = tmp_path / "allocation.json"
    source.write_text(json.dumps(projection), encoding="utf-8")
    original = source.read_bytes()
    expected = project_allocation(profile, projection)
    output = tmp_path / "normalized-allocation.json"

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network and reconciliation are forbidden during projection")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(CostManagementCollector, "collect_costs", denied)
    arguments = [
        "project-allocation",
        "--allocation-profile",
        profile,
        "--allocation",
        str(source),
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    payload = output.read_text(encoding="utf-8")
    assert CostAllocation.model_validate_json(payload) == expected
    assert source.read_bytes() == original
    assert "status" not in json.loads(payload)
    assert "estimated_monthly_savings" not in json.loads(payload)
    assert set(tmp_path.iterdir()) == {source, output}
    assert CliRunner().invoke(app, arguments).exit_code == 1
    assert output.read_text(encoding="utf-8") == payload


@pytest.mark.parametrize("defect", ["version", "pricing", "unknown", "amount", "period", "shape"])
def test_project_allocation_cli_fails_without_output_or_sensitive_errors(
    tmp_path: Path, defect: str
) -> None:
    projection = json.loads(json.dumps(opencost_projection()))
    projection["source_reference"] = "synthetic-private-marker"
    if defect == "version":
        projection["producer_version"] = "synthetic-private-marker"
    elif defect == "pricing":
        projection["pricing_basis"] = "list-price"
    elif defect == "unknown":
        projection["credentials"] = "synthetic-private-marker"
    elif defect == "amount":
        projection["amounts"][0]["amount"] = 60.0
    elif defect == "period":
        projection["period"]["end"] = START
    else:
        projection["shares"] = import_payload()["allocation"]["shares"]
    source = tmp_path / "allocation.json"
    source.write_text(json.dumps(projection), encoding="utf-8")
    output = tmp_path / "normalized-allocation.json"
    result = CliRunner().invoke(
        app,
        [
            "project-allocation",
            "--allocation-profile",
            "opencost-allocation",
            "--allocation",
            str(source),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2
    assert "synthetic-private-marker" not in result.output
    assert not output.exists()


def test_project_allocation_cli_requires_a_ledger_for_row_shares(tmp_path: Path) -> None:
    projection = dict(import_payload()["allocation"])
    projection.pop("profile")
    projection.update(schema_version="reviewed-allocation-shares-v1", producer_version="1.0.0")
    source = tmp_path / "shares.json"
    source.write_text(json.dumps(projection), encoding="utf-8")
    output = tmp_path / "normalized.json"
    result = CliRunner().invoke(
        app,
        [
            "project-allocation",
            "--allocation-profile",
            "reviewed-allocation-shares",
            "--allocation",
            str(source),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2
    assert not output.exists()


def test_azure_cost_details_projection_maps_allowlisted_fields() -> None:
    result = project_ledger("azure-cost-details-amortized", azure_projection())
    assert result.schema_version == "1.0"
    assert result.ledger_profile.id == "azure-cost-details-amortized"
    assert result.rows[0].amount == 100
    assert result.rows[0].source_category == "Virtual Machines"
    assert result.allocation is None


def test_focus_effective_cost_projection_maps_to_effective_ledger() -> None:
    result = project_ledger("finops-focus", focus_projection())
    assert result.cost_basis == "effective"
    assert result.rows[0].charge_category == "compute"
    assert result.rows[0].source_category == "Compute"


def reconcile_focus(**changes: object) -> CostReconciliation:
    payload = focus_projection()
    payload["rows"][0].update(changes)
    ledger = project_ledger("finops-focus", payload)
    allocation = import_payload()["allocation"]
    allocation["cost_basis"] = "effective"
    for share in allocation["shares"]:
        share["row_id"] = "focus-1"
    evidence = CostImport.model_validate(
        ledger.model_dump(mode="json") | {"allocation": allocation}
    )
    return CostManagementCollector().collect_costs(evidence, as_of=AS_OF)


def test_focus_usage_retains_source_semantics_and_replays() -> None:
    result = reconcile_focus()
    assert result.status == "reconciled"
    row = result.rows[0].original
    assert row.focus.charge_category == "Usage"
    assert row.focus.pricing_category == "Standard"
    assert row.pricing_model == "OnDemand"
    assert CostReconciliation.model_validate_json(result.model_dump_json()) == result
    assert result.estimated_monthly_savings is None


@pytest.mark.parametrize("category", ["Purchase", "Tax", "Credit", "Adjustment"])
@pytest.mark.parametrize("amount", ["100.00", "-10.00"])
def test_focus_nonusage_charges_keep_amounts_and_never_reconcile(
    category: str, amount: str
) -> None:
    result = reconcile_focus(
        charge_category=category,
        pricing_category="Standard" if category == "Purchase" else None,
        effective_cost=amount,
    )
    assert result.status == "blocked"
    assert "unsupported-charge" in result.reason_codes
    assert result.rows[0].original.charge_type == category
    assert result.rows[0].original.focus.charge_category == category
    assert result.rows[0].original.amount == Decimal(amount)
    assert result.rows[0].unallocated == Decimal(amount)
    assert result.rows[0].allocations == []
    assert result.currencies[0].total == Decimal(amount)


def test_focus_positive_usage_correction_never_becomes_ordinary_usage() -> None:
    result = reconcile_focus(charge_class="Correction")
    assert result.status == "blocked"
    assert "unsupported-charge" in result.reason_codes
    assert result.rows[0].original.focus.charge_class == "Correction"
    assert result.rows[0].original.amount == Decimal("100")
    assert result.rows[0].allocations == []


def test_focus_negative_usage_refund_is_preserved_and_blocked() -> None:
    result = reconcile_focus(effective_cost="-10.00")
    assert result.status == "blocked"
    assert "unsupported-charge" in result.reason_codes
    assert result.rows[0].original.charge_type == "Usage"
    assert result.rows[0].original.amount == Decimal("-10")


def test_focus_dynamic_pricing_is_not_relabelled_as_on_demand_or_spot() -> None:
    result = reconcile_focus(pricing_category="Dynamic")
    assert result.status == "reconciled"
    assert result.rows[0].original.pricing_model == "Dynamic"
    assert result.rows[0].original.focus.pricing_category == "Dynamic"


@pytest.mark.parametrize(
    "field,value",
    [("charge_type", "Purchase"), ("pricing_model", "Spot"), ("benefit_id", "invented")],
)
def test_normalized_focus_rows_cannot_contradict_original_semantics(field: str, value: str) -> None:
    payload = project_ledger("finops-focus", focus_projection()).model_dump(mode="json")
    payload["rows"][0][field] = value
    with pytest.raises(ValidationError, match="match the retained FOCUS metadata"):
        CostImport.model_validate(payload)


def test_normalized_focus_import_without_source_metadata_is_blocked() -> None:
    original = reconcile_focus()
    payload = original.evidence.model_dump(mode="json")
    payload["rows"][0]["focus"] = None
    result = CostManagementCollector().collect_costs(
        CostImport.model_validate(payload), as_of=AS_OF
    )
    assert result.status == "blocked"
    assert "focus-metadata-missing" in result.reason_codes


@pytest.mark.parametrize(
    "category,discount_type", [("Usage", "Reservation"), ("Spend", "Savings Plan")]
)
def test_focus_committed_usage_preserves_benefit_identity(
    category: str, discount_type: str
) -> None:
    result = reconcile_focus(
        pricing_category="Committed",
        commitment_discount_category=category,
        commitment_discount_type=discount_type,
        commitment_discount_id="synthetic-benefit",
        commitment_discount_status="Used",
    )
    assert result.status == "reconciled"
    row = result.rows[0].original
    assert row.pricing_model == "Committed"
    assert row.benefit_id == "synthetic-benefit"
    assert row.focus.commitment_discount_category == category
    assert row.focus.commitment_discount_type == discount_type
    assert row.focus.commitment_discount_status == "Used"
    assert result.estimated_monthly_savings is None


@pytest.mark.parametrize("status", ["Unused", None])
def test_focus_unused_or_unknown_commitment_consumption_is_blocked(status: str | None) -> None:
    result = reconcile_focus(
        pricing_category="Committed",
        commitment_discount_category="Usage",
        commitment_discount_type="Reservation",
        commitment_discount_id="synthetic-benefit",
        commitment_discount_status=status,
    )
    assert result.status == "blocked"
    assert result.rows[0].original.focus.commitment_discount_status == status
    assert result.rows[0].original.amount == Decimal("100")
    assert result.rows[0].allocations == []


def test_focus_committed_usage_cannot_bypass_missing_benefit_gate() -> None:
    result = reconcile_focus(
        pricing_category="Committed",
        commitment_discount_category="Spend",
        commitment_discount_type="Savings Plan",
        commitment_discount_status="Used",
    )
    assert result.status == "blocked"
    assert "benefit-metadata-missing" in result.reason_codes
    assert result.rows[0].allocations == []


def test_focus_standard_usage_cannot_hide_commitment_metadata() -> None:
    result = reconcile_focus(commitment_discount_id="synthetic-benefit")
    assert result.status == "blocked"
    assert "focus-pricing-inconsistent" in result.reason_codes


def test_focus_other_pricing_is_preserved_but_not_financially_reconciled() -> None:
    result = reconcile_focus(pricing_category="Other")
    assert result.status == "blocked"
    assert "unsupported-pricing-model" in result.reason_codes
    assert result.rows[0].original.focus.pricing_category == "Other"
    assert result.rows[0].original.amount == Decimal("100")


@pytest.mark.parametrize(
    "field,value",
    [
        ("charge_category", "Usage-Based"),
        ("pricing_category", "On-Demand"),
        ("charge_class", "Unknown"),
        ("commitment_discount_status", "Unknown"),
        ("pricing_category", None),
    ],
)
def test_focus_unknown_or_missing_required_semantics_are_rejected(
    field: str, value: str | None
) -> None:
    payload = focus_projection()
    payload["rows"][0][field] = value
    with pytest.raises(ValidationError):
        project_ledger("finops-focus", payload)


def test_opencost_projection_stays_source_native_aggregate() -> None:
    result = project_allocation("opencost-allocation", opencost_projection())
    assert result.profile.id == "opencost-allocation"
    assert result.shares == []
    assert result.amounts[0].namespace == "apps"
    assert result.pricing_basis == "billing-ledger"


@pytest.mark.parametrize("profile_id", ["opencost-allocation", "kubecost-allocation"])
@pytest.mark.parametrize("pricing_basis", ["list-price", "source-declared"])
def test_vendor_allocation_cannot_relabel_estimates_as_billing_cost(
    profile_id: str, pricing_basis: str
) -> None:
    payload = opencost_projection()
    if profile_id == "kubecost-allocation":
        payload["schema_version"] = "reviewed-kubecost-allocation-v1"
        payload["producer_version"] = "2.4.0"
    payload["pricing_basis"] = pricing_basis
    with pytest.raises(ValueError, match="pricing"):
        project_allocation(profile_id, payload)


@pytest.mark.parametrize("source", ["azure", "focus", "opencost"])
def test_projectors_reject_uncharacterized_versions_before_producing_evidence(source: str) -> None:
    if source == "opencost":
        payload = opencost_projection()
        payload["producer_version"] = "99.0.0"
        with pytest.raises(ValueError, match="producer version"):
            project_allocation("opencost-allocation", payload)
    else:
        payload = azure_projection() if source == "azure" else focus_projection()
        payload["producer_version"] = "99.0.0"
        with pytest.raises(ValueError, match="producer version"):
            project_ledger(
                "azure-cost-details-amortized" if source == "azure" else "finops-focus", payload
            )


def test_projectors_reject_unknown_fields() -> None:
    payload = azure_projection()
    payload["download_url"] = "https://example.invalid/secret"
    with pytest.raises(ValidationError):
        project_ledger("azure-cost-details-amortized", payload)


def test_project_costs_cli_combines_saved_sources_exclusively(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    allocation = tmp_path / "allocation.json"
    output = tmp_path / "normalized.json"
    ledger.write_text(json.dumps(azure_projection()), encoding="utf-8")
    allocation.write_text(json.dumps(opencost_projection()), encoding="utf-8")
    args = [
        "project-costs",
        "--ledger-profile",
        "azure-cost-details-amortized",
        "--ledger",
        str(ledger),
        "--allocation-profile",
        "opencost-allocation",
        "--allocation",
        str(allocation),
        "--output",
        str(output),
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["allocation"]["profile"]["id"] == "opencost-allocation"
    assert runner.invoke(app, args).exit_code == 1
