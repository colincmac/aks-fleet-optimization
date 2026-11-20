from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment
from aks_fleet_efficiency.catalog.models import PackId, Version
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.fleet import FleetResourceEnvelope, PeerGroup, _resource_envelope
from aks_fleet_efficiency.models import (
    AnalysisReport,
    BlockedRecommendation,
    Recommendation,
    UtcDatetime,
)
from aks_fleet_efficiency.rules.engine import analyze

MAXIMUM_RUNS = 1000
MAXIMUM_ARTIFACT_BYTES = 32 * 1024 * 1024
MAXIMUM_STORE_BYTES = 128 * 1024 * 1024
MAXIMUM_RECORD_BYTES = 2 * MAXIMUM_ARTIFACT_BYTES
MAXIMUM_TREND_ASSESSMENTS = 100
MAXIMUM_TREND_BYTES = 128 * 1024 * 1024
MAXIMUM_DRIFT_BYTES = 4 * 1024 * 1024
ARTIFACT_NAMES = frozenset(
    {"fragments.json", "snapshot.json", "analysis-config.json", "assessment.json", "report.md"}
)
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
TrendState = Literal["new", "persistent", "changed", "blocked", "not_observed", "not_comparable"]


class _HistoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _StoreIdentity(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID


class _ArtifactManifest(_HistoryModel):
    schema_version: Literal["1.0"]
    status: Literal["complete", "partial"]
    input_digest: Digest
    files: dict[str, Digest]


class _StoredRun(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    manifest: _ArtifactManifest
    payloads: dict[str, str]


class HistoryRun(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: Digest
    tenant_id: UUID
    generated_at: UtcDatetime
    window_start: UtcDatetime
    window_end: UtcDatetime
    status: Literal["complete", "partial"]
    snapshot_digest: Digest
    configuration_digest: Digest
    comparison_key: Digest
    recommendations: int = Field(ge=0)
    blocked_recommendations: int = Field(ge=0)
    savings: None = None


class FindingTrend(_HistoryModel):
    finding_id: str
    rule_id: str
    resource_id: str
    state: TrendState
    first_observed_at: UtcDatetime | None = None
    last_observed_at: UtcDatetime | None = None


class HistoryTrend(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    previous_run_id: Digest
    current_run_id: Digest
    comparable: bool
    findings: list[FindingTrend]
    savings: None = None


class FleetFindingRecurrence(_HistoryModel):
    finding_id: str
    rule_id: str
    resource_id: str
    observed_runs: int = Field(ge=2, strict=True)
    first_observed_at: UtcDatetime
    last_observed_at: UtcDatetime


class FleetHistorySeries(_HistoryModel):
    cluster_resource_id: str
    cluster_uid: str
    peer_group: PeerGroup
    runs: list[HistoryRun] = Field(min_length=1, max_length=100)
    comparisons: list[HistoryTrend]
    comparable: bool
    reason_codes: list[Literal["insufficient_samples", "comparison_basis_changed"]]
    recurring_findings: list[FleetFindingRecurrence] | None


class FleetHistoryTrend(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    series: list[FleetHistorySeries] = Field(min_length=1, max_length=100)
    estimated_monthly_savings: None = None


class FleetPackEvidence(_HistoryModel):
    pack_id: PackId
    version: Version
    digest: Digest
    examined_subjects: int = Field(ge=0, strict=True)
    qualified_findings: int = Field(ge=0, strict=True)
    blocked_records: int = Field(ge=0, strict=True)
    high_or_critical_findings: int = Field(ge=0, strict=True)


class FleetCheckEvidence(_HistoryModel):
    packs: list[FleetPackEvidence]
    coverage_reason: Literal["expected_subject_roster_not_retained"] = (
        "expected_subject_roster_not_retained"
    )


class FleetDriftObservation(_HistoryModel):
    run: HistoryRun
    age_seconds: float = Field(ge=0)
    metric_sample_count: int = Field(ge=0)
    metric_coverage_ratio: float = Field(ge=0, le=1)
    high_or_critical: int | None = Field(default=None, ge=0)
    check_evidence: FleetCheckEvidence | None = None
    resources: FleetResourceEnvelope


type DriftReason = Literal[
    "insufficient_samples",
    "comparison_basis_changed",
    "source_basis_changed",
    "controller_identity_changed",
    "workload_policy_changed",
]


class FleetDriftRow(_HistoryModel):
    cluster_resource_id: str
    cluster_uid: str
    peer_group: PeerGroup
    selected_runs: int = Field(ge=1)
    latest: FleetDriftObservation
    latest_comparison: HistoryTrend | None
    prior_comparable_resources: FleetDriftObservation | None
    reason_codes: list[DriftReason]
    recurring_findings: list[FleetFindingRecurrence] | None


class FleetDriftMatrix(_HistoryModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    evaluated_at: UtcDatetime
    rows: list[FleetDriftRow] = Field(min_length=1, max_length=MAXIMUM_TREND_ASSESSMENTS)


@dataclass(frozen=True)
class _TrendSample:
    run: HistoryRun
    assessment: OfflineAssessment
    config: AdvisorConfig
    source_basis: tuple[str, ...] = ()


type _SeriesKey = tuple[str, str, str]


def _canonical(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _digest(model: BaseModel) -> str:
    return sha256(_canonical(model).encode()).hexdigest()


def _safe_path(path: Path) -> None:
    if any(parent.is_symlink() or parent.is_junction() for parent in (path, *path.parents)):
        raise ValueError("history paths must not use links or junctions")


def _read_text(path: Path, maximum: int) -> str:
    _safe_path(path)
    if not path.is_file():
        raise ValueError("history input must be a regular file")
    with path.open("rb") as handle:
        payload = handle.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("history input exceeds the byte limit")
    return payload.decode("utf-8")


def _publish(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".pending-", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text.encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate(archive: _StoredRun) -> tuple[OfflineAssessment, AdvisorConfig]:
    if set(archive.manifest.files) != ARTIFACT_NAMES or set(archive.payloads) != ARTIFACT_NAMES:
        raise ValueError("artifact integrity requires the exact supported file set")
    for name in sorted(ARTIFACT_NAMES):
        if sha256(archive.payloads[name].encode()).hexdigest() != archive.manifest.files[name]:
            raise ValueError("artifact integrity check failed")
    assessment = OfflineAssessment.model_validate_json(archive.payloads["assessment.json"])
    config = AdvisorConfig.model_validate_json(archive.payloads["analysis-config.json"])
    fragments = AssessmentFragments.model_validate_json(archive.payloads["fragments.json"])
    source_tenants = [
        *(item.tenant_id for item in fragments.azure),
        *(item.tenant_id for item in fragments.kubernetes),
        *(item.tenant_id for item in fragments.metrics),
        *(item.tenant_id for item in assessment.metadata_evidence),
    ]
    if any(tenant_id != str(archive.tenant_id) for tenant_id in source_tenants):
        raise ValueError("original fragment tenant binding is invalid")
    snapshot = assessment.snapshot
    report = assessment.report
    manifest = snapshot.collection_manifest
    if (
        manifest is None
        or manifest.tenant_id != str(archive.tenant_id)
        or snapshot.model_dump(mode="json") != json.loads(archive.payloads["snapshot.json"])
        or assessment.status != archive.manifest.status
        or assessment.input_digest != archive.manifest.input_digest
        or assessment.input_digest != _digest(fragments)
        or report.snapshot_digest != _digest(snapshot)
        or report.configuration_digest != _digest(config)
        or report.observation_window != snapshot.metric_window
        or report.mode != config.mode
    ):
        raise ValueError("artifact integrity or tenant binding is invalid")
    findings: list[Recommendation | BlockedRecommendation] = list(report.recommendations)
    findings.extend(report.blocked_recommendations)
    if len({item.id for item in findings}) != len(findings):
        raise ValueError("finding identities must be distinct")
    versions = {item.id: item.version for item in report.pack_provenance}
    if any(versions.get(item.rule_id) != item.rule_version for item in findings):
        raise ValueError("finding versions must match original pack provenance")
    return assessment, config


def _read_archive(
    directory: Path, *, tenant_id: UUID | None = None, maximum_bytes: int | None = None
) -> _StoredRun:
    _safe_path(directory)
    manifest = _ArtifactManifest.model_validate_json(_read_text(directory / "manifest.json", 4096))
    if set(manifest.files) != ARTIFACT_NAMES:
        raise ValueError("artifact integrity requires the exact supported file set")
    payloads: dict[str, str] = {}
    remaining = (
        min(MAXIMUM_ARTIFACT_BYTES, maximum_bytes)
        if maximum_bytes is not None
        else MAXIMUM_ARTIFACT_BYTES
    )
    for name in sorted(ARTIFACT_NAMES):
        payloads[name] = _read_text(directory / name, remaining)
        remaining -= len(payloads[name].encode())
    if tenant_id is None:
        assessment = OfflineAssessment.model_validate_json(payloads["assessment.json"])
        collection = assessment.snapshot.collection_manifest
        if collection is None:
            raise ValueError("assessment artifacts require collection provenance")
        tenant_id = UUID(collection.tenant_id)
    return _StoredRun(tenant_id=tenant_id, manifest=manifest, payloads=payloads)


def read_assessment_artifacts(directory: Path) -> tuple[OfflineAssessment, AdvisorConfig]:
    return _validate(_read_archive(directory))


def _read_verified_archive(
    directory: Path, *, tenant_id: UUID, maximum_bytes: int | None = None
) -> tuple[_StoredRun, OfflineAssessment, AdvisorConfig]:
    archive = _read_archive(directory, tenant_id=tenant_id, maximum_bytes=maximum_bytes)
    assessment, config = _validate(archive)
    if (
        analyze(assessment.snapshot, config, as_of=assessment.report.generated_at)
        != assessment.report
    ):
        raise ValueError("assessment report does not match deterministic replay")
    return archive, assessment, config


def _summary(
    archive: _StoredRun, assessment: OfflineAssessment, config: AdvisorConfig
) -> HistoryRun:
    report = assessment.report
    manifest = assessment.snapshot.collection_manifest
    assert manifest is not None
    assert report.snapshot_digest is not None and report.configuration_digest is not None
    basis = {
        "tenant_id": str(archive.tenant_id),
        "clusters": sorted((item.resource_id, item.uid) for item in assessment.snapshot.clusters),
        "scope": sorted(
            (item.collector, sorted(item.requested_scope)) for item in manifest.source_results
        ),
        "configuration": config.model_dump(mode="json"),
        "packs": sorted(
            (item.model_dump(mode="json") for item in report.pack_provenance),
            key=lambda item: str(item["id"]),
        ),
        "window_seconds": (
            report.observation_window.end - report.observation_window.start
        ).total_seconds(),
    }
    return HistoryRun(
        run_id=_digest(archive),
        tenant_id=archive.tenant_id,
        generated_at=report.generated_at,
        window_start=report.observation_window.start,
        window_end=report.observation_window.end,
        status=assessment.status,
        snapshot_digest=report.snapshot_digest,
        configuration_digest=report.configuration_digest,
        comparison_key=sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest(),
        recommendations=len(report.recommendations),
        blocked_recommendations=len(report.blocked_recommendations),
    )


def _compare_assessments(
    before_run: HistoryRun,
    before: OfflineAssessment,
    after_run: HistoryRun,
    after: OfflineAssessment,
    *,
    basis_matches: bool = True,
) -> HistoryTrend:
    if before_run.tenant_id != after_run.tenant_id:
        raise ValueError("history tenant binding does not match")
    if (
        after_run.generated_at <= before_run.generated_at
        or after_run.window_end < before_run.window_end
    ):
        raise ValueError(
            "history comparison requires strictly ordered evaluation times "
            "and nondecreasing windows"
        )
    comparable = basis_matches and before_run.comparison_key == after_run.comparison_key
    old_findings: dict[str, Recommendation | BlockedRecommendation] = {
        item.id: item for item in before.report.recommendations
    }
    old_findings.update({item.id: item for item in before.report.blocked_recommendations})
    new_findings: dict[str, Recommendation | BlockedRecommendation] = {
        item.id: item for item in after.report.recommendations
    }
    new_findings.update({item.id: item for item in after.report.blocked_recommendations})
    findings = []
    for finding_id in sorted(old_findings.keys() | new_findings.keys()):
        old = old_findings.get(finding_id)
        new = new_findings.get(finding_id)
        item = new if new is not None else old
        assert item is not None
        state: TrendState
        if not comparable:
            state = "not_comparable"
        elif isinstance(new, BlockedRecommendation):
            state = "blocked"
        elif new is None:
            state = "not_observed"
        elif old is None or isinstance(old, BlockedRecommendation):
            state = "new"
        else:
            state = "persistent" if old == new else "changed"
        findings.append(
            FindingTrend(
                finding_id=finding_id,
                rule_id=item.rule_id,
                resource_id=item.resource_id,
                state=state,
                first_observed_at=before_run.generated_at
                if isinstance(old, Recommendation)
                else after_run.generated_at
                if isinstance(new, Recommendation)
                else None,
                last_observed_at=after_run.generated_at
                if isinstance(new, Recommendation)
                else before_run.generated_at
                if isinstance(old, Recommendation)
                else None,
            )
        )
    return HistoryTrend(
        tenant_id=before_run.tenant_id,
        previous_run_id=before_run.run_id,
        current_run_id=after_run.run_id,
        comparable=comparable,
        findings=findings,
    )


def compare_assessment_artifacts(previous: Path, current: Path, *, tenant_id: str) -> HistoryTrend:
    tenant = UUID(tenant_id)
    before_archive, before, before_config = _read_verified_archive(previous, tenant_id=tenant)
    after_archive, after, after_config = _read_verified_archive(current, tenant_id=tenant)
    return _compare_assessments(
        _summary(before_archive, before, before_config),
        before,
        _summary(after_archive, after, after_config),
        after,
    )


def _recurring_findings(
    entries: list[_TrendSample],
) -> list[FleetFindingRecurrence]:
    observations: dict[str, list[tuple[HistoryRun, Recommendation]]] = {}
    for entry in entries:
        for finding in entry.assessment.report.recommendations:
            observations.setdefault(finding.id, []).append((entry.run, finding))
    result = []
    for finding_id, samples in sorted(observations.items()):
        if len(samples) < 2:
            continue
        first, last = samples[0], samples[-1]
        result.append(
            FleetFindingRecurrence(
                finding_id=finding_id,
                rule_id=last[1].rule_id,
                resource_id=last[1].resource_id,
                observed_runs=len(samples),
                first_observed_at=first[0].generated_at,
                last_observed_at=last[0].generated_at,
            )
        )
    return result


def _read_fleet_series(
    artifacts: list[tuple[Path, str]], *, tenant: UUID, include_source_basis: bool = False
) -> dict[_SeriesKey, list[_TrendSample]]:
    if not 2 <= len(artifacts) <= MAXIMUM_TREND_ASSESSMENTS:
        raise ValueError("fleet trends require between two and 100 assessment bundles")
    groups = [TypeAdapter(PeerGroup).validate_python(group) for _, group in artifacts]
    series_entries: dict[_SeriesKey, list[_TrendSample]] = {}
    seen: set[str] = set()
    remaining = MAXIMUM_TREND_BYTES
    for (directory, _), peer_group in zip(artifacts, groups, strict=True):
        archive, assessment, config = _read_verified_archive(
            directory, tenant_id=tenant, maximum_bytes=remaining
        )
        remaining -= sum(len(text.encode()) for text in archive.payloads.values())
        if len(assessment.snapshot.clusters) != 1:
            raise ValueError("fleet trend samples require exactly one cluster")
        run = _summary(archive, assessment, config)
        if run.run_id in seen:
            raise ValueError("fleet trend samples must be distinct")
        seen.add(run.run_id)
        cluster = assessment.snapshot.clusters[0]
        if cluster.uid is None or not cluster.uid.strip():
            raise ValueError("fleet trend samples require an exact cluster fingerprint")
        key = (cluster.resource_id, cluster.uid, peer_group)
        source_basis: tuple[str, ...] = ()
        if include_source_basis:
            originals = AssessmentFragments.model_validate_json(archive.payloads["fragments.json"])
            source_basis = tuple(
                sorted(
                    json.dumps(
                        item.model_dump(
                            mode="json",
                            include={
                                "source_name",
                                "query_version",
                                "step_seconds",
                                "source_profile",
                            },
                        ),
                        sort_keys=True,
                    )
                    for item in originals.metrics
                    if cluster.resource_id in item.collection.requested_scope
                )
            )
        series_entries.setdefault(key, []).append(
            _TrendSample(run, assessment, config, source_basis)
        )
    for entries in series_entries.values():
        entries.sort(key=lambda item: (item.run.generated_at, item.run.window_end, item.run.run_id))
    return series_entries


def summarize_fleet_artifacts(
    artifacts: list[tuple[Path, str]], *, tenant_id: str
) -> FleetHistoryTrend:
    tenant = UUID(tenant_id)
    series = []
    for (resource_id, cluster_uid, peer_group), entries in sorted(
        _read_fleet_series(artifacts, tenant=tenant).items()
    ):
        comparisons = [
            _compare_assessments(before.run, before.assessment, after.run, after.assessment)
            for before, after in pairwise(entries)
        ]
        comparable = len(entries) >= 2 and all(pair.comparable for pair in comparisons)
        reasons: list[Literal["insufficient_samples", "comparison_basis_changed"]] = []
        if len(entries) < 2:
            reasons.append("insufficient_samples")
        elif not comparable:
            reasons.append("comparison_basis_changed")
        series.append(
            FleetHistorySeries(
                cluster_resource_id=resource_id,
                cluster_uid=cluster_uid,
                peer_group=peer_group,
                runs=[entry.run for entry in entries],
                comparisons=comparisons,
                comparable=comparable,
                reason_codes=reasons,
                recurring_findings=_recurring_findings(entries) if comparable else None,
            )
        )
    return FleetHistoryTrend(tenant_id=tenant, series=series)


def _observed_controller_uids(
    entry: _TrendSample,
) -> dict[tuple[str, str, str], tuple[str, ...]]:
    result = {}
    for workload in entry.assessment.snapshot.clusters[0].workloads:
        context = workload.autoscaler_configuration
        if context is None or context.namespace_uid is None or context.workload_uid is None:
            continue
        key = (context.namespace_uid, context.workload_uid)
        if context.hpa_observed:
            result[(*key, "hpa")] = tuple(sorted(item.uid for item in context.hpas))
        if context.vpa_observed:
            result[(*key, "vpa")] = tuple(sorted(item.uid for item in context.vpas))
        if context.keda_observed:
            result[(*key, "keda")] = tuple(sorted(item.uid for item in context.kedas))
    return result


def _check_evidence(report: AnalysisReport) -> FleetCheckEvidence:
    findings = Counter(item.rule_id for item in report.recommendations)
    blocked = Counter(item.rule_id for item in report.blocked_recommendations)
    high_risk = Counter(
        item.rule_id for item in report.recommendations if item.severity in {"high", "critical"}
    )
    return FleetCheckEvidence(
        packs=[
            FleetPackEvidence(
                pack_id=pack.id,
                version=pack.version,
                digest=pack.digest,
                examined_subjects=report.summary.pack_subject_counts[pack.id],
                qualified_findings=findings[pack.id],
                blocked_records=blocked[pack.id],
                high_or_critical_findings=high_risk[pack.id],
            )
            for pack in sorted(report.pack_provenance, key=lambda item: item.id)
        ]
    )


def _drift_observation(entry: _TrendSample, as_of: datetime) -> FleetDriftObservation:
    report = entry.assessment.report
    window = report.observation_window
    return FleetDriftObservation(
        run=entry.run,
        age_seconds=(as_of - entry.run.generated_at).total_seconds(),
        metric_sample_count=window.sample_count,
        metric_coverage_ratio=window.coverage_ratio,
        high_or_critical=report.summary.high_or_critical,
        check_evidence=_check_evidence(report),
        resources=_resource_envelope(
            entry.assessment, entry.assessment.snapshot.clusters[0], entry.config
        ),
    )


def _observed_policy_digests(entry: _TrendSample) -> dict[tuple[str, str], str | None]:
    return {
        (workload.namespace, workload.uid): (
            _digest(workload.safety_policy) if workload.safety_policy is not None else None
        )
        for workload in entry.assessment.snapshot.clusters[0].workloads
        if workload.uid is not None
    }


def project_fleet_drift_matrix(
    artifacts: list[tuple[Path, str]], *, tenant_id: str, as_of: datetime
) -> FleetDriftMatrix:
    """Project replayed run references and evidence without publishing original bundles."""
    if as_of.utcoffset() is None:
        raise ValueError("fleet drift requires a timezone-aware evaluation clock")
    tenant = UUID(tenant_id)
    rows: list[FleetDriftRow] = []
    output_bytes = 0
    series = _read_fleet_series(artifacts, tenant=tenant, include_source_basis=True)
    for (resource_id, cluster_uid, group), entries in sorted(series.items()):
        latest = entries[-1]
        if latest.run.generated_at > as_of:
            raise ValueError("fleet drift requires an evaluation clock no earlier than every run")
        reasons: dict[DriftReason, None] = {}
        previous_sources: tuple[str, ...] = ()
        previous_controllers: dict[tuple[str, str, str], tuple[str, ...]] = {}
        previous_policies: dict[tuple[str, str], str | None] = {}
        comparison = None
        if len(entries) == 1:
            reasons["insufficient_samples"] = None
        for index, entry in enumerate(entries):
            controllers = _observed_controller_uids(entry)
            changed_sources = bool(
                previous_sources and entry.source_basis and previous_sources != entry.source_basis
            )
            changed_controllers = any(
                previous_controllers[key] != controllers[key]
                for key in previous_controllers.keys() & controllers.keys()
            )
            policies = _observed_policy_digests(entry)
            changed_policies = any(
                previous_policies[key] != policies[key]
                for key in previous_policies.keys() & policies.keys()
            )
            if entry.source_basis:
                previous_sources = entry.source_basis
            previous_controllers.update(controllers)
            previous_policies.update(policies)
            if index == 0:
                continue
            earlier = entries[index - 1]
            if earlier.run.comparison_key != entry.run.comparison_key:
                reasons["comparison_basis_changed"] = None
            if changed_sources:
                reasons["source_basis_changed"] = None
            if changed_controllers:
                reasons["controller_identity_changed"] = None
            if changed_policies:
                reasons["workload_policy_changed"] = None
            comparison = _compare_assessments(
                earlier.run,
                earlier.assessment,
                entry.run,
                entry.assessment,
                basis_matches=not (changed_sources or changed_controllers or changed_policies),
            )
        row = FleetDriftRow(
            cluster_resource_id=resource_id,
            cluster_uid=cluster_uid,
            peer_group=group,
            selected_runs=len(entries),
            latest=_drift_observation(latest, as_of),
            latest_comparison=comparison,
            prior_comparable_resources=_drift_observation(entries[-2], as_of)
            if comparison is not None and comparison.comparable
            else None,
            reason_codes=list(reasons),
            recurring_findings=_recurring_findings(entries) if not reasons else None,
        )
        output_bytes += len(row.model_dump_json().encode())
        if output_bytes > MAXIMUM_DRIFT_BYTES:
            raise ValueError("fleet drift matrix exceeds the projection byte budget")
        rows.append(row)
    matrix = FleetDriftMatrix(tenant_id=tenant, evaluated_at=as_of, rows=rows)
    if len(matrix.model_dump_json().encode()) > MAXIMUM_DRIFT_BYTES:
        raise ValueError("fleet drift matrix exceeds the projection byte budget")
    return matrix


class HistoryStore:
    def __init__(self, directory: Path, *, tenant_id: str) -> None:
        self.directory = directory
        self.tenant_id = UUID(tenant_id)

    def _identity(self) -> None:
        _safe_path(self.directory)
        identity = _StoreIdentity.model_validate_json(
            _read_text(self.directory / "store.json", 1024)
        )
        if identity.tenant_id != self.tenant_id:
            raise ValueError("history tenant binding does not match")

    def _paths(self) -> list[Path]:
        _safe_path(self.directory)
        if not self.directory.exists():
            return []
        self._identity()
        paths = []
        total_bytes = 0
        for path in self.directory.iterdir():
            if path.name == "store.json" or path.name.startswith(".pending-"):
                continue
            _safe_path(path)
            if not re.fullmatch(r"[0-9a-f]{64}\.json", path.name) or not path.is_file():
                raise ValueError("unsupported history store entry")
            paths.append(path)
            total_bytes += path.stat().st_size
            if len(paths) > MAXIMUM_RUNS or total_bytes > MAXIMUM_STORE_BYTES:
                raise ValueError("history store exceeds configured limits")
        return sorted(paths)

    def _load(self, path: Path) -> tuple[_StoredRun, OfflineAssessment, AdvisorConfig]:
        archive = _StoredRun.model_validate_json(_read_text(path, MAXIMUM_RECORD_BYTES))
        if archive.tenant_id != self.tenant_id or _digest(archive) != path.stem:
            raise ValueError("history integrity or tenant binding is invalid")
        assessment, config = _validate(archive)
        return archive, assessment, config

    def import_assessment(self, directory: Path) -> HistoryRun:
        archive, assessment, config = _read_verified_archive(directory, tenant_id=self.tenant_id)
        summary = _summary(archive, assessment, config)
        paths = self._paths()
        for path in paths:
            self._load(path)
        destination = self.directory / f"{summary.run_id}.json"
        encoded = _canonical(archive) + "\n"
        if destination in paths:
            return summary
        if (
            len(paths) >= MAXIMUM_RUNS
            or len(encoded.encode()) > MAXIMUM_RECORD_BYTES
            or sum(path.stat().st_size for path in paths) + len(encoded.encode())
            > MAXIMUM_STORE_BYTES
        ):
            raise ValueError("history store exceeds configured limits")
        self.directory.mkdir(exist_ok=True)
        identity = self.directory / "store.json"
        try:
            _publish(identity, _canonical(_StoreIdentity(tenant_id=self.tenant_id)) + "\n")
        except FileExistsError:
            pass
        self._identity()
        try:
            _publish(destination, encoded)
        except FileExistsError:
            existing, _, _ = self._load(destination)
            if existing != archive:
                raise ValueError("history identity conflict") from None
        return summary

    def list_runs(self) -> list[HistoryRun]:
        runs = [_summary(*self._load(path)) for path in self._paths()]
        return sorted(runs, key=lambda item: (item.generated_at, item.window_end, item.run_id))

    def compare(self, previous: str, current: str) -> HistoryTrend:
        if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in (previous, current)):
            raise ValueError("history run IDs must be SHA-256 digests")
        paths = self._paths()
        selected = [self.directory / f"{value}.json" for value in (previous, current)]
        if any(path not in paths for path in selected):
            raise ValueError("history run is unavailable")
        before_archive, before, before_config = self._load(selected[0])
        after_archive, after, after_config = self._load(selected[1])
        return _compare_assessments(
            _summary(before_archive, before, before_config),
            before,
            _summary(after_archive, after, after_config),
            after,
        )
