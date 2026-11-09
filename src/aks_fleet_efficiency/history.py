from __future__ import annotations

import json
import os
import re
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.models import BlockedRecommendation, Recommendation, UtcDatetime
from aks_fleet_efficiency.rules.engine import analyze

MAXIMUM_RUNS = 1000
MAXIMUM_ARTIFACT_BYTES = 32 * 1024 * 1024
MAXIMUM_STORE_BYTES = 128 * 1024 * 1024
MAXIMUM_RECORD_BYTES = 2 * MAXIMUM_ARTIFACT_BYTES
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
        _safe_path(directory)
        manifest = _ArtifactManifest.model_validate_json(
            _read_text(directory / "manifest.json", 4096)
        )
        if set(manifest.files) != ARTIFACT_NAMES:
            raise ValueError("artifact integrity requires the exact supported file set")
        payloads: dict[str, str] = {}
        remaining = MAXIMUM_ARTIFACT_BYTES
        for name in sorted(ARTIFACT_NAMES):
            payloads[name] = _read_text(directory / name, remaining)
            remaining -= len(payloads[name].encode())
        archive = _StoredRun(tenant_id=self.tenant_id, manifest=manifest, payloads=payloads)
        assessment, config = _validate(archive)
        if (
            analyze(assessment.snapshot, config, as_of=assessment.report.generated_at)
            != assessment.report
        ):
            raise ValueError("assessment report does not match deterministic replay")
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
        before_run = _summary(before_archive, before, before_config)
        after_run = _summary(after_archive, after, after_config)
        if (
            after_run.generated_at <= before_run.generated_at
            or after_run.window_end < before_run.window_end
        ):
            raise ValueError(
                "history comparison requires strictly ordered evaluation times "
                "and nondecreasing windows"
            )
        comparable = before_run.comparison_key == after_run.comparison_key
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
            tenant_id=self.tenant_id,
            previous_run_id=previous,
            current_run_id=current,
            comparable=comparable,
            findings=findings,
        )
