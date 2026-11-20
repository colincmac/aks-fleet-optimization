from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from aks_fleet_efficiency.advisory import (
    MAXIMUM_AI_PACKAGE_BYTES,
    AIAssessmentReference,
    AIChecklist,
    AIEvidencePackage,
    AIExperiment,
    AIExperimentIntent,
    AIExplanation,
    AIFindingSummary,
    AIResourceEvidencePackage,
    AIResourceMeasurement,
    AIResourceQuality,
    AIReviewIntent,
    MeasurementDimension,
    _utc,
    admit_ai_checklist,
    admit_ai_experiment,
    admit_ai_explanation,
    content_digest,
)
from aks_fleet_efficiency.assessment import AssessmentFragments
from aks_fleet_efficiency.history import _digest, _read_verified_archive
from aks_fleet_efficiency.models import CollectionStatus

MAXIMUM_AI_INPUT_BYTES = 128 * 1024 * 1024


def _identity_digest(*parts: str) -> str:
    return sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def export_ai_evidence(
    directories: list[Path], *, tenant_id: str, as_of: datetime, ttl_seconds: int = 3600
) -> AIEvidencePackage:
    generated_at = _utc(as_of)
    tenant = UUID(tenant_id)
    if not 1 <= len(directories) <= 16:
        raise ValueError("AI export requires one to 16 original artifact bundles")
    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not 60 <= ttl_seconds <= 3600
    ):
        raise ValueError("AI package lifetime must be 60 to 3600 seconds")
    assessments = []
    records = []
    remaining = MAXIMUM_AI_INPUT_BYTES
    expires_at = generated_at + timedelta(seconds=ttl_seconds)
    for directory in directories:
        archive, assessment, config = _read_verified_archive(
            directory, tenant_id=tenant, maximum_bytes=remaining
        )
        remaining -= sum(len(text.encode()) for text in archive.payloads.values())
        report = assessment.report
        if len(assessment.snapshot.clusters) != 1:
            raise ValueError("AI export requires one exact cluster per assessment")
        cluster = assessment.snapshot.clusters[0]
        if cluster.uid is None or not cluster.uid.strip():
            raise ValueError("AI export requires an exact cluster fingerprint")
        run_id = _digest(archive)
        scope_id = _identity_digest(str(tenant), cluster.resource_id, cluster.uid)
        valid_until = report.generated_at + timedelta(
            hours=config.thresholds.maximum_evidence_age_hours
        )
        expires_at = min(expires_at, valid_until)
        assert report.snapshot_digest is not None and report.configuration_digest is not None
        assessments.append(
            AIAssessmentReference(
                run_id=run_id,
                scope_id=scope_id,
                snapshot_digest=report.snapshot_digest,
                configuration_digest=report.configuration_digest,
                evaluated_at=report.generated_at,
                valid_until=valid_until,
                window_start=report.observation_window.start,
                window_end=report.observation_window.end,
                status=assessment.status,
                mode=report.mode,
            )
        )
        for finding in report.recommendations:
            records.append(
                AIFindingSummary(
                    record_id=_identity_digest(run_id, finding.id),
                    run_id=run_id,
                    scope_id=scope_id,
                    resource_digest=_identity_digest(str(tenant), finding.resource_id),
                    rule_id=finding.rule_id,
                    rule_version=finding.rule_version,
                    state="finding",
                    severity=finding.severity,
                    confidence=finding.confidence,
                    reason_digests=(),
                )
            )
        for blocked in report.blocked_recommendations:
            records.append(
                AIFindingSummary(
                    record_id=_identity_digest(run_id, blocked.id),
                    run_id=run_id,
                    scope_id=scope_id,
                    resource_digest=_identity_digest(str(tenant), blocked.resource_id),
                    rule_id=blocked.rule_id,
                    rule_version=blocked.rule_version,
                    state="blocked",
                    severity=None,
                    confidence=None,
                    reason_digests=tuple(
                        sorted({_identity_digest(reason) for reason in blocked.reason_codes})
                    ),
                )
            )
        if len(records) > 128:
            raise ValueError(
                "AI export exceeds the summary record budget; narrow selected assessments"
            )
    package = AIEvidencePackage(
        tenant_digest=_identity_digest(str(tenant)),
        generated_at=generated_at,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
        assessments=tuple(sorted(assessments, key=lambda item: item.run_id)),
        records=tuple(sorted(records, key=lambda item: item.record_id)),
    )
    if len((package.model_dump_json(indent=2) + "\n").encode()) > MAXIMUM_AI_PACKAGE_BYTES:
        raise ValueError("AI package exceeds the byte limit")
    return package


