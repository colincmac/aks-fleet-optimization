from __future__ import annotations

import html
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from aks_fleet_efficiency.advisory import ExperimentController, ExperimentDimension
from aks_fleet_efficiency.artifacts import write_exclusive
from aks_fleet_efficiency.catalog.models import CatalogModel, Digest, PackId, Text, Version
from aks_fleet_efficiency.history import _read_text, _read_verified_archive, _summary
from aks_fleet_efficiency.models import Recommendation, UtcDatetime

ExperimentCheckKind = Literal["baseline", "canary", "observe", "abort", "rollback", "no_change"]


def _no_change_alternative() -> list[Literal["retain_current_configuration"]]:
    return ["retain_current_configuration"]


class ExperimentCriterion(CatalogModel):
    measure_ref: Text
    operator: Literal["lt", "lte", "gt", "gte", "eq"]
    threshold: float
    unit: Text


class ExperimentHandoffCheck(CatalogModel):
    kind: ExperimentCheckKind
    description: Text
    evidence_refs: list[Digest] = Field(default_factory=list, max_length=32)


class ExperimentHandoffRequest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    finding_id: Text
    dimension: ExperimentDimension
    controller: ExperimentController
    owner_ref: Text
    reviewer_ref: Text
    hypothesis: Text
    unchanged_dimensions: list[ExperimentDimension] = Field(min_length=1, max_length=6)
    representative_scenarios: list[Text] = Field(min_length=1, max_length=32)
    criteria: list[ExperimentCriterion] = Field(min_length=1, max_length=32)
    observation_duration_seconds: int = Field(gt=0, le=2_592_000, strict=True)
    checks: list[ExperimentHandoffCheck] = Field(min_length=6, max_length=6)
    rollback_reference: Text
    rollback_value_reference: Text
    unresolved_prerequisites: list[Text] = Field(default_factory=list, max_length=32)
    alternatives: list[Literal["retain_current_configuration"]] = Field(
        default_factory=_no_change_alternative,
        min_length=1,
        max_length=1,
    )
    proposal_source: Literal["guarded_finding", "operator_supplied", "none"] = "none"
    proposed_value: float | None = None
    proposed_unit: Text | None = None
    ai_experiment_digest: Digest | None = None
    ai_state: Literal["unverified_experiment"] | None = None


