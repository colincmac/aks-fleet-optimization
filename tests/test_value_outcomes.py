from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from test_assessment import profile
from test_experiments import handoff_request
from test_history import TENANT, write_run
from typer.testing import CliRunner

from aks_fleet_efficiency.artifacts import write_assessment_artifacts
from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment, assess_fragments
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.experiments import (
    ExperimentOutcomeRequest,
    prepare_experiment_handoff,
    record_experiment_outcome,
    write_experiment_handoff_bundle,
    write_experiment_outcome_bundle,
)
from aks_fleet_efficiency.history import _read_verified_archive, _summary
from aks_fleet_efficiency.value_outcomes import (
    CapacityEffect,
    EngineeringChangeRecord,
    EngineeringWindowObservation,
    ExperimentValueOutcome,
    ExperimentValueOutcomeRequest,
    FinancialEffect,
    ResourceChange,
    review_cpu_request_outcome,
    validate_experiment_value_outcome,
    write_experiment_value_outcome_bundle,
)

AS_OF = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("matched", "observed_change"),
        ("slo_regression", "regression"),
        ("different_demand", "inconclusive"),
        ("missing_slo", "inconclusive"),
        ("partial_service", "inconclusive"),
        ("overlapping_change", "inconclusive"),
        ("recreated_hpa", "inconclusive"),
        ("other_config", "inconclusive"),
        ("rollback", "inconclusive"),
    ],
)
def test_cpu_request_outcome_uses_originals_and_independent_service_observations(
    tmp_path: Path,
    case: str,
    expected: str,
) -> None:
    fixture = Path("examples") / "fixtures" / "autoscalers-assessment.json"
    observations = []
    for offset in range(2):
        fragments = AssessmentFragments.model_validate_json(fixture.read_bytes())
        fragments.metrics.clear()
        start = AS_OF - timedelta(hours=2) + timedelta(hours=2 * offset)
        end = start + timedelta(hours=1)
        fragments.window_start, fragments.window_end = start, end
        metadata = fragments.kubernetes[0]
        metadata.generated_at = end
        metadata.collection.started_at = start
        metadata.collection.completed_at = end
        metadata.collection.source_observed_at = end
        if offset:
            pod = next(item for item in metadata.resources if item.kind == "Pod")
            pod.spec["containers"][0]["resources"]["requests"]["cpu"] = "500m"
            if case == "other_config":
                pod.spec["containers"][0]["resources"]["requests"]["memory"] = "4Gi"
            if case == "recreated_hpa":
                hpa = next(
                    item for item in metadata.resources if item.kind == "HorizontalPodAutoscaler"
                )
                hpa.uid = "recreated-hpa"
        vpa = next(item for item in metadata.resources if item.kind == "VerticalPodAutoscaler")
        vpa.spec["updatePolicy"]["updateMode"] = "Off"
        config = profile()
        assessment = assess_fragments(fragments, config, as_of=end)
        directory = tmp_path / str(offset)
        write_assessment_artifacts(directory, fragments, assessment, config.analysis)
        original, replayed, locked = _read_verified_archive(directory, tenant_id=UUID(TENANT))
        observations.append(
            EngineeringWindowObservation(
                run_id=_summary(original, replayed, locked).run_id,
                window_start=start,
                window_end=end,
                source="synthetic-sli-v1",
                observation_ref=f"synthetic-window-{offset}",
                coverage_complete=not (offset and case == "partial_service"),
                request_count=2000 if offset and case == "different_demand" else 1000,
                success_count=980 if offset and case == "slo_regression" else 1000,
            )
        )
    cluster = metadata.cluster_resource_id
    cluster_uid = metadata.cluster_uid
    assert cluster_uid is not None
    record = EngineeringChangeRecord(
        schema_version="1.0",
        tenant_id=UUID(TENANT),
        cluster_resource_id=cluster,
        cluster_uid=cluster_uid,
        namespace_uid="namespace-uid",
        workload_uid="workload-uid",
        hpa_uid="synthetic-hpa-uid",
        container="api",
        approval_ref="synthetic-approval",
        changed_at=AS_OF + timedelta(minutes=30)
        if case == "overlapping_change"
        else AS_OF - timedelta(minutes=30),
        before=observations[0],
        after=observations[1].model_copy(update={"success_count": None})
        if case == "missing_slo"
        else observations[1],
        minimum_success_ratio="0.99",
        maximum_demand_change_ratio="0.1",
        owner_disposition="rolled_back" if case == "rollback" else "review",
    )
    result = review_cpu_request_outcome(tmp_path / "0", tmp_path / "1", record=record)
    assert result.status == expected
    if expected != "inconclusive":
        assert result.before.cpu_request_mcpu == 1000
        assert result.after.cpu_request_mcpu == 500
        assert result.before.configuration_revision != result.after.configuration_revision
        assert result.before_service.request_count == result.after_service.request_count == 1000
    if case == "rollback":
        assert result.owner_disposition == "rolled_back"