def _matched_measurement_quality(
    directory: Path, fragments: AssessmentFragments, tenant_id: str
) -> dict[str, AIResourceQuality]:
    from aks_fleet_efficiency.catalog import digest_json, load_catalog
    from aks_fleet_efficiency.catalog.models import RenderedQuery
    from aks_fleet_efficiency.collectors.metric_queries import render_query
    from aks_fleet_efficiency.operator import retained_query_quality

    result = {}
    catalog = load_catalog()
    for fragment in fragments.metrics:
        profile = fragment.source_profile
        if (
            profile is None
            or profile.identity == "name-only"
            or catalog.sources.get(profile.id) != profile
        ):
            continue
        queries = {}
        for observation in fragment.observations:
            if observation.metric not in {
                "cpu_request",
                "cpu_usage",
                "memory_request",
                "memory_usage",
            }:
                continue
            quality = observation.quality
            asset = catalog.queries.get(observation.metric)
            if (
                asset is None
                or not quality.query_expression
                or quality.query_asset_version != asset.version
                or not 1 <= quality.step_seconds <= 300
            ):
                continue
            entity = observation.entity
            fields = ("cluster_resource_id", "namespace", "workload_kind", "workload", "container")
            if entity.kind != "container" or not all(field in profile.labels for field in fields):
                continue
            labels = {profile.labels[field]: str(getattr(entity, field)) for field in fields}
            labels.update(workload_uid=str(entity.workload_uid), pod_uid=str(entity.pod_uid))
            if len(labels) != 7 or quality.query_expression != render_query(
                asset.expression, labels, quality.step_seconds
            ):
                continue
            query = RenderedQuery.model_validate(
                {
                    "metric": observation.metric,
                    "version": asset.version,
                    "source": fragment.source_name,
                    "expression": quality.query_expression,
                    "expression_digest": sha256(
                        quality.query_expression.encode("utf-8")
                    ).hexdigest(),
                    "entity_digest": digest_json(observation.entity.model_dump(mode="json")),
                    "step_seconds": quality.step_seconds,
                }
            )
            queries[(query.metric, query.entity_digest)] = query
        if not queries:
            continue
        retained = retained_query_quality(
            directory, list(queries.values()), profile, tenant_id=tenant_id
        )
        for record in retained.records:
            if record.status != "matched" or record.quality is None:
                continue
            quality = record.quality
            receipt = next(
                item
                for item in retained.receipts
                if digest_json(item.model_dump(mode="json")) == record.receipt_digest
            )
            assert quality is not None and receipt.source_observed_at is not None
            assert record.latest_sample_at is not None and record.observation_digest is not None
            assert record.source_profile_digest is not None and record.receipt_digest is not None
            if receipt.source_observed_at < quality.window.end:
                continue
            result[record.observation_digest] = AIResourceQuality(
                qualified_at=retained.evaluated_at,
                observed_at=quality.observed_at,
                source_observed_at=receipt.source_observed_at,
                latest_sample_at=record.latest_sample_at,
                window_start=quality.window.start,
                window_end=quality.window.end,
                step_seconds=quality.step_seconds,
                sample_count=quality.window.sample_count,
                coverage_ratio=quality.window.coverage_ratio,
                source_digest=_identity_digest(record.query.source),
                source_profile_digest=record.source_profile_digest,
                receipt_digest=record.receipt_digest,
                observation_digest=record.observation_digest,
                query_expression_digest=record.query.expression_digest,
                query_asset_version=record.query.version,
                adapter_version="1.0",
            )
    return result


