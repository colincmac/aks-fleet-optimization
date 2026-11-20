from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aks_fleet_efficiency.models import Confidence, Severity, UtcDatetime

Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4096, pattern=r"\S")]
Reference = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
]
TenantId = Annotated[
    str, Field(strict=True, pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
]
MAXIMUM_PROPOSAL_BYTES = 64 * 1024
MAXIMUM_AI_PACKAGE_BYTES = 256 * 1024


class _AdvisoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def content_digest(model: BaseModel) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _distinct(values: tuple[str, ...], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be distinct")


def _interval(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValueError("expiry must follow observation or generation")


def _utc(as_of: datetime) -> datetime:
    if as_of.utcoffset() is None:
        raise ValueError("evaluation time must be timezone aware")
    return as_of.astimezone(UTC)


class AdvisoryTarget(_AdvisoryModel):
    tenant_id: TenantId
    cluster_resource_id: Annotated[
        str,
        Field(
            strict=True,
            max_length=2048,
            pattern=r"^/subscriptions/[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"
            r"/resourceGroups/[^/\s]+/providers/Microsoft.ContainerService/managedClusters/[^/\s]+$",
        ),
    ]
    cluster_fingerprint: Reference
    namespace: Annotated[
        str,
        Field(strict=True, min_length=1, max_length=63, pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"),
    ]
    namespace_uid: Reference
    workload_api_version: Literal["apps/v1"]
    workload_kind: Literal["Deployment", "StatefulSet"]
    workload_uid: Reference


Targets = Annotated[tuple[AdvisoryTarget, ...], Field(min_length=1, max_length=16)]


def _targets(targets: tuple[AdvisoryTarget, ...]) -> None:
    _distinct(tuple(content_digest(target) for target in targets), "target identities")
    if len({target.tenant_id for target in targets}) != 1:
        raise ValueError("one bundle cannot cross tenant scope")
    clusters: dict[str, str] = {}
    namespaces: dict[tuple[str, str], str] = {}
    for target in targets:
        if clusters.setdefault(target.cluster_resource_id, target.cluster_fingerprint) != (
            target.cluster_fingerprint
        ):
            raise ValueError("cluster incarnations must not conflict")
        key = (target.cluster_resource_id, target.namespace)
        if namespaces.setdefault(key, target.namespace_uid) != target.namespace_uid:
            raise ValueError("Namespace incarnations must not conflict")


class HpaSignalFact(_AdvisoryModel):
    kind: Literal["hpa_signal"]
    controller_uid: Reference
    signal: Literal["utilization", "absolute", "external", "pods", "object"]
    resource: Literal["cpu", "memory"] | None = None


class VpaModeFact(_AdvisoryModel):
    kind: Literal["vpa_mode"]
    controller_uid: Reference
    mode: Literal["Off", "Initial", "Recreate", "Auto", "InPlaceOrRecreate"]


class AdmittedRequestFact(_AdvisoryModel):
    kind: Literal["admitted_request"]
    container: Reference
    resource: Literal["cpu", "memory"]
    value: Annotated[float, Field(strict=True, ge=0)]
    unit: Literal["mCPU", "MiB"]

    @model_validator(mode="after")
    def validate_unit(self) -> Self:
        if self.unit != {"cpu": "mCPU", "memory": "MiB"}[self.resource]:
            raise ValueError("resource and unit must match")
        return self


class OwnerContext(_AdvisoryModel):
    kind: Literal["owner_context"]
    category: Literal["objective", "slo", "demand", "portability", "performance_summary"]
    owner_ref: Reference
    summary: Text


class UnknownEvidence(_AdvisoryModel):
    kind: Literal["unknown"]
    reason_code: Literal["missing", "denied", "unsupported", "stale", "not_observed"]


class AdvisoryEvidenceRecord(_AdvisoryModel):
    record_id: Reference
    revision: Digest
    target: AdvisoryTarget
    source_ref: Reference
    observed_at: UtcDatetime | None
    expires_at: UtcDatetime | None
    quality: Literal["complete", "partial", "unknown"]
    payload: Annotated[
        HpaSignalFact | VpaModeFact | AdmittedRequestFact | OwnerContext | UnknownEvidence,
        Field(discriminator="kind"),
    ]

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.quality == "unknown":
            if (
                self.payload.kind != "unknown"
                or self.observed_at is not None
                or (self.expires_at is not None)
            ):
                raise ValueError(
                    "unknown evidence requires an explicit gap without invented clocks"
                )
        else:
            if (
                self.payload.kind == "unknown"
                or self.observed_at is None
                or self.expires_at is None
            ):
                raise ValueError("known evidence requires observation and expiry")
            _interval(self.observed_at, self.expires_at)
        return self


class ArtifactReference(_AdvisoryModel):
    name: Literal[
        "fragments.json", "snapshot.json", "analysis-config.json", "assessment.json", "report.md"
    ]
    digest: Digest


class FindingReference(_AdvisoryModel):
    finding_id: Reference
    artifact_digest: Digest


class AIInvestigationBundle(_AdvisoryModel):
    schema_version: Literal["1.0"]
    bundle_id: Reference
    run_id: Digest
    targets: Targets
    generated_at: UtcDatetime
    expires_at: UtcDatetime
    maximum_evidence_age_seconds: Annotated[int, Field(strict=True, ge=1, le=2592000)]
    artifacts: tuple[ArtifactReference, ...] = Field(min_length=1, max_length=5)
    finding_refs: tuple[FindingReference, ...] = Field(default=(), max_length=128)
    question: Text
    owner_objective_id: Reference
    records: tuple[AdvisoryEvidenceRecord, ...] = Field(min_length=1, max_length=128)

    @property
    def owner_context_digest(self) -> str:
        return content_digest(
            next(record for record in self.records if record.record_id == self.owner_objective_id)
        )

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        _interval(self.generated_at, self.expires_at)
        _targets(self.targets)
        _distinct(tuple(artifact.name for artifact in self.artifacts), "artifact names")
        _distinct(tuple(record.record_id for record in self.records), "record IDs")
        _distinct(tuple(finding.finding_id for finding in self.finding_refs), "finding IDs")
        artifact_digests = {artifact.digest for artifact in self.artifacts}
        if any(finding.artifact_digest not in artifact_digests for finding in self.finding_refs):
            raise ValueError("finding references must bind an original artifact")
        objective = next(
            (record for record in self.records if record.record_id == self.owner_objective_id), None
        )
        if (
            objective is None
            or objective.payload.kind != "owner_context"
            or (objective.payload.category != "objective" or objective.quality != "complete")
        ):
            raise ValueError("a complete, exact owner objective is required")
        for record in self.records:
            if record.target not in self.targets:
                raise ValueError("record target must match exact approved scope")
            if record.observed_at is not None and record.expires_at is not None:
                age = (self.generated_at - record.observed_at).total_seconds()
                if age < 0 or age > self.maximum_evidence_age_seconds:
                    raise ValueError("record observation is future or stale")
                if record.expires_at <= self.generated_at:
                    raise ValueError("record is expired")
        return self


class EvidenceCitation(_AdvisoryModel):
    record_id: Reference
    record_digest: Digest


Citations = Annotated[tuple[EvidenceCitation, ...], Field(min_length=1, max_length=128)]


class AdvisoryAlternative(_AdvisoryModel):
    kind: Literal["no_change", "alternative"]
    description: Text
    citations: Citations


class AdvisoryProvenance(_AdvisoryModel):
    provider: Reference
    model: Reference
    prompt_revision: Digest
    skill_revision: Digest
    tool_revision: Digest


class AdvisoryExperiment(_AdvisoryModel):
    owner_ref: Reference
    plan: Text
    disconfirming_checks: tuple[Text, ...] = Field(min_length=1, max_length=32)
    stop_conditions: tuple[Text, ...] = Field(min_length=1, max_length=32)
    rollback: Text


class _ModelProposal(_AdvisoryModel):
    schema_version: Literal["1.0"]
    advisory_id: Reference
    bundle_digest: Digest
    run_id: Digest
    targets: Targets
    owner_context_digest: Digest
    generated_at: UtcDatetime
    expires_at: UtcDatetime
    provenance: AdvisoryProvenance
    hypothesis: Text
    alternatives: tuple[AdvisoryAlternative, ...] = Field(min_length=1, max_length=16)
    citations: Citations
    assumptions: tuple[Text, ...] = Field(min_length=1, max_length=32)
    counterevidence: tuple[Text, ...] = Field(min_length=1, max_length=32)
    gaps: tuple[Text, ...] = Field(max_length=32)
    required_checks: tuple[Reference, ...] = Field(max_length=32)
    experiment: AdvisoryExperiment

    @model_validator(mode="after")
    def validate_proposal(self) -> Self:
        _interval(self.generated_at, self.expires_at)
        _targets(self.targets)
        _distinct(self.required_checks, "required check IDs")
        if not any(alternative.kind == "no_change" for alternative in self.alternatives):
            raise ValueError("alternatives must include no change")
        return self


class AIOptimizationAdvisory(_ModelProposal):
    state: Literal["hypothesis", "blocked"]


def _fresh_bundle(bundle: AIInvestigationBundle, as_of: datetime) -> AIInvestigationBundle:
    validated = AIInvestigationBundle.model_validate(bundle.model_dump())
    if not validated.generated_at <= as_of < validated.expires_at:
        raise ValueError("bundle is future or expired")
    for record in validated.records:
        if record.observed_at is not None and record.expires_at is not None:
            age = (as_of - record.observed_at).total_seconds()
            if (
                age < 0
                or age > validated.maximum_evidence_age_seconds
                or as_of >= record.expires_at
            ):
                raise ValueError("required evidence is future, stale or expired")
    return validated


def admit_advisory(
    payload: str, *, bundle: AIInvestigationBundle, as_of: datetime
) -> AIOptimizationAdvisory:
    as_of = _utc(as_of)
    bundle = _fresh_bundle(bundle, as_of)
    if len(payload.encode("utf-8")) > MAXIMUM_PROPOSAL_BYTES:
        raise ValueError("model proposal exceeds the byte limit")
    proposal = _ModelProposal.model_validate_json(payload)
    if (
        proposal.bundle_digest != content_digest(bundle)
        or proposal.run_id != bundle.run_id
        or proposal.targets != bundle.targets
        or proposal.owner_context_digest != bundle.owner_context_digest
    ):
        raise ValueError("proposal must bind the exact bundle, run, targets and owner revision")
    if not bundle.generated_at <= proposal.generated_at <= as_of < proposal.expires_at:
        raise ValueError("proposal is future or expired")
    if proposal.expires_at > bundle.expires_at:
        raise ValueError("proposal cannot outlive the bundle")
    records = {record.record_id: record for record in bundle.records}
    if bundle.owner_objective_id not in {citation.record_id for citation in proposal.citations}:
        raise ValueError("proposal must cite the owner objective")
    for citations in (proposal.citations, *(option.citations for option in proposal.alternatives)):
        _distinct(tuple(citation.record_id for citation in citations), "citation IDs")
        for citation in citations:
            record = records.get(citation.record_id)
            if record is None or citation.record_digest != content_digest(record):
                raise ValueError("citation is missing, foreign or substituted")
            if record.expires_at is not None and proposal.expires_at > record.expires_at:
                raise ValueError("proposal cannot outlive cited evidence")
    blocked = (
        bool(proposal.gaps)
        or not proposal.required_checks
        or any(record.quality != "complete" for record in bundle.records)
    )
    return AIOptimizationAdvisory.model_validate(
        proposal.model_dump() | {"state": "blocked" if blocked else "hypothesis"}
    )


class AdvisoryCheckResult(_AdvisoryModel):
    schema_version: Literal["1.0"]
    check_id: Reference
    checker: Reference
    checker_version: Reference
    scenario_id: Reference
    candidate_digest: Digest
    input_digest: Digest
    owner_context_digest: Digest
    catalog_digest: Digest | None
    targets: Targets
    observed_at: UtcDatetime
    expires_at: UtcDatetime
    supported_constraints: tuple[Reference, ...] = Field(min_length=1, max_length=128)
    outcome: Literal["pass", "fail", "unknown"]
    reason_codes: tuple[Reference, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        _interval(self.observed_at, self.expires_at)
        _targets(self.targets)
        _distinct(self.supported_constraints, "supported constraints")
        _distinct(self.reason_codes, "reason codes")
        return self


def validate_check_result(
    result: AdvisoryCheckResult,
    *,
    bundle: AIInvestigationBundle,
    proposal: AIOptimizationAdvisory,
    scenario_id: str,
    catalog_digest: str | None,
    as_of: datetime,
) -> AdvisoryCheckResult:
    as_of = _utc(as_of)
    bundle = _fresh_bundle(bundle, as_of)
    proposal_payload = proposal.model_dump(mode="json", exclude={"state"})
    validated_proposal = admit_advisory(json.dumps(proposal_payload), bundle=bundle, as_of=as_of)
    if validated_proposal != proposal:
        raise ValueError("advisory state must match deterministic admission")
    result = AdvisoryCheckResult.model_validate(result.model_dump())
    if (
        result.candidate_digest != content_digest(proposal)
        or result.input_digest != content_digest(bundle)
        or result.owner_context_digest != bundle.owner_context_digest
        or result.targets != bundle.targets
        or result.catalog_digest != catalog_digest
        or result.scenario_id != scenario_id
        or result.check_id not in proposal.required_checks
    ):
        raise ValueError(
            "check result must bind the exact scenario, candidate, inputs and revisions"
        )
    if not bundle.generated_at <= result.observed_at <= as_of < result.expires_at:
        raise ValueError("check result is future or expired")
    if result.expires_at > min(bundle.expires_at, proposal.expires_at) or (
        (as_of - result.observed_at).total_seconds() > bundle.maximum_evidence_age_seconds
    ):
        raise ValueError("check result is stale or outlives its inputs")
    return result


class AIAssessmentReference(_AdvisoryModel):
    run_id: Digest
    scope_id: Digest
    snapshot_digest: Digest
    configuration_digest: Digest
    evaluated_at: UtcDatetime
    valid_until: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    status: Literal["complete", "partial"]
    mode: Literal["baseline", "guarded"]

    @model_validator(mode="after")
    def validate_clocks(self) -> Self:
        _interval(self.evaluated_at, self.valid_until)
        _interval(self.window_start, self.window_end)
        return self


class AIFindingSummary(_AdvisoryModel):
    record_id: Digest
    run_id: Digest
    scope_id: Digest
    resource_digest: Digest
    rule_id: Annotated[str, Field(strict=True, pattern=r"^AKS-[A-Z]+-[0-9]{3}$")]
    rule_version: Annotated[str, Field(strict=True, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    state: Literal["finding", "blocked"]
    severity: Severity | None
    confidence: Confidence | None
    reason_digests: tuple[Digest, ...] = Field(max_length=128)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        _distinct(self.reason_digests, "reason digests")
        if self.state == "blocked":
            if self.severity is not None or self.confidence is not None or not self.reason_digests:
                raise ValueError("blocked summaries retain reasons without invented severity")
        elif self.severity is None or self.confidence is None or self.reason_digests:
            raise ValueError(
                "finding summaries require their deterministic severity and confidence"
            )
        return self


class AIEvidencePackage(_AdvisoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_digest: Digest
    generated_at: UtcDatetime
    expires_at: UtcDatetime
    ttl_seconds: Annotated[int, Field(strict=True, ge=60, le=3600)]
    assessments: tuple[AIAssessmentReference, ...] = Field(min_length=1, max_length=16)
    records: tuple[AIFindingSummary, ...] = Field(max_length=128)
    notice: Literal[
        "Pseudonymous finding summaries, not anonymous data or source attestation. "
        "Raw evidence and blocker text withheld. No AI invocation, approval or action authority."
    ] = (
        "Pseudonymous finding summaries, not anonymous data or source attestation. "
        "Raw evidence and blocker text withheld. No AI invocation, approval or action authority."
    )

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        _interval(self.generated_at, self.expires_at)
        if (self.expires_at - self.generated_at).total_seconds() > self.ttl_seconds:
            raise ValueError("package cannot exceed its requested lifetime")
        _distinct(tuple(item.run_id for item in self.assessments), "assessment runs")
        _distinct(tuple(item.record_id for item in self.records), "summary records")
        bindings = {(item.run_id, item.scope_id) for item in self.assessments}
        if any((item.run_id, item.scope_id) not in bindings for item in self.records):
            raise ValueError("summary records must bind an admitted assessment scope")
        for assessment in self.assessments:
            if (
                not assessment.evaluated_at
                <= self.generated_at
                < self.expires_at
                <= assessment.valid_until
            ):
                raise ValueError("package assessment is future, stale or expired")
        return self


MeasurementDimension = Literal["cpu_request", "cpu_usage_p95", "memory_request", "memory_usage_p99"]
MeasurementReason = Literal[
    "executed_provenance_unavailable",
    "identity_unavailable",
    "metric_unavailable",
    "quality_unqualified",
    "query_definition_unavailable",
    "ambiguous_original_metric",
]


class AIResourceQuality(_AdvisoryModel):
    qualified_at: UtcDatetime
    observed_at: UtcDatetime
    source_observed_at: UtcDatetime
    latest_sample_at: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    step_seconds: Annotated[int, Field(strict=True, gt=0, le=300)]
    sample_count: Annotated[int, Field(strict=True, gt=0)]
    coverage_ratio: Annotated[float, Field(strict=True, ge=0, le=1)]
    source_digest: Digest
    source_profile_digest: Digest
    receipt_digest: Digest
    observation_digest: Digest
    query_expression_digest: Digest
    query_asset_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    adapter_version: Literal["1.0"]

    @model_validator(mode="after")
    def validate_quality_clocks(self) -> Self:
        _interval(self.window_start, self.window_end)
        if not self.window_start <= self.latest_sample_at <= self.window_end <= self.observed_at:
            raise ValueError("Measurement quality requires ordered original window/sample clocks")
        if self.source_observed_at < self.window_end:
            raise ValueError("Measurement source clock must not precede its completed window")
        return self


class AIResourceMeasurement(_AdvisoryModel):
    record_id: Digest
    run_id: Digest
    scope_id: Digest
    subject_digest: Digest
    dimension: MeasurementDimension
    unit: Literal["mCPU", "MiB"]
    status: Literal["observed", "withheld"]
    value: Annotated[float, Field(strict=True, ge=0)] | None
    reason_codes: tuple[MeasurementReason, ...]
    quality: AIResourceQuality | None = None

    @model_validator(mode="after")
    def validate_measurement(self) -> Self:
        expected = "mCPU" if self.dimension.startswith("cpu_") else "MiB"
        if self.unit != expected or len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Measurement requires exact units and distinct closed reasons")
        if (self.status == "withheld") != (self.value is None) or (
            (self.status == "withheld") != bool(self.reason_codes)
        ):
            raise ValueError("Measurement state must preserve withheld values and observed facts")
        if (self.status == "observed") != (self.quality is not None):
            raise ValueError(
                "Observed measurements require original quality; withheld values do not"
            )
        return self


class AIResourceEvidencePackage(_AdvisoryModel):
    schema_version: Literal["1.0"] = "1.0"
    summary: AIEvidencePackage
    measurements: tuple[AIResourceMeasurement, ...] = Field(max_length=512)
    notice: Literal[
        "Separately opted-in pseudonymous measurements; not anonymous data, source attestation, "
        "safe values or action authority. No model invocation."
    ] = (
        "Separately opted-in pseudonymous measurements; not anonymous data, source attestation, "
        "safe values or action authority. No model invocation."
    )

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        bindings = {(item.run_id, item.scope_id) for item in self.summary.assessments}
        _distinct(tuple(item.record_id for item in self.measurements), "measurement records")
        if any((item.run_id, item.scope_id) not in bindings for item in self.measurements):
            raise ValueError("Measurements require exact admitted original assessment scopes")
        keys = {(item.run_id, item.subject_digest, item.dimension) for item in self.measurements}
        if len(keys) != len(self.measurements):
            raise ValueError("Measurement dimensions must be distinct within each subject")
        references = {item.run_id: item for item in self.summary.assessments}
        for item in self.measurements:
            if item.quality is None:
                continue
            reference = references[item.run_id]
            quality = item.quality
            if (
                quality.qualified_at != reference.evaluated_at
                or quality.window_start != reference.window_start
                or quality.window_end != reference.window_end
                or quality.observed_at > reference.evaluated_at
                or quality.source_observed_at > reference.evaluated_at
            ):
                raise ValueError(
                    "Measurement quality must bind its original assessment window/clock"
                )
        return self


class AIExplanationClaim(_AdvisoryModel):
    fact: AIFindingSummary
    citation: EvidenceCitation
    interpretation: Text


class AIExplanationDraft(_AdvisoryModel):
    schema_version: Literal["1.0"] = "1.0"
    package_digest: Digest
    generated_at: UtcDatetime
    expires_at: UtcDatetime
    provenance: AdvisoryProvenance
    claims: tuple[AIExplanationClaim, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_draft(self) -> Self:
        _interval(self.generated_at, self.expires_at)
        _distinct(tuple(claim.citation.record_id for claim in self.claims), "claim citations")
        return self


class AIExplanation(AIExplanationDraft):
    state: Literal["unverified_interpretation"] = "unverified_interpretation"


def admit_ai_explanation(
    payload: str, *, package: AIEvidencePackage, as_of: datetime
) -> AIExplanation:
    evaluated_at = _utc(as_of)
    package = AIEvidencePackage.model_validate(package.model_dump())
    if len(package.model_dump_json().encode()) > MAXIMUM_AI_PACKAGE_BYTES:
        raise ValueError("AI package exceeds the byte limit")
    if not package.generated_at <= evaluated_at < package.expires_at:
        raise ValueError("AI package is future or expired")
    if len(payload.encode()) > MAXIMUM_PROPOSAL_BYTES:
        raise ValueError("AI explanation exceeds the byte limit")
    draft = AIExplanationDraft.model_validate_json(payload)
    if draft.package_digest != content_digest(package):
        raise ValueError("explanation must bind the exact package")
    if (
        not package.generated_at
        <= draft.generated_at
        <= evaluated_at
        < draft.expires_at
        <= package.expires_at
    ):
        raise ValueError("explanation is future, expired or outlives its package")
    records = {record.record_id: record for record in package.records}
    for claim in draft.claims:
        record = records.get(claim.citation.record_id)
        if (
            record is None
            or claim.citation.record_digest != content_digest(record)
            or content_digest(claim.fact) != content_digest(record)
        ):
            raise ValueError("explanation citation or copied fact is foreign or substituted")
    return AIExplanation.model_validate(draft.model_dump())


class AIReviewIntent(_AdvisoryModel):
    schema_version: Literal["1.0"] = "1.0"
    package_digest: Digest
    scope_id: Digest
    objective: Literal[
        "investigate-resource-settings",
        "investigate-controller-interactions",
        "review-missing-evidence",
    ]


class AIChecklistStep(_AdvisoryModel):
    kind: Literal[
        "confirm_scope",
        "inspect_source_gaps",
        "review_controller_interactions",
        "define_test_and_abort_criteria",
        "verify_rollback_prerequisites",
        "retain_no_change_option",
    ]
    citation: EvidenceCitation


class AIChecklistDraft(_AdvisoryModel):
    schema_version: Literal["1.0"] = "1.0"
    intent_digest: Digest
    explanation: AIExplanationDraft
    steps: tuple[AIChecklistStep, ...] = Field(min_length=3, max_length=32)

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        _distinct(
            tuple(f"{step.kind}/{step.citation.record_id}" for step in self.steps),
            "checklist steps",
        )
        if not {
            "define_test_and_abort_criteria",
            "verify_rollback_prerequisites",
            "retain_no_change_option",
        }.issubset({step.kind for step in self.steps}):
            raise ValueError("checklists require test/abort, rollback and no-change review steps")
        return self


class AIChecklist(AIChecklistDraft):
    state: Literal["unverified_checklist"] = "unverified_checklist"


def admit_ai_checklist(
    payload: str, *, package: AIEvidencePackage, intent: AIReviewIntent, as_of: datetime
) -> AIChecklist:
    if len(payload.encode()) > MAXIMUM_PROPOSAL_BYTES:
        raise ValueError("AI checklist exceeds the byte limit")
    intent = AIReviewIntent.model_validate(intent.model_dump())
    package = AIEvidencePackage.model_validate(package.model_dump())
    if intent.package_digest != content_digest(package) or intent.scope_id not in {
        item.scope_id for item in package.assessments
    }:
        raise ValueError("review intent must bind the exact package and an admitted scope")
    draft = AIChecklistDraft.model_validate_json(payload)
    if draft.intent_digest != content_digest(intent):
        raise ValueError("checklist must bind the exact caller-supplied review intent")
    explanation = admit_ai_explanation(
        draft.explanation.model_dump_json(), package=package, as_of=as_of
    )
    if any(claim.fact.scope_id != intent.scope_id for claim in explanation.claims):
        raise ValueError("checklist facts must remain within the selected review scope")
    citations = {claim.citation.record_id: claim.citation for claim in explanation.claims}
    if set(citations) != {step.citation.record_id for step in draft.steps} or any(
        citations.get(step.citation.record_id) != step.citation for step in draft.steps
    ):
        raise ValueError("checklist steps must cite the exact selected explanation facts")
    return AIChecklist.model_validate(draft.model_dump())


ExperimentDimension = Literal[
    "cpu_request",
    "memory_request",
    "memory_limit",
    "replica_floor",
    "controller_configuration",
    "evidence_only",
]
ExperimentController = Literal["none", "hpa", "vpa", "keda", "nap", "fixed"]


class AIExperimentIntent(AIReviewIntent):
    dimension: ExperimentDimension
    controller: ExperimentController


class AIExperimentCheck(_AdvisoryModel):
    kind: Literal["baseline", "canary", "observe", "abort", "rollback", "no_change"]
    citation: EvidenceCitation


class AIExperimentDraft(_AdvisoryModel):
    schema_version: Literal["1.0"] = "1.0"
    intent_digest: Digest
    dimension: ExperimentDimension
    controller: ExperimentController
    explanation: AIExplanationDraft
    hypothesis: Text
    alternatives: tuple[
        Literal[
            "retain_current_configuration",
            "collect_missing_evidence",
            "review_single_dimension_canary",
        ],
        ...,
    ] = Field(min_length=1, max_length=3)
    checks: tuple[AIExperimentCheck, ...] = Field(min_length=6, max_length=32)
    unresolved_prerequisites: tuple[
        Literal[
            "owner_review",
            "representative_load",
            "application_readiness",
            "slo_and_abort",
            "rollback_validation",
            "source_completeness",
            "controller_semantics",
        ],
        ...,
    ] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_experiment(self) -> Self:
        _distinct(self.alternatives, "experiment alternatives")
        _distinct(self.unresolved_prerequisites, "experiment prerequisites")
        _distinct(
            tuple(f"{check.kind}/{check.citation.record_id}" for check in self.checks),
            "experiment checks",
        )
        if "retain_current_configuration" not in self.alternatives or {
            check.kind for check in self.checks
        } != {"baseline", "canary", "observe", "abort", "rollback", "no_change"}:
            raise ValueError("experiments require staged checks and a no-change alternative")
        return self


class AIExperiment(AIExperimentDraft):
    state: Literal["unverified_experiment"] = "unverified_experiment"
    execution_authority: Literal["none"] = "none"


def admit_ai_experiment(
    payload: str, *, package: AIEvidencePackage, intent: AIExperimentIntent, as_of: datetime
) -> AIExperiment:
    if len(payload.encode("utf-8")) > MAXIMUM_PROPOSAL_BYTES:
        raise ValueError("AI experiment exceeds the byte limit")
    intent = AIExperimentIntent.model_validate(intent.model_dump())
    package = AIEvidencePackage.model_validate(package.model_dump())
    if intent.package_digest != content_digest(package) or intent.scope_id not in {
        item.scope_id for item in package.assessments
    }:
        raise ValueError("experiment intent must bind the exact package and scope")
    draft = AIExperimentDraft.model_validate_json(payload)
    if (
        draft.intent_digest != content_digest(intent)
        or draft.dimension != intent.dimension
        or draft.controller != intent.controller
    ):
        raise ValueError("experiment must bind the caller's exact dimension and controller intent")
    explanation = admit_ai_explanation(
        draft.explanation.model_dump_json(), package=package, as_of=as_of
    )
    if any(claim.fact.scope_id != intent.scope_id for claim in explanation.claims):
        raise ValueError("experiment facts must remain within the selected scope")
    citations = {claim.citation.record_id: claim.citation for claim in explanation.claims}
    if set(citations) != {check.citation.record_id for check in draft.checks} or any(
        citations.get(check.citation.record_id) != check.citation for check in draft.checks
    ):
        raise ValueError("experiment checks must cite the exact selected explanation facts")
    return AIExperiment.model_validate(draft.model_dump())