class ExperimentHandoff(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["portable-experiment-handoff"] = "portable-experiment-handoff"
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    run_id: Digest
    finding_id: Text
    pack_id: PackId
    pack_version: Version
    generated_at: UtcDatetime
    baseline_window_start: UtcDatetime
    baseline_window_end: UtcDatetime
    baseline_configuration_digest: Digest
    dimension: ExperimentDimension
    controller: ExperimentController
    owner_ref: Text
    reviewer_ref: Text
    hypothesis: Text
    unchanged_dimensions: list[ExperimentDimension] = Field(min_length=1, max_length=6)
    representative_scenarios: list[Text] = Field(min_length=1, max_length=32)
    criteria: list[ExperimentCriterion] = Field(min_length=1, max_length=32)
    observation_duration_seconds: int = Field(gt=0, le=2_592_000, strict=True)
    checks: list[ExperimentHandoffCheck] = Field(min_length=6, max_length=6)
    rollback_reference: Text
    rollback_value_reference: Text
    unresolved_prerequisites: list[Text] = Field(default_factory=list, max_length=32)
    alternatives: list[Literal["retain_current_configuration"]] = Field(min_length=1, max_length=1)
    proposal_source: Literal["guarded_finding", "operator_supplied", "none"] = "none"
    proposed_value: float | None = None
    proposed_unit: Text | None = None
    ai_experiment_digest: Digest | None = None
    ai_state: Literal["unverified_experiment"] | None = None
    state: Literal["prepared", "blocked"]
    execution_authority: Literal["none"] = "none"
    notice: Literal[
        "Portable review record only; not change approval, executable configuration, "
        "proof of execution, a safe setting or financial value."
    ] = (
        "Portable review record only; not change approval, executable configuration, "
        "proof of execution, a safe setting or financial value."
    )

    @model_validator(mode="after")
    def validate_handoff(self) -> ExperimentHandoff:
        if (
            self.baseline_window_end <= self.baseline_window_start
            or self.generated_at < self.baseline_window_end
        ):
            raise ValueError("Experiment handoff requires an ordered baseline and clock")
        if len(set(self.unchanged_dimensions)) != len(self.unchanged_dimensions):
            raise ValueError("Unchanged dimensions must be distinct")
        if self.dimension in self.unchanged_dimensions:
            raise ValueError("The selected dimension cannot be unchanged")
        if len(set(self.representative_scenarios)) != len(self.representative_scenarios):
            raise ValueError("Representative scenarios must be distinct")
        criterion_keys = [(item.measure_ref, item.unit) for item in self.criteria]
        if len(set(criterion_keys)) != len(criterion_keys):
            raise ValueError("Experiment criteria must be distinct")
        check_kinds = [check.kind for check in self.checks]
        if set(check_kinds) != {
            "baseline",
            "canary",
            "observe",
            "abort",
            "rollback",
            "no_change",
        } or len(set(check_kinds)) != len(check_kinds):
            raise ValueError("Experiment handoffs require all staged checks exactly once")
        for check in self.checks:
            if len(set(check.evidence_refs)) != len(check.evidence_refs):
                raise ValueError("Experiment check evidence references must be distinct")
        if self.alternatives != ["retain_current_configuration"]:
            raise ValueError("Experiment handoffs require the no-change alternative")
        expected_state = "blocked" if self.unresolved_prerequisites else "prepared"
        if self.state != expected_state:
            raise ValueError("Experiment handoff state must reflect prerequisites")
        proposal_fields = (self.proposed_value, self.proposed_unit)
        if self.proposal_source == "none":
            if any(value is not None for value in proposal_fields):
                raise ValueError("A proposal value requires an admitted proposal source")
        elif any(value is None for value in proposal_fields):
            raise ValueError("An admitted proposal source requires a value and unit")
        if (self.ai_experiment_digest is None) != (self.ai_state is None):
            raise ValueError("Optional AI attachment requires both digest and unverified state")
        return self


class ExperimentBundleManifest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["prepared", "blocked"]
    experiment_digest: Digest
    files: dict[str, Digest]

    @model_validator(mode="after")
    def validate_files(self) -> ExperimentBundleManifest:
        if set(self.files) != {"experiment.json", "experiment.md"}:
            raise ValueError("Experiment bundle requires the exact supported file set")
        if self.experiment_digest != self.files["experiment.json"]:
            raise ValueError("Experiment digest must bind the original JSON file")
        return self


class ExperimentOutcomeRequest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    outcome: Literal["completed", "aborted", "rolled_back", "inconclusive", "not_executed"]
    execution_reference: Text
    evidence_references: list[Text] = Field(default_factory=list, max_length=32)
    before_assessment_digest: Digest | None = None
    after_assessment_digest: Digest | None = None

    @model_validator(mode="after")
    def validate_request(self) -> ExperimentOutcomeRequest:
        if len(set(self.evidence_references)) != len(self.evidence_references):
            raise ValueError("Execution evidence references must be distinct")
        if self.outcome == "completed" and (
            not self.evidence_references
            or self.before_assessment_digest is None
            or self.after_assessment_digest is None
        ):
            raise ValueError("Completed execution requires evidence and before/after assessments")
        if self.outcome == "not_executed" and (
            self.evidence_references or self.after_assessment_digest is not None
        ):
            raise ValueError("An unexecuted experiment cannot retain execution evidence")
        return self


class ExperimentExecutionOutcome(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    basis: Literal["operator-declared-experiment-outcome"] = "operator-declared-experiment-outcome"
    experiment_digest: Digest
    tenant_id: Text
    cluster_resource_id: Text
    cluster_uid: Text
    finding_id: Text
    dimension: ExperimentDimension
    recorded_at: UtcDatetime
    outcome: Literal["completed", "aborted", "rolled_back", "inconclusive", "not_executed"]
    execution_reference: Text
    evidence_references: list[Text] = Field(default_factory=list, max_length=32)
    before_assessment_digest: Digest | None = None
    after_assessment_digest: Digest | None = None
    state: Literal["operator_declared"] = "operator_declared"
    execution_authority: Literal["none"] = "none"
    notice: Literal[
        "Operator-declared outcome and references only; not proof of execution, approval, "
        "service safety, finding resolution, capacity release or financial value."
    ] = (
        "Operator-declared outcome and references only; not proof of execution, approval, "
        "service safety, finding resolution, capacity release or financial value."
    )


class ExperimentOutcomeBundleManifest(CatalogModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["completed", "aborted", "rolled_back", "inconclusive", "not_executed"]
    experiment_digest: Digest
    files: dict[str, Digest]

    @model_validator(mode="after")
    def validate_files(self) -> ExperimentOutcomeBundleManifest:
        if set(self.files) != {"outcome.json", "outcome.md"}:
            raise ValueError("Experiment outcome bundle requires the exact supported file set")
        return self


def _finding_proposal(
    finding: Recommendation, dimension: ExperimentDimension
) -> tuple[float, str] | None:
    requests = finding.proposed_requests
    if dimension == "cpu_request" and requests is not None and requests.cpu_mcores is not None:
        return requests.cpu_mcores, "mCPU"
    if dimension == "memory_request" and requests is not None and requests.memory_mib is not None:
        return requests.memory_mib, "MiB"
    if dimension == "memory_limit" and finding.proposed_limits is not None:
        return finding.proposed_limits.memory_mib, "MiB"
    if dimension == "replica_floor" and finding.proposed_replica_floor is not None:
        return float(finding.proposed_replica_floor), "replicas"
    return None


def prepare_experiment_handoff(
    directory: Path,
    *,
    tenant_id: str,
    request: ExperimentHandoffRequest,
    as_of: UtcDatetime,
) -> ExperimentHandoff:
    request = ExperimentHandoffRequest.model_validate(request.model_dump())
    archive, assessment, configuration = _read_verified_archive(
        directory, tenant_id=UUID(tenant_id)
    )
    report = assessment.report
    if len(assessment.snapshot.clusters) != 1:
        raise ValueError("Experiment handoff requires an exact single-cluster assessment")
    finding = next((item for item in report.recommendations if item.id == request.finding_id), None)
    if finding is None:
        raise ValueError("Experiment handoff requires one admitted recommendation finding")
    proposed_value, proposed_unit = request.proposed_value, request.proposed_unit
    if request.proposal_source == "guarded_finding":
        proposal = _finding_proposal(finding, request.dimension)
        if proposal is None or proposal != (proposed_value, proposed_unit):
            raise ValueError("Guarded value must match the replayed finding proposal")
        proposed_value, proposed_unit = proposal
    provenance = next((item for item in report.pack_provenance if item.id == finding.rule_id), None)
    if provenance is None or provenance.version != finding.rule_version:
        raise ValueError("Experiment finding does not match original pack provenance")
    if as_of < report.generated_at:
        raise ValueError("Experiment handoff evaluation cannot precede the original report")
    if report.configuration_digest is None:
        raise ValueError("Experiment handoff requires original configuration provenance")
    cluster = assessment.snapshot.clusters[0]
    if cluster.uid is None:
        raise ValueError("Experiment handoff requires an exact cluster fingerprint")
    run = _summary(archive, assessment, configuration)
    return ExperimentHandoff(
        tenant_id=tenant_id,
        cluster_resource_id=cluster.resource_id,
        cluster_uid=cluster.uid,
        run_id=run.run_id,
        finding_id=finding.id,
        pack_id=finding.rule_id,
        pack_version=finding.rule_version,
        generated_at=as_of,
        baseline_window_start=report.observation_window.start,
        baseline_window_end=report.observation_window.end,
        baseline_configuration_digest=report.configuration_digest,
        dimension=request.dimension,
        controller=request.controller,
        owner_ref=request.owner_ref,
        reviewer_ref=request.reviewer_ref,
        hypothesis=request.hypothesis,
        unchanged_dimensions=request.unchanged_dimensions,
        representative_scenarios=request.representative_scenarios,
        criteria=request.criteria,
        observation_duration_seconds=request.observation_duration_seconds,
        checks=request.checks,
        rollback_reference=request.rollback_reference,
        rollback_value_reference=request.rollback_value_reference,
        unresolved_prerequisites=request.unresolved_prerequisites,
        alternatives=request.alternatives,
        proposal_source=request.proposal_source,
        proposed_value=proposed_value,
        proposed_unit=proposed_unit,
        ai_experiment_digest=request.ai_experiment_digest,
        ai_state=request.ai_state,
        state="blocked" if request.unresolved_prerequisites else "prepared",
    )


def read_experiment_handoff_bundle(
    directory: Path,
) -> tuple[ExperimentBundleManifest, ExperimentHandoff]:
    manifest = ExperimentBundleManifest.model_validate_json(
        _read_text(directory / "manifest.json", 4096)
    )
    payloads = {
        name: _read_text(directory / name, 32 * 1024 * 1024)
        for name in ("experiment.json", "experiment.md")
    }
    if any(
        sha256(payloads[name].encode()).hexdigest() != manifest.files[name] for name in payloads
    ):
        raise ValueError("Experiment bundle integrity check failed")
    handoff = ExperimentHandoff.model_validate_json(payloads["experiment.json"])
    if handoff.state != manifest.status:
        raise ValueError("Experiment bundle status does not match its handoff")
    return manifest, handoff


def record_experiment_outcome(
    directory: Path,
    *,
    request: ExperimentOutcomeRequest,
    recorded_at: UtcDatetime,
) -> ExperimentExecutionOutcome:
    request = ExperimentOutcomeRequest.model_validate(request.model_dump())
    manifest, handoff = read_experiment_handoff_bundle(directory)
    if recorded_at < handoff.generated_at:
        raise ValueError("Experiment outcome cannot precede its handoff")
    if handoff.state == "blocked" and request.outcome == "completed":
        raise ValueError("A blocked handoff cannot be recorded as completed")
    return ExperimentExecutionOutcome(
        experiment_digest=manifest.experiment_digest,
        tenant_id=handoff.tenant_id,
        cluster_resource_id=handoff.cluster_resource_id,
        cluster_uid=handoff.cluster_uid,
        finding_id=handoff.finding_id,
        dimension=handoff.dimension,
        recorded_at=recorded_at,
        outcome=request.outcome,
        execution_reference=request.execution_reference,
        evidence_references=request.evidence_references,
        before_assessment_digest=request.before_assessment_digest,
        after_assessment_digest=request.after_assessment_digest,
    )


def read_experiment_outcome_bundle(
    directory: Path,
) -> tuple[ExperimentOutcomeBundleManifest, ExperimentExecutionOutcome]:
    manifest = ExperimentOutcomeBundleManifest.model_validate_json(
        _read_text(directory / "manifest.json", 4096)
    )
    payloads = {
        name: _read_text(directory / name, 32 * 1024 * 1024)
        for name in ("outcome.json", "outcome.md")
    }
    if any(
        sha256(payloads[name].encode()).hexdigest() != manifest.files[name] for name in payloads
    ):
        raise ValueError("Experiment outcome bundle integrity check failed")
    outcome = ExperimentExecutionOutcome.model_validate_json(payloads["outcome.json"])
    if (
        outcome.outcome != manifest.status
        or outcome.experiment_digest != manifest.experiment_digest
    ):
        raise ValueError("Experiment outcome bundle does not match its manifest")
    return manifest, outcome


def _markdown(value: str) -> str:
    escaped = html.escape(value, quote=False)
    return re.sub(r"([\\`*_\[\]{}()#!|>])", r"\\\1", escaped).replace("\n", " ")


def render_experiment_handoff_markdown(handoff: ExperimentHandoff) -> str:
    lines = [
        "# Experiment Handoff",
        "",
        f"State: **{handoff.state}**. Execution authority: **none**.",
        "",
        f"Finding: `{_markdown(handoff.finding_id)}`; pack: `{handoff.pack_id}` "
        f"v{handoff.pack_version}.",
        "",
        f"Cluster: `{_markdown(handoff.cluster_resource_id)}`.",
        "",
        f"Baseline: {handoff.baseline_window_start.isoformat()} to "
        f"{handoff.baseline_window_end.isoformat()}.",
        "",
        f"Dimension: **{handoff.dimension}**; controller: **{handoff.controller}**.",
        "",
        "## Hypothesis",
        "",
        _markdown(handoff.hypothesis),
        "",
        "## Owner Criteria",
        "",
    ]
    lines.extend(
        f"- `{_markdown(item.measure_ref)}` {item.operator} {item.threshold:g} "
        f"{_markdown(item.unit)}"
        for item in handoff.criteria
    )
    lines.extend(["", "## Staged Checks", ""])
    lines.extend(f"- **{item.kind}**: {_markdown(item.description)}" for item in handoff.checks)
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            f"- Runbook reference: `{_markdown(handoff.rollback_reference)}`",
            f"- Original-value reference: `{_markdown(handoff.rollback_value_reference)}`",
            "",
            "## Boundaries",
            "",
            f"- {handoff.notice}",
            "- Retaining the current configuration remains an explicit alternative.",
        ]
    )
    if handoff.ai_state is not None:
        lines.append(
            "- Optional AI attachment is unverified interpretation and has no execution authority."
        )
    return "\n".join(lines) + "\n"


def render_experiment_outcome_markdown(outcome: ExperimentExecutionOutcome) -> str:
    lines = [
        "# Experiment Execution Outcome",
        "",
        f"Declared outcome: **{outcome.outcome}**. Execution authority: **none**.",
        "",
        f"Experiment digest: `{outcome.experiment_digest}`.",
        "",
        f"Finding: `{_markdown(outcome.finding_id)}`; dimension: **{outcome.dimension}**.",
        "",
        f"Recorded: {outcome.recorded_at.isoformat()}.",
        "",
        f"Execution reference: `{_markdown(outcome.execution_reference)}`.",
        "",
        "## Evidence References",
        "",
    ]
    lines.extend(f"- `{_markdown(reference)}`" for reference in outcome.evidence_references)
    if not outcome.evidence_references:
        lines.append("- None supplied.")
    lines.extend(
        [
            "",
            "## Assessment Bindings",
            "",
            f"- Before: `{outcome.before_assessment_digest or 'not supplied'}`",
            f"- After: `{outcome.after_assessment_digest or 'not supplied'}`",
            "",
            "## Boundaries",
            "",
            f"- {outcome.notice}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_experiment_handoff_bundle(directory: Path, handoff: ExperimentHandoff) -> None:
    handoff = ExperimentHandoff.model_validate(handoff.model_dump())
    directory.mkdir(exist_ok=False)
    content = {
        "experiment.json": handoff.model_dump_json(indent=2),
        "experiment.md": render_experiment_handoff_markdown(handoff),
    }
    digests = {}
    for name, text in content.items():
        encoded = text.rstrip("\n") + "\n"
        if len(encoded.encode("utf-8")) > 32 * 1024 * 1024:
            raise ValueError("Experiment handoff output exceeds its byte budget")
        write_exclusive(directory / name, encoded)
        digests[name] = sha256(encoded.encode()).hexdigest()
    write_exclusive(
        directory / "manifest.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "status": handoff.state,
                "experiment_digest": digests["experiment.json"],
                "files": digests,
            },
            indent=2,
            sort_keys=True,
        ),
    )


def _write_outcome_payloads(
    directory: Path, kind: Literal["outcome", "value"], json_text: str, markdown: str
) -> dict[str, str]:
    encoded_content = {
        f"{kind}.json": json_text.rstrip("\n") + "\n",
        f"{kind}.md": markdown.rstrip("\n") + "\n",
    }
    if any(len(text.encode("utf-8")) > 32 * 1024 * 1024 for text in encoded_content.values()):
        raise ValueError(f"Experiment {kind} output exceeds its byte budget")
    directory.mkdir(exist_ok=False)
    digests = {}
    for name, text in encoded_content.items():
        write_exclusive(directory / name, text)
        digests[name] = sha256(text.encode()).hexdigest()
    return digests


def write_experiment_outcome_bundle(directory: Path, outcome: ExperimentExecutionOutcome) -> None:
    outcome = ExperimentExecutionOutcome.model_validate(outcome.model_dump())
    digests = _write_outcome_payloads(
        directory,
        "outcome",
        outcome.model_dump_json(indent=2),
        render_experiment_outcome_markdown(outcome),
    )
    write_exclusive(
        directory / "manifest.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "status": outcome.outcome,
                "experiment_digest": outcome.experiment_digest,
                "files": digests,
            },
            indent=2,
            sort_keys=True,
        ),
    )