def export_ai_measurements(
    directories: list[Path], *, tenant_id: str, as_of: datetime, ttl_seconds: int = 3600
) -> AIResourceEvidencePackage:
    summary = export_ai_evidence(
        directories, tenant_id=tenant_id, as_of=as_of, ttl_seconds=ttl_seconds
    )
    references = {item.run_id: item for item in summary.assessments}
    measurements = []
    remaining = MAXIMUM_AI_INPUT_BYTES
    dimensions: tuple[MeasurementDimension, ...] = (
        "cpu_request",
        "cpu_usage_p95",
        "memory_request",
        "memory_usage_p99",
    )
    for directory in directories:
        archive, assessment, configuration = _read_verified_archive(
            directory, tenant_id=UUID(tenant_id), maximum_bytes=remaining
        )
        remaining -= sum(len(value.encode("utf-8")) for value in archive.payloads.values())
        run_id = _digest(archive)
        if run_id not in references:
            raise ValueError("Measurement originals changed after summary admission")
        reference = references[run_id]
        cluster = assessment.snapshot.clusters[0]
        fragments = AssessmentFragments.model_validate_json(archive.payloads["fragments.json"])
        matched = _matched_measurement_quality(directory, fragments, tenant_id)
        metadata = [
            item for item in fragments.kubernetes if item.cluster_resource_id == cluster.resource_id
        ]
        metadata_valid = (
            len(metadata) == 1
            and metadata[0].cluster_uid == cluster.uid
            and metadata[0].collection.status == CollectionStatus.COMPLETE
            and metadata[0].collection.source_observed_at is not None
            and metadata[0].generated_at <= reference.evaluated_at
            and (reference.evaluated_at - metadata[0].collection.source_observed_at).total_seconds()
            <= configuration.thresholds.maximum_evidence_age_hours * 3600
            and [
                item.uid
                for item in metadata[0].resources
                if item.kind == "Namespace"
                and item.api_version == "v1"
                and item.name == "kube-system"
            ]
            == [cluster.uid]
        )
        for workload in cluster.workloads:
            namespaces = (
                [
                    item
                    for item in metadata[0].resources
                    if item.kind == "Namespace"
                    and item.api_version == "v1"
                    and item.name == workload.namespace
                ]
                if metadata_valid
                else []
            )
            for container in workload.containers:
                subject = _identity_digest(
                    str(UUID(tenant_id)),
                    cluster.resource_id,
                    cluster.uid or "",
                    namespaces[0].uid if len(namespaces) == 1 else "",
                    workload.namespace,
                    workload.uid or "",
                    container.name,
                )
                resources = container.resources
                values: dict[MeasurementDimension, tuple[str, float | None]] = {
                    "cpu_request": ("cpu_request", resources.request_cpu_mcores),
                    "cpu_usage_p95": ("cpu_usage", resources.usage_cpu_p95_mcores),
                    "memory_request": ("memory_request", resources.request_memory_mib),
                    "memory_usage_p99": ("memory_usage", resources.usage_memory_p99_mib),
                }
                for dimension in dimensions:
                    metric, value = values[dimension]
                    observations = [
                        observation
                        for fragment in fragments.metrics
                        for observation in fragment.observations
                        if observation.metric == metric
                        and observation.entity.kind == "container"
                        and observation.entity.cluster_resource_id == cluster.resource_id
                        and observation.entity.namespace == workload.namespace
                        and observation.entity.workload_uid == workload.uid
                        and observation.entity.workload_kind == workload.kind
                        and observation.entity.workload == workload.name
                        and observation.entity.container == container.name
                        and observation.entity.pod_uid is not None
                    ]
                    admitted_quality = None
                    if (
                        metadata_valid
                        and len(namespaces) == 1
                        and workload.uid
                        and len(observations) == 1
                    ):
                        observation = observations[0]
                        pods = [
                            item
                            for item in metadata[0].resources
                            if item.kind == "Pod"
                            and item.uid == observation.entity.pod_uid
                            and item.namespace == workload.namespace
                        ]
                        bound = (
                            len(pods) == 1
                            and metadata[0].workload_bindings.get(pods[0].uid) == workload.uid
                        )
                        statistic = (
                            observation.p95
                            if dimension == "cpu_usage_p95"
                            else observation.p99
                            if dimension == "memory_usage_p99"
                            else observation.minimum
                        )
                        if bound and value is not None and value >= 0 and statistic == value:
                            from aks_fleet_efficiency.catalog import digest_json

                            admitted_quality = matched.get(
                                digest_json(observation.model_dump(mode="json"))
                            )
                            if dimension in {"cpu_request", "memory_request"} and not (
                                observation.minimum
                                == observation.maximum
                                == observation.quality.minimum
                                == observation.quality.maximum
                                == value
                            ):
                                admitted_quality = None
                    measurements.append(
                        AIResourceMeasurement(
                            record_id=_identity_digest(run_id, subject, dimension),
                            run_id=run_id,
                            scope_id=reference.scope_id,
                            subject_digest=subject,
                            dimension=dimension,
                            unit="mCPU" if dimension.startswith("cpu_") else "MiB",
                            status="observed" if admitted_quality is not None else "withheld",
                            value=value if admitted_quality is not None else None,
                            reason_codes=()
                            if admitted_quality is not None
                            else ("executed_provenance_unavailable",),
                            quality=admitted_quality,
                        )
                    )
                if len(measurements) > 512:
                    raise ValueError("AI measurement export exceeds its record budget")
    package = AIResourceEvidencePackage(
        summary=summary, measurements=tuple(sorted(measurements, key=lambda item: item.record_id))
    )
    if len((package.model_dump_json(indent=2) + "\n").encode("utf-8")) > MAXIMUM_AI_PACKAGE_BYTES:
        raise ValueError("AI measurement package exceeds its byte budget")
    return package


