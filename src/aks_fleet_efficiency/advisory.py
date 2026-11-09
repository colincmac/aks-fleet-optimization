from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from aks_fleet_efficiency.models import UtcDatetime

Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4096, pattern=r"\S")]
Reference = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
]
TenantId = Annotated[
    str, Field(strict=True, pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
]
MAXIMUM_PROPOSAL_BYTES = 64 * 1024


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
