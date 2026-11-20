from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_history import TENANT, write_run
from typer.testing import CliRunner

from aks_fleet_efficiency.assessment import OfflineAssessment
from aks_fleet_efficiency.cli import app
from aks_fleet_efficiency.experiments import (
    ExperimentCriterion,
    ExperimentHandoff,
    ExperimentHandoffCheck,
    ExperimentHandoffRequest,
    ExperimentOutcomeRequest,
    prepare_experiment_handoff,
    read_experiment_outcome_bundle,
    record_experiment_outcome,
    write_experiment_handoff_bundle,
)

AS_OF = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


def checks() -> list[ExperimentHandoffCheck]:
    return [
        ExperimentHandoffCheck(kind=kind, description=f"Review {kind} evidence.")
        for kind in ["baseline", "canary", "observe", "abort", "rollback", "no_change"]
    ]


def handoff(**changes: object) -> ExperimentHandoff:
    payload: dict[str, object] = {
        "tenant_id": "00000000-0000-0000-0000-000000000000",
        "cluster_resource_id": (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/rg-synthetic/providers/Microsoft.ContainerService/"
            "managedClusters/aks-synthetic"
        ),
        "cluster_uid": "cluster-uid-synthetic",
        "run_id": DIGEST,
        "finding_id": "finding-synthetic",
        "pack_id": "AKS-RQ-002",
        "pack_version": "1.0.0",
        "generated_at": AS_OF,
        "baseline_window_start": datetime(2026, 10, 22, 12, 0, tzinfo=UTC),
        "baseline_window_end": AS_OF,
        "baseline_configuration_digest": DIGEST,
        "dimension": "cpu_request",
        "controller": "none",
        "owner_ref": "owner-ref-synthetic",
        "reviewer_ref": "reviewer-ref-synthetic",
        "hypothesis": "A CPU request experiment may release reservation safely.",
        "unchanged_dimensions": ["memory_request", "memory_limit", "replica_floor"],
        "representative_scenarios": ["startup", "representative_peak"],
        "criteria": [
            ExperimentCriterion(
                measure_ref="latency-slo-synthetic",
                operator="lte",
                threshold=250,
                unit="milliseconds",
            )
        ],
        "observation_duration_seconds": 3600,
        "checks": checks(),
        "rollback_reference": "rollback-runbook-synthetic",
        "rollback_value_reference": "original-cpu-request-synthetic",
        "unresolved_prerequisites": [],
        "alternatives": ["retain_current_configuration"],
        "state": "prepared",
    }
    payload.update(changes)
    return ExperimentHandoff.model_validate(payload)


def test_experiment_handoff_is_portable_and_has_no_execution_authority() -> None:
    result = handoff()

    assert result.state == "prepared"
    assert result.execution_authority == "none"
    assert {check.kind for check in result.checks} == {
        "baseline",
        "canary",
        "observe",
        "abort",
        "rollback",
        "no_change",
    }


def test_experiment_handoff_requires_all_stages() -> None:
    valid_checks = checks()
    invalid_checks = [*valid_checks[:-1], valid_checks[0]]
    with pytest.raises(ValidationError, match="all staged checks"):
        handoff(checks=invalid_checks)


def test_experiment_handoff_cannot_be_prepared_with_unresolved_prerequisites() -> None:
    with pytest.raises(ValidationError, match="state must reflect prerequisites"):
        handoff(unresolved_prerequisites=["representative_load"])


def test_experiment_handoff_keeps_selected_dimension_out_of_unchanged_dimensions() -> None:
    with pytest.raises(ValidationError, match="selected dimension cannot be unchanged"):
        handoff(unchanged_dimensions=["cpu_request", "memory_request"])


def handoff_request(finding_id: str) -> ExperimentHandoffRequest:
    return ExperimentHandoffRequest(
        finding_id=finding_id,
        dimension="controller_configuration",
        controller="nap",
        owner_ref="owner-ref-synthetic",
        reviewer_ref="reviewer-ref-synthetic",
        hypothesis="One bounded NAP policy experiment may explain retained capacity.",
        unchanged_dimensions=["cpu_request", "memory_request", "memory_limit"],
        representative_scenarios=["representative_peak", "voluntary_disruption"],
        criteria=[
            ExperimentCriterion(
                measure_ref="availability-slo-synthetic",
                operator="gte",
                threshold=99.9,
                unit="percent",
            )
        ],
        observation_duration_seconds=3600,
        checks=checks(),
        rollback_reference="rollback-runbook-synthetic",
        rollback_value_reference="original-nap-policy-synthetic",
        unresolved_prerequisites=[],
    )