def validate_ai_measurements(
    directories: list[Path], *, package: object, tenant_id: str, as_of: datetime
) -> AIResourceEvidencePackage:
    try:
        candidate = AIResourceEvidencePackage.model_validate(
            package.model_dump() if isinstance(package, AIResourceEvidencePackage) else package
        )
    except ValueError:
        raise ValueError("Invalid closed richer-evidence package") from None
    clock = _utc(as_of)
    if not candidate.summary.generated_at <= clock < candidate.summary.expires_at:
        raise ValueError("Richer-evidence package is future or expired")
    if len(candidate.model_dump_json().encode("utf-8")) > MAXIMUM_AI_PACKAGE_BYTES:
        raise ValueError("Richer-evidence package exceeds its byte budget")
    original = export_ai_measurements(
        directories,
        tenant_id=tenant_id,
        as_of=candidate.summary.generated_at,
        ttl_seconds=candidate.summary.ttl_seconds,
    )
    if original != candidate:
        raise ValueError("Richer-evidence package must exactly match regeneration from originals")
    return original


def _regenerate_ai_package(
    directories: list[Path],
    *,
    tenant_id: str,
    package: AIEvidencePackage,
) -> AIEvidencePackage:
    package = AIEvidencePackage.model_validate(package.model_dump())
    original = export_ai_evidence(
        directories,
        tenant_id=tenant_id,
        as_of=package.generated_at,
        ttl_seconds=package.ttl_seconds,
    )
    if content_digest(package) != content_digest(original):
        raise ValueError("AI package must match the original verified assessment artifacts")
    return original


def validate_ai_explanation(
    directories: list[Path],
    *,
    tenant_id: str,
    package: AIEvidencePackage,
    payload: str,
    as_of: datetime,
) -> AIExplanation:
    original = _regenerate_ai_package(directories, tenant_id=tenant_id, package=package)
    return admit_ai_explanation(payload, package=original, as_of=as_of)


def validate_ai_checklist(
    directories: list[Path],
    *,
    tenant_id: str,
    package: AIEvidencePackage,
    intent: AIReviewIntent,
    payload: str,
    as_of: datetime,
) -> AIChecklist:
    original = _regenerate_ai_package(directories, tenant_id=tenant_id, package=package)
    return admit_ai_checklist(payload, package=original, intent=intent, as_of=as_of)


def validate_ai_experiment(
    directories: list[Path],
    *,
    tenant_id: str,
    package: AIEvidencePackage,
    intent: AIExperimentIntent,
    payload: str,
    as_of: datetime,
) -> AIExperiment:
    original = _regenerate_ai_package(directories, tenant_id=tenant_id, package=package)
    return admit_ai_experiment(payload, package=original, intent=intent, as_of=as_of)