def resource_change() -> ResourceChange:
    return ResourceChange(
        status="observed",
        dimension="cpu_request",
        unit="mCPU",
        before="1000",
        after="750",
        before_assessment_digest=DIGEST,
        after_assessment_digest=DIGEST,
        demand_comparable=True,
        reason_codes=[],
    )


def outcome(**changes: object) -> ExperimentValueOutcome:
    payload: dict[str, object] = {
        "tenant_id": "00000000-0000-0000-0000-000000000000",
        "cluster_resource_id": (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/"
            "managedClusters/aks-synthetic"
        ),
        "cluster_uid": "cluster-uid-synthetic",
        "experiment_digest": DIGEST,
        "evaluated_at": AS_OF,
        "execution_outcome": "completed",
        "execution_reference": "change-record-synthetic",
        "engineering": resource_change(),
        "capacity": CapacityEffect(status="not_supplied", reason_codes=[]),
        "modeled_cost_avoidance": FinancialEffect(status="not_supplied", reason_codes=[]),
        "reconciled_bill_effect": FinancialEffect(status="not_supplied", reason_codes=[]),
        "reviewer_reference": "finops-review-synthetic",
    }
    payload.update(changes)
    return ExperimentValueOutcome.model_validate(payload)


def test_value_outcome_preserves_engineering_result_without_finance() -> None:
    result = outcome()

    assert result.engineering.status == "observed"
    assert result.capacity.status == "not_supplied"
    assert result.modeled_cost_avoidance.status == "not_supplied"
    assert result.reconciled_bill_effect.status == "not_supplied"
    assert result.estimated_monthly_savings is None


def test_value_bundle_hashes_exact_payload_bytes_and_escapes_markdown(tmp_path: Path) -> None:
    directory = tmp_path / "value"
    write_experiment_value_outcome_bundle(directory, outcome(reviewer_reference="<r> *[ref]*"))
    manifest = json.loads((directory / "manifest.json").read_bytes())
    assert set(manifest["files"]) == {"value.json", "value.md"}
    for name, digest in manifest["files"].items():
        content = (directory / name).read_bytes()
        assert content.endswith(b"\n") and not content.endswith(b"\n\n")
        assert sha256(content).hexdigest() == digest
    assert rb"&lt;r&gt; \*\[ref\]\*" in (directory / "value.md").read_bytes()


def test_capacity_effect_cannot_be_inferred_from_request_reduction() -> None:
    with pytest.raises(ValidationError, match="Observed capacity requires"):
        CapacityEffect(status="observed", reason_codes=[])


def test_noncompleted_experiment_cannot_report_financial_effect() -> None:
    modeled = FinancialEffect(
        status="modeled",
        reason_codes=[],
        amount="25.00",
        currency="USD",
        evidence_digest=DIGEST,
        method_reference="counterfactual-v1",
    )

    with pytest.raises(ValidationError, match="completed execution"):
        outcome(execution_outcome="rolled_back", modeled_cost_avoidance=modeled)