def test_prepare_experiment_derives_original_finding_provenance(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    finding = assessment.report.recommendations[0]

    result = prepare_experiment_handoff(
        directory,
        tenant_id=TENANT,
        request=handoff_request(finding.id),
        as_of=AS_OF,
    )

    assert result.finding_id == finding.id
    assert result.pack_id == finding.rule_id
    assert result.pack_version == finding.rule_version
    assert result.baseline_configuration_digest == assessment.report.configuration_digest
    assert result.execution_authority == "none"


def test_prepare_experiment_rejects_guarded_value_without_replayed_proposal(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    finding = assessment.report.recommendations[0]
    assert finding.proposed_requests is None
    request = handoff_request(finding.id).model_copy(
        update={
            "dimension": "cpu_request",
            "unchanged_dimensions": ["memory_request", "memory_limit"],
            "controller": "none",
            "proposal_source": "guarded_finding",
            "proposed_value": 250,
            "proposed_unit": "mCPU",
        }
    )

    with pytest.raises(ValueError, match="replayed finding proposal"):
        prepare_experiment_handoff(directory, tenant_id=TENANT, request=request, as_of=AS_OF)


def guarded_assessment(tmp_path: Path) -> Path:
    examples = Path(__file__).resolve().parents[1] / "examples"
    directory = tmp_path / "guarded"
    assessment_result = CliRunner().invoke(
        app,
        [
            "assess",
            "--fragments",
            str(examples / "fixtures/history-assessment.json"),
            "--config",
            str(examples / "cpu-pack-config.yaml"),
            "--mode",
            "guarded",
            "--as-of",
            AS_OF.isoformat(),
            "--artifacts",
            str(directory),
        ],
    )
    assert assessment_result.exit_code == 3, assessment_result.output
    return directory


def test_prepare_experiment_binds_exact_guarded_value_and_unit(tmp_path: Path) -> None:
    directory = guarded_assessment(tmp_path)
    assessment = OfflineAssessment.model_validate_json((directory / "assessment.json").read_bytes())
    finding = assessment.report.recommendations[0]
    assert finding.proposed_requests is not None
    assert finding.proposed_requests.cpu_mcores == 500
    request = handoff_request(finding.id).model_copy(
        update={
            "dimension": "cpu_request",
            "unchanged_dimensions": ["memory_request", "memory_limit"],
            "controller": "none",
            "proposal_source": "guarded_finding",
            "proposed_value": 500.0,
            "proposed_unit": "mCPU",
        }
    )

    result = prepare_experiment_handoff(directory, tenant_id=TENANT, request=request, as_of=AS_OF)
    assert (result.proposed_value, result.proposed_unit) == (500, "mCPU")

    for mismatch in ({"proposed_value": 250.0}, {"proposed_unit": "cores"}):
        with pytest.raises(ValueError, match="replayed finding proposal"):
            prepare_experiment_handoff(
                directory,
                tenant_id=TENANT,
                request=request.model_copy(update=mismatch),
                as_of=AS_OF,
            )


def test_saved_dashboard_to_no_change_decision(tmp_path: Path) -> None:
    directory = guarded_assessment(tmp_path)
    assessment_path = directory / "assessment.json"
    assessment = OfflineAssessment.model_validate_json(assessment_path.read_bytes())
    runner = CliRunner()
    dashboard = tmp_path / "dashboard"
    exported = runner.invoke(
        app,
        [
            "catalog",
            "export",
            "AKS-RQ-002",
            "--config",
            "examples/cpu-pack-config.yaml",
            "--entities",
            "examples/cpu-pack-entities.json",
            "--source",
            "synthetic",
            "--mode",
            "guarded",
            "--grafana",
            "--assessment-artifacts",
            str(directory),
            "--output",
            str(dashboard),
        ],
    )
    assert exported.exit_code == 0, exported.output
    assert "Retained assessment quality" in (dashboard / "dashboard.json").read_text(
        encoding="utf-8"
    )
    capacity = tmp_path / "capacity.md"
    reviewed = runner.invoke(
        app,
        [
            "review-retained-capacity",
            "--assessment",
            str(assessment_path),
            "--tenant",
            TENANT,
            "--output",
            str(capacity),
        ],
    )
    assert reviewed.exit_code == 0, reviewed.output
    capacity_review = capacity.read_text(encoding="utf-8")
    assert "not selected" in capacity_review
    assert "Scheduler fit: blocked" in capacity_review

    bundle = tmp_path / "handoff"
    request = handoff_request(assessment.report.recommendations[0].id).model_copy(
        update={
            "dimension": "evidence_only",
            "controller": "none",
            "unresolved_prerequisites": ["retain_intentional_reserve"],
        }
    )
    handoff_result = prepare_experiment_handoff(
        directory, tenant_id=TENANT, request=request, as_of=AS_OF
    )
    assert handoff_result.state == "blocked"
    write_experiment_handoff_bundle(bundle, handoff_result)
    outcome = record_experiment_outcome(
        bundle,
        request=ExperimentOutcomeRequest(
            outcome="not_executed", execution_reference="retain-reserve-synthetic"
        ),
        recorded_at=AS_OF,
    )
    assert outcome.outcome == "not_executed"
    assert outcome.after_assessment_digest is None
    assert outcome.execution_authority == "none"


def test_experiment_bundle_is_exclusive_and_manifest_bound(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    handoff_result = prepare_experiment_handoff(
        directory,
        tenant_id=TENANT,
        request=handoff_request(assessment.report.recommendations[0].id),
        as_of=AS_OF,
    )
    output = tmp_path / "experiment"

    write_experiment_handoff_bundle(output, handoff_result)

    assert (
        ExperimentHandoff.model_validate_json(
            (output / "experiment.json").read_text(encoding="utf-8")
        )
        == handoff_result
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"experiment.json", "experiment.md"}
    with pytest.raises(FileExistsError):
        write_experiment_handoff_bundle(output, handoff_result)


def test_prepare_experiment_cli_writes_portable_bundle(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(
        handoff_request(assessment.report.recommendations[0].id).model_dump_json(),
        encoding="utf-8",
    )
    output = tmp_path / "prepared-experiment"

    result = CliRunner().invoke(
        app,
        [
            "prepare-experiment",
            "--assessment",
            str(directory / "assessment.json"),
            "--tenant",
            TENANT,
            "--request",
            str(request_path),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "experiment.json").is_file()
    assert (output / "experiment.md").is_file()
    assert (output / "manifest.json").is_file()


def test_record_experiment_outcome_binds_verified_handoff(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    handoff_result = prepare_experiment_handoff(
        directory,
        tenant_id=TENANT,
        request=handoff_request(assessment.report.recommendations[0].id),
        as_of=AS_OF,
    )
    bundle = tmp_path / "experiment"
    write_experiment_handoff_bundle(bundle, handoff_result)

    result = record_experiment_outcome(
        bundle,
        request=ExperimentOutcomeRequest(
            outcome="completed",
            execution_reference="change-record-synthetic",
            evidence_references=["test-result-synthetic"],
            before_assessment_digest="b" * 64,
            after_assessment_digest="c" * 64,
        ),
        recorded_at=AS_OF,
    )

    assert result.outcome == "completed"
    assert result.finding_id == handoff_result.finding_id
    assert result.execution_authority == "none"
    assert (
        result.experiment_digest
        == json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["files"][
            "experiment.json"
        ]
    )


def test_blocked_handoff_cannot_be_recorded_completed(tmp_path: Path) -> None:
    blocked = handoff(unresolved_prerequisites=["representative_load"], state="blocked")
    bundle = tmp_path / "blocked-experiment"
    write_experiment_handoff_bundle(bundle, blocked)

    with pytest.raises(ValueError, match="blocked handoff"):
        record_experiment_outcome(
            bundle,
            request=ExperimentOutcomeRequest(
                outcome="completed",
                execution_reference="change-record-synthetic",
                evidence_references=["test-result-synthetic"],
                before_assessment_digest="b" * 64,
                after_assessment_digest="c" * 64,
            ),
            recorded_at=AS_OF,
        )


def test_record_experiment_outcome_cli_writes_portable_bundle(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "assessment", as_of=AS_OF)
    assessment = OfflineAssessment.model_validate_json(
        (directory / "assessment.json").read_text(encoding="utf-8")
    )
    handoff_result = prepare_experiment_handoff(
        directory,
        tenant_id=TENANT,
        request=handoff_request(assessment.report.recommendations[0].id),
        as_of=AS_OF,
    )
    experiment = tmp_path / "experiment"
    write_experiment_handoff_bundle(experiment, handoff_result)
    request_path = tmp_path / "outcome-request.json"
    request_path.write_text(
        ExperimentOutcomeRequest(
            outcome="completed",
            execution_reference="change-record-synthetic",
            evidence_references=["test-result-synthetic"],
            before_assessment_digest="b" * 64,
            after_assessment_digest="c" * 64,
        ).model_dump_json(),
        encoding="utf-8",
    )
    output = tmp_path / "recorded-outcome"

    result = CliRunner().invoke(
        app,
        [
            "record-experiment-outcome",
            "--experiment",
            str(experiment),
            "--request",
            str(request_path),
            "--as-of",
            AS_OF.isoformat(),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "outcome.json").is_file()
    assert (output / "outcome.md").is_file()
    assert (output / "manifest.json").is_file()
    manifest, recorded = read_experiment_outcome_bundle(output)
    assert manifest.experiment_digest == recorded.experiment_digest
    assert recorded.outcome == "completed"