def test_blocked_finance_does_not_block_observed_engineering() -> None:
    blocked = FinancialEffect(status="blocked", reason_codes=["period_not_comparable"])
    result = outcome(modeled_cost_avoidance=blocked)

    assert result.engineering.status == "observed"
    assert result.modeled_cost_avoidance.status == "blocked"


def experiment_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    handoff = prepare_experiment_handoff(
        directory,
        tenant_id=TENANT,
        request=handoff_request(assessment.report.recommendations[0].id),
        as_of=AS_OF,
    )
    experiment = tmp_path / "experiment"
    write_experiment_handoff_bundle(experiment, handoff)
    execution = record_experiment_outcome(
        experiment,
        request=ExperimentOutcomeRequest(
            outcome="completed",
            execution_reference="change-record-synthetic",
            evidence_references=["test-result-synthetic"],
            before_assessment_digest="b" * 64,
            after_assessment_digest="c" * 64,
        ),
        recorded_at=AS_OF,
    )
    recorded = tmp_path / "recorded"
    write_experiment_outcome_bundle(recorded, execution)
    return experiment, recorded


def value_request() -> ExperimentValueOutcomeRequest:
    return ExperimentValueOutcomeRequest(
        engineering=ResourceChange(
            status="declared",
            dimension="controller_configuration",
            unit="policy_revision",
            before="1",
            after="2",
            before_assessment_digest="b" * 64,
            after_assessment_digest="c" * 64,
            demand_comparable=True,
            reason_codes=[],
        ),
        capacity=CapacityEffect(status="not_supplied", reason_codes=[]),
        modeled_cost_avoidance=FinancialEffect(status="not_supplied", reason_codes=[]),
        reconciled_bill_effect=FinancialEffect(status="not_supplied", reason_codes=[]),
        reviewer_reference="finops-review-synthetic",
    )


@pytest.mark.parametrize("layer", ["engineering", "capacity"])
def test_value_builder_rejects_digest_only_observations(tmp_path: Path, layer: str) -> None:
    experiment, recorded = experiment_artifacts(tmp_path)
    request = value_request()
    if layer == "engineering":
        request.engineering.status = "observed"
    else:
        request.capacity = CapacityEffect(
            status="observed", before_node_hours="1", after_node_hours="0", evidence_digest=DIGEST
        )

    with pytest.raises(ValueError, match="require original evidence"):
        validate_experiment_value_outcome(experiment, recorded, request=request, evaluated_at=AS_OF)


def test_value_builder_binds_experiment_and_declared_engineering_references(
    tmp_path: Path,
) -> None:
    experiment, recorded = experiment_artifacts(tmp_path)

    result = validate_experiment_value_outcome(
        experiment,
        recorded,
        request=value_request(),
        evaluated_at=AS_OF,
    )

    assert result.execution_outcome == "completed"
    assert result.engineering.status == "declared"
    assert result.estimated_monthly_savings is None


def test_value_builder_refuses_positive_finance_without_qualified_adapter(
    tmp_path: Path,
) -> None:
    experiment, recorded = experiment_artifacts(tmp_path)
    request = value_request()
    request.modeled_cost_avoidance = FinancialEffect(
        status="modeled",
        amount="25.00",
        currency="USD",
        evidence_digest=DIGEST,
        method_reference="counterfactual-v1",
        reason_codes=[],
    )

    with pytest.raises(ValueError, match="qualified financial adapter"):
        validate_experiment_value_outcome(
            experiment,
            recorded,
            request=request,
            evaluated_at=AS_OF,
        )


def test_validate_value_outcome_cli_writes_portable_bundle(tmp_path: Path) -> None:
    experiment, recorded = experiment_artifacts(tmp_path)
    request_path = tmp_path / "value-request.json"
    request_path.write_text(value_request().model_dump_json(), encoding="utf-8")
    output = tmp_path / "value-outcome"

    result = CliRunner().invoke(
        app,
        [
            "validate-value-outcome",
            "--experiment",
            str(experiment),
            "--outcome",
            str(recorded),
            "--request",
            str(request_path),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "value.json").is_file()
    assert (output / "value.md").is_file()
    assert (output / "manifest.json").is_file()
